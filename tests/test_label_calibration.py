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
    check('57 records carry it nested and numeric', len(nested) == 57,
          len(nested))

    bands = {'Bullish': [], 'Neutral': [], 'Bearish': []}
    for r in nested:
        ov = (r.get('scores') or {}).get('overall')
        if not isinstance(ov, (int, float)):
            continue
        lab = ('Bullish' if ov >= bull else 'Bearish' if ov < bear
               else 'Neutral')
        bands[lab].append(float(r['stockReaction']['pctChangeNextDay']))

    print('')
    print('=== each band re-derives its claimed rate ===')
    for lab in ('Bullish', 'Neutral', 'Bearish'):
        vals = bands[lab]
        n, up, down, mean = CLAIMED[lab]
        got_up = sum(1 for v in vals if v > 0)
        got_dn = sum(1 for v in vals if v < 0)
        got_mean = sum(vals) / len(vals) if vals else 0.0
        check('%-8s n = %d' % (lab, n), len(vals) == n, len(vals))
        check('    up %d of %d' % (up, n), got_up == up, got_up)
        if down is not None:
            check('    DOWN %d of %d — the reason Neutral is not "met '
                  'expectations"' % (down, n), got_dn == down, got_dn)
        check('    mean move %+.2f%%' % mean, abs(got_mean - mean) < 0.005,
              '%+.4f' % got_mean)

    print('')
    print('=== the three n sum to the calibration population ===')
    check('28 + 20 + 9 = 57', sum(len(v) for v in bands.values()) == 57,
          sum(len(v) for v in bands.values()))

    print('')
    print('=== not one Bearish print has EVER closed up ===')
    check('0 of 9, and it survives dropping the no-card record',
          all(v <= 0 for v in bands['Bearish'])
          and len([v for v in bands['Bearish'] if v < 0]) == 9)

    print('')
    print('=== the flat record is why "70%% down" and "25%% up" both hold ===')
    flat = [v for v in bands['Neutral'] if v == 0]
    check('exactly one Neutral record closed unchanged', len(flat) == 1,
          len(flat))

    print('')
    print('=== 19 records have NO outcome and are NOT counted ===')
    missing = [r['id'] for r in m.records
               if not isinstance((r.get('stockReaction') or {}), dict)
               or not isinstance((r.get('stockReaction') or {})
                                 .get('pctChangeNextDay'), (int, float))]
    # ★ A FLOOR. Every pre-earnings build adds records with no outcome yet:
    # 19 when written, 23 after the 2026-08-26 build.
    check('at least 19 records sit outside the calibration',
          len(missing) >= 19, len(missing))
    print('     %s' % ', '.join(sorted(missing)[:6]) + ' ...')
    print('     Backfilling these would CHANGE the published rates, not')
    print('     confirm them. That is a calibration decision, not a repair.')

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
