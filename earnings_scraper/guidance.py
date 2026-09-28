# -*- coding: utf-8 -*-
"""THE GUIDE SECTION — what globalDocumentLabelMap was missing.

★★★★ FOR A GUIDE ROW THE METRIC LABEL IS USUALLY IDENTICAL TO THE REPORTED
ONE. 'Revenue' is 'Revenue' in the highlights and in the outlook. What makes
one of them a GUIDE is THE SECTION IT SITS IN, and the map carried every
metric name and never carried the sections.

So this reads four blocks the card author wrote and turns them into the
fields a spec needs:

    sectionAnchor  from guidanceSectionAnchors, matched AS A HEADING
    period         from the heading itself, GUIDE_FY / GUIDE_NEXT_Q /
                   UNRESOLVED -- and UNRESOLVED MAY RANK, NEVER EXCLUDE
    rangeForm      from guidanceRangeForms
    direction      from directionVerbs

★★★ THE DIRECTION VERB IS A SCORECARD INPUT, NOT A LOCATOR. FY guidance is
scored raised / maintained / cut, which is 30% of the weight, so the verb is
captured alongside the figure rather than used to find it and discarded.

★★ AND THE ASYMMETRIC FORMS ARE NOT BANDS. 'at least $3.75 billion' has a
LOW and no HIGH; grading it as a point understates every beat above it. 'up
to X' has a HIGH and no LOW, and a volunteered ceiling is bearish
information in itself. Neither gets an invented other end.

★ THE SPAN CLOSES AT THE NEXT HEADING, never by a length, and the anchor
matches as a HEADING rather than as a substring of prose -- 'Outlook' occurs
inside sentences in every release ever written.
"""

import re

from . import extract
from . import period as period_mod
from . import spans as spans_mod

#: ★ THE PRECEDENCE ALREADY EXISTS. period.py has carried _QUARTER_SCOPE and
#: _WHOLE_YEAR since the classifier was built, and _WHOLE_YEAR is
#: deliberately 'full year / full fiscal / annual' and NOT a bare 'fiscal
#: year' -- because in 'Fourth Quarter Fiscal Year 2026 Business Outlook' the
#: year QUALIFIES the quarter rather than competing with it. A second pair
#: written here would have made that heading UNRESOLVED and split one
#: condition across two rules. WAS THIS FACT EVER COMPUTED ANYWHERE IN THE
#: CALL PATH? It was.
_QUARTER_WORD = period_mod._QUARTER_SCOPE
_YEAR_WORD = period_mod._WHOLE_YEAR

GUIDE_FY = 'GUIDE_FY'
GUIDE_NEXT_Q = 'GUIDE_NEXT_Q'
UNRESOLVED = 'UNRESOLVED'


def heading_period(heading):
    """GUIDE_FY | GUIDE_NEXT_Q | UNRESOLVED for a guidance heading.

    ★ NEITHER, OR BOTH, IS UNRESOLVED. Do not guess: an inferred period may
    RANK, never EXCLUDE, and a heading naming both a quarter and a year is
    exactly the case where guessing costs a row.
    """
    t = heading or ''
    q = bool(_QUARTER_WORD.search(t))
    y = bool(_YEAR_WORD.search(t))
    if q and not y:
        return GUIDE_NEXT_Q
    if y and not q:
        return GUIDE_FY
    return UNRESOLVED


def _norm(s):
    return ' '.join((s or '').split()).lower().rstrip(':').strip()


