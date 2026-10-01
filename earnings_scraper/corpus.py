# -*- coding: utf-8 -*-
r"""THE 8-K CORPUS — EVERY SPEC TESTABLE BEFORE THE PRINT.

★★★★★ EVERY CONSTRAINT IN THIS BUILD TRACED BACK TO ELEVEN CAPTURED FRAMES.
Which code paths got exercised was decided by which issuers we happened to
have specced, and the holes only showed when a print walked into one:
is_heading broken by MDB's 66-character wrap, NO_LINE_STRUCTURE invisible
until the first Globe Newswire ticker reached a card, a held-out set of
five because that was all there was to hold out.

EDGAR removes that constraint. Every 8-K for all 57 library tickers is
fetchable now, in ONE format, without waiting for anybody to report. A spec
stops being a guess the moment the prior quarter's exhibit can be read.

★ LIBRARY-DRIVEN, EXACTLY AS THE WATCHLIST IS. No per-ticker config and no
special cases: the ticker set is derived from the library at runtime, so a
ticker is covered the moment its record exists and every future
pre-earnings build inherits this with no extra step.

★★ THE CACHE IS A CACHE. It lives under the gitignored state directory
because it is regenerable from EDGAR in a few minutes. Nothing here is a
source of truth; the exhibits are.
"""

import io
import json
import os
import time

from . import extract
from . import sec

#: ~25 KB a document, a few hundred documents.
CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'state', 'corpus')


def library_tickers(model=None):
    """Every ticker the library holds a record for. DERIVED, never listed."""
    from .model import Model
    model = model or Model()
    out = set()
    for rec in (model.library.get('records') or []):
        rid = rec.get('id') or ''
        if '-' in rid:
            out.add(rid.rsplit('-', 1)[0].upper())
    return sorted(out)


def path_for(ticker, accession, out_dir=None):
    return os.path.join(out_dir or CORPUS_DIR, ticker.upper(),
                        '%s.json' % accession)


def store(doc, out_dir=None):
    p = path_for(doc['ticker'], doc['accession'], out_dir)
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    io.open(p, 'w', encoding='utf-8', newline=chr(10)).write(
        json.dumps(doc, indent=1, ensure_ascii=False))
    return p


def load(ticker, out_dir=None):
    """Every cached exhibit for a ticker, newest filing first."""
    d = os.path.join(out_dir or CORPUS_DIR, str(ticker or '').upper())
    if not os.path.isdir(d):
        return []
    docs = []
    for name in os.listdir(d):
        if not name.endswith('.json'):
            continue
        try:
            docs.append(json.load(io.open(os.path.join(d, name),
                                          encoding='utf-8')))
        except Exception:                               # noqa: BLE001
            continue
    return sorted(docs, key=lambda x: x.get('filingDate') or '', reverse=True)


def fetch_ticker(ticker, quarters=2, out_dir=None, timeout=sec.DEFAULT_TIMEOUT,
                 fetcher=None, scan=6):
    """Cache up to `quarters` EARNINGS exhibits for one ticker.

    ★ SCANS MORE 8-Ks THAN IT KEEPS. An issuer files for executive changes,
    debt and material agreements too, so taking 'the last two 8-Ks' would
    quietly fill the corpus with departure announcements. It walks back
    `scan` filings and keeps the ones whose exhibit reads like an earnings
    release.
    """
    cik = sec.cik_for(ticker, timeout, fetcher)
    if not cik:
        return [], sec.NO_CIK
    kept, outcome = [], sec.OK
    for accession, filed, accepted in sec.recent_8ks(cik, scan, timeout,
                                                     fetcher):
        if len(kept) >= quarters:
            break
        p = path_for(ticker, accession, out_dir)
        if os.path.exists(p):
            try:
                doc = json.load(io.open(p, encoding='utf-8'))
            except Exception:                           # noqa: BLE001
                doc = None
            if doc:
                if doc.get('isEarnings'):
                    kept.append(doc)
                continue
        text, got, url = sec.exhibit_text(cik, accession, timeout, fetcher)
        if got != sec.OK:
            outcome = got
            continue
        doc = dict(ticker=ticker.upper(), cik=cik, accession=accession,
                   filingDate=filed, accepted=accepted, url=url,
                   charsPerLine=round(extract.chars_per_line(text), 1),
                   bytes=len(text),
                   isEarnings=sec.looks_like_earnings(text),
                   fetchedAt=time.strftime('%Y-%m-%dT%H:%M:%S'),
                   text=text)
        store(doc, out_dir)
        if doc['isEarnings']:
            kept.append(doc)
    return kept, outcome


def sweep(tickers=None, quarters=2, out_dir=None, model=None,
          timeout=sec.DEFAULT_TIMEOUT, fetcher=None, log=None):
    """Fetch the corpus. Returns a per-ticker summary.

    NEVER raises: a ticker that cannot be resolved is recorded and the
    sweep continues, because one delisted symbol must not cost the other
    fifty-six.
    """
    log = log if log is not None else print
    names = tickers or library_tickers(model)
    summary, started = {}, time.time()
    for i, ticker in enumerate(names, 1):
        try:
            kept, outcome = fetch_ticker(ticker, quarters, out_dir, timeout,
                                         fetcher)
        except Exception as exc:                        # noqa: BLE001
            summary[ticker] = dict(kept=0, outcome='CRASHED: %s'
                                   % type(exc).__name__)
            continue
        summary[ticker] = dict(
            kept=len(kept), outcome=outcome,
            dates=[d.get('filingDate') for d in kept],
            charsPerLine=[d.get('charsPerLine') for d in kept])
        if log:
            log('  %3d/%-3d %-6s %d exhibit(s) %-14s %s'
                % (i, len(names), ticker, len(kept), outcome,
                   ', '.join(str(d.get('filingDate')) for d in kept)))
    if log:
        have = sum(1 for v in summary.values() if v['kept'])
        log('')
        log('%d of %d tickers have at least one earnings exhibit · %d docs '
            '· %.0fs' % (have, len(names),
                         sum(v['kept'] for v in summary.values()),
                         time.time() - started))
    return summary
