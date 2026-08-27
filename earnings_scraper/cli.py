"""Command line entry point.

Typical day:

    # 1. Pull first -- the card may have been written minutes ago in Cowork.
    #    Then paste the day's names. Warms the expected column.
    py -m earnings_scraper watch

    # 2. Go live. Stays connected, pops a card the moment a release lands.
    py -m earnings_scraper run -u kmusser --prod

    # Anytime:
    py -m earnings_scraper selftest -t CSCO
    py -m earnings_scraper replay news.log
"""

import argparse
import json
import os
import sys
import threading
import time

from . import config, listener as listener_mod, watchlist as watchlist_mod
from .model import Model, NoCard, NoProfile


def _read_paste(path=None):
    if path:
        with open(path, 'r', encoding='utf-8') as fh:
            return fh.read()
    print("Paste today's earnings names (one per line, or comma separated).")
    print('Finish with Ctrl+Z then Enter on Windows.')
    print('-' * 60)
    return sys.stdin.read()


def cmd_watch(args):
    text = _read_paste(args.file)
    if not text.strip():
        print('Nothing pasted; watchlist unchanged.')
        return 1
    model = Model()
    wl = watchlist_mod.build(text, today=args.date, model=model)
    path = watchlist_mod.save(wl)
    print('')
    print(watchlist_mod.summarise(wl))
    print('')
    print('Saved to %s' % path)
    if not wl['invariantHolds']:
        print('')
        print('!! calibration.recordsUsed has DIVERGED from the pinning set.')
        print('!! Regenerate calibration.json rather than adjusting tests.')
    return 0


def cmd_show(args):
    wl = watchlist_mod.load()
    if not wl:
        print('No watchlist yet. Run: py -m earnings_scraper watch')
        return 1
    print(watchlist_mod.summarise(wl))
    return 0


def cmd_run(args):
    wl = watchlist_mod.load()
    if not wl or not wl.get('entries'):
        print('No watchlist. Run: py -m earnings_scraper watch')
        return 1
    if wl.get('today') != time.strftime('%Y-%m-%d'):
        print('!! Watchlist was built for %s, today is %s. Re-run `watch`.'
              % (wl.get('today'), time.strftime('%Y-%m-%d')))
        return 1

    from shelnewsgateway import NewsGatewayClient, auth
    from shelnewsgateway.environments import Environment, Staging, Prod
    from .popup import CardPopup

    model = Model()
    popup = None if args.no_popup else CardPopup()
    lst = listener_mod.Listener(wl, popup=popup, verbose=True, model=model)

    if args.host or args.port:
        env = Environment(args.host or Staging.SHEL_DATA_ENGINE_HOST,
                          args.port or Staging.SHEL_DATA_ENGINE_PORT)
    else:
        env = Prod if args.prod else Staging

    token = args.token or auth.get_token(args.user)
    client = NewsGatewayClient(env, args.user, token=token)

    print('Connecting to %s:%s as %s ...' % (
        env.SHEL_DATA_ENGINE_HOST, env.SHEL_DATA_ENGINE_PORT, args.user))
    # ★ HOST AND PORT MUST BE PASSED. connect(host=None, port=None) forwards
    # both to the socket unchanged -- it does NOT fall back to the environment
    # the client was constructed with -- so a bare connect() reaches
    # socket.connect((None, None)). The print above already had the values.
    client.connect(env.SHEL_DATA_ENGINE_HOST, env.SHEL_DATA_ENGINE_PORT)
    handle = listener_mod.subscribe(client, lst, mode='full')
    gradeable = [t for t, e in wl['entries'].items() if not e.get('error')]
    nocard = [t for t, e in wl['entries'].items() if e.get('error')]
    print('Subscribed to %s in full mode.' % ', '.join(config.WIRE_SOURCES))
    print('Gradeable: %s' % (', '.join(gradeable) or 'none'))
    if nocard:
        print('NO_CARD (display only): %s' % ', '.join(nocard))
    print('Waiting for releases. Ctrl+C to stop.')
    print('')

    def pump_wire():
        """Drain the wire until the subscription genuinely ends.

        ★ client.wait() RETURNS whenever nothing is outstanding, normally and
        silently -- it drains what is currently pending, it is not a stream. A
        single call read the socket once and returned; the thread then died
        while the popup mainloop kept the process alive showing "Waiting for
        releases", and no release was ever read. This is the SDK CLI's own
        loop, including its check for a subscription that ended rather than
        merely reconnected.
        """
        while not lst.stop_requested:
            try:
                client.wait()
            except KeyboardInterrupt:
                return
            except Exception as exc:
                print('')
                print('=' * 78)
                print('WIRE ERROR — %r' % (exc,))
                print('   The connection is down. No release can be scored '
                      'until this is fixed.')
                print('=' * 78)
                return
            if client.outstanding_request_count() == 0:
                # Nothing outstanding and we were not asked to stop: the
                # SUBSCRIPTION itself ended -- rejected, or closed by the
                # server. A recovered disconnect would have replayed the
                # subscribe and re-added an outstanding request.
                print('')
                print('=' * 78)
                print('SUBSCRIPTION ENDED — the wire is no longer being read.')
                try:
                    if handle is not None:
                        handle.raise_on_error()
                    print('   No error reported; the server closed it.')
                except Exception as exc:
                    print('   %r' % (exc,))
                    print('   A REJECTED subscription looks exactly like a '
                          'quiet wire from the outside.')
                print('   Nothing further will be scored. Restart the run.')
                print('=' * 78)
                return

    if popup is not None:
        threading.Thread(target=pump_wire, daemon=True).start()
        try:
            popup.run()
        except KeyboardInterrupt:
            pass
    else:
        try:
            pump_wire()
        except KeyboardInterrupt:
            pass

    # ★ Tell the pump this was a deliberate stop, so an ENDED SUBSCRIPTION
    # stays distinguishable from an operator quitting.
    lst.stop_requested = True
    print('')
    print('stats: %s' % lst.stats)
    return 0


