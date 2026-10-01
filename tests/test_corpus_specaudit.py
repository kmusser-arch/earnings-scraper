# -*- coding: utf-8 -*-
r"""THE CORPUS SWEEP AND THE SPEC AUDIT, DRIVEN OFF A FAKE EDGAR.

★ The whole point of the corpus is that a spec stops being a guess before
the print. So the audit has to be able to FAIL -- an auditor that passes
everything is a tick mark, not a check -- and the absent-string arm below
is driven on the real defect that cost the MU card.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import corpus                     # noqa: E402
from earnings_scraper import sec                        # noqa: E402
from earnings_scraper import specaudit                  # noqa: E402

TICKERS = '{"0":{"cik_str":723125,"ticker":"MU","title":"MICRON"}}'
SUBS = ('{"filings":{"recent":{'
        '"form":["8-K","8-K","8-K"],'
        '"filingDate":["2026-09-30","2026-08-26","2026-06-24"],'
        '"items":["2.02,9.01","5.02","2.02"],'
        '"acceptanceDateTime":["2026-09-30T20:02:22.000Z",'
        '"2026-08-26T12:06:55.000Z","2026-06-24T20:02:01.000Z"],'
        '"accessionNumber":["acc-sep","acc-aug","acc-jun"]}}}')
INDEX = ('{"directory":{"item":['
         '{"name":"q2fy27pr.htm","size":"341113"},'
         '{"name":"R1.htm","size":"900000"},'
         '{"name":"0000-index.html","size":"900"}]}}')

BODY = ('<html><body><p>Business Outlook</p>'
        + '<p>Fourth quarter fiscal 2026 results, diluted per share</p>'
        + '<p>GAAP net income and gross margin guidance</p>'
        + ''.join('<tr><td>Revenue</td><td>$61.5 billion</td></tr>'
                  for _ in range(40)) + '</body></html>')


def fetcher(url, timeout):
    if 'company_tickers' in url:
        return TICKERS, 200
    if 'submissions' in url:
        return SUBS, 200
    if url.endswith('index.json'):
        return INDEX, 200
    return BODY, 200


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    out = tempfile.mkdtemp(prefix='corpus-')
    try:
        sec._TICKERS = {}
        kept, outcome = corpus.fetch_ticker('MU', quarters=2, out_dir=out,
                                            fetcher=fetcher)
        check(len(kept) == 2 and outcome == sec.OK,
              'two EARNINGS exhibits cached, skipping the Item 5.02 filing '
              'between them (%d kept, %s)' % (len(kept), outcome))
        check([d['filingDate'] for d in kept] == ['2026-09-30', '2026-06-24'],
              'and the August 5.02 departure filing is never fetched: %s'
              % [d['filingDate'] for d in kept])

        # ★ THE FILENAME ALLOWLIST THAT COST 17 TICKERS
        check(kept[0]['url'].endswith('q2fy27pr.htm'),
              "an exhibit named q2fy27pr.htm is found — the old allowlist "
              "needed 'ex99' or 'pressrelease' in the NAME and reported "
              "NO_EXHIBIT for NVDA, TSLA and GOOGL, a reader miss wearing "
              "the clothes of a data absence")
        check(not kept[0]['url'].endswith('R1.htm'),
              'while R1.htm — bigger than the release — is excluded by '
              'ROLE, because it is the XBRL viewer stub and never a document')

        # ── the cache is readable with NO transport at all ───────────────
        # ★ AND ONLY THE EXHIBITS ARE CACHED. fetch_ticker still asks the
        # submissions API every time, by design: which filings exist is the
        # thing that changes, and a stale answer there is how a sweep comes
        # to miss the print it was run for. load() is the offline half.
        again = corpus.load('MU', out_dir=out)
        check(len(again) == 2 and all(d.get('text') for d in again),
              'the cached exhibits re-read from disk with no transport in '
              'the call at all (%d docs)' % len(again))
        check([d['filingDate'] for d in again] == ['2026-09-30',
                                                   '2026-06-24'],
              'newest filing first, so the audit can take [0] for this '
              'quarter and [1] for the prior one')

        # ── ★★★ THE AUDIT MUST BE ABLE TO FAIL ───────────────────────────
        rec = {'id': 'MU-2026Q4', 'reportDate': '2026-09-30',
               'preEarnings': {'keyKPIs': [
                   {'name': 'present', 'extraction': {
                       'specState': 'EXTRACTABLE',
                       'sectionAnchor': 'Business Outlook'}},
                   {'name': 'absent', 'extraction': {
                       'specState': 'EXTRACTABLE',
                       'sectionAnchor': 'FQ1-27 GUIDANCE',
                       'spanTerminator': 'The following table reconciles'}}]}}
        doc = specaudit.exhibit_for(rec, 'MU', out_dir=out)
        check(doc is not None and doc['filingDate'] == '2026-09-30',
              'the audit picks the exhibit matching the record reportDate, '
              'not merely the newest one')
        rows = specaudit.audit(rec, doc['text'])
        found = dict(((i, f), n) for i, f, _v, n in rows)
        check(found.get((0, 'sectionAnchor')) == 1,
              "a string that IS in the document is counted, not merely "
              "ticked — 'found 3' and 'found 1' warrant different responses")
        check(found.get((1, 'sectionAnchor')) == 0
              and found.get((1, 'spanTerminator')) == 0,
              'and BOTH strings that cost the MU card report 0 occurrences '
              '— absent means defect, not risk')

        prior = specaudit.exhibit_for(rec, 'MU', prior=True, out_dir=out)
        check(prior is not None and prior['filingDate'] == '2026-06-24',
              'prior=True returns the quarter BEFORE (%s), which is what a '
              'spec being authored has to be checked against — its own '
              'document does not exist yet'
              % (prior or {}).get('filingDate'))
    finally:
        shutil.rmtree(out, ignore_errors=True)


main()
