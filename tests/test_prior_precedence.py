# -*- coding: utf-8 -*-
"""A printed PRIOR marker outranks a NEARER level preposition — within a clause.

SNOW writes 'Product revenue of $6,070 million, representing 36% year-over-year
growth, up from previous guidance of $5,840 million'. Both 'up from' and
'guidance of' sit inside the 34-character back-context of 5,840, and the
LEVEL preposition wins because it is nearer. So the row returned the PREVIOUS
guidance — the very number 'up from' exists to mark.

★★★ PROXIMITY IS A HEURISTIC, A PRINTED MARKER IS EVIDENCE, and where they
disagree the printed signal wins.

★★ BUT ONLY WITHIN THE SAME CLAUSE, AND THE MEASUREMENT IS WHY. The unbounded
form — 'a PRIOR marker ANYWHERE in the back-context' — flips 27 level
candidates across the corpus, and 14 of them take their marker from the
PREVIOUS SENTENCE:

    'up 112.2% from the prior-year period. Data Center Networking was $382
     million'

382 is a hand-read MATCH, and the marker governing it belongs to the sentence
before. Bounding the rule at the clause break takes 27 flips down to 13 and
keeps every one of those. That bound is not a new invention: period.py already
states that a marker only governs a number it PRECEDES.

Marginal contribution, measured by A/B on the standing sweep (8 releases,
2026-09-21): MATCH 29 -> 30, MISMATCH 2 -> 1.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'releases')
MODEL = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
LIB = os.path.join(MODEL, 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def roles(window, spec=None):
    return {c['raw']: c['role'] for c in X.candidates(window, spec or {})}


def main():
    # ── the marker wins over the nearer level preposition ────────────────
    snow = ('of $6,070 million, representing 36% year-over-year growth, '
            'up from previous guidance of $5,840 million')
    r = roles(snow)
    check(r.get('5,840') == 'delta',
          "5,840 is PRIOR: 'up from' outranks the nearer 'guidance of'")
    check(r.get('6,070') != 'delta',
          'and 6,070 is not demoted with it')

    # ── a marker in the PREVIOUS sentence does not govern ────────────────
    hpe = ('up 112.2% from the prior-year period. Data Center Networking '
           'was $382 million')
    r2 = roles(hpe)
    check(r2.get('382') == 'level',
          '382 stays a LEVEL — the prior-year marker belongs to the sentence '
          'before it, and 382 is a hand-read MATCH')

    # ── the same-clause comparison still flips ───────────────────────────
    avgo = ('cash and cash equivalents at the end of the fiscal quarter were '
            '$24.0 billion, compared to $19.6 billion')
    r3 = roles(avgo)
    check(r3.get('19.6') == 'delta',
          "19.6 is PRIOR: 'compared to' governs it inside the clause")
    check(r3.get('24.0') == 'level', 'and 24.0 remains the level')

    # ── the bound is a clause break, not a character count ───────────────
    check(bool(X._CLAUSE_BREAK.search('abc. def')),
          'a full stop plus space is a clause break')
    check(not X._CLAUSE_BREAK.search('up from previous guidance of '),
          'and a comma is not — the marker still governs across it')

    # ── the live row, end to end ─────────────────────────────────────────
    path = os.path.join(FIX, 'SNOW-2026-09-02.txt')
    if os.path.exists(path) and os.path.exists(LIB):
        body = io.open(path, encoding='utf-8').read()
        recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
                ['records']}
        rec = recs.get('SNOW-2027Q2')
        rows = [r for r in (rec or {}).get('preEarnings', {}).get('keyKPIs',
                                                                  [])
                if 'FY27 Product Revenue Guide' in (r.get('name') or '')]
        if rows:
            got = X.value_for(body, rows[0], record=rec)
            check(got.get('value') != 5840.0,
                  'the live SNOW row no longer returns 5,840, the previous '
                  'guidance (it returns %r)' % (got.get('value'),))


main()
