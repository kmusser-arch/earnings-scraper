"""Basis is a modifier, and the BARE row is the dangerous class.

Allowing the income-statement zone was right -- revenue and EPS live in its line
items -- but it admits the one region where GAAP and non-GAAP sit side by side.
WDC-2026Q4 states GAAP 64 times and non-GAAP 65; SNDK 82 and 52. The zone always
offers both.

107 of 746 rows name a basis: adj 61, non-GAAP 22, CC 15, ex-credits 3, GAAP 2,
organic 2, core 2. SIXTY more are bare rows on basis-sensitive metrics.

★ BARE DOES NOT MEAN "EITHER IS FINE". It means the basis the street was
quoting, which is almost always non-GAAP. So a bare row takes non-GAAP when both
are offered, and NEVER GAAP silently.

Founding cases:
  WDC   GAAP EPS $8.21 against a $3.29 street estimate -- a 150% false BEAT
  CBRS  GAAP missed 7.0% while company-defined "core" beat 9.9%; tape traded GAAP

★ 'adj' is the most common spelling by a wide margin -- 61 of 107. The inline
basis check this replaced knew 'non-gaap' and 'gaap' but not 'adj', so three
fifths of the declaring rows were invisible to it.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import basis as B                      # noqa: E402
from earnings_scraper import parse as P                      # noqa: E402
from earnings_scraper import score as S                      # noqa: E402
from earnings_scraper.model import Model                     # noqa: E402

FAIL = [0]
WDC = {'GAAP': 8.21, 'non-GAAP': 3.56, 'unknown': 8.21}


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:32]))
    if not ok:
        FAIL[0] += 1


def main():
    model = Model()

    print('=== every spelling of a declared basis ===')
    for name, want in (('Q3 Non-GAAP EPS ($)', B.NON_GAAP),
                       ('Q1 Adj OI ($B)', B.NON_GAAP),
                       ('Q1 Adj GM (%)', B.NON_GAAP),
                       ('Q2 Adjusted Operating Income ($M)', B.NON_GAAP),
                       ('GAAP Operating Income ($B)', B.GAAP),
                       ('Core Revenue ($M)', B.CORE),
                       ('cRPO Growth CC (%)', B.CC),
                       ('Azure FXN Growth (%)', B.CC),
                       ('Q4 EPS Guide ($)', None),
                       ('Q1 Operating Income ($B)', None),
                       ('FY26 EPS ($)', None)):
        check('%-34s -> %s' % (name[:34], want or 'bare'),
              B.declared(name) == want, B.declared(name))

    print('')
    print('=== a declaring row matches ONLY that basis, both directions ===')
    v, b, _n = B.select('Q3 Non-GAAP EPS ($)', WDC)
    check('non-GAAP row takes 3.56', (v, b) == (3.56, B.NON_GAAP), (v, b))
    v, b, _n = B.select('Q1 Adj EPS ($)', WDC)
    check('an "Adj" row is the same thing', (v, b) == (3.56, B.NON_GAAP),
          (v, b))
    v, b, _n = B.select('GAAP EPS ($)', WDC)
    check('a GAAP row takes 8.21', (v, b) == (8.21, B.GAAP), (v, b))
    v, b, note = B.select('Q1 Adj OI ($B)', {'GAAP': 900.0})
    check('a non-GAAP row REFUSES a GAAP-only release', v is None, v)
    check('    and the refusal cites CBRS', 'CBRS' in (note or ''),
          (note or '')[:34])
    v, b, note = B.select('GAAP EPS ($)', {'non-GAAP': 3.56})
    check('a GAAP row refuses a non-GAAP-only release', v is None, v)

    print('')
    print('=== the bare row: non-GAAP when both are offered ===')
    v, b, note = B.select('Q4 EPS Guide ($)', WDC)
    check('takes 3.56, NOT the 8.21 that would be a 150% false beat',
          (v, b) == (3.56, B.NON_GAAP), (v, b))
    check('    and records that both were offered',
          'both were offered' in (note or ''), (note or '')[:38])
    v, b, note = B.select('Q1 Operating Income ($B)', {'GAAP': 900.0})
    check('GAAP-only is taken but LOUDLY', (v, b) == (900.0, B.GAAP), (v, b))
    check('    with the warning that bare means the STREET basis',
          'STREET basis' in (note or ''), (note or '')[:34])
    v, b, note = B.select('Q1 Revenue ($B)', {'unknown': 850.5})
    check('an unstated basis on a bare row is fine', v == 850.5, v)

    print('')
    print('=== a declaring row with only an unstated basis on offer ===')
    v, b, note = B.select('Q1 Adj OI ($B)', {'unknown': 2540.0})
    check('read, but flagged unverified on basis', v == 2540.0, v)
    check('    and the note says so',
          'NOT STATED' in (note or ''), (note or '')[:34])

    print('')
    print('=== margins keep BOTH bases now ===')
    both = P.parse_margins('GAAP gross margin of 54.1%; '
                           'non-GAAP gross margin of 54.4%.')
    by = (both.get('grossMargin') or {}).get('byBasis') or {}
    check('both bases retained', len(by) >= 2, sorted(by))
    check('non-GAAP is 54.4',
          (by.get('non-GAAP') or {}).get('value') == 54.4)
    check('and GAAP 54.1 is no longer discarded',
          (by.get('GAAP') or {}).get('value') == 54.1)

    print('')
    print('=== the basis read is recorded on EVERY row ===')
    body = ('Western Digital Reports Results\n\n'
            'Revenue was $3.75 billion.\n'
            'GAAP gross margin of 54.1%; non-GAAP gross margin of 54.4%.\n'
            'GAAP diluted EPS of $8.21; non-GAAP diluted EPS of $3.56.\n')
    entry = model.prepare_from_record(model.record_by_id('WDC-2026Q4'))
    card = S.score_release(P.parse_release(dict(
        msg_type='news_item', source='BUS', id='WDC-2026Q4',
        headline='WD Reports Results', body=body)), entry, model)
    rows = card['keyKPIs']
    check('every row carries the three basis fields',
          all(set(('basisDeclared', 'basisRead', 'basisSensitive')) <= set(r)
              for r in rows))
    gm = next((r for r in rows if 'Gross Margin' in r['name']
               and 'Guide' not in r['name']), None)
    check('the margin row took NON-GAAP 54.4, not GAAP 54.1',
          gm and gm['actual'] == 54.4, (gm or {}).get('actual'))
    check('    and says which basis it read',
          gm and gm.get('basisRead') == B.NON_GAAP, (gm or {}).get('basisRead'))
    check('    with the reason in the note',
          gm and 'NON-GAAP' in (gm.get('vsConsNote') or ''),
          (gm or {}).get('vsConsNote', '')[:40])

    print('')
    print('=== sensitivity is marked, so a bare row is visible as a risk ===')
    for name, sens in (('Q4 EPS Guide ($)', True),
                       ('Q1 Operating Income ($B)', True),
                       ('FQ4 Gross Margin (%)', True),
                       ('2Q Adj EBITDA ($B)', True),
                       ('Q1 Revenue ($B)', False),
                       ('cRPO ($M)', False)):
        check('%-30s sensitive=%s' % (name, sens),
              B.is_sensitive(name) is sens, B.is_sensitive(name))

    print('')
    print('=== the library census the rules were measured on ===')
    declaring = bare_sensitive = total = 0
    spellings = {}
    for rec in model.records:
        for k in ((rec.get('preEarnings') or {}).get('keyKPIs')) or []:
            nm = k.get('name') or ''
            if not nm:
                continue
            total += 1
            d = B.declared(nm)
            if d:
                declaring += 1
                spellings[d] = spellings.get(d, 0) + 1
            elif B.is_sensitive(nm):
                bare_sensitive += 1
    check('rows declaring a basis are ~14%% of the library',
          0.10 <= declaring / float(total) <= 0.20,
          '%d of %d' % (declaring, total))
    check('non-GAAP (incl. adj) is the dominant spelling',
          max(spellings, key=spellings.get) == B.NON_GAAP, spellings)
    check('and there are dozens of BARE basis-sensitive rows',
          bare_sensitive >= 40, bare_sensitive)

    print('')
    print('=== the corpus offers both bases, which is why this matters ===')
    import io
    C = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
         r'\tests\corpus\%s.txt')
    for rid in ('WDC-2026Q4', 'SNDK-2026Q4'):
        try:
            txt = io.open(C % rid, encoding='utf-8').read()
        except IOError:
            continue
        g = len(re.findall(r'\bGAAP\b', txt)) - len(
            re.findall(r'non-?GAAP', txt, re.I))
        ng = len(re.findall(r'non-?GAAP', txt, re.I))
        check('%-13s states both bases' % rid, g > 10 and ng > 10,
              'GAAP~%d non-GAAP~%d' % (g, ng))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
