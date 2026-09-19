# -*- coding: utf-8 -*-
"""Canonical backfill — a SECOND read, fetched after the card has shipped.

★★★ NEVER IN THE 4:15pm PATH. A network round-trip belongs nowhere near the
card: latency spent there is spent in the one place it cannot be. This runs
AFTER delivery, writes only where the wire body produced nothing, and a
failure is a no-op with the card unchanged.

WHY IT EXISTS. The aggregator renders a body that begins at the lede, so the
SUB-HEADLINE BLOCK above the dateline is dropped — and that block is where an
issuer puts what it wants noticed, which makes its rows heroes
disproportionately, by construction. Adobe's release carries two:

    'Adobe AI-first ARR grew more than 150% year over year'
    'Achieves major milestone of 1 billion monthly active users (MAU)'

Neither is in the capture, both are rows on that card, one is a hero. The
gateway route is closed — subscribe_news offers one format and strip_body
applies to FTI alone — so the canonical permalink, which every BUS capture
carries in its own text, is the only lever.

★★ GATED ON WHAT WE ALREADY HOLD. Fetch only when completeness reports
subHeadlineBlock == ABSENT. A capture whose block survived needs nothing, and
never fetching what we already hold is what keeps the request count equal to
the gap count.

★ AND IT MEASURES THE THING THAT BLOCKED IT. Canonical fetch was rejected once
before because page-live latency was unmeasured — nobody knew whether the
permalink resolves in one second or thirty, or at all, at 16:05. Every attempt
records outcome, elapsed milliseconds and whether the page was live, so the
number arrives as a by-product of the first few prints rather than as a
research task. Failure is free; the measurement is not deferred.
"""

import re
import time

from . import completeness
from . import extract
from . import registry

#: the canonical permalink an issuer prints in its own release
PERMALINK = re.compile(
    r'https?://(?:www\.)?(?:businesswire|prnewswire|globenewswire)\.com'
    r'/[^\s<>"\']{6,200}', re.I)

DEFAULT_TIMEOUT = 8.0
USER_AGENT = 'earnings-scraper/1.0 (+card backfill; contact kmusser@trlm.com)'

OK = 'OK'
NO_PERMALINK = 'NO_PERMALINK'
NOT_NEEDED = 'NOT_NEEDED'
TIMEOUT = 'TIMEOUT'
HTTP_ERROR = 'HTTP_ERROR'
NETWORK_ERROR = 'NETWORK_ERROR'


def permalink(body):
    """The canonical URL the release prints for itself, or None.

    Taken from the LAST match: BusinessWire prints its source link in the
    trailer, and an earlier match is usually a company URL in boilerplate.
    """
    found = PERMALINK.findall(body or '')
    return found[-1].rstrip('.,);') if found else None


def should_fetch(body, state=None):
    """(bool, reason) — is anything to be gained by fetching this release?

    ★ NEVER FETCH WHAT WE ALREADY HOLD. A capture whose sub-headline block
    survived has nothing above the dateline to recover, so the request count
    stays equal to the gap count rather than to the print count.
    """
    st = state or completeness.assess(body)
    if st.get('subHeadlineBlock') != 'ABSENT':
        return False, NOT_NEEDED
    if not permalink(body):
        return False, NO_PERMALINK
    return True, None


def _urllib_fetch(url, timeout):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return resp.status, raw.decode('utf-8', 'replace')


def _strip_html(html):
    """Plain text from a fetched page — crude on purpose.

    The readers downstream want prose and space-aligned tables, and both
    survive tag removal. Anything cleverer is a second parser to maintain.
    """
    txt = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html or '')
    txt = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</tr>', '\n', txt)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&#39;', "'"),
                 ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>')):
        txt = txt.replace(a, b)
    txt = re.sub(r'[ \t]{3,}', '   ', txt)
    return re.sub(r'\n{3,}', '\n\n', txt)


def fetch(url, timeout=DEFAULT_TIMEOUT, fetcher=None):
    """(text, outcome, elapsed_ms, http_status). NEVER raises.

    The fetcher is injectable so the tests never touch the network: this code
    runs in the process that produces the card, and a dependency that can only
    be exercised live is one that gets exercised for the first time at 4:15pm.
    """
    get = fetcher or _urllib_fetch
    started = time.time()
    try:
        status, html = get(url, timeout)
        elapsed = int((time.time() - started) * 1000)
        if status and int(status) >= 400:
            return None, HTTP_ERROR, elapsed, int(status)
        return _strip_html(html), OK, elapsed, int(status or 200)
    except Exception as exc:                            # noqa: BLE001
        elapsed = int((time.time() - started) * 1000)
        name = type(exc).__name__.lower()
        outcome = TIMEOUT if ('timeout' in name or 'timedout' in name) \
            else NETWORK_ERROR
        return None, outcome, elapsed, None


def backfill(kpi_rows, entry, wire_body, timeout=DEFAULT_TIMEOUT,
             fetcher=None):
    """Fill blanks from the canonical page. Returns an attempt record.

    ★★ WRITES ONLY WHERE scraperRead IS BLANK, and never overwrites a value
    the wire body produced. The wire body is what the card was built from; a
    later, different reading of the same row is a disagreement to surface, not
    a correction to apply silently.
    """
    attempt = dict(attemptedAt=time.strftime('%Y-%m-%dT%H:%M:%S'),
                   outcome=None, elapsedMs=None, httpStatus=None,
                   pageLive=None, url=None, filled=0, rows=[])

    go, why = should_fetch(wire_body)
    if not go:
        attempt['outcome'] = why
        return attempt

    url = permalink(wire_body)
    attempt['url'] = url
    text, outcome, elapsed, status = fetch(url, timeout, fetcher)
    attempt.update(outcome=outcome, elapsedMs=elapsed, httpStatus=status,
                   pageLive=(outcome == OK))
    if outcome != OK or not text:
        return attempt                     # a no-op; the card is unchanged

    pre = (entry or {}).get('keyKPIs') or []
    rec = dict(fiscalQuarter=(entry or {}).get('fiscalQuarter'),
               fiscalYear=(entry or {}).get('fiscalYear'))
    for i, out_row in enumerate(kpi_rows or []):
        if not isinstance(out_row, dict) or i >= len(pre):
            continue
        if out_row.get('scraperRead') is not None:
            continue                       # the wire body already answered
        spec = registry.spec_for(pre[i])
        if registry.status_of(spec) != 'EXTRACTABLE':
            continue
        try:
            got = extract.value_for(text, pre[i], record=rec) or {}
        except Exception:                                # noqa: BLE001
            continue
        from . import parallel
        sr = parallel.in_stored_unit(got, spec)
        if sr is None:
            continue
        out_row['scraperRead'] = sr
        out_row['extractionKind'] = parallel.kind_of(
            got, spec, text, [l.strip() for l in text.split(chr(10))])
        out_row['currencyTaken'] = got.get('currencyTaken') or 'REPORTED'
        out_row['candidateCount'] = got.get('candidateCount')
        out_row['seenCount'] = got.get('seenCount')
        out_row['refusalReason'] = None
        out_row['scraperSource'] = 'CANONICAL_BACKFILL'
        out_row['agreesWithActual'] = parallel.agrees_on_card(
            out_row.get('actual'), sr, spec)
        attempt['filled'] += 1
        attempt['rows'].append((pre[i].get('name') or '')[:48])
    return attempt
