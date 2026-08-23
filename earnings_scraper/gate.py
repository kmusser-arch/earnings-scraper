"""The PR-only decision gate.

A press release cannot settle Narrative -- that needs the call. Narrative carries
weight 0.20 and is bounded [-2, +2], so it can move `overall` by at most ±0.40.
A PR-only run therefore knows `overall` to within an exactly 0.80-wide bracket:

    partial = 0.20*CQ + 0.30*NextQ + 0.30*FY
    overall ∈ [partial - 0.40, partial + 0.40]

Emit the bracket. Never a point estimate.

★ DO NOT RENORMALIZE
====================
Rescaling the three known categories to 25 / 37.5 / 37.5 was TESTED AND
REJECTED. It flips 6 of 76 labels, in the worst direction:

    CSCO-2026Q4   +0.35 -> +0.81   actual reaction  -8.40%
    RDDT-2026Q2   -0.00 -> +0.50   actual reaction -12.00%

    (Those were label FLIPS under scoreLabelCalibration v1, where Bullish began
    at +0.50. Under v2 both land in Neutral, so the label no longer flips -- but
    the rejection stands on the stronger ground: rescaling moves the score
    toward the bullish end on two records that fell 8% and 12%, and it does so
    by deleting the narrative term, which is exactly where the signal was.)

Narrative is where "cleared revenue and EPS by 6-9.5%, and the market graded
gross margin" lives. Rescaling the remainder deletes precisely the signal that
mattered.

★ NO POSITIONING MODIFIER
=========================
Only 6 of the 29 DECISIVE_BULLISH records carry a positioning score, so the
"good print / bad tape" hypothesis is UNTESTED in the cohort where it would
matter. Positioning is shown as context and never applied as a modifier.

Bands and base rates are loaded from earnings-library.json ->
prOnlyGateFramework. Never hardcoded here.
"""

import re

WEIGHTS = {'currentQuarter': 0.20, 'nextQGuidance': 0.30,
           'fyGuidance': 0.30, 'narrative': 0.20}

# Narrative's maximum influence on overall: weight * full [-2,+2] half-range.
NARRATIVE_SWING = WEIGHTS['narrative'] * 2.0        # 0.40

# ★ THE LABEL THRESHOLDS ARE NOT MINE TO DECLARE.
#
# These were hardcoded at +0.50 / -0.50, which were the v1 label bands. The gate
# bands are DEFINED in terms of the label -- DECISIVE_BULLISH means "narrative
# cannot drag this out of Bullish" -- so a hardcoded copy silently keeps the old
# definition after a recalibration. scoreLabelCalibration v2 moved Bullish to
# >= +1.00 and Bearish to < 0.00 on n=57, because the old +0.5..+1.0 sub-band
# FELL 67% of the time: a positive label on a losing cohort.
#
# So they are read from render_scorecard.LABEL_BULLISH_AT / LABEL_BEARISH_BELOW
# at call time, through the provenance-checked loader.


def label_thresholds():
    """(bullish_at, bearish_below) from the shared renderer. Never local."""
    from . import scorecard
    mod = scorecard.renderer()
    for attr in ('LABEL_BULLISH_AT', 'LABEL_BEARISH_BELOW'):
        if not isinstance(getattr(mod, attr, None), (int, float)):
            raise scorecard.RendererFunctionMissing(
                'render_scorecard.%s is missing. Refusing to fall back to a '
                'local threshold: a stale label band puts a positive label on '
                'a losing cohort, which is the defect v2 corrected.' % attr)
    return (float(mod.LABEL_BULLISH_AT), float(mod.LABEL_BEARISH_BELOW))

# Half-step scores can land EXACTLY on a threshold: 0.30*1.5 + 0.30*1.5 gives
# partial 0.8999999999999999, so lo is 0.4999999999999999 and a bare
# `lo >= 0.50` files a genuine DECISIVE_BULLISH as STAY_FOR_CALL on float noise
# alone. Verified against the live library: this tolerance does NOT change the
# published tally (29 / 1 / 27, mean -3.80% with and without it).
_EPS = 1e-9


class IncompleteScore(Exception):
    """A category is None. Do NOT substitute a value -- abort the gate."""


class BracketContainmentError(Exception):
    """The stored overall fell outside the bracket.

    Containment is arithmetically guaranteed, so this is never a data quirk --
    it is a real bug in the weights, the bracket width, or the score itself.
    """


def framework_from(model):
    """Pull prOnlyGateFramework off a loaded Model, or refuse."""
    fw = (model.library or {}).get('prOnlyGateFramework')
    if not fw:
        raise RuntimeError(
            'prOnlyGateFramework missing from the library — refusing to '
            'hardcode bands')
    return fw


def reaction_of(record):
    """The next-day regular-session close.

    ★ NESTED: stockReaction.pctChangeNextDay, with beatMagnitude.reactionPct as
    the documented fallback. It is never a top-level field, and it is never the
    print-day move or the after-hours settle.
    """
    for outer, inner in (('stockReaction', 'pctChangeNextDay'),
                         ('beatMagnitude', 'reactionPct')):
        v = (record.get(outer) or {}).get(inner)
        if isinstance(v, (int, float)):
            return v
    return None


