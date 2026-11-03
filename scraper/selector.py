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
from scraper import passthrough                             # noqa: E402
from scraper import prose_guidance as PROSE                 # noqa: E402
from scraper import prose_labels                            # noqa: E402

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
    # ★★★ THE SAME LINE UNDER THE NAME HALF THE MARKET USES. Added to
    # prose_guidance._SUBJECT and NOT here, which left the reader able
    # to parse 'Adjusted income from operations of between $1.640 -
    # $1.644 billion' and the selector unable to ask for it: both of
    # PLTR's income-from-operations heroes read 'not in release' against
    # a document that plainly carries them. TWO VOCABULARIES, ONE GAP
    # CLOSED IN ONE -- map-vs-reader disagreement, in a single edit.
    ('income from operations', 'operatingIncome'),
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
    # ★★★ AND A FISCAL-QUARTER TOKEN IS ONE TOKEN. This stripped a lone
    # 'q' and a lone 'fy' but left 'f4q', 'q3' and 'fy2027' standing, so
    # 'F4Q Gross Margin (%)' reduced to 'f4q gross margin' -- which is
    # not 'gross margin', so canonical() refused a hero that is exactly
    # a metric. The same leftover made _residue count 'q2' as content
    # and refuse 13 matches that were right.
    t = re.sub(r'\b(f?\d?q\d?|fy\d*|cy\d*|h[12]|yr|\d+)\b', ' ', t)
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
    """Does anything around this cell say the column is a percentage?

    ★★★★ THE TABLE'S UNIT NOTE IS THE DOCUMENT'S OWN DECLARATION, and it
    was the one place this did not look. Palantir heads the table
    '(in thousands, except percentages and per share amounts)' and then
    prints 'Adjusted operating margin' as a bare 62 -- the % sign lives
    in a column header that cells.from_html does not attach to the row,
    so label, period and section all come back clean and the percent
    guard refused the single row that hero exists for.

    ★★ APPLE'S TABLE SAYS '(In millions, except number of shares ... and
    per-share amounts)' and says nothing about percentages, so its
    DOLLAR line called 'Gross margin' is still refused. The difference
    is not magnitude, inference or ticker knowledge -- it is that one
    issuer declared percentages in this table and the other did not.
    """
    hay = norm('%s %s %s %s' % (row.get('label') or '',
                                row.get('period') or '',
                                row.get('section') or '',
                                row.get('table') or ''))
    # ★★★ 'GROWTH' AND 'Y/Y' ARE THE DOCUMENT SAYING 'RATE'. Amazon's
    # supplemental table labels the row 'AWS -- Y/Y growth, excluding
    # F/X' and prints a bare 17. Nothing in the table note, the section
    # or the column mentions percentages -- the LABEL is the only place
    # the unit is stated, and it states it twice. A quantity called a
    # year-over-year growth is not a dollar amount.
    return ('%' in hay or 'percent' in hay or 'margin %' in hay
            or 'rate' in hay or ' ppt' in hay or 'basis points' in hay
            or 'growth' in hay or 'y/y' in hay or 'yoy' in hay
            # ★★ 'MARGIN' IS A RATIO BY DEFINITION -- and the famous
            # counter-example is not a counter-example. Apple's 'Gross
            # margin' row IS a dollar line, 54,820, and what refuses it
            # is the PLAUSIBILITY check beside this one, not a pretence
            # that the word means nothing. Leaving 'margin' out here
            # made that check unreachable and blanked six correct
            # readings -- 40.2, 49.2, 44.2, 47.4, 16.0, 24.0 -- every
            # one a bare percentage under a label that says margin.
            or 'margin' in hay)


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


#: the unit a hero writes in its own name: 'F4Q Gross Margin (%)'
_NAMEUNIT = re.compile(r'\((%|\$[BMK]?|bps|pct)\)\s*$')


def name_unit(name):
    """The unit a hero writes in its own name, or ''."""
    m = _NAMEUNIT.search(str(name or '').strip())
    return m.group(1) if m else ''


#: does this currency unit STATE a scale? '$' does not; '$K/$M/$B' do.
_SCALED = frozenset(('$K', '$M', '$B'))


def _scale_rank(u):
    return 1 if str(u or '').strip() in _SCALED else 0


