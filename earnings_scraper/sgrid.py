# -*- coding: utf-8 -*-
"""The STACKED grid — a vertically exploded block, read as its own shape.

SNOW prints one row as a label followed by its cells, one per line:

    Product gross profit
    $1,057.4        <- GAAP amount
    70.9%           <- GAAP margin
    $1,114.1        <- non-GAAP amount
    74.7%           <- non-GAAP margin

and above the block, twice over, the column names 'Amount (millions)' and
'Margin', under the two basis headers 'GAAP Results' and 'Non-GAAP
Results(1)'. So the cells divide into equal contiguous groups, one per basis
header -- which is axes.partition, the mechanism already built and pinned.

★★★ IT HAS ITS OWN CELL READER, AND THAT IS THE POINT. tables.row_value_cells
stops at an inline percent, so this block yields ONE cell there. Widening the
shared pattern was tried and REVERTED: it took SNOW's Q2 Product Revenue row
from 1 cell to 8 and the cardinality guard refused a value that had been
reading correctly. One reader's coverage gap is another reader's guard, so the
stacked shape gets its own rules rather than bending the shape that works.

★★ AND PARENTHESES ARE NEGATIVE HERE, SAFELY. SNOW prints its GAAP operating
income as ($263.0) and its GAAP operating margin as (17.0%). The shared
parser's polarity defect is PINNED RED because a blanket negate would invert
SNDK's footnote marker '(1)'. Inside a stacked cell the ambiguity is
resolvable: a footnote is a bare integer in parentheses, while a magnitude
carries a decimal point, a thousands separator, a currency symbol or a percent
sign. Requiring one of those is the discriminator the blanket rule lacked --
so this reader honours the sign and the pin stays red for the parser that
cannot.
"""

import re

#: a stacked cell is a whole line that is nothing but a figure
_CELL = re.compile(r'^\(?\s*\$?\s*(-?[\d,]+(?:\.\d+)?)\s*%?\s*\)?$')

#: what separates a magnitude in parentheses from a footnote marker
_MAGNITUDE = re.compile(r'[.,%$]')

MAX_CELLS = 12


def cell(line):
    """(value, is_pct) for one stacked cell line, or None.

    ★ PARENTHESES MEAN NEGATIVE, but only where the content is a MAGNITUDE.
    '(17.0%)' and '($263.0)' carry a decimal, a currency symbol or a percent
    sign; '(1)' is a footnote marker and keeps its sign. That distinction is
    exactly what the blanket rule lacked, which is why the shared parser's
    version of this stays pinned red.
    """
    t = (line or '').strip()
    m = _CELL.match(t)
    if not m:
        return None
    raw = m.group(1)
    try:
        val = float(raw.replace(',', ''))
    except ValueError:
        return None
    negative = t.startswith('(') and t.endswith(')') and bool(
        _MAGNITUDE.search(t))
    if negative:
        val = -abs(val)
    return (val, t.rstrip(') ').endswith('%'))


def block_cells_at(lines, label_idx, limit=MAX_CELLS):
    """[(value, is_pct, line_index)] for the stacked row at `label_idx`.

    The block ends at the next line that is not blank and not a cell -- which
    is the next row's label. No length, no count: the document says where the
    row stops by starting the next one.

    A STACKED CELL IS ITS OWN LINE, so the line index IS the cell's location.
    This is the one shape where the coordinate was free all along and simply
    was not returned, which is why the audit read the LABEL's clause for a
    value printed four lines below it.
    """
    out = []
    j = label_idx + 1
    while j < len(lines) and len(out) < limit:
        t = (lines[j] or '').strip()
        if not t:
            j += 1
            continue
        # ★ TWO CONVENTIONS FOR ONE THING. SNOW attaches the percent sign to
        # the figure ('70.9%'); SNDK and APP put a bare '%' on the NEXT line,
        # and a bare '$' on the line BEFORE. Reading only one of them is the
        # seam that has produced most of this build's defects, so the block
        # reader takes both and the marker lines are not cell boundaries.
        if t in ('$', '%'):
            if t == '%' and out:
                # ★ AND THE REWRITE MUST KEEP THE COORDINATE. This line used
                # to rebuild the entry as a PAIR, silently dropping the line
                # index on any cell whose percent sign arrives on the next
                # line -- the SNDK and APP convention. SNOW attaches its
                # percent to the figure, so the corpus never reached it and
                # the loss would have surfaced as an IndexError on a live
                # print instead.
                out[-1] = (out[-1][0], True, out[-1][2])
            j += 1
            continue
        got = cell(t)
        if got is None:
            break
        out.append((got[0], got[1], j))
        j += 1
    return out


