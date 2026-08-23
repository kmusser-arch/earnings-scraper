"""Read the flat `actuals` fields, for records whose grid is lossy by design.

Why this exists
===============
Non-negotiable 1 requires `actuals.keyKPIs` to be index-aligned 1:1 with
`preEarnings.keyKPIs`, because the dashboard maps them positionally. On nine
records the graded actuals were SHORTER than the pre-earnings array -- AMZN
Q1 2026 had 11 against 13 -- so the rows were padded and trimmed to satisfy the
alignment rule. Padding a shorter list into a longer one pushes values past
their slots. Those records carry `actuals.alignmentFlag` saying so explicitly,
and pointing at the Actuals tab for the real figure:

    "LEGACY ALIGNMENT REPAIRED 8/5/26 ... NOTHING WAS FABRICATED. Any row
     reading 'NOT GRADED' means no bogey-vs-actual comparison was recorded
     pre-print; check the Actuals and Call Notes tabs for the figure."

So the grid is one VIEW of the record and, on those nine, a lossy one. The flat
fields are the authority: `nextQGuidance.revenueMid` is 196.5 where the grid
slot holds the string '$22B mid'. Nothing was ever missing.

The nine: MSFT Q3/Q4, META Q1/Q2, AMZN Q1/Q2, QCOM Q2, IBM Q2, AAPL Q3 -- every
one a mega-cap.

Discipline
==========
Order of resolution, and it matters:

  1. FLAT FIELD, when the alias table resolves to exactly one candidate whose
     scale is consistent with the stored expectation.
  2. COERCE THE SLOT, when flat lookup is ambiguous or absent and the string in
     the slot is a number wearing punctuation ('$10.44' -> 10.44).
  3. LEAVE IT, otherwise. 'see call', 'qualitative' and 'unchanged' are honest
     statements that no comparison was recorded; overwriting them would invent
     one.

Step 1 refuses on ambiguity rather than choosing, because AMZN's
"International Retail Growth YoY (%)" row has TWO flat candidates --
`internationalYoY` 19 and `internationalExFX` 11 -- against a consensus of 16.5
that the record's own note describes as "street ex-FX". Taking the reported 19
turns a documented MISS into a CLEAR. The slot string '+11% ex-FX' names its own
basis, so on ambiguity the slot wins.

Step 2 refuses a DELTA. META's "FY26 Capex ($B)" slot holds '+$10B raise'
against a capex level near 200; coercing it to 10.0 would report a 95% miss on
a raise. Delta words and a scale check both guard it.
"""

import re

# ── the alias table ─────────────────────────────────────────────────────────
#
# Written from the shapes the nine records actually use, not from a convention:
# next-quarter revenue is `revenueMid` on META Q1 and AMZN Q1 and plain
# `revenue` on AMZN Q2, AAPL Q3, MSFT Q4 and META Q2.
_NEXTQ = (
    ('revenue', ('revenueMid', 'revenue')),
    ('operating income', ('opIncomeMid', 'opIncome')),
    ('op income', ('opIncomeMid', 'opIncome')),
    ('gross margin', ('grossMarginMid', 'grossMargin')),
    ('eps', ('epsMid', 'eps')),
)
_FY = (
    ('revenue', ('revenueMid', 'revenue')),
    ('capex', ('capexMid', 'capex')),
    ('opex', ('totalExpensesMid', 'totalExpenses', 'opex')),
    ('expenses', ('totalExpensesMid', 'totalExpenses')),
    ('eps', ('epsMid', 'eps')),
    ('gross margin', ('grossMarginMid', 'grossMargin')),
)

# Segment stems for CURRENT_Q rows. Key is a qualifier token from the row name;
# value is the flat-field stem the record uses.
_SEGMENT_STEMS = {
    'aws': 'aws',
    'na': 'northAmerica', 'northamerica': 'northAmerica',
    'international': 'international', 'intl': 'international',
    'advertising': 'advertising', 'ads': 'advertising',
    'subscription': 'subscription',
    'azure': 'azure',
    'iphone': 'iphone', 'services': 'services', 'mac': 'mac', 'ipad': 'ipad',
    'qct': 'qct', 'qtl': 'qtl',
    'reality': 'realityLabs', 'labs': 'realityLabs',
}

# A string that describes a CHANGE rather than a level. Never coerce one.
_DELTA_WORDS = re.compile(
    r'\b(?:raise|raised|increase\w*|decrease\w*|unchanged|reaffirm\w*|'
    r'mid|midpoint|high|low|top|bottom|end|above|below|vs|versus|'
    r'see\s+call|qualitative|not\s+graded|n/?a|tbd|pending|new|none)\b', re.I)

