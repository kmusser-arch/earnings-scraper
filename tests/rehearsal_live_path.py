# -*- coding: utf-8 -*-
"""Dress rehearsal: a REAL wire envelope carrying a REAL release body.

★ WHY THIS IS NOT ANOTHER SYNTHETIC TEST. Every card this project has produced
came from a message I built myself, and the worst bug in the whole effort was a
fabricated "$1923.686 billion" revenue line that made a correct pipeline look
broken for two rounds. So:

  the ENVELOPE  comes from tests/fixtures/wire_messages.jsonl -- one of 317
                messages captured off the live feed, with its real id, source,
                publish_type and primary_instruments
  the BODY      comes from tests/corpus/*.txt -- the actual press release text
                for that quarter, as published

Nothing here is invented except the join, which is exactly what full mode does:
core.py pops 'body' in headlines mode and leaves it in full mode.

This exercises the path that has NEVER run end to end --
    handle -> detect -> revisions -> parse -> score -> card
-- as opposed to calling score_release directly, which is all the suite does.
"""

import io
import json
import os
import sys

sys.path.insert(0, r'c:\Users\Trader\Desktop\shelnewsapi')

from earnings_scraper import listener as listener_mod
from earnings_scraper import config, detect, revisions
from earnings_scraper.model import Model

HERE = r'c:\Users\Trader\Desktop\shelnewsapi'
CORPUS = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model\tests\corpus'
FIX = os.path.join(HERE, 'tests', 'fixtures', 'wire_messages.jsonl')

PAIRS = [('WDC-2026Q4', 'WDC'), ('SNDK-2026Q4', 'SNDK'), ('APP-2026Q2', 'APP')]


def real_envelopes():
    """Real news_item envelopes that carry primary_instruments."""
    with io.open(FIX, encoding='utf-8') as fh:
        msgs = [json.loads(l) for l in fh if l.strip()]
    return [m for m in msgs
            if m.get('msg_type') == 'news_item' and m.get('primary_instruments')
            and m.get('publish_type') == 'first-publication'
            and m.get('source') in __import__('earnings_scraper.config',fromlist=['x']).WIRE_SOURCES]


def main():
    model = Model()
    envs = real_envelopes()
    print('=== %d real first-publication envelopes with instruments ===' % len(envs))
    print('    sample: %s' % json.dumps(
        {k: v for k, v in envs[0].items() if k != 'headline'})[:150])
    print('')

    # A watchlist holding only the tickers we are rehearsing.
    wl = {}
    for rid, tkr in PAIRS:
        rec = model.record_by_id(rid)
        try:
            wl[tkr] = model.prepare_from_record(rec)
        except Exception as exc:
            print('  %s: prepare failed -- %s' % (tkr, exc))

    log = revisions.RevisionLog()
    cards = []

    class Capture(object):
        def submit(self, card):
            cards.append(card)

    # ★ Listener takes a WATCHLIST, and reads watchlist["entries"]. Passing a
    # bare {ticker: entry} dict left self.entries EMPTY, so every message was
    # reported "off-watchlist" -- a routed ticker with nowhere to land.
    lst = listener_mod.Listener(dict(entries=wl), popup=Capture(), verbose=True,
                               model=model, log_hits=False)

    for i, (rid, tkr) in enumerate(PAIRS):
        body = io.open(os.path.join(CORPUS, rid + '.txt'),
                       encoding='utf-8').read()
        env = dict(envs[i % len(envs)])
        # full mode: the envelope is untouched and the body rides along
        env['primary_instruments'] = ['EQ:US:%s' % tkr]
        env['headline'] = '%s Reports Results' % tkr
        env['body'] = body

        tickers, src = detect.extract_tickers(env, wl)
        action, note = log.classify(env)
        print('--- %s (%s) ---' % (rid, env.get('source')))
        print('    routed via %-20s -> %s' % (src, tickers))
        print('    revision   %-20s %s' % (action, (note or '')[:40]))
        print('    body       %d chars, %d lines'
              % (len(body), body.count('\n')))

        before = len(cards)
        lst.handle(env)
        got = cards[before:]
        if not got:
            print('    ⛔ NO CARD EMITTED — the silent failure')
            continue
        c = got[0]
        rows = c.get('keyKPIs') or []
        filled = sum(1 for r in rows
                     if isinstance(r.get('actual'), (int, float)))
        print('    CARD       %s %s  overall=%s  status=%s'
              % (c.get('ticker'), c.get('quarter'), c.get('overall'),
                 c.get('status')))
        print('    grid       %d rows, %d with a numeric actual (%d%%)'
              % (len(rows), filled,
                 round(100.0 * filled / len(rows)) if rows else 0))
        print('    latency    %s ms' % c.get('latencyMs'))
        for r in rows:
            if isinstance(r.get('actual'), (int, float)):
                print('       %-34s %-10s %-11s %s'
                      % (r['name'][:34], r['actual'],
                         r.get('vsBogey') or '-',
                         (r.get('extractionSource') or '')[:18]))
        print('')

    print('=== %d of %d releases produced a card ===' % (len(cards), len(PAIRS)))
    return 0 if len(cards) == len(PAIRS) else 1


if __name__ == '__main__':
    sys.exit(main())