def evaluate(cq, nextq, fy, framework):
    """Run the gate. All three categories must be numeric.

    Returns the bracket, the band, the cohort base rate and the tail warning.
    """
    for name, v in (('currentQuarter', cq), ('nextQGuidance', nextq),
                    ('fyGuidance', fy)):
        if not isinstance(v, (int, float)):
            raise IncompleteScore(
                '%s is %r. Non-negotiable 7: never fabricate a category '
                'score. Emit the card ungraded with the reason.' % (name, v))

    partial = (WEIGHTS['currentQuarter'] * cq
               + WEIGHTS['nextQGuidance'] * nextq
               + WEIGHTS['fyGuidance'] * fy)
    lo, hi = partial - NARRATIVE_SWING, partial + NARRATIVE_SWING
    bands = framework['bands']

    _bull, _bear = label_thresholds()
    if lo >= _bull - _EPS:
        band = 'DECISIVE_BULLISH'
    elif hi <= _bear + _EPS:
        band = 'DECISIVE_BEARISH'
    else:
        band = 'STAY_FOR_CALL'
    b = bands.get(band) or {}

    # ★ THE BASE RATE NO LONGER DESCRIBES THIS BAND.
    # Moving the thresholds moved 21 of 76 records between bands:
    # DECISIVE_BULLISH 36 -> 19, STAY_FOR_CALL 39 -> 52, DECISIVE_BEARISH 1 -> 5.
    # The published rates (DECISIVE_BULLISH 23/29 = 79%; STAY_FOR_CALL 21 of 27
    # down, mean -3.80%) were measured on the v1 populations. Attaching them to a
    # v2 band is the same error as carrying the 0.80-width base rate onto a
    # widened bracket -- so the rate is reported as NOT APPLICABLE until it is
    # re-measured on the new membership, rather than transferred.
    _stale = dict(
        baseRateMeasuredUnder='v1 label thresholds (+0.50 / -0.50)',
        labelThresholds=dict(bullishAt=_bull, bearishBelow=_bear),
        cohortApplies=False,
        note=('band membership changed with scoreLabelCalibration v2 (21 of 76 '
              'records moved), so the published base rate for this band is not '
              'this population\'s rate. Re-measure before quoting it.'))

    return dict(
        band=band,
        labelCalibration=_stale,
        partial=round(partial, 4),
        overallBracket=[round(lo, 4), round(hi, 4)],
        overallPoint=None,          # ★ never a point estimate on a PR-only run
        bracketWidth=round(hi - lo, 4),
        narrativeUnknown=True,
        knownCategories=['currentQuarter', 'fyGuidance', 'nextQGuidance'],
        unknownCategories=['narrative'],
        narrativeOnly=True,
        # Narrative is the ONLY unknown here, which is the case the published
        # base rates were measured on -- so they apply.
        cohortApplies=True,
        renormalized=False,
        positioningApplied=False,
        cohortN=b.get('n'),
        cohortBaseRate=(b.get('★baseRate') or b.get('directionallyCorrect')
                        or b.get('note')),
        cohortMeanReaction=b.get('meanReaction'),
        interpretation=b.get('★interpretation'),
        tailWarning=b.get('★theTailThatKillsTheShort'),
        failures=b.get('failures'),
        failureNote=b.get('failureNote'),
        actionable=_actionable(band, b),
        doNotRenormalize=framework.get('★why'),
    )


