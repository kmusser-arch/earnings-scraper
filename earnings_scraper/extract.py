# -*- coding: utf-8 -*-
"""Candidate -> VALUE, routed by whereKind, selected by unit / period / basis.

★★★ THE ACCEPTANCE TEST, AND THE TWO BULLETS NEED DIFFERENT SELECTORS:

    EPS  "...non-GAAP Earnings per Share up 30% in USD and constant currency
          to $1.92."
         candidates {30, 1.92} -- UNIT($) drops the 30% -> {1.92}

    RPO  "Remaining Performance Obligations or RPO up $209 billion
          year-over-year to $664 billion"
         candidates {209, 664} -- BOTH are $B, so unit cannot separate them
         and there is no basis qualifier. ONLY THE PREPOSITION WORKS.

★★ SO DELTA vs LEVEL IS SEMANTIC, NOT POSITIONAL. 'to X' marks the LEVEL;
'up / down / from / versus X' marks the DELTA. Last-candidate-wins passes both
of today's bullets by luck and breaks the moment an issuer writes
"to $664 billion, up $209 billion from a year ago" -- which is why that
ordering is pinned as a fixture rather than left to chance.

★ WRAPPED IS A PREREQUISITE, NOT A REFINEMENT. ORCL prints

    17 |    -- Remaining Performance Obligations or RPO up $209 billion
    18 |       to $664 billion

so the label is on line 17 and the answer on line 18. Any matcher scoped to a
line sees a label with no number and a number with no label.
"""

import math
import re

from . import frames as _frames
from . import priority as _priority
from . import vocab as _vocab
from . import registry
from . import tables as _tables
from . import period as _period_mod
from . import axes as _axes

#: a number with its optional currency and unit words
_NUM = re.compile(
    r'(?P<pre>[A-Za-z%\s,\'\-]{0,26}?)'
    r'(?P<cur>\$)?\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s*'
    r'(?P<unit>%|billion|bn|million|mm?\b|trillion)?', re.I)

#: ★ THE PREPOSITION CARRIES THE MEANING. 'to' is the level; 'up/from' is the
#: change. Measured on ORCL: "up $209 billion year-over-year to $664 billion".
#: ★★★ 'of' IS BOTH, AND THE DISCRIMINATOR IS THE WORD IT ATTACHES TO.
#:      'guidance of approximately $34.8 billion'   of -> LEVEL
#:      'an increase of 93 percent'                 of -> DELTA
#: As a bare token 'of' sat in the LEVEL list, and the level test runs first,
#: so every delta construction ending in 'of' was classified a level: AVGO's
#: revenue guide returned 93.0 -- the growth rate -- for a $B row. REORDERING
#: THE TESTS ONLY INVERTS WHICH CONSTRUCTION LOSES; binding 'of' to its head
#: noun makes the order stop mattering. Same move as 'to marks the level'.
#: ★★ THE HEDGE IS THE OTHER HALF. 'approximately' was in NEITHER vocabulary,
#: so 'guidance of approximately $34.8' ended with the hedge and never reached
#: its own 'of' -- 34.8 came back role=None and the prose path dropped it.
#: A level preposition firing on a delta, and a hedge word hiding a level.
#: ★ AND IT REMOVES 18 SPURIOUS LEVELS NEITHER OF US WAS LOOKING FOR: bare
#: 'of' made YEARS into level candidates -- 'fourth quarter of fiscal 2027'
#: and 'Reform Act of 1995' both yielded a level. A head that is not a metric
#: now yields no role at all.
#: Measured over 8 releases: 87 of-before-figure constructions, 7 with a
#: change head; MATCH 33 -> 34, MISMATCH 3 -> 2, nothing lost.
_LEVEL_HEAD = (r'(?:guidance|revenue|revenues|total|totals|margin|margins|eps|'
               r'income|earnings|loss|losses|flow|flows|backlog|arr|rpo|'
               r'bookings|dividend|dividends|range|ranges|rate|rates|price|'
               r'prices|value|expenses|expenditures|costs?|sales|sale|'
               r'operations|proceeds|balance|amount|adjustments|accounts|'
               r'transactions)')
_DELTA_HEAD = r'(?:increase|increases|decrease|decreases|growth|decline|declines)'
#: A hedge is transparent: it modifies the figure, it does not re-role it.
_HEDGE = r'(?:approximately|about|around|roughly|nearly|~)'

_LEVEL_PREP = re.compile(
    r'\b(?:' + _LEVEL_HEAD + r'\s+of|to|was|were|at|reached|totall?ed|'
    r'climbed\s+to|grew\s+to|increased\s+to)\s*(?:' + _HEDGE + r'\s*)?$', re.I)
#: the issuer's own prior-period markers, shared with period.py so the
#: two readers cannot drift apart on what a comparison looks like
_PRIOR_MARK = _period_mod._PRIOR
_CLAUSE_BREAK = re.compile(r'[.;:]\s')

_DELTA_PREP = re.compile(
    r'\b(?:' + _DELTA_HEAD + r'\s+of|up|down|rose|fell|grew|declined|'
    r'increased|decreased|from|versus|vs\.?|compared\s+to|'
    r'year-over-year|y/y)\s*(?:' + _HEDGE + r'\s*)?$', re.I)

_SCALE = {'billion': 1000.0, 'bn': 1000.0, 'b': 1000.0,
          'million': 1.0, 'mm': 1.0, 'm': 1.0,
          'trillion': 1000000.0}

#: the row's declared unit -> the multiplier that puts a $M figure in it
_ROW_UNIT = {'$B': 0.001, '$M': 1.0, '$K': 1000.0, '$': None, '%': None}


def dewrap_mapped(text):
    """(dewrapped text, segment map) — joins wrapped bullets AND stays locatable.

    ★★★ DEWRAPPED OFFSETS ARE NOT DOCUMENT OFFSETS. Joining lines and
    stripping indentation shifts every position, and `pos` was being recorded
    in this shifted space then persisted as the value's LOCATION. AVGO's Q4
    guide figure sits at 1635 in the document and was recorded at 1541, which
    is a sentence earlier -- inside the CEO's Q3 remark. Provenance off by a
    sentence degrades every column that exists to make disagreement visible.

    The map is [(out_start, orig_start, length)] per emitted run; to_original
    translates back by binary search.
    """
    src = text or ''
    out_parts, segs = [], []
    buf = []          # [(stripped, orig_start)]
    pos = 0           # running offset in the ORIGINAL text
    out_len = 0

    def flush():
        nonlocal out_len
        if not buf:
            return
        for n, (piece, o_start) in enumerate(buf):
            if n:
                out_parts.append(' ')
                out_len += 1
            segs.append((out_len, o_start, len(piece)))
            out_parts.append(piece)
            out_len += len(piece)
        buf.clear()

    for raw in src.splitlines(True):
        line = raw.rstrip('\r\n')
        nl = len(raw) - len(line)
        stripped = line.strip()
        if not stripped:
            flush()
            out_parts.append('\n')
            out_len += 1
            pos += len(raw)
            continue
        lead = len(line) - len(line.lstrip())
        o_start = pos + lead
        if stripped.startswith('--') or stripped.startswith('*'):
            flush()
            if out_parts and out_parts[-1] != '\n':
                out_parts.append('\n')
                out_len += 1
        buf.append((stripped, o_start))
        pos += len(raw)
        del nl
    flush()
    # ★ THE RESULT IS DEWRAPPED AND NOW SAYS SO. Five defects came
    # from an offset measured in one frame and used in another.
    _out = ''.join(out_parts), segs
    return (_frames.framed(_out[0], _frames.DEWRAPPED), _out[1])


