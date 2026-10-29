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
    check(res['found'] == [] and res['notInRelease'] == [],
          'an empty heroKPIs list yields zero found and zero missing, '
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

    # ★ the qualitative taxonomy was REMOVED. A hero is found in the
    # release or it is not; there is no third category and no opinion
    # about why. What remains must add up.
    out = S.select(rows['INTC'], 'INTC')
    ok, n = S.coverage_ok(out)
    check(ok, 'found + notInRelease == heroCount (%d of %d) — completeness, '
          'not grading' % (n, out.get('heroCount')))
    check('qualitative' not in out and 'notFound' not in out,
          'and the old grading buckets are gone from the result shape')

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
    from scraper import prose_guidance as _PG
    from earnings_scraper import sec as _sec
    _p = dict((t, _PG.from_text(_sec.to_text(
        io.open(paths[t], encoding='utf-8').read()))) for t in paths)
    out = S.select(rows['INTC'], 'INTC', prose_rows=_p['INTC'])
    check([n['hero'] for n in out['notInRelease']],
          'a hero absent from the release is listed plainly, with no '
          'explanation attached: %s'
          % [n['hero'][:28] for n in out['notInRelease']])
    out2 = S.select(rows['AMZN'], 'AMZN', prose_rows=_p['AMZN'])
    prose = [f for f in out2['found'] if f.get('channel') == 'prose']
    check(len(prose) == 2,
          'prose guidance RESOLVES rather than being reported missing '
          '(%d rows), and carries channel=prose so it can never be '
          'mistaken for a statement figure' % len(prose))
    na_hero = [h for h in out2['found']
               if h['hero'].startswith('North America revenue')]
    check(na_hero and na_hero[0]['value'] == 112852.0,
          'segmentContext resolves North America to 112,852, not '
          "International's 43,108 or AWS's 45,984 (%s)"
          % (na_hero[0]['value'] if na_hero else None))
    # ★ SECTION NARROWS, RECENCY CHOOSES. The filter removes the other
    # two segments; what remains is North America across several period
    # columns, and the Q3 2026 one wins on recency. Asserting a single
    # survivor would be asserting something that is not true -- the two
    # terms do different jobs and both are needed.
    check(na_hero and na_hero[0].get('segment')
          and 'North America' in na_hero[0]['segment'],
          'and the row carries its segment, so the choice is inspectable '
          'rather than implicit: %r'
          % (na_hero[0].get('segment') if na_hero else None))
    check(all(f.get('value') is not None or f.get('low') is not None
              for f in out2['found']),
          'every found row carries a number or a range')


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


def labels_dump():
    r"""THE DUMP IS WHAT A HUMAN WRITES A MAP FROM.

    ★★★★ A PLAUSIBLE-BUT-WRONG SAMPLE GETS A BAD MAP CONFIRMED BY EYE.
    'Latest year wins' showed Amazon's North America net sales as 333,172
    -- the NINE-MONTH figure -- where the quarter is 112,852. Nine months
    is not more recent than three months, it is WIDER. That is the recency
    failure aimed at the reader instead of the selector, and the reader
    has no second check.
    """
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    fx = os.path.join(here, '..', 'scraper', 'fixtures',
                      'AMZN_2026Q3.html')
    if not os.path.exists(fx):
        print('SKIP labels dump - fixture missing')
        return
    spec = importlib.util.spec_from_file_location(
        'pk', os.path.join(here, '..', 'scraper', 'parse_kpis.py'))
    pk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pk)

    rows = cells.from_html(io.open(fx, encoding='utf-8').read())
    view = pk.labels_view(rows, section='Segment Information')
    samples = {}
    for _sec, items in view:
        for label, _tags, sample, seg in items:
            if label == 'Net sales':
                samples[seg] = sample
    print('')
    print('=== --labels sample values ===')
    check(samples.get('North America') == '112,852',
          'North America Net sales samples the QUARTER 112,852, never the '
          'nine-month 333,172 (%s)' % samples.get('North America'))
    check(samples.get('International') == '43,108',
          'International 43,108, not 125,094 (%s)'
          % samples.get('International'))
    check(samples.get('AWS') == '45,984',
          'AWS 45,984, not 125,803 (%s)' % samples.get('AWS'))

    ix = os.path.join(here, '..', 'scraper', 'fixtures', 'INTC_2026Q3.html')
    irows = cells.from_html(io.open(ix, encoding='utf-8').read())
    iview = pk.labels_view(irows, grep='gross margin')
    both = [s for _sec, items in iview for _l, _t, s, _g in items
            if 'GAAP' in s and '/' in s]
    check(both,
          'where one label carries two bases under one period, BOTH are '
          'shown: %s' % (both[:1] or 'none'))

    # ★ `table` must not creep back into the schema
    profiles, _m = S.load_profiles()
    dead = [(t, h) for t, p in profiles.items()
            for h, e in (p.get('documentLabelMap') or {}).items()
            if isinstance(e, dict) and 'table' in e]
    check(not dead,
          '`table` is gone from every map entry — it held strings the '
          'parser never emits and nothing read it, so it read as '
          'verification: %s' % (dead[:2] or 'clean'))


