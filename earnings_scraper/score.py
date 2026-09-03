"""Run parsed actuals against the earnings model.

THE DISCRIMINATOR
=================
Current Quarter grades on **clearance of the BOGEY on the ticker's priority-1
hero KPI**, modified by an **offsetting-flag count**. Two-dimensional, and
neither axis is revenue or consensus.

A band function keyed on consensus delta provably cannot reproduce the accepted
grades: SNDK beat consensus +6.9% and scored +1.0 (it missed bogey by 5.6%);
TSLA beat +0.5% and scored +2.0. Medians by band: +2.0 -> +1.32% vs bogey,
+1.5 -> +0.06%, +1.0 -> -0.73%, +0.5 -> -0.74%. Because +0.5 and +1.0 share a
median, bogey clearance ALONE cannot separate them -- the flag count does.

DERIVED_STEP_DOWN
=================
The published band table has no row for "clears bogey 0-2% with >=2 flags",
which is exactly where SNDK-2026Q4 (+1.0) sits. The rule that reconciles the
table with all three pinned grades is:

    score = base_band - 0.5 * max(0, flags - band.maxFlags)

    TSLA  hero +6.67% -> base +2.0 (maxFlags 0), 0 flags -> +2.0  = pinned
    SNDK  hero +0.71% -> base +1.5 (maxFlags 1), 2 flags -> +1.0  = pinned
    CSCO  no bogey, cons +2.54% -> base +2.0 (maxFlags 0), 2 flags -> +1.0 = pinned

This step-down is an INFERENCE, not a documented rule. It is isolated here and
reported on every card as `stepDownApplied` so it can be reviewed rather than
trusted silently.
"""

import re

from . import basis as basis_mod
from . import modifiers as modifiers_mod
from . import quotes as quotes_mod
from . import period as period_mod
from . import config, gate, plausibility, units
from .parse import pct_delta, verdict_for

DERIVED_STEP_DOWN = (
    'score = base_band - 0.5 * max(0, flags - band.maxFlags). Derived to '
    'reconcile the published bands with SNDK/TSLA/CSCO; not a documented rule.'
)

# Narrative is permanently deferred on a PR. This is by design, not a stopgap.
NARRATIVE_PR_REASON = 'PR-only; narrative requires the call'

# Guidance actions that must NEVER be auto-scored. Per CLAUDE.md these are in
# the "what must NOT be automated" list -- the weight depends on WHICH metric
# was retired or capped, which is a call judgment.
_DEFER_ACTIONS = frozenset(('WITHDRAWN', 'CAPPED', 'CEILING'))

# An FY-period marker anywhere in a KPI name. Used to keep FY rows out of
# next-quarter cohorts -- classify the period before matching the metric word.
_FY_IN_NAME = re.compile(r'\bFY\s?\d{2,4}\b|\bFY\b|\bfull[- ]year\b', re.I)


class PolarityPredicateMissing(Exception):
    """render_scorecard._is_reverse_polarity could not be loaded.

    Do NOT substitute a local heuristic. The predicate decides which rows the
    "actual >= consensus is good" comparison is INVERTED on, and a second
    implementation would drift from the renderer's -- which is exactly how
    META-2026Q2 entered a published cohort on a capex overshoot read as a beat.
    """


def is_reverse_polarity(name):
    """★ Shared predicate, imported from render_scorecard. Never reimplemented.

    28 rows in the library are reverse-polarity, and every comparison built on
    "actual >= consensus is good" is inverted on them. The sign is CONTEXTUAL --
    META-2026Q1's capex raise was the bullish event of its print, META-2026Q2's
    capex overshoot was a negative -- so these rows are EXCLUDED from mechanical
    comparison rather than inverted. Guessing an inversion is as wrong as
    guessing the original direction.
    """
    from . import scorecard
    try:
        pred = getattr(scorecard.renderer(), '_is_reverse_polarity')
    except Exception as exc:
        raise PolarityPredicateMissing(
            'cannot load render_scorecard._is_reverse_polarity (%s). Refusing '
            'to reimplement it: a divergent copy is how a capex overshoot got '
            'read as a beat.' % exc)
    return bool(pred(name or ''))


class AlignmentError(Exception):
    """actuals.keyKPIs is not index-aligned 1:1 with preEarnings.keyKPIs."""


# --- band parsing -------------------------------------------------------------

_RANGE_RE = re.compile(r'^\s*(-?[\d.]+)\s*to\s*\+?(-?[\d.]+)\s*$', re.I)
_GE_RE = re.compile(r'^\s*>=\s*\+?(-?[\d.]+)\s*$')
_FLAGS_RANGE = re.compile(r'^\s*(\d+)\s*-\s*(\d+)\s*$')
_FLAGS_GE = re.compile(r'^\s*>=\s*(\d+)\s*$')


def _band_matches_clearance(band, clearance_pct):
    """Does this band's clearance condition hold?"""
    spec = band.get('heroClearsBogeyPct')
    if spec is None or clearance_pct is None:
        return False
    spec = str(spec)
    m = _GE_RE.match(spec)
    if m:
        return clearance_pct >= float(m.group(1))
    m = _RANGE_RE.match(spec)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return lo <= clearance_pct <= hi
    if 'AND beats consensus' in spec:
        m = _RANGE_RE.match(spec.split('AND')[0].strip())
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            return lo <= clearance_pct <= hi
    return False


def _band_max_flags(band):
    if 'maxFlags' in band:
        return int(band['maxFlags'])
    f = band.get('flags')
    if f is None:
        return None
    m = _FLAGS_RANGE.match(str(f))
    if m:
        return int(m.group(2))
    m = _FLAGS_GE.match(str(f))
    if m:
        return int(m.group(1))
    return None


def _round_half(x):
    return None if x is None else max(-2.0, min(2.0, round(x * 2) / 2))


# --- hero KPI resolution ------------------------------------------------------

def _match_kpi_slot(hero_name, key_kpis, record_quarter=None):
    """Find the preEarnings.keyKPIs index carrying the hero KPI.

    Matched on significant word overlap, because the profile name and the KPI
    name are written independently: profile "Gross Margin (%) - current and
    guided" against keyKPI "FQ4 Gross Margin (%)".
    """
    if not hero_name:
        return None
    stop = {'the', 'and', 'or', 'a', 'of', 'current', 'guided', 'vs',
            'not', 'level', 'direction', 'step', 'up'}
    want = {w for w in re.findall(r'[a-z]{3,}', hero_name.lower())
            if w not in stop}
    if not want:
        return None
    best, best_score = None, 0.0
    for i, k in enumerate(key_kpis):
        name = (k.get('name') or '').lower()
        # A forward slot can never carry the current-quarter hero.
        if _classify_period(k.get('name') or '', record_quarter) != 'CURRENT_Q':
            continue
        # ★ Nor can a row measuring a DIFFERENT SUBJECT. Word overlap alone put
        # a "Product Gross Margin" hero on a company gross-margin row at 67%
        # overlap, and a "Hardware Revenue" hero on the total revenue row.
        if not hero_scope_matches(hero_name, k.get('name') or ''):
            continue
        have = set(re.findall(r'[a-z]{3,}', name))
        if not have:
            continue
        overlap = len(want & have) / len(want)
        if overlap > best_score:
            best, best_score = i, overlap
    return best if best_score >= 0.5 else None


# --- period classification (SKILL.md §6.4) ------------------------------------

_PERIOD_TOKEN = re.compile(r'\bF?Q([1-4])\b|\bFY\s?(\d{2,4})\b', re.I)


def _period_tokens(text):
    """(quarters, fiscal-years) named in a KPI name or a quarter label."""
    quarters, years = set(), set()
    for m in _PERIOD_TOKEN.finditer(text or ''):
        if m.group(1):
            quarters.add(m.group(1))
        if m.group(2):
            years.add(m.group(2)[-2:])
    return quarters, years


def _classify_period(name, record_quarter=None):
    """FY_GUIDE | NEXTQ_GUIDE | CURRENT_Q.

    The documented rules (SKILL.md §6.4) key on the words FY and Guid. Those
    alone are NOT sufficient: CSCO-2026Q4 carries the KPI
    "Q1 FY27 Non-GAAP Gross Margin (%) ★★", which contains no "Guid" and so
    classifies as CURRENT_Q -- and the hero matcher then binds the graded
    current-quarter metric to a slot describing NEXT quarter's guide.

    So when the record's own quarter is known, an explicit period token that
    DISAGREES with it also marks the slot forward.
    """
    n = (name or '')
    has_guid = bool(re.search(r'guid|outlook|target', n, re.I))
    has_fy = bool(re.search(r'\bFY\b|FY\s?\d{2,4}|\bfull[- ]year\b', n, re.I))

    # ★ A QUARTER TOKEN OUTRANKS AN FY TOKEN.
    # "Q1 FY27 Revenue Guide" is a NEXT-QUARTER guide that merely names the
    # fiscal year it falls in. The documented "FY and Guid -> FY_GUIDE" rule
    # files it as full-year, which hid ARM-2026Q4 (+0.80% cons / -5.26% bogey)
    # from the next-Q fade-zone cohort entirely -- and that record fell 7.50%,
    # so its absence flattered the cohort's base rate.
    name_quarters, _ny = _period_tokens(n)
    if has_guid and name_quarters:
        return 'NEXTQ_GUIDE'

    if has_fy and has_guid:
        return 'FY_GUIDE'

    # ★ An FY TOKEN WITH NO QUARTER TOKEN IS A FULL-YEAR ROW, whether or not the
    # name says "guide". "FY26 EPS ($)" and "FY26 Capex ($B)" both classified as
    # CURRENT_Q, so a reported quarterly EPS could be written into a full-year
    # slot -- non-negotiable 2, which exists precisely because a Q4 actual once
    # landed in an FY27 guide slot.
    #
    # EXCEPT on the Q4 print, where the named year has CLOSED and its total is a
    # reported actual, not a guide: CSCO-2026Q4's "FY26 AI Infrastructure Orders
    # ($B) ★★" is the FY26 total announced with the Q4 result. The record's own
    # quarter label carries the year -- 'Q4 (FY26)' -- so the two are comparable
    # without guessing, and "FY27 Capex" on that same print stays forward.
    if has_fy and not name_quarters:
        rec_q, rec_y = _period_tokens(record_quarter or '')
        _n, name_y = _period_tokens(n)
        if '4' in rec_q and name_y and rec_y and (name_y & rec_y):
            return 'CURRENT_Q'
        return 'FY_GUIDE'

    if has_guid:
        return 'NEXTQ_GUIDE'

    if record_quarter:
        kq, ky = _period_tokens(n)
        rq, ry = _period_tokens(record_quarter)
        if ky and ry and not (ky & ry):
            return 'FY_GUIDE' if not kq else 'NEXTQ_GUIDE'
        if kq and rq and not (kq & rq):
            return 'NEXTQ_GUIDE'
    return 'CURRENT_Q'


def _is_forward(name, record_quarter=None):
    return _classify_period(name, record_quarter) != 'CURRENT_Q'


# --- offsetting flags ---------------------------------------------------------
#
# ★ THE PR-ONLY CURRENT QUARTER IS A CEILING, NOT A POINT ESTIMATE.
#
# The step-down is score = base - 0.5 * max(0, flags - maxFlags), and 3 of the 7
# flags cannot be assessed from a press release at all. So a PR-only flag count
# is a FLOOR: fewer flags means less step-down means a HIGHER score. The call can
# only ADD flags, never remove them, so the score can only FALL.
#
# Confirmed on the 3-release corpus: scraper cq exceeded the hand-built cq on
# 3 of 3, by exactly 1, 2 and 1 notches -- matching 1, 2 and 1 unassessable
# flags. The direction is forced by the formula, not fitted to the data.
#
# This biases the PR-only read BULLISH by construction, inside the
# STAY_FOR_CALL cohort that resolves DOWN 78% of the time. So the ceiling is
# reported and NO corrective haircut is applied: the direction is certain, the
# magnitude is unknown at n=3, and inventing the size would be the same error
# in the opposite direction.

# The canonical seven, and whether a press release can settle each one.
FLAG_REGISTRY = (
    ('secondHeroMissedBogey', True,
     'a second priority-1 hero KPI missed its bogey'),
    ('marginDownYoY', True, 'gross or operating margin down year-over-year'),
    ('atOrBelowOwnGuideTop', True,
     "reported at or below the company's own guide top"),
    ('gaapBasisGapFlipsSign', True,
     'a GAAP vs non-GAAP basis gap materially changes the sign'),
    # ★ The three that require the call. Named in the library as the reason a
    # PR-only count is a floor.
    ('segmentDown20Sequential', False, 'a segment down >20% sequentially'),
    ('growthPriceNotVolume', False, 'growth majority price rather than volume'),
    ('arrRpoLagsOrders', False,
     'ARR/RPO growth lagging order growth by >20pp'),
)

FLAGS_TOTAL = len(FLAG_REGISTRY)
FLAGS_REQUIRING_CALL = tuple(fid for fid, ok, _ in FLAG_REGISTRY if not ok)


def flag_accounting(assessed_ids, fired_ids):
    """The denominator. A flag count without it reads as complete."""
    assessed = [f for f in assessed_ids if f]
    return dict(
        flagsFired=len(fired_ids),
        flagsAssessed=len(assessed),
        flagsTotal=FLAGS_TOTAL,
        flagsRequiringCall=list(FLAGS_REQUIRING_CALL),
        notAssessedIds=[fid for fid, _ok, _d in FLAG_REGISTRY
                        if fid not in assessed],
        summary=('flags assessed %d of %d possible — %d require the call'
                 % (len(assessed), FLAGS_TOTAL, len(FLAGS_REQUIRING_CALL))),
        isFloor=True,
        note=('a PR-only flag count is a FLOOR: the call can only ADD flags, '
              'so the score can only FALL from here'))

