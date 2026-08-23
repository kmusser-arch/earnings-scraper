"""ARR / RPO / cRPO — recurring-revenue balances, flows and run-rates.

★ WHY THIS IS NOT "JUST ANOTHER NUMBER"
39 rows across the library carry one of these three words and they are NOT one
metric. Matching the wrong one is worse than deferring, because every one of
these is a `★★` or `★★★` hero on the record that names it.

Six things called "ARR":
    Q3 ARR ($M)                     3525    total ARR LEVEL
    Q1 Agentforce ARR ($M)          1200    PRODUCT ARR
    Total AI ARR ($B)               3.4     CATEGORY ARR
    Q3 NGS ARR ($B)                 8.1     SEGMENT ARR
    Organic NGS ARR (ex-M&A) ($B)   6.5     segment ARR, excluding M&A
    AI Cloud ARR Run-Rate ($M)      ~70     a RUN-RATE, not a balance

And three that are not dollars at all:
    $1M+ ARR Customer Count         1519    a COUNT
    Net New $100K+ ARR Customers    +96     a COUNT
    Large Customer Adds (>$1M ARR)  779     a COUNT

★ THE COUNT ROWS ARE THE DANGEROUS ONES. GTLB's "$1M+ ARR Customer Count" has a
~160 bogey and an actual of 1,519 customers. A total-ARR parser matching it puts
1,519 against 160 and renders a spectacular false CLEAR on a ★★ hero. They are
fenced out here and never touch the dollar path -- counts belong to a count-unit
path that does not exist yet, and refusing is the correct behaviour until it does.

★ FOUR MORE DISTINCTIONS THE DATA FORCES
  RPO != cRPO      Total versus CURRENT (next 12 months). GTLB cRPO is $724.1M
                   and PANW RPO is $18.4B. Substituting one for the other is the
                   CBRS definitional mismatch, at 25x scale.
  growth != level  "cRPO Growth CC (%)" is 15.5 and "cRPO ($M)" is 724.1. Both
                   contain "cRPO". A wrong match puts 15.5 against a 730 bogey.
  flow != balance  Net New ARR is a FLOW. CRWD's is $256M against ZS's $3,525M
                   ARR balance -- same word, 14x apart.
  run-rate         "ARR Run-Rate" is an annualised projection, not a booked
                   balance. Kept separate.

Every value returned declares `unit_seen` and is normalised to $M, following the
revenue parser's value_musd contract, because the library stores these in both
$M and $B inconsistently (CBRS RPO 25400 as $M, ORCL RPO 638 as $B).
"""

import re

from .parse import _decimals, _sentences, _to_float, _to_millions, _UNIT

# ── the metric words ────────────────────────────────────────────────────────
#
# cRPO contains "RPO", but \brpo\b does NOT match inside "cRPO" -- the preceding
# 'c' is a word character, so the boundary fails. That is load-bearing: it is
# what keeps the RPO parser off a cRPO row.
_ARR = re.compile(r'\bARR\b|annual\s+recurring\s+revenue', re.I)
_CRPO = re.compile(r'\bcRPO\b|current\s+remaining\s+performance\s+obligation',
                   re.I)
_RPO = re.compile(r'\bRPO\b|(?<!current\s)remaining\s+performance\s+obligation',
                  re.I)

# A row that counts CUSTOMERS, not dollars. Fenced out entirely.
_COUNT_ROW = re.compile(
    r'customer\s+count|customers\b|\bcount\b|\badds\b|\blogos\b|\bseats\b',
    re.I)

# A row asking for a RATE, not a level.
_RATE_ROW = re.compile(r'\(%\)|\bgrowth\b|\byoy\b|\brate\s*\(', re.I)

# "Run-Rate" is its own metric: an annualised projection, not a booked balance.
_RUNRATE = re.compile(r'run[-\s]?rate', re.I)

# ★ MODIFIER SYMMETRY, in BOTH directions. Requiring only that the row's
# qualifiers appear in the sentence is half a rule: "Q3 NGS ARR ($B)" has
# qualifiers {'ngs'}, and all of them appear in "Organic NGS ARR was $6.5
# billion" -- so the plain segment row would take the ORGANIC figure, 6.5
# against its own 8.1. The broader-match trap running backwards. Each modifier
# must be present on BOTH sides or neither.
_MODIFIERS = (
    ('organic', re.compile(r'\borganic\b', re.I)),
    ('excluding', re.compile(r'\bex(?:cluding)?[-\s]', re.I)),
)

# ★ Segment abbreviations, row-name form -> the forms a release actually uses.
# Closed by design: a token with no entry here is matched literally, and a row
# whose qualifier never appears stays not-found rather than guessing.
_ALIASES = {
    'ngs': (r'ngs', r'next[-\s]?gen(?:eration)?\s+security'),
    'crpo': (r'crpo', r'current\s+remaining\s+performance\s+obligation'),
    'aws': (r'aws', r'amazon\s+web\s+services'),
    'gcp': (r'gcp', r'google\s+cloud'),
    'm365': (r'm365', r'microsoft\s+365'),
    'xsiam': (r'xsiam',),
    'agentforce': (r'agentforce',),
}


def _qualifier_pattern(token):
    """A pattern matching every spelling this project has seen for `token`."""
    forms = _ALIASES.get(token.lower())
    if not forms:
        return re.compile(r'\b%s' % re.escape(token), re.I)
    return re.compile('|'.join(r'\b(?:%s)' % f for f in forms), re.I)


_MONEY = re.compile(r'\$\s?([\d,]+(?:\.\d+)?)\s*' + _UNIT, re.I)
_FORWARD = re.compile(
    r'\b(?:expect\w*|guid\w*|outlook|forecast\w*|target\w*|anticipat\w*|'
    r'will\s+be|we\s+see)\b', re.I)

