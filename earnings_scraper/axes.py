# -*- coding: utf-8 -*-
"""ONE MECHANISM AT 1, 2 OR 3 AXES — the cell grid, indexed by header text.

★★★ THE AXES INDEX THE SAME CELLS AND MUST BE APPLIED TOGETHER. The spec
originally carried columnSelect, basisColumns and rangeColumns as three
independent fields and nothing composed them, so a reader that resolved the
period could never then resolve the basis -- which is why basis:'non-GAAP'
sat inert on every row that declared it. columnAxes replaces all three with
one list over one grid: resolve each axis by HEADER TEXT, intersect, and
refuse on an empty intersection.

★★ NEVER FALL BACK TO AN INDEX. The corpus punishes it three ways:
    ORCL supplemental grid  the 5th of six columns is a FY TOTAL
    HPE                     the SEQUENTIAL quarter sits BETWEEN current and
                            year-ago, at 0.87x -- invisible by magnitude
    ORCL/SNDK reconciliation  six declared columns, the EPS row supplies FOUR
The third is why `ragged` defaults to true: a row may supply fewer cells than
the header declares, and mapping a short list onto a long one silently shifts
every column after the gap.

★ WHAT A GROUP IS. An axis divides the row's cells into equal contiguous
groups, one per distinct header the issuer printed for that axis. SNOW's
highlights table prints 'GAAP Results' and 'Non-GAAP Results(1)' above one
shared grid, and each row block runs
    [GAAP amount, GAAP margin, non-GAAP amount, non-GAAP margin]
so the BASIS axis is two groups of two. The PERIOD axis over the same grid
has ONE distinct period, so it is one group and narrows nothing -- which is
correct, and is the case a reader built only for period could never express.
"""

import re

from . import period as _period

#: a header line is a SHORT line that is only about the axis. The 1,400-char
#: methodology paragraph names both bases a dozen times and is not a header.
MAX_HEADER_CHARS = 48
DEFAULT_LOOKBACK = 60


def _norm(s):
    return ' '.join((s or '').split()).strip().lower()


def header_groups(lines, label_idx, headers, lookback=DEFAULT_LOOKBACK):
    """Distinct axis headers standing above this row, in document order.

    Matched LONGEST FIRST: 'Non-GAAP' contains 'GAAP', and taking the shorter
    one would label the non-GAAP group GAAP -- the exact inversion this axis
    exists to prevent.
    """
    if not headers:
        return []
    ranked = sorted(headers, key=len, reverse=True)
    found = []
    lo = max(0, label_idx - lookback)
    for k in range(lo, label_idx):
        line = lines[k] if k < len(lines) else ''
        if not line or len(line) > MAX_HEADER_CHARS:
            continue
        n = _norm(line)
        for h in ranked:
            hn = _norm(h)
            # the header may carry a footnote marker: 'Non-GAAP Results(1)'
            if n == hn or n.startswith(hn + ' ') or re.match(
                    re.escape(hn) + r'\b', n):
                found.append((k, h))
                break
    # collapse repeats of the same header, keeping first appearance order
    out = []
    for _k, h in found:
        if h not in out:
            out.append(h)
    return out


def partition(n_cells, n_groups):
    """Cell index -> group index, for equal contiguous groups. None if ragged.

    RAGGED REFUSES. Six declared columns and four supplied cells is not a
    grid with two blanks at the end -- it is a row whose gaps are unlocated,
    and every index after the first gap means something else.
    """
    if n_groups <= 0 or n_cells <= 0:
        return None
    if n_cells % n_groups:
        return None
    width = n_cells // n_groups
    return [i // width for i in range(n_cells)]


def _period_assign(lines, label_idx, n_cells, record_quarter, record_year,
                   lookback=DEFAULT_LOOKBACK):
    """Period class per cell, or None when the header cannot be classified."""
    for k in range(label_idx - 1, max(-1, label_idx - lookback), -1):
        line = lines[k] if k < len(lines) else ''
        cc = _period.column_classes(line, record_quarter, record_year)
        if not cc:
            continue
        cc = [c for c in cc if c is not None]
        if not cc:
            continue
        # A LINE THAT CLASSIFIES NOTHING IS NOT A HEADER. '5,950' yields
        # ['UNRESOLVED']; taking it stopped the walk on a DATA line.
        if all(c == _period.UNRESOLVED for c in cc):
            continue
        if len(cc) == n_cells:
            return cc
        groups = partition(n_cells, len(cc))
        if groups is not None:
            return [cc[g] for g in groups]
        return None
    return None


def resolve(lines, label_idx, cells, axes_spec, record_quarter=None,
            record_year=None, want_period='REPORTED'):
    """Which cell the axes select, or a refusal that names what stopped it.

    Returns dict(valueIndex, axisTrace, why). valueIndex is None on refusal.
    """
    axes = (axes_spec or {}).get('axes') or []
    n = len(cells)
    if not axes or n == 0:
        return dict(valueIndex=None, axisTrace=[],
                    why='no axes declared, or the row supplied no cells')

    alive = set(range(n))
    trace = []

    for ax in axes:
        kind = (ax.get('axis') or '').upper()
        want = ax.get('want')
        if kind == 'PERIOD':
            assign = _period_assign(lines, label_idx, n, record_quarter,
                                    record_year)
            if assign is None:
                trace.append((kind, 'unresolved', None))
                continue          # a period it cannot read narrows nothing
            # THE WANTED PERIOD IS THE ROW'S, NOT A CONSTANT. SNDK's three
            # basis rows are GUIDANCE; hardcoding REPORTED refused them all.
            if want_period not in assign:
                # the header resolved but never names what this row wants --
                # narrow nothing rather than refuse on a header that may
                # simply not carry the period axis at all
                trace.append((kind, assign, None))
                continue
            keep = {i for i in alive
                    if i < len(assign) and assign[i] == want_period}
            trace.append((kind, assign, sorted(keep)))
        elif kind in ('BASIS', 'RANGE'):
            groups = header_groups(lines, label_idx, ax.get('headers'))
            if len(groups) < 2:
                trace.append((kind, 'headers not found above the row', None))
                continue
            part = partition(n, len(groups))
            if part is None:
                return dict(valueIndex=None, axisTrace=trace,
                            why='ragged: %d cell(s) do not divide into %d %s '
                                'group(s) (%s)'
                                % (n, len(groups), kind, ', '.join(groups)))
            labels = [groups[g] for g in part]
            if kind == 'RANGE':
                trace.append((kind, labels, sorted(alive)))
                continue          # a range wants BOTH ends; it selects later
            keep = {i for i in alive
                    if _norm(labels[i]).startswith(_norm(want or ''))}
            trace.append((kind, labels, sorted(keep)))
        else:
            trace.append((kind, 'unknown axis', None))
            continue

        if trace[-1][2] is not None:
            alive &= set(trace[-1][2])
        if not alive:
            return dict(valueIndex=None, axisTrace=trace,
                        why='%s axis left no cell: nothing in this row is %r'
                            % (kind, want))

    if len(alive) == 1:
        return dict(valueIndex=alive.pop(), axisTrace=trace, why=None)
    return dict(valueIndex=None, axisTrace=trace, candidates=sorted(alive),
                why='%d cell(s) survive every axis — the grid does not '
                    'separate them' % len(alive))