def declared_unit(field, named):
    """(unit, problem) -- reconcile a unit FIELD against the hero's NAME.

    `problem` is None, or (severity, message) with severity 'defect' or
    'warn'.

    ★★★★ A DECLARATION MUST NEVER BE ABLE TO SILENCE THE CHECK IT
    BELONGS TO. Four heroes named '(%)' carried unit 'bps'. bps has no
    class at all, so unit_class returned None and the class guard and
    the plausibility check switched off together -- the same failure as
    an EMPTY unit, except that it looks declared, so nothing about it
    reads as missing. One of them was a hero named '(%)' whose map said
    '$B'; it printed $1.463 billion under a percent label and no guard
    in this file could object, because the declaration had disabled
    them.

    So the FIELD is authoritative only while it agrees with the name:

      - field absent, or carrying a unit this module cannot class ->
        the NAME is the declaration, and it is the one always present.
      - field and name in different classes -> a DEFECT, reported and
        refused. Not an override, not a silent pick: the two statements
        the profile makes about one hero disagree, and resolving a
        figure against either would be choosing which author to trust.
      - otherwise -> the field, which is the more precise of the two
        ('$M' where the name says '$').
    """
    f, n = str(field or '').strip(), str(named or '').strip()
    fc, nc = unit_class(f), unit_class(n)
    if not f:
        return n, None
    if fc and nc and fc != nc:
        return n, ('defect',
                   'unit conflict: the name says %r (%s) and the profile '
                   'declares %r (%s)' % (n, nc, f, fc))

    # ★★★★ SAME CLASS, DIFFERENT SCALE. $B and $M are both CURRENCY, so
    # the arm above cannot see a THOUSANDFOLD disagreement -- and that is
    # the error that keeps recurring, because a scale is easy to write
    # wrong and nothing on screen contradicts it: the card renders the
    # document's own words, so the unit field never reaches the display.
    #
    # ★★★ THE HARM IS A DEAD GUARD, NOT A WRONG NUMBER. _plausible bounds
    # a '$B' hero at 10,000 and a '$M' hero at 10,000,000 -- so a scale
    # mismatch widens the guard a thousandfold and it reports clean
    # forever after. Same family as a unit the module cannot class at
    # all.
    #
    # ★★ BUT '$' IS NOT A DIFFERENT SCALE, IT IS NO SCALE. Three heroes
    # name ($M) and declare '$', which does not contradict anything --
    # it simply says less. Taking the SPECIFIED one is the whole of the
    # 'more precise wins' rule, and it was written backwards: it always
    # took the field, which on those three is the vaguer of the two and
    # leaves _plausible with no bound at all.
    if fc == 'CURRENCY' and nc == 'CURRENCY' and f.strip() != n.strip():
        rf, rn = _scale_rank(f), _scale_rank(n)
        if rf != rn:
            return (f if rf > rn else n), None
        # ★ FLIPPED TO DEFECT 2026-11-03, once the count reached zero.
        # It shipped as a warning because refusing then would have
        # blanked six of one watchlist ticker's eleven resolved rows over
        # a profile bookkeeping error. The list is clear library-wide, so
        # the next one to appear is a NEW mistake rather than a backlog
        # entry -- and a refusal that costs nothing today is the cheapest
        # it will ever be.
        return n, ('defect',
                   'unit scale: the name says %r and the profile declares '
                   '%r -- a 1000x gap, and _plausible is bounded by the '
                   'declared one' % (n, f))
    # ★★ A UNIT THIS MODULE CANNOT CLASS IS LEFT ALONE, AND THAT IS A
    # DELIBERATE STOPPING POINT. 28 heroes declare 'bps', 5 more declare
    # 'GWh', 'GW', 'KRW tn' or 'qualitative'. Overriding those with the
    # '(%)' in the name switches the class guard back on for all of them
    # -- and on the two I checked it swapped one wrong answer for
    # another: a segment's dollar line, 7,761, became that segment's
    # GROSS PROFIT MARGIN, 82.6, under a hero asking for revenue GROWTH.
    # Neither is the growth rate, because the release does not print one.
    # That is a hero binding to a same-named row of a different quantity,
    # which is the table-side of the _residue problem and is not fixed
    # by anything to do with units. Reported, not papered over.
    return f, None


def _unit_of(h, name):
    """The hero's declared unit -- from the field, else from the NAME."""
    field = h.get('unit') if isinstance(h, dict) else None
    return declared_unit(field, name_unit(name))[0]


