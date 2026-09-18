# -*- coding: utf-8 -*-
"""The horizontal grid: period x basis x currency, by column POSITION.

★★★ THE ISSUER DRAWS THE COLUMNS. Both horizontal releases underline their
headers, and every data cell falls inside exactly one dash run, so the grid
needs no index arithmetic and no cell counting. An index rule takes ORCL's
fifth column believing it is a quarter when it is a FY TOTAL; a position rule
cannot, because it reads the marks a human reads.

★★ RELATION, NOT POSITION, PICKS THE PERIOD — and that sidesteps the
fiscal/calendar trap. ORCL's Q1 FY27 report heads its columns 2026 and 2025,
CALENDAR years, while the record's fiscalYear is 2027; comparing the header to
the record would call the reported column prior-year. Comparing columns to
each other cannot.

★ AND A CHANGE COLUMN IS NOISE TO A LEVEL ROW AND THE TARGET OF A RATE ROW.
ORCL's last two columns are '% Increase in US $' and '% Increase in Constant
Currency', so the revenue row must discard exactly what the cc growth row
wants. The row's own unit decides.

Every expectation below was hand-checked against the captured release.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import axes as A            # noqa: E402
from earnings_scraper import hgrid as H           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORCL = os.path.join(ROOT, 'earnings_scraper', 'state', 'pending',
                    '20260910-161341-ORCL.json')
AVGO = os.path.join(HERE, 'fixtures', 'releases', 'AVGO-2026-09-02.txt')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not (os.path.exists(ORCL) and os.path.exists(AVGO)):
        print('FAIL horizontal fixtures missing')
        return
    orcl = ((json.load(io.open(ORCL, encoding='utf-8')).get('rawItem') or {})
            .get('body') or '').split(chr(10))
    avgo = io.open(AVGO, encoding='utf-8').read().split(chr(10))
    B = A.is_table_boundary

    def sel(lines, idx, spec):
        got = H.select(lines, idx, spec, is_boundary=B)
        return ' '.join(str(got.get('value') or '').split())

    # ── ORCL: one row, four different answers, none of them an index ─────
    check(sel(orcl, 99, {'documentUnit': '$M'}) == '$ 11,607',
          'ORCL Cloud LEVEL is 11,607 — the 2026 column, not the first cell')
    check(sel(orcl, 99, {'documentUnit': '%',
                         'currencyBasis': 'USD'}) == '62 %',
          'ORCL Cloud growth IN US $ is 62%')
    check(sel(orcl, 99, {'documentUnit': '%',
                         'currencyBasis': 'CONSTANT_CURRENCY'}) == '61 %',
          'ORCL Cloud growth IN CONSTANT CURRENCY is 61% — the sixth axis, '
          'drawn in the header of the release that produced it')
    check(sel(orcl, 100, {'documentUnit': '$M'}) == '5,550',
          'ORCL Software LEVEL is 5,550')

    # ── AVGO: the two-axis cross ─────────────────────────────────────────
    check(sel(avgo, 47, {'basis': 'non-GAAP'}) == '$ 3.32',
          'AVGO diluted EPS non-GAAP is 3.32 — column 3, the hand read')
    check(sel(avgo, 47, {'basis': 'GAAP'}) == '$ 2.68',
          'and GAAP is 2.68 — column 0, which the card reads today')
    check(sel(avgo, 43, {'basis': 'non-GAAP'}) == '$29,591',
          'AVGO net revenue non-GAAP is 29,591')

    # ── the classifiers, on the descriptions the grid actually builds ────
    cells = H.describe_cells(orcl, 99, is_boundary=B)
    check(len(cells) == 6, 'ORCL Cloud yields six described cells')
    periods = [H.column_period(d) for _x, _r, d in cells]
    check(periods[0] == (2026, 0) and periods[2] == (2025, 0),
          'the year columns parse as 2026 and 2025')
    check(periods[1] is None and periods[4] is None,
          "and '% of Revenues' and '% Increase' name no period — a DAY is "
          "not a year, so 'August 31,' no longer reads as 2031")
    check(H.column_currency(cells[5][2]) == 'CONSTANT_CURRENCY',
          "the last column keeps 'in Constant' even though the outer rule "
          'stops short of it')
    check(H.is_delta_column(cells[1][2]) and not H.is_delta_column(cells[0][2]),
          'the share-of-revenue column is a delta and the level column is not')

    # ── a rule line is not prose, and a wide header is not a sentence ────
    check(not H.is_prose_line('----  -------  -------  ----  ----  ----  ---'),
          'a rule line is never prose — its eight dash runs are not eight '
          'words')
    check(not H.is_prose_line('2026   Revenues   2025   Revenues   in US $'),
          'and a wide column header is not a sentence')
    check(H.is_prose_line('The following table summarizes our financial '
                          'results for the second quarter of fiscal 2027:'),
          'while the line that introduces a table still is')


main()
