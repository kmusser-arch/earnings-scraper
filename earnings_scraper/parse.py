"""Extract reported figures from a press-release body.

Everything is normalised to the library's units: revenue in $M (matching
`preEarnings.revUnit`), EPS in dollars, margins in percent.

Two rules inherited from the model's error classes:

- Error class 5 (units mismatches): every magnitude carries the unit it was
  parsed from, so a $M/$B mix cannot silently produce a +103,882% delta.
- Error class 7 (GAAP/non-GAAP headline traps): GAAP and non-GAAP EPS are
  parsed into separate fields, never merged. A record that cannot establish
  which basis a figure uses returns it with basis='unknown' so the caller
  can refuse to grade it.
"""

import re

# --- number helpers -----------------------------------------------------------

_SCALE = {
    'billion': 1000.0, 'b': 1000.0,
    'million': 1.0, 'm': 1.0,
    'thousand': 0.001, 'k': 0.001,
}

_NUM = r'\(?\$?\s?(-?[\d,]+(?:\.\d+)?)\s*\)?'
_UNIT = r'(billion|million|thousand|[BMK])\b'


def _to_float(raw, negative_parens=False, was_paren=False):
    try:
        v = float(str(raw).replace(',', '').replace('$', '').strip())
    except (TypeError, ValueError):
        return None
    if negative_parens and was_paren:
        v = -abs(v)
    return v


def _to_millions(raw, unit, was_paren=False):
    """Normalise a magnitude to $M."""
    v = _to_float(raw, negative_parens=True, was_paren=was_paren)
    if v is None:
        return None
    mult = _SCALE.get((unit or 'million').lower(), 1.0)
    return round(v * mult, 3)


# --- revenue ------------------------------------------------------------------

_REV_LABEL = (r'(?:total\s+)?(?:net\s+)?(?:revenues?|net\s+sales|total\s+sales|'
              r'sales|net\s+revenues?)')