labels_dump()


def period_vocabulary_and_units():
    r"""READER DEFECTS 1 and 2 of the ADBE/ORCL pre-diagnosis.

    ★★★★ A MISSING PERIOD TERM IS EXPENSIVE IN ONE DIRECTION AND POISONOUS
    IN THE OTHER. Adobe heads its guidance table 'financial targets'; with
    only outlook/guidance/forecast in the vocabulary that whole table read
    as the CURRENT QUARTER, so both guidance heroes were rejected AND an
    FY target leaked into the current-quarter row as 18.12.
    """
    print('')
    print('=== forward-period vocabulary ===')
    for word in ('outlook', 'guidance', 'forecast', 'targets', 'target'):
        got = S.period_class('Q4 FY2026 %s table' % word, '')
        check(got == 'nextQGuidance',
              '%-9s heads a guidance table -> %s' % (word, got))
    # ★ the COLUMN outranks the TABLE
    check(S.period_class('2026 financial targets and assumptions',
                         'Fiscal Year 2026 Low') == 'fyGuidance',
          'a Fiscal Year COLUMN inside a targets TABLE is fyGuidance, not '
          'nextQ — scanning both together let "targets" match first and an '
          'FY figure validated clean as a next-quarter guide')
    check(S.period_class('2026 financial targets and assumptions',
                         'Q4 2026') == 'nextQGuidance',
          'while a Q4 column in the same table is the next-quarter guide')
    # ★★ the NARRATIVE VERBS are deliberately absent
    for word in ('we expect', 'expects', 'anticipate'):
        got = S.period_class('and %s margins to improve' % word, '')
        check(got != 'nextQGuidance',
              '%-11s does NOT reclassify a table (%s) — a heading here is '
              'the tail of the preceding paragraph, so a narrative verb '
              'above a current-quarter statement would turn it into '
              'guidance. Sentences belong to the prose channel.'
              % (word, got))

    print('')
    print('=== recency reads a date as a quarter ===')
    cases = [('Three Months EndedSeptember 30, 2026', 3),
             ('Three Months Ended Sep 26, 2026', 3),
             ('Three Months Ended May 29,2026', 2),
             ('Q3 2026', 3)]
    for period, want in cases:
        got = S._recency({'period': period, 'table': ''})[1]
        check(got == want, '%-38s -> Q%s' % (period[:38], got))
    check(S._recency({'period': 'prices may increase', 'table': ''})[1] == 0,
          "and 'may' in prose is not a May date — anchoring on the DAY "
          'NUMBER is what separates them')

    print('')
    print('=== unit class is a hard refusal, never a scale warning ===')
    check(S.unit_class('$M') == 'CURRENCY'
          and S.raw_class('150%') == 'PERCENT',
          'a $M hero and a 150% candidate are different CLASSES')
    rows = [{'table': 't', 'section': '', 'label': 'AI-first ARR',
             'period': 'Q3 2026', 'value': 150.0, 'raw': '150%'}]
    prof = {'Z': {'heroKPIs': [{'name': 'AI-first ARR', 'priority': 1,
                                'appliesTo': 'currentQuarter',
                                'unit': '$M'}],
                  'documentLabelMap': {
                      'AI-first ARR': {'documentLabels': ['AI-first ARR'],
                                       'unit': '$M'}}}}
    out = S.select(rows, 'Z', profiles=prof)
    check(out['found'] == [],
          'a $M hero REFUSES a percent candidate outright (%d found) - '
          'Adobe discloses AI-first ARR only as a growth rate, and binding '
          'it to a dollar hero is a 1000x disagreement that looks entirely '
          'plausible' % len(out['found']))
    check(len(out['notInRelease']) == 1,
          'and the hero is reported absent rather than answered wrongly')

    print('')
    print('=== basis is a token, not a sentence ===')
    check(S.basis_of('nonGAAP') == 'NON_GAAP'
          and S.basis_of('NON_GAAP') == 'NON_GAAP'
          and S.basis_of('gaap') == 'GAAP',
          'every spelling of a basis token resolves')
    prose = u"\u2605 GAAP row is 'Diluted net income per share' - same word"
    check(S.basis_of(prose) is None,
          'but PROSE in the basis field is refused (%r) — prefix-matching '
          'it to GAAP forced Adobe EPS to 4.62 where the adjusted answer '
          'is 6.13' % S.basis_of(prose))


