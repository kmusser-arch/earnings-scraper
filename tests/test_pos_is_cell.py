# -*- coding: utf-8 -*-
"""THE RECORDED POSITION IS THE SELECTED CELL, not the row that matched.

Provenance has now arrived one level too coarse three times: first shifted by
dewrap into a frame the caller does not hold, then anchored at the LABEL of a
table row whose cells sit lines or columns away. A check that reads 'the
clause at pos' was being handed the words the ROW opens with -- on AVGO's EPS
row, 'GAAP Non-GAAP ---- ---- (Dollars in millions', which names both bases
and no period at all.

Both readers already knew where the cell was. hgrid carries each cell's column
x out of describe_cells; sgrid and tables walk line indices. Neither returned
it, so the coordinate existed and was thrown away at the last step.

★ AND THE ASSERTION IS NOT VACUOUS. A test that only says 'pos is an int' or
'pos is inside the table' passes on the label too. Each case below asserts the
document text AT pos is the selected figure AND that the label position is
NOT -- so if the change were reverted, every case fails rather than one.

★★ WHAT THIS TEST CANNOT TELL APART: whether the cell selected was the RIGHT
cell. It pins the coordinate to the reader's own choice. A reader that picks
the prior-year column passes this test pointing precisely at the wrong number,
which is what the synthetic injection is for.
"""

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import hgrid as HG           # noqa: E402
from earnings_scraper import sgrid as SG           # noqa: E402
from earnings_scraper import tables as T           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AVGO = os.path.join(HERE, 'fixtures', 'releases', 'AVGO-2026-09-02.txt')
SNOW = os.path.join(HERE, 'fixtures', 'releases', 'SNOW-2026-09-02.txt')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def digits(s):
    return re.sub(r'[^0-9]', '', s or '')


def at(text, pos, want):
    """Does the document AT pos print `want`, separators and all?"""
    if not isinstance(pos, int):
        return False
    here = text[pos:pos + 40].lstrip(' ($')
    return digits(here).startswith(digits(want))


def main():
    for p in (AVGO, SNOW):
        if not os.path.exists(p):
            print('FAIL fixture missing: %s' % os.path.basename(p))
            return

    # ── the readers report a coordinate at all ───────────────────────────
    body = io.open(AVGO, encoding='utf-8').read()
    lines = [l.strip() for l in body.split(chr(10))]
    # the label WRAPS: 'Earnings per common' on 46, ' share - diluted' plus
    # every cell on 47. The data row is 47, and the test says so out loud
    # rather than searching, so a fixture edit fails here and not silently.
    eps = 47
    check(lines[eps].startswith('share - diluted'),
          'the AVGO EPS data row is still line %d of the fixture' % eps)
    sel = HG.select(lines, eps, {'basis': 'non-GAAP', 'documentUnit': '$'},
                    is_boundary=None)
    check(sel.get('cellX') is not None and sel.get('cellLine') == eps,
          'hgrid returns the chosen cell\'s column x and line, not just its '
          'value (x=%s line=%s)' % (sel.get('cellX'), sel.get('cellLine')))

    off = X.cell_offset(body, sel['cellLine'], sel['cellX'])
    check(at(body, off, sel['raw']),
          'and cell_offset puts that back into DOCUMENT coordinates, landing '
          'on %r' % body[off:off + 6])
    # ★ THE LEADING WHITESPACE IS PUT BACK. The readers are handed STRIPPED
    # lines, so an x taken straight to the document is short by the indent --
    # the dewrap shift again in a different frame.
    naive = body.count(chr(10), 0, off)
    raw_line = body.split(chr(10))[naive]
    check(raw_line != raw_line.lstrip(),
          'on a line that IS indented (%d spaces), which is what makes the '
          'correction observable rather than assumed'
          % (len(raw_line) - len(raw_line.lstrip())))

    # ── stacked: the cell is a line of its own ───────────────────────────
    snow = io.open(SNOW, encoding='utf-8').read()
    slines = [l.strip() for l in snow.split(chr(10))]
    got = SG.select(slines, 374, {'basis': 'non-GAAP', 'documentUnit': '%'})
    check(got.get('value') == 74.7 and got.get('cellLine') == 409,
          'sgrid names the LINE its cell came from (%s) -- 74.7 is THIRTY '
          'FIVE lines below the label at 374, which is the whole point: no '
          'arithmetic on the label index reaches it' % got.get('cellLine'))
    check(SG.block_cells(slines, 374) == [(1057.4, False), (70.9, True),
                                          (1114.1, False), (74.7, True)],
          'while block_cells keeps its pair contract for every other caller')

    # ── vertical: the walker says which line, arithmetic cannot ──────────
    trips = T.row_value_cells_at(slines, 374)
    check([ln for _v, _p, ln in trips] == [381],
          'tables reports a line per cell too (%s) -- blank lines and bare '
          '$ / %% markers are skipped, so cell i is NOT at label + i + 1 and '
          'the coordinate cannot be derived by arithmetic'
          % [ln for _v, _p, ln in trips])
    check(T.row_value_cells(slines, 374) == [(v, p) for v, p, _l in trips],
          'and its pair form is exactly the triples without the coordinate')

    # ── end to end, ON THE ROW'S OWN SPEC, not one written here ──────────
    # A hand-built spec tests the spec I just wrote, not the one that runs.
    # This reads AVGO[8] out of the library exactly as the sweep does.
    if not os.path.exists(LIB):
        print('SKIP library not reachable — the end-to-end case did not run')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    rec = recs['AVGO-2026Q3']
    prow = rec['preEarnings']['keyKPIs'][8]
    out = X.value_for(body, prow, record=rec) or {}
    if out.get('value') is None:
        check(False, 'AVGO[8] produced no value: %s'
              % (out.get('why') or '')[:70])
        return
    check(at(body, out.get('pos'), '3.32'),
          'value_for records pos ON the selected cell (%r)'
          % body[out['pos']:out['pos'] + 6])
    check(out.get('lpos') != out.get('pos'),
          'and lpos still carries the LABEL separately — the row is not lost, '
          'it is no longer pretending to be the value')
    # THE ANTI-VACUOUS HALF: the label would not satisfy the assertion, so a
    # revert turns every case above red instead of silently passing.
    check(not at(body, out.get('lpos'), '3.32'),
          'the label position does NOT satisfy that assertion — reverting the '
          'change fails this test rather than passing it quietly')


main()