def count_flags(parsed, entry, kpi_rows):
    """Count offsetting flags. Returns (flags, evidence, undeterminable).

    Flags requiring prior-year or segment data that a press release may not
    carry are reported as UNDETERMINABLE rather than assumed absent -- an
    unassessed flag can move the band, so the card must say so.
    """
    flags, evidence, unknown = 0, [], []
    assessed, fired = [], []
    polarity_skipped = []

    # 1. a second priority-1 hero KPI missed its bogey
    hero_names = {h.get('name') for h in (entry.get('allHeroes') or [])
                  if h.get('priority') == 1}
    graded = entry.get('heroName')
    misses = []
    for k in entry.get('keyKPIs') or []:
        name = k.get('name') or ''
        bogey = k.get('bogey')
        if not isinstance(bogey, (int, float)):
            continue
        if not _name_matches_any(name, hero_names):
            continue
        if graded and _name_matches_any(name, {graded}):
            continue
        # ★ REVERSE POLARITY: "missed its bogey" has no fixed meaning on a cost
        # metric, so the row cannot raise a flag mechanically.
        if is_reverse_polarity(name):
            polarity_skipped.append(name)
            continue
        actual = _resolved_actual(name, kpi_rows)
        # Numeric, not merely present. Stored actuals are frequently prose --
        # AMD-2026Q1 holds 'Implicit raise to $50B+ (no formal raise; ...)' on a
        # KPI row with a numeric bogey, which float() cannot take.
        if not isinstance(actual, (int, float)):
            continue
        b_norm, a_norm = _normalise_pair(bogey, actual, name)
        if b_norm is None or a_norm is None:
            continue
        if a_norm < b_norm:
            misses.append('%s (%s vs bogey %s)' % (name[:34], a_norm, b_norm))
    assessed.append('secondHeroMissedBogey')
    if misses:
        flags += len(misses)
        fired.append('secondHeroMissedBogey')
        evidence.extend('second priority-1 hero missed bogey: ' + m
                        for m in misses)

    # 2. gross or operating margin down YEAR-OVER-YEAR
    yoy = _margin_yoy(parsed, entry)
    if yoy is None:
        unknown.append('marginDownYoY — no prior-year margin stated in the '
                       'release (assessable in principle)')
    else:
        assessed.append('marginDownYoY')
        if yoy < 0:
            flags += 1
            fired.append('marginDownYoY')
            evidence.append('margin down YoY (%+d bps)' % yoy)

    # 3. reported figure landed AT or BELOW the company's own guide top
    own = _own_guide_top(entry)
    rev = (parsed.get('revenue') or {}).get('value_musd')
    if own is None:
        unknown.append("atOrBelowOwnGuideTop — the company's own prior guide "
                       'top is not stated (assessable in principle)')
    else:
        assessed.append('atOrBelowOwnGuideTop')
        if rev is not None and rev <= own:
            flags += 1
            fired.append('atOrBelowOwnGuideTop')
            evidence.append('revenue at/below own guide top (%s vs %s)'
                            % (rev, own))

    # 4. GAAP vs non-GAAP basis gap materially changes the sign
    eps_now = parsed.get('eps') or {}
    if 'GAAP' in eps_now and 'non-GAAP' in eps_now:
        assessed.append('gaapBasisGapFlipsSign')
        if _basis_flips_sign(parsed, entry):
            flags += 1
            fired.append('gaapBasisGapFlipsSign')
            evidence.append('GAAP/non-GAAP basis gap changes the sign '
                            'vs consensus')
    else:
        unknown.append('gaapBasisGapFlipsSign — only one EPS basis found, so '
                       'the gap cannot be assessed')

    # ★ 5-7. NEVER determinable from a press release. These are the three that
    # make a PR-only count a floor.
    for fid, ok, desc in FLAG_REGISTRY:
        if not ok:
            unknown.append('%s — %s: REQUIRES THE CALL' % (fid, desc))

    for nm in polarity_skipped:
        unknown.append('⚑ POLARITY %s — reverse-polarity row, excluded from '
                       'mechanical comparison (the sign is contextual)'
                       % nm[:44])

    return flags, evidence, unknown, flag_accounting(assessed, fired)


def _name_matches_any(name, candidates):
    n = set(re.findall(r'[a-z]{3,}', (name or '').lower()))
    for c in candidates:
        if not c:
            continue
        stop = {'the', 'and', 'current', 'guided', 'vs', 'not', 'level',
                'direction', 'step'}
        w = {x for x in re.findall(r'[a-z]{3,}', c.lower()) if x not in stop}
        if w and len(w & n) / len(w) >= 0.5:
            return True
    return False


def _resolved_actual(kpi_name, kpi_rows):
    for row in kpi_rows:
        if row.get('name') == kpi_name:
            return gradeable_actual(row)
    return None


def _normalise_pair(expected, actual, kpi_name, actual_unit=None):
    """Put an expectation and an actual on the same scale, or return (None, None).

    ★ Converting only the EXPECTED side is wrong, and it was wrong here for a
    long time. AMD-2026Q2 stores "Q3 Revenue Guide ($B)" with consensus 12.514
    and an actual of 13.0 -- BOTH in $B. Normalising just the expectation gave
    12514 vs 13.0, so a +3.88% beat read as a catastrophic miss. That silently
    suppressed the next-Q fade-zone detector on 6 of 10 known records, and it
    is the same defect class as the AMZN clearance bug.

    Resolution order matches the dollar-hero fallback:
      1. a DECLARED actual unit wins outright;
      2. otherwise take whichever reading is scale-consistent;
      3. if both readings or neither are plausible, refuse.
    """
    if not isinstance(expected, (int, float)) or not isinstance(actual, (int, float)):
        return None, None
    if not units.is_dollar_magnitude(kpi_name):
        return float(expected), float(actual)

    exp_m, problem = units.kpi_to_musd(expected, kpi_name)
    if problem or exp_m is None:
        return None, None

    if actual_unit:
        act_m, dproblem = units.declared_to_musd(actual, actual_unit)
        if not dproblem and act_m is not None:
            return exp_m, act_m

    # No declaration: choose the scale-consistent reading, never prefer.
    _c, basis, _why = gate._scale_consistent_clearance(
        expected, exp_m, float(actual))
    if basis == 'row unit' or (basis or '').startswith('unambiguous'):
        return float(expected), float(actual)
    if basis == '$M':
        return exp_m, float(actual)
    return None, None


def _margin_yoy(parsed, entry):
    """Basis-point YoY margin change if the release states it."""
    m = parsed.get('marginYoYBps')
    return m if isinstance(m, (int, float)) else None


def _own_guide_top(entry):
    """Top of the company's own prior guide, in $M, if the card records it."""
    for field in ('revNote', 'setup', 'whatMattersMost'):
        text = entry.get(field)
        if not text:
            continue
        m = re.search(r'own guide\s*\$?([\d.]+)\s*-\s*\$?([\d.]+)\s*([BM])?',
                      str(text), re.I)
        if m:
            hi = float(m.group(2))
            unit = (m.group(3) or 'B').upper()
            return hi * (1000.0 if unit == 'B' else 1.0)
    return None


def _basis_flips_sign(parsed, entry):
    eps = parsed.get('eps') or {}
    cons = entry.get('epsConsensus')
    if not isinstance(cons, (int, float)):
        return False
    g, ng = eps.get('GAAP'), eps.get('non-GAAP')
    if not (g and ng):
        return False
    return (g['value'] - cons) * (ng['value'] - cons) < 0


# ── row-name qualifiers ──────────────────────────────────────────────────────
#
# ★ A row name must be matched on ALL its distinguishing tokens, never on one.
# "revenue in name" matched Q1 Revenue, Q1 Data Center Revenue, Q1 Client
# Revenue, Q1 Gaming Revenue AND Q1 Embedded Revenue, so a single parsed total
# was written into five rows. Three of them then rendered a MISS against their
# own bogeys when all three had actually cleared.
#
# Generic scaffolding a name carries regardless of WHICH metric it is.
_GENERIC_TOKENS = frozenset((
    'q1', 'q2', 'q3', 'q4', 'f1q', 'f2q', 'f3q', 'f4q', 'fy', 'fy26', 'fy27',
    'total', 'net', 'the', 'and', 'of', 'vs', 'guide', 'guidance', 'outlook',
    'revenue', 'revenues', 'sales', 'eps', 'share', 'per', 'diluted', 'basic',
    'margin', 'gross', 'operating', 'op', 'adj', 'adjusted', 'non', 'gaap',
    'ebitda', 'income', 'earnings', 'current', 'quarter', 'year', 'mid',
    'midpoint', 'street', 'bogey', 'cons', 'consensus', 'fq',
    # ★ Metric ABBREVIATIONS name the metric, they do not distinguish a segment.
    # "Q1 Adj GM (%)" is the company gross margin; "Auto GM ex-credits (%)" is
    # not, and only 'auto'/'ex'/'credits' carry that distinction.
    'gm', 'opm', 'oi', 'ebit', 'fcf',
    # ★ A profile hero name and a keyKPI name are written independently, months
    # apart, and they spell the same metric differently: "Search Revenue Growth
    # YoY" against "Search Rev Growth YoY", "Azure Growth CC" against "Azure FXN
    # Growth", "Gross Margin (%) - current and guided" against "FQ4 Gross
    # Margin (%)". None of that is a difference in WHAT is being measured.
    'rev', 'yoy', 'guided', 'cc', 'fxn', 'ccy', 'constant', 'currency',
    'segment', 'division', 'business', 'unit', 'line',
))

# ★ Tokens that describe the FORM of a metric rather than its subject. A hero
# named "US Commercial Revenue Growth YoY (%)" and a row named "US Commercial
# Revenue ($M)" measure the SAME THING in two shapes -- and since the row
# supplies both the actual and the expectation, that comparison is internally
# consistent. What must never differ is the SUBJECT.
_FORM_TOKENS = frozenset(('growth', 'decline', 'trajectory'))

_TOKEN_RE = re.compile(r'[a-z]{2,}')


# 34 rows across 24 tickers name their margin by abbreviation -- "Q1 Adj GM
# (%)", "F4Q Adj GM Guide (%)", "Auto GM ex-credits (%)" -- and most are graded
# HEROES. A matcher keyed on the literal "gross margin" reaches none of them, so
# every one of those rows read not-found from a release that stated the figure.
_GM_NAME = re.compile(r'\bgross\s+margin\b|\bGM\b', re.I)
_OPM_NAME = re.compile(r'\boperating\s+margin\b|\bOPM\b|\bop\s+margin\b',
                       re.I)


def is_gross_margin_row(name):
    """True for "Gross Margin", "Adj GM", "Non-GAAP GM", "GM Guide"."""
    return bool(_GM_NAME.search(name or ''))


def balance_row(name):
    """True for any row naming ARR, RPO or cRPO -- INCLUDING the ones the dollar
    path must refuse (counts, growth rates). The refusal has to be reached, so
    the predicate is deliberately wider than `classify_row`.
    """
    import re as _re
    return bool(_re.search(r'\bARR\b|\bRPO\b|crpo|annual\s+recurring',
                           name or '', _re.I))


def is_op_income_row(name):
    """True for "Operating Income", "Adj OI", "Op Income", "OI Guide".

    ★ 11 rows in the library name this metric and 4 are graded HEROES, three of
    them AMZN -- where OI is the hero and the Q2 guide's $22B midpoint against a
    $23.85B Q1 base was the whole trade. There was no extractor at all: adjusted
    EBITDA was parsed and operating income was not.

    Checked BEFORE the operating-margin predicate, because "Q2 Adj Op Income
    ($B) / margin (%)" satisfies both and the declared unit settles it -- a
    dollar magnitude is the income line, a percentage is the margin.
    """
    return bool(_OI_NAME.search(name or ''))


_OI_NAME = re.compile(
    r'\boperating\s+income\b|\bop\s+income\b|\bOI\b|'
    r'\bincome\s+from\s+operations\b|\boperating\s+profit\b', re.I)


def op_income_basis(name):
    """The basis a row DEMANDS, or None when it names none.

    Mirrors how EPS is handled: a row naming its basis gets that basis or
    nothing. CBRS-2026Q2 is why -- GAAP missed 7.0% while the company's "core"
    basis beat 9.9%, and the tape traded GAAP.
    """
    low = (name or '').lower()
    if re.search(r'non-?gaap|\badj\b|\badj\.|adjusted', low):
        return 'non-GAAP'
    if 'gaap' in low:
        return 'GAAP'
    return None


def is_operating_margin_row(name):
    """True for "Operating Margin", "OPM", "Op Margin"."""
    return bool(_OPM_NAME.search(name or ''))


#: decoration that must never become a qualifier. PHRASES, not positions.
_DECOR_PHRASE = re.compile(
    r'\bTHE\s+HERO\b|\bTHE\s+EVENT\b|\bTHE\s+KPI(?:\s+IN\s+FOCUS)?\b'
    r'|\bTHE\s+TRADE\b|\bHIGHEST\s+VALUE\b|\bNOISE\b'
    r'|\bREVERSE\s+POLARITY\b|\bIN\s+FOCUS\b|\bINVERTED\s+ROW\b'
    r'|\bWHERE\s+UPSIDE\s+LIVES\b|\bTHE\s+SECOND\s+GATE\b'
    r'|\bDERIVED\b|\bPENDING\b', re.I)


def row_qualifiers(name):
    """Tokens that make this row a SPECIFIC metric rather than the headline one.

    "Q1 Client Revenue ($M)" -> {'client'};  "Q1 Revenue ($B)" -> set().
    A row with qualifiers can only be filled by a figure parsed for THAT
    qualifier -- never by the headline total, and never by a broader fallback.
    """
    # ★ KNOWN DECORATION PHRASES ONLY. "— THE HERO" and "— HIGHEST VALUE"
    # inject `hero`, `highest`, `value` into the qualifier set, so a segment
    # lookup demands words a table can never contain -- SNOW's product revenue
    # is in the table at 1491.861 and was missed solely because `hero` was also
    # required.
    #
    # NOT a blanket em-dash strip: measured over 33 affected rows, several
    # suffixes carry REAL qualifiers ("Custom Silicon Ramp — Trainium / Maia",
    # "pipeline color — UALink / NVLink"), and dropping those leaves an empty
    # core set, which is a subset of everything.
    name = _DECOR_PHRASE.sub(' ', name or '')
    base = re.sub(r'\([^)]*\)', ' ', name or '')          # drop unit parens
    base = base.replace('\u2605', ' ')                     # drop stars
    toks = {t for t in _TOKEN_RE.findall(base.lower())}
    return toks - _GENERIC_TOKENS


def rounding_halfstep_pct(stated, decimals):
    """Half the last stated decimal place, as a PERCENT of the figure.

    ★ A prose segment figure is ROUNDED. "Data Center segment revenue was $5.8
    billion" against a bogey of 5.7 clears by 1.75%, but the sentence only
    resolves the figure to +/-0.05 -- 0.86%. Where the clearance is SMALLER than
    the rounding, the verdict is not determined by the release, and printing a
    green CLEAR would be the same accident as grading a unitless magnitude.
    """
    try:
        stated = float(stated)
        d = int(decimals or 0)
    except (TypeError, ValueError):
        return None
    if stated == 0:
        return None
    return (0.5 * (10.0 ** -d)) / abs(stated) * 100.0


def rounding_ambiguous(pct, halfstep_pct):
    """True when a verdict sits inside the rounding of the figure behind it."""
    if pct is None or halfstep_pct is None:
        return False
    return abs(pct) <= halfstep_pct


class UnitDeclarationError(Exception):
    """A numeric actual reached a scale-declaring row with no actualUnit.

    ★ This is a WRITE-TIME invariant, not a validate-time one. HARD 11 catches
    an undeclared actualUnit when validate_library.py runs; that is hours late.
    At 4:01 PM a "Q1 Revenue ($B)" row holding 10253.0 renders as 10.253 ($B)
    when actualUnit='$M' is declared and as a bare 10,253 when it is not -- and
    BOTH clear a bogey of 10.25, the second one by accident. The accident is the
    danger: it produces a correct grade from a broken pipe, so nothing looks
    wrong until a release where the accident does not hold.
    """


