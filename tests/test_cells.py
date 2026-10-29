# -*- coding: utf-8 -*-
r"""THE FLAT CELL PARSER — EVERY RULE IN THE SPEC, DRIVEN.

Structural rules run on synthetic HTML so they never need the network. The
acceptance criteria from the spec run against the REAL Amazon and Intel
Q3 2026 exhibits when SEC_CONTACT is set, and skip cleanly when it is not.

★ WHAT THIS PARSER MUST NEVER DO is as pinned as what it must do: no
rewritten label, no merged column, no number taken from a sentence.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells                          # noqa: E402

NL = chr(10)

#: two bases, two spanning headers, six columns -- Intel's summary shape
SPAN = """<p>Q3 2026 Financial Results</p><table>
<tr><td></td><td colspan="3">GAAP</td><td colspan="3">Non-GAAP</td></tr>
<tr><td></td><td>Q3 2026</td><td>Q3 2025</td><td>vs.</td>
    <td>Q3 2026</td><td>Q3 2025</td><td>vs.</td></tr>
<tr><td>Gross margin</td><td>43.0%</td><td>38.2%</td><td>up 4.8 ppts</td>
    <td>44.1%</td><td>40.0%</td><td>up 4.1 ppts</td></tr>
</table>"""

#: Amazon's shape: period on one row, YEARS on the next, $ in its own cell
YEARS = """<p>Consolidated Statements of Operations</p><table>
<tr><td></td><td colspan="2">Three Months Ended</td>
    <td colspan="2">Nine Months Ended</td></tr>
<tr><td></td><td>2025</td><td>2026</td><td>2025</td><td>2026</td></tr>
<tr><td>Total net sales</td><td>180,169</td><td>201,944</td>
    <td>503,538</td><td>584,069</td></tr>
<tr><td>Intersegment eliminations</td><td>(6.3)</td><td>(7.1)</td>
    <td></td><td>n/a</td></tr>
</table>"""


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def pick(rows, label):
    return [r for r in rows if r['label'] == label]


def main():
    # ── RULE 1: labels verbatim, both bases survive ──────────────────────
    r = cells.from_html(SPAN)
    gm = pick(r, 'Gross margin')
    check(len(gm) == 4,
          'four numeric cells on the Gross margin row, not one: %d' % len(gm))
    vals = [x['value'] for x in gm]
    check(43.0 in vals and 44.1 in vals,
          'BOTH bases survive as separate entries (%s) — rewriting the '
          'label to grossMargin forces one of them to be thrown away'
          % vals)
    byv = dict((x['value'], x['period']) for x in gm)
    check('GAAP' in byv[43.0] and 'Non-GAAP' in byv[44.1],
          'and the spanning header reaches its columns: 43.0 under %r, '
          '44.1 under %r' % (byv[43.0], byv[44.1]))
    check('Non-GAAP' not in byv[43.0],
          "and 'GAAP' does not swallow the non-GAAP half — the colspan "
          'carry stops where the next header begins')

    # ── RULE 2: columns never collapse, and the YEAR row is a header ─────
    r = cells.from_html(YEARS)
    tns = pick(r, 'Total net sales')
    check(len(tns) == 4, 'all four columns kept: %d' % len(tns))
    periods = [x['period'] for x in tns]
    check(len(set(periods)) == 4,
          'and each carries a DISTINCT header (%s) — a year row reads as '
          'numeric, and treating it as data leaves both three-month '
          'columns labelled identically' % len(set(periods)))
    check(any('Three Months' in p and '2026' in p for p in periods),
          'period combines the span and the year: %r'
          % [p for p in periods if '2026' in p][:1])

    # ── RULE 6: clean value, raw kept, parens negative ───────────────────
    neg = pick(r, 'Intersegment eliminations')
    check(neg and neg[0]['value'] == -6.3 and neg[0]['raw'] == '(6.3)',
          'parentheses mean negative, and raw is untouched: %r -> %s'
          % (neg[0]['raw'], neg[0]['value']) if neg else 'row missing')

    # ── RULE 5: absent means absent ──────────────────────────────────────
    check(len(neg) == 2,
          'the empty cell and the n/a cell are OMITTED, not zero-filled '
          '(%d entries on a four-column row)' % len(neg))
    check(all(x['value'] != 0 for x in r),
          'and no entry anywhere carries a fabricated 0')

    # ── RULE 7: no ticker anywhere in the module ─────────────────────────
    src = open(cells.__file__, encoding='utf-8').read()
    import re as _re
    hits = [t for t in ('AMZN', 'INTC', 'NFLX', 'META', 'TXN', 'LRCX',
                        'SPCX', 'NVDA', 'MU')
            if _re.search(r'\b%s\b' % t, src)]
    check(not hits,
          'no ticker symbol appears in the parser: %s' % (hits or 'clean'))

    # ── the real exhibits ────────────────────────────────────────────────
    if not os.environ.get('SEC_CONTACT'):
        print('SKIP live acceptance — SEC_CONTACT unset')
        return
    from earnings_scraper import sec
    got = {}
    for t in ('AMZN', 'INTC'):
        cik = sec.cik_for(t)
        acc, _a = sec.filing_on(cik, '2026-10-29')
        url = sec.exhibit_url(cik, acc)
        html, _s = sec._get(url, 15)
        t0 = time.time()
        got[t] = cells.from_html(html)
        print('     %s parsed in %.0f ms, %d entries'
              % (t, (time.time() - t0) * 1000, len(got[t])))

    i = got['INTC']
    gaap = [x for x in i if x['label'] == 'GAAP gross margin percentage']
    nong = [x for x in i if x['label'] == 'Non-GAAP gross margin percentage']
    check(any(x['value'] == 43.0 for x in gaap)
          and any(x['value'] == 44.1 for x in nong),
          'INTC returns BOTH 43.0 GAAP and 44.1 non-GAAP, verbatim labels')
    check(any(x['value'] == 16513.0 for x in i
              if x['label'] == 'Net revenue'),
          'INTC revenue is 16,513 from the statement, not 16,500 from the '
          'sentence')
    outlook = [x for x in gaap + nong if 'Outlook' in x['period']]
    check(outlook,
          'the Q4 outlook rows appear under their own period header (%s), '
          'distinct from the Q3 actuals that share the label'
          % [x['period'][:26] for x in outlook][:1])
    segs = set(x['label'] for x in i
               if 'CCPG' in x['label'] or x['label'] == 'Intel Foundry'
               or x['label'] == 'Intersegment eliminations')
    check(len(segs) >= 3,
          'segment rows appear verbatim with no summing: %s'
          % sorted(segs)[:3])

    a = got['AMZN']
    check(any(x['value'] == 201944.0 for x in a
              if x['label'] == 'Total net sales'),
          'AMZN total net sales is 201,944 from the table, not 201,900 '
          'from the paragraph')


main()
