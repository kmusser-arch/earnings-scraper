# -*- coding: utf-8 -*-
"""The extraction registry: what to look for, read OFF THE ROW.

★★★ NO RUNTIME NAME MATCHING. The extraction spec lives on
`preEarnings.keyKPIs[i].extraction`, written at pre-earnings build time, so
nothing here has to guess which card row a document label belongs to.

That replaces a six-entry hardcoded `_LABELS` table pointed at seventeen-row
cards, and it removes the 50%-token-overlap binder from the path. The binder
was not merely imprecise -- profile heroes are PERIOD-RELATIVE by design ("FY
capex framework") so they survive the fiscal roll, while library rows are
PERIOD-SPECIFIC ("FY27 Capex ($B)"). Two correct naming systems with nothing
bridging them, and fuzzy matching across that gap produced PERIOD INVERSION:
ADBE's "Current-quarter revenue" nearest-matched the Q4 REVENUE GUIDE row --
a plausible number from a real label, which is non-negotiable 2.

    row.extraction = {
        documentLabels,   the literal strings the issuer prints
        unit,             $B / $M / % / $
        period,           REPORTED / GUIDE_NEXT_Q / GUIDE_FY
        basis,            non-GAAP / GAAP / ...
        where,            table | prose bullet | WRAPPED | RANGE
        disqualify,       context tokens that REJECT a candidate
        extractable,      false -> NOT GRADED BY DESIGN, not a failure
        needsRemap,       true  -> issuer changed disclosure; blank + flag
    }

★★ THE DECOY. globalDocumentLabelMap.metrics.dividendPerShare exists ONLY to
be excluded. ORCL Q1 FY27 printed "the board of directors declared a quarterly
cash dividend of $0.50 per share" and the parser graded it as Adjusted EPS
against a $1.745 street -- a false 🔴 MISS on a line that BEAT by 9.7%. HPE
printed "$0.1425 per share" and took the same hit. Both carry `dividend` and
`declared` within ~70 characters of the number; the real ORCL EPS ("non-GAAP
earnings per share climbed to $1.92") carries neither.
"""

import re

#: confidence MEDIUM means INFERRED, not read off a release. Bind AND FLAG.
MEDIUM_TICKERS = frozenset((
    'AEHR', 'ALAB', 'BE', 'CBRS', 'CIFR', 'CRDO', 'CRWV', 'IREN', 'NBIS',
    'RKLB', 'SPCX'))


def spec_for(row, global_map=None, metric_kind=None):
    """The extraction spec for a card row.

    ★ ROW FIRST, GLOBAL SECOND, NOTHING THIRD. A row with no spec and no
    global fallback returns None and the caller must refuse -- inventing a
    label here would reintroduce the guessing this module removes.
    """
    spec = (row or {}).get('extraction')
    # ★ A SPEC WITH NO LABELS IS STILL A SPEC. specState says whether that is
    # a refusal or a gap; requiring documentLabels here is what collapsed the
    # two into one indistinguishable 'no-spec'.
    if isinstance(spec, dict) and spec:
        return dict(spec, source='row')
    if global_map and metric_kind:
        g = ((global_map.get('metrics') or {}).get(metric_kind) or {})
        if g.get('documentLabels'):
            return dict(g, source='global')
    return None


def status_of(spec):
    """EXTRACTABLE | NOT_EXTRACTABLE | NEEDS_REMAP | no-spec.

    ★★ READ specState. NEVER INFER IT FROM AN EMPTY LABEL LIST. My first
    version treated "has documentLabels" as "has a spec", so a DELIBERATE
    REFUSAL (extractable:false, empty labels) was indistinguishable from an
    OMISSION -- and both reported as 'no-spec'. A refusal that reads as a gap
    invites someone to go fill it.

    ★ NOT_EXTRACTABLE renders NOT GRADED BY DESIGN and is EXCLUDED from
    coverage statistics. Counting it as a miss is what made the blank rate
    read 82% against a denominator that was too large.
    """
    if not spec:
        return 'no-spec'
    st = spec.get('specState')
    if st in ('EXTRACTABLE', 'NOT_EXTRACTABLE', 'NEEDS_REMAP'):
        return st
    # pre-schema rows: fall back, but never invent NOT_EXTRACTABLE
    if spec.get('extractable') is False:
        return 'NOT_EXTRACTABLE'
    if spec.get('needsRemap'):
        return 'NEEDS_REMAP'
    return 'EXTRACTABLE' if spec.get('documentLabels') else 'no-spec'


#: how the value is laid out. ★ READ, NEVER SNIFFED. My first version parsed
#: the human `where` prose for the token 'table', which resolved "dedicated
#: FCF table" and silently failed on "supplemental grid" and "reconciliation"
#: -- it half-worked by accident on 27 of 34 rows. `whereKind` is now an
#: explicit enum LIST and `whereNote` carries the prose.
#:
#: ★★ FOURTH oneConditionTwoNames THIS WEEK: unitAmbiguous/scaleSuspect,
#: highlights/businessHighlights, profile-hero/library-row, where/whereKind.
#: Every one was correct on one side, unreadable on the other, and failed
#: SILENTLY.
WHERE_KINDS = ('TABLE', 'PROSE', 'WRAPPED', 'RANGE', 'HEADLINE')


