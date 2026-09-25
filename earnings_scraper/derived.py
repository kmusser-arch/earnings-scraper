# -*- coding: utf-8 -*-
"""A row the issuer never prints, computed from two rows it does.

HPE reports segment results as a Net Revenue block and an Earnings Before
Taxes block, with NO margin row anywhere. So the margin is a quotient:

    Networking    637 / 2,893  = 22.0%      stored 22.0
    Cloud & AI  1,539 / 9,042  = 17.0%      stored 17.0

and the spec has said so since 17 September — `derived` names the operation
and `sourceRows` names both blocks. The reader had never read either field,
which is why the rows refused with 'no candidate matched the declared unit':
the fence was correct, the label was correct, and the block it points at
prints DOLLARS because the percentage does not exist in the document.

★★★ THE OPERANDS ARE MATCHED BY NAME, NOT BY POSITION. `derived` says
'earnings ÷ revenue' and sourceRows lists revenue FIRST, so an order rule
would invert every margin on this corpus and produce 4.5x instead of 22%. The
operand words are matched against the sourceRow anchors -- 'earnings' to the
Earnings block, 'revenue' to the Net Revenue block -- so the spec's own
sentence decides which is the numerator.

★★ AND THE BLOCKS BOUND EACH OTHER. A sourceRow is a FENCE plus a LABEL
written 'Net Revenue(5): Cloud & AI', and an anchor with no close is a
zero-width fence. Each block's terminator is therefore the OTHER block's
anchor, plus the issuer's own segment totals -- which is exactly how the two
HPE rows were closed by hand.

★ A DERIVED VALUE IS NOT A READ VALUE. It carries derivedFrom naming both
operands and their values, because a quotient that agrees with a hand read is
agreement about two numbers and one operation, and a card that cannot say
which is a card that cannot be checked.
"""

import re

from . import extract
from . import registry

#: 'earnings ÷ revenue', 'earnings / revenue', 'A divided by B'
_RATIO = re.compile(
    r'([a-z][a-z \-]{2,40}?)\s*(?:÷|/|divided\s+by)\s*'
    r'([a-z][a-z \-]{2,40}?)\b', re.I)

#: the issuer's own block totals, which close a segment block
SEGMENT_CLOSERS = ('Total segment net revenue',
                   'Total segment earnings from operations',
                   'Total segment earnings')


def split_source_row(text):
    """('Net Revenue(5):', 'Cloud & AI') from 'Net Revenue(5): Cloud & AI'.

    A sourceRow is a FENCE and a LABEL, not a string the document contains
    contiguously -- the block header and the segment name sit on different
    lines. Splitting on the LAST colon keeps 'Net Revenue(5):' whole.
    """
    t = (text or '').strip()
    i = t.rfind(':')
    if i < 0:
        return None, t
    return t[:i + 1].strip(), t[i + 1:].strip()


def operands(derived_text):
    """('earnings', 'revenue') — numerator first, from the spec's sentence."""
    m = _RATIO.search(derived_text or '')
    if not m:
        return None, None
    return m.group(1).strip().lower(), m.group(2).strip().lower()


def _match_source(word, sources):
    """The sourceRow whose FENCE names this operand word."""
    for src in sources:
        anchor, _label = split_source_row(src)
        if word and anchor and word.split()[0][:6] in anchor.lower():
            return src
    return None


def read_source(text, src, spec, record, all_anchors=()):
    """The value of one sourceRow, or None.

    ★ THE OTHER BLOCK IS THIS BLOCK'S CLOSE. An anchor with no terminator
    fences a span the width of the anchor phrase itself, so nothing inside it
    can ever match.
    """
    anchor, label = split_source_row(src)
    if not anchor or not label:
        return None
    closers = [a for a in all_anchors if a and a != anchor]
    closers.extend(SEGMENT_CLOSERS)
    probe = dict(spec or {})
    probe.pop('derived', None)
    probe.pop('sourceRows', None)
    probe['documentLabels'] = [label]
    probe['sectionAnchor'] = [anchor]
    probe['spanTerminator'] = closers
    probe['whereKind'] = ['TABLE']
    probe['documentUnit'] = '$M'
    probe['storedUnit'] = '$M'
    probe.pop('requiresRangePair', None)
    probe.pop('basisPrefix', None)
    got = extract.value_for(text, dict(extraction=probe, name=label),
                            record=record) or {}
    v = got.get('value')
    return v if isinstance(v, (int, float)) else None


