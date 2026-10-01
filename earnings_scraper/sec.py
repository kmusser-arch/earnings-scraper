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
NOT_EARNINGS = 'NOT_EARNINGS'
FETCH_FAILED = 'FETCH_FAILED'

#: A RANK HINT, NEVER A FILTER -- see exhibit_candidates for why.
_EXHIBIT = re.compile(r'(?i)ex.{0,8}99|pressrelease|earnings|[^a-z]pr\.')

#: R1.htm, R2.htm ... are the XBRL viewer's rendering stubs, not documents.
_RENDER_STUB = re.compile(r'(?i)^r\d+\.htm')

#: how many documents in one accession are worth reading before giving up.
#: An earnings 8-K carries the release plus perhaps a CFO commentary; more
#: than a handful means the ranking is wrong, not that the release is deep
#: in the list.
MAX_CANDIDATES = 4

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


#: SEC asks for no more than ten requests a second. A live print spends
#: three; a corpus sweep over 57 tickers spends a few hundred, which is the
#: only time this matters -- so the pace is enforced here rather than left
#: to each caller to remember.
MIN_INTERVAL = 0.12
_last_request = [0.0]


def _throttle():
    import time as _t
    wait = MIN_INTERVAL - (_t.time() - _last_request[0])
    if wait > 0:
        _t.sleep(wait)
    _last_request[0] = _t.time()


