"""Release zones: PROSE, INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW.

★ THE POLICY EXISTED; THE CODE DID NOT.
CLAUDE.md's do-not-automate list already forbids sourcing a graded figure from
"the cash-flow statement or balance sheet" -- founding case SNDK's $93.9B
backlog, a figure that is real, correctly parsed, and the wrong definition for
the row it would have filled. The parser had no zone concept, so the policy was
unenforced: a balance-sheet blob is exactly where a correct-LOOKING number of
the wrong definition comes from.

★ WHY THE INCOME STATEMENT IS A SEPARATE ZONE, NOT LUMPED IN
Refusing every statement region would break the table path entirely. APP-2026Q2
states its figures ONLY in tables -- prose extraction returns nothing from it --
and its revenue and adjusted EBITDA come off the statements of operations. That
is the income statement's own line items, which is where the graded metrics
legitimately live. The rule is about the BALANCE SHEET and the CASH-FLOW
STATEMENT, where a figure with a similar name means something else entirely.

So three statement zones, not one, and only two of them are refused.

★ DENSITY MATTERS, NOT SIZE. SNDK's longest unpunctuated block is 13,216 chars
and holds ZERO figures -- an inert legal table. APP's 9,621-char block holds 12.
Refusing by block length would have refused the wrong things.
"""

import re

PROSE = 'prose'
INCOME_STATEMENT = 'incomeStatement'
BALANCE_SHEET = 'balanceSheet'
CASH_FLOW = 'cashFlow'
EQUITY = 'equity'

#: zones a graded actual may NOT be sourced from
REFUSED = frozenset((BALANCE_SHEET, CASH_FLOW, EQUITY))

_HEADERS = (
    (BALANCE_SHEET, re.compile(
        r'(?:condensed\s+)?consolidated\s+balance\s+sheets?', re.I)),
    (CASH_FLOW, re.compile(
        r'(?:condensed\s+)?consolidated\s+statements?\s+of\s+cash\s+flows?',
        re.I)),
    (EQUITY, re.compile(
        r'(?:condensed\s+)?consolidated\s+statements?\s+of\s+'
        r'(?:stockholders|shareholders)', re.I)),
    (INCOME_STATEMENT, re.compile(
        r'(?:condensed\s+)?consolidated\s+statements?\s+of\s+'
        r'(?:operations|income|comprehensive)', re.I)),
)


def zone_spans(text):
    """[(start, end, zone)] covering `text`, in order.

    A header opens a zone that runs until the next header. Everything before the
    first header is PROSE -- which is where a release states its narrative and
    its guidance, and where the graded figures are supposed to come from.
    """
    marks = []
    for zone, pat in _HEADERS:
        for m in pat.finditer(text or ''):
            marks.append((m.start(), zone))
    marks.sort()
    spans, pos, cur = [], 0, PROSE
    for start, zone in marks:
        if start > pos:
            spans.append((pos, start, cur))
        pos, cur = start, zone
    spans.append((pos, len(text or ''), cur))
    return spans


def zone_at(text, offset, spans=None):
    """Which zone `offset` falls in."""
    for start, end, zone in (spans or zone_spans(text)):
        if start <= offset < end:
            return zone
    return PROSE


def is_refused_zone(text, offset, spans=None):
    """True when a graded actual must NOT be sourced from this offset."""
    return zone_at(text, offset, spans) in REFUSED


def refusal_note(zone):
    return (
        '⛔ the figure at this position sits in the %s, which '
        'CLAUDE.md\'s do-not-automate list forbids as a source for a graded '
        'actual. Founding case: SNDK\'s $93.9B backlog -- real, correctly '
        'parsed, and the wrong definition for the row.'
        % {BALANCE_SHEET: 'CONSOLIDATED BALANCE SHEET',
           CASH_FLOW: 'CONSOLIDATED STATEMENT OF CASH FLOWS',
           EQUITY: 'STATEMENT OF STOCKHOLDERS EQUITY'}.get(zone, zone))


def summarise(text):
    """Zone sizes and figure counts -- the measurement behind the policy."""
    num = re.compile(r'\$\s?[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?\s*%')
    out = {}
    for start, end, zone in zone_spans(text):
        chunk = (text or '')[start:end]
        agg = out.setdefault(zone, dict(chars=0, figures=0, spans=0))
        agg['chars'] += len(chunk)
        agg['figures'] += len(num.findall(chunk))
        agg['spans'] += 1
    return out
