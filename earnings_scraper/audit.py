"""Audit rules, each declaring WHICH PATH its subject came from.

Why the tagging exists
======================
Three consecutive false alarms, all the same mistake:

  1. 13 rows flagged for a missing `actualUnit`. False. A LIVE row gets its
     value from the parser, which normalises every dollar magnitude to $M, so a
     "($B)" row holding a $M value must declare the unit or it renders as a bare
     number. A STORED row follows the opposite convention -- the value is
     already in the unit the name declares -- so there is nothing to declare.
  2. AMZN-2026Q1 reported as data corruption. False. Its grid is lossy BY
     DESIGN and the record says so in `actuals.alignmentFlag`; the figures were
     all present in the flat fields.
  3. AXTI-2026Q2 reported as a weighting defect. False. The weighted value is
     1.9249999..., which rounds down to the stored 1.92, and the comparison
     tolerance was tighter than the rounding it was comparing across.

Every one was a rule built for the live path applied to stored data, or a rule
that read one view of a record as if it were the only one. The pattern was found
three times by hand. So it is a PRECONDITION here, not a habit: a rule declares
its path, the runner refuses to apply it to the other, and a rule that reads a
positional grid must declare whether it tolerates a flagged record.
"""

from . import flat
from . import score
from . import units
from .scorecard import row_cons as _row_cons, row_name as _row_name

LIVE = 'live'          # a card built from a press release, this minute
STORED = 'stored'      # a record already in the library
BOTH = 'both'

# ★ The weighting tolerance. 0.0051 rather than 0.005: the stored `overall` is
# rounded to 2dp, so the weighted sum can legitimately sit half a cent away
# (AXTI-2026Q2 computes 1.9249999... and stores 1.92). A tolerance tighter than
# the rounding it compares across reports arithmetic that is not wrong.
OVERALL_TOLERANCE = 0.0051

WEIGHTS = dict(currentQuarter=0.20, nextQGuidance=0.30,
               fyGuidance=0.30, narrative=0.20)


def is_declared_exclusion(rec):
    """A record the library has DECLARED unscoreable, not one that is broken.

    ★ IBM-2026Q2 carries `preEarningsAbsent`: a legacy record scored before the
    pre-earnings build existed, for which a card CANNOT be added -- writing a
    bogey after the fact would fabricate the expectation column, which
    non-negotiable 9 forbids and which would corrupt beatMagnitude. Its own
    declaration says "Declared exclusion, not an open item. Do not let an audit
    re-raise it as HARD."

    So the scraper refuses it under the no-card rule and the audit stays quiet.
    An audit that keeps re-reporting a resolved decision teaches you to skim it.
    """
    return bool((rec or {}).get('preEarningsAbsent'))


def exclusion_reason(rec):
    ex = (rec or {}).get('preEarningsAbsent') or {}
    return ex.get('consequence') or ex.get('reason') or ''


class PathMismatch(Exception):
    """A rule was applied to a subject from the path it does not describe."""


class Finding(object):
    def __init__(self, rule, severity, detail):
        self.rule, self.severity, self.detail = rule, severity, detail

    def __repr__(self):
        return '%-22s %-9s %s' % (self.rule, self.severity, self.detail)


class Rule(object):
    """One check, and the path whose data it is entitled to judge.

    `grid_positional` marks a rule that reads `actuals.keyKPIs` by index. Such a
    rule is SKIPPED on a record carrying `alignmentFlag` unless it opts in with
    `flag_safe=True`, because on those records the grid is not the authority.
    """

    def __init__(self, name, path, fn, why, grid_positional=False,
                 flag_safe=False):
        self.name = name
        self.path = path
        self.fn = fn
        self.why = why
        self.grid_positional = grid_positional
        self.flag_safe = flag_safe

    def applies_to(self, kind):
        return self.path in (kind, BOTH)


# ── stored-path rules ───────────────────────────────────────────────────────

