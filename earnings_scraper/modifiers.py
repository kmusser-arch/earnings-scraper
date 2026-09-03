# -*- coding: utf-8 -*-
"""KEY 2 — a modifier on EITHER side and absent on the other disqualifies.

★ ONE RULE, STATED SYMMETRICALLY. Both AVGO defects are the same rule mirrored,
and an implementation checking one direction fixes one and misses the other:

    [10]  row "Non-AI Semi Revenue"      candidate "Q3 AI semiconductor revenue"
          -> the ROW carries the NEGATION `non-`, the candidate does not
    [ 1]  row "Q4 AI Semi Revenue Guide" candidate "Fourth quarter fiscal year
                                          2026 revenue guidance"
          -> the ROW carries `ai`, the candidate does not

and the mirror of the mirror, from HPE:

    [ 8]  row "Q3 Non-GAAP EPS"          candidate "regular cash dividend of
                                          $0.1425 per share"
          -> the CANDIDATE carries `dividend`, the row does not

Hard disqualify, not a score penalty: a near-match on a modifier is not a
weaker match, it is a different quantity.

★★ KEY 2 OWNS ONE AXIS ONLY, AND THAT IS THE WHOLE POINT.

Measured over 448 period-matched rows, an unscoped token list disqualified
75.0% of them -- rows compared against a spelled-out phrasing of the SAME
metric and SAME period, so every one of those was false by construction:

    as originally specified                    336 / 448   75.0%
    minus net, gross, per-share  (METRIC)      174         38.8%
    minus guide, framework, target (PERIOD)     92         20.5%
    minus the basis family        (BASIS)       ...        see below

A token kept on two axes does not double-protect. It DOUBLE-REFUSES, and
refusalIsNotFree records that a refusal is a scoring decision which can land
further from truth than a wrong fill.

    METRIC   net, gross, per-share          -> hero_metric_kind()
             "net revenue" IS the standard reported revenue line; 182 plain
             Revenue rows disqualified against it.
    PERIOD   guide, guidance, framework,
             target                         -> period.may_fill() (KEY 1)
             "Q4 EPS Guide ($)" vs "EPS is expected to be $1.10" conflicts on
             `guide` while KEY 1 already agrees both are GUIDE_NEXT_Q. 51 rows.
    BASIS    adj, non-GAAP, GAAP, CC,
             organic, core, pro-forma       -> basis.declared() / select()

★ THE BASIS CARVE-OUT -- deferral is NOT unconditional:
    one side bare              -> defer to basis.select(), which SELECTS and
                                  RECORDS which basis it took. Better than
                                  refusing, and it is the 60-row residue.
    both declare and DISAGREE  -> KEY 2 disqualifies.
  Founding case: CBRS. GAAP missed 7.0% while company-defined "core" beat 9.9%
  and the tape traded GAAP. A row declaring GAAP must not take a "core"
  candidate, and basis.select() will not stop that -- it only arbitrates when
  the row is bare.

★★ THE "non-" AMBIGUITY SPANS TWO AXES, so the branch is on the token that
FOLLOWS it, never on "non-" itself:
    "non-GAAP"  -> BASIS    -> defer to basis.select()
    "Non-AI"    -> NEGATION -> KEY 2 disqualifies
  Backwards, this either blanks every non-GAAP row or lets AVGO [10] through
  again.
"""

import re

from . import basis as _basis

# ══ THE MODIFIER AXIS — negation, scope, kind, window ═════════════════════
#
# Nothing here belongs to the metric, period or basis axes. Each token names a
# DIFFERENT QUANTITY while metric and period both agree.

#: basis words that may follow "ex-" -- these are BASIS, not negation.
#: The library records ex-credits as a basis on 3 rows.
_EX_BASIS = re.compile(r'^(?:credits?|fx|currency|ccy|items?|charges?)\b', re.I)

#: NEGATION: non-X and ex-X, EXCEPT where X is a basis term.
#: ★ The branch is on what FOLLOWS the prefix. "non-GAAP" is a basis and must
#: fall through to basis.select(); "Non-AI" is a negation and disqualifies.
_NON_PREFIX = re.compile(r'\bnon-\s*(\w+)', re.I)
_EX_PREFIX = re.compile(r'\bex-\s*(\w+)', re.I)

_MODIFIERS = {
    # SCOPE -- sub-metric identity
    'ai': (r'\bai\b',),
    'semi': (r'\bsemi\b', r'\bsemiconductors?\b'),
    # KIND -- a different quantity entirely
    'backlog': (r'\bbacklog\b',),
    'orders': (r'\borders?\b',),
    'dividend': (r'\bdividend\b',),
    # WINDOW -- a different aggregation
    'trailing': (r'\btrailing\b', r'\bttm\b'),
}

