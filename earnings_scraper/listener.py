"""The wire listener: subscribe, detect, parse, score, pop.

Runs on the SDK's reader thread. Does NOT touch Tk -- finished cards go to
CardPopup.submit(), which is queue-based and thread-safe.

mode='full' is mandatory. Verified against news.log: in headlines mode wire
items carry no `body` at all (0 of 641 lines had one) and the `teaser` truncates
at ~140 characters, mid-sentence, before any figures appear.
"""

import io
import json
import re
import threading
import os
import time

from . import backfill
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from . import config, detect, gate, parse, revisions, score, scorecard
from scraper import passthrough



def _wire_card(ticker, item):
    """The INSTANT card: the release's own words, quoted, nothing parsed.

    ★★★ NO HERO ROWS ARE POSSIBLE HERE AND THAT IS NOT A BUG. The wire
    delivers PROSE; cells.py anchors on <td>; a body with no tables yields
    no cells and therefore no graded row. Parsing numbers out of wire
    prose is exactly what the retired flash channel did, and measured
    against the source releases it was WRONG ON FOUR OF FOUR -- Amazon's
    "+39.3%" was the AWS segment rate against a total of 12%, Intel's
    43.0% was GAAP printed beside a non-GAAP margin.

    ★★ SO THIS QUOTES INSTEAD. Headline, highlights and outlook come
    straight out of the body; on a release like Palantir's the headline
    alone carries both growth rates and both raised guides. The graded
    rows arrive on the 8-K path a minute or two later.

    ★ IF THE FENCES FIND NOTHING, SHOW THE TOP OF THE BODY RAW rather
    than an empty window. The wire body's shape has never been captured
    in full mode, so a fence that misses is the expected failure, and
    raw text is still the information.
    """
    body = (item.get('body') or '').strip()
    head = (item.get('headline') or '').strip()
    out = ['%s  WIRE  %s' % (ticker, time.strftime('%H:%M:%S')),
           '',
           'SOURCE TEXT ONLY - the wire carries no tables, so no hero row',
           'is graded here. The 8-K card follows with the numbers.']
    try:
        blocks = passthrough.blocks(body)
    except Exception:                                       # noqa: BLE001
        blocks = []
    # ★ ONE HEADLINE BLOCK, MERGED. Apple's headline is THREE lines -- the
    # title plus two subheads naming which records were set -- and the
    # wire's `headline` field carries only the first. Skipping the parsed
    # block to avoid repeating line 1 threw the subheads away; emitting
    # both printed the same header twice.
    hl = [head] if head else []
    for title, lines in blocks:
        if title == 'HEADLINE':
            hl += [ln for ln in lines
                   if ln.strip() and ln.strip() != head.strip()]
    if hl:
        out += ['', '>> HEADLINE - VERBATIM FROM THE WIRE, NOT PARSED']
        out += ['>> %s' % ln for ln in hl]
    for title, lines in blocks:
        if title == 'HEADLINE':
            continue
        out.append('')
        out.append('>> %s - VERBATIM FROM THE WIRE, NOT PARSED' % title)
        out.extend('>> %s' % ln for ln in lines)
    if not blocks and body:
        out += ['', '>> BODY (no section fence matched) - VERBATIM, FIRST 40 LINES']
        out.extend('>> %s' % ln.strip()
                   for ln in body.splitlines()[:40] if ln.strip())
    if not body:
        out += ['', 'NO BODY ON THIS FRAME - headlines mode, or the source '
                'strips it. Re-run with --mode full.']
    return chr(10).join(out)


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
        #: the canonical backfill is a NETWORK dependency in the
        #: process that makes the card. It runs after delivery and
        #: fails as a no-op, but it is named here so it can be
        #: turned off without editing the emit path.
        self.backfill_enabled = True
        self.on_card = on_card
        self.verbose = verbose
        self.log_hits = log_hits
        self._seen_ids = set()
        self._dropped_watched = set()
        self._filing_shape_shown = False
        # ★ Set on shutdown so the wire pump can tell "asked to stop" from
        # "subscription died". Without it, an ended subscription and a clean
        # Ctrl+C are indistinguishable.
        self.stop_requested = False
        # ★ Transport liveness. Distinguishes an IDLE wire (nothing being read)
        # from a QUIET one (read fine, nothing to say). Last night those two
        # looked identical for four hours.
        self.started_at = time.time()
        self.first_frame_at = None
        self._last_beat = self.started_at
        self._dead_warned = False
        self.heartbeat_seconds = 60.0
        self.first_frame_deadline = 30.0
        self.stats = dict(items=0, wire_items=0, candidates=0, cards=0,
                          rejected=0, off_watchlist=0, no_card=0, errors=0)

    # --- liveness -------------------------------------------------------------

    def tick(self, now=None):
        """Called from the wire pump between drains. Prints, returns nothing.

        ★ Two jobs, both about telling IDLE from QUIET:

        1. A FIRST-FRAME WATCHDOG. If nothing at all has arrived within
           `first_frame_deadline`, the transport is suspect -- said ONCE, with
           the base rate attached so the operator can judge it against the
           clock.
        2. A HEARTBEAT every `heartbeat_seconds`: frames read, wire items,
           watchlist matches, cards. An idle wire and a quiet wire produce
           different numbers here, which is the whole point -- last night they
           were indistinguishable without waiting for a print that never came.
        """
        now = now or time.time()

        if self.first_frame_at is None and not self._dead_warned:
            waited = now - self.started_at
            if waited >= self.first_frame_deadline:
                self._dead_warned = True
                hour = time.gmtime(now).tm_hour
                busy = 10 <= hour <= 23
                print('')
                print('=' * 78)
                print('NO FRAMES IN %.0f SECONDS — the transport may be dead.'
                      % waited)
                print('   Measured over 36,213 real frames: the median gap '
                      'between frames is 0.0s')
                print('   and p99 is 34s. At 20Z (16:00 ET) the feed runs ~188 '
                      'frames/MINUTE.')
                if busy:
                    print('   It is %02dZ, inside the busy window — %.0fs of '
                          'total silence is NOT' % (hour, waited))
                    print('   normal. Check the subscription before the next '
                          'print.')
                else:
                    print('   It is %02dZ. Overnight (02Z-06Z) the feed drops '
                          'to 1-59 frames per HOUR,' % hour)
                    print('   so this may simply be a quiet wire. Re-check '
                          'inside market hours.')
                print('=' * 78)

        if now - self._last_beat >= self.heartbeat_seconds:
            self._last_beat = now
            st = self.stats
            up = now - self.started_at
            print('   [%s] up %dm · %d frames · %d wire · %d matched · '
                  '%d cards · %d no-card%s'
                  % (time.strftime('%H:%M:%S'), int(up // 60), st['items'],
                     st['wire_items'], st['candidates'] - st['off_watchlist'],
                     st['cards'], st['no_card'],
                     '' if self.first_frame_at else '  ⛔ NOTHING READ YET'))

    # --- the hot path ---------------------------------------------------------

    def _filing_tickers(self, item):
        """Tickers on a filing frame, tolerating an unknown field shape.

        ★ detect.extract_tickers wants 'EQ:US:META' in
        primary_instruments; a filing frame may carry 'US:META', or put it
        in 'instrument' singular. The shape is unverified, so every
        plausible one is tried rather than assumed.
        """
        found = []
        try:
            ticks, _how = detect.extract_tickers(item, self.entries)
            found.extend(ticks or [])
        except Exception:                               # noqa: BLE001
            pass
        raw = []
        for key in ('primary_instruments', 'instruments', 'instrument',
                    'symbol', 'symbols', 'ticker'):
            v = item.get(key)
            if isinstance(v, str):
                raw.append(v)
            elif isinstance(v, (list, tuple)):
                raw.extend(str(x) for x in v)
        for one in raw:
            tail = str(one).split(':')[-1].strip().upper()
            if tail and tail not in found:
                found.append(tail)
        head = (item.get('headline') or '').upper()
        for t in self.entries:
            if t in found:
                continue
            if re.search(r'\b%s\b' % re.escape(t), head):
                found.append(t)
        return [t for t in found if t in self.entries]

    def _flash(self, ticker, item, parsed, how):
        """The prose read, LOGGED not displayed. Never raises.

        ★★★★ RETIRED FROM STDOUT 2026-10-29. Measured against the source
        releases it was wrong on four of four rows where the selector was
        right: Amazon's 'revenue YoY +39.3%' is the AWS SEGMENT growth
        rate against a total of 12%; both revenue figures were prose
        roundings of statement numbers (201,900 for 201,944; 16,500 for
        16,513); and Intel's 43.0% gross margin printed beside a non-GAAP
        operating margin, silently mixing bases on adjacent lines.

        ★★ IT STILL RUNS. The disagreement between this channel and the
        table channel is the only evidence that decides whether a prose
        reader is worth re-displaying, and deleting the path would delete
        the comparison. One line to stdout so the run is auditable; the
        figures go to scraper/logs/.
        """
        try:
            figs = _raw_figures(parsed) or {}
        except Exception:                               # noqa: BLE001
            figs = {}
        print('   . flash read %d figure(s) from %s - logged, not shown'
              % (len(figs), how))
        try:
            self._log_flash(ticker, item, figs, how)
        except Exception:                               # noqa: BLE001
            pass

    def _log_flash(self, ticker, item, figs, how):
        """scraper/logs/flash_<TICKER>_<date>.json -- the diff corpus."""
        import json as _json
        root = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'scraper', 'logs')
        if not os.path.isdir(root):
            os.makedirs(root)
        path = os.path.join(root, 'flash_%s_%s.json'
                            % (ticker, time.strftime('%Y-%m-%d')))
        payload = {'ticker': ticker, 'channel': 'prose',
                   'source': how,
                   'headline': (item.get('headline') or '')[:200],
                   'readAt': time.strftime('%Y-%m-%dT%H:%M:%S'),
                   'figures': dict((k, str(v)) for k, v in figs.items())}
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(_json.dumps(payload, indent=1, ensure_ascii=False))

    def _announce_drop(self, item, kind, src):
        """One line when a DROPPED frame names a watchlist ticker."""
        self.stats['dropped'] = self.stats.get('dropped', 0) + 1
        try:
            ticks, _how = detect.extract_tickers(item, self.entries)
        except Exception:                               # noqa: BLE001
            return
        watched = [t for t in (ticks or []) if t in self.entries]
        if not watched:
            return
        key = (src, tuple(watched))
        if key in self._dropped_watched:
            return
        self._dropped_watched.add(key)
        print('')
        print('=' * 78)
        print('DROPPED \u2014 %s on source %r, which is NOT SUBSCRIBED.'
              % (chr(44).join(watched), src))
        print('   msg_type=%r  headline: %s'
              % (kind, (item.get('headline') or '')[:58]))
        print('   It named a ticker you are waiting for, and was thrown away.')
        print('   Subscribed: %s' % (chr(44).join(config.ALL_SOURCES),))
        print('=' * 78)

    def _on_filing(self, item):
        """An SEC filing frame: fetch the exhibit and score from IT.

        ★★★ THE DOCUMENT THE SPECS DESCRIBE. The wire body and the 8-K
        EX-99.1 are different shapes -- a 49-line fence on the exhibit
        is 1,517 lines on the wire with the same anchors and every
        authored string present. Three prints failed on that.
        """
        self.stats['filings'] = self.stats.get('filings', 0) + 1
        form = str(item.get('form_type') or item.get('form') or '')
        watched = self._filing_tickers(item)
        if not watched:
            # ★★★★ NO REAL EDG FRAME HAS EVER BEEN SEEN, so its shape is a
            # guess. An unresolved filing must NOT vanish the way last
            # night's wire frames did -- it prints once per source so the
            # real field names can be read off the terminal and wired.
            if not self._filing_shape_shown:
                self._filing_shape_shown = True
                print('')
                print('=' * 78)
                print('FILING FRAME, TICKER UNRESOLVED — form=%r' % (form,))
                print('   fields: %s'
                      % ', '.join('%s=%r' % (k, str(v)[:28])
                                  for k, v in sorted(item.items())
                                  if k != 'body'))
                print('   Nothing dropped silently: paste this and the '
                      'resolver gets the real shape.')
                print('=' * 78)
            return
        # ★ AN 8-K IS NOT NECESSARILY EARNINGS -- 62% of them are not,
        # measured over 3,893 filings for the 57 library tickers. The
        # exhibit fetch re-checks Item 2.02 itself, so a non-earnings
        # filing costs one refusal and no card.
        if form and '8-K' not in form:
            print('   \u00b7 %s filed %s \u2014 not an 8-K, ignored'
                  % (chr(44).join(watched), form))
            return
        print('')
        print('=' * 78)
        print('SEC FILING \u2014 %s %s. Fetching the exhibit.'
              % (chr(44).join(watched), form or '8-K'))
        print('=' * 78)
        for ticker in watched:
            self._score_from_filing(ticker, item)

    def _score_from_filing(self, ticker, item):
        """Render the EX-99.1 through the SELECTOR. No grading, ever.

        ★★★★★ NO CELLS -> NO ROWS. NEVER FALL BACK TO PROSE.

        This path used to run parse -> score -> scorecard on the exhibit's
        STRIPPED TEXT. sec.press_release returns text, so cells.from_html
        could never run, the table scan came back empty, and an empty scan
        was treated as "try something else" instead of "there is nothing
        here". The prose matcher then took the first "revenue ... $X
        billion" phrase in the document -- Palantir's U.S. REVENUE bullet,
        1937.0 -- paired it with a growth rate lifted from a DIFFERENT
        bullet (148%, U.S. commercial), named it 3Q Revenue, compared it
        to a bogey of 2320 and printed "missed bogey". Total revenue was
        2,313,411 and it CLEARED. The most important row of the night,
        graded backwards, live.

        The prose matcher was not the bug. The FALLBACK was. A blank row
        is honest; a prose-derived row wearing a hero's name is not.

        ★★★ AND THE SCRAPER DOES NOT GRADE. No bogey, no street, no
        beat/miss, no branch, no score. Those are judgments and they
        happen in chat. The bogey comparison that produced 1937.0 was only
        possible because a bogey was in scope at all.
        """
        from . import sec
        from earnings_scraper import cells
        from scraper import prose_guidance as PG
        from scraper import selector as S

        labels, _drift = self._card_labels(ticker)
        t0 = time.perf_counter()
        html, url, outcome = self._exhibit_html(ticker)
        if not html:
            print('   %s: exhibit %s - wire card stands' % (ticker, outcome))
            return
        rows = cells.from_html(html)
        text = sec.to_text(html)
        if not rows:
            # ★ THE INVARIANT, STATED ON THE CARD. Zero rows is the answer,
            # not a reason to go looking somewhere softer.
            print('')
            print('=' * 78)
            print('%s  NO TABLE CELLS IN THE EXHIBIT - ZERO HERO ROWS BY '
                  'DESIGN.' % ticker)
            print('   The source blocks below are verbatim. Nothing was '
                  'parsed out of prose.')
            print('=' * 78)
        try:
            res = S.select(rows, ticker, prose_rows=PG.from_text(text))
            # ★★ THE THREE-SECTION CARD IS WHAT POPS. CURRENT QUARTER /
            # NEXT QUARTER / FULL YEAR, the profile's preset KPIs under
            # each, nothing else. The diagnostics, the universal dump and
            # the reconciliation footer are in S.report and reachable by
            # `scrape_print.py --full`; at 16:05 they are lines between
            # the reader and the numbers.
            rendered = S.card(res, ticker, labels.get('quarter') or '',
                              source_text=text)
        except Exception as exc:                        # noqa: BLE001
            print('   %s: rendering the exhibit raised %r' % (ticker, exc))
            return
        ms = round((time.perf_counter() - t0) * 1000, 2)
        card = {'ticker': ticker, 'quarter': labels.get('quarter') or '',
                'rendered': rendered, 'documentSource': 'SEC-8K',
                'documentUrl': url, 'latencyMs': ms,
                'wire': 'SEC 8-K EX-99.1'}
        print('   %s: exhibit OK, %d cells, %.0f ms' % (ticker, len(rows), ms))
        self.stats['cards'] += 1
        self._emit(card, item)

    def _exhibit_html(self, ticker):
        """(html, url, outcome) -- the RAW HTML, because tables are the point.

        sec.press_release returns stripped TEXT and that is what starved
        the old path into prose. Same transport, same Item 2.02 filter,
        HTML kept.
        """
        from . import sec
        try:
            cik = sec.cik_for(ticker)
            if not cik:
                return None, None, sec.NO_CIK
            accession, _accepted = sec.filing_on(cik)
            if not accession:
                return None, None, sec.NO_FILING
            for url in sec.exhibit_candidates(cik, accession)[:6]:
                html, _st = sec._get(url, sec.DEFAULT_TIMEOUT)
                if html and html.lower().count('<td') > 20:
                    return html, url, sec.OK
            return None, None, sec.NO_EXHIBIT
        except Exception as exc:                        # noqa: BLE001
            return None, None, '%s: %s' % (type(exc).__name__, exc)

    #: ★★★★★ EVERY FIELD THE LISTENER MAY HOLD FROM THE LIBRARY. Three.
    #: `card = dict(entry)` spread FORTY-EIGHT keys onto a live card --
    #: revBogey, epsBogey, revConsensus, epsConsensus, bogeyMethod,
    #: impliedMove, scenarioLadder, band, score10, signModifier. Nothing
    #: rendered them, and that is exactly the state scoring was in before
    #: 2026-11-02, when a bogey that was merely IN SCOPE reached the card
    #: and graded Palantir's revenue backwards.
    #:
    #: "Present but unused" is not a stable condition. The scraper pulls
    #: numbers; consensus and bogeys belong to the scorecard, in chat.
    #: To add a field here, name it -- never widen this back to a spread.
    CARD_FIELDS = ('ticker', 'quarter', 'error')

    def _card_labels(self, ticker):
        """(labels, drift) -- ONLY what the card header needs."""
        entry, drift = self._live_entry(ticker)
        return dict((k, entry.get(k)) for k in self.CARD_FIELDS), drift

    def _live_entry(self, ticker):
        """The card AS IT IS NOW, not as it was when the watchlist was built.

        THE WATCHLIST FROZE THE CONTENT. build_wide derives MEMBERSHIP
        from the library at runtime and then snapshots the whole
        prepared card into the entry, so the listener scored a 14:11
        copy of a card fixed before 15:00 -- every spec'd row refusing
        SPEC_INVALID on fields the author had already corrected, with
        nothing erroring and the stale read invisible.

        MEMBERSHIP stays frozen on purpose: who is watched tonight is a
        decision, and a ticker should not appear or vanish mid-session.
        CONTENT is re-read, because the card is the config and a config
        read once at startup is a config that silently goes stale.

        Falls back to the frozen entry on any failure: a re-read that
        raises must cost nothing, because the frozen card still scores.
        """
        frozen = self.entries.get(ticker) or {}
        if self.model is None:
            return frozen, 'no model: frozen entry'
        try:
            rec = self.model.index_for(
                time.strftime('%Y-%m-%d')).get(ticker)
            if rec is None:
                return frozen, 'not indexed today: frozen entry'
            fresh = self.model.prepare_from_record(rec)
        except Exception as exc:                        # noqa: BLE001
            return frozen, 'live read failed (%s): frozen entry' % (
                type(exc).__name__,)
        fresh['note'] = frozen.get('note')
        fresh['error'] = frozen.get('error')
        drift = _spec_drift(frozen, fresh)
        return fresh, drift


    def handle(self, item):
        self.stats['items'] += 1
        if self.first_frame_at is None:
            self.first_frame_at = time.time()
        kind = item.get('msg_type')
        src = item.get('source')

        # ★★★ A FILING IS A SECOND PASS, NOT A WIRE ITEM. It carries no
        # body worth parsing -- the exhibit is fetched by accession -- so it
        # routes away from the wire path entirely.
        if kind == 'edgar_item' or src in config.FILING_SOURCES:
            self._on_filing(item)
            return

        if kind != 'news_item' or src not in config.WIRE_SOURCES:
            # ★★★★ LAST NIGHT THIS RETURNED IN SILENCE. NFLX and SPCX both
            # printed and neither frame was ever seen; the terminal looked
            # exactly like a quiet wire. Not every drop is worth a line --
            # 38 sources at full volume would bury the signal -- but a drop
            # that NAMES A TICKER WE ARE WAITING FOR is the whole failure
            # mode, and it gets one.
            self._announce_drop(item, kind, src)
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

        # ★ DID FULL MODE ACTUALLY TAKE EFFECT? subscribe() refuses any mode
        # but 'full' -- but that checks the REQUEST, not the RESPONSE, and
        # nothing has ever verified the response because the scraper has never
        # run in full mode.
        #
        # This sits BEFORE detect deliberately. detect scores an earnings
        # headline at 0.60 with no body and 0.65 with a short one -- under its
        # threshold either way, because confidence comes mostly from figure
        # classes in the body. So a bodyless print is rejected as a near-miss
        # and an alarm placed after detection can never fire.
        #
        # Gated on the WATCHLIST so ordinary bodyless traffic is untouched:
        # ticker routing reads primary_instruments, which needs no body.
        if not (item.get('body') or '').strip():
            _tk, _ = detect.extract_tickers(item, self.entries)
            _watched = [t for t in _tk if t in self.entries]
            if _watched:
                self.stats['bodyless'] = self.stats.get('bodyless', 0) + 1
                print('')
                print('=' * 78)
                print('STOP — %s WIRE ITEM WITH NO BODY (%d so far). Full mode '
                      'is NOT in effect.'
                      % (','.join(_watched), self.stats['bodyless']))
                print('   %s carries strip_body=False -- FTI is the only one '
                      'of 38 sources that' % item.get('source'))
                print('   withholds a body -- so the source did not strip it. '
                      'Either the subscription')
                print('   is in headlines mode or the entitlement does not '
                      'grant bodies.')
                print('   NO CARD IS POSSIBLE from a headline, and this is a '
                      'ticker you are waiting')
                print('   on. Fix the subscription before the next print.')
                print('   %s' % (item.get('headline') or '')[:70])
                print('=' * 78)
                return

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
            # ★★★★★ FIGURES FIRST. Before the card, before the grade,
            # before anything that can refuse or mis-map. The numbers are
            # the deliverable at 4:01; the grade is commentary on them.
            self._flash(ticker, item, parsed,
                        config.WIRE_NAMES.get(item.get('source'),
                                              item.get('source') or '?'))
            # ONE SOURCE, READ AT SCORING TIME.
            entry, _drift = self._card_labels(ticker)
            if _drift:
                print('   * %s: %s' % (ticker, _drift))
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

            # ★★★★★ THE WIRE CARD IS VERBATIM SOURCE TEXT AND NOTHING
            # ELSE, AND NOTHING HERE GRADES. A wire body is PROSE --
            # cells.py is <td>-anchored, so there are no tables in it and
            # no hero row can be resolved from it. What CAN be shown
            # instantly is the release's own words, and an uninterpreted
            # string cannot be a wrong value.
            #
            # score_release and scorecard.diagnostics used to run here.
            # They no longer do. The scraper pulls numbers; it does not
            # decide anything about them. Scoring that merely runs is not
            # harmless -- on 2026-11-02 a bogey comparison reached the
            # card and graded Palantir's revenue BACKWARDS, and it could
            # only do that because a bogey was in scope at all.
            card = dict(entry)
            card.update(meta)
            card['rendered'] = _wire_card(ticker, item)
            card['latencyMs'] = round((time.perf_counter() - t0) * 1000, 2)
            self.stats['cards'] += 1
            self._emit(card, item)

    def _emit(self, card, item):
        path = self._persist(card, item) if self.log_hits else None
        if self.popup is not None:
            self.popup.submit(card)
        if self.on_card is not None:
            self.on_card(card)
        if self.verbose:
            self._print_summary(card)
        # ★ LAST, AND ONLY LAST. Everything above has already reached the
        # trader; the network is touched after the card exists and cannot
        # delay it.
        self._backfill_async(card, item, path)

    def _backfill_async(self, card, item, path):
        """Fetch the canonical release and fill blanks, off the card's path.

        A daemon thread so a hung socket cannot hold the listener open, and
        every exception is swallowed: the contract is that failure is a no-op
        and the card is unchanged.
        """
        if not self.backfill_enabled:
            return
        body = (item or {}).get('body') or ''
        go, _why = backfill.should_fetch(body)
        if not go:
            return
        entry = self.entries.get(card.get('ticker'))
        if not entry:
            return

        def _run():
            try:
                attempt = backfill.backfill(card.get('keyKPIs') or [],
                                            entry, body)
                self.stats['backfill'] = self.stats.get('backfill', 0) + 1
                if attempt.get('filled'):
                    print('   · canonical backfill filled %d row(s) in %sms: '
                          '%s' % (attempt['filled'], attempt.get('elapsedMs'),
                                  ', '.join(attempt.get('rows') or [])))
                else:
                    print('   · canonical backfill %s in %sms (card '
                          'unchanged)' % (attempt.get('outcome'),
                                          attempt.get('elapsedMs')))
                # ★ THE SAME FILE. A new sidecar would be a new timestamp on
                # the same ticker, which the continuation join reads as a
                # CONTINUATION PAGE -- the backfill would manufacture a
                # sibling and splice a card's own re-read onto its release.
                if path and os.path.exists(path):
                    with open(path, encoding='utf-8') as fh:
                        blob = json.load(fh)
                    blob['card'] = card
                    blob['backfillAttempt'] = attempt
                    with open(path, 'w', encoding='utf-8') as fh:
                        json.dump(blob, fh, indent=1, ensure_ascii=False,
                                  default=str)
            except Exception as exc:                     # noqa: BLE001
                print('[listener] backfill no-op: %r' % exc)

        threading.Thread(target=_run, daemon=True,
                         name='backfill-%s' % card.get('ticker')).start()

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
            return path
        except OSError as exc:
            print('[listener] could not persist sidecar: %r' % exc)
        return None

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


def _spec_drift(frozen, fresh):
    """A one-line note when the live card differs from the frozen one.

    Silence is the failure mode this exists to end: the stale read cost
    a whole print and produced no error of any kind.
    """
    a = frozen.get('keyKPIs') or []
    b = fresh.get('keyKPIs') or []
    if len(a) != len(b):
        return 'card RE-READ LIVE: %d rows -> %d' % (len(a), len(b))
    moved = sum(1 for x, y in zip(a, b)
                if (x or {}).get('extraction') != (y or {}).get('extraction'))
    if moved:
        return ('card RE-READ LIVE: %d row spec(s) changed '
                'since the watchlist was built' % moved)
    return None


def subscribe(client, listener, sources=None, mode=None):
    sources = sources or config.ALL_SOURCES
    mode = mode or config.DEFAULT_MODE
    if mode != 'full':
        raise ValueError(
            "mode must be 'full' -- headlines mode carries no body and the "
            'teaser truncates before any figures, so nothing can be graded')
    return client.subscribe_news(listener.handle, sources=sources, mode=mode)
