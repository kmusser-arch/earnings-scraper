"""Vertical-table extraction for real wire releases.

Why this exists
===============
The prose parser was built and validated against synthetic bodies of the form
"Total revenue of $17.25 billion". Real Business Wire releases put the numbers in
a VERTICAL table -- label on one line, value one or two lines later, the unit
declared in a header far above:

    (In millions, except percentages)
    ...
    Revenue
     <tab>
    $1,924          <- current period

    $1,259          <- prior period

    Gross Margin

    84.6
    %

Measured against tests/corpus: AppLovin's entire release is tabular and the prose
parser extracted ZERO fields from it. SNDK states gross margin -- its graded HERO
KPI -- only in a table, so the hero fell through to a revenue fallback and the
Current Quarter grade came out 0.0 against a hand-built 1.0.

Discipline
==========
Percentages are unit-free and safe to read straight off the table. MAGNITUDES are
not: without an explicit "(In millions" / "(In thousands" header there is nothing
to normalise against, and guessing from the digit count is the error class D5
failure. So a magnitude with no declared scale is skipped, not inferred.

The FIRST numeric after a label is the current period -- every release in the
corpus orders the columns newest-first.
"""

import re

# A unit header that governs the rows beneath it.
_SCALE_HEADER = re.compile(
    r'\(?\s*(?:amounts\s+)?in\s+(millions|thousands|billions)\b', re.I)
_SCALE_TO_MUSD = {'billions': 1000.0, 'millions': 1.0, 'thousands': 0.001}

# Label -> (metric, wants_percent). Anchored so a sentence mentioning the words
# in passing is not mistaken for a table row.
_LABELS = [
    ('grossMargin', True, re.compile(
        r'^(?:non-?GAAP\s+)?gross\s+margin$', re.I)),
    ('operatingMargin', True, re.compile(
        r'^(?:non-?GAAP\s+)?operating\s+margin$', re.I)),
    ('revenue', False, re.compile(
        r'^(?:total\s+|net\s+)?revenue(?:s)?$', re.I)),
    ('adjEbitda', False, re.compile(
        r'^(?:total\s+)?(?:adjusted|adj\.?)\s+EBITDA$', re.I)),
    ('operatingIncome', False, re.compile(
        r'^(?:total\s+|consolidated\s+)?(?:non-?GAAP\s+|adjusted\s+)?'
        r'(?:operating\s+income|income\s+from\s+operations|'
        r'operating\s+profit)$', re.I)),
    ('eps', False, re.compile(
        r'^(?:non-?GAAP\s+)?diluted\s+(?:net\s+)?(?:income|earnings)\s+per\s+'
        r'share$', re.I)),
]

#: AN ATTACHED PERCENT SIGN STILL ENDS THE ROW, AND THAT IS A KNOWN GAP.
#: SNOW writes '70.9%' inline; the bare-'%'-on-its-own-line path below is
#: APP's layout. Widening this pattern makes SNOW's margins visible AND
#: takes its Q2 Product Revenue row from 1 cell to 8, which the cardinality
#: guard then refuses -- a correct production value lost. It re-lands with
#: the axis binding, when the guard can be taught the wider list in the
#: same step. See tests/test_axes.py.
#: NOTE: the parentheses stay OUTSIDE the capture group -- that is the
#: pinned polarity defect (tests/test_paren_polarity.py), not an
#: oversight, and it is not fixed here.
#: ★ EITHER ORDER. SNOW prints '($263.0)' with the currency symbol
#: INSIDE the parentheses; the pattern accepted only '$(263.0)', so that
#: cell did not parse at all and VANISHED from the row -- silently
#: renumbering every column after it, which is worse than a dropped sign.
_NUMERIC = re.compile(r'^\(?\s*\$?\s*\(?\s*(-?[\d,]+(?:\.\d+)?)\s*\)?$')
_PERCENT_ONLY = re.compile(r'^%$')
_SKIPPABLE = re.compile(r'^[\s\t$(]*$')

# A table cell is a short line. Prose sentences are not table cells.
_MAX_CELL_LEN = 24
_LOOKAHEAD = 8


def _to_float(tok):
    try:
        return float(tok.replace(',', ''))
    except (TypeError, ValueError):
        return None


