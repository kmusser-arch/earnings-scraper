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

from . import registry
from . import tables as _tables

#: a number with its optional currency and unit words
_NUM = re.compile(
    r'(?P<pre>[A-Za-z%\s,\'\-]{0,26}?)'
    r'(?P<cur>\$)?\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s*'
    r'(?P<unit>%|billion|bn|million|mm?\b|trillion)?', re.I)

#: ★ THE PREPOSITION CARRIES THE MEANING. 'to' is the level; 'up/from' is the
#: change. Measured on ORCL: "up $209 billion year-over-year to $664 billion".
_LEVEL_PREP = re.compile(r'\b(?:to|of|was|were|at|reached|totall?ed|climbed'
                         r'\s+to|grew\s+to|increased\s+to)\s*$', re.I)
_DELTA_PREP = re.compile(r'\b(?:up|down|rose|fell|grew|declined|increased|'
                         r'decreased|from|versus|vs\.?|compared\s+to|'
                         r'year-over-year|y/y)\s*$', re.I)

_SCALE = {'billion': 1000.0, 'bn': 1000.0, 'b': 1000.0,
          'million': 1.0, 'mm': 1.0, 'm': 1.0,
          'trillion': 1000000.0}

#: the row's declared unit -> the multiplier that puts a $M figure in it
_ROW_UNIT = {'$B': 0.001, '$M': 1.0, '$K': 1000.0, '$': None, '%': None}


def dewrap(text):
    """Join a hard-wrapped bullet into one line, preserving offsets loosely.

    ★ A bullet that wraps is still one sentence. ORCL's RPO label and its
    number are on different lines, and every sentence-scoped matcher in this
    package was blind to that.
    """
    out, buf = [], []
    for raw in (text or '').splitlines():
        line = raw.rstrip()
        if not line.strip():
            if buf:
                out.append(' '.join(buf))
                buf = []
            out.append('')
            continue
        stripped = line.strip()
        # a new bullet or a short label line starts a new logical line
        if stripped.startswith('--') or stripped.startswith('*'):
            if buf:
                out.append(' '.join(buf))
            buf = [stripped]
        else:
            buf.append(stripped)
    if buf:
        out.append(' '.join(buf))
    return '\n'.join(out)


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
_DENOM_RE = re.compile(
    r'\(\s*(?:\$\s*)?(?:in|amounts\s+in|dollars\s+in)\s+'
    r'(thousand|million|billion)s?\b[^)]*\)', re.I)
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
    lines = [l.strip() for l in body.split(chr(10))]
    idx = body.count(chr(10), 0, label_pos)
    # HORIZONTAL first: on a space-aligned row the label and every column sit
    # on ONE line, and the vertical reader walks DOWN into the next label.
    # ORCL and AVGO are horizontal; the other six are vertical.
    # THE SPEC OWNS THE LAYOUT. A sniff that can disagree with it is a
    # second authority on one condition, which is the defect this build
    # keeps finding. ORCL HORIZONTAL, ADBE VERTICAL, on all 19 TABLE rows.
    if (spec or {}).get('tableLayout') == 'HORIZONTAL':
        h = tables.h_column_value(lines, idx, rq, ry)
        if h and h.get('value') is not None and _cell_unit_ok(False, spec):
            return dict(value=h['value'], pct=False,
                        columnIndex=h.get('columnIndex'),
                        columnClasses=h.get('columnClasses'))
        return None
    cells = tables.row_value_cells(lines, idx)
    if len(cells) < 2:
        return None
    got = vtables.column_map(lines, idx, len(cells), rq, ry,
                             values=[c[0] for c in cells])
    i = got.get('valueIndex')
    if i is None or i >= len(cells):
        return None
    # THE SELECTED CELL MUST PASS THE ROW'S UNIT CLASS. The prose candidates
    # are filtered by _unit_ok and the column path was not, so a $ row could
    # take a percentage cell -- which is exactly what allowing inline percent
    # cells would have handed the two APP rows.
    if not _cell_unit_ok(cells[i][1], spec):
        return None
    return dict(value=cells[i][0], pct=cells[i][1], columnIndex=i,
                columnClasses=got.get('classes'))



def _lands_in_table(src, hit):
    """Does this label hit sit on a line that parses as a table row?"""
    lines = getattr(_lands_in_table, '_cache', None)
    key = id(src)
    if not lines or lines[0] != key:
        lines = (key, [l.strip() for l in src.split(chr(10))])
        _lands_in_table._cache = lines
    idx = src.count(chr(10), 0, hit[0])
    return bool(_tables.row_value_cells(lines[1], idx))


