"""HARD 10 — domain-implausible expected values.

The SNDK signature is what this exists for: both columns implausible AND
mutually consistent, which is precisely what a bogey-vs-consensus comparison
cannot see.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import plausibility as PL      # noqa: E402
from earnings_scraper.model import Model             # noqa: E402


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, got))

    print('=== the founding case is caught ===')
    model = Model()
    findings, summary = PL.audit(model)
    sndk = [f for f in findings if f['recordId'] == 'SNDK-2026Q4']
    check('SNDK-2026Q4 flagged', bool(sndk), len(sndk))
    check('all four flagged rows found', len(sndk) == 4, len(sndk))
    check('flagged as SYSTEMATIC (both columns)',
          all(f.get('systematic') for f in sndk))
    check('the blind spot is named',
          all('HARD 8/9' in (f.get('blindSpot') or '') for f in sndk))
    check('GM 84.0 bogey is one of them',
          any(f['value'] == 84.0 and f['column'] == 'bogey' for f in sndk))
    check('GM 81.5 consensus is one of them',
          any(f['value'] == 81.5 and f['column'] == 'consensus' for f in sndk))

    print()
    print('=== no false positives on the rest of the library ===')
    others = {f['recordId'] for f in findings} - {'SNDK-2026Q4'}
    check('only SNDK is flagged', not others, sorted(others))
    check('summary agrees', summary['recordsFlagged'] == 1,
          summary['recordsFlagged'])

    print()
    print('=== APP is NOT a false positive ===')
    # AppLovin adj EBITDA margin genuinely printed 85% against 81% prior year.
    # A flat 70% ceiling would call that an error.
    f = PL.check_expectation('Q1 Adj EBITDA Margin (%) ★★', 84.0,
                             'Software / AdTech / AI Advertising')
    check('84% adtech adj EBITDA margin is plausible', f is None, f)
    f = PL.check_expectation('Q1 Adj EBITDA Margin (%)', 96.0,
                             'Software / AdTech / AI Advertising')
    check('96% is still flagged', f is not None)

    print()
    print('=== sector conditioning ===')
    cases = [
        # (name, value, sector, should_flag)
        ('FQ4 Gross Margin (%)', 84.0, 'Semiconductors / Memory', True),
        ('FQ4 Gross Margin (%)', 38.0, 'Semiconductors / Memory', False),
        ('Gross Margin (%)', 84.0, 'Software / SaaS', False),
        ('Gross Margin (%)', 30.0, 'Software / SaaS', True),
        # CSCO's real non-GAAP gross margin is 66.3% -- inside the band, and
        # flagging it would be the false positive that makes HARD 10 useless.
        ('Gross Margin (%)', 66.3, 'Networking / AI Infrastructure', False),
        ('Gross Margin (%)', 85.0, 'Networking / AI Infrastructure', True),
        ('Operating Margin (%)', 35.9, 'Networking / AI Infrastructure', False),
        ('AWS Revenue Growth YoY (%)', 17.0, 'Consumer Discretionary / Cloud',
         False),
        ('Revenue Growth YoY (%)', 900.0, 'Cloud / AI Infrastructure', True),
    ]
    for name, value, sector, should in cases:
        got = PL.check_expectation(name, value, sector) is not None
        check('%-28s %-6s %-30s -> %s'
              % (name[:28], value, sector[:30], 'FLAG' if should else 'ok'),
              got == should, 'FLAG' if got else 'ok')

    print()
    print('=== it flags, it never corrects ===')
    f = PL.check_expectation('FQ4 Gross Margin (%)', 84.0,
                             'Semiconductors / Memory')
    check('no corrected/suggested value in the finding',
          'corrected' not in f and 'suggested' not in f and 'fixed' not in f,
          sorted(f))
    check('the finding carries a reason', bool(f.get('why')),
          (f.get('why') or '')[:44])
    check('the finding carries the band', f['low'] == 5.0 and f['high'] == 70.0)

    print()
    print('=== actuals are NOT checked ===')
    # A surprising actual is news; an impossible expectation is a data error.
    rec = dict(id='X', ticker='X', sector='Semiconductors / Memory',
               preEarnings=dict(keyKPIs=[dict(name='Gross Margin (%)',
                                              consensus=38.0, bogey=40.0)]),
               actuals=dict(keyKPIs=[dict(actual=84.6)]))
    check('a wild ACTUAL does not trigger HARD 10',
          PL.check_record(rec) == [], PL.check_record(rec))

    print()
    print('=== non-numeric and missing values are ignored ===')
    check('text consensus ignored',
          PL.check_expectation('Gross Margin (%)', '$68.69B / $4.64',
                               'Semiconductors / Memory') is None)
    check('None ignored',
          PL.check_expectation('Gross Margin (%)', None,
                               'Semiconductors / Memory') is None)
    check('unknown sector ignored (no band -> no claim)',
          PL.check_expectation('Gross Margin (%)', 84.0,
                               'Financials / Brokerage') is None)

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