def parse_tables(text):
    """Extract metrics from vertical tables.

    Returns {metric: {'value': float, 'basis': 'non-GAAP'|'GAAP'|None,
                      'scale': str|None, 'line': int}} for whatever was found,
    preferring the FIRST occurrence of each metric (release highlights precede
    the full statements) and preferring a non-GAAP row over a GAAP one.
    """
    lines = [l.strip() for l in (text or '').splitlines()]
    scale = None
    found = {}

    # ★ Offsets per line, so a table row can be placed in a ZONE. The table
    # path is the ONLY way APP-2026Q2's figures are read, so the income
    # statement stays allowed -- but a balance-sheet or cash-flow row must not
    # become a graded actual.
    from . import zones
    spans = zones.zone_spans(text or '')
    offs, acc = [], 0
    for raw in (text or '').splitlines():
        offs.append(acc)
        acc += len(raw) + 1

    for i, line in enumerate(lines):
        if i < len(offs) and zones.is_refused_zone(text, offs[i], spans):
            continue
        if not line:
            continue
        m = _SCALE_HEADER.search(line)
        if m and len(line) <= 80:
            scale = m.group(1).lower()
            continue
        if len(line) > _MAX_CELL_LEN:
            continue

        for metric, wants_pct, pat in _LABELS:
            if not pat.match(line):
                continue
            basis = ('non-GAAP' if re.match(r'^non-?GAAP', line, re.I)
                     else None)
            val, is_pct, why = verified_value(lines, i)
            # ★ THE VERIFICATION TRAVELS WITH THE VALUE. Downstream must not
            # infer 'came from a table, therefore checked' -- that is the same
            # assumption this module exists to remove.
            col_verified = val is not None
            if val is None:
                # ★ REFUSED, NOT SKIPPED SILENTLY. The reason travels with the
                # metric so the card can say 'column unverified' rather than
                # 'not found in release' -- two different problems with two
                # different remedies.
                if why:
                    found.setdefault('_refused', {})[metric] = dict(
                        line=i, note=why, label=line[:60])
                break
            if wants_pct:
                # Percentages need no declared scale.
                if not is_pct and not (0.0 <= val <= 100.0):
                    break
                _record(found, metric, val, basis, None, i, col_verified)
            else:
                if is_pct:
                    break
                if scale is None:
                    # ★ No declared scale -- refuse the magnitude rather than
                    # inferring one from the digit count (error class D5).
                    break
                _record(found, metric, val * _SCALE_TO_MUSD[scale], basis,
                        scale, i, col_verified)
            break
    return found


def _record(found, metric, value, basis, scale, line, column_verified=False):
    prev = found.get(metric)
    # First occurrence wins, EXCEPT that a non-GAAP row supersedes a GAAP one.
    if prev is not None and not (basis == 'non-GAAP'
                                 and prev.get('basis') != 'non-GAAP'):
        return
    found[metric] = dict(value=value, basis=basis, scale=scale, line=line,
                         source='table', columnVerified=column_verified)


def row_value_cells(lines, label_index, limit=12):
    """Every numeric cell of a vertically exploded row, in document order.

    ★ THE CELLS ARE THE COLUMNS. _first_value() took cell 0 and called it the
    quarter; this returns the whole row so the header can say which cell that
    actually is.
    """
    out = []
    j = label_index + 1
    while j < len(lines) and len(out) < limit:
        cell = lines[j]
        if _SKIPPABLE.match(cell):
            j += 1
            continue
        # ★ A LONE UNIT MARKER IS NOT A CELL BOUNDARY. APP interleaves a bare
        # '%' after each percentage column and a bare '$' before each dollar
        # column; treating either as the end of the row truncated the cell
        # list to 3 of 6 and the cardinality guard refused the row -- while
        # index 0 would still have been the right VALUE off a wrong list.
        if _PERCENT_ONLY.match(cell) or cell.strip() in ('$', '(', ')'):
            j += 1
            continue
        m = _NUMERIC.match(cell)
        if not m:
            break
        val = _to_float(m.group(1))
        if val is None:
            break
        k = j + 1
        while k < len(lines) and _SKIPPABLE.match(lines[k]):
            k += 1
        is_pct = k < len(lines) and bool(_PERCENT_ONLY.match(lines[k]))
        if not is_pct and cell.endswith('%'):
            is_pct = True
        # ★★★ A PARENTHESISED CELL IS NEGATIVE, AND POSITION IS THE
        # DISCRIMINATOR. The lexical test -- a magnitude carries a decimal,
        # separator, currency symbol or percent sign -- cannot reach HPE's
        # '(67)', which is character-for-character the shape of the footnote
        # marker '(1)'. But a FOOTNOTE IS PART OF A LABEL and a VALUE IS A
        # CELL: nothing makes 'Non-GAAP(1)' or 'Net Revenue(5):' a cell,
        # while 67 arrived here as one. The two never occupy this position.
        #
        # ★ AND THE PARENTHESES SPLIT ACROSS LINES. HPE prints '(67' on one
        # line and ')' on another, and the closer is skipped above as a bare
        # marker -- so the test is whether the cell OPENS with a paren, not
        # whether it is wrapped in a matched pair.
        if cell.lstrip().startswith('(') or cell.lstrip().startswith('$('):
            val = -abs(val)
        out.append((val, is_pct))
        j += 1
    return out


