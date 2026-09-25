# -*- coding: utf-8 -*-
"""SYNTHETIC INJECTION — FALSE_MATCH driven to fire on a real corpus row.

FALSE_MATCH has read 0 across every sweep, and a verdict that never fires
looks exactly like one that passes. The audit has no confirmed positive:
AVGO[8] was reclassified four times and ended as right-by-cancellation, not
as a false green. So the only calibration route left is to inject one.

★★★ AND THE CORPUS OFFERS NO NATURAL TARGET. The sibling-cell audit walked
all 11 grid-read rows and 33 sibling cells looking for a cell whose DIGITS
COINCIDE with the selected one while its axes differ. There are none. So the
injection forges the coincidence on a real document rather than pretending to
find it:

    HPE Q3 Revenue prints  12,213 REPORTED · 10,678 SEQUENTIAL · 9,136 PY
    forged            ->   12,213 REPORTED · 10,678 SEQUENTIAL · 12,213 PY

A FLAT YEAR IS NOT AN EXOTIC DOCUMENT. It is one character of edit and it is
what half the corpus will look like in a downturn, which is exactly when the
wrong column stops being detectable by magnitude.

★★ TWO CONTROLS, DISABLED SEPARATELY. An injection that fires is worth
nothing unless each half is shown to be load-bearing:

    forge the digits, do NOT force the column  -> MATCH      (no fault)
    force the column, do NOT forge the digits  -> MISMATCH   (caught by digits)
    both                                       -> FALSE_MATCH

★ WHAT IS SYNTHETIC AND WHAT IS REAL, stated rather than blurred: the
document is HPE's real release with ONE number changed, the spec is HPE's own
row spec out of the library, and the verdict machinery is untouched. What is
forced is the SELECTOR -- vtables returning index 2 instead of 0 -- because
that is the fault being injected.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import registry as R         # noqa: E402
from earnings_scraper import sweep as SW           # noqa: E402
from earnings_scraper import vtables as VT         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HPE = os.path.join(HERE, 'fixtures', 'releases', 'HPE-2026-09-02.txt')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')

PY_LINE = 499          # the PRIOR_YEAR_Q cell of HPE's Q3 Revenue row
PY_REAL = '9,136'
REPORTED = '12,213'


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def forge(body):
    """HPE's real release with ONE number changed: a flat year."""
    lines = body.split(chr(10))
    assert lines[PY_LINE].strip() == PY_REAL, (
        'fixture moved: line %d is %r, not %r'
        % (PY_LINE, lines[PY_LINE].strip(), PY_REAL))
    lines[PY_LINE] = lines[PY_LINE].replace(PY_REAL, REPORTED)
    return chr(10).join(lines)


def run(body, rec, prow, force_column):
    """Judge one row, optionally forcing the selector onto the PY column."""
    spec = R.spec_for(prow)
    slot = (rec.get('actuals') or {})['keyKPIs'][7]
    real = VT.column_map

    def wrong(lines, idx, n, rq, ry, values=None):
        got = dict(real(lines, idx, n, rq, ry, values=values) or {})
        if got.get('valueIndex') is not None:
            got['valueIndex'] = 2          # THE PRIOR-YEAR COLUMN
        return got

    if force_column:
        VT.column_map = wrong
    try:
        got = X.value_for(body, prow, record=rec) or {}
    finally:
        VT.column_map = real
    return SW.judge(body, prow, slot, spec, rec.get('fiscalQuarter'),
                    got=got or None, record=rec), got


def main():
    if not os.path.exists(HPE) or not os.path.exists(LIB):
        print('FAIL HPE fixture or library not reachable')
        return
    body = io.open(HPE, encoding='utf-8').read()
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    rec = recs['HPE-2026Q3']
    prow = rec['preEarnings']['keyKPIs'][7]

    # ── the row as it really is ──────────────────────────────────────────
    base, gb = run(body, rec, prow, force_column=False)
    # the judge reports in the row's STORED unit ($B), not in $M
    check(base['verdict'] == 'MATCH' and base['value'] == 12.213,
          'HPE[7] reads 12,213 ($M) from the REPORTED column, reported as '
          '%s in the row unit, and MATCHes untouched' % base['value'])
    check((gb.get('cellAxes') or {}).get('period') == 'REPORTED',
          'with the column class REPORTED travelling out of the reader')

    # ── CONTROL 1: forge the digits, do not force the column ─────────────
    flat = forge(body)
    c1, _ = run(flat, rec, prow, force_column=False)
    check(c1['verdict'] == 'MATCH',
          'CONTROL — a flat-year document alone changes nothing: the reader '
          'still takes the REPORTED column and the verdict is %s'
          % c1['verdict'])

    # ── CONTROL 2: force the column, do not forge the digits ─────────────
    c2, _ = run(body, rec, prow, force_column=True)
    check(c2['verdict'] == 'MISMATCH',
          'CONTROL — forcing the PRIOR_YEAR column on the REAL document is '
          'caught by the DIGITS (%s, read %s). This is the easy case, and it '
          'is the one that stops being detectable when the year is flat'
          % (c2['verdict'], c2['value']))

    # ── THE INJECTION: both, and FALSE_MATCH must fire ───────────────────
    inj, gi = run(flat, rec, prow, force_column=True)
    check(inj['verdict'] == 'FALSE_MATCH',
          'INJECTION — flat year AND the wrong column: the digits agree with '
          'the hand read and the verdict is %s, not MATCH' % inj['verdict'])
    check(inj['value'] == 12.213,
          'the value it would have published is 12.213 — INDISTINGUISHABLE '
          'from the correct answer by magnitude, which is the whole reason '
          'this verdict exists')
    check('PRIOR_YEAR_Q' in (inj.get('reason') or ''),
          'and the reason names the column class that caught it: %r'
          % (inj.get('reason') or '')[:70])
    check((inj.get('checks') or {}).get('period') == SW.EVIDENCE,
          'the period check is EVIDENCE-bearing here, not vacuous — it had '
          'something to read and it said NO')

    # ── and the injection is REVERSIBLE, which is the pin ────────────────
    again, _ = run(body, rec, prow, force_column=False)
    check(again['verdict'] == 'MATCH',
          'reverting both halves returns the row to MATCH — the fault was '
          'the injection, not a change left behind in the fixture')
    check(io.open(HPE, encoding='utf-8').read() == body,
          'and the fixture on disk is untouched: the forge lives in memory, '
          'so a corpus row is never quietly edited to make a test pass')


main()
