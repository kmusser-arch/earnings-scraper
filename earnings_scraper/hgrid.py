# -*- coding: utf-8 -*-
"""The HORIZONTAL grid, read by COLUMN POSITION — the issuer draws the columns.

★★★ THE RULE LINE IS THE COLUMN DEFINITION, AND THE ISSUER PRINTS IT. Both
horizontal releases underline their headers, and every data cell falls inside
exactly one dash run:

    ORCL  ----  ---------------  -------------------  --------  ...
          cells at x 36, 48, 68, 79, 88, 101 land in runs 2..7
    AVGO  ----------------------   -------  -------  --------  ...
          cells at x 26, 35, 45, 54, 63, 73 land in runs 1..6

So the grid needs no index arithmetic and no cell counting. An index rule
takes ORCL's fifth column believing it is a quarter when it is a FY total; an
x-position rule cannot, because it is reading the same marks a human reads.

★★ EVERY RULE LINE IS A STRATUM. AVGO prints two: one under 'GAAP / Non-GAAP'
that defines the BASIS groups, and one under 'Q3 26 / Q3 25 / Change' that
defines the periods within them. A cell belongs to one span in EACH stratum,
so its full description is 'Q3 26' plus 'Non-GAAP' -- the two axes crossed,
which is what the spec means by columnAxes over one grid.

★ ORCL PRINTS A CURRENCY STRATUM IN THE SAME BLOCK: its last two columns are
'% Increase in US $' and '% Increase in Constant Currency'. The sixth axis is
not exotic; it is already drawn in the header of the release that produced the
founding case.

RAGGED IS FREE HERE. A row that supplies fewer cells than the header declares
simply leaves some spans empty -- there is no short list to map onto a long
one, and therefore no silent renumbering after a gap.
"""

import re

RULE = re.compile(r'-{3,}')
NUM = re.compile(r'\(?\$?\s*(-?[\d,]+(?:\.\d+)?)\s*%?\)?')

#: a rule line is mostly dashes and nothing else
_RULE_LINE = re.compile(r'^[\s\-]*$')

#: how far above a row to look for its header block, as a GUARD only; the
#: close is the prose boundary, the same one axes.py uses.
GUARD = 60

#: strata of ONE header block are adjacent; a wider gap is another table
MAX_RULE_GAP = 8


def is_prose_line(line):
    """Is this line a SENTENCE, as opposed to a wide table header?

    ★ A WIDE HEADER IS NOT A SENTENCE. ORCL's column rule splits into eight
    dash tokens and its header line into nine ('2026 Revenues 2025 Revenues
    in US $ Currency (1)'), so a bare word count called both prose and stopped
    the walk on the very lines that define the grid. Prose has letters and
    runs on; a header is mostly short tokens and figures.
    """
    t = (line or '').strip()
    if not t or not any(ch.isalpha() for ch in t):
        return False                       # a rule line is never prose
    words = t.split()
    if not words:
        return False
    alpha = [w for w in words if any(c.isalpha() for c in w)]
    if len(alpha) < 6:
        return False
    # a sentence's words are mostly long-ish and mostly not figures
    figures = sum(1 for w in words if any(c.isdigit() for c in w))
    return figures * 3 < len(words)


def is_rule_line(line):
    t = (line or '').strip()
    return bool(t) and bool(_RULE_LINE.match(t)) and t.count('-') >= 6


def rule_spans(line):
    """[(x0, x1)] — one span per dash run."""
    return [(m.start(), m.end()) for m in RULE.finditer(line or '')]


def cell_positions(line):
    """[(x, text)] for every numeric cell on a data row, with its column x."""
    out = []
    for m in NUM.finditer(line or ''):
        raw = m.group(1)
        if not raw or not any(ch.isdigit() for ch in raw):
            continue
        out.append((m.start(1), m.group(0).strip()))
    return out


def _covering(spans, x):
    for i, (a, b) in enumerate(spans):
        if a <= x < b:
            return i
    # a cell may sit a character outside its rule on a right-aligned column
    best, bestd = None, 3
    for i, (a, b) in enumerate(spans):
        d = 0 if a <= x < b else min(abs(x - a), abs(x - b))
        if d < bestd:
            best, bestd = i, d
    return best



def clean_slice(src, a, b):
    """The span's text, or '' when the slice CUT A WORD.

    A centred title spans the whole table, so slicing it at one column's
    x-range returns a fragment -- 'Year 2026 Financial Highl' and 'hts' from
    AVGO's section title, 'CONDENSED CONSOLIDATED STATEMENTS' from ORCL's. A
    real column header sits INSIDE its column, so its slice is bounded by
    whitespace. Cutting a word is the tell that the line belongs to the table,
    not to the column.
    """
    line = src or ''
    if a > 0 and a <= len(line) - 1:
        if line[a - 1:a].strip() and line[a:a + 1].strip():
            return ''
    if b < len(line):
        if line[b - 1:b].strip() and line[b:b + 1].strip():
            return ''
    return line[a:b].strip()


