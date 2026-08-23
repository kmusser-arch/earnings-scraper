"""pr_only_gate.py — the PR-only decision gate, ported into the scraper.

Same gate as the reference implementation in the model repo, but the logic lives
in `earnings_scraper/gate.py` (so the scraper and this runner cannot drift) and
the library is read by ABSOLUTE path from config.LIB_DIR, never from a local
copy.

    py pr_only_gate.py

Reproduces the published tally: DECISIVE_BULLISH n=29, DECISIVE_BEARISH n=1,
STAY_FOR_CALL n=27 with mean -3.80%.
"""

import sys

from earnings_scraper import gate
from earnings_scraper.model import Model


def selftest(model=None):
    """Re-derive every published base rate from the live library.

    Fails loudly on drift, and asserts bracket containment on every record --
    containment is arithmetically guaranteed, so any miss is a real bug.
    """
    model = model or Model()
    fw = gate.framework_from(model)

    tally, contained, skipped = {}, 0, 0
    for rec in model.records:
        s = rec.get('scores') or {}
        try:
            g = gate.evaluate(s.get('currentQuarter'), s.get('nextQGuidance'),
                              s.get('fyGuidance'), fw)
        except gate.IncompleteScore:
            skipped += 1
            continue

        # Asserts, raising BracketContainmentError on any failure.
        if gate.assert_containment(g['overallBracket'], s.get('overall')):
            contained += 1

        px = gate.reaction_of(rec)
        if px is None:
            continue
        t = tally.setdefault(g['band'], dict(n=0, down=0, up=0, total=0.0,
                                             abs_total=0.0, ups=[]))
        t['n'] += 1
        t['total'] += px
        t['abs_total'] += abs(px)
        if px < 0:
            t['down'] += 1
        elif px > 0:
            t['up'] += 1
            t['ups'].append(px)

    print('library      : %s' % model.library_path)
    print('records      : %d   (%d skipped: a category is None)'
          % (len(model.records), skipped))
    print('containment  : %d/%d — arithmetically guaranteed, any miss is a '
          'real bug' % (contained, len(model.records) - skipped))
    print('')
    print('%-18s %5s %8s %8s %10s %10s' % ('BAND', 'n', 'down', 'up',
                                           'mean', 'mean |x|'))
    print('-' * 64)
    for band in ('DECISIVE_BULLISH', 'DECISIVE_BEARISH', 'STAY_FOR_CALL'):
        t = tally.get(band)
        if not t:
            print('%-18s %5s' % (band, '-'))
            continue
        print('%-18s %5d %8s %8s %+9.2f%% %9.2f%%' % (
            band, t['n'],
            '%d (%.0f%%)' % (t['down'], t['down'] / t['n'] * 100),
            '%d (%.0f%%)' % (t['up'], t['up'] / t['n'] * 100),
            t['total'] / t['n'], t['abs_total'] / t['n']))

    sfc = tally.get('STAY_FOR_CALL')
    if sfc and sfc['ups']:
        ups = sorted(sfc['ups'], reverse=True)
        print('')
        print('★ STAY_FOR_CALL is a SHORT-SIDE signal, not "wait and see":')
        print('  %d of %d resolved DOWN (%.0f%%), mean %+.2f%%'
              % (sfc['down'], sfc['n'], sfc['down'] / sfc['n'] * 100,
                 sfc['total'] / sfc['n']))
        print('  but the %d up-cases mean %+.2f%% — %s'
              % (len(ups), sum(ups) / len(ups),
                 ', '.join('%+.2f' % u for u in ups[:5])))
        print('  Report the base rate and the tail TOGETHER. A naked short '
              'into the call carries unbounded tail risk.')

    assert contained > 0, 'no record produced a containable bracket'
    return tally


EXPECTED = {'DECISIVE_BULLISH': 29, 'DECISIVE_BEARISH': 1,
            'STAY_FOR_CALL': 27}
EXPECTED_SFC_MEAN = -3.80


def main():
    tally = selftest()
    print('')
    ok = True
    for band, n in EXPECTED.items():
        got = (tally.get(band) or {}).get('n')
        good = got == n
        ok = ok and good
        print('%s %-18s n=%-4s expected %d' % (
            'PASS' if good else 'FAIL', band, got, n))
    sfc = tally.get('STAY_FOR_CALL') or {}
    mean = sfc['total'] / sfc['n'] if sfc.get('n') else None
    good = mean is not None and abs(mean - EXPECTED_SFC_MEAN) < 0.005
    ok = ok and good
    print('%s STAY_FOR_CALL mean %s expected %.2f%%' % (
        'PASS' if good else 'FAIL',
        ('%+.2f%%' % mean) if mean is not None else 'None',
        EXPECTED_SFC_MEAN))
    print('')
    print('ALL GREEN' if ok else 'DRIFT DETECTED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
