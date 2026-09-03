# -*- coding: utf-8 -*-
"""KEY 1 — period classification. Classify BEFORE matching the metric.

★ THE DEFECT THIS EXISTS FOR is the mirror image of non-negotiable 2. That rule
forbids filling a FORWARD slot from reported actuals. What the scraper was doing
is the opposite: filling a CURRENT slot from forward guidance.

    HPE  [15] Q3 Adjusted Operating Margin  took 14    -> the FY27 framework
    SNOW  [8] Non-GAAP Operating Margin     took 15.5  -> the Q3 GUIDE

Both rendered a confident verdict. Same defect, opposite direction.

★ THE MATCHED SPAN IS NOT ENOUGH, and this is the load-bearing lesson. HPE's
value arrives with raw = "non-GAAP operating margin rate to be in the range of
14%" -- "to be in the range of" is right there. But SNOW's arrives as
"Non-GAAP operating margin2 of 15.5%", which carries NO period marker at all.
Its period lives in the ENCLOSING SENTENCE:

    "For the third quarter of fiscal 2027, the company expects: ... non-GAAP
     operating margin2 of 15.5%"

So a classifier fed the matched span alone gets SNOW wrong, exactly as the
earlier `m.group(0)` guards did nothing because a trailing "is expected" never
appears inside the span. Classification must see the clause that GOVERNS the
number, which is why classify_candidate takes the sentence.

★ UNRESOLVED NEVER FILLS. That is the whole point: when the period cannot be
established, a blank with a reason beats a coin flip with a colour on it.
"""

import re

REPORTED = 'REPORTED'
GUIDE_NEXT_Q = 'GUIDE_NEXT_Q'
GUIDE_FY = 'GUIDE_FY'
PRIOR_PERIOD = 'PRIOR_PERIOD'
UNRESOLVED = 'UNRESOLVED'

#: what _classify_period() calls a ROW maps onto these classes 1:1
ROW_CLASS = {
    'CURRENT_Q': REPORTED,
    'NEXTQ_GUIDE': GUIDE_NEXT_Q,
    'FY_GUIDE': GUIDE_FY,
}

# ── the vocabularies ───────────────────────────────────────────────────────
#
# Order of testing matters and is asserted by the tests: a fragment can carry
# several markers, and the MOST SPECIFIC wins. "For the full year we expect"
# is GUIDE_FY, not GUIDE_NEXT_Q, even though "we expect" appears in both.

#: forward intent -- the number has not happened yet
_FORWARD = re.compile(
    r'\bexpect\w*|\bguidance\b|\bguide\b|\boutlook\b|\bforecast\w*'
    r'|\bto\s+be\s+in\s+the\s+range\b|\bwe\s+see\b|\banticipat\w*'
    r'|\btarget\w*|\bframework\b|\bwill\s+be\b|\bprojec\w*'
    r'|\bassum\w*', re.I)

#: full-year / multi-year scope
_FY_SCOPE = re.compile(
    r'\bfull[-\s]year\b|\bfull\s+fiscal\b|\bfiscal\s+year\b|\bFY\s?\d{2,4}\b'
    r'|\bfor\s+(?:the\s+)?(?:full|entire)\b|\bannual\b'
    r'|\blong[-\s]term\b|\bmulti[-\s]year\b', re.I)

#: an explicit prior-period comparison -- never fills, comparison only
_PRIOR = re.compile(
    r'\bcompared\s+(?:to|with)\b|\bup\s+from\b|\bdown\s+from\b'
    r'|\bversus\s+(?:the\s+)?prior\b|\bvs\.?\s+(?:the\s+)?prior\b'
    r'|\bprior[-\s]year\b|\byear[-\s]ago\b|\ba\s+year\s+earlier\b'
    r'|\bin\s+the\s+same\s+(?:period|quarter)\b', re.I)

#: reported intent -- the number has happened
_REPORTED = re.compile(
    r'\bfor\s+the\s+(?:first|second|third|fourth)\s+quarter\b'
    r'|\bin\s+the\s+quarter\b|\bfor\s+the\s+quarter\b'
    r'|\bwas\b|\bwere\b|\breported\b|\bdelivered\b|\bgrew\b|\bincreased\s+to\b'
    r'|\bcame\s+in\b|\bof\s+the\s+quarter\b|\bthis\s+quarter\b'
    r'|\bQ[1-4]\s+\w+\s+(?:revenue|margin|income|EPS)\b', re.I)

