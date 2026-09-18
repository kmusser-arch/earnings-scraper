# -*- coding: utf-8 -*-
"""Joining a release that arrived in parts, without ever claiming it is whole.

★★★ THE KEY WAS ALREADY IN THE FILENAME. Days went into pairing continuation
pages by WIRE KEY — shared timestamp 58% false positive, 100ms proximity
25.4%, cross-id unusable — while both ORCL files were already resolved to ORCL
by the pipeline and already named for the same date. Ticker and date answer
'do these belong together'; the wire key was re-deriving a decision already
made upstream.

★★ THE JOIN NEVER CLEARS truncated. Part 1's income statement ends at Hardware
and part 2's supplemental grid STARTS at Hardware: the parts do not abut and
pages are missing between them. 'Joined, still incomplete' is honest; 'joined,
complete' would be the silent corruption everything here exists to prevent.

★ AND THE JOIN CREATES A HAZARD THAT THE SEAM CLOSES. Part 2 begins MID-TABLE
with no column header — the header is in the pages that never came. Before the
seam, the horizontal reader walked up across the join, borrowed part 1's
income-statement header, and returned 16,058 for a row whose answer is 19,345:
right metric, wrong column, plausible header, no complaint. The seam is a
sentence, because prose is what every close in this codebase stops at.

So the join's value is NOT that it fills those rows. It does not. Its value is
more text plus an honest refusal where a wrong number stood.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import axes as A                 # noqa: E402
from earnings_scraper import continuation as C         # noqa: E402
from earnings_scraper import hgrid as H                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PEND = os.path.join(os.path.dirname(HERE), 'earnings_scraper', 'state',
                    'pending')
P1 = os.path.join(PEND, '20260910-161341-ORCL.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    check(C.parse_name('20260910-161341-ORCL.json') == ('20260910', '161341',
                                                        'ORCL'),
          'the filename carries the ticker and the date — the whole key')
    check(C.parse_name('not-a-pending-file.txt') is None,
          'and a file that is not a pending capture yields no key')

    if not os.path.exists(P1):
        print('FAIL ORCL part 1 missing from pending')
        return

    got = C.join(P1)
    check(got['joined'] == 2 and len(got['parts']) == 2,
          'both ORCL parts join on ticker+date: %s' % ', '.join(got['parts']))
    check(len(got['text']) > 19000,
          'the joined document is about twice part 1 (%d chars)'
          % len(got['text']))
    check(got['truncated'] is True and got['marker'] == '(MORE TO FOLLOW)',
          'TRUNCATION IS STICKY — a join can never declare the document whole')
    check('STILL INCOMPLETE' in (got['note'] or ''),
          'and the note says so in those words')
    for figure in ('19,345', '7,388', '4,219'):
        check(figure in got['text'],
              'part 2 contributes %s to the text' % figure)

    # ── the seam, and what it prevents ───────────────────────────────────
    check(C.SEAM in got['text'], 'a seam is written between the parts')
    check(H.is_prose_line(C.SEAM) and A.is_table_boundary(C.SEAM),
          'and BOTH upward-walking readers treat it as a hard stop')

    lines = got['text'].split(chr(10))
    idx = [i for i, l in enumerate(lines) if '19,345' in l]
    check(bool(idx), 'the Total revenues row is present in the joined text')
    if idx:
        sel = H.select(lines, idx[0], {'documentUnit': '$M',
                                       'currencyBasis': 'USD'},
                       is_boundary=A.is_table_boundary)
        check(sel.get('value') is None,
              'and it REFUSES: part 2 arrives headerless, so nothing says '
              'which column is the FY total and which is FY27 Q1')
        check('16,058' not in str(sel.get('value')),
              'it does NOT return 16,058 — the value it gave before the seam, '
              'read off part 1\'s income-statement header across the join')

    # ── a single-part release is untouched ───────────────────────────────
    solo = os.path.join(PEND, '20260902-160503-HPE.json')
    if os.path.exists(solo):
        one = C.join(solo)
        check(one['joined'] == 1 and C.SEAM not in one['text'],
              'a release that arrived whole gets no seam and no join')


main()
