"""Routing and dedup, against REAL captured wire messages.

317 messages extracted from a live capture -- not synthesised. Every harness bug
in this project came from a synthesised message asserting a shape the wire does
not guarantee, the worst being a fabricated "$1923.686 billion" revenue line
that made a correct pipeline look broken for two rounds.

The sample is stratified because the revision classes are rare: 47 `update` and
217 `minor-update` out of 21,660 news_items, so a first-N sample would contain
none of them and the dedup path would be untested.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import detect, revisions                # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:36]))
    if not ok:
        FAIL[0] += 1


def load():
    with io.open(os.path.join(FIX, 'wire_messages.jsonl'),
                 encoding='utf-8') as fh:
        return [json.loads(l) for l in fh if l.strip()]


def main():
    msgs = load()
    news = [m for m in msgs if m.get('msg_type') == 'news_item']

    print('=== the fixtures are real and cover every shape ===')
    check('317 messages committed', len(msgs) == 317, len(msgs))
    types = {m.get('msg_type') for m in msgs}
    check('news_item, edgar_item and court_case all present',
          {'news_item', 'edgar_item', 'court_case'} <= types, sorted(types))
    ptypes = {m.get('publish_type') for m in news}
    check('all three publish_type classes present',
          {'first-publication', 'minor-update', 'update'} <= ptypes,
          sorted(x for x in ptypes if x))
    check('every one of the 47 update messages is kept',
          sum(1 for m in news if m.get('publish_type') == 'update') == 47,
          sum(1 for m in news if m.get('publish_type') == 'update'))

    print('')
    print('=== headlines mode carries no body on a NEWS item ===')
    for field in ('body', 'text', 'story', 'url', 'link', 'href'):
        check('no %-6s field on any news_item' % field,
              not any(m.get(field) for m in news))

    print('')
    print('=== but an EDGAR item DOES carry a fetchable url ===')
    # ★ The asymmetry that matters. There is no fetch-by-id for a press wire --
    # no url, no API -- so mode='full' is the only way to get a release body.
    # An edgar_item is different: every one carries a direct SEC filing URL, a
    # form_type and a single `instrument`. 320 of the 15,291 captured filings
    # are 8-K, which is the earnings vehicle, so for that source class a
    # second fetch IS available: stream the filing, match the instrument, pull
    # only that one document.
    edgar = [m for m in msgs if m.get('msg_type') == 'edgar_item']
    check('every edgar_item carries a url',
          bool(edgar) and all(m.get('url') for m in edgar), len(edgar))
    check('and a form_type', all(m.get('form_type') for m in edgar))
    check('and a single instrument, not primary_instruments',
          all(m.get('instrument') for m in edgar)
          and not any(m.get('primary_instruments') for m in edgar))
    check('the urls point at sec.gov',
          all('sec.gov' in (m.get('url') or '') for m in edgar))

    print('')
    print('=== primary_instruments is the routing key ===')
    withi = [m for m in news if m.get('primary_instruments')]
    check('about half carry instruments', 100 <= len(withi) <= 200, len(withi))
    unparsed = [m['primary_instruments'] for m in withi
                if not revisions.tickers_from_instruments(m)]
    check('every instrument string parses', unparsed == [], unparsed[:2])
    sample = {m['primary_instruments'][0]:
              revisions.tickers_from_instruments(m)[0] for m in withi}
    check('EQ:US:DIS resolves to DIS', sample.get('EQ:US:DIS') == 'DIS')
    check('the venue prefix is never kept',
          not any(':' in t for ts in
                  (revisions.tickers_from_instruments(m) for m in withi)
                  for t in ts))

    print('')
    print('=== detect agrees, and prefers the structured field ===')
    agree = 0
    for m in withi[:40]:
        want = set(revisions.tickers_from_instruments(m))
        got, src = detect.extract_tickers(m, {t: {} for t in want})
        if set(got) == want and src == 'primary_instruments':
            agree += 1
    check('detect routes off primary_instruments', agree == 40, agree)

    print('')
    print('=== the revision ledger, replayed over the capture ===')
    log = revisions.RevisionLog()
    acts = {}
    for m in news:
        a, _n = log.classify(m)
        acts[a] = acts.get(a, 0) + 1
    check('most messages score', acts.get('score', 0) > 200, acts)
    check('revisions of a seen story are suppressed',
          acts.get('suppress-quiet', 0) + acts.get('suppress-loud', 0) > 0,
          acts)
    s = log.summary()
    check('the summary counts material updates separately',
          s['materialUpdates'] > 0, s)

    print('')
    print('=== the three classes behave differently ===')
    log2 = revisions.RevisionLog()
    sid = 'story-1'
    a1, _ = log2.classify(dict(id=sid, publish_type='first-publication'))
    check('first-publication scores', a1 == 'score', a1)
    a2, n2 = log2.classify(dict(id=sid, publish_type='minor-update'))
    check('minor-update is suppressed QUIETLY', a2 == 'suppress-quiet', a2)
    check('    with a one-line note', bool(n2) and 'no new card' in n2)
    a3, n3 = log2.classify(dict(id=sid, publish_type='update'))
    check('update is suppressed LOUDLY', a3 == 'suppress-loud', a3)
    check('    and says the revision is itself a trade',
          bool(n3) and 'ITSELF a trade' in n3, (n3 or '')[:36])
    check('    and it names what to do',
          bool(n3) and 'compare it against' in n3)

    print('')
    print('=== a revision with no prior sighting is NOT suppressed ===')
    log3 = revisions.RevisionLog()
    a4, n4 = log3.classify(dict(id='never-seen', publish_type='update'))
    check('it scores, as the first sighting', a4 == 'score', a4)
    check('    and says why', bool(n4) and 'without the original' in n4)

    print('')
    print('=== a message with no id cannot be deduped, so it scores ===')
    log4 = revisions.RevisionLog()
    a5, n5 = log4.classify(dict(publish_type='update', headline='x'))
    check('no id -> score', a5 == 'score', a5)
    check('    and the note is explicit',
          bool(n5) and 'cannot dedup' in n5)

    print('')
    print('=== related_instruments is never the routing key ===')
    rel = [m for m in news if m.get('related_instruments')]
    check('some messages carry related instruments', len(rel) > 0, len(rel))
    check('related tickers parse but are reported separately',
          all(isinstance(revisions.related_tickers(m), list) for m in rel))

    print('')
    print('=== the handshake fixture lists the entitled sources ===')
    with io.open(os.path.join(FIX, 'subscribed.json'), encoding='utf-8') as fh:
        sub = json.load(fh)
    check('39 sources', len(sub.get('sources') or []) == 39,
          len(sub.get('sources') or []))
    wires = {'PRN', 'BUS', 'NFI', 'ASW', 'PZM'}
    check('the five wire sources are all entitled',
          wires <= set(sub['sources']),
          sorted(wires - set(sub['sources'])) or 'all present')
    check('the capture was in headlines mode',
          sub.get('mode') == 'headlines', sub.get('mode'))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
