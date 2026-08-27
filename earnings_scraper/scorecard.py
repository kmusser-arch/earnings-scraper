"""Adapter to the ONE renderer: render_scorecard.render(rec, framework).

★ There is no formatter in this package. The scraper builds a record dict, calls
render(), and emits the result verbatim. A second formatter would drift from the
chat path within a print or two, and the whole point of the locked format is that
identical input produces byte-identical output on both paths.

render_scorecard.py lives in the model repo and is loaded by ABSOLUTE path -- not
copied here -- for the same reason the library is: a copy goes stale.

What the scraper can fill mechanically:
    hero KPI table, three category scores, the bracket, the novelty separator,
    the branch match, the flags
What only the call can fill:
    narrative, the four one-sentence reads, key takeaways
Those are left None/empty so render() emits its own explicit deferral markers.
"""

import importlib.util
import os

from . import config
from . import flat
from . import units
from . import score

_MODULE = None


class RendererMissing(Exception):
    """render_scorecard.py could not be loaded. Do NOT fall back to a local
    formatter -- that is the drift this module exists to prevent."""


def renderer():
    """Load render_scorecard from the model repo, once."""
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    path = os.path.join(config.LIB_DIR, 'render_scorecard.py')
    if not os.path.exists(path):
        raise RendererMissing(
            'render_scorecard.py not found at %s. Refusing to format locally: '
            'a parallel formatter would drift from the chat path.' % path)
    spec = importlib.util.spec_from_file_location('render_scorecard', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODULE = mod
    return mod


class RendererFunctionMissing(Exception):
    """A display/verdict function could not be loaded from the model repo.

    ★ Same discipline as PolarityPredicateMissing: REFUSE rather than
    reimplement. `_display_actual` and `_verdict_cell` decide what number the
    trader reads and whether the cell is green, and a divergent copy of either
    is the worst class of bug this project has -- it fails in the BULLISH
    direction, on the rows that decide the trade, and it fails silently. A green
    cell on a revenue guide reads as confirmation.
    """


def _renderer_function(attr):
    """Load one function from render_scorecard and PROVE where it came from.

    The proof matters: an import that silently fell back to a local definition
    would pass every test that only checks the OUTPUT of the pipeline, because
    the local copy would be self-consistent. So the module file is asserted to
    be the model repo's render_scorecard.py.
    """
    mod = renderer()
    fn = getattr(mod, attr, None)
    if fn is None or not callable(fn):
        raise RendererFunctionMissing(
            'render_scorecard.%s is missing. Refusing to reimplement it: a '
            'divergent copy renders a false CLEAR on a missed guide.' % attr)
    src = getattr(fn, '__module__', None)
    mod_file = getattr(mod, '__file__', '') or ''
    fn_file = getattr(getattr(fn, '__code__', None), 'co_filename', '')
    if not mod_file.replace('\\', '/').lower().endswith(
            'render_scorecard.py'):
        raise RendererFunctionMissing(
            'render_scorecard resolved to %r, not the model repo file' % mod_file)
    if fn_file and fn_file != mod_file:
        raise RendererFunctionMissing(
            '%s was defined in %r, not in %r -- that is a divergent copy'
            % (attr, fn_file, mod_file))
    if src and 'earnings_scraper' in str(src):
        raise RendererFunctionMissing(
            '%s resolved to a LOCAL definition (%s)' % (attr, src))
    return fn


def display_actual(name, actual_row):
    """render_scorecard._display_actual. Imported, never reimplemented."""
    return _renderer_function('_display_actual')(name, actual_row)


def verdict_cell(actual_row, pre_row=None):
    """render_scorecard._verdict_cell. Imported, never reimplemented."""
    return _renderer_function('_verdict_cell')(actual_row, pre_row)


def assert_render_functions():
    """Startup assertion: both functions load, from the model repo, and CONVERT.

    ★ The behavioural half is the point. Both functions convert a $M value into
    a ($B)-named row ONLY when `actualUnit` is present -- with the unit absent
    they print the raw number and grade it against a $B expectation, which is a
    false 🟢 CLEAR on a row that missed. So the assertion checks the conversion
    actually happens, not merely that the symbol resolved.

    APP-2026Q2 row [2] is the pin: raw 2070 in "3Q Revenue Guide ($B)" against a
    2.08 street must read 2.07 and 🔴 MISS. APP fell 19.66% on that print.
    """
    name = '3Q Revenue Guide ($B) \u2605'
    ak = dict(actual=2070, actualUnit='$M')
    pk = dict(name=name, consensus=2.08, bogey=2.12)
    shown = display_actual(name, ak)
    verdict = verdict_cell(ak, pk)
    if '2.07' not in shown or '$B' not in shown:
        raise RendererFunctionMissing(
            '_display_actual did not convert: 2070 ($M) in a ($B) row rendered '
            '%r, expected "2.07 ($B)". The suffix without the division is the '
            'signature of a divergent copy.' % shown)
    if 'MISS' not in verdict:
        raise RendererFunctionMissing(
            '_verdict_cell graded the UNCONVERTED number: 2070 vs a 2.08 '
            'street returned %r, expected a MISS.' % verdict)
    return True


def undeclared_magnitude_rows(record):
    """Rows that would render a raw magnitude against a scaled expectation.

    ★ THE REACHABLE FAILURE. Both renderer functions key their conversion on
    `actualUnit`; with it absent a $M value in a ($B) row prints as "2,070" and
    grades 🟢 CLEAR against a 2.12 bogey. 92 dollar-magnitude rows in the
    library carry no actualUnit today -- none of them currently holds a
    thousand-fold value, so none renders wrong, but nothing PREVENTS the next
    one. This is checked before render() is handed anything.
    """
    pre = ((record or {}).get('preEarnings') or {}).get('keyKPIs') or []
    act = ((record or {}).get('actuals') or {}).get('keyKPIs') or []
    out = []
    for i, kpi in enumerate(pre):
        name = (kpi or {}).get('name') or ''
        if not units.is_dollar_magnitude(name):
            continue
        row = act[i] if i < len(act) and isinstance(act[i], dict) else {}
        val = row.get('actual')
        if not isinstance(val, (int, float)) or row.get('actualUnit'):
            continue
        ref = None
        for key in ('bogey', 'consensus'):
            if isinstance(kpi.get(key), (int, float)):
                ref = kpi[key]
                break
        if not ref:
            continue
        ratio = abs(val) / abs(ref)
        if ratio >= 100.0:
            out.append((i, name, val, ref, ratio))
    return out


def row_name(pre_row):
    """render_scorecard._row_name. Imported, never reimplemented.

    ★ TWO SCHEMA VARIANTS for the same field. 31 rows across AEHR-2026Q4,
    NFLX-2026Q2 and TSLA-2026Q2 store the metric under 'metric' and the street
    under 'cons'. A reader that knows only 'name' printed the literal string
    "None" six times on AEHR's card, and TSLA-2026Q2's entire cap-the-model read
    -- Auto GM 16.3% against 19.2%, FCF -$1.09B, Robotaxi language removed, AI5
    slipped to mid-2027 -- was invisible. The data was never missing; the reader
    was looking in one of two places.
    """
    return _renderer_function('_row_name')(pre_row)


def row_cons(pre_row):
    """render_scorecard._row_cons. Companion to row_name."""
    return _renderer_function('_row_cons')(pre_row)


_READ_CATS = ('currentQuarter', 'nextQGuidance', 'fyGuidance', 'narrative')


def active_event_flag(record):
    """The flag, only when it is LIVE. None for withdrawn or unfired.

    ★ CRM-2027Q1 carries `withdrawn: True` with a withdrawnReason -- the flag was
    retracted on calibration review. A retracted flag does not demand a
    narrative read on the same footing as a live one, and it is the single
    record separating 15 flagged-without-reads from the 14 that actually matter.
    """
    flag = (record or {}).get('asymmetricEventFlag')
    if not isinstance(flag, dict):
        return None
    if flag.get('withdrawn'):
        return None
    if 'fired' in flag and not flag.get('fired'):
        return None
    return flag


def read_state_kind(record):
    """'pending' for a PR-only card, 'stored' for a completed one.

    ★ ORDER MATTERS AND IT BIT BOTH COPIES OF THIS GUARD. 'SCORED-PR-ONLY'
    starts with 'SCORED', so a `startswith('SCORED')` test calls a PR-only card
    a completed record -- and then reports a build-regression DEFECT against a
    read that nobody was supposed to have written yet. PR-ONLY has to be tested
    first, because it is a SUFFIX on a string whose PREFIX means the opposite.
    Same species as 'MAJOR MISS' containing no 'STREET'.

    GTLB-2027Q1 and NFLX-2026Q2 are the two records this reclassifies: their
    missing reads are legitimate pending-call state, so the population is 12
    defects and 2 pending, not 14 defects.
    """
    status = str((record or {}).get('status') or '').upper()
    if 'PR-ONLY' in status:
        return 'pending'
    if status.startswith('SCORED'):
        return 'stored'
    return 'live'


def _is_pending_card(record):
    """PRE-EARNINGS with no actuals: the print has not happened.

    ★ Its category reads are absent because reads are written FROM THE CALL.
    That is not the missing-deliverable defect this module hunts -- it is the
    normal state of a card built this morning for tonight's print.
    """
    rec = record or {}
    if str(rec.get('status') or '').upper() != 'PRE-EARNINGS':
        return False
    return not ((rec.get('actuals') or {}).get('keyKPIs') or [])


def flagged_without_read(record, kind=None):
    """An ACTIVE asymmetric event flag on a card carrying no category read.

    ★ WHY THIS IS GUARDED AT RENDER TIME AND NOT LEFT TO THE AUDIT.
    A flag means STAY FOR THE CALL, so the narrative read IS the deliverable --
    the failure lands precisely on the prints where it costs most. And it is a
    LIVE bug, not history: the branch worked on ZS-2026Q3 at 15:00 on
    2026-05-27 and failed on MRVL-2027Q1 at 19:00 the same day, and the 25
    records built since the last flagged one (TSLA-2026Q2, 2026-07-27) include
    NONE that fire the flag. So there is no evidence of a fix, only an absence
    of tests -- the next flagged print takes the same branch.

    `kind` changes the WORDING, not the predicate. On a stored record the reads
    were supposed to exist, so their absence is a defect. On a live card at 4:01
    they have not been written yet, so the same condition is a reminder that
    this is the print that needs them.
    """
    if _is_pending_card(record):
        return None
    if not active_event_flag(record):
        return None
    if kind is None:
        kind = read_state_kind(record)
    scores = (record or {}).get('scores') or {}
    summaries = (record or {}).get('summaries') or {}
    scored = [c for c in _READ_CATS
              if isinstance(scores.get(c), (int, float))]
    if kind == 'stored' and not scored:
        return None
    if any(str(summaries.get(c) or '').strip() for c in scored or _READ_CATS):
        return None
    if kind in ('live', 'pending'):
        return ('\u26a0 FLAGGED PRINT, READ PENDING THE CALL — this card fires '
                'an asymmetric event flag, which means STAY FOR THE CALL: the '
                'one-sentence category reads ARE the deliverable here, and on a '
                'PR-only print they are not written yet. NOT a defect.')
    return ('\u26d4 FLAGGED PRINT WITH NO CATEGORY READ — an active asymmetric '
            'event flag and %d scored categor%s, and not one one-sentence read. '
            'On a flagged print the read is the deliverable. 14 records share '
            'this shape and every one carries the flag, so suspect the '
            'flag branch rather than the record.'
            % (len(scored), 'y' if len(scored) == 1 else 'ies'))


def coerce_bogey(bogey):
    """render_scorecard._coerce_bogey. Imported, never reimplemented.

    ★ A bogey written '>800' is a NUMBER. CIFR-2026Q2's "Average annualized NOI
    ($M)" has street 787, bogey '>800', actual 793 -- a FADE-ZONE row, beats
    street and misses bogey, which is the single most consequential cell in the
    model (7 of 9 fall). Read as prose it fell through to the no-numeric-bogey
    branch and rendered a clean beat.

    Importing it matters for a second reason: the row VERDICT and the category
    SCORE must not disagree. If the renderer coerces '>800' and my grader still
    treats it as prose, the card shows FADE while the category grades as though
    no bogey existed -- the same split that put a bare +0.00 under a 🔴 MISS on
    CRM. Only unambiguous single figures coerce; ranges stay prose.
    """
    return _renderer_function('_coerce_bogey')(bogey)


def bogey_direction(bogey):
    """render_scorecard._bogey_direction -> 'lower' | 'higher'. Imported.

    ★ A '<' or '≤' BOGEY MEANS LOWER IS BETTER, and it inverts BOTH legs.
    AMAT-2026Q2 'China Revenue (% of total) ★★' has bogey '<25% + no
    incremental restrictions' -- concentration RISK. 27% against a <25% bar is
    a MISS, and `actual >= bogey` calls it 🟢 CLEAR: exactly backwards on a
    hero row. CRWV, CRDO and SPCX carry the same shape.

    This is a SECOND, INDEPENDENT direction signal from `is_reverse_polarity`.
    That one reads the metric NAME (capex, opex, churn) and REFUSES, because
    the sign is contextual. This one reads the bogey's OPERATOR, where the
    direction is stated outright -- so it inverts rather than refuses. 'China
    Revenue (% of total)' matches no cost-metric word, so only the operator
    reveals which way is good.
    """
    return _renderer_function('_bogey_direction')(bogey)


def coerce_consensus(consensus):
    """render_scorecard._coerce_consensus -> (value, strict). Imported.

    ★ THE OPERATOR IS PART OF THE THRESHOLD, and it has to survive the
    coercion. SPCX-2026Q2 'Starlink subs (M) ★' has street '>12' and an actual
    of 12.0. Twelve does not exceed twelve, so that is a street MISS -- and
    coercing '>12' to a bare 12 and then comparing with >= turns the miss into
    a TIE, which is the opposite error. So `strict` travels with the number:
    '>' and '<' are strict, '>=' / '<=' / a bare figure are not.
    """
    return _renderer_function('_coerce_consensus')(consensus)


def canonicalise_kpis(pre_rows):
    """COPIES of `pre_rows` with 'name' and 'consensus' filled from the aliases.

    ★ Applied at the BOUNDARY rather than at each of the 55 places this package
    reads a KPI's name or consensus. Editing 55 call sites can be partially
    applied and silently leave one behind; normalising once as the rows enter
    cannot. The alias logic itself is still the imported one, so there remains a
    single definition of where the field lives.

    Never mutates the library record -- Model holds those dicts.
    """
    out = []
    for row in pre_rows or []:
        if not isinstance(row, dict):
            out.append(row)
            continue
        fixed = dict(row)
        if not fixed.get('name'):
            fixed['name'] = row_name(row)
        if fixed.get('consensus') is None:
            fixed['consensus'] = row_cons(row)
        # ★ '>800' becomes 800.0 here, so every downstream comparison sees the
        # same number the verdict cell sees. The ORIGINAL is kept under
        # bogeyRaw, because the '>' is a real qualifier a human may need.
        # ★ Direction FIRST, from the raw string. Coercion strips the operator,
        # so reading it afterwards would always answer 'higher'.
        fixed['bogeyDirection'] = bogey_direction(fixed.get('bogey'))
        coerced = coerce_bogey(fixed.get('bogey'))
        if coerced is not fixed.get('bogey'):
            fixed['bogeyRaw'] = fixed.get('bogey')
            fixed['bogey'] = coerced
        # ★ Consensus too, with the operator preserved as `consensusStrict`.
        # Storing only the number would silently relax '>12' into '12'.
        cval, cstrict = coerce_consensus(fixed.get('consensus'))
        if cval is not fixed.get('consensus'):
            fixed['consensusRaw'] = fixed.get('consensus')
            fixed['consensus'] = cval
        fixed['consensusStrict'] = bool(cstrict)
        out.append(fixed)
    return out


def record_from_card(card, entry):
    """Assemble the record dict render() expects.

    The pre/actual arrays are rebuilt as two positionally-aligned lists, since
    that is the contract render() asserts on. `unverified` and `unitAmbiguous`
    are written on BOTH sides of each pair -- render checks either side, and the
    library carries them on either side too.
    """
    pre_src = entry.get('keyKPIs') or []
    rows = card.get('keyKPIs') or []

    pre, act = [], []
    for i, src in enumerate(pre_src):
        row = rows[i] if i < len(rows) else {}
        unverified = bool(src.get('unverified') or row.get('unverified'))
        ambiguous = bool(src.get('unitAmbiguous') or row.get('unitAmbiguous'))
        pre.append(dict(
            name=src.get('name'),
            consensus=src.get('consensus'),
            bogey=src.get('bogey'),
            unverified=unverified or None,
            unitAmbiguous=ambiguous or None))
        act.append(dict(
            actual=row.get('actual'),
            actualUnit=row.get('actualUnit'),
            vsCons=row.get('vsCons'),
            vsBogey=row.get('vsBogey'),
            unverified=unverified or None,
            unitAmbiguous=ambiguous or None))

    return dict(
        ticker=card.get('ticker'),
        company=card.get('company'),
        quarter=card.get('quarter'),
        status=card.get('status'),
        # ★ PROVENANCE, STAMPED AT THE MOMENT OF WRITING. The library reserves
        # 'extractor' alongside the 80 'hand-written' records so the reads
        # hypothesis can be scoped to the population the flag branch actually
        # governs. Reserving the value is useless unless the write path sets
        # it -- without this line the first machine-written record would be
        # indistinguishable from a hand-written one, and the hypothesis would
        # quantify over an empty set forever while appearing to wait.
        provenance='extractor',
        extractedAt=card.get('receivedAt'),
        extractedFrom=card.get('wire'),
        # ★ narrative stays None; the three others carry what was graded.
        scores=dict(card.get('scores') or {}),
        preEarnings=dict(keyKPIs=pre),
        actuals=dict(keyKPIs=act),
        # ★ Left empty on purpose -> render() emits its deferral markers.
        summaries={},
        takeaways=[],
        asymmetricEventFlag=entry.get('asymmetricEventFlag'),
        positioningAxis=entry.get('positioningAxis'),
        # The RAW block, not the gate's derived context -- render() maps
        # novelty itself, and passing a doctored novelty would be falsifying it.
        forwardCommitment=entry.get('forwardCommitment'),
        # render() handles a null `branch` itself now, so the block is passed
        # through as-is.
        branchMatched=card.get('branchMatched'),
        # ★ render() prints the cohort warning on the Next Quarter line from
        # this flag. Context only -- the score is untouched.
        nextQFadeZone=(True if card.get('nextQFadeZone') else None),
        # The tie state. render() prints a separate line for it, pointing at
        # the inline rules rather than the fade-zone cohort.
        nextQInline=(True if card.get('nextQInline') else None),
        # Ready for a renderer line; harmless until one exists.
        nextQToleranceMiss=(True if card.get('nextQToleranceMiss') else None),
        nextQTolerancePct=card.get('nextQTolerancePct'),
    )


def precedence_from_card(card):
    """The gate's precedence verdict, in the shape render() expects.

    render() DISPLAYS this; it never re-derives it. Passing nothing makes
    render() print an explicit "PRECEDENCE NOT EVALUATED — this line is
    UNQUALIFIED" warning, so a bare SHORT VOID can no longer render silently
    on a record where rule 1 fires.

    ★ RETURNING None FOR A NON-NEW NOVELTY IS CORRECT -- DO NOT "FIX" IT.
    render() distinguishes three states, and it keys them on this value being
    FALSY together with the record's own novelty:

        precedence truthy                 -> "rule N evaluated: no override"
        precedence falsy + novelty != NEW -> "rule 1 NOT APPLICABLE -- it
                                             overrides NEW only"
        precedence falsy + novelty == NEW -> "PRECEDENCE NOT EVALUATED" warning

    So returning a dict here for a non-NEW novelty would route TSLA-2026Q1 into
    the FIRST branch and print "evaluated: no override" -- suppressing the
    NOT-APPLICABLE determination and asserting an evaluation that never ran.
    The third state lives in the renderer by design; None is how it is reached.
    """
    fc = card.get('forwardCommitment') or {}
    rule = fc.get('precedenceRule')
    if not rule:
        return None

    ev = fc.get('peakCycleEvidence') or {}
    bits = []
    if rule == 1:
        bits.append('cyclical sector (%s)' % (ev.get('sector') or '?'))
        if ev.get('peakCycleQuote'):
            bits.append('peak-cycle language: "%s"'
                        % ' '.join(str(ev['peakCycleQuote']).split())[:90])
        if ev.get('clearancePct') is not None:
            bits.append('inline vs bogey %+.2f%%' % ev['clearancePct'])
        fb = (ev.get('denominationEvidence') or {}).get('dollarHeroFallback')
        if fb and fb.get('used'):
            bits.append('clearance leg via the dollar ★ row %s (%s)'
                        % (fb['row'], fb['scaleBasis']))
    else:
        bits.append(_why_not_summary(ev))

    return dict(
        rule=rule,
        verdict=fc.get('reliability'),
        overridesNovelty=(rule == 1),
        detail=' · '.join(b for b in bits if b),
    )


def _why_not_summary(ev):
    if not ev:
        return 'precedence legs not evaluated'
    if ev.get('inlineVsBogey') is None:
        return ('inline leg deferred (%s hero, no usable dollar ★ fallback)'
                % str(ev.get('heroDenomination')).lower())
    missing = []
    if not ev.get('cyclicalSector'):
        missing.append('sector not cyclical')
    if not ev.get('peakCycleLanguage'):
        missing.append('no peak-cycle language')
    if ev.get('inlineVsBogey') is False:
        missing.append('cleared bogey beyond the nuke-crush bar')
    return '; '.join(missing) or 'all legs evaluated, no override'


def ceiling_from_card(card):
    """The PR-only currentQuarter bound, in the shape render() expects.

    DISPLAY ONLY -- render() does not compute it. It goes on the
    '1. Current Quarter:' line itself, because a ceiling shown anywhere other
    than beside the number reads as a point estimate. That is why this moved
    out of the diagnostics block.
    """
    if not card.get('currentQuarterIsCeiling'):
        return None
    acc = card.get('flagAccounting') or {}
    return dict(
        flagsAssessed=acc.get('flagsAssessed'),
        flagsPossible=acc.get('flagsTotal', 7),
        requireCall=len(acc.get('flagsRequiringCall') or []) or 3,
        notAssessed=list(acc.get('notAssessedIds') or []),
    )


def _guard_units(record):
    """Refuse to render a magnitude whose scale the renderer cannot resolve."""
    bad = undeclared_magnitude_rows(record)
    if not bad:
        return
    act = ((record.get('actuals') or {}).get('keyKPIs')) or []
    for i, name, val, ref, ratio in bad:
        if i < len(act) and isinstance(act[i], dict):
            # ★ Blank the value and flag the row rather than let it render a
            # raw magnitude that grades 🟢 CLEAR against a scaled expectation.
            act[i]['actual'] = None
            act[i]['unitAmbiguous'] = True
            act[i]['actualNote'] = (
                '\u26d4 NOT GRADED — %s holds %s against an expectation of %s '
                '(%.0fx). No actualUnit is declared, so neither the display nor '
                'the verdict can resolve the scale.' % (name[:40], val, ref,
                                                        ratio))


def render_card(card, entry, framework=None):
    """The scraper's card, verbatim from the single renderer."""
    return renderer().render(record_from_card(card, entry), framework,
                             precedence_from_card(card),
                             ceiling_from_card(card))


def precedence_for_record(model, rec):
    """Precedence for a RAW library record, not a scored card.

    Needed because rendering a stored record straight from the library skipped
    precedence entirely, so SNDK -- the one record where rule 1 fires -- printed
    "PRECEDENCE NOT EVALUATED". The gate is perfectly able to evaluate it from
    the stored actuals; nothing was asking it to.
    """
    from . import gate, score as _score
    try:
        entry = model.prepare_from_record(rec)
    except Exception:
        return None

    ak = (rec.get('actuals') or {}).get('keyKPIs') or []
    rows = []
    for i, k in enumerate(entry.get('keyKPIs') or []):
        a = ak[i] if i < len(ak) and isinstance(ak[i], dict) else {}
        rows.append(dict(name=k.get('name') or '', actual=a.get('actual'),
                         actualUnit=a.get('actualUnit'),
                         unitAmbiguous=a.get('unitAmbiguous')))

    # The stored currentQuarter clearance is not recorded, so re-derive the
    # hero clearance the same way the live path does.
    cq = _score.grade_current_quarter(
        dict(revenue=None, eps={}, guidance={}, margins={}), entry, rows,
        model)
    ctx = gate.forward_commitment_context(
        entry, 'STAY_FOR_CALL',
        (model.frameworks or {}).get('forwardCommitmentFindings'),
        clearance_pct=cq.get('clearance'), kpi_rows=rows)
    return precedence_from_card(dict(forwardCommitment=ctx))


def render_record(model, rec, framework=None):
    """A stored library record, WITH precedence evaluated.

    ★ When the record carries `actuals.alignmentFlag`, its keyKPI grid is lossy
    BY DESIGN -- the graded actuals were shorter than the pre-earnings array and
    were padded to satisfy the positional-alignment rule, which pushed values
    past their slots. The flat `actuals` fields are the authority there, so the
    record is repaired from them BEFORE rendering. The library record is never
    mutated; `repair_alignment` returns a copy.
    """
    shown, repairs, _skipped = flat.repair_alignment(
        rec, score._classify_period, score.row_qualifiers)
    _guard_units(shown)
    return renderer().render(shown, framework,
                             precedence_for_record(model, shown))


def alignment_notes(rec):
    """The flag, and every slot resolved under it. Empty when not flagged.

    render() has no field for this, so it travels in the diagnostics block
    beside the card rather than inside the locked format.
    """
    if not flat.has_flag(rec):
        return []
    _shown, repairs, skipped = flat.repair_alignment(
        rec, score._classify_period, score.row_qualifiers)
    out = ['⚙ GRID REPAIRED FROM THE FLAT ACTUALS FIELDS — this record '
           'declares its own grid lossy:',
           '   "%s"' % flat.flag_text(rec)[:200]]
    for i, name, was, now, src in repairs:
        out.append('   [%2d] %-34s %r → %s   (%s)'
                   % (i, name[:34], was, now, src))
    for i, name, was in skipped:
        out.append('   [%2d] %-34s %r — left as stored (no comparison was '
                   'recorded)' % (i, name[:34], was))
    return out


# ── Scraper-only diagnostics ──────────────────────────────────────────────────
#
# These are NOT a reformatting of anything render() emits. They are the things
# render() has no field for, and they are appended below its output rather than
# interleaved, so the rendered block stays byte-comparable to the chat path.

def diagnostics(card, record=None):
    """Lines render() does not carry. Empty list when there is nothing to add."""
    out = []

    # ★ The grid-repair notice, when the source record declares its grid lossy.
    if record is not None:
        out.extend(alignment_notes(record))

    # ★ An active event flag with no read. Checked on the STORED record when one
    # is supplied, and on the live card otherwise.
    # ★ Classified by STATUS, not by which argument was supplied. Routing on
    # "a record was passed" made every PR-only record a stored one.
    subject = record if record is not None else card
    note = flagged_without_read(subject)
    if note:
        out.append(note)

    # ★ The row says MISS and the category says 0.0. render() has no line for
    # this state, so it is stated here rather than left to be noticed.
    # ★ The ⚠ NEXT-Q TOLERANCE line moved INTO render_scorecard, which prints
    # it from nextQToleranceMiss / nextQTolerancePct. Repeating it here would put
    # the same warning on the card twice, and the renderer's wording is better:
    # it says neutral means "too close to call", NOT "met expectations". Both
    # fields are passed through record_from_card.

    # NB: the ceiling and the flag denominator are NOT here. They render inside
    # the locked block via the `ceiling=` argument, on the Current Quarter line
    # itself -- a bound shown apart from its number reads as a point estimate.

    # ★ The widened bracket carries NO base rate, and none can be borrowed.
    # Measured on all 57 records with a verified reaction: at any width >= 1.60
    # every record collapses into STAY_FOR_CALL at 47% down, mean +2.93% -- a
    # coin flip. So cohortApplies stays False and no rate is transferred
    # across widths; attaching the 0.80-width 78% rate to a 47% population is
    # the worst outcome available.
    g = card.get('gate') or {}
    if g.get('bracketWidth') and abs(g['bracketWidth'] - 0.80) > 1e-6:
        out.append('bracket width %.2f — NO base rate exists at this width '
                   '(all 57 records collapse to 47%% down, mean +2.93%%). '
                   'cohortApplies=False is correct; the rate is not '
                   'transferable across widths.' % g['bracketWidth'])

    h10 = card.get('hard10') or []
    if h10:
        syst = ' (SYSTEMATIC — HARD 8/9 blind spot)' if any(
            f.get('systematic') for f in h10) else ''
        out.append('HARD 10 — %d implausible expected value(s)%s'
                   % (len(h10), syst))
        for f in h10[:6]:
            out.append('   %-9s %-32s %-8s outside %g-%g'
                       % (f['column'], f['name'][:32], f['value'],
                          f['low'], f['high']))

    fc = card.get('forwardCommitment') or {}
    rule = fc.get('precedenceRule')
    if rule:
        # The verdict itself now renders INSIDE the locked block, via the
        # `precedence` argument, so only the supporting evidence lands here.
        out.append('precedence rule %s — %s (verdict shown in the card above)'
                   % (rule, fc.get('reliability')))
        ev = fc.get('peakCycleEvidence') or {}
        if ev.get('inlineVsBogey') is None and ev.get('inlineNote'):
            out.append('   %s' % ev['inlineNote'])
        fb = (ev.get('denominationEvidence') or {}).get('dollarHeroFallback')
        if fb and fb.get('used'):
            out.append('   clearance leg via %s (%s) = %+.2f%%'
                       % (fb['row'], fb['scaleBasis'], fb['clearancePct']))
        elif fb:
            out.append('   clearance leg deferred: %s'
                       % str(fb.get('reason'))[:110])
        if fc.get('postHocCaveat'):
            out.append('   %s' % fc['postHocCaveat'])

    flags = card.get('flagEvidence') or []
    if flags:
        out.append('offsetting flags counted: %d' % (card.get('flags') or 0))
        for f in flags:
            out.append('   · %s' % f)
    unknown = card.get('flagUnknown') or []
    if unknown:
        out.append('not assessable from a press release (could move the band):')
        for f in unknown:
            out.append('   ? %s' % f)

    if card.get('branchNote'):
        out.append(card['branchNote'])

    for p in card.get('problems') or []:
        out.append('PROBLEM: %s' % p)
    for d in card.get('deferred') or []:
        out.append('NOT GRADED: %s' % d)
    return out
