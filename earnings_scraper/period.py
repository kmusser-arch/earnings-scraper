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
    r'|\bQ[1-4]\s+\w+\s+(?:revenue|margin|income|EPS)\b'
    # ★ HPE's house style for a reported figure carries NO VERB at all:
    # "Non-GAAP(1) of 16.2%, up 770 basis points". With no forward marker
    # present, "of <number>" is a statement of fact.
    r'|\bof\s+\$?\d', re.I)


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
