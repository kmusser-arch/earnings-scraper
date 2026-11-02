# -*- coding: utf-8 -*-
r"""VERBATIM SOURCE TEXT. Nothing here parses a number.

★★★★ AN UNINTERPRETED STRING CANNOT BE A WRONG VALUE. That is the whole
reason this module exists and the whole reason it is shippable hours
before a print. Every other route to Palantir's guidance has to decide
what a number MEANS -- which period it belongs to, which basis, which
end of a range -- and each of those decisions is a place to be wrong.
Copying the sentence out makes none of them.

The concrete case: one 'Outlook' section stamps a single period across
both the Q and the FY bullets, so a parsed read returns the ~$8.5B FULL
YEAR guide labelled nextQGuidance -- into a Q4 slot whose bogey is
$2.56B. Printing the block verbatim carries the same information and
cannot make that mistake.

★★ SLICING, NOT UNDERSTANDING. Every function below finds a start line
and an end line and returns what is between them, unchanged. If a fence
picks the wrong lines the result is a visibly odd quotation of the
release, not a number anyone would trade. That asymmetry is why the
heuristics here are allowed to be simple.
"""

import re

#: EDGAR prefixes every exhibit with its own filing furniture -- the form
#: type, a sequence number, the filename, 'Document'. The headline is the
#: first real line after it.
_EXHIBIT = re.compile(r'(?i)^\s*exhibit\s+\d+(\.\d+)?\s*$')

#: a press release dateline closes the headline: 'MIAMI - (BUSINESS WIRE)
#: - ...', 'CUPERTINO, CALIFORNIA - Apple ...', or a bare date on its own
#: line. Anchored on the CAPITALISED PLACE so a headline containing a dash
#: does not end itself.
_DATELINE = re.compile(
    r'(?u)^\s*(?:[A-Z][A-Z\s.,&-]{2,40}\s*[—–-]\s*'
    r'|\d{1,2}/\d{1,2}/\d{2,4}\s*$'
    r'|(?:January|February|March|April|May|June|July|August|September'
    r'|October|November|December)\s+\d{1,2},?\s+\d{4}\s*$)')

_BULLET = re.compile(r'^\s*[•◦▪·*\-–—]\s*')

#: headings that open a block we quote whole
_OUTLOOK = re.compile(r'(?i)^\s*(outlook|business outlook|financial '
                      r'guidance|guidance)\s*:?\s*$')
_HIGHLIGHTS = re.compile(r'(?i)^\s*(.{0,30}?highlights)\s*:?\s*$')


def _lines(text):
    return [ln.rstrip() for ln in (text or '').splitlines()]


def headline(text):
    """The release title, verbatim. [] if the document has no exhibit mark.

    ★ CHECKED BEFORE IT WAS WRITTEN: the headline DOES survive into the
    parser's input on both of tonight's documents, sitting immediately
    after 'Exhibit 99.1'. It matters because Palantir puts four of its
    five decisive numbers in the title, as percentages, in a fixed
    grammar -- US comm growth, total growth, and both raised guides.
    """
    ls = _lines(text)
    start = None
    for i, ln in enumerate(ls[:80]):
        if _EXHIBIT.match(ln):
            start = i + 1
    if start is None:
        return []
    # ★ THE DATELINE IS THE ONLY TERMINATOR. Breaking on the first blank
    # line cost Apple its two subheads -- 'September quarter records for
    # total company revenue, iPhone revenue and EPS' and 'Services revenue
    # reaches new all-time high' -- because EDGAR puts a blank between
    # every one. Those subheads are the company's own framing of the
    # print, which is exactly what a headline block is for.
    out = []
    for ln in ls[start:start + 16]:
        s = ln.strip()
        if not s:
            continue
        if _DATELINE.match(s):
            break
        out.append(s)
        if len(out) >= 4:
            break
    return out


def _block(text, pattern, limit=40):
    """Lines from a matching heading to the end of its bulleted body."""
    ls = _lines(text)
    for i, ln in enumerate(ls):
        m = pattern.match(ln.strip())
        if not m:
            continue
        out, blanks = [ln.strip()], 0
        for nxt in ls[i + 1:i + 1 + limit]:
            s = nxt.strip()
            if not s:
                blanks += 1
                # ★ A SINGLE BLANK IS LAYOUT, NOT THE END. EDGAR puts an
                # empty line between every bullet; stopping on the first
                # one returns a heading and nothing else.
                if blanks >= 6 and len(out) > 1:
                    break
                continue
            blanks = 0
            # a bullet, or the 'For Q3 2026, we expect:' lead-in that
            # introduces one, continues the block
            if _BULLET.match(nxt) or s.lower().startswith('for ') \
                    or s.endswith(':'):
                out.append(s)
                continue
            break
        return out if len(out) > 1 else []
    return []


def outlook(text):
    """The guidance block, verbatim. NOT parsed into periods or ranges."""
    return _block(text, _OUTLOOK)


def highlights(text):
    """The '<Quarter> Highlights' bullets, verbatim.

    Where US commercial revenue actually lives on this ticker -- narrated,
    never tabled, which is why the documentLabelMapSegments entry for
    'U.S. commercial revenue' has nothing to bind to.
    """
    return _block(text, _HIGHLIGHTS, limit=60)


#: sentences worth quoting whole because the FIGURE EXISTS ONLY IN PROSE.
#: Apple's gross margin percentage is nowhere in its tables -- the table
#: row called 'Gross margin' is a DOLLAR line -- and the tariff adjustment
#: beside it is not a number any parser should be deriving.
_PROSE_FIGURE = re.compile(
    r'(?i)\b(gross margin was|gross margin of|earnings per share was'
    r'|diluted earnings per share was)\b')


def prose_figures(text, limit=3):
    """Sentences that carry a figure published ONLY as prose."""
    flat = re.sub(r'\s+', ' ', text or '')
    # ★★ A DECIMAL POINT IS NOT A FULL STOP. Splitting on a bare '.' cut
    # Apple's sentence at 'Diluted earnings per share was $1.' -- throwing
    # away the figure the block exists to show. A sentence ends with a
    # period that is NOT between two digits and is followed by space.
    ends = [m.start() for m in re.finditer(r'(?<!\d)\.(?=\s|$)', flat)]
    out = []
    for m in _PROSE_FIGURE.finditer(flat):
        before = [e for e in ends if e < m.start()]
        a = (before[-1] + 1) if before else max(0, m.start() - 200)
        after = [e for e in ends if e >= m.end()]
        b = after[0] if after else -1
        s = flat[a:(b + 1) if b > 0 else min(len(flat), m.end() + 240)].strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def blocks(text):
    """[(title, [lines])] -- every passthrough block this document offers.

    A block that is not present is simply absent. An empty section would
    claim the release had a heading it does not have.
    """
    out = []
    for title, got in (('HEADLINE', headline(text)),
                       ('HIGHLIGHTS', highlights(text)),
                       ('OUTLOOK', outlook(text)),
                       ('PROSE-ONLY FIGURES', prose_figures(text))):
        if got:
            out.append((title, got))
    return out
