# -*- coding: utf-8 -*-
"""THE FIVE-CLASS COMPARATOR for vertically exploded tables.

★ WHY HEADER CLASSIFICATION IS THE ONLY OPTION, NOT THE BETTER ONE. The
wrong-column value is the same metric in the same unit, and its distance from
the right one is a function with a zero:

        wrong / right  =  prior-year-YTD / current-Q  =  2 / (1 + g)

    g =  34%  (HPE)      -> 1.49x   visible
    g =  59%  (APP)      -> 1.26x   plausible blowout
    g =  86%  (AVGO)     -> 1.075x  inside every band
    g = 100%             -> 1.00x   ★★★ IDENTICAL - nothing to detect
    g = 221%  (AVGO AI)  -> 0.62x   visible again

The invisibility zone is centred on ~100% year-on-year growth, which is the
cohort this library trades. At the centre there is no signal of any magnitude
to threshold against, so no band tuned on any corpus can transfer.

★★ MEASURED EXPOSURE BEFORE THE BUILD: 5 of 15 filled values are
table-sourced, 0 of 5 had their column verified, and 4 of 5 had an invisible
wrong-window neighbour -- 3 of those verdict-flipping:

    SNDK  gross margin   84.6 vs 78.4 prior quarter      0.93x  BEAT -> MISS
    HPE   revenue      12,213 vs 10,678 prior quarter    0.87x  BEAT -> MISS
    APP   adj EBITDA    1,614 vs 1,956 prior-year 6mo    1.21x  +21% blowout
    APP   revenue       1,924 vs 2,418 prior-year 6mo    1.26x  +26% blowout
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import vtables as V

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'fixtures', 'releases')
CORPUS = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
          r'\tests\corpus')

FAIL = [0]


def check(label, ok, detail=''):
    if ok:
        print('PASS %-58s %s' % (label, str(detail)[:24]))
    else:
        print('FAIL %-58s %s' % (label, str(detail)[:40]))
        FAIL[0] += 1


def _lines(path):
    return io.open(path, encoding='utf-8').read().splitlines()


def _explode(cells, gap=6):
    """A vertically exploded document: one cell per line, blank runs between.

    ★ Synthetic, so the cardinality probe can insert a stray cell without
    editing a real release -- and so the mis-map it produces is visible as a
    WRONG VALUE rather than only a wrong index.
    """
    out = []
    for c in cells:
        out.append(str(c))
        out.extend([''] * gap)
    return out


HPE_HEADER = ['For the three months ended', 'July 31, 2026', 'April 30, 2026',
              'July 31, 2025', 'In millions, except per share amounts']


def main():
    # ── the three real layouts, and the two that must refuse ──────────────
    cases = [
        ('HPE 3-month, sequential middle column',
         os.path.join(FIX, 'HPE-2026-09-02.txt'), 428, 3, 3, 2026, 0,
         ['REPORTED', V.SEQUENTIAL, V.PRIOR_YEAR_Q]),
        ('HPE 9-month block has no quarter column',
         os.path.join(FIX, 'HPE-2026-09-02.txt'), 2689, 2, 3, 2026, None,
         None),
        ('SNOW 3 strata, share columns excluded',
         os.path.join(FIX, 'SNOW-2026-09-02.txt'), 9668, 8, 2, 2027, 0,
         ['REPORTED', None, V.PRIOR_YEAR_Q, None, V.YTD, None,
          V.PRIOR_YEAR_YTD, None]),
        ('APP revenue, quarter beside six months',
         os.path.join(CORPUS, 'APP-2026Q2.txt'), 30, 6, 2, 2026, 0,
         ['REPORTED', V.PRIOR_YEAR_Q, None, V.YTD, V.PRIOR_YEAR_YTD, None]),
        ('APP adj EBITDA, a MID-TABLE row',
         os.path.join(CORPUS, 'APP-2026Q2.txt'), 75, 6, 2, 2026, 0,
         ['REPORTED', V.PRIOR_YEAR_Q, None, V.YTD, V.PRIOR_YEAR_YTD, None]),
        ('APP reconciliation table',
         os.path.join(CORPUS, 'APP-2026Q2.txt'), 1592, 4, 2, 2026, 0, None),
        ('SNDK highlights table has NO header',
         os.path.join(CORPUS, 'SNDK-2026Q4.txt'), 50, 4, 4, 2026, None, None),
    ]
    for label, path, idx, vc, rq, ry, want, want_cls in cases:
        if not os.path.exists(path):
            print('SKIP %s (no fixture)' % label)
            continue
        got = V.column_map(_lines(path), idx, vc, record_quarter=rq,
                           record_year=ry)
        check(label, got['valueIndex'] == want,
              'index %s' % got['valueIndex'])
        if want_cls is not None:
            check('  %s — full class map' % label.split(',')[0],
                  got['classes'] == want_cls, got['classes'])

    # ── ★ SEQUENTIAL IS ITS OWN CLASS ────────────────────────────────────
    got = V.column_map(_lines(os.path.join(FIX, 'HPE-2026-09-02.txt')), 428, 3,
                       record_quarter=3, record_year=2026)
    check('HPE April 30 is SEQUENTIAL, not PRIOR_YEAR_Q',
          got['classes'][1] == V.SEQUENTIAL, got['classes'][1])
    check('HPE July 2025 is PRIOR_YEAR_Q',
          got['classes'][2] == V.PRIOR_YEAR_Q, got['classes'][2])

    # ── ★ THE YEAR AXIS IS READ OFF THE HEADER, not the fiscal record ─────
    # SNOW's fiscal 2027 Q2 ended July 31 2026, so its columns say 2026 while
    # the record id says 2027. Comparing the two made every column PRIOR_YEAR.
    got = V.column_map(_lines(os.path.join(FIX, 'SNOW-2026-09-02.txt')), 9668,
                       8, record_quarter=2, record_year=2027)
    check('SNOW fiscal 2027 vs calendar 2026 header still resolves',
          got['valueIndex'] == 0, got['note'] or got['valueIndex'])

    # ── ★★ THE CARDINALITY GUARD, PROBED ANTI-VACUOUSLY ──────────────────
    # A stray cell is inserted BEFORE the reported figure, so a mis-map takes
    # a value that is not the quarter at all.
    clean = _explode(HPE_HEADER + ['Net revenue', '12,213', '10,678', '9,136'])
    stray = _explode(HPE_HEADER + ['Net revenue', '1', '12,213', '10,678',
                                   '9,136'])
    li_clean = next(i for i, l in enumerate(clean) if l == 'Net revenue')
    li_stray = next(i for i, l in enumerate(stray) if l == 'Net revenue')

    base = V.column_map(clean, li_clean, 3, record_quarter=3, record_year=2026)
    check('synthetic clean table resolves to the quarter',
          base['valueIndex'] == 0, base['note'] or base['valueIndex'])

    guarded = V.column_map(stray, li_stray, 4, record_quarter=3,
                           record_year=2026)
    check('a stray cell REFUSES', guarded['valueIndex'] is None,
          guarded['note'])
    check('  and the refusal names the counts',
          'cell count mismatch' in (guarded['note'] or ''), guarded['note'])

    # ★ NOW DISABLE THE GUARD. If the same input still refuses, something else
    # is doing the work and the guard is decoration.
    saved = V.cardinality_ok
    try:
        V.cardinality_ok = lambda a, b: True
        vacuous = V.column_map(stray, li_stray, 4, record_quarter=3,
                               record_year=2026)
    finally:
        V.cardinality_ok = saved
    check('with the guard OFF the same input MIS-MAPS',
          vacuous['valueIndex'] is not None, vacuous['note'])

    values = [1.0, 12213.0, 10678.0, 9136.0]
    mis = (values[vacuous['valueIndex']]
           if vacuous['valueIndex'] is not None else None)
    check('  and the mis-map takes a value that is NOT the quarter',
          mis is not None and abs(mis - 12213.0) > 1.0,
          'took %s, quarter is 12213' % mis)
    check('  the guard is therefore load-bearing, not decoration',
          guarded['valueIndex'] is None and vacuous['valueIndex'] is not None)

    # ── ★ DELTA CLOSURE, scoped by measurement to 1 of 5 rows ────────────
    sndk = os.path.join(CORPUS, 'SNDK-2026Q4.txt')
    if os.path.exists(sndk):
        L = _lines(sndk)
        got = V.delta_closure(L, 50, [84.6, 78.4, 84.6, 78.4])
        check('SNDK "up 6.2 ppt" closes uniquely on 84.6',
              got['valueIndex'] == 0 and got['value'] == 84.6,
              got['note'] or got['value'])
        check('  and the closure carries its evidence',
              len(got['evidence']) >= 2, got['evidence'])
        # ★ DISTINCT VALUES, NOT INDEX PAIRS. The highlights table prints the
        # same pair four times; counting index pairs called it ambiguous.
        check('  a repeated pair is ONE solution, not four',
              got['valueIndex'] is not None, got['note'])

        got2 = V.delta_closure(L, 186, [84.6, 26.2, 84.6, 26.4])
        check('SNDK "up 58.4 ppt" also closes on 84.6',
              got2['value'] == 84.6, got2['note'] or got2['value'])

    app = os.path.join(CORPUS, 'APP-2026Q2.txt')
    if os.path.exists(app):
        L = _lines(app)
        got = V.delta_closure(L, 30, [1924.0, 1259.0, 53.0, 3766.0, 2418.0,
                                      56.0])
        check('APP has no PROSE delta near the row — refuses',
              got['valueIndex'] is None, got['note'])

    hpe = _lines(os.path.join(FIX, 'HPE-2026-09-02.txt'))
    got = V.delta_closure(hpe, 428, [12213.0, 10678.0, 9136.0])
    check('HPE has no stated delta near the row — refuses',
          got['valueIndex'] is None, got['note'])

    # ★ TWO VALID DELTAS FOR TWO WINDOWS MUST REFUSE, not pick one.
    # ★ MY FIRST VERSION OF THIS PROBE DID NOT CONFLICT. 'up 6.2 ppt' and
    # 'up 20.0 ppt' against [84.6, 78.4, 64.6] both close on 84.6 -- they
    # AGREE, so the test asserted a refusal that should never have happened.
    # A conflict probe has to name two DIFFERENT current-period members.
    # ★★ AND IT MUST REFUSE FOR THE RIGHT REASON. My first version spaced the
    # cells 6 lines apart, putting the deltas 48 lines from the label -- past
    # the 40-line window -- so the probe passed on 'no stated delta found'
    # while claiming to test conflict detection. A test that passes for the
    # wrong reason is the render_test.js failure in miniature.
    synth = _explode(['Gross Margin', '84.6', '%', '78.4', '%', '100.0', '%',
                      'up 6.2 ppt', 'up 21.6 ppt'], gap=2)
    li = next(i for i, l in enumerate(synth) if l == 'Gross Margin')
    got = V.delta_closure(synth, li, [84.6, 78.4, 100.0])
    check('conflicting stated deltas REFUSE rather than prefer one',
          got['valueIndex'] is None, got['note'])
    check('  and the refusal says they DISAGREE, not that none was found',
          'disagree' in (got['note'] or ''), got['note'])

    # ── ★ REFUSAL IS NOT FREE: a header that resolves must not be refused ──
    for label, path, idx, vc, rq, ry in (
            ('HPE', os.path.join(FIX, 'HPE-2026-09-02.txt'), 428, 3, 3, 2026),
            ('SNOW', os.path.join(FIX, 'SNOW-2026-09-02.txt'), 9668, 8, 2,
             2027)):
        if not os.path.exists(path):
            continue
        got = V.column_map(_lines(path), idx, vc, record_quarter=rq,
                           record_year=ry)
        check('%s is NOT refused (a detector that refuses all is worthless)'
              % label, got['valueIndex'] is not None, got['note'])

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