def unit_undeclared(rows):
    """Indices holding a numeric actual in a scale-declaring row, unitless.

    Detection is deliberately BROAD (units.looks_like_dollar_magnitude), so a
    name whose scale is spelled in a form the resolver's closed list does not
    carry -- "($bn)", "(US$M)", "($ in millions)" -- is caught rather than
    silently written without a unit.
    """
    out = {}
    for i, r in enumerate(rows or []):
        if not isinstance(r.get('actual'), (int, float)):
            continue
        if r.get('actualUnit'):
            continue
        if units.looks_like_dollar_magnitude(r.get('name')):
            out[i] = units.declared_scale_token(r.get('name'))
    return out


def assert_units_declared(rows):
    """Hard invariant: nothing survives with a value, a scale and no unit.

    `unit_undeclared` refuses the rows it can explain (an unresolvable scale
    token). Anything still standing here arrived by a path that skipped the
    actualUnit assignment altogether, which is a code defect and must be loud
    rather than rendered.
    """
    bad = unit_undeclared(rows)
    if bad:
        raise UnitDeclarationError(
            'actualUnit missing on %d scale-declaring row(s) after refusal: %s'
            % (len(bad), '; '.join(
                '%r declares %r holding %r'
                % ((rows[i].get('name') or '')[:44], tok, rows[i].get('actual'))
                for i, tok in sorted(bad.items()))))


def hero_scope(name):
    """WHAT a KPI measures, stripped of wording and of metric form.

    ★ This is the definitional-mismatch guard for hero resolution. `Product
    Gross Margin (%)` and `Non-GAAP Gross Margin (%)` are different metrics;
    grading the second against the first's consensus is the mismatch CLAUDE.md
    lists under what must not be automated. Across the library the rule refuses
    exactly one match -- CBRS's `Hardware Revenue ($M)` hero resolving onto the
    TOTAL revenue row -- and leaves eight wording-only matches intact.
    """
    return row_qualifiers(name) - _FORM_TOKENS


# ★ Cosmetics and RANK tokens are not part of a name. A profile hero written
# "🔥 #1 Q4 Adj EPS ($)" and a grid row written "Q4 Adj EPS ($) ★★★" are the same
# metric; the marker and the rank must never reach the matcher.
_MARKERS = re.compile(r'[🔥★⚡✅⛔]+|#\s*\d+', re.U)

# ★ WHAT is being measured, on an axis INDEPENDENT of the subject scope.
#
# hero_scope() deliberately strips every metric word -- 'revenue', 'eps',
# 'margin', 'gm', 'ebitda' are all in _GENERIC_TOKENS -- because a profile hero
# name and a keyKPI name are written months apart and spell the same metric
# differently. That is right for the SUBJECT question ("is this the Auto segment
# or the company?") and catastrophic for the ROW question: it makes the scope of
# "Q4 Adj EPS ($)" and of "Q4 Total Revenue ($B)" both EMPTY, and empty equals
# empty. 19 heroes scope to nothing and 27 of 76 records matched more than one
# row -- ORCL's EPS hero matched 7, including revenue, FCF and gross margin.
#
# So the metric is recovered on its own axis, from the words scope throws away.
# Order matters: the margin forms must be tested before their level forms, and
# EBITDA margin before gross margin, or "Adj EBITDA Margin" reads as a margin
# of the wrong kind.
_METRIC_KINDS = (
    ('ebitdaMargin', re.compile(r'ebitda\s*margin', re.I)),
    ('grossMargin', re.compile(r'gross\s*margin|\bgm\b', re.I)),
    ('opMargin', re.compile(r'operating\s*margin|\bop\s*margin\b|\bopm\b',
                            re.I)),
    ('opIncome', re.compile(r'operating\s+income|\bop\s+income\b|\boi\b'
                            r'|income\s+from\s+operations', re.I)),
    ('ebitda', re.compile(r'\bebitda\b', re.I)),
    ('eps', re.compile(r'\beps\b|earnings\s+per\s+share', re.I)),
    ('fcf', re.compile(r'\bfcf\b|free\s+cash\s+flow', re.I)),
    ('capex', re.compile(r'\bcapex\b|capital\s+expenditure', re.I)),
    ('backlog', re.compile(r'\bbacklog\b', re.I)),
    ('rpo', re.compile(r'\bc?rpo\b|remaining\s+performance', re.I)),
    ('arr', re.compile(r'\barr\b|annual\s+recurring', re.I)),
    ('netIncome', re.compile(r'net\s+income|net\s+profit', re.I)),
    ('revenue', re.compile(r'\brevenues?\b|\brev\b|\bsales\b|\bacv\b',
                           re.I)),
)


def hero_metric_kind(name):
    """WHICH METRIC a name denotes, or None when it names no known metric."""
    n = _MARKERS.sub(' ', name or '')
    for kind, pat in _METRIC_KINDS:
        if pat.search(n):
            return kind
    return None


def hero_scope_matches(hero_name, row_name):
    """True when a row measures the same SUBJECT and the same METRIC.

    Both axes are required. The subject axis alone admitted a gross-margin hero
    onto a revenue row (TSLA: "Auto GM ex-credits" and "Auto Revenue
    ex-credits YoY" share the scope {auto, ex, credits} exactly), and admitted
    every empty-scope hero onto every other empty-scope row.
    """
    if hero_scope(hero_name) != hero_scope(row_name):
        return False
    # ★ THE SAME MODIFIER RULE AS KEY 2, applied here too. hero_scope strips
    # decoration and generic tokens, which makes "AI Semi Revenue" and "Non-AI
    # Semi Revenue" scope-identical -- the exact collision KEY 2 exists to
    # split. One rule, applied everywhere it applies.
    from . import modifiers as _mod
    if _mod.disqualify(hero_name, row_name):
        return False
    h, r = hero_metric_kind(hero_name), hero_metric_kind(row_name)
    # A name with no recognisable metric constrains nothing, so it is not used
    # to REFUSE a subject match -- only to split two subject-identical rows.
    if h is None or r is None:
        return True
    return h == r


#: profile appliesTo -> the period class _classify_period returns
_APPLIES_TO_PERIOD = {
    'currentQuarter': 'CURRENT_Q',
    'nextQGuidance': 'NEXTQ_GUIDE',
    'fyGuidance': 'FY_GUIDE',
}


def hero_period_matches(applies_to, row_name, quarter=None):
    """True when a row sits in the period the profile says the hero grades.

    ★ The third axis, and the one the data handed over for free. 20 of the 76
    heroes matched exactly two rows -- the reported quarter and the guide for
    the same metric -- and `appliesTo` already distinguishes them. Nothing is
    inferred from wording here.

    A hero whose appliesTo is `narrative`, or absent, constrains no period:
    narrative rows are qualitative and do not live on the period axis.
    """
    want = _APPLIES_TO_PERIOD.get(applies_to)
    if want is None:
        return True
    return _classify_period(row_name or '', quarter) == want


def resolve_hero_row(hero_name, row_names, applies_to=None, quarter=None):
    """The ONE row this hero grades, or (None, why).

    ★ A non-unique match is a FAILURE, not a partial success. Taking the first
    of seven is how a hero silently grades the wrong metric, and taking none is
    how it silently falls back to revenue -- which provably cannot reproduce the
    accepted grades (SNDK beat 6.9% and scored +1.0; TSLA beat 0.5% and +2.0).
    """
    hits = [i for i, nm in enumerate(row_names)
            if hero_scope_matches(hero_name, nm or '')
            and hero_period_matches(applies_to, nm, quarter)]
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, ('hero %r matches NO row in this grid — refusing rather '
                      'than falling back to revenue' % hero_name)
    return None, ('hero %r matches %d rows (%s) — AMBIGUOUS, refusing rather '
                  'than grading the first' % (
                      hero_name, len(hits),
                      ', '.join((row_names[i] or '')[:22] for i in hits[:4])))


def duplicate_actuals(rows):
    """Indices whose numeric actual repeats WITHIN one period. Rule imported.

    ★ The decision belongs to render_scorecard._duplicate_actuals and is not
    reimplemented here. Two overlapping fixes for the same defect existed
    briefly -- per-period scoping (mine) and an all-percentage exemption (the
    model repo's) -- and the second was removed because the first subsumes it:
    scoping by period also refuses a SAME-period percentage pair, like Q1 Gross
    Margin 56.0 beside Q1 Op Margin 56.0, which the exemption let through.
    Keeping one rule in one place means there is one reason the behaviour
    exists.

    The imported predicate returns a set of indices; the value and count below
    are computed only to WORD the refusal, and never to decide it.
    """
    from . import scorecard
    predicate = scorecard._renderer_function('_duplicate_actuals')
    rows = rows or []
    pre = [dict(name=(r.get('name') or '')) for r in rows]
    act = [dict(actual=r.get('actual')) for r in rows]

    flagged = predicate(pre, act)
    out = {}
    for i in sorted(flagged):
        v = rows[i].get('actual')
        n = sum(1 for j in flagged if rows[j].get('actual') == v)
        out[i] = (v, n)
    return out


def segment_sum_check(rows, entry):
    """Segments should APPROXIMATELY sum to the total, and never EQUAL it.

    Equality is the duplication signature; a wild sum is a units or scope
    error. Returns a problem string, or None.
    """
    total, segs = None, []
    for r in rows or []:
        name = r.get('name') or ''
        v = gradeable_actual(r)
        if not isinstance(v, (int, float)):
            continue
        if _classify_period(name, entry.get('quarter')) != 'CURRENT_Q':
            continue
        if 'revenue' not in name.lower():
            continue
        if row_qualifiers(name):
            segs.append((name, v))
        elif total is None:
            total = v
    if total is None or len(segs) < 2:
        return None

    if any(abs(v - total) < 1e-9 for _n, v in segs):
        return ('SEGMENT SUM: a segment row EQUALS total revenue (%s) — that is '
                'the duplication signature, not a reading' % total)

    # ★ SEGMENTS ARE NOT ALWAYS A PARTITION. They can NEST. AVGO-2026Q2 carries
    # Semi Solutions 15,009 + Infrastructure Software 7,178 = 22,187, which is
    # the total EXACTLY -- and also AI Semi Revenue 10,800, which is a SUBSET of
    # Semi Solutions. Summing all three double-counts to 149% and this check
    # reported a defect on a record that was perfectly consistent.
    #
    # So the test is not "do all the rows sum to the total" but "is there a
    # subset that does". If one exists, the remaining rows are nested detail and
    # the figures agree. Only when NO subset reconciles does the loose band on
    # the full sum apply.
    n = len(segs)
    if n <= 12:
        tol = max(0.02 * abs(total), 0.02)
        for mask in range(1, 1 << n):
            subtotal = 0.0
            for i in range(n):
                if mask & (1 << i):
                    subtotal += segs[i][1]
            if abs(subtotal - total) <= tol:
                return None          # a partition exists; the rest is nesting

    ssum = sum(v for _n, v in segs)
    if not (0.30 * total <= ssum <= 1.30 * total):
        return ('SEGMENT SUM: no subset of the %d segment rows reconciles to '
                'the headline revenue %s (they total %s, %.0f%%) — check units '
                'and scope' % (n, round(total, 3), round(ssum, 3),
                               ssum / total * 100))
    return None


# --- KPI rows -----------------------------------------------------------------

def _segment_for(parsed, quals):
    """Resolve ONE qualified row against the release. Table first, then prose.

    Returns a dict with value_musd / source / note, or with `ambiguous` set, or
    None when the release simply does not state it.
    """
    # ★ THE MASKED COPY. A span inside quotation marks is a QUOTE whatever it
    # names, and this matcher has no notion of quotation marks -- AVGO's hero
    # sat at chars 1395..1515 inside Tan's quote and came back labelled
    # 'prose (segment)', which put it at precedence rank 2 instead of rank 4.
    text = parsed.get('prose') or parsed.get('text') or ''
    if not text:
        return None
    toks = sorted(quals)

    from .tables import find_segment
    tbl = find_segment(text, toks)
    if tbl is not None:
        return dict(value_musd=tbl['value'], source=tbl['source'],
                    note='parsed from the segment table ($M, declared %s)'
                         % tbl['scale'],
                    stated=None, decimals=None, raw='table', ambiguous=None)

    from .parse import segment_revenue
    pr = segment_revenue(text, toks)
    if pr is None:
        return None
    if pr.get('ambiguous'):
        return pr
    return dict(value_musd=pr['value_musd'], source=pr['source'],
                note='parsed for segment %s from prose ($M, stated in %s)'
                     % ('+'.join(toks), pr.get('unit_seen')),
                stated=pr.get('stated'), decimals=pr.get('decimals'),
                raw=pr.get('raw'), ambiguous=None)


def _balance_for(parsed, name, want_forward=False):
    """ARR / RPO / cRPO / Net-New / run-rate for ONE row. Never a fallback.

    Returns dict(value_musd, source, note, ...) or dict(refused=...) or None.
    The metric the ROW asks for is decided by balances.classify_row, and a count
    row or a growth row never reaches the dollar path at all.
    """
    from . import balances
    text = parsed.get('text') or ''
    metric = balances.classify_row(name)
    if metric is None:
        why = balances.refusal_reason(name)
        return dict(refused=why) if why else None
    if not text:
        return None
    quals = balances.qualifiers(name, row_qualifiers)
    res = balances.parse_balance(text, metric, quals,
                                 want_forward=want_forward, row_name=name)
    if res is None:
        return None
    if res.get('ambiguous'):
        return res
    label = '+'.join(sorted(quals)) or 'total'
    return dict(value_musd=res['value_musd'], source=res['source'],
                note='parsed %s (%s) from prose ($M, stated in %s)'
                     % (metric, label, res.get('unit_seen')),
                stated=res.get('stated'), decimals=res.get('decimals'),
                raw=res.get('raw'), ambiguous=None)


def _segment_ebitda_for(parsed, quals):
    """Resolve a qualified EBITDA row against the release text."""
    text = parsed.get('text') or ''
    if not text:
        return None
    toks = sorted(quals)
    from .parse import segment_adj_ebitda
    se = segment_adj_ebitda(text, toks)
    if se is None:
        return None
    if se.get('ambiguous'):
        return se
    return dict(value_musd=se['value_musd'], source=se['source'],
                note='parsed EBITDA for segment %s from prose ($M)'
                     % '+'.join(toks),
                stated=se.get('stated'), decimals=se.get('decimals'),
                raw=se.get('raw'), ambiguous=None)


def _segment_op_income_for(parsed, quals):
    """Resolve a qualified operating-income row against the release text."""
    text = parsed.get('text') or ''
    if not text:
        return None
    toks = sorted(quals)
    from .parse import segment_op_income
    so = segment_op_income(text, toks)
    if so is None:
        return None
    if so.get('ambiguous'):
        return so
    return dict(value_musd=so['value_musd'], source=so['source'],
                note='parsed OI for segment %s from prose ($M)'
                     % '+'.join(toks),
                stated=so.get('stated'), decimals=so.get('decimals'),
                raw=so.get('raw'), ambiguous=None)


