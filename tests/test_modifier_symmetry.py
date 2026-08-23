"""Forward-looking language is a modifier the row must also carry.

★ NON-NEGOTIABLE 2 IN MIRROR IMAGE. That rule forbids populating a FORWARD slot
from reported actuals, and only that direction was ever written down. The
reverse -- a CURRENT-quarter row absorbing a guidance sentence -- is the
dominant form of the reverse-match collision: `guide` is the single restricting
token in roughly half of them.

Period scoping catches this only when the release NAMES the quarter. When the
sentence says merely "is expected to be" or "we see", the forward-looking VERB
is the only signal, and a row whose name lacks `guide` has no token to fail on.

The collision pairs are DERIVED here rather than read from a stored list, and
deliberately without stripping the metric word. Stripping `revenue` as noise
gives plain revenue rows an EMPTY core set, and the empty set is a subset of
everything -- which is how a real 75 was first measured as 256. A measurement
whose preprocessing manufactures the pattern it reports is worthless in the same
way an assertion that asserts nothing is.
"""

import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse as P                       # noqa: E402
from earnings_scraper import score as S                       # noqa: E402
from earnings_scraper.model import Model                      # noqa: E402

FAIL = [0]

_PERIOD = re.compile(r'^(?:f?[1-4]q\d*|q[1-4]|fy\d*|f\dq)$', re.I)
_NOISE = {'the', 'and', 'of', 'vs', 'non', 'gaap', 'adj', 'adjusted', 'mid',
          'midpoint', 'street', 'bogey', 'cons', 'consensus', 'per', 'share',
          'diluted', 'basic'}
_METRIC = re.compile(r'revenue|sales|ebitda|margin|income|eps|earnings|arr|rpo'
                     r'|capex|opex|fcf|cash|backlog|orders|units|subs', re.I)


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:32]))
    if not ok:
        FAIL[0] += 1


def core(name):
    base = re.sub(r'\([^)]*\)|★|☆|🔥|#\d+', ' ', name or '')
    toks = {t for t in re.findall(r'[a-z]{2,}', base.lower())}
    return {t for t in toks if t not in _NOISE and not _PERIOD.match(t)}


def collisions(model):
    """Pairs where core(a) is a STRICT SUBSET of core(b), same metric family."""
    out = []
    for rec in model.records:
        rows = [(k.get('name') or '')
                for k in ((rec.get('preEarnings') or {}).get('keyKPIs') or [])]
        for i, a in enumerate(rows):
            for j, b in enumerate(rows):
                if i == j:
                    continue
                ca, cb = core(a), core(b)
                if not ca or not cb or ca == cb or not ca < cb:
                    continue
                ma = {t for t in ca if _METRIC.match(t)}
                mb = {t for t in cb if _METRIC.match(t)}
                if not ma or not (ma & mb):
                    continue
                out.append((rec['id'], a, b, tuple(sorted(cb - ca))))
    return out


# every forward phrasing seen or plausible on a wire
FORWARD = (
    '%s is expected to be approximately $8.7 billion.',
    'We expect %s of $8.7 billion.',
    '%s of $8.7 billion is expected.',
    'The company anticipates %s of $8.7 billion.',
    'We see %s of $8.7 billion.',
    'For the next quarter, %s is expected to be $8.7 billion.',
    '%s is targeted at $8.7 billion.',
    'Guidance calls for %s of $8.7 billion.',
)

PCT_FORWARD = (
    '%s is expected to be approximately 55.5%%.',
    'We expect %s of 55.5%%.',
    'The company anticipates %s of 55.5%%.',
)


