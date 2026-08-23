"""Decide whether a wire item is an actual earnings release, and for whom.

Two problems the live feed forces on us, both confirmed against news.log:

1. There is no earnings topic code. PR Newswire tags items `prel`/`sn`/`pr`,
   BusinessWire `cw`/`company_announcement`, Globe Newswire `cnw`. The
   vocabularies are provider-specific and none of them mark earnings. So
   detection is headline + body driven.

2. `primary_instruments` is frequently empty on press wires -- the PRN items
   in the sample carried `[]`. Ticker extraction needs a fallback chain.

And one trap: "EHang to Report Second Quarter 2026 Results on August 25" is a
scheduling notice, not a print. Those must never fire.
"""

import re

from .config import MIN_FINANCIAL_FIGURES

_PERIOD = (r'(?:first|second|third|fourth|1st|2nd|3rd|4th|Q[1-4]|'
           r'full[- ]year|fiscal|half[- ]year)')

_REPORT_VERB = re.compile(
    r'\b(?:report(?:s|ed|ing)?|announce(?:s|d)?|post(?:s|ed)?|'
    r'deliver(?:s|ed)?|release(?:s|d)?|provide(?:s|d)?)\b', re.I)

_RESULTS_NOUN = re.compile(
    r'\b(?:results?|earnings|financial results|operating results|revenue|'
    r'net income|net loss|EPS|earnings per share|performance)\b', re.I)

_PERIOD_RE = re.compile(_PERIOD, re.I)

# Scheduling-notice decoys. Future-tense report language announces a DATE,
# not a result.
_SCHEDULING = re.compile(
    r'\b(?:to\s+(?:report|announce|release|host|hold|discuss)'
    r'|will\s+(?:report|announce|release|host|hold|discuss)'
    r'|set\s+to\s+(?:report|announce|release)'
    r'|schedul\w+'
    r'|to\s+be\s+held'
    r'|invites?\s+(?:you|investors)'
    r'|date\s+(?:set|announced)'
    r'|conference\s+call\s+(?:and\s+webcast\s+)?(?:on|scheduled)'
    r'|announces?\s+(?:the\s+)?(?:date|timing))\b', re.I)

# Non-earnings press-release classes that mention money and could otherwise
# sneak past the figure gate. All of these appear on the wires in volume --
# class_action alone was 12 of 91 items in the sample.
_NON_EARNINGS = re.compile(
    r'\b(?:class action|lawsuit|investigat\w+|deadline reminder'
    r'|notifies investors|law offices|securities fraud|shareholder alert'
    r'|named a leader|magic quadrant|vendor evaluation|wins? award'
    r'|market research report|market size|CAGR|forecast to reach'
    r'|appoint\w+|names? \w+ as (?:its |the )?(?:new )?(?:CEO|CFO|COO|president)'
    r'|joins? (?:the )?board|dividend declar\w+|declares? (?:a )?(?:quarterly )?dividend'
    r'|stock split|public offering|prices? (?:its )?offering)\b', re.I)

# Reported-figure evidence. An actual release states numbers.
_FIG_PATTERNS = [
    # $17.25 billion / $16,825 million / $1.2B
    re.compile(r'\$\s?[\d,]+(?:\.\d+)?\s*(?:billion|million|thousand|[BMK])\b', re.I),
    # $1.22 per diluted share / $(0.45) per share
    re.compile(r'\$\s?\(?\d+(?:\.\d+)?\)?\s*per\s+(?:diluted\s+|basic\s+)?share', re.I),
    # revenue increased 18% / grew 18 percent
    re.compile(r'\b(?:increas\w+|decreas\w+|grew|grow\w+|declin\w+|rose|fell|up|down)\s+'
               r'(?:by\s+)?\d+(?:\.\d+)?\s*(?:%|percent)', re.I),
    re.compile(r'\bnon-?GAAP\b', re.I),
    re.compile(r'\b(?:diluted|basic)\s+(?:net\s+)?(?:income|loss|earnings)\s+per\s+share\b', re.I),
]

# Statement-of-operations markers: near-conclusive evidence of a real release.
_STATEMENT_MARKERS = re.compile(
    r'\b(?:condensed consolidated|consolidated (?:statements?|balance sheets?)'
    r'|statements? of operations|gross margin|operating (?:income|margin|expenses)'
    r'|cost of (?:revenue|sales)|total revenues?)\b', re.I)


def count_financial_figures(text):
    """How many distinct kinds of reported-figure evidence appear."""
    if not text:
        return 0
    return sum(1 for p in _FIG_PATTERNS if p.search(text))