_COMPILED = tuple((canon, re.compile('|'.join(pats), re.I))
                  for canon, pats in _MODIFIERS.items())

#: decoration that must never contribute a token
_DECOR = re.compile(r'[★☆\U0001F525⚠⛔\U0001F6A8]+'
                    r'|\bTHE\s+HERO\b|\bTHE\s+EVENT\b|\(DERIVED\)'
                    r'|\bTHE\s+KPI\b|\bWHERE\s+UPSIDE\s+LIVES\b'
                    r'|\bTHE\s+TRADE\b|\bNOISE\b|#\s*\d+', re.I | re.U)

#: preferred when naming a conflict -- the tokens a human can act on.
#: "it matched the dividend" beats "it disagreed on ai".
_INFORMATIVE = ('dividend', 'backlog', 'orders', 'trailing')


def _negations(text):
    """non-X / ex-X tokens where X is NOT a basis term.

    ★ Branching on the FOLLOWING token is what separates the two axes:
    non-GAAP is a basis, Non-AI is a negation.
    """
    out = set()
    for m in _NON_PREFIX.finditer(text or ''):
        word = m.group(1)
        if word.lower() == 'gaap':
            continue                      # BASIS -- basis.select() owns it
        out.add('non-' + word.lower())
    for m in _EX_PREFIX.finditer(text or ''):
        word = m.group(1)
        if _EX_BASIS.match(word):
            continue                      # BASIS -- ex-credits, ex-FX
        out.add('ex-' + word.lower())
    return out


def modifier_set(text):
    """The canonical modifier tokens in `text`, on the MODIFIER axis only.

    ★ `revenue`, `margin` and `EPS` are absent by design: they name the metric
    rather than modifying it. Stripping metric nouns is what produced 181
    phantom collisions in an earlier pass -- an empty core set is a subset of
    everything -- so they simply never enter these sets.
    """
    t = _DECOR.sub(' ', text or '')
    found = {canon for canon, pat in _COMPILED if pat.search(t)}
    return found | _negations(t)


def basis_conflict(row_name, candidate_label):
    """(row_basis, candidate_basis) when BOTH declare and they DISAGREE.

    None when either side is bare -- that is basis.select()'s job, and it
    selects and RECORDS rather than refusing.
    """
    rb = _basis.declared(row_name or '')
    cb = _basis.declared(candidate_label or '')
    if rb and cb and rb != cb:
        return rb, cb
    return None


def disqualify(row_name, candidate_label):
    """(token, side) when a modifier is on one side only, else None."""
    if not row_name or not candidate_label:
        return None

    # ★ BASIS FIRST, and only when BOTH sides declare one. CBRS: a GAAP row
    # must not take a "core" candidate, and basis.select() cannot stop that.
    bc = basis_conflict(row_name, candidate_label)
    if bc:
        return 'basis:%s-vs-%s' % bc, 'both'

    row = modifier_set(row_name)
    cand = modifier_set(candidate_label)
    only_row = sorted(row - cand)
    only_cand = sorted(cand - row)
    if not only_row and not only_cand:
        return None
    for token in _INFORMATIVE:
        if token in only_cand:
            return token, 'candidate'
        if token in only_row:
            return token, 'row'
    if only_row:
        return only_row[0], 'row'
    return only_cand[0], 'candidate'


def conflicts(row_name, candidate_label):
    """Every modifier on one side only: (only_row, only_candidate)."""
    row = modifier_set(row_name or '')
    cand = modifier_set(candidate_label or '')
    return sorted(row - cand), sorted(cand - row)


def refusal_note(row_name, candidate_label):
    """Why this candidate may not fill this row, or None."""
    hit = disqualify(row_name, candidate_label)
    if not hit:
        return None
    token, side = hit
    if side == 'both':
        rb, cb = basis_conflict(row_name, candidate_label)
        return ('basis conflict: the row declares %s and the candidate '
                'declares %s — CBRS: GAAP missed 7.0%% while "core" beat '
                '9.9%% and the tape traded GAAP' % (rb, cb))
    other = 'candidate' if side == 'row' else 'row'
    only_row, only_cand = conflicts(row_name, candidate_label)
    extra = ''
    if len(only_row) + len(only_cand) > 1:
        extra = (' (row-only %s; candidate-only %s)'
                 % (only_row or '[]', only_cand or '[]'))
    return ('modifier conflict: %r is on the %s and absent from the %s '
            '— a modifier changes WHICH QUANTITY is named, so this is a '
            'different metric, not a weaker match%s'
            % (token, side, other, extra))
