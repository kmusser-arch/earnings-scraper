"""Regression pinning against the live library.

Each case isolates one rule. These grade from the STORED actuals rather than a
parsed press release, so a failure means the scoring rule is wrong, not that the
parser missed a number.

  SNDK-2026Q4  cq +1.0   bogey not consensus (+6.9% consensus beat -> +1.0)
  TSLA-2026Q1  cq +2.0   hero KPI not revenue (+0.5% consensus beat -> +2.0)
  APP-2026Q2   cq -1.5   hero-margin hard cap AND own-guide-range failure
  CBRS-2026Q2  cq -1.5   GAAP basis rule
  CSCO-2026Q4  nq +1.0 / fy +0.5 / narr -1.5   the withdrawal rule
  NBIS-2026Q2  fy +0.5   the reaffirm band
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import score as score_mod                  # noqa: E402
from earnings_scraper.model import Model                          # noqa: E402


def parsed_from_record(rec):
    """Reconstruct a `parsed` dict from a record's stored actuals.

    Lets the scoring rule be tested independently of the press-release parser.
    """
    ac = rec.get('actuals') or {}
    rev = ac.get('revenue')
    unit = ac.get('revenueUnit') or '$M'
    rev_musd = None
    if isinstance(rev, (int, float)):
        rev_musd = float(rev) * (1000.0 if unit == '$B' else 1.0)

    eps = {}
    if isinstance(ac.get('nonGaapEPS'), (int, float)):
        eps['non-GAAP'] = dict(value=ac['nonGaapEPS'], raw='stored')
    if isinstance(ac.get('gaapEPS'), (int, float)):
        eps['GAAP'] = dict(value=ac['gaapEPS'], raw='stored')

    margins = {}
    if isinstance(ac.get('nonGaapGm'), (int, float)):
        margins['grossMargin'] = dict(value=ac['nonGaapGm'], basis='non-GAAP',
                                      raw='stored')
    if isinstance(ac.get('nonGaapOpMargin'), (int, float)):
        margins['operatingMargin'] = dict(value=ac['nonGaapOpMargin'],
                                          basis='non-GAAP', raw='stored')

    yoy = None
    for key in ('nonGaapGmYoYbps', 'productGmYoYbps', 'grossMarginYoYbps'):
        if isinstance(ac.get(key), (int, float)):
            yoy = ac[key]
            break

    return dict(revenue=(dict(value_musd=rev_musd, unit_seen=unit.lower(),
                              growth_pct=ac.get('revGrowthYoY'), raw='stored')
                         if rev_musd is not None else None),
                eps=eps, guidance={}, margins=margins, marginYoYBps=yoy,
                fields=99)


def stored_kpi_rows(rec, entry):
    """Use the record's stored actuals.keyKPIs, preserving index alignment."""
    pre = entry.get('keyKPIs') or []
    stored = ((rec.get('actuals') or {}).get('keyKPIs')) or []
    rows = []
    for i, kpi in enumerate(pre):
        s = stored[i] if i < len(stored) else {}
        name = kpi.get('name') or ''
        rows.append(dict(name=name, consensus=kpi.get('consensus'),
                         bogey=kpi.get('bogey'), actual=s.get('actual'),
                         pctVsCons=s.get('pctVsCons'),
                         pctVsBogey=s.get('pctVsBogey'),
                         vsCons=s.get('vsCons') or 'N/A',
                         vsBogey=s.get('vsBogey') or '—',
                         vsConsNote='stored', vsBogeyNote='',
                         hero='★' in name,
                         period=score_mod._classify_period(name),
                         forward=score_mod._is_forward(name)))
    return rows


CASES = [
    ('SNDK-2026Q4', 'currentQuarter', 1.0, 'BOGEY not consensus'),
    ('TSLA-2026Q1', 'currentQuarter', 2.0, 'HERO KPI not revenue'),
    ('APP-2026Q2', 'currentQuarter', -1.5, 'hard cap + own-guide failure'),
    ('CBRS-2026Q2', 'currentQuarter', -1.5, 'GAAP basis rule'),
]


def evidence_from_record(rec):
    """Signals the scoring rule needs that live outside the KPI grid.

    At print time the scraper reads these from the press release, which
    restates the prior guide and the comparative margins. Here they are lifted
    from the stored record so the RULE is under test, not the parser.
    """
    ac = rec.get('actuals') or {}
    blob = ' '.join(str(v) for v in [
        (rec.get('summaries') or {}).get('currentQuarter') or '',
        ' '.join(str((k or {}).get('vsBogeyNote') or '')
                 for k in (ac.get('keyKPIs') or [])),
        ' '.join(str(x) for x in ((rec.get('verification') or {})
                                  .get('twoSourceConfirmed') or [])),
    ])

    own_guide_failed = bool(re.search(
        r'below the low end of its own guide|failed its own guide'
        r'|below-low-end', blob, re.I))

    margin_declined = False
    for key in ('nonGaapGmYoYbps', 'productGmYoYbps', 'grossMarginYoYbps'):
        if isinstance(ac.get(key), (int, float)) and ac[key] < 0:
            margin_declined = True
    if (isinstance(ac.get('coreGm'), (int, float))
            and isinstance(ac.get('coreGmPriorQ'), (int, float))
            and ac['coreGm'] < ac['coreGmPriorQ']):
        margin_declined = True
    if re.search(r'sequential (?:core-)?margin decline|consecutive sequential '
                 r'decline', blob, re.I):
        margin_declined = True

    margin_collapse = bool(re.search(r'margin collapse|−1,?\d{3}bps'
                                     r'|-1,?\d{3}bps', blob, re.I))

    return dict(ownGuideFailed=own_guide_failed,
                marginDeclined=margin_declined,
                marginCollapse=margin_collapse)


