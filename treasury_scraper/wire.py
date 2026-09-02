"""The wire listener -- the PRIMARY path.

Sub-second. On the founding case the gateway delivered the first Hammerstone
headline with a 2.2 second lag (first_published 08:36:18.000, received
08:36:20.209) and the operative number 2m22s later. treasury.gov cannot be
read in under eight seconds per request. This is the path that gets the trade.
"""

import time

from . import config, noise, state


class MacroListener:
    def __init__(self, on_alert=None, ledger=None, seen=None, verbose=True):
        self.on_alert = on_alert
        self.ledger = ledger or state.Ledger()
        self.seen = seen if seen is not None else state.SeenCache()
        self.verbose = verbose
        self.started_at = time.time()
        self.first_frame_at = None
        self.stop_requested = False
        self.stats = dict(items=0, alerts=0, logs=0, confirms=0, dropped=0)

    def on_frame(self, item):
        """Called on the SDK reader thread. Does no I/O and no drawing."""
        if item.get('msg_type') != 'news_item':
            return
        if self.first_frame_at is None:
            self.first_frame_at = time.time()
        self.stats['items'] += 1

        v = noise.classify(item, ledger=self.ledger, seen=self.seen,
                           hot=state.is_hot())

        if v.action == 'ALERT':
            self.stats['alerts'] += 1
            self._emit(item, v)
        elif v.action == 'LOG':
            self.stats['logs'] += 1
            if self.verbose:
                print('  [log %.1f] %-4s %s' % (
                    v.score, item.get('source'), (item.get('headline') or '')[:70]))
        elif v.action == 'CONFIRM':
            self.stats['confirms'] += 1
            if self.verbose:
                print('  [confirm] %-4s %s' % (
                    item.get('source'), (item.get('headline') or '')[:70]))
        else:
            self.stats['dropped'] += 1

    def _emit(self, item, v):
        lag = (item.get('received_time', 0) - item.get('first_published_time', 0)) / 1e6
        line = (
            '\a\n'
            '================ MACRO ALERT  %.1f/%.1f ================\n'
            '%s  [%s]  wire lag %.0f ms\n'
            '%s\n'
            'why: %s\n'
        ) % (v.score, v.floor,
             time.strftime('%H:%M:%S'), item.get('source'), lag,
             item.get('headline'), ' '.join(v.reasons))
        if v.amounts:
            line += 'figures: %s\n' % ', '.join(
                '$%.3gB' % (a / 1e9) for a in v.amounts)
        line += '=' * 56
        print(line)
        if self.on_alert:
            self.on_alert(item, v)


def subscribe(client, listener, sources=None, mode=None):
    """Attach to the gateway.

    NOTE: NewsGatewayClient.__init__ ALREADY connects and logs in. Calling
    connect() again discards the login and the next subscribe is rejected with
    "Client must be logged in before requesting news-gateway". That regression
    cost a night on the earnings side -- do not reintroduce it here.
    """
    return client.subscribe_news(
        listener.on_frame,
        sources=sources or config.SUBSCRIBE_SOURCES,
        mode=mode or config.DEFAULT_MODE,
    )