def _overall_weighting(rec):
    sc = rec.get('scores') or {}
    parts = {k: sc.get(k) for k in WEIGHTS}
    if not all(isinstance(v, (int, float)) for v in parts.values()):
        return []
    if not isinstance(sc.get('overall'), (int, float)):
        return []
    calc = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
    if abs(calc - sc['overall']) <= OVERALL_TOLERANCE:
        return []
    return [Finding('overall-weighting', 'HARD',
                    'stored %.4f vs weighted %.4f (tolerance %.4f)'
                    % (sc['overall'], calc, OVERALL_TOLERANCE))]


def _is_pending(rec):
    """A card built but not yet reported: PRE-EARNINGS with no actuals.

    ★ Its actuals array is legitimately EMPTY -- the print has not happened. Any
    rule that compares grid lengths must exempt it, or every pre-earnings build
    raises a HARD alignment failure on the very cards it just created.
    """
    if str(rec.get('status') or '').upper() != 'PRE-EARNINGS':
        return False
    return not ((rec.get('actuals') or {}).get('keyKPIs') or [])


def _alignment_length(rec):
    if _is_pending(rec):
        return []          # not yet reported -- empty actuals is right
    pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
    act = ((rec.get('actuals') or {}).get('keyKPIs')) or []
    if not pre and not act:
        return []
    if len(pre) != len(act):
        return [Finding('alignment-length', 'HARD',
                        '%d pre / %d actual -- the dashboard maps positionally'
                        % (len(pre), len(act)))]
    return []


def _positioning_separation(rec):
    pa = rec.get('positioningAxis') or {}
    sc = rec.get('scores') or {}
    adj, sign, ov = (pa.get('adjustedScore'), pa.get('signModifier'),
                     sc.get('overall'))
    if not all(isinstance(x, (int, float)) for x in (adj, sign, ov)):
        return []
    if abs((ov + sign) - adj) > 1e-6:
        return [Finding('positioning-separation', 'HARD',
                        'adjusted %.2f != overall %.2f + modifier %.2f'
                        % (adj, ov, sign))]
    return []


def _sector_stable(rec, all_records=()):
    tk = rec.get('ticker')
    seen = {x.get('sector') for x in all_records if x.get('ticker') == tk}
    if len(seen) > 1:
        return [Finding('sector-stability', 'HARD',
                        '%s has %d sectors: %s'
                        % (tk, len(seen), sorted(str(s)[:30] for s in seen)))]
    return []


def _structure(rec):
    out = []
    if 'preEarnings' not in rec and not is_declared_exclusion(rec):
        out.append(Finding('record-structure', 'HARD',
                           'no preEarnings key -- nothing to grade against'))
    pct = (rec.get('stockReaction') or {}).get('pctChangeNextDay',
                                               rec.get('pctChangeNextDay'))
    if pct is not None and not isinstance(pct, (int, float)):
        out.append(Finding('next-day-close', 'HARD',
                           'pctChangeNextDay is %r, not numeric' % (pct,)))
    return out


def _prose_in_numeric_slot(rec):
    """A gradeable row holding prose -- the loss the validator does not check.

    Reads the grid positionally, so it is SKIPPED on a flagged record: there the
    loss is declared, expected, and repaired from the flat fields instead.
    """
    pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
    act = ((rec.get('actuals') or {}).get('keyKPIs')) or []
    out = []
    for i, k in enumerate(pre):
        a = act[i] if i < len(act) and isinstance(act[i], dict) else {}
        v = a.get('actual')
        if not isinstance(v, str):
            continue
        if not any(isinstance(k.get(x), (int, float))
                   for x in ('consensus', 'bogey')):
            continue
        # ★ A pointer to the call is a FINDING about what the release carried,
        # not a gap in the record. prVsCallProvenanceRule: filling it would make
        # a call figure indistinguishable from a PR one and inflate the measured
        # PR-availability rate that the ceiling, the deferral rule and the 78%
        # base rate are all calibrated on. Reported separately so it can never
        # be mistaken for a to-do.
        if flat._CALL_POINTER.search(v):
            out.append(Finding('pr-withheld', 'FINDING',
                               '[%d] %s — the release did not carry it (%r)'
                               % (i, (_row_name(k) or '')[:34], v)))
            continue
        out.append(Finding('prose-in-numeric-slot', 'SOFT',
                           '[%d] %s holds %r against a numeric expectation'
                           % (i, (_row_name(k) or '')[:34], v)))
    return out


