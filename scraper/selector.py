# -*- coding: utf-8 -*-
r"""THE SELECTOR: which ~10 of the parser's ~1000 rows this card wants.

    API -> parser (dumb, universal) -> SELECTOR -> ~10 rows -> flash

★★★★★ IT NEVER PARSES. It filters, labels, and REPORTS MISSES. Every
number it emits came out of the parser with the issuer's own words on it.

★★★ AND IT MATCHES ON (LABEL, PERIOD) TOGETHER. Intel prints
'Non-GAAP gross margin percentage' in the current-quarter actuals AND in
the Q4 outlook -- identical string, different number, opposite meaning.
Matching on the label alone returns whichever came first, which is a coin
flip on a priority-1 row.

★★ CONFIG IS READ LIVE, EVERY CALL. ticker-profiles.json parses in ~1.5ms,
so there is no export, no cache and no regeneration step -- a second copy
of the truth is a copy that drifts. The repo rule is that frameworks live
in the data and are loaded at runtime.

NO TICKER SYMBOL APPEARS IN THIS MODULE, pinned by a test.
"""

import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

#: the upstream source of truth, owned by the pre-earnings build
PROFILES_PATH = os.environ.get('TICKER_PROFILES') or os.path.join(
    'C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude', 'Projects',
    'earnings Model', 'ticker-profiles.json')
ALIASES_PATH = os.path.join(HERE, 'universal_aliases.json')

_WS = re.compile(r'\s+')
#: a trailing footnote: '…percentage1', '…flow -- TTM (1)', '…Group (CCPG)2'
_FOOTNOTE = re.compile(r'(?:\s*\(\d{1,2}\)|\s*[\d*†‡]{1,2})\s*$')
_BASIS = re.compile(r'^(non-gaap|gaap|u\.s\. gaap|adjusted)\s+', re.I)

#: the ONLY fuzzy step, and it is safe because the PERIOD is never
#: inferred from text -- it comes from the hero's explicit appliesTo.
_CANON = (
    ('revenue guide', 'revenue'), ('rev guide', 'revenue'),
    ('net sales', 'revenue'), ('revenue', 'revenue'),
    ('gross margin', 'grossMargin'), (' gm', 'grossMargin'),
    ('earnings per share', 'eps'), ('eps', 'eps'),
    ('operating income', 'operatingIncome'), ('ebit', 'operatingIncome'),
    ('operating margin', 'operatingMargin'),
    ('capital expenditure', 'capex'), ('capex', 'capex'),
    ('free cash flow', 'freeCashFlow'), ('fcf', 'freeCashFlow'),
    ('operating cash flow', 'operatingCashFlow'),
    ('net income', 'netIncome'),
)

#: parser period/table text -> the hero's appliesTo vocabulary
#: ENDING vs ENDED IS THE WHOLE SIGNAL, and the vocabulary below could not
#: see it: the needle is 'three months', which matches 'Three Months Ended'
#: and 'Three Months Ending' alike. 74 rows across 8 documents -- KLAC,
#: AKAM, NOW, DELL -- offered a GUIDANCE column to fill a reported-quarter
#: hero, which is non-negotiable 2 running backwards. ('quarter ended' does
#: carry the tense, which is why 'Quarter Ending December 31, 2026' was
#: already correct while 'Three Months Ending July 31, 2026' was not.)
#:
#: ENUMERATED, NOT PATCHED. Every <word>+END* pair in the corpus's 1,023
#: distinct period strings was listed before this was written, because
#: adding only the spelling that bit us is how this family produces five
#: appearances instead of one. The forward forms are 'months ending',
#: 'year ending' and the CONCATENATED 'endingjune' / 'endingseptember' --
#: EDGAR drops the space, the same defect _despace exists for -- so the
#: pattern deliberately carries no trailing word boundary.
#:
#: 'low end' and 'high end' are Akamai's guide-range columns. They are the
#: word END, not ENDING, and \bending cannot reach them.
_FORWARD = re.compile(r'(?i)\bending')

#: WHICH forward period. 'Twelve Months Ending December 31, 2026' is
#: ServiceNow's FULL YEAR and it never says the word "year"; read as a
#: next-quarter guide it files an annual number under Q+1.
_FWD_YEAR = re.compile(r'(?i)\b(fiscal\s*)?years?\b|\bfull\s*year\b'
                       r'|\btwelve\s*months\b')

_PERIOD = (
    # ★★★★ TABLE-TITLE NOUNS ONLY. Adobe heads its guidance table
    # 'financial targets and assumptions' -- the word is TARGETS, and with
    # only outlook/guidance/forecast in the vocabulary that whole table read
    # as the current quarter and both Adobe guidance heroes were rejected
    # with their labels sitting right there. Guidance is 60% of the
    # scorecard weight, so a term missing here is expensive in one
    # direction and poisonous in the other.
    #
    # MEASURED over the fixture set, 2,384 rows: 'targets' moves 34 rows,
    # ALL of them from None, and NOT ONE off currentQuarter. The dangerous
    # direction is empty.
    #
    # ★★ THE NARRATIVE VERBS ARE DELIBERATELY ABSENT -- 'expects',
    # 'we expect', 'anticipate', 'expected to be'. A table heading here is
    # the text immediately BEFORE the table, usually the tail of a
    # paragraph, so a sentence saying 'we expect' above a CURRENT-QUARTER
    # statement would reclassify the whole table as guidance. Oracle does
    # say 'Total Cloud revenue is expected to grow' -- and that is a
    # SENTENCE, which belongs to the prose channel. Nouns title tables;
    # verbs make sentences.
    ('outlook', 'nextQGuidance'), ('guidance', 'nextQGuidance'),
    ('forecast', 'nextQGuidance'),
    ('targets', 'nextQGuidance'), ('target', 'nextQGuidance'),
    ('twelve months', 'TTM'), ('ttm', 'TTM'),
    ('trailing twelve', 'TTM'),
    ('three months', 'currentQuarter'), ('quarter ended', 'currentQuarter'),
    ('nine months', 'nineMonths'), ('six months', 'sixMonths'),
    # a FULL-YEAR column is not a next-quarter guide, even inside a table
    # headed 'targets'
    ('fiscal year', 'fyGuidance'), ('full year', 'fyGuidance'),
    ('full-year', 'fyGuidance'), ('year ending', 'fyGuidance'),
)


