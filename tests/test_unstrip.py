# -*- coding: utf-8 -*-
"""THE ISSUER DREW THE COLUMNS AND STRIPPING ERASED THEM.

hgrid's whole mechanism is that a cell's COLUMN POSITION falls inside a dash
run the issuer printed. It was handed `[l.strip() for l in body.split(NL)]`
-- every line stripped INDEPENDENTLY. On AVGO the basis header sits at indent
36, its rule at 25 and the data row at 1: three different shifts on one
table, so the outer stratum stopped lining up with the cells beneath it.

★★★ AVGO[8] WAS RIGHT BY TWO ERRORS CANCELLING, not by reading. 'GAAP'
landed by arithmetic coincidence on the column that IS GAAP, 'Non-GAAP' fell
off the right-hand end entirely, and the correct column survived the basis
filter AS UNLABELLED RATHER THAN AS MATCHING -- because the filter keeps a
column whose basis is None. The value never moved and nothing could ever have
flagged it.

So the assertion here is NOT 3.32. The value was already 3.32 and will stay
3.32 whatever happens to the header. THE OBSERVABLE TRANSITION IS THE
CALIBRATION: the cell description must go from ['Q3 26'] to
['Q3 26', 'Non-GAAP'] -- right by cancellation becomes right by evidence.

★★ MEASURED REPORT-ONLY BEFORE LANDING, over all eight releases: 0 of 102
rows move verdict, value or position; exactly 2 rows gain a basis word. Six
of the eight documents carry no indentation at all, so stripping is a no-op
there and the entire question lives on two documents.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import hgrid as HG           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AVGO = os.path.join(HERE, 'fixtures', 'releases', 'AVGO-2026-09-02.txt')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')

EPS_ROW = 47


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not os.path.exists(AVGO):
        print('FAIL AVGO fixture missing')
        return
    body = io.open(AVGO, encoding='utf-8').read()
    raw = body.split(chr(10))

    # ── the three shifts are real and this fixture still has them ────────
    ind = [len(raw[i]) - len(raw[i].lstrip()) for i in (37, 38, EPS_ROW)]
    check(ind == [36, 25, 1],
          'the basis header, its rule and the data row are indented %s -- '
          'three different amounts, which is what independent stripping '
          'turns into three different shifts' % ind)

    kept = [l.rstrip() for l in raw]
    lost = [l.strip() for l in raw]
    spec = {'basis': 'non-GAAP', 'documentUnit': '$'}

    good = HG.select(kept, EPS_ROW, spec)
    bad = HG.select(lost, EPS_ROW, spec)

    check(good.get('description') == ['Q3 26', 'Non-GAAP'],
          'with the indent KEPT the cell is described %s -- period and basis '
          'crossed, which is what the grid was built to do'
          % good.get('description'))
    # ★ THE ANTI-VACUOUS HALF. If stripping had also produced the basis word
    # this test would pass while proving nothing, so the old frame is shown
    # to LACK it rather than assumed to.
    check(bad.get('description') == ['Q3 26'],
          'with the indent stripped it is described %s -- the basis word is '
          'GONE, so this test fails on a revert instead of passing quietly'
          % bad.get('description'))
    check(good.get('value') == bad.get('value') == '$  3.32',
          'AND THE VALUE IS THE SAME EITHER WAY (%r). The number was never '
          'the finding: it was right by two errors cancelling and is now '
          'right by evidence, and only the description can tell those apart'
          % good.get('value'))

    # ── the whole header row, so the cancellation is visible ─────────────
    kept_all = [(x, r, d) for x, r, d in HG.describe_cells(kept, EPS_ROW)]
    lost_all = [(x, r, d) for x, r, d in HG.describe_cells(lost, EPS_ROW)]
    check([d[-1] for _x, _r, d in kept_all]
          == ['GAAP', 'GAAP', 'GAAP', 'Non-GAAP', 'Non-GAAP', 'Non-GAAP'],
          'every cell on the row now carries its basis group, three and '
          'three, as the issuer drew it')
    check([' '.join(d) for _x, _r, d in lost_all][:2] == ['Q3 26 GAAP',
                                                          'Q3 25'],
          'where stripped, GAAP landed on ONE column by coincidence and the '
          'other five carried no basis at all: %s'
          % [' '.join(d) for _x, _r, d in lost_all])

    # ── cell_offset must know which frame it was handed ──────────────────
    # The reader counts the indent when it is present; adding it again puts
    # the coordinate one character right of the figure. One function, two
    # frames -- the same defect shape as a name that is correct on one side.
    off_kept = X.cell_offset(body, good['cellLine'], good['cellX'],
                             stripped=False)
    off_lost = X.cell_offset(body, bad['cellLine'], bad['cellX'],
                             stripped=True)
    check(off_kept == off_lost,
          'both frames resolve to the SAME document offset (%d) -- the indent '
          'is added back exactly once, whichever frame produced the x'
          % off_kept)
    check(body[off_kept:off_kept + 4] == '3.32',
          'and that offset is the figure itself (%r)'
          % body[off_kept:off_kept + 4])

    # ── end to end on the row's own spec ─────────────────────────────────
    if not os.path.exists(LIB):
        print('SKIP library not reachable — end-to-end case not run')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    rec = recs['AVGO-2026Q3']
    out = X.value_for(body, rec['preEarnings']['keyKPIs'][8],
                      record=rec) or {}
    check(out.get('value') == 3.32,
          'AVGO[8] still reads 3.32 end to end')
    check('Non-GAAP' in (out.get('columnClasses') or []),
          'and the basis now travels OUT of the extractor on columnClasses '
          '(%s) — computed by the grid since the grid was written, and '
          'discarded at the same step as the coordinate'
          % (out.get('columnClasses') or []))


main()
