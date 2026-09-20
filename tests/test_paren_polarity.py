# -*- coding: utf-8 -*-
"""A parenthesised CELL is negative — and POSITION is the discriminator.

★★★ THIS TEST WAS RED FOR THREE DAYS BY DESIGN, AND THE PIN PAID. When it was
written the measurement was n=0: 902 parenthesised printings in the corpus, 2
at a position any row resolved to, and ZERO with a dropped sign. The ruling was
that n=0 on today's coverage is not n=0 on next month's, because MATCH had gone
7 -> 18 in three days, straight into the tables where parenthesised negatives
live. Coverage reached one: HPE prints its Corporate Investments segment
earnings as (67) and the reader returned +67, which would have made a derived
margin +24.1% on a segment that lost money.

★★ THE LEXICAL DISCRIMINATOR COULD NOT REACH IT. The first rule was that a
magnitude carries a decimal, separator, currency symbol or percent sign and a
footnote does not:

    (263.0) decimal   ($263.0) currency   (1,234) separator   (17.0%) percent
    (67)    NONE OF THEM — character-for-character the shape of (1)

★★★ THE POSITIONAL ONE DOES, and it was already computed before the sign
question arose: A FOOTNOTE MARKER IS PART OF A LABEL, A VALUE IS A CELL.
Nothing makes 'Non-GAAP(1)' or 'Net Revenue(5):' a cell; 67 arrived as one. The
two cases never occupy the same position — the same move that settled "to marks
the level", where the discriminator lives in the STRUCTURE THE ISSUER PRODUCED
rather than in the characters.

★ AND THE PARENTHESES SPLIT ACROSS LINES. HPE writes '(67' on one line and ')'
on another, and the closer is skipped as a bare marker, so the test is whether
the cell OPENS with a parenthesis rather than whether it is wrapped in a
matched pair.

Measured before wiring: 375 cells reached by a label hit, 13 opening with a
paren, and NO row that matches its hand read today reads one — so the rule
costs nothing and unblocks the segment it was pinned for.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import tables as T          # noqa: E402


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def first(lines):
    """The first cell of a one-row block, or None."""
    got = T.row_value_cells(lines, 0)
    return got[0][0] if got else None


def main():
    # ── the four original fixtures, now read AS CELLS ────────────────────
    check(first(['Operating income', '(263.0)', '237.0']) == -263.0,
          'a parenthesised figure is negative')
    check(first(['Operating income', '($263.0)', '237.0']) == -263.0,
          'currency INSIDE the parentheses — the form SNOW prints')
    check(first(['Operating income', '$(263.0)', '237.0']) == -263.0,
          'currency outside the parentheses, same value')
    check(first(['Revenue', '(1,234)', '5']) == -1234.0,
          'thousands separators inside parentheses')

    # ── the case the lexical rule could not reach ────────────────────────
    check(first(['Corporate Investments', '(67', ')', '9']) == -67.0,
          "HPE's (67) — a BARE INTEGER in parentheses, split across lines, "
          'indistinguishable from a footnote by any character test')
    check(first(['Free cash flow', '(934', '1,000']) == -934.0,
          'and an unmatched opening paren is still negative, because the '
          'closer arrives as its own line and is skipped')

    # ── the footnote, which never reaches this position ──────────────────
    check(T.row_value_cells(['Non-GAAP(1) gross margin', '54.4', '50.5'],
                            0)[0][0] == 54.4,
          "a footnote marker on a LABEL never becomes a cell, so it is never "
          'a candidate for negation — position, not characters')
    check(T.row_value_cells(['Net Revenue(5):', 'Networking', '2,893'],
                            0) == [],
          'and a block header carrying (5) yields no cells at all')

    # ── unparenthesised values are untouched ─────────────────────────────
    for txt, want in (('263.0', 263.0), ('$263.0', 263.0), ('1,234', 1234.0)):
        check(first(['Revenue', txt, '5']) == want,
              'unparenthesised %s stays positive' % txt)


main()
