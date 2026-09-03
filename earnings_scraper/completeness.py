# -*- coding: utf-8 -*-
"""Is the ingested release COMPLETE? Assert it; never assume it.

★ THE FOUNDING CASE. AVGO's 2026-09-02 release arrived over PRN as 9,498
characters ending in "(MORE TO FOLLOW)" -- a wire continuation marker. The other
five releases in the corpus ran 19,712 / 32,317 / 35,555 / 83,827 / 85,211 and
all terminated naturally. Every financial-statement section was missing:

    CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS   ABSENT
    FINANCIAL RECONCILIATION: GAAP TO NON-GAAP        ABSENT
    CONDENSED CONSOLIDATED BALANCE SHEETS             ABSENT
    CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS   ABSENT

The live card was scored off part 1, and every build measurement taken over
AVGO was measured over part 1 -- including a table-source count of 4 across six
earnings releases, which is not a low number but an impossible one.

★★ DEGRADE LOUDLY, DO NOT REFUSE. Part 1 CONTAINED THE HERO: $16.7B AI semi
revenue, the $21.7B Q4 guide, total revenue, EPS, segment revenue. What was
missing was the appendix. Refusing to card that would cost the trader the most
important number on the print, at 4:15pm, to protect him from an appendix he was
never going to read in ninety seconds.

So: a banner, a distinct non-emission reason, and 'source incomplete' on every
unfilled row -- while every row that DID fill is kept, because it came from text
that was present and is valid.

★ THE AMBIGUITY THIS REMOVES cost four build cycles: a blank from a truncated
ingest and a blank from a parser gap were indistinguishable. Now they are not.
"""

import re

#: wire continuation markers. A body ending in one of these is part 1 of N.
_CONTINUES = re.compile(
    r'\(\s*MORE\s+TO\s+FOLLOW\s*\)\s*$'
    r'|\(\s*MORE\s*\)\s*$'
    r'|\bTO\s+BE\s+CONTINUED\b\s*$'
    r'|/MORE\s*$', re.I)

#: sections an earnings release of any length should carry
_SECTIONS = (
    ('income statement', re.compile(
        r'CONDENSED\s+CONSOLIDATED\s+STATEMENTS?\s+OF\s+OPERATIONS'
        r'|CONSOLIDATED\s+STATEMENTS?\s+OF\s+OPERATIONS'
        r'|STATEMENTS?\s+OF\s+INCOME', re.I)),
    ('balance sheet', re.compile(
        r'CONDENSED\s+CONSOLIDATED\s+BALANCE\s+SHEETS?'
        r'|CONSOLIDATED\s+BALANCE\s+SHEETS?', re.I)),
    ('cash flow', re.compile(
        r'STATEMENTS?\s+OF\s+CASH\s+FLOWS?', re.I)),
    ('GAAP reconciliation', re.compile(
        r'RECONCILIATION[^\n]{0,40}(?:GAAP|NON-?GAAP)'
        r'|GAAP\s+TO\s+NON-?GAAP', re.I)),
)

#: ★ Calibrated on this corpus: complete releases ran 19,712 chars and up; the
#: truncated one ran 9,498. A floor at 15,000 separates them with room on both
#: sides, and it would have caught AVGO on the night.
LENGTH_FLOOR = 15000

#: rows whose value lives in a specific appendix section, so a truncated
#: release can say WHERE to go read rather than only that something is missing
_ROW_SECTION = (
    (re.compile(r'buyback|repurchase|share\s+repurchase', re.I), 'cash flow'),
    (re.compile(r'\bfcf\b|free\s+cash\s+flow|cash\s+from\s+ops'
                r'|operating\s+cash\s+flow', re.I), 'cash flow'),
    (re.compile(r'\bcapex\b|capital\s+expenditure', re.I), 'cash flow'),
    (re.compile(r'\bdividend\b', re.I), 'cash flow'),
    (re.compile(r'shares?\s+outstanding|diluted\s+shares?'
                r'|weighted[-\s]average\s+shares?', re.I), 'income statement'),
    (re.compile(r'\bdebt\b|\bcash\s+(?:and|balance)\b|inventor(?:y|ies)'
                r'|\bgoodwill\b', re.I), 'balance sheet'),
    (re.compile(r'stock[-\s]based\s+compensation|\bsbc\b', re.I),
     'GAAP reconciliation'),
)