ARR, CRPO, RPO, NET_NEW_ARR, RUN_RATE = ('arr', 'crpo', 'rpo',
                                         'netNewArr', 'runRate')

# tokens that name the metric itself, so they are not "distinguishing"
_METRIC_TOKENS = frozenset((
    'arr', 'rpo', 'crpo', 'recurring', 'remaining', 'performance',
    'obligation', 'obligations', 'annual', 'annualised', 'annualized',
    'backlog', 'run', 'rate', 'new',
))


def classify_row(name):
    """Which metric a ROW is asking for, or None when it is not one of these.

    Returns one of ARR / CRPO / RPO / NET_NEW_ARR / RUN_RATE, or None. A count
    row and a rate row both return None: the first has no dollar reading, and
    the second is a percentage handled by the growth path.
    """
    n = name or ''
    if not (_ARR.search(n) or _CRPO.search(n) or _RPO.search(n)):
        return None
    if _COUNT_ROW.search(n):
        return None            # ★ a count, never a dollar figure
    # ★ RUN-RATE IS TESTED FIRST. "AI Cloud ARR Run-Rate ($M)" contains the word
    # "Rate" followed by a paren, so the growth-rate pattern matched it and
    # refused a row that is a dollar LEVEL. A run-rate is annualised dollars,
    # not a percentage.
    if _RUNRATE.search(n):
        return RUN_RATE
    if _RATE_ROW.search(n):
        return None            # a growth rate, not a balance
    if _CRPO.search(n):
        return CRPO
    if _RPO.search(n):
        return RPO
    if re.search(r'\bnet\s+new\b', n, re.I):
        return NET_NEW_ARR
    return ARR


def refusal_reason(name):
    """Why a row carrying one of these words is NOT gradeable on the dollar path."""
    n = name or ''
    if _COUNT_ROW.search(n):
        return ('counts CUSTOMERS, not dollars — refused rather than compared '
                'against a dollar bogey. GTLB\'s "$1M+ ARR Customer Count" has '
                'an actual of 1,519 customers against a ~160 bogey; a dollar '
                'parser matching it renders a false CLEAR on a hero row.')
    if _RATE_ROW.search(n):
        return ('asks for a GROWTH RATE, not a level — "cRPO Growth CC (%)" is '
                '15.5 while "cRPO ($M)" is 724.1, and both contain "cRPO"')
    return None


_PATTERNS = {
    ARR: _ARR, CRPO: _CRPO, RPO: _RPO, NET_NEW_ARR: _ARR, RUN_RATE: _ARR,
}


def qualifiers(name, row_qualifiers):
    """The row's distinguishing tokens, minus the words naming the metric.

    "Q3 NGS ARR ($B)" -> {'ngs'};  "Q3 ARR ($M)" -> set().
    "Organic NGS ARR (ex-M&A) ($B)" -> {'organic', 'ngs', 'ex'}.
    """
    return set(row_qualifiers(name or '')) - _METRIC_TOKENS


def parse_balance(text, metric, quals, want_forward=False, row_name=''):
    """One balance, matched on the metric word AND every distinguishing token.

    Returns {value_musd, unit_seen, raw, source, decimals, stated} or None, or a
    dict with `ambiguous` set when two different values match. There is no
    broader fallback: a qualified row is filled only from a sentence carrying
    all of its qualifiers, the same discipline segment revenue uses.
    """
    pat = _PATTERNS.get(metric)
    if pat is None:
        return None
    qpats = [_qualifier_pattern(t) for t in sorted(quals)]
    net_new = metric == NET_NEW_ARR
    run_rate = metric == RUN_RATE

    hits = []
    for sent in _sentences(text):
        if not pat.search(sent):
            continue
        # ★ cRPO and RPO are different metrics. A cRPO sentence must not fill an
        # RPO row, and the reverse holds too.
        if metric == RPO and _CRPO.search(sent) and not _RPO.search(
                _CRPO.sub(' ', sent)):
            continue
        if metric == CRPO and not _CRPO.search(sent):
            continue
        if not all(q.search(sent) for q in qpats):
            continue
        # flow vs balance, and run-rate vs balance, both cut both ways
        has_net_new = bool(re.search(r'\bnet\s+new\b', sent, re.I))
        has_run_rate = bool(_RUNRATE.search(sent))
        if net_new != has_net_new:
            continue
        if run_rate != has_run_rate:
            continue
        # ★ `mpat`, not `pat` -- reusing the name here shadows the METRIC
        # pattern inside the comprehension, which is the kind of quiet aliasing
        # that made the shadowed `evidence` bug in count_flags.
        if any(bool(mpat.search(sent)) != bool(mpat.search(row_name or ''))
               for _label, mpat in _MODIFIERS):
            continue
        fwd = bool(_FORWARD.search(sent))
        if fwd != bool(want_forward):
            continue
        m = _MONEY.search(sent)
        if not m:
            continue
        val = _to_millions(m.group(1), m.group(2))
        if val is None:
            continue
        hits.append((val, m.group(1), (m.group(2) or '').lower(), sent))

    if not hits:
        return None
    distinct = {round(h[0], 6) for h in hits}
    if len(distinct) > 1:
        return dict(value_musd=None, unit_seen=None, source='AMBIGUOUS',
                    raw='; '.join(h[3][:70] for h in hits[:3]),
                    decimals=None, stated=None, ambiguous=sorted(distinct))
    val, num, unit, sent = hits[0]
    return dict(value_musd=val, unit_seen=unit, source='prose (%s)' % metric,
                raw=sent[:120], decimals=_decimals(num), stated=_to_float(num),
                ambiguous=None)
