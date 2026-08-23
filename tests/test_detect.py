"""Detector tests. The four positive/negative cases are real items pulled
from news.log; the rest are the failure modes worth locking down.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper.detect import classify, extract_tickers  # noqa: E402

REAL_RELEASE_BODY = (
    'Net income of $1.2 million, or $0.45 per diluted share, compared to '
    '$0.9 million in the prior year period. Total revenues increased 8% to '
    '$14.3 million. Condensed consolidated statements of operations follow.'
)

CISCO_BODY = (
    'Revenue of $17.25 billion, up 18% year over year. Non-GAAP diluted EPS '
    'of $1.22; GAAP diluted EPS of $0.97. Non-GAAP gross margin of 66.3%. '
    'Cisco will host a conference call at 4:30 p.m. Condensed consolidated '
    'statements of operations attached.'
)

CASES = [
    # (headline, body, expected_is_earnings, label)
    ('EHang to Report Second Quarter 2026 Unaudited Financial Results on '
     'Tuesday, August 25, 2026', '', False, 'scheduling notice'),
    ('JSB Financial Inc. Reports Second Quarter 2026 Results',
     REAL_RELEASE_BODY, True, 'real release'),
    ('ColorTokens Named a Leader in Q3 2026 Microsegmentation Vendor '
     'Evaluation By Independent Research Firm', '', False, 'analyst award'),
    ('Cisco Reports Fourth Quarter and Fiscal Year 2026 Earnings',
     CISCO_BODY, True, 'release that also schedules a call'),
    ('ROSEN, TOP RANKED INVESTOR COUNSEL, Encourages Acme Investors to '
     'Secure Counsel - Class Action',
     'investors who purchased $5.0 million of securities', False,
     'class action'),
    ('Acme Corp Declares Quarterly Dividend of $0.25 Per Share',
     'The board declared a dividend of $0.25 per share, payable...', False,
     'dividend'),
    ('Acme Announces Q2 2026 Financial Results',
     'Total revenues of $88.0 million, up 12%. Non-GAAP operating income of '
     '$9.1 million. Gross margin 61.2%.', True, 'announces + figures'),
]

TICKER_CASES = [
    ({'primary_instruments': ['EQ:US:CSCO'], 'headline': 'x'},
     ['CSCO'], 'primary_instruments'),
    ({'primary_instruments': [],
      'headline': 'Acme Corp (NASDAQ: ACME) Reports Q2 Results',
      'body': ''}, ['ACME'], 'exchange tag'),
    ({'primary_instruments': [],
      'headline': 'Widget Industries Reports Second Quarter Results',
      'body': 'Widget Industries (NYSE American: WDG) today announced'},
     ['WDG'], 'exchange tag'),
    ({'primary_instruments': [], 'headline': 'No symbol anywhere here',
      'body': ''}, [], 'unresolved'),
]


def main():
    failures = 0

    print('=== classify ===')
    for headline, body, expected, label in CASES:
        r = classify({'headline': headline, 'body': body})
        ok = r['is_earnings'] == expected
        failures += 0 if ok else 1
        print('%s %-38s got=%-5s exp=%-5s c=%.2f f=%d  %s' % (
            'PASS' if ok else 'FAIL', label, r['is_earnings'], expected,
            r['confidence'], r['figures'], r['reason']))

    print()
    print('=== extract_tickers ===')
    watchlist = {'ACME': {'company': 'Acme Corporation'}}
    for item, expected, expected_src in TICKER_CASES:
        tickers, src = extract_tickers(item, watchlist)
        ok = tickers == expected and src == expected_src
        failures += 0 if ok else 1
        print('%s got=%-10s src=%-19s exp=%s' % (
            'PASS' if ok else 'FAIL', tickers, src, expected))

    # Company-name fallback needs an empty exchange tag to reach stage 3.
    item = {'primary_instruments': [],
            'headline': 'Acme Corporation Reports Second Quarter 2026 Results',
            'body': 'no exchange tag in this one'}
    tickers, src = extract_tickers(item, watchlist)
    ok = tickers == ['ACME'] and src == 'company name'
    failures += 0 if ok else 1
    print('%s got=%-10s src=%-19s exp=[\'ACME\']' % (
        'PASS' if ok else 'FAIL', tickers, src))

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