# ★ A POINTER TO THE CALL, not a missing value. prVsCallProvenanceRule:
#
#   "A slot reading 'PENDING - call only' or 'see Actuals / Call Notes tabs' is
#    NOT a missing value. It is a statement that the PRESS RELEASE did not
#    contain the figure and the call did."
#
# Backfilling one makes a call-derived number indistinguishable from a
# PR-derived one, and every measurement on the PR-only path -- the current-
# quarter ceiling, the extraction-gap deferral, the STAY_FOR_CALL base rate --
# is computed over PR-AVAILABLE information. Filling these would inflate the
# measured availability rate and quietly invalidate all three. AXTI is the
# sharpest case: its founding lesson is that guidance was WITHHELD from the
# release and given on the call, so filling its EPS slot erases the record's
# entire point.
_CALL_POINTER = re.compile(
    r'\bsee\s+call\b|\bcall[\s-]only\b|\bon\s+the\s+call\b|\bpending\b|'
    r'see\s+actuals|call\s+notes|\bnot\s+disclosed\b|\bwithheld\b', re.I)

_NUM_RE = re.compile(r'^[+\-]?\$?\s*([\d,]+(?:\.\d+)?)\s*%?$')

# ★ A trailing BASIS qualifier is part of the reading, not a caveat on it.
# AMZN's international slot holds '+11% ex-FX', and refusing to read it sent the
# row to a blanket refusal even though the string is the one thing in the record
# that states WHICH basis the 16.5 consensus is on.
_BASIS_SUFFIX = re.compile(
    r'^([+\-]?\$?\s*[\d,]+(?:\.\d+)?\s*%?)\s*'
    r'(?:\(?(?:ex-?FX|cc|constant\s+currency|reported|GAAP|non-?GAAP|YoY|'
    r'y/y)\)?)$', re.I)


