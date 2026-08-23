"""An ACTIVE event flag with no category read — the live-bug guard.

The reads pass takes a different branch when a record carries
`asymmetricEventFlag`, and that branch skips the pass. The evidence:

  · 15 records in the library lack category reads. EVERY ONE carries the flag.
  · 18 unflagged records were built in the same window. NOT ONE lacks reads.
  · The branch worked on ZS-2026Q3 at 15:00 on 2026-05-27 and failed on
    MRVL-2027Q1 at 19:00 the same day.
  · 25 records have been built since the last flagged one (TSLA-2026Q2,
    2026-07-27) and none of them fires the flag.

So the branch has not been exercised since it broke. There is no evidence of a
fix, only an absence of tests, which makes this a LIVE bug: the next flagged
print skips its reads. And a flag means STAY FOR THE CALL, so the narrative read
IS the deliverable — the failure lands on the prints where it costs most.

Two independent guards cover it, one here and one in render_scorecard.py. They
must agree, and both must stay silent on the seven flagged records that carry
their reads.

★ 12 DEFECTS + 2 PENDING, not 14 defects. 'SCORED-PR-ONLY' starts with
'SCORED', so classifying by prefix calls a PR-only card a completed record and
reports a build regression against a read nobody was supposed to have written
yet. GTLB-2027Q1 and NFLX-2026Q2 are PR-only: their missing reads are
legitimate pending-call state. PR-ONLY must be tested FIRST, because it is a
SUFFIX on a string whose PREFIX means the opposite -- the same species as
'MAJOR MISS' containing no 'STREET'.

Accounting of the 15 unread records:
  12  DEFECT   — a completed record whose reads were supposed to exist
   2  PENDING  — GTLB-2027Q1, NFLX-2026Q2, awaiting the call
   1  SILENT   — CRM-2027Q1, flag withdrawn on calibration review

And of the 12 defects, by how they failed:
  10  no scoreLabels — the pass never ran (the flag branch)
   2  scoreLabels present — the pass ran and could not NAME the rows, because
      AEHR-2026Q4 and TSLA-2026Q2 store the metric under 'metric'. The alias
      fix covers those two.
NFLX-2026Q2 is a metric/cons variant AND lacks scoreLabels, so it was blocked
upstream before the naming defect could reach it -- which is why it counts as
pending rather than as a third naming failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import audit                        # noqa: E402
from earnings_scraper import scorecard as SC              # noqa: E402
from earnings_scraper.model import Model                  # noqa: E402

FAIL = [0]

# flagged, and known to carry their reads
KNOWN_GOOD = ('ZS-2026Q3', 'IBM-2026Q2', 'AVGO-2026Q2', 'AMD-2026Q1',
              'ANET-2026Q1', 'AMAT-2026Q2', 'NVDA-2027Q1')

# the 12 DEFECTS: a completed record whose reads were supposed to exist
EXPECTED = {
    'MRVL-2027Q1', 'SNOW-2027Q1', 'MDB-2027Q1', 'DELL-2027Q1', 'CRDO-2026Q4',
    'PANW-2026Q3', 'CRWD-2027Q1', 'ORCL-2026Q4', 'CBRS-2026Q1',
    'MU-2026Q3', 'AEHR-2026Q4', 'TSLA-2026Q2',
}
# PR-only: flagged, unread, and CORRECTLY so until the call happens
PENDING = {'GTLB-2027Q1', 'NFLX-2026Q2'}


def check(label, ok, detail=''):
    print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:38]))
    if not ok:
        FAIL[0] += 1


def main():
    model = Model()

    print('=== the guard fires on exactly the affected records ===')
    fires = {r['id'] for r in model.records
             if SC.flagged_without_read(r)}
    defects = {r for r in fires
               if SC.read_state_kind(model.record_by_id(r)) == 'stored'}
    pending = fires - defects
    check('12 defects', len(defects) == 12, len(defects))
    check('on exactly the expected set', defects == EXPECTED,
          sorted(defects ^ EXPECTED) or 'exact')
    check('2 pending, and they are the PR-only pair', pending == PENDING,
          sorted(pending ^ PENDING) or 'exact')

    print('')
    print('=== silent where the reads exist ===')
    for rid in KNOWN_GOOD:
        rec = model.record_by_id(rid)
        if rec is None:
            continue
        check('%-14s silent' % rid,
              SC.flagged_without_read(rec, 'stored') is None,
              SC.flagged_without_read(rec, 'stored'))

    print('')
    print('=== a WITHDRAWN flag does not demand a read ===')
    crm = model.record_by_id('CRM-2027Q1')
    check('CRM-2027Q1 has a withdrawn flag',
          bool((crm.get('asymmetricEventFlag') or {}).get('withdrawn')))
    check('active_event_flag returns None for it',
          SC.active_event_flag(crm) is None)
    check('so the guard is silent', SC.flagged_without_read(crm) is None)
    check('it is the ONE record separating 15 from 14',
          crm['id'] not in EXPECTED and not any(
              str((crm.get('summaries') or {}).get(c) or '').strip()
              for c in SC._READ_CATS))

    print('')
    print('=== an unfired flag is not an active one either ===')
    check('fired=False -> None',
          SC.active_event_flag(dict(asymmetricEventFlag=dict(fired=False)))
          is None)
    check('fired=True  -> the flag',
          SC.active_event_flag(
              dict(asymmetricEventFlag=dict(fired=True, direction='BULL')))
          is not None)
    check('a flag with no `fired` key counts as active',
          SC.active_event_flag(
              dict(asymmetricEventFlag=dict(direction='BULL'))) is not None)
    check('a non-dict flag is ignored',
          SC.active_event_flag(dict(asymmetricEventFlag='BULL')) is None)

    print('')
    print('=== every firing record actually carries the flag ===')
    check('all 14 carry an active flag',
          all(SC.active_event_flag(model.record_by_id(r)) for r in fires))
    unflagged_unread = [
        r['id'] for r in model.records
        if not r.get('asymmetricEventFlag')
        and isinstance((r.get('scores') or {}).get('currentQuarter'),
                       (int, float))
        and not any(str((r.get('summaries') or {}).get(c) or '').strip()
                    for c in SC._READ_CATS)]
    check('NO unflagged record lacks its reads — the branch is the cause',
          unflagged_unread == [], unflagged_unread)

    print('')
    print('=== the wording distinguishes stored from live ===')
    rec = model.record_by_id('MU-2026Q3')
    stored = SC.flagged_without_read(rec, 'stored')
    check('stored reads as a defect', 'NO CATEGORY READ' in stored,
          stored[:34])
    check('and points at the branch, not the record',
          'flag branch' in stored)
    live = SC.flagged_without_read(
        dict(asymmetricEventFlag=dict(fired=True), scores={}, summaries={}),
        'live')
    check('live reads as a reminder, not a defect',
          live and 'READ PENDING THE CALL' in live, (live or '')[:34])
    check('and says the read is the deliverable',
          'deliverable' in (live or ''))
    check('STAY FOR THE CALL is stated on the live card',
          'STAY FOR THE CALL' in (live or ''))

    print('')
    print('=== it travels with the card ===')
    lines = SC.diagnostics({}, rec)
    check('diagnostics carries it',
          any('FLAGGED PRINT' in l for l in lines), len(lines))
    clean = SC.diagnostics({}, model.record_by_id('ZS-2026Q3'))
    check('and not for a record with reads',
          not any('FLAGGED PRINT' in l for l in clean))

    print('')
    print('=== the audit counts it apart from unread-categories ===')
    findings, _skipped = audit.audit_library(model)
    fw = [i for i, x in findings if x.rule == 'flagged-without-read']
    uc = [i for i, x in findings if x.rule == 'unread-categories']
    # ★ 12, not 14. GTLB-2027Q1 and NFLX-2026Q2 are SCORED-PR-ONLY, so their
    # missing reads are legitimate pending-call state. They are counted under
    # flagged-read-pending instead -- a defect count that includes them would
    # be reporting a build regression against a read nobody had written yet.
    fp = [i for i, x in findings if x.rule == 'flagged-read-pending']
    check('flagged-without-read n=12 (defects)', len(fw) == 12, len(fw))
    check('flagged-read-pending n=2 (PR-only)', len(fp) == 2, len(fp))
    check('and the two are disjoint', not (set(fw) & set(fp)),
          sorted(set(fw) & set(fp)))
    check('unread-categories is the broader set', len(uc) >= len(fw),
          '%d vs %d' % (len(uc), len(fw)))
    check('it is a FINDING, not SOFT',
          all(x.severity == 'FINDING' for _i, x in findings
              if x.rule == 'flagged-without-read'))
    check('and never HARD — nothing is corrupt, a read was never written',
          not any(x.severity == 'HARD' for _i, x in findings))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
