"""criticalUnitConversionInVerdicts — the false 🟢 CLEAR on a missed guide.

15 library rows are named ($B) while their actual is stored in $M. If the
conversion is skipped before the comparison, the raw number beats the bogey
trivially and the row renders 🟢 CLEAR on a guide that MISSED. It fails in the
BULLISH direction, on the rows that decide the trade, and it fails silently —
every other guard in this project refuses when unsure; this one asserts a beat
that did not happen.

THE PIN: APP-2026Q2 row [2], raw 2070 in "3Q Revenue Guide ($B)" against a 2.08
street, must render 2.07 AND 🔴 MISS. APP fell 19.66% on that print.

Both halves are checked, because either alone passes while the card is wrong:
  · the DISPLAY must divide, and
  · the VERDICT must be computed on the divided number.

`_display_actual` and `_verdict_cell` are IMPORTED from render_scorecard and the
import proves its provenance — a divergent local copy would be self-consistent
and would pass any test that only inspects pipeline output.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import gate, parse as P                # noqa: E402
from earnings_scraper import score as S                      # noqa: E402
from earnings_scraper import scorecard as SC                 # noqa: E402
from earnings_scraper.model import Model                     # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:38]))
    if not ok:
        FAIL[0] += 1


def main():
    model = Model()

    print('=== THE PIN: raw 2070 in a ($B) row vs a 2.08 street ===')
    name = '3Q Revenue Guide ($B) ★'
    ak = dict(actual=2070, actualUnit='$M')
    pk = dict(name=name, consensus=2.08, bogey=2.12)
    shown, verdict = SC.display_actual(name, ak), SC.verdict_cell(ak, pk)
    check('display divides: 2070 ($M) -> 2.07', shown.startswith('2.07'), shown)
    check('and states the unit it converted to', '($B)' in shown, shown)
    check('verdict is computed on the DIVIDED number', 'MISS' in verdict,
          verdict)
    check('not on the raw one (2070 vs 2.12 would be a CLEAR)',
          'CLEAR' not in verdict, verdict)

    print('')
    print('=== the startup assertion covers both halves ===')
    check('assert_render_functions passes', SC.assert_render_functions() is True)

    print('')
    print('=== provenance: the functions come from the model repo ===')
    for attr in ('_display_actual', '_verdict_cell'):
        fn = SC._renderer_function(attr)
        f = (getattr(fn, '__code__', None).co_filename or '').lower()
        check('%s is defined in render_scorecard.py' % attr,
              f.endswith('render_scorecard.py'), f[-42:])
        check('    and not inside earnings_scraper',
              'earnings_scraper' not in f)

    class Fake(object):
        def _display_actual(self, name, ak):
            return '2,070 ($B)'          # the exact bug signature

    saved = SC.renderer
    try:
        SC.renderer = lambda: Fake()
        try:
            SC._renderer_function('_display_actual')
            check('a stand-in module is refused', False, 'accepted')
        except SC.RendererFunctionMissing as exc:
            check('a stand-in module is refused', True, str(exc)[:34])
    finally:
        SC.renderer = saved

    print('')
    print('=== with NO actualUnit the renderer cannot resolve the scale ===')
    bare = dict(actual=2070)
    check('display prints the raw number',
          SC.display_actual(name, bare).startswith('2,070'),
          SC.display_actual(name, bare))
    check('and the verdict would be a FALSE CLEAR',
          'CLEAR' in SC.verdict_cell(bare, pk),
          SC.verdict_cell(bare, pk))
    check('...which is why the guard blanks the row before render() sees it',
          True)

    rec = dict(preEarnings=dict(keyKPIs=[dict(name=name, consensus=2.08,
                                              bogey=2.12)]),
               actuals=dict(keyKPIs=[dict(actual=2070)]))
    found = SC.undeclared_magnitude_rows(rec)
    check('the guard detects it', len(found) == 1, found)
    check('    and reports the ratio', found and found[0][4] > 100,
          found[0][4] if found else None)
    SC._guard_units(rec)
    row = rec['actuals']['keyKPIs'][0]
    check('the value is refused, not rendered', row['actual'] is None,
          row['actual'])
    check('the row is flagged unit-ambiguous', row['unitAmbiguous'] is True)
    check('and the note names both figures',
          '2070' in row['actualNote'] and '2.12' in row['actualNote'],
          row['actualNote'][:36])

    print('')
    print('=== a correctly-declared row is left alone ===')
    ok_rec = dict(preEarnings=dict(keyKPIs=[dict(name=name, consensus=2.08,
                                                 bogey=2.12)]),
                  actuals=dict(keyKPIs=[dict(actual=2070, actualUnit='$M')]))
    check('nothing detected', SC.undeclared_magnitude_rows(ok_rec) == [])
    SC._guard_units(ok_rec)
    check('the value survives the guard',
          ok_rec['actuals']['keyKPIs'][0]['actual'] == 2070)

    print('')
    print('=== APP-2026Q2 end to end, STORED path ===')
    fw = gate.framework_from(model)
    txt = SC.render_record(model, model.record_by_id('APP-2026Q2'), fw)
    rows = [l for l in txt.splitlines() if '($B)' in l and 'metric' not in l]
    # ★ TOLERANCE, NOT AN EXACT PIN. These were pinned as rendered strings --
    # '1.924' -- and the 2026-09-04 $M->$B rescale made the stored actual
    # 1.923686, so the render became '1.9237' and four assertions broke on a
    # repair that changed no score. An exact pin on a rendered float re-breaks
    # on the next rescale and teaches nothing.
    #
    # ★★ WHAT THIS TEST IS ACTUALLY ABOUT is the row NOT rendering a raw
    # thousand-fold magnitude, which the assertion below states directly. The
    # per-row check now asserts the MAGNITUDE within tolerance and the verdict
    # exactly -- the verdict is the part a wrong unit would flip.
    want = [('2Q Revenue', 1.9237, 'MISS'),
            ('2Q Adj EBITDA', 1.6138, 'MISS'),
            ('3Q Revenue Guide', 2.07, 'MISS'),
            ('3Q Adj EBITDA Guide', 1.725, 'MISS')]
    for label, value, verdict in want:
        line = next((l for l in rows if label in l), '')
        nums = [float(t.replace(',', '')) for t in re.findall(
            r'-?\d[\d,]*\.?\d*', line)]
        near = any(abs(n - value) < 0.01 for n in nums)
        check('%-22s renders ~%-8s and %s' % (label, value, verdict),
              near and verdict in line, line.strip()[-46:])
    check('no row on this card renders a raw thousand-fold magnitude',
          not any(',' in l.split()[-2] if len(l.split()) > 2 else False
                  for l in rows), 'checked %d rows' % len(rows))

    print('')
    print('=== APP-2026Q2 end to end, LIVE path from real wire copy ===')
    entry = model.prepare_from_record(model.record_by_id('APP-2026Q2'))
    body = ('AppLovin Corporation Reports Q2 Results\n\n'
            'Total revenue was $1.924 billion.\n'
            'For the third quarter, the company expects revenue of '
            '$2.070 billion.\n')
    card = S.score_release(P.parse_release(
        dict(msg_type='news_item', source='BUS', id='APP-2026Q2',
             headline=body.splitlines()[0], body=body)), entry, model)
    check('the parser normalises to $M', card['keyKPIs'][0]['actual'] == 1924.0,
          card['keyKPIs'][0]['actual'])
    check('and DECLARES the unit, which is what makes conversion possible',
          card['keyKPIs'][0]['actualUnit'] == '$M',
          card['keyKPIs'][0]['actualUnit'])
    check('row [0] grades a MISS vs the 1.94 street',
          card['keyKPIs'][0]['vsCons'] == 'MISS',
          card['keyKPIs'][0]['vsCons'])
    live = SC.render_card(card, entry, fw)
    l0 = next((l for l in live.splitlines() if '2Q Revenue' in l), '')
    l2 = next((l for l in live.splitlines() if '3Q Revenue Guide' in l), '')
    check('rendered [0]: 1.924 ($B) and MISS',
          '1.924 ($B)' in l0 and 'MISS' in l0, l0.strip()[-42:])
    check('rendered [2]: 2.07 ($B) and MISS',
          '2.07 ($B)' in l2 and 'MISS' in l2, l2.strip()[-42:])

    print('')
    print('=== every live dollar-magnitude row declares its unit ===')
    from earnings_scraper import units as U
    mags = [r for r in card['keyKPIs']
            if isinstance(r.get('actual'), (int, float))
            and U.is_dollar_magnitude(r['name'])]
    check('there are magnitude rows to check', len(mags) >= 2, len(mags))
    check('all declare actualUnit', all(r.get('actualUnit') for r in mags),
          [(r['name'][:14], r.get('actualUnit')) for r in mags])

    print('')
    print('=== the library carries no unresolvable magnitude row ===')
    exposed = []
    for rec2 in model.records:
        for hit in SC.undeclared_magnitude_rows(rec2):
            exposed.append((rec2.get('id'), hit[1], hit[2], hit[4]))
    check('none of the 76 records would false-CLEAR', exposed == [], exposed[:3])

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
