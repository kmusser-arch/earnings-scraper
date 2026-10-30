# -*- coding: utf-8 -*-
r"""EVERY LABELLED NUMBER IN A RELEASE, VERBATIM. NOTHING ELSE.

★★★★★ THIS MODULE INTERPRETS NOTHING. No consensus, no grading, no
canonical names, no derived metrics, no GAAP/non-GAAP reconciliation. It
emits what the issuer printed, with the words the issuer used.

    {table, label, period, value, raw}

Every prior reader in this repo failed by DECIDING something -- which
column was the quarter, which of two bases a row meant, which card row a
figure belonged to. Intel prints BOTH of these, four cells apart:

    GAAP gross margin percentage       43.0 %
    Non-GAAP gross margin percentage   44.1 %

Keep the labels and the distinction is free. Rewrite them to `grossMargin`
and one of the two has to be thrown away -- which is exactly how a wrong
number reaches a card wearing a right label.

★★ AND IT READS TABLES, NOT SENTENCES. The prose rounds and the table does
not: Amazon's paragraph says $201.9 billion, its statement says 201,944;
Intel's summary says $16.5 and its statement says 16,513. A narrative
sentence is a summary of a number, not the number.

★ NO TICKER APPEARS ANYWHERE IN THIS FILE. It must run on an issuer no one
has seen, with no configuration.
"""

import re
from html.parser import HTMLParser

#: a cell that is only a currency mark, a sign or a footnote marker carries
#: no value of its own -- the figure sits in the NEXT cell. EDGAR splits
#: '$ 16,513' across two <td>s constantly.
_ORPHAN = re.compile(r'^[\s$€£¥(),.%*†‡+\-–—]*$')

#: '1,234', '(1,234)', '$1,234.5', '43.0%', '(0.12)%', '1,234 )'
_NUMERIC = re.compile(
    r'^[\s$€£¥]*\(?\s*-?\s*[\d,]+(?:\.\d+)?\s*\)?[\s%]*\)?[\s*†‡]*$')

_WS = re.compile(r'\s+')


def _clean(s):
    return _WS.sub(' ', (s or '')).strip()


def to_number(raw):
    """A float from a printed cell, or None. Parens mean negative."""
    if raw is None:
        return None
    s = _clean(raw)
    if not s:
        return None
    if _RANGE.match(s):
        return None            # a range has no single value; `raw` carries it
    # THE OPENING PAREN IS THE SIGNAL; THE CLOSING ONE IS OFTEN A CELL OF
    # ITS OWN. EDGAR emits Oracle's reconciliation as five cells --
    # '$' '12,617' '$' '(1,423' ')' -- so requiring BOTH parens in one
    # string dropped the sign on 660 rows across 15 documents, among them
    # interest expense, every non-GAAP adjustment column, and a free cash
    # flow of -5,396 that read as +5,396 while the same release's prose
    # said "negative $5 billion".
    #
    # NOT a new rule: parse.py:621 already took the leading paren alone as
    # the signal. This is that rule, ported, with the matched pair kept so
    # a single intact cell still works.
    head = s.lstrip('$ ')
    neg = head.startswith('(') or ('(' in s and ')' in s)
    s = re.sub(r'[^\d.\-]', '', s.replace(',', ''))
    if s in ('', '-', '.', '-.'):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if (neg and v > 0) else v


#: '$15.0 - $16.0', '15.0 to 16.0' -- a GUIDE RANGE in a single cell.
#: Intel's whole Q4 revenue outlook is one of these, and dropping it loses
#: the guide entirely. Kept with value=None and `raw` intact, per rule 6:
#: a cell that will not reduce to ONE number is still a reported figure.
_RANGE = re.compile(
    r'^[\s$€£¥]*\(?-?[\d,]+(?:\.\d+)?\)?\s*%?\s*(?:-|–|—|to)\s*'
    r'[\s$€£¥]*\(?-?[\d,]+(?:\.\d+)?\)?\s*%?[\s*†‡]*$')


def is_range(raw):
    s = _clean(raw)
    return bool(s) and bool(_RANGE.match(s))


def is_value(raw):
    s = _clean(raw)
    if not s or _ORPHAN.match(s):
        return False
    return bool(_NUMERIC.match(s)) or bool(_RANGE.match(s))


