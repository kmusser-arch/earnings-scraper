# -*- coding: utf-8 -*-
r"""GUIDANCE STATED IN SENTENCES — a second channel, clearly labelled.

★★★★★ GUIDANCE CARRIES 60% OF THE SCORECARD (next-Q 30% + FY 30%), and
where it lives is an issuer's house style, not a rule. Intel prints a
Business Outlook TABLE; Amazon prints bullets:

    Net sales are expected to be between $240.0 billion and $247.0 billion
    Operating income is expected to be between $28.5 billion and $33.5 billion

A table-anchored parser reads Intel's guide perfectly and is blind to
Amazon's -- on the highest-weighted rows of a megacap.

★★★ NARROW ON PURPOSE. It reads ONLY inside a guidance SECTION, never the
document body. A number lifted from narrative prose is how 201,944 became
201,900: the body rounds, and it rounds differently in every paragraph.
No heading, no rows. There is no fallback scan and there must never be.

★★ AND EVERY ROW IS STAMPED confidence='prose'. A prose figure and a table
figure must never look alike on the card. If this extractor is wrong, the
channel has to be visible at a glance -- which is also why it keeps the
whole sentence it read.
"""

import re

#: the only headings that open a guidance section
_HEADING = re.compile(
    r'(?im)^[\s•▪*#>-]*('
    r'financial guidance|business outlook|guidance|outlook'
    r'|(?:first|second|third|fourth)[\s-]quarter\s+\d{4}\s+guidance'
    r'|q[1-4]\s+\d{4}\s+(?:outlook|guidance)'
    r'|(?:first|second|third|fourth)\s+quarter\s+\d{4}\s+guidance'
    r')\s*:?\s*$')

#: a heading of equal or greater rank closes the section. Anything short,
#: title-ish and not a sentence ends it.
_CLOSER = re.compile(
    r'(?m)^[\s]*(?=[A-Z★])([^\n.;:]{4,70})\s*$')

_SCALE = {'billion': 1000.0, 'bn': 1000.0, 'million': 1.0, 'mm': 1.0,
          'thousand': 0.001}

_NUM = r'\$?\s*([\d,]+(?:\.\d+)?)\s*(billion|million|bn|mm|thousand)?'

_RANGE_PATS = (
    re.compile(r'(?i)expected to be between\s+' + _NUM + r'\s+and\s+' + _NUM),
    re.compile(r'(?i)expected to be in the range of\s+' + _NUM
               + r'\s+(?:to|and)\s+' + _NUM),
    re.compile(r'(?i)\bof\s+' + _NUM + r'\s+to\s+' + _NUM),
    re.compile(r'(?i)\bbetween\s+' + _NUM + r'\s+and\s+' + _NUM),
    # ★★ THE DASH RANGE, ANCHORED ON THE WORD 'between'. Palantir writes
    # 'Revenue of between $2.649 - $2.653 billion' -- a range whose two
    # ends are joined by a dash, not by 'and', which is why every guide
    # on that ticker read as zero rows. A BARE 'NUM - NUM' would also
    # match, and must not: CrowdStrike's guidance table flattens to
    # 'Total revenue  $1,436.0 - $1,442.0 million  $5,914.7 - $5,958.7
    # million', the quarter range and the full-year range on one line,
    # and first-match-wins would file one under the other's period.
    re.compile(r'(?i)\bbetween\s+' + _NUM + r'\s*[-–—]\s*' + _NUM),
)
_POINT_PATS = (
    re.compile(r'(?i)expected to be approximately\s+' + _NUM),
    re.compile(r'(?i)we continue to expect.{0,40}?to be approximately\s+'
               + _NUM),
    re.compile(r'(?i)\bapproximately\s+' + _NUM),
)
_GROWTH_PATS = (
    re.compile(r'(?i)to grow between\s+([\d.]+)\s*%\s+and\s+([\d.]+)\s*%'),
    re.compile(r'(?i)growth of approximately\s+([\d.]+)\s*%'),
)

#: sentence subject -> canonical metric. Deliberately small: a guidance
#: bullet names its metric plainly, and guessing beyond this list is how a
#: wrong row gets a believable number.
_SUBJECT = (
    ('net sales', 'revenue'), ('revenue', 'revenue'),
    ('operating income', 'operatingIncome'),
    # the same line under the name half the market uses for it. Palantir
    # and CrowdStrike both say 'income from operations'; neither ever
    # says 'operating income', so the highest-weighted guidance row on
    # those tickers had no subject to bind to.
    ('income from operations', 'operatingIncome'),
    ('operating margin', 'operatingMargin'),
    ('gross margin', 'grossMargin'),
    ('capital expenditure', 'capex'), ('capex', 'capex'),
    ('free cash flow', 'freeCashFlow'),
    ('earnings per share', 'eps'),
    ('adjusted ebitda', 'adjustedEbitda'),
)

