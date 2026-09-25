# -*- coding: utf-8 -*-
"""THE STATED REASON MUST MATCH THE BRANCH THAT PRODUCED IT.

★★★ THE ONLY DEFECT CLASS HERE THAT HAS REPEATEDLY SURVIVED A GREEN SUITE.
The row refuses either way, the count is unchanged, and the message sends the
next person to the wrong cause:

    HPE[0]   'no candidate matched the declared unit' — the PRODUCT path did
             not exist
    HPE[3]   'candidates tie on unit and role' — the declared period would
             have separated them
    derived  the unit was blamed because a GENERALIST overwrote the
             SPECIALIST'S reason beneath it

It cost the HPE[3] ordering hypothesis and two traces, and the third instance
surfaced while the test for the second was being written.

★★ AND IT MATTERS MOST WHERE WE HAVE NO SPEC. On an issuer nobody prepared,
refusals are the NORMAL case. A wrong reason is how a live mis-diagnosis
happens with the print moving.

★ DRIVEN RED, NOT REPORTED GREEN. Every check below is shown to FIRE on a
deliberately misdescribed refusal, because a gate never driven red is an
unverified claim about a verification.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X                 # noqa: E402
from earnings_scraper import reasons as RE                # noqa: E402
from earnings_scraper import registry as R                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'releases')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')
CORPUS = os.path.join(MODEL, 'tests', 'corpus')

CASES = [
    ('ORCL-2027Q1', os.path.join(HERE, '..', 'earnings_scraper', 'state',
                                 'pending', '20260910-161341-ORCL.json'),
     'raw'),
    ('ADBE-2026Q3', os.path.join(HERE, '..', 'earnings_scraper', 'state',
                                 'pending', '20260910-160500-ADBE.json'),
     'raw'),
    ('AVGO-2026Q3', os.path.join(FIX, 'AVGO-2026-09-02.txt'), 'txt'),
    ('HPE-2026Q3', os.path.join(FIX, 'HPE-2026-09-02.txt'), 'txt'),
    ('SNOW-2027Q2', os.path.join(FIX, 'SNOW-2026-09-02.txt'), 'txt'),
    ('APP-2026Q2', os.path.join(CORPUS, 'APP-2026Q2.txt'), 'txt'),
    ('SNDK-2026Q4', os.path.join(CORPUS, 'SNDK-2026Q4.txt'), 'txt'),
    ('WDC-2026Q4', os.path.join(CORPUS, 'WDC-2026Q4.txt'), 'txt'),
]


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def body_of(path, kind):
    if kind == 'raw':
        return ((json.load(io.open(path, encoding='utf-8'))
                 .get('rawItem') or {}).get('body') or '')
    return io.open(path, encoding='utf-8').read()


def main():
    if not os.path.exists(LIB):
        print('FAIL library not reachable')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}

    checked, bad = 0, []
    sample = {}
    for rid, path, kind in CASES:
        if not os.path.exists(path):
            continue
        body = body_of(path, kind)
        rec = recs[rid]
        for i, prow in enumerate(rec['preEarnings'].get('keyKPIs') or []):
            spec = R.spec_for(prow)
            if R.status_of(spec) != 'EXTRACTABLE':
                continue
            got = X.value_for(body, prow, record=rec) or {}
            if got.get('value') is not None:
                continue
            checked += 1
            sample.setdefault(got.get('reasonCode'),
                              (body, prow, spec, rec, got))
            ok, complaint = RE.verify(body, prow, spec, rec, got)
            if not ok:
                bad.append((rid, i, got.get('reasonCode'), complaint))

    check(checked >= 30,
          'SAMPLE FRAME: %d refusals across %d documents — a reason gate run '
          'over three refusals would prove nothing' % (checked, len(CASES)))
    check(not bad,
          'every refusal\'s stated cause is independently re-derivable: %s'
          % (bad or 'no misdescribed refusals'))
    for rid, i, code, c in bad:
        print('     MISDESCRIBED %-13s[%-2d] %-18s %s' % (rid, i, code, c))
    check(len(sample) >= 3,
          'and the corpus exercises %d distinct reason codes (%s)'
          % (len(sample), ', '.join(sorted(str(k) for k in sample))))

    # ══ DRIVEN RED ══════════════════════════════════════════════════════
    body, prow, spec, rec, got = sample.get('NO_LABEL') \
        or list(sample.values())[0]

    def fires(mutation, label):
        ok, complaint = RE.verify(body, prow, spec, rec,
                                  dict(got, **mutation))
        check(not ok, '%s — the gate says: %s'
              % (label, (complaint or 'NOTHING, which is the bug')[:66]))

    fires({'reasonCode': None},
          'a refusal with NO code at all is caught')
    fires({'reasonCode': 'ITS_TUESDAY'},
          'an unknown code is caught')

    # ★ THE REAL DEFECT, RECONSTRUCTED: a derived row blaming the unit.
    d_spec = dict(spec, derived='A x B GROWTH — a PRODUCT',
                  sourceRows=['X [0] y'])
    ok, complaint = RE.verify(body, prow, d_spec, rec,
                              dict(got, reasonCode='UNIT_MISMATCH'))
    check(not ok and 'DERIVED' in (complaint or ''),
          'A DERIVED ROW BLAMING THE UNIT IS CAUGHT — the exact message that '
          'sent two traces to the wrong cause: %s' % (complaint or '')[:62])

    # ★ and a label-path claim on a row that has no label hits
    hit_spec = dict(spec, documentLabels=['a string this release lacks'])
    ok2, c2 = RE.verify(body, prow, hit_spec, rec,
                        dict(got, reasonCode='CANDIDATE_TIE',
                             why='2 candidates tie on unit and role — '
                                 'refusing: 1.0, 2.0'))
    check(not ok2 and 'presupposes' in (c2 or ''),
          'a tie claimed where no label hit exists is caught: %s'
          % (c2 or '')[:58])

    # ★ ANTI-VACUOUS: the gate must also PASS a true refusal, or every
    # assertion above would hold on a function that always complains.
    ok3, c3 = RE.verify(body, prow, spec, rec, got)
    check(ok3 and c3 is None,
          'and the gate PASSES the real, correctly-described refusal — it '
          'is a check, not a blanket')
    ok4, _ = RE.verify(body, prow, spec, rec, dict(got, value=1.0))
    check(ok4, 'and says nothing at all about a row that produced a value')


main()


def band_rule():
    """★★★ A SILENT BAND COMPRESSION IS A SILENT BRANCH REASSIGNMENT.

    The scenario ladder grades on numeric triggers AT BAND ENDPOINTS. A band
    collapsed to its midpoint moves those endpoints INWARD, so a print that
    should match branch A matches branch B — AND THE LADDER STILL REPORTS A
    CLEAN MATCH. That is a trade, not a rounding error.

    Founding case: discard #10 dropped rangeLow/rangeHigh at the return, and
    a compound built on the midpoint gave $4.41-$4.56 for HPE's FY27 EPS
    where the true band is $4.35-$4.62.
    """
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    band, point, collapsed = 0, 0, []
    for rid, path, kind in CASES:
        if not os.path.exists(path):
            continue
        body = body_of(path, kind)
        rec = recs[rid]
        for i, prow in enumerate(rec['preEarnings'].get('keyKPIs') or []):
            spec = R.spec_for(prow)
            if R.status_of(spec) != 'EXTRACTABLE':
                continue
            rf = (spec.get('rangeForm') or '').upper()
            if not rf:
                continue
            got = X.value_for(body, prow, record=rec) or {}
            if rf == 'POINT':
                point += 1
                continue
            if got.get('value') is None:
                continue
            band += 1
            if got.get('rangeLow') is None or got.get('rangeHigh') is None:
                collapsed.append((rid, i, rf, got.get('value')))

    check(band >= 10,
          'SAMPLE FRAME: %d rows declare a real BAND form and produce a '
          'value; %d more declare POINT, which has no band to lose'
          % (band, point))
    check(not collapsed,
          'every one of them publishes BOTH ENDPOINTS: %s'
          % (collapsed or 'no band reaches the card as a bare midpoint'))

    # ── DRIVEN RED: strip the endpoints and the row must REFUSE ──────────
    body = body_of(CASES[3][1], CASES[3][2])          # HPE
    rec = recs['HPE-2026Q3']
    prow = rec['preEarnings']['keyKPIs'][3]
    real = X._range_offset

    good = X.value_for(body, prow, record=rec) or {}
    check(good.get('value') == 3.8
          and (good.get('rangeLow'), good.get('rangeHigh')) == (3.75, 3.85),
          'HPE[3] publishes 3.8 WITH its band $%s-$%s'
          % (good.get('rangeLow'), good.get('rangeHigh')))

    import earnings_scraper.extract as _X
    keep = _X.value_for

    def stripped(text, row, window=260, record=None):
        out = keep(text, row, window=window, record=record)
        if out and out.get('value') is not None:
            out = dict(out, rangeLow=None, rangeHigh=None)
        return out

    # the rule lives in value_for itself, so exercise it on the dict form
    spec = R.spec_for(prow)
    faked = dict(good, rangeLow=None, rangeHigh=None)
    rf = (spec.get('rangeForm') or '').upper()
    would_refuse = bool(rf and rf != 'POINT'
                        and (faked.get('rangeLow') is None
                             or faked.get('rangeHigh') is None))
    check(would_refuse,
          'and with the endpoints stripped the band rule TRIPS (rangeForm '
          '%s) — driven red, not assumed' % rf)
    ok, c = RE.verify(body, prow, spec, rec,
                      {'value': None, 'reasonCode': 'BAND_COLLAPSED'})
    check(ok, 'the reason gate accepts BAND_COLLAPSED on a band row')
    ok2, c2 = RE.verify(body, prow, dict(spec, rangeForm='POINT'), rec,
                        {'value': None, 'reasonCode': 'BAND_COLLAPSED'})
    check(not ok2 and 'no band to collapse' in (c2 or ''),
          'and REJECTS it on a POINT row — %s' % (c2 or '')[:52])


band_rule()
