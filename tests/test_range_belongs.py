# -*- coding: utf-8 -*-
"""The pair must belong to the row the label matched.

★★★ A RANGE WITH NO LABEL IS STILL A RANGE. WDC's revenue guide anchored on
the correct sentence -- the CFO quote naming $4.1 billion -- and came back
holding 395.0, the midpoint of '$390M - $400M', which is the OPERATING
EXPENSES row of the guidance table. It reported candidateCount 1, rejected [],
why None: complete confidence. The anchor was right, the pair was well formed,
and nothing asked whether they belong to each other.

★★ THE WINDOW ALREADY OPENS AT THE LABEL. The first walk-back written here
required the nearest preceding cell to BE the label, and it rejected 6 of the
10 corpus rows that reach a pair -- because for most of them there is no
preceding cell at all: the label is the window's own start. Reaching the start
is the STRONGEST belonging, not the weakest. Grammar that joins a label to its
figures -- 'between', 'of', 'to be' -- is transparent for the same reason.

★ AND THE RULE HAS A MEASURED BOUNDARY, WHICH IS WHY IT IS OPT-IN. Where ONE
PROSE SENTENCE CARRIES TWO METRICS it refuses a CORRECT pair: SNOW writes
'Product revenue of $1,588 million to $1,593 million, representing 37% to 38%
year-over-year growth', and from the growth pair the revenue figures look like
a rival. SNOW does not declare the field, so nothing breaks -- but a row whose
figure sits downstream of another metric in the same sentence MUST NOT declare
it. Declared on the two WDC rows: 1 gain, 0 losses. Applied to every range
row: 2 gains, 1 loss.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


WDC = ('revenue of $4.1 billion, non-GAAP gross margin of 55.5% | '
       'Non-GAAP(1) | Revenue | $4.1B +/- $100M | Gross margin | 55% - 56% | '
       'Operating expenses | $390M - $400M |')
REV = {'documentLabels': ['Revenue of $'], 'rangeMustBelongToLabel': True,
       'documentUnit': '$M', 'requiresRangePair': True}
GM = {'documentLabels': ['Gross margin'], 'rangeMustBelongToLabel': True,
      'documentUnit': '%', 'requiresRangePair': True}


def main():
    # ── the founding case ────────────────────────────────────────────────
    k = WDC.index('$390M')
    check(not X.belongs_to_label(WDC, k, REV),
          "the operating-expenses pair is REFUSED for a revenue row — the "
          'nearest words-cell is Operating expenses')
    k2 = WDC.index('55% - 56%')
    check(X.belongs_to_label(WDC, k2, GM),
          "and the gross-margin pair is KEPT for a gross-margin row")
    check(not X.belongs_to_label(WDC, k2, REV),
          'that same pair is refused for the revenue row — one window, two '
          'rows, and the walk-back separates them')

    # ── reaching the window start is the STRONGEST belonging ─────────────
    check(X.belongs_to_label('$6.80 billion to $6.85 billion', 0,
                             {'documentLabels': ['Revenue']}),
          'a pair at the window start belongs: the label opened the window')
    w = ' to be between $1.85 and $1.93'
    check(X.belongs_to_label(w, w.index('$1.85'),
                             {'documentLabels': ['EPS']}),
          "'to be between' is grammar joining a label to its own figures, "
          'not a competing label')

    # ── the measured boundary, pinned so it cannot be forgotten ──────────
    # ★ THE WINDOW OPENS JUST AFTER THE LABEL, so the label's own words are
    # NOT in the walk-back's view -- only whatever sits between it and the
    # pair. Written as a flat sentence INCLUDING 'Product revenue' this case
    # passes, which is how a fixture can hide the defect it was written for.
    snow = (' of $1,588 million to $1,593 million, representing '
            '37% to 38% year-over-year growth')
    check(not X.belongs_to_label(snow, snow.index('37%'),
                                 {'documentLabels': ['Product revenue']}),
          '★ THE KNOWN FALSE POSITIVE: one prose sentence carrying two '
          'metrics refuses the SECOND one. SNOW must not declare this field')

    # ── and the flag is what switches it on ──────────────────────────────
    check(X.range_pair(WDC, dict(REV, rangeMustBelongToLabel=False))
          == (390.0, 400.0),
          'without the declaration the dash grammar still takes the first '
          'unit-matching pair — the rule is opt-in, not ambient')
    check(X.range_pair(WDC, REV) is None,
          'and with it declared, no $ pair in this window belongs to the '
          'revenue label, so range_pair yields nothing rather than a wrong '
          'number — the PLUS_MINUS reader supplies the right one')


main()
