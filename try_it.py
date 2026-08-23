#!/usr/bin/env python3
"""
Quick manual client for exploring the News Gateway API.

Connects to staging only and subscribes to news. Prompts for your SHEL
password at most once a day and caches the resulting JWT (see
shelnewsgateway.auth), unless you pass --token yourself.

For production or the Scribe/Social feeds, use the shelnewsgateway command
line utility or the SDK directly instead -- this script is intentionally
staging + news only. --host/--port below can still point it at prod's
news-only instance if needed (e.g. --host e1tdvprdapp01.trlm.com --port
65502), it just isn't the default.

Usage examples:
    # All entitled sources, headlines mode
    python3 try_it.py -u vphan

    # Specific sources, full body
    python3 try_it.py -u vphan --sources FTI DJN --mode full

    # Arbitrary host/port, e.g. a local SDE instance or prod's news instance
    python3 try_it.py -u vphan --host 127.0.0.1 --port 59111

    # Ctrl+C to stop
"""

import argparse
import json
import signal
import sys
from datetime import datetime

from shelnewsgateway import NewsGatewayClient, auth
from shelnewsgateway.environments import Environment, Staging


def parse_args():
    p = argparse.ArgumentParser(description='News Gateway manual test client')
    p.add_argument('-u', '--user', required=True, help='SHEL username')
    p.add_argument('--token', default=None, metavar='JWT',
                   help='JWT token. Omit to reuse/fetch one automatically (prompts '
                        'for your SHEL password at most once a day).')
    p.add_argument('--sources', nargs='*', metavar='SRC',
                   help='Source codes to subscribe to (default: all entitled)')
    p.add_argument('--mode', choices=['headlines', 'full'], default='headlines')
    p.add_argument('--host', default=None,
                    help="Override SDE host (default: staging). E.g. prod's news instance: "
                         'e1tdvprdapp01.trlm.com')
    p.add_argument('--port', type=int, default=None,
                    help="Override SDE port (default: staging). E.g. prod's news instance: 65502")
    p.add_argument('--json', action='store_true', dest='as_json',
                   help='Print events as formatted JSON instead of repr')
    return p.parse_args()


def fmt_ts(ns):
    if not ns:
        return ''
    return datetime.fromtimestamp(ns / 1e9).strftime('%H:%M:%S.%f')[:-3]


def pretty(event, as_json):
    if as_json:
        print(json.dumps(event, indent=2))
        return

    t = event.get('msg_type', '?')

    if t == 'subscribed':
        sources = ', '.join(event.get('sources', []))
        warnings = event.get('warnings', [])
        print(f'[subscribed] mode={event.get("mode")} sources=[{sources}]', flush=True)
        if warnings:
            print(f'  warnings (no entitlement): {", ".join(warnings)}', flush=True)

    elif t == 'news_item':
        ts = fmt_ts(event.get('received_time'))
        src = event.get('source', '')
        headline = event.get('headline', '')
        ptype = event.get('publish_type', '')
        instruments = ', '.join(event.get('primary_instruments') or [])
        print(f'[{ts}] {src:4s} {ptype:18s} {headline}', flush=True)
        if instruments:
            print(f'       instruments: {instruments}', flush=True)
        if 'body' in event:
            body_preview = event['body'][:200].replace('\n', ' ')
            print(f'       body: {body_preview}...', flush=True)

    elif t == 'edgar_item':
        ts = fmt_ts(event.get('received_time'))
        print(f'[{ts}] EDG {event.get("form_type"):6s} {event.get("instrument")}  {event.get("url")}', flush=True)

    elif t == 'court_case':
        ts = fmt_ts(event.get('received_time'))
        print(f'[{ts}] PACER [{event.get("district")}] {event.get("case_num")}  {event.get("headline")}', flush=True)
        if 'body' in event:
            body_preview = event['body'][:200].replace('\n', ' ')
            print(f'       body: {body_preview}...', flush=True)

    else:
        print(event, flush=True)


def main():
    args = parse_args()

    if args.host or args.port:
        env = Environment(
            args.host or Staging.SHEL_DATA_ENGINE_HOST,
            args.port or Staging.SHEL_DATA_ENGINE_PORT,
        )
    else:
        env = Staging

    token = args.token if args.token is not None else auth.get_token(args.user)

    print(f'Connecting to {env.SHEL_DATA_ENGINE_HOST}:{env.SHEL_DATA_ENGINE_PORT} '
          f'as {args.user!r} ...', flush=True)

    handle = None

    def _sigint(sig, frame):
        print('\nCancelling...', flush=True)
        if handle:
            handle.cancel()

    signal.signal(signal.SIGINT, _sigint)

    with NewsGatewayClient(env, user_id=args.user, token=token) as client:
        handle = client.subscribe_news(
            lambda e: pretty(e, args.as_json),
            sources=args.sources or [],
            mode=args.mode,
        )
        handle.wait()
        try:
            handle.raise_on_error()
        except Exception as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
