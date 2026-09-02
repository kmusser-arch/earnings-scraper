"""Treasury / macro noise-filter tests.

Pins the 2026-08-19 founding case and the four false-positive classes the
first two replays surfaced. Every fixture below is a VERBATIM message from
news.log, not a synthetic one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from treasury_scraper import config, noise, state        # noqa: E402


def item(headline, source='HAM', instruments=(), topics=(), teaser=None):
    return {'msg_type': 'news_item', 'headline': headline, 'source': source,
            'teaser': teaser if teaser is not None else headline,
            'primary_instruments': list(instruments), 'topics': list(topics)}


# The three messages that were the trade, at their real wire times.
H0836 = ('$SPY U.S. Treasury increasing size of liquidity support buyback '
         'operations for longer-dated nominal coupon securities')
H0837 = ('$SPY (more) US Treasury: Change is effective September 9.'
         'US Treasury Department announces increased sizes')
H0838 = ('$SPY US Treasury: Current maximum size of $2B per operation will '
         'be at least $4B per operation')


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, got))

    # --- the founding case ---------------------------------------------------
    print('=== 2026-08-19 08:36:18 -- the message that was the trade ===')
    led, seen = state.Ledger(), state.SeenCache()
    t0 = 1787142978.0                                    # 08:36:18 ET
    v = noise.classify(item(H0836, 'HAM', ['EQ:US:SPY']), ledger=led,
                       seen=seen, now=t0, hot=True)
    check('fires an ALERT', v.action == 'ALERT', v.action)
    check('clears the hot floor', v.score >= v.floor,
          '%.1f/%.1f' % (v.score, v.floor))
    check('tier A', v.tier == 'A', v.tier)
    check('sovereign context recognised', 'sovereign' in v.reasons)
    check('SPY instrument tag scored', 'instr' in v.reasons)

    print('\n=== 08:38:40 -- the number, which carries NO tier-A keyword ===')
    v2 = noise.classify(item(H0838, 'HAM', ['EQ:US:SPY']), ledger=led,
                        seen=seen, now=t0 + 142, hot=True)
    check('attaches as ENRICH, not dropped', v2.action == 'ENRICH', v2.action)
    check('both figures extracted', v2.amounts == [2e9, 4e9], v2.amounts)
    check('delta computed off the ledger',
          any('2B->4B' in r for r in v2.reasons), v2.reasons)
    check('ledger seed was $2B', led.rows['buyback_op_max']['value'] == 2e9)

    print('\n=== the same story does not alert twice ===')
    v3 = noise.classify(
        item('Yield Decline Intensifies as Treasury Increases Buybacks',
             'DJN', topics=['tsy', 'bon']),
        ledger=led, seen=seen, now=t0 + 900, hot=False)   # +15m, inside
    check('demoted to CONFIRM by story cooldown', v3.action == 'CONFIRM',
          v3.action)
    check('cooldown names the family', 'debt_supply' in (v3.drop_reason or ''),
          v3.drop_reason)
    v4 = noise.classify(
        item('Bonds Bounce as Treasury Shows Willingness on Buybacks',
             'DJN', topics=['tsy']),
        # +900 suppressed and SLID the clock to t0+900, so the cooldown does
        # not lapse until t0+900+7200. This offset pins the sliding semantics:
        # at t0+7500 the story is still open, which is the whole point.
        ledger=led, seen=seen, now=t0 + 9000, hot=False)
    check('a fresh story alerts once the wire has gone quiet',
          v4.action == 'ALERT', v4.action)
    v5 = noise.classify(
        item('Treasury Buyback Still Small; Fixes Nothing', 'DJN',
             topics=['tsy']),
        ledger=led, seen=seen, now=t0 + 7500, hot=False)
    check('...but not while it is still being talked about',
          v5.action == 'CONFIRM', v5.action)

    # --- false-positive classes ---------------------------------------------
    print('\n=== L5: corporate buybacks are not macro ===')
    for h in ('SK Hynix Announces $28.6 Billion Share Buyback on AI Boom',
              'Curtiss-Wright expands 2026 share buyback program by $100M',
              'John Marshall Bancorp extends stock buyback program to Aug 2027',
              'Ipsos: Disclosure of trading in own shares under a share '
              'buyback programme'):
        vv = noise.classify(item(h, 'SIN'), ledger=state.Ledger(),
                            seen=state.SeenCache())
        check('dropped: %s' % h[:44], vv.action == 'DROP', vv.drop_reason)

    print('\n=== L3: "tga" must not match inside "mortgage" ===')
    for h in ('US MBA Mortgage Survey Of Current Interest Rates',
              'Mortgage applications dip 0.4% as purchase demand falls',
              'Invesco Mortgage price target lowered to $7.75 from $8.25'):
        vv = noise.classify(item(h, 'DJN', topics=['tsy']),
                            ledger=state.Ledger(), seen=state.SeenCache())
        check('no alert: %s' % h[:44], vv.action != 'ALERT',
              '%s %s' % (vv.action, vv.drop_reason or vv.reasons))
    check('bare TGA in caps still matches',
          'tga' in noise._hits(('the tga balance', 'The TGA balance'),
                               noise._A_PAT))

    print('\n=== L2: ceremonial and boilerplate releases ===')
    for h in ('READOUT: Financial Stability Oversight Council Meeting',
              'Remarks by Secretary Bessent on the debt limit',
              'Fitch Assigns Final Ratings to BSPDF 2026-FL5 Issuer, LLC',
              'Economic Calendar for Today: 11:00 AM ET Treasury buyback'):
        vv = noise.classify(item(h, 'GOV'), ledger=state.Ledger(),
                            seen=state.SeenCache())
        check('dropped: %s' % h[:44], vv.action == 'DROP', vv.drop_reason)

    print('\n=== L1: republication is deduped, not re-alerted ===')
    led2, seen2 = state.Ledger(), state.SeenCache()
    a = noise.classify(item(H0836, 'HAM', ['EQ:US:SPY']), ledger=led2,
                       seen=seen2, now=t0, hot=True)
    b = noise.classify(item('MW ' + H0836 + ' -- WSJ', 'DJN'), ledger=led2,
                       seen=seen2, now=t0 + 60, hot=True)
    check('first alerts', a.action == 'ALERT', a.action)
    check('republication does not re-alert', b.action != 'ALERT', b.action)
    check('normalise strips MW/-- WSJ and tickers',
          noise.normalise('MW ' + H0836 + ' -- WSJ') == noise.normalise(H0836))

    print('\n=== L4: a restatement of a known figure is not news ===')
    led3 = state.Ledger()
    check('no delta when the number has not moved',
          led3.delta('buyback', [2.0e9]) is None, led3.delta('buyback', [2.0e9]))
    check('delta when it doubles', led3.delta('buyback', [2e9, 4e9])
          == '2B->4B (+100%)', led3.delta('buyback', [2e9, 4e9]))
    check('restatement detected', led3.is_restatement('buyback', [2.0e9]))

    print('\n=== source triage ===')
    check('EDG never alerts',
          noise.classify(item('Treasury buyback filing', 'EDG')).action == 'DROP')
    check('HAM/FLY/SIN are the fast desks',
          config.FAST_SOURCES == ['HAM', 'FLY', 'SIN'], config.FAST_SOURCES)
    check('DJN is a confirmer, never an originator',
          'DJN' in config.CONFIRM_SOURCES and 'DJN' not in config.FAST_SOURCES)

    print('\n%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