def assess(text, is_earnings=True):
    """Completeness of an ingested body.

    Returns dict(complete, truncated, marker, chars, missing, short, reasons).
    `missing` names the absent sections; `short` is the length-floor flag.
    """
    body = text or ''
    tail = body.rstrip()
    m = _CONTINUES.search(tail[-80:]) if tail else None
    missing = [name for name, pat in _SECTIONS if not pat.search(body)]
    short = is_earnings and len(body) < LENGTH_FLOOR

    reasons = []
    if m:
        reasons.append('body ends %r -- a wire continuation marker'
                       % m.group(0).strip())
    if short:
        reasons.append('only %d chars; complete releases in this corpus run '
                       '19,712 and up' % len(body))
    if missing:
        reasons.append('missing section(s): %s' % ', '.join(missing))

    # ★ The MARKER is decisive on its own. The floor and the section check are
    # corroboration -- a genuinely short but complete release should not be
    # condemned by length alone, so it takes two signals without a marker.
    truncated = bool(m) or (short and len(missing) >= 2)
    return dict(complete=not truncated, truncated=truncated,
                marker=(m.group(0).strip() if m else None),
                chars=len(body), missing=missing, short=short,
                reasons=reasons)


def banner(state):
    """The lines that go at the VERY TOP of a card, above the hero table."""
    if not state or not state.get('truncated'):
        return []
    out = ['⛔ SOURCE INCOMPLETE — %d chars%s.'
           % (state['chars'],
              (', ends %r' % state['marker']) if state.get('marker') else '')]
    if state.get('missing'):
        out.append('   MISSING: %s.' % ', '.join(state['missing']))
        out.append('   Rows sourced from those sections CANNOT fill — a '
                   'blank below means the')
        out.append('   TEXT was absent, not that the parser failed.')
    return out


def row_reason(row_name, state):
    """The ungradedReason for an unfilled row on a truncated source.

    ★ Names the SECTION when the row's value is known to live in one, so the
    banner becomes a checklist of what to read by hand. AVGO's buyback lives in
    the cash-flow statement, and 'value is in the missing cash flow section'
    beats 'source incomplete'.
    """
    if not state or not state.get('truncated'):
        return None
    missing = set(state.get('missing') or ())
    for pat, section in _ROW_SECTION:
        if pat.search(row_name or '') and section in missing:
            return ('source incomplete: this value lives in the %s, which is '
                    'not in the ingested text' % section)
    return 'source incomplete: the release was truncated before scoring'


#: reasons that mean "the number was not there" and nothing more. Only these
#: are worth replacing with a truncation explanation.
_ABSENCE = re.compile(r'not\s+found\s+in\s+release|no\s+candidate'
                      r'|not\s+found\b|not\s+in\s+the\s+release', re.I)

#: reasons that stand on their own merit. A forward-period slot, a text
#: consensus, a period mismatch and a scale refusal all describe a blank that
#: would still be blank on a COMPLETE release.
_STRUCTURAL = re.compile(r'forward-period|consensus\s+is\s+text'
                         r'|grade\s+manually|period\s+mismatch|qualified'
                         r'|scale:|unit|duplicate|basis|modifier|zero', re.I)


def reason_is_absence(reason):
    """Is this ungradedReason worth replacing with a truncation explanation?

    ★ Replace only the reasons that say nothing beyond "absent". Anything that
    already names a STRUCTURAL cause is more informative than the truncation
    banner and is left exactly as the parser wrote it.
    """
    if not reason:
        return True
    if _STRUCTURAL.search(reason):
        return False
    return bool(_ABSENCE.search(reason))
