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
import re

from . import extract
from . import parallel
from . import period as period_mod
from . import registry

#: ★★★ EXCLUDED SPLITS THREE WAYS, AND TWO OF THEM STAY IN THE DENOMINATOR.
#:
#:   EXCLUDED       a closed-list reason -- NOT_IN_PR / CALL_SOURCED /
#:                  QUALITATIVE. Genuinely out. The ONLY exit.
#:   UNSPECD        NEEDS_REMAP: the issuer changed disclosure and our spec
#:                  is stale. That is OUR gap, so it counts against us.
#:   UNCLASSIFIED   NOT_EXTRACTABLE for a reason nobody put on the list. A
#:                  row no one ruled on is not an excused row.
#:   NO_ANSWER_KEY  a value was read and there is no hand read to compare.
#:                  Its own verdict: neither a pass nor a failure, and
#:                  folding it into EXCLUDED hid it inside an exit.
VERDICTS = ('MATCH', 'FALSE_MATCH', 'MISMATCH', 'LOST', 'REFUSED',
            'UNSPECD', 'CARD_DEFECT', 'UNCLASSIFIED', 'NO_ANSWER_KEY',
            'EXCLUDED')

#: the only verdict that leaves the graded population
OUT_OF_DENOMINATOR = ('EXCLUDED',)


EVIDENCE, ABSENT, VACUOUS, NA = 'EVIDENCE', 'ABSENT', 'VACUOUS', 'NA'


def basis_token(value):
    """The BASIS a field declares, ignoring any prose that follows it.

    ★★★ `basis` CARRIES PROSE ON SOME ROWS, and one of them carries a
    FIGURE: ORCL[7] declares 'non-GAAP. ★ reconciliation row is RAGGED --
    header declares 6 cols...' and ADBE[12] declares 'non-GAAP ($2,974). ★
    GAAP is $2,354 and appears FIRST...'. Comparing a resolved basis against
    that whole paragraph fails every time, and the ADBE string contains the
    ANSWER -- a leak on the surface I had called closed.

    Reading only the leading token is the defensive fix. The field itself is
    Kyle's to split.
    """
    t = (value or '').strip()
    m = re.match(r'(non[- ]gaap|gaap|core|adjusted|cash)', t, re.I)
    return m.group(1) if m else t.split('.')[0].strip()


def _same_basis(a, b):
    na = basis_token(a).lower().replace(' ', '').replace('-', '')
    nb = basis_token(b).lower().replace(' ', '').replace('-', '')
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
    # ★★★ POSITION FIRST, CLAUSE SECOND. The basis qualifier LEADS its value
    # -- the mirror of the currency rule, which exists because a currency
    # qualifier TRAILS its figure. A sentence naming BOTH bases separates
    # them perfectly by position ('GAAP EPS ... $1.56 ... and non-GAAP EPS
    # ... $1.92') and scored VACUOUS for want of a mechanism that had been
    # built for the other axis.
    at = extract.basis_at(text, pos)
    if at:
        if _same_basis(at, want):
            return True, None, EVIDENCE
        return (False, 'the nearest basis word before this value is %s, the '
                'row declares %s' % (at, want), EVIDENCE)
    # ★★★ THE PROSE PATH USES THE SECTION HEADING TOO. A guide clause names
    # no basis; the block above it does -- ADBE prints 'Non-GAAP diluted net
    # income per share' as the heading over the figure.
    frag = extract.governing_context(text, pos)
    low = (frag or '').lower()
    has_non = bool(_NON_GAAP.search(low))
    # ★★★ 'gaap' in low IS ALWAYS TRUE WHEN 'non-gaap' IS PRESENT. Every
    # non-GAAP-only clause therefore read as naming BOTH bases, which this
    # function scores VACUOUS -- so the basis check could NEVER find
    # non-GAAP evidence in prose, which is most of where it lives. A
    # substring test for a token whose negation CONTAINS it.
    has_gaap = bool(_BARE_GAAP.search(low))
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


#: 'gaap' NOT preceded by 'non-' or 'non ' -- the negation contains the token
_BARE_GAAP = __import__('re').compile(r'(?<!non-)(?<!non )gaap')
_NON_GAAP = __import__('re').compile(r'non[- ]gaap')


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


#: how good a verdict is. A derived row can be no better than its worst
#: operand, so these are ordered and min() over them is the cap.
_RANK = {'MATCH': 5, 'NO_ANSWER_KEY': 4, 'CARD_DEFECT': 3, 'UNSPECD': 2,
         'REFUSED': 2, 'MISMATCH': 1, 'LOST': 1, 'FALSE_MATCH': 0,
         'UNCLASSIFIED': 2, 'EXCLUDED': 5}