def where_kind(spec):
    """The declared layout kinds for this row, as a list."""
    w = (spec or {}).get('whereKind')
    if isinstance(w, str):
        w = [w]
    return [k for k in (w or []) if k in WHERE_KINDS] or ['UNKNOWN']


#: ★ MEASURED, NOT PICKED -- and my first draft of this comment asserted a
#: failure mode the sweep then disproved. Swept at 40/60/90/120/200/400 over
#: five candidates in two held releases:
#:
#:   40, 60   MISS the HPE table decoy "Cash dividends declared per share
#:            0.1425" -- the disqualifying words sit just outside
#:   90+      every decoy rejected (ORCL $0.50, HPE $0.1425 prose AND table)
#:            and every real EPS kept (ORCL $1.92, $1.56)
#:   400      still no false rejection
#:
#: So 90 is the measured FLOOR and 400 is the widest verified. The costs are
#: asymmetric: too narrow lets a dividend through as EPS, which is the false
#: 🔴 MISS this exists to kill; too wide blanks a row, which is visible and
#: flagged. That argues above the floor, so 150 -- with the honest caveat
#: that n=5 candidates in 2 releases is a small sample and the number should
#: be re-swept when more artifacts land.
DISQUALIFY_WINDOW = 150


def disqualified(text, pos, spec, window=DISQUALIFY_WINDOW):
    """Does the context around `pos` carry a disqualifying token?

    Returns the offending token, or None.

    ★ THE CONTEXT IS THE EVIDENCE. '$0.50 per share' is a perfectly good EPS
    shape; only the surrounding words say it is a dividend. So the test reads
    the neighbourhood rather than the number.
    """
    toks = (spec or {}).get('disqualify') or []
    if not toks:
        return None
    lo = max(0, pos - window)
    ctx = (text or '')[lo:pos + window].lower()
    for t in toks:
        t = (t or '').strip().lower()
        if t and t in ctx:
            return t
    return None


_NUM = re.compile(r'\(?-?\$?\s?([\d,]+(?:\.\d+)?)\s*(%?)\)?')


#: ★ RULE 2. Anything shorter than this MUST match on word boundaries. 57 of
#: the 342 labels are acronyms -- AWS, RPO, cRPO, ISG, QCT, DRAM, HBM, ASP,
#: InP, GaAs -- and each is safe as \\bAWS\\b and unsafe as a substring.
SHORT_LABEL_CHARS = 6

#: ★ RULE 3. A negation on one side and not the other is a HARD disqualify.
#: This is the AVGO founding case: 'AI semiconductor revenue' must never be
#: filled from 'non-AI semiconductor revenue', and longest-match alone is
#: SILENT there because no longer label is competing.
_NEG = re.compile(r'(?:\bnon-?|\bex-|\bexcluding\s+)\s*$', re.I)


def _label_negated(label):
    return bool(re.match(r'\s*(?:non-?|ex-|excluding\b)', label or '', re.I))


def label_hits(text, spec):
    """Every position where a documentLabel matches, after rules 1-3.

    ★ ALL of them, never the first -- 'first match wins' is the majority path
    in this corpus and it is how ADBE graded GAAP 4.62 against a 6.13
    non-GAAP street with the right value sitting at hit #2.

    Applied in contract order:
      1 NEGATION     context says 'non-X', the label says 'X'  -> reject
      2 WHOLE TOKEN  word boundaries, REQUIRED under 6 chars
      3 LONGEST      a longer label matching the same span owns it
    """
    text = text or ''
    raw = []
    for lab in (spec or {}).get('documentLabels') or []:
        if not lab:
            continue
        # ── RULE 2: word boundaries, always; mandatory for short labels ──
        # ★ A TRAILING FOOTNOTE MARKER IS NOT PART OF THE LABEL.
        # ADBE's targets block prints 'Earnings per share1'; the
        # superscript renders as a digit and the whole-token lookahead
        # refused it. One or two trailing footnote digits, or a *, are
        # allowed -- longer digit runs are still a different token.
        pat = re.compile(
            r'(?<![A-Za-z0-9])%s(?:\d{1,2}|\*)?(?![A-Za-z0-9])'
            % re.escape(lab), re.I)
        lab_neg = _label_negated(lab)
        for m in pat.finditer(text):
            # ── RULE 1: negation asymmetry is a HARD disqualify ──────────
            back = text[max(0, m.start() - 16):m.start()]
            if _NEG.search(back) and not lab_neg:
                continue
            raw.append((m.start(), m.end(), lab))

    # ── RULE 3: maximal munch. A longer label covering the same text wins.
    raw.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept = []
    for h in raw:
        if any(k[0] <= h[0] and h[1] <= k[1] and (k[1] - k[0]) > (h[1] - h[0])
               for k in kept):
            continue
        kept.append(h)
    kept.sort()
    return kept