def _segment_margin_for(parsed, quals):
    """Resolve a qualified margin row against the release text."""
    text = parsed.get('text') or ''
    if not text:
        return None
    toks = sorted(quals)
    from .parse import segment_margin
    sm = segment_margin(text, toks)
    if sm is None:
        return None
    if sm.get('ambiguous'):
        return sm
    return dict(value=sm['value'], source=sm['source'],
                note='parsed for %s from prose (%%)' % '+'.join(toks),
                stated=sm.get('stated'), decimals=sm.get('decimals'),
                raw=sm.get('raw'), ambiguous=None)


#: the ratio band a candidate must sit inside, relative to its street value.
#: OUTSIDE this, the value is refused rather than graded.
SCALE_RATIO_LOW = 0.33
SCALE_RATIO_HIGH = 3.0

#: a row whose name declares one of these is a rate, not a magnitude
_PCT_ROW = re.compile(r'\(\s*%\s*\)|\bpercent\b', re.I)

#: per-share rows -- a dividend and an EPS both sit near "per share"
_PER_SHARE_ROW = re.compile(r'\beps\b|earnings\s+per\s+share|per\s+share|'
                            r'per\s+diluted\s+share', re.I)


def gradeable_actual(row):
    """A row's actual AS FAR AS SCORING IS CONCERNED.

    ★ None whenever the value failed the scale guard. kpi_rows is read for
    actuals in five places -- flag counting, hero extraction gaps, the hero
    clearance leg, the consensus-miss count and the next-Q fade zone. If any
    one of them reads `actual` directly, a value too suspect to grade still
    moves a category score. Routed through here so a sixth consumer added later
    inherits the exclusion instead of reintroducing the bug.
    """
    if not row:
        return None
    if row.get('scaleSuspect'):
        return None
    return row.get('actual')


def declared_unit(name):
    """The unit a ROW NAME declares: '$B', '$M', '%', '$' or None."""
    n = name or ''
    if re.search(r'\(\s*\$\s*B\s*\)', n, re.I):
        return '$B'
    if re.search(r'\(\s*\$\s*M\s*\)', n, re.I):
        return '$M'
    if _PCT_ROW.search(n):
        return '%'
    if re.search(r'\(\s*\$\s*\)', n):
        return '$'
    return None


def scale_refusal(name, actual, expected, actual_unit=None):
    """Why this value must NOT be written to this row, or None to allow it.

    ★ Refusing is correct behaviour. A blank row is honest; a wrong row lies
    with a colour on it. HPE reported 🔴 MISS on non-GAAP EPS using 0.1425 --
    the DIVIDEND -- when EPS was 1.11, a beat of $0.18. That inverts the trade.
    """
    if not isinstance(actual, (int, float)):
        return None
    unit = declared_unit(name)

    # ★ RULE (b) IS DELETED. "any value > 100 cannot fill a (%) row" had a 100%
    # false-positive rate over 407 hand-filled rows -- 8 refusals, 8 wrong, 6 of
    # them hero rows: OKTA NRR 107, NET DBNRR 118, MDB NRR 122, PLTR NDR 150 and
    # 157, PLTR US Commercial growth 133. Retention rates EXCEED 100 BY
    # DEFINITION and growth rates routinely do. It also had no unique true
    # positives: rule (c) catches SNOW's 1588 at 52x street.

    # ★ ZERO IS EXEMPT FROM THE RATIO TEST ENTIRELY. A scale error never
    # produces exactly 0.0 -- mis-parses land as 1588, 34800, 0.1425, wrong
    # MAGNITUDES. Zero is a value. AVGO Buyback: street 600, reported nil, and
    # the nil was the finding.
    if actual == 0:
        return None

    if not isinstance(expected, (int, float)) or not expected:
        return None

    # ★ Put both sides on one scale BEFORE dividing. The parser emits $M while
    # a row's street may be stored in $B; comparing raw gives ~1000x on almost
    # every dollar row.
    exp, act = _normalise_pair(expected, actual, name, actual_unit)
    if exp is None or act is None or not exp:
        return None

    # ★ A RATIO IS MEANINGLESS ONCE A SIGN IS INVOLVED.
    if (exp < 0) != (act < 0):
        # A sign flip is never a scale problem -- it is a different quantity.
        # META-2026Q1 stores -4.028 for Daily Active People against a 3.58
        # street; no scale interpretation makes a negative user count valid.
        return ('polarity: sign flip \u2014 street %g, actual %g' % (exp, act))
    if exp < 0 and act < 0:
        # Both negative: skip the ratio entirely. AXTI's non-GAAP EPS improving
        # from -0.04 to -0.01 is a BEAT, and reads as 0.25x.
        return None

    ratio = act / float(exp)

    # ── 2. the per-share case, named explicitly ───────────────────────────
    if unit == '$' and _PER_SHARE_ROW.search(name or ''):
        if ratio < SCALE_RATIO_LOW or ratio > SCALE_RATIO_HIGH:
            return ('scale: per-share %g vs street %g = %.2fx \u2014 a '
                    'per-share row this far from street is usually the '
                    'DIVIDEND or a different share basis, not EPS'
                    % (act, exp, ratio))

    # ── 3. the general band ───────────────────────────────────────────────
    if ratio < SCALE_RATIO_LOW or ratio > SCALE_RATIO_HIGH:
        return ('scale: actual %g vs street %g = %.2fx' % (act, exp, ratio))
    return None


def scale_refusals(rows, pre_rows):
    """{index: reason} for every row whose value fails the scale guard."""
    out = {}
    for i, row in enumerate(rows):
        pre = pre_rows[i] if i < len(pre_rows) else {}
        exp = _row_expected(pre)
        why = scale_refusal(row.get('name'), row.get('actual'), exp,
                            row.get('actualUnit'))
        if why:
            out[i] = why
    return out


def _row_expected(pre_row):
    """The street value for a pre-earnings row, coerced, or None."""
    from . import scorecard as _sc
    val, _strict = _sc.coerce_consensus(_sc.row_cons(pre_row or {}))
    return val if isinstance(val, (int, float)) else None