def operand_cap(text, spec, record, quarter, depth=0):
    """(verdict, why) of the WORST operand of a derived row, or (None, None).

    ★★★ A DERIVED ROW'S VERDICT IS CAPPED BY ITS WEAKEST OPERAND. HPE
    published 4.485 as a MATCH, derived from the FY26 EPS guide range
    $3.75-$3.85 -- while HPE[3], WHICH IS THAT GUIDE, REFUSED. Same figure,
    same document, same card: published via derivation, refused via direct
    read, and nothing on the card could see the disagreement.

    ★★ AND THIS LANDS WITH DERIVATION COVERAGE, NOT AFTER IT. Every derived
    row is an all-vacuous MATCH -- fence, basis and period have nothing
    structural to read on a computed number -- so growing derivation grows
    the UN-AUDITABLE set. A capability that increases the count of rows
    nothing can check is a liability on its own terms.
    """
    from . import derived as _derived
    sources = (spec or {}).get('sourceRows') or []
    rid = (record or {}).get('id')
    rows = ((record or {}).get('preEarnings') or {}).get('keyKPIs') or []
    acts = ((record or {}).get('actuals') or {}).get('keyKPIs') or []
    worst, worst_why = None, None
    for src in sources:
        m = _derived._CARD_REF.match((src or '').strip())
        if not m or m.group(1) != rid:
            continue
        i = int(m.group(2))
        if i >= len(rows) or depth >= _derived.MAX_DEPTH:
            continue
        sub_spec = registry.spec_for(rows[i])
        sub_slot = acts[i] if i < len(acts) and isinstance(acts[i], dict)             else {}
        sub = judge(text, rows[i], sub_slot, sub_spec, quarter,
                    record=record, _depth=depth + 1)
        if _RANK.get(sub['verdict'], 0) < _RANK.get(worst or 'MATCH', 5):
            worst = sub['verdict']
            worst_why = ('operand [%d] %r is %s: %s'
                         % (i, (rows[i].get('name') or '')[:30],
                            sub['verdict'], (sub.get('reason') or '')[:70]))
    return worst, worst_why


def judge(text, pre_row, slot, spec, quarter=None, got=None, record=None,
          _depth=0):
    """The verdict for one row, with its provenance reasons."""
    stored = (slot or {}).get('actual')
    _st = registry.status_of(spec)
    # ★★★ AN AUTHORED RULING OUTRANKS EVERY INFERENCE. A duplicate slot or an
    # inverted row is a fact about OUR CARD: excluding it hides it, so it
    # stays in the denominator with its own name.
    _disp = registry.row_disposition(spec)
    if _disp == 'CARD_DEFECT':
        return dict(verdict='CARD_DEFECT', value=None, pos=None,
                    reason=str((spec or {}).get('rowDefectNote')
                               or 'authored CARD_DEFECT')[:160])
    if _disp == 'UNSPECD':
        return dict(verdict='UNSPECD', value=None, pos=None,
                    reason=str((spec or {}).get('rowDefectNote')
                               or 'authored UNSPECD — unfinished work')[:160])
    if _st == 'NEEDS_REMAP':
        return dict(verdict='UNSPECD', value=None, pos=None,
                    reason='issuer changed disclosure — the spec is stale, '
                           'and that is our gap, not an exemption')
    if _st != 'EXTRACTABLE':
        klass = registry.exclusion_class(spec)
        if klass:
            return dict(verdict='EXCLUDED', value=None, pos=None,
                        exclusionClass=klass,
                        reason='%s — closed list' % klass)
        return dict(verdict='UNCLASSIFIED', value=None, pos=None,
                    reason=('specState %s, but the stated reason is not on '
                            'the closed list (%s): %r'
                            % (_st, '/'.join(registry.EXCLUSION_CLASSES),
                               str((spec or {}).get('why') or '')[:90])))
    # ★ THE CALLER'S RECORD, NOT A STUB. This rebuilt {'fiscalQuarter': q}
    # and threw the real record away, so a derived row re-judged here could
    # not resolve a sourceRow written as an index into the card -- and
    # refused with a unit message that described nothing. Discard pattern
    # again: the fact was in the call and was dropped one frame down.
    got = got if got is not None else (
        extract.value_for(text, pre_row,
                          record=(record or {'fiscalQuarter': quarter}))
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
        return dict(verdict='NO_ANSWER_KEY', value=value, pos=pos,
                    reason='a value was read and there is no hand read to '
                           'compare it against')

    if not parallel.agrees(stored, value):
        return dict(verdict='MISMATCH', reason='digits disagree',
                    value=value, pos=pos)

    # ★ THE FOURTH CHECK. Structure cannot vouch for a computed number, so a
    # derived row is vouched for by its OPERANDS or not at all.
    if (spec or {}).get('derived') and (spec or {}).get('sourceRows')             and _depth < 3:
        cap, cap_why = operand_cap(text, spec, record, quarter, _depth)
        if cap is not None and _RANK.get(cap, 0) < _RANK['MATCH']:
            return dict(verdict=cap, value=value, pos=pos,
                        reason='DERIVED ROW CAPPED BY ITS WEAKEST OPERAND — '
                               + (cap_why or ''),
                        checks={'fence': NA, 'basis': NA, 'period': NA,
                                'operand': cap, 'evidenceCount': 1,
                                'notes': [cap_why or '']})

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
    """A line that cannot be quoted without its denominator.

    ★ AND THE GRADED POPULATION IS PRINTED SEPARATELY, because only EXCLUDED
    leaves it. UNSPECD and UNCLASSIFIED are our own gaps and stay in.
    """
    total = sum(counts.get(v, 0) for v in VERDICTS)
    out = sum(counts.get(v, 0) for v in OUT_OF_DENOMINATOR)
    parts = ' · '.join('%s %d' % (v, counts.get(v, 0)) for v in VERDICTS)
    return ('%s   [all %d rows shown of %d; GRADED POPULATION %d — only '
            'EXCLUDED leaves it]' % (parts, total, population, total - out))
