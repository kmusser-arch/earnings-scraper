# -*- coding: utf-8 -*-
"""Executive-quote extraction — LOWEST precedence, fills gaps only.

★ MEASURED BEFORE BUILT. Across six real releases only 5 of 15 quote figures
exist nowhere else in the document, and 4 of those 5 are AVGO's:

    AVGO   $16.7 billion, 221%, $21.7 billion, 236%     (4 of 11 figures)
    SNOW   $1.49 billion                                (1 of 3)
    HPE    none of 1                                    <- 8 quote spans, 0 gaps
    APP / SNDK / WDC   none

So this is deliberately NARROW. HPE's segment margins are in prose bullets the
parser already reaches, not in quotes, so the concern that quotes carry
widespread hidden value did not reproduce. A reader scoped to quoted spans is
right; generalising it is not.

★★ QUOTES SIT AT THE BOTTOM OF PRECEDENCE, DESPITE FEELING AUTHORITATIVE. A CEO
naming a figure for the current quarter is maximally SPECIFIC and less RELIABLE
than the reconciliation table, because executives round and tables do not.
Measured: SNOW's quote says "$1.49 billion" where the table says 1,491.9 --
0.94% apart, and the rounded quote flatters the read.

That is precedenceMustTrackReliability, and putting quotes high because they
feel specific is the same error as `of <number>` at precedence level 1.

    1. reconciliation / financial-statement table   (most precise)
    2. segment table
    3. prose bullet
    4. executive quote                              <- here

★★★ AND DISQUALIFICATION IS EVALUATED BEFORE PRECEDENCE. A disqualified
candidate is not a low-ranked candidate, it is NOT A CANDIDATE:

    build candidates -> FILTER (period, modifier, basis, scale) -> RANK -> take

Ranking first would let a high-precedence bad candidate beat a low-precedence
good one, which is the same rule inverted. This module therefore only ever
OFFERS a candidate; every filter still applies to it.
"""

import re

QUOTE_SPAN = re.compile(r'"([^"]{40,900})"')

#: a figure with its magnitude word, and a percentage form
_FIG = re.compile(
    r'\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|trillion|bn|mm|B|M)?\b'
    r'|(?<![\d.])([\d,]+(?:\.\d+)?)\s*%')

_SENT = re.compile(r'(?<=[.!?])\s+')


def _to_musd(num, unit):
    v = float(str(num).replace(',', ''))
    u = (unit or '').lower()
    if u.startswith('t'):
        return v * 1000000.0
    if u.startswith('b'):
        return v * 1000.0
    if u.startswith('m'):
        return v
    return v


def spans(text):
    """[(start, quote_text)] for every quoted block."""
    return [(m.start(1), m.group(1)) for m in QUOTE_SPAN.finditer(text or '')]


def candidates(text):
    """Every figure inside a quote, with the SENTENCE that governs it.

    Returns [dict(value_musd, is_pct, raw, sentence, offset)].

    ★ The sentence, not the span. AVGO's block carries a REPORTED figure and a
    GUIDE figure in ADJACENT sentences -- $16.7B for Q3 and $21.7B for Q4,
    1.1%-adjacent in a neighbouring release -- so classifying per span would
    give both the same period and fill the wrong row. Per sentence, KEY 1
    separates them: measured 7 clean, 0 UNRESOLVED.
    """
    out = []
    for start, span in spans(text or ''):
        pos = 0
        for sent in _SENT.split(span):
            s_off = start + span.find(sent, pos)
            pos = max(pos, span.find(sent, pos) + 1)
            for m in _FIG.finditer(sent):
                if m.group(3) is not None:
                    out.append(dict(
                        value_musd=float(m.group(3).replace(',', '')),
                        is_pct=True, raw=m.group(0).strip(),
                        sentence=sent, offset=s_off + m.start()))
                else:
                    out.append(dict(
                        value_musd=_to_musd(m.group(1), m.group(2)),
                        is_pct=False, raw=m.group(0).strip(),
                        sentence=sent, offset=s_off + m.start()))
    return out


def for_row(text, row_name, want_pct=False):
    """The quote candidates whose SENTENCE mentions this row's metric.

    Deliberately crude on the metric: the caller applies KEY 2, which is the
    real discriminator. This only narrows the set to sentences that plausibly
    concern the row at all, so a revenue row is not offered an EPS figure.
    """
    from . import modifiers as _mod
    from . import score as _score

    toks = _mod.modifier_set(row_name or '')

    # ★★ THE METRIC MUST AGREE, and this is not optional. Requiring only that
    # the row's MODIFIER tokens appear in the sentence is vacuously true for
    # any row that has none, so every quote figure matched every such row --
    # total revenue landed in an EBITDA row, in a gross-margin row and in two
    # qualitative rows. An empty required-set is a subset of everything.
    #
    # hero_metric_kind() already owns metric identity; consulting it beats
    # inventing a second notion here. A row OR sentence whose metric cannot be
    # identified is not a match: a filter that cannot discriminate must not be
    # treated as a filter that passed.
    row_kind = _score.hero_metric_kind(row_name or '')
    if row_kind is None:
        return []

    out = []
    for cand in candidates(text):
        if bool(cand['is_pct']) != bool(want_pct):
            continue
        if _score.hero_metric_kind(cand['sentence']) != row_kind:
            continue
        sent_toks = _mod.modifier_set(cand['sentence'])
        # every SCOPE token the row demands must appear in the sentence.
        # KEY 2 still runs afterwards and can still refuse; this is a
        # pre-filter, not the decision.
        if toks and not toks <= sent_toks:
            continue
        out.append(cand)
    return out
