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

★★★ AND THE BASIS CHECK HAS NEVER ONCE READ A COLUMN HEADER.

    "a cell is surrounded by digits, the words are in the header, and
    _governing_sentence cannot reach a column header from any position, at
    any offset, ever."

That is a proof, not an observation, and it is recorded here verbatim
because it indicts the three functions directly below it. The audit reported
basis evidence on 1 of 34 MATCH rows; that one row was HPE[16], whose `pos`
sat on the LABEL LINE 'Non-GAAP gross profit margin', so the check was
reading a LABEL and reporting it as provenance. Point `pos` at the cell and
it goes to 0. IT WAS ALWAYS 0. Every GAAP/non-GAAP selection in this corpus
is unverified and has been for the life of the project -- with the CBRS
failure mode (GAAP -7.0% while 'core' beat +9.9%, and the tape traded GAAP)
completely unguarded.

★★ A MEASUREMENT CHANGE THAT IMPROVES ACCURACY SHOULD BE EXPECTED TO LOWER
THE SCORE. IF PRECISION MAKES A NUMBER GO UP, SUSPECT IT. basis 1 -> 0 and
all-vacuous 7 -> 8 is the first number in this build to fall for a good
reason.
"""

import io
import json
import os

from . import extract
from . import parallel
from . import period as period_mod
from . import registry

VERDICTS = ('MATCH', 'FALSE_MATCH', 'MISMATCH', 'LOST', 'REFUSED', 'EXCLUDED')


EVIDENCE, ABSENT, VACUOUS, NA = 'EVIDENCE', 'ABSENT', 'VACUOUS', 'NA'


def _same_basis(a, b):
    na = (a or '').lower().replace(' ', '').replace('-', '')
    nb = (b or '').lower().replace(' ', '').replace('-', '')
    return na == nb


def _fence_ok(text, pos, spec):
    """Is the value inside the section the row declared?

    A row that names its section and takes a figure from outside it has the
    right digits from the wrong place -- the definition of a false green.
    """
    anchors = spec.get('sectionAnchor')
    if not anchors:
        return True, None, NA
    if not isinstance(pos, int):
        return True, None, VACUOUS
    spans = extract.section_spans(text, anchors, spec.get('spanTerminator'),
                                  spec.get('spanStartAfter'))
    if not spans:
        # THE ANCHOR IS DECLARED AND THE DOCUMENT HAS NO SUCH SECTION. That
        # is a fact about the release, not an excuse to pass.
        return True, 'declared section not found in this document', ABSENT
    if any(lo <= pos <= hi for lo, hi in spans):
        return True, None, EVIDENCE
    return False, 'outside its declared section', EVIDENCE


def _basis_ok(text, pos, spec, axes=None):
    """Does the basis of the SELECTED CELL match what the row declares?

    ★ STRUCTURE FIRST. In a table the basis is in the column header, and
    _governing_sentence cannot reach a column header from any position, at
    any offset, ever. cellAxes carries what the grid resolved for the cell
    it chose -- the header group, not the list of groups that exist.
    """
    want = (spec or {}).get('basis')
    if not want:
        return True, None, NA
    if axes is not None:
        got = axes.get('basis')
        if got:
            if _same_basis(got, want):
                return True, None, EVIDENCE
            return (False, 'the COLUMN is %s, the row declares %s'
                    % (got, want), EVIDENCE)
        # ★ TWO EMPTIES, NOT ONE. basis=None meant both 'the grid read this
        # cell's headers and the issuer named no basis' and 'no reader ever
        # looked'. The first is a fact about the RELEASE and the strict arm
        # refuses on it; the second is a fact about US and refusing on it
        # would publish a refusal with false provenance.
        if (axes.get('basisState') or 'UNREAD_BY_GRID') == 'UNREAD_BY_GRID':
            return True, 'no reader looked for a basis on this cell', VACUOUS
        return True, 'the column carries no basis word', ABSENT
    if not isinstance(pos, int):
        return True, None, VACUOUS
    frag = extract._governing_sentence(text, pos)
    low = (frag or '').lower()
    has_non = 'non-gaap' in low or 'non gaap' in low
    has_gaap = 'gaap' in low
    if not (has_gaap or has_non):
        return True, None, VACUOUS
    if has_gaap and has_non:
        # BOTH WORDS IN ONE CLAUSE SEPARATE NOTHING. A table block names
        # every basis it prints; that is not evidence about one cell.
        return True, None, VACUOUS
    if want.lower().startswith('non'):
        if has_gaap and not has_non:
            return False, 'clause says GAAP, row declares non-GAAP', EVIDENCE
        return True, None, EVIDENCE
    if want.upper() == 'GAAP':
        if has_non:
            return False, 'clause says non-GAAP, row declares GAAP', EVIDENCE
        return True, None, EVIDENCE
    return True, None, VACUOUS


#: a vertical column class that is NOT the reporting period
_NOT_REPORTED = ('SEQUENTIAL', 'PRIOR_YEAR_Q', 'YTD', 'PRIOR_YEAR_YTD')


def _period_ok(text, pos, spec, quarter=None, axes=None, record=None):
    """Does the period of the SELECTED CELL contradict what the row declares?

    Three sources, in order of how much they can prove:

    1. A VERTICAL COLUMN CLASS. vtables classified every column and the
       selector picked one; REPORTED vs SEQUENTIAL / PRIOR_YEAR_Q / YTD is a
       direct answer, and HPE sits the sequential quarter BETWEEN current
       and year-ago at 0.87x, so it is the answer that matters most.

    2. A HORIZONTAL HEADER PERIOD, as (year, quarter). ★ AGREEMENT ONLY.
       ORCL's Q1 FY27 release heads its columns 2026 and 2025 -- CALENDAR
       years against a fiscalYear of 2027 -- so a DISAGREEMENT here cannot
       be told apart from the fiscal/calendar offset. Agreement is evidence;
       disagreement is INCONCLUSIVE and must never fail a row.

    3. The text clause, EXPLICIT evidence only, as before.
    """
    want = (spec or {}).get('period')
    if not want:
        return True, None, NA
    want = {'FY_GUIDE': period_mod.GUIDE_FY}.get(want, want)

    if axes is not None:
        got = axes.get('period')
        if isinstance(got, str) and got:
            if want == period_mod.REPORTED:
                if got == 'REPORTED':
                    return True, None, EVIDENCE
                if got in _NOT_REPORTED:
                    return (False, 'the COLUMN is %s, the row declares '
                            'REPORTED' % got, EVIDENCE)
            # a guide row's column class says nothing about guidance
            return True, None, VACUOUS
        if isinstance(got, (tuple, list)) and len(got) == 2:
            ry = (record or {}).get('fiscalYear')
            rq = (record or {}).get('fiscalQuarter') or quarter
            if want == period_mod.REPORTED and got[0] == ry and (
                    not got[1] or got[1] == rq):
                return True, None, EVIDENCE
            # ★ CANNOT TELL A CALENDAR-LABELLED COLUMN FROM A WRONG ONE.
            return True, None, VACUOUS

    if not isinstance(pos, int):
        return True, None, VACUOUS
    frag = extract._governing_sentence(text, pos)
    if not frag:
        return True, None, VACUOUS
    klass = period_mod.classify_candidate(frag, quarter)
    if klass == period_mod.UNRESOLVED:
        return True, None, VACUOUS
    basis, phrase = extract.period_basis(frag)
    if basis != 'EXPLICIT':
        return True, None, VACUOUS
    if klass == want:
        return True, None, EVIDENCE
    return (False, 'clause is %s (%r), row declares %s'
            % (klass, phrase, want), EVIDENCE)


def provenance(text, pos, spec, quarter=None, axes=None, record=None):
    """(ok, [failures], {check: state}) for one row's position.

    The state matters as much as the verdict: a check that PASSED because it
    read nothing is not a check that passed, and reporting the two together
    is what let FALSE_MATCH 0 look like a result for a week.
    """
    fails, states, notes = [], {}, []
    for name, res in (('fence', _fence_ok(text, pos, spec)),
                      ('basis', _basis_ok(text, pos, spec, axes)),
                      ('period', _period_ok(text, pos, spec, quarter, axes,
                                            record))):
        ok, why, state = res
        states[name] = state
        if not ok:
            fails.append(why)
        elif why:
            notes.append('%s: %s' % (name, why))
    states['notes'] = notes
    states['evidenceCount'] = sum(1 for k in ('fence', 'basis', 'period')
                                  if states[k] == EVIDENCE)
    return (not fails), fails, states


def judge(text, pre_row, slot, spec, quarter=None, got=None, record=None):
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

    ok, fails, states = provenance(text, pos, spec, quarter,
                                   got.get('cellAxes'), record)
    if ok:
        # ★ THE SPLIT TRAVELS WITH THE VERDICT. Counting evidence-bearing
        # rows in a separate script is how 'MATCH 34' was quoted for a week
        # without anyone knowing 8 of them had nothing behind them.
        return dict(verdict='MATCH', reason=None, value=value, pos=pos,
                    checks=states)
    # ★ THE DIGITS AGREE AND THE POSITION DOES NOT SUPPORT THEM.
    return dict(verdict='FALSE_MATCH', reason='; '.join(fails), value=value,
                pos=pos, checks=states)


def report(counts, population):
    """A line that cannot be quoted without its denominator."""
    total = sum(counts.get(v, 0) for v in VERDICTS)
    parts = ' · '.join('%s %d' % (v, counts.get(v, 0)) for v in VERDICTS)
    return '%s   [denominator %d of %d rows: %s]' % (parts, total, population,
                                                     'all verdicts shown')