def _iter_log(path):
    """Read a captured news.log. Handles its UTF-16LE encoding."""
    for encoding in ('utf-16', 'utf-8'):
        try:
            with open(path, 'r', encoding=encoding) as fh:
                lines = fh.readlines()
            if lines and lines[0].lstrip().startswith('{'):
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        raise SystemExit('could not decode %s as UTF-16 or UTF-8' % path)
    for line in lines:
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def cmd_replay(args):
    wl = watchlist_mod.load() or dict(entries={}, frameworks={}, today='')
    popup = None
    if args.popup:
        from .popup import CardPopup
        popup = CardPopup()
    lst = listener_mod.Listener(wl, popup=popup, verbose=not args.quiet,
                               log_hits=False, model=Model())

    def feed():
        for item in _iter_log(args.path):
            lst.handle(item)
        print('')
        print('replay stats: %s' % lst.stats)
        if lst.stats['cards'] == 0 and lst.stats['no_card'] == 0:
            print('')
            print('No cards produced. For a headlines-mode capture that is '
                  'expected -- items carry no body, so there are no figures '
                  'to grade. Re-capture with mode=full.')

    if popup is not None:
        threading.Thread(target=feed, daemon=True).start()
        popup.run()
    else:
        feed()
    return 0


DEFAULT_SELFTEST_BODY = """
Total revenue of $17.25 billion, up 18% year over year. GAAP diluted earnings
per share of $0.97; non-GAAP diluted earnings per share of $1.22. Non-GAAP gross
margin of 66.3%, down 210 basis points year over year. Product gross margin of
64.8%. Non-GAAP operating margin of 35.9%.

For the first quarter of fiscal 2027, the company expects revenue of
$18.1 billion to $18.3 billion. For full year fiscal 2027, the company expects
revenue of $76.5 billion to $77.5 billion.

Condensed consolidated statements of operations follow.
"""