def _hero_fields(h):
    if isinstance(h, dict):
        name = h.get('name') or ''
        return (name, h.get('priority'),
                h.get('appliesTo') or '', _unit_of(h, name),
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


#: words that survive _bare but still say nothing about WHAT is measured.
#: Deliberately short: every addition here widens the loose prose match,
#: and the loose match is the one that cannot see a segment.
_PROSE_RESIDUE_OK = frozenset(
    'total company consolidated growth bps pct b m k bn mm'.split())
_PROSE_WORD = re.compile(r'[a-z0-9]+')

#: ★ A PERIOD TOKEN IS NOT CONTENT. _bare strips a lone 'q' and a lone
#: 'fy' but leaves 'q2', 'f4q' and 'fy2027' standing, and counting those
#: as residue refused 13 matches that were right -- 'Q2 Revenue Guide
#: ($M)' reduced to 'q2 revenue' and then refused itself over the 'q2'.
#: Which period a row belongs to is settled by _prose_hit, not here.
_PERIODISH = re.compile(r'^(f?\d?q\d?|fy\d*|cy\d*|h\d|\d+)$')


def _residue(bare, needle):
    """Content words left in a hero name once the metric word is removed."""
    return [w for w in _PROSE_WORD.findall(bare.replace(needle, ' '))
            if w not in _PROSE_RESIDUE_OK and not _PERIODISH.match(w)]


def _prose_metric(hero_name, prose_rows):
    """The prose metric this hero names, or None.

    ★ LOOSER THAN canonical() ON PURPOSE, AND ONLY HERE. The prose channel
    is already fenced to a guidance SECTION, so the candidate set is a
    handful of sentences rather than a thousand table cells. Matching the
    metric word among three guidance bullets is safe where it would not
    be against the whole document.

    ★★ BUT ONLY WHEN THE METRIC WORD IS THE WHOLE NAME. An earlier
    revision cited 'FY+1 capex framing ($B)' as a name this should catch.
    It no longer does, and that is the fix, not a loss: the only capex
    sentence Amazon prints is its CURRENT year's, so the match would have
    answered an FY+1 hero with an FY figure -- a period error that
    _prose_hit cannot see, because both sides normalise to fyGuidance.
    See _residue.
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
            # ★★★★ WHAT IS LEFT OF THE NAME IS THE PART THE PROSE CHANNEL
            # CANNOT REPRESENT. _bare has already removed the period, the
            # basis and the word 'guide'; anything still standing after
            # the metric word is taken out is a SEGMENT or a TRANSFORM --
            # 'us commercial', 'aws', 'north america', 'raise', 'cc
            # action' -- and prose_guidance has no vocabulary for any of
            # them. It would hand back the CONSOLIDATED line every time.
            # Measured over the corpus: 21 loose matches carried a
            # residue and all 21 were wrong; 13 carried none and all 13
            # were right.
            if _residue(bare, n):
                continue
            return metric
    return None


#: prose periods -> the hero `appliesTo` vocabulary. prose_guidance stamps
#: a full-year row 'FY2026' or bare 'FY'; the profiles call that slot
#: 'fyGuidance'. Two names for one period is how they failed to meet.
def _prose_period_class(period):
    return ('fyGuidance' if str(period or '').startswith('FY')
            else str(period or ''))


def _prose_hit(prose_rows, metric, applies):
    """The guidance row for THIS hero's period, or None.

    ★★★★ MATCHING ON THE METRIC ALONE PUTS THE QUARTER GUIDE IN THE
    FULL-YEAR ROW. `next(p for p in prose_rows if p['metric'] == pm)`
    takes the first row that names the metric, and on any issuer who
    guides both periods in one section the first one is the QUARTER.
    Salesforce's FY revenue hero was reading $11.27-11.35B -- the quarter
    -- when the full-year guide on the same page said $45.9-46.2B. Four
    times the number, in the corpus, today, with nothing on the card to
    show for it.

    ★★ AND A GUIDANCE SECTION CANNOT REPORT THE QUARTER THAT JUST CLOSED.
    Rocket Lab's reported-quarter hero was being filled from 'between
    $225 million and $240 million' -- the guide for the quarter AHEAD --
    which is non-negotiable 2 running backwards. A currentQuarter or
    narrative hero gets nothing from this channel and falls through to
    the table, where a reported number actually lives.
    """
    if not metric or applies not in ('nextQGuidance', 'fyGuidance'):
        return None
    return next((p for p in (prose_rows or [])
                 if p.get('metric') == metric
                 and _prose_period_class(p.get('period')) == applies), None)


_YOYNAME = re.compile(r'(?i)\b(yoy|y/y|year[\s-]over[\s-]year)\b')


def select(parser_rows, ticker, profiles=None, aliases=None,
           prose_rows=None, source_text=None):
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

    out['sourceTextFirst'] = bool(prof.get('sourceTextFirst'))
    dlm = prof.get('documentLabelMap') or {}
    segs = ((prof.get('documentLabelMapSegments') or {}).get('labels')) or {}
    heroes = prof.get('heroKPIs') or []
    out['heroCount'] = len(heroes)
    claimed = set()

    for _hero_i, hero in enumerate(heroes):
        name, prio, applies, unit, _inv = _hero_fields(hero)
        # the unit the hero writes in its own name, kept so the MAP's
        # override can be reconciled against it too -- the live conflict
        # was declared there, not in heroKPIs.
        nunit = name_unit(name)
        uprob = (declared_unit(hero.get('unit'), nunit)[1]
                 if isinstance(hero, dict) else None)
        # ★ appliesTo AND PROFILE ORDER TRAVEL WITH EVERY HERO,
        # including the ones that do not resolve. A hero that is not
        # in the release still belongs to a section, and an FY block
        # that is empty BECAUSE nothing resolved is a real signal --
        # which it cannot be if the row has nowhere to appear.
        base = {'hero': name, 'priority': prio,
                'appliesTo': applies or '', 'order': _hero_i}
        labels, seg_ctx, channel, unverified = [], None, None, False
        want_basis = None
        # ★★★★ A HERO WITH NO MAP ENTRY IS THE COMMON CASE, NOT AN EDGE
        # CASE. 59 of 66 profiles carry no documentLabelMap at all, so
        # dlm.get(name) returns None for most heroes in the library --
        # and `'expect' in entry` on that None took select() down with a
        # TypeError for 24 tickers, several of them megacaps: 47 of 121
        # corpus documents, no card at all, on a print night it would
        # have been the whole read. Shipped in a34c723 and never seen,
        # because validate_maps
        # walks only the 7 tickers that HAVE a map and every fixture is
        # one of those 7. The gate covered 10% of the library and said
        # PASS. Normalised here so no later reader has to remember.
        entry = dlm.get(name)
        if not isinstance(entry, dict):
            entry = {}
        if entry:
            labels = [str(x) for x in (entry.get('documentLabels') or [])]
            want_basis = basis_of(entry.get('basis'))
            seg_ctx = entry.get('segmentContext')
            channel = entry.get('channel')
            unverified = bool(entry.get('needsVerification'))
            if entry.get('period'):
                applies = entry['period']
            if entry.get('unit'):
                unit, prob = declared_unit(entry['unit'], nunit)
                uprob = uprob or prob
        if not labels:
            for short, sentry in segs.items():
                if short and norm(short) in norm(name):
                    labels = [str(x) for x in
                              ((sentry or {}).get('documentLabels') or [])]
                    break

        # ★★★ AND IT IS REPORTED, NOT RESOLVED. A hero whose two
        # declarations disagree about what KIND of quantity it is cannot
        # be answered safely by either, and an UNRESOLVED says exactly
        # that: the figure may well be in the release and we are
        # refusing to guess which one it is. Silently preferring one
        # side is how a percent label came to carry $1.463 billion.
        # ★★ A DEFECT REFUSES; A WARNING RESOLVES AND SAYS SO. Refusing a
        # scale mismatch today would blank six of one watchlist ticker's
        # eleven resolved rows over a profile bookkeeping error -- a card
        # going empty is a regression the trader sees, while the mismatch
        # itself is invisible to him. So the row still renders and
        # carries the flag, and the flag is what gets cleared.
        uwarn = None
        if uprob:
            severity, umsg = uprob
            if severity == 'defect':
                out['notInRelease'].append(dict(base, reason=umsg))
                continue
            uwarn = umsg
        base['unitWarning'] = uwarn

        low = norm(name)
        if not want_basis:
            if 'non-gaap' in low:
                want_basis = 'NON_GAAP'
            elif 'gaap' in low:
                want_basis = 'GAAP'

        # ── the PROSE channel, where the issuer states it in a sentence ──
        if channel == 'prose' or not labels:
            # ★★★★ THE RANGE-AWARE READER GOES FIRST, ALWAYS.
            # prose_guidance parses a guidance bullet into BOTH ENDS and
            # stamps its period; prose_labels finds one declared phrase
            # and reads ONE figure near it. Letting the second overrule
            # the first turned the FY revenue guide from 7,650-7,662
            # into 7.65 -- the high end gone and the scale word with it,
            # because 'between $7.650 - $7.662 billion' puts 'billion'
            # after the far number. Richer reader first; the phrase
            # reader is what runs when it finds nothing.
            pm = _prose_metric(name, prose_rows)
            hit = _prose_hit(prose_rows, pm, applies)

            # ★★★ A DECLARED PHRASE, WHEN THE VOCABULARY CANNOT HELP.
            # 'U.S. commercial revenue' and 'revenue' reduce to the same
            # word, so no metric vocabulary can keep a SEGMENT apart from
            # the consolidated line. The profile naming the exact phrase
            # is the only thing that can, and _residue refuses the loose
            # match precisely so this path is reached instead.
            # ★★★ A HERO THAT IS EXACTLY A METRIC NAMES ITS OWN PHRASE.
            # Apple states two of its headline figures only in prose --
            # 'Company gross margin was 47.9 percent' and 'Diluted
            # earnings per share was $2.10' -- and declares no
            # documentLabels for either, because in the TABLE both
            # collide: 'Gross margin' is a dollar line and a bare
            # 'Diluted' returns the share count, 14,714,676.
            #
            # canonical() already requires the name to reduce EXACTLY to
            # a metric phrase, residue and all, so using that metric's
            # own universal vocabulary as the search phrase guesses
            # nothing. A hero carrying a segment or a transform does not
            # reduce, gets no phrase here, and stays blank.
            declared = bool(labels)
            if (hit is None and channel == 'prose' and not labels
                    and applies == 'currentQuarter'):
                exact = canonical(name)
                if exact:
                    labels = [n.strip() for n, m in _CANON if m == exact]
            if hit is None and channel == 'prose' and labels:
                # ★★ A WIRING FAULT, BUT ONLY WHEN THE PROFILE ASKED FOR
                # ONE. If the profile DECLARED a phrase and nobody handed
                # this function the prose to search, that is a caller bug
                # and 'not in release' would report it as a fact about
                # the document. Phrases DERIVED from the hero's own name
                # are a convenience: without source_text they simply do
                # not apply, and the row falls through to the ordinary
                # declared absence below.
                #
                # ★ AND IT STILL NAMES THE CHANNEL. An absence that does
                # not say which channel was declared is the one kind of
                # blank _why exists to prevent.
                if not source_text and declared:
                    # ★★ AN UNDECLARED ABSENCE IS A DEFECT. The hero names
                    # a phrase and nobody handed this function the prose
                    # to look in: a wiring fault, not a fact about the
                    # release. 'not in release' here reports a bug as a
                    # finding.
                    out['notInRelease'].append(dict(
                        base, channel=channel,
                        reason='documentLabels declared, but select() was '
                        'called without source_text'))
                    continue
                if not source_text:
                    labels = []
                # ★ AND A GUIDANCE HERO SEES ONLY ITS OWN SUB-BLOCK.
                # This reader has no notion of period -- over the whole
                # release it answers the FY free-cash-flow GUIDE with the
                # quarter's reported $1.216 billion, from a highlights
                # bullet, under an FY label. Fenced to the sub-block, the
                # sentence it finds is a guidance sentence for the right
                # period or there is no sentence at all.
                hay = source_text or ''
                if applies in ('nextQGuidance', 'fyGuidance'):
                    hay = PROSE.block_text(source_text or '', applies)
                elif applies != 'currentQuarter':
                    hay = ''
                lab = prose_labels.find(hay, labels, unit_class(unit),
                                        yoy=bool(_YOYNAME.search(name)))
                if lab is not None:
                    out['found'].append(dict(
                        base, label=lab.get('phrase') or name,
                        value=lab.get('value'), low=lab.get('low'),
                        high=None, raw=None,
                        printed=lab.get('printed'), period=applies,
                        basis=None, segment=None, channel='prose',
                        pinned=('expect' in entry
                                or 'expectRange' in entry),
                        needsVerification=unverified,
                        sourceSentence=lab.get('sentence')))
                    continue
            # ★★★★ A DECLARED CHANNEL IS A DECLARATION, NOT A
            # PREFERENCE. channel:'prose' on Apple's Gross Margin (%) says
            # the percent exists ONLY in a sentence -- the table label
            # 'Gross margin' is a DOLLAR line, 54,770. Falling through to
            # the table when the prose lookup found nothing returned
            # 54,770 as a gross MARGIN: a 54,770% margin, resolved,
            # displayed, and counted as found.
            if hit is None and channel == 'prose':
                out['notInRelease'].append(dict(
                    base, channel='prose',
                    reason=entry.get('absenceReason')))
                continue
            if hit is not None:
                out['found'].append(dict(
                    base, label=hit.get('label') or pm, value=hit.get('value'),
                    low=hit.get('low'), high=hit.get('high'),
                    raw=hit.get('raw'), period=hit.get('period'),
                    printed=hit.get('printed'),
                    basis=None, segment=None, channel='prose',
                    pinned=('expect' in entry or 'expectRange' in entry),
                    sourceSentence=hit.get('sourceSentence')))
                continue
        # ★★★ WHY A ROW IS BLANK IS NOT ALL ONE THING. 'call' means ask the
        # transcript. 'derived' means the INPUTS are printed but the figure
        # is not -- Apple prints Services at 30,739 and 27,423 and never
        # the +12.1%. Collapsing them loses the difference between a number
        # that exists nowhere and one that is two columns and a division
        # away. Neither is computed here; the parser reports what was
        # printed, and the display says which kind of absence this is.
        if channel in ('call', 'derived', 'unmapped'):
            # a hero may say WHY in its own words; 'derived' on a row
            # the document actually prints is a wrong reason, and a
            # wrong reason is believed exactly like a wrong number.
            out['notInRelease'].append(dict(
                base, channel=channel,
                reason=entry.get('absenceReason')))
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
            # ★★★★ C2. The guard above refuses an unmarked cell for a
            # percent hero, and it is right to: Apple prints a DOLLAR
            # line called 'Gross margin', 54,770, inside a $M table with
            # no '$' in the cell, and nothing but this stopped it being
            # read as a 54,770% margin.
            #
            # But Palantir prints 'Adjusted operating margin' as a bare
            # 62 with the % sign in a COLUMN HEADER that cells.from_html
            # never attaches to the row -- so label, period and section
            # all come back clean and _pct_context cannot see it. The
            # guard then refuses the one row the hero was built for.
            #
            # MAGNITUDE IS THE DISCRIMINATOR THE CONTEXT CANNOT SUPPLY.
            # 54,770 is not a percentage at any plausible scale; 62 is.
            # This does not loosen the guard for a marked cell, does not
            # apply to any other unit class, and only ever runs on a row
            # whose LABEL the profile already named.
            if hc == 'PERCENT' and rc is None:
                if not _pct_context(row):
                    continue
                # ★★ AND THE MAGNITUDE MUST BE CREDIBLE AS A PERCENT.
                # _pct_context now reads the table's unit note, which is
                # a statement about the TABLE, not about this cell: a
                # table headed '(in millions, except percentages)' holds
                # both kinds of column. _plausible is the second net, and
                # it is the one that refuses 54,820 whatever the note
                # says. Defined since the first cut and never called
                # until now.
                if not _plausible(cells.to_number(row.get('raw')), '%'):
                    continue
            found.append((i, row))

        if not found:
            # ★ A DECLARED CHANNEL THAT MATCHED NOTHING IS A FAILURE, AND
            # IT PRINTED MUTE. Every declared absence carries [prose] /
            # [call] / [derived]; a table hero whose rows were all refused
            # carried nothing at all, so the one row we CANNOT explain
            # looked exactly like the seven we can. Named, not relabelled
            # -- calling it a declared absence would be adjusting the
            # output to look right.
            #
            # The live case is a bare integer with its % in the COLUMN
            # header: Palantir prints 'Adjusted operating margin' as 62,
            # the percent guard refuses an unmarked cell for a percent
            # hero, and that guard is what keeps Apple's 54,770 dollar
            # line out of a gross-margin slot.
            why = 'declared %s, no row matched' % (channel or 'table')
            if unit_class(unit) == 'PERCENT':
                refused = [r for i, r in enumerate(parser_rows or [])
                           if raw_class(r.get('raw')) is None
                           and not _pct_context(r)
                           and norm(r.get('label')) in
                           set(norm(x) for x in (labels or []))]
                if refused:
                    why = ('percent guard: %s unmarked, %% is in the column '
                           'header' % str(refused[0].get('raw'))[:12])
            out['notInRelease'].append(dict(base, reason=why))
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
        # ★★ A CHECKED VALUE AND AN UNCHECKED ONE MUST NOT LOOK ALIKE.
        # Three AAPL heroes resolve; two are pinned to a hand-read
        # figure and two have never been value-checked, and on the
        # card they rendered identically. Under time pressure that
        # reads as four verified numbers.
        rec['pinned'] = ('expect' in entry or 'expectRange' in entry)
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


#: THE CARD. Fixed order, the three periods a print actually has.
CARD_SECTIONS = (('currentQuarter', 'CURRENT QUARTER'),
                 ('nextQGuidance', 'NEXT QUARTER'),
                 ('fyGuidance', 'FULL YEAR'))


#: ★★★★ AN UNCLOSED PAREN IS A NEGATIVE WITH ITS OTHER HALF ON THE NEXT
#: LINE. Oracle's free cash flow cell arrives as '(5,396' -- cells.py
#: already reads it as -5396.0, so the VALUE has been right all along and
#: only the rendering was truncated. On free cash flow the sign is the
#: entire signal: -$5.4B against +$5.4B is a $10.8B swing and the
#: difference between a company burning cash and generating it.
#:
#: ★★★ THE PAREN IS CLOSED, NOT TRANSLATED. The document printed
#: '(5,396)' across two cells; restoring the half that was cut off is
#: repair, while rewriting it as '-5,396' would be the card inventing a
#: notation the issuer did not use. Nothing is computed and nothing is
#: dropped -- the release said negative, so the card says negative.
#:
#: Same family as the 660-row sign defect in the parser, reaching the
#: display by a different route.
_OPEN_PAREN = re.compile(r'^\(\s*[\d$]')


def _close_paren(text):
    t = str(text or '')
    if _OPEN_PAREN.match(t) and ')' not in t:
        return t + ')'
    return t


def _printed(h):
    """The figure AS THE DOCUMENT PRINTED IT, scale word and all.

    ★★★★ NEVER THE NORMALISED NUMBER. _scale multiplies a 'billion' by
    1000 so the channels can be compared in one unit, which is right for
    the pipeline and catastrophic on the card: the next-quarter guide
    would render as `Revenue Guide ($B)  2,649-2,653`, and 2,649 billion
    is the same figure out by a factor of a thousand. The raw string the
    reader kept says '$2.649 - $2.653 billion' and cannot be read wrong.

    ★★ IT ALSO MAKES A UNIT DISAGREEMENT VISIBLE INSTEAD OF SILENT. When
    the hero name claims ($B) and the document prints thousands, the two
    sit side by side on one line and a human sees it. Converting to the
    hero's declared unit would have hidden exactly that -- and which unit
    a number is in has already been wrong on this ticker three ways at
    once.
    """
    for key in ('printed', 'raw'):
        v = h.get(key)
        if v not in (None, ''):
            return _close_paren(v)
    if h.get('low') is not None and h.get('high') is not None:
        return '%s-%s' % (_fmt(h['low']), _fmt(h['high']))
    return _fmt(h.get('value'))


def _card_label(name):
    """The hero's NAME, without the trading note bolted onto it.

    ★ Profiles carry the why on the same string -- 'North America revenue
    ($B) — ⚠ the bogey sits above street' -- which is the right place for
    it and the wrong thing to truncate a card column with. _bare already
    cuts at the em-dash for matching; the display cuts at the same point
    so the two never disagree about which part is the name.
    """
    s = str(name or '')
    for sep in (u' — ', u' - ', u'—'):
        if sep in s:
            s = s.split(sep)[0]
            break
    return s.strip()


def _card_period(h):
    """What the DOCUMENT said this row's period was, as a section key."""
    if h.get('channel') == 'prose':
        return _prose_period_class(h.get('period'))
    return period_class(h.get('table'), h.get('period'), h.get('label'))


def card(result, ticker, heading='', source_text=None, clock=''):
    """THE CARD. Three periods, the profile's preset KPIs under each.

    ★★★★ IT PULLS NUMBERS AND SHOWS THEM. No street, no bogey, no
    clears/misses, no branch, no base rate, no direction, no magnitude.
    Every one of those is a judgment and judgment does not happen here.

    ★★★ THE PRESET SET IS THE PRESET SET. A KPI that did not resolve is
    still listed, with a blank value and a short reason -- because the
    hero that is missing from a print is itself the read, and a card that
    quietly drops it looks like a clean sheet.
    """
    found = result.get('found') or []
    missing = result.get('notInRelease') or []
    head = '%s  %s' % (ticker, heading or '')
    if clock:
        head = '%-52s %s' % (head.rstrip(), clock)
    lines = [head.rstrip()]

    shown = 0
    for key, title in CARD_SECTIONS:
        fs = [h for h in found if h.get('appliesTo') == key]
        ms = [n for n in missing if n.get('appliesTo') == key]
        if not fs and not ms:
            continue
        lines.append('')
        lines.append(title)
        for h in sorted(fs, key=lambda r: r.get('order', 0)):
            shown += 1
            # ★ THE SECTION IS A CLAIM AND THE DOCUMENT IS ANOTHER. They
            # agree silently; when they do not, say so on the row. This
            # is the only thing on the card that is not a plain reading,
            # and it exists because the one defect no gate could catch
            # was a row whose value was real and whose PERIOD was not.
            got = _card_period(h)
            flag = '' if got in (key, '', None) else '  <- document says %s' \
                % _short(h.get('period'))[:22]
            # ★ A UNIT SCALE WARNING RIDES ON ITS OWN ROW. The value
            # is the document's own words and is not in doubt; what
            # is in doubt is the bound _plausible applied while
            # choosing it, which a 1000x gap widens or narrows.
            if h.get('unitWarning'):
                flag += '  <- UNIT SCALE: name and profile disagree'
            lines.append('  %-42s %26s%s'
                         % (_card_label(h.get('hero'))[:42],
                            _printed(h)[:26], flag))
        for n in ms:
            shown += 1
            # ★ SHORT. The full absenceReason is a paragraph and belongs
            # in --full; on the card it only has to say which KIND of
            # absence this is, so a blank row is never mistaken for a
            # number the scraper failed to find.
            why = _why(n)
            if len(why) > 62:
                why = why[:59].rstrip(' .,;') + '...]'
            lines.append(('  %-42s %26s  %s'
                          % (_card_label(n.get('hero'))[:42], '',
                             why)).rstrip())

    if source_text:
        lines.extend(_source_lines(source_text))

    # ── one status line. Everything else belongs in --full or a log ──
    total = result.get('heroCount') or 0
    unres = [m for m in missing if _is_unresolved(m)]
    offcard = total - shown
    tail = ('%d of %d KPIs resolved - %d absent - %d UNRESOLVED'
            % (len(found), total, len(missing) - len(unres), len(unres)))
    # ★★ A HERO THAT IS ON NO PERIOD IS OFF THE CARD, NOT DROPPED. The
    # UNCLASSIFIED bucket is gone, but a narrative hero still counts
    # against the profile and the arithmetic has to close, or the card
    # is quietly showing fewer KPIs than the ticker was built with.
    if offcard:
        # ★ NAME IT. 'off-card (no period)' reads like a silent drop;
        # it is the narrative hero, which belongs to no period section
        # and is still counted against the profile.
        tail += (' - %d narrative row%s, no period section'
                 % (offcard, '' if offcard == 1 else 's'))
    lines.append('')
    lines.append(tail)
    for m in unres:
        lines.append('   UNRESOLVED is a DEFECT, not a decision: %s'
                     % m['hero'][:50])
    return '\n'.join(lines)


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
    # a CHECKED value and an UNCHECKED one must be distinguishable at a
    # glance: ok = pinned to a hand-read figure validate_maps compares
    # on every run, ~ = resolved but never value-checked.
    mark = 'ok' if h.get('pinned') else ' ~'
    return ('%s %-38s %14s   %-10s %s'
            % (mark, str(h.get('label'))[:38], shown[:14],
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


#: a figure carries a currency sign, a percent, a decimal or a
#: thousands group. 'For Q4 2026, we expect:' carries none of
#: them, which is why a bare digit test cannot find a silent block.
_FIGURE = re.compile(r'\$\s*\d|\d\s*%|\d[\d,]*\.\d|\d{1,3}(?:,\d{3})+')


def _source_lines(source_text):
    """The >> blocks. SOURCE TEXT, QUOTED, NEVER PARSED.

    An uninterpreted string cannot be a wrong value, which is why these
    can carry guidance that the parser is not allowed to touch.
    """
    try:
        blocks = passthrough.blocks(source_text)
    except Exception:                                       # noqa: BLE001
        return []
    out = []
    for title, body in blocks:
        out.append('')
        out.append('>> %s - VERBATIM FROM THE RELEASE, NOT PARSED' % title)
        for ln in body:
            out.append('>> %s' % ln)
        # ★★ A HEADING WITH NOTHING UNDER IT IS NOT 'NONE WAS GIVEN'.
        # 'OUTLOOK' followed by silence reads as the company declining to
        # guide; on a guidance-cadence name that is a trade-deciding
        # misread, and the truth is a body that has not finished
        # arriving. The card can tell the difference, so it says which.
        if title in ('OUTLOOK', 'HIGHLIGHTS'):
            rest = [ln for ln in body[1:] if ln.strip()]
            if not any(_FIGURE.search(ln) for ln in rest):
                out.append('>> (no figures under this heading in this frame '
                           '- NOT a statement that none was given)')
    return out


def _why(n):
    """How this hero came to be blank, in the strongest terms available.

    AN ABSENCE IS A DECISION; AN UNRESOLVED IS A DEFECT. A declared
    channel says the figure is not in the release and names where it does
    live. An UNRESOLVED says the figure IS in the release and we failed to
    reach it. They must not read alike, and the footer must not let the
    second pass as the first.
    """
    if n.get('channel'):
        return ('[%s: %s]' % (n['channel'], n['reason'])
                if n.get('reason') else '[%s]' % n['channel'])
    if n.get('reason'):
        return '[UNRESOLVED: %s]' % n['reason']
    return ''


def _is_unresolved(n):
    return not n.get('channel') and bool(n.get('reason'))


def report(result, ticker, heading='', show_overflow=0, parser_rows=None,
           source_text=None):
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
    # ★ WHERE THE SOURCE TEXT GOES IS A PER-TICKER FACT, AND IT LIVES
    # IN THE PROFILE, NOT HERE. On a ticker whose hero block is one
    # row and whose HEADLINE carries four of the five decisive
    # numbers, nine lines of mostly-absences should not come first.
    # On one whose heroes are the useful part, they should. Reading
    # it from sourceTextFirst keeps the ticker out of this module.
    if source_text and result.get('sourceTextFirst'):
        lines.extend(_source_lines(source_text))
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
                          % (n['hero'][:44], _why(n))).rstrip())

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
    # ★★★★ SOURCE TEXT, QUOTED, NEVER PARSED. Sits between the heroes and
    # the dump and is fenced in >> marks so no one can mistake a quotation
    # for a verified value. An uninterpreted string cannot be a wrong
    # number -- which is the only reason this is safe to add hours before
    # a print, when parsing the same sentences is not.
    if source_text and not result.get('sourceTextFirst'):
        lines.extend(_source_lines(source_text))

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
    unres = [m for m in missing if _is_unresolved(m)]
    lines.append('')
    if unres:
        lines.append('heroes in profile %d - found %d - declared absent '
                     '%d - UNRESOLVED %d  = %d  %s'
                     % (result.get('heroCount') or 0, len(found),
                        len(missing) - len(unres), len(unres), n,
                        'OK' if ok else 'MISMATCH'))
        for m in unres:
            lines.append('   an UNRESOLVED is a DEFECT, not a decision:'
                         ' %s' % m['hero'][:56])
    else:
        lines.append('heroes in profile %d - found %d - not in release '
                     '%d  = %d  %s'
                     % (result.get('heroCount') or 0, len(found),
                        len(missing), n, 'OK' if ok else 'MISMATCH'))
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
