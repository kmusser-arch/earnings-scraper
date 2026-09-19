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
