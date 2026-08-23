"""Unit normalisation for the expected column.

The library is not unit-homogeneous. Across the 79 records `preEarnings.revUnit`
is `$B` 58 times, `$M` 14 times, and **null 7 times**.

Parsed actuals are always normalised to $M, so grading revenue requires knowing
which unit the stored consensus used. When `revUnit` is null we do NOT guess.
INTC's 12.36 is "obviously" $B and NOW's 3.74 "obviously" $B, but the model's
error class 4 is explicit about this failure mode -- an AMD bogey column reading
"140%" was taken as implied vol when it was YTD move, and it produced a FALSE
CONFIRMATION because the inferred value happened to look reasonable. So an
undeclared unit yields a refusal to grade that line, surfaced on the card,
rather than a plausible-looking number.
"""

import re

_TO_MUSD = {'$m': 1.0, 'm': 1.0, '$mm': 1.0,
            '$b': 1000.0, 'b': 1000.0, '$bn': 1000.0,
            '$k': 0.001, 'k': 0.001}


class UndeclaredUnit(Exception):
    """Raised when a stored figure has no declared unit."""


def to_musd(value, unit):
    """Normalise a stored expectation to $M.

    Raises UndeclaredUnit when `unit` is missing -- callers must handle this
    by refusing to grade the line, never by inferring.
    """
    if value is None:
        return None
    if unit is None or str(unit).strip() == '':
        raise UndeclaredUnit('revUnit is not declared on this record')
    mult = _TO_MUSD.get(str(unit).strip().lower())
    if mult is None:
        raise UndeclaredUnit('unrecognised unit %r' % unit)
    try:
        return float(value) * mult
    except (TypeError, ValueError):
        return None


def normalise_expectation(value, unit):
    """Best-effort normalise. Returns (value_musd, problem_or_None)."""
    try:
        return to_musd(value, unit), None
    except UndeclaredUnit as exc:
        return None, str(exc)


_NAME_UNIT = re.compile(r'\((\$B|\$M|\$K|%|bps|GWh|MW|\$)\)', re.I)


def unit_from_kpi_name(name):
    """Extract the declared unit from a KPI name, e.g. "FQ4 Revenue ($B)".

    The unit lives in the NAME, and within one row the bogey and the stored
    actual can disagree: SNDK-2026Q4 keyKPI[0] is "FQ4 Revenue ($B)" with
    bogey 9.5 and a stored actual of 8965 -- $B against $M. Comparing them
    raw reports a MISS of -5.6% as a clean CLEAR. Always resolve the name's
    unit before comparing anything on that row.
    """
    if not name:
        return None
    m = _NAME_UNIT.search(str(name))
    return m.group(1) if m else None


def kpi_to_musd(value, kpi_name):
    """Normalise a KPI figure to $M using the unit declared in its name.

    Returns (value_musd, problem). A non-dollar unit (%, bps, GWh) returns the
    value unchanged with unit_kind set, since those are already comparable.
    """
    unit = unit_from_kpi_name(kpi_name)
    if value is None or not isinstance(value, (int, float)):
        return None, None
    if unit is None:
        return None, ('no unit declared in KPI name %r -- refusing to '
                      'normalise' % str(kpi_name)[:50])
    low = unit.lower()
    if low in ('%', 'bps', 'gwh', 'mw'):
        return float(value), None          # already comparable, not a $ figure
    mult = _TO_MUSD.get(low)
    if mult is None:
        if low == '$':
            return float(value), None      # per-share dollars
        return None, 'unrecognised KPI unit %r' % unit
    return float(value) * mult, None


def declared_to_musd(value, declared_unit):
    """Normalise using an EXPLICITLY DECLARED unit. Returns (value, problem).

    This is the preferred path: when a row declares `actualUnit` there is
    nothing to resolve and no ambiguity to refuse over.
    """
    if value is None or not isinstance(value, (int, float)):
        return None, None
    if not declared_unit:
        return None, 'no declared unit'
    mult = _TO_MUSD.get(str(declared_unit).strip().lower())
    if mult is None:
        return None, 'unrecognised declared unit %r' % declared_unit
    return float(value) * mult, None


def is_dollar_magnitude(kpi_name):
    """True when a KPI's unit is a dollar MAGNITUDE ($B/$M/$K), not a rate."""
    return (unit_from_kpi_name(kpi_name) or '').lower() in ('$b', '$m', '$k')


def looks_like_billions(value):
    """Diagnostic only -- NEVER used to grade.

    Used solely to phrase the warning shown to the user, e.g. "stored 12.36
    with no unit; if this is $B the actual is a beat". It is a prompt for a
    human decision, not an input to any score.
    """
    try:
        return 0.0 < float(value) < 1000.0
    except (TypeError, ValueError):
        return False

# ── does the NAME declare a scale at all? ────────────────────────────────────
#
# ★ `unit_from_kpi_name` answers "which unit is this" against a CLOSED list.
# The dangerous case is a name that declares a scale in a form the list does not
# carry -- "Q1 Revenue ($bn)", "Q1 Revenue (US$M)", "Q1 Revenue ($ in millions)".
# There `unit_from_kpi_name` returns None, so `is_dollar_magnitude` is False, so
# no actualUnit is declared, so 10253.0 renders as a bare 10,253 instead of
# 10.253 ($B) -- and 10,253 still grades CLEAR against a bogey of 10.25, by
# ACCIDENT. The next release where the accident does not hold grades wrong.
#
# So a second, DELIBERATELY BROADER predicate: does this name look like it
# declares a dollar magnitude, whether or not we can resolve it? A True here
# with a None from unit_from_kpi_name is a gap in the closed list, and the row
# must be refused rather than written unitless.
_NAME_PAREN = re.compile(r'\(([^)]{1,24})\)')

_MAGNITUDE_WORD = re.compile(
    r'^(?:us\s*)?\$?\s*(?:in\s+)?'
    r'(b|bn|bil|billion|billions|m|mm|mil|million|millions|k|thousand|'
    r'thousands)\s*(?:\$|usd)?$', re.I)


def declared_scale_token(name):
    """The parenthetical of `name` that looks like a unit declaration, or None.

    Returns the raw token so a refusal can NAME what it could not resolve --
    "($bn)" is far more actionable than "unit unresolved".
    """
    for tok in _NAME_PAREN.findall(str(name or '')):
        t = tok.strip()
        if _MAGNITUDE_WORD.match(t) or t.lower() in (
                '%', 'bps', 'gwh', 'mw', '$', '$b', '$m', '$k'):
            return t
    return None


def looks_like_dollar_magnitude(name):
    """Broad: does this name declare a dollar MAGNITUDE in any spelling?

    Deliberately wider than `is_dollar_magnitude`. Used only to detect that a
    scale WAS declared and could not be resolved -- never to grade.
    """
    tok = declared_scale_token(name)
    if tok is None:
        return False
    if tok.lower() in ('%', 'bps', 'gwh', 'mw', '$'):
        return False                       # a rate or a per-share figure
    return bool(_MAGNITUDE_WORD.match(tok))
