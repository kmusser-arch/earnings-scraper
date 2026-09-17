# -*- coding: utf-8 -*-
"""Vertically exploded tables: which cell is the CURRENT QUARTER?

★ THE LAYOUT. HPE, SNOW, APP and SNDK arrive one cell per line, with runs of
blank lines between cells. There are no space-aligned rows and no spatial
header row -- a "column" is a POSITION IN THE CELL SEQUENCE after the row
label, and the header is a NEST of strata above it:

    HPE     For the three months ended
              July 31, 2026 | April 30, 2026 | July 31, 2025
            Net revenue
              12,213        | 10,678         | 9,136

    SNOW    Three Months Ended July 31, | Six Months Ended July 31,
              2026 | 2025               | 2026 | 2025
              Amount | % of Revenue     (x4, one per year)
            Product revenue
              1,491,861 | 96% | 1,090,496 | 95% | 2,826,190 | 96% | ...

    APP     Quarter Ended June 30, | Six Months Ended June 30,
              2026 | 2025 | % Change | 2026 | 2025 | % Change
            Revenue
              1,924 | 1,259 | 53 | 3,766 | 2,418 | 56

★★ WHY THIS IS THE ONLY OPTION, NOT THE BETTER ONE. The wrong-column value is
the same metric in the same unit, and its distance from the right one is a
FUNCTION with a zero:

        wrong / right  =  prior-year-YTD / current-Q  =  2 / (1 + g)

    g =  34%  (HPE)      -> 1.49x   visible
    g =  59%  (APP)      -> 1.26x   plausible blowout
    g =  86%  (AVGO)     -> 1.075x  inside every band
    g = 100%             -> 1.00x   ★★★ IDENTICAL - nothing to detect
    g = 221%  (AVGO AI)  -> 0.62x   visible again

The invisibility zone is centred on ~100% year-on-year growth, which is the
cohort this library trades. At the centre there is no signal of any magnitude
to threshold against, so no heuristic tuned on any corpus can transfer.

★ FIVE CLASSES, because three adjacencies are dangerous and they are different:
REPORTED, SEQUENTIAL (HPE's April 30 middle column), PRIOR_YEAR_Q, YTD, and
PRIOR_YEAR_YTD -- the last being the one that collides at g=100%.

★★ CARDINALITY BEFORE MAPPING. An off-by-one in alignment produces EXACTLY the
defect being guarded against: it hands over the neighbour. A stray cell, a
footnote marker, a lone currency symbol or a wrapped label all shift alignment
silently, so the leaf count and the value count must be EQUAL or the row is
refused. Never map a shorter list onto a longer one.
"""

import re

from .period import PRIOR_PERIOD, REPORTED, UNRESOLVED

#: the five period classes of a vertically exploded column
SEQUENTIAL = 'SEQUENTIAL'
PRIOR_YEAR_Q = 'PRIOR_YEAR_Q'
YTD = 'YTD'
PRIOR_YEAR_YTD = 'PRIOR_YEAR_YTD'
NOT_A_PERIOD = None

#: window phrases, and how many months each spans
_WINDOW = re.compile(
    r'\b(three|six|nine|twelve)\s+months?\s+ended\b'
    r'|\b(quarter)\s+ended\b'
    r'|\b(?:fiscal\s+)?(year)\s+ended\b', re.I)
_MONTHS = {'three': 3, 'six': 6, 'nine': 9, 'twelve': 12,
           'quarter': 3, 'year': 12}

#: a year on its own, or a full date
_YEAR_ONLY = re.compile(r'^\s*(?:19|20)(\d{2})\s*$')
_DATE = re.compile(
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+'
    r'(\d{1,2})\s*,?\s*((?:19|20)\d{2})?', re.I)
_MONTH_NO = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
             'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

#: a change/variance leaf -- never a period
_CHANGE = re.compile(r'%\s*change|\bchange\b|\bvariance\b|\bgrowth\b'
                     r'|\bvs\.?\b|\by/y\b|\byoy\b|\bbasis\s+points?\b', re.I)

#: a SHARE column: a value against a denominator, never a period.
#: ★ 'Amount as a % of Revenue' contains the word 'Amount'.
_SHARE = re.compile(r'%\s*of\s*(?:revenue|total|net|sales)'
                    r'|as\s+a\s+(?:%|percent)', re.I)

#: a measure leaf: what is being reported, not when
_MEASURE = re.compile(r'\bamount\b|%\s*of\s*(?:revenue|total|net)'
                      r'|\bas\s+a\b', re.I)

