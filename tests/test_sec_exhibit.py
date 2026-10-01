# -*- coding: utf-8 -*-
r"""THE 8-K EXHIBIT FETCH — DRIVEN ENTIRELY OFF A FAKE EDGAR.

★ THE FETCHER IS INJECTED, so this never touches the network and never
depends on what Micron filed. The one live assertion sits behind
SEC_CONTACT and is skipped when it is unset.

★★ THE REFUSALS ARE THE POINT. This module's whole contract is 'a
better-shaped document, or nothing', and a transport that returns a WORSE
document while reporting success is strictly worse than no transport at
all -- the caller would throw away a wire body it could still have read.
So every path that must yield nothing is driven here, including the one
that succeeds at every network step and is thrown away at the last gate.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import sec                        # noqa: E402

NL = chr(10)

TICKERS = '{"0":{"cik_str":723125,"ticker":"MU","title":"MICRON"}}'
SUBS = ('{"filings":{"recent":{'
        '"form":["8-K","8-K"],'
        '"filingDate":["2026-09-30","2026-08-26"],'
        '"acceptanceDateTime":["2026-09-30T20:02:22.000Z",'
        '"2026-08-26T12:06:55.000Z"],'
        '"items":["2.02,9.01","5.02"],'
        '"accessionNumber":["0000723125-26-000018",'
        '"0001104659-26-101067"]}}}')
INDEX = ('{"directory":{"item":['
         '{"name":"mu-20260930.htm","size":"28747"},'
         '{"name":"a2026q4ex991-pressrelease.htm","size":"356891"},'
         '{"name":"0000723125-26-000018-index.html","size":"900"},'
         '{"name":"mu-20260930_lab.xml","size":"21629"}]}}')

#: a structured exhibit, and the entity EDGAR actually writes for +/-
EXHIBIT = ('<html><body><p>Business Outlook</p>'
           + '<p>Fourth quarter fiscal 2026 results</p>'
           + '<p>GAAP net income, or per share, diluted</p>'
           + '<p>Gross margin and operating income guidance</p>'
           + ''.join('<tr><td>Revenue</td><td>$61.5 billion &#177; $1.5 '
                     'billion</td></tr>' for _ in range(40))
           + '</body></html>')

FLAT = ('<html><body><p>' + ('revenue gross margin per share fiscal ' * 400)
        + '</p></body></html>')

#: ★ an 8-K that is NOT an earnings release. Structured, fetches cleanly,
#: and must still be refused -- 62% of 8-Ks look like this.
DEPARTURE = ('<html><body>'
             + ''.join('<p>On September 30, 2026 the Board appointed a new '
                       'director pursuant to the agreement.</p>'
                       for _ in range(40))
             + '</body></html>')


def fake(exhibit=EXHIBIT, index=INDEX, subs=SUBS, tickers=TICKERS):
    def fetcher(url, timeout):
        if 'company_tickers' in url:
            return tickers, 200
        if 'submissions' in url:
            return subs, 200
        if url.endswith('index.json'):
            return index, 200
        if url.endswith('.htm'):
            return exhibit, 200
        return None, None
    return fetcher


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    sec._TICKERS = {}
    txt, outcome, ms, url = sec.press_release('MU', '2026-09-30',
                                              fetcher=fake())
    check(outcome == sec.OK and txt,
          'the happy path returns text with outcome OK (%s, %d ms)'
          % (outcome, ms))
    check(url and url.endswith('a2026q4ex991-pressrelease.htm'),
          'and picks the EXHIBIT, not the 8-K cover page — largest match '
          'wins because both match on name and only one has the tables: %s'
          % (url or '').rsplit('/', 1)[-1])

    # ── ★★ THE ENTITY. &#177; is what carries the guidance band ──────────
    check('±' in txt and '&#177;' not in txt,
          'the +/- survives as a character — backfill._strip_html decodes '
          'six NAMED entities and leaves every numeric one, so without '
          'html.unescape the three PLUS_MINUS guide rows lose their band '
          'and BAND_COLLAPSED fires on the rows that are the trade')

    # ── ★★★★★ AND THEN THE UNESCAPE POISONS EVERY TABLE ─────────────────
    # &#160; decodes to U+00A0 NO-BREAK SPACE, and EDGAR writes it between
    # every figure and its column gap. The horizontal reader splits on runs
    # of ORDINARY spaces, so a no-break space inside the gap makes the whole
    # row invisible -- label=None, zero values, silently.
    import earnings_scraper.tables as _T
    poisoned = ('   Percent of revenue   86.8    %   84.6    %   '
                '44.7    %   87.0    %   84.9    %   45.7    %  ')
    check(not _T.h_row_cells(poisoned),
          'a row carrying \xa0 in its column gaps reads as NOTHING — the '
          'defect this normalisation exists to prevent')
    clean = sec.to_text('<p>' + poisoned.replace(' ', '&#160;') + '</p>')
    cells = _T.h_row_cells(clean.strip(chr(10)).split(chr(10))[0]
                           if chr(10) in clean.strip() else clean.strip())
    check(cells and [v for v, _p in cells[1]] == [86.8, 84.6, 44.7, 87.0,
                                                  84.9, 45.7],
          'through to_text it reads all six cells IN ORDER %s — which is '
          'what makes a six-column GAAP|Non-GAAP block addressable at all'
          % ([v for v, _p in cells[1]] if cells else None))
    check(' ' not in clean and ' ' not in clean,
          'and no no-break space survives. MEASURED: all 109 corpus '
          'exhibits carried it (54,268 + 64 occurrences) and ZERO of the '
          'three wire fixtures did — never a property of the documents, '
          'only of this path')

    # ── ★ THE DATE IS A FILTER, NOT A PREFERENCE ─────────────────────────
    _t, out, _ms, _u = sec.press_release('MU', '2026-09-29', fetcher=fake())
    check(out == sec.NO_FILING and _t is None,
          'a date with no 8-K returns NO_FILING rather than falling back to '
          'the most recent one — August governance filing that parses '
          'cleanly is the worst thing this module could hand back (%s)' % out)

    # ── ★★★ STRUCTURE IS THE WHOLE CONTRACT ──────────────────────────────
    # Every network step succeeds here. The capture is discarded at the last
    # gate, which is the only place the module's promise can actually be
    # kept or broken.
    _t, out, _ms, _u = sec.press_release('MU', '2026-09-30',
                                         fetcher=fake(exhibit=FLAT))
    check(out == sec.NO_STRUCTURE and _t is None,
          'a capture WITHOUT line structure is thrown away (%s) — the '
          'contract is "a better-shaped document, or nothing", and '
          'returning a flat document while reporting OK would make the '
          'caller discard a wire body it could still have read' % out)

    # ── ★★★ 62% OF 8-Ks ARE NOT EARNINGS ─────────────────────────────────
    # Measured over all 57 library tickers: 3,893 8-Ks, 1,495 carrying Item
    # 2.02. A departure announcement that parsed cleanly and scored as a
    # print would be a fabricated read with full provenance behind it.
    sec._TICKERS = {}
    _t, out, _ms, _u = sec.press_release('MU', '2026-09-30',
                                         fetcher=fake(exhibit=DEPARTURE))
    check(out == sec.NOT_EARNINGS and _t is None,
          'a STRUCTURED 8-K that is not an earnings release is refused '
          '(%s) — it fetches cleanly and parses, and that is exactly what '
          'makes it dangerous' % out)

    # ── ★★ ITEM 2.02 IS THE ISSUER'S OWN ANSWER ──────────────────────────
    SUBS_NO_202 = SUBS.replace('"2.02,9.01"', '"5.02"')
    sec._TICKERS = {}
    _t, out, _ms, _u = sec.press_release('MU', '2026-09-30',
                                         fetcher=fake(subs=SUBS_NO_202))
    check(out == sec.NO_FILING,
          'an 8-K filed under Item 5.02 (departures) is not even fetched '
          '(%s) — the filer declared what it was, and guessing from the '
          'date would be re-deriving in ignorance something already stated'
          % out)

    # ── the unresolvable paths ───────────────────────────────────────────
    sec._TICKERS = {}
    _t, out, _ms, _u = sec.press_release('ZZZZ', '2026-09-30', fetcher=fake())
    check(out == sec.NO_CIK, 'an unknown ticker is NO_CIK (%s)' % out)
    sec._TICKERS = {}
    _t, out, _ms, _u = sec.press_release(
        'MU', '2026-09-30', fetcher=fake(index='{"directory":{"item":[]}}'))
    check(out == sec.NO_EXHIBIT, 'an accession with no exhibit is NO_EXHIBIT '
          '(%s)' % out)
    sec._TICKERS = {}
    _t, out, _ms, _u = sec.press_release(
        'MU', '2026-09-30', fetcher=lambda u, t: (None, None))
    check(out == sec.NO_CIK and _t is None,
          'and a dead transport refuses rather than raising (%s)' % out)

    # ── ★ NO FABRICATED CONTACT ──────────────────────────────────────────
    old = os.environ.pop('SEC_CONTACT', None)
    try:
        check(sec.user_agent() is None,
              'with SEC_CONTACT unset there is NO default User-Agent — '
              'inventing a contact address to put in a request header is '
              'not ours to do')
        sec._TICKERS = {}
        _t, out, _ms, _u = sec.press_release('MU', '2026-09-30')
        check(out == sec.NO_CONTACT,
              'and the real fetch refuses with a NAMED reason (%s) rather '
              'than a 403 that reads like an outage' % out)
        os.environ['SEC_CONTACT'] = 'someone@example.com'
        check('someone@example.com' in (sec.user_agent() or ''),
              'set, it is carried — www.sec.gov 403s a UA it cannot read '
              'as a contact, and the SHAPE is what it checks')
    finally:
        os.environ.pop('SEC_CONTACT', None)
        if old is not None:
            os.environ['SEC_CONTACT'] = old

    if not os.environ.get('SEC_CONTACT'):
        print('SKIP live EDGAR assertion — SEC_CONTACT unset')
        return
    sec._TICKERS = {}
    txt, out, ms, url = sec.press_release('MU', '2026-09-30')
    check(out == sec.OK and txt and '±' in txt,
          'LIVE: the real MU exhibit fetches, has structure and carries '
          'the band (%s, %d ms)' % (out, ms))


main()
