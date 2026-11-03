# -*- coding: utf-8 -*-
r"""ONE COMMAND FOR A LIVE PRINT. Poll EDGAR, render, pop up.

    py scrape_print.py PLTR AAPL

★★★★ WHY THIS EXISTS AND WHY IT IS NOT `earnings_scraper watch`. The
armed listener path builds its card from scorecard.render_card and does
NOT import scraper/selector.py -- `grep -rn "scraper.selector"
earnings_scraper/` is empty. Everything validated for tonight (the hero
block, the ok/~ pins, the >> passthrough blocks, period tags, the
UNRESOLVED split) lives in the selector, so `watch` would open a window
containing the OLD card. This runs the validated path instead.

★★ IT POLLS, BECAUSE EDGAR TRAILS THE WIRE. The 8-K is filed minutes
after the press release crosses, so a single fetch at 4:05 reports
nothing and looks like a failure. Each ticker is polled until its filing
appears or --deadline passes, and a ticker that never arrives says so
rather than going quiet.

★ IT ONLY ACCEPTS TODAY'S FILING. recent_8ks is Item 2.02 filtered, but
the newest earnings 8-K on file in the afternoon is still LAST quarter's
until the new one posts. Printing a stale document that parses cleanly is
the worst thing this could do, so the filing date must match.
"""

import argparse
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from earnings_scraper import cells, sec                     # noqa: E402
from scraper import prose_guidance as PG                    # noqa: E402
from scraper import selector as S                           # noqa: E402


def exhibit(cik, accession):
    """The first structured exhibit in the accession, as raw HTML."""
    for url in sec.exhibit_candidates(cik, accession)[:6]:
        html, _st = sec._get(url, sec.DEFAULT_TIMEOUT)
        if html and html.lower().count('<td') > 20:
            return html, url
    return None, None


def render(ticker, html, quarter, full=False):
    """(card, ms, cells). DEFAULT IS THE THREE-SECTION CARD.

    ★★★ --full IS THE OLD CARD, UNCHANGED. The diagnostics, the universal
    dump, the period column and the reconciliation footer are all still
    one flag away; what they are not is the first thing on the screen at
    16:05. The default answers one question -- what did they print --
    and everything that answers a different question moved behind the
    flag.
    """
    t0 = time.time()
    text = sec.to_text(html)
    rows = cells.from_html(html)
    res = S.select(rows, ticker, prose_rows=PG.from_text(text),
                   source_text=text)
    if full:
        out = S.report(res, ticker, quarter, parser_rows=rows,
                       source_text=text)
    else:
        out = S.card(res, ticker, quarter, source_text=text)
    ms = (time.time() - t0) * 1000
    return out, ms, len(rows)


def today_filing(ticker, on):
    """(cik, accession) for a filing made ON `on`, else (cik, None)."""
    cik = sec.cik_for(ticker)
    if not cik:
        return None, None
    for acc, fdate, _acc in sec.recent_8ks(cik, limit=4):
        if str(fdate) == on:
            return cik, acc
    return cik, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('tickers', nargs='+')
    ap.add_argument('--on', default=time.strftime('%Y-%m-%d'),
                    help='filing date to accept (default: today)')
    ap.add_argument('--every', type=float, default=20.0,
                    help='seconds between EDGAR polls')
    ap.add_argument('--deadline', type=float, default=45.0,
                    help='minutes to keep polling')
    ap.add_argument('--full', action='store_true',
                    help='include the universal dump')
    ap.add_argument('--no-popup', action='store_true')
    ap.add_argument('--accession', help='skip polling, render this one')
    args = ap.parse_args(argv)

    if not sec.user_agent():
        print('SEC_CONTACT is not set. EDGAR refuses an anonymous client.')
        print('   $env:SEC_CONTACT = "kmusser@trlm.com"')
        return 2

    popup = None
    if not args.no_popup:
        try:
            from earnings_scraper.popup import CardPopup
            popup = CardPopup()
        except Exception as exc:                            # noqa: BLE001
            print('popup unavailable (%s) - terminal only' % exc)

    pending = list(args.tickers)
    stop = time.time() + args.deadline * 60
    print('watching %s for an Item 2.02 8-K filed %s  (every %.0fs, '
          'until %s)' % (', '.join(pending), args.on, args.every,
                         time.strftime('%H:%M:%S', time.localtime(stop))))
    while pending and time.time() < stop:
        for ticker in list(pending):
            try:
                if args.accession:
                    cik, acc = sec.cik_for(ticker), args.accession
                else:
                    cik, acc = today_filing(ticker, args.on)
            except Exception as exc:                        # noqa: BLE001
                print('   %-5s transport error: %s' % (ticker, exc))
                continue
            if not acc:
                continue
            html, url = exhibit(cik, acc)
            if not html:
                print('   %-5s %s has no structured exhibit yet' % (ticker, acc))
                continue
            card, ms, ncells = render(ticker, html, args.on, args.full)
            print('')
            print('=' * 78)
            print(card)
            print('')
            print('%s  %d cells  %.0f ms  %s' % (ticker, ncells, ms, url))
            sys.stdout.flush()
            if popup is not None:
                popup.submit({'ticker': ticker, 'quarter': args.on,
                              'rendered': card, 'latencyMs': ms,
                              'wire': 'EDGAR 8-K %s' % acc,
                              'receivedAt': time.strftime('%H:%M:%S')})
            pending.remove(ticker)
        if pending and time.time() < stop:
            time.sleep(args.every)

    if pending:
        # ★ A TICKER THAT NEVER ARRIVED IS A FINDING, NOT SILENCE.
        print('')
        print('NO 8-K FILED %s FOR: %s' % (args.on, ', '.join(pending)))
        print('   The release may be out on the wire with the filing still '
              'pending; re-run, or pass --accession once it posts.')
    if popup is not None:
        print('')
        print('Close the window(s) to exit.')
        popup.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
