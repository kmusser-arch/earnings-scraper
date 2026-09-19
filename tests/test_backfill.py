# -*- coding: utf-8 -*-
"""Canonical backfill: a second read that arrives late and loudly.

★★★ IT CANNOT TOUCH THE CARD. It runs after delivery, writes only where
scraperRead is BLANK, never overwrites a value the wire body produced, and a
failure is a no-op. Every assertion here is about that boundary, because the
whole basis for allowing a network dependency into this process is that it
cannot cost anything when it fails.

★★ THE FETCHER IS INJECTED AND THE TESTS NEVER TOUCH THE NETWORK. A dependency
that can only be exercised live is one that gets exercised for the first time
at 4:15pm.

★ AND IT MEASURES WHAT BLOCKED IT. Canonical fetch was refused once before
because page-live latency was unmeasured. Every attempt records outcome,
elapsedMs and pageLive, so the number arrives from the first few prints as a
by-product rather than as a research task.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import backfill as B            # noqa: E402

WIRE_NO_BLOCK = (
    'Adobe (Nasdaq:ADBE), the global technology leader, today reported.\n'
    'Total revenue was $6.76 billion.\n'
    'View source version on businesswire.com: '
    'https://www.businesswire.com/news/home/20260910832552/en/\n')

WIRE_WITH_BLOCK = (
    'Adobe AI-first ARR grew more than 150% year over year\n'
    'SAN JOSE, Calif.--(BUSINESS WIRE)-- Adobe (Nasdaq:ADBE) today reported.\n'
    'View source version on businesswire.com: '
    'https://www.businesswire.com/news/home/20260910832552/en/\n')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    # ── the permalink, and the gate ──────────────────────────────────────
    check(B.permalink(WIRE_NO_BLOCK)
          == 'https://www.businesswire.com/news/home/20260910832552/en/',
          'the canonical permalink is read out of the release itself')
    check(B.permalink('no link here') is None, 'and absent when there is none')

    go, why = B.should_fetch(WIRE_NO_BLOCK)
    check(go, 'a body whose sub-headline block is ABSENT is worth fetching')
    go2, why2 = B.should_fetch(WIRE_WITH_BLOCK)
    check(not go2 and why2 == B.NOT_NEEDED,
          'NEVER FETCH WHAT WE ALREADY HOLD — a capture whose block survived '
          'is skipped, so requests equal gaps rather than prints')
    go3, why3 = B.should_fetch('body with no link and no dateline')
    check(not go3 and why3 == B.NO_PERMALINK,
          'and no permalink means no attempt')

    # ── failure is a no-op ───────────────────────────────────────────────
    def explodes(url, timeout):
        raise OSError('connection refused')

    rows = [dict(actual=1.0, scraperRead=None)]
    entry = dict(keyKPIs=[dict(name='x', extraction={'specState': 'EXTRACTABLE',
                                                     'documentLabels': ['x']})])
    att = B.backfill(rows, entry, WIRE_NO_BLOCK, fetcher=explodes)
    check(att['outcome'] == B.NETWORK_ERROR,
          'a refused connection is recorded, not raised')
    check(att['pageLive'] is False and isinstance(att['elapsedMs'], int),
          'and the attempt still records pageLive and elapsedMs — the '
          'measurement does not depend on success')
    check(rows[0]['scraperRead'] is None and rows[0]['actual'] == 1.0,
          'the rows are untouched: failure is a no-op and the card is '
          'unchanged')

    def times_out(url, timeout):
        raise TimeoutError('timed out')
    att_t = B.backfill(rows, entry, WIRE_NO_BLOCK, fetcher=times_out)
    check(att_t['outcome'] == B.TIMEOUT, 'a timeout is its own outcome')

    def http_404(url, timeout):
        return 404, '<html>gone</html>'
    att_4 = B.backfill(rows, entry, WIRE_NO_BLOCK, fetcher=http_404)
    check(att_4['outcome'] == B.HTTP_ERROR and att_4['httpStatus'] == 404,
          'an HTTP error records its status')

    # ── a successful fetch fills ONLY the blanks ─────────────────────────
    page = ('<html><body><p>Adobe AI-first ARR grew more than 150% year '
            'over year</p><p>Total revenue was $6.76 billion.</p>'
            '</body></html>')

    def ok(url, timeout):
        return 200, page

    rows2 = [
        dict(actual=None, scraperRead=None),          # blank -> may fill
        dict(actual=None, scraperRead=999.0),         # already read -> keep
    ]
    entry2 = dict(fiscalQuarter=3, fiscalYear=2026, keyKPIs=[
        dict(name='AI-First ARR (%)', extraction={
            'specState': 'EXTRACTABLE', 'documentLabels': ['AI-first ARR'],
            'documentUnit': '%', 'storedUnit': '%', 'whereKind': ['PROSE']}),
        dict(name='Q3 Revenue ($B)', extraction={
            'specState': 'EXTRACTABLE', 'documentLabels': ['Total revenue'],
            'documentUnit': '$B', 'storedUnit': '$B', 'whereKind': ['PROSE']}),
    ])
    att2 = B.backfill(rows2, entry2, WIRE_NO_BLOCK, fetcher=ok)
    check(att2['outcome'] == B.OK and att2['pageLive'] is True,
          'a live page records OK and pageLive')
    check(rows2[1]['scraperRead'] == 999.0,
          'A VALUE THE WIRE BODY PRODUCED IS NEVER OVERWRITTEN — a later '
          'different reading is a disagreement to surface, not a correction '
          'to apply silently')
    if rows2[0]['scraperRead'] is not None:
        check(rows2[0].get('scraperSource') == 'CANONICAL_BACKFILL',
              'a value that came from the fetch says so (%s)'
              % rows2[0]['scraperRead'])
    else:
        check(att2['filled'] == 0,
              'nothing filled, and the attempt says so rather than pretending')

    # ── html stripping keeps the prose the readers need ──────────────────
    txt = B._strip_html(page)
    check('AI-first ARR grew more than 150%' in txt,
          'tag removal leaves the sentence intact')
    check('<' not in txt, 'and leaves no markup behind')


main()
