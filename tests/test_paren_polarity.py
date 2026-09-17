# -*- coding: utf-8 -*-
"""PINNED, NOT SHIPPED: a parenthesised figure is NEGATIVE.

★★★ THIS TEST IS RED ON PURPOSE. tables._NUMERIC puts `\\(?` and `\\)?`
OUTSIDE its capture group:

    _NUMERIC = re.compile(r'^\\$?\\s*\\(?(-?[\\d,]+(?:\\.\\d+)?)\\)?$')

so '(263.0)' returns +263.0 and '$(263.0)' returns +263.0. By accounting
convention both are MINUS 263.0. SNOW prints its GAAP operating income as
($263.0) and its GAAP operating margin as (17.0%).

★★ WHY IT IS PINNED AND NOT FIXED. Measured report-only over all eight
releases: 902 parenthesised printings in the corpus, but only 2 sit at a
position any of the 77 extractable rows resolves to, and ZERO show a dropped
sign against the hand-read answer key. Both of those 2 are false positives of
the detector -- SNOW's (17.0%) is a different metric entirely, and SNDK's is
the FOOTNOTE MARKER '(1)' beside a row that already matches at 10,550. A
blanket negate would turn that footnote into -1. Wiring a rule at n=0 is how
the family-five rule and the AAPL shift-fitter got written.

★ SO WHY PIN IT AT ALL: n=0 ON TODAY'S COVERAGE IS NOT n=0 ON NEXT MONTH'S.
MATCH went 7 -> 18 and LOST 41 -> 31 in three days, straight into the tables
where parenthesised negatives live. A polarity inversion is the one defect
class that reads as a perfectly well-formed number -- right metric, right
period, wrong side of zero -- so it cannot be caught by a magnitude band, a
tie count, or a refusal. The day it starts firing should be the day a test
goes red, not the day a verdict flips on a live print.

Registered in run_tests.KNOWN_RED: it reports loudly and does not set the
exit code. The fix must also decide the footnote case -- '(1)' alone is not
a magnitude -- which is why it is a change, not a one-line edit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import tables as T          # noqa: E402


def cell_value(text):
    """What the vertical cell parser makes of one cell."""
    m = T._NUMERIC.match(text)
    if not m:
        return None
    return T._to_float(m.group(1))


def main():
    # ── the pin Kyle specified ───────────────────────────────────────────
    cases = [
        ('(263.0)', -263.0, 'a parenthesised figure is negative'),
        ('$(263.0)', -263.0, 'the currency symbol does not change the sign'),
        ('(1,234)', -1234.0, 'thousands separators inside parentheses'),
    ]
    for text, want, why in cases:
        got = cell_value(text)
        ok = got is not None and abs(got - want) < 1e-9
        print('%s %-12s -> %-10s (want %-9s) %s'
              % ('PASS' if ok else 'FAIL', text, got, want, why))

    # ── the cases that must NOT flip ─────────────────────────────────────
    # A FOOTNOTE MARKER IS NOT A MAGNITUDE. SNDK prints '(1)' beside a value
    # that is already correct; a blanket negate makes it -1.
    got = cell_value('(1)')
    print('%s %-12s -> %-10s a lone (1) is a footnote marker, not -1'
          % ('PASS' if got is None or got >= 0 else 'FAIL', '(1)', got))

    for text in ('263.0', '$263.0', '1,234'):
        got = cell_value(text)
        ok = got is not None and got > 0
        print('%s %-12s -> %-10s unparenthesised stays positive'
              % ('PASS' if ok else 'FAIL', text, got))


main()