def build_kpi_rows(parsed, entry):
    """actuals.keyKPIs, index-aligned 1:1 with preEarnings.keyKPIs.

    Built by ITERATING preEarnings.keyKPIs in its stored order. Never from the
    parse order of the release -- that is how a Q4 actual gets filed into an
    "FY27 Revenue + EPS Guide" slot.
    """
    rows = []
    rev = parsed.get('revenue')
    eps = parsed.get('eps') or {}
    margins = parsed.get('margins') or {}
    guides = parsed.get('guidance') or {}
    record_quarter = entry.get('quarter')

    for kpi in entry.get('keyKPIs') or []:
        name = kpi.get('name') or ''
        low = name.lower()
        period = _classify_period(name, record_quarter)
        actual, note = None, 'not found in release'
        # ★ What the scraper actually READ for this row, so a grade can never
        # be mistaken for a reading that never happened.
        src = 'not-found'
        # Set only when the figure came from a ROUNDED prose statement, so its
        # precision can be weighed against the clearance margin.
        seg_precision = None
        # ★ Which basis was actually READ. Recorded on every row so a wrong one
        # is visible on the card rather than inferred from the number.
        basis_read = None
        # ★ Which period class the value was read under, so a refusal can name
        # it instead of leaving the trader to guess.
        periodRead = None
        # ★ Set when a candidate's period could NOT be checked because level 2
        # is unbuilt -- an honest record of an unenforced row, not a pass.
        periodGap = False
        # ★ The TEXT that was matched, so KEY 2 can compare modifier sets. The
        # row name alone cannot disqualify anything -- the asymmetry is between
        # the row and what was actually read.
        cand_label = None

        # ★ A qualified row (Client / Gaming / Data Center / Embedded ...) can
        # only be filled from a figure parsed for that qualifier. We do not
        # parse segments, so it stays not-found rather than inheriting the
        # headline total.
        quals = row_qualifiers(name)

        if period == 'CURRENT_Q':
            # ★ ARR / RPO / cRPO FIRST. These rows often also contain the word
            # "revenue" ("Revenue backlog / RPO ($B)"), so the generic revenue
            # leg would otherwise claim them and write a total-revenue figure
            # into an RPO row.
            _bal = (_balance_for(parsed, name)
                    if balance_row(name) else None)
            if _bal is not None:
                if _bal.get('refused'):
                    note = '⛔ NOT GRADED — %s' % _bal['refused']
                    src = 'metric-kind-refused'
                elif _bal.get('ambiguous'):
                    note = ('%s matched %d different values — refusing to '
                            'choose (%s)' % (name[:30], len(_bal['ambiguous']),
                                             _bal['ambiguous']))
                    src = 'balance-ambiguous'
                elif _bal.get('value_musd') is not None:
                    actual = _bal['value_musd']
                    note = _bal['note']
                    src = _bal['source']
                    seg_precision = _bal
            elif balance_row(name):
                note = ('%s not stated in the release — refusing the generic '
                        'revenue figure, which is a different metric'
                        % name[:40])

            # ★ A QUALIFIED revenue row is filled from a figure parsed FOR that
            # qualifier -- never from the headline total, and never from a
            # broader match. The table is preferred over prose here because the
            # table states 5,775 where the prose rounds to "$5.8 billion".
            if balance_row(name):
                pass                      # already handled above, never fall through
            elif 'revenue' in low and quals:
                seg = _segment_for(parsed, quals)
                if seg and seg.get('value_musd') is not None:
                    actual = seg['value_musd']
                    # ★ KEY 2 needs the matched TEXT. "Q3 AI semiconductor
                    # revenue of $16.7 billion" carries `ai`+`semi` and no
                    # negation, so a "Non-AI Semi Revenue" row disqualifies it
                    # on `non-ai` -- independent of how far apart the two
                    # numbers happen to be.
                    cand_label = seg.get('raw')
                    note = seg.get('note') or 'parsed for segment %s ($M)' % (
                        '+'.join(sorted(quals)))
                    src = seg.get('source')
                    seg_precision = seg
                elif seg and seg.get('ambiguous'):
                    note = ('segment %s matched %d different values in the '
                            'release - refusing to choose (%s)'
                            % ('+'.join(sorted(quals)), len(seg['ambiguous']),
                               seg['ambiguous']))
                    src = 'segment-ambiguous'
            elif 'revenue' in low and rev and not quals:
                actual, note = rev['value_musd'], 'parsed from release ($M)'
                src = rev.get('source') or 'prose'
            elif ('eps' in low or 'earnings per share' in low) and eps:
                # ★ ONE selector for every basis-sensitive metric. The old
                # inline version knew 'non-gaap' and 'gaap' but NOT 'adj' --
                # which is 61 of the 107 rows that declare a basis, three
                # fifths of them invisible to it.
                _pick, _b, _note = basis_mod.select(
                    name, {k: v['value'] for k, v in eps.items()})
                basis_read = _b
                if _pick is not None:
                    actual = _pick
                    note = 'parsed from release — %s' % _note
                    src = 'prose'
                elif _note:
                    note = _note
                    src = 'basis-refused'
            elif 'ebitda' in low:
                if quals:
                    # ★ A qualified EBITDA row is a different measure from the
                    # company figure -- same rule as revenue, margin and OI.
                    se = _segment_ebitda_for(parsed, quals)
                    if se and se.get('value_musd') is not None:
                        actual, note, src = (se['value_musd'], se['note'],
                                             se['source'])
                        seg_precision = se
                    elif se and se.get('ambiguous'):
                        note = ('segment EBITDA for %s matched %d values - '
                                'refusing to choose'
                                % ('+'.join(sorted(quals)),
                                   len(se['ambiguous'])))
                        src = 'segment-ambiguous'
                    else:
                        note = ('qualified EBITDA row (%s) - the release states '
                                'no EBITDA for this qualifier'
                                % '+'.join(sorted(quals)))
                elif parsed.get('adjEbitda'):
                    _eb = parsed.get('adjEbitdaByBasis') or {
                        parsed.get('adjEbitdaBasis') or 'unknown':
                        parsed['adjEbitda']['value_musd']}
                    _pick, _b, _note = basis_mod.select(name, _eb)
                    basis_read = _b
                    if _pick is not None:
                        actual = _pick
                        src = parsed['adjEbitda'].get('source') or 'prose'
                        note = 'parsed from release ($M) — %s' % _note
                    elif _note:
                        note = _note
                        src = 'basis-refused'
            elif (is_op_income_row(name)
                  and units.is_dollar_magnitude(name)):
                want = op_income_basis(name)
                oi = parsed.get('opIncome') or {}
                if quals:
                    # ★ "Cloud OI ($B)" is a SEGMENT line. The company's
                    # operating income is a different metric and must never
                    # fill it -- the same rule the revenue and margin rows now
                    # carry.
                    so = _segment_op_income_for(parsed, quals)
                    if so and so.get('value_musd') is not None:
                        actual = so['value_musd']
                        note = so['note']
                        src = so['source']
                        seg_precision = so
                    elif so and so.get('ambiguous'):
                        note = ('segment OI for %s matched %d different values '
                                '- refusing to choose (%s)'
                                % ('+'.join(sorted(quals)),
                                   len(so['ambiguous']), so['ambiguous']))
                        src = 'segment-ambiguous'
                    else:
                        note = ('qualified operating-income row (%s) - the '
                                'release states no OI for this qualifier, and '
                                'company OI is a different metric'
                                % '+'.join(sorted(quals)))
                else:
                    _pick, _b, _note = basis_mod.select(
                        name, {k: v['value_musd'] for k, v in oi.items()})
                    basis_read = _b
                    if _pick is not None:
                        actual = _pick
                        note = 'parsed from release ($M) — %s' % _note
                        src = 'prose'
                    elif _note:
                        note = _note
                        src = 'basis-refused'
            elif is_gross_margin_row(name) or is_operating_margin_row(name):
                which = ('grossMargin' if is_gross_margin_row(name)
                         else 'operatingMargin')
                if quals:
                    # ★ A QUALIFIED margin row is a different metric from the
                    # company margin. Filling "Auto GM ex-credits (%)" or
                    # "Product Gross Margin (%)" from the consolidated figure is
                    # a definitional mismatch, not an approximation.
                    sm = _segment_margin_for(parsed, quals)
                    if sm and sm.get('value') is not None:
                        actual = sm['value']
                        note = sm['note']
                        src = sm['source']
                        seg_precision = sm
                    elif sm and sm.get('ambiguous'):
                        note = ('margin for %s matched %d different values - '
                                'refusing to choose (%s)'
                                % ('+'.join(sorted(quals)),
                                   len(sm['ambiguous']), sm['ambiguous']))
                        src = 'segment-ambiguous'
                    else:
                        note = ('qualified margin row (%s) - the release states '
                                'no margin for this qualifier, and the company '
                                'margin is a different metric'
                                % '+'.join(sorted(quals)))
                elif which in margins:
                    # ★ KEY 1 BEFORE THE METRIC. The row's period must match
                    # the scope in force where the value was found, or the
                    # value is not written. HPE's 14% sits under "Fiscal 2027
                    # Outlook Framework" and SNOW's 15.5% under "For the third
                    # quarter of fiscal 2027, the company expects" -- neither
                    # carries a marker in its own span, which is why a wider
                    # window cannot fix this and a register can.
                    # ★ PROSE ONLY, for now. A TABLE candidate carries
                    # offset=None and raw='table', so it classifies UNRESOLVED
                    # -- not because the document is ambiguous but because
                    # precedence level 2 (the column header) is NOT BUILT.
                    # Refusing on that is refusing on my own ignorance.
                    #
                    # It cost SNDK-2026Q4 its gross margin (84.6, table) and
                    # falsified the PR-only ceiling theorem: currentQuarter
                    # fell +1.0 -> +0.0, two notches BELOW the hand read.
                    _msrc = margins[which].get('source')
                    _from_table = (_msrc == 'table'
                                   or margins[which].get('offset') is None)
                    if _from_table:
                        _pcls, _psrc = None, 'table (level 2 not built)'
                        periodRead = None
                        periodGap = True
                    else:
                        _pcls, _psrc = period_mod.classify_at(
                            parsed.get('text') or '',
                            margins[which].get('offset') or 0,
                            fragment=margins[which].get('raw'),
                            register=parsed.get('periodRegister'))
                    if _pcls is not None and not period_mod.may_fill(
                            period, _pcls):
                        note = period_mod.refusal_note(period, _pcls)
                        src = 'period-refused'
                        periodRead = _pcls
                        actual = None
                        margins = dict(margins)
                        margins.pop(which, None)
                    _by = (margins.get(which) or {}).get('byBasis') or {}
                    if which not in margins:
                        _avail = {}
                    else:
                        _avail = ({k: v['value'] for k, v in _by.items()}
                                  if _by else
                                  {margins[which].get('basis') or 'unknown':
                                   margins[which]['value']})
                    _pick, _b, _note = ((None, None, None) if not _avail
                                        else basis_mod.select(name, _avail))
                    basis_read = _b
                    if _pick is not None:
                        actual = _pick
                        note = 'parsed from release — %s' % _note
                        src = margins[which].get('source') or 'prose'
                    elif _note:
                        note = _note
                        src = 'basis-refused'
        else:
            # A CURRENT_Q parse may ONLY fill a CURRENT_Q slot.
            note = 'forward-period slot (%s) - not filled from reported actuals' % period
            if balance_row(name):
                _bal = _balance_for(parsed, name, want_forward=True)
                if _bal and _bal.get('value_musd') is not None:
                    actual = _bal['value_musd']
                    note = '%s guide: %s' % (period, _bal['note'])
                    src = 'prose (guidance)'
                    seg_precision = _bal
                elif _bal and _bal.get('refused'):
                    note = '⛔ NOT GRADED — %s' % _bal['refused']
                    src = 'metric-kind-refused'
                else:
                    note = ('%s guide not stated in the release' % name[:40])
                g = None
            else:
                g = (guides.get('fy') if period == 'FY_GUIDE'
                     else guides.get('nextQ'))
            # ★ A metrics-only block carries no midpoint. Writing None into a
            # revenue row is correct (not-found); writing 0 or guessing is not.
            if g and 'revenue' in low and g.get('mid') is not None:
                actual = g['mid']
                cand_label = g.get('raw')
                note = '%s midpoint parsed from release (%s-%s)' % (
                    period, g['low'], g['high'])
                src = 'prose (guidance)'
            elif (g and 'ebitda' in low and not quals
                  and g.get('ebitdaMid') is not None):
                actual = g['ebitdaMid']
                note = ('%s EBITDA guide midpoint parsed from the release '
                        '(%s-%s)' % (period, g.get('ebitdaLow'),
                                     g.get('ebitdaHigh')))
                src = 'prose (guidance)'
            elif (g and is_op_income_row(name) and not quals
                  and units.is_dollar_magnitude(name)
                  and g.get('opIncomeMid') is not None):
                # ★ The MIDPOINT. AMZN guides OI as a range and the consensus is
                # a midpoint; taking the $24B high end instead reads the guide
                # as a beat when the record grades it a miss.
                actual = g['opIncomeMid']
                note = ('%s operating-income guide midpoint parsed from the '
                        'release (%s-%s)' % (period, g.get('opIncomeLow'),
                                             g.get('opIncomeHigh')))
                src = 'prose (guidance)'
            elif (g and is_gross_margin_row(name) and not quals
                  and g.get('grossMarginPct') is not None):
                actual = g['grossMarginPct']
                note = '%s gross-margin guide parsed from the release' % period
                src = 'prose (guidance)'
            elif g and ('eps' in low or 'earnings per share' in low)                     and g.get('epsMid') is not None:
                actual = g['epsMid']
                note = '%s EPS guide parsed from the release' % period
                src = 'prose (guidance)'

        cons, bogey = kpi.get('consensus'), kpi.get('bogey')
        # The live parser always emits $M for a dollar magnitude, so declare it.
        src_unit = ('$M' if (actual is not None
                             and units.is_dollar_magnitude(name)) else None)
        pct_c = pct_b = None
        if actual is not None and isinstance(cons, (int, float)):
            e, a = _normalise_pair(cons, actual, name, src_unit)
            if e is not None:
                pct_c, flag = pct_delta(a, e)
                if flag:
                    note += ' | ' + flag
        if actual is not None and isinstance(bogey, (int, float)):
            e, a = _normalise_pair(bogey, actual, name, src_unit)
            if e is not None:
                pct_b, _ = pct_delta(a, e)
        if cons is not None and not isinstance(cons, (int, float)):
            note += ' | consensus is text, grade manually'

        # ★ A verdict inside the rounding of its own source figure is not a
        # reading of the release.
        hs = None
        if seg_precision is not None:
            hs = rounding_halfstep_pct(seg_precision.get('stated'),
                                       seg_precision.get('decimals'))
        rounding_note = ''
        if hs is not None:
            for label, pct in (('bogey', pct_b), ('consensus', pct_c)):
                if rounding_ambiguous(pct, hs):
                    rounding_note += (
                        ' | \u26a0 vs %s (%+.2f%%) is INSIDE the rounding of '
                        '"%s" (+/-%.2f%%) - the release does not resolve this '
                        'verdict' % (label, pct, seg_precision.get('raw', '')[:40],
                                     hs))
                    if label == 'bogey':
                        pct_b = None
                    else:
                        pct_c = None
        note += rounding_note

        rows.append(dict(
            name=name,
            consensus=cons,
            bogey=bogey,
            actual=actual,
            pctVsCons=pct_c,
            pctVsBogey=pct_b,
            vsCons=verdict_for(pct_c) if pct_c is not None else 'N/A',
            vsBogey=verdict_for(pct_b) if pct_b is not None else '—',
            vsConsNote=note,
            vsBogeyNote='',
            hero='★' in name,
            period=period,
            forward=period != 'CURRENT_Q',
            extractionSource=src,
            basisDeclared=basis_mod.declared(name),
            basisRead=basis_read,
            basisSensitive=basis_mod.is_sensitive(name),
            periodRead=periodRead,
            rowPeriod=period,
            periodUnchecked=periodGap,
            candidateLabel=cand_label,
            unverified=bool(kpi.get('unverified')),
            # The parser normalises every dollar magnitude to $M, so the live
            # path DECLARES its unit rather than leaving it to be resolved.
            actualUnit=('$M' if (actual is not None
                                 and units.is_dollar_magnitude(name))
                        else None),
            unitAmbiguous=False,
            # ★ Spec step 8: '— · ungraded' tells the trader nothing. A reason
            # tells him whether to hand-fill it in the ninety seconds he has.
            ungradedReason=(None if actual is not None else note),
            scaleRejected=None,
            scaleSuspect=False,
            modifierRejected=None,
            zeroReported=False,
        ))

    # ★ Refuse a value whose SCALE was declared in the row name but could not
    # be resolved. Writing it unitless is what turns 10.253 ($B) into a bare
    # 10,253 that grades CLEAR by accident.
    # ★ SCALE GUARD (spec step 1). Runs BEFORE the unit-undeclared pass so a
    # value refused on scale is reported as a scale problem rather than a unit
    # one -- the trader needs to know WHICH, to decide whether to hand-fill.
    # ★ A REPORTED NIL GETS ITS OWN VERDICT. Not a blank (which loses the
    # finding) and not a MISS (which buries a deliberate capital-allocation
    # change under the same colour as a shortfall).
    for i, row in enumerate(rows):
        if row.get('actual') == 0 and not row.get('scaleSuspect'):
            row['vsBogey'] = 'ZERO'
            row['vsCons'] = 'N/A'
            row['pctVsCons'] = None
            row['pctVsBogey'] = None
            row['zeroReported'] = True
            row['ungradedReason'] = 'reported nil'
            row['vsConsNote'] = (
                'REPORTED NIL \u2014 the value is 0, which is a reading and '
                'not a scale error: a mis-parse lands as a wrong MAGNITUDE '
                '(1588, 34800, 0.1425), never as exactly zero. Shown as ZERO '
                'rather than MISS because a deliberate nil is a finding in its '
                'own right.')

    # ★ periodUnchecked, OVER EVERY BRANCH. It was set only inside the margin
    # branch, so (a) counted 1 row when table-sourced revenue, EPS and segment
    # values were passing unflagged. Same twelve-elif problem the scale guard
    # and KEY 2 already solved by living here.
    #
    # A row is unchecked when its value came from a TABLE and no period class
    # was established: precedence level 2 (the column header) is what would
    # resolve it, and level 2 is not built.
    for row in rows:
        if row.get('actual') is None:
            continue
        _src = str(row.get('extractionSource') or '')
        if 'table' in _src and not row.get('periodRead'):
            row['periodUnchecked'] = True

    # ★ KEY 2, over every branch at once. A modifier on EITHER side and absent
    # from the other disqualifies: AVGO [10] has `non-ai` on the ROW, AVGO [1]
    # has `ai` on the ROW, HPE [8] has `dividend` on the CANDIDATE. One rule,
    # three directions.
    for i, row in enumerate(rows):
        label = row.get('candidateLabel')
        if not label or row.get('actual') is None:
            continue
        why = modifiers_mod.refusal_note(row.get('name') or '', label)
        if not why:
            continue
        row['modifierRejected'] = row['actual']
        row['actual'] = None
        row['pctVsCons'] = None
        row['pctVsBogey'] = None
        row['vsCons'] = 'N/A'
        row['vsBogey'] = '\u2014'
        row['extractionSource'] = 'modifier-refused'
        row['ungradedReason'] = why
        row['vsConsNote'] = (
            '\u26d4 NOT GRADED \u2014 %s' % why)

    for i, why in scale_refusals(rows, entry.get('keyKPIs') or []).items():
        polarity = why.startswith('polarity:')
        # ★ THE VALUE STAYS VISIBLE. A blank tells the trader nothing; "267
        # SCALE? (4.05x street)" tells him CRWV genuinely beat 4x in two
        # seconds, and "0.1425 SCALE? (0.15x — the DIVIDEND)" tells him it is
        # garbage. The bug was never the number being visible, it was a
        # CONFIDENT VERDICT on an unvalidated number.
        #
        # A POLARITY flip is different: a sign mismatch is not the same
        # quantity at all, so that value is NOT written.
        if polarity:
            rows[i]['scaleRejected'] = rows[i]['actual']
            rows[i]['actual'] = None
            rows[i]['vsBogey'] = 'POLARITY'
            rows[i]['extractionSource'] = 'polarity-refused'
        else:
            rows[i]['scaleRejected'] = rows[i]['actual']
            rows[i]['vsBogey'] = 'SCALE?'
            rows[i]['extractionSource'] = 'scale-unvalidated'
        rows[i]['pctVsCons'] = None
        rows[i]['pctVsBogey'] = None
        rows[i]['vsCons'] = 'N/A'
        rows[i]['ungradedReason'] = why
        # ★ Excluded from every category score and from beatMagnitude. A score
        # resting on a value too suspect to grade is a fabricated score
        # (non-negotiable 7).
        rows[i]['scaleSuspect'] = True
        rows[i]['vsConsNote'] = (
            '\u26d4 NOT GRADED \u2014 %s. The value is shown so it can be '
            'read at a glance, but it is EXCLUDED from every category score: a '
            'confident verdict on an unvalidated number is the original bug.'
            % why)

    # ★★ QUOTE PASS — LAST, AND STILL FILTERED.
    #
    # Runs after every branch and after the scale / KEY 2 / period post-passes,
    # so it sees only rows nothing else could fill. That is what makes it
    # lowest precedence, per precedenceMustTrackReliability: a CEO naming a
    # figure is maximally SPECIFIC and less RELIABLE than a reconciliation
    # table, because executives round and tables do not (SNOW: quote "$1.49
    # billion" vs table 1,491.9, 0.94% apart).
    #
    # Being last does NOT make it privileged: KEY 1, KEY 2 and the scale guard
    # all still apply to a quote candidate.
    _qtext = parsed.get('text') or ''
    _qreg = parsed.get('periodRegister')
    if _qtext:
        for i, row in enumerate(rows):
            # ★ ONLY A HELD VALUE CLOSES A ROW. A row whose earlier candidate
            # was DISQUALIFIED is still open: excluding a candidate must not
            # exclude its slot, or filter-then-rank is inverted at the row
            # level. AVGO [1] disqualifies 34,800 on `ai` and must still be
            # free to take the legitimate 21.7 from the quote.
            #
            # A scale-unvalidated row DOES hold a value (shown as SCALE?), so
            # overwriting it would discard what the trader is meant to see.
            if row.get('actual') is not None or row.get('scaleSuspect'):
                continue
            nm = row.get('name') or ''
            want_pct = declared_unit(nm) == '%'
            pre = (entry.get('keyKPIs') or [None] * len(rows))[i] or {}
            exp = _row_expected(pre)
            rper = row.get('rowPeriod') or _classify_period(
                nm, entry.get('quarter'))
            for cand in quotes_mod.for_row(_qtext, nm, want_pct=want_pct):
                cls, csrc = period_mod.classify_at(
                    _qtext, cand['offset'], fragment=cand['sentence'],
                    register=_qreg)
                if not period_mod.may_fill(rper, cls):
                    continue
                if modifiers_mod.disqualify(nm, cand['sentence']):
                    continue
                val = cand['value_musd']
                if scale_refusal(nm, val, exp, '$M' if not want_pct else None):
                    continue
                row['actual'] = val
                row['actualUnit'] = None if want_pct else '$M'
                row['extractionSource'] = 'quote'
                row['periodRead'] = cls
                row['candidateLabel'] = cand['sentence']
                row['ungradedReason'] = None
                row['vsConsNote'] = (
                    'parsed from an EXECUTIVE QUOTE (%s, %s) \u2014 lowest '
                    'precedence: filled only because no table or prose source '
                    'carried it. Quotes are ROUNDED, so a table figure always '
                    'wins.' % (cand['raw'], cls))
                break

    for i, tok in unit_undeclared(rows).items():
        rows[i]['actual'] = None
        rows[i]['pctVsCons'] = None
        rows[i]['pctVsBogey'] = None
        rows[i]['vsCons'] = 'N/A'
        rows[i]['vsBogey'] = '\u2014'
        rows[i]['extractionSource'] = 'unit-undeclared'
        rows[i]['ungradedReason'] = (
            'unit: the row declares its scale as %r and this build cannot '
            'resolve it \u2014 a unitless magnitude grades correctly only by '
            'accident' % tok)
        rows[i]['unitAmbiguous'] = True
        rows[i]['vsConsNote'] = (
            '\u26d4 NOT GRADED \u2014 the row name declares its scale as %r, '
            'which this build cannot resolve, so the value carries no unit. A '
            'unitless magnitude grades correctly only by accident.' % tok)

    # ★ Refuse duplicated actuals BEFORE the rows are written or graded.
    dupes = duplicate_actuals(rows)
    for i, (val, n) in dupes.items():
        rows[i]['actual'] = None
        rows[i]['pctVsCons'] = None
        rows[i]['pctVsBogey'] = None
        rows[i]['vsCons'] = 'N/A'
        rows[i]['vsBogey'] = '—'
        rows[i]['extractionSource'] = 'duplicate-refused'
        rows[i]['ungradedReason'] = (
            'duplicate: %s appeared in %d rows \u2014 one figure in two rows '
            'is a matcher, not a reading' % (val, n))
        rows[i]['vsConsNote'] = (
            '⛔ NOT GRADED — the value %s appeared in %d rows, so it is a '
            'matcher firing too widely rather than a reading' % (val, n))

    assert_units_declared(rows)
    assert_alignment(entry.get('keyKPIs') or [], rows)
    return rows