def cmd_selftest(args):
    """Grade a synthetic release against a real card. No wire needed."""
    from . import parse as parse_mod, score as score_mod
    from .popup import CardPopup

    model = Model()
    ticker = args.ticker.upper()

    if args.record:
        rec = model.record_by_id(args.record)
        if rec is None:
            print('no record %s' % args.record)
            return 1
    else:
        rec = model.latest_record(ticker)
        if rec is None:
            print('%s: NO_CARD — no record in the library. The scraper would '
                  'extract, display and grade NOTHING.' % ticker)
            return 1

    try:
        entry = model.prepare_from_record(rec)
    except NoProfile as exc:
        print('%s: NO_PROFILE — %s. Refusing to grade.' % (ticker, exc))
        return 1

    body = args.body
    if args.body_file:
        with open(args.body_file, 'r', encoding='utf-8') as fh:
            body = fh.read()

    item = dict(msg_type='news_item', source='BUS', id='selftest',
                headline='%s Reports %s Results' % (ticker, entry['quarter']),
                body=body)
    parsed = parse_mod.parse_release(item)

    t0 = time.perf_counter()
    card = score_mod.score_release(parsed, entry, model)
    elapsed = (time.perf_counter() - t0) * 1000
    card.update(wire='SELFTEST', headline=item['headline'],
                receivedAt=time.strftime('%H:%M:%S'), latencyMs=round(elapsed, 2),
                parsedFields=parsed['fields'])

    s = card['scores']
    print('')
    print('%s  %s   record=%s' % (ticker, entry['quarter'], rec['id']))
    print('  hero KPI            %s' % (card.get('heroName') or 'NONE'))
    print('  resolved to         %s' % (card.get('heroKpiName') or '-'))
    cq = card['currentQuarterDetail']
    print('  clearance           %s vs %s' % (
        ('%+.2f%%' % cq['clearance']) if cq.get('clearance') is not None else '--',
        cq.get('clearanceVs')))
    print('  base band           %s   flags %d   step-down -%.1f' % (
        cq.get('base'), cq.get('flags') or 0, cq.get('stepDownApplied') or 0))
    print('')
    print('  1. Current Quarter  %s' % _fs(s['currentQuarter']))
    print('  2. Next-Q Guidance  %s' % _fs(s['nextQGuidance']))
    print('  3. FY Guidance      %s' % _fs(s['fyGuidance']))
    print('  4. Narrative        --    (%s)' % card['narrativeReason'])
    print('  OVERALL             %s' % ('--    deferred'
                                        if card['overall'] is None
                                        else card['overall']))
    print('  status              %s' % card['status'])
    print('  keyKPI alignment    %d pre / %d actual' % (
        len(entry['keyKPIs']), len(card['keyKPIs'])))
    print('  scoring time        %.2f ms' % elapsed)
    print('  reason              %s' % (cq.get('reason') or '-'))
    for e in card.get('flagEvidence') or []:
        print('    flag: %s' % e)

    if args.expect_cq is not None:
        got = s['currentQuarter']
        ok = got == args.expect_cq
        print('')
        print('  EXPECT currentQuarter %+.1f -> got %s : %s' % (
            args.expect_cq, _fs(got), 'PASS' if ok else 'FAIL'))
        if not args.popup:
            return 0 if ok else 1

    if args.popup:
        popup = CardPopup()
        popup.submit(card)
        print('')
        print('Rendering the card. Close the window to exit.')
        popup.run()
    return 0


def _fs(v):
    return '--' if v is None else '%+.1f' % v


def cmd_audit(args):
    """HARD 10 across the live library."""
    from . import plausibility
    model = Model()
    findings, summary = plausibility.audit(model)
    print(plausibility.format_report(findings, summary))
    return 1 if findings else 0


