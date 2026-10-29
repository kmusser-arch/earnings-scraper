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