_FY = re.compile(r'(?i)\b(full[\s-]year|fiscal\s+year)\b')
_BARE_YEAR = re.compile(r'\b(20\d\d)\b')
_QWORD = re.compile(r'(?i)\b(quarter|q[1-4])\b')

#: a lead-in that RE-PERIODS the bullets beneath it. Anchored on a line
#: that BEGINS with 'For' and ENDS with a colon -- heading-like, not a
#: sentence. NVIDIA's 'For the full year fiscal 2027, NVIDIA expects GAAP
#: and non-GAAP tax rates to be ...' is a SENTENCE, already periodised one
#: sentence at a time, and must not be mistaken for a lead-in and re-stamp
#: every bullet that follows it.
_LEADIN = re.compile(r'(?i)^\s*[•▪*>-]*\s*for\b[^.;]{0,70}:\s*$')


def _period_of(sentence, default):
    """FY<year> when the sentence names a year and no quarter.

    ★★★ Amazon's capex bullet reads 'We continue to expect 2026 cash
    capital expenditures to be approximately $220 billion' -- a FULL-YEAR
    figure sitting inside a block headed 'Fourth Quarter 2026 Guidance'.
    Taking the heading's period would file an annual number into a
    quarterly slot, which is non-negotiable 2 running the other way.
    """
    if _FY.search(sentence):
        m = _BARE_YEAR.search(sentence)
        return 'FY%s' % m.group(1) if m else 'FY'
    m = _BARE_YEAR.search(sentence)
    if m and not _QWORD.search(sentence):
        return 'FY%s' % m.group(1)
    return default
#: a clean name for the card. The SENTENCE is kept in sourceSentence;
#: putting it in `label` made the row unreadable next to table rows.
_DISPLAY = {'revenue': 'Revenue', 'operatingIncome': 'Operating income',
            'operatingMargin': 'Operating margin',
            'grossMargin': 'Gross margin',
            'capex': 'Capital expenditures',
            'freeCashFlow': 'Free cash flow', 'eps': 'EPS',
            'adjustedEbitda': 'Adjusted EBITDA'}

_WS = re.compile(r'\s+')


def _printed(match, parts, unit, pct=False):
    """The figure AS PRINTED, compactly: '$2.649 - $2.653 billion'.

    ★★★★ THE CARD MUST NOT SHOW THE NORMALISED NUMBER. _scale turns a
    'billion' into 1000s of millions so the channels share one unit --
    right for the pipeline, a thousand-fold error on a card whose label
    says ($B). And it must not show `raw` either: that is a whole clause
    ('expected to be between $240.0 billion and $247.0 billion'), which
    truncates mid-word at any sane column width, and a range whose unit
    word has been cut off is the same error wearing a different hat.

    ★★ SO THE DIGITS AND THE SCALE WORD ARE KEPT AS THE DOCUMENT WROTE
    THEM, reordered and nothing else. No arithmetic happens here, which
    is why it cannot be wrong about a magnitude.
    """
    dollar = '$' if '$' in match.group(0) else ''
    tail = (' %s' % unit) if unit else ''
    body = ' - '.join('%s%s%s' % (dollar, p, '%' if pct else '')
                      for p in parts if p is not None)
    return (body + ('' if pct else tail)).strip()


def _scale(num, word):
    try:
        v = float(str(num).replace(',', ''))
    except (TypeError, ValueError):
        return None
    return v * _SCALE.get((word or 'million').lower(), 1.0)


def sections(text):
    """[(heading, body)] for every guidance section. Empty if none."""
    out = []
    for m in _HEADING.finditer(text or ''):
        start = m.end()
        rest = text[start:start + 4000]
        end = len(rest)
        for c in _CLOSER.finditer(rest):
            if c.start() > 40:
                end = c.start()
                break
        out.append((_WS.sub(' ', m.group(1)).strip(), rest[:end]))
    return out


def _subject(sentence):
    low = sentence.lower()
    best, at = None, 10 ** 6
    for needle, metric in _SUBJECT:
        i = low.find(needle)
        if 0 <= i < at:
            best, at = metric, i
    return best


