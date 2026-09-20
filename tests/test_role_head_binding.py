# -*- coding: utf-8 -*-
"""'of' is both a level and a delta, and its HEAD NOUN decides which.

    'guidance of approximately $34.8 billion'   of -> LEVEL
    'an increase of 93 percent'                 of -> DELTA

★★★ AS A BARE TOKEN IT SAT IN THE LEVEL LIST, AND THE LEVEL TEST RUNS FIRST,
so every delta construction ending in 'of' was classified a level. AVGO's Q4
revenue guide came back as 93.0 -- the GROWTH RATE -- on a row declaring $B,
from the sentence 'revenue guidance of approximately $34.8 billion, an
increase of 93 percent from the prior year period'.

★★ REORDERING THE TESTS IS NOT THE FIX: it only inverts which construction
loses. Binding 'of' to its head makes the order stop mattering. The same move
that settled 'to marks the level' -- the discriminator lives in the structure
the issuer produced, not in a token.

★ THE HEDGE IS THE OTHER HALF, AND IT IS A PAIRS DEFECT. 'approximately' was
in NEITHER vocabulary, so 'guidance of approximately $34.8' ended with the
hedge and never reached its own 'of': 34.8 came back role=None and the prose
path, which keeps only role='level', dropped it. A level preposition firing on
a delta, and a hedge word hiding a level. Either half alone leaves the row
wrong.

★ AND IT REMOVES 18 SPURIOUS LEVELS NEITHER OF US WAS LOOKING FOR. Bare 'of'
made YEARS into level candidates: 'fourth quarter of fiscal year 2027' and
'Private Securities Litigation Reform Act of 1995' each yielded one. A head
that is not a metric now yields no role at all.

Measured over 8 releases before wiring: 87 of-before-figure constructions, 7
with a change head, 8 hedged. MATCH 33 -> 34, MISMATCH 3 -> 2, nothing lost.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def roles(text):
    return [(c['value'], c['role']) for c in X.candidates(text, {})]


def main():
    # ── the founding case, both halves in one sentence ───────────────────
    avgo = (' revenue guidance of approximately $34.8 billion, an increase '
            'of 93 percent from the prior year period')
    got = dict((v, r) for v, r in roles(avgo))
    check(got.get(34.8) == 'level',
          "'guidance of approximately $34.8 billion' is a LEVEL — the hedge "
          'is transparent and does not hide the preposition')
    check(got.get(93.0) == 'delta',
          "'an increase of 93 percent' is a DELTA — same preposition, "
          'different head, and the test order no longer decides')

    # ── ordinary level heads keep working ────────────────────────────────
    for txt, val in ((' revenue of $29.6 billion', 29.6),
                     (' EPS of $1.11', 1.11),
                     (' free cash flow of $1.28 billion', 1.28),
                     (' operating margin of 55.5%', 55.5)):
        check(dict(roles(txt)).get(val) == 'level',
              '%r stays a level' % txt.strip())

    # ── change heads are deltas ──────────────────────────────────────────
    for txt, val in ((' growth of 19%', 19.0), (' a decline of 12%', 12.0)):
        check(dict(roles(txt)).get(val) == 'delta',
              '%r is a delta' % txt.strip())

    # ── ★ the spurious levels that bare 'of' was producing ───────────────
    check(dict(roles(' fourth quarter of fiscal year 2027')).get(2027.0)
          is None,
          "★ a YEAR after 'quarter of' is no longer a LEVEL candidate")
    check(dict(roles(' Securities Litigation Reform Act of 1995')).get(1995.0)
          is None,
          "★ nor is the year in 'Act of 1995' — a head that is not a metric "
          'yields no role')

    # -- and the ORCL case that set the original rule still holds ------
    orcl = dict(roles(' up $209 billion year-over-year to $664 billion'))
    check(orcl.get(209.0) == 'delta' and orcl.get(664.0) == 'level',
          'the founding case survives: up ... to is still delta then '
          'level')


main()
