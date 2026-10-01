# -*- coding: utf-8 -*-
r"""THE 8-K EXHIBIT — A SECOND CAPTURE OF THE SAME RELEASE, WITH STRUCTURE.

★★★ THE WIRE BODY IS NOT THE DOCUMENT. On the MU F4Q26 print the PZM frame
arrived as 18.6 KB containing TEN line breaks -- 1,859 characters per line.
Every table-shaped row refused NO_LINE_STRUCTURE, and correctly so: there
were no column boundaries to read. The issuer files the SAME release with
the SEC as an 8-K exhibit, where the table markup survives:

    WIRE          18,592 B     10 newlines   1,859.2 chars/line   NO
    8-K EX-99.1   25,568 B    552 newlines      46.3 chars/line   YES

That is the whole of this module's reason to exist. It changes the DOCUMENT,
not the readers.

★★ NEVER IN THE 4:15pm PATH -- the same rule backfill.py carries, and for a
second reason here. MU's 8-K was accepted at 16:02:22 ET against a 16:01:00
wire frame: EIGHTY-TWO SECONDS LATE. The June print matches (20:02:01Z). So
the card ships on the wire, and this runs after delivery or not at all.
Blocking the card on a filing that does not exist yet would trade the thing
Kyle needs for the thing he can read later.

★ AND IT REFUSES TO MAKE THINGS WORSE. A capture that comes back without
line structure is discarded rather than returned: the caller keeps the wire
body it already had. The only outcome this module is allowed to produce is
'a better-shaped document, or nothing'.

SEC ETIQUETTE: www.sec.gov 403s a User-Agent it cannot read as a contact.
The identity does not matter -- the SHAPE does -- but SEC asks for a real
one, so set SEC_CONTACT in .env. Measured: 'shelnewsapi research' -> 403;
'shelnewsapi/1.0 (research; contact: x@example.com)' -> 200.
"""

import json
import os
import re
import time

from . import backfill
from . import extract

#: SEC asks for ten requests per second at the outside. This module spends
#: three per print, so the limit is never the constraint -- the courtesy is.
DEFAULT_TIMEOUT = 8.0

TICKER_MAP_URL = 'https://www.sec.gov/files/company_tickers.json'
SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK%010d.json'
ARCHIVE_URL = 'https://www.sec.gov/Archives/edgar/data/%d/%s/'

#: outcomes. OK is the only one that carries text.
OK = 'OK'
NO_CONTACT = 'NO_CONTACT'
NO_CIK = 'NO_CIK'
NO_FILING = 'NO_FILING'
NO_EXHIBIT = 'NO_EXHIBIT'
NO_STRUCTURE = 'NO_STRUCTURE'
FETCH_FAILED = 'FETCH_FAILED'

#: the press release is filed as EX-99.1, occasionally EX-99.2. The 8-K
#: itself (mu-20260930.htm) is the COVER PAGE and carries no table.
_EXHIBIT = re.compile(r'(?i)ex-?99|pressrelease|earnings')

_TICKERS = {}


def user_agent():
    """The UA string, or None when no contact is configured.

    ★ NO SILENT DEFAULT CONTACT. Inventing an address to put in someone
    else's request header is not ours to do, so an unset SEC_CONTACT is a
    refusal with a named reason rather than a fabricated identity.
    """
    contact = (os.environ.get('SEC_CONTACT') or '').strip()
    if not contact:
        return None
    return 'shelnewsapi/1.0 (earnings research; contact: %s)' % contact


