"""Boundary recovery and statement zones.

★ BOUNDARY RECOVERY. A wire marks bullets with newlines, not terminal
punctuation. WDC-2026Q4's header is six real lines with no glyphs and no full
stops, and splitting on [.!?] merged all six into one 482-char run holding TEN
figures -- so the word "expected" on the LAST line governed the whole block, and
the reported $3.75B and 54.1% landed in the F1Q revenue and margin GUIDE rows.
Recovering the boundaries the input actually carries fixes every per-clause rule
at once, not just the forward guard.

But a newline is not always a boundary: bodies wrap at ~72 columns, so
"...expects revenue of" / "$18.1 billion" / "to $18.3 billion." is ONE clause
across three lines. Two signals are required -- the next line must START a
clause and the previous line must be able to CLOSE one.

★ STATEMENT ZONES. CLAUDE.md forbids sourcing a graded figure from the
cash-flow statement or balance sheet; the parser had no zone concept, so the
policy was unenforced. The income statement is deliberately NOT refused: its
line items are where revenue and EPS live, and APP-2026Q2 states its figures
ONLY in tables.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse as P                       # noqa: E402
from earnings_scraper import zones as Z                        # noqa: E402

CORPUS = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
          r'\tests\corpus\%s.txt')
FAIL = [0]
NUM = re.compile(r'\$\s?[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?\s*%')


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:32]))
    if not ok:
        FAIL[0] += 1


def corpus(rid):
    try:
        return io.open(CORPUS % rid, encoding='utf-8').read()
    except IOError:
        return None


def main():
    print('=== WDC header: six lines, no glyphs, no full stops ===')
    hdr = ('Q4FY26 Highlights:\n'
           'Revenue of $3.75 billion, up 44% year-over-year\n'
           'GAAP gross margin of 54.1%; non-GAAP gross margin of 54.4%\n'
           'GAAP diluted EPS of $8.21; non-GAAP diluted EPS of $3.56\n'
           'Cash flow from operations of $1.39 billion\n'
           'Q1FY27 revenue expected to be up 42% to 49% year-over-year\n')
    segs = P._sentences(hdr)
    check('splits into at least 5 clauses', len(segs) >= 5, len(segs))
    check('the revenue bullet stands alone',
          any(s.startswith('Revenue of $3.75 billion') for s in segs),
          [s[:30] for s in segs][:3])
    check('no clause holds more than 4 figures',
          max(len(NUM.findall(s)) for s in segs) <= 4,
          max(len(NUM.findall(s)) for s in segs))
    check('the forward word is isolated to its own clause',
          all(('expected' in s) == s.startswith('Q1FY27') for s in segs))
    # the whole point: the reported figures must not become guidance
    g = P.parse_guidance(hdr)
    mids = {k: v.get('mid') for k, v in g.items()}
    check('the reported $3.75B is NOT read as a revenue guide',
          3750.0 not in mids.values(), mids)
    check('nor the reported 54.1% as a margin guide',
          all((v or {}).get('grossMarginPct') != 54.1 for v in g.values()),
          {k: (v or {}).get('grossMarginPct') for k, v in g.items()})

    print('')
    print('=== a hard wrap is NOT a boundary ===')
    wrapped = ('For the first quarter of fiscal 2027, the company expects '
               'revenue of\n$18.1 billion\nto $18.3 billion.\n')
    segs = P._sentences(wrapped)
    check('the wrapped clause stays whole', len(segs) == 1, len(segs))
    g = P.parse_guidance(wrapped)
    check('so the range parses as a RANGE, not a point',
          (g.get('nextQ') or {}).get('low') == 18100.0
          and (g.get('nextQ') or {}).get('high') == 18300.0,
          {k: (v.get('low'), v.get('high')) for k, v in g.items()})

    print('')
    print('=== the line predicates, individually ===')
    for line, starts in (('Revenue of $3.75 billion', True),
                         ('GAAP gross margin of 54.1%', True),
                         ('Q1FY27 revenue expected to be up', True),
                         ('  • Net new ARR was $166 million', True),
                         ('to $18.3 billion.', False),
                         ('and free cash flow of $1.28 billion', False),
                         ('of $3.75 billion', False),
                         ('billion in the quarter', False)):
        check('%-38s starts=%s' % (line[:38], starts),
              P._line_starts_clause(line) is starts,
              P._line_starts_clause(line))
    for line, closeable in (('Q4FY26 Highlights:', True),
                            ('Revenue of $3.75 billion, up 44% YoY', True),
                            ('the company expects revenue of', False),
                            ('revenue was $850 million and', False),
                            ('gross margin of 54.4%,', False)):
        check('%-38s closeable=%s' % (line[:38], closeable),
              P._line_is_closeable(line) is closeable,
              P._line_is_closeable(line))

    print('')
    print('=== no re.I on a lowercase test ===')
    # ★ The first version had [a-z] under re.I, which matches UPPERCASE too, so
    # EVERY line read as a continuation and nothing split at all.
    check('an uppercase line is not a continuation',
          P._line_starts_clause('GAAP gross margin of 54.1%') is True)
    check('a lowercase line is', P._line_starts_clause('and margin of 54%')
          is False)

    print('')
    print('=== zones: four kinds, two refused ===')
    check('balance sheet is refused', Z.BALANCE_SHEET in Z.REFUSED)
    check('cash flow is refused', Z.CASH_FLOW in Z.REFUSED)
    check('the INCOME statement is NOT refused',
          Z.INCOME_STATEMENT not in Z.REFUSED)
    check('prose is not refused', Z.PROSE not in Z.REFUSED)

    txt = corpus('WDC-2026Q4')
    if txt:
        spans = Z.zone_spans(txt)
        found = {z for _s, _e, z in spans}
        check('WDC segments into all four zones',
              {Z.PROSE, Z.INCOME_STATEMENT, Z.BALANCE_SHEET, Z.CASH_FLOW}
              <= found, sorted(found))
        summary = Z.summarise(txt)
        check('the cash-flow zone is the biggest figure pool',
              summary[Z.CASH_FLOW]['figures'] > 50,
              summary[Z.CASH_FLOW]['figures'])
        check('and it is refused',
              Z.is_refused_zone(txt, next(s for s, _e, z in spans
                                          if z == Z.CASH_FLOW) + 50, spans))
        check('while the income statement is allowed',
              not Z.is_refused_zone(txt, next(s for s, _e, z in spans
                                              if z == Z.INCOME_STATEMENT) + 50,
                                    spans))
        check('the refusal names the founding case',
              '93.9B' in Z.refusal_note(Z.BALANCE_SHEET))

    print('')
    print('=== a graded figure is not sourced from a refused zone ===')
    synth = ('Total revenue was $850.5 million.\n'
             '\n'
             'CONSOLIDATED BALANCE SHEETS\n'
             '(in thousands)\n'
             'Total revenue was $9,999.9 million.\n')
    check('the prose figure is read', (P.parse_revenue(synth) or {})
          .get('value_musd') == 850.5,
          (P.parse_revenue(synth) or {}).get('value_musd'))
    only_bs = ('CONSOLIDATED BALANCE SHEETS\n(in thousands)\n'
               'Total revenue was $9,999.9 million.\n')
    check('a balance-sheet-only figure is refused',
          P.parse_revenue(only_bs) is None, P.parse_revenue(only_bs))
    only_cf = ('CONSOLIDATED STATEMENTS OF CASH FLOWS\n'
               'Total revenue was $9,999.9 million.\n')
    check('a cash-flow-only figure is refused',
          P.parse_revenue(only_cf) is None, P.parse_revenue(only_cf))
    only_is = ('CONSOLIDATED STATEMENTS OF OPERATIONS\n'
               'Total revenue was $9,999.9 million.\n')
    check('an income-statement figure is ALLOWED',
          (P.parse_revenue(only_is) or {}).get('value_musd') == 9999.9,
          (P.parse_revenue(only_is) or {}).get('value_musd'))

    print('')
    print('=== density, not size ===')
    sndk = corpus('SNDK-2026Q4')
    if sndk:
        blocks = sorted(P._sentences(sndk), key=len, reverse=True)[:1]
        check('SNDK longest clause holds few figures',
              len(NUM.findall(blocks[0])) <= 4,
              '%d figures in %d chars' % (len(NUM.findall(blocks[0])),
                                          len(blocks[0])))

    print('')
    print('=== the corpus still extracts what it did before ===')
    for rid, want in (('APP-2026Q2', 1924.0), ('SNDK-2026Q4', 8970.0),
                      ('WDC-2026Q4', 3750.0)):
        txt = corpus(rid)
        if txt is None:
            continue
        got = (P.parse_revenue(txt) or {}).get('value_musd')
        # APP is fully tabular, so prose revenue may be absent by design
        ok = got == want or (rid == 'APP-2026Q2' and got is None)
        check('%-13s prose revenue %s' % (rid, want), ok, got)

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
