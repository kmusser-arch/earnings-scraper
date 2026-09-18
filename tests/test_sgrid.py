# -*- coding: utf-8 -*-
"""The stacked grid — cells below the label, basis groups above the block.

SNOW prints a row as its label followed by one cell per line, and above the
block prints 'Amount (millions) / Margin' TWICE, under 'GAAP Results' and
'Non-GAAP Results(1)'. So the cells divide into equal contiguous groups, one
per basis header, which is axes.partition — the mechanism already pinned.

★★★ A SINGLE CANDIDATE IS NOT EVIDENCE OF THE RIGHT CANDIDATE. SNOW's
gross-margin row yielded exactly ONE prose candidate, 70.9 — the GAAP figure —
so no tie ever formed, the column path was never asked, and the row returned a
confident wrong number. One candidate meant only one reader had looked. A row
that declares a basis now consults the basis-aware reader whether or not
anything ties.

★★ AND PARENTHESES ARE NEGATIVE HERE, WHERE THE AMBIGUITY IS RESOLVABLE. The
shared parser's polarity defect stays PINNED RED because a blanket negate
inverts SNDK's footnote marker '(1)'. Inside a stacked cell a magnitude
carries a decimal, separator, currency symbol or percent sign and a footnote
does not, which is the discriminator the blanket rule lacked.

★ IT IS FOR COLUMN-GROUP BASIS ONLY. HPE and ADBE carry the basis in the ROW
LABEL — 'Non-GAAP gross profit margin' — so there is no group to partition and
the label has already done the work. Running the stacked reader there took
HPE's Q3 adjusted gross margin from 40.4, its hand read, to 38.1 out of the
nine-month block. basisLocation decides.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import sgrid as SG               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNOW = os.path.join(HERE, 'fixtures', 'releases', 'SNOW-2026-09-02.txt')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    # ── the cell reader, both conventions and the polarity ───────────────
    check(SG.cell('$1,057.4') == (1057.4, False),
          'a currency cell reads as a level')
    check(SG.cell('70.9%') == (70.9, True),
          "SNOW's attached percent sign is read")
    check(SG.cell('($263.0)') == (-263.0, False),
          'a parenthesised magnitude is NEGATIVE')
    check(SG.cell('(17.0%)') == (-17.0, True),
          'and so is a parenthesised percentage')
    check(SG.cell('(1)') == (1.0, False),
          "but '(1)' stays POSITIVE — a footnote marker carries no decimal, "
          'separator, currency symbol or percent sign, which is the '
          'discriminator the blanket rule lacked')
    check(SG.cell('Product gross profit') is None,
          'a label is not a cell, which is what ends the block')

    if not os.path.exists(SNOW):
        print('FAIL SNOW fixture missing')
        return
    lines = io.open(SNOW, encoding='utf-8').read().split(chr(10))

    # ── the blocks, read whole ───────────────────────────────────────────
    gp = SG.block_cells(lines, 374)
    check([v for v, _p in gp] == [1057.4, 70.9, 1114.1, 74.7],
          'Product gross profit yields all four cells, margins included')
    oi = SG.block_cells(lines, 418)
    check([v for v, _p in oi] == [-263.0, -17.0, 237.0, 15.3],
          'Operating income yields four cells with the GAAP pair NEGATIVE — '
          'the row that used to be right by luck is now right by reading')

    # ── selection by basis group ─────────────────────────────────────────
    spec_pct = {'basis': 'non-GAAP', 'documentUnit': '%'}
    got = SG.select(lines, 374, spec_pct)
    check(got.get('value') == 74.7,
          'non-GAAP + (%) selects 74.7, against the 70.9 the row returned '
          'from its single prose candidate')
    check(got.get('groups') == ['GAAP', 'non-GAAP'],
          'and both basis groups are found above the block')
    check(SG.select(lines, 374, {'basis': 'GAAP',
                                 'documentUnit': '%'}).get('value') == 70.9,
          'asking for GAAP returns 70.9 — the groups are real, not assumed')
    check(SG.select(lines, 418, spec_pct).get('value') == 15.3,
          'and the operating-margin row selects 15.3')

    # ── the basis may be declared on the row OR on the axis ──────────────
    axis_form = {'documentUnit': '%', 'columnAxes': {'axes': [
        {'axis': 'BASIS', 'want': 'non-GAAP',
         'headers': ['GAAP Results', 'Non-GAAP Results(1)']}]}}
    check(SG.select(lines, 374, axis_form).get('value') == 74.7,
          'the basis is read from the AXIS too — SNOW declares it on the row '
          'and SNDK on the axis, and a reader that knows one is silent on '
          'half the corpus')

    # ── a $ row does not take a % cell ───────────────────────────────────
    dollars = SG.select(lines, 374, {'basis': 'non-GAAP',
                                     'documentUnit': '$M'})
    check(dollars.get('value') == 1114.1,
          'a ($M) row takes the non-GAAP AMOUNT, 1114.1, not its margin')


main()