def cmd_extract(args):
    """Run the scraper on a raw corpus release and dump the record as JSON.

    This is the input side of replay_test.py. The byte-identity test proves both
    paths call the same renderer; THIS answers the question that matters -- does
    the scraper BUILD the same record from raw press-release text that the hand
    path built?

    The card's expected column (consensus / bogey / keyKPI order) is read from
    the library exactly as it is at runtime. Only the ACTUALS come from the
    corpus text, which is the half under test.
    """
    import json as _json
    from . import parse as parse_mod, score as score_mod

    model = Model()
    text = open(args.path, 'r', encoding='utf-8').read()
    rid = args.record or os.path.splitext(os.path.basename(args.path))[0]

    rec = model.record_by_id(rid)
    if rec is None:
        print('no library record %s — cannot resolve the expected column' % rid)
        return 1
    try:
        entry = model.prepare_from_record(rec)
    except NoProfile as exc:
        print('%s: NO_PROFILE — %s' % (rid, exc))
        return 1

    lines = text.splitlines()
    item = dict(msg_type='news_item', source='BUS', id=rid,
                headline=(lines[0] if lines else ''), body=text)
    parsed = parse_mod.parse_release(item)
    card = score_mod.score_release(parsed, entry, model)

    rows = []
    for i, row in enumerate(card.get('keyKPIs') or []):
        rows.append(dict(index=i, name=row.get('name'),
                         consensus=row.get('consensus'),
                         bogey=row.get('bogey'), actual=row.get('actual'),
                         actualUnit=row.get('actualUnit'),
                         vsBogey=row.get('vsBogey'),
                         # ★ Where the number CAME FROM. A row can match the
                         # golden value and still be untrustworthy if it was
                         # inherited rather than read, so the provenance is part
                         # of the dump, not a debug aside.
                         extractionSource=row.get('extractionSource'),
                         unverified=bool(row.get('unverified'))))

    out = dict(
        id=rid, ticker=card.get('ticker'), quarter=card.get('quarter'),
        corpusFile=args.path, corpusChars=len(text),
        scores=dict(card.get('scores') or {}),
        band=(card.get('gate') or {}).get('band'),
        keyKPIs=rows,
        forwardCommitment=((entry.get('forwardCommitment') or {})
                           .get('novelty')),
        asymmetricEventFlagPresent=bool(entry.get('asymmetricEventFlag')),
        parsedFields=parsed.get('fields'),
        # ★ The fields that decide whether a score is DISPLAYED at all. Without
        # them a replay dump shows a number the live card would never have
        # shown -- WDC's nextQ reads +1.0 in the scores dict and carries a fade
        # -zone flag on the card, and the JSON hid the flag.
        currentQuarterIsCeiling=card.get('currentQuarterIsCeiling'),
        currentQuarterCeilingNote=card.get('currentQuarterCeilingNote'),
        nextQFadeZone=card.get('nextQFadeZone'),
        nextQInline=card.get('nextQInline'),
        deferred=card.get('deferred') or [],
        problems=card.get('problems') or [],
        notes='Produced by the scraper from the corpus text. Expected column '
              'read from the library at runtime; only the actuals are '
              'extracted.',
    )
    dest = args.out or (rid + '.scraper.json')
    with open(dest, 'w', encoding='utf-8') as fh:
        _json.dump(out, fh, ensure_ascii=False, indent=1)
    print('wrote %s  (%d rows, %d parsed field groups)'
          % (dest, len(rows), parsed.get('fields') or 0))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog='earnings_scraper',
        description='Scrape press-wire earnings releases and run them through '
                    'the earnings model.')
    sub = p.add_subparsers(dest='cmd', required=True)

    w = sub.add_parser('watch', help="paste today's names and warm the model")
    w.add_argument('-f', '--file', help='read the paste from a file instead')
    w.add_argument('--date', default=None,
                   help='index cards for this reportDate (default: today)')
    w.set_defaults(func=cmd_watch)

    s = sub.add_parser('show', help='show the current watchlist')
    s.set_defaults(func=cmd_show)

    r = sub.add_parser('run', help='go live on the wires')
    r.add_argument('-u', '--user', required=True, help='SHEL username')
    r.add_argument('--token', default=None, help='JWT; omit to fetch/reuse')
    r.add_argument('--prod', action='store_true',
                   help='use the production news instance instead of staging')
    r.add_argument('--host', default=None)
    r.add_argument('--port', type=int, default=None)
    r.add_argument('--no-popup', action='store_true', help='terminal only')
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser('replay', help='replay a captured news.log')
    rp.add_argument('path')
    rp.add_argument('--popup', action='store_true')
    rp.add_argument('--quiet', action='store_true')
    rp.set_defaults(func=cmd_replay)

    ex = sub.add_parser('extract',
                        help='run the scraper on a raw release and dump JSON '
                             'for replay_test.py')
    ex.add_argument('path', help='corpus .txt file')
    ex.add_argument('--record', default=None,
                    help='library record id (default: the filename stem)')
    ex.add_argument('-o', '--out', default=None)
    ex.set_defaults(func=cmd_extract)

    au = sub.add_parser('audit',
                        help='HARD 10 — domain-implausible expected values')
    au.set_defaults(func=cmd_audit)

    st = sub.add_parser('selftest',
                        help='grade a synthetic release against a real card')
    st.add_argument('-t', '--ticker', default='CSCO')
    st.add_argument('--record', default=None, help='pin an exact record id')
    st.add_argument('--body', default=DEFAULT_SELFTEST_BODY)
    st.add_argument('--body-file', default=None)
    st.add_argument('--popup', action='store_true', help='also render the card')
    st.add_argument('--expect-cq', type=float, default=None,
                    help='assert currentQuarter equals this')
    st.set_defaults(func=cmd_selftest)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    os.makedirs(config.STATE_DIR, exist_ok=True)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
