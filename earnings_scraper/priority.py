# -*- coding: utf-8 -*-
"""How important is this row? Read off an AUTHORED signal, never inferred.

The absence ruling refuses a value on a priority-1 hero row, so whatever
answers this question decides whether a number reaches Kyle's card. That
makes it exactly the wrong place for a fuzzy binder.

★★★ AND THE OBVIOUS BINDER IS ALREADY BANNED HERE. score._name_matches_any
binds a card row to a profile hero on 50% token overlap. registry.py removed
that same binder from the extraction path because profile heroes are
PERIOD-RELATIVE by design ("FY capex framework") while library rows are
PERIOD-SPECIFIC ("FY27 Capex ($B)") -- two correct naming systems with
nothing bridging them, and fuzzy matching across the gap produced PERIOD
INVERSION: ADBE's "Current-quarter revenue" nearest-matched the Q4 REVENUE
GUIDE row. Reusing it to drive a REFUSAL would put that defect on the path
that decides whether a value is published at all.

So priority comes from one of two authored places, in order:

  1. spec['priority']          written at pre-earnings build time. Explicit.
  2. the card's own star scale  ONLY where the card actually grades with it

★★ AND THE STAR SCALE IS NOT UNIVERSAL. AVGO and HPE mark heroes ★★★ and
supporting rows ★★ or ★. SNDK, APP and WDC mark EVERY row ★. On those cards
a star count carries no priority information at all, so reading one would
manufacture a priority where the author expressed none -- and the lenient
arm of the ruling would then fire on a row the author may have considered
critical. Where the card has no graded scale this returns None, meaning
UNKNOWN, and UNKNOWN is reported rather than rounded down to 'not a hero'.
"""

import re

STAR = re.compile(u'\u2605')

#: a card grades with stars only if it actually uses more than one level
_GRADED_MIN_LEVELS = 2


def card_uses_star_scale(pre_rows):
    """Does THIS card express priority through its star counts?

    True only when the rows carry at least two distinct non-zero counts --
    an all-★ card (SNDK, APP, WDC) expresses nothing and must not be read.
    """
    levels = {len(STAR.findall(r.get('name') or ''))
              for r in (pre_rows or [])}
    levels.discard(0)
    return len(levels) >= _GRADED_MIN_LEVELS


def row_priority(pre_row, spec=None, pre_rows=None):
    """1 (hero) | 2 (supporting) | None (UNKNOWN -- say so, never assume).

    `pre_rows` is the whole card, because whether a star count MEANS anything
    is a property of the card, not of the row.
    """
    # ★★★ THE ROW IS WHERE PRIORITY BELONGS, AND IT IS WHERE IT WAS
    # AUTHORED. 614 rows carry `priority` on the ROW and ZERO carry it
    # inside `extraction`, because priority is a property of the CARD ROW --
    # which KPI decides the print -- not of the extraction spec, which is
    # about how to read a document. This read the spec only, so 0b stayed
    # at 164 of 195 after the whole library was authored.
    #
    # One condition, two places. The row is checked FIRST because it is the
    # correct home; the spec is still honoured so a spec-level override
    # keeps working.
    declared = (pre_row or {}).get('priority')
    if declared not in (1, 2, 3):
        declared = (spec or {}).get('priority')
    if declared in (1, 2, 3):
        return declared
    if not card_uses_star_scale(pre_rows):
        return None
    stars = len(STAR.findall((pre_row or {}).get('name') or ''))
    if stars >= 3:
        return 1
    if stars >= 1:
        return 2
    return None


def describe(priority):
    return {1: 'priority-1 hero', 2: 'supporting row'}.get(
        priority, 'priority UNKNOWN -- the card declares none and its star '
                  'scale is not graded')
