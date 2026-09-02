"""Replay a wire capture through the filter and report what survives.

This is the acceptance test for the whole package. It is not "does the code
run" -- it is "on the day we missed the trade, would this have alerted, how
early, and how much would it have interrupted us for nothing".

    py -m treasury_scraper replay news.log

news.log is UTF-16LE. Reading it as UTF-8 or cp1252 returns ZERO parseable
messages and looks like an empty file, which is how 39 MB of evidence sat in
this repo unexamined.
"""

import collections
import datetime
import io
import json

from . import config, noise, state

UTC = datetime.timezone.utc


def _open(path):
    """UTF-16LE with a BOM. Fall back to UTF-8 for the committed fixtures."""
    with open(path, 'rb') as fh:
        head = fh.read(2)
    enc = 'utf-16' if head == b'\xff\xfe' else 'utf-8'
    return io.open(path, 'r', encoding=enc, errors='replace')


def load(path):
    rows = []
    with _open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get('msg_type') == 'news_item':
                rows.append(obj)
    rows.sort(key=lambda r: r.get('first_published_time') or 0)
    return rows


def et(ns):
    d = datetime.datetime.fromtimestamp(ns / 1e9, UTC) - datetime.timedelta(hours=4)
    return d.strftime('%Y-%m-%d %H:%M:%S')


def run(path, verbose=True):
    rows = load(path)
    ledger = state.Ledger()
    seen = state.SeenCache()
    drops = collections.Counter()
    alerts, logs, confirms, enrich = [], [], [], []

    for r in rows:
        ns = r.get('first_published_time') or 0
        now = ns / 1e9
        hot = _hot_at(ns)
        v = noise.classify(r, ledger=ledger, seen=seen, now=now, hot=hot)
        if v.action == 'ALERT':
            alerts.append((ns, r, v))
        elif v.action == 'LOG':
            logs.append((ns, r, v))
        elif v.action == 'CONFIRM':
            confirms.append((ns, r, v))
        elif v.action == 'ENRICH':
            enrich.append((ns, r, v))
            alerts.append((ns, r, v))          # shown inline under its story
        else:
            drops[(v.drop_reason or '?').split(' ')[0]] += 1

    total = len(rows)
    print('REPLAY  %s' % path)
    print('=' * 78)
    print('messages parsed          %6d' % total)
    print('-' * 78)
    for layer, n in sorted(drops.items()):
        print('  dropped at %-12s  %6d   %5.1f%%' % (layer, n, 100.0 * n / total))
    print('-' * 78)
    print('  CONFIRM (dup, 2nd src) %6d' % len(confirms))
    print('  ENRICH  (attached fig) %6d' % len(enrich))
    print('  LOG     (scored, low)  %6d' % len(logs))
    print('  ALERT   (popup)        %6d   %5.2f%% of the wire'
          % (len(alerts), 100.0 * len(alerts) / total))
    print('=' * 78)

    if verbose and alerts:
        print('\nALERTS RAISED')
        print('-' * 78)
        for ns, r, v in alerts:
            tag = '+' if v.action == 'ENRICH' else ' '
            print('%s %s%-4s %5.1f  %s' % (
                et(ns), tag, r.get('source'), v.score,
                (r.get('headline') or '')[:74]))
            if v.reasons:
                print('%s  %s' % (' ' * 21, ' '.join(v.reasons)))
    return dict(total=total, alerts=alerts, logs=logs,
                confirms=confirms, enrich=enrich, drops=drops)


def _hot_at(ns):
    d = datetime.datetime.fromtimestamp(ns / 1e9, UTC) - datetime.timedelta(hours=4)
    return state.is_hot(d)
