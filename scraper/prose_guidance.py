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
_WS = re.compile(r'\s+')


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


def from_text(text, heading_period='nextQGuidance'):
    """[{metric, period, value, low, high, raw, confidence, ...}].

    ★ ZERO ROWS IS THE CORRECT ANSWER on a release whose guidance is a
    table. Returning something there would double-report what the table
    parser already has, at lower precision.
    """
    out = []
    for heading, body in sections(text):
        for raw_sentence in re.split(r'(?<=[.;])\s+|\n', body):
            sentence = _WS.sub(' ', raw_sentence).strip(' •▪*-')
            if len(sentence) < 20:
                continue
            metric = _subject(sentence)
            if not metric:
                continue
            period = _period_of(sentence, heading_period)
            row = None
            for pat in _RANGE_PATS:
                m = pat.search(sentence)
                if m:
                    lo = _scale(m.group(1), m.group(2) or m.group(4))
                    hi = _scale(m.group(3), m.group(4) or m.group(2))
                    if lo is not None and hi is not None:
                        row = {'value': None, 'low': lo, 'high': hi,
                               'raw': _WS.sub(' ', m.group(0)).strip()}
                    break
            if row is None:
                for pat in _GROWTH_PATS:
                    m = pat.search(sentence)
                    if m:
                        g = m.groups()
                        row = ({'value': float(g[0]), 'low': None,
                                'high': None, 'raw': m.group(0)}
                               if len(g) == 1 else
                               {'value': None, 'low': float(g[0]),
                                'high': float(g[1]), 'raw': m.group(0)})
                        break
            if row is None:
                for pat in _POINT_PATS:
                    m = pat.search(sentence)
                    if m:
                        v = _scale(m.group(1), m.group(2))
                        if v is not None:
                            row = {'value': v, 'low': None, 'high': None,
                                   'raw': _WS.sub(' ', m.group(0)).strip()}
                        break
            if row is None:
                continue
            row.update({'metric': metric, 'period': period,
                        'table': heading, 'label': sentence[:70],
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