def _flagged_without_read(rec):
    """The subset of unread-categories that carries an ACTIVE event flag.

    Reported apart from `unread-categories` because the two are not the same
    problem: an unread category is a content gap, while an unread FLAGGED print
    is the deliverable missing on the one print type the framework says to stay
    for. Severity FINDING, not SOFT -- and not HARD, because nothing is corrupt
    or unrenderable; the read was never written.
    """
    from . import scorecard
    note = scorecard.flagged_without_read(rec)
    if not note:
        return []
    kind = scorecard.read_state_kind(rec)
    if kind != 'stored':
        # ★ A PR-only print has not had its call yet. Reporting it as a defect
        # would put the build-regression count at 14 when it is 12.
        return [Finding('flagged-read-pending', 'INFO',
                        'active event flag, reads pending the call (%s)'
                        % (rec.get('status') or '?'))]
    return [Finding('flagged-without-read', 'FINDING',
                    'active asymmetric event flag, zero category reads')]


def _rotation_declared(rec):
    """Report rows the LIBRARY has already marked rotationSuspect. SOFT only.

    ★ SOFT, AND IT MUST STAY SOFT. The obvious detector -- "does this row's note
    describe a different metric than the row name?" -- was tried as a HARD gate
    and returned 5 of 5 FALSE POSITIVES, because note-figure-matches-actual
    holds for CORRECT rows too: a good note quotes the number in its own row.
    So there is no test here that infers a rotation. This rule only surfaces the
    ones a human already found and blanked, so they stay visible without being
    re-litigated.

    Four rows carry it: MSFT-2026Q3 FY27 Capex Expect (held an RPO figure),
    META-2026Q1 FY27 EPS (an op margin), STX-2026Q4 Adj Op Margin (a revenue
    figure), ANET-2026Q1 Q2 GM Guide (op margin graded against gross-margin
    expectations).

    A fifth was withdrawn on inspection, which is the reason this rule reports
    rather than decides: AMZN-2026Q2 Q3 Revenue Guide ★ held 220.0 because a
    single note was displaced, not because the block rotated, and its true
    midpoint 199.5 grades 🔴 MISS against a 204 street. It is repaired and
    graded. A HARD gate would have kept it blank.
    """
    act = ((rec.get('actuals') or {}).get('keyKPIs')) or []
    pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
    out = []
    for i, row in enumerate(act):
        if not isinstance(row, dict) or not row.get('rotationSuspect'):
            continue
        name = ((pre[i] or {}).get('name') if i < len(pre) else '') or '?'
        graded = isinstance(row.get('actual'), (int, float))
        out.append(Finding(
            'rotation-declared', 'FINDING',
            '[%d] %s — declared rotationSuspect and %s'
            % (i, name[:40],
               'BLANKED (correct)' if not graded
               else 'STILL HOLDS A VALUE (%s) — a declared rotation must not '
                    'grade' % row.get('actual'))))
    return out