def evaluate_partial(scores, framework):
    """The bracket generalised to ANY set of unknown categories.

    Why this exists: `evaluate` requires all three of CQ / NextQ / FY, which is
    what the published base rates were derived on. But on a live press release
    `fyGuidance` almost always defers -- raise-versus-reaffirm needs the PRIOR
    range, which a release often does not restate -- so `evaluate` raises
    IncompleteScore and the card carries no decision at all. That is the same
    "correct, and useless at 4:01 PM" failure the gate was built to fix,
    recurring one level up.

    The arithmetic generalises exactly, with no estimation:

        partial = Σ w_k · s_k        over KNOWN categories
        swing   = Σ w_k · 2          over UNKNOWN categories
        overall ∈ [partial − swing, partial + swing]

    ★ The cohort base rates DO NOT APPLY when more than one category is
    unknown -- they were measured on the narrative-only case. So a band is
    assigned only if the WIDER bracket still clears the threshold, and
    `cohortApplies` is False, with no base rate attached.
    """
    known, unknown = {}, []
    for key, weight in WEIGHTS.items():
        v = scores.get(key)
        if isinstance(v, (int, float)):
            known[key] = v
        else:
            unknown.append(key)

    if not known:
        return dict(band=None, unknownCategories=unknown,
                    reason='every category is unknown — nothing to bracket')

    partial = sum(WEIGHTS[k] * v for k, v in known.items())
    swing = sum(WEIGHTS[k] * 2.0 for k in unknown)
    lo, hi = partial - swing, partial + swing

    narrative_only = unknown == ['narrative']
    _bull, _bear = label_thresholds()
    if lo >= _bull - _EPS:
        band = 'DECISIVE_BULLISH'
    elif hi <= _bear + _EPS:
        band = 'DECISIVE_BEARISH'
    else:
        band = 'STAY_FOR_CALL'
    b = (framework.get('bands') or {}).get(band) or {}

    out = dict(
        band=band,
        partial=round(partial, 4),
        overallBracket=[round(lo, 4), round(hi, 4)],
        overallPoint=None,
        bracketWidth=round(hi - lo, 4),
        knownCategories=sorted(known),
        unknownCategories=unknown,
        narrativeOnly=narrative_only,
        cohortApplies=narrative_only,
        renormalized=False,
        positioningApplied=False,
        doNotRenormalize=framework.get('★why'),
    )

    if narrative_only:
        out.update(cohortN=b.get('n'),
                   cohortBaseRate=(b.get('★baseRate')
                                   or b.get('directionallyCorrect')
                                   or b.get('note')),
                   cohortMeanReaction=b.get('meanReaction'),
                   interpretation=b.get('★interpretation'),
                   tailWarning=b.get('★theTailThatKillsTheShort'),
                   failures=b.get('failures'),
                   failureNote=b.get('failureNote'),
                   actionable=_actionable(band, b))
    else:
        out.update(cohortN=None, cohortBaseRate=None, tailWarning=None,
                   actionable=(
                       'WIDENED BRACKET — %s also unknown, so the bracket is '
                       '%.2f wide instead of 0.80 and the published cohort '
                       'base rates DO NOT APPLY. The bracket itself is still '
                       'exact.' % (', '.join(k for k in unknown
                                             if k != 'narrative'),
                                   hi - lo)))
    return out


def _actionable(band, b):
    """One line, phrased so the base rate and the tail arrive together."""
    if band == 'STAY_FOR_CALL':
        return ('SHORT-SIDE LEAN — %s. Ambiguity is bearish; clean prints are '
                'unambiguous. But the 22%% that resolve up do so violently — '
                'size for the tail or use defined risk.'
                % (b.get('★baseRate') or 'n/a'))
    if band == 'DECISIVE_BULLISH':
        # "cannot drag it below Bullish" is true BY CONSTRUCTION -- the band
        # is the bracket sitting entirely above the imported Bullish threshold.
        # It says nothing about the base rate, which v2 membership invalidated.
        return ('LONG LEAN — the whole bracket sits at or above the Bullish '
                'threshold (%+.2f), so narrative cannot move the label. Base '
                'rate NOT APPLICABLE: it was measured under v1 bands and 21 of '
                '76 records changed band. Positioning remains the suspect and '
                'is UNTESTED (6/29 coverage).' % label_thresholds()[0])
    return ('n=%s in this band. NO BASE RATE EXISTS — do not trade it as one. '
            'Defer to the call.' % b.get('n'))


# ── The tail separator ────────────────────────────────────────────────────────
#
# ⛔ The $-anchor hypothesis is FALSIFIED. Do not implement it. $-anchored n=3
# mean +10.71% vs not-anchored n=3 mean +3.99% -- overlapping. SNDK carries the
# strongest anchor in the library ($93.9B contracted minimum with floor pricing)
# and FELL 6.81%; QCOM disclosed a hyperscaler deal with NO dollar figure and
# rose 15.00%. The anchor is a MAGNITUDE DAMPENER, not a direction signal:
# within the down-cohort SNDK's -6.81% is the smallest decline against WDC's
# -13.03% on a structurally identical setup.
#
# What separates the tail is NOVELTY. Not "is there a big number" but "is there
# a NEW commitment, and can I locate it." An existing commitment that goes
# unmentioned (CBRS's $20B OpenAI master agreement, absent from PR, 10-Q AND
# call) grades with the absences -- omission is an ACTION.

# NEW voids the short. With NEW-BUT-SPEND split out it is 4/5 UP, mean +11.43%,
# and the payoff is asymmetric: mean up-case +15.98% against a single down-case
# of -6.81%. "Stand down" discards a permissive long with favourable asymmetry.
_NOVELTY_UNRELIABLE = frozenset(('NEW',))