class _Tables(HTMLParser):
    """Tables as grids, with colspan expanded and the text above each one.

    ★ COLSPAN IS NOT COSMETIC. Intel heads six columns with two spanning
    cells, 'GAAP' and 'Non-GAAP'. Dropping the span collapses them to
    columns 0 and 1 and every figure after the third lands under the wrong
    heading -- a silent column shift, the defect this repo has paid for
    most.
    """

    def __init__(self):
        HTMLParser.__init__(self)
        self.tables = []            # [(heading, [[cell, ...], ...])]
        self._depth = 0
        self._stack = []            # one frame per open <table>
        self._outside = []          # text seen outside any table
        self._cell = None
        self._span = 1

    # ── structure ───────────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._depth += 1
            self._stack.append({'rows': [], 'row': None,
                                'heading': _clean(' '.join(
                                    self._outside[-6:]))[-120:]})
            self._outside = []
            return
        if not self._stack:
            return
        top = self._stack[-1]
        if tag == 'tr':
            top['row'] = []
        elif tag in ('td', 'th'):
            self._cell = []
            self._span = 1
            for k, v in attrs:
                if k == 'colspan':
                    try:
                        self._span = max(1, min(24, int(v)))
                    except (TypeError, ValueError):
                        self._span = 1

    def handle_endtag(self, tag):
        if tag == 'table':
            if self._stack:
                fr = self._stack.pop()
                if fr['row']:
                    fr['rows'].append(fr['row'])
                if fr['rows']:
                    self.tables.append((fr['heading'], fr['rows']))
            self._depth = max(0, self._depth - 1)
            return
        if not self._stack:
            return
        top = self._stack[-1]
        if tag == 'tr':
            if top['row'] is not None:
                top['rows'].append(top['row'])
                top['row'] = None
        elif tag in ('td', 'th'):
            if self._cell is not None and top['row'] is not None:
                text = _clean(''.join(self._cell))
                top['row'].append(text)
                # a spanning cell occupies its extra columns, empty
                for _ in range(self._span - 1):
                    top['row'].append('')
            self._cell = None
            self._span = 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif not self._stack:
            t = _clean(data)
            if t:
                self._outside.append(t)


#: a bare four-digit year, which is a COLUMN HEADER and not a figure
_YEAR = re.compile(r'^\s*(19|20)\d{2}\s*$')


def _is_section_row(row):
    """A label-only row that heads a GROUP OF ROWS, not a set of columns.

    ★★★★ AMAZON'S SEGMENT TABLE IS BUILT THIS WAY. 'North America
    Segment:' sits alone on a row, then 'Net sales', 'Operating income' and
    the rest belong to it; then 'International Segment:' and the SAME
    labels repeat. Read as a column header it carried rightward across
    every column, so all three segments' net sales came back claiming North
    America -- 112,852 and 43,108 and 45,984, indistinguishable.

    One non-empty cell, in the first column, carrying no value.
    """
    filled = [(j, _clean(c)) for j, c in enumerate(row) if _clean(c)]
    if len(filled) != 1:
        return False
    j, text = filled[0]
    return j == 0 and not is_value(text) and not _ORPHAN.match(text)


def _is_header_row(row):
    """A row that labels columns rather than reporting them.

    ★★★ A YEAR ROW IS NUMERIC AND IS NOT DATA. Amazon heads its columns
    with 'Three Months Ended' on one line and '2025 / 2026 / 2025 / 2026'
    on the next. Treating the second as data stops the header walk one row
    early, and BOTH three-month columns then read 'Three Months Ended
    September 30,' with no year -- two different quarters, indistinguishable
    in the output, which is rule 2 broken silently.
    """
    vals = [c for c in row if is_value(c)]
    if not vals:
        return True
    if not all(_YEAR.match(_clean(c)) for c in vals):
        return False
    # a year row carries no prose label of its own
    return not any(_clean(c) and not is_value(c) and not _ORPHAN.match(c)
                   for c in row)


def _headers(rows):
    """(column -> header text, index of the first data row).

    Header rows are the leading rows that carry NO value cell. Several are
    combined top-down, so 'GAAP' above 'Q3 2026' reads 'GAAP Q3 2026'.
    ★ A spanning header is carried RIGHTWARD across the columns it covers,
    which is what makes the GAAP / non-GAAP halves separable at all.
    """
    width = max((len(r) for r in rows), default=0)
    cols = [[] for _ in range(width)]
    first_data = 0
    for i, row in enumerate(rows):
        if _is_section_row(row) or not _is_header_row(row):
            first_data = i
            break
        carry = ''
        for j in range(width):
            cell = _clean(row[j]) if j < len(row) else ''
            if cell:
                carry = cell
            elif carry and j < len(row):
                cell = carry           # the span reaches this column
            if cell and cell not in cols[j]:
                cols[j].append(cell)
        first_data = i + 1
    return [' '.join(c).strip() for c in cols], first_data


def from_html(html_text, max_tables=60):
    """[{table, label, period, value, raw}] for every labelled number."""
    p = _Tables()
    try:
        p.feed(html_text or '')
        p.close()
    except Exception:                                       # noqa: BLE001
        pass
    out = []
    for heading, rows in p.tables[:max_tables]:
        rows = [r for r in rows if any(_clean(c) for c in r)]
        if len(rows) < 2:
            continue
        cols, start = _headers(rows)
        section = ''
        for row in rows[start:]:
            if _is_section_row(row):
                section = _clean([c for c in row if _clean(c)][0])
                continue
            # the label is the first cell that is not a value and not an
            # orphan punctuation cell
            label, label_at = '', -1
            for j, cell in enumerate(row):
                c = _clean(cell)
                if c and not is_value(c) and not _ORPHAN.match(c):
                    label, label_at = c, j
                    break
            if not label:
                continue
            for j in range(label_at + 1, len(row)):
                raw = _clean(row[j])
                if not is_value(raw):
                    continue
                period = cols[j] if j < len(cols) else ''
                out.append({'table': heading, 'label': label,
                            'section': section, 'period': period,
                            'value': to_number(raw), 'raw': raw})
    return out