#: header noise -- scale statements, footnote markers, rules
_NOISE = re.compile(r'^\s*\(?in\s+(?:millions|thousands|billions)'
                    r'|except\s+per\s+share|unaudited|\(\d+\)\s*$'
                    r'|^\s*[-_=]+\s*$|^\s*\$\s*$|^\s*%\s*$', re.I)

_NUMCELL = re.compile(r'^\s*\(?-?\$?\s*([\d,]+\.?\d*)\)?\s*%?\s*$')


#: ★ THE PROSE STOP EXISTS FOR ONE REASON: the intro paragraph contains
#: 'financial results for the three months ended July 31, 2026' and a 'nine
#: months ended' phrase, and absorbing those multiplies the window count. That
#: paragraph runs 300+ characters. A 56-character stop also cut APP's
#: reconciliation ROW LABEL -- 'Loss (income) from discontinued operations, net
#: of income taxes', 63 characters -- and refused the row on my threshold
#: rather than on the document.
PROSE_CHARS = 110

#: ★★ A WINDOW PHRASE IS A HEADER, NOT A SENTENCE. The longest real one in this
#: corpus is 'For the three months ended' at 26 characters. Capping this is
#: what actually protects against the intro paragraph, so the prose stop no
#: longer has to be tight enough to do that job as a side effect.
WINDOW_CHARS = 46


def _is_num(line):
    return bool(_NUMCELL.match(line or ''))


def _is_data_num(line):
    """A numeric cell that is DATA, not a year label.

    ★ '2025' alone matches the numeric pattern. Treating it as data made the
    year stratum look like a data row and stopped the header walk one stratum
    short, refusing SNOW, APP and SNDK on a terminator of my own making.
    """
    if not _is_num(line):
        return False
    t = (line or '').strip()
    if _YEAR_ONLY.match(t):
        return False
    return True


def _cell_kind(text):
    """window | date | change | measure | noise | other"""
    t = ' '.join((text or '').split())
    if not t:
        return None
    if _NOISE.match(t):
        return 'noise'
    if _WINDOW.search(t) and len(t) <= WINDOW_CHARS:
        return 'window'
    if _CHANGE.search(t):
        return 'change'
    if _YEAR_ONLY.match(t) or _DATE.search(t):
        return 'date'
    if _MEASURE.search(t):
        return 'measure'
    return 'other'


def _window_months(text):
    m = _WINDOW.search(text or '')
    if not m:
        return None
    word = (m.group(1) or m.group(2) or m.group(3) or '').lower()
    return _MONTHS.get(word)


def _date_of(text):
    """(year, month) from a header cell, or (year, None), or None."""
    t = ' '.join((text or '').split())
    m = _YEAR_ONLY.match(t)
    if m:
        return (2000 + int(m.group(1)), None)
    m = _DATE.search(t)
    if m:
        year = int(m.group(3)) if m.group(3) else None
        return (year, _MONTH_NO[m.group(1).lower()[:3]])
    return None


#: THE CLOSE IS THE PROSE STOP BELOW; THIS IS ONLY A GUARD against
#: running off the document. It was 900 and HPE's header sits 905
#: lines above its row, so the guard -- not the issuer's boundary --
#: was deciding, and the refusal said 'no period header' when the
#: header was there.
HEADER_GUARD = 4000


def header_cells(lines, label_idx, back=HEADER_GUARD):
    """Header cells above a row label, nearest first reversed to document order.

    Stops at the previous DATA row -- a run of numeric cells means the table
    body has already started and anything above it belongs to another block.
    """
    out = []
    for k in range(label_idx - 1, max(-1, label_idx - back), -1):
        line = lines[k]
        if not line.strip():
            continue
        # ★ DATA CELLS ARE CROSSED, NOT STOPPED AT. APP's Adjusted EBITDA row
        # sits below its Revenue row, so a walk that halts at the first data
        # cell never reaches the header. Crossing is safe because the prose
        # stop bounds the walk and the NEAREST window run is the one used.
        if _is_data_num(line):
            continue
        text = ' '.join(line.split())
        kind = _cell_kind(text)
        if kind is None:
            continue
        # ★ STOP AT PROSE. Walking far enough back reaches the intro paragraph,
        # whose 'financial results for the three months ended...' and 'nine
        # months ended' read as window phrases and multiply the window count.
        if len(text) > PROSE_CHARS and kind != 'noise':
            break
        out.append((k, text, kind))
        _last_k = k
    out.reverse()
    return out