#: ★★★ EVERY DASH IS THE SAME DASH. Intel prints 'Earnings per share
#: attributable to Intel—diluted' with an EM DASH; the alias list writes it
#: with a hyphen. Without folding, that priority-1 EPS row matches nothing
#: and reports NOT FOUND against a document that plainly contains it.
_DASHES = dict((ord(c), u'-') for c in u'‐‑‒–—'
               u'―−')


def norm(s):
    """Lowercased, whitespace-collapsed, dashes folded, footnote removed."""
    t = _WS.sub(' ', (s or '')).strip().translate(_DASHES)
    t = _FOOTNOTE.sub('', t)
    return t.lower().strip()


def basis_of(word):
    """Any spelling of a basis -> GAAP | NON_GAAP | None.

    ★★★ THE CONFIG AND THE CODE SPELL IT DIFFERENTLY. The label maps
    are hand-written and say "nonGAAP"; the parser derives "NON_GAAP" from
    the document. Comparing them raw made two priority-1 Intel gross-margin
    rows report NOT FOUND the moment their map landed -- the map MADE them
    worse, which is the hardest kind of regression to see.
    """
    raw = str(word or '').strip()
    if not raw:
        return None
    # ★★★★ A BASIS IS A TOKEN, NOT A SENTENCE, AND THE FIELD IS STRUCTURAL
    # BY ITS CONTENT. Adobe's map carries
    #   "basis": "★ GAAP row is 'Diluted net income per share' — same word..."
    # which prefix-matched to GAAP and forced the GAAP row: 4.62 where the
    # hero asked for the ADJUSTED figure, 6.13. Prose in a token field must
    # be REFUSED, never mined for the first word that looks right.
    if len(raw) > 24:
        return None
    w = re.sub(r'[^a-z]', '', raw.lower())
    if w in ('nongaap', 'nongap', 'adjusted', 'adj', 'excldeferrals'):
        return 'NON_GAAP'
    if w in ('gaap', 'usgaap', 'reported'):
        return 'GAAP'
    return None


def split_basis(label):
    """('GAAP'|'NON_GAAP'|None, label without the prefix)."""
    t = _WS.sub(' ', (label or '')).strip()
    m = _BASIS.match(t)
    if not m:
        return None, t
    word = m.group(1).lower()
    rest = t[m.end():]
    if word.startswith('non'):
        return 'NON_GAAP', rest
    if word == 'adjusted':
        return 'NON_GAAP', rest
    return 'GAAP', rest


def load_profiles(path=None):
    p = path or PROFILES_PATH
    with io.open(p, encoding='utf-8') as fh:
        doc = json.load(fh)
    return doc.get('profiles') or {}, os.path.getmtime(p)


def load_aliases(path=None):
    with io.open(path or ALIASES_PATH, encoding='utf-8') as fh:
        doc = json.load(fh)
    out = {}
    for metric, labels in doc.items():
        if metric.startswith('_'):
            continue
        for rank, lab in enumerate(labels):
            _b, core = split_basis(lab)
            out.setdefault(norm(core), []).append((metric, rank))
    return out


def alias_rank(aliases, label, metric):
    """Position of this label in its metric's list. LOWER IS BETTER.

    ★★★ THE LIST IS WRITTEN IN PREFERENCE ORDER AND THAT IS LOAD-BEARING.
    'Total net sales' is listed before 'Net sales' because Amazon prints
    BOTH -- the consolidated total and one per segment. Without the order a
    segment's 112,852 answers a request for consolidated revenue with the
    right label, the right period and the WRONG FACT. Intel is the same
    shape: 'Net revenue 16,513' outranks the summary's 'Revenue ($B) 16.5'.
    """
    _b, core = split_basis(label or '')
    for m, rank in aliases.get(norm(core), ()):
        if m == metric:
            return rank
    return 99


def metrics_for(aliases, label):
    _b, core = split_basis(label or '')
    return [m for m, _r in aliases.get(norm(core), ())]


#: decoration that says WHEN or HOW, never WHAT
_DECOR = re.compile(
    r"(?i)\b(current|next|last|prior|this|the|a|of|for|on|in|at|per|y/y|yoy|"
    r"q/q|qoq|quarter|quarterly|qtr|year|yearly|annual|fy|cy|ttm|trailing|"
    r"twelve|months?|guide|guidance|outlook|forecast|actual|actuals|reported|"
    r"gaap|non|adjusted|adj|inverted|approximately|approx|about)\b")
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_YEARRE = re.compile(r"\b(19|20)(\d{2})\b")


def _bare(name):
    """A hero name reduced to the metric words it is actually about."""
    t = norm(name)
    t = t.split(u'—')[0].split(' - ')[0]
    t = re.sub(r"\([^)]*\)", ' ', t)
    t = _DECOR.sub(' ', t)
    t = _PUNCT.sub(' ', t)
    # ★★ THE LEFTOVER TOKENS ARE DECORATION TOO. 'Next-Q gross margin
    # guide' reduced to 'q gross margin' and matched nothing -- a stray 'q'
    # from the hyphen, and 'FY+1 capex' left a bare '1'. Both reported NOT
    # FOUND against documents that plainly carry the figure.
    t = re.sub(r'\b(q|fy|cy|h|yr|\d+)\b', ' ', t)
    return _WS.sub(' ', t).strip()