# ★ REMOVED: r'\bof\s+\$?\d' as reported intent.
#
# It was added for HPE's verbless bullet style ("Non-GAAP(1) of 16.2%") and it
# DEFEATED THE REGISTER. SNOW's guide value arrives as the bare span "Non-GAAP
# operating margin2 of 15.5%", which the rule read as REPORTED -- and because
# an inline marker outranks the register (precedence level 1), it beat the
# "For the third quarter of fiscal 2027, the company expects:" header that
# actually governs it. The guide value then filled a reported slot and graded
# DEMOLISH.
#
# A WEAK INLINE RULE IS WORSE THAN NO INLINE RULE: it outranks the structure
# that does know the answer. "of 15.5%" states a value, not a period. The
# verbless bullets resolve from the register instead -- HPE's 16.2% at offset
# 1521 sits under "Third Quarter Fiscal 2026 Financial Results" at 1048 and
# classifies REPORTED without any inline help.


#: the first numeric token in a fragment -- used ONLY to order a marker
#: against the number it might govern
_FIRST_NUMBER = re.compile(r'\(?\$?\s?\d[\d,]*(?:\.\d+)?')


def classify_candidate(fragment, quarter=None):
    """The period a candidate value belongs to, from the clause GOVERNING it.

    `fragment` must be the enclosing sentence or bullet, NOT the matched span.
    See the module docstring: SNOW's guide value carries no marker inside its
    own span.
    """
    f = ' '.join((fragment or '').split())
    if not f:
        return UNRESOLVED

    forward = bool(_FORWARD.search(f))
    fy = bool(_FY_SCOPE.search(f))

    # ★ A TRAILING COMPARISON DOES NOT MAKE THE NUMBER A COMPARISON, and this
    # is positional, exactly like _forward_governs in parse.py: a marker only
    # governs a number it PRECEDES.
    #
    #   "compared to 7.0% for the prior-year period"        marker first -> PRIOR
    #   "of 16.2%, up 770 bps from the prior-year period"   number first -> not
    #
    # Nearly every reported figure carries a YoY clause, so an eager rule here
    # would misclassify most of them and blank the column it protects.
    if not forward:
        pm = _PRIOR.search(f)
        if pm:
            num = _FIRST_NUMBER.search(f)
            marker_leads = (num is None) or (pm.start() < num.start())
            if marker_leads:
                return PRIOR_PERIOD

    if forward:
        # ★ MOST SPECIFIC WINS. "for the full year we expect" carries both
        # markers; the full-year scope is the more specific claim.
        return GUIDE_FY if fy else GUIDE_NEXT_Q

    if _REPORTED.search(f):
        return REPORTED

    # A bare table cell with no prose around it. Refusing here is deliberate:
    # a value whose period cannot be established is the SNOW defect.
    return UNRESOLVED


def row_class(row_period):
    """Map a ROW's period (from _classify_period) onto a candidate class."""
    return ROW_CLASS.get(row_period, UNRESOLVED)


def may_fill(row_period, candidate_class):
    """True only on an EXACT class match. UNRESOLVED never fills, either side.

    ★ Deliberately not permissive. The alternative -- 'fill unless we are sure
    it is wrong' -- is what put a Q3 guide into a reported margin slot and
    graded it green.
    """
    want = row_class(row_period)
    if want == UNRESOLVED or candidate_class == UNRESOLVED:
        return False
    if candidate_class == PRIOR_PERIOD:
        return False
    return want == candidate_class


def refusal_note(row_period, candidate_class):
    """Why a candidate may not fill this row."""
    want = row_class(row_period)
    if candidate_class == PRIOR_PERIOD:
        return ('period: the value is a PRIOR-PERIOD comparison, which never '
                'fills a slot')
    if candidate_class == UNRESOLVED:
        return ('period: could not establish whether the value is reported or '
                'guided, so it is not written')
    if want == UNRESOLVED:
        return ('period: the row name does not declare a period this build '
                'can classify')
    return ('period mismatch: found %s, row wants %s'
            % (candidate_class, want))

# ══ THE PERIOD SCOPE REGISTER ══════════════════════════════════════════════
#
# Scope markers, tested in this order. The FIRST match on a line wins, and the
# ordering is deliberate: a full-year phrase must be tested before the
# quarter phrase it contains ("full year fiscal 2027" also matches "fiscal
# 2027").

_ORD = r'(?:first|second|third|fourth|1st|2nd|3rd|4th|Q[1-4]|[1-4]Q)'