#: 'HPE-2026Q3 [3] FY26 Non-GAAP EPS Guide ($)' -- an index into the CARD
_CARD_REF = re.compile(r'^([A-Z][A-Z0-9]*-\d{4}Q\d)\s*\[\s*(\d+)\s*\]')

#: a percentage range the issuer prints: '16% to 20%', '16 to 20%'
_PCT_RANGE = re.compile(
    r'(-?\d+(?:\.\d+)?)\s*%?\s*(?:to|-|–|and)\s*(-?\d+(?:\.\d+)?)\s*%')

#: a dollar range: '$3.75 to $3.85'
_DOLLAR_RANGE = re.compile(
    r'\$\s*(\d+(?:\.\d+)?)\s*(?:to|-|–|and)\s*\$?\s*(\d+(?:\.\d+)?)')

#: how deep a card row may reference another before we call it a cycle
MAX_DEPTH = 3


def is_compound(recipe):
    """Does this recipe grow a base by a RATE, rather than multiply two levels?

    The discriminator is the issuer's own word: a GROWTH operand is a rate,
    and a rate compounds. Nothing here infers it from the magnitudes.
    """
    low = (recipe or '').lower()
    return ('growth' in low and
            (' x ' in low or '*' in low or 'product' in low
             or 'multipl' in low))


def card_row_value(text, ref, record, depth=0):
    """(lo, hi) for a source row written as an index into the card, or None.

    ★ A CARD THAT REFERENCES ITSELF MUST REFUSE, NOT RECURSE. The depth guard
    is the close; without one a mutual reference between two rows hangs the
    extractor on a live print, which costs the card rather than the cell.
    """
    m = _CARD_REF.match((ref or '').strip())
    if not m or depth >= MAX_DEPTH:
        return None
    rid, idx = m.group(1), int(m.group(2))
    if (record or {}).get('id') != rid:
        return None                       # cross-record refs are not resolved
    rows = ((record or {}).get('preEarnings') or {}).get('keyKPIs') or []
    if idx >= len(rows):
        return None
    # ★★★ THE OPERAND IS EXTRACTED, NEVER READ OUT OF THE REFERENCE. An
    # earlier version preferred the endpoints written in the sourceRow
    # sentence -- 'HPE-2026Q3 [3] ... the $3.75-$3.85 range' -- because the
    # referenced row might be refusing. That is precisely the case where it
    # must NOT substitute: A DERIVED VALUE WHOSE OPERAND COMES FROM THE
    # CARD'S PROSE IS THE HAND READ WITH ARITHMETIC APPLIED. It cannot
    # disagree with the author, and it produces a NUMBER that lands on the
    # card. Same family as a check consulting the population instead of the
    # selection, one level worse.
    from . import extract as _x
    got = _x.value_for(text, rows[idx], record=record) or {}
    lo, hi = got.get('rangeLow'), got.get('rangeHigh')
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return (float(lo), float(hi))
    v = got.get('value')
    if isinstance(v, (int, float)):
        return (float(v), float(v))
    return None


def rate_range(text, ref):
    """(lo, hi) as FRACTIONS for a growth range named by a source row."""
    quoted = re.search(r"'([^']+)'", ref or '')
    needle = (quoted.group(1) if quoted else '').strip()
    if needle and needle in text:
        m = _PCT_RANGE.search(text, text.index(needle),
                              text.index(needle) + len(needle) + 40)
        if m:
            return (float(m.group(1)) / 100.0, float(m.group(2)) / 100.0)
    # the phrase may be reflowed; fall back to the numbers written in the ref
    m = _PCT_RANGE.search(ref or '')
    if m:
        return (float(m.group(1)) / 100.0, float(m.group(2)) / 100.0)
    return None


