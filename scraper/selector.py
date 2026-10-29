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
import time

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

#: hero names that can never match a number -- see RULE 3
_QUALITATIVE = ('(qualitative)', 'commentary', 'framing', 'color', 'colour',
                'named', 'progress', 'timing', 'language')

#: the ONLY fuzzy step, and it is safe because the PERIOD is never
#: inferred from text -- it comes from the hero's explicit appliesTo.
_CANON = (
    ('revenue guide', 'revenue'), ('rev guide', 'revenue'),
    ('net sales', 'revenue'), ('revenue', 'revenue'),
    ('gross margin', 'grossMargin'), (' gm', 'grossMargin'),
    ('earnings per share', 'eps'), ('eps', 'eps'),
    ('operating income', 'operatingIncome'), ('ebit', 'operatingIncome'),
    ('operating margin', 'operatingMargin'),
    ('capital expenditure', 'capex'), ('capex', 'capex'),
    ('free cash flow', 'freeCashFlow'), ('fcf', 'freeCashFlow'),
    ('operating cash flow', 'operatingCashFlow'),
    ('net income', 'netIncome'),
)

#: parser period/table text -> the hero's appliesTo vocabulary
_PERIOD = (
    ('outlook', 'nextQGuidance'), ('guidance', 'nextQGuidance'),
    ('forecast', 'nextQGuidance'),
    ('twelve months', 'TTM'), ('ttm', 'TTM'),
    ('trailing twelve', 'TTM'),
    ('three months', 'currentQuarter'), ('quarter ended', 'currentQuarter'),
    ('nine months', 'nineMonths'), ('six months', 'sixMonths'),
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
    w = re.sub(r'[^a-z]', '', str(word or '').lower())
    if not w:
        return None
    if w.startswith('non') or w == 'adjusted':
        return 'NON_GAAP'
    if w.startswith('gaap') or w == 'usgaap':
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
    t = re.sub(r'\b(q|fy|cy|h|yr|\d+)\b', ' ', t)
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
    hay = '%s %s' % (row.get('period') or '', row.get('table') or '')
    ys = _YEARRE.findall(hay)
    year = max((int(a + b) for a, b in ys), default=0)
    qs = _QNUM.findall(hay)
    return (year, max((int(q) for q in qs), default=0))


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
    hay = norm('%s %s' % (table or '', period or ''))
    for needle, cls in _PERIOD:
        if needle in hay:
            return cls
    # a bare 'Q3 2026' heading is the reported quarter
    if _QTR.search(hay):
        return 'currentQuarter'
    return None


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


def _hero_fields(h):
    if isinstance(h, dict):
        return (h.get('name') or '', h.get('priority'),
                h.get('appliesTo') or '', h.get('unit') or '',
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
    return (_recency(row)[0],
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
            -alias_rank(aliases, row.get('label'), metric),
            _recency(row)[1])


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


def select(parser_rows, ticker, profiles=None, aliases=None):
    """{heroes, qualitative, notFound, overflow, config} for one card."""
    if profiles is None:
        profiles, mtime = load_profiles()
    else:
        mtime = None
    aliases = load_aliases() if aliases is None else aliases
    prof = (profiles or {}).get(str(ticker or '').upper())

    out = {'heroes': [], 'qualitative': [], 'notFound': [], 'overflow': [],
           'config': {'tickers': len(profiles or {}),
                      'heroRows': sum(len(p.get('heroKPIs') or [])
                                      for p in (profiles or {}).values()),
                      'mtime': mtime}}

    # ── RULE 6c: an unmapped ticker still prints something readable ─────
    if not prof:
        out['overflow'] = [dict(r, noProfile=True) for r in parser_rows]
        out['noProfile'] = True
        return out

    dlm = prof.get('documentLabelMap') or {}
    segs = ((prof.get('documentLabelMapSegments') or {}).get('labels')) or {}
    dna = [str(x) for x in (prof.get('doNotAutomate') or [])]
    claimed = set()

    for hero in (prof.get('heroKPIs') or []):
        name, prio, applies, unit, inverted = _hero_fields(hero)
        base = {'hero': name, 'priority': prio, 'appliesTo': applies,
                'unit': unit, 'inverted': inverted}

        # ── RULE 3: qualitative rows are skipped, never reported missing
        low = norm(name)
        if any(w in low for w in _QUALITATIVE):
            out['qualitative'].append(base)
            continue

        # ── RULE 6b: doNotAutomate wins over everything
        hit = next((d for d in dna if low and low[:24] in norm(d)), None)
        if hit:
            out['notFound'].append(dict(base, notGradeable=True,
                                        why=hit[:160]))
            continue

        want_basis, _core = split_basis(name)
        if 'non-gaap' in low:
            want_basis = 'NON_GAAP'
        elif 'gaap' in low:
            want_basis = want_basis or 'GAAP'

        # ── resolution order: explicit map, segments, canonical ─────────
        labels, why_remap, source = [], None, None
        seg_ctx, channel, unverified = None, None, False
        entry = dlm.get(name)
        if isinstance(entry, dict):
            source = 'documentLabelMap'
            if entry.get('needsRemap'):
                why_remap = entry.get('why') or 'needsRemap'
            labels = [str(x) for x in (entry.get('documentLabels') or [])]
            want_basis = want_basis or basis_of(entry.get('basis'))
            seg_ctx = entry.get('segmentContext')
            channel = entry.get('channel')
            unverified = bool(entry.get('needsVerification'))
            if entry.get('period'):
                applies = entry['period']
            # ★★ THE MAP'S UNIT IS THE DOCUMENT'S, THE HERO'S IS THE CARD'S.
            # Kyle stores North America revenue as $B; Amazon prints it in
            # $M. Checking 112,852 for plausibility against $B flagged a
            # correct read as a scale problem -- a warning on the one row
            # that was right.
            if entry.get('unit'):
                unit = entry['unit']
            # ★★★ A STRUCTURAL ABSENCE IS NOT A FAILED MATCH. channel
            # 'call' means the figure is NEVER in the release -- Intel has
            # published no 2027 capex at all. Reporting NOT FOUND there
            # trains you to ignore NOT FOUND everywhere.
            if channel == 'call':
                out['notFound'].append(dict(base, callOnly=True,
                                            channel='call',
                                            why=(entry.get('where') or '')[:160]))
                continue
            if channel == 'prose':
                out['notFound'].append(dict(base, proseChannel=True,
                                            channel='prose',
                                            why=(entry.get('where') or '')[:160]))
                continue
        if not labels:
            for short, sentry in segs.items():
                if short and norm(short) in low:
                    labels = [str(x) for x in
                              ((sentry or {}).get('documentLabels') or [])]
                    source = 'segments'
                    break
        metric = None
        if not labels:
            metric = canonical(name)
            if metric:
                source = 'canonical'

        if why_remap:                       # RULE 6a
            out['notFound'].append(dict(base, needsRemap=True,
                                        why=why_remap[:160]))
            continue
        if not labels and not metric:
            out['notFound'].append(dict(base, reason='no label mapping'))
            continue

        # ★★★ STRIP THE BASIS FROM THE CONFIGURED LABEL TOO, and keep it.
        # The map writes "Non-GAAP gross margin percentage"; rows are keyed
        # on the basis-stripped core. Comparing the two raw meant the
        # label never matched, and the map SILENTLY MADE TWO PRIORITY-1
        # ROWS WORSE than having no map at all.
        wanted = set()
        for x in labels:
            xb, xcore = split_basis(x)
            wanted.add(norm(xcore))
            want_basis = want_basis or xb
        found = []
        for i, row in enumerate(parser_rows):
            rb, rcore = split_basis(row.get('label') or '')
            key = norm(rcore)
            if wanted:
                if key not in wanted:
                    continue
            elif metric not in metrics_for(aliases, row.get('label')):
                continue
            # ── RULE 1: the period must agree, never the label alone ────
            pc = period_class(row.get('table'), row.get('period'),
                              row.get('label'))
            if applies and pc and pc != applies:
                continue
            if applies and not pc and applies != 'currentQuarter':
                continue
            # ── RULE 5: basis never falls back ──────────────────────────
            if want_basis and rb and rb != want_basis:
                continue
            if want_basis and not rb and want_basis == 'NON_GAAP':
                continue
            # ★★★★ SEGMENT CONTEXT. 'Net sales' repeats under North
            # America, International AND AWS with the same period and the
            # same label. Without the section it is a one-in-three guess
            # that looks like a read.
            if seg_ctx and norm(seg_ctx) not in norm(row.get('section')):
                continue
            found.append((i, row))

        if not found:
            out['notFound'].append(dict(base, reason='no (label, period) '
                                        'match', source=source))
            continue

        _c = _repeats(parser_rows)
        found.sort(key=lambda ir: _rank_key(
            ir[1], metric or '', aliases, applies, _c), reverse=True)
        vals = [r for _i, r in found]
        bad = [v for v in vals if not _plausible(v.get('value'), unit)]
        rec = dict(base, source=source,
                   matches=[{'label': v['label'], 'period': v['period'],
                             'value': v['value'], 'raw': v['raw'],
                             'table': v['table']} for v in vals[:4]])
        if bad and len(set(v.get('value') for v in vals)) > 1:
            rec['scaleWarning'] = True      # RULE 4 -- show both, pick none
        if unverified:
            rec['needsVerification'] = True
        if channel:
            rec['channel'] = channel
        out['heroes'].append(rec)
        claimed.update(i for i, _r in found)

    out['heroes'].sort(key=lambda h: (h.get('priority') or 9))
    for i, row in enumerate(parser_rows):
        if i in claimed:
            continue
        _b, core = split_basis(row.get('label') or '')
        if metrics_for(aliases, row.get('label')):
            out['overflow'].append(row)
    return out


def report(result, ticker, heading=''):
    """The 4:01 view: heroes first, misses visible, overflow last."""
    cfg = result.get('config') or {}
    lines = ['%s  %s   profile tickers=%s heroRows=%s mtime=%s'
             % (ticker, heading,
                cfg.get('tickers'), cfg.get('heroRows'),
                time.strftime('%Y-%m-%d %H:%M',
                              time.localtime(cfg['mtime']))
                if cfg.get('mtime') else '-')]
    for h in result.get('heroes') or []:
        # one line per hero: the best match. More than one is shown
        # only when the scale check could not choose between them.
        for m in h['matches'][:(2 if h.get('scaleWarning') else 1)]:
            lines.append('  %-38s %12s  %-14s [p%s %s]'
                         % (m['label'][:38], m['raw'][:12],
                            h.get('appliesTo', '')[:14],
                            h.get('priority'), h['hero'][:34]))
        if h.get('scaleWarning'):
            lines.append('      SCALE WARNING - candidates differ by '
                         'magnitude, none chosen')
    for n in result.get('notFound') or []:
        tag = ('CALL-ONLY - not in release' if n.get('callOnly')
               else 'PROSE CHANNEL' if n.get('proseChannel')
               else 'NOT GRADEABLE' if n.get('notGradeable')
               else 'NOT FOUND')
        lines.append('  %s - p%s %s%s'
                     % (tag, n.get('priority'), n['hero'][:46],
                        (' - ' + n['why'][:60]) if n.get('why') else ''))
    q = result.get('qualitative') or []
    if q:
        lines.append('  -- qualitative (call rows, not parseable) --')
        for n in q:
            lines.append('     %s' % n['hero'][:60])
    ov = result.get('overflow') or []
    if ov:
        lines.append('  -- overflow (%d alias hits not claimed) --' % len(ov))
        for r in ov[:6]:
            lines.append('     %-38s %12s  %s'
                         % (r['label'][:38], r['raw'][:12],
                            r['period'][:22]))
    return '\n'.join(lines)
