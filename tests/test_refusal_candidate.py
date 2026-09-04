# -*- coding: utf-8 -*-
"""aRefusalMustCarryTheCandidate.

★★★ THE FAILURE MODE OF A CORRECT REFUSAL IS NOT A WRONG NUMBER. It is a
trader who stops reading refusals. At 4:15pm:

    ⛔ NOT GRADED                                            unusable
    ⛔ NOT GRADED — candidate 21.7, classified GUIDE_NEXT_Q,
                    row wants REPORTED                       a 4-second check

SPEC §8 said 'add a reason column' and underspecified it: the reason justifies
the refusal, the CANDIDATE is what makes it survivable live.

★ MEASURED FIRST: 45 of 46 ungraded fixture rows were bare. And the measure
itself undercounted -- 'scale-unvalidated' rows keep `actual` SET, so they
already render their candidate and an `actual is None` filter never sees them.
The real scope is rows where a candidate was FOUND AND DECLINED.

★★ 'not found in release' IS NOT ONE OF THEM. There is no candidate to carry,
and a placeholder there would put noise in the one field that has to stay
trustworthy.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import tables as T
from earnings_scraper import vtables as V

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'fixtures', 'releases')
FAIL = [0]


def check(label, ok, detail=''):
    if ok:
        print('PASS %-58s %s' % (label, str(detail)[:22]))
    else:
        print('FAIL %-58s %s' % (label, str(detail)[:44]))
        FAIL[0] += 1


def _explode(cells, gap=6):
    out = []
    for c in cells:
        out.append(str(c))
        out.extend([''] * gap)
    return out


HDR = ['For the three months ended', 'July 31, 2026', 'April 30, 2026',
       'July 31, 2025', 'In millions, except per share amounts']


def main():
    lines = [l.strip() for l in io.open(
        os.path.join(FIX, 'HPE-2026-09-02.txt'), encoding='utf-8').read(
        ).splitlines()]

    # ── the formatter ────────────────────────────────────────────────────
    check('a cell renders thousands-separated',
          V.fmt_num(12213.0) == '12,213', V.fmt_num(12213.0))
    check('a fraction keeps its precision, drops trailing zeros',
          V.fmt_num(1.4900) == '1.49', V.fmt_num(1.49))
    check('a missing cell renders ? not a crash', V.fmt_num(None) == '?')

    got = V.render_candidates([12213.0, 10678.0, 9136.0],
                              ['REPORTED', V.SEQUENTIAL, V.PRIOR_YEAR_Q])
    check('candidates render value AND class',
          '12,213 [REPORTED?]' in got and 'SEQUENTIAL?' in got, got)
    # ★ THE '?' IS LOAD-BEARING. A class printed as FACT on a refused mapping
    # asserts a correctness the refusal itself denies.
    check('  and the class carries a ? because the mapping did NOT close',
          got.count('?') == 3, got)
    check('  provisional=False drops the ?',
          '?' not in V.render_candidates([1.0], ['REPORTED'],
                                         provisional=False))

    # ── the cardinality refusal ──────────────────────────────────────────
    stray = _explode(HDR + ['Net revenue', '1', '12,213', '10,678', '9,136'])
    li = next(i for i, l in enumerate(stray) if l == 'Net revenue')
    r = V.column_map(stray, li, 4, values=[1.0, 12213.0, 10678.0, 9136.0])
    check('a cardinality refusal still refuses', r['valueIndex'] is None)
    check('  and names EVERY declined candidate',
          all(x in r['note'] for x in ('12,213', '10,678', '9,136')),
          r['note'])
    check('  and still says why',
          'cell count mismatch' in r['note'], r['note'])
    # ★ classification never ran here, so there are no classes to print --
    # and inventing them would be worse than omitting them.
    check('  no classes are invented when classification never ran',
          '[' not in (r.get('candidates') or ''), r.get('candidates'))

    # ── the refusal where classification DID run ────────────────────────
    dup = _explode(['For the three months ended', 'July 31, 2026',
                    'July 31, 2026', 'In millions',
                    'Net revenue', '12,213', '10,678'])
    li2 = next(i for i, l in enumerate(dup) if l == 'Net revenue')
    r2 = V.column_map(dup, li2, 2, values=[12213.0, 10678.0])
    check('two REPORTED columns refuse rather than choose',
          r2['valueIndex'] is None, r2['note'])
    check('  and the refusal carries both candidates WITH their classes',
          '12,213 [REPORTED?]' in r2['note']
          and '10,678 [REPORTED?]' in r2['note'], r2['note'])

    # ── the nine-month block ────────────────────────────────────────────
    cells = T.row_value_cells(lines, 2689)
    r3 = V.column_map(lines, 2689, len(cells),
                      values=[c[0] for c in cells])
    check('HPE nine-month block refuses', r3['valueIndex'] is None)
    check('  and names the YTD figures it declined',
          '32,192' in (r3['note'] or ''), r3['note'])

    # ── ★ REFUSAL IS NOT FREE: a row that RESOLVES adds no noise ────────
    r4 = V.column_map(lines, 428, 3, values=[12213.0, 10678.0, 9136.0])
    check('a resolved row has valueIndex 0', r4['valueIndex'] == 0)
    check('  and NO candidate list', r4.get('candidates') is None,
          r4.get('candidates'))
    check('  and NO note', r4.get('note') is None, r4.get('note'))

    # ── the same, through verified_value ────────────────────────────────
    v, pct, why = T.verified_value(lines, 2689)
    check('verified_value refuses the nine-month row', v is None)
    check('  and its note carries the candidates',
          why and '32,192' in why, why)

    v2, pct2, why2 = T.verified_value(lines, 428)
    check('verified_value fills the three-month row', v2 == 12213.0, v2)
    check('  with no refusal note', why2 is None, why2)

    # ── the row-level formatter in score.py ─────────────────────────────
    from earnings_scraper import score as S
    row = {}
    S.refused(row, 'period mismatch: found GUIDE_NEXT_Q, row wants REPORTED',
              candidate=21.7, unit='$B')
    check('refused() puts the CANDIDATE FIRST',
          row['ungradedReason'].startswith('candidate 21.7 $B — '),
          row['ungradedReason'])
    check('  and keeps the value machine-readable',
          row['refusedCandidate'] == 21.7 and row['refusedCandidateUnit'] ==
          '$B')
    # ★★ NO CANDIDATE, NO PLACEHOLDER. 'not found in release' has nothing to
    # carry, and a fabricated one would poison the field that must stay
    # trustworthy.
    bare = {}
    S.refused(bare, 'not found in release')
    check('a refusal with no candidate stays bare',
          bare['ungradedReason'] == 'not found in release'
          and 'refusedCandidate' not in bare, bare)

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