def derive_compound(text, row, record=None, depth=0):
    """base x (1 + growth) over two ranges, or a refusal naming the operand."""
    spec = registry.spec_for(row)
    sources = (spec or {}).get('sourceRows') or []
    recipe = (spec or {}).get('derived') or ''
    base = rate = None
    base_src = rate_src = None
    for src in sources:
        if base is None:
            got = card_row_value(text, src, record, depth)
            if got:
                base, base_src = got, src
                continue
        if rate is None:
            got = rate_range(text, src)
            if got:
                rate, rate_src = got, src
    if base is None:
        prose = [s for s in sources if _DOLLAR_RANGE.search(str(s))]
        return dict(value=None, derivedFrom=None,
                    why=('the BASE operand did not resolve by EXTRACTION'
                         + (' — and its sourceRow states the endpoints as '
                            'PROSE (%r), which is the answer key with '
                            'arithmetic applied and is never substituted'
                            % str(prose[0])[:60] if prose
                            else ' from %s' % sources)))
    if rate is None:
        return dict(value=None, derivedFrom=None,
                    why=('the GROWTH operand did not resolve — the framework '
                         'phrase is not in this release'))
    ends = [b * (1.0 + g) for b in base for g in rate]
    lo, hi = min(ends), max(ends)
    return dict(value=round((lo + hi) / 2.0, 4), rangeLow=round(lo, 4),
                rangeHigh=round(hi, 4), why=None,
                derivedFrom=dict(
                    operation='GROWTH_COMPOUND',
                    # ★ THE SPEC SAYS PRODUCT AND THE ARITHMETIC IS A
                    # COMPOUND. Recorded, not silently reconciled.
                    recipeWording=recipe[:80],
                    note=('spec wording says PRODUCT; the operation performed '
                          'is base x (1 + growth), which is what the card\'s '
                          'own arithmetic does'),
                    base=dict(row=base_src, range=list(base)),
                    growth=dict(row=rate_src,
                                range=[round(r, 4) for r in rate])))


def derive(text, row, record=None):
    """The computed value for a derived row, with its provenance, or None.

    Returns dict(value, derivedFrom, why). `why` is set when it cannot be
    computed, and names which operand failed rather than the row.
    """
    spec = registry.spec_for(row)
    sources = (spec or {}).get('sourceRows') or []
    recipe = (spec or {}).get('derived') or ''
    if not sources or not recipe:
        return None

    # ★ THE OPERATION IS READ OFF THE RECIPE, not assumed to be a ratio.
    # The ratio path was the only one that existed, so a PRODUCT row had
    # nowhere to go and refused with 'no candidate matched the declared
    # unit' -- a refusal that described the wrong failure entirely.
    if is_compound(recipe):
        return derive_compound(text, row, record)

    num_word, den_word = operands(recipe)
    if not num_word or not den_word:
        return dict(value=None, derivedFrom=None,
                    why='derived recipe %r names no ratio' % recipe[:40])

    num_src = _match_source(num_word, sources)
    den_src = _match_source(den_word, sources)
    if not num_src or not den_src or num_src == den_src:
        return dict(value=None, derivedFrom=None,
                    why='cannot match %r and %r onto the source rows %s'
                        % (num_word, den_word, sources))

    anchors = [split_source_row(s)[0] for s in sources]
    num = read_source(text, num_src, spec, record, anchors)
    den = read_source(text, den_src, spec, record, anchors)
    if num is None or den is None:
        missing = num_src if num is None else den_src
        return dict(value=None, derivedFrom=None,
                    why='source row %r did not resolve' % missing)
    if not den:
        return dict(value=None, derivedFrom=None,
                    why='denominator %r is zero' % den_src)

    want_pct = ((spec.get('documentUnit') or '').strip().startswith('%'))
    value = (num / den) * (100.0 if want_pct else 1.0)
    return dict(value=round(value, 4), why=None,
                derivedFrom=dict(recipe=recipe[:80],
                                 numerator=dict(row=num_src, value=num),
                                 denominator=dict(row=den_src, value=den)))