def bullish_drift_watch(model):
    """Count, don't correct: every place a SOFT outcome reads neutral-or-better.

    ★ threeDefinitionsOfInline names the concern -- "three independent places
    where the model reads a soft outcome as neutral-or-better ... if that
    pattern holds as n grows, the correction is systematic, not per-band." The
    three are not reconciled in code (n=3 on the tolerance cohort, and APP and
    NET argue opposite ways), so this counts them instead, per place, so the
    pattern is measurable rather than remembered.

    Reconciling them now would be refitting on three rows -- the same trap as
    the fade-zone band at n=10.
    """
    from . import score as _score

    out = {}

    # 1. the ±0.5% next-Q tolerance band: a guide BELOW street scores 0.0
    tol = []
    for rec in model.records:
        try:
            entry = model.prepare_from_record(rec)
        except Exception:
            continue
        pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
        act = ((rec.get('actuals') or {}).get('keyKPIs')) or []
        for i, kpi in enumerate(pre):
            # ★ metric/cons variant: 31 rows across AEHR-2026Q4, NFLX-2026Q2
            # and TSLA-2026Q2 store the name under `metric` and the street
            # under `cons`. A direct k['name'] read skipped every one of them
            # SILENTLY -- the drift watch was blind to 3 records.
            name = _row_name(kpi) or ''
            if _score._classify_period(name, rec.get('quarter')) \
                    != 'NEXTQ_GUIDE':
                continue
            if 'revenue' not in name.lower() or _score.row_qualifiers(name):
                continue
            row = act[i] if i < len(act) and isinstance(act[i], dict) else {}
            val, cons = row.get('actual'), _row_cons(kpi)
            if not isinstance(val, (int, float)) \
                    or not isinstance(cons, (int, float)):
                continue
            exp, got = _score._normalise_pair(cons, val, name,
                                              row.get('actualUnit'))
            if not exp:
                continue
            pct = (got - exp) / abs(exp) * 100.0
            if -0.5 <= pct < 0.0:
                tol.append((rec.get('id'), name[:30], round(pct, 2)))
    out['nextQToleranceBand'] = tol

    # 2. the PR-only current-quarter ceiling: 3 of 7 flags need the call, so a
    #    PR flag count is a FLOOR and the score is an upper bound
    ceil = [r.get('id') for r in model.records
            if str(r.get('status', '')).upper().endswith('PR-ONLY')]
    out['prOnlyCeiling'] = ceil

    # 3. the fade-zone band: beats street, misses bogey -> +1.0, on a cohort
    #    that resolves DOWN 7 of 9
    fade = []
    for rec in model.records:
        if (rec.get('scores') or {}).get('nextQGuidance') is None:
            continue
        pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
        act = ((rec.get('actuals') or {}).get('keyKPIs')) or []
        for i, kpi in enumerate(pre):
            name = _row_name(kpi) or ''
            if '\u2605' not in name:
                continue
            if _score._classify_period(name, rec.get('quarter')) \
                    != 'NEXTQ_GUIDE':
                continue
            if _score.is_reverse_polarity(name):
                continue
            row = act[i] if i < len(act) and isinstance(act[i], dict) else {}
            val = row.get('actual')
            cons, bog = _row_cons(kpi), kpi.get('bogey')
            if not all(isinstance(x, (int, float)) for x in (val, cons, bog)):
                continue
            ec, ac_ = _score._normalise_pair(cons, val, name,
                                             row.get('actualUnit'))
            eb, ab = _score._normalise_pair(bog, val, name,
                                            row.get('actualUnit'))
            if not ec or not eb:
                continue
            if ac_ > ec and ab < eb:
                fade.append((rec.get('id'), name[:30]))
            break
    out['fadeZoneBand'] = fade

    out['total'] = len(tol) + len(ceil) + len(fade)
    return out