# ── Precedence rule 1: the peak-cycle override ────────────────────────────────
#
# SNDK is the one NEW case that fell, and it is not unexplained: cyclical sector
# (Semiconductors / Memory) + explicit peak-cycle language + inline-vs-bogey.
# That is the Peak-Cycle Buyside-Inline Fade rule, whose founding case is MU
# Q3 FY26 in the SAME sector. Two rules pointed opposite ways; this defines
# which wins.
#
# Sector alone is NOT sufficient -- QCOM is also Semiconductors and rose 15.00%.
# The discriminator is the peak-cycle PHRASE, and it must be a tight phrase:
# QCOM's record is full of "cycle bottom", "trough" and "inventory bottoming",
# which is the OPPOSITE of peak-cycle, and NOW's carries "vs >50% at peak" in a
# growth-rate sense plus "sales-cycle". A loose /cycle|peak/ test false-positives
# on both.
# ★ THE VALIDATED PREDICATE, adopted verbatim. Kyle measured
# `semiconduct|memory|hardware|storage` against the library and it flagged SNDK
# ALONE -- 1 true positive, 0 false positives. My own version added
# `nand|dram|semis|substrat|wafer|wfe|commodit|mining|shipping|refin|chemical`
# and dropped `hardware`.
#
# On the current 76 records mine was a strict SUBSET (28 sectors against 30, the
# two being DELL's "Enterprise Hardware" and IBM's "IT Services / Hardware"), so
# it could not have produced a new false positive TODAY. But in PATTERN space it
# is strictly broader: "Chemicals", "Shipping / Tankers", "Copper Mining" and
# "Oil Refining" all match mine and none match the validated one. The first
# commodity or shipping record written would have been judged by an alternation
# that was never measured, and it would have inherited a 1 TP / 0 FP reputation
# it had no claim to.
#
# A predicate does not inherit validation by being similar to a validated one.
# So: the measured pattern, unmodified. The dropped terms are recorded above as
# a hypothesis to be measured if a cyclical non-semi record ever lands.
_CYCLICAL_SECTOR = re.compile(r'semiconduct|memory|hardware|storage', re.I)

_PEAK_CYCLE_LANG = re.compile(
    r'peak[-\s]cycle|cycle[-\s]peak|peak of the cycle|late[-\s]cycle|'
    r'stretched cycle|peak[-\s]cycle positioning', re.I)

# ── The inline leg ────────────────────────────────────────────────────────────
#
# LESSONS E6 puts the nuke-crush bar at >110% of bogey, so for a DOLLAR- or
# VOLUME-denominated hero clearance above +10% breaks the override.
#
# ★ IT DOES NOT TRANSPOSE TO A PERCENTAGE HERO. E6 was derived on MU, a
# dollar/volume hero. Applied as a RATIO to a percentage metric it becomes
# nonsense: a 40.0% gross-margin bogey x 1.10 = 44.0%, a +400bp beat. That is
# not a high bar, it is an impossibility.
#
# The library carries NO calibrated nuke-crush threshold in basis points, so for
# a percentage hero the inline leg DEFERS -- it returns None and the record
# falls through to precedence rule 2 with the reason stated. Inventing a bp
# threshold would be fabricating the one number the override turns on
# (non-negotiable 7).
_INLINE_VS_BOGEY_MAX_PCT = 10.0

_PERCENT_UNITS = frozenset(('%', 'bps'))
_DOLLAR_UNITS = frozenset(('$b', '$m', '$k', '$', 'gwh', 'mw'))


def hero_denomination(hero):
    """('DOLLAR' | 'PERCENT' | 'UNCLASSIFIED', evidence).

    Resolved from the KPI NAME first, with the profile's `unit` field as a
    fallback -- because `unit` is wrong on three profiles. NBIS, CRWV and CBRS
    all declare unit "%" while their names read "Adjusted EBITDA ($M)",
    "Adjusted Operating Income ($M)" and "Hardware Revenue ($M)". Those are
    dollar heroes, and trusting `unit` would defer their inline leg for no
    reason. The conflict is reported so it can be fixed at the source.
    """
    from . import units as _u
    name = (hero or {}).get('name') or ''
    unit = (hero or {}).get('unit')

    def classify(u):
        if not u:
            return None
        low = str(u).lower()
        if low in _PERCENT_UNITS:
            return 'PERCENT'
        if low in _DOLLAR_UNITS:
            return 'DOLLAR'
        return None

    from_name = classify(_u.unit_from_kpi_name(name))
    from_unit = classify(unit)
    conflict = bool(from_name and from_unit and from_name != from_unit)
    resolved = from_name or from_unit or 'UNCLASSIFIED'

    return resolved, dict(
        heroName=name, unitField=unit,
        unitFromName=_u.unit_from_kpi_name(name),
        resolvedFrom=('name' if from_name else
                      'unit field' if from_unit else 'neither'),
        nameUnitConflict=conflict,
        conflictNote=(
            'profile unit %r disagrees with the name %r — the NAME wins; fix '
            'the profile' % (unit, _u.unit_from_kpi_name(name))
            if conflict else None))


def _pre_print_text(entry):
    """Concatenate ONLY fields that exist before the print.

    Reading post-print fields (summaries, callCommentary, takeaways, actuals)
    would make this work in backtest and fail live. SNDK's peak-cycle phrase
    sits in scenarioLadder[].basedOn, which the pre-earnings build writes.
    """
    parts = []
    for key in ('setup', 'whatMattersMost', 'bearCase', 'bullCase',
                'bogeyMethod', 'bogeyReliability', 'marketRegime'):
        v = (entry or {}).get(key)
        if isinstance(v, str):
            parts.append(v)
    ctx = (entry or {}).get('stockContext')
    if isinstance(ctx, dict):
        for v in ctx.values():
            if isinstance(v, str):
                parts.append(v)
    pa = (entry or {}).get('positioningAxis')
    if isinstance(pa, dict):
        for k in ('rationale', 'band', 'note'):
            if isinstance(pa.get(k), str):
                parts.append(pa[k])
    for branch in ((entry or {}).get('scenarioLadder') or []):
        if isinstance(branch, dict):
            for k in ('basedOn', 'positioningContext', 'branch', 'trigger'):
                if isinstance(branch.get(k), str):
                    parts.append(branch[k])
    return '\n'.join(parts)