def guide_sections(text, anchors):
    """[(heading, start, end, period)] for every guidance section.

    Matched AS A HEADING -- blank-line adjacent, not a bullet, no figure --
    because 'Outlook' appears inside prose in every release ever written.
    Closed at the NEXT heading.
    """
    lines = (text or '').split(chr(10))
    offs, run = [], 0
    for ln in lines:
        offs.append(run)
        run += len(ln) + 1
    wanted = {_norm(a) for a in (anchors or []) if a}
    out = []
    for i, ln in enumerate(lines):
        if not extract.is_section_heading(lines, i):
            continue
        norm = _norm(ln)
        # an exact heading, or a patterned one that ENDS in a listed anchor
        # ('Third Quarter Fiscal 2027 Guidance' ends in 'guidance')
        hit = norm in wanted or any(
            norm.endswith(' ' + w) for w in wanted if ' ' not in w)
        if not hit:
            continue
        # ★★★ AN EMPTY SPAN IS NOT A SECTION. DELL stacks its guidance
        # headings -- 'Guidance Summary', then 'Third-Quarter Guidance',
        # then 'Full-Year Guidance' -- so closing at the VERY NEXT heading
        # produced spans of 18, 49, 51 and 75 characters: the heading and
        # nothing else. Four guide rows then refused for want of a value
        # that was never inside the fence. A close must close AFTER the
        # content, so consecutive headings are skipped until one follows
        # something.
        end, closer = len(text or ''), None
        seen_content = False
        for j in range(i + 1, len(lines)):
            if extract.is_section_heading(lines, j):
                if seen_content:
                    end, closer = offs[j], lines[j].strip()
                    break
                continue
            if lines[j].strip():
                seen_content = True
        # ★ THE SPAN KNOWS HOW IT WAS CLOSED, and says so when it cannot be
        # trusted. Six violations of a-span-needs-a-CLOSE, one of them in
        # this very function.
        sp = spans_mod.Span(offs[i], end,
                            spans_mod.BY_HEADING if closer
                            else spans_mod.BY_DOCUMENT_END, ln.strip())
        spans_mod.check(sp, text, 'guidance.guide_sections')
        out.append((ln.strip(), sp[0], sp[1], heading_period(ln), closer))
    return out


def direction_at(text, pos, verbs, window=400):
    """RAISED | MAINTAINED | CUT | NARROWED | WITHDRAWN before `pos`, or None.

    The qualifier LEADS in guidance prose -- the mirror of currency, which
    trails -- so the governing verb is the LAST one before the figure.
    """
    if not isinstance(pos, int) or not text:
        return None
    lo = max(0, pos - window)
    seg = (text[lo:pos] or '').lower()
    best, best_at = None, -1
    for name, forms in (verbs or {}).items():
        if name.startswith((chr(9733), chr(0x2605))) or not isinstance(
                forms, list):
            continue
        for f in forms:
            f = (f or '').split('...')[0].strip().lower()
            if not f:
                continue
            at = seg.rfind(f)
            if at > best_at:
                best, best_at = name, at
    return best


def specs_for(text, gmap, metric_kind, unit=None):
    """[(spec, heading, period)] -- one candidate guide spec per section.

    Everything comes off the card author's blocks: the section from the
    anchors, the period from the heading, the labels from `metrics`. No
    metric label is invented here, because none is needed.
    """
    g = gmap or {}
    anchors_block = g.get(chr(0x2605) + 'guidanceSectionAnchors') or {}
    anchors = anchors_block.get('anchors') or []
    metrics = (g.get('metrics') or {}).get(metric_kind) or {}
    labels = metrics.get('documentLabels') or []
    if not labels:
        return []
    out = []
    for heading, _lo, _hi, period, closer in guide_sections(text, anchors):
        # ★★★ THE CLOSE TRAVELS WITH THE ANCHOR. guide_sections computes the
        # span and an earlier version passed only the heading NAME, so
        # section_spans re-derived a fence with NO TERMINATOR -- MDB's
        # 716-character guidance section became 3,192 characters running to
        # the end of the document, and every guide row tied on candidates
        # inside it. A SPAN NEEDS A CLOSE, and the close was computed and
        # discarded one line before it was needed.
        # ★★★ A LIST IN A ROUTING FIELD IS AN ORDERED PREFERENCE, NOT A SET
        # OF PERMISSIONS -- and the library has carried
        # whereKindIsAPreferenceOrder: True all along. Declaring all three
        # 'to be safe' selects the FIRST branch and hides which one ran:
        # clip() then applies the prose stop rule and returns an empty
        # window. Breadth in a routing field is not caution.
        #
        # ★★ AND rangeForm IS NOT ASSERTED WHERE NOTHING WAS DETECTED. A
        # declared SEPARATOR sends the row through the range arm, which
        # finds no adjacent pair in a table cell and yields nothing. DELL[16]
        # needed BOTH: one routing kind AND no invented range form. Either
        # alone still refuses -- the access/information pair again.
        base = dict(specState='EXTRACTABLE', documentLabels=list(labels),
                    sectionAnchor=[heading],
                    documentUnit=unit or '$M', storedUnit=unit or '$B')
        if closer:
            base['spanTerminator'] = [closer]
        if period in (GUIDE_FY, GUIDE_NEXT_Q):
            base['period'] = period
        else:
            base['periodHint'] = period
        # ONE SPEC PER ROUTING KIND, IN PREFERENCE ORDER. A refusal then
        # NAMES the branch it tried; breadth hides it.
        for kind in ('TABLE', 'PROSE'):
            out.append((dict(base, whereKind=[kind]), heading, period))
    return out