def verified_value(lines, label_index):
    """The REPORTED-column value of a row, or a refusal.

    Returns (value, is_percent, note). `value` is None with a note whenever the
    column cannot be identified.

    ★★ THE COLUMN IS IDENTIFIED, NEVER ASSUMED. The wrong column is the same
    metric in the same unit, and prior-year-YTD / current-Q = 2/(1+g) equals
    1.00 at 100% year-on-year growth -- the cohort this library trades. There
    is no magnitude to threshold against at the centre of that zone, so the
    header is the only thing that can answer.
    """
    from . import vtables
    cells = row_value_cells(lines, label_index)
    if not cells:
        return None, False, None
    if len(cells) == 1:
        # a single-column row states one period and cannot be mis-picked
        return cells[0][0], cells[0][1], None

    # ★ THE CELLS GO IN, SO THE REFUSAL CAN NAME THEM. verified_value
    # already holds the whole row; not passing it was the difference between a
    # refusal a trader can act on and one that only says the parser gave up.
    got = vtables.column_map(lines, label_index, len(cells),
                             values=[c[0] for c in cells])
    if got.get('valueIndex') is not None:
        i = got['valueIndex']
        return cells[i][0], cells[i][1], None

    # ★ FALLBACK: the document's own stated delta, where no header is
    # reachable. SNDK's highlights table says 'up 6.2 ppt' and
    # 84.6 - 78.4 = 6.2 -- a constraint with a unique solution, not a guess.
    closure = vtables.delta_closure(lines, label_index,
                                    [c[0] for c in cells])
    if closure.get('valueIndex') is not None:
        i = closure['valueIndex']
        return cells[i][0], cells[i][1], None

    return None, False, ('column unverified: %s; %s'
                         % (got.get('note') or 'no header',
                            closure.get('note') or 'no stated delta'))


def refused_candidates(lines, label_index):
    """The declined candidate list for a row, for callers that want it apart
    from the note."""
    from . import vtables
    cells = row_value_cells(lines, label_index)
    if len(cells) < 2:
        return None
    got = vtables.column_map(lines, label_index, len(cells),
                             values=[c[0] for c in cells])
    return got.get('candidates')


def _first_value(lines, label_index):
    """The first numeric cell after a label. Returns (value, is_percent).

    ★ SUPERSEDED by verified_value() for multi-column rows. Kept because a
    single-column row needs nothing more, and because other readers call it.
    """
    j = label_index + 1
    seen = 0
    while j < len(lines) and seen < _LOOKAHEAD:
        cell = lines[j]
        if _SKIPPABLE.match(cell):
            j += 1
            continue
        m = _NUMERIC.match(cell)
        if m:
            val = _to_float(m.group(1))
            if val is None:
                return None, False
            # A bare '%' on the next non-blank line marks it a percentage.
            k = j + 1
            while k < len(lines) and _SKIPPABLE.match(lines[k]):
                k += 1
            is_pct = k < len(lines) and bool(_PERCENT_ONLY.match(lines[k]))
            if not is_pct and cell.endswith('%'):
                is_pct = True
            return val, is_pct
        # Any other content means this was not a table row.
        return None, False
    return None, False