_STAR = re.compile(r'★')

# A reading is COHERENT if it describes an outcome a business could actually
# print. -99.90% is coherent -- revenue really can collapse. +94,263% is not.
# The bound is D6's suppression threshold.
_COHERENT_PCT = 300.0


def _scale_consistent_clearance(bogey_raw, bogey_musd, actual):
    """Resolve the actual's unit when it is NOT declared, or REFUSE.

    ★ Never prefer. When both readings are coherent, and when neither is, the
    row is refused and the caller tries the next candidate.

    The reason is that a real collapse and a unit error are indistinguishable
    without a declaration. A bogey of 9.5 ($B) against a bare actual of 9.5
    reads as either +0.00% (inline, actual in $B) or -99.90% (a collapse,
    actual in $M). Both are coherent business outcomes, so preferring one turns
    a catastrophic miss into "inline" -- the single worst direction for this
    error to run.

    Only when exactly one reading is coherent is the answer forced. SNDK's
    "FQ4 Revenue ($B)" with an actual of 8965 reads +94,263% as $B, which no
    company prints, so $M is the only coherent reading at -5.63%.
    """
    readings = []
    if bogey_raw:
        readings.append(('row unit',
                         (actual - bogey_raw) / abs(bogey_raw) * 100.0))
    if bogey_musd:
        readings.append(('$M', (actual - bogey_musd) / abs(bogey_musd) * 100.0))

    coherent = [(basis, c) for basis, c in readings if abs(c) <= _COHERENT_PCT]
    detail = ', '.join('%s %+.1f%%' % (b, c) for b, c in readings)

    # ★ The two readings only DIFFER when the row's unit is not already $M. On a
    # ($M) row kpi_to_musd is a no-op, so both readings are the same number and
    # there is nothing to resolve -- refusing there rejected every ($M) row and
    # broke the CBRS pin. Collapse identical readings before judging ambiguity.
    if len(coherent) == 2 and abs(coherent[0][1] - coherent[1][1]) < 1e-9:
        return coherent[0][1], 'unambiguous (row unit == $M)', None

    if len(coherent) == 1:
        return coherent[0][1], coherent[0][0], None
    if len(coherent) > 1:
        return None, None, (
            'BOTH readings are coherent (%s) and no actualUnit is declared — '
            'a real collapse and a unit error are indistinguishable here, so '
            'this row is REFUSED rather than preferring one' % detail)
    return None, None, (
        'NEITHER reading is coherent (%s) — refusing rather than grading a '
        'scale mismatch' % detail)


