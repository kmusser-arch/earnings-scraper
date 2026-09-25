# -*- coding: utf-8 -*-
"""All six verdicts, each shown to FIRE — FALSE_MATCH above all.

★★★ DIGITS AGREEING IS NOT THE SAME AS BEING RIGHT. Nine rows moved into
MATCH between the frozen column and the live sweep, and a MISMATCH becomes a
MATCH two ways: the extractor found the right cell, or it found a DIFFERENT
WRONG CELL whose digits agree. Nothing in the system distinguished those, so
every tuning decision was scored by a gradient that rewards coincidence
exactly as much as correctness.

FALSE_MATCH exists from the writer's first run rather than being bolted on
afterwards, because bolting it on means re-running that loop against the same
blind metric for however long it takes.

★★ AND A VERDICT THAT NEVER FIRES LOOKS EXACTLY LIKE ONE THAT PASSES. The
corpus reports FALSE_MATCH 0; that number is worth nothing unless the verdict
can be shown to fire, so each of the three provenance checks is driven to
failure here and the full judge is driven to all six outcomes.

★ THE BLIND SPOT IS MEASURED, NOT ASSUMED. On a horizontal grid `pos` points
at the ROW, not at the selected cell, so a clause carrying both GAAP and
non-GAAP cannot discriminate: 3 of the 34 MATCH rows have an inert basis
check for that reason. All 34 still have at least one check that applies,
because every extractable row declares a period.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import sweep as SW            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AVGO = os.path.join(HERE, 'fixtures', 'releases', 'AVGO-2026-09-02.txt')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not os.path.exists(AVGO):
        print('FAIL AVGO fixture missing')
        return
    body = io.open(AVGO, encoding='utf-8').read()

    # ── each provenance check must be able to say NO ─────────────────────
    gaap = body.lower().find('gaap operating income')
    ok, fails = SW.provenance(body, gaap,
                              {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'})
    check(not ok and any('GAAP' in f for f in fails),
          'BASIS check fires: a non-GAAP row whose position sits in a '
          'GAAP-only clause')

    q4 = body.find('In Q4 the momentum')
    ok2, f2 = SW.provenance(body, q4,
                            {'period': 'REPORTED', 'specState': 'EXTRACTABLE'})
    check(not ok2 and any('GUIDE_NEXT_Q' in f for f in f2),
          'PERIOD check fires: a REPORTED row whose position sits in an '
          'explicit Q4 guide clause')

    ok3, f3 = SW.provenance(body, 10, {
        'sectionAnchor': ['Third Quarter Fiscal Year 2026 Financial '
                          'Highlights'], 'specState': 'EXTRACTABLE'})
    check(not ok3 and any('outside' in f for f in f3),
          'FENCE check fires: a position far outside the declared section')

    # ── and each must be able to say YES ─────────────────────────────────
    okp, _ = SW.provenance(body, body.find('Infrastructure software'),
                           {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'})
    check(okp, 'and the basis check PASSES where the clause does not '
               'contradict — it is not simply on')

    # ── the full judge reaches all six ───────────────────────────────────
    spec = {'specState': 'EXTRACTABLE', 'basis': 'non-GAAP',
            'storedUnit': '$B', 'documentUnit': '$B'}
    prow = {'extraction': spec}
    slot = {'actual': 16.0}
    good = {'value': 16.0, 'value_musd': 16000.0, 'why': None,
            'pos': body.find('Infrastructure software')}
    bad = dict(good, pos=gaap)

    cases = [
        ('MATCH', good),
        ('FALSE_MATCH', bad),
        ('MISMATCH', dict(good, value=99.0, value_musd=99000.0)),
        ('LOST', {'value': None, 'why': None}),
        ('REFUSED', {'value': None, 'why': '2 candidates tie on unit'}),
    ]
    for want, got in cases:
        v = SW.judge(body, prow, slot, spec, 3, got=got)['verdict']
        check(v == want, 'judge returns %s where it should (%s)' % (v, want))

    v6 = SW.judge(body, {'extraction': {'specState': 'NOT_EXTRACTABLE'}},
                  slot, {'specState': 'NOT_EXTRACTABLE'}, 3, got={})['verdict']
    check(v6 == 'EXCLUDED', 'judge returns EXCLUDED for a NOT_EXTRACTABLE row')

    # ── the report cannot be quoted without its denominator ──────────────
    line = SW.report({'MATCH': 34, 'MISMATCH': 1}, 102)
    check('of 102' in line and 'FALSE_MATCH 0' in line
          and 'LOST 0' in line,
          'the report line carries the denominator AND prints every verdict '
          'including the zeros: %r' % line[:70])


main()
