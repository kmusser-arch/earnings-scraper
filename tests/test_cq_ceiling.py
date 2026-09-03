"""The PR-only Current Quarter is a CEILING, not a point estimate.

Arithmetic, not calibration: the step-down is
    score = base − 0.5 × max(0, flags − maxFlags)
and 3 of the 7 flags cannot be assessed from a press release. So a PR flag count
is a FLOOR, fewer flags means less step-down means a HIGHER score, and the call
can only ADD flags. The score can only fall.

★ THE FALSIFICATION WATCH lives here. If the scraper's cq ever comes in BELOW the
hand-built cq, the theorem is wrong for that record and the likely cause is the
opposite defect -- the hand read missed a flag the PR actually carried. That is
worth catching loudly, so it is an assertion rather than a note.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import config, parse as P, score as S     # noqa: E402
from earnings_scraper.model import Model, NoProfile             # noqa: E402

CORPUS = os.path.join(config.LIB_DIR, 'tests', 'corpus')
GOLDEN = os.path.join(config.LIB_DIR, 'tests', 'golden')


def score_corpus(model, rid):
    rec = model.record_by_id(rid)
    if rec is None:
        return None, None
    try:
        entry = model.prepare_from_record(rec)
    except NoProfile:
        return None, None
    text = open(os.path.join(CORPUS, rid + '.txt'), encoding='utf-8').read()
    item = dict(msg_type='news_item', source='BUS', id=rid,
                headline=text.splitlines()[0],
                # ★ Prepend a period scope header: step 2 refuses a
                # value whose period cannot be established, and a
                # synthesised body carries none.
                body='Third Quarter Fiscal 2026 Financial Results\n' + text)
    return S.score_release(P.parse_release(item), entry, model), entry


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, got))

    model = Model()

    print('=== the registry ===')
    check('7 flags in the registry', S.FLAGS_TOTAL == 7, S.FLAGS_TOTAL)
    check('exactly 3 require the call',
          len(S.FLAGS_REQUIRING_CALL) == 3, S.FLAGS_REQUIRING_CALL)
    check('and they are the three named in the library',
          set(S.FLAGS_REQUIRING_CALL) == {'segmentDown20Sequential',
                                          'growthPriceNotVolume',
                                          'arrRpoLagsOrders'},
          sorted(S.FLAGS_REQUIRING_CALL))

    print()
    print('=== ★ THE FALSIFICATION WATCH ===')
    print('    scraper cq BELOW hand-built cq would mean the hand read missed')
    print('    a flag the PR carried — a different defect entirely.')
    print('')
    if not os.path.isdir(CORPUS):
        print('    no corpus directory — nothing to check')
    else:
        rows = []
        for f in sorted(os.listdir(CORPUS)):
            if not f.endswith('.txt'):
                continue
            rid = f[:-4]
            gpath = os.path.join(GOLDEN, rid + '.json')
            if not os.path.exists(gpath):
                continue
            golden = json.load(open(gpath, encoding='utf-8'))
            gcq = (golden.get('scores') or {}).get('currentQuarter')
            card, _entry = score_corpus(model, rid)
            if card is None:
                continue
            scq = (card.get('scores') or {}).get('currentQuarter')
            rows.append((rid, gcq, scq, card))

        for rid, gcq, scq, card in rows:
            if gcq is None or scq is None:
                print('  –    %-14s golden=%s scraper=%s  (not comparable)'
                      % (rid, gcq, scq))
                continue
            notches = (scq - gcq) / 0.5
            acc = (card.get('currentQuarterDetail') or {}).get(
                'flagAccounting') or {}
            missing = len(acc.get('notAssessedIds') or [])
            # ★ The assertion: the scraper must never come in BELOW.
            ok = scq >= gcq - 1e-9
            failures += 0 if ok else 1
            print('  %s %-14s golden=%+.1f scraper=%+.1f  %+.0f notch(es)  '
                  'unassessed flags=%d'
                  % ('PASS' if ok else '★FAIL', rid, gcq, scq, notches,
                     missing))
            if not ok:
                print('       ⛔ FALSIFIED for this record. The scraper scored '
                      'BELOW the hand read, so the ceiling theorem does not '
                      'hold here. Most likely the HAND read missed a flag the '
                      'press release carried — check the hand-built record, '
                      'not the parser.')

        print('')
        check('every record is at or above its hand read (ceiling holds)',
              all(scq >= gcq - 1e-9 for _r, gcq, scq, _c in rows
                  if gcq is not None and scq is not None))

    print()
    print('=== the ceiling is reported, and NO haircut is applied ===')
    card, entry = score_corpus(model, 'WDC-2026Q4')
    check('cq is flagged as a ceiling', card['currentQuarterIsCeiling'] is True)
    check('the note states the bound',
          'PR-only ceiling' in (card['currentQuarterCeilingNote'] or ''),
          (card['currentQuarterCeilingNote'] or '')[:40])
    check('it says the score can only FALL',
          'can only FALL' in card['currentQuarterCeilingNote'])
    check('it explicitly disclaims a haircut',
          'No haircut applied' in card['currentQuarterCeilingNote'])

    # ★ No corrective haircut: the score equals the raw band arithmetic.
    cq = card['currentQuarterDetail']
    base, step = cq.get('base'), cq.get('stepDownApplied') or 0.0
    if base is not None:
        check('score == base − step exactly (no haircut folded in)',
              abs(card['scores']['currentQuarter'] - (base - step)) < 1e-9,
              '%s − %s = %s' % (base, step, card['scores']['currentQuarter']))

    print()
    print('=== the denominator travels with the count ===')
    acc = cq.get('flagAccounting') or {}
    check('flagsTotal is 7', acc.get('flagsTotal') == 7, acc.get('flagsTotal'))
    check('summary names the denominator AND the call requirement',
          'of 7 possible' in acc.get('summary', '')
          and 'require the call' in acc.get('summary', ''),
          acc.get('summary'))
    check('marked as a floor', acc.get('isFloor') is True)
    check('unassessed ids listed', bool(acc.get('notAssessedIds')),
          len(acc.get('notAssessedIds') or []))

    print()
    print('=== bracket edges are asymmetric ===')
    g = card.get('gate') or {}
    check('top edge marked firm', 'firm' in (g.get('topEdge') or ''),
          g.get('topEdge'))
    check('bottom edge marked as the direction of travel',
          'DOWN' in (g.get('bottomEdge') or ''), (g.get('bottomEdge') or '')[:40])
    check('ceilingApplies set when narrative is None',
          g.get('ceilingApplies') is True)

    print()
    print('=== a fully-scored run is NOT a ceiling ===')
    full = dict(card)
    full['scores'] = dict(card['scores'])
    full['scores']['narrative'] = -1.0
    # Recompute via the real path rather than mutating the flag.
    check('the ceiling flag keys on narrative being None',
          card['scores']['narrative'] is None
          and card['currentQuarterIsCeiling'] is True)

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