def classify(item):
    """Classify a wire item as an earnings release or not.

    Returns {is_earnings, reason, confidence, figures, scheduling}.
    Pure function, no I/O -- safe on the hot path.
    """
    headline = item.get('headline') or ''
    body = item.get('body') or ''
    teaser = item.get('teaser') or ''
    blob = '\n'.join([headline, teaser, body])

    scheduling = bool(_SCHEDULING.search(headline))
    figures = count_financial_figures(blob)
    has_statement = bool(_STATEMENT_MARKERS.search(blob))

    if _NON_EARNINGS.search(headline):
        return dict(is_earnings=False, reason='non-earnings PR class',
                    confidence=0.0, figures=figures, scheduling=scheduling)

    # A real release CAN say "will host a conference call" alongside its
    # numbers, so scheduling language alone is not disqualifying -- the
    # absence of reported figures alongside it is.
    if scheduling and not has_statement and figures < MIN_FINANCIAL_FIGURES:
        return dict(is_earnings=False,
                    reason='scheduling notice (no reported figures)',
                    confidence=0.0, figures=figures, scheduling=scheduling)

    headline_says_results = bool(
        _REPORT_VERB.search(headline) and _RESULTS_NOUN.search(headline))
    headline_has_period = bool(_PERIOD_RE.search(headline))

    confidence = 0.0
    reasons = []
    if headline_says_results:
        confidence += 0.45
        reasons.append('headline reports results')
    if headline_has_period:
        confidence += 0.15
        reasons.append('fiscal period in headline')
    if has_statement:
        confidence += 0.30
        reasons.append('statement-of-operations markers')
    confidence += min(figures, 4) * 0.05
    if figures:
        reasons.append('%d figure classes' % figures)

    is_earnings = (
        confidence >= 0.60
        and figures >= MIN_FINANCIAL_FIGURES
        and (headline_says_results or has_statement)
    )

    return dict(is_earnings=is_earnings,
                reason=', '.join(reasons) or 'no earnings evidence',
                confidence=round(min(confidence, 1.0), 2),
                figures=figures, scheduling=scheduling)


_INSTRUMENT = re.compile(r'^(?:EQ|OTC|ETF):(?:US|[A-Z]{2}):([A-Z0-9.\-]+)$')

# (NASDAQ: CSCO) / (NYSE American: XYZ) / (Nasdaq Global Select Market: ABCD)
_EXCHANGE_TAG = re.compile(
    r'\(\s*(?:NASDAQ|Nasdaq|NYSE|AMEX|OTCQB|OTCQX|OTC|CBOE|TSX|TSXV)'
    r'[^):]{0,40}?:\s*([A-Z][A-Z0-9.\-]{0,6})\s*\)')

_SYMBOL_PHRASE = re.compile(
    r'(?:ticker\s+symbol|symbol)\s*[:"“]?\s*([A-Z][A-Z0-9.\-]{0,6})\b')

_NAME_SUFFIX = re.compile(
    r'\b(?:inc|corp|corporation|company|co|ltd|limited|plc|holdings?|group|'
    r'technologies|technology|systems|solutions|international|the)\b', re.I)


def extract_tickers(item, watchlist=None):
    """Resolve tickers for a wire item, best source first.

    1. `primary_instruments` -- authoritative when present, often empty.
    2. Exchange-qualified tag in headline or body, e.g. "(NASDAQ: CSCO)".
    3. Company-name match against today's watchlist.

    Returns (tickers, source).
    """
    out, seen = [], set()
    for inst in (item.get('primary_instruments') or []):
        m = _INSTRUMENT.match(inst)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    if out:
        return out, 'primary_instruments'

    blob = '\n'.join([item.get('headline') or '',
                      item.get('teaser') or '',
                      (item.get('body') or '')[:4000]])
    for pat in (_EXCHANGE_TAG, _SYMBOL_PHRASE):
        for m in pat.finditer(blob):
            t = m.group(1).upper()
            if t not in seen:
                seen.add(t)
                out.append(t)
        if out:
            return out, 'exchange tag'

    if watchlist:
        headline = (item.get('headline') or '').lower()
        for ticker, entry in watchlist.items():
            name = (entry.get('company') or '')
            if not name:
                continue
            stem = _NAME_SUFFIX.sub('', name).strip(' ,.').lower()
            if len(stem) >= 4 and stem in headline:
                return [ticker], 'company name'

    return [], 'unresolved'