def _join_wrapped(cells):
    """Merge continuation cells into the cell above them.

    ★ SNOW writes one logical header as two lines -- 'Amount as a' then
    '% of Revenue' -- and the gap between them is far smaller than the gap
    between sibling cells. Measured, not assumed: the run's own median gap is
    the yardstick, so a document with different spacing still splits correctly.
    """
    if len(cells) < 3:
        return list(cells)
    gaps = sorted(cells[i + 1][0] - cells[i][0] for i in range(len(cells) - 1))
    median = gaps[len(gaps) // 2]
    if median < 4:
        return list(cells)
    out = [list(cells[0])]
    for prev, cur in zip(cells, cells[1:]):
        if (cur[0] - prev[0]) * 2 < median:
            out[-1][1] = '%s %s' % (out[-1][1], cur[1])
            out[-1][2] = _cell_kind(out[-1][1]) or out[-1][2]
        else:
            out.append(list(cur))
    return [tuple(c) for c in out]


def _absorb_window_dates(cells):
    """A bare date directly after a dateless window phrase belongs to it.

    ★ APP: 'Quarter Ended' + 'June 30,' is ONE window cell. SNOW's 'Three
    Months Ended July 31,' already carries its date, so the '2026' that follows
    is a separate leaf and must not be absorbed. The test is whether the window
    phrase names a date, not how far away the next cell sits -- every gap in
    APP's header is 1 to 4 lines, so spacing separates nothing.
    """
    out = []
    for idx, text, kind in cells:
        _d = _date_of(text)
        if (out and out[-1][2] == 'window' and kind == 'date'
                and _date_of(out[-1][1]) is None
                # ★ a date that carries its own YEAR is a column, not part of
                # the phrase. HPE's 'July 31, 2026' is a column; APP's bare
                # 'June 30,' takes its year from the stratum below.
                and _d is not None and _d[0] is None):
            out[-1] = (out[-1][0], '%s %s' % (out[-1][1], text), 'window')
            continue
        out.append((idx, text, kind))
    return out


def _strata(cells):
    """Group header cells into runs of the same kind, in document order."""
    runs = []
    for idx, text, kind in cells:
        if kind == 'noise':
            continue
        if runs and runs[-1][0] == kind:
            runs[-1][1].append((idx, text))
        elif runs and kind == 'change' and runs[-1][0] == 'date':
            runs[-1][1].append((idx, text))     # '% Change' sits among years
        elif runs and kind == 'date' and runs[-1][0] == 'change':
            runs[-1] = ['date', runs[-1][1] + [(idx, text)]]
        else:
            runs.append([kind, [(idx, text)]])
    return runs


def _classify(months, year, month, record_quarter, record_year, q_months):
    """One leaf's period class.

    ★ THE FIVE CLASSES EXIST BECAUSE THREE ADJACENCIES ARE DANGEROUS AND THEY
    ARE NOT THE SAME PROBLEM: a sequential prior quarter (HPE 0.87x), a
    prior-year quarter, and a prior-year YTD (APP 1.21x, and 1.00x at g=100%).
    Collapsing any two of them re-opens the hole.
    """
    if months is None or year is None:
        return UNRESOLVED
    is_ytd = months is not None and q_months is not None and months > q_months
    if record_year is None:
        return UNRESOLVED
    if year == record_year:
        if is_ytd:
            return YTD
        # same fiscal year, quarter window: current or a SEQUENTIAL earlier one
        if month is None or record_quarter is None:
            return REPORTED
        return REPORTED, month
    if year < record_year:
        return PRIOR_YEAR_YTD if is_ytd else PRIOR_YEAR_Q
    return UNRESOLVED


def fmt_num(v):
    """A cell as a trader reads it: thousands separated, no trailing zeros."""
    if v is None:
        return '?'
    if isinstance(v, float) and v == int(v) and abs(v) >= 1000:
        return '{:,.0f}'.format(v)
    if isinstance(v, float):
        return ('{:,.4f}'.format(v)).rstrip('0').rstrip('.')
    return '{:,}'.format(v)


def render_candidates(values, classes=None, provisional=True):
    """'12,213 [REPORTED?] | 10,678 [SEQUENTIAL?] | 9,136 [PRIOR_YEAR_Q?]'

    ★★ THE CANDIDATES ARE THE CONTENT OF THE REFUSAL. The message being sent
    is 'I could not prove which of these is the quarter', so a version that
    omits the list omits everything actionable and leaves only 'gave up'.

    ★ Classes render with a trailing '?' when the mapping did NOT close --
    printing an unproven class as fact would be asserting a correctness the
    refusal itself denies.
    """
    if not values:
        return None
    mark = '?' if provisional else ''
    out = []
    for i, v in enumerate(values):
        cls = None
        if classes and i < len(classes):
            cls = classes[i]
        if cls:
            out.append('%s [%s%s]' % (fmt_num(v), cls, mark))
        else:
            out.append(fmt_num(v))
    return ' | '.join(out)


def cardinality_ok(n_leaves, n_values):
    """Do the header leaves and the value cells line up exactly?

    ★ A NAMED SEAM SO THE PROBE CAN DISABLE IT. An anti-vacuous test must show
    that the same input MIS-MAPS once this returns True unconditionally --
    otherwise the refusal might be coming from somewhere else and this guard
    is decoration.

    ★★ Equality, not 'at least as many'. A stray cell, a footnote marker, a
    lone currency symbol or a wrapped label all shift alignment silently, and
    mapping a shorter list onto a longer one delivers the NEIGHBOUR -- the
    exact value this whole module exists to keep off the card.
    """
    return n_leaves == n_values


def _column_map_inner(lines, label_idx, value_count, record_quarter=None,
                      record_year=None, quarter_months=3):
    """Period class per value cell of a vertically exploded row.

    Returns dict(classes, valueIndex, leaves, note, candidates). `valueIndex`
    is the index of the single REPORTED, non-change, amount-bearing leaf, or
    None with a `note` saying why the row was refused.

    ★★ EVERY REFUSAL NAMES THE CANDIDATES IT DECLINED. Pass `values` and the
    note becomes a hand-check instead of a dead end -- the refusal is ABOUT
    those numbers, so omitting them omits the message.
    """
    # ★ ONE DECORATION POINT. Threading the candidate list through eleven
    # separate return statements is the twelve-elif problem again -- so the
    # refusals are built as they were and the candidates are attached once,
    # by the wrapper below.
    cells = _absorb_window_dates(_join_wrapped(header_cells(lines, label_idx)))
    runs = _strata(cells)

    # ★ THE NEAREST WINDOW RUN GOVERNS. Crossing data rows can collect an
    # earlier table's header too; this row sits under the LAST one.
    w_at = [k for k, (kind, _) in enumerate(runs) if kind == 'window']
    if not w_at:
        return dict(classes=None, valueIndex=None, leaves=[],
                    note='no period header above this row')
    w = w_at[-1]
    windows = [(i, t) for i, t in runs[w][1]]

    # ★ A ROW LABEL IS NOT A HEADER LEAF. SNOW's 'Revenue:' section heading sat
    # between the measure stratum and the data and became a one-cell leaf
    # stratum, refusing an eight-value row on my own parse.
    leaf_runs = [cs for kind, cs in runs[w + 1:]
                 if kind in ('date', 'change', 'measure')]
    if not leaf_runs:
        return dict(classes=None, valueIndex=None, leaves=[],
                    note='no leaf header stratum below the period phrase')
    leaves = leaf_runs[-1]
    dates_run = None
    for kind, cs in runs[w + 1:]:
        if kind == 'date':
            dates_run = cs

    # ★★ CARDINALITY FIRST. An off-by-one hands over the neighbour, which IS
    # the defect. Refuse rather than map a short list onto a long one.
    if not cardinality_ok(len(leaves), value_count):
        return dict(classes=None, valueIndex=None, leaves=[t for _, t in leaves],
                    note='cell count mismatch: %d header leaves vs %d values'
                         % (len(leaves), value_count))

    n_win = len(windows)
    if value_count % n_win:
        return dict(classes=None, valueIndex=None,
                    leaves=[t for _, t in leaves],
                    note='%d values do not divide across %d period windows'
                         % (value_count, n_win))
    per_window = value_count // n_win

    dates = dates_run or leaves
    if len(dates) % n_win:
        return dict(classes=None, valueIndex=None,
                    leaves=[t for _, t in leaves],
                    note='%d date cells do not divide across %d windows'
                         % (len(dates), n_win))
    per_date = value_count // len(dates) if dates else 1

    # ★★ FIRST PASS: read each leaf's (window months, year, month) off the
    # header. No classification yet -- the classes are RELATIVE and cannot be
    # decided one leaf at a time.
    facts = []
    for i, (_, text) in enumerate(leaves):
        wtext = windows[i // per_window][1]
        dtext = dates[i // per_date][1] if dates else ''
        leaf_kind = _cell_kind(text)
        if leaf_kind == 'change' or _CHANGE.search(text):
            facts.append(None)                      # a change column
            continue
        # ★ SHARE FIRST. SNOW labels its percentage columns 'Amount as a %
        # of Revenue', which CONTAINS the word Amount -- so an amount test run
        # first admitted the share column as a period and produced TWO
        # REPORTED columns. What makes a column a share is its denominator.
        if _SHARE.search(text):
            facts.append(None)
            continue
        if leaf_kind == 'measure' and not re.search(r'\bamount\b', text,
                                                    re.I):
            facts.append(None)                      # some other measure column
            continue
        got = _date_of(dtext) or _date_of(wtext)
        months = _window_months(wtext)
        if got is None or months is None:
            facts.append('?')
            continue
        year, month = got
        if year is None:
            _alt = _date_of(wtext)
            year = _alt[0] if _alt else None
        facts.append((months, year, month))

    real = [f for f in facts if isinstance(f, tuple)]
    if not real:
        return dict(classes=None, valueIndex=None,
                    leaves=[t for _, t in leaves],
                    note='no column in this header resolves to a period')
    years = [f[1] for f in real if f[1] is not None]
    if not years:
        return dict(classes=None, valueIndex=None,
                    leaves=[t for _, t in leaves],
                    note='no column in this header names a year')
    # ★ THE LATEST YEAR IS THE REPORTED ONE, read off the header rather than
    # compared against a fiscal record year that does not share its calendar.
    top_year = max(years)
    q_window = min(f[0] for f in real)
    # ★ THE SHORTEST WINDOW IS THE QUARTER -- unless it is longer than a
    # quarter, in which case this block has no quarter column at all. HPE's
    # nine-month table must refuse, not surrender its YTD figure.
    if quarter_months is not None and q_window > quarter_months:
        return dict(classes=[None] * len(leaves), valueIndex=None,
                    leaves=[t for _, t in leaves],
                    note='header names no window shorter than %d months — '
                         'this block has no quarter column' % q_window)

    classes, months_seen = [], []
    for f in facts:
        if f is None:
            classes.append(NOT_A_PERIOD)
            months_seen.append(None)
            continue
        if f == '?':
            classes.append(UNRESOLVED)
            months_seen.append(None)
            continue
        months, year, month = f
        is_ytd = months > q_window
        current = (year == top_year)
        if is_ytd:
            classes.append(YTD if current else PRIOR_YEAR_YTD)
            months_seen.append(None)
        elif current:
            classes.append(REPORTED)
            months_seen.append(month)
        else:
            classes.append(PRIOR_YEAR_Q)
            months_seen.append(None)

    # ★ SEQUENTIAL. HPE's header names July 31 2026, April 30 2026 and
    # July 31 2025: two same-year quarter columns, the middle one the PRIOR
    # QUARTER at 0.87x -- invisible, and verdict-flipping if taken. The latest
    # month among the reported-year quarter columns is the current one.
    same_year = [(i, m) for i, (c, m) in enumerate(zip(classes, months_seen))
                 if c == REPORTED and m is not None]
    if len(same_year) > 1:
        newest = max(m for _, m in same_year)
        for i, m in same_year:
            if m != newest:
                classes[i] = SEQUENTIAL

    reported = [i for i, c in enumerate(classes) if c == REPORTED]
    if len(reported) != 1:
        return dict(classes=classes, valueIndex=None,
                    leaves=[t for _, t in leaves],
                    note='%d columns classify as REPORTED — refusing rather '
                         'than choosing' % len(reported))
    return dict(classes=classes, valueIndex=reported[0],
                leaves=[t for _, t in leaves], note=None)


#: 'up 6.2 ppt', 'up 1,050 basis points', 'down 30 bps', 'up 8%'
_STATED_DELTA = re.compile(
    r'\b(up|down|increased|decreased|grew|declined)\s+'
    r'([\d,]+\.?\d*)\s*'
    r'(ppt|percentage\s+points?|basis\s+points?|bps|%)', re.I)

#: how far from the row label a stated delta may sit and still describe it
DELTA_WINDOW = 40


def stated_deltas(lines, label_idx, window=DELTA_WINDOW):
    """(magnitude, additive) for every stated delta near a row label."""
    out = []
    for k in range(label_idx, min(len(lines), label_idx + window)):
        for m in _STATED_DELTA.finditer(lines[k] or ''):
            try:
                v = float(m.group(2).replace(',', ''))
            except ValueError:
                continue
            unit = m.group(3).lower()
            additive = ('ppt' in unit or 'percentage' in unit
                        or 'bas' in unit or 'bps' in unit)
            if 'bas' in unit or 'bps' in unit:
                v = v / 100.0
            if m.group(1).lower() in ('down', 'decreased', 'declined'):
                v = -v
            out.append((v, additive, ' '.join(m.group(0).split())))
    return out


def _closes(values, v, additive):
    """DISTINCT current-period members consistent with a stated delta.

    ★ Distinct VALUES, not index pairs. A highlights table that prints the same
    pair four times has one solution, not four.
    """
    firsts = set()
    for a in values:
        for b in values:
            if a == b:
                continue
            if additive:
                ok = abs((a - b) - v) < 0.051
            elif b:
                ok = abs((a / b - 1) * 100.0 - v) < 0.75
            else:
                ok = False
            if ok:
                firsts.add(round(a, 6))
    return firsts


def delta_closure(lines, label_idx, values, window=DELTA_WINDOW):
    """Which value is the current period, per the document's stated deltas?

    Returns dict(valueIndex, value, note, evidence). valueIndex is None with a
    note whenever the deltas are absent, fail to close, or disagree -- the row
    is then refused rather than resolved by preference.
    """
    ds = stated_deltas(lines, label_idx, window)
    if not ds:
        return dict(valueIndex=None, value=None, evidence=[],
                    note='no stated delta within %d lines of the row' % window)
    agreed, evidence = None, []
    for v, additive, text in ds:
        firsts = _closes(values, v, additive)
        if not firsts:
            continue
        if len(firsts) > 1:
            return dict(valueIndex=None, value=None, evidence=evidence,
                        note='delta %r closes on %d different values — '
                             'ambiguous' % (text, len(firsts)))
        got = firsts.pop()
        evidence.append('%s -> %g' % (text, got))
        if agreed is None:
            agreed = got
        elif abs(agreed - got) > 0.051:
            # ★ TWO VALID DELTAS FOR TWO DIFFERENT WINDOWS. APP states a change
            # for the quarter pair AND one for the six-month pair; each is
            # correct and they name different cells. Preferring one would be a
            # guess dressed as arithmetic.
            return dict(valueIndex=None, value=None, evidence=evidence,
                        note='stated deltas disagree on the current period '
                             '(%g vs %g) — they describe different windows'
                             % (agreed, got))
    if agreed is None:
        return dict(valueIndex=None, value=None, evidence=evidence,
                    note='no pair of values reproduces any stated delta')
    for i, val in enumerate(values):
        if abs(val - agreed) < 0.051:
            return dict(valueIndex=i, value=agreed, evidence=evidence,
                        note=None)
    return dict(valueIndex=None, value=None, evidence=evidence,
                note='closure produced a value not present in the row')


def column_map(lines, label_idx, value_count, record_quarter=None,
               record_year=None, quarter_months=3, values=None):
    """column_map, with every REFUSAL carrying the candidates it declined.

    ★★★ THE FAILURE MODE OF A CORRECT REFUSAL IS A TRADER WHO STOPS READING
    REFUSALS. 'cell count mismatch: 3 header leaves vs 4 values' is true and
    unusable; the same refusal followed by
    'candidates 12,213 [REPORTED?] | 10,678 [SEQUENTIAL?] | 9,136
    [PRIOR_YEAR_Q?]' is a four-second hand-check on a hero that would
    otherwise be lost.

    ★ ONE DECORATION POINT, not eleven return statements. Every previous
    attempt to add a cross-cutting property to a multi-branch function in this
    codebase left a branch behind.
    """
    got = _column_map_inner(lines, label_idx, value_count,
                            record_quarter=record_quarter,
                            record_year=record_year,
                            quarter_months=quarter_months)
    if got.get('valueIndex') is not None or not values:
        got.setdefault('candidates', None)
        return got
    cand = render_candidates(values, got.get('classes'))
    got['candidates'] = cand
    if cand and got.get('note'):
        got['note'] = '%s — candidates %s' % (got['note'], cand)
    elif cand:
        got['note'] = 'candidates %s' % cand
    return got