_SCOPE_MARKERS = (
    # ── full-year guidance, tested FIRST ──────────────────────────────────
    (GUIDE_FY, r'for\s+the\s+full[-\s]?year(?:\s+of)?\s+fiscal'),
    (GUIDE_FY, r'full[-\s]?year\s+fiscal\s+\d{2,4}\s+outlook'),
    (GUIDE_FY, r'fiscal\s+\d{2,4}\s+full[-\s]?year\s+outlook'),
    (GUIDE_FY, r'fiscal\s+\d{2,4}\s+outlook\s+framework'),
    (GUIDE_FY, r'\bFY\s?\d{2,4}\s+outlook'),
    (GUIDE_FY, r'full[-\s]?year\s+(?:guidance|outlook|framework)'),
    (GUIDE_FY, r'for\s+(?:the\s+)?full\s+fiscal\s+year'),
    (GUIDE_FY, r'for\s+the\s+full\s+year,?\s+(?:we|the\s+company)\s+expect'),

    # ── next-quarter guidance ─────────────────────────────────────────────
    (GUIDE_NEXT_Q,
     r'for\s+the\s+' + _ORD + r'\s+quarter\s+of\s+fiscal[^.]{0,40}'
     r'(?:we|the\s+company)\s+expect'),
    (GUIDE_NEXT_Q, r'for\s+the\s+' + _ORD + r'\s+quarter[^.]{0,30}expect'),
    (GUIDE_NEXT_Q, r'the\s+outlook\s+for\s+the\s+' + _ORD + r'\s+quarter'),
    (GUIDE_NEXT_Q, r'fiscal\s+\d{2,4}\s+' + _ORD + r'\s+quarter\s+outlook'),
    (GUIDE_NEXT_Q, _ORD + r'\s+quarter\s+fiscal\s+\d{2,4}\s+outlook'),
    (GUIDE_NEXT_Q, r'\b' + _ORD + r'\s+quarter\s+(?:guidance|outlook)\b'),
    (GUIDE_NEXT_Q, r'\bguidance\s+for\s+the\s+' + _ORD + r'\s+quarter'),

    # ── reported results ──────────────────────────────────────────────────
    (REPORTED,
     _ORD + r'\s+quarter\s+fiscal(?:\s+year)?\s+\d{2,4}\s+'
     r'(?:financial\s+)?(?:results|highlights)'),
    (REPORTED,
     r'fiscal(?:\s+year)?\s+\d{2,4}\s+' + _ORD + r'\s+quarter\s+'
     r'(?:financial\s+)?(?:results|highlights)'),
    (REPORTED, r'\b' + _ORD + r'\s+quarter\s+(?:financial\s+)?results\b'),
    (REPORTED, r'results\s+for\s+the\s+' + _ORD + r'\s+quarter'),
    (REPORTED, r'\b(?:financial\s+)?highlights\b'),
)

_SCOPE_COMPILED = tuple((cls, re.compile(pat, re.I)) for cls, pat in
                        _SCOPE_MARKERS)

#: a table column header naming the reported period
_COL_REPORTED = re.compile(
    r'\b(?:three|six|nine|twelve)\s+months\s+ended\b', re.I)


def scope_marker(line):
    """The period scope a LINE establishes for what follows, or None.

    Only the FIRST match matters: a line is one scope statement, and testing
    full-year before quarter keeps "full year fiscal 2027" out of the
    quarter bucket.
    """
    text = ' '.join((line or '').split())
    if not text:
        return None
    for cls, pat in _SCOPE_COMPILED:
        if pat.search(text):
            return cls
    return None


def build_register(text):
    """[(offset, period)] for every scope marker, in DOCUMENT ORDER.

    ★ Structural, not proximity-based. A window wide enough to reach SNOW's
    list header would be wide enough to reach the WRONG header on the next
    release.
    """
    reg = []
    offset = 0
    for line in (text or '').splitlines():
        cls = scope_marker(line)
        if cls:
            reg.append((offset, cls))
        offset += len(line) + 1
    return reg


def period_at(register, offset):
    """The scope in force at `offset` -- the nearest PRECEDING marker."""
    current = UNRESOLVED
    for off, cls in register or ():
        if off > offset:
            break
        current = cls
    return current


