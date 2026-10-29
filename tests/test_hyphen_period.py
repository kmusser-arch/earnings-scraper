# -*- coding: utf-8 -*-
r"""ONE CHARACTER COST INTEL ITS REVENUE AND ITS GUIDE.

    'Third-quarter revenue was $16.5 billion'  -> nothing
    'Third quarter revenue was $16.5 billion'  -> 16,500 / +21%

On 2026-10-29 Amazon and Sandisk both parsed cleanly off the same release
shape; Intel returned grossMargin and operatingMargin and nothing else. It
hyphenates every period word. The hyphen is TYPOGRAPHY, not meaning, so it
is normalised once in parse_release rather than taught to each pattern.

MEASURED report-only over 130 documents (corpus + wire fixtures + live
captures): 18 carry a hyphenated period word, 5 values NEWLY parse, and
ZERO are lost or changed. Measured on CORRECTNESS -- a document whose
revenue already parsed must parse to the SAME value. That is the test the
chars-per-line floor failed, and why it was reverted.

★★★★ AND THE FIRST CUT OF THE PATTERN CARRIED A BACKSPACE. Written through
a nested shell quote, `\b` collapsed to chr(8), so the regex matched
nothing and INTC still read nothing -- the SAME defect that made
basis_token report two false FALSE_MATCHes. The repo-wide guard in
test_reason_gate would have caught it; it was not run between introducing
the bug and fixing it. The guard was fine. The discipline was not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse                          # noqa: E402


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def rev(body):
    p = parse.parse_release({'headline': '', 'body': body})
    return (p.get('revenue') or {}).get('value_musd')


def guide(body):
    p = parse.parse_release({'headline': '', 'body': body})
    return ((p.get('guidance') or {}).get('nextQ') or {}).get('mid')


def main():
    # ── the pattern itself must be clean and must match ──────────────────
    pat = parse._HYPHEN_PERIOD.pattern
    check(not any(chr(c) in pat for c in (7, 8, 11, 12)),
          'the pattern carries NO control character: %r' % pat)
    check(parse._HYPHEN_PERIOD.findall('Third-Quarter and third-quarter'),
          'and it matches both cases — a pattern that matches nothing is '
          'the backspace failure wearing a clean diff')

    # ── Intel's real sentences ───────────────────────────────────────────
    intc = ('Third-quarter revenue was $16.5 billion, up 21% '
            'year-over-year (YoY).')
    check(rev(intc) == 16500.0,
          "Intel's own hyphenated sentence now reads 16,500 (%s)"
          % rev(intc))
    check(rev(intc.replace('Third-quarter', 'Third quarter')) == rev(intc),
          'and reads the SAME with a space — the normalisation changes '
          'typography, never the number')

    g = 'Forecasting fourth-quarter 2026 revenue of $15.0 billion to $16.0 billion.'
    check(guide(g) == 15500.0,
          'the hyphenated GUIDE parses too, mid 15,500 (%s) — it was the '
          'second number Intel lost' % guide(g))

    # ── ★ AND THE UNHYPHENATED WORLD IS UNTOUCHED ────────────────────────
    sndk = 'Fiscal first quarter revenue was $11.0 billion, up 23%.'
    amzn = 'Net sales increased 12% to $201.9 billion in the third quarter.'
    check(rev(sndk) == 11000.0,
          "Sandisk's phrasing is unchanged (%s)" % rev(sndk))
    check(rev(amzn) == 201900.0,
          "Amazon's phrasing is unchanged (%s)" % rev(amzn))

    # ── and a hyphen that is NOT a period word is left alone ─────────────
    # ★ ASSERTED ON THE REWRITE, NOT ON A PARSE. The first cut of this
    # check asked whether 'Year-over-year revenue was $5.0 billion' parsed
    # to 5,000 — it does not, for reasons that have nothing to do with the
    # hyphen, so a FAIL there would have accused the wrong code. What this
    # normalisation owes is that it touches nothing it should not.
    noise = ('Year-over-year and quarter-over-quarter and non-GAAP and '
             'twenty-four-quarter growth')
    check(parse._HYPHEN_PERIOD.sub('X', noise) == noise,
          'no non-period hyphen is rewritten: %r' % noise[:52])
    check(parse._HYPHEN_PERIOD.sub('X', 'in the fourth-quarter of') ==
          'in the X of',
          'while a real period word IS matched, so the check above is not '
          'passing because the pattern matches nothing at all')


main()