def value_for(text, row, window=260, record=None):
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
    prefers_table = ('TABLE' in kinds
                     and 'RANGE' not in kinds
                     and not spec.get('requiresRangePair')
                     and not ('PROSE' in kinds or 'WRAPPED' in kinds
                              or 'HEADLINE' in kinds or 'QUOTE' in kinds))
    if prefers_table:
        got = _value_for_pass(text, row, window, record,
                              hit_pred=_lands_in_table)
        if got is not None and got.get('value') is not None:
            got['extractionKind'] = 'TABLE'
            return got
    got = _value_for_pass(text, row, window, record)
    if got is None:
        got = dict(value=None, candidates=[],
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
        return dict(value=None, specState=state, why=(
            'NOT GRADED BY DESIGN' if state == 'NOT_EXTRACTABLE' else
            'issuer changed disclosure — spec is stale' if state ==
            'NEEDS_REMAP' else 'no extraction spec on this row'))

    kinds = registry.where_kind(spec)
    src = dewrap(text) if ('WRAPPED' in kinds or 'PROSE' in kinds
                           or 'HEADLINE' in kinds) else text

    hits = registry.label_hits(src, spec)
    if hit_pred is not None:
        hits = [h for h in hits if hit_pred(src, h)]
        if not hits:
            return None          # this PASS has nothing; the caller falls on
    if not hits:
        return dict(value=None, specState=state, candidates=[],
                    why='no documentLabel found in this text')

    # ★★ PERIOD AS A FILTER. The section the candidate sits in IS its period:
    # guidance in a named targets block, actuals in the statements.
    anchors = section_spans(src, spec.get('sectionAnchor'),
                            spec.get('spanTerminator'),
                            spec.get('spanStartAfter'))
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
        if spec.get('requiresRangePair'):
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
            for v in (lo, hi):
                seen.append(dict(value=v, value_musd=None, pct=False,
                                 unit='', role='level', pos=end, gpos=end,
                                 lpos=start, raw=str(v), label=lab))
            # ★ THE MIDPOINT IS WHAT THE LIBRARY STORES. Both ends travel
            # with it: a band is information the midpoint discards, and the
            # clearance against a bogey depends which end is asked about.
            mid = round((lo + hi) / 2.0, 6)
            picked.append(dict(value=mid, value_musd=None, pct=False,
                               unit='', role='level', pos=end, gpos=end,
                               lpos=start, raw='%s-%s' % (lo, hi), label=lab,
                               rangeLow=lo, rangeHigh=hi))
            continue
        for c in candidates(win, spec):
            if not _unit_ok(c, spec):
                continue
            # gpos is ALWAYS source-absolute. `pos` is window-local here
            # and source-absolute in the range arm above -- one field, two
            # frames, and column_value silently read line 0 of the document.
            c = dict(c, label=lab, gpos=win_base + c.get('pos', 0),
                     lpos=start)
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
        why = 'label found, no candidate matched the declared unit %r' % (
            doc_unit(spec) or None)
        if fenced:
            why += ' (%d hit(s) outside the row\'s own section)' % fenced
        if rejected:
            why += ' (%d candidate(s) disqualified: %s)' % (
                len(rejected), ', '.join(sorted({r[1] for r in rejected})))
        return dict(value=None, specState=state, candidates=[], why=why,
                    rejected=rejected)

    pool = picked or [c for c in seen if c['role'] != 'delta']
    if not pool:
        return dict(value=None, specState=state,
                    candidates=[c['raw'] for c in seen],
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
                _d = denomination(src, lp)
                return dict(value=col['value'],
                            value_musd=(col['value'] * _MUSD[_d[0]]
                                        if _d and _d[0] in _MUSD else None),
                            denomination=_d[0] if _d else None,
                            denominationPhrase=_d[1] if _d else None,
                            denominationFinding=finding,
                            unitUnverified=(_d is None
                                            and declared in _MUSD),
                            # a table cell has no magnitude word of its own
                            pos=lp, lpos=lp,
                            unit=doc_unit(spec), specState=state,
                            label=c.get('label'), role='level',
                            columnIndex=col['columnIndex'],
                            columnClasses=col['columnClasses'],
                            candidates=[x['raw'] for x in seen], why=None,
                            rejected=rejected)
    if len(vals) > 1:
        return dict(value=None, specState=state,
                    candidates=[c['raw'] for c in pool],
                    why='%d candidates tie on unit and role — refusing: %s'
                        % (len(vals), ', '.join(c['raw'] for c in pool[:6])))
    best = pool[0]
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
                coveredPrintings=best.get('coveredPrintings'),
                pos=best.get('gpos'), lpos=best.get('lpos'),
                candidates=[c['raw'] for c in seen], why=None,
                rejected=rejected)