def dollar_hero_fallback(entry, kpi_rows):
    """The clearance-leg fallback. Returns (clearance_pct, evidence).

    When the priority-1 hero is percentage-denominated, deferring the clearance
    leg makes precedence rule 1 unreachable in practice -- a rule that can never
    fire is decorative, and silently so. Instead, grade the leg on the
    highest-priority DOLLAR-denominated ★ row that has a numeric bogey and is
    not flagged unverified.

    This invents no threshold: it reuses E6's >110% ratio on the metric type E6
    was actually derived on.

    On SNDK it lands on FQ4 Revenue ($B) -- bogey 9.5 against an actual of
    8.965B, a -5.63% MISS against the buyside bogey, which E6 grades MAX SHORT
    (stronger than inline). That row is NOT one of the four flagged implausible,
    so the fallback routes AROUND the unverified GM and EPS rows rather than
    depending on them.

    Scope: the clearance leg ONLY. Never hero selection, never Current Quarter.

    ★ Guard: consensus is NEVER substituted for a missing bogey. The three
    grading columns are bogey / street / own-guide, and quietly reading a
    different one changes what the rule means.
    """
    rows_by_name = {r.get('name'): r for r in (kpi_rows or [])}
    record_quarter = (entry or {}).get('quarter')
    candidates = []

    for i, kpi in enumerate((entry or {}).get('keyKPIs') or []):
        name = kpi.get('name') or ''
        if not _STAR.search(name):
            continue
        if kpi.get('unverified') is True:
            continue                      # flagged -- route around it
        bogey = kpi.get('bogey')
        if not isinstance(bogey, (int, float)):
            continue                      # ★ never fall back to consensus
        from . import units as _u
        if not _u.is_dollar_magnitude(name):
            continue
        # The clearance leg is about THIS print against its bogey, so a forward
        # slot cannot serve -- grading a next-quarter guide row as "the print
        # landed inline" is the definitional mismatch of error class 6.
        from .score import _classify_period
        if _classify_period(name, record_quarter) != 'CURRENT_Q':
            continue
        row = rows_by_name.get(name) or {}
        # ★ Skip unitAmbiguous exactly as unverified is skipped. The four
        # flagged rows in the library are genuinely misaligned -- their notes
        # describe a different metric than the row name.
        if row.get('unitAmbiguous') is True:
            continue
        actual = row.get('actual')
        if not isinstance(actual, (int, float)):
            continue
        stars = len(_STAR.findall(name))
        candidates.append((-stars, i, name, bogey, actual,
                           row.get('actualUnit')))

    if not candidates:
        return None, dict(
            used=False,
            reason=('no dollar-denominated ★ row with a numeric, unflagged '
                    'bogey and a resolved actual — deferring, and NOT '
                    'substituting consensus for a missing bogey'))

    candidates.sort()
    from . import units as _u
    rejected = []
    for _neg_stars, idx, name, bogey, actual, declared in candidates:
        bogey_m, problem = _u.kpi_to_musd(bogey, name)
        if problem:
            rejected.append('%s: %s' % (name[:28], problem))
            continue

        if declared:
            # ★ Declared unit wins. Nothing to resolve, nothing to refuse.
            actual_m, dproblem = _u.declared_to_musd(actual, declared)
            if dproblem or actual_m is None:
                rejected.append('%s: declared actualUnit %r — %s'
                                % (name[:28], declared, dproblem))
                continue
            clearance = (actual_m - bogey_m) / abs(bogey_m) * 100.0
            basis, why_not = 'declared %s' % declared, None
        else:
            clearance, basis, why_not = _scale_consistent_clearance(
                bogey, bogey_m, actual)

        if clearance is None:
            rejected.append('%s: %s' % (name[:28], why_not))
            continue
        return clearance, dict(
            used=True, row=name, kpiIndex=idx, stars=-_neg_stars,
            bogey=bogey, bogeyMusd=bogey_m, actual=actual, scaleBasis=basis,
            clearancePct=round(clearance, 3), column='bogey',
            rejectedRows=rejected,
            note=('clearance leg graded on the highest-priority dollar ★ row '
                  'instead of the percentage hero — E6\'s ratio applied to the '
                  'metric type it was derived on (scale basis: %s). %s'
                  % (basis,
                     'a MISS against the buyside bogey, which E6 grades MAX '
                     'SHORT (stronger than inline)' if clearance < 0
                     else 'clears the bogey by %+.2f%%' % clearance)))

    return None, dict(
        used=False, rejectedRows=rejected,
        reason=('every dollar ★ candidate was rejected on scale grounds: %s'
                % '; '.join(rejected)[:200]))


def _quote_window(text, match, before=30, after=50):
    """A readable window around the matched phrase, trimmed to word boundaries.

    A raw character slice lands mid-token and reads as noise on the card --
    "ev guide >=$12.0B AND F1Q EPS guide >=$55 peak-cycle buyside-inline fade".
    """
    lo = max(0, match.start() - before)
    hi = min(len(text), match.end() + after)
    frag = ' '.join(text[lo:hi].split())
    if lo > 0 and ' ' in frag:
        frag = frag.split(' ', 1)[1]
        lo = 1
    if hi < len(text) and ' ' in frag:
        frag = frag.rsplit(' ', 1)[0]
    return ('…' if lo else '') + frag + ('…' if hi < len(text) else '')


