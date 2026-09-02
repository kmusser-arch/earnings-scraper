"""Command line.

    py -m treasury_scraper replay news.log     # acceptance test on real tape
    py -m treasury_scraper poll                # treasury.gov, adaptive interval
    py -m treasury_scraper probe               # measure the Akamai edge yourself
    py -m treasury_scraper run -u kmusser      # the wire (primary path)
    py -m treasury_scraper ledger              # show / set the novelty ledger
"""

import argparse
import sys
import time

from . import config, poller, replay, state, wire


def main(argv=None):
    p = argparse.ArgumentParser(prog='treasury_scraper')
    sub = p.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('replay', help='run a wire capture through the filter')
    r.add_argument('path')
    r.add_argument('-q', '--quiet', action='store_true')

    sub.add_parser('poll', help='poll treasury.gov on the adaptive interval')
    sub.add_parser('probe', help='measure home.treasury.gov latency')

    rn = sub.add_parser('run', help='listen to the wire (primary path)')
    rn.add_argument('-u', '--user', required=True)
    rn.add_argument('--prod', action='store_true')
    rn.add_argument('--mode', default=config.DEFAULT_MODE)

    lg = sub.add_parser('ledger', help='show or set a novelty-ledger row')
    lg.add_argument('--set', nargs=2, metavar=('CONCEPT', 'VALUE'))

    a = p.parse_args(argv)

    if a.cmd == 'replay':
        res = replay.run(a.path, verbose=not a.quiet)
        return 0 if res['total'] else 1

    if a.cmd == 'probe':
        return _probe()

    if a.cmd == 'ledger':
        led = state.Ledger()
        if a.set:
            concept, value = a.set
            led.rows[concept] = {'value': float(value), 'asof': time.strftime('%Y-%m-%d'),
                                 'note': 'set from cli'}
            led.save()
        for k, v in sorted(led.rows.items()):
            print('%-20s %14s  asof %s  %s' % (
                k, state._fmt(v['value']), v.get('asof', '?'), v.get('note', '')))
        return 0

    if a.cmd == 'poll':
        pl = poller.Poller()
        try:
            pl.run()
        except KeyboardInterrupt:
            pl.stop_requested = True
        print('\n[poller] %s' % pl.stats)
        return 0

    if a.cmd == 'run':
        return _run_wire(a)
    return 2


def _probe():
    """Reproduce the latency measurement that set the poll interval."""
    import urllib.request
    targets = [('index', config.PRESS_INDEX),
               ('leaf', config.LEAF_FMT % 'sb0400'),
               ('miss', config.LEAF_FMT % 'sb9999')]
    for name, url in targets:
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                code, n = resp.status, len(resp.read())
        except Exception as exc:               # a 404 is a result, not a crash
            code, n = getattr(exc, 'code', 'ERR'), 0
        print('%-6s %-58s %s  %6.2fs  %d bytes'
              % (name, url[-58:], code, time.time() - t0, n))
    print('\nNine of those seconds are Akamai edge revalidation; the origin '
          'answers in 4 ms.\nThat is the floor. It is why the poll interval is '
          '%.0fs hot / %.0fs cold and not 1s.'
          % (config.HOT_INTERVAL_S, config.COLD_INTERVAL_S))
    return 0


def _run_wire(a):
    try:
        from shelnewsgateway import NewsGatewayClient, auth
    except ImportError:
        print('shelnewsgateway is not installed. See README.', file=sys.stderr)
        return 1

    env = 'prod' if a.prod else 'uat'
    token = auth.get_token(a.user) if hasattr(auth, 'get_token') else None
    # __init__ connects and logs in. Do NOT call connect() after this.
    client = NewsGatewayClient(env, a.user, token=token)

    listener = wire.MacroListener()
    wire.subscribe(client, listener, mode=a.mode)
    print('subscribed: alert=%s confirm=%s mode=%s'
          % (config.FAST_SOURCES, config.CONFIRM_SOURCES, a.mode))
    print('alert floor %.1f (%.1f inside a hot window)'
          % (config.ALERT_FLOOR, config.ALERT_FLOOR - config.HOT_FLOOR_RELIEF))
    try:
        while not listener.stop_requested:
            client.wait()
    except KeyboardInterrupt:
        listener.stop_requested = True
    print('\n%s' % listener.stats)
    return 0
