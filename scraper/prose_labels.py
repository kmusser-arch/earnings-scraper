# -*- coding: utf-8 -*-
r"""A FIGURE ATTACHED TO A LABEL THE PROFILE NAMED. Nothing inferred.

★★★★ THIS IS NOT A VOCABULARY AND MUST NEVER BECOME ONE. prose_guidance
carries a small universal subject list because a guidance bullet names
its metric plainly. The figures here are SEGMENT figures -- 'U.S.
commercial revenue', 'U.S. commercial TCV' -- and the one thing that
must never happen to a segment is being answered with the consolidated
line. So nothing here guesses what a hero is about: the profile states
the exact phrase to look for, this finds the sentence containing that
phrase, and takes the figure of the class the hero declared.

A phrase the profile did not write is not searched for. A sentence that
does not contain it is not read. There is no fallback scan.

★★★ WHY THE CLASS DECIDES WHICH NUMBER. Palantir's bullet reads 'U.S.
commercial revenue grew 148% year-over-year and 29% quarter-over-quarter
to $984 million' -- three figures, two of them percentages, in one
sentence. A hero declaring (%) wants the 148 and a hero declaring ($M)
wants the 984, and nothing but the declared unit can tell them apart.

★★ AND AMONG PERCENTAGES, THE ONE THE DOCUMENT CALLS YEAR-OVER-YEAR.
Taking the first percentage in that sentence gives 148 by luck of word
order; in 'up 11% year-over-year' after a quarter-over-quarter clause it
would give the wrong one. The percentage that belongs to a y/y hero is
the one the sentence marks as y/y.
"""

import re

_WS = re.compile(r'\s+')

#: ★ A DECIMAL POINT IS NOT A FULL STOP, AND NEITHER IS THE DOT IN
#: 'U.S.'. Splitting on a bare '.' cut 'U.S. commercial revenue' into a
#: fragment that no longer contains the phrase the profile asked for --
#: the qualifier gone before anything could match on it, which is how a
#: segment number reaches a company row.
_SENT = re.compile(r'(?<!\d)(?<![A-Z])\.(?=\s|$)')

_SCALE = {'billion': 1000.0, 'bn': 1000.0, 'million': 1.0, 'mm': 1.0,
          'thousand': 0.001, 'k': 0.001, 'b': 1000.0, 'm': 1.0}

#: a currency figure, with the scale word the document used
_MONEY = re.compile(r'(?i)\$\s*([\d,]+(?:\.\d+)?)\s*'
                    r'(billion|million|thousand|bn|mm)?')
#: ★ 'PERCENT' SPELLED OUT IS STILL A PERCENT. Apple writes 'Company
#: gross margin was 47.9 percent' and never prints the sign, so a
#: matcher anchored on '%' finds the figure the release states most
#: plainly nowhere at all. 'percentage point' is excluded: in the same
#: sentence -- 'a favorable impact of approximately 1 percentage point
#: from tariff refunds' -- it is a DELTA, not the margin.
_PCT = re.compile(r'(?i)([\d,]+(?:\.\d+)?)\s*(?:%|percent\b(?!age))')

#: the marker that a percentage is the year-over-year one
_YOY = re.compile(r'(?i)\b(year[\s-]over[\s-]year|y/y|yoy|'
                  r'compared to .{0,30}(?:prior|last) year)\b')

#: ★ A FLOOR IS NOT A RANGE AND NOT A POINT. 'in excess of $3.559
#: billion' states a lower bound and no upper one. Reporting it as a
#: point value claims a precision the issuer withheld; reporting it as a
#: range invents a high end. It is carried as low-with-no-high and
#: printed with the '>' the document means.
_FLOOR = re.compile(r'(?i)\b(in excess of|at least|no less than|'
                    r'greater than|more than)\s*$')


