"""Today's watchlist, and the pre-market warm-up that makes the hot path fast.

The whole latency strategy lives here. When you paste the day's names, this
module does every expensive thing up front: load the library, index today's
PRE-EARNINGS cards, resolve each ticker's hero KPI from the profile, and pull
its consensus, bogeys and `keyKPIs` IN ORDER.

By the time a release crosses the wire, the entire expected column is resident
in memory and the print-time path touches no disk and no network.

★ THE NO-CARD RULE
A pasted ticker with no PRE-EARNINGS card reporting today is recorded as
NO_CARD and will be extracted and DISPLAYED but never graded. There is no
fallback to the most recent record and no fallback to revenue.
"""

import json
import os
import re
import time

from . import config
from .model import Model, NoCard, NoProfile


def parse_pasted(text):
    """Pull tickers out of whatever you paste.

    Accepts bare tickers, comma/space/newline separated, optionally with
    company names, times and notes. Lines beginning with # are ignored.
    Returns an ordered, de-duplicated list of (ticker, note).
    """
    out, seen = [], set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        chunks = [c.strip() for c in line.split(',') if c.strip()]
        if len(chunks) > 1 and all(
                re.fullmatch(r'[A-Za-z][A-Za-z0-9.\-]{0,6}', c) for c in chunks):
            candidates = chunks
        else:
            candidates = [line]
        for cand in candidates:
            m = re.match(r'^([A-Za-z][A-Za-z0-9.\-]{0,6})\b(.*)$', cand)
            if not m:
                continue
            ticker = m.group(1).upper()
            note = m.group(2).strip(' -–—\t,')
            if ticker in seen:
                continue
            seen.add(ticker)
            out.append((ticker, note))
    return out


def build(pasted_text, today=None, model=None):
    """Build today's watchlist with expectations warmed.

    Every pasted ticker gets an entry. Those without a card carry
    `error: "NO_CARD"` and are never graded.
    """
    t0 = time.perf_counter()
    model = model or Model()
    today = today or time.strftime('%Y-%m-%d')
    index = model.index_for(today)

    entries, problems = {}, []
    for ticker, note in parse_pasted(pasted_text):
        rec = index.get(ticker)
        if rec is None:
            entries[ticker] = dict(ticker=ticker, note=note, error='NO_CARD',
                                   message='%s: NO PRE-EARNINGS CARD — '
                                           'CANNOT SCORE' % ticker)
            problems.append('%s NO_CARD' % ticker)
            continue
        try:
            entry = model.prepare_from_record(rec)
        except NoProfile as exc:
            entries[ticker] = dict(ticker=ticker, note=note,
                                   error='NO_PROFILE', message=str(exc),
                                   recordId=rec.get('id'))
            problems.append('%s NO_PROFILE' % ticker)
            continue
        entry['note'] = note
        entry['error'] = None
        entries[ticker] = entry

    ok, invariant_msg = model.check_invariant()
    return dict(
        builtAt=time.strftime('%Y-%m-%dT%H:%M:%S'),
        today=today,
        counts=model.counts(),
        invariantHolds=ok,
        invariantMessage=invariant_msg,
        warmupMs=round((time.perf_counter() - t0) * 1000, 1),
        frameworks=model.frameworks,
        entries=entries,
        problems=problems,
    )


def save(watchlist, path=None):
    path = path or config.WATCHLIST_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    slim = dict(watchlist)
    slim['frameworks'] = sorted(watchlist.get('frameworks') or {})
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(slim, fh, indent=1, ensure_ascii=False, default=str)
    return path


def summarise(watchlist):
    """Warm-up report, so gaps are visible before the open."""
    lines = []
    c = watchlist['counts']
    entries = watchlist['entries']
    ready = [t for t, e in entries.items() if not e.get('error')]
    nocard = [t for t, e in entries.items() if e.get('error') == 'NO_CARD']
    noprof = [t for t, e in entries.items() if e.get('error') == 'NO_PROFILE']

    lines.append('Warmed in %.0f ms for %s  |  library v%s (%s)' % (
        watchlist['warmupMs'], watchlist['today'],
        c.get('libraryVersion'), c.get('libraryLastUpdated')))
    lines.append('records %d · abandoned %d (not indexed) · profiles %d · '
                 'revUnit null %d' % (c['records'], c['abandoned'],
                                      c['profiles'], c['revUnitNull']))
    lines.append('pinning set %d vs calibration.recordsUsed %s — %s' % (
        c['pinningSet'], c['calibrationRecordsUsed'],
        'invariant holds' if watchlist['invariantHolds']
        else 'DIVERGED, regenerate calibration.json'))
    lines.append('')
    lines.append('%d ticker(s): %d gradeable, %d NO_CARD, %d NO_PROFILE'
                 % (len(entries), len(ready), len(nocard), len(noprof)))
    lines.append('')

    header = ('%-7s %-11s %-30s %-9s %-5s %s'
              % ('TICKER', 'QUARTER', 'HERO KPI (graded metric)', 'REV CONS',
                 'KPIs', 'POSITIONING'))
    lines.append(header)
    lines.append('-' * len(header))
    for ticker, e in entries.items():
        if e.get('error'):
            lines.append('%-7s %s' % (ticker, e['message']))
            continue
        pos = '-'
        if e.get('score10') is not None:
            pos = '%.1f %s%s' % (e['score10'], e.get('band') or '',
                                 ' (ESTIMATE %s)' % e.get('componentsScored')
                                 if e.get('score10IsEstimate') else '')
        lines.append('%-7s %-11s %-30s %-9s %-5s %s' % (
            ticker, (e['quarter'] or '-')[:11],
            (e.get('heroName') or 'NO HERO')[:30],
            e['revConsensus'] if e['revConsensus'] is not None else '-',
            len(e['keyKPIs']) or '-', pos))

    warn = []
    if nocard:
        warn.append('NO_CARD (extract and display only, never graded): %s'
                    % ', '.join(nocard))
    if noprof:
        warn.append('NO_PROFILE (refuse to grade): %s' % ', '.join(noprof))
    review = [t for t, e in entries.items() if e.get('needsReview')]
    if review:
        warn.append('DERIVED hero profile, confirm at the next build: %s'
                    % ', '.join(review))
    nounit = [t for t, e in entries.items()
              if not e.get('error') and e.get('revUnit') is None]
    if nounit:
        warn.append('revUnit UNDECLARED, revenue will not be graded: %s'
                    % ', '.join(nounit))
    noladder = [t for t, e in entries.items()
                if not e.get('error') and not e.get('scenarioLadder')]
    if noladder:
        warn.append('no scenario ladder; a required-surprise TIER will be '
                    'shown instead of a matched branch: %s' % ', '.join(noladder))
    if warn:
        lines.append('')
        for w in warn:
            lines.append('  ! %s' % w)
    return '\n'.join(lines)


def load(path=None):
    path = path or config.WATCHLIST_PATH
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)
