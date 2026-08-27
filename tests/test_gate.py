"""PR-only decision gate tests.

Pins the three corrections from the 2026-08-20 addendum:
  1. reaction is NESTED at stockReaction.pctChangeNextDay
  2. no renormalization -- the ±0.40 bracket plus the cohort base rate, and
     containment asserted on every run
  3. no positioning modifier -- 6/29 coverage, unvalidated
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import gate                       # noqa: E402
from earnings_scraper.model import Model                # noqa: E402


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, got))

    model = Model()
    fw = gate.framework_from(model)

    print('=== framework comes from the library, never hardcoded ===')
    check('prOnlyGateFramework loaded', bool(fw.get('bands')),
          sorted(fw.get('bands') or {}))
    check('all three bands present',
          set(fw['bands']) == {'DECISIVE_BULLISH', 'DECISIVE_BEARISH',
                               'STAY_FOR_CALL'})
    check('framework is in Model.frameworks',
          'prOnlyGateFramework' in model.frameworks)
    check('narrative swing is exactly 0.40',
          abs(gate.NARRATIVE_SWING - 0.40) < 1e-12, gate.NARRATIVE_SWING)

    print()
    print('=== bracket arithmetic ===')
    g = gate.evaluate(1.0, 1.0, 0.5, fw)          # CSCO's three known scores
    # partial covers only the three KNOWN categories, whose weights sum to
    # 0.80 -- it is not the stored 4-category overall. CSCO: 0.65 partial,
    # and 0.65 + 0.20*(-1.5) = 0.35, which is the stored overall.
    check('CSCO partial = 0.65', abs(g['partial'] - 0.65) < 1e-9, g['partial'])
    check('bracket is [0.25, 1.05]',
          g['overallBracket'] == [0.25, 1.05], g['overallBracket'])
    check('stored overall 0.35 sits inside the bracket',
          gate.assert_containment(g['overallBracket'],
                                  (model.record_by_id('CSCO-2026Q4')
                                   ['scores']['overall'])) is True)
    check('bracket width is exactly 0.80',
          abs((g['overallBracket'][1] - g['overallBracket'][0]) - 0.80) < 1e-9)
    check('CSCO lands STAY_FOR_CALL', g['band'] == 'STAY_FOR_CALL', g['band'])
    check('no point estimate emitted', g['overallPoint'] is None)
    check('renormalized flag is False', g['renormalized'] is False)
    check('positioningApplied is False', g['positioningApplied'] is False)
    check('cohortApplies True when narrative is the only unknown',
          g['cohortApplies'] is True)
    check('bracketWidth reported', g['bracketWidth'] == 0.80, g['bracketWidth'])

    print()
    print('=== generalised bracket when MORE than narrative is unknown ===')
    gp = gate.evaluate_partial(dict(currentQuarter=1.5, nextQGuidance=None,
                                    fyGuidance=1.0, narrative=None), fw)
    check('known/unknown split correct',
          gp['knownCategories'] == ['currentQuarter', 'fyGuidance']
          and gp['unknownCategories'] == ['nextQGuidance', 'narrative'],
          gp['unknownCategories'])
    check('partial = 0.20*1.5 + 0.30*1.0 = 0.60',
          abs(gp['partial'] - 0.60) < 1e-9, gp['partial'])
    check('swing widens to 0.30*2 + 0.20*2 = 1.00',
          gp['bracketWidth'] == 2.00, gp['bracketWidth'])
    check('★ cohort base rates do NOT apply', gp['cohortApplies'] is False)
    check('no base rate attached', gp['cohortBaseRate'] is None)
    check('no tail warning attached', gp['tailWarning'] is None)
    check('actionable says WIDENED BRACKET',
          'WIDENED BRACKET' in gp['actionable'])
    check('still never renormalizes', gp['renormalized'] is False)
    gp2 = gate.evaluate_partial(dict(currentQuarter=1.0, nextQGuidance=1.0,
                                     fyGuidance=0.5, narrative=None), fw)
    check('narrative-only via evaluate_partial matches evaluate',
          gp2['overallBracket'] == g['overallBracket']
          and gp2['cohortApplies'] is True, gp2['overallBracket'])
    allnone = gate.evaluate_partial(dict(currentQuarter=None,
                                         nextQGuidance=None, fyGuidance=None,
                                         narrative=None), fw)
    check('all-unknown yields no band', allnone['band'] is None)

    print()
    print('=== the rejected renormalization ===')
    # 25 / 37.5 / 37.5 on CSCO's three -> +0.81 BULLISH, on a -8.40% print.
    renorm = 0.25 * 1.0 + 0.375 * 1.0 + 0.375 * 0.5
    check('renormalizing CSCO would give +0.81', abs(renorm - 0.8125) < 1e-9,
          round(renorm, 4))
    # Under v1 this crossed the +0.50 Bullish floor. Under v2 it does not, so
    # the finding rests on the score MOVING toward bullish on a print that fell
    # 8.40% -- not on the label flipping.
    check('renormalizing moves it toward bullish', renorm > 0.35,
          round(renorm, 4))
    check('and it does NOT reach the v2 Bullish threshold',
          renorm < gate.label_thresholds()[0], round(renorm, 4))
    check('the gate does NOT flip it', g['band'] != 'DECISIVE_BULLISH')
    csco = model.record_by_id('CSCO-2026Q4')
    check('CSCO actually fell', (gate.reaction_of(csco) or 0) < 0,
          gate.reaction_of(csco))
    check('the "why" is carried on every result',
          'REJECTED' in (g.get('doNotRenormalize') or ''))

    print()
    print('=== band boundaries ===')
    # The three known weights sum to 0.80, so an all-equal score s gives
    # ★ Recomputed at scoreLabelCalibration v2 (Bullish >= +1.00, Bearish <
    # 0.00), imported from render_scorecard. partial = 0.8s for an even print,
    # and DECISIVE_BULLISH now needs lo >= 1.00, i.e. partial >= 1.40 -- so even
    # an all-+1.5 print is STAY_FOR_CALL. The band got much harder to reach,
    # which is the point: the old +0.5 floor labelled a cohort that fell 67%.
    for cq, nq, fy, expected in [
        (2.0, 2.0, 2.0, 'DECISIVE_BULLISH'),     # partial 1.60, lo 1.20
        (1.5, 1.5, 1.5, 'STAY_FOR_CALL'),        # partial 1.20, lo 0.80
        (0.0, 1.5, 1.5, 'STAY_FOR_CALL'),        # partial 0.90, lo 0.50
        (2.0, 1.5, 2.0, 'DECISIVE_BULLISH'),     # partial 1.75, lo 1.35
        (0.5, 1.5, 1.0, 'STAY_FOR_CALL'),        # partial 0.85, lo 0.45
        (1.0, 1.0, 1.0, 'STAY_FOR_CALL'),        # partial 0.80, lo 0.40
        (0.0, 0.0, 0.0, 'STAY_FOR_CALL'),
        (-2.0, -2.0, -2.0, 'DECISIVE_BEARISH'),  # partial -1.60, hi -1.20
        (-1.0, -1.0, -1.0, 'DECISIVE_BEARISH'),  # partial -0.80, hi -0.40
        (-0.5, -0.5, -0.5, 'DECISIVE_BEARISH'),  # partial -0.40, hi 0.00 exact
        (0.0, -1.5, -1.5, 'DECISIVE_BEARISH'),   # partial -0.90, hi -0.50 exact

    ]:
        got = gate.evaluate(cq, nq, fy, fw)['band']
        check('(%+.1f,%+.1f,%+.1f) -> %s' % (cq, nq, fy, expected),
              got == expected, got)

    print()
    print('=== a None category aborts, never substitutes ===')
    for args in ((None, 1.0, 1.0), (1.0, None, 1.0), (1.0, 1.0, None)):
        try:
            gate.evaluate(*args, framework=fw)
            check('None in %s raises' % (args,), False, 'no raise')
        except gate.IncompleteScore as exc:
            check('None aborts the gate: %s' % str(exc).split('.')[0][:34], True)

    print()
    print('=== containment is asserted, and a breach raises ===')
    check('valid overall contained',
          gate.assert_containment([-0.05, 0.75], 0.35) is True)
    check('None overall is a no-op',
          gate.assert_containment([-0.05, 0.75], None) is None)
    try:
        gate.assert_containment([-0.05, 0.75], 0.95)
        check('out-of-bracket overall raises', False, 'no raise')
    except gate.BracketContainmentError:
        check('out-of-bracket overall raises BracketContainmentError', True)

    print()
    print('=== reaction path is NESTED ===')
    check('reads stockReaction.pctChangeNextDay',
          gate.reaction_of({'stockReaction': {'pctChangeNextDay': -8.4}}) == -8.4)
    check('falls back to beatMagnitude.reactionPct',
          gate.reaction_of({'beatMagnitude': {'reactionPct': -3.2}}) == -3.2)
    check('prefers stockReaction over the fallback',
          gate.reaction_of({'stockReaction': {'pctChangeNextDay': -8.4},
                            'beatMagnitude': {'reactionPct': 1.0}}) == -8.4)
    check('a TOP-LEVEL pctChangeNextDay is ignored (not the contract)',
          gate.reaction_of({'pctChangeNextDay': -8.4}) is None)
    check('missing reaction -> None', gate.reaction_of({}) is None)
    covered = sum(1 for r in model.records if gate.reaction_of(r) is not None)
    check('live library reaction coverage is 57', covered == 57, covered)

    print()
    print('=== published tally reproduced from the live library ===')
    tally = {}
    contained = 0
    evaluable = 0
    for rec in model.records:
        s = rec.get('scores') or {}
        try:
            gg = gate.evaluate(s.get('currentQuarter'), s.get('nextQGuidance'),
                               s.get('fyGuidance'), fw)
        except gate.IncompleteScore:
            # ★ A PRE-EARNINGS card has no scores yet. It is not a containment
            # failure; it is a print that has not happened.
            continue
        evaluable += 1
        if gate.assert_containment(gg['overallBracket'], s.get('overall')):
            contained += 1
        px = gate.reaction_of(rec)
        if px is None:
            continue
        t = tally.setdefault(gg['band'], dict(n=0, down=0, total=0.0))
        t['n'] += 1
        t['down'] += (px < 0)
        t['total'] += px

    # ★ THE DENOMINATOR IS EVALUABLE RECORDS, NOT ALL RECORDS. The loop above
    # skips anything the gate cannot evaluate -- which is precisely a
    # PRE-EARNINGS card. Comparing against len(model.records) was right only
    # while every record happened to be scored.
    pending = len(model.records) - evaluable
    print('     %d evaluable · %d pending/incomplete · %d records'
          % (evaluable, pending, len(model.records)))
    check('containment holds for every EVALUABLE record',
          contained == evaluable, '%d of %d' % (contained, evaluable))

    # ★ THE PUBLISHED 29 / 1 / 27 TALLY IS A v1 MEASUREMENT AND IS PINNED AS
    # HISTORY. It is what produced the STAY_FOR_CALL base rate, so it must stay
    # reproducible -- but it describes the v1 populations, not today's bands.
    # Recomputed here at the v1 thresholds explicitly, so the number survives
    # the recalibration instead of being quietly overwritten.
    def _tally_at(bull, bear):
        out = {}
        for rec in model.records:
            sc = rec.get('scores') or {}
            if any(not isinstance(sc.get(k), (int, float)) for k in
                   ('currentQuarter', 'nextQGuidance', 'fyGuidance')):
                continue
            partial = (0.20 * sc['currentQuarter'] + 0.30 * sc['nextQGuidance']
                       + 0.30 * sc['fyGuidance'])
            lo, hi = partial - 0.40, partial + 0.40
            if lo >= bull - 1e-9:
                bd = 'DECISIVE_BULLISH'
            elif hi <= bear + 1e-9:
                bd = 'DECISIVE_BEARISH'
            else:
                bd = 'STAY_FOR_CALL'
            px = gate.reaction_of(rec)
            if px is None:
                continue
            t = out.setdefault(bd, dict(n=0, down=0, total=0.0))
            t['n'] += 1
            t['down'] += (px < 0)
            t['total'] += px
        return out

    v1 = _tally_at(0.50, -0.50)
    check('v1 history: DECISIVE_BULLISH n=29', v1['DECISIVE_BULLISH']['n'] == 29,
          v1['DECISIVE_BULLISH']['n'])
    check('v1 history: DECISIVE_BEARISH n=1', v1['DECISIVE_BEARISH']['n'] == 1,
          v1['DECISIVE_BEARISH']['n'])
    check('v1 history: STAY_FOR_CALL n=27', v1['STAY_FOR_CALL']['n'] == 27,
          v1['STAY_FOR_CALL']['n'])
    sfc1 = v1['STAY_FOR_CALL']
    check('v1 history: STAY_FOR_CALL mean -3.80%',
          abs(sfc1['total'] / sfc1['n'] + 3.80) < 0.005,
          '%+.2f%%' % (sfc1['total'] / sfc1['n']))
    check('v1 history: STAY_FOR_CALL 21 of 27 down', sfc1['down'] == 21,
          sfc1['down'])

    # ★ And the LIVE tally, at the imported thresholds. Membership moved, which
    # is why the gate reports cohortApplies=False rather than carrying the v1
    # rate onto a different population.
    bull, bear = gate.label_thresholds()
    check('the live thresholds are v2', (bull, bear) == (1.0, 0.0),
          (bull, bear))
    live_n = sum(t['n'] for t in tally.values())
    check('the same 57 reactions are still classified', live_n == 57, live_n)
    check('DECISIVE_BULLISH shrank under v2',
          tally['DECISIVE_BULLISH']['n'] < v1['DECISIVE_BULLISH']['n'],
          '%d vs %d' % (tally['DECISIVE_BULLISH']['n'],
                        v1['DECISIVE_BULLISH']['n']))
    check('DECISIVE_BEARISH grew under v2',
          tally['DECISIVE_BEARISH']['n'] > v1['DECISIVE_BEARISH']['n'],
          '%d vs %d' % (tally['DECISIVE_BEARISH']['n'],
                        v1['DECISIVE_BEARISH']['n']))
    g_live = gate.evaluate(0.0, 0.0, 0.0, fw)
    check('the gate refuses to quote a v1 base rate on a v2 band',
          (g_live.get('labelCalibration') or {}).get('cohortApplies') is False,
          (g_live.get('labelCalibration') or {}).get('cohortApplies'))
    check('and it names which calibration measured it',
          'v1' in ((g_live.get('labelCalibration') or {})
                   .get('baseRateMeasuredUnder') or ''))

    print()
    print('=== the tail is never reported without the base rate ===')
    sfc_g = gate.evaluate(0.0, 0.0, 0.0, fw)
    check('STAY_FOR_CALL carries a base rate',
          bool(sfc_g.get('cohortBaseRate')))
    check('STAY_FOR_CALL carries the tail warning',
          bool(sfc_g.get('tailWarning')))
    check('actionable line names both the lean and the tail',
          'SHORT-SIDE' in sfc_g['actionable']
          and 'tail' in sfc_g['actionable'].lower(), sfc_g['actionable'][:52])
    bear = gate.evaluate(-2.0, -2.0, -2.0, fw)
    check('DECISIVE_BEARISH says NO BASE RATE EXISTS',
          'NO BASE RATE' in bear['actionable'], bear['actionable'][:44])
    bull = gate.evaluate(2.0, 2.0, 2.0, fw)
    check('DECISIVE_BULLISH names the untested positioning caveat',
          'UNTESTED' in bull['actionable'], bull['actionable'][-40:])

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