def assert_alignment(pre_kpis, actual_rows):
    """Fail loudly rather than write a mismatch.

    A missing or short actuals.keyKPIs renders blank rows with default INLINE
    verdicts AND still returns a healthy character count. That silent failure
    broke 12 records while the render test passed.
    """
    if len(pre_kpis) != len(actual_rows):
        raise AlignmentError(
            'actuals.keyKPIs length %d != preEarnings.keyKPIs length %d -- '
            'refusing to emit a misaligned grid'
            % (len(actual_rows), len(pre_kpis)))


# --- the extraction gate (non-negotiable 7) -----------------------------------

_CATEGORY_PERIOD = {'currentQuarter': 'CURRENT_Q',
                    'nextQGuidance': 'NEXTQ_GUIDE',
                    'fyGuidance': 'FY_GUIDE'}


def hero_extraction_gaps(entry, kpi_rows, category):
    """Priority-1 hero rows feeding `category` that FAILED TO EXTRACT.

    ★ A category whose graded row did not parse must DEFER, not score. WDC
    would otherwise display nextQ +1.00 on a stock that fell 13.03%: its
    forward gross-margin guide -- one of two priority-1 nextQ heroes -- never
    extracted, and the remaining revenue row scored on its own. A score resting
    on a row that did not parse is a fabricated score, non-negotiable 7.

    Two deliberate exclusions:

    * A hero with NO keyKPI slot is not an extraction failure -- the card never
      offered a row to read. CSCO's Product Gross Margin has no slot and no
      published consensus at all, and the documented behaviour there is the
      revenue fallback.
    * A row flagged `unverified` is excluded: its EXPECTED column is already
      untrusted and the reference excludes it too, so deferring on it would
      conflate a bad expectation with a failed extraction.
    """
    want = _CATEGORY_PERIOD.get(category)
    if not want:
        return []
    record_quarter = entry.get('quarter')
    heroes = [h for h in (entry.get('allHeroes') or [])
              if h.get('priority') == 1 and h.get('appliesTo') == category]
    if not heroes:
        return []

    by_name = {r.get('name'): r for r in (kpi_rows or [])}
    gaps = []
    for hero in heroes:
        for kpi in entry.get('keyKPIs') or []:
            name = kpi.get('name') or ''
            if _classify_period(name, record_quarter) != want:
                continue
            if not _name_matches_any(name, {hero.get('name')}):
                continue
            row = by_name.get(name) or {}
            if row.get('unverified') or kpi.get('unverified'):
                break
            if gradeable_actual(row) is None:
                gaps.append(dict(hero=hero.get('name'), row=name,
                                 extractionSource=(row.get('extractionSource')
                                                   or 'not-found')))
            break
    return gaps


def lower_is_better(kpi):
    """True when the bogey's operator says a SMALLER number is the good one."""
    return (kpi or {}).get('bogeyDirection') == 'lower'


def clears_consensus(actual, kpi, pct=None):
    """Did `actual` BEAT the street on this row, honouring operator AND direction.

    ★ A tie against a strict threshold is a MISS. '>12' with an actual of 12.0
    does not clear, and the fade zone requires a genuine beat -- so the strict
    flag has to reach the comparison, not just the display.

    ★ AND DIRECTION INVERTS THIS LEG TOO. On a '<25%' concentration bar, 24
    against a street of 26 BEATS the street; comparing `actual > cons` calls it
    a miss. Inverting only the bogey leg is worse than not inverting at all,
    because the consensus check fires first and the row then reports the wrong
    direction while looking handled.
    """
    cons = kpi.get('consensus')
    if not isinstance(actual, (int, float)) or not isinstance(cons,
                                                             (int, float)):
        return None
    lower = lower_is_better(kpi)
    if kpi.get('consensusStrict'):
        return actual < cons if lower else actual > cons
    return actual <= cons if lower else actual >= cons


def clears_bogey(actual, kpi):
    """Did `actual` clear the BAR, in the direction the operator declares."""
    bogey = kpi.get('bogey')
    if not isinstance(actual, (int, float)) or not isinstance(bogey,
                                                             (int, float)):
        return None
    return actual <= bogey if lower_is_better(kpi) else actual >= bogey


def next_q_fade_zone(entry, kpi_rows):
    """True when a priority-1 next-Q guide row beats street but misses bogey.

    ★ Cohort context only. The score stays exactly what the band table says.

    Measured n=10: a next-Q guide in this configuration resolved DOWN 8 of 10,
    mean -3.23%, while the band table assigns the same configuration a mean
    score of +0.60. The verdict cell calls it 🟡 FADE and the category score
    calls it bullish -- opposite readings of identical inputs, and the tape
    sides with the verdict cell.

    Deliberately NOT acted on:
      * the band table is not rewritten -- n=10 would reprice the library and
        move the 5 pinned regression cases;
      * the category is not deferred -- a deferral costs the 0.80 bracket and
        buys a 47% coin flip, so a qualified score beats a blank.

    ★ STRICT >, not >=. "Beats street" excludes a tie, and the framework's
    three states (clears bogey / fade zone / misses street) do not partition the
    space -- an exact tie to consensus is a FOURTH state. It routes to
    `nextQInline` instead, where the Peak-Cycle Buyside-Inline Fade rule and
    fyInlineIsBearish already cover it.

    A tolerance band around consensus was rejected: an epsilon fitted to two
    records is a knob that silently moves base rates later.

    Returns (fired, inline, evidence).
    """
    record_quarter = entry.get('quarter')
    by_name = {r.get('name'): r for r in (kpi_rows or [])}

    for kpi in entry.get('keyKPIs') or []:
        name = kpi.get('name') or ''
        # ★ CLASSIFY THE PERIOD BEFORE MATCHING THE METRIC WORD
        # (non-negotiable 2). The cohort is a NEXT-QUARTER guide, so an FY row
        # must never enter it -- AMD's "FY26 Revenue Guide", WDAY's "FY27 FCF"
        # and CRM's forward FCF row all reached the metric test. They were then
        # refused as unit-ambiguous so nothing broke, but that is luck, not a
        # guard. Excluded explicitly and on the NAME as well as the
        # classification, since a row can carry FY semantics without an FY
        # token (CRM's "FCF Guide ($B)").
        if _classify_period(name, record_quarter) != 'NEXTQ_GUIDE':
            continue
        # FY exclusion, but ONLY when the name carries no quarter token --
        # "Q1 FY27 Revenue Guide" is next-quarter, not full-year.
        if _FY_IN_NAME.search(name) and not _period_tokens(name)[0]:
            continue
        # ★ marks priority 1 (SKILL.md §6). Matching the PROFILE hero name
        # instead detects only 4 of the 10 known records, because some tickers
        # carry no nextQGuidance hero at all -- AMD-2026Q2 has none, yet its
        # "Q3 Revenue Guide ($B) ★★★" row is squarely in the configuration.
        if '★' not in name:
            continue
        # ★ REVERSE POLARITY: excluded, never inverted. This is the founding
        # case -- META-2026Q2 entered the cohort on "FY26 Capex Guide ($B) ★★
        # REVERSE POLARITY" at +1.26% vs consensus, an OVERSHOOT read as a
        # beat, and it moved a base rate already rendering on live cards.
        if is_reverse_polarity(name):
            continue
        row = by_name.get(name) or {}
        actual = gradeable_actual(row)
        cons, bogey = kpi.get('consensus'), kpi.get('bogey')
        if not all(isinstance(v, (int, float)) for v in (actual, cons, bogey)):
            continue
        au = row.get('actualUnit')
        c_norm, a_norm = _normalise_pair(cons, actual, name, au)
        b_norm, _a2 = _normalise_pair(bogey, actual, name, au)
        if None in (c_norm, a_norm, b_norm):
            continue
        # ★ On a lower-is-better row the percentage deltas keep their arithmetic
        # sign but the VERDICT flips, so the legs are evaluated through the
        # directional predicates rather than from the sign of the delta.
        lower = lower_is_better(kpi)
        ev = dict(
            row=name, actual=a_norm, consensus=c_norm, bogey=b_norm,
            lowerIsBetter=lower,
            pctVsCons=round((a_norm - c_norm) / abs(c_norm) * 100, 2),
            pctVsBogey=round((a_norm - b_norm) / abs(b_norm) * 100, 2))

        # An exact tie is its own state -- neither a beat nor a miss. Against a
        # STRICT street ('>12') a tie is not even inline, it is a miss, so it
        # must not be routed to the inline reading either.
        if a_norm == c_norm and a_norm < b_norm:
            if kpi.get('consensusStrict'):
                return False, False, ev
            return False, True, ev
        # beats street (STRICTLY) AND misses bogey -- in the row's direction
        beats = (a_norm < c_norm) if lower else (a_norm > c_norm)
        misses_bogey = (a_norm > b_norm) if lower else (a_norm < b_norm)
        if beats and misses_bogey:
            return True, False, ev
    return False, False, None


def _gap_reason(category, gaps):
    return ('DEFERRED — %d priority-1 hero row(s) feeding %s did not extract '
            'from the release: %s. A score resting on a row that did not parse '
            'is a fabricated score (non-negotiable 7), so the bracket widens '
            'and the published cohort base rates do not apply.'
            % (len(gaps), category,
               '; '.join('%s → %s [%s]' % (g['hero'][:30], g['row'][:30],
                                           g['extractionSource'])
                         for g in gaps)))


# --- category grading ---------------------------------------------------------

def _fmt_num(v):
    if isinstance(v, (int, float)):
        return ('%.4f' % v).rstrip('0').rstrip('.')
    return 'n/a'


def _derivation_phrase(hero_name, derivation, source_name, lower_authority):
    """State WHICH figure was read and by WHICH path, never just the hero name.

    A reason line that names only the profile's hero cannot be distinguished
    from one that graded the revenue fallback -- and when the two percentages
    agree to two decimals, as they did on CSCO, nothing in the output reveals
    which happened.
    """
    hero = (hero_name or 'unnamed hero')[:34]
    if derivation == 'revenue-fallback':
        phrase = ('hero %r HAS NO CURRENT-Q ROW -> REVENUE FALLBACK '
                  '(documented no-bogey path)' % hero)
    elif derivation and derivation.startswith('hero-row'):
        phrase = 'hero %r read from %s' % (hero, derivation)
    else:
        phrase = 'hero %r (derivation unrecorded)' % hero
    if lower_authority:
        phrase += ' [no bogey -- graded vs consensus, LOWER AUTHORITY]'
    return phrase