def _num(text):
    """A number wearing punctuation, or None. '$10.44' -> 10.44, '+12%' -> 12."""
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text or '').strip()
    if not s:
        return None
    m = _NUM_RE.match(s)
    if not m:
        b = _BASIS_SUFFIX.match(s)
        if b:
            m = _NUM_RE.match(b.group(1).strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except ValueError:
        return None


def _same_scale(value, reference):
    """Is `value` within a decimal order of the expectation it will be graded on?

    The scale guard, not a plausibility judgement: 22 against a consensus of 189
    is the wrong figure, not a big miss.
    """
    if not isinstance(value, (int, float)) or not isinstance(
            reference, (int, float)) or reference == 0:
        return None                       # nothing to check against
    ratio = abs(value) / abs(reference)
    return 0.1 <= ratio <= 10.0


def _reference(kpi):
    for key in ('bogey', 'consensus'):
        v = kpi.get(key)
        if isinstance(v, (int, float)):
            return v
    return None


def _lookup(table, block, low):
    """Candidates from one alias table, longest metric phrase first."""
    for metric, fields in sorted(table, key=lambda t: -len(t[0])):
        if metric not in low:
            continue
        hits = [(f, block[f]) for f in fields
                if isinstance(block.get(f), (int, float))]
        if hits:
            return metric, hits
    return None, []


def flat_candidates(record, kpi, period, quals=None):
    """Every flat field that could supply this slot. May be more than one."""
    ac = record.get('actuals') or {}
    name = kpi.get('name') or ''
    low = name.lower()

    if period == 'NEXTQ_GUIDE':
        block = ac.get('nextQGuidance') or {}
        metric, hits = _lookup(_NEXTQ, block, low)
        return [('nextQGuidance.%s' % f, v) for f, v in hits]

    if period == 'FY_GUIDE':
        block = ac.get('fyGuidance') or {}
        metric, hits = _lookup(_FY, block, low)
        return [('fyGuidance.%s' % f, v) for f, v in hits]

    # ★ CURRENT_Q only. If the row NAMES a different period, the flat
    # current-quarter fields are the wrong period by definition -- this is the
    # guard that stopped "FY26 EPS ($)" and "FY27 EPS ($)" both being filled
    # from actuals.eps 2.78, a reported quarterly GAAP figure that itself
    # carries a $16.8B one-off gain.
    if period != 'CURRENT_Q':
        return []

    # CURRENT_Q -- segment and headline rows live flat on `actuals`.
    out = []
    stems = {_SEGMENT_STEMS[t] for t in (quals or set())
             if t in _SEGMENT_STEMS}
    wants_growth = bool(re.search(r'growth|yoy', low))
    for stem in sorted(stems):
        for suffix in (('YoY', 'ExFX', 'Growth') if wants_growth
                       else ('Rev', 'Revenue', 'OpIncome', 'Margin')):
            key = stem + suffix
            v = _num(ac.get(key))
            if v is not None:
                out.append(('actuals.%s' % key, v))
    if out:
        return out

    if not quals:
        if re.search(r'\brevenue\b|\bnet sales\b', low) and isinstance(
                ac.get('revenue'), (int, float)):
            out.append(('actuals.revenue', ac['revenue']))
        elif re.search(r'\beps\b|earnings per share', low) and isinstance(
                ac.get('eps'), (int, float)):
            out.append(('actuals.eps', ac['eps']))
    return out


def is_gradeable(kpi):
    """Does this row carry a numeric expectation at all?

    ★ A qualitative row has nothing to grade, so it has nothing to repair.
    AMZN's "AWS forward commentary (qualitative)" slot holds '$14.16B' -- AWS
    operating income, correct and informative -- and an earlier pass blanked it
    while trying to help. A repair that removes a true reading is worse than the
    misalignment it was fixing.
    """
    return any(isinstance(kpi.get(k), (int, float))
               for k in ('consensus', 'bogey'))


def resolve_slot(record, kpi, slot_value, period, quals=None,
                 allow_backfill=False):
    """One slot, resolved -- and it declares WHICH of two operations it did.

    ★ prVsCallProvenanceRule, generalised: "Coercion is safe: same figure, same
    basis, different formatting. Backfill is not: a different SOURCE. Ask which
    of the two you are doing before repairing any row, on flagged records and
    unflagged alike."

    So the order is COERCION FIRST, and backfill is opt-in per call site rather
    than a default. Every result carries `provenance` and `prAvailable`, so a
    backfilled row can never be counted as PR-available information.

    Returns dict(value, source, provenance, prAvailable, note) or None. None
    means LEAVE THE SLOT ALONE.
    """
    if not is_gradeable(kpi):
        return None                        # qualitative row -- nothing to grade

    ref = _reference(kpi)
    raw = str(slot_value or '')

    # ── 0. a pointer to the call is a FINDING, never a gap ─────────────────
    if _CALL_POINTER.search(raw):
        return dict(value=None, source='call-only', provenance='call',
                    prAvailable=False,
                    note='⛔ NOT A GAP — %r states that the press release did '
                         'not carry this figure and the call did. Filling it '
                         'would make a call figure indistinguishable from a PR '
                         'one (prVsCallProvenanceRule).' % slot_value)

    # ── 1. COERCION: same figure, same basis, same source ──────────────────
    if not _DELTA_WORDS.search(raw):
        coerced = _num(slot_value)
        if coerced is not None:
            if _same_scale(coerced, ref) is False:
                return dict(value=None, source='scale-refused',
                            provenance='pr', prAvailable=True,
                            note='⛔ NOT GRADED — slot holds %r, off the scale '
                                 'of the stored expectation %s'
                                 % (slot_value, ref))
            return dict(value=coerced, source='grid-slot (coerced)',
                        provenance='pr', prAvailable=True,
                        note='the slot already held this figure as text (%r) — '
                             'same figure, same basis, same source'
                             % slot_value)

    # ── 2. BACKFILL: a DIFFERENT SOURCE, so it is opt-in and it is marked ──
    if not allow_backfill:
        return None

    cands = flat_candidates(record, kpi, period, quals)
    scaled = [(pth, v) for pth, v in cands if _same_scale(v, ref) is not False]
    distinct = {round(v, 6) for _p, v in scaled}
    if not scaled:
        return None
    if len(distinct) > 1:
        # ★ Two flat fields disagree on BASIS -- AMZN's international row has
        # internationalYoY 19 and internationalExFX 11 against a consensus the
        # record's own note calls "street ex-FX". Refuse; do not choose.
        return dict(value=None, source='ambiguous-refused', provenance='flat',
                    prAvailable=False,
                    note='⛔ NOT GRADED — flat fields disagree (%s) and the slot '
                         '%r does not resolve the basis'
                         % (', '.join('%s=%s' % (pth.split('.')[-1], v)
                                      for pth, v in scaled), slot_value))
    path, val = scaled[0]
    return dict(value=val, source='library-flat:%s' % path, provenance='flat',
                prAvailable=False,
                note='BACKFILLED from %s because the grid slot held %r, which '
                     'is a padding artifact rather than a reading. This is a '
                     'different SOURCE from the grid, so the row is marked '
                     'prAvailable=False and must never be counted as '
                     'PR-available information.' % (path, slot_value))


def has_flag(record):
    """The record's own declaration that its grid is lossy."""
    return bool(((record or {}).get('actuals') or {}).get('alignmentFlag'))


def flag_text(record):
    return (((record or {}).get('actuals') or {}).get('alignmentFlag') or '')


def repair_alignment(record, classify_period, qualifiers):
    """A COPY of `record` with resolvable slots filled from the flat fields.

    The library record is never mutated -- Model holds it, and a repair is a
    view built for display and grading, not a correction to the data.

    Returns (copy, repairs, skipped).
    """
    if not has_flag(record):
        return record, [], []

    import copy as _copy
    out = _copy.deepcopy(record)
    pre = ((out.get('preEarnings') or {}).get('keyKPIs')) or []
    ac = out.get('actuals') or {}
    rows = ac.get('keyKPIs') or []
    repairs, skipped = [], []

    call_only, withheld = [], []

    def name_of(k):
        return (k or {}).get('name') or ''

    for i, kpi in enumerate(pre):
        if i >= len(rows) or not isinstance(rows[i], dict):
            continue
        cur = rows[i].get('actual')
        if isinstance(cur, (int, float)):
            continue                       # already gradeable

        # ★ A row the LIBRARIAN blanked is not a gap to fill. Four rows carry
        # rotationSuspect + unverified because their stored value belonged to a
        # different slot, and the decision was to BLANK rather than guess:
        # MSFT-2026Q3 FY27 Capex Expect, META-2026Q1 FY27 EPS, STX-2026Q4 Adj
        # Op Margin, ANET-2026Q1 Q2 GM Guide. Non-negotiable 9 settles it --
        # unverified rows are EXCLUDED, not recovered.
        #
        # A fifth, AMZN-2026Q2 [2] "Q3 Revenue Guide ($B) ★", was NOT a rotation
        # at all: a single displaced note dragged 220.0 into the slot, and the
        # true midpoint of its $197-202B guide is 199.5 -- which is what
        # nextQGuidance.revenue holds. It is now repaired in the library, so this
        # guard no longer applies to it, and filling it would have been a
        # COERCION under prVsCallProvenanceRule (same metric, same source) rather
        # than the cross-source backfill I took it for.
        if rows[i].get('unverified') or rows[i].get('rotationSuspect'):
            withheld.append((i, name_of(kpi), cur))
            continue
        name = kpi.get('name') or ''
        period = classify_period(name, out.get('quarter'))
        # ★ Backfill is authorised HERE and only here: this record declares
        # its grid lossy, so a slot holding a padding artifact has a known
        # mechanical cause. It is still a different source, and still marked.
        res = resolve_slot(out, kpi, cur, period, qualifiers(name),
                           allow_backfill=True)
        if res is None:
            skipped.append((i, name, cur))
            continue
        if res['provenance'] == 'call':
            # ★ KEEP THE TEXT. 'see call' is the finding, and it renders as the
            # finding; replacing it with None would delete the one statement in
            # the record about what the release actually carried.
            rows[i]['actualProvenance'] = 'call'
            rows[i]['prAvailable'] = False
            rows[i]['actualNote'] = res['note']
            call_only.append((i, name, cur))
            continue
        rows[i]['actual'] = res['value']
        rows[i]['actualSource'] = res['source']
        rows[i]['actualNote'] = res['note']
        rows[i]['actualProvenance'] = res['provenance']
        rows[i]['prAvailable'] = res['prAvailable']
        repairs.append((i, name, cur, res['value'], res['source']))

    return out, repairs, skipped + call_only + withheld


def pr_available_rows(record):
    """Rows whose value is PR-derived. Backfilled and call-only rows excluded.

    Any measurement of what a press release carried must count THIS, not the
    repaired grid -- otherwise the repair inflates the very rate the PR-only
    ceiling, the deferral rule and the 78% base rate are calibrated on.
    """
    rows = ((record or {}).get('actuals') or {}).get('keyKPIs') or []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get('prAvailable') is False:
            continue
        out.append(r)
    return out


def call_only_rows(record, classify_period, qualifiers):
    """Slots that state the figure was on the CALL, not in the release.

    These are FINDINGS -- the PR withheld it -- and they are what the PR-only
    availability rate is measuring. Never repair them.
    """
    pre = ((record or {}).get('preEarnings') or {}).get('keyKPIs') or []
    rows = ((record or {}).get('actuals') or {}).get('keyKPIs') or []
    out = []
    for i, kpi in enumerate(pre):
        if i >= len(rows) or not isinstance(rows[i], dict):
            continue
        v = rows[i].get('actual')
        if isinstance(v, str) and _CALL_POINTER.search(v) and is_gradeable(kpi):
            out.append((i, kpi.get('name'), v))
    return out