def classify_at(text, offset, fragment=None, register=None,
                column_class=None):
    """The period of a candidate at `offset`, by the four-level precedence.

    Returns (period, source) so a refusal can say WHERE the period came from --
    'inline' / 'column' / 'register' / 'unresolved'.
    """
    # 1. an inline marker inside the candidate's own clause
    if fragment:
        inline = classify_candidate(fragment)
        if inline != UNRESOLVED:
            return inline, 'inline'

    # 2. a table column header
    if column_class:
        return column_class, 'column'

    # 3. the register
    if register is None:
        register = build_register(text)
    cls = period_at(register, offset)
    if cls != UNRESOLVED:
        return cls, 'register'

    # 4. never fills
    return UNRESOLVED, 'unresolved'

# ══ LEVEL 2 — COLUMN HEADERS ═══════════════════════════════════════════════
#
# ★ A period LABEL is not a period STATEMENT. classify_candidate() looks for a
# verb or an expectation; 'Q3 26' has neither, so every column header comes
# back UNRESOLVED. Level 2 therefore compares labels to the record's own
# quarter rather than classifying them as prose.

#: 'Q3 26', 'Q3 FY26', '3Q26', 'Q3 2026'
_Q_LABEL = re.compile(r'\b(?:Q([1-4])\s?(?:FY)?\s?(\d{2,4})'
                      r'|([1-4])Q\s?(?:FY)?\s?(\d{2,4}))\b', re.I)
#: 'Three Months Ended August 2, 2026'
_MONTHS_ENDED = re.compile(
    r'\b(three|six|nine|twelve)\s+months\s+ended\b[^|]{0,30}?(\d{4})', re.I)
#: a change/variance column -- never a period
_CHANGE_COL = re.compile(r'\bchange\b|\bvariance\b|\bvs\b|\bgrowth\b|%', re.I)


def _norm_year(y):
    y = int(y)
    return y + 2000 if y < 100 else y


def parse_period_label(label):
    """(quarter, year) from a column header, or None.

    Returns quarter=None for a 'months ended' header, which names a year and a
    span rather than a fiscal quarter.
    """
    t = ' '.join((label or '').split())
    if not t:
        return None
    m = _Q_LABEL.search(t)
    if m:
        q = m.group(1) or m.group(3)
        y = m.group(2) or m.group(4)
        return int(q), _norm_year(y)
    m = _MONTHS_ENDED.search(t)
    if m:
        return None, _norm_year(m.group(2))
    return None


def column_classes(header, record_quarter=None, record_year=None):
    """[period class] per column, left to right, from a header line.

    ★ Classified by RELATION to the record's own period:
        same quarter AND year   -> REPORTED
        anything earlier        -> PRIOR_PERIOD
        a change/variance col   -> None (not a period at all)
        unparseable             -> UNRESOLVED, which never fills
    """
    out = []
    for cell in _split_header(header):
        if _CHANGE_COL.search(cell) and not _Q_LABEL.search(cell):
            out.append(None)
            continue
        got = parse_period_label(cell)
        if got is None:
            out.append(UNRESOLVED)
            continue
        q, y = got
        if record_year is None:
            out.append(UNRESOLVED)
            continue
        if y < record_year:
            out.append(PRIOR_PERIOD)
        elif y > record_year:
            out.append(GUIDE_NEXT_Q)
        elif q is None or record_quarter is None:
            out.append(REPORTED)
        elif q < record_quarter:
            out.append(PRIOR_PERIOD)
        elif q > record_quarter:
            out.append(GUIDE_NEXT_Q)
        else:
            out.append(REPORTED)
    return out


def _split_header(header):
    """Header cells, in order. Splits on 2+ spaces, then on period tokens.

    AVGO collapses its header to 'data) Q3 26 Q3 25 Change Q3 26 Q3 25 Change'
    with single spaces, so a whitespace split alone yields nothing usable --
    the period tokens themselves are the delimiters.
    """
    t = ' '.join((header or '').split())
    if not t:
        return []
    cells, last = [], 0
    marks = [(m.start(), m.end()) for m in _Q_LABEL.finditer(t)]
    if not marks:
        return [c for c in re.split(r'\s{2,}', t) if c.strip()]
    for a, z in marks:
        cells.append(t[a:z])
        # anything between this label and the next that looks like a change
        # column counts as its own cell
        last = z
        nxt = t.find(' ', z)
        if nxt != -1:
            gap = t[z:t.find('Q', z) if t.find('Q', z) > z else len(t)]
            if _CHANGE_COL.search(gap):
                cells.append(gap.strip())
    return [c for c in cells if c.strip()]