def to_original(segs, pos):
    """A dewrapped offset back to its position in the source document."""
    if not segs or not isinstance(pos, int):
        return pos
    lo, hi = 0, len(segs) - 1
    best = segs[0]
    while lo <= hi:
        mid = (lo + hi) // 2
        if segs[mid][0] <= pos:
            best = segs[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    out_start, orig_start, length = best
    delta = pos - out_start
    if delta > length:
        delta = length
    return orig_start + delta


def dewrap(text):
    """Join a hard-wrapped bullet into one line.

    ★ A bullet that wraps is still one sentence. ORCL's RPO label and its
    number are on different lines, and every sentence-scoped matcher in this
    package was blind to that.

    Offsets in the result are NOT document offsets -- use dewrap_mapped and
    to_original where the position is going to be recorded.
    """
    return dewrap_mapped(text)[0]


#: ★ THE WINDOW STOPS AT ITS OWN SENTENCE. A 260-char window past
#: ORCL's RPO bullet ran into the dateline paragraph and collected '10,'
#: '2026' '850' '19.3'; a later label hit put one of those after a level
#: preposition, so the selector saw three competing levels and refused a
#: bullet that was unambiguous on its own. The refusal was right, the
#: candidate set was wrong.
_STOP = re.compile(r'\n\s*\n|(?<=[a-z0-9%])\.\s+(?=[A-Z])|\n\s*--')


#: ★ A VERTICALLY EXPLODED TABLE HAS NO BLANK-LINE BOUNDARY TO CLIP ON.
#: ADBE separates the cells of ONE row with seven blank CRLF lines, so every
#: blank-run rule -- one, two or three newlines -- fires at offset 0 or 1 and
#: returns an empty window. The bound for a tabular row is the sectionAnchor,
#: which the issuer printed, not whitespace.
_STOP_TABLE = re.compile(r'(?:\r?\n\s*){14,}')

#: tabular rows need a WIDE window: the cells of one row are hundreds of
#: characters apart when 45,133 chars are spread over 12,756 lines.
TABLE_WINDOW = 900


def clip(window, kinds=None):
    """Truncate a candidate window at the end of its own region.

    ★★ A BLANK LINE MEANS DIFFERENT THINGS IN DIFFERENT LAYOUTS. In prose it
    ends the sentence; in a vertically exploded table it separates two cells
    of the SAME row, and ADBE puts seven of them there. So the prose rule
    clipped all four guide windows to '' and the selector refused a candidate
    set that was empty by construction.
    """
    kinds = kinds or []
    tabular = ('TABLE' in kinds or 'RANGE' in kinds) and not (
        'PROSE' in kinds or 'WRAPPED' in kinds)
    pat = _STOP_TABLE if tabular else _STOP
    m = pat.search(window or '')
    return (window or '')[:m.start()] if m else (window or '')


def candidates(window, spec):
    """Every numeric candidate in `window`, with its role and unit.

    Each is dict(value_musd, raw, unit, role) where role is 'level' | 'delta'
    | None, decided by the PRECEDING preposition.
    """
    out = []
    for m in _NUM.finditer(window or ''):
        raw = m.group('num')
        if not raw:
            continue
        try:
            v = float(raw.replace(',', ''))
        except ValueError:
            continue
        unit = (m.group('unit') or '').lower()
        is_pct = unit == '%'
        pre = (m.group('pre') or '')
        # look a little further back than the match's own prefix
        start = max(0, m.start() - 34)
        back = (window or '')[start:m.start('num')]
        back = re.sub(r'[\$\d,\.]+\s*$', '', back)
        role = None
        if _LEVEL_PREP.search(back):
            role = 'level'
        elif _DELTA_PREP.search(back):
            role = 'delta'
        # ★★★ A PRINTED PRIOR MARKER OUTRANKS A NEARER LEVEL PREPOSITION.
        # Proximity is a heuristic; a marker the issuer printed is evidence,
        # and where they disagree the printed signal wins. SNOW writes
        # 'up from previous guidance of $5,840 million': 'guidance of' sits
        # nearer the number than 'up from' and won on distance alone, so the
        # row returned the PREVIOUS guidance.
        #
        # ★★ BUT ONLY WITHIN THE SAME CLAUSE. Measured over the corpus, the
        # unbounded form flips 27 level candidates and 14 of them take their
        # marker from the PREVIOUS SENTENCE -- HPE's 'up 112.2% from the
        # prior-year period. Data Center Networking was $382 million' would
        # make 382, a hand-read MATCH, unfillable. A marker only governs a
        # number it precedes with no sentence break between them, which is
        # the positional discipline period.py already states.
        if role == 'level':
            _last = None
            for _pm in _PRIOR_MARK.finditer(back):
                _last = _pm
            if _last is not None and not _CLAUSE_BREAK.search(back[_last.end():]):
                role = 'delta'
        musd = None
        if not is_pct:
            mult = _SCALE.get(unit)
            if mult is not None:
                musd = v * mult
            elif m.group('cur'):
                musd = v          # a bare $ figure: per-share or already $M
        out.append(dict(value=v, value_musd=musd, pct=is_pct, unit=unit,
                        role=role, pos=m.start('num'), raw=raw))
    return out


def doc_unit(spec):
    """The unit AS PRINTED IN THE RELEASE.

    ★ `unit` used to name two different quantities: what the issuer prints and
    what the library stores. HPE prints 12,213 ($M) and stores 12.213 ($B) --
    both correct, 26 rows differ. The reader wants documentUnit; only the
    answer-key comparison wants storedUnit.
    """
    return ((spec or {}).get('documentUnit')
            or (spec or {}).get('unit') or '')


def unit_class(want):
    """'%' | '$' | None -- the CLASS the row is asking for."""
    want = (want or '').strip()
    if want == '%':
        return '%'
    if want.startswith('$'):
        return '$'
    return None


def _unit_ok(cand, spec):
    """Does this candidate match the unit the ROW declares?

    ★★ THE SYMBOL ADJACENT TO THE CANDIDATE DECIDES, not its position and not
    the row's wish. '$1.85' leads with $; '19%' trails with %.
    """
    want = doc_unit(spec)
    if want == '%':
        return cand['pct']
    if want.startswith('$'):
        if cand['pct']:
            return False
        # a '$' row is per-share: a bare small dollar figure, never a magnitude
        if want == '$':
            return cand['unit'] not in ('billion', 'bn', 'million', 'mm',
                                        'trillion')
        return True
    return not cand['pct']



# ══ PERIOD SELECTION ══════════════════════════════════════════════════════
#
# ★ THE SECTION IS THE PERIOD. Guidance lives in a named targets block and
# actuals live in the statements, so fencing by section is both simpler and
# better evidenced than parsing date tokens out of column headers.

def _norm(t):
    return re.sub(r'\s+', ' ', (t or '')).strip().lower()


def section_spans(text, anchors, terminators=None, start_after=None):
    """(start, end) spans, CLOSED BY TEXT THE ISSUER PRINTED.

    ★★★ A SPAN NEEDS A CLOSE, NOT A LENGTH. Every span defect in this build
    was a missing terminator that I answered with a number -- 260 into ORCL's
    dateline, 1,800 straddling ADBE's Q4 and FY tables, a three-newline clip
    against seven blank CRLF lines. A length is a guess about a document I
    have not read; a terminator is a string the issuer printed.

    `start_after` moves the opening past an earlier occurrence of the same
    heading -- ADBE prints 'Fourth Quarter Fiscal 2026' THREE times (EPS,
    operating-margin and tax-rate reconciliations), so narrowing the anchor
    cannot separate them and only an explicit open/close can.
    """
    # ★★★★ A STRING IS ONE ANCHOR, NOT A LIST OF CHARACTERS. MU's live card
    # authored sectionAnchor as a bare string, and iterating it searched for
    # 'F', then 'Q', then '1' -- 47 spans instead of one, the fence landing
    # wherever a letter appears. registry.where_kind has coerced a string to
    # a single-element list since it was written; section_spans never did.
    # Found at pre-flight on a live card three hours before a print.
    if isinstance(anchors, str):
        anchors = [anchors]
    if isinstance(terminators, str):
        terminators = [terminators]
    text = text or ''
    low = text.lower()
    floor = 0
    if start_after:
        i = low.find(_norm(start_after))
        if i >= 0:
            floor = i + len(start_after)

    terms = [_norm(t) for t in (terminators or []) if t]
    out = []
    for a in anchors or []:
        a = _norm(a)
        if not a:
            continue
        start = floor
        while True:
            i = low.find(a, start)
            if i < 0:
                break
            # ★ CLOSE ON THE FIRST TERMINATOR THAT FOLLOWS, never on a length
            end = len(text)
            for t in terms:
                j = low.find(t, i + len(a))
                if j >= 0:
                    end = min(end, j)
            if not terms:
                # no terminator declared: close at the next blank-line block
                # boundary rather than inventing a character count
                m = re.compile(r'(?:\r?\n\s*){10,}').search(text, i + len(a))
                end = m.start() if m else len(text)
            out.append((i, end))
            start = i + 1
    return out


def in_any(pos, spans):
    return any(lo <= pos <= hi for lo, hi in spans)


#: ★ a range pair needs a CURRENCY OR UNIT ANCHOR. SNOW prints '1-800' and
#: '330-6730'; a naked N-N matcher reads phone numbers as guidance.
_RANGE_PAIR = re.compile(
    # ★ THE UNIT SITS BETWEEN THE NUMBER AND THE SEPARATOR:
    #     "$6.80 billion to $6.85 billion"   "$1.12 to $1.22"   "34% to 37%"
    # My first pattern demanded the separator immediately after the figure,
    # so every DOLLAR-MAGNITUDE range failed while percentage ranges passed.
    # ★★ AND BOTH ENDS STAY ANCHORED by a currency symbol or a unit word --
    # SNOW prints '1-800' and '330-6730', and a naked N-N matcher reads phone
    # numbers as guidance.
    r'(?P<a>\$\s?[\d,]+(?:\.\d+)?)\s*(?P<ua>billion|million|bn|mm?\b)?\s*'
    r'(?:to|through|and|–|-)\s*'
    r'(?P<b>\$\s?[\d,]+(?:\.\d+)?)\s*(?P<ub>billion|million|bn|mm?\b)?'
    r'|'
    r'(?P<a2>[\d,]+(?:\.\d+)?)\s*(?P<u2>%)\s*(?:to|through|and|–|-)\s*'
    r'(?P<b2>[\d,]+(?:\.\d+)?)\s*(?P<u3>%)?',
    re.I)


#: '$4.1B +/- $100M', '$4.00 +/- $0.15' -- a CENTRE and a TOLERANCE, which
#: the separator grammar above cannot see at all: there is no 'to', no dash
#: between two figures, and the two halves are not both ends of the range.
_PLUS_MINUS = re.compile(
    r'\$?\s*(?P<c>[\d,]+(?:\.\d+)?)\s*(?P<cu>B|M|K|billion|million|thousand)?\b'
    r'\s*(?:\+/-|±|\+\s*/\s*-)\s*'
    r'\$?\s*(?P<t>[\d,]+(?:\.\d+)?)\s*(?P<tu>B|M|K|billion|million|thousand)?\b',
    re.I)

_PM_SCALE = {'b': 1000.0, 'billion': 1000.0, 'm': 1.0, 'million': 1.0,
             'k': 0.001, 'thousand': 0.001}
_PM_BASE = {'$B': 1000.0, '$M': 1.0, '$K': 0.001}


def plus_minus_pair(window, spec=None):
    """(low, high) from a CENTRE +/- TOLERANCE expression, or None.

    ★★★ THE TWO HALVES CARRY THEIR OWN SCALES. WDC prints
    '$4.1B +/- $100M' on a row that declares documentUnit $M: a centre in
    BILLIONS and a tolerance in MILLIONS, inside one printed cell. Returning
    4.1 would be read as $4.1M -- one condition, two names, with the seam
    inside a single cell rather than between two modules. So each half is
    converted through ITS OWN suffix into the unit the ROW declares.

    ★★ ONLY CONSULTED WHERE THE ROW DECLARES rangeForm PLUS_MINUS. The corpus
    holds exactly two such expressions, both in WDC's guidance table, and a
    bare '4.1 +/- 100' with no suffix on either half is refused rather than
    guessed -- a tolerance whose scale is unknown is not a narrower range, it
    is an unknown one.
    """
    m = _PLUS_MINUS.search(window or '')
    if not m:
        return None
    cf = _PM_SCALE.get((m.group('cu') or '').lower())
    tf = _PM_SCALE.get((m.group('tu') or '').lower())
    if cf is None or tf is None:
        return None
    base = _PM_BASE.get((doc_unit(spec) or '').strip(), 1.0)
    try:
        c = float(m.group('c').replace(',', '')) * cf / base
        t = float(m.group('t').replace(',', '')) * tf / base
    except (TypeError, ValueError):
        return None
    return round(c - t, 6), round(c + t, 6)


#: Grammar that joins a label to its own figures. Transparent to the walk-back
#: below: 'between' and 'of' are not competing labels.
_CONNECTIVE = set(
    'of to be between and or at approximately about totaling total is was '
    'were in the a an for from with expects expected expect range'.split())

#: A cell holding no words: a placeholder, a bare symbol, a footnote marker.
_PLACEHOLDER_CELL = re.compile(
    r'^(?:n/?a|nm|--?|\u2014|\u2013|~|\$|%|\(\d+\))$', re.I)


def _core_words(text):
    """The words of a cell with pure grammar and digits removed."""
    t = re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()
    return ' '.join(w for w in t.split()
                    if w and not w.isdigit() and w not in _CONNECTIVE)


def belongs_to_label(window, at, spec):
    """Does the pair at `at` sit on the row the LABEL matched?

    ★★★ A RANGE WITH NO LABEL IS STILL A RANGE. WDC's revenue row anchored on
    the right sentence and came back holding the midpoint of the OPERATING
    EXPENSES range, reporting candidateCount 1, rejected [], why None. The
    anchor was right and the pair was well formed; nothing asked whether they
    belong to each other. That is the pairs defect at the value level.

    ★★ THE WINDOW ALREADY OPENS AT THE LABEL, so reaching its start is the
    STRONGEST belonging, not the weakest -- the pair sits on the label that
    opened the window. Only a cell that still carries words once grammar is
    stripped is a rival.

    ★ MEASURED BOUNDARY: this refuses a CORRECT pair where ONE PROSE SENTENCE
    CARRIES TWO METRICS. SNOW writes 'Product revenue of $1,588 million to
    $1,593 million, representing 37% to 38% year-over-year growth', and from
    the growth pair the walk-back sees the revenue figures as a rival. That is
    why the row must OPT IN: declared on the two WDC rows it was built for,
    1 gain and 0 losses; applied to every range row, it would break SNOW.
    """
    for cell in reversed(re.split(r'[|\n\r\t]+', window[:at])):
        cell = cell.strip().strip(':').strip()
        if not cell or _PLACEHOLDER_CELL.match(cell):
            continue
        if not re.search(r'[A-Za-z]{2}', cell):
            continue
        core = _core_words(cell)
        if not core:
            continue
        for lab in (spec or {}).get('documentLabels') or []:
            lc = _core_words(lab)
            if lc and (core == lc or core in lc or lc in core):
                return True
        return False
    return True


def range_pair(window, spec=None):
    """(low, high) from an anchored range, or None.

    ★ ANCHORED ON BOTH ENDS BY A UNIT OR CURRENCY. '$6.80 billion to $6.85
    billion' and '34% to 37%' qualify; '1-800' and '330-6730' do not.
    """
    want = unit_class(doc_unit(spec)) if spec else None
    for m in _RANGE_PAIR.finditer(window or ''):
        # ★★ THE UNIT CLASS OF THE RANGE MUST MATCH THE ROW. ORCL prints
        # "between $1.85 and $1.93 ... growth of 19% to 23%" in ONE sentence:
        # both are anchored ranges, both survive role, and only the symbol
        # says which belongs to a ($) row. Taking the first anchored range
        # returned 19.0 for an EPS guide.
        got_pct = bool(m.group('u2') or m.group('u3'))
        got_dol = bool(m.group('a') or m.group('b'))
        if want == '%' and not got_pct:
            continue
        if want == '$' and not got_dol:
            continue
        # ★ AND THE PAIR MUST BELONG TO THE ROW THE LABEL MATCHED. Opt-in:
        # the rows that declare it are the ones whose guidance table puts
        # another row's range inside the same window.
        if (spec or {}).get('rangeMustBelongToLabel') and not belongs_to_label(
                window or '', m.start(), spec):
            continue
        break
    else:
        return None
    a = m.group('a') or m.group('a2')
    b = m.group('b') or m.group('b2')
    if a is None or b is None:
        return None
    try:
        lo = float(re.sub(r'[^\d.]', '', a))
        hi = float(re.sub(r'[^\d.]', '', b))
    except ValueError:
        return None
    if hi < lo:
        lo, hi = hi, lo
    return lo, hi



def adjacent_pair(window, spec):
    """Two adjacent same-unit figures as a low/high pair, or None.

    ★ Used only when the row declares rangeColumns, so the issuer has already
    told us the two columns are a bounded range. Without that declaration two
    adjacent numbers are just two numbers.
    """
    cands = [c for c in candidates(window, spec) if _unit_ok(c, spec)]
    if len(cands) < 2:
        return None
    a, b = cands[0]['value'], cands[1]['value']
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    # a guidance band is narrow: reject a pair that is not plausibly a range
    hi, lo = max(a, b), min(a, b)
    if hi / lo > 1.60:
        return None
    return lo, hi


def column_pair(text, spec, window=900):
    """A low/high pair bound by COLUMN NAME, where the issuer labels them.

    ★ APP prints 'Low' and 'High' as literal column headers. Binding by name
    is the cleanest anchor available and needs no separator grammar at all.
    """
    cols = (spec or {}).get('rangeColumns') or []
    if len(cols) != 2:
        return None
    lo_i = (text or '').lower().find(_norm(cols[0]))
    hi_i = (text or '').lower().find(_norm(cols[1]))
    if lo_i < 0 or hi_i < 0 or abs(hi_i - lo_i) > 120:
        return None
    return ('COLUMN', lo_i, hi_i)




#: THE ISSUERS' OWN WORDS, collected from the corpus -- 38 declarations over
#: 7 of 8 releases. AVGO wraps the phrase across three lines, so the tail
#: must be allowed to cross a newline.
#: ★★★ THE PARENTHESES WERE LOAD-BEARING AND ONLY ONE MODULE THOUGHT SO.
#: tables._SCALE_HEADER has always written the paren as OPTIONAL; this pattern
#: required it. HPE prints every one of its 18 denomination headers BARE --
#: 'July 31, 2025 In millions, except per share amounts' -- so it has ZERO
#: parenthesised headers and this reader saw none of them. One condition, two
#: names, and the module that could see the header was not the one that
#: needed it: HPE's free cash flow came back as 958 with documentUnit $B,
#: which is 958 BILLION dollars, while 'In millions' sat 694 chars above it.
#: ★★ AND THE RELAXATION HAS ONE FALSE POSITIVE TO REFUSE. Making the paren
#: optional lets the pattern match the SUBSTRING 'in millions)' inside ADBE's
#: '(Shares in millions)' -- a SHARE COUNT, which would then denominate every
#: dollar row beneath it. The lookbehinds refuse that: the phrase must start a
#: word and must not follow 'shares'.
#: Measured: 18 newly found headers, all HPE, 0 share-header false positives,
#: 1 row moves (958.0 -> 0.958) and no row that matches today changes.
_DENOM_RE = re.compile(
    r'(?<![A-Za-z])(?<!shares\s)(?<!Shares\s)'
    r'\(?\s*(?:\$\s*)?(?:in|amounts\s+in|dollars\s+in)\s+'
    r'(thousand|million|billion)s?\b[^)\n]{0,40}\)?', re.I)
_DENOM_SCALE = {'thousand': '$K', 'million': '$M', 'billion': '$B'}
_MUSD = {'$K': 0.001, '$M': 1.0, '$B': 1000.0}


def denomination(text, pos):
    """(scale, phrase, declPos) governing `pos`, or None.

    A header governs from where it is printed until the next one. Silence is
    NOT a default: None means the document never said, and the caller must
    fall back to the spec and record that it did.
    """
    got = None
    for m in _DENOM_RE.finditer(text or ''):
        if m.start() <= pos:
            got = (_DENOM_SCALE[m.group(1).lower()],
                   ' '.join(m.group(0).split())[:60], m.start())
        else:
            break
    return got


def sig_digits(raw):
    """Significant digits AS PRINTED. 1,923,686 -> 7; 1,924 -> 4; 2.97 -> 3."""
    t = re.sub(r'[^0-9.]', '', str(raw or ''))
    if not t:
        return 0
    whole, _, frac = t.partition('.')
    whole = whole.lstrip('0')
    if whole:
        return len(whole) + len(frac)
    return len(frac.lstrip('0')) or len(frac)


def _last_place(value, digits):
    """The magnitude of the printed number's last significant digit."""
    if not value or not digits:
        return 0.0
    return 10.0 ** (math.floor(math.log10(abs(value))) - digits + 1)


def same_number(a_val, a_digits, b_val, b_digits):
    """True when two printings agree within the COARSER one's last digit.

    1,923,686 thousands and 1,924 millions are ONE number printed twice:
    |1923.686 - 1924| = 0.314, and the coarser prints to the nearest 0.5.
    """
    if a_val is None or b_val is None:
        return False
    tol = max(_last_place(a_val, a_digits), _last_place(b_val, b_digits)) / 2.0
    return abs(a_val - b_val) <= tol


def collapse_precision(pool):
    """Drop printings that a MORE PRECISE printing of the same number covers.

    Compares on the $M-normalised value, which is the only frame in which the
    thousands table and the millions summary are recognisable as one number.
    """
    ranked = sorted(pool, key=lambda c: -c.get('sigDigits', 0))
    kept = []
    for c in ranked:
        cov = None
        for k in kept:
            if same_number(k.get('musd'), k.get('sigDigits', 0),
                           c.get('musd'), c.get('sigDigits', 0)):
                cov = k
                break
        if cov is None:
            kept.append(c)
        else:
            cov.setdefault('coveredPrintings', []).append(c.get('raw'))
    order = {id(c): i for i, c in enumerate(pool)}
    return sorted(kept, key=lambda c: order.get(id(c), 0))


def _record_period(record):
    """(fiscalQuarter, fiscalYear) from a library record, or (None, None).

    DERIVED FIELDS, INTS, ON 89 OF 89 RECORDS -- and no string fallback. The
    raw `year` spells itself three ways and `quarter` fifteen; parsing them at
    the point of use is what made one field mean three things. ARM proves the
    derived pair is not cosmetic: its id and quarter say FY2027 while `year`
    says 2026, so a parser would hunt FY26 columns in an FY27 release and
    resolve nothing -- surfacing as "candidates tie", the message that has
    hidden five separate defects.
    """
    if not isinstance(record, dict):
        return (None, None)
    q = record.get('fiscalQuarter')
    y = record.get('fiscalYear')
    return (q if isinstance(q, int) else None,
            y if isinstance(y, int) else None)


def _cell_unit_ok(is_pct, spec):
    """Does a table cell's shape match the unit the row declares?

    A percentage cell cannot fill a $ row and a magnitude cell cannot fill a
    (%) row. The prose path has always enforced this through _unit_ok; the
    column path did not, which only stayed harmless while the rows whose
    first cell is a percentage produced no cells at all.
    """
    want = unit_class((spec or {}).get('documentUnit')
                      or (spec or {}).get('unit'))
    if want == '%':
        return bool(is_pct)
    if want == '$':
        return not is_pct
    return True


#: readers that crashed this run, as (reader, exception) -- for the report
READER_FAILURES = []


def guarded(label, fn, *args, **kwargs):
    """Run a reader; on ANY exception return None and record why.

    The guard is LOUD. A blanket try/except that swallows everything is how a
    defect lives for a year, so the failure is appended to READER_FAILURES
    and the caller turns it into a refusal whose reason NAMES the reader and
    the exception. A crash must read as a crash, never as 'no candidate'.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:                            # noqa: BLE001
        note = 'READER FAILED in %s: %s: %s' % (
            label, type(exc).__name__, str(exc)[:120])
        READER_FAILURES.append(note)
        return None


#: a body with fewer than one line break per this many characters carries
#: no readable structure. MEASURED, NOT PICKED: across 12 captured frames
#: BUS runs 3-12 chars per line, PRN 78-112, and MU on PZM is 1,859. The
#: threshold sits an order of magnitude clear of both sides.
MAX_CHARS_PER_LINE = 400

#: ★★★★ A FLOOR WAS PROPOSED HERE AND THE PREMISE WAS FALSE. KEPT AS A
#: MEASUREMENT, DELIBERATELY NOT WIRED.
#:
#: The reasoning was: ORCL's exhibit renders ONE TABLE CELL PER LINE --
#: 7,496 lines, 82.6% blank -- so no horizontal reader can assemble a row,
#: and unlike the ceiling it fails by PUBLISHING A FRAGMENT rather than
#: refusing (0.001 against a key of 6.582, three of the four mismatches in
#: the five-spec corpus run). Measured over 109 exhibits, 20 separated the
#: 12 fragmented documents from a healthy band at p25=45.5.
#:
#: ★★★ THEN THE WIRE FIXTURES SAID NO. The real HPE and SNOW wire bodies
#: are 2.8 and 2.4 CHARS PER LINE -- more fragmented than ORCL -- and the
#: table reader reads them CORRECTLY today:
#:
#:     HPE wire, 'Net revenue\n\n\n$\n\n\n12,213\n\n\n', 94% blank lines
#:     -> tables.row_value_cells_at returns 12213.0, and has all along
#:
#: So one-cell-per-line is NOT an unreadable shape; it is a shape this
#: reader already handles. The floor would have refused 18 assertions'
#: worth of working rows on real wire bodies. ORCL's mismatches have some
#: other cause, still unfound.
#:
#: THE CORPUS ALONE COULD NOT HAVE CAUGHT THIS: the false positives live
#: in the WIRE fixtures, which is where the shape is most extreme.
MIN_CHARS_PER_LINE = 20


def chars_per_line(text):
    """How much text sits between line breaks. Large means NO STRUCTURE."""
    if not text:
        return 0.0
    return float(len(text)) / max(1, text.count(chr(10)))


def is_fragmented(text):
    """MEASUREMENT ONLY -- one cell per line. NOT a refusal condition.

    ★★★ NOTHING CALLS THIS AS A GATE, AND THAT IS THE FINDING. See
    MIN_CHARS_PER_LINE: the real HPE and SNOW wire bodies sit at 2.8 and
    2.4 chars per line and their table rows read correctly, so a low ratio
    does not mean unreadable. Kept so the shape can be REPORTED -- it is
    still a useful thing to know about a document -- and so the next person
    to propose this floor finds the disproof instead of re-deriving it.
    """
    cpl = chars_per_line(text)
    return 0 < cpl < MIN_CHARS_PER_LINE


def has_line_structure(text):
    """Can a TABLE reader work on this body at all?

    ★★★★ EVERY READER BUILT THIS MONTH DEPENDS ON LINE STRUCTURE. hgrid reads
    dash rules, sgrid reads stacked cells, vtables reads columns,
    is_section_heading reads blank-line adjacency, definitional_spans and
    guide_sections walk lines. MU's Globe Newswire body has TEN newlines in
    18,592 characters and arrives as one continuous string:

        Revenue$61.5 billion +- $1.5 billion$61.5 billion +- $1.5 billion

    You cannot tell from that where the GAAP column ends and Non-GAAP
    begins. The values are IDENTICAL AND CONCATENATED, and the only reason
    anyone knows there are two columns is that they read the PDF.

    ★★ SO THIS DETECTS AND REFUSES. It does not reflow: reflowing would
    INVENT a boundary on the rows that decide trades, and it would be a
    sixth coordinate frame -- one WE fabricated rather than one the pipeline
    created. hgrid is not wrong here; its input is empty.
    """
    return chars_per_line(text) <= MAX_CHARS_PER_LINE


def cell_offset(text, line_idx, x=0, stripped=True):
    """Document offset of column `x` on the STRIPPED line `line_idx`.

    THE READERS WORK ON STRIPPED LINES. hgrid and sgrid are handed
    [l.strip() for l in body.split(chr(10))], so a cell's x is an offset into
    the stripped line and the leading whitespace has to be put back. Skipping
    that is the dewrap shift again in a different frame: a coordinate right
    where it was computed and wrong where it is recorded.
    """
    if not isinstance(line_idx, int) or not text:
        return None
    lines = text.split(chr(10))
    if not (0 <= line_idx < len(lines)):
        return None
    base = 0
    for k in range(line_idx):
        base += len(lines[k]) + 1
    raw = lines[line_idx]
    lead = (len(raw) - len(raw.lstrip())) if stripped else 0
    return min(len(text), base + lead + (x or 0))


def column_value(text, spec, label_pos, record=None):
    """The REPORTED-column cell of the table row at `label_pos`, or None.

    ★★ DELEGATES TO vtables.column_map. That reader already classifies the
    header strata into REPORTED / SEQUENTIAL / PRIOR_YEAR_Q / YTD /
    PRIOR_YEAR_YTD, refuses on a cardinality mismatch, and is pinned by an
    anti-vacuous probe. HPE's header runs July 31 2026 / April 30 2026 /
    July 31 2025 -- the SEQUENTIAL quarter BETWEEN current and year-ago at
    0.87x -- and column_map is the thing that already knows that.

    ★ NEVER BY INDEX. The spec says so and the corpus proves it: ORCL's
    supplemental grid puts a FY TOTAL in the fifth column, and
    reconciliations are RAGGED -- fewer cells than the header declares.
    """
    from . import tables, vtables
    #: THE CLASSIFIER NEEDS THE RECORD'S OWN PERIOD. Without it
    #: column_classes returns UNRESOLVED for every column and the
    #: selector refuses -- silently, because the caller blames the tie.
    rq, ry = _record_period(record)
    if ry is None:
        return dict(value=None, columnIndex=None, columnClasses=None,
                    note='no record period supplied: the column header cannot be classified')
    # ONE CONVENTION FOR BOTH. splitlines() drops CRLF's two characters and
    # `len(line) + 1` restores one, so on a CRLF document the index drifts a
    # character per line -- ADBE carries 12,755 of them and the selector read
    # a row hundreds of lines away. Split on the newline, count the newline.
    body = text or ''
    # THE ISSUER DREW THE COLUMNS AND STRIPPING ERASES THEM. Each line was
    # stripped INDEPENDENTLY, so AVGO's header at indent 36, its rule at 25
    # and its data row at 1 were shifted by three different amounts and
    # stopped lining up -- in a reader whose entire mechanism is that a
    # cell's column falls inside a dash run.
    lines = [l.rstrip() for l in body.split(chr(10))]
    idx = body.count(chr(10), 0, label_pos)
    # HORIZONTAL first: on a space-aligned row the label and every column sit
    # on ONE line, and the vertical reader walks DOWN into the next label.
    # ORCL and AVGO are horizontal; the other six are vertical.
    # THE SPEC OWNS THE LAYOUT. A sniff that can disagree with it is a
    # second authority on one condition, which is the defect this build
    # keeps finding. ORCL HORIZONTAL, ADBE VERTICAL, on all 19 TABLE rows.
    if (spec or {}).get('tableLayout') == 'HORIZONTAL':
        # ★ THE 2-D GRID, READ BY COLUMN POSITION. The issuer draws the
        # columns with a rule line and every cell falls inside one, so period
        # x basis x currency cross without an index anywhere. ORCL's fifth
        # column is a FY total and AVGO's fourth is the non-GAAP quarter;
        # only the header can tell them apart.
        from . import hgrid as _hg
        _sel = guarded('hgrid.select', _hg.select, lines, idx, spec,
                       is_boundary=_axes.is_table_boundary) or {}
        if _sel.get('value') is not None:
            _raw = str(_sel['value'])
            _pct = '%' in _raw
            _num = re.sub(r'[^0-9.\-]', '', _raw.replace('(', '-'))
            try:
                _v = float(_num)
            except ValueError:
                _v = None
            if _v is not None and _cell_unit_ok(_pct, spec):
                return dict(value=_v, pct=_pct, columnIndex=None,
                            columnClasses=_sel.get('description'),
                            cellAxes=_sel.get('cellAxes'),
                            cellPos=cell_offset(body, _sel.get('cellLine'),
                                                _sel.get('cellX'),
                                                stripped=False))
            return None
        return None
        h = tables.h_column_value(lines, idx, rq, ry)
        if h and h.get('value') is not None and _cell_unit_ok(False, spec):
            return dict(value=h['value'], pct=False,
                        columnIndex=h.get('columnIndex'),
                        columnClasses=h.get('columnClasses'))
        return None
    # ★ THE STACKED SHAPE, where the row's cells are stacked BELOW its label
    # one per line and a basis group owns each half. Engaged only where the
    # row declares a basis: SNDK's guide rows resolve correctly through the
    # prose path today and their label hits land on the ACTUALS block, so a
    # stacked read there would replace 10,550 with 5,950 -- a prior-year cell.
    _want_basis = (spec or {}).get('basis') or next(
        (a.get('want') for a in ((spec or {}).get('columnAxes') or {})
         .get('axes', []) if (a.get('axis') or '').upper() == 'BASIS'), None)
    if _want_basis and (spec or {}).get('basisLocation') != 'ROW_LABEL':
        from . import sgrid as _sg
        _st = guarded('sgrid.select', _sg.select, lines, idx, spec) or {}
        if _st.get('value') is not None and _cell_unit_ok(_st.get('pct'), spec):
            return dict(value=_st['value'], pct=_st.get('pct'),
                        columnIndex=None, columnClasses=_st.get('groups'),
                        cellAxes=_st.get('cellAxes'),
                        cellPos=cell_offset(body, _st.get('cellLine'),
                                            _st.get('cellX')))
    cells = guarded('tables.row_value_cells_at',
                    tables.row_value_cells_at, lines, idx) or []
    if len(cells) < 2:
        return None
    got = guarded('vtables.column_map', vtables.column_map, lines, idx,
                  len(cells), rq, ry, values=[c[0] for c in cells]) or {}
    i = got.get('valueIndex')
    if i is None or i >= len(cells):
        return None
    # THE SELECTED CELL MUST PASS THE ROW'S UNIT CLASS. The prose candidates
    # are filtered by _unit_ok and the column path was not, so a $ row could
    # take a percentage cell -- which is exactly what allowing inline percent
    # cells would have handed the two APP rows.
    if not _cell_unit_ok(cells[i][1], spec):
        return None
    # ★ vtables CLASSIFIED EVERY COLUMN and the selector picked index i, so
    # classes[i] is the SELECTED cell's period. Computed since vtables was
    # written, returned as a list, and never indexed by anybody.
    _cls = got.get('classes') or []
    return dict(value=cells[i][0], pct=cells[i][1], columnIndex=i,
                columnClasses=_cls,
                # ★ THE VERTICAL READER NEVER LOOKS FOR A BASIS. Its
                # strata are PERIOD classes, so a None here is OUR blindness,
                # not the issuer's silence -- and the strict arm must not
                # refuse a priority-1 row for a header it never read.
                cellAxes=dict(basis=None, currency=None,
                              basisState='UNREAD_BY_GRID',
                              period=(_cls[i] if i < len(_cls) else None),
                              headers=list(_cls)),
                cellPos=cell_offset(body, cells[i][2]))



def _lands_in_table(src, hit):
    """Does this label hit sit on a line that parses as a table row?"""
    lines = getattr(_lands_in_table, '_cache', None)
    key = id(src)
    if not lines or lines[0] != key:
        lines = (key, [l.strip() for l in src.split(chr(10))])
        _lands_in_table._cache = lines
    idx = src.count(chr(10), 0, hit[0])
    return bool(_tables.row_value_cells(lines[1], idx))



#: THE ISSUERS' OWN PHRASES. 'cc' is NOT here: two characters against a
#: six-character whole-token floor, and n=0 in the corpus.
_CURRENCY_RE = {
    'USD': re.compile(r'in\s+U\.?S\.?\s*(?:D|dollars)\b|in\s+USD\b', re.I),
    'CONSTANT_CURRENCY': re.compile(r'(?:in\s+)?constant\s+currency', re.I),
}

#: the contrast the issuer builds to mark the exception: "13% growth, OR 12%
#: in constant currency". The qualified alternative starts at this word.
#: ★ 'and' IS NOT HERE. It belongs to the RANGE grammar -- "between $1.83
#: and $1.91" -- and using it as a contrast marker cut ORCL's range in half,
#: leaving '$1.93' where '$1.85 and $1.93' was needed. Which axis owns the
#: token, asked of the data: the range owns 'and', the contrast owns 'or'.
_CONTRAST = re.compile(r'(?<![A-Za-z])(?:or|versus|vs\.?|compared\s+to)'
                       r'(?![A-Za-z])', re.I)

REPORTED = 'REPORTED'


def currency_marks(window):
    """[(start, end, currency)] for every qualifier in the window, in order."""
    out = []
    for cur, rx in _CURRENCY_RE.items():
        for m in rx.finditer(window or ''):
            out.append((m.start(), m.end(), cur))
    out.sort()
    return out


def currency_spans(window):
    """[(start, end, currency)] — the VALUE regions each qualifier governs.

    THE QUALIFIER TRAILS THE VALUE, measured 29 to 4 in this corpus, so a
    governed region runs from the contrast word that introduces it (or the
    previous qualifier) up to the qualifier itself. Everything outside every
    region is REPORTED.
    """
    marks = currency_marks(window)
    spans = []
    prev_end = 0
    for st, en, cur in marks:
        lo = prev_end
        seg = (window or '')[prev_end:st]
        last = None
        for m in _CONTRAST.finditer(seg):
            last = m
        if last is not None:
            lo = prev_end + last.end()
        spans.append((lo, st, cur))
        prev_end = en
    return spans


def currency_of(spans, pos):
    """Which currency governs a position — REPORTED when no region covers it."""
    for lo, hi, cur in spans:
        if lo <= pos < hi:
            return cur
    return REPORTED


def currency_mask(window, spec):
    """(masked window, why) — regions this row's currency does NOT own, blanked.

    MASKED, NOT SLICED: the blanks are the same length as what they replace,
    so every offset in the window stays valid. Slicing moves the frame, and a
    frame moved by hand is what put every header lookup on the dateline.
    """
    spans = currency_spans(window)
    want = (spec or {}).get('currencyBasis')
    if not spans:
        return window, None                    # nothing qualified: REPORTED
    kinds = {c for _lo, _hi, c in spans}
    if not want:
        if len(kinds) > 1:
            # ★ BOTH PRINTED AND NEITHER DECLARED. No default is safe: one
            # ORCL release wants USD on its EPS guide and CONSTANT CURRENCY
            # on its cloud growth guide.
            return None, ('the document prints this figure in %s and the row '
                          'declares no currencyBasis'
                          % ' and '.join(sorted(kinds)))
        # ★ A SINGLE QUALIFIER IS NOT AMBIGUOUS. The issuer marked the
        # exception with a contrast; the unqualified figure is REPORTED.
        return window, None
    chars = list(window)
    if want == REPORTED:
        for lo, hi, _cur in spans:
            for i in range(lo, min(hi, len(chars))):
                chars[i] = ' '
        return ''.join(chars), None
    if want not in kinds:
        return None, ('the row declares currencyBasis %s and the document '
                      'qualifies this figure only as %s'
                      % (want, ' and '.join(sorted(kinds))))
    keep = [(lo, hi) for lo, hi, cur in spans if cur == want]
    for i, _ch in enumerate(chars):
        if not any(lo <= i < hi for lo, hi in keep):
            chars[i] = ' '
    return ''.join(chars), None



_SENTENCE_END = re.compile(r'(?<=[.:;])\s|\n\s*\n')


def _governing_sentence(text, pos):
    """The clause that GOVERNS a candidate, not the span that contains it.

    period.classify_candidate is explicit about needing the enclosing sentence
    or bullet: SNOW's guide value carries no marker inside its own span, which
    is exactly why the row reads the wrong number.
    """
    if not isinstance(pos, int) or not text:
        return ''
    lo = 0
    for m in _SENTENCE_END.finditer(text, 0, pos):
        lo = m.end()
    m = _SENTENCE_END.search(text, pos)
    hi = m.start() if m else min(len(text), pos + 400)
    return text[lo:hi]


def guidance_contamination(text, cand, spec, quarter=None):
    """Why a REPORTED row may not take this candidate, or None.

    ★ ONE DIRECTION ONLY, and it is the one that fails. A REPORTED row taking
    a value out of a guidance sentence is measured at 1 occurrence and 0 false
    positives across the corpus; the reverse -- a guide row reading a reported
    sentence -- costs two correct values to catch nothing, because the
    classifier misreads both of those sentences.
    """
    want = (spec or {}).get('period')
    if {'FY_GUIDE': 'GUIDE_FY'}.get(want, want) != _period_mod.REPORTED:
        return None
    frag = _governing_sentence(text, cand.get('gpos'))
    if not frag:
        return None
    klass = _period_mod.classify_candidate(frag, quarter)
    if klass in (_period_mod.GUIDE_FY, _period_mod.GUIDE_NEXT_Q):
        return ('the row is REPORTED and this figure sits in a %s sentence: %r'
                % (klass, ' '.join(frag.split())[:90]))
    return None



def _range_offset(window, low, high):
    """Where the range's LOW endpoint is printed inside `window`, or None.

    ★ A RANGE ROW RECORDED ITS POSITION AT THE LABEL. On AVGO's Q4 guide the
    figure sits a sentence after the label, inside a CEO quote, so anything
    reading the governing clause at that position read the wrong sentence.
    The value's location must be the value's location.
    """
    for val in (low, high):
        if val is None:
            continue
        for txt in ('%g' % val, '%.1f' % val, '%.2f' % val,
                    '{:,.0f}'.format(val) if abs(val) >= 1000 else None):
            if not txt:
                continue
            j = (window or '').find(txt)
            if j >= 0:
                return j
    return None



#: a LITERAL period phrase -- the issuer named the period in this clause.
#: Anything outside this set means the class came from position, section,
#: proximity or a default, and nobody printed it.
_PERIOD_PHRASE = re.compile(
    r'\b(?:first|second|third|fourth)\s+quarter\b'
    r'|\bfiscal\s+(?:year\s+)?\d{2,4}\b'
    r'|\b(?:three|six|nine|twelve)\s+months\s+ended\b'
    r'|\bfull[-\s]year\b|\bQ[1-4]\b|\bFY\s?\d{2,4}\b'
    r'|\byear[-\s]to[-\s]date\b', re.I)


#: a heading does not end a sentence
_ENDS_SENTENCE = re.compile(r'[.;:]\s*$')


def is_heading(line):
    """Is this line a SECTION HEADING rather than prose or a data row?

    Short, word-bearing, not sentence-terminated, and not mostly figures.
    HPE prints 'Fiscal 2026 Fourth Quarter Outlook' and 'Fiscal 2026 Full
    Year Outlook' exactly this way, and they are the only thing in the
    document that says which period the clauses beneath them describe.
    """
    t = (line or '').strip()
    if not t or len(t) > 80 or _ENDS_SENTENCE.search(t):
        return False
    words = [w for w in t.split() if any(c.isalpha() for c in w)]
    if not (1 <= len(words) <= 10):
        return False
    figs = sum(1 for w in t.split() if any(c.isdigit() for c in w))
    return figs * 2 <= len(t.split())


#: THE NON-GAAP DEFINITIONAL BLOCK, which every US release carries BY
#: CONVENTION rather than by issuer. It NAMES every metric and PRINTS NO
#: NUMBERS, so a label matching there has matched a DEFINITION, not a row.
#:
#: THE MEASUREMENT: 4 spans across 8 documents, digit density 0.0% to 0.6%.
#: A definitional block prints no figures, so that density is the check that
#: no RECONCILIATION table was caught by mistake.
#:
#: 'RECONCILIATION' IS DELIBERATELY ABSENT. "Exclude this section" conflates
#: two operations and for that block the correct answers are OPPOSITE: its
#: LABELS are definitional noise, its VALUES are the authority. One flag
#: cannot express both, so this governs LABEL MATCHING ONLY, never
#: value-taking.
DEFINITIONAL = re.compile(
    r'^\s*(?:use of\s+)?(?:certain\s+)?non[- ]gaap financial '
    r'(?:measures|information)\s*:?\s*$'
    r'|^\s*about non[- ]gaap(?: financial measures)?\s*:?\s*$', re.I)


def definitional_spans(text):
    """[(start, end)] for each non-GAAP definitional block.

    CLOSED AT THE NEXT HEADING, never by a length.
    """
    lines = (text or '').split(chr(10))
    offs, run = [], 0
    for ln in lines:
        offs.append(run)
        run += len(ln) + 1
    out = []
    for i, ln in enumerate(lines):
        if not DEFINITIONAL.match(ln.strip()):
            continue
        end = len(text or '')
        for j in range(i + 1, len(lines)):
            if is_heading(lines[j]) and not DEFINITIONAL.match(
                    lines[j].strip()):
                end = offs[j]
                break
        out.append((offs[i], end))
    return out


#: a data bullet, not a section heading
_BULLET = re.compile(r'^\s*(?:--+|[-*•–])\s')
#: a heading NAMES a section; a line carrying a FIGURE is reporting one
_HAS_FIGURE = re.compile(r'[$\u00a3\u20ac]\s*\d|\d\s*%'
                         r'|\bbillion\b|\bmillion\b', re.I)


def is_section_heading(lines, k):
    """Is line `k` a SECTION HEADING, judged STRUCTURALLY?

    is_heading ALONE OVER-TRIGGERS ON HARD-WRAPPED PROSE. MDB wraps at
    about 66 characters, so 54 of its lines passed the short-line test,
    and heading_above would have handed the period classifier
    '-- Revenue: Total revenue was $771.8 million for the second quarte'
    as the section a value sits under. The eight spec'd documents are
    double-spaced, so the corpus could never have shown it -- WHICH CODE
    PATHS GET EXERCISED IS DECIDED BY WHICH ISSUERS WE HAPPENED TO SPEC.

    Three structural discriminators, none of them a word list:
      - ADJACENT TO A BLANK LINE: a heading stands alone
      - not a BULLET: a data point is not a section
      - carries NO FIGURE: a line reporting a number is reporting one,
        not naming a section

    MDB 54 -> 6, and the six are the real ones, including 'Third Quarter
    Fiscal 2027 Guidance'. HPE's three Outlook headings survive.
    """
    if not (0 <= k < len(lines)):
        return False
    line = lines[k]
    if not is_heading(line):
        return False
    if _BULLET.match(line) or _HAS_FIGURE.search(line):
        return False
    prev = lines[k - 1].strip() if k > 0 else ''
    nxt = lines[k + 1].strip() if k + 1 < len(lines) else ''
    if prev == '' or nxt == '':
        return True
    # A RULE THAT NEEDS BLANK LINES CANNOT BE APPLIED WHERE THERE ARE NONE.
    # dewrap_mapped joins wrapped prose, so the dewrapped frame has almost
    # no blank lines at all -- and requiring adjacency there silently lost
    # HPE's 'Fiscal 2026 Full Year Outlook' and refused a derived hero. The
    # FIFTH frame defect: raw, dewrapped, stripped, kept, and now a rule
    # whose evidence exists in one frame and not the other. Where the
    # neighbourhood has no blanks the test cannot discriminate, so it is not
    # applied; the bullet and figure tests still are.
    near = [lines[j].strip() for j in range(max(0, k - 3),
                                            min(len(lines), k + 4))]
    return not any(x == '' for x in near)


def heading_above(text, pos, max_lines=400):
    """The nearest preceding section heading, or ''.

    ★ THE FIRST HEADING FOUND WALKING UP *IS* THE SECTION. No length is
    chosen: the walk stops at the heading or at the top of the document,
    which is the same close/no-length rule section_spans already follows.
    """
    if not isinstance(pos, int) or not text:
        return ''
    lines = text.split(chr(10))
    idx = text.count(chr(10), 0, pos)
    for k in range(idx, max(-1, idx - max_lines), -1):
        if k != idx and is_section_heading(lines, k):
            return lines[k].strip()
    return ''


def governing_context(text, pos):
    """The clause PLUS the section heading it sits under.

    ★★★ IN A DOCUMENT, STRUCTURE CARRIES PERIOD AND THE SENTENCE DOES NOT.
    HPE's FY26 guide sentence names no period at all -- 'HPE is raising both
    GAAP diluted net EPS ... and non-GAAP diluted net EPS(1) to be in the
    range of $3.75 to $3.85' -- so it classified GUIDE_NEXT_Q, identically
    to the Q4 sentence, and INFERRED. The heading above it says 'Fiscal 2026
    Full Year Outlook'. Same shape as cellAxes for tables: the evidence was
    in the structure and the reader was only ever shown the text.
    """
    frag = _governing_sentence(text, pos)
    head = heading_above(text, pos)
    return (head + '. ' + frag) if head else frag


#: 'gaap' NOT preceded by 'non-' or 'non ' -- the negation CONTAINS the token
_BARE_GAAP_RE = re.compile(r'(?<!non-)(?<!non )gaap', re.I)
_NON_GAAP_RE = re.compile(r'non[- ]gaap', re.I)


def basis_at(text, pos):
    """Which basis governs the value at `pos`, or None.

    ★★★ THE QUALIFIER LEADS THE VALUE, which is the MIRROR of the currency
    rule. currency_spans exists because a currency qualifier TRAILS its
    figure ('13% growth, or 12% in constant currency', measured 29 to 4).
    A basis qualifier leads it:

        'Q1 GAAP earnings per share increased to $1.56, up 55%, and
         non-GAAP earnings per share climbed to $1.92, up 30%.'

    So the governing basis is the LAST basis word before the value, within
    the value's own sentence. The mechanism was built for one axis and never
    for the other, which is why a clause naming both bases scored VACUOUS and
    the basis check went blind on exactly the sentences that carry both.

    ★ DOCUMENT COORDINATES THROUGHOUT. Prefixing a heading and then indexing
    into the joined string is the frame defect this build has logged three
    times; the scan runs on `text` itself.
    """
    if not isinstance(pos, int) or not text:
        return None
    lo = 0
    for m in _SENTENCE_END.finditer(text, 0, pos):
        lo = m.end()
    seg = text[lo:pos]
    last_non = None
    for m in _NON_GAAP_RE.finditer(seg):
        last_non = m
    last_bare = None
    for m in _BARE_GAAP_RE.finditer(seg):
        last_bare = m
    if last_non is None and last_bare is None:
        return None
    if last_non is None:
        return 'GAAP'
    if last_bare is None or last_non.start() > last_bare.start():
        return 'non-GAAP'
    return 'GAAP'


def period_basis(fragment):
    """('EXPLICIT', phrase) when the issuer named the period, else INFERRED."""
    m = _PERIOD_PHRASE.search(fragment or '')
    return ('EXPLICIT', m.group(0)) if m else ('INFERRED', None)


def _period_evidence(text, spec, pos, quarter=None):
    """READ | ABSENT_IN_DOCUMENT | UNREAD | NOT_GUIDE for a row's period.

    ★★★ A FENCE LOCATES; IT DOES NOT ANNOUNCE THAT IT IS GUIDANCE. ADBE[3]
    fences to 'Fourth Quarter Fiscal 2026', which names the period plainly,
    and classify_candidate returns UNRESOLVED for it because that function
    wants a guidance VERB -- while ADBE[2]'s 'fourth quarter FY2026 targets'
    classifies, purely because it happens to carry the word 'targets'.
    Refusing ADBE[3] on that difference would be a FALSE REFUSAL.
    So an anchor on a row that ALREADY DECLARES a guide period only has to
    supply the SCOPE, and period.py's own quarter/year precedence is what
    reads it.

    ★★ AND ABSENT_IN_DOCUMENT REQUIRES POSITIVE EVIDENCE THAT THE READER
    LOOKED, exactly as the basis ruling required.
    """
    want = (spec or {}).get('period')
    want = {'FY_GUIDE': _period_mod.GUIDE_FY}.get(want, want)
    if want not in (_period_mod.GUIDE_FY, _period_mod.GUIDE_NEXT_Q):
        return 'NOT_GUIDE'
    for anchor in ((spec or {}).get('sectionAnchor') or []):
        if _period_mod._QUARTER_SCOPE.search(anchor or '') or                 _period_mod._WHOLE_YEAR.search(anchor or ''):
            return 'READ'
        if _period_mod.classify_candidate(anchor, quarter) !=                 _period_mod.UNRESOLVED:
            return 'READ'
    if not isinstance(pos, int) or not text:
        return 'UNREAD'
    frag = governing_context(text, pos)
    if not frag:
        return 'UNREAD'
    if _period_mod.classify_candidate(frag, quarter) !=             _period_mod.UNRESOLVED:
        return 'READ'
    if _period_mod._QUARTER_SCOPE.search(frag) or             _period_mod._WHOLE_YEAR.search(frag):
        return 'READ'
    # the reader looked at the anchor, the clause AND its section heading,
    # and none named a period: that is a fact about the RELEASE
    return 'ABSENT_IN_DOCUMENT'


def period_conflict(text, pos, spec, quarter=None):
    """Why this row may not take a value at `pos`, or None.

    ★★★ EXPLICIT MAY EXCLUDE; INFERRED MAY ONLY RANK. A classification the
    issuer's own words support is evidence and can refuse a value; one
    derived from position or proximity is advisory, because the reader of
    the evidence is exactly what was wrong the last three times this was
    measured.
    """
    want = (spec or {}).get('period')
    if not want:
        return None
    want = {'FY_GUIDE': _period_mod.GUIDE_FY}.get(want, want)
    frag = governing_context(text, pos)
    if not frag:
        return None
    klass = _period_mod.classify_candidate(frag, quarter)
    if klass in (_period_mod.UNRESOLVED, want):
        return None
    basis, phrase = period_basis(frag)
    if basis != 'EXPLICIT':
        return None                 # advisory only: it may rank, not exclude
    return ('the row is %s and the issuer marked this clause %s (%r): %r'
            % (want, klass, phrase, ' '.join(frag.split())[:80]))


def value_for(text, row, window=260, record=None):
    """One cell, guarded. See _value_for for the reader itself.

    ★★★ THE OUTER BOUNDARY IS THE ONE THAT SAVES THE CARD. The inner guards
    let one reader fail and the next one try; this one guarantees that
    whatever still escapes -- from the parser, the registry, the classifier,
    anything -- costs this ROW and nothing else. The scorer above it sees an
    ordinary refusal and every other row still renders.
    """
    # ★★★ A FIELD IS STRUCTURAL BY ITS CONTENT, NOT BY ITS NAME. An
    # allowlist by KEY was the vulnerability: prose crossed into `basis`, a
    # key on that very allowlist, and five of six such fields carried the
    # ANSWER VALUE. So every matcher field is validated against a CLOSED
    # VOCABULARY here, and a violation refuses ONE ROW -- loudly, with its
    # own code -- rather than raising and costing the card.
    _bad = _vocab.violations(registry.spec_for(row))
    if _bad:
        return dict(value=None, reasonCode='SPEC_INVALID',
                    specViolations=[list(b) for b in _bad],
                    why=('SPEC: %s=%r %s' % _bad[0])[:300])

    # ★ THE ENTRY POINT NAMES ITS FRAME. value_for dewraps what it is
    # handed, so being handed already-dewrapped text dewraps it twice --
    # frame defect n=5, a silent hero refusal.
    _frames.expect(text, _frames.RAW, 'value_for')

    # ★★★★ A TABLE READER CANNOT READ A BODY WITH NO LINES. Refusing NAMES
    # the wire shape; guessing a cell boundary would be a wrong number in
    # green on the rows that decide trades.
    _sp0 = registry.spec_for(row) or {}
    _kinds0 = registry.where_kind(_sp0) or []
    if 'TABLE' in _kinds0 and not has_line_structure(text):
        return dict(value=None, specState=_sp0.get('specState'),
                    reasonCode='NO_LINE_STRUCTURE',
                    charsPerLine=round(chars_per_line(text), 1),
                    why=('NO LINE STRUCTURE: %d characters per line against a '
                         'ceiling of %d. This wire delivers the body as one '
                         'continuous string, so there are no dash rules, no '
                         'column alignment and no blank lines for a table '
                         'reader to work on. Refusing rather than inventing '
                         'a cell boundary.'
                         % (chars_per_line(text), MAX_CHARS_PER_LINE)))

    # ★★★★ AND THE SAME REFUSAL FROM THE OTHER END. One cell per line is
    # not a readable table either, and it fails in the EXPENSIVE direction:
    # the ceiling REFUSES, the floor PUBLISHES A FRAGMENT. Three of the four
    # mismatches in the five-spec corpus run came from a document like this.
    #
    # ★★★ BUT IT DISABLES THE TABLE PATH, NOT THE ROW. whereKind is an
    # ORDERED PREFERENCE, and a fragmented document is still perfectly
    # readable as PROSE. My first cut of this gate refused on 'TABLE in
    # kinds' and cost ORCL[7] its correct 1.92 -- a row that declares
    # ['TABLE','PROSE','WRAPPED'] and had actually read the figure from the
    # sentence 'non-GAAP Earnings per Share up 30% ... to $1.92'. Killing a
    # correct value to prevent a wrong one is not the trade; dropping the
    # reader that cannot work and keeping the ones that can is.

    mark = len(READER_FAILURES)
    try:
        got = _value_for(text, row, window=window, record=record)
    except Exception as exc:                            # noqa: BLE001
        note = 'READER FAILED in value_for: %s: %s' % (
            type(exc).__name__, str(exc)[:120])
        READER_FAILURES.append(note)
        return dict(value=None, specState=registry.status_of(
            registry.spec_for(row)), readerCrashed=True,
            reasonCode='READER_CRASHED', why=note)
    # ★★★ A SILENT BAND COMPRESSION IS A SILENT BRANCH REASSIGNMENT. The
    # scenario ladder grades on numeric triggers AT BAND ENDPOINTS, so a band
    # collapsed to its midpoint moves those endpoints INWARD: a print that
    # should match branch A matches branch B, and the ladder still reports a
    # clean match. A derived or guided band is published with BOTH ENDPOINTS
    # or the row is REFUSED. Never a midpoint alone.
    if got is not None and got.get('value') is not None:
        _sp = registry.spec_for(row) or {}
        _rf = (_sp.get('rangeForm') or '').upper()
        if _rf and _rf != 'POINT' and (got.get('rangeLow') is None
                                       or got.get('rangeHigh') is None):
            return dict(value=None, specState=_sp.get('specState'),
                        reasonCode='BAND_COLLAPSED',
                        why=('rangeForm %s declares a BAND and only a '
                             'midpoint survived (%s) — a band collapsed to '
                             'a point has lost what the ladder grades on, '
                             'and the collapse is invisible downstream'
                             % (_rf, got.get('value'))))
    if got is not None and got.get('value') is None \
            and len(READER_FAILURES) > mark:
        # a reader crashed and the row found nothing: say WHICH, rather than
        # letting a crash wear the clothes of an ordinary miss
        got = dict(got, readerCrashed=True, reasonCode='READER_CRASHED',
                   why=('%s | %s' % (READER_FAILURES[mark],
                                     got.get('why') or 'no value'))[:400])
    return got


def _value_for(text, row, window=260, record=None):
    """The row's value, taking whereKind as a PREFERENCE ORDER.

    The declared kind is tried first and the rest only if it yields nothing.
    `extractionKind` on the result says which one answered, so a value taken
    from the fallback is never mistaken for one taken from the declared kind.
    """
    spec = registry.spec_for(row)
    kinds = registry.where_kind(spec) or []
    # ★ A RANGE ROW IS NEVER A PLAIN CELL READ. requiresRangePair rows must
    # resolve to an ADJACENT low/high pair and return the MIDPOINT, which is
    # the range arm's job; the table pass returns single cells and took
    # ADBE's Q4 guide to 6.35, the high, instead of 6.325. Preferring the
    # table must not bypass the shape the row declares.
    # ★★★ whereKind IS AN ORDERED PREFERENCE, AND THE LIBRARY SAYS SO:
    # `whereKindIsAPreferenceOrder: True` has been authored on the spec all
    # along, and this read the list as a SET -- requiring PROSE to be ABSENT
    # before it would prefer the table. 29 of 76 rows declare more than one
    # kind and 9 of those refused. ADBE[6] declares TABLE/PROSE and reads
    # 6.13, its exact hand value, the moment the ORDER is honoured.
    # Third instance of a fact present in the system and not consulted.
    _first_layout = next((k for k in kinds
                          if k in ('TABLE', 'PROSE', 'WRAPPED', 'HEADLINE',
                                   'QUOTE')), None)
    prefers_table = (_first_layout == 'TABLE'
                     and 'RANGE' not in kinds
                     and not spec.get('requiresRangePair'))
    if prefers_table:
        got = _value_for_pass(text, row, window, record,
                              hit_pred=_lands_in_table)
        if got is not None and got.get('value') is not None:
            got['extractionKind'] = 'TABLE'
            return got
    got = _value_for_pass(text, row, window, record)
    if got is None:
        got = dict(value=None, candidates=[],
                   reasonCode='NO_LABEL_AFTER_FILTERS',
                   why='no label hit survived the row\'s filters')
    if got.get('value') is not None:
        got['extractionKind'] = 'FALLBACK' if prefers_table else (
            kinds[0] if kinds else None)
    return got


def _value_for_pass(text, row, window=260, record=None, hit_pred=None):
    """The extracted value for one card row, or a refusal.

    Returns dict(value, unit, why, candidates, label, specState).

    ★ REFUSE, NEVER GUESS. Two survivors that tie on unit, role and basis are
    a refusal naming both -- the same discipline as the column comparator.
    """
    spec = registry.spec_for(row)
    state = registry.status_of(spec)
    if state != 'EXTRACTABLE':
        return dict(value=None, specState=state, reasonCode='SPEC_STATE',
                    why=(
            'NOT GRADED BY DESIGN' if state == 'NOT_EXTRACTABLE' else
            'issuer changed disclosure — spec is stale' if state ==
            'NEEDS_REMAP' else 'no extraction spec on this row'))

    kinds = registry.where_kind(spec)
    if ('WRAPPED' in kinds or 'PROSE' in kinds or 'HEADLINE' in kinds):
        src, _segs = dewrap_mapped(text)
    else:
        src, _segs = text, None

    def _to_doc(p):
        # ★ POSITIONS THAT LEAVE THIS FUNCTION ARE PROVENANCE. Internally the
        # matchers work in `src`; only the recorded location has to point
        # into the document the caller holds. AVGO's Q4 figure is at 1635 in
        # the document and 1533 in dewrapped space, and 1533 reads as the
        # CEO's PREVIOUS sentence.
        return to_original(_segs, p) if (_segs and isinstance(p, int)) else p

    # ★★★ A DERIVED ROW IS NOT IN THE DOCUMENT. HPE prints a Net Revenue
    # block and an Earnings block and NO margin row, so reading cannot
    # succeed -- the fence and the label are both right and the block holds
    # dollars. The spec has said so since 17 September via `derived` and
    # `sourceRows`; nothing read either field until now.
    if (spec or {}).get('derived') and (spec or {}).get('sourceRows'):
        from . import derived as _derived
        # ★★★ THE ORIGINAL DOCUMENT, NOT THIS FRAME. derive() re-enters
        # value_for to resolve a card-row operand, and value_for dewraps
        # what it is handed -- so passing `src` DEWRAPS A SECOND TIME and
        # every offset inside the operand's own read shifts. HPE[3]
        # resolved standalone and refused as an operand, and the derived
        # hero above it refused with it. Frame defect n=5: raw, dewrapped,
        # stripped, kept, and now dewrapped TWICE.
        _frames.expect(text, _frames.RAW, 'derived.derive')
        _d = _derived.derive(text, row, record) or {}
        if _d.get('value') is not None:
            return dict(value=_d['value'], value_musd=None,
                        unit=doc_unit(spec), specState=state,
                        label=(spec.get('sourceRows') or [None])[0],
                        role='derived', derivedFrom=_d.get('derivedFrom'),
                        # the band survives the derivation too: the ladder
                        # grades against ends, not against a midpoint
                        rangeLow=_d.get('rangeLow'),
                        rangeHigh=_d.get('rangeHigh'),
                        candidateCount=2, seenCount=2,
                        currencyTaken=REPORTED, candidates=[], why=None,
                        rejected=[])
        # ★★★ THE SPECIALIST'S REFUSAL IS THE ANSWER, NOT A REASON TO TRY
        # SOMETHING WEAKER. A DERIVED ROW IS NOT IN THE DOCUMENT, so the
        # label path below cannot be right about it -- and it overwrote a
        # precise reason ("the BASE operand did not resolve by EXTRACTION")
        # with one that describes nothing ("no candidate matched the
        # declared unit '$'"). Third time a wrong reason has hidden the real
        # failure, and the same shape as the crash fallback: DEGRADATION
        # LOSES CAPABILITY, NEVER CONSTRAINTS.
        if _d.get('why'):
            return dict(value=None, specState=state, candidates=[],
                        role='derived', reasonCode='DERIVED_OPERAND',
                        why=_d['why'])

    hits = registry.label_hits(src, spec)
    # A LABEL HIT INSIDE THE DEFINITIONAL BLOCK IS NOT A LABEL HIT. HPE[8]
    # matched 'Non-GAAP diluted net earnings per share' in the boilerplate
    # and then took the nearest number, which was a dividend. The block is
    # present BY CONVENTION, so this is worth more on a document nobody has
    # spec'd than on the eight that are: 0 of 102 corpus rows move.
    _defs = definitional_spans(src)
    if _defs and hits:
        hits = [h for h in hits
                if not any(lo <= h[0] < hi for lo, hi in _defs)]
    if hit_pred is not None:
        hits = [h for h in hits if hit_pred(src, h)]
        if not hits:
            return None          # this PASS has nothing; the caller falls on
    if not hits:
        return dict(value=None, specState=state, candidates=[],
                    reasonCode='NO_LABEL',
                    why='no documentLabel found in this text')

    # ★★ PERIOD AS A FILTER. The section the candidate sits in IS its period:
    # guidance in a named targets block, actuals in the statements.
    anchors = section_spans(src, spec.get('sectionAnchor'),
                            spec.get('spanTerminator'),
                            spec.get('spanStartAfter'))

    # ★★★★★ AN EMPTY FENCE IS NOT A PERMISSIVE FENCE. The region filter
    # below reads `if anchors and not in_any(...)`, so an EMPTY list makes
    # the whole check vanish and the entire document becomes the fence.
    # That is "absence treated as permission" -- the same defect as
    # `(column_basis(desc) or want) == want` keeping an unlabelled column.
    #
    # It converts an AUTHORING MISTAKE INTO A WRONG NUMBER instead of a
    # refusal. NKE[8] and NKE[9] had ZERO spans and published anyway:
    # Converse 3.0 against a true 263, EMEA 0.001 against a true $3.2B.
    #
    # MEASURED report-only over the corpus AND the wire fixtures and
    # captures -- 312 row/document pairs, 28 with an anchor declared and
    # not found:
    #     18  already refuse, no change
    #     10  publish from an empty fence  <- all become refusals
    #      0  CORRECT VALUES LOST
    # The ten include SNDK 31.5 against a hand-read 45.0, WDC 51.5 against
    # 55.5 and ORCL 60.0 against 67.0, so this is not only NKE's two.
    if spec.get('sectionAnchor') and not anchors:
        return dict(value=None, specState=spec.get('specState'),
                    candidates=[], reasonCode='EMPTY_FENCE',
                    why=('EMPTY FENCE: sectionAnchor %r is declared and '
                         'matches NOTHING in this document, so there is no '
                         'region to read. Refusing rather than falling back '
                         'to the whole release, which is how an anchor that '
                         'was never found publishes a number from somewhere '
                         'else entirely.'
                         % (spec.get('sectionAnchor'),))[:400])

    excludes = section_spans(src, spec.get('excludeSections'))

    #: whereKind ROUTING IS NOT ENFORCED HERE, AND THAT IS MEASURED.
    #: Skipping prose hits on TABLE-only rows costs MATCH 18 -> 12; skipping
    #: them only when a real table row exists still costs 18 -> 14. 23 of the
    #: 46 TABLE-only rows have NO parseable table row at any label hit,
    #: because their value genuinely lives in a sentence -- 'Adobe expects
    #: fourth quarter revenue of $6.80 to $6.85 billion' -- while the spec
    #: says TABLE. The spec and the document disagree; until that is
    #: reconciled, honouring whereKind loses values we already read.
    picked, seen, rejected, fenced = [], [], [], 0
    cur_refusals = []
    # THE PREFERRED PASS READS WITH THE TABLE READER, not the prose scanner.
    table_pass = hit_pred is not None
    doc_lines = [l.strip() for l in src.split(chr(10))] if table_pass else []
    for start, end, lab in hits:
        if registry.disqualified(src, start, spec):
            rejected.append((lab, registry.disqualified(src, start, spec)))
            continue
        # ★ a row that names its section must be INSIDE it
        if anchors and not in_any(start, anchors):
            fenced += 1
            continue
        if table_pass:
            # THE CELLS ARE THE CANDIDATES. row_value_cells already reads the
            # bare-'%'-on-its-own-line convention that defeats prose
            # adjacency, so the unit test uses the cell's own flag.
            cells = _tables.row_value_cells(
                doc_lines, src.count(chr(10), 0, start))
            for ci, (cv, cp) in enumerate(cells):
                if not _cell_unit_ok(cp, spec):
                    continue
                cand = dict(value=cv, value_musd=None, pct=cp,
                            unit='%' if cp else '', role='level',
                            pos=0, gpos=start, lpos=start, cellIndex=ci,
                            raw=('%g%%' % cv) if cp else ('%g' % cv),
                            label=lab)
                seen.append(cand)
                picked.append(cand)
            continue
        # ★ and must never be inside an excluded one
        if excludes and in_any(start, excludes):
            fenced += 1
            continue
        # whereKind IS A DECLARED ROUTING VALUE, not documentation. A row that
        # says its value lives in a table does not want the sentence that
        # merely mentions the label.
        # ★★ FOR A TABULAR ROW THE WINDOW IS THE SPAN. The section is already
        # closed by a terminator the issuer printed, so a second bound is a
        # guess -- and every guess I made here was wrong: 260 chars, 3
        # newlines, 14 newlines. Run to the end of the row's own span.
        tabular = ('TABLE' in kinds or 'RANGE' in kinds) and not (
            'PROSE' in kinds or 'WRAPPED' in kinds)
        if tabular and anchors:
            span_end = min((hi for lo, hi in anchors if lo <= start <= hi),
                           default=end + TABLE_WINDOW)
            win = src[end:span_end]
            win_base = end
        elif tabular:
            win = clip(src[end:end + TABLE_WINDOW], kinds)
            win_base = end
        else:
            win = clip(src[end:end + window], kinds)
            win_base = end
        # ★★ SHAPE GATE. A RANGE row must resolve to an ADJACENT low/high
        # pair; a lone 4.62 fails this test, which kills the ADBE guide bug
        # even where section fencing is unavailable.
        # ★★ BASIS LOCATION #4 -- A LINE PREFIX ON THE VALUE. ADBE's
        # targets block prints 'GAAP: $4.65 to $4.70' and
        # 'Non-GAAP: $6.30 to $6.35' on consecutive lines under ONE generic
        # label. A reader that only knows row-label basis takes the first
        # range it sees and returns the GAAP figure -- which is exactly how
        # the FY26 guide came back 18.12.
        bp = spec.get('basisPrefix')
        if bp:
            # ★ REQUIRED ONLY WHEN THE LABEL DOES NOT DECLARE THE BASIS.
            # 'Non-GAAP diluted net income per share' already states it
            # (location 1); 'Earnings per share' does not, and there the
            # line prefix (location 4) is the only thing separating
            # 'GAAP: $4.65' from 'Non-GAAP: $6.30'.
            label_states_basis = _norm(bp).rstrip(':') in _norm(lab)
            k = win.lower().find(_norm(bp))
            if k >= 0:
                # the basis prefix re-slices the window: the frame moves too
                win = win[k + len(bp):]
                win_base += k + len(bp)
            elif not label_states_basis:
                continue
        # ★ CURRENCY, THE SIXTH AXIS. Masked, never sliced: the offsets in
        # this window are already load-bearing.
        _cspans = currency_spans(win)
        _masked, _cwhy = currency_mask(win, spec)
        if _masked is None:
            cur_refusals.append(_cwhy)
            continue
        win = _masked
        if spec.get('requiresRangePair'):
            # ★ THE DECLARED FORM IS TRIED FIRST. WDC's revenue guide prints
            # '$4.1B +/- $100M' and the dash grammar walks straight past it to
            # '$390M - $400M' -- the OPERATING EXPENSES row -- and reports
            # candidateCount 1, rejected [], why None. Complete confidence
            # while holding the midpoint of a different row's range.
            pair = None
            if (spec.get('rangeForm') or '').strip().upper() == 'PLUS_MINUS':
                pair = plus_minus_pair(win, spec)
            if pair is None:
                pair = range_pair(win, spec)
            if pair is None and spec.get('rangeColumns'):
                # ★ WHERE THE ISSUER LABELS THE COLUMNS, THE PAIR IS ADJACENT
                # AND UNSEPARATED: '$ 6.30  $ 6.35' under 'Low | High'. A
                # separator grammar finds nothing there, and this is the
                # strongest anchor in the corpus -- the APP pattern.
                pair = adjacent_pair(win, spec)
            if pair is None:
                continue
            lo, hi = pair
            # ★ THE VALUE'S LOCATION IS THE VALUE'S LOCATION, not the label's.
            _roff = _range_offset(win, lo, hi)
            _rpos = (win_base + _roff) if _roff is not None else end
            for v in (lo, hi):
                seen.append(dict(value=v, value_musd=None, pct=False,
                                 unit='', role='level', pos=_rpos,
                                 gpos=_rpos, lpos=start, raw=str(v),
                                 label=lab))
            # ★ THE MIDPOINT IS WHAT THE LIBRARY STORES. Both ends travel
            # with it: a band is information the midpoint discards, and the
            # clearance against a bogey depends which end is asked about.
            mid = round((lo + hi) / 2.0, 6)
            picked.append(dict(value=mid, value_musd=None, pct=False,
                               unit='', role='level', pos=_rpos, gpos=_rpos,
                               lpos=start, raw='%s-%s' % (lo, hi), label=lab,
                               currency=((spec or {}).get('currencyBasis')
                                         or currency_of(_cspans, 0)),
                               rangeLow=lo, rangeHigh=hi))
            continue
        for c in candidates(win, spec):
            if not _unit_ok(c, spec):
                continue
            # gpos is ALWAYS source-absolute. `pos` is window-local here
            # and source-absolute in the range arm above -- one field, two
            # frames, and column_value silently read line 0 of the document.
            c = dict(c, label=lab, gpos=win_base + c.get('pos', 0),
                     lpos=start,
                     currency=currency_of(_cspans, c.get('pos', 0)))
            seen.append(c)
            # 'to' is the LEVEL. Without this, RPO returns 209.
            # AND IN A TABLE THE HEADER IS THE GRAMMAR. A cell carries no
            # preposition, so role is None -- not delta, just unspoken. On a
            # tabular row that is a level by construction; refusing it let
            # prose from lower in the span outrank the row itself.
            if c['role'] == 'level' or (tabular and c['role'] is None):
                picked.append(c)

    if not seen:
        # THE FILTER READS documentUnit; the message read spec['unit'], which
        # is None on all 78 rows. So every unit refusal said 'declared unit
        # None' and looked like an inert filter. The filter was never inert --
        # the MESSAGE named a field nobody writes.
        if cur_refusals:
            return dict(value=None, specState=state, candidates=[],
                        reasonCode='CURRENCY',
                        why='CURRENCY: %s' % cur_refusals[0],
                        rejected=rejected)
        why = 'label found, no candidate matched the declared unit %r' % (
            doc_unit(spec) or None)
        if fenced:
            why += ' (%d hit(s) outside the row\'s own section)' % fenced
        if rejected:
            why += ' (%d candidate(s) disqualified: %s)' % (
                len(rejected), ', '.join(sorted({r[1] for r in rejected})))
        return dict(value=None, specState=state, candidates=[],
                    reasonCode='UNIT_MISMATCH', why=why,
                    rejected=rejected)

    pool = picked or [c for c in seen if c['role'] != 'delta']
    if not pool:
        return dict(value=None, specState=state,
                    candidates=[c['raw'] for c in seen],
                    reasonCode='ALL_DELTA',
                    why='every candidate reads as a DELTA, none as a level')

    # THE TABLE'S OWN HEADER SCALES THE CELL. documentUnit is the check.
    declared = (spec or {}).get('documentUnit')
    finding = None
    for c in pool:
        d = denomination(src, c.get('gpos', 0))
        c['denomination'] = d[0] if d else None
        c['denominationPhrase'] = d[1] if d else None
        c['sigDigits'] = sig_digits(c.get('raw'))
        if c.get('value_musd') is None and d and _MUSD.get(d[0]):
            c['musd'] = c['value'] * _MUSD[d[0]]
        else:
            c['musd'] = c.get('value_musd')
        if d and declared in _MUSD and d[0] != declared:
            # A FINDING, NOT AN ERROR: the issuer's header outranks the spec,
            # and the two disagreeing is information about the spec.
            finding = ('documentUnit %s, but the governing header says %s: %s'
                       % (declared, d[0], c['denominationPhrase']))
    pool = collapse_precision(pool)

    # ★★★ A BASIS ROW CONSULTS THE BASIS-AWARE READER EVEN WHEN NOTHING TIES.
    # SNOW's gross-margin row yields exactly ONE prose candidate, 70.9 -- the
    # GAAP figure -- so no tie ever formed and the column path was never
    # asked. A single candidate is not evidence of the right candidate; it is
    # evidence that only one reader looked.
    _basis_want = (spec or {}).get('basis') or next(
        (a.get('want') for a in ((spec or {}).get('columnAxes') or {})
         .get('axes', []) if (a.get('axis') or '').upper() == 'BASIS'), None)
    # ★ ONLY WHERE THE BASIS IS A COLUMN GROUP. HPE and ADBE carry the basis
    # in the ROW LABEL itself -- 'Non-GAAP gross profit margin' -- so there is
    # no group to partition and the label has already done the work. Running
    # the stacked reader there took HPE's Q3 adjusted gross margin from 40.4,
    # its hand read, to 38.1 out of the nine-month block.
    _basis_where = (spec or {}).get('basisLocation')
    if _basis_want and pool and _basis_where != 'ROW_LABEL':
        from . import sgrid as _sg
        _doc = [l.strip() for l in src.split(chr(10))]
        for c in pool:
            lp = c.get('lpos')
            if lp is None:
                continue
            # ★★★ A CRASH MUST NOT FALL THROUGH TO A LESS-SPECIFIC READER.
            # This branch exists because the row declares a BASIS; the prose
            # pool below it is basis-blind. Letting a raising sgrid drop
            # through published SNOW's GAAP 70.9 in place of the non-GAAP
            # 74.7 -- the CBRS failure mode, delivered by the crash guard
            # that was supposed to make failure safe. A guard that converts
            # a crash into a WRONG VALUE is worse than the crash.
            _mark = len(READER_FAILURES)
            got_s = guarded('sgrid.select', _sg.select, _doc,
                            src.count(chr(10), 0, lp), spec) or {}
            if len(READER_FAILURES) > _mark:
                return dict(value=None, specState=state, readerCrashed=True,
                            candidates=[x['raw'] for x in seen],
                            reasonCode='READER_CRASHED',
                            why=('%s — refusing rather than falling through '
                                 'to the basis-blind prose pool on a row '
                                 'that declares %s'
                                 % (READER_FAILURES[_mark], _basis_want)),
                            rejected=rejected)
            if got_s.get('value') is None:
                continue
            if not _cell_unit_ok(got_s.get('pct'), spec):
                continue
            # ★★ THE SAME RULING, ON THE OTHER TABLE SHAPE. This branch
            # returns before the column path, so leaving it out would make
            # the rule fire on horizontal grids and not on stacked ones --
            # one condition with two behaviours, which is the defect this
            # build keeps finding. sgrid reports the GROUP ITS CELL IS IN,
            # so absence here means the block declared no basis groups.
            _sax = got_s.get('cellAxes') or {}
            _sev = ('AGREES' if _sax.get('basis')
                    else _sax.get('basisState') or 'UNREAD_BY_GRID')
            if _sax.get('basis') and (
                    _vocab.canonical_basis(_sax['basis'])
                    != _vocab.canonical_basis(_basis_want)):
                _sev = 'CONTRADICTS'
            _sprio = _priority.row_priority(
                row, spec,
                ((record or {}).get('preEarnings') or {}).get('keyKPIs'))
            if _sev == 'CONTRADICTS' or (_sev == 'ABSENT_IN_DOCUMENT'
                                         and _sprio == 1):
                return dict(value=None, specState=state,
                            basisEvidence=_sev, rowPriority=_sprio,
                            candidates=[x['raw'] for x in seen],
                            reasonCode='BASIS',
                            why=('BASIS: the stacked block resolves %s for '
                                 'this cell and the row declares %s'
                                 % (_sax.get('basis') or 'NO BASIS GROUP',
                                    _basis_want)
                                 + (' — refusing on a priority-1 hero'
                                    if _sev == 'ABSENT' else '')),
                            rejected=rejected)
            return dict(value=got_s['value'], value_musd=None,
                        basisEvidence=_sev, rowPriority=_sprio,
                        unit=doc_unit(spec), specState=state,
                        label=c.get('label'), role='level',
                        basisRead=_basis_want,
                        columnClasses=got_s.get('groups'),
                        cellAxes=got_s.get('cellAxes'),
                        # ★ THE STACKED READER SELECTED AMONG ITS CELLS, not
                        # among the prose candidates. Reporting len(seen) here
                        # filed the two SNOW rows this reader just FIXED as
                        # 'nothing looked' -- the instrument mismeasuring the
                        # very selection it was built to record.
                        candidateCount=len(got_s.get('cells') or []) or 1,
                        seenCount=max(len(got_s.get('cells') or []), len(seen)),
                        currencyTaken=c.get('currency') or REPORTED,
                        pos=_to_doc(cell_offset(src, got_s.get('cellLine'),
                                                got_s.get('cellX'))
                                    or lp),
                        cellPos=_to_doc(cell_offset(src,
                                                    got_s.get('cellLine'),
                                                    got_s.get('cellX'))),
                        lpos=_to_doc(lp),
                        candidates=[x['raw'] for x in seen], why=None,
                        rejected=rejected)

    # ★★ THE DECLARED AXIS IS CONSULTED BEFORE THE TIE, NOT AFTER IT. On its
    # own this reordering moved 0 of 102 rows, because both of HPE[3]'s
    # candidates classified identically off their sentences. With the
    # heading in the context it separates them. ORDER AND EVIDENCE HAD TO
    # LAND TOGETHER; either alone is a no-op.
    if (spec or {}).get('period') and len(pool) > 1:
        _q = (record or {}).get('fiscalQuarter')
        _keep = [c for c in pool
                 if not period_conflict(src, c.get('gpos'), spec, _q)]
        if _keep and len(_keep) < len(pool):
            rejected = list(rejected) + [
                'PERIOD: %s dropped by the declared period, read from the '
                'section heading' % (len(pool) - len(_keep))]
            pool = _keep

    vals = {round(c['value'], 6) for c in pool}
    # columnAxes REPLACED columnSelect; both are written today, and a
    # reader that asks only for the older name goes quiet the moment
    # the newer one stands alone.
    if len(vals) > 1 and (spec.get('columnSelect')
                          or spec.get('columnAxes')) \
            and 'TABLE' in kinds:
        # ★★ THE TIE IS BETWEEN COLUMNS OF ONE ROW, NOT BETWEEN ROWS. Ask the
        # header which cell is the reporting period; unit, role, period and
        # basis are identical across them by construction.
        anchors_seen = []
        for c in pool:
            lp = c.get('lpos')
            if lp is None or lp in anchors_seen:
                continue
            anchors_seen.append(lp)
            # ANCHOR AT THE LABEL, NOT THE CANDIDATE. A window runs to the
            # section terminator, so candidates overrun the rows below their
            # own label; column_map's parameter is named `label_idx` and I
            # was handing it a candidate.
            col = column_value(src, spec, lp, record=record)
            if col is not None:
                # ★★★ THE COLUMN IS GENUINELY UNLABELLED, AND THAT IS A FACT
                # ABOUT THE DOCUMENT. Before cellAxes, absence of a basis
                # word meant WE COULD NOT SEE; now it means THE ISSUER DID
                # NOT SAY. The filter used to keep such a column silently --
                # `(column_basis(desc) or want) == want` -- which is why
                # FALSE_MATCH 0 was never news: a check that ACCEPTS on
                # missing evidence cannot fail when it has none.
                _axes_got = col.get('cellAxes') or {}
                _basis_ev = 'NOT_DECLARED'
                if (spec or {}).get('basis'):
                    _basis_ev = ('AGREES' if _axes_got.get('basis')
                                 else _axes_got.get('basisState')
                                 or 'UNREAD_BY_GRID')
                    # ★★★ ONE CANONICALISER, EVERY COMPARISON. This is the
                    # FIFTH call site of the same test and the THIRD time it
                    # has been fixed where it was noticed rather than
                    # everywhere it occurs. 'NON_GAAP' vs 'non-GAAP' read as
                    # a CONTRADICTION and refused three graded rows,
                    # including two heroes, the moment the library was
                    # normalised to the underscore form.
                    if _axes_got.get('basis') and (
                            _vocab.canonical_basis(_axes_got['basis'])
                            != _vocab.canonical_basis(spec['basis'])):
                        _basis_ev = 'CONTRADICTS'
                _prio = _priority.row_priority(
                    row, spec,
                    ((record or {}).get('preEarnings') or {}).get('keyKPIs'))
                if _basis_ev == 'CONTRADICTS':
                    return dict(value=None, specState=state,
                                basisEvidence=_basis_ev,
                                candidates=[x['raw'] for x in seen],
                                reasonCode='BASIS_CONTRADICTS',
                                why=('BASIS: the selected column is %s and '
                                     'the row declares %s'
                                     % (_axes_got.get('basis'),
                                        spec['basis'])),
                                rejected=rejected)
                # ★ ONLY ABSENT_IN_DOCUMENT REFUSES. UNREAD_BY_GRID is a
                # gap in us, and blanking a hero row because our own reader
                # never looked would publish a refusal with false provenance.
                if _basis_ev == 'ABSENT_IN_DOCUMENT' and _prio == 1:
                    # THE SNDK PRINCIPLE: on the row that decides the trade,
                    # a refusal beats a wrong number.
                    return dict(value=None, specState=state,
                                basisEvidence=_basis_ev, rowPriority=_prio,
                                candidates=[x['raw'] for x in seen],
                                reasonCode='BASIS_ABSENT',
                                why=('BASIS: this row declares %s and the '
                                     'column it was read from carries no '
                                     'basis word — refusing on a priority-1 '
                                     'hero rather than publishing an '
                                     'unverifiable basis' % spec['basis']),
                                rejected=rejected)
                _d = denomination(src, lp)
                return dict(value=col['value'],
                            value_musd=(col['value'] * _MUSD[_d[0]]
                                        if _d and _d[0] in _MUSD else None),
                            denomination=_d[0] if _d else None,
                            denominationPhrase=_d[1] if _d else None,
                            denominationFinding=finding,
                            # EVERY path that returns a VALUE records which
                            # currency it took; a blank here would read as
                            # 'not applicable' on a row where it applies.
                            currencyTaken=(c.get('currency') or REPORTED),
                            candidateCount=len({round(x['value'], 6)
                                                for x in pool}),
                            seenCount=len(seen),
                            unitUnverified=(_d is None
                                            and declared in _MUSD),
                            # THE CELL, NOT THE ROW. A row-level pos hands
                            # every provenance check the words the row opens
                            # with; the cell is what was actually selected,
                            # and it is what the audit has to be able to see.
                            pos=_to_doc(col.get('cellPos')
                                        if col.get('cellPos') is not None
                                        else lp),
                            cellPos=_to_doc(col.get('cellPos')),
                            lpos=_to_doc(lp),
                            unit=doc_unit(spec), specState=state,
                            label=c.get('label'), role='level',
                            columnIndex=col['columnIndex'],
                            columnClasses=col['columnClasses'],
                            cellAxes=col.get('cellAxes'),
                            # ACCEPT AND FLAG. The row is published, and it
                            # says out loud that its basis is unverified.
                            basisEvidence=_basis_ev, rowPriority=_prio,
                            candidates=[x['raw'] for x in seen], why=None,
                            rejected=rejected)
    if len(vals) > 1:
        return dict(value=None, specState=state,
                    candidates=[c['raw'] for c in pool],
                    reasonCode='CANDIDATE_TIE',
                    why='%d candidates tie on unit and role — refusing: %s'
                        % (len(vals), ', '.join(c['raw'] for c in pool[:6])))
    # ★★★ THE PERIOD STRICT ARM — GUIDE ROWS ONLY.
    #
    # A REPORTED figure has exactly ONE possible period: the reporting
    # period. A GUIDE figure has SEVERAL, in the same release and often the
    # same table. Silence is INFORMATIVE for a reported row and EMPTY for a
    # guide row, so the arm belongs only on the second.
    #
    # ★★ AND THE SAFETY HALF IS CARRIED, NOT JUST THE ENFORCEMENT. The basis
    # ruling required POSITIVE EVIDENCE THAT THE READER LOOKED before
    # claiming the document silent. Carrying only the REFUSE arm to period
    # would have blanked 11 correct heroes. The enforcement is the memorable
    # half; the safety is what makes it survivable.
    _pv = _period_evidence(src, spec, (pool[0].get('gpos') if pool else None),
                           (record or {}).get('fiscalQuarter'))
    if _pv == 'ABSENT_IN_DOCUMENT':
        _pprio = _priority.row_priority(
            row, spec, ((record or {}).get('preEarnings') or {}).get('keyKPIs'))
        if _pprio == 1:
            return dict(value=None, specState=state,
                        periodEvidence=_pv, rowPriority=_pprio,
                        reasonCode='PERIOD_ABSENT',
                        candidates=[c['raw'] for c in seen],
                        why=('PERIOD: this GUIDE row declares %s and nothing '
                             'in the document locates the figure in a '
                             'period — a guide figure has several possible '
                             'periods in the same release, so silence '
                             'cannot support a publish on a priority-1 hero'
                             % spec.get('period')),
                        rejected=rejected)

    best = pool[0]
    # ★ THE DECLARED PERIOD IS CONSULTED, NOT MERELY AVAILABLE AS A
    # TIE-BREAKER. A single candidate formed no tie, so nothing ever asked
    # whether SNOW's 36% came from the CFO's FULL-YEAR guidance sentence.
    _contam = period_conflict(src, best.get('gpos'), spec,
                              (record or {}).get('fiscalQuarter'))
    if _contam:
        return dict(value=None, specState=state,
                    candidates=[c['raw'] for c in seen],
                    reasonCode='PERIOD', why='PERIOD: %s' % _contam,
                    rejected=rejected)
    return dict(value=best['value'], value_musd=best.get('musd'),
                unit=(spec or {}).get('unit'), specState=state,
                label=best['label'], role=best['role'],
                denomination=best.get('denomination'),
                denominationPhrase=best.get('denominationPhrase'),
                denominationFinding=finding,
                # NEITHER THE HEADER NOR THE NUMBER SAID. A prose figure
                # carries its own magnitude word ('$2.97 billion') and is
                # scaled by it; only a bare cell under no declaration has
                # nothing but documentUnit behind it.
                unitUnverified=(best.get('musd') is None
                                and declared in _MUSD),
                sigDigits=best.get('sigDigits'),
                # BOTH ENDS TRAVEL WITH THE MIDPOINT -- the range arm says so
                # in as many words and the return dropped them anyway, so a
                # compound derived from this row narrowed $4.35-$4.62 to
                # $4.41-$4.56 by squaring a midpoint. Discard #10.
                rangeLow=best.get('rangeLow'),
                rangeHigh=best.get('rangeHigh'),
                coveredPrintings=best.get('coveredPrintings'),
                pos=_to_doc(best.get('gpos')),
                lpos=_to_doc(best.get('lpos')),
                currencyTaken=best.get('currency') or REPORTED,
                # ★ HOW MANY DISTINCT VALUES DID A FILTER HAVE TO CHOOSE
                # BETWEEN? 1 means none did, and the answer is unverified by
                # construction however right it happens to be.
                candidateCount=len({round(c['value'], 6) for c in pool}),
                seenCount=len(seen),
                candidates=[c['raw'] for c in seen], why=None,
                rejected=rejected)
