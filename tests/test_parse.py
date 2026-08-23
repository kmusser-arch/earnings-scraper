"""Parser tests.

The CSCO case uses the real figures stored in earnings-library.json for
CSCO-2026Q4 (revenue $17,252M, non-GAAP EPS $1.22, GAAP EPS $0.97, non-GAAP
gross margin 66.3%) wrapped in press-release prose, so a pass means the parser
reproduces a figure set the model already trusts.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper.parse import (  # noqa: E402
    parse_release, pct_delta, verdict_for,
)

CSCO_PR = """
Cisco Reports Fourth Quarter and Fiscal Year 2026 Earnings

SAN JOSE, Calif. -- Cisco today reported fourth quarter results. Total
revenue of $17.25 billion, up 18% year over year. GAAP diluted earnings per
share of $0.97; non-GAAP diluted earnings per share of $1.22. Non-GAAP gross
margin of 66.3%. Non-GAAP operating margin of 35.9%.

For the first quarter of fiscal 2027, Cisco expects revenue of $18.1 billion
to $18.3 billion. For full year fiscal 2027, Cisco expects revenue of
$76.5 billion to $77.5 billion.

Cisco will host a conference call at 4:30 p.m. Condensed consolidated
statements of operations follow.
"""

SMALLCAP_PR = """
Widget Industries Reports Second Quarter 2026 Results

Net revenues decreased 4.2% to $88.0 million. Net loss per diluted share was
$(0.45), compared to net income of $0.12 per diluted share in the prior year.
Gross margin was 41.5%.
"""


def approx(a, b, tol=0.01):
    return a is not None and abs(a - b) <= tol


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-46s %s' % ('PASS' if ok else 'FAIL', label, got))

    print('=== CSCO (real library figures) ===')
    p = parse_release({'headline': 'Cisco Reports Fourth Quarter and Fiscal '
                                   'Year 2026 Earnings', 'body': CSCO_PR})
    rev = p['revenue']
    check('revenue normalised to $M', approx(rev and rev['value_musd'], 17250.0, 5),
          rev and rev['value_musd'])
    check('revenue growth captured', approx(rev and rev['growth_pct'], 18.0),
          rev and rev['growth_pct'])
    check('non-GAAP EPS separated', approx(p['eps'].get('non-GAAP', {}).get('value'), 1.22),
          p['eps'].get('non-GAAP', {}).get('value'))
    check('GAAP EPS separated', approx(p['eps'].get('GAAP', {}).get('value'), 0.97),
          p['eps'].get('GAAP', {}).get('value'))
    check('gross margin', approx(p['margins'].get('grossMargin', {}).get('value'), 66.3),
          p['margins'].get('grossMargin', {}).get('value'))
    nq = p['guidance'].get('nextQ')
    check('next-Q guide midpoint', approx(nq and nq['mid'], 18200.0, 5), nq and nq['mid'])
    fy = p['guidance'].get('fy')
    check('FY guide midpoint', approx(fy and fy['mid'], 77000.0, 5), fy and fy['mid'])

    print()
    print('=== small cap, negative EPS, revenue decline ===')
    p2 = parse_release({'headline': 'Widget Industries Reports Second Quarter '
                                    '2026 Results', 'body': SMALLCAP_PR})
    r2 = p2['revenue']
    check('revenue $M', approx(r2 and r2['value_musd'], 88.0), r2 and r2['value_musd'])
    check('decline is negative', (r2 or {}).get('growth_pct', 0) < 0,
          r2 and r2['growth_pct'])
    eps_vals = [v['value'] for v in p2['eps'].values()]
    check('parenthesised loss is negative', any(v < 0 for v in eps_vals), eps_vals)

    print()
    print('=== surprise math ===')
    pct, flag = pct_delta(17252.0, 16825.0)
    check('CSCO rev vs cons = +2.5%', approx(pct, 2.54, 0.02), pct)
    check('no units flag', flag is None, flag)
    pct2, flag2 = pct_delta(17252.0, 16.825)   # $M actual vs $B expected
    check('units mismatch suppressed', pct2 is None and flag2 is not None, flag2)
    check('verdict +2.5% -> BEAT', verdict_for(2.54) == 'BEAT', verdict_for(2.54))
    check('verdict +12% -> DEMOLISH', verdict_for(12.0) == 'DEMOLISH', verdict_for(12.0))
    check('verdict -0.2% -> INLINE', verdict_for(-0.2) == 'INLINE', verdict_for(-0.2))
    check('verdict -8% -> MISS', verdict_for(-8.0) == 'MISS', verdict_for(-8.0))
    check('verdict None -> N/A', verdict_for(None) == 'N/A', verdict_for(None))

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
