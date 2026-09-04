"""Two write-time invariants and the extractor that makes them worth having.

1. A value never lands in a scale-declaring row without a unit
   -------------------------------------------------------------
   "Q1 Revenue ($B)" holding 10253.0 renders 10.253 ($B) when actualUnit='$M'
   is declared and a bare 10,253 when it is not -- and BOTH clear a bogey of
   10.25, the second by ACCIDENT. HARD 11 catches this when validate_library.py
   runs, which is hours after the trade. So it is enforced at write time, and
   detection is deliberately broader than the resolver's closed unit list:
   "($bn)", "(US$M)" and "($ in millions)" all declare a scale that
   unit_from_kpi_name cannot resolve.

2. A qualified row is filled only from a figure parsed FOR that qualifier
   ---------------------------------------------------------------------
   AMD's priority-1 hero is "Q1 Data Center Revenue ($B)" and the release
   states it. Before the segment extractor there was no way to read it in prose
   OR table, so the row could only ever be filled by accident -- which is
   exactly what the headline-total matcher was doing. Refusing beat a false
   MISS; reading the number beats both.

3. A verdict inside the rounding of its own source figure is not a reading
   ----------------------------------------------------------------------
   "$5.8 billion" resolves the figure to +/-0.05, which is 0.86%. Against a
   bogey of 5.7 the clearance is 1.75% and resolves. Against a bogey of 5.8 it
   is 0.00% and does not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse as P                    # noqa: E402
from earnings_scraper import score as S                    # noqa: E402
from earnings_scraper import units as U                    # noqa: E402
from earnings_scraper.model import Model                   # noqa: E402
from earnings_scraper.tables import find_segment           # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:40]))
    if not ok:
        FAIL[0] += 1


def card(model, rid, body):
    entry = model.prepare_from_record(model.record_by_id(rid))
    return S.score_release(P.parse_release(
        dict(msg_type='news_item', source='BUS', id=rid,
             headline='%s reports' % rid, # ★ Every real release states its period in a heading, and
             # step 2 refuses a value whose period cannot be
             # established. Prepended HERE so every call site
             # inherits it.
             body='Third Quarter Fiscal 2026 Financial Results\n' + body)), entry, model)


def main():
    model = Model()

    print('=== a declared scale is detected even when it cannot be resolved ===')
    for name, narrow, broad in [
            ('Q1 Revenue ($B)', True, True),
            ('Q1 Revenue ($M)', True, True),
            ('Q1 Revenue ($bn)', False, True),
            ('Q1 Revenue (US$M)', False, True),
            ('Q1 Revenue ($ in millions)', False, True),
            ('FQ4 Gross Margin (%)', False, False),
            ('FQ4 Non-GAAP EPS ($)', False, False),
            ('Q1 Adj GM (bps)', False, False),
            ('MI Accelerator FY Revenue', False, False)]:
        check('%-28s narrow=%-5s broad=%s' % (name, narrow, broad),
              U.is_dollar_magnitude(name) is narrow
              and U.looks_like_dollar_magnitude(name) is broad,
              '%s / %s' % (U.is_dollar_magnitude(name),
                           U.looks_like_dollar_magnitude(name)))

    print('')
    print('=== the unitless value is refused, not written ===')
    rows = [dict(name='Q1 Revenue ($bn)', actual=10253.0, actualUnit=None),
            dict(name='Q1 Revenue ($B)', actual=10253.0, actualUnit='$M'),
            dict(name='FQ4 Gross Margin (%)', actual=84.6, actualUnit=None),
            dict(name='Q1 EPS ($)', actual=1.22, actualUnit=None),
            dict(name='Q1 Revenue (US$M)', actual=None, actualUnit=None)]
    bad = S.unit_undeclared(rows)
    check('the unresolvable scale token is caught', 0 in bad, bad.get(0))
    check('and the token itself is named', bad.get(0) == '$bn', bad.get(0))
    check('a declared unit passes', 1 not in bad)
    check('a percentage needs no scale', 2 not in bad)
    check('per-share dollars need no scale', 3 not in bad)
    check('no value, no claim', 4 not in bad)

    print('')
    print('=== the invariant is loud when nothing explains it ===')
    try:
        S.assert_units_declared(
            [dict(name='Q1 Revenue ($B)', actual=10253.0, actualUnit=None)])
        check('assert_units_declared raises', False, 'no exception')
    except S.UnitDeclarationError as exc:
        check('assert_units_declared raises', True)
        check('the message names the row and the value',
              'Q1 Revenue' in str(exc) and '10253' in str(exc), str(exc)[:40])
    check('a clean row set passes silently',
          S.assert_units_declared(
              [dict(name='Q1 Revenue ($B)', actual=1.0, actualUnit='$M')])
          is None)

    print('')
    print('=== every live row that holds a magnitude declares its unit ===')
    # ★ A period scope HEADER: step 2 refuses a value whose period
    # cannot be established, and every real release states its period.
    body = ('Third Quarter Fiscal 2026 Financial Results\n'
            'Total revenue of $10.253 billion, up 32% year over year.\n'
            'Data Center segment revenue was $5.8 billion.\n'
            'Client segment revenue was $2,885 million.\n'
            'Non-GAAP gross margin of 55.0%.\n')
    c = card(model, 'AMD-2026Q1', body)
    mags = [r for r in c['keyKPIs']
            if isinstance(r.get('actual'), (int, float))
            and U.looks_like_dollar_magnitude(r['name'])]
    check('AMD has magnitude rows filled', len(mags) >= 3, '%d' % len(mags))
    check('every one declares actualUnit',
          all(r.get('actualUnit') for r in mags),
          [(r['name'][:18], r.get('actualUnit')) for r in mags])

    print('')
    print('=== the segment extractor: prose ===')
    text = ('Total revenue of $10.253 billion, up 32% year over year.\n'
            'Data Center segment revenue was $5.8 billion, up 14% from '
            '$5.1 billion a year ago.\n'
            'Client segment revenue was $2,885 million.\n'
            'We expect Data Center segment revenue of $6.5 billion in the '
            'second quarter.\n')
    dc = P.segment_revenue(text, ['data', 'center'])
    check('Data Center reads 5,800 ($M)', dc['value_musd'] == 5800.0,
          dc['value_musd'])
    check('the prior-year comparative is not taken',
          dc['value_musd'] != 5100.0, dc['value_musd'])
    check('the GUIDE sentence is not taken as an actual',
          dc['value_musd'] != 6500.0, dc['raw'][:40])
    check('the stated precision is recorded', dc['decimals'] == 1,
          dc['decimals'])
    check('Client reads 2,885 ($M)',
          P.segment_revenue(text, ['client'])['value_musd'] == 2885.0)
    check('a segment the release omits stays None',
          P.segment_revenue(text, ['embedded']) is None)
    check('no tokens means no match',
          P.segment_revenue(text, []) is None)
    check('a partial token set does not match',
          P.segment_revenue('Center revenue was $9.9 billion.',
                            ['data', 'center']) is None)

    amb = P.segment_revenue(
        'Client segment revenue was $2,885 million. Client segment revenue '
        'was $2,900 million.', ['client'])
    check('two different values refuse rather than choose',
          amb.get('value_musd') is None and amb.get('ambiguous'),
          amb.get('ambiguous'))

    print('')
    print('=== the segment extractor: table, preferred for precision ===')
    # ★ THE HEADER IS PART OF THE FIXTURE NOW. A real vertical segment table
    # states its windows, and without one 5,775 and 4,573 are the same metric
    # in the same unit with nothing to say which is the quarter. The headerless
    # case is asserted separately below, so this is the fixture becoming
    # realistic rather than the rule becoming weaker.
    #
    # ⚠ HONEST LIMIT: AMD's REAL release is NOT in the corpus -- source text is
    # held for AVGO, HPE, SNOW, APP, SNDK and WDC only. So this header is
    # MODELLED on the four vertical layouts that were measured (SNOW, APP,
    # SNDK, HPE all state 'Ended' phrases) and has NOT been checked against an
    # AMD document. Until one is pulled, the assertion below -- that a
    # headerless two-column row refuses -- is the only one here describing an
    # observed shape rather than a plausible one.
    tbl = ('(In millions, except percentages)\n'
           'Three Months Ended March 29,\n2026\n2025\n'
           'Data Center segment revenue\n$\n5,775\n4,573\n'
           'Client segment revenue\n2,885\n')
    t = find_segment(tbl, ['data', 'center'])
    check('the table states 5,775 where prose rounds to 5,800',
          t['value'] == 5775.0, t['value'])
    check('the declared scale is recorded', t['scale'] == 'millions', t['scale'])
    check('an undeclared scale is refused, not inferred',
          find_segment('Data Center segment revenue\n5,775\n',
                       ['data', 'center']) is None)

    # ★★ AND THE COLUMN IS REFUSED WHEN NOTHING IDENTIFIES IT. Two cells, no
    # period header, no stated delta: 5,775 and 4,573 are the same metric in
    # the same unit, and prior-year-YTD / current-Q = 2/(1+g) is 1.00 at 100%
    # growth. A hero blank with a stated reason is a decision; a hero filled
    # from an unidentified column is a trade.
    headerless = find_segment('(In millions)\n'
                              'Data Center segment revenue\n$\n5,775\n'
                              '4,573\n', ['data', 'center'])
    check('a headerless two-column segment row REFUSES',
          headerless is not None and headerless.get('value') is None,
          headerless)
    check('  and it says the column is unverified',
          'unverified' in ((headerless or {}).get('source') or ''),
          (headerless or {}).get('source'))
    check('the table wins over prose on the same release',
          card(model, 'AMD-2026Q1',
               'Data Center segment revenue was $5.8 billion.\n' + tbl
               )['keyKPIs'][1]['actual'] == 5775.0)

    print('')
    print('=== a verdict inside the rounding is refused ===')
    hs = S.rounding_halfstep_pct(5.8, 1)
    check('$5.8 billion resolves to +/-0.86%', abs(hs - 0.862) < 0.01, hs)
    check('$5.75 billion resolves ten times finer',
          abs(S.rounding_halfstep_pct(5.75, 2) - 0.087) < 0.01,
          S.rounding_halfstep_pct(5.75, 2))
    check('a 1.75% clearance survives 0.86% rounding',
          not S.rounding_ambiguous(1.75, hs))
    check('a 0.00% clearance does not',
          S.rounding_ambiguous(0.0, hs))
    check('an unstated precision makes no claim',
          S.rounding_halfstep_pct(None, None) is None)

    on_bogey = card(model, 'AMD-2026Q1',
                    'Data Center segment revenue was $5.7 billion.\n')
    row = on_bogey['keyKPIs'][1]
    check('a figure landing ON the bogey grades no verdict',
          row['pctVsBogey'] is None and row['vsBogey'] == '—',
          '%s / %s' % (row['pctVsBogey'], row['vsBogey']))
    check('and the note says the release does not resolve it',
          'INSIDE the rounding' in row['vsConsNote'],
          row['vsConsNote'][-60:])
    clear = card(model, 'AMD-2026Q1',
                 'Data Center segment revenue was $5.8 billion.\n')
    check('a figure clearing it by more than the rounding still grades',
          clear['keyKPIs'][1]['pctVsBogey'] == 1.75,
          clear['keyKPIs'][1]['pctVsBogey'])

    print('')
    print('=== abbreviated margin names are reachable ===')
    for name, gm, opm in [('FQ4 Gross Margin (%)', True, False),
                          ('Q1 Adj GM (%)', True, False),
                          ('F4Q Adj GM Guide (%)', True, False),
                          ('Auto GM ex-credits (%)', True, False),
                          ('Q1 Non-GAAP Operating Margin (%)', False, True),
                          ('Q1 OPM (%)', False, True),
                          ('Q1 Revenue ($B)', False, False)]:
        check('%-34s gm=%-5s opm=%s' % (name, gm, opm),
              S.is_gross_margin_row(name) is gm
              and S.is_operating_margin_row(name) is opm)

    print('')
    print('=== a qualified margin row is a DIFFERENT metric ===')
    c2 = card(model, 'TSLA-2026Q1',
              'Total revenue of $22.5 billion.\nGAAP gross margin of 17.9%.\n')
    auto = [r for r in c2['keyKPIs'] if 'Auto GM' in r['name']][0]
    check('Auto GM ex-credits refuses the company gross margin',
          auto['actual'] is None, auto['actual'])
    check('and says why',
          'different metric' in auto['vsConsNote'], auto['vsConsNote'][:40])
    c3 = card(model, 'TSLA-2026Q1',
              'Total revenue of $22.5 billion.\nGAAP gross margin of 17.9%.\n'
              'Automotive gross margin excluding regulatory credits was 16.4%.\n')
    auto3 = [r for r in c3['keyKPIs'] if 'Auto GM' in r['name']][0]
    check('it reads the qualified figure when stated',
          auto3['actual'] == 16.4, auto3['actual'])
    check('and records that it came from the segment line',
          'segment margin' in (auto3['extractionSource'] or ''),
          auto3['extractionSource'])

    c4 = card(model, 'AMD-2026Q1', 'Non-GAAP gross margin of 55.0%.\n')
    gmrow = [r for r in c4['keyKPIs'] if r['name'] == 'Q1 Adj GM (%) ★']
    gmrow = gmrow or [r for r in c4['keyKPIs'] if 'Adj GM (%)' in r['name']]
    check('an UNqualified abbreviation takes the company figure',
          gmrow[0]['actual'] == 55.0, gmrow[0]['actual'])

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