#: a HORIZONTAL table row: a text label, then two or more numeric columns on
#: the SAME line. AVGO's segment table is written this way; the five other
#: releases measured carry ZERO such rows, which is what bounds this reader.
#: ★ THE CURRENCY SYMBOL IS DETACHED FROM ITS NUMBER. ORCL prints
#: '$         11,607' -- nine spaces -- and the old `\$?\s?` allowed one.
#: Zero of three ORCL rows matched, so the horizontal reader existed and
#: could not read the horizontal release.
#: ★ POSSESSIVE GAPS. Widening the currency gap to `\s*` inside a
#: repeated group anchored at `$` made the engine try every split of the
#: whitespace between every cell -- catastrophic backtracking, and the
#: sweep hung past 120s on the first release. `*+` forbids the retry.
_H_ROW = re.compile(
    r'^[ \t]*([A-Za-z][A-Za-z0-9 /&\'\-\.\(\)]{2,44}?)[ \t]{2,}'
    r'((?:[+\-]?\(?\$?[ \t]*+[\d,]+(?:\.\d+)?\)?[ \t]*+%?\)?[ \t]*+){2,})$')
#: ★ THE CLOSING PAREN MAY FOLLOW THE PERCENT SIGN: '(3 %)'. And a
#: parenthesised figure is NEGATIVE -- reading it as +3 turns a decline
#: into a gain on a row that looks well-formed.
_H_NUM = re.compile(
    r'([+\-]?)(\()?\$?[ \t]*([\d,]+(?:\.\d+)?)\)?[ \t]*(%?)(\))?')



def h_row_cells(line):
    """(label, [(value, is_pct), ...]) for a HORIZONTAL table row, or None.

    ★ Space-aligned rows put the label and every column on ONE line, so the
    vertical reader -- which walks DOWN for the next cell -- finds the next
    label instead and returns nothing. Two of the eight releases are laid out
    this way, and they are the two with the worst tie counts.
    """
    m = _H_ROW.match((line or '').rstrip())
    if not m:
        return None
    out = []
    for sign, lparen, num, pct, rparen in _H_NUM.findall(m.group(2)):
        try:
            v = float(num.replace(',', ''))
        except ValueError:
            return None
        # ★ PARENTHESES MEAN NEGATIVE. '(3 %)' is a 3% DECLINE.
        neg = sign == '-' or (lparen and rparen)
        out.append((-v if neg else v, pct == '%'))
    return (m.group(1).strip(), out) if out else None


def h_column_value(lines, idx, record_quarter=None, record_year=None):
    """The REPORTED-column cell of the horizontal row at `lines[idx]`.

    ★★ NEVER BY INDEX. ORCL's supplemental grid runs FY26 Q1/Q2/Q3/Q4/TOTAL
    then FY27 Q1 -- the fifth column is a YEAR TOTAL, not a quarter -- and the
    reconciliations are RAGGED, fewer cells than the header declares. So the
    column is chosen by HEADER TEXT via period.column_classes, the same
    authority the vertical reader uses, and a count mismatch REFUSES.
    """
    from . import period as _period
    got = h_row_cells(lines[idx] if idx < len(lines) else '')
    if not got:
        return None
    label, cells = got
    values = [(v, p) for v, p in cells if not p]      # drop share columns
    if not values:
        return None

    classes = None
    for k in range(idx - 1, max(-1, idx - 40), -1):
        cc = _period.column_classes(lines[k], record_quarter, record_year)
        if cc and any(c in ('REPORTED', 'PRIOR_PERIOD') for c in cc):
            classes = [c for c in cc if c is not None]
            break
    if not classes:
        return dict(value=None, note='no period header above this row',
                    cells=[v for v, _ in values])
    if len(classes) != len(values):
        # ★ RAGGED ROW: refuse rather than map a short list onto a long one.
        return dict(value=None, cells=[v for v, _ in values],
                    note='ragged row: header declares %d period(s), row '
                         'supplies %d value cell(s)'
                         % (len(classes), len(values)))
    for i, c in enumerate(classes):
        if c == 'REPORTED':
            return dict(value=values[i][0], columnIndex=i, columnClasses=classes,
                        cells=[v for v, _ in values], note=None)
    return dict(value=None, cells=[v for v, _ in values],
                note='no REPORTED column in the header')


