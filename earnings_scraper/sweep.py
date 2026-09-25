# -*- coding: utf-8 -*-
"""ONE SWEEP, ONE WRITER — and FALSE_MATCH is a verdict, not an afterthought.

Three numbers described this corpus and none of them described the artifact:

    answerkey headline   76 rows minus a DYNAMIC exclusion   30 /  1 / 29
    fixed-population      all 78 rows carrying the column    34 /  1 / 37
    library column        the same 78, FROZEN by hand        25 /  6 / 42

The column the dashboard renders was written by a script nobody's gate ran.
So the extractor emits the column here, the dashboard renders what was
emitted, and the sweep counts the rows the dashboard shows. One writer.

★★★ AND DIGITS AGREEING IS NOT THE SAME AS BEING RIGHT. Nine rows moved into
MATCH between the snapshot and the live run, and a MISMATCH becomes a MATCH
two ways: the extractor found the right cell, or it found a DIFFERENT WRONG
CELL whose digits agree. Nothing distinguished those, so every tuning
decision was scored by a gradient that rewards coincidence exactly as much as
correctness. FALSE_MATCH exists from this module's first run because bolting
it on afterwards means re-running that loop against the same blind metric.

    MATCH        digits agree AND the position passes fence, basis, period
    FALSE_MATCH  digits agree AND the position FAILS one of the three
    MISMATCH     digits disagree
    LOST         no value and no stated reason
    REFUSED      value withheld WITH a reason
    EXCLUDED     NOT_IN_PR or call-sourced — out of the denominator

Every report carries the denominator. A count without one is what let a
headline quote three of six buckets for a week.
"""

import io
import json
import os

from . import extract
from . import parallel
from . import period as period_mod
from . import registry

VERDICTS = ('MATCH', 'FALSE_MATCH', 'MISMATCH', 'LOST', 'REFUSED', 'EXCLUDED')


def _fence_ok(text, pos, spec):
    """Is the value inside the section the row declared?

    A row that names its section and takes a figure from outside it has the
    right digits from the wrong place -- the definition of a false green.
    """
    anchors = spec.get('sectionAnchor')
    if not anchors or not isinstance(pos, int):
        return True, None
    spans = extract.section_spans(text, anchors, spec.get('spanTerminator'),
                                  spec.get('spanStartAfter'))
    if not spans:
        return True, None
    if any(lo <= pos <= hi for lo, hi in spans):
        return True, None
    return False, 'outside its declared section'


def _basis_ok(text, pos, spec):
    """Does the clause at the value contradict the declared basis?

    Only a CONTRADICTION fails. Silence is not a failure: most tables carry
    no basis word at all, and treating that as a failure would mark the
    majority false.
    """
    want = (spec or {}).get('basis')
    if not want or not isinstance(pos, int):
        return True, None
    frag = extract._governing_sentence(text, pos)
    low = (frag or '').lower()
    has_non = 'non-gaap' in low or 'non gaap' in low
    has_gaap = 'gaap' in low
    if want.lower().startswith('non'):
        if has_gaap and not has_non:
            return False, 'clause says GAAP, row declares non-GAAP'
    elif want.upper() == 'GAAP':
        if has_non:
            return False, 'clause says non-GAAP, row declares GAAP'
    return True, None


def _period_ok(text, pos, spec, quarter=None):
    """Does the clause at the value contradict the declared period?

    EXPLICIT evidence only, matching the filter: a class the issuer's own
    words support can contradict; one inferred from position cannot.
    """
    want = (spec or {}).get('period')
    if not want or not isinstance(pos, int):
        return True, None
    want = {'FY_GUIDE': period_mod.GUIDE_FY}.get(want, want)
    frag = extract._governing_sentence(text, pos)
    if not frag:
        return True, None
    klass = period_mod.classify_candidate(frag, quarter)
    if klass in (period_mod.UNRESOLVED, want):
        return True, None
    basis, phrase = extract.period_basis(frag)
    if basis != 'EXPLICIT':
        return True, None
    return False, 'clause is %s (%r), row declares %s' % (klass, phrase, want)


def provenance(text, pos, spec, quarter=None):
    """(ok, [failures]) — does the POSITION support this being the row's value?"""
    fails = []
    for check in (_fence_ok(text, pos, spec),
                  _basis_ok(text, pos, spec),
                  _period_ok(text, pos, spec, quarter)):
        ok, why = check
        if not ok:
            fails.append(why)
    return (not fails), fails


def judge(text, pre_row, slot, spec, quarter=None, got=None):
    """The verdict for one row, with its provenance reasons."""
    stored = (slot or {}).get('actual')
    if registry.status_of(spec) != 'EXTRACTABLE':
        return dict(verdict='EXCLUDED', reason='specState %s'
                    % registry.status_of(spec), value=None, pos=None)
    got = got if got is not None else (
        extract.value_for(text, pre_row, record={'fiscalQuarter': quarter})
        or {})
    value = parallel.in_stored_unit(got, spec)
    pos = got.get('pos')
    why = got.get('why') or ''

    if value is None:
        if why:
            return dict(verdict='REFUSED', reason=why[:160], value=None,
                        pos=pos)
        return dict(verdict='LOST', reason='no value and no stated reason',
                    value=None, pos=pos)

    if not isinstance(stored, (int, float)):
        return dict(verdict='EXCLUDED', reason='no hand read to compare',
                    value=value, pos=pos)

    if not parallel.agrees(stored, value):
        return dict(verdict='MISMATCH', reason='digits disagree',
                    value=value, pos=pos)

    ok, fails = provenance(text, pos, spec, quarter)
    if ok:
        return dict(verdict='MATCH', reason=None, value=value, pos=pos)
    # ★ THE DIGITS AGREE AND THE POSITION DOES NOT SUPPORT THEM.
    return dict(verdict='FALSE_MATCH', reason='; '.join(fails), value=value,
                pos=pos)


def report(counts, population):
    """A line that cannot be quoted without its denominator."""
    total = sum(counts.get(v, 0) for v in VERDICTS)
    parts = ' · '.join('%s %d' % (v, counts.get(v, 0)) for v in VERDICTS)
    return '%s   [denominator %d of %d rows: %s]' % (parts, total, population,
                                                     'all verdicts shown')
