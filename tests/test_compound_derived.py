# -*- coding: utf-8 -*-
"""A BASE RANGE GROWN BY A RATE RANGE — HPE's priority-1 hero.

Both operands are in THIS release, and neither is the row itself:

    FY26 non-GAAP EPS guide      $3.75 to $3.85     (card row [3])
    FY27 EPS growth framework    16% to 20%         ('Fiscal 2027 Outlook')
    ->                           $4.35 to $4.62     midpoint 4.485

The row had been refusing with 'no candidate matched the declared unit',
which described the wrong failure entirely: the ratio path was the only
derived path that existed, so a PRODUCT row had nowhere to go.

★★★ THE SPEC SAYS 'PRODUCT' AND THE ARITHMETIC IS A COMPOUND. A literal
product is 3.75 x 0.16 = 0.60. The operation performed is base x (1 + growth),
which is what the card's own arithmetic does ('+12% = $3.86' on a $3.45 base).
Rather than silently reinterpret an authored word, the operation is NAMED
GROWTH_COMPOUND and the discrepancy is recorded in derivedFrom.

★★ AND THE AGREEMENT IS NOT THE POINT HERE. 4.485 agrees with the stored 4.50
only at the stored precision, and the two come from DIFFERENT SOURCES — this
is derived from the PRESS RELEASE framework, the hand read is the midpoint of
a range given ON THE CALL. The test pins the RANGE and the OPERANDS, because
those are what the extractor actually established.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import derived as D                # noqa: E402
from earnings_scraper import extract as X                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HPE = os.path.join(HERE, 'fixtures', 'releases', 'HPE-2026-09-02.txt')
LIB = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                   'Projects', 'earnings Model', 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not (os.path.exists(HPE) and os.path.exists(LIB)):
        print('FAIL fixture or library not reachable')
        return
    body = io.open(HPE, encoding='utf-8').read()
    rec = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
           ['records']}['HPE-2026Q3']
    prow = rec['preEarnings']['keyKPIs'][0]

    # ── the operation is READ OFF the recipe, not assumed ────────────────
    check(D.is_compound('FY26 EPS guide RANGE x FY27 EPS GROWTH RANGE — '
                        'a PRODUCT'),
          'a recipe naming a GROWTH operand and a product is a COMPOUND')
    check(not D.is_compound('earnings / revenue'),
          'while a ratio recipe is still a ratio — the two paths coexist, '
          'they do not replace each other')

    # ── ★★★ THE OPERAND IS EXTRACTED, NEVER READ OUT OF THE REFERENCE ───
    # An earlier version preferred the endpoints written in the sourceRow
    # sentence because the referenced row might be refusing. That is exactly
    # the case where it must NOT substitute: A DERIVED VALUE WHOSE OPERAND
    # COMES FROM THE CARD'S PROSE IS THE HAND READ WITH ARITHMETIC APPLIED.
    # It cannot disagree with the author, and it produces a NUMBER.
    live = D.derive(body, prow, rec)
    check((live or {}).get('value') == 4.485,
          'HPE[0] derives 4.485 from the EXTRACTED operand — row [3] now '
          'reads $3.75-$3.85 off its section heading, so the chain closes')
    df0 = (live or {}).get('derivedFrom') or {}
    check((df0.get('base') or {}).get('range') == [3.75, 3.85],
          'and the base is the extracted RANGE %s, not a midpoint squared: '
          'both ends travel, because a band is information the midpoint '
          'discards' % (df0.get('base') or {}).get('range'))

    got = live

    # ★ AND THE CHAIN IS REAL: break the operand and the derivation follows.
    broken = json.loads(json.dumps(rec))
    broken['preEarnings']['keyKPIs'][3]['extraction']['documentLabels'] = [
        'a label this release does not contain']
    dead = D.derive(body, prow, broken)
    check((dead or {}).get('value') is None
          and 'EXTRACTION' in ((dead or {}).get('why') or ''),
          'with row [3] unable to read, HPE[0] REFUSES rather than falling '
          'back on the endpoints written in its own sourceRow prose: %r'
          % ((dead or {}).get('why') or '')[:66])

    check(got.get('value') == 4.485
          and (got.get('rangeLow'), got.get('rangeHigh')) == (4.35, 4.62),
          'the derived RANGE is $%s to $%s, midpoint %s — the same endpoints '
          'the card reached by hand'
          % (got.get('rangeLow'), got.get('rangeHigh'), got.get('value')))

    df = got.get('derivedFrom') or {}
    check(df.get('operation') == 'GROWTH_COMPOUND',
          'the operation is NAMED on the row (%s), so the card can say which '
          'arithmetic ran' % df.get('operation'))
    check('PRODUCT' in (df.get('recipeWording') or '')
          and '(1 + growth)' in (df.get('note') or ''),
          'and the spec-says-PRODUCT / arithmetic-is-a-compound discrepancy '
          'is RECORDED, not silently reconciled')
    check((df.get('base') or {}).get('range') == [3.75, 3.85],
          'both operands are reported with their values: base %s'
          % (df.get('base') or {}).get('range'))
    check((df.get('growth') or {}).get('range') == [0.16, 0.2],
          'growth %s — read from THIS release, which RAISED the framework '
          'from 12-16%% to 16-20%%' % (df.get('growth') or {}).get('range'))

    # ── a card that references itself must refuse, not recurse ───────────
    loop = {'name': 'self', 'extraction': {
        'specState': 'EXTRACTABLE', 'documentUnit': '$',
        'derived': 'A RANGE x B GROWTH RANGE — a PRODUCT',
        'sourceRows': ['HPE-2026Q3 [0] no range written here']}}
    spun = D.derive(body, loop, rec)
    check((spun or {}).get('value') is None
          and 'operand' in ((spun or {}).get('why') or ''),
          'a self-referencing row REFUSES and names the operand that failed '
          '(%r) — RE-ENTRY is the close. `depth` cannot cross into '
          'value_for, so counting frames guards nothing and a genuine cycle '
          'would have hung the extractor on a live print'
          % ((spun or {}).get('why') or '')[:54])

    # ★ AND THE CYCLE IS DRIVEN, not assumed: row [0] pointed at ITSELF.
    import copy as _copy
    cyc = _copy.deepcopy(rec)
    cyc['preEarnings']['keyKPIs'][0]['extraction']['sourceRows'] = [
        'HPE-2026Q3 [0] itself',
        "FY27: 'growth to be in the range of 16% to 20%'"]
    out_c = D.derive(body, cyc['preEarnings']['keyKPIs'][0], cyc)
    check((out_c or {}).get('value') is None,
          'a row whose operand IS ITSELF refuses instead of recursing — one '
          'cell lost, the card still renders')

    # ── end to end ───────────────────────────────────────────────────────
    out = X.value_for(body, prow, record=rec) or {}
    check(out.get('value') == 4.485,
          'and value_for returns it end to end (%s) — a priority-1 hero '
          'that had been REFUSED now carries a value whose every operand '
          'was EXTRACTED' % out.get('value'))


main()