def strata(lines, label_idx, guard=GUARD, is_boundary=None):
    """[(rule_index, spans, [header text per span])] above a data row.

    Each rule line is one stratum, nearest first. The header text for a span
    is read from the lines between that rule and the rule above it, sliced at
    the span's own x-range -- which is why a centred group label like 'GAAP'
    lands on its whole group rather than on one column.
    """
    out = []
    lo = max(0, label_idx - guard)
    rules = []
    last = label_idx
    for k in range(label_idx - 1, lo - 1, -1):
        line = lines[k] if k < len(lines) else ''
        if is_rule_line(line):
            # ★ THE RULE CHAIN IS ITS OWN CLOSE. Strata of one header block
            # sit within a few lines of each other; when the gap opens up the
            # block above belongs to a different table.
            if rules and last - k > MAX_RULE_GAP:
                break
            rules.append(k)
            last = k
            continue
        if is_boundary is not None and is_prose_line(line) and is_boundary(line):
            break
    for n, k in enumerate(rules):
        spans = rule_spans(lines[k])
        if not spans:
            continue
        # ★ A STRATUM'S HEADER IS ADJACENT TO ITS RULE. Reaching further
        # up pulls the table TITLE into every column: ORCL's outermost
        # rule spans the full width, so 'CONDENSED CONSOLIDATED
        # STATEMENTS OF OPERATIONS' sliced cleanly and read as a header.
        top = rules[n + 1] + 1 if n + 1 < len(rules) else max(lo, k - 2)
        texts = []
        for (a, b) in spans:
            parts = []
            for j in range(top, k):
                src = lines[j] if j < len(lines) else ''
                if is_rule_line(src):
                    continue          # a rule is not header TEXT
                seg = clean_slice(src, a, b)
                if seg:
                    parts.append(seg)
            texts.append(' '.join(parts))
        out.append((k, spans, texts))
    return out


def describe_cells(lines, label_idx, guard=GUARD, is_boundary=None):
    """[(x, raw, [header text, outer stratum last])] for the row's cells.

    The description of a cell is every stratum's header for the span it sits
    in -- 'Q3 26' from the period rule and 'Non-GAAP' from the basis rule --
    so the two axes are crossed without either being an index.
    """
    row = lines[label_idx] if label_idx < len(lines) else ''
    cells = cell_positions(row)
    if not cells:
        return []
    layers = strata(lines, label_idx, guard, is_boundary)
    out = []
    inner = layers[0][1] if layers else []
    for x, raw in cells:
        desc = []
        own = None
        j = _covering(inner, x) if inner else None
        if j is not None:
            own = inner[j]
        for _k, spans, texts in layers:
            i = _covering(spans, x)
            if i is not None and texts[i]:
                desc.append(texts[i])
                continue
            # ★ A CELL NO OUTER SPAN COVERS STILL HAS ITS OWN COLUMN. ORCL's
            # outer rule stops before the two '% Increase' columns, so 'in
            # Constant' was dropped and the currency column became
            # indistinguishable from the US-dollar one.
            if own is not None:
                top = _k - 2
                parts = []
                for row_i in range(max(0, top), _k):
                    src = lines[row_i] if row_i < len(lines) else ''
                    if is_rule_line(src):
                        continue
                    seg = clean_slice(src, own[0], own[1])
                    if seg:
                        parts.append(seg)
                if parts:
                    desc.append(' '.join(parts))
        out.append((x, raw, desc))
    return out


# ══ SELECTION ═════════════════════════════════════════════════════════════
#
# ★★★ CLASSIFIED BY RELATION, NOT BY POSITION. The reported column is the
# LATEST period the header names, not the first cell -- ORCL's supplemental
# grid puts a FY TOTAL fifth and HPE sits the sequential quarter BETWEEN
# current and year-ago at 0.87x, so any index rule is wrong on one of them.
#
# ★★ AND RELATION SIDESTEPS THE FISCAL/CALENDAR TRAP. ORCL's Q1 FY27 report
# heads its columns 2026 and 2025 -- CALENDAR years -- while the record's
# fiscalYear is 2027. Comparing the header to the record's own year would
# call the reported column prior-year. Comparing the columns to EACH OTHER
# cannot: the later of 2026 and 2025 is the one being reported, whatever the
# fiscal label says.

_YEAR = re.compile(r'(?<!\d)(20\d\d|\d\d)(?!\d)')
_QTR = re.compile(r'Q([1-4])', re.I)
_DELTA_COL = re.compile(r'change|increase|decrease|%\s*of|growth', re.I)
_GUIDE_COL = re.compile(r'guidance|guide|outlook|expected', re.I)