def peak_cycle_override(entry, clearance_pct, kpi_rows=None):
    """Precedence rule 1. Returns (applies, evidence).

    Cyclical sector AND peak-cycle language AND inline-vs-bogey -> the
    Peak-Cycle Buyside-Inline Fade wins, the short stays live, and NEW is
    overridden.

    The inline leg is denomination-dependent and may be None (deferred), in
    which case the override cannot fire and the record falls to rule 2.
    """
    sector = str((entry or {}).get('sector') or '')
    cyclical = bool(_CYCLICAL_SECTOR.search(sector))
    text = _pre_print_text(entry)
    m = _PEAK_CYCLE_LANG.search(text)

    heroes = (entry or {}).get('heroes') or []
    denom, denom_ev = hero_denomination(heroes[0] if heroes else {})

    if denom == 'DOLLAR':
        inline = (clearance_pct is not None
                  and clearance_pct <= _INLINE_VS_BOGEY_MAX_PCT)
        inline_note = ('ratio test: clearance %s vs the >+%.0f%% nuke-crush bar'
                       % (('%+.2f%%' % clearance_pct)
                          if clearance_pct is not None else 'n/a',
                          _INLINE_VS_BOGEY_MAX_PCT))
    else:
        # ★ The hero is percentage-denominated, so E6's ratio cannot be applied
        # to it. Fall back to a dollar ★ row rather than deferring outright --
        # deferring made rule 1 unreachable in practice.
        fb_clearance, fallback = dollar_hero_fallback(entry, kpi_rows)
        if fallback.get('used'):
            inline = fb_clearance <= _INLINE_VS_BOGEY_MAX_PCT
            clearance_pct = fb_clearance
            inline_note = (
                'hero is %s-denominated (%s), so the clearance leg falls back '
                'to the dollar ★ row %r: %s. No bp threshold invented — E6\'s '
                'ratio applied to the metric type it was derived on.'
                % (denom.lower(), denom_ev['heroName'][:34],
                   fallback['row'][:34], fallback['note']))
        else:
            # No usable dollar ★ row. DEFER, and never read a different column.
            inline = None
            inline_note = (
                'INLINE LEG DEFERRED — the hero is %s-denominated (%s) and the '
                'dollar ★ fallback found nothing usable (%s). E6\'s '
                '>110%%-of-bogey bar is a RATIO; applied to a percentage metric '
                'it demands a ~400bp beat, which is not a high bar but an '
                'impossibility. No bp threshold is invented, and consensus is '
                'never substituted for a missing bogey.'
                % (denom.lower(), denom_ev['heroName'][:34],
                   fallback.get('reason', '')[:80]))
        denom_ev['dollarHeroFallback'] = fallback

    evidence = dict(
        cyclicalSector=cyclical, sector=sector,
        peakCycleLanguage=bool(m),
        peakCycleQuote=_quote_window(text, m) if m else None,
        inlineVsBogey=inline, inlineNote=inline_note,
        clearancePct=clearance_pct,
        heroDenomination=denom, denominationEvidence=denom_ev,
        # ★ The clearance leg rests on SNDK's expected column, which is flagged
        # implausible and unverified. Text legs are unaffected.
        clearanceLegProvisional=True,
        clearanceLegNote=(
            'PROVISIONAL: rule 1 was founded on SNDK-2026Q4, whose expected '
            'column is flagged domain-implausible and systematically so (FQ4 '
            'GM bogey 84.0 / cons 81.5 where memory GM runs ~30-40%). Four '
            'rows are unverified. The sector and peak-cycle legs are '
            'text-derived and unaffected; the clearance leg is not validated '
            'until the SNDK preview is re-sourced.'))

    applies = bool(cyclical and bool(m) and inline is True)
    return applies, evidence

# A taxonomy of absence. These reinforce the short: 1/6 up, mean -11.02%.
_NOVELTY_REINFORCES = frozenset(('ABSENT', 'WITHDRAWN', 'OMITTED', 'FLAT',
                                 'WEAK'))

# ★ Its own class. A capex commitment is a COST and the tape grades it as one.
# SPCX was labelled NEW-BUT-SPEND a priori and fell 12.00%; excluding it lifts
# NEW to 4/5 and +11.4% mean.
_NOVELTY_SPEND = frozenset(('NEW-BUT-SPEND',))


def _why_not(evidence):
    """Which leg of precedence rule 1 failed, so the reader can second-guess it."""
    missing = []
    if not evidence.get('cyclicalSector'):
        missing.append('sector %r not cyclical' % (evidence.get('sector') or '')[:30])
    if not evidence.get('peakCycleLanguage'):
        missing.append('no peak-cycle language in the pre-print fields')
    inline = evidence.get('inlineVsBogey')
    if inline is None:
        missing.append('inline leg DEFERRED (%s hero — no calibrated bp bar)'
                       % str(evidence.get('heroDenomination')).lower())
    elif not inline:
        missing.append('not inline vs bogey (clearance %s)'
                       % evidence.get('clearancePct'))
    return '; '.join(missing) or 'all legs held'


