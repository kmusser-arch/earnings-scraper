"""The AMD-2026Q1 defect: one figure written into five rows.

Hand truth was 10.253 $B total / 5.775 $B data centre / 2885 / 720 / 873 $M.
The scraper wrote 10.3 into Total, Data Center, Client, Gaming AND Embedded,
and Client / Gaming / Embedded then rendered MISS when all three had CLEARED
their bogeys. Two independent causes, so three independent guards:

  1. row_qualifiers      -- a name matches on ALL its distinguishing tokens.
                            "revenue is in the name" is not a match.
  2. duplicate_actuals   -- one numeric actual in >1 row is a matcher firing
                            too widely, never a reading. Refuse BEFORE writing.
  3. segment_sum_check   -- segments approximately sum to the total, and a
                            segment never EQUALS it.

The extraction-gap rule could not catch any of this: the rows were POPULATED.
The failure was in what populated them.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse as P            # noqa: E402
from earnings_scraper import score as S            # noqa: E402
from earnings_scraper.model import Model           # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:44]))
    if not ok:
        FAIL[0] += 1


def main():
    print('=== row_qualifiers: the headline row has none, segments do ===')
    cases = [
        ('Q1 Revenue ($B)', set()),
        ('Q1 Total Revenue ($B)', set()),
        ('Q1 Client Revenue ($M)', {'client'}),
        ('Q1 Data Center Revenue ($B)', {'data', 'center'}),
        ('Q1 Gaming Revenue ($M)', {'gaming'}),
        ('Q1 Embedded Revenue ($M)', {'embedded'}),
        ('Q2 Revenue Guide ($B)', set()),
        ('FQ4 Gross Margin (%)', set()),
        ('F1Q Revenue Guide ($B)', set()),
    ]
    for name, want in cases:
        got = S.row_qualifiers(name)
        check('%-30s -> %s' % (name, sorted(want) or 'headline'),
              got == want, 'got %s' % sorted(got))

    print('')
    print('=== a qualified row is never filled from the headline total ===')
    model = Model()
    rec = model.record_by_id('AMD-2026Q1')
    entry = model.prepare_from_record(rec)
    body = ('Total revenue of $10.253 billion, up 32% year over year.\n'
            'Non-GAAP gross margin of 54.0%.\n'
            'Condensed consolidated statements of operations follow.')
    card = S.score_release(P.parse_release(
        dict(msg_type='news_item', source='BUS', id='AMD-2026Q1',
             headline='AMD Reports Q1 Results', body=body)), entry, model)
    rows = card['keyKPIs']
    seg = [r for r in rows
           if S.row_qualifiers(r['name']) and 'revenue' in r['name'].lower()]
    check('AMD has segment revenue rows to protect', len(seg) >= 3,
          '%d rows' % len(seg))
    check('no segment row inherited the headline total',
          all(r.get('actual') is None for r in seg),
          [r.get('actual') for r in seg])
    check('every segment row is honest about not parsing',
          all(r.get('extractionSource') == 'not-found' for r in seg),
          sorted({str(r.get('extractionSource')) for r in seg}))
    check('the headline row still extracted',
          isinstance(rows[0].get('actual'), (int, float)),
          rows[0].get('actual'))

    print('')
    print('=== duplicate_actuals: the value, and how many rows it hit ===')
    dup_rows = [dict(name='Q1 Revenue ($B)', actual=10.3),
                dict(name='Q1 Data Center Revenue ($B)', actual=10.3),
                dict(name='Q1 Adj GM (%)', actual=54.0),
                dict(name='Q1 Client Revenue ($M)', actual=10.3),
                dict(name='Q1 Gaming Revenue ($M)', actual=None),
                dict(name='Q1 Embedded Revenue ($M)', actual='n/a')]
    d = S.duplicate_actuals(dup_rows)
    check('all three duplicated rows are named',
          sorted(d) == [0, 1, 3], sorted(d))
    check('the count travels with each one',
          all(d.get(i) == (10.3, 3) for i in (0, 1, 3)), d.get(0))
    check('a unique value is untouched', 2 not in d)
    check('None is not a duplicate of None', 4 not in d)
    check('a prose actual is not compared numerically', 5 not in d)
    check('a clean set of rows yields nothing',
          S.duplicate_actuals([dict(name='a', actual=1.0),
                               dict(name='b', actual=2.0)]) == {})

    print('')
    print('=== the refusal lives in the write path, not in a log line ===')
    check('build_kpi_rows consults duplicate_actuals',
          'duplicate_actuals' in S.build_kpi_rows.__code__.co_names,
          sorted(n for n in S.build_kpi_rows.__code__.co_names
                 if 'dup' in n.lower()))
    check('and it refuses before assert_alignment',
          (S.build_kpi_rows.__code__.co_names.index('duplicate_actuals')
           < S.build_kpi_rows.__code__.co_names.index('assert_alignment')))

    print('')
    print('=== segment_sum_check: equality is the duplication signature ===')
    equal_rows = [dict(name='Q1 Revenue ($B)', actual=10.3),
                  dict(name='Q1 Client Revenue ($M)', actual=10.3),
                  dict(name='Q1 Gaming Revenue ($M)', actual=10.3)]
    msg = S.segment_sum_check(equal_rows, entry)
    check('a segment equal to the total is refused', bool(msg), msg)
    check('the message says duplication, not units',
          'duplication' in (msg or ''), msg)

    truth = [dict(name='Q1 Revenue ($B)', actual=10253.0),
             dict(name='Q1 Data Center Revenue ($B)', actual=5775.0),
             dict(name='Q1 Client Revenue ($M)', actual=2885.0),
             dict(name='Q1 Gaming Revenue ($M)', actual=720.0),
             dict(name='Q1 Embedded Revenue ($M)', actual=873.0)]
    check('the hand-built truth passes clean',
          S.segment_sum_check(truth, entry) is None,
          S.segment_sum_check(truth, entry))

    mixed = [dict(name='Q1 Revenue ($B)', actual=10253.0),
             dict(name='Q1 Data Center Revenue ($B)', actual=5.775),
             dict(name='Q1 Client Revenue ($M)', actual=2.885)]
    check('a scale error inside the segments is caught',
          bool(S.segment_sum_check(mixed, entry)),
          S.segment_sum_check(mixed, entry))

    check('one segment alone makes no claim',
          S.segment_sum_check(
              [dict(name='Q1 Revenue ($B)', actual=10253.0),
               dict(name='Q1 Client Revenue ($M)', actual=2885.0)],
              entry) is None)
    check('no total means no claim',
          S.segment_sum_check(
              [dict(name='Q1 Client Revenue ($M)', actual=2885.0),
               dict(name='Q1 Gaming Revenue ($M)', actual=720.0)],
              entry) is None)

    print('')
    print('=== a prose value never inherits a table scale ===')
    # The second half of the AMD defect: the unit came from a document-level
    # "(In millions)" header while the value came from prose "$10.3 billion",
    # so the card rendered 0.01 ($B).
    tabled = ('AMD Reports Q1 Results\n'
              '(In millions, except per share amounts)\n'
              'Total revenue of $10.253 billion, up 32% year over year.\n'
              'Non-GAAP gross margin of 54.0%.\n')
    parsed = P.parse_release(dict(msg_type='news_item', source='BUS',
                                  id='AMD-2026Q1',
                                  headline='AMD Reports Q1 Results',
                                  body=tabled))
    # A prose figure is parsed as a dict that CARRIES ITS OWN unit_seen. That
    # is the structural fix: there is no separate unit for a table header to
    # supply, so the header cannot reach the value.
    rev = parsed.get('revenue') or {}
    val = rev.get('value_musd')
    check('the prose figure carries its own unit',
          rev.get('unit_seen') == 'billion', rev.get('unit_seen'))
    check('a billions prose figure survives an (In millions) header',
          isinstance(val, (int, float)) and 10000 <= val <= 11000,
          '%s (%s)' % (val, rev.get('unit_seen')))
    check('the prose row grades as ~$10.25B, not 0.01',
          isinstance(val, (int, float)) and abs(val / 1000.0 - 10.253) < 0.05,
          val)
    check('the raw text is kept for the audit',
          'billion' in (rev.get('raw') or ''), rev.get('raw'))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
