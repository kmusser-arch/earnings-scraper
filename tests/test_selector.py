# -*- coding: utf-8 -*-
r"""THE SELECTOR — acceptance, negative controls, and the live-config proof.

★ THE NEGATIVE CONTROLS ARE THE POINT. A selector that returns a plausible
number for every request is indistinguishable from one that works, and
this repo has shipped that twice.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells                          # noqa: E402
from scraper import selector as S                           # noqa: E402

SCRATCH = os.path.join(
    'C:' + os.sep, 'Users', 'Trader', 'AppData', 'Local', 'Temp', 'claude',
    'c--Users-Trader-Desktop-shelnewsapi',
    'ffea150e-3593-4826-a39c-a3639f624d0d', 'scratchpad')

ACCEPT = [
    ('INTC', 'grossMargin', 'currentQuarter', 'NON_GAAP', 44.1),
    ('INTC', 'grossMargin', 'currentQuarter', 'GAAP', 43.0),
    ('INTC', 'grossMargin', 'nextQGuidance', 'NON_GAAP', 38.0),
    ('INTC', 'grossMargin', 'nextQGuidance', 'GAAP', 37.1),
    ('INTC', 'revenue', 'currentQuarter', None, 16513.0),
    ('INTC', 'eps', 'currentQuarter', 'NON_GAAP', 0.52),
    ('INTC', 'freeCashFlow', 'currentQuarter', None, 1639.0),
    ('AMZN', 'revenue', 'currentQuarter', None, 201944.0),
    ('AMZN', 'operatingIncome', 'currentQuarter', None, 28076.0),
    ('AMZN', 'operatingMargin', 'currentQuarter', None, 13.9),
    ('AMZN', 'freeCashFlow', 'TTM', None, -42357.0),
    ('AMZN', 'capex', 'TTM', None, 210657.0),
    ('AMZN', 'operatingCashFlow', 'TTM', None, 168300.0),
]


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    # ── RULE 7 / spec: no ticker symbol in the module ────────────────────
    import re
    src = io.open(S.__file__, encoding='utf-8').read()
    hits = [t for t in ('AMZN', 'INTC', 'NFLX', 'META', 'TXN', 'LRCX',
                        'NVDA', 'MU', 'SNDK', 'ORCL', 'ADBE')
            if re.search(r'\b%s\b' % t, src)]
    check(not hits, 'no ticker symbol in selector.py: %s' % (hits or 'clean'))

    # ── CONTROL 5: the config must be real and must be counted ───────────
    profiles, mtime = S.load_profiles()
    check(len(profiles) > 0,
          'config loaded: %d tickers, %d hero rows, mtime %s'
          % (len(profiles),
             sum(len(p.get('heroKPIs') or []) for p in profiles.values()),
             time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))))
    if not profiles:
        sys.exit(1)             # a selector with no config asserts nothing

    # ── CONTROL 4: LIVE config, no restart, no regeneration ──────────────
    # ★ RUN AGAINST A COPY. The spec asks for the edit to be made directly
    # to ticker-profiles.json; that file is the upstream source of truth and
    # the same spec says DO NOT EDIT IT. A crash mid-test would leave it
    # dirty. The property under test is that a change is picked up with NO
    # restart and NO regeneration step, and a copy proves that identically.
    tmp = tempfile.mkdtemp(prefix='profiles-')
    copy = os.path.join(tmp, 'ticker-profiles.json')
    shutil.copyfile(S.PROFILES_PATH, copy)
    try:
        doc = json.load(io.open(copy, encoding='utf-8'))
        before, _m = S.load_profiles(copy)
        check('ZZZZ' not in before, 'the fake ticker is absent to begin with')
        doc['profiles']['ZZZZ'] = {'heroKPIs': [
            {'name': 'Revenue', 'priority': 1,
             'appliesTo': 'currentQuarter', 'unit': '$M'},
            {'name': 'Gross margin', 'priority': 1,
             'appliesTo': 'currentQuarter', 'unit': '%'}]}
        io.open(copy, 'w', encoding='utf-8').write(
            json.dumps(doc, ensure_ascii=False))
        after, _m = S.load_profiles(copy)
        check('ZZZZ' in after and len(after['ZZZZ']['heroKPIs']) == 2,
              'a profile added with NO restart is picked up on the next '
              'call — the config is read live, not cached')
        del doc['profiles']['ZZZZ']
        io.open(copy, 'w', encoding='utf-8').write(
            json.dumps(doc, ensure_ascii=False))
        gone, _m = S.load_profiles(copy)
        check('ZZZZ' not in gone, 'and removing it takes effect immediately')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── CONTROL 3: a ticker with no heroes ───────────────────────────────
    empty = {'EMPTYCO': {'heroKPIs': []}}
    res = S.select([{'table': 't', 'label': 'Net sales', 'period': 'Q3 2026',
                     'value': 5.0, 'raw': '5.0'}], 'EMPTYCO', profiles=empty)
    check(res['heroes'] == [] and res['notFound'] == [],
          'an empty heroKPIs list yields zero heroes and zero misses, '
          'not a crash')
    check(len(res['overflow']) == 1,
          'and the alias hit still appears as overflow, so the print is '
          'not blank: %d' % len(res['overflow']))

    # ── RULE 6c: unknown ticker is not an error ──────────────────────────
    res = S.select([{'table': 't', 'label': 'Net sales', 'period': 'Q3 2026',
                     'value': 5.0, 'raw': '5.0'}], 'NOSUCH', profiles={})
    check(res.get('noProfile') and len(res['overflow']) == 1,
          'an unmapped ticker emits noProfile + full overflow, so it still '
          'prints something readable at 4:01')

    # ── the real releases ────────────────────────────────────────────────
    paths = dict((t, os.path.join(SCRATCH, '%s.html' % t))
                 for t in ('AMZN', 'INTC'))
    if not all(os.path.exists(p) for p in paths.values()):
        print('SKIP live acceptance — exhibit fixtures not cached')
        return
    rows = dict((t, cells.from_html(io.open(p, encoding='utf-8').read()))
                for t, p in paths.items())

    bad = []
    for ticker, metric, period, basis, want in ACCEPT:
        hits = S.resolve(rows[ticker], metric, period, basis)
        got = hits[0]['value'] if hits else None
        if got != want:
            bad.append((ticker, metric, period, basis, want, got))
    check(not bad, 'all %d acceptance values resolve exactly: %s'
          % (len(ACCEPT), bad or 'clean'))

    # ── CONTROL 1: basis NEVER falls back ────────────────────────────────
    gaap_only = [r for r in rows['INTC']
                 if S.split_basis(r['label'])[0] != 'NON_GAAP']
    hits = S.resolve(gaap_only, 'grossMargin', 'currentQuarter', 'NON_GAAP')
    check(not hits,
          'asking for non-GAAP on a release carrying only GAAP returns '
          'NOTHING — substituting would answer a question nobody asked, '
          'with a number that looks right')

    # ── CONTROL 2: period must not leak actuals into a guide ─────────────
    g = S.resolve(rows['INTC'], 'revenue', 'nextQGuidance')
    check(g and g[0]['raw'].replace('$', '').replace(' ', '') == '15.0-16.0',
          'INTC revenue nextQ is the Business Outlook range %r, NOT 16,513 '
          'from the actuals' % (g[0]['raw'] if g else None))
    check(g and g[0]['value'] is None,
          'and a range carries value=None with raw intact — inventing a '
          'midpoint here would be the parser interpreting')

    # ── RULE 3: qualitative heroes are skipped, not reported missing ─────
    out = S.select(rows['INTC'], 'INTC')
    check(out['qualitative'],
          'qualitative heroes are listed separately (%d), never as NOT '
          'FOUND — a warning that fires every quarter trains you to ignore '
          'it' % len(out['qualitative']))
    check(all('NOT FOUND' not in str(q) for q in out['qualitative']),
          'and they carry no miss marker')

    t0 = time.time()
    S.select(rows['AMZN'], 'AMZN')
    ms = (time.time() - t0) * 1000
    check(ms < 500, 'select on %d parser rows in %.1f ms'
          % (len(rows['AMZN']), ms))


main()


def ranking_and_channels():
    r"""THE FIVE RANKING FIXTURES, PINNED. Each came from a wrong answer.

    ★ These are the sharpest failure class in this repo: every cell
    internally consistent, only the SELECTION wrong, and nothing
    downstream able to catch it.
    """
    paths = dict((t, os.path.join(SCRATCH, '%s.html' % t))
                 for t in ('AMZN', 'INTC'))
    if not all(os.path.exists(p) for p in paths.values()):
        print('SKIP ranking fixtures — exhibit fixtures not cached')
        return
    rows = dict((t, cells.from_html(io.open(p, encoding='utf-8').read()))
                for t, p in paths.items())

    print('')
    print('=== the five ranking terms ===')
    h = S.resolve(rows['AMZN'], 'operatingMargin', 'currentQuarter')
    check(h and h[0]['value'] == 13.9,
          '1 RECENCY (year AND quarter): 13.9 from Q3 2026, never 13.1 '
          '(Q1) or 13.7 (Q2) — "Three Months Ended" is true of all three')
    h = S.resolve(rows['AMZN'], 'capex', 'TTM')
    check(h and h[0]['value'] == 210657.0,
          '2 EXPLICIT PERIOD IN THE LABEL: 210,657 from the "-- TTM" row, '
          'not the unsuffixed cash-flow line')
    na = [r for r in rows['AMZN']
          if r['label'] == 'Net sales' and r['value'] == 112852.0]
    check(na and 'North America' in (na[0].get('section') or ''),
          '3 SEGMENT REPEATS: 112,852 carries section=%r, so North America '
          'is separable from International (43,108) and AWS (45,984)'
          % (na[0].get('section') if na else None))
    h = S.resolve(rows['INTC'], 'revenue', 'currentQuarter')
    check(h and h[0]['value'] == 16513.0,
          '4 PRECISION: 16,513 from the statements, not 16.5 from the '
          'summary')
    check(h and 'Intel Products' not in (h[0].get('period') or ''),
          '5 PERIOD QUALIFICATION: the plain header is the company, not a '
          'business unit (%r)' % (h[0]['period'][:34] if h else None))

    # ── B3: a percentage hero must never take a dollar total ─────────────
    check(S.canonical('AWS revenue growth y/y (%)') is None,
          'B3 canonical(): a segment growth RATE does not resolve to '
          '`revenue` — answering it with 201,944 is always wrong')

    print('')
    print('=== channels ===')
    out = S.select(rows['INTC'], 'INTC')
    call = [n for n in out['notFound'] if n.get('callOnly')]
    check(call,
          'CALL-ONLY is distinct from NOT FOUND: %s — a structural absence '
          'must not look like a failed match'
          % [c['hero'][:30] for c in call])
    out2 = S.select(rows['AMZN'], 'AMZN')
    prose = [n for n in out2['notFound'] if n.get('proseChannel')]
    check(prose, 'PROSE CHANNEL is flagged for rows the table cannot hold')
    na_hero = [h for h in out2['heroes']
               if h['hero'].startswith('North America revenue')]
    check(na_hero and na_hero[0]['matches'][0]['value'] == 112852.0,
          'segmentContext resolves North America to 112,852, not '
          "International's 43,108 or AWS's 45,984 (%s)"
          % (na_hero[0]['matches'][0]['value'] if na_hero else None))
    # ★ SECTION NARROWS, RECENCY CHOOSES. The filter removes the other
    # two segments; what remains is North America across several period
    # columns, and the Q3 2026 one wins on recency. Asserting a single
    # survivor would be asserting something that is not true -- the two
    # terms do different jobs and both are needed.
    others = [m for m in (na_hero[0]['matches'] if na_hero else [])
              if m['value'] in (43108.0, 45984.0)]
    check(not others,
          'and NO International (43,108) or AWS (45,984) row survives the '
          'section filter: %s' % ([m['value'] for m in others] or 'none'))
    check(not any(h.get('scaleWarning') for h in out2['heroes']),
          'and with the map declaring the DOCUMENT unit, no false scale '
          'warning fires on a correct read')


def prose_channel():
    r"""PART A — prose guidance, and the two negative controls.

    ★★ ZERO ROWS ON INTEL IS THE RESULT, not a gap. Intel's guidance is a
    table; returning anything here would double-report what the table
    parser already holds, at lower precision.
    """
    from earnings_scraper import sec
    from scraper import prose_guidance as PG
    paths = dict((t, os.path.join(SCRATCH, '%s.html' % t))
                 for t in ('AMZN', 'INTC'))
    if not all(os.path.exists(p) for p in paths.values()):
        print('SKIP prose — exhibit fixtures not cached')
        return
    txt = dict((t, sec.to_text(io.open(p, encoding='utf-8').read()))
               for t, p in paths.items())

    print('')
    print('=== prose guidance ===')
    got = PG.from_text(txt['AMZN'])
    by = dict(((g['metric'], g['period']), g) for g in got)
    rev = by.get(('revenue', 'nextQGuidance'))
    check(rev and rev['low'] == 240000.0 and rev['high'] == 247000.0,
          'AMZN revenue nextQ 240,000-247,000 from prose')
    oi = by.get(('operatingIncome', 'nextQGuidance'))
    check(oi and oi['low'] == 28500.0 and oi['high'] == 33500.0,
          'AMZN operatingIncome nextQ 28,500-33,500 from prose')
    cx = by.get(('capex', 'FY2026'))
    check(cx and cx['value'] == 220000.0,
          'AMZN capex FY2026 220,000 — a FULL-YEAR figure inside a block '
          'headed "Fourth Quarter 2026 Guidance", so the heading period '
          'must not be taken blindly')
    check(all(g['confidence'] == 'prose' and g.get('sourceSentence')
              for g in got),
          'every prose row carries confidence="prose" and the verbatim '
          'sentence — the channel has to be visible at a glance')

    check(PG.from_text(txt['INTC']) == [],
          'NEGATIVE CONTROL 1 — Intel returns ZERO rows; its guidance is a '
          'table and double-reporting it would lower the precision')
    blind = txt['AMZN'].replace('Fourth Quarter 2026 Guidance', 'XXXX') \
                       .replace('Financial Guidance', 'YYYY')
    check(PG.from_text(blind) == [],
          'NEGATIVE CONTROL 2 — with the headings gone it returns ZERO, '
          'and never falls back to scanning the body. That fallback is how '
          '201,944 would become 201,900')


ranking_and_channels()
prose_channel()