def main():
    model = Model()

    print('=== the collision corpus, derived not stored ===')
    pairs = collisions(model)
    check('collision pairs found', len(pairs) > 50, len(pairs))
    mods = Counter(t for _r, _a, _b, extra in pairs for t in extra)
    guide = [p for p in pairs if 'guide' in p[3]]
    check('`guide` is the single most common restricting token',
          mods.most_common(1)[0][0] == 'guide', mods.most_common(3))
    check('and it accounts for roughly half the pairs',
          0.35 <= len(guide) / float(len(pairs)) <= 0.65,
          '%d of %d' % (len(guide), len(pairs)))
    check('the metric word is NOT stripped (no empty core sets)',
          all(core(a) for _r, a, _b, _e in pairs))

    print('')
    print('=== no dollar metric absorbs a forward-looking sentence ===')
    for metric, fn in (('revenue', lambda t: (P.parse_revenue(t) or {})
                        .get('value_musd')),
                       ('operating income',
                        lambda t: {k: v['value_musd'] for k, v
                                   in P.parse_op_income(t).items()} or None),
                       ('adjusted EBITDA',
                        lambda t: {k: v['value_musd'] for k, v
                                   in P.parse_adj_ebitda(t).items()} or None),
                       ('non-GAAP EPS',
                        lambda t: {k: v['value'] for k, v
                                   in P.parse_eps(t).items()} or None)):
        absorbed = [tpl % metric for tpl in FORWARD if fn(tpl % metric)]
        check('%-18s refuses all %d phrasings' % (metric, len(FORWARD)),
              absorbed == [], absorbed[:1])

    print('')
    print('=== nor does a margin ===')
    absorbed = [t % 'non-GAAP gross margin' for t in PCT_FORWARD
                if P.parse_margins(t % 'non-GAAP gross margin')]
    check('gross margin refuses all %d phrasings' % len(PCT_FORWARD),
          absorbed == [], absorbed[:1])

    print('')
    print('=== a REPORTED sentence is still read ===')
    for text, want in (
            ('Total revenue was $850.5 million.', 850.5),
            ('Revenue of $8.7 billion.', 8700.0),
            ('First quarter revenue increased 17% to $181.5 billion.',
             181500.0)):
        check('%-46s -> %s' % (text[:46], want),
              (P.parse_revenue(text) or {}).get('value_musd') == want,
              (P.parse_revenue(text) or {}).get('value_musd'))
    check('reported margin still read',
          P.parse_margins('Non-GAAP gross margin of 88.0%.')
          .get('grossMargin', {}).get('value') == 88.0)
    check('reported EPS still read',
          P.parse_eps('Non-GAAP diluted earnings per share of $1.08.')
          .get('non-GAAP', {}).get('value') == 1.08)

    print('')
    print('=== end to end: a guidance-only release fills NO current row ===')
    # ★ The real test. Take records that actually carry a guide collision and
    # feed a release containing ONLY forward-looking language.
    ids = []
    for rid, _a, _b, extra in guide:
        if 'guide' in extra and rid not in ids:
            ids.append(rid)
    tested = leaked = 0
    for rid in ids[:14]:
        rec = model.record_by_id(rid)
        try:
            entry = model.prepare_from_record(rec)
        except Exception:
            continue
        body = ('%s Reports Results\n\n'
                'For the next quarter, revenue is expected to be '
                'approximately $8.7 billion, with non-GAAP gross margin of '
                '55.5%% and non-GAAP EPS of $1.22.\n'
                % (rec.get('company') or rid))
        card = S.score_release(P.parse_release(dict(
            msg_type='news_item', source='BUS', id=rid,
            headline='%s Reports Results' % rid, body=body)), entry, model)
        tested += 1
        for row in card['keyKPIs']:
            if row.get('period') != 'CURRENT_Q':
                continue
            if isinstance(row.get('actual'), (int, float)):
                leaked += 1
                if leaked <= 3:
                    print('      LEAK %-13s %-30s = %s'
                          % (rid, row['name'][:30], row['actual']))
    check('%d records tested with a guidance-only release' % tested,
          tested >= 10, tested)
    check('NO current-quarter row was filled from it', leaked == 0, leaked)

    print('')
    print('=== and the guide rows DO fill from that same release ===')
    rec = model.record_by_id('STX-2026Q3')
    entry = model.prepare_from_record(rec)
    body = ('Seagate Reports Results\n\n'
            'For the fourth quarter, revenue is expected to be approximately '
            '$3.45 billion and non-GAAP EPS of $5.00.\n')
    card = S.score_release(P.parse_release(dict(
        msg_type='news_item', source='BUS', id='STX-2026Q3',
        headline='Seagate Reports Results', body=body)), entry, model)
    fwd = [r for r in card['keyKPIs']
           if r.get('period') != 'CURRENT_Q'
           and isinstance(r.get('actual'), (int, float))]
    cur = [r for r in card['keyKPIs']
           if r.get('period') == 'CURRENT_Q'
           and isinstance(r.get('actual'), (int, float))]
    check('at least one forward row filled', len(fwd) >= 1,
          [(r['name'][:22], r['actual']) for r in fwd])
    check('and zero current rows filled', cur == [],
          [(r['name'][:22], r['actual']) for r in cur])

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