def _get(url, timeout, fetcher=None):
    """(text, status) or (None, None). NEVER raises."""
    if fetcher is not None:
        return fetcher(url, timeout)
    ua = user_agent()
    if not ua:
        return None, None
    _throttle()
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

    ★★ AND THE DATE IS NOT ENOUGH ON ITS OWN. An issuer can file two 8-Ks
    in one afternoon -- results at 16:02 and a director appointment at
    16:40 -- so the date alone would be a coin flip between them. Item 2.02
    is the filer's own declaration of which is which, and this is the LIVE
    path, where picking the wrong one costs a fabricated read on the card.
    """
    body, _ = _get(SUBMISSIONS_URL % int(cik), timeout, fetcher)
    if not body:
        return None, None
    try:
        recent = json.loads(body)['filings']['recent']
    except Exception:                                   # noqa: BLE001
        return None, None
    n = len(recent.get('form') or [])
    items = recent.get('items') or [''] * n
    accepted = recent.get('acceptanceDateTime') or [None] * n
    on = on or time.strftime('%Y-%m-%d')
    for i, form in enumerate(recent.get('form') or []):
        if (form == '8-K' and recent['filingDate'][i] == on
                and EARNINGS_ITEM in (items[i] or '')):
            return recent['accessionNumber'][i], accepted[i]
    return None, None


#: ★★★ 8-K ITEM 2.02 -- 'Results of Operations and Financial Condition'.
#: THE ISSUER DECLARES THIS ITSELF, and the submissions API carries it in
#: the `items` field, so filtering on it costs NO extra request.
#:
#: MEASURED ACROSS ALL 57 LIBRARY TICKERS: 3,893 8-Ks, of which 1,495 carry
#: Item 2.02 -- SIXTY-TWO PERCENT OF 8-Ks ARE NOT EARNINGS. Taking 'the
#: most recent 8-K' would therefore be wrong about twice as often as right.
EARNINGS_ITEM = '2.02'


def recent_8ks(cik, limit=4, timeout=DEFAULT_TIMEOUT, fetcher=None,
               earnings_only=True):
    """[(accession, filingDate, accepted)] newest first.

    ★ THE ISSUER ALREADY ANSWERED THE QUESTION. An 8-K is filed for
    executive changes, debt and material agreements as well as results, and
    guessing from the filename or the date would be re-deriving in
    ignorance something the filer stated outright in the item code.
    """
    body, _ = _get(SUBMISSIONS_URL % int(cik), timeout, fetcher)
    if not body:
        return []
    try:
        recent = json.loads(body)['filings']['recent']
    except Exception:                                   # noqa: BLE001
        return []
    n = len(recent.get('form') or [])
    accepted = recent.get('acceptanceDateTime') or [None] * n
    items = recent.get('items') or [''] * n
    out = []
    for i, form in enumerate(recent.get('form') or []):
        if form != '8-K':
            continue
        if earnings_only and EARNINGS_ITEM not in (items[i] or ''):
            continue
        out.append((recent['accessionNumber'][i], recent['filingDate'][i],
                    accepted[i] if i < len(accepted) else None))
        if len(out) >= limit:
            break
    return out


#: Phrases that appear in an earnings release and essentially nowhere else
#: in the 8-K population.
_EARNINGS_MARKERS = (
    'diluted', 'gross margin', 'per share', 'operating income',
    'revenue', 'net income', 'guidance', 'outlook', 'fourth quarter',
    'first quarter', 'second quarter', 'third quarter', 'fiscal',
)


def looks_like_earnings(text, need=4):
    """Does this exhibit carry the furniture of an earnings release?

    ★★ AN 8-K ON EARNINGS DAY IS NOT NECESSARILY THE EARNINGS RELEASE. They
    are also filed for executive changes, debt issuance and material
    agreements, and a company can file two in one afternoon. A departure
    announcement that parsed cleanly and scored as a print would be a
    fabricated read with full provenance behind it, which is worse than a
    refusal by exactly the margin that makes it believable.

    Deliberately a WEAK test used as a DISQUALIFIER, never as proof: it
    throws out obvious non-earnings filings and leaves the real check --
    does this exhibit carry the metrics the card declares -- to the caller,
    who alone knows what the card declares.
    """
    low = (text or '').lower()
    return sum(1 for m in _EARNINGS_MARKERS if m in low) >= need


def exhibit_candidates(cik, accession, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """Every plausible exhibit URL in an accession, best first.

    ★★★ A FILENAME ALLOWLIST WAS THE DEFECT. Requiring 'ex99' or
    'pressrelease' in the name threw away SEVENTEEN OF FIFTY-SEVEN tickers
    and reported NO_EXHIBIT -- a reader miss wearing the clothes of a data
    absence. The releases it could not see were named q2fy27pr.htm (NVDA),
    exhibit991.htm (TSLA) and googexhibit991q22026.htm (GOOGL); the last
    even contains '99' and still failed, because 'ex-?99' does not match
    'exhibit991'.

    So the name is a RANK HINT and never a filter. Candidates are ordered
    by (looks like an exhibit, size) and the CALLER decides by READING
    them: a document identifies itself by what is in it, not by what it is
    called. Only the index pages and the XBRL rendering stubs are dropped,
    and those by exact role rather than by guess.
    """
    base = ARCHIVE_URL % (int(cik), str(accession).replace('-', ''))
    body, _ = _get(base + 'index.json', timeout, fetcher)
    if not body:
        return None
    try:
        items = json.loads(body)['directory']['item']
    except Exception:                                   # noqa: BLE001
        return None
    out = []
    for it in items:
        name = str(it.get('name') or '')
        low = name.lower()
        if not low.endswith(('.htm', '.html')):
            continue
        # the EDGAR index pages and the XBRL viewer's rendering stubs
        # (R1.htm, R2.htm ...) are never the release
        if 'index' in low or _RENDER_STUB.match(low):
            continue
        try:
            size = int(it.get('size') or 0)
        except Exception:                               # noqa: BLE001
            size = 0
        out.append((1 if _EXHIBIT.search(low) else 0, size, base + name))
    out.sort(reverse=True)
    return [u for _h, _s, u in out]


def exhibit_url(cik, accession, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """The single best-guess exhibit URL, or None. Prefer exhibit_text()."""
    found = exhibit_candidates(cik, accession, timeout, fetcher)
    return found[0] if found else None


def to_text(html):
    """Plain text from the exhibit.

    ★★ backfill._strip_html PLUS html.unescape, and the second half is not
    cosmetic. EDGAR writes the guidance band as '$61.5 billion &#177; $1.5
    billion'; _strip_html decodes six named entities and leaves every
    numeric one, so the PLUS_MINUS range parser sees no +/- at all and the
    three guide rows -- the trade -- lose their band.

    ★★★★★ AND THEN THE UNESCAPE POISONS EVERY TABLE, WHICH IS A DEFECT THIS
    FUNCTION INTRODUCED. &#160; decodes to U+00A0 NO-BREAK SPACE, and EDGAR
    writes it between every figure and its column gap. The horizontal table
    reader splits on RUNS OF ORDINARY SPACES, so a no-break space inside the
    gap makes the whole row invisible:

        '   Percent of revenue   86.8\\xa0   %   84.6\\xa0   % ...'
            h_row_cells -> label=None, NO VALUES
        the same line with \\xa0 -> ' '
            h_row_cells -> 'Percent of revenue', [86.8, 84.6, 44.7,
                                                  87.0, 84.9, 45.7]

    MEASURED: all 109 corpus exhibits carry it, 54,268 occurrences, plus 64
    of U+202F. ZERO of the three wire fixtures do -- the wire bodies arrive
    clean, so this was never a property of the documents, only of this path.

    Normalising every non-newline, non-tab whitespace character to a plain
    space, because the readers' entire model of a column boundary is 'a run
    of spaces' and any character that merely LOOKS like a space breaks it
    silently.
    """
    import html as _h
    txt = backfill._strip_html(_h.unescape(html or ''))
    return re.sub(r'[^\S\n\t]', ' ', txt)


def exhibit_text(cik, accession, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """(text, outcome, url) for one accession. The shared leg.

    ★ ONE CODE PATH FOR THE LIVE CARD AND THE CORPUS. A sweep that fetched
    documents by a different route than the 4:15pm path would be measuring
    a transport nothing actually uses, and every number it produced would
    carry a silent asterisk.
    """
    found = exhibit_candidates(cik, accession, timeout, fetcher)
    if not found:
        return None, NO_EXHIBIT, None
    # ★ READ, THEN DECIDE. The ranking is a hint; the document is the
    # evidence. Walking the candidates and keeping the first that is both
    # structured and recognisably an earnings release is what let the
    # filename allowlist go, and with it the seventeen false NO_EXHIBITs.
    best = (None, NO_EXHIBIT, found[0])
    for url in found[:MAX_CANDIDATES]:
        html, _status = _get(url, timeout, fetcher)
        if not html:
            best = (None, FETCH_FAILED, url)
            continue
        text = to_text(html)
        if not extract.has_line_structure(text):
            best = (None, NO_STRUCTURE, url)
            continue
        if not looks_like_earnings(text):
            best = (None, NOT_EARNINGS, url)
            continue
        return text, OK, url
    return best


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
    # ★ THE ONLY REASON THIS MODULE EXISTS IS STRUCTURE. exhibit_text
    # discards a capture that has none, rather than swapping one unreadable
    # document for another while reporting success.
    text, outcome, url = exhibit_text(cik, accession, timeout, fetcher)
    return done(text, outcome, url)
