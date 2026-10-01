# -*- coding: utf-8 -*-
r"""THE CHARS-PER-LINE FLOOR THAT WAS PROPOSED, MEASURED, AND DISPROVED.

★★★★ ONE CELL PER LINE IS NOT AN UNREADABLE SHAPE.

The proposal was symmetric with the ceiling and the reasoning was good:

    MU    1,859.2 chars/line   one continuous string -> the table reader
                               finds no cells and REFUSES (costs a blank)
    ORCL      7.4 chars/line   one cell per line -> the table reader was
                               believed to pick up fragments and PUBLISH
                               them (0.001 against a key of 6.582)

Measured over 109 corpus exhibits a floor of 20 separated 12 fragmented
documents from a healthy band at p25=45.5, clear by better than 2x.

★★★ THEN THE WIRE FIXTURES SAID NO. HPE and SNOW's real wire bodies are
2.8 and 2.4 chars per line -- MORE fragmented than ORCL -- and their table
rows have been reading correctly all along. The floor would have refused
them. THE CORPUS ALONE COULD NOT HAVE CAUGHT THIS: the false positives
live in the wire fixtures, not in the exhibits it was measured on.

This file exists so the floor is not proposed a second time. It pins the
DISPROOF, not the feature.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HPE = os.path.join(HERE, 'fixtures', 'releases', 'HPE-2026-09-02.txt')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not (os.path.exists(HPE) and os.path.exists(LIB)):
        print('SKIP fixture or library not reachable')
        return
    body = io.open(HPE, encoding='utf-8').read()
    cpl = X.chars_per_line(body)

    check(cpl < X.MIN_CHARS_PER_LINE,
          'the REAL HPE wire body measures %.1f chars per line — under the '
          'proposed floor of %d, and more fragmented than the ORCL exhibit '
          'the floor was designed to catch' % (cpl, X.MIN_CHARS_PER_LINE))
    check(X.is_fragmented(body),
          'is_fragmented() agrees, and is kept for exactly this: REPORTING '
          'the shape, never refusing on it')

    lines = body.split(chr(10))
    blank = sum(1 for ln in lines if not ln.strip())
    check(blank * 1.0 / max(1, len(lines)) > 0.9,
          '%.0f%% of its lines are blank — the body is literally '
          "'Net revenue\\n\\n\\n$\\n\\n\\n12,213', one cell to a line"
          % (100.0 * blank / max(1, len(lines))))

    # ★★★★ AND IT READS. This is the whole disproof.
    import json
    rec = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
           ['records']}['HPE-2026Q3']
    got = X.value_for(body, rec['preEarnings']['keyKPIs'][7],
                      record=rec) or {}
    check(got.get('value') == 12213.0,
          'and tables.row_value_cells_at reads 12213.0 out of it ANYWAY '
          '(%s) — a low chars-per-line ratio does not mean unreadable, so '
          'the floor must not be wired' % got.get('value'))
    check(not got.get('reasonCode'),
          'with no refusal code at all (%r): nothing about this document '
          'shape needs guarding' % got.get('reasonCode'))


main()