def canonical(hero_name):
    """The universal metric this hero IS, or None.

    ★★★★ CONSERVATIVE ON PURPOSE. The first cut fired whenever the name
    CONTAINED the word, so 'AWS revenue growth y/y (%)' resolved to
    `revenue` and matched 'Total net sales' -- a segment growth RATE
    answered with a consolidated dollar TOTAL. That is exactly the
    plausible-but-wrong match the spec forbids, and it would have printed
    201,944 against a hero asking for a percentage.

    So the name must REDUCE to the metric phrase once period, unit and
    basis decoration is stripped. Anything left over -- a segment name, a
    'growth', a 'per customer' -- means this is a ticker-specific hero,
    which is hand-written or NOT FOUND, never inferred.
    """
    bare = _bare(hero_name)
    if not bare:
        return None
    for needle, metric in _CANON:
        n = needle.strip()
        if bare == n or bare == n + 's':
            return metric
    return None


_QNUM = re.compile(r'(?i)\bq([1-4])\b')
_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june',
           'july', 'august', 'september', 'october', 'november',
           'december']
#: ★ ABBREVIATIONS COUNT. Intel writes 'Sep 26, 2026'. Matching only full
#: month names left that column with no quarter at all, so the summary
#: table's 'GAAP Q3 2026' outranked the statement and returned 16.5 where
#: the answer is 16,513.
_MON3 = [m[:3] for m in _MONTHS]
#: ★★ NO LEADING WORD BOUNDARY -- EDGAR CONCATENATES. Amazon's column reads
#: 'Three Months EndedSeptember 30, 2026' as ONE token, so a \b before the
#: month matched nothing: the CONSOLIDATED row scored quarter 0 while every
#: segment row scored 3, and the company line lost to its own North America
#: segment on a missing space.
#:
#: Anchored on the DAY NUMBER instead, which also stops 'prices may
#: increase' reading as a May date -- it was scoring quarter 2.
_MONTHRE = re.compile(
    r'(?i)(' + '|'.join(_MON3) + r')[a-z]*\.?\s*(?=\d{1,2}\b)')