def forward_commitment_context(record, band, findings, clearance_pct=None,
                               kpi_rows=None):
    """Cohort context for the STAY_FOR_CALL tail. NEVER folded into a score.

    Gated on presence: only 12 of 76 records carry a `forwardCommitment` block,
    so when it is absent the card must say the separator is unavailable rather
    than imply a neutral reading.

    Precedence, from the library's ★noveltyPrecedence:
      1. cyclical + peak-cycle + inline-vs-bogey -> PEAK-CYCLE FADE WINS
      2. NEW                                    -> the short is VOID
      3. NEW-BUT-SPEND                          -> reinforces (a cost)
      4. absence class                          -> reinforces
      5. NONE                                   -> no signal
    """
    fc = (record or {}).get('forwardCommitment')
    if not isinstance(fc, dict) or not fc.get('novelty'):
        return dict(
            available=False,
            applies=band == 'STAY_FOR_CALL',
            note=('no forwardCommitment block on this record — the tail '
                  'separator is UNAVAILABLE, so the 78% short base rate '
                  'carries its full unseparated tail risk (only 12 of 76 '
                  'records are classified)'))

    novelty = str(fc['novelty']).upper()
    out = dict(available=True, applies=band == 'STAY_FOR_CALL',
               novelty=novelty, present=fc.get('present'),
               structure=fc.get('structure'),
               locationInFiling=fc.get('locationInFiling'),
               customerNamed=fc.get('customerNamed'),
               dollarAmount=fc.get('dollarAmount'),
               quote=fc.get('quote'),
               n=(findings or {}).get('n'))

    if novelty in _NOVELTY_SPEND:
        out.update(
            klass='NEW-BUT-SPEND',
            reliability='REINFORCES',
            verdict=('NEW-BUT-SPEND — a capex/spending commitment, not a '
                     'revenue commitment. A cost, and the tape grades it as '
                     'one. Founding case SPCX -12.00%, classified a priori.'))
    elif novelty in _NOVELTY_UNRELIABLE:
        overridden, evidence = peak_cycle_override(record, clearance_pct,
                                                  kpi_rows)
        out['peakCycleEvidence'] = evidence
        if overridden:
            # ★ PRECEDENCE RULE 1. This is SNDK.
            out.update(
                klass='NEW (overridden)',
                reliability='REINFORCES',
                precedenceRule=1,
                verdict=('PEAK-CYCLE FADE WINS — NEW is OVERRIDDEN and the '
                         'SHORT STAYS LIVE. Cyclical sector (%s) + peak-cycle '
                         'language + inline-vs-bogey (%s). At stretched cycle '
                         'positioning, inline against a stretched bogey is a '
                         'sell; only a nuke-crush >110%% of bogey saves it.'
                         % (evidence['sector'][:40],
                            ('%+.2f%%' % clearance_pct)
                            if clearance_pct is not None else 'n/a')),
                postHocCaveat=(
                    '★ POST-HOC: this separating rule was selected AFTER '
                    'seeing which NEW record fell — 1 true positive, 0 false '
                    'positives on n=5. What keeps it out of pure curve-fitting '
                    'is that the Peak-Cycle Buyside-Inline Fade already existed '
                    'in LESSONS.md with an INDEPENDENT founding case (MU Q3 '
                    'FY26, same sector) predating this test. Treat as ONE '
                    'confirmation, not a validated hierarchy. The next '
                    'cyclical peak-cycle NEW print is the real test.'),
                rejectedAlternative=(
                    'REJECTED: "fyGuidance == 0.0 outranks NEW" was the more '
                    'obvious rule and it false-positives on NOW-2026Q2 — NEW, '
                    'fy 0.0, and it rose +4.80%.'))
        else:
            out.update(
                klass='NEW',
                reliability='SHORT VOID',
                precedenceRule=2,
                verdict=('SHORT VOID — long permissive, unsized (n=5). '
                         '4/5 up, mean +11.43%, and the payoff is asymmetric: '
                         'mean up-case +15.98% against a single down-case of '
                         '-6.81%. This is a tradeable asymmetry, not ambiguity '
                         '— but it is UNSIZED at n=5.'),
                postHocCaveat=(
                    'Precedence rule 1 (the peak-cycle override) did not fire '
                    'here: %s. That rule is post-hoc on n=5 — if this name is '
                    'cyclical and you read peak-cycle framing anywhere the '
                    'card does not, the short may still be live.'
                    % _why_not(evidence)))
    elif novelty in _NOVELTY_REINFORCES:
        out.update(
            klass='ABSENCE',
            reliability='REINFORCES',
            verdict=('%s — a taxonomy-of-absence case, which REINFORCES the '
                     'short. (n=6, up 1/6, mean -11.02%%.) Omission is an '
                     'action.' % novelty))
    else:
        # NONE: TSLA-2026Q1 was present=False yet rose +4.00% on FCF, an
        # unrelated axis. Not evidence for either side.
        out.update(
            klass='NO SIGNAL',
            reliability='NO SIGNAL',
            verdict=('novelty %s carries no tail signal — the TSLA exception '
                     'rose on an unrelated axis (FCF), so this neither '
                     'reinforces nor undermines the base rate.' % novelty))

    if fc.get('dollarAmount') is not None:
        out['dollarNote'] = (
            '$%.1fB anchor — MAGNITUDE DAMPENER ONLY, not direction. The '
            '$-anchor direction hypothesis is falsified.' % fc['dollarAmount'])

    out['caveat'] = (findings or {}).get('caveats')
    return out


def fy_inline_context(fy_score, framework_inline):
    """"INLINE = BEARISH SKEW" context when fyGuidance resolves to 0.0.

    A neutral FY category score is a BEARISH outcome signal: FY carries 30%
    weight and is graded against a bar the market already raised, so landing
    inline is the absence of the raise that was priced. Cohort context only --
    never folded into the score, same discipline as the positioning line.
    """
    if fy_score != 0.0 or not framework_inline:
        return None
    return dict(
        label='INLINE = BEARISH SKEW (8/11 down, mean -6.85%)',
        n=framework_inline.get('n'),
        why=framework_inline.get('why'),
        caveat=framework_inline.get('caveat'),
        absenceVsInline=framework_inline.get('absenceVsInline'),
        foldedIntoScore=False)


def assert_containment(bracket, overall):
    """Assert the stored overall lies inside the bracket.

    Called on every run. Containment is arithmetically guaranteed, so a failure
    is a genuine bug rather than an edge case to tolerate.
    """
    if not isinstance(overall, (int, float)):
        return None
    lo, hi = bracket
    if not (lo - 1e-9 <= overall <= hi + 1e-9):
        raise BracketContainmentError(
            'overall %.4f outside bracket [%.4f, %.4f] — containment is '
            'arithmetically guaranteed, so this is a real bug'
            % (overall, lo, hi))
    return True
