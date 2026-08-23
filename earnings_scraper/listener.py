"""The wire listener: subscribe, detect, parse, score, pop.

Runs on the SDK's reader thread. Does NOT touch Tk -- finished cards go to
CardPopup.submit(), which is queue-based and thread-safe.

mode='full' is mandatory. Verified against news.log: in headlines mode wire
items carry no `body` at all (0 of 641 lines had one) and the `teaser` truncates
at ~140 characters, mid-sentence, before any figures appear.
"""

import json
import os
import time

from . import config, detect, gate, parse, revisions, score, scorecard


class Listener:
    def __init__(self, watchlist, popup=None, on_card=None, verbose=True,
                 log_hits=True, model=None):
        self.watchlist = watchlist
        self.entries = watchlist.get('entries', {})
        self.model = model
        # ★ Per-session, in memory. A restart SHOULD re-score: the operator has
        # not seen a card from a session they were not watching, and swallowing
        # the first card after a crash is worse than a duplicate.
        self.revisions = revisions.RevisionLog()
        self.popup = popup
        self.on_card = on_card
        self.verbose = verbose
        self.log_hits = log_hits
        self._seen_ids = set()
        self.stats = dict(items=0, wire_items=0, candidates=0, cards=0,
                          rejected=0, off_watchlist=0, no_card=0, errors=0)

    # --- the hot path ---------------------------------------------------------

    def handle(self, item):
        self.stats['items'] += 1
        if item.get('msg_type') != 'news_item':
            return
        if item.get('source') not in config.WIRE_SOURCES:
            return
        self.stats['wire_items'] += 1

        item_id = item.get('id')
        if item_id and item_id in self._seen_ids:
            return
        if item_id:
            self._seen_ids.add(item_id)

        t0 = time.perf_counter()
        # ★ REVISION GATE, before anything expensive. 264 of 21,660 captured
        # messages are re-fires of a story already on the wire (217
        # minor-update, 47 update). Each one would otherwise push a second card
        # for a print already read -- and the second can DISAGREE with the
        # first, because the body may have changed between them.
        action, rev_note = self.revisions.classify(item)
        if action != 'score':
            if action == 'suppress-loud':
                print('')
                print('=' * 78)
                print(rev_note)
                print('   %s' % (item.get('headline') or '')[:72])
                print('=' * 78)
            else:
                print('   · %s' % rev_note)
            return
        if rev_note:
            print('   · %s' % rev_note)

        cls = detect.classify(item)
        if not cls['is_earnings']:
            self.stats['rejected'] += 1
            if self.verbose and cls['confidence'] >= 0.45:
                print('[near-miss %.2f] %-4s %s  (%s)' % (
                    cls['confidence'], item.get('source'),
                    (item.get('headline') or '')[:70], cls['reason']))
            return

        self.stats['candidates'] += 1
        tickers, tsource = detect.extract_tickers(item, self.entries)
        matched = [t for t in tickers if t in self.entries]
        if not matched:
            self.stats['off_watchlist'] += 1
            if self.verbose:
                print('[off-watchlist] %-4s %-10s %s' % (
                    item.get('source'), ','.join(tickers) or '?',
                    (item.get('headline') or '')[:66]))
            return

        parsed = parse.parse_release(item)

        for ticker in matched:
            entry = self.entries[ticker]
            meta = dict(
                wire=config.WIRE_NAMES.get(item.get('source'), item.get('source')),
                wireCode=item.get('source'),
                headline=item.get('headline'),
                itemId=item_id,
                tickerSource=tsource,
                detectConfidence=cls['confidence'],
                parsedFields=parsed['fields'],
                receivedAt=time.strftime('%H:%M:%S'))

            # ★ THE NO-CARD RULE. Extract, display, alert -- never grade.
            if entry.get('error'):
                card = dict(entry)
                card.update(meta)
                card['rawFigures'] = _raw_figures(parsed)
                card['latencyMs'] = round((time.perf_counter() - t0) * 1000, 2)
                self.stats['no_card'] += 1
                self._emit(card, item)
                continue

            try:
                card = score.score_release(parsed, entry, self.model)
            except score.AlignmentError as exc:
                # Fail loudly. Never write or display a misaligned grid.
                self.stats['errors'] += 1
                print('')
                print('!!! ALIGNMENT FAILURE on %s: %s' % (ticker, exc))
                print('!!! No card emitted. This is the silent failure mode '
                      'that broke 12 records -- fix the KPI list, do not '
                      'bypass the assertion.')
                continue
            except Exception as exc:
                self.stats['errors'] += 1
                print('[listener] scoring %s raised %r' % (ticker, exc))
                continue

            card.update(meta)
            # ★ The card's text comes from the ONE renderer. No local
            # formatting -- a second formatter drifts from the chat path.
            try:
                fw = gate.framework_from(self.model) if self.model else None
                card['rendered'] = scorecard.render_card(card, entry, fw)
            except Exception as exc:
                card['rendered'] = None
                card['renderError'] = '%s: %s' % (type(exc).__name__, exc)
            card['diagnostics'] = scorecard.diagnostics(card)
            card['latencyMs'] = round((time.perf_counter() - t0) * 1000, 2)
            self.stats['cards'] += 1
            self._emit(card, item)

    def _emit(self, card, item):
        if self.log_hits:
            self._persist(card, item)
        if self.popup is not None:
            self.popup.submit(card)
        if self.on_card is not None:
            self.on_card(card)
        if self.verbose:
            self._print_summary(card)

    # --- side outputs ---------------------------------------------------------

    def _persist(self, card, item):
        """Sidecar write. Nothing goes into earnings-library.json here.

        The library is only written after both gates pass:
            py validate_library.py   &&   node render_test.js
        """
        try:
            os.makedirs(config.PENDING_DIR, exist_ok=True)
            stamp = time.strftime('%Y%m%d-%H%M%S')
            path = os.path.join(config.PENDING_DIR, '%s-%s.json' % (
                stamp, card.get('ticker', 'UNK')))
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(dict(card=card, rawItem=item), fh, indent=1,
                          ensure_ascii=False, default=str)
        except OSError as exc:
            print('[listener] could not persist sidecar: %r' % exc)

    def _print_summary(self, card):
        """Print the rendered card verbatim. This method formats nothing."""
        print('')
        print('=' * 78)
        if card.get('error'):
            print('%s — %s   [%s, %.1f ms]' % (
                card.get('ticker'), card['error'], card.get('wire'),
                card.get('latencyMs') or 0))
            print('  %s' % (card.get('message') or ''))
            print('  NOTHING GRADED. Extracted figures:')
            for k, v in (card.get('rawFigures') or {}).items():
                print('    %-24s %s' % (k, v))
            print('=' * 78)
            return

        print('%s  [%s, %.1f ms]' % (card.get('headline') or '',
                                     card.get('wire'),
                                     card.get('latencyMs') or 0))
        print('-' * 78)
        if card.get('rendered'):
            print(card['rendered'])
        else:
            print('⛔ RENDERER UNAVAILABLE: %s' % card.get('renderError'))
            print('   No local formatting attempted — a parallel formatter '
                  'would drift from the chat path.')
        diag = card.get('diagnostics') or []
        if diag:
            print('')
            print('─' * 78)
            print('SCRAPER DIAGNOSTICS — not part of the locked format')
            print('─' * 78)
            for line in diag:
                print(line)
        print('=' * 78)


def _raw_figures(parsed):
    """Flatten a parse into displayable figures for an ungraded card."""
    out = {}
    rev = parsed.get('revenue')
    if rev:
        out['revenue ($M)'] = rev['value_musd']
        if rev.get('growth_pct') is not None:
            out['revenue YoY'] = '%+.1f%%' % rev['growth_pct']
    for basis, v in (parsed.get('eps') or {}).items():
        out['EPS (%s)' % basis] = v['value']
    for name, v in (parsed.get('margins') or {}).items():
        out[name] = '%s%%' % v['value']
    for key, g in (parsed.get('guidance') or {}).items():
        out['%s guide ($M)' % key] = '%s-%s (mid %s)' % (g['low'], g['high'],
                                                         g['mid'])
    return out


def subscribe(client, listener, sources=None, mode=None):
    sources = sources or config.WIRE_SOURCES
    mode = mode or config.DEFAULT_MODE
    if mode != 'full':
        raise ValueError(
            "mode must be 'full' -- headlines mode carries no body and the "
            'teaser truncates before any figures, so nothing can be graded')
    return client.subscribe_news(listener.handle, sources=sources, mode=mode)
