# -*- coding: utf-8 -*-
"""A denomination header need not be parenthesised.

★★★ ONE CONDITION, TWO NAMES, AND THE MODULE THAT COULD SEE IT WAS NOT THE
ONE THAT NEEDED IT. tables._SCALE_HEADER has always written the parenthesis as
OPTIONAL; extract._DENOM_RE required it. HPE prints every one of its 18
denomination headers BARE -- 'July 31, 2025 In millions, except per share
amounts' -- so HPE has ZERO parenthesised headers and the extractor saw none
of them. Its free cash flow came back as 958.0 on a row declaring $B: 958
BILLION dollars, with 'In millions' sitting 694 characters above it.

★★ THE READER ALREADY KNEW IT WAS GUESSING. The result carried
unitUnverified=True and shipped the magnitude anyway -- the doubt was measured
and nothing consulted it. But REFUSING on that flag is the wrong fix and the
corpus says so: 6 magnitude rows ship unverified, and 4 of them MATCH their
hand read, because they carry the unit in their own text ('$6.80 billion') or
declare it correctly. Refusing all six would cost 4 matches to remove 2
mismatches. The fix is to READ THE HEADER, which is what was actually missing.

★ AND THE RELAXATION HAS EXACTLY ONE FALSE POSITIVE, WHICH IS REFUSED. With
the paren optional the pattern matches the SUBSTRING 'in millions)' inside
ADBE's '(Shares in millions)' -- a SHARE COUNT that would then denominate
every dollar row beneath it. Measured: 18 newly found headers, all HPE, 0
share-header false positives, 1 row moves and no row that matches today
changes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import tables as T           # noqa: E402


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    hpe = ('July 31, 2025 In millions, except per share amounts\n'
           'Net cash provided by operating activities\n'
           'Free cash flow $ 958 $ 915\n')
    got = X.denomination(hpe, hpe.index('958'))
    check(got is not None and got[0] == '$M',
          "HPE's BARE 'In millions' is a denomination header — the form that "
          'made free cash flow read as 958 BILLION dollars')

    check(X.denomination('($ in millions)\nRevenue 1,924\n', 20)[0] == '$M',
          'and the parenthesised form still reads, unchanged')
    check(X.denomination('(in thousands)\nRevenue 1,923,686\n', 20)[0] == '$K',
          'thousands too')
    check(X.denomination('(dollars in billions)\nRevenue 1.9\n', 24)[0] == '$B',
          'and billions')

    # ── the false positive the relaxation creates, and its refusal ───────
    adbe = '(Shares in millions)\nDiluted 430\n'
    check(X.denomination(adbe, adbe.index('430')) is None,
          "★ '(Shares in millions)' is a SHARE COUNT, not a denomination — "
          'accepting it would denominate every dollar row beneath it')

    # ── silence is still not a default ───────────────────────────────────
    check(X.denomination('Revenue was strong this quarter. 1,924\n', 30)
          is None,
          'a document that never said stays None — the caller falls back to '
          'the spec AND records that it did')

    # ── the two modules now agree about what a header is ─────────────────
    bare = 'In millions'
    check(bool(T._SCALE_HEADER.search(bare))
          and X.denomination(bare + '\nRevenue 1,924\n',
                             len(bare) + 10) is not None,
          'tables and extract now accept the SAME header shape — the '
          'disagreement was the whole defect')


main()