def block_cells(lines, label_idx, limit=MAX_CELLS):
    """[(value, is_pct)] -- the pair contract its callers and tests hold."""
    return [(v, p) for v, p, _ln in block_cells_at(lines, label_idx, limit)]


def select(lines, label_idx, spec, basis_headers=None, lookback=400):
    """The cell this row's basis and unit select from a stacked block.

    Returns dict(value, pct, cells, groups, why). Refuses rather than guessing.
    """
    from . import axes

    cells = block_cells_at(lines, label_idx)
    if not cells:
        return dict(value=None, cells=[], why='no stacked cells below this row')

    # ★ THE BASIS IS WRITTEN IN TWO PLACES AND BOTH ARE LIVE. SNOW declares
    # it on the row as `basis`; SNDK declares it as the BASIS axis inside
    # columnAxes, which was introduced to unify exactly this. A reader that
    # consults one of them is silent on half the corpus -- SNDK's five rows
    # read as 'no basis wanted' and picked by unit alone.
    want = (spec or {}).get('basis')
    axes_spec = (spec or {}).get('columnAxes') or {}
    declared_headers = None
    for ax in (axes_spec.get('axes') or []):
        if (ax.get('axis') or '').upper() != 'BASIS':
            continue
        want = want or ax.get('want')
        declared_headers = ax.get('headers') or None
    headers = basis_headers or declared_headers or [
        'GAAP Results', 'Non-GAAP Results(1)', 'GAAP', 'Non-GAAP']
    groups = axes.header_groups(lines, label_idx, headers, lookback=lookback)
    # collapse the two spellings to the two bases
    seen = []
    for g in groups:
        key = 'non-GAAP' if g.lower().startswith('non-') else 'GAAP'
        if key not in seen:
            seen.append(key)

    unit = ((spec or {}).get('documentUnit') or '').strip()
    want_pct = unit.startswith('%')

    if want and len(seen) >= 2:
        part = axes.partition(len(cells), len(seen))
        if part is None:
            return dict(value=None, cells=[c[0] for c in cells],
                        why='ragged: %d cell(s) do not divide into %d basis '
                            'group(s)' % (len(cells), len(seen)))
        from . import vocab as _vocab
        # ★ SAME CANONICALISER AS EVERY OTHER BASIS COMPARISON.
        _w = _vocab.canonical_basis(want)
        labels = [seen[g] for g in part]
        alive = [i for i, lab in enumerate(labels)
                 if _vocab.canonical_basis(lab) == _w]
        picked_basis = labels
        if not alive:
            return dict(value=None, cells=[c[0] for c in cells],
                        why='no %s group in this block' % want)
    else:
        alive = list(range(len(cells)))
        # ★ NO GROUPING RAN, SO NO CELL HAS A RESOLVED BASIS. Reporting the
        # group LIST here is what turned 'the block contains a non-GAAP
        # group somewhere' into 'this cell is non-GAAP'.
        picked_basis = None

    picked = [i for i in alive if cells[i][1] == want_pct]
    if len(picked) == 1:
        i = picked[0]
        return dict(value=cells[i][0], pct=cells[i][1],
                    cellLine=cells[i][2], cellX=0,
                    # THE GROUP THIS CELL IS IN, not the groups that exist.
                    cellAxes=dict(basis=(picked_basis[i] if picked_basis
                                         else None),
                                  period=None, currency=None,
                                  headers=list(seen),
                                  # ★ THIS READER NEVER CLAIMS ABSENCE. Its
                                  # groups come from a LOOKBACK SEARCH, and a
                                  # lookback that finds nothing cannot tell
                                  # 'the issuer printed no basis header' from
                                  # 'the window was too short' -- the same
                                  # reason a span needs a CLOSE, not a
                                  # LENGTH. So a miss here is OURS.
                                  basisState=('READ' if picked_basis
                                              else 'UNREAD_BY_GRID')),
                    cells=[c[0] for c in cells], groups=seen, why=None)
    if not picked:
        return dict(value=None, cells=[c[0] for c in cells], groups=seen,
                    why='no cell in the %s group matches the row unit %r'
                        % (want or 'only', unit))
    return dict(value=None, cells=[c[0] for c in cells], groups=seen,
                why='%d cells survive basis and unit — nothing separates them'
                    % len(picked))
