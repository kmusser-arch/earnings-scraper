"""Which figure the hero band is derived from, and how the card says so.

The founding case is CSCO-2026Q4. Its reason line read

    hero Product Gross Margin (%) clears consensus by +2.53%

and the +2.53% was REVENUE vs revConsensus -- the profile's hero name printed
over a number it had no part in. The hand read grades revenue over its own guide
top, EPS, and AI orders, with margin used as a FLAG; +1.0 is the revenue
fallback minus two flags, the documented no-bogey path (Non-GAAP Gross Margin
has cons=None and bogey=None). The score was right; the sentence explaining it
was not.

What makes it dangerous is the collision: revenue vs consensus is +2.53% and
66.3/64.66 is +2.54%. The two derivations agree to two decimals, so no reader
could tell from the output which one had happened. Hence two rules:

  1. A hero may only resolve onto a row measuring the SAME SUBJECT.
     Word overlap alone put a "Product Gross Margin" hero on a company
     gross-margin row at 67% overlap, and a "Hardware Revenue" hero on the
     total revenue row.
  2. The reason line names the SOURCE ROW and the DERIVATION PATH, always.

Scope is compared after stripping wording noise ("Search Rev" vs "Search
Revenue", "Azure CC" vs "Azure FXN") and metric FORM ("Revenue Growth YoY (%)"
vs "Revenue ($M)"). Form may differ because the row supplies both the actual and
the expectation, so that comparison is internally consistent. The SUBJECT may
not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from earnings_scraper import score as S                    # noqa: E402
from earnings_scraper.model import Model                   # noqa: E402
from test_regression import (evidence_from_record,         # noqa: E402
                             parsed_from_record, stored_kpi_rows)

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:38]))
    if not ok:
        FAIL[0] += 1


def main():
    model = Model()

    print('=== wording noise is not a difference in subject ===')
    same = [
        ('Search Revenue Growth YoY (%)', 'Search Rev Growth YoY (%)'),
        ('Azure Growth CC (%)', 'Azure FXN Growth (%)'),
        ('US Commercial Revenue Growth YoY (%)', 'US Commercial Revenue ($M)'),
        ('F1Q Royalty Rev ($M)', 'Q4 Royalty Revenue ($M)'),
        ('cRPO Growth CC (%)', 'Q1 cRPO Growth (cc) (%)'),
        ('Product Revenue Growth YoY (%)', 'Q1 Product Revenue ($M)'),
        ('AWS Revenue Growth YoY (%)', 'AWS Growth (ex-FX %)'),
        ('Gross Margin (%) - current and guided', 'FQ4 Gross Margin (%)'),
        ('Client Segment Revenue ($B)', 'Q1 Client Revenue ($M)'),
    ]
    for hero, row in same:
        check('%-34s == %s' % (hero[:34], row[:26]),
              S.hero_scope_matches(hero, row),
              '%s / %s' % (sorted(S.hero_scope(hero)),
                           sorted(S.hero_scope(row))))

    print('')
    print('=== a different SUBJECT is refused ===')
    diff = [
        ('Hardware Revenue ($M)', 'Q1 Revenue ($M)'),
        ('Product Gross Margin (%)', 'Q4 Non-GAAP Gross Margin (%)'),
        ('Data Center Revenue ($B)', 'Q1 Revenue ($B)'),
        ('Data Center Revenue ($B)', 'Q1 Client Revenue ($M)'),
        ('Auto GM ex-credits (%)', 'Q1 Gross Margin (%)'),
    ]
    for hero, row in diff:
        check('%-34s != %s' % (hero[:34], row[:26]),
              not S.hero_scope_matches(hero, row),
              '%s / %s' % (sorted(S.hero_scope(hero)),
                           sorted(S.hero_scope(row))))

    print('')
    print('=== the slot matcher honours it ===')
    rows = [dict(name='Q1 Revenue ($M)'),
            dict(name='Q1 Non-GAAP Gross Margin (%)'),
            dict(name='Q1 Product Gross Margin (%)')]
    check('a product-margin hero skips the company-margin row',
          S._match_kpi_slot('Product Gross Margin (%)', rows, 'Q1') == 2,
          S._match_kpi_slot('Product Gross Margin (%)', rows, 'Q1'))
    check('with no product row it resolves to nothing, not to the company row',
          S._match_kpi_slot('Product Gross Margin (%)', rows[:2], 'Q1') is None,
          S._match_kpi_slot('Product Gross Margin (%)', rows[:2], 'Q1'))
    check('a hardware-revenue hero does not take total revenue',
          S._match_kpi_slot('Hardware Revenue ($M)', rows, 'Q1') is None)
    check('an unqualified margin hero still resolves',
          S._match_kpi_slot('Gross Margin (%) - current and guided',
                            rows[:2], 'Q1') == 1)

    print('')
    print('=== CSCO: the reason line names the row and the path ===')
    rec = model.record_by_id('CSCO-2026Q4')
    entry = model.prepare_from_record(rec)
    cq = S.grade_current_quarter(parsed_from_record(rec), entry,
                                 stored_kpi_rows(rec, entry), model,
                                 evidence_from_record(rec))
    reason = cq['reason'] or ''
    check('the pin still lands at +1.0', cq['score'] == 1.0, cq['score'])
    check('the derivation is recorded as the revenue fallback',
          cq.get('derivation') == 'revenue-fallback', cq.get('derivation'))
    check('the reason SAYS revenue fallback', 'REVENUE FALLBACK' in reason)
    check('it names the documented no-bogey path',
          'no-bogey path' in reason)
    check('it flags the lower authority of a consensus comparison',
          'LOWER AUTHORITY' in reason)
    check('it names the source figure, not just the hero',
          'revenue (hero KPI not present' in reason)
    check('it no longer claims the hero was READ',
          'Product Gross Margin' in reason
          and 'clears consensus' not in reason, reason[:38])
    # 17252 is the STORED revenue; the selftest body says $17.25B -> 17250.
    # Both are the revenue fallback, and both collide with the margin ratio.
    check('the compared pair is stated in full',
          '17252' in reason and '16825' in reason, reason[-70:])
    check('two flags, allowance zero',
          cq['flags'] == 2 and cq['base'] == 2.0,
          '%s flags, base %s' % (cq['flags'], cq['base']))

    print('')
    print('=== a hero-row derivation is labelled differently ===')
    rec2 = model.record_by_id('SNDK-2026Q4')
    e2 = model.prepare_from_record(rec2)
    cq2 = S.grade_current_quarter(parsed_from_record(rec2), e2,
                                  stored_kpi_rows(rec2, e2), model,
                                  evidence_from_record(rec2))
    r2 = cq2['reason'] or ''
    check('SNDK still pins at +1.0', cq2['score'] == 1.0, cq2['score'])
    check('its derivation is a hero ROW, not the fallback',
          (cq2.get('derivation') or '').startswith('hero-row'),
          cq2.get('derivation'))
    check('and it names which row index', 'hero-row[' in r2, r2[:40])
    check('the fallback wording is absent',
          'REVENUE FALLBACK' not in r2)
    check('the row it read is named',
          'Gross Margin' in r2, r2[:60])

    print('')
    print('=== the +2.53 / +2.54 collision is now decidable ===')
    # Both derivations round to the same clearance. Only the path distinguishes
    # them, which is exactly why the path is printed.
    check('CSCO clearance is the revenue comparison',
          abs(cq['clearance'] - 2.53) < 0.01, cq['clearance'])
    check('and the sentence attributes it to revenue',
          'revenue' in reason.split('|')[1] if '|' in reason else False,
          reason.split('|')[1][:40] if '|' in reason else reason[:40])
    margin_ratio = (66.3 / 64.66 - 1.0) * 100.0
    check('the margin derivation would read the same to 2dp',
          abs(margin_ratio - cq['clearance']) < 0.02,
          '%.4f vs %.4f' % (margin_ratio, cq['clearance']))

    print('')
    print('=== CBRS-2026Q1: refusing beats grading the wrong subject ===')
    rec3 = model.record_by_id('CBRS-2026Q1')
    e3 = model.prepare_from_record(rec3)
    cq3 = S.grade_current_quarter(parsed_from_record(rec3), e3,
                                  stored_kpi_rows(rec3, e3), model,
                                  evidence_from_record(rec3))
    check('the hardware hero does not resolve onto total revenue',
          cq3.get('heroSlot') is None, cq3.get('heroSlot'))
    check('and the refusal names the hero it could not find',
          'Hardware Revenue' in (cq3['reason'] or ''), cq3['reason'][:40])
    check('the score is unchanged (it was ungradeable either way)',
          cq3['score'] is None, cq3['score'])

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
