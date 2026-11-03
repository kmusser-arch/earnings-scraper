# -*- coding: utf-8 -*-
r"""DEFINITION OF DONE, PINNED. The four tickers Kyle trades.

Every preset KPI under CURRENT QUARTER, NEXT QUARTER and FULL YEAR shows
a VALUE, or a declared reason why it structurally cannot. This file
states which is which, so a row that quietly goes blank -- or quietly
fills with the wrong thing -- fails here rather than at 16:05.

★★★ EVERY VALUE BELOW WAS READ OUT OF THE DOCUMENT, NOT OFF THE CARD.
An expectation snapshotted from today's output pins today's bugs as the
specification.

★★ THE DECLARED ABSENCES ARE NOT GAPS AND MUST NOT BE 'FIXED'. Apple
publishes no numeric guidance in its release, ever -- the three F1Q rows
are [call] and that is the correct, final answer for them. Net dollar
retention is a deck metric. FY+1 capex is call-only on both tickers that
carry it, and on one of them it was REFUSED on the call when asked
directly.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                       # noqa: E402
from scraper import prose_guidance as PG                      # noqa: E402
from scraper import selector as S                             # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'scraper', 'fixtures')

#: hero -> the figure AS THE DOCUMENT PRINTS IT
VALUES = {
    'PLTR_2026Q3': {
        'US Commercial Revenue Growth YoY (%)':   '148%',
        'US Commercial TCV ($B)':                 '$1.463 billion',
        'Adj Operating Margin (%)':               '62',
        'Q3 Revenue ($K)':                        '2,313,411',
        'Adj EPS ($)':                            '0.44',
        'Next-Q Revenue Guide ($M)':              '$2.649 - $2.653 billion',
        'Next-Q Adj Income from Operations ($M)': '$1.640 - $1.644 billion',
        'FY Revenue Guide ($M)':                  '$8.530 - $8.534 billion',
        'FY Adj Income from Operations ($M)':     '$5.245 - $5.249 billion',
        'FY Adj Free Cash Flow ($M)':             '$4.8 - $5.0 billion',
        'FY US Commercial Revenue Guide ($M)':    '>$3.559 billion',
    },
    'AAPL_2026Q4': {
        'F4Q iPhone Revenue ($M)':        '57,583',
        'F4Q Revenue ($M)':               '114,477',
        'F4Q Greater China Revenue ($M)': '17,539',
        'F4Q Services Revenue ($M)':      '31,573',
        'F4Q Gross Margin (%)':           '47.9%',
        'F4Q EPS ($)':                    '$2.10',
    },
    'AMZN_2026Q3': {
        'AWS operating margin (%)':           '38.7',
        'AWS revenue growth y/y (%)':         '39',
        'North America revenue ($M)':         '112,852',
        'Next-Q operating income guide ($B)': '$28.5 - $33.5 billion',
    },
    'INTC_2026Q3': {
        'Current-quarter gross margin (%), non-GAAP': '44.1',
        'DCAI revenue ($B)':                          '7.3',
        'Next-Q gross margin guide (%), non-GAAP':    '38.0',
        'Next-Q revenue guide ($B)':                  '$15.0 - $16.0',
    },
}

#: hero -> the channel that must be named. A STRUCTURAL absence: the
#: figure is not in the release and the card says where it does live.
ABSENT = {
    'PLTR_2026Q3': {'Net Dollar Retention (%)': 'call',
                    'FY Revenue Guide Raise (% of prior guide)': 'derived'},
    'AAPL_2026Q4': {'F1Q Revenue Guide (% YoY)': 'call',
                    'F1Q Gross Margin Guide (%)': 'call',
                    'F1Q Services Guide (% YoY)': 'call'},
    'AMZN_2026Q3': {'FY+1 capex framing ($B)': 'call'},
    'INTC_2026Q3': {'FY+1 capex ($B)': 'call'},
}

FAILED = []


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))
    if not ok:
        FAILED.append(msg)


def build(stem):
    path = os.path.join(FIX, '%s.html' % stem)
    if not os.path.exists(path):
        return None, None
    html = io.open(path, encoding='utf-8', errors='replace').read()
    text = sec.to_text(html)
    res = S.select(cells.from_html(html), stem.split('_')[0],
                   prose_rows=PG.from_text(text), source_text=text)
    return res, S.card(res, stem.split('_')[0], stem.split('_')[1],
                       source_text=text)


def main():
    for stem in sorted(VALUES):
        res, card = build(stem)
        if res is None:
            check(False, '%s fixture missing -- nothing asserted' % stem)
            continue
        print('')
        print('== %s' % stem)
        found = dict((f['hero'], f) for f in res.get('found') or [])
        absent = dict((n['hero'], n) for n in res.get('notInRelease') or [])

        for hero, want in sorted(VALUES[stem].items()):
            f = next((v for k, v in found.items() if k.startswith(hero)),
                     None)
            got = S._printed(f) if f else None
            check(got == want,
                  '  %-44s %s' % (hero[:44],
                                  want if got == want
                                  else 'WANT %r GOT %r' % (want, got)))

        for hero, chan in sorted(ABSENT[stem].items()):
            n = next((v for k, v in absent.items() if k.startswith(hero)),
                     None)
            check(n is not None and n.get('channel') == chan,
                  '  %-44s [%s]%s'
                  % (hero[:44], chan,
                     '' if n is not None and n.get('channel') == chan
                     else '  -- GOT %r' % (n and n.get('channel'))))

        # ★★★★ NOTHING MAY BE UNRESOLVED. A declared absence is a
        # decision and an UNRESOLVED is a defect: it says the figure IS
        # in the release and we failed to reach it. On these four
        # tickers that count is zero and must stay zero.
        unres = [n['hero'] for n in res.get('notInRelease') or []
                 if S._is_unresolved(n)]
        check(not unres, '  ZERO UNRESOLVED%s'
              % ('' if not unres else ' -- %s' % unres))

        # and every preset KPI with a period is accounted for, one way
        # or the other -- no row may simply vanish from the card
        profiles, _mt = S.load_profiles()
        periodic = [h['name'] for h in
                    profiles[stem.split('_')[0]]['heroKPIs']
                    if h.get('appliesTo') in ('currentQuarter',
                                              'nextQGuidance', 'fyGuidance')]
        loose = [n for n in periodic
                 if n not in found and n not in absent]
        check(not loose,
              '  all %d period KPIs are on the card%s'
              % (len(periodic),
                 '' if not loose else ' -- UNACCOUNTED %s' % loose))


def units():
    """★★★★ A DECLARATION MUST NEVER SILENCE THE CHECK IT BELONGS TO.

    Four heroes named '(%)' carried unit 'bps', and one of them carried
    map unit '$B'. bps has no class, so unit_class returned None and the
    class guard and the plausibility check switched off together -- the
    same failure as an EMPTY unit, except it looks declared, so nothing
    reads as missing. That hero then printed $1.463 billion under a
    percent label and no guard in selector.py could object.
    """
    print('')
    print('== unit declarations')
    for field, named, want, conflict in (
            ('$B', '%', '%', True),      # the live case, exactly
            ('%', '$M', '$M', True),
            ('', '%', '%', False),       # absent -> the name
            ('$M', '$', '$M', False),    # agree -> the more precise
            ('bps', '%', 'bps', False),  # unclassable -> left alone
            ('%', '%', '%', False)):
        got, why = S.declared_unit(field, named)
        check(got == want and bool(why) == conflict,
              '  field=%-4r name=%-4r -> %-4r %s'
              % (field, named, got, 'CONFLICT' if conflict else 'ok'))

    # ★ and the four tickers' own profiles must be free of it
    profiles, _mt = S.load_profiles()
    bad = []
    for stem in sorted(VALUES):
        tic = stem.split('_')[0]
        dlm = profiles[tic].get('documentLabelMap') or {}
        for h in profiles[tic].get('heroKPIs') or []:
            nu = S.name_unit(h.get('name') or '')
            e = dlm.get(h.get('name')) or {}
            for src in (h.get('unit'),
                        e.get('unit') if isinstance(e, dict) else None):
                why = S.declared_unit(src, nu)[1]
                if why:
                    bad.append((tic, (h.get('name') or '')[:34], why[:48]))
    check(not bad,
          '  no hero on the four tickers contradicts its own name%s'
          % ('' if not bad else ' -- %s' % bad))


def scales():
    """★★★★ SAME CLASS, DIFFERENT SCALE -- THE 1000x GAP NO CLASS GUARD
    CAN SEE. $B and $M are both CURRENCY, so the conflict arm above
    passes them and takes the field. The error has recurred four times
    and it is invisible on screen, because the card renders the
    document's own words and the unit field never reaches the display.

    ★★★ WHAT IT ACTUALLY BREAKS IS A GUARD. _plausible bounds a '$B'
    hero at 10,000 and a '$M' hero at 10,000,000, so a scale mismatch
    widens the bound a thousandfold and it reports clean forever after.
    Not a wrong-number risk -- a DEAD-GUARD risk, which compounds.

    ★★ IT SHIPPED AS A WARNING AND IS NOW A DEFECT, IN THAT ORDER AND
    FOR A MEASURED REASON. Refusing on day one would have blanked SIX of
    PLTR's eleven resolved rows over a profile bookkeeping error: a card
    going empty is a regression the trader sees, while the mismatch
    itself is invisible to him. The list is clear library-wide, so the
    next one is a NEW mistake rather than a backlog entry.

    ★ AND '$' IS NOT A SCALE. Three heroes name ($M) and declare '$',
    which says less rather than something different. The specified one
    wins and nothing is flagged.
    """
    print('')
    print('== unit SCALE')
    for field, named, want, sev in (
            ('$B', '$M', '$M', 'defect'),
            ('$M', '$B', '$B', 'defect'),
            ('$', '$M', '$M', None),     # no scale stated -> take the one that is
            ('$M', '$', '$M', None),
            ('$M', '$M', '$M', None),
            ('$B', '%', '%', 'defect')):  # the class arm still wins
        got, prob = S.declared_unit(field, named)
        sev_got = prob[0] if prob else None
        check(got == want and sev_got == sev,
              '  field=%-4r name=%-4r -> %-4r %s'
              % (field, named, got, sev_got or 'ok'))

    # ── the watchlist must stay at ZERO, in the profile ─────────────────
    profiles, _mt = S.load_profiles()
    watch = set(stem.split('_')[0] for stem in VALUES)
    lib, mine = [], []
    for tic, v in sorted(profiles.items()):
        dlm = v.get('documentLabelMap') or {}
        for h in v.get('heroKPIs') or []:
            if not isinstance(h, dict):
                continue
            nu = S.name_unit(h.get('name') or '')
            e = dlm.get(h.get('name')) or {}
            for f in (h.get('unit'),
                      e.get('unit') if isinstance(e, dict) else None):
                prob = S.declared_unit(f, nu)[1]
                if prob and prob[0] == 'warn':
                    (mine if tic in watch else lib).append(
                        (tic, (h.get('name') or '')[:34]))
    check(not mine,
          '  the four tickers carry ZERO scale contradictions%s'
          % ('' if not mine else ' -- %s' % mine))
    print('   (library-wide, off-watchlist: %d outstanding %s)'
          % (len(lib), sorted(set(t for t, _n in lib))))

    # ── and ZERO reach a rendered card, over ALL 121 documents ──────────
    # ★ THE FLOOR WALKS EVERYTHING. A gate that walks the 7 mapped
    # tickers is what let select() crash on 24 others for a week.
    flagged, built = [], 0
    for d in (FIX, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'earnings_scraper', 'state', 'html')):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.html'):
                continue
            tic = fn.split('_')[0].upper()
            if tic not in profiles:
                continue
            html = io.open(os.path.join(d, fn), encoding='utf-8',
                           errors='replace').read()
            text = sec.to_text(html)
            res = S.select(cells.from_html(html), tic,
                           prose_rows=PG.from_text(text), source_text=text)
            built += 1
            if 'unit scale:' in S.card(res, tic, '', source_text=text):
                flagged.append(fn)
    # ★★★ THE FLOOR WALKS EVERY PROFILED DOCUMENT, NOT THE FOUR. A gate
    # that walked the 7 mapped tickers is what let select() crash on 24
    # others for a week, and a scale contradiction is exactly the kind
    # of thing that lands on a ticker nobody is looking at.
    check(built >= 100,
          '  anti-vacuous: %d profiled documents went through' % built)
    check(not flagged,
          '  and not one card carries a unit defect%s'
          % ('' if not flagged else ' -- %s' % flagged))


def sign():
    """★★★★ AN UNCLOSED PAREN IS A NEGATIVE WITH ITS OTHER HALF CUT OFF.

    Oracle's free cash flow cell arrives as '(5,396'. cells.py has read
    that as -5396.0 all along -- the VALUE was never wrong -- and only
    the rendering was truncated, so the card showed '(5,396' and the
    sign was there to be missed.

    ON FREE CASH FLOW THE SIGN IS THE ENTIRE SIGNAL: -$5.4B against
    +$5.4B is a $10.8B swing, and the difference between a company
    burning cash and generating it. Same family as the 660-row parser
    sign defect, reaching the display by another route.
    """
    print('')
    print('== the sign')
    for raw, want in (('(5,396', '(5,396)'),      # the live case
                      ('(23,686', '(23,686)'),
                      ('(5,396)', '(5,396)'),     # already closed, untouched
                      ('5,396', '5,396'),         # positive, untouched
                      ('(6%)', '(6%)'),
                      ('>$3.559 billion', '>$3.559 billion')):
        got = S._close_paren(raw)
        check(got == want,
              '  %-18r -> %-12r %s' % (raw, got, '' if got == want
                                       else 'WANT %r' % want))

    # ★ AND THE INVERSE, WHICH IS THE ONE THAT MATTERS: no row may carry
    # a negative value while showing no sign at all.
    profiles, _mt = S.load_profiles()
    unsigned, closed, built = [], 0, 0
    for d in (FIX, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'earnings_scraper', 'state', 'html')):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.html'):
                continue
            tic = fn.split('_')[0].upper()
            if tic not in profiles:
                continue
            html = io.open(os.path.join(d, fn), encoding='utf-8',
                           errors='replace').read()
            text = sec.to_text(html)
            res = S.select(cells.from_html(html), tic,
                           prose_rows=PG.from_text(text), source_text=text)
            built += 1
            for f in res.get('found') or []:
                shown = S._printed(f)
                v = f.get('value')
                if str(f.get('raw') or '').startswith('(') and shown.endswith(')'):
                    closed += 1
                if (v is not None and v < 0 and '(' not in shown
                        and '-' not in shown and not shown.startswith('>')):
                    unsigned.append((fn[:28], f['hero'][:26], shown, v))
    check(built >= 100,
          '  anti-vacuous: %d profiled documents went through' % built)
    check(closed > 0,
          '  anti-vacuous: %d rows actually had a paren closed, so the '
          'check below is not passing on an empty set' % closed)
    check(not unsigned,
          '  NO row shows a negative value without a sign%s'
          % ('' if not unsigned else ' -- %s' % unsigned[:4]))


main()
units()
scales()
sign()
if FAILED:
    sys.exit(1)