def _get(url, timeout, fetcher=None):
    """(text, status) or (None, None). NEVER raises."""
    if fetcher is not None:
        return fetcher(url, timeout)
    ua = user_agent()
    if not ua:
        return None, None
    import urllib.request
    req = urllib.request.Request(
        url, headers={'User-Agent': ua, 'Accept-Encoding': 'identity'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', 'replace'), resp.status
    except Exception:                                   # noqa: BLE001
        return None, None


def cik_for(ticker, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """The SEC's CIK for a ticker, or None. Cached for the process."""
    global _TICKERS
    if not _TICKERS:
        body, _ = _get(TICKER_MAP_URL, timeout, fetcher)
        if not body:
            return None
        try:
            _TICKERS = {str(v['ticker']).upper(): int(v['cik_str'])
                        for v in json.loads(body).values()}
        except Exception:                               # noqa: BLE001
            return None
    return _TICKERS.get(str(ticker or '').upper())


def filing_on(cik, on=None, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """(accession, acceptedISO) for the 8-K filed on `on`, else (None, None).

    ★ THE DATE IS A FILTER, NOT A PREFERENCE. Returning 'the most recent
    8-K' would hand back August's governance filing when tonight's earnings
    8-K has not posted yet, and a stale document that parses cleanly is the
    worst thing this module could produce.
    """
    body, _ = _get(SUBMISSIONS_URL % int(cik), timeout, fetcher)
    if not body:
        return None, None
    try:
        recent = json.loads(body)['filings']['recent']
    except Exception:                                   # noqa: BLE001
        return None, None
    on = on or time.strftime('%Y-%m-%d')
    for i, form in enumerate(recent.get('form') or []):
        if form == '8-K' and recent['filingDate'][i] == on:
            return (recent['accessionNumber'][i],
                    (recent.get('acceptanceDateTime') or [None] * (i + 1))[i])
    return None, None


def exhibit_url(cik, accession, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """The URL of the press-release exhibit inside an accession, or None.

    Largest match wins: the cover page and the exhibit both match on name,
    and the exhibit is the one with the tables in it.
    """
    base = ARCHIVE_URL % (int(cik), str(accession).replace('-', ''))
    body, _ = _get(base + 'index.json', timeout, fetcher)
    if not body:
        return None
    try:
        items = json.loads(body)['directory']['item']
    except Exception:                                   # noqa: BLE001
        return None
    best, best_size = None, -1
    for it in items:
        name = str(it.get('name') or '')
        if not name.lower().endswith(('.htm', '.html')):
            continue
        if 'index' in name.lower() or not _EXHIBIT.search(name):
            continue
        try:
            size = int(it.get('size') or 0)
        except Exception:                               # noqa: BLE001
            size = 0
        if size > best_size:
            best, best_size = name, size
    return (base + best) if best else None


def to_text(html):
    """Plain text from the exhibit.

    ★★ backfill._strip_html PLUS html.unescape, and the second half is not
    cosmetic. EDGAR writes the guidance band as '$61.5 billion &#177; $1.5
    billion'; _strip_html decodes six named entities and leaves every
    numeric one, so the PLUS_MINUS range parser sees no +/- at all and the
    three guide rows -- the trade -- lose their band.
    """
    import html as _h
    return backfill._strip_html(_h.unescape(html or ''))


def press_release(ticker, on=None, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """(text, outcome, elapsed_ms, url). NEVER raises, NEVER blocks a card.

    text is None unless outcome is OK.
    """
    started = time.time()

    def done(text, outcome, url=None):
        return text, outcome, int((time.time() - started) * 1000), url

    if fetcher is None and not user_agent():
        return done(None, NO_CONTACT)
    cik = cik_for(ticker, timeout, fetcher)
    if not cik:
        return done(None, NO_CIK)
    accession, _accepted = filing_on(cik, on, timeout, fetcher)
    if not accession:
        return done(None, NO_FILING)
    url = exhibit_url(cik, accession, timeout, fetcher)
    if not url:
        return done(None, NO_EXHIBIT)
    html, _status = _get(url, timeout, fetcher)
    if not html:
        return done(None, FETCH_FAILED, url)
    text = to_text(html)
    # ★ THE ONLY REASON THIS MODULE EXISTS IS STRUCTURE. Returning a capture
    # that has none would swap one unreadable document for another while
    # reporting success.
    if not extract.has_line_structure(text):
        return done(None, NO_STRUCTURE, url)
    return done(text, OK, url)