def column_period(desc):
    """(year, quarter) named by a column description, or None."""
    text = ' '.join(desc or [])
    if not text or _GUIDE_COL.search(text):
        return None
    q = _QTR.search(text)
    y = None
    # ★ A TWO-DIGIT YEAR IS ONLY A YEAR WHERE THE ISSUER WRITES IT AS ONE.
    # 'Three Months Ended August 31,' made 2031 the latest period and handed
    # the row a '% of Revenues' column. After a quarter token two digits are
    # a year ('Q3 26'); everywhere else four digits are required.
    if q:
        tail = text[q.end():q.end() + 6]
        m2 = re.search(r'(?<!\d)(\d\d)(?!\d)', tail)
        if m2:
            y = 2000 + int(m2.group(1))
    for m in re.finditer(r'(?<!\d)(20\d\d)(?!\d)', text):
        val = int(m.group(1))
        y = val if y is None else max(y, val)
    if y is None:
        return None
    return (y, int(q.group(1)) if q else 0)


def column_basis(desc):
    text = ' '.join(desc or []).lower()
    if 'non-gaap' in text or 'non gaap' in text:
        return 'non-GAAP'
    if 'gaap' in text:
        return 'GAAP'
    return None


def column_currency(desc):
    text = ' '.join(desc or []).lower()
    if 'constant' in text and 'currenc' in text:
        return 'CONSTANT_CURRENCY'
    if 'us $' in text or 'usd' in text or 'u.s. dollar' in text:
        return 'USD'
    return None


def is_delta_column(desc):
    """A change or share-of-total column is not a level, whatever its unit."""
    return bool(_DELTA_COL.search(' '.join(desc or [])))


def select(lines, label_idx, spec, guard=GUARD, is_boundary=None):
    """The cell this row's axes select on a horizontal grid, or a refusal.

    Returns dict(value, raw, description, why). Refuses rather than guessing:
    an empty intersection names the axis that emptied it.
    """
    cells = describe_cells(lines, label_idx, guard, is_boundary)
    if not cells:
        return dict(value=None, why='no numeric cells on this row')

    want_basis = (spec or {}).get('basis')
    want_cur = (spec or {}).get('currencyBasis')
    alive = list(range(len(cells)))
    trace = []

    # ★ A CHANGE COLUMN IS ONLY NOISE TO A LEVEL ROW. ORCL's last two columns
    # ARE '% Increase in US $' and '% Increase in Constant Currency', so a
    # growth row wants exactly what a revenue row must discard. The row's own
    # unit decides: a ($) row drops them, a (%) row keeps them.
    unit = ((spec or {}).get('documentUnit') or '').strip()
    if not unit.startswith('%'):
        keep = [i for i in alive if not is_delta_column(cells[i][2])]
        if keep:
            alive = keep
            trace.append('dropped change/share columns')

    if want_basis:
        keep = [i for i in alive
                if (column_basis(cells[i][2]) or want_basis) == want_basis]
        if not keep:
            return dict(value=None, description=[c[2] for c in cells],
                        why='BASIS %s: no column on this row is that basis'
                            % want_basis)
        alive, _t = keep, trace.append('basis=%s' % want_basis)

    if want_cur:
        # ★ SILENCE IS NOT CONFLICT. A grid that names no currency is showing
        # the reported figure -- the same rule the prose path uses, where a
        # single qualifier marks the exception and the unqualified figure is
        # REPORTED. ORCL's supplemental grid carries no currency header at
        # all, and requiring an explicit 'in USD' there rejected every column
        # of the table holding 19,345.
        named = [i for i in alive if column_currency(cells[i][2])]
        if named:
            # THE GRID NAMES CURRENCIES, so an unqualified column is not a
            # candidate: ORCL's Cloud row prints '% Increase in US $' beside
            # '% Increase in Constant Currency', and accepting the silent
            # columns too put the level columns back in the running.
            keep = [i for i in named
                    if column_currency(cells[i][2]) == want_cur]
        else:
            # SILENCE IS NOT CONFLICT. A grid naming no currency at all is
            # showing the reported figure -- the same rule the prose path
            # uses. ORCL's supplemental grid has no currency header, and
            # demanding an explicit 'in USD' rejected every column of it.
            keep = list(alive) if want_cur in ('USD', 'REPORTED') else []
        if not keep:
            return dict(value=None, description=[c[2] for c in cells],
                        why='CURRENCY %s: no column on this row is that '
                            'currency' % want_cur)
        alive = keep
        trace.append('currency=%s' % want_cur)

    dated = [(column_period(cells[i][2]), i) for i in alive]
    dated = [(p, i) for p, i in dated if p]
    if len(dated) >= 2:
        # THE LATEST PERIOD IS THE REPORTED ONE, by relation to the others.
        best = max(dated)[1]
        return dict(value=cells[best][1], raw=cells[best][1],
                    description=cells[best][2], why=None,
                    columns=[c[2] for c in cells], how=trace + ['latest period'])
    if len(alive) == 1:
        i = alive[0]
        return dict(value=cells[i][1], raw=cells[i][1],
                    description=cells[i][2], why=None,
                    columns=[c[2] for c in cells], how=trace + ['sole survivor'])
    return dict(value=None, description=[c[2] for c in cells],
                why='%d columns survive and the header names fewer than two '
                    'periods to order them' % len(alive))