def sentences(text):
    """The document's prose, one BULLET or sentence per entry.

    ★★★★ THE LINE BREAK IS THE DOCUMENT'S OWN PUNCTUATION AND THROWING
    IT AWAY IS HOW THIS GOES WRONG. The first cut flattened the release
    to a single string and split on periods. Palantir's highlights
    bullets carry no terminating period, so the entire block came back
    as ONE sentence -- and 'the $ figure nearest the phrase' inside that
    blob answered 'U.S. commercial revenue' with $1.937 billion.

    THAT IS 1937.0. The identical wrong number as the founding defect,
    reached by a different route, in a reader written to prevent it.
    One bullet per line, then sentences within a line.
    """
    out = []
    for line in (text or '').splitlines():
        line = _WS.sub(' ', line).strip(' •▪◦*-')
        if not line:
            continue
        at = 0
        for m in _SENT.finditer(line):
            s = line[at:m.start() + 1].strip()
            if s:
                out.append(s)
            at = m.end()
        tail = line[at:].strip()
        if tail:
            out.append(tail)
    return out


def _scale(num, word):
    try:
        v = float(str(num).replace(',', ''))
    except (TypeError, ValueError):
        return None
    return v * _SCALE.get((word or 'million').lower(), 1.0)


def _money(sentence, phrase_at):
    """The currency figure in this sentence, nearest the phrase."""
    best = None
    for m in _MONEY.finditer(sentence):
        d = abs(m.start() - phrase_at)
        if best is None or d < best[0]:
            best = (d, m)
    if best is None:
        return None
    m = best[1]
    floor = bool(_FLOOR.search(sentence[:m.start()]))
    v = _scale(m.group(1), m.group(2))
    if v is None:
        return None
    unit = m.group(2) or ''
    printed = '%s$%s%s' % ('>' if floor else '', m.group(1),
                           (' %s' % unit) if unit else '')
    return {'value': None if floor else v,
            'low': v if floor else None,
            'floor': floor, 'printed': printed, 'class': 'CURRENCY'}


def _percent(sentence, phrase_at, yoy_only):
    """The percentage in this sentence; the y/y one when asked for.

    ★★ AFTER THE PHRASE, NOT MERELY IN THE SAME SENTENCE. The CEO quote
    runs 'overall revenue soared 96% year-over-year, U.S. commercial
    revenue grew 148% year-over-year' -- two y/y percentages, and the
    first belongs to the line the hero is NOT asking about.
    """
    hits = [m for m in _PCT.finditer(sentence) if m.start() >= phrase_at]
    if not hits:
        return None
    pick = hits[0]
    if yoy_only:
        marked = None
        for m in hits:
            after = sentence[m.end():m.end() + 40]
            if _YOY.match(after.lstrip(' ,')) or _YOY.search(after[:26]):
                marked = m
                break
        if marked is None:
            # ★ THE SENTENCE DOES NOT SAY WHICH ONE IS YEAR-OVER-YEAR, SO
            # NEITHER DO WE. Picking the first would be right on one
            # issuer's word order and wrong on the next.
            return None
        pick = marked
    try:
        v = float(pick.group(1).replace(',', ''))
    except ValueError:
        return None
    return {'value': v, 'low': None, 'floor': False,
            'printed': '%s%%' % pick.group(1), 'class': 'PERCENT'}


def find(text, phrases, want_class, yoy=False):
    """{value, low, printed, sentence, phrase} or None.

    `phrases` is what the PROFILE declared. `want_class` is CURRENCY or
    PERCENT, from the hero's declared unit. Nothing else is consulted.
    """
    if not phrases or not want_class:
        return None
    # ★★★★ PROFILE ORDER IS PRIORITY ORDER, NOT DOCUMENT ORDER. The TCV
    # entry lists ['U.S. commercial TCV', 'total contract value'] -- the
    # segment first and the consolidated line as a fallback -- and the
    # release prints them the other way round: 'Closed total contract
    # value ("TCV") of $2.918 billion' comes one bullet BEFORE 'Closed
    # $1.463 billion of U.S. commercial TCV'. Walking the document and
    # taking whichever phrase turned up first answered the segment hero
    # with the consolidated figure, which is the single thing this
    # module exists to prevent. Phrases are tried in the order the
    # profile wrote them; the document's order decides nothing.
    lines = sentences(text)
    for phrase in [(p or '').lower().strip() for p in phrases if p]:
        for sentence in lines:
            at = sentence.lower().find(phrase)
            if at < 0:
                continue
            got = (_money(sentence, at) if want_class == 'CURRENCY'
                   else _percent(sentence, at, yoy))
            if got is None:
                continue
            got.update({'sentence': sentence, 'phrase': phrase,
                        'confidence': 'prose'})
            return got
    return None