def _recency(row):
    """(year, quarter) -- the most recent column wins among same-class ties.

    ★ 'Three Months Ended Sep 26, 2026' and 'Three Months Ended Sep 27,
    2025' are BOTH the current-quarter class. Without a year the prior-year
    column is as likely to be returned as the reported one.

    ★★★ AND THE QUARTER MATTERS TOO. Amazon's supplemental table is a TREND
    across Q1 2026 | Q2 2026 | Q3 2026 | Q2 2025 | Q3 2025. Ranking on the
    year alone ties the three 2026 columns and returns Q1 -- a figure two
    quarters stale, in the right units, with the right label, on the right
    row. Nothing downstream could catch that.
    """
    # THE COLUMN ONLY. The `table` field is NOT a caption -- EDGAR hands
    # back the text immediately before the <table>, which is routinely the
    # tail of the preceding paragraph. Dell's reads 'r over year, and
    # non-GAAP diluted EPS to be $17.90 at the midp...', the tail of a
    # FORWARD GUIDANCE sentence carrying fiscal 2027. Pooling it with the
    # column gave every silent column a year the document never granted
    # it, and Dell's unheaded "Change" column -- (0,0) on its own -- took
    # (2027,0) from that prose and beat the dollar column's explicit
    # (2026,2). Net revenue came back as 88%.
    #
    # Alphabet is the same defect in the other direction: its caption says
    # 'for the quarters ended September 30, 2025 AND 2026', so the 2025
    # column inherited 2026, tied with the real one, and document order
    # handed back prior-year revenue, operating income and EPS.
    #
    # A column that names no period scores (0, 0) and loses to any column
    # that names itself. Where NO column names a period they all tie and
    # document order decides, exactly as before.
    #
    # MEASURED over 111 corpus documents + 6 wire fixtures: 57 selected
    # answers change, 0.85%, 9 documents, every one read by hand and every
    # one a correction off a stale column -- prior-year, prior-quarter, or
    # a percent-of-revenue column standing in for dollars.
    hay = row.get('period') or ''
    ys = _YEARRE.findall(hay)
    year = max((int(a + b) for a, b in ys), default=0)
    qs = [int(q) for q in _QNUM.findall(hay)]
    # ★★★★ A DATE IS A QUARTER TOO, AND MOST ISSUERS WRITE ONLY THE DATE.
    # Adobe heads its columns 'Three Months Ended August 28, 2026' and
    # 'Three Months Ended May 29, 2026' -- same year, no Q token, so both
    # scored (2026, 0) and the PRIOR quarter won on a tiebreak. That
    # returned 4.25 for a current-quarter hero whose answer is 6.13.
    #
    # Fourth appearance of this one term: Q1-of-a-six-column-trend, the
    # prior-year column, the wider period in the --labels dump, and now
    # the prior quarter by month. Every time the cell was internally
    # consistent and only the SELECTION was wrong.
    if not qs:
        qs = [(_MON3.index(m.lower()[:3]) // 3) + 1
              for m in _MONTHRE.findall(hay) if m.lower()[:3] in _MON3]
    return (year, max(qs, default=0))


def range_ends(raw):
    """(low, high) for a printed range cell, else (None, None).

    EXTRACTION, NOT DERIVATION. The two numbers are both on the page; the
    midpoint is on neither. cells.is_range already decides what counts as
    a range -- this reuses that judgement rather than writing a second,
    quietly different one.
    """
    if not cells.is_range(raw):
        return None, None
    nums = re.findall(r'-?[\d,]+(?:\.\d+)?', str(raw))
    if len(nums) != 2:
        return None, None
    try:
        return float(nums[0].replace(',', '')), float(nums[1].replace(',', ''))
    except ValueError:
        return None, None


def _precision(row):
    """How many significant digits the printed figure carries.

    ★★ THE SAME METRIC IS OFTEN PRINTED TWICE AT DIFFERENT PRECISION.
    Intel's summary says 'Revenue ($B) $16.5' and its statement says 'Net
    revenue 16,513'; both are tables, both the reported quarter. The
    unrounded one is the answer -- it is the figure the company filed, and
    the other is a display rounding of it.
    """
    digits = re.sub(r'[^0-9]', '', (row.get('raw') or ''))
    return len(digits.lstrip('0'))


#: 'Q3 2026', 'Q3 2026 Cash Flows and Shares' -- a quarter named outright
_QTR = re.compile(r'(?i)\bq[1-4]\s*\'?\d{2,4}\b')


def period_class(table, period, label=None):
    """currentQuarter / nextQGuidance / TTM / ... from label, table, column.

    ★ THE TABLE HEADING COUNTS. Intel's Q4 revenue guide sits in a column
    headed 'GAAP' inside a table headed 'Business Outlook'; the column
    alone says nothing about the period.

    ★★★ AND SO DOES THE LABEL, WHICH IS WHERE AMAZON PUTS THE PERIOD. Its
    supplemental table is headed 'Q3 2026 Cash Flows and Shares' and the
    TTM-ness lives in the ROW: 'Free cash flow -- TTM', 'Purchases of
    property and equipment … -- TTM'. Reading only the column header
    classifies those as the quarter and answers a TTM question with a
    quarterly number -- the same magnitude, a different fact.
    """
    lab = norm(label or '')
    if lab:
        for needle in ('-- ttm', 'ttm', 'trailing twelve'):
            if needle in lab:
                return 'TTM'
    # ★★★★ THE COLUMN BEFORE THE TABLE. The column header describes the
    # COLUMN; the table heading describes the table, and when they
    # disagree the column is the narrower claim.
    #
    # Adobe's targets table carries 'Fiscal Year 2026 Low'. Scanning table
    # and column together let 'targets' match first, so an FY figure --
    # 24.45 -- resolved as a NEXT-QUARTER guide and validated clean. That
    # is a wrong number wearing a PASS, which is worse than the FAIL it
    # replaced.
    # A FORWARD PERIOD IS NOT A NARROWER READING OF A REPORTED ONE, so this
    # runs BEFORE the vocabulary rather than inside it -- 'three months'
    # would otherwise match first and claim the column for the quarter.
    # Column before table here too: a guidance column inside a results
    # table is guidance, and a results column is not reclassified by the
    # guidance table it happens to sit in.
    for hay in (norm(period or ''), norm(table or '')):
        if _FORWARD.search(hay):
            return 'fyGuidance' if _FWD_YEAR.search(hay) else 'nextQGuidance'
    for hay in (norm(period or ''), norm(table or '')):
        for needle, cls in _PERIOD:
            if needle in hay:
                return cls
    # a bare 'Q3 2026' heading is the reported quarter
    # ★ CHECKED AGAINST BOTH AGAIN: the column-first loop above leaves
    # `hay` bound to the TABLE, so testing it alone lost every period that
    # says only 'Q3 2026' -- which is Amazon's whole supplemental table.
    for hay2 in (norm(period or ''), norm(table or '')):
        if _QTR.search(hay2):
            return 'currentQuarter'
    return None


def unit_class(spec):
    """CURRENCY | PERCENT | COUNT from a declared unit or a printed figure.

    ★★★★ A CLASS MISMATCH IS A NON-MATCH, NEVER A SCALE WARNING. Adobe
    discloses AI-first ARR only as a GROWTH RATE -- 'grew more than 150%
    year over year' -- while the hero declares ($M). On bag-of-words that
    row and 'Digital Media ARR ($B)' bound to each other across a 1000x
    unit disagreement, and a percentage answered a dollar hero.
    Percent and currency are not the same quantity at a different scale;
    they are different quantities, and no amount of scaling reconciles
    them.
    """
    u = str(spec or '').strip()
    if not u:
        return None
    if u.endswith('%') or u == 'pct' or u == 'ppt':
        return 'PERCENT'
    if u[0] in '$€£¥' or u.upper() in ('USD', 'EUR', 'GBP'):
        return 'CURRENCY'
    if u.lower() in ('count', 'customers', 'users', 'subs', 'm', 'b', 'k'):
        return 'COUNT'
    return None


def raw_class(raw):
    """The class a PRINTED figure belongs to, from how it is written."""
    t = str(raw or '').strip()
    if not t:
        return None
    if t.endswith('%') or '%' in t:
        return 'PERCENT'
    if any(c in t for c in '$€£¥'):
        return 'CURRENCY'
    return None


def _pct_context(row):
    """Does anything around this cell say the column is a percentage?"""
    hay = norm('%s %s %s' % (row.get('label') or '', row.get('period') or '',
                             row.get('section') or ''))
    return ('%' in hay or 'percent' in hay or 'margin %' in hay
            or 'rate' in hay or ' ppt' in hay or 'basis points' in hay)


def _plausible(value, unit):
    """RULE 4 -- is this magnitude believable for the hero's unit?"""
    if value is None or not unit:
        return True
    u = str(unit).strip()
    if u == '%':
        return -200.0 <= value <= 200.0
    if u == '$B':
        return abs(value) < 10000.0
    if u == '$M':
        return abs(value) < 10000000.0
    return True


def _hero_fields(h):
    if isinstance(h, dict):
        return (h.get('name') or '', h.get('priority'),
                h.get('appliesTo') or '', h.get('unit') or '',
                bool(h.get('inverted')))
    return (str(h), None, '', '', False)


def _explicit_period(label, period_cls):
    """Does the LABEL itself name the period being asked for?

    ★★ Amazon prints capex twice for the trailing twelve months: once as
    'Purchases of property and equipment' in the cash-flow statement under
    a 'Twelve Months Ended' column, and once as the same label plus
    '-- TTM' in the supplemental table. Both are TTM; only one SAYS so, and
    that is the one the card means.
    """
    lab = norm(label or '')
    if period_cls == 'TTM':
        return 1 if ('ttm' in lab or 'trailing twelve' in lab) else 0
    return 0


def _repeats(rows):
    """(table, period, label) -> how many times it occurs.

    ★★★ A LABEL REPEATED WITHIN ONE TABLE AND PERIOD IS A SEGMENT ROW.
    Intel's segment table prints 'Revenue' four times for the same quarter
    -- once per business unit -- while the consolidated statement prints
    'Net revenue' once. Without this, a $15.4B business unit answers a
    request for the $16.5B company, with the right label and period.
    """
    counts = {}
    for r in rows or []:
        k = (r.get('table'), r.get('period'), norm(r.get('label')))
        counts[k] = counts.get(k, 0) + 1
    return counts


def _rank_key(row, metric, aliases, period_cls, counts):
    k = (row.get('table'), row.get('period'), norm(row.get('label')))
    # ★★★★ RECENCY IS THE HIGHEST-PRIORITY TERM, NOT A TIEBREAK -- YEAR AND
    # QUARTER TOGETHER. With quarter ranked last, Adobe's May column beat
    # its August column because 'Three Months Ended May 29,2026' is three
    # characters SHORTER than the August header and period-length outranked
    # it. A current-quarter hero answered with the prior quarter, on a
    # length coincidence.
    return (_recency(row)[0], _recency(row)[1],
            # ★★★★ ASKED FOR THE COMPANY, NOT A UNIT. A row sitting in a
            # segment SECTION is a business unit's figure; the
            # consolidated line sits in none. Amazon's 'Net sales' under
            # 'North America Segment:' beat 'Total net sales' because its
            # period header is shorter -- 112,852 answering a request for
            # 201,944, on a length coincidence.
            #
            # Neutral when the hero DECLARES a segmentContext, because the
            # section filter has already restricted the candidates to it.
            0 if (row.get('section') or '') else 1,
            _explicit_period(row.get('label'), period_cls),
            -counts.get(k, 1),
            _precision(row),
            # ★★★ A QUALIFIED PERIOD HEADER IS A SEGMENT COLUMN. Intel's
            # consolidated line sits under 'Three Months Ended Sep 26,
            # 2026'; its business units sit under that SAME date plus a
            # unit name -- 'Intel Products CCPG1', 'Intel Products DCAI'.
            # Each is unique, so counting repeats does not separate them,
            # but the extra words do. Ranked BELOW precision deliberately:
            # the summary's 'Revenue ($B)' under a short 'GAAP Q3 2026'
            # header would otherwise beat the statement's 16,513.
            -len(row.get('period') or ''),
            -alias_rank(aliases, row.get('label'), metric))


def resolve(parser_rows, metric, period=None, basis=None, aliases=None):
    """Every row matching (metric, period, basis), most recent first.

    ★★★ THE PERIOD IS PART OF THE KEY, NOT A FILTER APPLIED AFTERWARDS.
    Intel prints 'Non-GAAP gross margin percentage' in the Q3 actuals AND
    in the Q4 outlook. Same string, different number, opposite meaning. A
    lookup by label alone returns whichever came first.

    ★★ AND BASIS NEVER FALLS BACK (rule 5). Asking for non-GAAP on a
    release that carries only the GAAP row returns NOTHING. Substituting
    would answer the question that was not asked, with a number that looks
    right.
    """
    aliases = load_aliases() if aliases is None else aliases
    out = []
    for row in parser_rows or []:
        rb, core = split_basis(row.get('label') or '')
        if metric not in metrics_for(aliases, row.get('label')):
            continue
        if period:
            pc = period_class(row.get('table'), row.get('period'),
                              row.get('label'))
            if pc != period:
                continue
        if basis:
            if rb != basis:
                continue
        out.append(row)
    counts = _repeats(parser_rows)
    out.sort(key=lambda r: _rank_key(r, metric, aliases, period, counts),
             reverse=True)
    return out


def _prose_metric(hero_name, prose_rows):
    """The prose metric this hero names, or None.

    ★ LOOSER THAN canonical() ON PURPOSE, AND ONLY HERE. The prose channel
    is already fenced to a guidance SECTION, so the candidate set is a
    handful of sentences rather than a thousand table cells. 'FY+1 capex
    framing ($B)' reduces to 'capex framing', which canonical() correctly
    refuses -- but among three guidance bullets, matching the metric word
    is safe where it would not be against the whole document.
    """
    bare = _bare(hero_name)
    if not bare:
        return None
    direct = canonical(hero_name)
    if direct:
        return direct
    seen = set(r.get('metric') for r in (prose_rows or []))
    for needle, metric in _CANON:
        n = needle.strip()
        if metric in seen and n in bare:
            return metric
    return None


def select(parser_rows, ticker, profiles=None, aliases=None,
           prose_rows=None):
    """{found, notInRelease, config} -- reported numbers and nothing else.

    ★★★ NO THIRD CATEGORY. A hero is in the release or it is not. Earlier
    versions sorted misses into CALL-ONLY, PROSE CHANNEL, NOT GRADEABLE and
    NOT FOUND, which is four ways of saying the same thing plus an opinion
    about why.
    """
    if profiles is None:
        profiles, mtime = load_profiles()
    else:
        mtime = None
    aliases = load_aliases() if aliases is None else aliases
    prose_rows = prose_rows or []
    prof = (profiles or {}).get(str(ticker or '').upper())

    out = {'found': [], 'notInRelease': [], 'overflow': [],
           'config': {'tickers': len(profiles or {}),
                      'heroRows': sum(len(p.get('heroKPIs') or [])
                                      for p in (profiles or {}).values()),
                      'mtime': mtime}}
    if not prof:
        out['overflow'] = [dict(r, noProfile=True) for r in parser_rows]
        out['noProfile'] = True
        out['heroCount'] = 0
        return out

    dlm = prof.get('documentLabelMap') or {}
    segs = ((prof.get('documentLabelMapSegments') or {}).get('labels')) or {}
    heroes = prof.get('heroKPIs') or []
    out['heroCount'] = len(heroes)
    claimed = set()

    for _hero_i, hero in enumerate(heroes):
        name, prio, applies, unit, _inv = _hero_fields(hero)
        # ★ appliesTo AND PROFILE ORDER TRAVEL WITH EVERY HERO,
        # including the ones that do not resolve. A hero that is not
        # in the release still belongs to a section, and an FY block
        # that is empty BECAUSE nothing resolved is a real signal --
        # which it cannot be if the row has nowhere to appear.
        base = {'hero': name, 'priority': prio,
                'appliesTo': applies or '', 'order': _hero_i}
        labels, seg_ctx, channel, unverified = [], None, None, False
        want_basis = None
        entry = dlm.get(name)
        if isinstance(entry, dict):
            labels = [str(x) for x in (entry.get('documentLabels') or [])]
            want_basis = basis_of(entry.get('basis'))
            seg_ctx = entry.get('segmentContext')
            channel = entry.get('channel')
            unverified = bool(entry.get('needsVerification'))
            if entry.get('period'):
                applies = entry['period']
            if entry.get('unit'):
                unit = entry['unit']
        if not labels:
            for short, sentry in segs.items():
                if short and norm(short) in norm(name):
                    labels = [str(x) for x in
                              ((sentry or {}).get('documentLabels') or [])]
                    break

        low = norm(name)
        if not want_basis:
            if 'non-gaap' in low:
                want_basis = 'NON_GAAP'
            elif 'gaap' in low:
                want_basis = 'GAAP'

        # ── the PROSE channel, where the issuer states it in a sentence ──
        if channel == 'prose' or not labels:
            pm = _prose_metric(name, prose_rows)
            hit = next((p for p in prose_rows if p.get('metric') == pm), None)
            # ★★★★ A DECLARED CHANNEL IS A DECLARATION, NOT A
            # PREFERENCE. channel:'prose' on Apple's Gross Margin (%) says
            # the percent exists ONLY in a sentence -- the table label
            # 'Gross margin' is a DOLLAR line, 54,770. Falling through to
            # the table when the prose lookup found nothing returned
            # 54,770 as a gross MARGIN: a 54,770% margin, resolved,
            # displayed, and counted as found.
            if hit is None and channel == 'prose':
                out['notInRelease'].append(dict(base, channel='prose'))
                continue
            if hit is not None:
                out['found'].append(dict(
                    base, label=hit.get('label') or pm, value=hit.get('value'),
                    low=hit.get('low'), high=hit.get('high'),
                    raw=hit.get('raw'), period=hit.get('period'),
                    basis=None, segment=None, channel='prose',
                    sourceSentence=hit.get('sourceSentence')))
                continue
        # ★★★ WHY A ROW IS BLANK IS NOT ALL ONE THING. 'call' means ask the
        # transcript. 'derived' means the INPUTS are printed but the figure
        # is not -- Apple prints Services at 30,739 and 27,423 and never
        # the +12.1%. Collapsing them loses the difference between a number
        # that exists nowhere and one that is two columns and a division
        # away. Neither is computed here; the parser reports what was
        # printed, and the display says which kind of absence this is.
        if channel in ('call', 'derived'):
            out['notInRelease'].append(dict(base, channel=channel))
            continue

        wanted = set()
        for x in labels:
            xb, xcore = split_basis(x)
            wanted.add(norm(xcore))
            want_basis = want_basis or xb
        metric = None if wanted else canonical(name)
        if not wanted and not metric:
            out['notInRelease'].append(base)
            continue

        found = []
        for i, row in enumerate(parser_rows):
            rb, rcore = split_basis(row.get('label') or '')
            key = norm(rcore)
            if wanted:
                if key not in wanted:
                    continue
            elif metric not in metrics_for(aliases, row.get('label')):
                continue
            pc = period_class(row.get('table'), row.get('period'),
                              row.get('label'))
            if applies and pc and pc != applies:
                continue
            if applies and not pc and applies != 'currentQuarter':
                continue
            if want_basis and rb and rb != want_basis:
                continue
            if want_basis and not rb and want_basis == 'NON_GAAP':
                continue
            if seg_ctx and norm(seg_ctx) not in norm(row.get('section')):
                continue
            # ★★★ UNIT CLASS, BEFORE ANY SCALE REASONING. A $M hero does
            # not bind to a % candidate at any magnitude.
            hc, rc = unit_class(unit), raw_class(row.get('raw'))
            if hc and rc and hc != rc:
                continue
            # ★★★ AND AN UNMARKED CELL IS NOT A PERCENT. The guard above
            # only fires when BOTH sides declare a class, and Apple prints
            # bare numbers inside a $M table -- no '$' in the cell and no
            # '%' either -- so raw_class returned None and 54,770 sailed
            # through to a % hero. A percentage is PRINTED as one: with a
            # % sign, or in a column that says so.
            if hc == 'PERCENT' and rc is None and not _pct_context(row):
                continue
            found.append((i, row))

        if not found:
            out['notInRelease'].append(base)
            continue
        _c = _repeats(parser_rows)
        found.sort(key=lambda ir: _rank_key(
            ir[1], metric or '', aliases, applies, _c), reverse=True)
        best = found[0][1]
        rec = dict(base, label=best['label'], value=best['value'],
                   raw=best['raw'], period=applies or period_class(
                       best.get('table'), best.get('period'),
                       best.get('label')),
                   basis=split_basis(best['label'])[0],
                   segment=best.get('section') or None, channel='table')
        # BOTH ENDS, NEVER A MIDPOINT. Intel's whole Q4 revenue outlook is
        # one cell, '$15.0 - $16.0', so value is None and the guide would
        # otherwise arrive as an unparsed string. A midpoint is CHAT's
        # arithmetic, not the document's -- the same line drawn on Services
        # YoY -- and the RANGE WIDTH is tradeable: this guide is 9.0% below
        # street and the worst-scoring row on the print. Splitting the
        # printed cell reports what Intel printed; averaging it does not.
        lo, hi = range_ends(rec.get('raw'))
        if lo is not None:
            rec['low'], rec['high'] = lo, hi
        if unverified:
            rec['needsVerification'] = True
        out['found'].append(rec)
        claimed.update(i for i, _r in found)

    out['found'].sort(key=lambda h: (h.get('priority') or 9,
                                     h.get('order') or 0))
    out['notInRelease'].sort(key=lambda h: (h.get('priority') or 9,
                                            h.get('order') or 0))
    for i, row in enumerate(parser_rows):
        if i not in claimed and metrics_for(aliases, row.get('label')):
            out['overflow'].append(row)
    return out


def coverage_ok(result):
    """found + notInRelease must equal the hero count. Completeness only."""
    n = len(result.get('found') or []) + len(result.get('notInRelease') or [])
    return n == (result.get('heroCount') or 0), n


#: the locked scorecard order. A hero's appliesTo places it; nothing here
#: knows what any of these sections MEAN.
SECTIONS = (('currentQuarter', 'CURRENT QUARTER'),
            ('nextQGuidance', 'NEXT-Q GUIDANCE'),
            ('fyGuidance', 'FY GUIDANCE'))


def _despace(text):
    """'Three Months EndedSeptember 30' -> '... Ended September 30'.

    ★ THE MISSING SPACE IS IN THE SOURCE TOKEN, not the truncation. EDGAR
    emits it concatenated, and ranking was already taught to see the month
    anyway; this is the DISPLAY catching up. Scoped to month names so a
    deliberate intercap like 'nonGAAP' is left alone.
    """
    import re as _re
    return _re.sub(r'(?<=[a-z])(?=(?:%s)[a-z]*\s*\d)'
                   % '|'.join(m.capitalize() for m in _MON3),
                   ' ', text or '')


def _row_line(h):
    if h.get('low') is not None and h.get('high') is not None:
        shown = '%s-%s' % (_fmt(h['low']), _fmt(h['high']))
    elif h.get('channel') == 'prose':
        shown = _fmt(h.get('value'))
    else:
        shown = h.get('raw') or _fmt(h.get('value'))
    tags = []
    seg = str(h.get('segment') or '')
    if 'segment' in seg.lower():
        tags.append('[%s]' % seg.rstrip(':'))
    if h.get('channel') == 'prose':
        tags.append('[prose]')
    if h.get('needsVerification'):
        tags.append('[UNVERIFIED]')
    return ('  %-38s %14s   %-10s %s'
            % (str(h.get('label'))[:38], shown[:14],
               _short(h.get('period')), ' '.join(tags))).rstrip()


def current_quarter_rows(parser_rows, exclude_labels=()):
    """Every row the document printed for the REPORTED QUARTER. No map.

    ★★★★ THE PERIOD FILTER IS UNIVERSAL AND ALWAYS WAS -- period_class
    takes (table, period, label) and knows nothing about a ticker, a
    profile or a hero. It was only ever REACHED through a hero lookup, so
    60 tickers with no documentLabelMap rendered a blank screen while the
    thing that beat the nine-month and prior-year columns on Apple sat
    right there, unused.

    ★★ DOCUMENT ORDER, VERBATIM LABELS, SECTION HEADINGS INTACT. No
    importance ranking, no headline grouping, no folding cost-of-sales or
    balance-sheet rows together. The moment this decides what matters it
    has left scope.

    One row per (section, label); where a label carries several columns in
    the quarter -- current and prior-year -- the most recent wins, by the
    same recency term the hero path uses.
    """
    skip = set(norm(x) for x in (exclude_labels or ()))
    seen, out = {}, []
    for r in parser_rows or []:
        if period_class(r.get('table'), r.get('period'),
                        r.get('label')) != 'currentQuarter':
            continue
        if norm(r.get('label')) in skip:
            continue
        key = (r.get('section') or '', r.get('label') or '')
        if key not in seen:
            seen[key] = len(out)
            out.append(r)
        else:
            cur = out[seen[key]]
            if (_recency(r), _precision(r)) > (_recency(cur),
                                               _precision(cur)):
                out[seen[key]] = r
    return out


def report(result, ticker, heading='', show_overflow=0, parser_rows=None):
    """Hero rows grouped by what the HERO asked for.

    ★★ THE SECTION AND THE PERIOD COLUMN ARE DIFFERENT CLAIMS and both
    stay. The header is what the hero asked for; the column is what the
    DOCUMENT gave. A row under FY GUIDANCE returning `nextQ` is a
    mismatch, and collapsing the two would hide exactly that.

    ★ A SECTION WITH HEROES BUT NO RESOLUTIONS STILL PRINTS, carrying its
    `not in release` rows. An empty FY block is a signal; a missing one is
    silence.
    """
    found = result.get('found') or []
    missing = result.get('notInRelease') or []
    lines = ['%s  %s' % (ticker, heading)]
    if found:
        pass

    placed = set()
    for key, title in SECTIONS:
        fs = [h for h in found if h.get('appliesTo') == key]
        ms = [h for h in missing if h.get('appliesTo') == key]
        if not fs and not ms:
            continue
        placed.add(key)
        lines.append('')
        lines.append(title)
        for h in fs:
            lines.append(_row_line(h))
        for n in ms:
            lines.append(('  not in release - %-44s %s'
                          % (n['hero'][:44],
                             ('[%s]' % n['channel']) if n.get('channel')
                             else '')).rstrip())

    # ★★★ AN UNRECOGNISED appliesTo IS NAMED, NEVER DEFAULTED. Dropping it
    # loses a hero from the count; filing it under currentQuarter invents
    # a claim the profile never made.
    rest_f = [h for h in found if h.get('appliesTo') not in placed]
    rest_m = [h for h in missing if h.get('appliesTo') not in placed]
    if rest_f or rest_m:
        lines.append('')
        lines.append('UNCLASSIFIED')
        for h in rest_f:
            lines.append('%s   (appliesTo=%r)'
                         % (_row_line(h), h.get('appliesTo')))
        for n in rest_m:
            lines.append('  not in release - %s   (appliesTo=%r)'
                         % (n['hero'][:46], n.get('appliesTo')))

    # ★ EVERYTHING ELSE THE DOCUMENT PRINTED FOR THE QUARTER, after the
    # mapped rows and clearly separated from them. For an unmapped ticker
    # this is the whole card; for a mapped one it is the context the hero
    # rows were chosen out of.
    if parser_rows is not None:
        claimed = set(str(h.get('label')) for h in found)
        rest = current_quarter_rows(parser_rows, exclude_labels=claimed)
        if rest:
            lines.append('')
            lines.append('CURRENT QUARTER - everything else printed (%d)'
                         % len(rest))
            # ★ WHERE ONE LABEL CARRIES TWO PERIODS, MARK THE OLDER. Apple's
            # year-end release repeats the income statement inside a
            # PRIOR-YEAR non-GAAP reconciliation whose columns are all the
            # September BEFORE the one being reported, under section ''.
            # Those rows have no current-year sibling to lose the dedupe
            # to, so the card showed Net income 14,736 -- FQ4'24 GAAP --
            # beside the correct 27,466, with nothing to tell them apart.
            #
            # MARKED, NOT DROPPED AND NOT REORDERED. A filter can delete a
            # good row and a reorder hides the document's own sequence;
            # neither is needed when the reader can simply SEE the period.
            newest = {}
            for r in rest:
                lab = str(r.get('label') or '')
                newest[lab] = max(newest.get(lab, (0, 0)), _recency(r))
            sec = None
            for r in rest:
                if (r.get('section') or '') != sec:
                    sec = r.get('section') or ''
                    lines.append('  -- %s' % (sec or '(no section)'))
                rec = _recency(r)
                stale = (rec[0] and rec < newest[str(r.get('label') or '')])
                lines.append('     %-38s %13s  %-14s %s'
                             % (str(r['label'])[:38], str(r['raw'])[:13],
                                period_tag(r.get('period')),
                                'STALE' if stale else ''))

    ok, n = coverage_ok(result)
    lines.append('')
    lines.append('heroes in profile %d - found %d - not in release %d'
                 '  = %d  %s'
                 % (result.get('heroCount') or 0, len(found), len(missing),
                    n, 'OK' if ok else 'MISMATCH'))
    if show_overflow:
        lines.append('')
        lines.append('OVERFLOW')
        for r in (result.get('overflow') or [])[:show_overflow]:
            lines.append('  %-38s %12s  %s'
                         % (r['label'][:38], r['raw'][:12],
                            _despace(r['period'])[:34]))
    return '\n'.join(lines)


def _short(period):
    return {'currentQuarter': 'currentQ', 'nextQGuidance': 'nextQ',
            'TTM': 'TTM'}.get(period, period or '')


#: the day-anchored month, plus the year that follows it. Reuses the same
#: anchor _MONTHRE uses, so the tag and the RANKING always read the same
#: date out of a column -- a display that parsed dates its own way could
#: print 'Sep 27, 2025' beside a row ranked on 2024.
_DATERE = re.compile(r'(?i)(' + '|'.join(_MON3)
                     + r')[a-z]*\.?\s*(\d{1,2})\b[,\s]*((?:19|20)\d{2})?')


def period_tag(period):
    """'Three Months Ended September 28, 2024 As Reported' -> 'Sep 28, 2024'.

    THE PARSER ALREADY KNOWS THIS AND THE DISPLAY WAS THROWING IT AWAY.
    Every row carries the column header that decided its class; printing
    only the figure asks the reader to assume which period it came from,
    and at fiscal year end that assumption is wrong five times on one
    Apple card.

    Falls back to the squeezed period rather than to nothing: an
    unparseable header is still evidence, and a blank tag would read as
    "no period given" when the truth is "a period I could not shorten".
    """
    m = _DATERE.search(period or '')
    if m:
        return ('%s %s, %s' % (m.group(1).capitalize(), m.group(2),
                               m.group(3)) if m.group(3)
                else '%s %s' % (m.group(1).capitalize(), m.group(2)))
    t = ' '.join((period or '').split())
    return t[:22]


def _fmt(v):
    if v is None:
        return '-'
    if isinstance(v, float) and abs(v - round(v)) < 1e-9 and abs(v) >= 1000:
        return '{:,.0f}'.format(v)
    return ('{:,.1f}'.format(v) if isinstance(v, float) else str(v))