def _bogey_coverage(rec):
    """No numeric bogey anywhere, or on fewer than half the rows. SOFT.

    ★ This is a DATA gap with a logic consequence, which is why it is worth a
    write-time rule rather than a card-time surprise. With no bogey on any row
    every beat renders "🟢 BEAT ST", and a column of green reads as a blowout:
    KLAC-2026Q4 showed six green rows on a print that fell 6.70% while its own
    narrative called it a "Textbook Peak-Cycle Buyside-Inline Fade".

    And the absence is not cosmetic. The FADE ZONE -- beats street, misses
    bogey -- resolved DOWN 7 of 9 and is the single most consequential cell in
    the model. An empty bogey column makes that cell UNDETECTABLE, so the gap
    removes the read that pays. 13 of 76 records have no numeric bogey at all;
    a new record built without one should be flagged when it is written, not
    found on a card months later.
    """
    pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
    if not pre:
        return []
    from . import scorecard
    n = sum(1 for k in pre
            if isinstance(scorecard.coerce_bogey((k or {}).get('bogey')),
                          (int, float)))
    if n == 0:
        return [Finding('bogey-coverage', 'SOFT',
                        'NO numeric bogey on any of %d rows — every beat reads '
                        '"BEAT ST" and the fade zone cannot be detected'
                        % len(pre))]
    if n < len(pre) / 2.0:
        return [Finding('bogey-coverage', 'SOFT',
                        'bogey on only %d of %d rows — the rest cannot show a '
                        'fade' % (n, len(pre)))]
    return []


def _unread_categories(rec):
    """A category that SCORED but carries no one-sentence read. SOFT.

    ★ AVGO-2026Q2 renders 15 rows and four category scores with ZERO reads, so
    the card shows a full grid under four bare numbers. CLAUDE.md is explicit
    that a read which cannot compress to one sentence per category means the
    score is wrong or the data is incomplete -- a scored category with no
    sentence is that condition, unannounced.
    """
    if _is_pending(rec):
        return []          # reads come from the call; it has not happened
    sm = rec.get('summaries') or {}
    sc = rec.get('scores') or {}
    cats = ('currentQuarter', 'nextQGuidance', 'fyGuidance', 'narrative')
    scored = [c for c in cats if isinstance(sc.get(c), (int, float))]
    unread = [c for c in scored if not str(sm.get(c) or '').strip()]
    if not scored or not unread:
        return []
    pre = ((rec.get('preEarnings') or {}).get('keyKPIs')) or []
    act = ((rec.get('actuals') or {}).get('keyKPIs')) or []
    graded = sum(1 for i, _k in enumerate(pre)
                 if i < len(act) and isinstance(act[i], dict)
                 and isinstance(act[i].get('actual'), (int, float)))
    if len(unread) == len(scored):
        return [Finding('unread-categories', 'SOFT',
                        '%d graded row(s) and %d scored categories with NO '
                        'one-sentence read at all'
                        % (graded, len(scored)))]
    return [Finding('unread-categories', 'SOFT',
                    '%d of %d scored categories have no read: %s'
                    % (len(unread), len(scored), ', '.join(unread)))]


# ── live-path rules ─────────────────────────────────────────────────────────

def _live_units(card):
    rows = card.get('keyKPIs') or []
    return [Finding('unit-declared', 'HARD',
                    '[%d] %s declares %r with no actualUnit'
                    % (i, (rows[i].get('name') or '')[:34], tok))
            for i, tok in score.unit_undeclared(rows).items()]


def _live_duplicates(card):
    rows = card.get('keyKPIs') or []
    return [Finding('duplicate-actual', 'HARD',
                    '[%d] %s shares %r with %d rows'
                    % (i, (rows[i].get('name') or '')[:34], val, n))
            for i, (val, n) in score.duplicate_actuals(rows).items()]


def _priority_one_hero(rec):
    """A profile with no priority-1 hero makes non-negotiable 3 UNREACHABLE.

    "A priority-1 hero KPI miss caps Current Quarter at 0.0" cannot fire if no
    hero declares priority 1. It was absent from three profiles -- HOOD, LITE
    and DUOL -- so the cap silently could not apply to them.

    ★ SOFT, deliberately. HOOD-2026Q1 and LITE-2026Q3 are stored records that
    were NOT re-scored when the profiles were fixed, so a hard failure here
    would demand re-scoring history to satisfy an audit. The check is worth
    having; it is not worth a forced re-score.
    """
    prof = (rec.get('_profile') or {})
    heroes = prof.get('heroKPIs') or rec.get('heroKPIs') or []
    if not heroes:
        return []
    if any(h.get('priority') == 1 for h in heroes if isinstance(h, dict)):
        return []
    return [Finding('priority-one-hero', 'SOFT',
                    'no hero declares priority 1, so non-negotiable 3 (a '
                    'priority-1 miss caps Current Quarter at 0.0) can never '
                    'fire for this ticker')]