period_vocabulary_and_units()


def sectioning():
    r"""HERO ROWS GROUPED BY appliesTo. Organisation only, no semantics."""
    print('')
    print('=== sections ===')
    prof = {'Z': {'heroKPIs': [
        {'name': 'CQ one', 'priority': 1, 'appliesTo': 'currentQuarter',
         'unit': '$M'},
        {'name': 'NQ one', 'priority': 1, 'appliesTo': 'nextQGuidance',
         'unit': '$M'},
        {'name': 'FY one', 'priority': 1, 'appliesTo': 'fyGuidance',
         'unit': '$M'},
        {'name': 'Odd one', 'priority': 2, 'appliesTo': 'someFutureThing',
         'unit': '$M'}]}}
    out = S.select([], 'Z', profiles=prof)
    txt = S.report(out, 'Z', 'Q3')
    for want in ('CURRENT QUARTER', 'NEXT-Q GUIDANCE', 'FY GUIDANCE'):
        check(want in txt, '%s prints even with nothing resolved — an empty '
              'FY block is a signal, a missing one is silence' % want)
    check('UNCLASSIFIED' in txt and 'someFutureThing' in txt,
          'an unrecognised appliesTo is NAMED, never defaulted to '
          'currentQuarter and never dropped')
    ok, n = S.coverage_ok(out)
    check(ok and n == 4,
          'and every hero is still accounted for across the sections '
          '(%d of %d)' % (n, out.get('heroCount')))

    # ★ a section with NO heroes is omitted entirely
    prof2 = {'Z': {'heroKPIs': [{'name': 'only CQ', 'priority': 1,
                                 'appliesTo': 'currentQuarter'}]}}
    txt2 = S.report(S.select([], 'Z', profiles=prof2), 'Z', 'Q3')
    check('CURRENT QUARTER' in txt2 and 'FY GUIDANCE' not in txt2,
          'while a section the ticker has NO heroes for is omitted')

    # ── the real fixtures ────────────────────────────────────────────────
    here = os.path.dirname(os.path.abspath(__file__))
    fx = os.path.join(here, '..', 'scraper', 'fixtures', 'INTC_2026Q3.html')
    if not os.path.exists(fx):
        return
    from scraper import prose_guidance as _PG
    from earnings_scraper import sec as _sec
    html = io.open(fx, encoding='utf-8').read()
    res = S.select(cells.from_html(html), 'INTC',
                   prose_rows=_PG.from_text(_sec.to_text(html)))
    txt = S.report(res, 'INTC', 'Q3 2026')
    cq = txt.index('CURRENT QUARTER')
    nq = txt.index('NEXT-Q GUIDANCE')
    fy = txt.index('FY GUIDANCE')
    check(cq < nq < fy,
          'the locked scorecard order holds: currentQuarter, nextQ, FY')
    tail = txt[fy:]
    check('not in release' in tail,
          "INTC's unresolved FY capex sits INSIDE the FY section, not "
          'trailing the whole block')
    check('44.1' in txt[cq:nq] and '38.0' in txt[nq:fy],
          'the two IDENTICAL gross-margin labels land in different '
          'sections — 44.1 current, 38.0 next-Q. Period is the only thing '
          'telling them apart, and the sections make that visible')

    # ★ the display normalisation, scoped to months
    check(S._despace('Three Months EndedSeptember 30, 2026')
          == 'Three Months Ended September 30, 2026',
          'the missing space in the SOURCE token is repaired for display')
    check(S._despace('nonGAAP results') == 'nonGAAP results',
          'but a deliberate intercap is left alone — scoped to month names')


sectioning()
