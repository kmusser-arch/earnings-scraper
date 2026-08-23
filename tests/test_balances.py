"""ARR / RPO / cRPO — six things called ARR, and the ones that are not dollars.

The library's 39 rows across 8 name shapes ARE the corpus. Matching the wrong
one is worse than deferring, because every one of these is a ★★ or ★★★ hero on
the record that names it.

The count rows are the dangerous ones. GTLB's "$1M+ ARR Customer Count" has a
~160 bogey and an actual of 1,519 CUSTOMERS. A total-ARR parser matching it puts
1,519 against 160 and renders a spectacular false CLEAR on a hero row. They are
fenced out of the dollar path entirely.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import balances as B                    # noqa: E402
from earnings_scraper import parse as P                       # noqa: E402
from earnings_scraper import score as S                       # noqa: E402
from earnings_scraper.model import Model                      # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:34]))
    if not ok:
        FAIL[0] += 1


def read(text, row, forward=False):
    metric = B.classify_row(row)
    if metric is None:
        return None
    q = B.qualifiers(row, S.row_qualifiers)
    r = B.parse_balance(text, metric, q, want_forward=forward, row_name=row)
    return r


def main():
    model = Model()

    print('=== the six things called ARR are classified apart ===')
    for row, want in [
            ('Q3 ARR ($M) ★★★', B.ARR),
            ('Q1 Agentforce ARR ($M) ★★★', B.ARR),
            ('Total AI ARR ($B) ★★', B.ARR),
            ('Q3 NGS ARR ($B) ★★★', B.ARR),
            ('Organic NGS ARR (ex-M&A) ($B) ★★★', B.ARR),
            ('AI Cloud ARR Run-Rate ($M) ★★★', B.RUN_RATE),
            ('Q3 Net New ARR ($M) ★★★', B.NET_NEW_ARR),
            ('cRPO ($M) ★★★', B.CRPO),
            ('RPO ($B) ★', B.RPO),
            ('$1M+ ARR Customer Count ★★', None),
            ('Net New $100K+ ARR Customers ★★', None),
            ('Large Customer Adds (>$1M ARR) ★★', None),
            ('cRPO Growth CC (%) ★', None)]:
        check('%-34s -> %s' % (row[:34], want or 'REFUSED'),
              B.classify_row(row) == want, B.classify_row(row))

    print('')
    print('=== a COUNT row never touches the dollar path ===')
    counts = ('$1M+ ARR Customer Count ★★', 'Net New $100K+ ARR Customers ★★',
              'Large Customer Adds (>$1M ARR) ★★')
    for row in counts:
        why = B.refusal_reason(row)
        check('%-34s refuses' % row[:34],
              why is not None and 'CUSTOMERS' in why, (why or '')[:30])
    check('and the refusal names the false-CLEAR risk',
          '1,519' in (B.refusal_reason(counts[0]) or ''))
    check('a count sentence yields nothing even if forced',
          read('We ended with 1,519 customers with $1M+ ARR.', counts[0])
          is None)

    print('')
    print('=== RPO is not cRPO ===')
    both = ('Current remaining performance obligation was $724.1 million.\n'
            'Remaining performance obligation was $1,204.0 million.\n')
    check('cRPO row reads 724.1',
          (read(both, 'cRPO ($M) ★★★') or {}).get('value_musd') == 724.1)
    check('RPO row reads 1204.0, not the cRPO figure',
          (read(both, 'RPO ($B) ★') or {}).get('value_musd') == 1204.0)
    only_crpo = 'Current remaining performance obligation was $724.1 million.\n'
    check('an RPO row refuses a cRPO-only release',
          read(only_crpo, 'RPO ($B) ★') is None)

    print('')
    print('=== growth is not level ===')
    check('a growth row never reaches the dollar path',
          B.classify_row('Q1 cRPO Growth (%) ★★★') is None)
    check('    and the reason names both figures',
          '724.1' in (B.refusal_reason('Q1 cRPO Growth (%) ★★★') or ''))

    print('')
    print('=== flow is not balance ===')
    zs = ('Annual recurring revenue was $3,525 million.\n'
          'Net new ARR was $166 million in the quarter.\n')
    check('total ARR reads 3525',
          (read(zs, 'Q3 ARR ($M) ★★★') or {}).get('value_musd') == 3525.0)
    check('net-new ARR reads 166, a 21x smaller flow',
          (read(zs, 'Q3 Net New ARR ($M) ★★★') or {}).get('value_musd')
          == 166.0)
    check('a balance row refuses a net-new-only release',
          read('Net new ARR was $166 million.\n', 'Q3 ARR ($M) ★★★') is None)
    check('a net-new row refuses a balance-only release',
          read('Annual recurring revenue was $3,525 million.\n',
               'Q3 Net New ARR ($M) ★★★') is None)

    print('')
    print('=== modifier symmetry, in BOTH directions ===')
    panw = ('Next-Generation Security ARR was $8.1 billion.\n'
            'Organic NGS ARR excluding M&A was $6.5 billion.\n')
    check('the plain NGS row reads 8.1',
          (read(panw, 'Q3 NGS ARR ($B) ★★★') or {}).get('value_musd') == 8100.0)
    check('the organic row reads 6.5',
          (read(panw, 'Organic NGS ARR (ex-M&A) ($B) ★★★') or {})
          .get('value_musd') == 6500.0)
    org_only = 'Organic NGS ARR excluding M&A was $6.5 billion.\n'
    check('a plain row REFUSES an organic-only sentence',
          read(org_only, 'Q3 NGS ARR ($B) ★★★') is None)
    plain_only = 'Next-Generation Security ARR was $8.1 billion.\n'
    check('an organic row refuses a plain-only sentence',
          read(plain_only, 'Organic NGS ARR (ex-M&A) ($B) ★★★') is None)

    print('')
    print('=== abbreviation aliases: the row says NGS, the wire spells it ===')
    check('NGS matches "Next-Generation Security"',
          (read(plain_only, 'Q3 NGS ARR ($B) ★★★') or {}).get('value_musd')
          == 8100.0)
    check('and still matches the literal abbreviation',
          (read('NGS ARR was $8.1 billion.\n', 'Q3 NGS ARR ($B) ★★★') or {})
          .get('value_musd') == 8100.0)
    check('a token with NO alias stays literal and refuses when absent',
          read('Widget ARR was $5 billion.\n', 'Q3 NGS ARR ($B) ★★★') is None)

    print('')
    print('=== a reported figure and a guide are told apart ===')
    guide = ('NGS ARR was $8.1 billion.\n'
             'For the fourth quarter, we expect NGS ARR of $8.9 billion.\n')
    check('the reported row takes 8.1',
          (read(guide, 'Q3 NGS ARR ($B) ★★★') or {}).get('value_musd')
          == 8100.0)
    check('the guide row takes 8.9',
          (read(guide, 'Q4 NGS ARR Guide ($B) ★★', forward=True) or {})
          .get('value_musd') == 8900.0)

    print('')
    print('=== two values for one metric refuses rather than choosing ===')
    amb = read('ARR was $3,525 million.\n'
               'Annual recurring revenue was $3,600 million.\n',
               'Q3 ARR ($M) ★★★')
    check('ambiguity is reported, not resolved',
          amb is not None and amb.get('value_musd') is None
          and amb.get('ambiguous') == [3525.0, 3600.0], (amb or {}).get('ambiguous'))

    print('')
    print('=== units: both $M and $B, always declared ===')
    for text, want in (('ARR was $3,525 million.\n', 3525.0),
                       ('ARR was $3.525 billion.\n', 3525.0),
                       ('ARR reached $3.4 billion.\n', 3400.0)):
        r = read(text, 'Q3 ARR ($M) ★★★')
        check('%-34s -> %s $M' % (text.strip()[:34], want),
              r and r['value_musd'] == want, (r or {}).get('value_musd'))
    r = read('ARR was $3.525 billion.\n', 'Q3 ARR ($M) ★★★')
    check('unit_seen is carried for the rounding guard',
          r and r.get('unit_seen') == 'billion', (r or {}).get('unit_seen'))

    print('')
    print('=== end to end: ZS-2026Q3 ARR and net-new on one card ===')
    entry = model.prepare_from_record(model.record_by_id('ZS-2026Q3'))
    card = S.score_release(P.parse_release(dict(
        msg_type='news_item', source='BUS', id='ZS-2026Q3',
        headline='Zscaler Reports Third Quarter Results',
        body='Revenue was $850.5 million, up 22%.\n'
             'Annual recurring revenue was $3,525 million.\n'
             'Net new ARR was $166 million in the quarter.\n'
             'Non-GAAP operating margin of 23.0%.\n'
             'Non-GAAP diluted earnings per share of $1.08.\n')), entry, model)
    rows = {r['name']: r for r in card['keyKPIs']}
    arr = rows.get('Q3 ARR ($M) ★★★')
    nn = rows.get('Q3 Net New ARR ($M) ★★★')
    check('the ARR hero extracts', arr and arr['actual'] == 3525.0,
          (arr or {}).get('actual'))
    check('    from the ARR path, not the revenue path',
          arr and arr['extractionSource'] == 'prose (arr)',
          (arr or {}).get('extractionSource'))
    check('the net-new hero extracts separately',
          nn and nn['actual'] == 166.0, (nn or {}).get('actual'))
    check('    and is labelled as the flow',
          nn and nn['extractionSource'] == 'prose (netNewArr)',
          (nn or {}).get('extractionSource'))
    check('currentQuarter now SCORES instead of deferring',
          isinstance(card['scores']['currentQuarter'], (int, float)),
          card['scores']['currentQuarter'])

    print('')
    print('=== end to end: GTLB cRPO scores, its count row refuses ===')
    e2 = model.prepare_from_record(model.record_by_id('GTLB-2027Q1'))
    c2 = S.score_release(P.parse_release(dict(
        msg_type='news_item', source='BUS', id='GTLB-2027Q1',
        headline='GitLab Reports First Quarter',
        body='Revenue was $264.2 million.\n'
             'Current remaining performance obligation was $724.1 million.\n'
             'We ended the quarter with 1,519 customers with $1M+ ARR.\n'
             'Non-GAAP gross margin of 88.0%.\n')), e2, model)
    r2 = {r['name']: r for r in c2['keyKPIs']}
    crpo = r2.get('cRPO ($M) ★★★')
    cnt = r2.get('$1M+ ARR Customer Count ★★')
    check('cRPO reads 724.1', crpo and crpo['actual'] == 724.1,
          (crpo or {}).get('actual'))
    check('the count row is refused, not filled',
          cnt and cnt['actual'] is None
          and cnt['extractionSource'] == 'metric-kind-refused',
          (cnt or {}).get('extractionSource'))
    check('    and 1,519 appears NOWHERE as a value',
          all(r.get('actual') != 1519 for r in c2['keyKPIs']))

    print('')
    print('=== the whole library corpus is classified, none silently dropped ===')
    pat = re.compile(r'\barr\b|\brpo\b|crpo', re.I)
    total = handled = 0
    for rec in model.records:
        for k in ((rec.get('preEarnings') or {}).get('keyKPIs')) or []:
            nm = k.get('name') or ''
            if not pat.search(nm):
                continue
            total += 1
            if B.classify_row(nm) or B.refusal_reason(nm):
                handled += 1
    check('39 rows carry one of these words', total == 39, total)
    check('every one is either classified or explicitly refused',
          handled == total, '%d of %d' % (handled, total))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
