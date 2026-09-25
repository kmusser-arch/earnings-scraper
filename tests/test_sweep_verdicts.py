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

★ THE BLIND SPOT IS MEASURED, NOT ASSUMED, AND IT IS WORSE THAN IT LOOKED.
`pos` now points at the SELECTED CELL rather than the matched row, which is
correct provenance and made the audit EMPTIER, not richer: basis evidence went
1 -> 0 and the all-vacuous MATCH rows went 7 -> 8. A cell is surrounded by
digits; the words are in the header, and these checks read prose.

    MATCH 34 = 29 with >=1 DISCRIMINATING check + 5 ALL-VACUOUS
    evidence-bearing rows: fence 18 · period 18 · basis 3

★★★ AND EACH CHECK NOW REPORTS WHICH OF THREE THINGS HAPPENED, because a
check whose behaviour on missing evidence is ACCEPT cannot fail when it has
no evidence at all — which is why FALSE_MATCH 0 was never news.

    EVIDENCE  it had something to read and could have failed
    ABSENT    the column exists and carries no such word — a fact about the
              DOCUMENT, not about our blindness
    VACUOUS   nothing readable at all — blind, and saying so

DECLARING A CHECK IS NOT DISCRIMINATING WITH IT. An earlier version of this
docstring said all 34 had a live check 'because every extractable row declares
a period'. Every row declaring one is exactly why that sentence proves
nothing.
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
    ok, fails, _st = SW.provenance(body, gaap,
                              {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'})
    check(not ok and any('GAAP' in f for f in fails),
          'BASIS check fires: a non-GAAP row whose position sits in a '
          'GAAP-only clause')

    q4 = body.find('In Q4 the momentum')
    ok2, f2, _st2 = SW.provenance(body, q4,
                            {'period': 'REPORTED', 'specState': 'EXTRACTABLE'})
    check(not ok2 and any('GUIDE_NEXT_Q' in f for f in f2),
          'PERIOD check fires: a REPORTED row whose position sits in an '
          'explicit Q4 guide clause')

    ok3, f3, _st3 = SW.provenance(body, 10, {
        'sectionAnchor': ['Third Quarter Fiscal Year 2026 Financial '
                          'Highlights'], 'specState': 'EXTRACTABLE'})
    check(not ok3 and any('outside' in f for f in f3),
          'FENCE check fires: a position far outside the declared section')

    # ── and each must be able to say YES ─────────────────────────────────
    okp, _fp, _stp = SW.provenance(body, body.find('Infrastructure software'),
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

    # ── ★★★ EXCLUDED SPLITS THREE WAYS, AND ONLY ONE LEAVES ─────────────
    # A row no one ruled on is not an excused row. Folding NEEDS_REMAP and
    # unclassified exclusions into EXCLUDED shrank the denominator by our own
    # gaps, which is how a headline nobody could reconcile gets made.
    def verdict(spec):
        return SW.judge(body, {'extraction': spec}, slot, spec, 3,
                        got={})['verdict']

    v6 = verdict({'specState': 'NOT_EXTRACTABLE',
                  'why': 'QUALITATIVE — forward commentary.'})
    check(v6 == 'EXCLUDED',
          'a closed-list reason (QUALITATIVE) is EXCLUDED — the only exit')
    v7 = verdict({'specState': 'NOT_EXTRACTABLE',
                  'why': 'Buyback is in the cash-flow statement.'})
    check(v7 == 'UNCLASSIFIED',
          'a NOT_EXTRACTABLE row whose reason is NOT on the closed list is '
          'UNCLASSIFIED and stays in the denominator — nobody ruled on it')
    v8 = verdict({'specState': 'NEEDS_REMAP'})
    check(v8 == 'UNSPECD',
          'NEEDS_REMAP is UNSPECD and stays in: the issuer changed '
          'disclosure, our spec is stale, and that is OUR gap')
    v9 = SW.judge(body, {'extraction': spec}, {'actual': None}, spec, 3,
                  got=good)['verdict']
    check(v9 == 'NO_ANSWER_KEY',
          'a value read with no hand read to compare gets its OWN verdict, '
          'not an exit — folding it into EXCLUDED hid it inside one')
    # ★ AND THE AUTHORED FIELD BEATS THE PROSE MATCH, because matching prose
    # is inference and this decides whether a row counts against us.
    v10 = verdict({'specState': 'NOT_EXTRACTABLE', 'why': 'QUALITATIVE.',
                   'exclusionClass': 'NOT_IN_PR'})
    check(v10 == 'EXCLUDED',
          'and an authored exclusionClass is read before any prose match')

    # ── the three STATES, each shown to occur ────────────────────────────
    # ★ A STATE THAT NEVER OCCURS LOOKS EXACTLY LIKE ONE THAT IS CORRECT.
    _, _, st_struct = SW.provenance(
        body, 0, {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'},
        axes={'basis': 'non-GAAP', 'period': None})
    check(st_struct['basis'] == SW.EVIDENCE,
          'a cell whose COLUMN is labelled non-GAAP gives the basis check '
          'EVIDENCE — read from structure, not from prose')

    okc, failc, st_bad = SW.provenance(
        body, 0, {'basis': 'GAAP', 'specState': 'EXTRACTABLE'},
        axes={'basis': 'non-GAAP', 'period': None})
    check(not okc and st_bad['basis'] == SW.EVIDENCE
          and any('COLUMN' in f for f in failc),
          'and the SAME source fails when the column contradicts the row: '
          '%r' % (failc[0] if failc else None))

    _, _, st_abs = SW.provenance(
        body, 0, {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'},
        axes={'basis': None, 'period': None,
              'basisState': 'ABSENT_IN_DOCUMENT'})
    check(st_abs['basis'] == SW.ABSENT and st_abs['evidenceCount'] == 0,
          'a column the grid READ and found unlabelled reports ABSENT, not a '
          'silent pass — the ruling keys on this')

    # ★★★ AND THE OTHER EMPTY IS NOT THE SAME EMPTY.
    _, _, st_unread = SW.provenance(
        body, 0, {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'},
        axes={'basis': None, 'period': None,
              'basisState': 'UNREAD_BY_GRID'})
    check(st_unread['basis'] == SW.VACUOUS,
          'while a cell NO READER LOOKED AT reports VACUOUS — blindness in '
          'us, not silence in the document, and the strict arm must not '
          'refuse on it')

    _, _, st_vac = SW.provenance(
        body, body.find('Infrastructure software'),
        {'basis': 'non-GAAP', 'specState': 'EXTRACTABLE'})
    check(st_vac['basis'] in (SW.EVIDENCE, SW.VACUOUS),
          'a PROSE row still falls back to the clause (%s) — structure '
          'first, text second, never text where structure exists'
          % st_vac['basis'])

    # ── the VERTICAL column class is period evidence ─────────────────────
    _, _, st_seq = SW.provenance(
        body, 0, {'period': 'REPORTED', 'specState': 'EXTRACTABLE'},
        axes={'basis': None, 'period': 'PRIOR_YEAR_Q'})
    check(st_seq['period'] == SW.EVIDENCE,
          'vtables already classified every column; the SELECTED class is '
          'period evidence and was computed and discarded until now')
    okq, failq, _ = SW.provenance(
        body, 0, {'period': 'REPORTED', 'specState': 'EXTRACTABLE'},
        axes={'basis': None, 'period': 'PRIOR_YEAR_Q'})
    check(not okq and any('PRIOR_YEAR_Q' in f for f in failq),
          'and a REPORTED row sitting on a PRIOR_YEAR_Q column FAILS: %r'
          % (failq[0] if failq else None))

    # ★★ WHAT THIS CANNOT TELL APART, asserted rather than hoped: a
    # horizontal header period is used for AGREEMENT ONLY, because ORCL
    # heads CALENDAR years against a fiscal year two ahead.
    oky, faily, st_y = SW.provenance(
        body, 0, {'period': 'REPORTED', 'specState': 'EXTRACTABLE'},
        axes={'basis': None, 'period': (2019, 3)},
        record={'fiscalYear': 2026, 'fiscalQuarter': 3})
    check(oky and not faily and st_y['period'] == SW.VACUOUS,
          'a header year that DISAGREES is inconclusive, never a failure — '
          'the fiscal/calendar offset is indistinguishable from a wrong '
          'column and this check must not pretend otherwise')

    # ── the report cannot be quoted without its denominator ──────────────
    line = SW.report({'MATCH': 34, 'MISMATCH': 1, 'EXCLUDED': 19,
                      'UNSPECD': 3}, 102)
    check('of 102' in line and 'FALSE_MATCH 0' in line
          and 'LOST 0' in line and 'GRADED POPULATION 38' in line,
          'the report line carries the denominator AND prints every verdict '
          'including the zeros: %r' % line[:70])


main()
