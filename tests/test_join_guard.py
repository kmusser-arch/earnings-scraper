# -*- coding: utf-8 -*-
"""The join checks the body's issuer against the filename's ticker.

★★★ AN EXISTING DEPENDENCY IS NOT A SAFE ONE, IT IS ONE NOBODY HAS CHECKED.
The continuation join keys on ticker + date from the filename, and that key was
adopted on the reasoning that ticker resolution is already a dependency the
card carries. True, and complacent — one capture in the set disagrees with
itself:

    20260826-122603-AAPL.json   filename AAPL   primary_instruments AAPL
                                body '(NASDAQ: WDC) Western Digital'

★★ AND primary_instruments CANNOT BE THE CHECK, because it is the field that is
wrong: the WIRE resolved that item to AAPL. The body is the only independent
witness, and a press release names its issuer in an exchange-qualified form
within the first few lines.

★ ABSENCE IS NOT DISAGREEMENT. ORCL's part 2 begins mid-table and names no
ticker at all — which is precisely the case the join exists to serve. The guard
fires only where the body NAMES a ticker and it is not the one claimed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import continuation as C        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PEND = os.path.join(os.path.dirname(HERE), 'earnings_scraper', 'state',
                    'pending')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    # ── the body names its issuer ────────────────────────────────────────
    check(C.body_ticker('Adobe (Nasdaq:ADBE), the global technology leader')
          == {'ADBE'}, 'an exchange-qualified ticker is read from the body')
    check(C.body_ticker('HPE (NYSE: HPE) today announced') == {'HPE'},
          'spacing and exchange name do not matter')
    check(C.body_ticker('  Hardware   670   776   714') == set(),
          'a continuation page that begins mid-table names NOTHING — and '
          'that is not a disagreement')

    # ── the guard fires on disagreement only ─────────────────────────────
    check(C.issuer_disagrees('20260826-122603-AAPL.json',
                             'SAN JOSE--(BUSINESS WIRE)-- Western Digital '
                             'Corporation (NASDAQ: WDC) today reported')
          is not None,
          'a body naming WDC under a filename claiming AAPL is REFUSED')
    check(C.issuer_disagrees('20260910-160500-ADBE.json',
                             'Adobe (Nasdaq:ADBE) announced') is None,
          'and a body naming its own ticker joins')
    check(C.issuer_disagrees('20260910-161605-ORCL.json',
                             '  Hardware   670   776') is None,
          'a silent continuation page joins — absence is not disagreement')

    # ── on the real captures ─────────────────────────────────────────────
    bad = os.path.join(PEND, '20260826-122603-AAPL.json')
    if os.path.exists(bad):
        got = C.join(bad)
        check(got['joined'] == 0 and got.get('rejectedParts'),
              'the real mismatched capture yields NO joined text, with the '
              'reason named')
        check('WDC' in str(got.get('rejectedParts')),
              'and the reason names the issuer the body actually carries')

    orcl = os.path.join(PEND, '20260910-161341-ORCL.json')
    if os.path.exists(orcl):
        got = C.join(orcl)
        check(got['joined'] == 2 and not got.get('rejectedParts'),
              'and ORCL still joins its two parts — the guard costs the '
              'legitimate join nothing')


main()