RULES = [
    Rule('overall-weighting', STORED, _overall_weighting,
         'scores.overall must equal the 0.2/0.3/0.3/0.2 weighting'),
    Rule('alignment-length', STORED, _alignment_length,
         'non-negotiable 1', grid_positional=True, flag_safe=True),
    Rule('positioning-separation', STORED, _positioning_separation,
         'non-negotiable 4'),
    Rule('sector-stability', STORED, _sector_stable,
         'non-negotiable 10'),
    Rule('record-structure', STORED, _structure,
         'a record must carry preEarnings; pctChangeNextDay must be numeric'),
    Rule('prose-in-numeric-slot', STORED, _prose_in_numeric_slot,
         'a gradeable row holding prose grades nothing',
         grid_positional=True),
    Rule('bogey-coverage', STORED, _bogey_coverage,
         'no numeric bogey disables the fade zone, the read that pays'),
    Rule('flagged-without-read', STORED, _flagged_without_read,
         'an active event flag with no read: the deliverable is missing on the '
         'print type the framework says to stay for'),
    Rule('unread-categories', STORED, _unread_categories,
         'a scored category with no one-sentence read'),
    Rule('priority-one-hero', STORED, _priority_one_hero,
         'a profile with no priority-1 hero makes non-negotiable 3 '
         'unreachable'),
    Rule('rotation-declared', STORED, _rotation_declared,
         'surface rows a human blanked as rotated; NEVER infer a rotation'),
    Rule('unit-declared', LIVE, _live_units,
         'a parsed magnitude is $M and must say so'),
    Rule('duplicate-actual', LIVE, _live_duplicates,
         'one value in two rows is a matcher, not a reading'),
]


def assert_applicable(rule, kind, subject=None):
    """The precondition. Raises rather than producing a finding.

    A rule applied to the wrong path does not yield a wrong answer, it yields a
    CONFIDENT wrong answer, which is how the same mistake was made three times.
    """
    if not rule.applies_to(kind):
        raise PathMismatch(
            '%r describes the %s path and cannot judge a %s subject (%s)'
            % (rule.name, rule.path, kind, rule.why))
    if (kind == STORED and rule.grid_positional and not rule.flag_safe
            and subject is not None and flat.has_flag(subject)):
        raise PathMismatch(
            '%r reads the keyKPI grid positionally, and this record carries '
            'alignmentFlag -- its grid is lossy by design, so the flat actuals '
            'fields are the authority' % rule.name)
    return True


def audit(subject, kind, all_records=()):
    """Run every rule entitled to judge `subject`. Returns (findings, skipped)."""
    findings, skipped = [], []
    for rule in RULES:
        try:
            assert_applicable(rule, kind, subject)
        except PathMismatch as exc:
            skipped.append((rule.name, str(exc)))
            continue
        if rule.name == 'sector-stability':
            findings.extend(rule.fn(subject, all_records))
        else:
            findings.extend(rule.fn(subject))
    return findings, skipped


def audit_library(model):
    """Every record, with the preconditions enforced.

    Declared exclusions are reported once as INFO and never as HARD.
    """
    findings, skipped = [], []
    for rec in model.records:
        if is_declared_exclusion(rec):
            findings.append((rec.get('id'), Finding(
                'declared-exclusion', 'INFO',
                'preEarningsAbsent — refused under the no-card rule, not a '
                'defect to fix')))
            continue
        f, s = audit(rec, STORED, model.records)
        findings.extend((rec.get('id'), x) for x in f)
        skipped.extend((rec.get('id'), n, why) for n, why in s)
    return findings, skipped
