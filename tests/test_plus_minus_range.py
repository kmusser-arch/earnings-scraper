# -*- coding: utf-8 -*-
"""A CENTRE and a TOLERANCE, and the two halves carry their own scales.

★★★ THE DASH GRAMMAR CANNOT SEE THIS FORM AT ALL. WDC prints its revenue
guide as '$4.1B +/- $100M': no 'to', no dash between two figures, and the two
halves are not the two ends. So range_pair walked past it to the first dash
range further down the window -- '$390M - $400M', the OPERATING EXPENSES row
-- and returned its midpoint, 395.0, against a hand read of 4.1.

★★ IT REPORTED COMPLETE CONFIDENCE WHILE DOING IT: candidateCount 1,
rejected [], why None. That is the pairs rule at the value level -- the
anchor was right, the pair was well formed, and nothing checked that they
belong to each other. A RANGE WITH NO LABEL IS STILL A RANGE.

★ AND THE UNIT TRAP IS INSIDE ONE PRINTED CELL. The centre is in BILLIONS,
the tolerance in MILLIONS, on a row declaring documentUnit $M. Returning 4.1
would be read as $4.1M: one condition, two names, with the seam between two
halves of a single expression rather than between two modules.

Measured before wiring: 21 rows in the corpus declare requiresRangePair, and
the +/- form occurs in exactly ONE release -- twice, both in WDC's guidance
table. Zero occurrences in AVGO, HPE, SNOW, APP or SNDK.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


WDC = ('Revenue | $4.1B +/- $100M | Gross margin | 55% - 56% | '
       'Operating expenses | $390M - $400M |')


def main():
    # ── each half converts through ITS OWN suffix ────────────────────────
    check(X.plus_minus_pair(WDC, {'documentUnit': '$M'}) == (4000.0, 4200.0),
          "a centre in BILLIONS and a tolerance in MILLIONS on a $M row")
    check(X.plus_minus_pair(WDC, {'documentUnit': '$B'}) == (4.0, 4.2),
          'and the same expression on a $B row, in $B')
    lo, hi = X.plus_minus_pair(WDC, {'documentUnit': '$M'})
    check(round((lo + hi) / 2.0, 6) == 4100.0,
          'the midpoint is the centre, which is what the library stores')

    # ── the form the dash grammar DOES see is left alone ─────────────────
    check(X.plus_minus_pair('Gross margin | 55% - 56% |', {}) is None,
          'a dash range is not a +/- range — this reader does not claim it')
    check(X.range_pair(WDC, {'documentUnit': '$M'}) == (390.0, 400.0),
          "and the dash grammar STILL takes the operating-expenses pair when "
          'asked — the fix is which reader is consulted, not a new guard')

    # ── a tolerance whose scale is unknown is refused, not guessed ───────
    check(X.plus_minus_pair('Revenue | 4.1 +/- 100 |', {'documentUnit': '$M'})
          is None,
          'a bare "4.1 +/- 100" is REFUSED: a tolerance with no scale is not '
          'a narrower range, it is an unknown one')

    # ── ± as the typographic character, not the ASCII spelling ───────────
    check(X.plus_minus_pair('Revenue | $4.1B ± $100M |',
                            {'documentUnit': '$M'}) == (4000.0, 4200.0),
          'the typographic ± reads the same as "+/-"')

    # ── and it is only consulted where the ROW declares the form ─────────
    check((X._PLUS_MINUS.search(WDC) is not None),
          'the pattern matches inside a pipe-joined table row')


main()
