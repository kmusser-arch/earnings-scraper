# -*- coding: utf-8 -*-
"""cmd_run's connection wiring, with a stub client instead of a live wire.

★ WHY THIS FILE EXISTS. cmd_run had NEVER executed. 1017 assertions, the
three-record corpus and the live-path rehearsal all enter at Listener.handle()
or below, so the handful of lines that build a client, open a socket and
subscribe had no coverage of any kind -- and one of them was wrong:

    client.connect()          # host=None, port=None -> socket.connect((None, None))

It died with "TypeError: str, bytes or bytearray expected, not NoneType" on the
first real run, one line after PRINTING the correct host and port. The values
were in hand and never passed.

★ THE EXCUSE THIS FILE REFUTES: "the connection path needs a live wire to
test." It does not. It needs a stub that records what it was called with. Every
assertion here would have caught the bug, and none of them touch the network.

What is checked:
  * connect() receives a real host and a real port, never None
  * subscribe_news() is called with mode='full' and the five wire sources
  * --prod and the default select DIFFERENT endpoints
  * a stale watchlist refuses BEFORE any network call is attempted
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cli, config                     # noqa: E402
from earnings_scraper import listener as listener_mod        # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:34]))
    if not ok:
        FAIL[0] += 1


class StubClient(object):
    """Records what cmd_run does to it. Touches no socket."""

    def __init__(self, env, user, token=None, **kw):
        self.env, self.user, self.token = env, user, token
        self.connected_to = None
        self.subscribed = None
        self.waited = False

    def connect(self, host=None, port=None):
        # The real client forwards these straight to socket.connect((host,
        # port)) with no fallback, so None here IS the bug.
        self.connected_to = (host, port)

    def subscribe_news(self, callback, sources=None, mode='headlines',
                       format_id=1):
        self.subscribed = dict(sources=sources, mode=mode)
        return object()

    def wait(self):
        self.waited = True


class Args(object):
    def __init__(self, **kw):
        self.user = 'tester'
        self.token = 'stub-token'
        self.prod = False
        self.host = None
        self.port = None
        self.no_popup = True
        self.__dict__.update(kw)


def run_with_stub(args, watchlist):
    """Call cmd_run with the SDK and the popup stubbed out."""
    import earnings_scraper.cli as C
    import shelnewsgateway
    from earnings_scraper import watchlist as W

    made = {}

    def factory(env, user, token=None, **kw):
        made['client'] = StubClient(env, user, token=token, **kw)
        return made['client']

    real_client = shelnewsgateway.NewsGatewayClient
    real_load = W.load
    real_sleep = time.sleep
    shelnewsgateway.NewsGatewayClient = factory
    W.load = lambda *a, **k: watchlist
    C.watchlist_mod.load = W.load
    time.sleep = lambda *_a: (_ for _ in ()).throw(KeyboardInterrupt())
    try:
        try:
            rc = C.cmd_run(args)
        except KeyboardInterrupt:
            rc = 0
    finally:
        shelnewsgateway.NewsGatewayClient = real_client
        W.load = real_load
        C.watchlist_mod.load = real_load
        time.sleep = real_sleep
    return rc, made.get('client')


def main():
    today = time.strftime('%Y-%m-%d')
    good = dict(today=today, entries={'WDC': dict(ticker='WDC')})

    print('=== a STALE watchlist refuses before any network call ===')
    stale = dict(today='2020-01-01', entries={'WDC': dict(ticker='WDC')})
    rc, client = run_with_stub(Args(), stale)
    check('returns non-zero', rc == 1, rc)
    check('and never built a client', client is None, client)

    print('')
    print('=== an EMPTY watchlist refuses too ===')
    rc, client = run_with_stub(Args(), dict(today=today, entries={}))
    check('returns non-zero', rc == 1, rc)
    check('and never built a client', client is None, client)

    print('')
    print('=== connect() gets a REAL host and port, never None ===')
    rc, client = run_with_stub(Args(), good)
    check('a client was built', client is not None)
    if client is None:
        print('%d failure(s)' % FAIL[0])
        return 1
    host, port = client.connected_to or (None, None)
    check('connect() was called', client.connected_to is not None)
    # ★ THE REGRESSION. A bare connect() passed (None, None) here.
    check('host is not None', host is not None, host)
    check('port is not None', port is not None, port)
    check('host is a non-empty string', isinstance(host, str) and len(host) > 3,
          host)
    check('port is an int-ish value', str(port).isdigit(), port)

    print('')
    print('=== and it is the endpoint that was PRINTED ===')
    from shelnewsgateway.environments import Staging
    check('default env is Staging', host == Staging.SHEL_DATA_ENGINE_HOST,
          host)
    check('    with Staging\'s port',
          str(port) == str(Staging.SHEL_DATA_ENGINE_PORT), port)

    print('')
    print('=== --prod selects a DIFFERENT endpoint ===')
    rc, pclient = run_with_stub(Args(prod=True), good)
    phost, pport = pclient.connected_to
    from shelnewsgateway.environments import Prod
    check('prod host is Prod\'s', phost == Prod.SHEL_DATA_ENGINE_HOST, phost)
    check('and differs from staging', phost != host, phost)
    check('prod host is not None', phost is not None)

    print('')
    print('=== --host/--port override both ===')
    rc, oclient = run_with_stub(Args(host='example.invalid', port=12345), good)
    check('host honoured', oclient.connected_to[0] == 'example.invalid',
          oclient.connected_to[0])
    check('port honoured', str(oclient.connected_to[1]) == '12345',
          oclient.connected_to[1])

    print('')
    print('=== the subscription is FULL mode on the five wires ===')
    sub = client.subscribed or {}
    check('subscribe_news was called', bool(sub))
    check('mode is full — never headlines', sub.get('mode') == 'full',
          sub.get('mode'))
    check('sources are exactly the five wires',
          sorted(sub.get('sources') or []) == sorted(config.WIRE_SOURCES),
          sorted(sub.get('sources') or []))
    check('    which is ASW, BUS, NFI, PRN, PZM',
          sorted(config.WIRE_SOURCES) == ['ASW', 'BUS', 'NFI', 'PRN', 'PZM'])

    print('')
    print('=== subscribe() itself refuses headlines mode ===')
    try:
        listener_mod.subscribe(StubClient(None, 'u'), None, mode='headlines')
        check('raises on headlines mode', False, 'no raise')
    except ValueError as exc:
        check('raises on headlines mode', True)
        check('    and says why', 'carries no body' in str(exc),
              str(exc)[:34])

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
