# -*- coding: utf-8 -*-
r"""AN EMPTY FENCE IS NOT A PERMISSIVE FENCE.

★★★★★ ABSENCE TREATED AS PERMISSION, A THIRD TIME.

    the basis filter   (column_basis(desc) or want) == want
                       -> an unlabelled column is KEPT
    the region filter  if anchors and not in_any(start, anchors)
                       -> an EMPTY anchor list makes the check VANISH and
                          the whole document becomes the fence

Both read as a check and neither can fail on missing evidence. The region
one is worse in one specific way: it converts an AUTHORING MISTAKE INTO A
WRONG NUMBER rather than into a refusal. On the live NKE print, rows [8]
and [9] had ZERO spans and published anyway -- Converse 3.0 against a hand
read of 263, EMEA 0.001 against a true $3.2B.

★★ MEASURED BEFORE WIRING, over the corpus AND the wire fixtures and live
captures -- 312 row/document pairs, 28 with an anchor declared and not
found:

        18  already refuse, no change
        10  publish from an empty fence   -> all become refusals
         0  CORRECT VALUES LOST

and the ten are not only NKE's two: SNDK 31.5 against a hand-read 45.0,
WDC 51.5 against 55.5, ORCL 60.0 against 67.0. Wrong numbers that have been
published from empty fences all along.

★ AND THE DISTINCTION THAT MAKES IT SAFE: a row declaring NO anchor
searches the whole document BY DESIGN and is untouched. Only a DECLARED
anchor that matches nothing refuses.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X                # noqa: E402
from earnings_scraper import reasons as RE               # noqa: E402

NL = chr(10)

DOC = NL.join([
    'NIKE, Inc. Reports Fiscal 2027 First Quarter Results',
    'Revenues for Converse were $263 million, down 27 percent.',
    'DIVISIONAL REVENUES',
    '  North America   4,862   4,824',
    '  Converse   263   357',
    '  Corporate   4   (23)',
])


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    base = {'specState': 'EXTRACTABLE', 'whereKind': ['PROSE', 'TABLE'],
            'documentLabels': ['Converse'], 'documentUnit': '$M',
            'storedUnit': '$M'}

    # ── a DECLARED anchor that matches nothing ───────────────────────────
    ghost = dict(base, sectionAnchor='TOTAL NIKE BRAND REVENUES')
    check(not X.section_spans(DOC, ghost['sectionAnchor']),
          'the anchor genuinely matches nothing in this document')
    got = X.value_for(DOC, {'name': 'Converse', 'extraction': ghost}) or {}
    check(got.get('value') is None
          and got.get('reasonCode') == 'EMPTY_FENCE',
          'a DECLARED anchor matching nothing REFUSES (%s) rather than '
          'falling back to the whole release' % got.get('reasonCode'))
    check('EMPTY FENCE' in (got.get('why') or '')
          and 'TOTAL NIKE BRAND' in (got.get('why') or ''),
          'and the refusal NAMES the anchor that was not found, so the '
          'authoring mistake is visible on the row')

    # ── ★ NO anchor declared: the whole document, BY DESIGN ──────────────
    free = dict(base)
    out = X.value_for(DOC, {'name': 'Converse', 'extraction': free}) or {}
    check(out.get('reasonCode') != 'EMPTY_FENCE',
          'a row declaring NO anchor is UNTOUCHED (%s) — an undeclared '
          'fence is the whole document by design, and conflating the two '
          'would refuse 208 rows that are working'
          % (out.get('reasonCode') or 'read a value'))

    # ── and a found anchor still reads ───────────────────────────────────
    real = dict(base, sectionAnchor='DIVISIONAL REVENUES')
    ok = X.value_for(DOC, {'name': 'Converse', 'extraction': real}) or {}
    check(ok.get('reasonCode') != 'EMPTY_FENCE',
          'an anchor that IS present never wears this code (%s)'
          % (ok.get('reasonCode') or 'read a value'))

    # ── the reason gate must reject a false claim ────────────────────────
    claim = dict(value=None, reasonCode='EMPTY_FENCE')
    bad, why = RE.verify(DOC, {'extraction': real}, real, None, claim)
    check(not bad and 'DOES' in (why or ''),
          'claiming EMPTY_FENCE where the anchor IS found is rejected: %s'
          % why)
    bad2, why2 = RE.verify(DOC, {'extraction': free}, free, None, claim)
    check(not bad2 and 'NO sectionAnchor' in (why2 or ''),
          'and claiming it on a row with no anchor at all is rejected: %s'
          % why2)
    good, _w = RE.verify(DOC, {'extraction': ghost}, ghost, None, claim)
    check(good, 'while the true claim verifies')


main()
