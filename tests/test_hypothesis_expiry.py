"""Expiry tests: each one breaks when a stated CAUSE stops explaining the data.

★ These are not correctness tests. A failure here does not mean the code is
wrong — it means an EXPLANATION has expired and a finding in the library now
describes something that is no longer true. That is rarer than a bug and more
valuable, because a stale explanation is invisible: the code keeps working and
the reasoning behind it quietly stops applying.

Every finding that names a cause gets one. The rule of construction is that the
assertion must be phrased against the CAUSE, not the symptom — "no unflagged
record lacks its reads" expires the flag-branch diagnosis, whereas "14 records
lack reads" would merely be a count that drifts.

When one of these fails, the correct response is to re-derive the finding, not
to update the number.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import audit, flat                  # noqa: E402
from earnings_scraper import score as S                   # noqa: E402
from earnings_scraper import scorecard as SC              # noqa: E402
from earnings_scraper import units as U                   # noqa: E402
from earnings_scraper.model import Model                  # noqa: E402

FAIL = [0]
CATS = SC._READ_CATS


def expiry(claim, holds, detail=''):
    print('%s %-58s %s' % ('HOLDS' if holds else 'EXPIRED', claim,
                           str(detail)[:36]))
    if not holds:
        FAIL[0] += 1


def main():
    model = Model()
    recs = model.records

    print('=== CAUSE: the reads pass is skipped by the event-flag branch ===')
    #
    # ★ PRESENCE, NOT LIVENESS. Two different predicates, and conflating them
    # made this very test report a false expiry on CRM-2027Q1. The BUILD branch
    # keys on the flag EXISTING; `active_event_flag` additionally requires it not
    # to be withdrawn, which is a later calibration judgement that has nothing
    # to do with which code path ran months earlier. CRM took the flag branch and
    # then had its flag retracted, so it is flagged for the hypothesis and
    # inactive for the guard. The guard is right to skip it; this test is not.
    def took_flag_branch(r):
        return bool(r.get('asymmetricEventFlag'))

    unread = [r for r in recs
              if isinstance((r.get('scores') or {}).get('currentQuarter'),
                            (int, float))
              and not any(str((r.get('summaries') or {}).get(c) or '').strip()
                          for c in CATS)]
    unflagged_unread = [r['id'] for r in unread if not took_flag_branch(r)]
    expiry('no record WITHOUT the flag lacks its reads',
           unflagged_unread == [], unflagged_unread)
    expiry('every unread record carries the flag',
           all(took_flag_branch(r) for r in unread),
           [r['id'] for r in unread if not took_flag_branch(r)])

    # ★ Compare on the DATE, not on a truncated timestamp literal. createdAt
    # carries microseconds and a Z ('2026-07-27T16:14:04.775598Z'), so a string
    # '>' against '2026-07-27T16:14:04' is true for the very record that defines
    # the boundary.
    LAST_FLAGGED = '2026-07-27'
    after = [r['id'] for r in recs if took_flag_branch(r)
             and str(r.get('createdAt') or '')[:10] > LAST_FLAGGED]
    expiry('the branch is still untested since it broke', after == [], after)

    print('')
    print('=== CAUSE: only IBM escaped the branch, via preEarningsAbsent ===')
    escaped = [r['id'] for r in recs
               if took_flag_branch(r) and 'preEarnings' not in r
               and any(str((r.get('summaries') or {}).get(c) or '').strip()
                       for c in CATS)]
    expiry('IBM-2026Q2 is the only preEarningsAbsent escapee',
           escaped == ['IBM-2026Q2'], escaped)

    print('')
    print('=== CAUSE: metric/cons variants broke the naming, 3 records ===')
    variants = [r['id'] for r in recs
                for k in ((r.get('preEarnings') or {}).get('keyKPIs') or [])
                if isinstance(k, dict) and not k.get('name') and k.get('metric')]
    expiry('exactly three records use the metric/cons variant',
           len(set(variants)) == 3, sorted(set(variants)))
    expiry('and the alias resolves every one of their rows',
           all(all(k.get('name') for k in
                   model.prepare_from_record(model.record_by_id(v))['keyKPIs'])
               for v in set(variants)))

    print('')
    print('=== CAUSE: a $M value in a ($B) row false-CLEARs without a unit ===')
    exposed = [(r.get('id'), h[1]) for r in recs
               for h in SC.undeclared_magnitude_rows(r)]
    expiry('no library row can reach the unitless-magnitude path',
           exposed == [], exposed[:3])

    print('')
    print('=== CAUSE: call-only slots are findings, not gaps ===')
    call_only = sum(len(flat.call_only_rows(r, S._classify_period,
                                            S.row_qualifiers))
                    for r in recs if 'preEarnings' in r)
    expiry('call-only slots still exist to be protected', call_only > 0,
           call_only)
    backfilled = []
    for r in recs:
        if not flat.has_flag(r):
            continue
        _c, _fix, skipped = flat.repair_alignment(r, S._classify_period,
                                                  S.row_qualifiers)
        for i, _n, was in skipped:
            row = ((r.get('actuals') or {}).get('keyKPIs') or [])[i]
            if isinstance(row, dict) and row.get('unverified') \
                    and isinstance(row.get('actual'), (int, float)):
                backfilled.append((r['id'], i))
    expiry('no withheld row has been silently filled', backfilled == [],
           backfilled)

    print('')
    print('=== CAUSE: one label shift explains three drift sites ===')
    w = audit.bullish_drift_watch(model)
    expiry('the drift sites are still the three that were named',
           set(w) >= {'nextQToleranceBand', 'prOnlyCeiling', 'fadeZoneBand'},
           sorted(k for k in w if k != 'total'))
    expiry('the tolerance cohort has not reached the n>=10 re-measure trigger',
           len(w['nextQToleranceBand']) < 10, len(w['nextQToleranceBand']))
    expiry('the fade-zone band is still the largest of the three',
           len(w['fadeZoneBand']) >= len(w['nextQToleranceBand'])
           and len(w['fadeZoneBand']) >= len(w['prOnlyCeiling']),
           '%d / %d / %d' % (len(w['fadeZoneBand']),
                             len(w['nextQToleranceBand']),
                             len(w['prOnlyCeiling'])))

    print('')
    print('=== CAUSE: rotations are declared by hand, never inferred ===')
    declared = [(r['id'], i) for r in recs
                for i, a in enumerate(((r.get('actuals') or {})
                                       .get('keyKPIs') or []))
                if isinstance(a, dict) and a.get('rotationSuspect')]
    expiry('every rotationSuspect row is still BLANK',
           all(not isinstance((((model.record_by_id(rid) or {})
                                .get('actuals') or {}).get('keyKPIs')
                               or [])[i].get('actual'), (int, float))
               for rid, i in declared), declared)
    # ★ A rotation rule must never become a gate: the detector was 5/5 false
    # positives, because a good note quotes the number in its own row.
    rot = [r for r in audit.RULES if r.name.startswith('rotation')]
    expiry('the rotation rule is still report-only',
           all(r.path == audit.STORED for r in rot) and len(rot) == 1,
           [r.name for r in rot])

    print('')
    print('=== CAUSE: the gate base rates were measured under v1 bands ===')
    bull, bear = __import__('earnings_scraper.gate',
                            fromlist=['x']).label_thresholds()
    expiry('the imported thresholds are still v2', (bull, bear) == (1.0, 0.0),
           (bull, bear))
    import earnings_scraper.gate as G
    g = G.evaluate(0.0, 0.0, 0.0, G.framework_from(model))
    expiry('the gate still refuses to quote a v1 rate on a v2 band',
           (g.get('labelCalibration') or {}).get('cohortApplies') is False)

    print('')
    print('=== CAUSE: PR-ONLY is a suffix whose prefix means the opposite ===')
    expiry("read_state_kind tests PR-ONLY before the SCORED prefix",
           SC.read_state_kind(dict(status='SCORED-PR-ONLY')) == 'pending'
           and SC.read_state_kind(dict(status='SCORED-POST-CALL')) == 'stored')
    pending = [r['id'] for r in recs if SC.flagged_without_read(r)
               and SC.read_state_kind(r) != 'stored']
    defects = [r['id'] for r in recs if SC.flagged_without_read(r)
               and SC.read_state_kind(r) == 'stored']
    expiry('the split is still 12 defects and 2 pending',
           (len(defects), len(pending)) == (12, 2),
           '%d / %d' % (len(defects), len(pending)))

    print('')
    print('%d explanation(s) expired' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