def grade_current_quarter(parsed, entry, kpi_rows, model, evidence=None):
    """The two-dimensional band, with the hard cap applied first."""
    out = dict(score=None, base=None, clearance=None, clearanceVs=None,
               flags=0, flagEvidence=[], flagUnknown=[], hardCapped=False,
               stepDownApplied=0.0, reason=None, heroName=entry.get('heroName'),
               heroActual=None, heroBogey=None, lowerAuthority=False)

    gaps = hero_extraction_gaps(entry, kpi_rows, 'currentQuarter')
    if gaps:
        out['extractionGaps'] = gaps
        out['reason'] = _gap_reason('currentQuarter', gaps)
        return out

    heroes = entry.get('heroes') or []
    if not heroes:
        out['reason'] = ('no priority-1 hero KPI with appliesTo=currentQuarter '
                         '-- cannot grade (never fall back to revenue)')
        return out

    hero = heroes[0]
    idx = _match_kpi_slot(hero.get('name'), entry.get('keyKPIs') or [],
                          entry.get('quarter'))

    hero_actual = hero_bogey = hero_cons = None
    hero_kpi_name = None
    # ★ WHICH derivation produced the clearance. CSCO's reason line read "hero
    # Product Gross Margin (%) clears consensus by +2.53%" while the +2.53% was
    # REVENUE vs revConsensus -- the profile hero name printed over a number it
    # had no part in. The collision is not hypothetical: revenue vs consensus
    # (+2.53%) and 66.3/64.66 (+2.54%) are identical to two decimals, so the
    # line could not be checked against itself. The path is now stated.
    derivation = None
    if idx is not None:
        hero_kpi_name = (entry['keyKPIs'][idx].get('name') or '')
        hero_actual = gradeable_actual(kpi_rows[idx])
        hero_bogey = entry['keyKPIs'][idx].get('bogey')
        hero_cons = entry['keyKPIs'][idx].get('consensus')
        if hero_actual is not None:
            derivation = 'hero-row[%d]' % idx

    # Fall back to the headline revenue line when the hero has no slot -- CSCO's
    # Product Gross Margin has no keyKPI and no published consensus at all.
    if hero_actual is None:
        rev = parsed.get('revenue') or {}
        hero_actual = rev.get('value_musd')
        hero_bogey, problem = units.normalise_expectation(
            entry.get('revBogey'), entry.get('revUnit'))
        hero_cons, cproblem = units.normalise_expectation(
            entry.get('revConsensus'), entry.get('revUnit'))
        hero_kpi_name = 'revenue (hero KPI not present in the release)'
        derivation = 'revenue-fallback'
        if problem or cproblem:
            out['reason'] = ('UNIT UNDECLARED on the stored expectation -- '
                             'refusing to grade (%s)' % (problem or cproblem))
            return out

    if hero_actual is None:
        out['reason'] = ('hero KPI %r not found in the release and no revenue '
                         'fallback available' % (hero.get('name') or '')[:50])
        return out

    out['heroActual'] = hero_actual
    out['heroBogey'] = hero_bogey
    out['heroKpiName'] = hero_kpi_name
    out['derivation'] = derivation
    out['heroSlot'] = idx

    reverse = hero.get('interpretation') == 'reverse-polarity'

    # Clearance: bogey first, consensus second with lower authority flagged.
    # ★ A lower-is-better hero clears by coming in BELOW its bar, so the sign
    # of the clearance has to flip or the band lookup reads a beat as a miss.
    hero_kpi = (entry.get('keyKPIs') or [{}])[idx] if idx is not None else {}
    _dir = -1.0 if lower_is_better(hero_kpi) else 1.0
    out['lowerIsBetter'] = _dir < 0

    if isinstance(hero_bogey, (int, float)):
        e, a = _normalise_pair(hero_bogey, hero_actual, hero_kpi_name)
        clearance = None if e in (None, 0) else (a - e) / abs(e) * 100.0 * _dir
        out['clearanceVs'] = 'bogey'
    elif isinstance(hero_cons, (int, float)):
        e, a = _normalise_pair(hero_cons, hero_actual, hero_kpi_name)
        clearance = None if e in (None, 0) else (a - e) / abs(e) * 100.0 * _dir
        out['clearanceVs'] = 'consensus'
        out['lowerAuthority'] = True
    else:
        out['reason'] = ('no bogey and no numeric consensus for the hero KPI '
                         '-- nothing to grade against')
        return out

    if clearance is None:
        out['reason'] = 'hero KPI expectation is zero or unusable'
        return out
    if reverse:
        clearance = -clearance
    out['clearance'] = round(clearance, 3)

    # NB: not `evidence` -- that name is the caller's evidence dict, and
    # shadowing it here passes a list into _negative_band.
    flags, flag_evidence, unknown, accounting = count_flags(
        parsed, entry, kpi_rows)
    out.update(flags=flags, flagEvidence=flag_evidence, flagUnknown=unknown,
               flagAccounting=accounting)

    # ★ THE HARD CAP -- applied BEFORE the band lookup.
    miss_band = hero.get('missBand')
    hero_missed = clearance < 0
    if isinstance(miss_band, (int, float)) and miss_band > 0:
        # missBand is expressed in the hero's own unit (bps / % / $B).
        hero_missed = clearance < 0
    if hero_missed:
        # ★ THE CAP IS A CEILING, NOT A VALUE. "Caps Current Quarter at 0.0"
        # means the score cannot be ABOVE 0 -- the negative bands still decide
        # how far below it lands. Treating the cap as the final answer scores
        # APP Q2 and CBRS Q2 at 0.0 when both are pinned at -1.5.
        out['hardCapped'] = True
        score, why = _negative_band(parsed, entry, kpi_rows, clearance,
                                    evidence)
        out['score'] = min(0.0, score)
        out['negativeBandReason'] = why
        out['reason'] = (
            '%s | %s = %s vs %s %s (%+.2f%%) MISSED -> ceiling 0.0; %s'
            % (_derivation_phrase(hero.get('name'), derivation, hero_kpi_name,
                                  out['lowerAuthority']),
               hero_kpi_name[:64], _fmt_num(hero_actual), out['clearanceVs'],
               _fmt_num(hero_bogey if out['clearanceVs'] == 'bogey'
                        else hero_cons), clearance, why))
        return out

    # Band lookup on clearance, then the derived flag step-down.
    base, max_flags = None, None
    for band in model.cq_bands:
        if _band_matches_clearance(band, clearance):
            base = float(band['score'])
            max_flags = _band_max_flags(band)
            break
    if base is None:
        out['reason'] = ('clearance %+.2f%% matched no band' % clearance)
        return out

    excess = max(0, flags - (max_flags if max_flags is not None else 0))
    step = excess * config.FLAG_STEP_DOWN
    out['base'] = base
    out['stepDownApplied'] = step
    out['score'] = _round_half(max(0.0, base - step))
    out['reason'] = (
        '%s | %s = %s vs %s %s (%+.2f%%) -> base %+.1f, %d flag(s) vs '
        'allowance %s -> %+.1f'
        % (_derivation_phrase(hero.get('name'), derivation, hero_kpi_name,
                              out['lowerAuthority']),
           hero_kpi_name[:64], _fmt_num(hero_actual), out['clearanceVs'],
           _fmt_num(hero_bogey if out['clearanceVs'] == 'bogey' else hero_cons),
           clearance, base, flags, max_flags, out['score']))
    return out


def _count_consensus_misses(kpi_rows):
    """Graded CURRENT_Q lines that missed consensus, worst first."""
    misses = []
    for row in kpi_rows:
        if row.get('forward'):
            continue
        pct = row.get('pctVsCons')
        if isinstance(pct, (int, float)) and pct < -0.5:
            misses.append((pct, row.get('name')))
    misses.sort()
    return misses


def _negative_band(parsed, entry, kpi_rows, clearance, evidence=None):
    """The negative bands, evaluated beneath the hard-cap ceiling.

    Evidence the release may or may not carry is passed in rather than
    guessed. `evidence` keys: ownGuideFailed, marginDeclined, marginCollapse.
    An undeterminable signal is treated as absent AND reported, so the score
    lands one band shallower rather than being invented.
    """
    ev = evidence or {}
    misses = _count_consensus_misses(kpi_rows)
    n = len(misses)
    own_guide_failed = bool(ev.get('ownGuideFailed'))
    margin_declined = bool(ev.get('marginDeclined'))
    margin_collapse = bool(ev.get('marginCollapse'))
    major = clearance is not None and clearance <= -20.0

    detail = ('%d consensus miss(es)%s%s%s'
              % (n,
                 ', own-guide range FAILED' if own_guide_failed else '',
                 ', margin declined' if margin_declined else '',
                 ', margin collapse' if margin_collapse else ''))

    if major and own_guide_failed and margin_collapse:
        return -2.0, '-2.0: hero major miss + own-guide failure + margin collapse (%s)' % detail
    if n >= 2 and (own_guide_failed or margin_declined or margin_collapse):
        return -1.5, '-1.5: multi-line consensus miss AND %s (%s)' % (
            'own-guide failure' if own_guide_failed else 'margin decline', detail)
    if n >= 2:
        return -1.0, '-1.0: consensus miss on the hero KPI plus another line (%s)' % detail
    if n == 1:
        return -0.5, '-0.5: modest consensus miss on one graded line (%s)' % detail
    return 0.0, '0.0: hero missed its bogey but no graded line missed consensus (%s)' % detail


def grade_next_q(parsed, entry, model, kpi_rows=None):
    """Next-quarter guidance. Defers when no numeric midpoint is parseable."""
    out = dict(score=None, reason=None, mid=None, pctVsBogey=None,
               pctVsCons=None)

    gaps = hero_extraction_gaps(entry, kpi_rows, 'nextQGuidance')
    if gaps:
        out['extractionGaps'] = gaps
        out['reason'] = _gap_reason('nextQGuidance', gaps)
        return out
    g = (parsed.get('guidance') or {}).get('nextQ')
    if not g:
        # Same rule as FY: absence is 0.0 for a company that does not guide,
        # and a deferral when a guide was expected and withheld.
        if _expects_no_guide(entry.get('nextQGuideExpected')):
            out['score'] = 0.0
            out['reason'] = ('no next-quarter guide, and the card expected '
                             'none — neutral, not a penalty')
        else:
            out['reason'] = ('a next-quarter guide was expected but none was '
                             'in the release — likely call-only for this '
                             'ticker, which is itself the event; deferring')
        return out
    if g.get('mid') is None:
        # ★ The sentence guided a margin or an EPS but no revenue. There is no
        # midpoint to grade the next-quarter band against, so this defers for
        # the same reason a missing guide does -- the row-level margin guide
        # still extracts and grades on its own row.
        out['reason'] = ('the guidance sentence carried no revenue midpoint '
                         '(metrics-only guide) — deferring the band rather '
                         'than grading a guide that was not given')
        return out
    out['mid'] = g['mid']

    bogey, cons = _forward_expectation(entry, 'nextQ')
    if bogey is None and cons is None:
        out['reason'] = ('nextQGuideExpected is prose, not a numeric midpoint '
                         '-- deferring rather than guessing')
        return out

    if bogey is not None:
        pct, _ = pct_delta(g['mid'], bogey)
        out['pctVsBogey'] = pct
        if pct is not None:
            out['score'] = (2.0 if pct >= 3.0 else 1.5 if pct >= 0.0 else None)
            if out['score'] is not None:
                out['reason'] = 'guide mid %+.2f%% vs bogey' % pct
                return out
    if cons is not None:
        pct, _ = pct_delta(g['mid'], cons)
        out['pctVsCons'] = pct
        if pct is None:
            out['reason'] = 'guide vs consensus not computable'
            return out
        # Beats consensus but misses bogey = the 🟡 fade zone.
        if bogey is not None and out['pctVsBogey'] is not None \
                and out['pctVsBogey'] < 0 and pct >= 1.0:
            out['score'] = 1.0
            out['reason'] = ('FADE ZONE: %+.2f%% vs consensus, %+.2f%% vs bogey'
                             % (pct, out['pctVsBogey']))
        elif pct >= 1.0:
            out['score'] = 1.0
            out['reason'] = 'guide mid %+.2f%% vs consensus' % pct
        elif pct > 0.0:
            out['score'] = 0.5
            out['reason'] = 'guide mid %+.2f%% vs consensus' % pct
        elif pct >= -0.5:
            out['score'] = 0.0
            out['reason'] = 'guide inline with consensus'
            if pct < 0.0:
                # ★ TWO DEFINITIONS OF "INLINE" IN ONE CARD, and they disagree.
                # The verdict cell is STRICT -- below street is 🔴 MISS -- while
                # this band treats anything within 0.5% of street as inline and
                # scores it a neutral 0.0. CRM-2027Q1 is the case: a Q2 guide of
                # 11.31 against an 11.36 street renders MISS on the row and
                # +0.00 on the category, and `nextQInline` is False because it
                # is not an exact tie, so no caveat line fires either. A street
                # miss scoring zero with nothing said about it reads as neutral.
                #
                # The band is NOT repriced here -- that would move the pins and
                # reprice the library on n=10. The disagreement is FLAGGED so it
                # cannot pass silently.
                out['toleranceAbsorbedMiss'] = True
                out['toleranceAbsorbedPct'] = pct
                out['reason'] = (
                    'guide %+.2f%% vs consensus — BELOW street, absorbed by the '
                    '±0.5%% inline tolerance and scored 0.0. The row grades '
                    'MISS; the category does not.' % pct)
        elif pct >= -2.0:
            out['score'] = -0.5
        elif pct >= -5.0:
            out['score'] = -1.0
        else:
            out['score'] = -1.5
        if out['reason'] is None:
            out['reason'] = 'guide mid %+.2f%% vs consensus' % pct
    return out


def grade_fy(parsed, entry, model, kpi_rows=None):
    """FY guidance. Keys on the ACTION -- raised vs reaffirmed vs cut.

    The band is an action table, not a delta table, so a midpoint alone cannot
    grade it. The action comes from an explicit verb in the release ("raises
    its full-year guidance", "reaffirms", "lowers", "is withdrawing") or from a
    stated prior range. When the release gives neither, this defers rather than
    guessing -- but that is now the exception, not the rule.
    """
    out = dict(score=None, reason=None, mid=None, pctVsCons=None, action=None)

    gaps = hero_extraction_gaps(entry, kpi_rows, 'fyGuidance')
    if gaps:
        out['extractionGaps'] = gaps
        out['reason'] = _gap_reason('fyGuidance', gaps)
        return out

    g = (parsed.get('guidance') or {}).get('fy')
    action_info = (parsed.get('guidanceAction') or {}).get('fy') or {}
    action = action_info.get('action')
    out['action'] = action

    if not g and not action:
        # "Do NOT penalise an absence" means the band is 0.0, not None -- but
        # ONLY for a company that does not give FY guidance. If the card
        # expected one and the release withheld it, that is the call being the
        # event (LESSONS B4), which defers.
        expected = entry.get('fyGuideExpected')
        if _expects_no_guide(expected):
            out['score'] = 0.0
            out['reason'] = ('no FY figure, and the card expected none — the '
                             'neutral score for a quarterly-only guider, not '
                             'a penalty (fyGuideExpected: %r)'
                             % str(expected)[:60])
        elif expected is None:
            # ★ The card records NO FY expectation at all. That is a
            # quarterly-only guider, and the band table is explicit: absence
            # scores 0.0, "do NOT penalise an absence". Deferring here was
            # wrong on all three corpus releases, whose hand-built answers are
            # 0.0. A DEFERRAL is reserved for the case where the card expected
            # a guide and the release withheld it -- that one is the call being
            # the event.
            out['score'] = 0.0
            out['reason'] = ('no FY figure in the release and no FY '
                             'expectation on the card — quarterly-only '
                             'guider, scored neutral rather than penalised')
        else:
            out['reason'] = ('an FY guide WAS expected but none was found in '
                             'the release — guidance withheld from the PR '
                             'means the call is the event, so this defers')
        return out

    # ★ WITHDRAWAL DEFERS. It must NOT be scored automatically.
    #
    # CLAUDE.md lists withdrawn metrics, capped roadmaps and volunteered
    # ceilings under "what must NOT be automated", and -2.0 is the rarest value
    # in the model -- 1 of 76 for fyGuidance. Auto-assigning the rarest score
    # from a regex is the wrong direction of error: a withdrawal is a bearish
    # ACTION whose weight depends on whether the retired metric was the one
    # carrying the story (CSCO's FY27 AI order target) or a routine line, and
    # that judgment needs the call.
    #
    # Deferring pushes FY to None, which routes the card through
    # evaluate_partial: a wider exact bracket, cohortApplies False, and
    # status SCORED-PR-ONLY with the reason stated.
    if action in _DEFER_ACTIONS:
        out['score'] = None
        out['deferReason'] = action
        out['reason'] = (
            'FY guidance %s — DEFERRED, not scored. Withdrawn metrics, capped '
            'roadmaps and volunteered ceilings are explicitly not automatable: '
            'the weight depends on whether the retired number was the one '
            'carrying the story, which needs the call. Bracket widens; cohort '
            'base rates do not apply.' % action)
        return out

    if action == 'CUT':
        out['score'] = -1.5
        out['reason'] = 'FY guidance CUT'
        return out

    if g:
        out['mid'] = g['mid']
    _, cons = _forward_expectation(entry, 'fy')
    if cons is not None and g:
        out['pctVsCons'] = pct_delta(g['mid'], cons)[0]

    # Prefer the release's own prior range over the card's consensus for the
    # raise/reaffirm call -- it is the company's own baseline.
    prior_mid = action_info.get('priorMid')
    if action is None and prior_mid is not None and g:
        action = 'RAISED' if g['mid'] > prior_mid else (
            'MAINTAINED' if abs(g['mid'] - prior_mid) < 1e-9 else 'CUT')
        out['action'] = action + ' (inferred from the stated prior range)'

    if action is None:
        out['reason'] = ('FY midpoint parsed but the release states no action '
                         'verb and no prior range -- raise-vs-reaffirm is '
                         'undeterminable, so deferring rather than guessing')
        return out

    if action == 'MAINTAINED':
        out['score'] = 0.0
        out['reason'] = ('FY guidance MAINTAINED. Note: a reaffirm is worth '
                         '-1.0 for a scale-economics story (check the profile '
                         'for interpretation: binary) -- not applied '
                         'automatically')
        return out

    if action == 'RAISED':
        pct = out['pctVsCons']
        if pct is None:
            out['score'] = 1.0
            out['reason'] = ('FY guidance RAISED, but no numeric consensus to '
                             'size it against -- graded at the "raised to '
                             'roughly consensus" band')
            return out
        if pct >= 3.0:
            out['score'] = 2.0
        elif pct >= 0.0:
            out['score'] = 1.5
        else:
            out['score'] = 1.0
        out['reason'] = ('FY guidance RAISED, mid %+.2f%% vs consensus' % pct)
        return out

    out['reason'] = 'unhandled FY action %r' % action
    return out