def subblocks(body, default):
    """[(period, text)] -- the section split at each 'For <period>:' lead-in.

    ★★★★ ONE HEADING, TWO PERIODS. Palantir files the quarter guide and
    the full-year guide under a single 'Outlook', separated only by the
    lines 'For Q4 2026, we expect:' and 'For full year 2026:'. Stamping
    the whole section with the heading's period puts ~$8.5B -- the ANNUAL
    revenue guide -- into a Q4 slot whose bogey is $2.65B. Nothing about
    that row looks wrong: the number is real, the metric is right, the
    label is right. Only the period is wrong, and a wrong number in the
    NEXT QUARTER section is worse than an empty one.
    """
    out, cur, buf = [], default, []
    for ln in body.splitlines():
        if _LEADIN.match(ln):
            if buf:
                out.append((cur, '\n'.join(buf)))
            cur, buf = _period_of(_WS.sub(' ', ln).strip(), default), []
            continue
        buf.append(ln)
    if buf:
        out.append((cur, '\n'.join(buf)))
    return out or [(default, body)]


def from_text(text, heading_period='nextQGuidance'):
    """[{metric, period, value, low, high, raw, confidence, ...}].

    ★ ZERO ROWS IS THE CORRECT ANSWER on a release whose guidance is a
    table. Returning something there would double-report what the table
    parser already has, at lower precision.
    """
    out = []
    for heading, body in sections(text):
        for block_period, block in subblocks(body, heading_period):
            for raw_sentence in re.split(r'(?<=[.;])\s+|\n', block):
                sentence = _WS.sub(' ', raw_sentence).strip(' •▪*-')
                if len(sentence) < 20:
                    continue
                metric = _subject(sentence)
                if not metric:
                    continue
                # the SENTENCE still wins over its block: Amazon's capex
                # bullet names its own full year inside a quarter block.
                period = _period_of(sentence, block_period)
                row = None
                for pat in _RANGE_PATS:
                    m = pat.search(sentence)
                    if m:
                        lo = _scale(m.group(1), m.group(2) or m.group(4))
                        hi = _scale(m.group(3), m.group(4) or m.group(2))
                        if lo is not None and hi is not None:
                            row = {'value': None, 'low': lo, 'high': hi,
                                   'raw': _WS.sub(' ', m.group(0)).strip(),
                                   'printed': _printed(
                                       m, (m.group(1), m.group(3)),
                                       m.group(4) or m.group(2))}
                        break
                if row is None:
                    for pat in _GROWTH_PATS:
                        m = pat.search(sentence)
                        if m:
                            g = m.groups()
                            row = ({'value': float(g[0]), 'low': None,
                                    'high': None, 'raw': m.group(0),
                                    'printed': _printed(m, (g[0],), None,
                                                        pct=True)}
                                   if len(g) == 1 else
                                   {'value': None, 'low': float(g[0]),
                                    'high': float(g[1]), 'raw': m.group(0),
                                    'printed': _printed(m, (g[0], g[1]),
                                                        None, pct=True)})
                            break
                if row is None:
                    for pat in _POINT_PATS:
                        m = pat.search(sentence)
                        if m:
                            v = _scale(m.group(1), m.group(2))
                            if v is not None:
                                row = {'value': v, 'low': None, 'high': None,
                                       'raw': _WS.sub(' ',
                                                      m.group(0)).strip(),
                                       'printed': _printed(
                                           m, (m.group(1),), m.group(2))}
                            break
                if row is None:
                    continue
                row.update({'metric': metric, 'period': period,
                            'table': heading,
                            'label': _DISPLAY.get(metric, metric),
                            'confidence': 'prose',
                            'sourceSentence': sentence})
                out.append(row)
    return out


def conflicts(prose_rows, table_rows_by_key):
    """RULE: a prose and a table figure that disagree are BOTH shown.

    ★★ NEVER PICK. The two channels disagreeing is information about the
    document, and resolving it silently throws that information away.
    """
    out = []
    for p in prose_rows or []:
        key = (p.get('metric'), p.get('period'))
        t = (table_rows_by_key or {}).get(key)
        if t is None:
            continue
        pv = p.get('value') if p.get('value') is not None else p.get('low')
        tv = t.get('value')
        if pv is None or tv is None:
            continue
        if abs(pv - tv) > max(0.01, abs(tv) * 0.005):
            out.append({'metric': p['metric'], 'period': p['period'],
                        'prose': p, 'table': t, 'channelConflict': True})
    return out
