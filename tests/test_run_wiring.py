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
        # ★ THE REAL CONTRACT. NewsGatewayClient.__init__ connects (journal.py:87)
        # and then calls self._login(). A constructed client is connected AND
        # authenticated; the caller must not connect again.
        self.connected_to = (env.SHEL_DATA_ENGINE_HOST,
                             env.SHEL_DATA_ENGINE_PORT)
        self.logged_in = True
        self.reconnects = 0
        self.subscribed = None
        self.waited = False
        self.wait_calls = 0
        self.delivered = 0
        self.callback = None
        self.handle = None
        self._outstanding = 0

    def connect(self, host=None, port=None):
        # ★ A SECOND CONNECT IS A NEW, ANONYMOUS SOCKET. The real client
        # forwards host/port straight to socket.connect() with no fallback (so
        # None is a TypeError), and nothing re-authenticates -- _login() runs
        # only from __init__ and from the internal reconnect path. Calling this
        # from outside therefore DISCARDS THE LOGIN.
        self.connected_to = (host, port)
        self.logged_in = False
        self.reconnects += 1

    def subscribe_news(self, callback, sources=None, mode='headlines',
                       format_id=1):
        # ★ Exactly what the gateway does on an unauthenticated connection.
        if not self.logged_in:
            raise RuntimeError('Client must be logged in before requesting '
                               'news-gateway')
        self.subscribed = dict(sources=sources, mode=mode)
        self.callback = callback
        self._outstanding = 1
        self.handle = StubHandle()
        return self.handle

    # ★ THE REAL CONTRACT. Session.wait() drains whatever is outstanding and
    # RETURNS -- normally, silently -- as soon as the count hits zero. It is
    # not a stream. A pump that calls it once reads one drain and then never
    # reads the socket again.
    def wait(self, max_count=None):
        self.waited = True
        self.wait_calls += 1
        if self.wait_calls > 3:
            # the wire goes quiet: nothing outstanding, wait() returns at once
            self._outstanding = 0
            return None
        if self.callback is not None:
            self.delivered += 1
            self.callback(dict(msg_type='news_item', source='BUS',
                               id='stub-%d' % self.wait_calls,
                               headline='Stub Co Reports Second Quarter Results'))
        return None

    def outstanding_request_count(self):
        return self._outstanding


class StubHandle(object):
    def raise_on_error(self):
        return None


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
        except RuntimeError as exc:
            # ★ The stub raises the gateway's own refusal when a subscribe is
            # attempted on an unauthenticated socket. Surfaced as a named
            # failure rather than a bare traceback so the OUTPUT states the
            # contract that was broken.
            print('FAIL %-58s %s' % ('subscribe on an unauthenticated socket',
                                     str(exc)[:34]))
            print('     cmd_run called connect() after construction, which '
                  'discards the login')
            print('     performed by __init__. This is the 2026-08-26 silence.')
            rc = 1
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
    # ★ INVERTED 2026-08-27. The old assertion -- "connect() received a real
    # host and port" -- verified the OPPOSITE of the contract. __init__ already
    # connects and logs in, so a second connect() replaces the authenticated
    # socket with an anonymous one and the following subscribe is rejected:
    # "Client must be logged in before requesting news-gateway". That was the
    # cause of the 2026-08-26 silence, and this test had blessed it.
    check('the client is connected by CONSTRUCTION', host is not None, host)
    check('    to a real host', isinstance(host, str) and len(host) > 3, host)
    check('    on a real port', str(port).isdigit(), port)
    check('connect() is NEVER called after construction',
          client.reconnects == 0, client.reconnects)
    check('    so the login survives', client.logged_in is True)

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
    print('=== --host/--port reach the CONSTRUCTOR, not a later connect() ===')
    rc, oclient = run_with_stub(Args(host='example.invalid', port=12345), good)
    check('host honoured', oclient.connected_to[0] == 'example.invalid',
          oclient.connected_to[0])
    check('port honoured', str(oclient.connected_to[1]) == '12345',
          oclient.connected_to[1])
    check('    and still no manual reconnect', oclient.reconnects == 0,
          oclient.reconnects)

    print('')
    print('=== a subscription on an unauthenticated socket is REJECTED ===')
    # Proof the stub can actually catch the regression: connect() by hand, and
    # the subscribe must fail the way the gateway failed it.
    probe = StubClient(type('E', (), dict(SHEL_DATA_ENGINE_HOST='h',
                                          SHEL_DATA_ENGINE_PORT=1))(), 'u')
    check('a constructed client is logged in', probe.logged_in is True)
    probe.connect('h', 1)
    check('    and a manual connect drops the login',
          probe.logged_in is False)
    try:
        probe.subscribe_news(lambda _i: None, sources=['BUS'], mode='full')
        check('subscribe is refused without a login', False, 'no raise')
    except RuntimeError as exc:
        check('subscribe is refused without a login', True)
        check('    with the gateway\'s own message',
              'must be logged in' in str(exc), str(exc)[:34])

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
    print('=== THE PUMP MUST LOOP — one wait() is not a stream ===')
    # ★ THE REGRESSION THAT COST FOUR PRINTS. pump_wire called client.wait()
    # once, on a daemon thread. wait() returns as soon as nothing is
    # outstanding -- normally and silently -- so the thread ended and the
    # socket was never read again while the popup showed "Waiting for
    # releases". Connected, subscribed, idle, silent.
    check('wait() was called MORE THAN ONCE', client.wait_calls > 1,
          client.wait_calls)
    check('    it kept draining until the wire went quiet',
          client.wait_calls >= 4, client.wait_calls)
    check('    and messages reached the listener on each pass',
          client.delivered >= 3, client.delivered)
    check('the pump stops when nothing is outstanding',
          client.outstanding_request_count() == 0)

    print('')
    print('=== the subscription HANDLE is kept, not discarded ===')
    # A rejected subscription is indistinguishable from a quiet wire unless
    # raise_on_error() can be consulted.
    check('subscribe returned a handle the caller retained',
          client.handle is not None)

    print('')
    print('=== subscribe() itself refuses headlines mode ===')
    try:
        # StubClient now reads the env for host/port (it connects by
        # construction, like the real client), so pass a real-shaped one.
        _e = type('E', (), dict(SHEL_DATA_ENGINE_HOST='h',
                                SHEL_DATA_ENGINE_PORT=1))()
        listener_mod.subscribe(StubClient(_e, 'u'), None, mode='headlines')
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