_NUM_IN_TEXT = re.compile(r'\$?\s?([\d,]+(?:\.\d+)?)\s*(billion|million|[BM])\b',
                          re.I)


_STRUCTURED_EXPECTATION = {'nextQ': 'q2Expectations', 'fy': 'fyExpectations'}

# A card saying no guide is expected -- "None.", "No formal FY rev/EPS",
# "does not guide". This is what separates a legitimate 0.0 (a quarterly-only
# guider gave no FY figure) from a deferral (a guide was expected and the PR
# withheld it, which per LESSONS B4 means the call is the event).
_NO_GUIDE_EXPECTED = re.compile(
    r'^\s*(?:none|n/?a|no)\b|^\s*no\s+(?:formal|explicit|fy\b|full)'
    r'|\bdoes\s+not\s+(?:guide|provide)|\bno\s+formal\s+(?:fy|annual)'
    r'|\bnever\s+guides?\b|\bquarterly[- ]only\b', re.I)


def _expects_no_guide(text):
    """True when the card explicitly says no guide is expected."""
    if text is None:
        return False
    s = str(text).strip()
    if not s:
        return False
    return bool(_NO_GUIDE_EXPECTED.search(s))


def _forward_expectation(entry, which):
    """Numeric (bogey, consensus) in $M for a forward category.

    Two STRUCTURED sources, in authority order:

      1. a `keyKPIs` slot classified to that period whose name mentions revenue
      2. `fyExpectations` / `q2Expectations` carrying `revenue` + `revenueUnit`

    Prose is deliberately NOT parsed. `fyGuideExpected` often embeds figures --
    NOW-2026Q1 reads "FY sub rev $15.53-15.57B" -- but that is SUBSCRIPTION
    revenue, and grading a total-revenue guide against it is precisely the
    definitional mismatch of error class D4. When neither structured source
    exists the category defers.
    """
    want = 'NEXTQ_GUIDE' if which == 'nextQ' else 'FY_GUIDE'
    record_quarter = entry.get('quarter')

    bogey = cons = None
    for kpi in entry.get('keyKPIs') or []:
        name = kpi.get('name') or ''
        if _classify_period(name, record_quarter) != want:
            continue
        if 'revenue' not in name.lower():
            continue
        b, c = kpi.get('bogey'), kpi.get('consensus')
        if isinstance(b, (int, float)):
            bogey, _ = units.kpi_to_musd(b, name)
        if isinstance(c, (int, float)):
            cons, _ = units.kpi_to_musd(c, name)
        break

    if bogey is None and cons is None:
        # The structured expectations dict. Read defensively -- the schema
        # varies by ticker and q2Expectations is a bare STRING on some records.
        block = entry.get(_STRUCTURED_EXPECTATION[which])
        if isinstance(block, dict):
            rev, unit = block.get('revenue'), block.get('revenueUnit')
            if isinstance(rev, (int, float)) and unit:
                v, problem = units.normalise_expectation(rev, unit)
                if not problem:
                    cons = v
    return bogey, cons


# --- top level ----------------------------------------------------------------

def score_release(parsed, entry, model, evidence=None):
    """Score a parsed release against a prepared card.

    `overall` is None whenever ANY category is None. Narrative is always None
    on a PR-only run, so the scraper NEVER emits an overall score: three
    categories and a deferral.
    """
    kpi_rows = build_kpi_rows(parsed, entry)

    cq = grade_current_quarter(parsed, entry, kpi_rows, model, evidence)
    nq = grade_next_q(parsed, entry, model, kpi_rows)
    fy = grade_fy(parsed, entry, model, kpi_rows)

    scores = dict(currentQuarter=cq['score'],
                  nextQGuidance=nq['score'],
                  fyGuidance=fy['score'],
                  narrative=None)

    deferred = []
    for key, block in (('nextQGuidance', nq), ('fyGuidance', fy)):
        if block['score'] is None:
            deferred.append('%s: %s' % (key, block['reason']))
    if cq['score'] is None:
        deferred.append('currentQuarter: %s' % cq['reason'])
    deferred.append('narrative: %s' % NARRATIVE_PR_REASON)

    # overall is None if ANY category is None -- and narrative always is on a
    # PR. So `overall` is NEVER emitted as a point estimate. Instead the gate
    # emits the exact ±0.40 bracket plus that band's cohort base rate.
    overall = None
    if all(v is not None for v in scores.values()):
        overall = round(sum(scores[k] * model.weights[k] for k in scores), 2)

    fw = gate.framework_from(model)
    gate_result = None
    gate_error = None
    try:
        # The published-cohort path: all three of CQ/NextQ/FY known.
        gate_result = gate.evaluate(scores['currentQuarter'],
                                    scores['nextQGuidance'],
                                    scores['fyGuidance'], fw)
    except gate.IncompleteScore as exc:
        gate_error = str(exc)
        # Fall back to the generalised bracket. Still exact arithmetic, but
        # wider, and it carries cohortApplies=False so the published base
        # rates are never misapplied to it.
        gate_result = gate.evaluate_partial(scores, fw)

    # Containment is arithmetically guaranteed -- assert on every run.
    if gate_result and gate_result.get('overallBracket'):
        gate.assert_containment(gate_result['overallBracket'], overall)

    # Cohort context. Both are surfaced ALONGSIDE the scores and are never
    # folded into them -- same discipline as the positioning line.
    fc_context = gate.forward_commitment_context(
        entry, (gate_result or {}).get('band'),
        (model.frameworks or {}).get('forwardCommitmentFindings'),
        clearance_pct=cq.get('clearance'), kpi_rows=kpi_rows)
    fy_inline = gate.fy_inline_context(
        scores['fyGuidance'], (model.frameworks or {}).get('fyInlineIsBearish'))

    # HARD 10. The expected column is as error-prone as the actual column, and
    # a systematic transposition is invisible to bogey-vs-consensus checks.
    hard10 = plausibility.check_record(dict(
        id=entry.get('recordId'), ticker=entry.get('ticker'),
        sector=entry.get('sector'),
        preEarnings=dict(keyKPIs=entry.get('keyKPIs') or [])))

    # ★ Bracket edge asymmetry. The top edge is FIRM -- narrative and any
    # further flags can only pull the answer down. The bottom edge is
    # OPTIMISTIC in the sense that it is the only end the truth can travel
    # toward. Reported, never applied.
    if gate_result and gate_result.get('overallBracket'):
        gate_result['topEdge'] = 'firm — flags can only be ADDED'
        gate_result['bottomEdge'] = ('the direction of travel as flags arrive; '
                                     'the true answer moves DOWN, never up')
        gate_result['ceilingApplies'] = scores['narrative'] is None

    pos = entry.get('positioningAxis') or {}
    # ★ NO POSITIONING MODIFIER. Only 6 of the 29 DECISIVE_BULLISH records
    # carry a positioning score, so the good-print/bad-tape hypothesis is
    # untested in the cohort where it matters. Shown as context, never applied.
    sign_mod = pos.get('signModifier')

    _branch = _match_branch(entry, cq)

    # ★ Cohort context, computed from the ROW not the score, and never folded
    # into any category. render() prints the warning on the Next Quarter line.
    nq_fade, nq_inline, nq_fade_ev = next_q_fade_zone(entry, kpi_rows)

    rev_pct_cons, rev_pct_bogey = _headline_pcts(parsed, entry)

    return dict(
        ticker=entry['ticker'],
        recordId=entry.get('recordId'),
        company=entry.get('company'),
        sector=entry.get('sector'),
        quarter=entry.get('quarter'),
        status='SCORED-PR-ONLY',
        scores=scores,
        overall=None,               # never emitted on a PR-only run
        overallDeferred=True,
        gate=gate_result,
        gateError=gate_error,
        forwardCommitment=fc_context,
        fyInlineContext=fy_inline,
        hard10=hard10,
        scoreLabel=None,
        currentQuarterDetail=cq,
        # ★ On any PR-only run the cq score is an UPPER BOUND. 3 of the 7 flags
        # need the call, the call can only ADD flags, and every added flag only
        # steps the score DOWN. No corrective haircut is applied: the direction
        # is certain, the magnitude is unknown at n=3.
        currentQuarterIsCeiling=(scores['narrative'] is None
                                 and cq['score'] is not None),
        currentQuarterCeilingNote=(
            'cq ≤ %+.1f (PR-only ceiling) — %s. The call can only ADD flags, '
            'so the true score can only FALL. No haircut applied: direction '
            'certain, magnitude unknown at n=3.'
            % (cq['score'], (cq.get('flagAccounting') or {}).get('summary', ''))
            if (scores['narrative'] is None and cq['score'] is not None)
            else None),
        flagAccounting=cq.get('flagAccounting'),
        nextQDetail=nq,
        fyDetail=fy,
        narrativeReason=NARRATIVE_PR_REASON,
        keyKPIs=kpi_rows,
        heroName=entry.get('heroName'),
        heroKpiName=cq.get('heroKpiName'),
        needsReview=entry.get('needsReview'),
        flags=cq['flags'],
        flagEvidence=cq['flagEvidence'],
        flagUnknown=cq['flagUnknown'],
        hardCapped=cq['hardCapped'],
        stepDownApplied=cq['stepDownApplied'],
        derivedStepDown=DERIVED_STEP_DOWN,
        # Detected on the row (actual >= consensus AND actual < bogey), which
        # is the measured configuration -- not inferred from the score landing
        # on +1.0.
        nextQFadeZone=nq_fade,
        # ★ The fourth state: an exact tie to consensus. Not the fade zone.
        nextQInline=nq_inline,
        # ★ The FIFTH: a genuine street miss absorbed by the band's tolerance.
        nextQToleranceMiss=bool(nq.get('toleranceAbsorbedMiss')),
        nextQTolerancePct=nq.get('toleranceAbsorbedPct'),
        nextQFadeZoneEvidence=nq_fade_ev,
        fadeZone=nq_fade,
        positioning=dict(
            band=entry.get('band'),
            score10=entry.get('score10'),
            score10IsEstimate=entry.get('score10IsEstimate'),
            confidence=entry.get('positioningConfidence'),
            componentsScored=entry.get('componentsScored'),
            signModifier=sign_mod,
            # Deliberately absent: no adjustedScore. The modifier is
            # unvalidated at 6/29 coverage in the cohort that matters.
            adjustedScore=None,
            modifierApplied=False),
        beatMagnitude=dict(
            revPctVsCons=rev_pct_cons,
            revPctVsBogey=rev_pct_bogey,
            epsPctVsCons=_eps_pct(parsed, entry),
            epsPctVsBogey=None,
            score=overall,
            reactionPct=None,
            impliedMove=entry.get('impliedMove')),
        branchMatched=_branch[0],
        branchNote=_branch[1],
        tradeSummaryPending=True,
        whatMattersMost=entry.get('whatMattersMost'),
        setup=entry.get('setup'),
        bogeyReliability=entry.get('bogeyReliability'),
        priorQuarter=entry.get('priorQuarter'),
        impliedMovePct=entry.get('impliedMovePct'),
        deferred=deferred,
        problems=[p for p in [
            ('⛔ %d row(s) NOT GRADED — a single value appeared in more than '
             'one row (duplicate-refused)' % len(duplicate_actuals(kpi_rows)))
            if duplicate_actuals(kpi_rows) else None,
            segment_sum_check(kpi_rows, entry),
            ('\u26d4 %d row(s) NOT GRADED \u2014 the row name declares a scale '
             'this build cannot resolve (unit-undeclared)'
             % len(unit_undeclared(kpi_rows)))
            if unit_undeclared(kpi_rows) else None,
        ] if p],
    )


def _headline_pcts(parsed, entry):
    rev = (parsed.get('revenue') or {}).get('value_musd')
    if rev is None:
        return None, None
    cons, p1 = units.normalise_expectation(entry.get('revConsensus'),
                                           entry.get('revUnit'))
    bogey, p2 = units.normalise_expectation(entry.get('revBogey'),
                                            entry.get('revUnit'))
    pc = pct_delta(rev, cons)[0] if (cons and not p1) else None
    pb = pct_delta(rev, bogey)[0] if (bogey and not p2) else None
    return pc, pb


def _eps_pct(parsed, entry):
    eps = parsed.get('eps') or {}
    pick = eps.get('non-GAAP') or eps.get('GAAP') or eps.get('unknown')
    cons = entry.get('epsConsensus')
    if not pick or not isinstance(cons, (int, float)):
        return None
    return pct_delta(pick['value'], cons)[0]


def _match_branch(entry, cq):
    """Returns (branchMatched, note). Always (None, note) -- BY DESIGN.

    ★ This is the permanent state of the PR-only path, not a stopgap, and the
    scraper deliberately takes NO price dependency to change it.

    branchAccuracyLog, both windows: direction 6 of 7, trigger identification
    3 of 3, **magnitude inside range 0 of 7**. Direction and trigger are the
    parts that work, and both come from the fundamental scorecard the card
    already carries at 4:01. Positioning component 3 (print-day move / implied
    move) feeds only the MAGNITUDE estimate -- the one output that has never
    once landed inside its range.

    Fetching an official close to compute component 3 would therefore buy the
    model's weakest output at the cost of a network dependency on the hot path,
    and LESSONS A2 forbids the cheap version anyway: an intraday snapshot is not
    acceptable, and the two locks set from one poisoned the whole read (SNDK's
    +10.65% snapshot against a -5.40% verified close forecast -12% to -20% on a
    print that fell 6.81%).

    So no branch is claimed. Returning {branch: None} would make render() print
    "⟨unnamed⟩" -- "a branch matched but nobody named it", the opposite of the
    truth. None gets render()'s "⟨none recorded⟩" and the reason goes to
    diagnostics.
    """
    ladder = entry.get('scenarioLadder') or []
    if not ladder:
        return None, ('no pre-written scenario ladder on this card — the '
                      'required-surprise TIER applies, not a matched branch')
    return None, (
        'scenario ladder present (%d branches); no branch claimed BY DESIGN. '
        'Branch magnitude is 0 of 7 inside range, and component 3 feeds only '
        'magnitude — direction (6/7) and trigger identification (3/3) already '
        'come from the scorecard above. The scraper takes no price dependency '
        'to buy the weakest output.' % len(ladder))
