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

_NUMERIC = re.compile(r'^\$?\s*\(?(-?[\d,]+(?:\.\d+)?)\)?$')
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
            val, is_pct = _first_value(lines, i)
            if val is None:
                break
            if wants_pct:
                # Percentages need no declared scale.
                if not is_pct and not (0.0 <= val <= 100.0):
                    break
                _record(found, metric, val, basis, None, i)
            else:
                if is_pct:
                    break
                if scale is None:
                    # ★ No declared scale -- refuse the magnitude rather than
                    # inferring one from the digit count (error class D5).
                    break
                _record(found, metric, val * _SCALE_TO_MUSD[scale], basis,
                        scale, i)
            break
    return found


def _record(found, metric, value, basis, scale, line):
    prev = found.get(metric)
    # First occurrence wins, EXCEPT that a non-GAAP row supersedes a GAAP one.
    if prev is not None and not (basis == 'non-GAAP'
                                 and prev.get('basis') != 'non-GAAP'):
        return
    found[metric] = dict(value=value, basis=basis, scale=scale, line=line,
                         source='table')


def _first_value(lines, label_index):
    """The first numeric cell after a label. Returns (value, is_percent)."""
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
_H_ROW = re.compile(
    r'^\s*([A-Za-z][A-Za-z /&\'\-\.]{2,40}?)\s{2,}'
    r'((?:[+\-]?\(?\$?\s?[\d,]+(?:\.\d+)?\)?\s*%?\s*){2,})$')
_H_NUM = re.compile(r'([+\-]?)\(?\$?\s?([\d,]+(?:\.\d+)?)\)?\s*(%?)')


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
    for i, raw in enumerate((text or '').splitlines()):
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
        mags = [(sg, nm) for sg, nm, pc in cols if not pc]
        classes = [c for c in (header_classes or []) if c is not None]
        pick_idx = None
        if classes and len(classes) == len(mags):
            for _k, _cls in enumerate(classes):
                if _cls == 'REPORTED':
                    pick_idx = _k
                    break
        if pick_idx is None:
            # ★ REFUSE, and say why. Defaulting to column 1 is the assumption
            # level 2 exists to remove.
            return dict(value=None, scale=scale, line=i, raw=label,
                        source='table (segment, horizontal)',
                        periodUnchecked=True,
                        note=('column header not aligned: %d period column(s) '
                              'vs %d magnitude column(s)'
                              % (len(classes), len(mags))),
                        columns=[c[1] for c in cols])
        sign, num = mags[pick_idx]
        val = float(num.replace(',', '')) * _SCALE_TO_MUSD[scale]
        if sign == '-':
            val = -val
        return dict(value=val, scale=scale, line=i, raw=label,
                    source='table (segment, horizontal)',
                    columnIndex=pick_idx, columnClasses=classes,
                    columns=[c[1] for c in cols])
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
        val, is_pct = _first_value(lines, i)
        if val is None or is_pct:
            continue
        if scale is None:
            continue                            # refuse, do not infer
        return dict(value=val * _SCALE_TO_MUSD[scale], scale=scale, line=i,
                    source='table (segment)')
    return None