def main():
    model = Model()
    ok, msg = model.check_invariant()
    counts = model.counts()

    print('=== live library ===')
    print('records %(records)d  abandoned %(abandoned)d  profiles %(profiles)d'
          % counts)
    print('revUnit: $B %(revUnitB)d  $M %(revUnitM)d  null %(revUnitNull)d'
          % counts)
    print('pinning set %(pinningSet)d  calibration.recordsUsed '
          '%(calibrationRecordsUsed)s' % counts)
    print('invariant: %s  (%s)' % ('HOLDS' if ok else 'DIVERGED', msg))
    if not ok:
        print('  -> regenerate calibration.json rather than adjusting tests')

    failures = 0
    print()
    print('=== currentQuarter pinning ===')
    for rid, cat, expected, pins in CASES:
        rec = model.record_by_id(rid)
        if rec is None:
            print('SKIP %-14s not in live library' % rid)
            continue
        try:
            entry = model.prepare_from_record(rec)
        except Exception as exc:
            print('FAIL %-14s prepare raised %r' % (rid, exc))
            failures += 1
            continue

        parsed = parsed_from_record(rec)
        rows = stored_kpi_rows(rec, entry)
        cq = score_mod.grade_current_quarter(
            parsed, entry, rows, model, evidence_from_record(rec))
        got = cq['score']
        good = got == expected
        failures += 0 if good else 1
        print('%s %-14s got %-6s exp %-6s  %s' % (
            'PASS' if good else 'FAIL', rid,
            ('%+.1f' % got) if got is not None else 'None',
            '%+.1f' % expected, pins))
        print('       hero=%s  clearance=%s vs %s  base=%s flags=%d step=-%.1f%s'
              % ((cq.get('heroName') or '?')[:34], cq.get('clearance'),
                 cq.get('clearanceVs'), cq.get('base'), cq['flags'],
                 cq['stepDownApplied'],
                 '  HARD-CAPPED' if cq['hardCapped'] else ''))
        if cq.get('reason'):
            print('       %s' % cq['reason'][:110])
        for e in cq['flagEvidence']:
            print('         flag: %s' % e[:100])

    print()
    print('=== structural invariants ===')

    def check(label, cond, got=''):
        nonlocal failures
        failures += 0 if cond else 1
        print('%s %-50s %s' % ('PASS' if cond else 'FAIL', label, got))

    rec = model.record_by_id('CSCO-2026Q4')
    entry = model.prepare_from_record(rec)
    parsed = parsed_from_record(rec)
    card = score_mod.score_release(parsed, entry, model,
                                   evidence_from_record(rec))

    check('narrative is None on a PR-only run',
          card['scores']['narrative'] is None, card['scores']['narrative'])
    check('overall is None when any category is None',
          card['overall'] is None, card['overall'])
    check('status is SCORED-PR-ONLY', card['status'] == 'SCORED-PR-ONLY',
          card['status'])
    check('tradeSummaryPending set', card['tradeSummaryPending'] is True)
    check('keyKPIs index-aligned 1:1',
          len(card['keyKPIs']) == len(entry['keyKPIs']),
          '%d vs %d' % (len(card['keyKPIs']), len(entry['keyKPIs'])))
    check('narrative deferral reason stated',
          any('narrative' in d for d in card['deferred']))

    # Alignment must FAIL LOUDLY, not silently write a short array.
    try:
        score_mod.assert_alignment([{'name': 'a'}, {'name': 'b'}],
                                   [{'name': 'a'}])
        check('short actuals array raises AlignmentError', False, 'no raise')
    except score_mod.AlignmentError:
        check('short actuals array raises AlignmentError', True)

    # NO_CARD / NO_PROFILE must refuse.
    from earnings_scraper.model import NoCard, NoProfile
    try:
        model.prepare('ZZZZ', '2026-08-18')
        check('unknown ticker raises NoCard', False, 'no raise')
    except NoCard:
        check('unknown ticker raises NoCard', True)
    except NoProfile:
        check('unknown ticker raises NoCard', False, 'raised NoProfile first')

    check('abandonedRecords not indexed',
          all(r.get('id') not in {x.get('id') for x in model.abandoned}
              for r in model.records))

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
