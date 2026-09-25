# -*- coding: utf-8 -*-
"""A DERIVED ROW'S VERDICT IS CAPPED BY ITS WEAKEST OPERAND.

    HPE[0]  published 4.485 as MATCH, derived from the FY26 EPS guide
            $3.75-$3.85
    HPE[3]  IS THAT GUIDE — and it REFUSED

Same figure, same document, same card: PUBLISHED VIA DERIVATION, REFUSED VIA
DIRECT READ. Either [3] should publish or [0] should not, and nothing on the
card could see the disagreement. oneConditionTwoNames n=16.

★★★ AND IT LANDS WITH DERIVATION COVERAGE, NOT AFTER IT. Every derived row
is an all-vacuous MATCH — fence, basis and period have nothing structural to
read on a computed number — so growing derivation GROWS THE UN-AUDITABLE SET.
A capability that increases the count of rows nothing can check is a
liability on its own terms, so the check ships with the capability.

★★ THE OPERAND IS THE PROVENANCE. On a read row the evidence is the cell's
column headers; on a derived row there is no cell. What vouches for 4.485 is
that $3.75-$3.85 and 16%-20% were each established — and [3] establishing
nothing is exactly what the cap is for.

★ NOTE WHAT THIS EXPOSES ABOUT THE DERIVATION ITSELF: HPE[0]'s base operand
resolves from the ENDPOINTS WRITTEN IN THE sourceRow STRING, not from
re-reading row [3]. It trusts the author's prose over the extractor. The cap
is what makes that visible.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import registry as R                # noqa: E402
from earnings_scraper import sweep as SW                  # noqa: E402

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
    pre, act = rec['preEarnings']['keyKPIs'], rec['actuals']['keyKPIs']
    q = rec.get('fiscalQuarter')

    # ★ THE FOUNDING CASE IS FIXED AND THE RULE IT EARNED IS NOT THEREBY
    # UNTESTED. HPE[3] now reads, because its section heading separates the
    # FY guide from the Q4 guide, so the cap is driven on a SYNTHETIC weak
    # operand below instead.
    j3 = SW.judge(body, pre[3], act[3], R.spec_for(pre[3]), q, record=rec)
    check(j3['verdict'] == 'MATCH' and j3['value'] == 3.8,
          'HPE[3], the FY26 EPS guide, now reads 3.8 and is %s'
          % j3['verdict'])

    j0 = SW.judge(body, pre[0], act[0], R.spec_for(pre[0]), q, record=rec)
    # ★ THE CAP IS NOW BELT AND BRACES, and that is the right order. Since
    # operands are EXTRACTED rather than read out of the sourceRow prose,
    # HPE[0] no longer produces a number at all while [3] refuses — so the
    # refusal arrives from the derivation itself and the cap never has to
    # fire. The cap remains for the case the arithmetic DOES succeed on a
    # weak operand, which is what operand_cap is exercised on below.
    check(j0['verdict'] == 'MATCH' and j0['value'] == 4.485,
          'and HPE[0], derived from it, is %s at %s — the chain closes'
          % (j0['verdict'], j0['value']))

    # ── THE CAP, DRIVEN RED on an operand forced weak ────────────────────
    weak = json.loads(json.dumps(rec))
    weak['preEarnings']['keyKPIs'][3]['extraction']['specState'] = \
        'NEEDS_REMAP'
    cw, whyw = SW.operand_cap(body, R.spec_for(pre[0]), weak, q)
    check(cw == 'UNSPECD' and 'operand [3]' in (whyw or ''),
          'with operand [3] forced UNSPECD the cap reports %s and NAMES it: '
          '%r' % (cw, (whyw or '')[:54]))
    jw = SW.judge(body, weak['preEarnings']['keyKPIs'][0], act[0],
                  R.spec_for(weak['preEarnings']['keyKPIs'][0]), q,
                  record=weak)
    check(jw['verdict'] != 'MATCH',
          'and the derived row is %s, not MATCH — the cap is SHOWN to fire '
          'rather than reported green' % jw['verdict'])

    # ── the cap is a CAP, not a floor: a sound operand does not lift ─────
    cap, why = SW.operand_cap(body, R.spec_for(pre[0]), rec, q)
    check(cap is None,
          'operand_cap does NOT fire where every operand is sound (%s) — '
          'the anti-vacuous half: a cap that always fired would pass every '
          'assertion below it' % cap)

    # ★ ANTI-VACUOUS: with the operand passing, the cap must NOT fire —
    # otherwise this test would pass on a function that always refuses.
    fake = dict(rec, preEarnings=dict(rec['preEarnings'],
                                      keyKPIs=list(pre)))
    fake['preEarnings']['keyKPIs'] = list(pre)
    fake['preEarnings']['keyKPIs'][3] = dict(
        pre[3], extraction=dict(R.spec_for(pre[3]),
                                specState='NOT_EXTRACTABLE',
                                why='QUALITATIVE.'))
    cap2, _ = SW.operand_cap(body, R.spec_for(pre[0]), fake, q)
    check(cap2 is None or SW._RANK.get(cap2, 0) >= SW._RANK['MATCH'],
          'and where the operand is EXCLUDED (rank 5) the cap does NOT fire '
          '(%s) — it is a cap, not a blanket refusal' % cap2)

    # ── a self-referencing chain terminates ──────────────────────────────
    loop = dict(pre[0], extraction=dict(
        R.spec_for(pre[0]), sourceRows=['HPE-2026Q3 [0] self']))
    jl = SW.judge(body, loop, act[0], R.spec_for(loop), q, record=rec)
    check(jl.get('verdict') is not None,
          'a row whose operand is ITSELF still returns a verdict (%s) rather '
          'than recursing — the depth guard is the close' % jl['verdict'])


main()