def find_segment_horizontal(text, tokens, record_quarter=None,
                            record_year=None):
    """A HORIZONTAL table row whose label carries all `tokens`.

    ★★ TAKES COLUMN 1 AND ONLY COLUMN 1. AVGO's rows run
        Net revenue  29,591  15,952  86  29,591  15,952  86
                     ^Q3'26  ^Q3'25 ^chg ^YTD'26 ^YTD'25 ^chg
    so column 2 is the PRIOR YEAR and column 4 is YEAR-TO-DATE. Either would be
    a plausible, same-metric, same-row, WRONG-PERIOD value -- the failure mode
    no other guard in this pipeline can see.

    Scale is still REQUIRED, never inferred (error D5).
    """
    toks = [x for x in (tokens or []) if x]
    if not toks:
        return None
    pats = [re.compile(r'\b%s' % re.escape(x), re.I) for x in toks]

    from . import period as _period

    scale = None
    header_classes = None
    lines_all = (text or '').splitlines()
    for i, raw in enumerate(lines_all):
        line = raw.rstrip()
        if not line.strip():
            continue
        # ★ A line carrying period LABELS is a column header. Held as the
        # running header until replaced, exactly like the scale header.
        _cc = _period.column_classes(line, record_quarter, record_year)
        if _cc and any(c in ('REPORTED', 'PRIOR_PERIOD') for c in _cc):
            header_classes = _cc
        sm = _SCALE_HEADER.search(line)
        if sm and len(line) <= 80:
            scale = sm.group(1).lower()
            continue
        m = _H_ROW.match(line)
        if not m:
            continue
        label = m.group(1).strip()
        if not all(pt.search(label) for pt in pats):
            continue
        cols = _H_NUM.findall(m.group(2))
        if len(cols) < 2:
            continue
        if scale is None:
            continue                     # refuse, never infer (D5)

        # ★★ LEVEL 2. Take the column whose HEADER says REPORTED, never
        # column 1 by assumption. AVGO's column 2 is 'Q3 25' -- the PRIOR
        # YEAR -- and a wrong-column pick is a plausible, same-metric,
        # same-row, in-band, WRONG-PERIOD value that nothing else here sees.
        #
        # Alignment is on MAGNITUDE columns only: the segment table's
        # share-of-total columns ('70 %', '57 %') carry no header of their
        # own, so percentages come off both sides before matching.
        # ★★ (c) CROSS-ROW ARITHMETIC identifies the VALUE columns, rather
        # than a '%' marker (unreliable -- this very table marks its share
        # columns on one row and not the next) or a position (the assumption
        # level 2 exists to remove).
        #
        # Reconciled against the table's OWN total row, so the check is
        # self-contained. Requires TWO closures: on a two-row table 'sums to
        # ~100' proves nothing by itself.
        block, totals = _table_block(lines_all, i)
        vcols = value_columns(block, totals) if block else None
        classes = [c for c in (header_classes or []) if c is not None]

        pick_idx = None
        why = None
        if vcols is None:
            why = 'column arithmetic did not close'
        elif len(vcols) != len(classes):
            why = ('column arithmetic closed on %d value column(s) but the '
                   'header names %d period(s)' % (len(vcols), len(classes)))
        else:
            for _k, _cls in enumerate(classes):
                if _cls == 'REPORTED':
                    pick_idx = vcols[_k]
                    break
            if pick_idx is None:
                why = 'no REPORTED column in the header'

        if pick_idx is None:
            return dict(value=None, scale=scale, line=i, raw=label,
                        source='table (segment, horizontal)',
                        periodUnchecked=True, note=why,
                        columns=[c[1] for c in cols])
        allnums = _row_numbers(line)[1]
        if pick_idx >= len(allnums):
            return dict(value=None, scale=scale, line=i, raw=label,
                        source='table (segment, horizontal)',
                        periodUnchecked=True,
                        note='value column %d is beyond this row' % pick_idx,
                        columns=[c[1] for c in cols])
        val = allnums[pick_idx] * _SCALE_TO_MUSD[scale]
        return dict(value=val, scale=scale, line=i, raw=label,
                    source='table (segment, horizontal)',
                    columnIndex=pick_idx, columnClasses=classes,
                    valueColumns=vcols, columns=[c[1] for c in cols])
    return None