_REVENUE_PATTERNS = [
    # revenue of $17.25 billion / total revenues of $88.0 million
    re.compile(_REV_LABEL + r'\s+(?:of|was|were|totall?ed|reached|came\s+in\s+at)\s+'
               r'\$?\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I),
    # revenue increased 18% to $17.3 billion
    # NB: the gap class must allow '.' and '$' -- "decreased 4.2% to $88.0
    # million" contains both, and excluding them silently kills the match.
    re.compile(_REV_LABEL + r'[^\n]{0,80}?\bto\s+\$\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I),
    # $17.25 billion in revenue
    re.compile(r'\$\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT + r'\s+(?:in|of)\s+' + _REV_LABEL, re.I),
]

_REV_GROWTH = re.compile(
    _REV_LABEL + r'[^\n]{0,60}?\b(increas\w+|decreas\w+|grew|declin\w+|rose|fell|up|down)\s+'
    r'(?:by\s+)?(\d+(?:\.\d+)?)\s*(?:%|percent)', re.I)


# ★ A SEGMENT sentence is not the company total. "Data Center segment revenue
# was $5.8 billion" satisfies the bare `revenue` label, so the total-revenue
# matcher read a segment figure as the headline -- the AMD defect running in the
# opposite direction. It surfaced only because the duplicate guard then saw the
# same 5,800 in the headline row and the Data Center row and blanked both; on a
# release that states segments but not a total it would have written a segment
# figure into "Q1 Revenue ($B)" silently.
_SEG_MODIFIER = re.compile(
    r'(?:\bsegment|\bdivision|\bbusiness\s+unit|\bproduct\s+line|\bgroup)'
    r'(?:\s+\w+)?\s*$', re.I)


def _is_segment_context(text, start):
    """True when the revenue label at `start` is qualified by a segment word."""
    left = text[max(0, start - 60):start]
    # Only the CURRENT sentence can qualify the label.
    left = re.split(r'(?<=[.!?])\s+', left)[-1]
    return bool(_SEG_MODIFIER.search(left))


def parse_revenue(text):
    """Returns {value_musd, unit_seen, growth_pct, raw} or None."""
    for pat in _REVENUE_PATTERNS:
        m = None
        for cand in pat.finditer(text):
            # ★ THE SAME discriminator operating income and EBITDA use. The
            # keyword version (_is_segment_context) only looks for the literal
            # words "segment"/"division", so "Subscription revenue was $10.593
            # billion" passed as the company total on CRM-2027Q1 -- and since
            # the Subscription row then held the same figure, the duplicate
            # guard refused BOTH rows. Two of Salesforce's ★★ heroes blanked
            # because one matcher was weaker than its siblings.
            if not _is_company_context(text, cand.start()):
                continue          # a segment or subject-qualified figure
            m = cand
            break
        if not m:
            continue
        groups = m.groups()
        # Pattern 3 puts the number first, so order is consistent: (num, unit)
        num, unit = groups[0], groups[1]
        val = _to_millions(num, unit)
        if val is None:
            continue
        growth = None
        gm = _REV_GROWTH.search(text)
        if gm:
            direction, pct = gm.group(1).lower(), _to_float(gm.group(2))
            if pct is not None:
                negative = direction.startswith(('decreas', 'declin', 'fell', 'down'))
                growth = -pct if negative else pct
        return dict(value_musd=val, unit_seen=unit.lower(),
                    growth_pct=growth, raw=m.group(0).strip())
    return None


# --- operating income --------------------------------------------------------
#
# ★ 11 rows across the library name operating income, 4 of them graded HEROES,
# and three of those four are AMZN -- where OI *is* the hero and the Q2 guide of
# $22B against a $23.85B Q1 base was the entire trade. Before this there was no
# extractor: adjusted EBITDA was parsed, operating income was not, so every one
# of those rows read not-found from a release that stated the figure plainly.
#
# Basis is handled exactly as EPS handles it -- GAAP and non-GAAP kept SEPARATE,
# never merged. A row naming its basis gets that basis or nothing; CBRS-2026Q2
# is the founding case, where GAAP missed 7.0% while the company's "core" basis
# beat 9.9% and the tape traded GAAP.

_OI_CORE = r'(?:operating\s+income|income\s+from\s+operations|operating\s+profit)'

_OI_PATTERNS = [
    # "Non-GAAP operating income of $2.77 billion"
    re.compile(r'(?:(non-?GAAP|GAAP|adjusted|adj\.?)\s+)?' + _OI_CORE +
               r'[^\n]{0,40}?of\s+' + _NUM + r'\s*' + _UNIT, re.I),
    # "Operating income was $23.9 billion"
    re.compile(r'(?:(non-?GAAP|GAAP|adjusted|adj\.?)\s+)?' + _OI_CORE +
               r'[^\n]{0,40}?(?:was|were|totaled|totalled|reached)\s+'
               + _NUM + r'\s*' + _UNIT, re.I),
    # "operating income increased 61% to $23.9 billion"
    re.compile(r'(?:(non-?GAAP|GAAP|adjusted|adj\.?)\s+)?' + _OI_CORE +
               r'[^\n]{0,50}?\bto\s+' + _NUM + r'\s*' + _UNIT, re.I),
]


# ★ COMPANY-LEVEL, not segment-level. `_is_segment_context` looks for the literal
# word "segment", and "Google Cloud operating income was $3.2 billion" does not
# contain it -- so the company matcher took Cloud's $3.2B as consolidated OI.
# The reliable signal is what stands between the start of the clause and the
# metric phrase: for a consolidated figure that is nothing but basis words, and
# for a segment figure it is the segment's NAME.
_CLAUSE_FILLER = re.compile(
    r'^(?:(?:non-?gaap|gaap|adjusted|adj\.?|total|consolidated|company|'
    r'our|the|a|its|worldwide|overall|net|reported|'
    # ★ Period words are scaffolding too. A wire release writes "First
    # quarter revenue increased 17% to ..." and "Q2 revenue was ...";
    # rejecting those as subject-qualified would refuse the headline
    # figure on most real releases.
    r'first|second|third|fourth|1st|2nd|3rd|4th|q[1-4]|fq[1-4]|'
    r'f[1-4]q|fy\d*|[12]\d{3}|fiscal|quarter|quarterly|year|full|annual)\b\s*)*$',
    re.I)


def _is_company_context(text, start):
    """True when the metric phrase at `start` is not qualified by a subject.

    ★ A NEWLINE ends a clause as surely as a full stop does. `parse_release`
    joins headline + teaser + body, and a wire headline carries no terminating
    period -- so the left context of the body's FIRST sentence was the headline
    itself, which is never filler, and every release stating operating income in
    its opening line was refused. Splitting on sentence punctuation alone worked
    only in test bodies whose preceding line happened to end in a period.
    """
    left = text[max(0, start - 160):start]
    # ★ split('\n'), NOT splitlines(): splitlines() DISCARDS the trailing empty
    # field, so a phrase sitting at the start of its own line was handed the
    # PREVIOUS line as its context -- "...to $181.5 billion in the first
    # quarter." -- which is never filler. That refused AMZN's company operating
    # income, the one row this extractor exists for.
    left = left.split('\n')[-1]
    left = re.split(r'(?<=[.!?])\s+', left)[-1]     # this sentence only
    left = left.rsplit(',', 1)[-1]                   # drop a leading clause
    return bool(_CLAUSE_FILLER.match(left.strip()))


def parse_op_income(text):
    """{basis: {value_musd, raw, source}} for operating income. Never merged.

    Basis keys are 'non-GAAP', 'GAAP' or 'unknown' -- the same three EPS uses,
    so a row that names its basis can demand it and a row that does not can
    prefer non-GAAP without either decision being implicit.
    """
    out = {}
    for pat in _OI_PATTERNS:
        for m in pat.finditer(text):
            if _SEG_FORWARD.search(m.group(0)):
                continue                   # a guide, not a reported actual
            if not _is_company_context(text, m.start()):
                continue                   # a segment or subject-qualified line
            basis = _norm_basis(m.group(1))
            val = _to_millions(m.group(2), m.group(3))
            if val is None:
                continue
            out.setdefault(basis, dict(value_musd=val, raw=m.group(0).strip(),
                                       source='prose'))
    return out


def segment_op_income(text, tokens):
    """Operating income stated FOR one segment, matched on ALL of `tokens`.

    "Google Cloud operating income was $3.2 billion" fills a "Cloud OI ($B)"
    row; the company operating income never does. Same discipline as segment
    revenue, for the same reason.
    """
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return None
    pats = [re.compile(r'\b%s' % re.escape(t), re.I) for t in toks]
    core = re.compile(_OI_CORE, re.I)

    hits = []
    for sent in _sentences(text):
        if not all(pt.search(sent) for pt in pats):
            continue
        if not core.search(sent):
            continue
        if _SEG_FORWARD.search(sent):
            continue
        m = _SEG_MONEY.search(sent)
        if not m:
            continue
        val = _to_millions(m.group(1), m.group(2))
        if val is None:
            continue
        hits.append((val, m.group(1), sent))

    if not hits:
        return None
    distinct = {round(h[0], 6) for h in hits}
    if len(distinct) > 1:
        return dict(value_musd=None, source='prose (segment OI) AMBIGUOUS',
                    raw='; '.join(h[2][:70] for h in hits[:3]),
                    decimals=None, stated=None, ambiguous=sorted(distinct))
    val, num, sent = hits[0]
    return dict(value_musd=val, source='prose (segment OI)', raw=sent[:120],
                decimals=_decimals(num), stated=_to_float(num), ambiguous=None)


# --- adjusted EBITDA ---------------------------------------------------------
#
# ★ APP-2026Q2's hero rows are "2Q Adj EBITDA ($B) ★" and "3Q Adj EBITDA Guide
# ($B) ★", and EBITDA existed only in the TABLE path -- which covers APP's real
# release (it is entirely tabular) and nothing stated in prose. It was the one
# routing miss left in the live push, on a hero row, which defers the whole
# Current Quarter under the extraction-gap rule.

_EBITDA_CORE = r'(?:adjusted\s+|adj\.?\s+)?EBITDA'

_EBITDA_PATTERNS = [
    re.compile(r'(?:(adjusted|adj\.?)\s+)?EBITDA'
               r'[^\n]{0,40}?of\s+' + _NUM + r'\s*' + _UNIT, re.I),
    re.compile(r'(?:(adjusted|adj\.?)\s+)?EBITDA'
               r'[^\n]{0,40}?(?:was|were|totaled|totalled|reached)\s+'
               + _NUM + r'\s*' + _UNIT, re.I),
    re.compile(r'(?:(adjusted|adj\.?)\s+)?EBITDA'
               r'[^\n]{0,50}?\bto\s+' + _NUM + r'\s*' + _UNIT, re.I),
]

# "Adjusted EBITDA of between $1.70 billion and $1.75 billion"
_GUIDE_EBITDA = re.compile(
    r'(?:adjusted\s+|adj\.?\s+)?EBITDA'
    r'[^\n]{0,60}?(?:of|between|to\s+be)\s+\$?\s?([\d,]+(?:\.\d+)?)\s*'
    r'(?:' + _UNIT + r')?\s*(?:to|and|-|\u2013)\s*\$?\s?'
    r'([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)

_GUIDE_EBITDA_POINT = re.compile(
    r'(?:adjusted\s+|adj\.?\s+)?EBITDA'
    r'[^\n]{0,60}?(?:of|to\s+be)\s+(?:approximately\s+)?\$?\s?'
    r'([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)


def parse_adj_ebitda(text):
    """{basis: {value_musd, raw, source}} for EBITDA. 'adjusted' or 'unknown'.

    A row named "Adj EBITDA" demands the ADJUSTED figure; plain EBITDA is a
    different measure and is kept under its own key rather than merged, the same
    way GAAP and non-GAAP EPS are.
    """
    out = {}
    for pat in _EBITDA_PATTERNS:
        for m in pat.finditer(text):
            if _SEG_FORWARD.search(m.group(0)):
                continue
            if not _is_company_context(text, m.start()):
                continue
            basis = 'adjusted' if m.group(1) else 'unknown'
            val = _to_millions(m.group(2), m.group(3))
            if val is None:
                continue
            out.setdefault(basis, dict(value_musd=val,
                                       raw=m.group(0).strip(),
                                       source='prose'))
    return out


def segment_adj_ebitda(text, tokens):
    """EBITDA stated FOR one qualifier. Company EBITDA never fills such a row."""
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return None
    pats = [re.compile(r'\b%s' % re.escape(t), re.I) for t in toks]
    core = re.compile(_EBITDA_CORE, re.I)
    hits = []
    for sent in _sentences(text):
        if not all(pt.search(sent) for pt in pats):
            continue
        if not core.search(sent) or _SEG_FORWARD.search(sent):
            continue
        m = _SEG_MONEY.search(sent)
        if not m:
            continue
        val = _to_millions(m.group(1), m.group(2))
        if val is not None:
            hits.append((val, m.group(1), sent))
    if not hits:
        return None
    distinct = {round(h[0], 6) for h in hits}
    if len(distinct) > 1:
        return dict(value_musd=None, source='prose (segment EBITDA) AMBIGUOUS',
                    raw='; '.join(h[2][:70] for h in hits[:3]),
                    decimals=None, stated=None, ambiguous=sorted(distinct))
    val, num, sent = hits[0]
    return dict(value_musd=val, source='prose (segment EBITDA)',
                raw=sent[:120], decimals=_decimals(num),
                stated=_to_float(num), ambiguous=None)


# --- segment revenue ---------------------------------------------------------
#
# ★ Why this exists: AMD-2026Q1's PRIORITY-1 hero is "Q1 Data Center Revenue
# ($B)", and the release states it plainly -- "Data Center segment revenue was
# $5.8 billion". Before this there was NO segment extractor of any kind, in
# prose or table, so the row could only ever be filled by accident: the
# headline-total matcher caught every row containing the word "revenue" and
# wrote 10.3 into five of them. Tightening the matcher fixed the false MISSes
# and left the hero unextractable, which makes the whole card unscoreable.
# Refusing beats a false MISS, but reading the number beats both.
#
# A segment figure is only ever accepted when EVERY distinguishing token of the
# row name appears in the same sentence as the figure. There is no broader
# fallback, by construction.

_SEG_FORWARD = re.compile(
    r'\b(?:guidance|guide|outlook|expect|expects|expected|forecast|'
    r'anticipat\w*|target\w*|will\s+be|we\s+see)\b', re.I)

# "up 14% year over year to $5.8 billion" -- the FIRST figure in a wire
# sentence is the reported one; a prior-year comparative follows it.
_SEG_MONEY = re.compile(r'\$\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)
_SEG_REV_WORD = re.compile(r'\b(?:revenue|revenues|net\s+sales|sales)\b', re.I)


def _decimals(raw):
    """Stated decimal places, so a ROUNDED figure can be graded honestly."""
    m = re.search(r'\.(\d+)', str(raw or ''))
    return len(m.group(1)) if m else 0


def segment_revenue(text, tokens):
    """Revenue for ONE segment, matched on ALL of `tokens`.

    Returns {value_musd, unit_seen, growth_pct, raw, source, decimals} or None.
    Two sentences yielding DIFFERENT values is an ambiguity, not a reading, and
    returns None -- the same discipline as refusing a duplicated actual.
    """
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return None
    pats = [re.compile(r'\b%s' % re.escape(t), re.I) for t in toks]

    hits = []
    for sent in _sentences(text):
        if not all(pt.search(sent) for pt in pats):
            continue
        if not _SEG_REV_WORD.search(sent):
            continue
        # A forward-looking sentence is a GUIDE, never a reported actual
        # (non-negotiable 2: classify the period before matching the metric).
        if _SEG_FORWARD.search(sent):
            continue
        m = _SEG_MONEY.search(sent)
        if not m:
            continue
        val = _to_millions(m.group(1), m.group(2))
        if val is None:
            continue
        hits.append((val, m.group(0), m.group(1), sent))

    if not hits:
        return None
    distinct = {round(h[0], 6) for h in hits}
    if len(distinct) > 1:
        return dict(value_musd=None, unit_seen=None, growth_pct=None,
                    raw='; '.join(h[3][:70] for h in hits[:3]),
                    source='prose (segment) AMBIGUOUS', decimals=None,
                    ambiguous=sorted(distinct))
    val, raw, num, sent = hits[0]
    return dict(value_musd=val, unit_seen=(_SEG_MONEY.search(sent).group(2)
                                           or '').lower(),
                growth_pct=None, raw=sent[:120], source='prose (segment)',
                decimals=_decimals(num), stated=_to_float(num),
                ambiguous=None)


_SEG_PCT = re.compile(r'(\d+(?:\.\d+)?)\s*%')
_SEG_MARGIN_WORD = re.compile(r'\b(?:gross\s+margin|operating\s+margin|GM|OPM)\b',
                              re.I)


def segment_margin(text, tokens):
    """A MARGIN stated for one qualifier, e.g. "Product gross margin of 64.8%".

    ★ The margin dimension of the same defect. "Auto GM ex-credits (%)" and
    "Product Gross Margin (%)" are NOT the company gross margin, and filling
    them from it is a definitional mismatch -- the failure mode CLAUDE.md lists
    under what must not be automated. So a qualified margin row is filled only
    from a sentence carrying ALL of its qualifiers.
    """
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return None
    pats = [re.compile(r'\b%s' % re.escape(t), re.I) for t in toks]

    hits = []
    for sent in _sentences(text):
        if not all(pt.search(sent) for pt in pats):
            continue
        if not _SEG_MARGIN_WORD.search(sent):
            continue
        if _SEG_FORWARD.search(sent):
            continue
        m = _SEG_PCT.search(sent)
        if not m:
            continue
        val = _to_float(m.group(1))
        if val is None or not (-100.0 <= val <= 100.0):
            continue
        hits.append((val, m.group(1), sent))

    if not hits:
        return None
    distinct = {round(h[0], 6) for h in hits}
    if len(distinct) > 1:
        return dict(value=None, source='prose (segment margin) AMBIGUOUS',
                    raw='; '.join(h[2][:70] for h in hits[:3]),
                    decimals=None, stated=None, ambiguous=sorted(distinct))
    val, num, sent = hits[0]
    return dict(value=val, source='prose (segment margin)', raw=sent[:120],
                decimals=_decimals(num), stated=val, ambiguous=None)


# --- EPS ----------------------------------------------------------------------

_EPS_CORE = (r'(?:diluted\s+|basic\s+)?(?:net\s+)?(?:income|loss|earnings)\s+per\s+'
             r'(?:diluted\s+|basic\s+)?share|EPS|earnings\s+per\s+share')

# The digit class must NOT be [\d.]+ -- it greedily swallows the sentence's
# terminating period, yielding '1.22.' which float() rejects, and the figure
# is then silently dropped.
_EPS_VALUE = r'\$?\s?(\(?-?\d+(?:\.\d+)?\)?)'

_EPS_PATTERNS = [
    # non-GAAP diluted EPS of $1.22
    re.compile(r'(non-?GAAP|GAAP|adjusted)\s+(?:diluted\s+|basic\s+)?'
               r'(?:' + _EPS_CORE + r')\s+(?:of|was|were|totall?ed|came\s+in\s+at)?\s*'
               + _EPS_VALUE, re.I),
    # $1.22 per diluted share on a non-GAAP basis
    re.compile(_EPS_VALUE + r'\s+per\s+(?:diluted\s+|basic\s+)?share'
               r'(?:[^.\n]{0,40}?(non-?GAAP|GAAP|adjusted))?', re.I),
    # diluted EPS of $0.97 (basis unstated)
    re.compile(r'(?:' + _EPS_CORE + r')\s+(?:of|was|were)\s+' + _EPS_VALUE, re.I),
]


def _norm_basis(raw):
    if not raw:
        return 'unknown'
    low = raw.lower().replace('-', '').replace(' ', '')
    if low in ('nongaap', 'adjusted'):
        return 'non-GAAP'
    if low == 'gaap':
        return 'GAAP'
    return 'unknown'


def parse_eps(text):
    """Returns {'GAAP': v, 'non-GAAP': v, 'unknown': v} for whatever was found.

    GAAP and non-GAAP are kept strictly separate -- per error class 7, a
    one-off mark-to-market gain can make headline GAAP EPS look like a huge
    beat against a non-GAAP consensus.
    """
    candidates = []
    for pat in _EPS_PATTERNS:
        for m in pat.finditer(text):
            # Locate which group is the basis and which is the number.
            basis_raw, num_raw = None, None
            for g in m.groups():
                if g is None:
                    continue
                if re.fullmatch(r'non-?gaap|gaap|adjusted', g, re.I):
                    basis_raw = g
                elif re.search(r'\d', g):
                    num_raw = g
            if num_raw is None:
                continue
            was_paren = num_raw.strip().startswith('(')
            val = _to_float(num_raw.strip('()'), negative_parens=True,
                            was_paren=was_paren)
            if val is None or abs(val) > 1000:
                continue
            candidates.append((m.start(), _norm_basis(basis_raw), val,
                               m.group(0).strip()))

    # Earliest mention wins per basis. Press releases lead with the current
    # period and mention the prior-year comparative afterwards, so position
    # order is what keeps "$(0.45) this quarter" from losing to "$0.12 in the
    # prior year period".
    found = {}
    for pos, basis, val, raw in sorted(candidates, key=lambda c: c[0]):
        found.setdefault(basis, dict(value=val, raw=raw))
    return found


# --- guidance -----------------------------------------------------------------

_GUIDE_TRIGGER = re.compile(
    r'\b(?:guidance|outlook|expects?|anticipat\w+|forecast\w*|project\w+|'
    r'sees?|guid\w+)\b', re.I)

_PERIOD_NEXTQ = re.compile(
    r'\b(?:(?:first|second|third|fourth|1st|2nd|3rd|4th|next|current)\s+quarter'
    r'|Q[1-4]\b)', re.I)
_PERIOD_FY = re.compile(
    r'\b(?:full[- ]year|full\s+fiscal\s+year|fiscal\s+(?:year\s+)?\d{2,4}'
    r'|FY\s?\d{2,4})\b', re.I)

# $17.3 billion to $17.5 billion  |  $17.3 to $17.5 billion  |  $17.3-$17.5 billion
_RANGE = re.compile(
    r'\$\s?([\d,]+(?:\.\d+)?)\s*(?:' + _UNIT + r')?\s*(?:to|-|–|and)\s*'
    r'\$?\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)

_SINGLE = re.compile(r'\$\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)

# ★ ANCHOR THE RANGE TO THE METRIC. `_RANGE` finds the first "$X to $Y" in the
# sentence and a real guidance sentence carries several metrics:
#
#   "expects revenue of $2.070 billion and adjusted EBITDA of between
#    $1.70 billion and $1.75 billion"
#
# The unanchored search crossed the two, so the REVENUE guide row and the EBITDA
# guide row received the same figure -- caught only because the duplicate guard
# refuses one value in two rows. On a release stating revenue plus any other
# ranged metric, the revenue guide would have been silently wrong.
_REV_WORD = r'(?:revenues?|net\s+sales|total\s+sales)'

_METRIC_NOUN = re.compile(
    r'ebitda|operating\s+income|income\s+from\s+operations|operating\s+profit|'
    r'earnings\s+per\s+share|\bEPS\b|margin|free\s+cash\s+flow|\bFCF\b|'
    r'capex|capital\s+expenditure', re.I)

_GUIDE_REV_RANGE = re.compile(
    _REV_WORD + r'([^\n]{0,40}?)\$\s?([\d,]+(?:\.\d+)?)\s*(?:' + _UNIT +
    r')?\s*(?:to|-|\u2013|and)\s*\$?\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT,
    re.I)

_GUIDE_REV_POINT = re.compile(
    _REV_WORD + r'([^\n]{0,40}?)\$\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)


def _clean_gap(m):
    """True when nothing between the metric word and the figure names ANOTHER
    metric -- "revenue of" is clean, "revenue ... and adjusted EBITDA of" is not.
    """
    return not _METRIC_NOUN.search(m.group(1) or '')

# Extra lines inside a guidance sentence.
# ★ "operating income of between $20.0 billion and $24.0 billion" -- AMZN's Q2
# OI guide, the row whose $22B midpoint against a $23.85B Q1 base was the trade.
_GUIDE_OI = re.compile(
    r'(?:operating\s+income|income\s+from\s+operations|operating\s+profit)'
    r'[^\n]{0,60}?(?:of|between|to\s+be)\s+\$?\s?([\d,]+(?:\.\d+)?)\s*'
    r'(?:' + _UNIT + r')?\s*(?:to|and|-|\u2013)\s*\$?\s?'
    r'([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)

_GUIDE_OI_POINT = re.compile(
    r'(?:operating\s+income|income\s+from\s+operations|operating\s+profit)'
    r'[^\n]{0,60}?(?:of|to\s+be)\s+(?:approximately\s+)?\$?\s?'
    r'([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)

_GUIDE_MARGIN = re.compile(
    r'(?:non-?GAAP\s+)?gross\s+margin\s+(?:of|at|to\s+be)\s+'
    r'(?:approximately\s+|about\s+|around\s+)?([\d.]+)\s*%', re.I)
# ★ TWO defects in one three-line pattern, both already documented elsewhere in
# this file and both still live here:
#
#  1. `([\d.]+)` with nothing after it swallows the sentence-ending period, so
#     "non-GAAP EPS of $5.00." captured '5.00.' and float() raised -- the value
#     was then dropped SILENTLY because the caller only assigns when the parse
#     succeeds. The comment at the top of the EPS section warns about exactly
#     this; the guidance leg never got the fix. The percent-suffixed patterns
#     are safe by accident: a '%' must follow, so the period cannot be eaten.
#
#  2. Only the token "EPS" was accepted, never the spelled-out phrase. A wire
#     release writes both, and "non-GAAP earnings per share of $5.00" is the
#     more common form in a guidance sentence.
_GUIDE_EPS = re.compile(
    r'(?:non-?GAAP\s+|GAAP\s+)?(?:diluted\s+)?'
    r'(?:EPS|earnings\s+per\s+(?:diluted\s+)?share)\s+(?:of|at|to\s+be)\s+'
    r'\$?\s?(\d+(?:\.\d+)?)', re.I)


def _sentences(text):
    """Split into sentences, tolerating hard-wrapped press-release copy.

    Wire bodies wrap at ~72 columns, so a guidance range routinely straddles
    a newline: "revenue of $18.1 billion\\nto $18.3 billion". Splitting on
    \\n first tears the range apart and the parser falls back to reading the
    low end as a point estimate. Collapse whitespace within each paragraph
    before splitting on sentence punctuation.
    """
    out = []
    for para in re.split(r'\n\s*\n', text):
        flat = re.sub(r'\s+', ' ', para).strip()
        if not flat:
            continue
        out.extend(s for s in re.split(r'(?<=[.!?])\s+', flat) if s)
    return out


def parse_guidance(text):
    """Extract next-quarter and full-year revenue guidance ranges.

    Returns {'nextQ': {...}, 'fy': {...}} with low/high/mid in $M, plus the
    sentence it came from so the figure is auditable.
    """
    out = {}
    for sent in _sentences(text):
        if not _GUIDE_TRIGGER.search(sent):
            continue
        # Quarter language wins over fiscal-year language. "For the first
        # quarter of fiscal 2027" names a QUARTER even though it contains
        # "fiscal 2027" -- checking FY first files next-Q guidance as FY and
        # leaves next-Q empty.
        is_nextq = bool(_PERIOD_NEXTQ.search(sent))
        is_fy = bool(_PERIOD_FY.search(sent)) and not is_nextq
        if not (is_fy or is_nextq):
            continue
        key = 'fy' if is_fy else 'nextQ'
        if key in out:
            continue

        # revenue-anchored first; the unanchored patterns are the fallback and
        # are only safe when the sentence names no other metric.
        am = _GUIDE_REV_RANGE.search(sent)
        if am and _clean_gap(am):
            lo_raw, lo_unit, hi_raw, hi_unit = (am.group(2), am.group(3),
                                                am.group(4), am.group(5))
            unit = lo_unit or hi_unit
            lo = _to_millions(lo_raw, unit)
            hi = _to_millions(hi_raw, hi_unit or unit)
            if lo is not None and hi is not None:
                out[key] = dict(low=lo, high=hi, mid=round((lo + hi) / 2, 3),
                                unit_seen=(unit or 'million').lower(),
                                basis='range', raw=sent.strip()[:300])
                continue
        ap = _GUIDE_REV_POINT.search(sent)
        if ap and _clean_gap(ap):
            val = _to_millions(ap.group(2), ap.group(3))
            if val is not None:
                out[key] = dict(low=val, high=val, mid=val,
                                unit_seen=ap.group(3).lower(),
                                basis='point', raw=sent.strip()[:300])
                continue
        if _METRIC_NOUN.search(sent):
            # Several metrics and no revenue-anchored match: refuse rather than
            # take whichever figure happens to come first.
            continue

        m = _RANGE.search(sent)
        if m:
            lo_raw, lo_unit, hi_raw, hi_unit = m.groups()
            # "$17.3 to $17.5 billion" -- the unit trails, so it governs both.
            unit = lo_unit or hi_unit
            lo = _to_millions(lo_raw, unit)
            hi = _to_millions(hi_raw, hi_unit or unit)
            if lo is not None and hi is not None:
                out[key] = dict(low=lo, high=hi, mid=round((lo + hi) / 2, 3),
                                unit_seen=(unit or 'million').lower(),
                                basis='range', raw=sent.strip()[:300])
                continue
        m = _SINGLE.search(sent)
        if m:
            val = _to_millions(m.group(1), m.group(2))
            if val is not None:
                out[key] = dict(low=val, high=val, mid=val,
                                unit_seen=m.group(2).lower(),
                                basis='point', raw=sent.strip()[:300])

    # ★ A guidance sentence usually carries MORE than revenue, and the extra
    # lines are often the ones a grade turns on. WDC's forward gross-margin
    # guide sits inside a CFO quote:
    #   "For our fiscal first quarter of 2027 ... we expect revenue of
    #    $4.1 billion, non-GAAP gross margin of 55.5%, and non-GAAP EPS of $4.00"
    # Extracting only the revenue left the F1Q Gross Margin Guide row empty,
    # which under the extraction-gap rule defers the whole nextQ category.
    # ★ A GUIDANCE SENTENCE WITH NO REVENUE FIGURE PRODUCED NO BLOCK AT ALL.
    # Every block above is created by the revenue leg, and the margin / EPS /
    # OI / EBITDA legs below only DECORATE an existing block. So
    #
    #   "For the full year, the company expects non-GAAP gross margin of 34.3%"
    #
    # was dropped entirely -- parse_guidance returned {} -- and BE-2026Q2's
    # "FY Adj Gross Margin Guide (%)" row read not-found from a release that
    # stated it plainly. Plenty of releases guide margin or EPS without
    # restating revenue in the same sentence.
    #
    # So: a second pass creates a METRICS-ONLY block for any guidance sentence
    # whose period has no block yet. `mid` stays None, because no revenue was
    # guided and inventing one would be worse than the gap; callers that need a
    # midpoint must treat None as absent.
    for sent in _sentences(text):
        if not _GUIDE_TRIGGER.search(sent):
            continue
        is_nextq = bool(_PERIOD_NEXTQ.search(sent))
        is_fy = bool(_PERIOD_FY.search(sent)) and not is_nextq
        if not (is_fy or is_nextq):
            continue
        key = 'fy' if is_fy else 'nextQ'
        if key in out:
            continue
        if not (_GUIDE_MARGIN.search(sent) or _GUIDE_EPS.search(sent)
                or _GUIDE_OI.search(sent) or _GUIDE_OI_POINT.search(sent)
                or _GUIDE_EBITDA.search(sent)
                or _GUIDE_EBITDA_POINT.search(sent)):
            continue
        out[key] = dict(low=None, high=None, mid=None, unit_seen=None,
                        basis='metrics-only', raw=sent.strip()[:300])

    for key, block in out.items():
        sent = block.get('raw') or ''
        mm = _GUIDE_MARGIN.search(sent)
        if mm:
            v = _to_float(mm.group(1))
            if v is not None and 0 <= v <= 100:
                block['grossMarginPct'] = v
        me = _GUIDE_EPS.search(sent)
        if me:
            v = _to_float(me.group(1))
            if v is not None:
                block['epsMid'] = v

        # ★ The operating-income leg of the same sentence. AMZN states its Q2 OI
        # guide as a RANGE in the same breath as revenue -- "net sales of $194.0
        # to $199.0 billion and operating income of between $20.0 billion and
        # $24.0 billion" -- and the midpoint is what grades against a midpoint
        # consensus. Taking the high end instead reads $24B as the guide and
        # turns a documented MISS into a beat.
        mb = _GUIDE_EBITDA.search(sent)
        if mb:
            lo = _to_millions(mb.group(1), mb.group(2) or mb.group(4))
            hi = _to_millions(mb.group(3), mb.group(4))
            if lo is not None and hi is not None:
                block['ebitdaLow'] = lo
                block['ebitdaHigh'] = hi
                block['ebitdaMid'] = (lo + hi) / 2.0
        elif _GUIDE_EBITDA_POINT.search(sent):
            mbp = _GUIDE_EBITDA_POINT.search(sent)
            v = _to_millions(mbp.group(1), mbp.group(2))
            if v is not None:
                block['ebitdaLow'] = block['ebitdaHigh'] = v
                block['ebitdaMid'] = v

        mo = _GUIDE_OI.search(sent)
        if mo:
            lo = _to_millions(mo.group(1), mo.group(2) or mo.group(4))
            hi = _to_millions(mo.group(3), mo.group(4))
            if lo is not None and hi is not None:
                block['opIncomeLow'] = lo
                block['opIncomeHigh'] = hi
                block['opIncomeMid'] = (lo + hi) / 2.0
        elif _GUIDE_OI_POINT.search(sent):
            mp = _GUIDE_OI_POINT.search(sent)
            v = _to_millions(mp.group(1), mp.group(2))
            if v is not None:
                block['opIncomeLow'] = block['opIncomeHigh'] = v
                block['opIncomeMid'] = v
    return out


# --- margins ------------------------------------------------------------------

_MARGIN_PATTERNS = {
    'grossMargin': re.compile(
        r'(non-?GAAP\s+|GAAP\s+)?gross\s+margin[^.\n]{0,40}?([\d.]+)\s*%', re.I),
    'operatingMargin': re.compile(
        r'(non-?GAAP\s+|GAAP\s+)?operating\s+margin[^.\n]{0,40}?([\d.]+)\s*%', re.I),
}


_ACTION_PATTERNS = [
    # ★ These three DEFER, they are never scored. See score._DEFER_ACTIONS.
    ('WITHDRAWN', re.compile(r'\b(?:withdraw\w*|suspend\w*|no longer '
                             r'provid\w+|discontinu\w+|retir\w+ (?:its |the )?'
                             r'(?:prior )?(?:guidance|outlook|target))\b', re.I)),
    # A capped roadmap: a previously escalating target replaced by prose.
    ('CAPPED', re.compile(r'\b(?:replac\w+ (?:its |the )?(?:prior )?'
                          r'(?:guidance|outlook|target)|'
                          r'meaningfully higher|no longer (?:quantif\w+|'
                          r'disclos\w+|break\w+ out))\b', re.I)),
    # A volunteered ceiling: a growth cap offered unprompted (APP's "compound
    # at roughly 30% annually" on a miss quarter).
    # NB: no trailing \b -- these alternatives end in '%', and \b between '%'
    # and a following space matches nothing, which silently kills the pattern.
    ('CEILING', re.compile(r'\b(?:compound\w*(?: at)? (?:roughly |approximately |'
                           r'about )?\d+(?:\.\d+)?%|long[- ]term (?:growth )?'
                           r'(?:target|model) of (?:roughly |about )?\d+(?:\.\d+)?%'
                           r'|(?:expects?|sees?) (?:growth )?to (?:moderate|'
                           r'normalize|settle) (?:to |at )?(?:roughly |about )?'
                           r'\d+(?:\.\d+)?%)', re.I)),
    ('RAISED', re.compile(r'\b(?:rais\w+|increas\w+|lift\w+|rev\w+ up\w*|'
                          r'improv\w+)\s+(?:its\s+|the\s+|full[- ]year\s+|'
                          r'fiscal\s+\S+\s+)*(?:revenue\s+)?'
                          r'(?:guidance|outlook|forecast|target)', re.I)),
    ('CUT', re.compile(r'\b(?:lower\w+|reduc\w+|cut\w*|trim\w+|narrow\w+ down)'
                       r'\s+(?:its\s+|the\s+|full[- ]year\s+|fiscal\s+\S+\s+)*'
                       r'(?:revenue\s+)?(?:guidance|outlook|forecast|target)',
                       re.I)),
    ('MAINTAINED', re.compile(r'\b(?:reaffirm\w+|maintain\w+|reiterat\w+|'
                              r'unchanged|confirm\w+)\s+(?:its\s+|the\s+|'
                              r'full[- ]year\s+|fiscal\s+\S+\s+)*'
                              r'(?:revenue\s+)?(?:guidance|outlook|forecast|'
                              r'target)', re.I)),
]

# "to $76.5 billion to $77.5 billion FROM $74.0 billion to $75.0 billion"
# "compared to prior guidance of $74.0-75.0 billion"
# "up from a prior range of ..."
_PRIOR_RANGE = re.compile(
    r'(?:\bfrom\b|compared\s+(?:to|with)|versus|vs\.?|prior\s+(?:guidance|'
    r'range|outlook)\s+of|previously)\s*'
    r'\$?\s?([\d,]+(?:\.\d+)?)\s*(?:' + _UNIT + r')?'
    r'(?:\s*(?:to|-|–)\s*\$?\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT + r')?', re.I)


def parse_guidance_action(text):
    """RAISED / MAINTAINED / CUT / WITHDRAWN per period, or {} when unstated.

    This is what unblocks FY guidance. The FY band keys on the ACTION -- raised
    versus reaffirmed versus cut -- which cannot be inferred from a midpoint
    alone; it needs the prior range or an explicit verb. Releases usually give
    one or the other, and when they give neither the category must defer rather
    than guess.
    """
    out = {}
    for sent in _sentences(text):
        if not _GUIDE_TRIGGER.search(sent) and not re.search(
                r'guidance|outlook|forecast', sent, re.I):
            continue
        is_fy = bool(_PERIOD_FY.search(sent))
        is_nextq = bool(_PERIOD_NEXTQ.search(sent))
        # Quarter language wins, same precedence as parse_guidance.
        key = 'nextQ' if is_nextq else ('fy' if is_fy else None)
        if key is None or key in out:
            continue
        for action, pat in _ACTION_PATTERNS:
            if pat.search(sent):
                entry = dict(action=action, raw=sent.strip()[:300])
                pm = _PRIOR_RANGE.search(sent)
                if pm:
                    lo_raw, lo_unit, hi_raw, hi_unit = pm.groups()
                    unit = lo_unit or hi_unit
                    lo = _to_millions(lo_raw, unit)
                    hi = _to_millions(hi_raw, hi_unit or unit) if hi_raw else lo
                    if lo is not None and hi is not None:
                        entry['priorLow'] = lo
                        entry['priorHigh'] = hi
                        entry['priorMid'] = round((lo + hi) / 2, 3)
                out[key] = entry
                break
    return out


def parse_margins(text):
    """Margins from prose, preferring the non-GAAP basis.

    ★ Order of appearance is the wrong tie-break. WDC's release opens with
    "GAAP gross margin of 54.1%; non-GAAP gross margin of 54.4%", so taking the
    first match reports the GAAP figure against a non-GAAP bogey -- error class
    D3/D7, on the graded line.
    """
    out = {}
    for name, pat in _MARGIN_PATTERNS.items():
        best = None
        for m in pat.finditer(text):
            val = _to_float(m.group(2))
            if val is None or not (0 <= val <= 100):
                continue
            basis = _norm_basis((m.group(1) or '').strip())
            cand = dict(value=val, basis=basis, raw=m.group(0).strip())
            if best is None:
                best = cand
            elif basis == 'non-GAAP' and best['basis'] != 'non-GAAP':
                best = cand
        if best is not None:
            out[name] = best
    return out


# Margin direction YoY. Feeds the "gross or operating margin down
# YEAR-OVER-YEAR" offsetting flag, which is one of the seven and is routinely
# stated outright in the release.
# NB: the gap class allows '.' -- "gross margin of 66.3%, down 210 basis
# points" carries a decimal point between the label and the direction word,
# and excluding '.' silently kills the match.
_MARGIN_BPS = re.compile(
    r'(?:gross|operating)\s+margin[^\n]{0,60}?'
    r'\b(down|up|decreas\w+|increas\w+|declin\w+|expand\w+|contract\w+)\s+'
    r'(?:by\s+)?([\d,]+)\s*(?:basis\s+points|bps|bp)\b', re.I)

# "gross margin of 66.3% compared with 68.4%" / "versus 68.4% a year ago"
_MARGIN_COMPARE = re.compile(
    r'(?:gross|operating)\s+margin[^.\n]{0,40}?([\d.]+)\s*%'
    r'[^.\n]{0,40}?(?:compared\s+(?:with|to)|versus|vs\.?|from)\s*([\d.]+)\s*%',
    re.I)

_NEGATIVE_WORDS = ('down', 'decreas', 'declin', 'contract')


def parse_margin_yoy_bps(text):
    """Basis-point YoY margin change, signed. None when not stated.

    Returned as None rather than 0 when absent -- the caller must be able to
    tell "margin held" from "the release did not say", because an unassessed
    flag can move the Current Quarter band.
    """
    m = _MARGIN_BPS.search(text)
    if m:
        direction = m.group(1).lower()
        val = _to_float(m.group(2))
        if val is not None:
            negative = any(direction.startswith(w) for w in _NEGATIVE_WORDS)
            return int(-val if negative else val)
    m = _MARGIN_COMPARE.search(text)
    if m:
        now, prior = _to_float(m.group(1)), _to_float(m.group(2))
        if now is not None and prior is not None:
            return int(round((now - prior) * 100))
    return None


# --- top level ----------------------------------------------------------------

def parse_release(item):
    """Parse a wire item's body into normalised reported figures.

    Returns a dict with revenue / eps / guidance / margins plus a `fields`
    count so the caller can tell a rich release from a thin one.
    """
    text = '\n'.join([item.get('headline') or '',
                      item.get('teaser') or '',
                      item.get('body') or ''])

    parsed = dict(
        revenue=parse_revenue(text),
        opIncome=parse_op_income(text),
        adjEbitdaProse=parse_adj_ebitda(text),
        eps=parse_eps(text),
        guidance=parse_guidance(text),
        margins=parse_margins(text),
        marginYoYBps=parse_margin_yoy_bps(text),
        guidanceAction=parse_guidance_action(text),
    )

    # ★ Vertical tables, as a FALLBACK only. Real wire releases carry the
    # figures in tables rather than prose -- AppLovin's is entirely tabular and
    # prose extraction returned nothing from it. Prose wins where both fire,
    # because a prose sentence states its own basis and unit explicitly.
    #
    # Run LAZILY: the scan touches every line of the body (a 36k-char release is
    # ~3,400 lines against 5 label patterns) and it measured +5 ms on the hot
    # path when run unconditionally. A release that states everything in prose
    # never needs it.
    needs_tables = (parsed['revenue'] is None
                    or 'grossMargin' not in parsed['margins']
                    or not parsed['eps']
                    or not parsed['opIncome']
                    or not parsed['adjEbitdaProse'])
    tbl = {}
    if needs_tables:
        from .tables import parse_tables
        tbl = parse_tables(text)
    parsed['tables'] = tbl
    parsed['tablesScanned'] = needs_tables

    if parsed['revenue'] is None and 'revenue' in tbl:
        parsed['revenue'] = dict(value_musd=tbl['revenue']['value'],
                                 unit_seen=tbl['revenue']['scale'],
                                 growth_pct=None, raw='table',
                                 source='table')
    for key in ('grossMargin', 'operatingMargin'):
        if key not in parsed['margins'] and key in tbl:
            parsed['margins'][key] = dict(value=tbl[key]['value'],
                                          basis=tbl[key]['basis'] or 'unknown',
                                          raw='table', source='table')
    if not parsed['opIncome'] and 'operatingIncome' in tbl:
        # ★ Basis 'unknown' when the table label did not state one -- the row
        # that demands non-GAAP will refuse it rather than assume.
        parsed['opIncome'][tbl['operatingIncome'].get('basis') or 'unknown'] = (
            dict(value_musd=tbl['operatingIncome']['value'], raw='table',
                 source='table'))
    prose_eb = parsed.pop('adjEbitdaProse', None) or {}
    pick_eb = prose_eb.get('adjusted') or prose_eb.get('unknown')
    if pick_eb:
        parsed['adjEbitda'] = dict(value_musd=pick_eb['value_musd'],
                                   raw=pick_eb['raw'], source='prose')
        parsed['adjEbitdaBasis'] = ('adjusted' if 'adjusted' in prose_eb
                                    else 'unknown')
    if 'adjEbitda' not in parsed and 'adjEbitda' in tbl:
        parsed['adjEbitda'] = dict(value_musd=tbl['adjEbitda']['value'],
                                   raw='table', source='table')
    if not parsed['eps'] and 'eps' in tbl:
        parsed['eps']['unknown'] = dict(value=tbl['eps']['value'],
                                        raw='table', source='table')
    # ★ The body is kept so a row-aware extractor can run AFTER the KPI names
    # are known. Segment rows cannot be parsed blind -- which segments matter is
    # a property of the pre-earnings card, not of the release.
    parsed['text'] = text

    parsed['fields'] = sum([
        1 if parsed['revenue'] else 0,
        len(parsed['opIncome']),
        len(parsed['eps']),
        len(parsed['guidance']),
        len(parsed['margins']),
    ])
    return parsed


# --- surprise math ------------------------------------------------------------

def pct_delta(actual, expected):
    """Percent surprise, with the model's ±300% units-mismatch suppression."""
    if actual is None or expected in (None, 0):
        return None, None
    pct = round((actual - expected) / abs(expected) * 100.0, 2)
    from .config import PCT_SUPPRESS_THRESHOLD
    if abs(pct) > PCT_SUPPRESS_THRESHOLD:
        return None, 'pctFlag: |%.0f%%| exceeds suppression threshold -- check units' % pct
    return pct, None


def verdict_for(pct, big=5.0, huge=10.0, nuke=20.0):
    """Map a percent surprise onto a renderer-recognised verdict string."""
    if pct is None:
        return 'N/A'
    if pct >= nuke:
        return 'NUKE-BEAT'
    if pct >= huge:
        return 'DEMOLISH'
    if pct >= big:
        return 'CRUSH'
    if pct > 0.5:
        return 'BEAT'
    if pct <= -nuke:
        return 'NUKE-MISS'
    if pct < -0.5:
        return 'MISS'
    return 'INLINE'
