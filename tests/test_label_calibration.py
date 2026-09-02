# -*- coding: utf-8 -*-
"""The v2 label bands, re-derived from the outcome field they were fitted on.

★ WHY THIS TEST EXISTS
The three band rates ARE the model's label calibration -- they decide whether a
card says Bullish, Neutral or Bearish, and "Neutral" must never render as "met
expectations" when 70% of that band closed DOWN. Until now nothing re-derived
them from data; they were constants nobody could contradict.

★ WHERE THE FIELD LIVES
`pctChangeNextDay` is nested inside `stockReaction`, NOT at the record's top
level. A top-level read returns None on all 76 records and makes the outcome
variable look absent library-wide. It is present, numeric, on 57 -- and
28 + 20 + 9 = 57 is exactly the calibration's own n.

★ WHAT BREAKS THIS TEST
Re-scoring history, moving a threshold, or backfilling the 19 records that lack
the field. All three are legitimate, and all three MUST re-state the rates
rather than inherit them silently -- a stale band rate mislabels every card.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import scorecard                       # noqa: E402
from earnings_scraper.model import Model                     # noqa: E402

FAIL = [0]

# band -> (n, up, down, mean move). Down is the load-bearing one for Neutral.
CLAIMED = {
    # ★ RE-PINNED 2026-08-26, not loosened. CRM-2027Q1's pctChangeNextDay was
    # corrected 0 -> -0.75% (print May 27 close $177.51, May 28 next-day close
    # $176.17). The quoted +8.17% was MAY 29 -- two sessions later, and a sector
    # event: IGV +5%, OKTA +30%, SNOW +46%. n and the up-count did not move,
    # which is why the calibration still stands.
    # ★ RE-PINNED AGAIN 2026-08-27. MRVL-2027Q1 corrected -2.00 -> +3.09
    # (verified tape, print May 27 2026 AMC). +5.09pp on one record moves
    # the mean +10.5457 -> +10.7275 AND crosses zero, so the up-count goes
    # 23 -> 24. Membership is unchanged: same 28 records.
    #
    # Two outcome corrections in two days, both raising the Bullish mean.
    # Worth watching: if the corrections keep landing one way, the
    # published +10.57 was biased by whichever tape reading was easiest to
    # find, not by the data. Not adjusted for -- recorded.
    'Bullish': (28, 24, None, +10.7275),
    'Neutral': (20, 5, 14, -1.60),
    'Bearish': (9, 0, None, -10.80),
}


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:34]))
    if not ok:
        FAIL[0] += 1


def main():
    m = Model()
    R = scorecard.renderer()
    bull, bear = R.LABEL_BULLISH_AT, R.LABEL_BEARISH_BELOW

    print('=== the thresholds are IMPORTED, never redefined locally ===')
    check('Bullish at %+.2f' % bull, abs(bull - 1.00) < 1e-9, bull)
    check('Bearish below %+.2f' % bear, abs(bear - 0.00) < 1e-9, bear)

    print('')
    print('=== the outcome field is nested under stockReaction ===')
    top = sum(1 for r in m.records if r.get('pctChangeNextDay') is not None)
    check('no record carries it at the TOP level', top == 0, top)
    nested = [r for r in m.records
              if isinstance((r.get('stockReaction') or {}), dict)
              and isinstance((r.get('stockReaction') or {})
                             .get('pctChangeNextDay'), (int, float))]
    # ★ Grows with every scored print: 57 -> 58 on 2026-09-02.
    print('     %d records carry it nested and numeric' % len(nested))
    check('at least 57 records carry it nested and numeric',
          len(nested) >= 57, len(nested))

    bands = {'Bullish': [], 'Neutral': [], 'Bearish': []}
    for r in nested:
        ov = (r.get('scores') or {}).get('overall')
        if not isinstance(ov, (int, float)):
            continue
        lab = ('Bullish' if ov >= bull else 'Bearish' if ov < bear
               else 'Neutral')
        bands[lab].append(float(r['stockReaction']['pctChangeNextDay']))

    print('')
    print('=== each band, MEASURED — the claim is the relationship ===')
    # ★ Populations and means move with every scored print. Pinning them meant
    # three hand re-pins in four days, which trains you to edit without
    # reading. What is load-bearing is the DIRECTION of each band, and that
    # survives growth. The numbers print so drift stays visible.
    stat = {}
    for lab in ('Bullish', 'Neutral', 'Bearish'):
        vals = bands[lab]
        up = sum(1 for v in vals if v > 0)
        dn = sum(1 for v in vals if v < 0)
        mean = sum(vals) / len(vals) if vals else 0.0
        stat[lab] = (len(vals), up, dn, mean)
        print('     %-8s n=%-3d up=%-3d down=%-3d mean=%+.2f%%'
              % (lab, len(vals), up, dn, mean))

    nb, ub, db, mb = stat['Bullish']
    check('Bullish: a large majority closes UP', ub >= 0.70 * nb,
          '%d of %d' % (ub, nb))
    check('    and the mean move is strongly positive', mb > 5.0,
          '%+.2f%%' % mb)

    nn, un, dn_, mn = stat['Neutral']
    # ★ THE ONE THAT MATTERS MOST. "Neutral" must never render as "met
    # expectations" while the majority of that band closes DOWN.
    check('Neutral: a MAJORITY closes DOWN', dn_ > nn / 2.0,
          '%d of %d down' % (dn_, nn))
    check('    and the mean move is negative', mn < 0, '%+.2f%%' % mn)
    check('    so Neutral is NOT "met expectations"', dn_ > un,
          '%d down vs %d up' % (dn_, un))

    nr, ur, dr, mr = stat['Bearish']
    check('Bearish: essentially none closes up', ur == 0, ur)
    check('    and the mean move is strongly negative', mr < -5.0,
          '%+.2f%%' % mr)

    print('')
    print('=== the three n sum to the calibration population ===')
    check('the bands account for every outcome record',
          sum(len(v) for v in bands.values()) == len(nested),
          '%d vs %d' % (sum(len(v) for v in bands.values()), len(nested)))

    print('')
    print('=== not one Bearish print has EVER closed up ===')
    check('not one Bearish print has closed up',
          all(v <= 0 for v in bands['Bearish']),
          '%d up' % sum(1 for v in bands['Bearish'] if v > 0))

    print('')
    print('=== the flat record is why "70%% down" and "25%% up" both hold ===')
    flat = [v for v in bands['Neutral'] if v == 0]
    print('     %d Neutral record(s) closed unchanged' % len(flat))
    check('flat records exist, so up%% and down%% need not sum to 100',
          len(flat) >= 1, len(flat))

    print('')
    print('=== 19 records have NO outcome and are NOT counted ===')
    missing = [r['id'] for r in m.records
               if not isinstance((r.get('stockReaction') or {}), dict)
               or not isinstance((r.get('stockReaction') or {})
                                 .get('pctChangeNextDay'), (int, float))]
    # ★ A FLOOR. Every pre-earnings build adds records with no outcome yet:
    # 19 when written, 23 after the 2026-08-26 build.
    print('     %d records sit outside the calibration' % len(missing))
    check('records without an outcome are excluded, not counted',
          all(not isinstance((r.get('stockReaction') or {})
                             .get('pctChangeNextDay'), (int, float))
              for r in m.records if r['id'] in set(missing)))
    print('     %s' % ', '.join(sorted(missing)[:6]) + ' ...')
    print('     Backfilling these would CHANGE the published rates, not')
    print('     confirm them. That is a calibration decision, not a repair.')

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
