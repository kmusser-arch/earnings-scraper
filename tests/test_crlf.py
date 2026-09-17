# -*- coding: utf-8 -*-
"""LINE ENDINGS ARE PART OF THE POPULATION, AND THE CORPUS WAS NOT.

★★★ THE WIRE CARRIES BOTH. ADBE's body arrived with 12,755 CRLF endings and
ORCL's with zero, in the same hour, off the same gateway. The extractor
converted a character offset to a line index with `len(line) + 1` while
splitting with splitlines(), which consumes CRLF's two characters and gives
back one -- a drift of one character per line, cumulative. On ADBE a label
deep in the document resolved to a row hundreds of lines away, and the column
selector then read a REAL, WELL-FORMED TABLE ROW BELONGING TO ANOTHER METRIC:
Subscription Revenue came back 6,760, the total revenue line. Not a crash, not
a refusal -- a plausible number with false provenance.

★★ AND THE HARNESS WAS HIDING IT. Reading a fixture with io.open(...) applies
universal-newline translation, so every .txt release reached the extractor as
bare LF no matter what the file held. Read with newline='' the same fixtures
show HPE at 30,121 CRLF and SNOW at 35,206. So the corpus was not short of
CRLF -- THE READER WAS ERASING IT, which is worse, because the files looked
like evidence that the wire's shape was covered.

Third instance of a corpus that was not the population, after DJN-vs-PRN and
the vtables horizontal corpus.

★ SO THIS IS A DIFFERENTIAL TEST, NOT A FIXTURE. A single CRLF fixture proves
one document parses; this asserts that EVERY extractable row returns the
IDENTICAL value and the IDENTICAL refusal under both line endings, across all
eight releases. A line ending must be invisible to a result. Where it is not,
the value it changes is the bug.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import registry as R         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
PEND = os.path.join(ROOT, 'earnings_scraper', 'state', 'pending')
FIX = os.path.join(HERE, 'fixtures', 'releases')
CORPUS = os.path.join(MODEL, 'tests', 'corpus')

CASES = [
    ('ORCL-2027Q1', os.path.join(PEND, '20260910-161341-ORCL.json'), 'raw'),
    ('ADBE-2026Q3', os.path.join(PEND, '20260910-160500-ADBE.json'), 'raw'),
    ('AVGO-2026Q3', os.path.join(FIX, 'AVGO-2026-09-02.txt'), 'txt'),
    ('HPE-2026Q3', os.path.join(FIX, 'HPE-2026-09-02.txt'), 'txt'),
    ('SNOW-2027Q2', os.path.join(FIX, 'SNOW-2026-09-02.txt'), 'txt'),
    ('APP-2026Q2', os.path.join(CORPUS, 'APP-2026Q2.txt'), 'txt'),
    ('SNDK-2026Q4', os.path.join(CORPUS, 'SNDK-2026Q4.txt'), 'txt'),
    ('WDC-2026Q4', os.path.join(CORPUS, 'WDC-2026Q4.txt'), 'txt'),
]

LF = chr(10)
CR = chr(13)


def raw_bytes_text(path, kind):
    """The document EXACTLY as stored -- no universal-newline translation.

    io.open() without newline='' rewrites CRLF to LF on the way in, which is
    what made eight releases look like one population.
    """
    if kind == 'raw':
        with io.open(path, encoding='utf-8') as fh:
            return (json.load(fh).get('rawItem') or {}).get('body') or ''
    with io.open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def as_lf(text):
    return text.replace(CR + LF, LF).replace(CR, LF)


def as_crlf(text):
    return as_lf(text).replace(LF, CR + LF)


def main():
    lib = json.load(io.open(os.path.join(MODEL, 'earnings-library.json'),
                            encoding='utf-8'))
    recs = {r['id']: r for r in lib['records']}

    print('LINE-ENDING COMPOSITION AS STORED')
    seen_crlf = 0
    checked = 0
    drifted = []

    for rid, path, kind in CASES:
        if not os.path.exists(path):
            print('   SKIP %-13s (absent)' % rid)
            continue
        stored = raw_bytes_text(path, kind)
        crlf = stored.count(CR + LF)
        lf_only = stored.count(LF) - crlf
        if crlf:
            seen_crlf += 1
        print('   %-13s CRLF=%-7d bare-LF=%-7d %s'
              % (rid, crlf, lf_only, 'CRLF' if crlf > lf_only else 'LF'))

        rec = recs.get(rid)
        if not rec:
            continue
        body_lf, body_crlf = as_lf(stored), as_crlf(stored)
        for row in rec['preEarnings'].get('keyKPIs') or []:
            spec = R.spec_for(row)
            if R.status_of(spec) != 'EXTRACTABLE':
                continue
            a = X.value_for(body_lf, row, record=rec)
            b = X.value_for(body_crlf, row, record=rec)
            checked += 1
            if a.get('value') != b.get('value'):
                drifted.append((rid, row.get('name'), a.get('value'),
                                b.get('value')))

    print('')
    print('   %d extractable row(s) run under BOTH line endings' % checked)
    for rid, nm, av, bv in drifted:
        print('   DRIFT %-13s %-38s LF=%s CRLF=%s' % (rid, (nm or '')[:38],
                                                      av, bv))

    # ── the assertions ───────────────────────────────────────────────────
    print('')
    ok = 'PASS'
    bad = 'FAIL'

    print('%s %d extractable row(s) exercised under both line endings'
          % (ok if checked > 0 else bad, checked))

    if drifted:
        print('%s %d row(s) return a DIFFERENT value under CRLF than under '
              'LF: %s' % (bad, len(drifted), drifted[:4]))
    else:
        print('%s a line ending is invisible to every extracted value' % ok)

    if seen_crlf >= 1:
        print('%s %d of %d releases carry CRLF as stored -- the regression '
              'set holds the shape the wire produces' % (ok, seen_crlf,
                                                         len(CASES)))
    else:
        print('%s no release in the regression set carries CRLF -- the corpus '
              'has drifted off the population' % bad)

    # THE READER MUST NOT BE THE THING THAT NORMALISES THE EVIDENCE.
    probe = 'a' + CR + LF + 'b'
    print('%s the round trip preserves the stored ending'
          % (ok if as_lf(probe).count(CR) == 0
             and as_crlf(as_lf(probe)) == probe else bad))
    print('%s the splitter and the counter agree on one convention'
          % (ok if len(probe.split(LF)) == probe.count(LF) + 1 else bad))


main()
