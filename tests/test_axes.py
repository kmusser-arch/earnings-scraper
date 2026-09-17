# -*- coding: utf-8 -*-
"""The cell grid, indexed by header text — one mechanism at 1, 2 or 3 axes.

★★★ WHAT IS PROVEN HERE IS THE MECHANISM, NOT THE BINDING. Given the basis
headers that govern a row, the resolver partitions the row's cells, labels
them, intersects the axes and returns the right cell: SNOW's Product gross
profit row is [1057.4, 70.9%, 1114.1, 74.7%] under 'GAAP Results' and
'Non-GAAP Results', and non-GAAP + the (%) unit class selects 74.7, which is
the hand-read actual.

★★ THE BINDING IS UNSOLVED AND IS NOT A LENGTH. Measured over the three
releases that print basis headers, the distance from a table row up to its
nearest basis header is:
        SNOW   min 63   median 11,031   max 16,537   lines
        SNDK   min 13   median    113   max  1,814
        WDC    min  8   median     21   max  1,189
No lookback separates them. A bound wide enough to reach SNOW's highlights
header (223 lines) also attaches a header 11,000 lines away to a row in an
unrelated table. This is the same lesson as the five window bugs and the
1,800-character span: A SPAN NEEDS A CLOSE, NOT A LENGTH. So resolve() is
exercised here with the governing headers supplied explicitly, and is NOT
wired into value_for until the close exists.

★ AND ONE APPARENT SUCCESS IS DISCARDED AS EVIDENCE. SNOW's Operating income
row also returns the right answer, 15.3 -- by coincidence. Its GAAP cells are
MISSING, because the issuer writes '($263.0)' with the currency symbol INSIDE
the parentheses and _NUMERIC expects it outside. Both surviving cells are
therefore non-GAAP, the partition labels the first one GAAP, and the unit
class carries the row to the right number anyway. Closure confirms a value,
not a mechanism, so that row is asserted only for the thing it really shows:
that a partition over a cell list missing its first group MISLABELS.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import axes as A            # noqa: E402
from earnings_scraper import tables as T          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNOW = os.path.join(HERE, 'fixtures', 'releases', 'SNOW-2026-09-02.txt')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    # ── partition: equal groups, and RAGGED REFUSES ──────────────────────
    check(A.partition(4, 2) == [0, 0, 1, 1], 'four cells split into two groups')
    check(A.partition(6, 3) == [0, 0, 1, 1, 2, 2], 'six cells, three groups')
    check(A.partition(4, 3) is None,
          'RAGGED REFUSES: 4 cells do not divide into 3 declared groups')
    check(A.partition(0, 2) is None, 'a row with no cells selects nothing')

    # ── header matching is LONGEST FIRST ─────────────────────────────────
    lines = ['GAAP Results', 'x', 'Non-GAAP Results(1)', 'y', 'Row label']
    got = A.header_groups(lines, 4, ['GAAP Results', 'Non-GAAP Results'],
                          lookback=10)
    check(got == ['GAAP Results', 'Non-GAAP Results'],
          "'Non-GAAP' is not matched as 'GAAP' — the inversion this prevents")
    check(A.header_groups(lines, 4, ['GAAP Results'], lookback=10)
          == ['GAAP Results'], 'a single declared header yields one group')

    # a 1,400-character methodology paragraph names both bases and is NOT a
    # header: only a SHORT line can be one.
    prose = ['Non-GAAP product gross profit is defined as the respective '
             'GAAP measure, excluding stock-based compensation and other '
             'items described below in this release', 'Row label']
    check(A.header_groups(prose, 1, ['GAAP', 'Non-GAAP'], lookback=5) == [],
          'a long prose line is not a basis header')

    # ── the real grid, with the binding supplied by hand ─────────────────
    if not os.path.exists(SNOW):
        print('FAIL SNOW fixture missing: %s' % SNOW)
        return
    body = io.open(SNOW, encoding='utf-8').read()
    doc = [l.strip() for l in body.split(chr(10))]

    cells = T.row_value_cells(doc, 374)
    check([v for v, _ in cells] == [1057.4, 70.9, 1114.1, 74.7],
          'the Product gross profit row yields four cells, margins included')

    groups = A.header_groups(doc, 374, ['GAAP Results', 'Non-GAAP Results'],
                             lookback=300)
    check(groups == ['GAAP Results', 'Non-GAAP Results'],
          'both basis groups are found above the row')

    part = A.partition(len(cells), len(groups))
    labels = [groups[g] for g in part]
    keep = [i for i, l in enumerate(labels) if l.lower().startswith('non-')]
    picked = [cells[i][0] for i in keep if cells[i][1]]      # the (%) row
    check(picked == [74.7],
          'non-GAAP + the (%) unit class selects 74.7, the hand-read actual')
    check(cells[1][0] == 70.9 and labels[1].startswith('GAAP'),
          '70.9 is labelled GAAP — the value the row returns today')

    # ── the coincidence, asserted as a coincidence ───────────────────────
    op = T.row_value_cells(doc, 432)
    check(len(op) == 2,
          "the Operating income row loses its GAAP cells: '($263.0)' puts "
          'the currency symbol inside the parentheses')
    op_labels = [['GAAP', 'Non-GAAP'][g]
                 for g in (A.partition(len(op), 2) or [])]
    check(op_labels[:1] == ['GAAP'],
          'and a partition over that short list MISLABELS a non-GAAP cell '
          'as GAAP — the right answer there is luck, not mechanism')


main()