def find_segment(text, tokens):
    """A vertical-table row whose LABEL carries all of `tokens`.

    Preferred over the prose path for segments: a table states 5,775 where the
    prose rounds to "$5.8 billion", and a hero graded against a bogey of 5.7
    has only 0.05 of rounding headroom. Magnitudes still require a declared
    scale header -- an undeclared one is refused, never inferred (error D5).

    Returns {'value','scale','line','source'} or None.
    """
    toks = [t for t in (tokens or []) if t]
    if not toks:
        return None
    pats = [re.compile(r'\b%s' % re.escape(t), re.I) for t in toks]
    rev = re.compile(r'\b(?:revenue|revenues|net\s+sales|sales)\b', re.I)

    lines = [l.strip() for l in (text or '').splitlines()]
    scale = None
    for i, line in enumerate(lines):
        if not line:
            continue
        m = _SCALE_HEADER.search(line)
        if m and len(line) <= 80:
            scale = m.group(1).lower()
            continue
        if len(line) > 44:                      # a label, not a sentence
            continue
        if not all(pt.search(line) for pt in pats):
            continue
        if not rev.search(line) and not re.search(r'^\s*segment', line, re.I):
            continue
        # ★ THE COLUMN IS IDENTIFIED HERE TOO. This path feeds SNOW's
        # priority-1 hero, and it was the last table reader still taking cell
        # 0 on faith. A refused hero with a stated reason is a decision; a
        # wrong hero is a trade.
        val, is_pct, why = verified_value(lines, i)
        if val is None:
            if why:
                return dict(value=None, scale=scale, line=i,
                            source='table (segment, column unverified)',
                            note=why)
            continue
        if is_pct:
            continue
        if scale is None:
            continue                            # refuse, do not infer
        return dict(value=val * _SCALE_TO_MUSD[scale], scale=scale, line=i,
                    source='table (segment)', columnVerified=True)
    return None

# ══ (c) COLUMN CLASSIFICATION BY CROSS-ROW ARITHMETIC ══════════════════════
#
# ★ Verify or refuse. A '%' marker is unreliable (the same AVGO table marks its
# share columns on one row and not the next) and position is the assumption
# level 2 exists to remove. Arithmetic across rows is checkable.

SHARE_TOL = 1.5          # a share column sums to 100 +/- this
VALUE_TOL = 0.005        # a value column matches a stated total within 0.5%


def _row_numbers(line):
    """The numeric fields of a horizontal row, in order, as floats."""
    m = _H_ROW.match((line or '').rstrip())
    if not m:
        return None, []
    out = []
    for sign, _lp, num, _pct, _rp in _H_NUM.findall(m.group(2)):
        try:
            v = float(num.replace(',', ''))
        except ValueError:
            return None, []
        out.append(-v if sign == '-' else v)
    return m.group(1).strip(), out


def _table_block(lines_all, i):
    """The consecutive horizontal rows around line `i`, and any stated totals.

    ★ A table's TOTAL row is its own reconciliation source, so the arithmetic
    check needs nothing imported from elsewhere. A block with no total row
    fails to close and is refused, which is correct.
    """
    lo = hi = i
    while lo > 0 and _row_numbers(lines_all[lo - 1])[0]:
        lo -= 1
    while hi + 1 < len(lines_all) and _row_numbers(lines_all[hi + 1])[0]:
        hi += 1
    rows, totals = [], []
    for k in range(lo, hi + 1):
        lbl, nums = _row_numbers(lines_all[k])
        if not lbl or not nums:
            continue
        if re.match(r'^\s*total\b', lbl, re.I):
            totals.extend(nums)
        else:
            rows.append(nums)
    return rows, tuple(t for t in totals if t and abs(t) > 100.0)


def classify_columns_by_arithmetic(rows, totals=()):
    """Classify each column of a table block by what its values SUM to.

    `rows`   [[float, ...]] -- the numeric fields of each data row
    `totals` stated totals the table should reconcile to, in any order

    Returns (classes, closures) where classes[i] is 'SHARE', 'VALUE' or None,
    and `closures` counts how many independent relations closed. The caller
    must REFUSE unless closures >= 2.
    """
    if not rows:
        return [], 0
    width = min(len(r) for r in rows)
    if width == 0:
        return [], 0
    classes = [None] * width
    closures = 0
    for i in range(width):
        col = [r[i] for r in rows]
        total = sum(col)
        if abs(total - 100.0) <= SHARE_TOL:
            classes[i] = 'SHARE'
            closures += 1
            continue
        for t in totals:
            if t and abs(total - t) <= abs(t) * VALUE_TOL:
                classes[i] = 'VALUE'
                closures += 1
                break
    return classes, closures


def value_columns(rows, totals=()):
    """Indices of the VALUE columns, or None when the arithmetic did not close.

    ★ Requires TWO independent closures. On a two-row table a single
    'sums to 100' proves nothing.
    """
    classes, closures = classify_columns_by_arithmetic(rows, totals)
    if closures < 2:
        return None
    return [i for i, c in enumerate(classes) if c == 'VALUE']
