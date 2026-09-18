# -*- coding: utf-8 -*-
"""Declared discriminators that must stay LIVE, and the limits of ablation.

★★★ ABLATION MEASURES MARGINAL CONTRIBUTION, NOT WHETHER ANYTHING READS THE
FIELD. Blanking each declaration and re-extracting showed five fields moving
no row at all:

    basis          20 rows, 0 moves
    disqualify      8 rows, 0 moves
    basisPrefix     2 rows, 0 moves
    labelFootnoteTolerant  2 rows, 0 moves
    storedUnit     66 rows, 0 moves

and only one of those readings is 'nothing consults it'. `storedUnit` is
consumed by the OUTPUT conversion, which the probe never exercised. `basis` is
redundant where the columnAxes BASIS axis or the row label carries the same
fact. And `disqualify` FIRES — twice on ADBE, once on HPE — but on rows where
the disqualified hit was not going to win anyway.

A GUARD THAT FIRES WITHOUT CHANGING THE OUTCOME IS DEFENCE IN DEPTH, NOT
NOTHING. Distinguishing that from a guard that never fires is precisely what
ablation cannot do, so the firing itself is pinned here: HPE's dividend is the
founding case of the whole actual-column spec, and a guard that quietly stops
firing looks exactly like a guard that passes.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import registry as R           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, 'fixtures', 'releases')
PEND = os.path.join(ROOT, 'earnings_scraper', 'state', 'pending')
MODEL = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
LIB = os.path.join(MODEL, 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def body_raw(path):
    with io.open(path, encoding='utf-8') as fh:
        return ((json.load(fh).get('rawItem') or {}).get('body') or '')


def fired_count(body, spec):
    return sum(1 for h in R.label_hits(body, spec)
               if R.disqualified(body, h[0], spec))


def main():
    if not os.path.exists(LIB):
        print('FAIL library not reachable')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}

    cases = [
        ('HPE-2026Q3', os.path.join(FIX, 'HPE-2026-09-02.txt'), 'txt',
         'Q3 Non-GAAP EPS', 1,
         "HPE's dividend guard still fires — 0.1425 in an EPS row is the "
         'founding case of the actual-column spec'),
        ('ADBE-2026Q3', os.path.join(PEND, '20260910-160500-ADBE.json'),
         'raw', 'Q4 Adj EPS Guide', 2,
         "ADBE's 'GAAP:' guard still fires twice — the line prefix that "
         'separates 4.65 from 6.30'),
    ]

    for rid, path, kind, frag, want, msg in cases:
        if not os.path.exists(path):
            print('FAIL %s source missing' % rid)
            continue
        body = body_raw(path) if kind == 'raw' else io.open(
            path, encoding='utf-8').read()
        rows = [r for r in recs[rid]['preEarnings']['keyKPIs']
                if frag in (r.get('name') or '')]
        if not rows:
            print('FAIL %s row %r not found' % (rid, frag))
            continue
        spec = R.spec_for(rows[0])
        check(bool(spec.get('disqualify')),
              '%s %s declares a disqualifier' % (rid, frag))
        n = fired_count(body, spec)
        check(n >= want,
              '%s (fired on %d hit(s), expected at least %d)' % (msg, n, want))

    # ── and the guard must still be able to say no ───────────────────────
    probe = {'documentLabels': ['per share'],
             'disqualify': ['dividend'], 'specState': 'EXTRACTABLE'}
    text = 'a dividend of $0.14 per share was declared'
    hits = R.label_hits(text, probe)
    check(bool(hits) and R.disqualified(text, hits[0][0], probe),
          'a label sitting beside its disqualifier is refused — the guard '
          'can still say no, which is what makes its silence meaningful')
    clean = 'non-GAAP earnings per share of $1.11'
    hits2 = R.label_hits(clean, probe)
    check(bool(hits2) and not R.disqualified(clean, hits2[0][0], probe),
          'and a clean sentence is not refused — the guard is not simply on')


main()
