# -*- coding: utf-8 -*-
"""THE single sweep and THE single writer.

The extractor emits the column, this writes it into the library, the
dashboard renders what was emitted, and the counts below are counts of those
same rows. Until this held, three numbers described the corpus and none of
them described the artifact on Kyle's screen.

Run it with --write to update the library column; without, it reports only.

★ EVERY REPORT CARRIES ITS DENOMINATOR, and all six verdicts are printed
every time -- including the zeros. A headline that quoted three of six
buckets went a week without anyone noticing the other three existed.
"""

import argparse
import collections
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import parallel as PAR       # noqa: E402
from earnings_scraper import registry as R         # noqa: E402
from earnings_scraper import sweep as SW           # noqa: E402

MODEL = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
LIB = os.path.join(MODEL, 'earnings-library.json')
PEND = os.path.join(HERE, 'earnings_scraper', 'state', 'pending')
FIX = os.path.join(HERE, 'tests', 'fixtures', 'releases')
CORPUS = os.path.join(MODEL, 'tests', 'corpus')

CASES = [
    ('ORCL-2027Q1', os.path.join(PEND, '20260910-161341-ORCL.json'), 'raw'),
    ('ADBE-2026Q3', os.path.join(PEND, '20260910-160500-ADBE.json'), 'raw'),
    ('AVGO-2026Q3', os.path.join(FIX, 'AVGO-2026-09-02.txt'), 'txt'),
    ('HPE-2026Q3', os.path.join(FIX, 'HPE-2026-09-02.txt'), 'txt'),
    ('SNOW-2027Q2', os.path.join(FIX, 'SNOW-2026-09-02.txt'), 'txt'),
    ('APP-2026Q2', os.path.join(CORPUS, 'APP-2026Q2.txt'), 'txt'),
    ('SNDK-2026Q4', os.path.join(CORPUS, 'SNDK-2026Q4.txt'), 'txt'),
    ('WDC-2026Q4', os.path.join(CORPUS, 'WDC-2026Q4.txt'), 'txt'),
]


def body_of(path, kind):
    if kind == 'raw':
        return ((json.load(io.open(path, encoding='utf-8'))
                 .get('rawItem') or {}).get('body') or '')
    return io.open(path, encoding='utf-8').read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true',
                    help='write scraperRead and sweepVerdict into the library')
    args = ap.parse_args()

    lib = json.load(io.open(LIB, encoding='utf-8'))
    recs = {r['id']: r for r in lib['records']}

    counts = collections.Counter()
    rows_seen = 0
    detail = []

    for rid, path, kind in CASES:
        if not os.path.exists(path):
            print('   SKIP %s (source absent)' % rid)
            continue
        body = body_of(path, kind)
        rec = recs[rid]
        q = rec.get('fiscalQuarter')
        pre = rec['preEarnings'].get('keyKPIs') or []
        act = rec.setdefault('actuals', {}).setdefault('keyKPIs', [])
        while len(act) < len(pre):
            act.append({})

        for i, prow in enumerate(pre):
            if not isinstance(act[i], dict):
                continue
            spec = R.spec_for(prow)
            slot = act[i]
            rows_seen += 1
            got = (X.value_for(body, prow, record=rec) or {}
                   if R.status_of(spec) == 'EXTRACTABLE' else {})
            j = SW.judge(body, prow, slot, spec, q, got=got or None)
            counts[j['verdict']] += 1
            detail.append((rid, i, (prow.get('name') or '')[:32],
                           slot.get('actual'), j['value'], j['verdict'],
                           j.get('reason') or ''))
            if args.write:
                slot['scraperRead'] = j['value']
                slot['sweepVerdict'] = j['verdict']
                slot['sweepReason'] = j.get('reason')
                slot['pos'] = j.get('pos')
                slot['agreesWithActual'] = PAR.agrees(slot.get('actual'),
                                                      j['value'])

    print('=' * 100)
    print('SWEEP — one writer, all six verdicts, denominator attached')
    print('=' * 100)
    print(SW.report(counts, rows_seen))
    print('')
    for v in SW.VERDICTS:
        rows = [d for d in detail if d[5] == v]
        if not rows:
            continue
        print('-' * 100)
        print('%s — %d of %d' % (v, len(rows), rows_seen))
        for rid, i, nm, stored, val, _v, why in rows[:12]:
            print('   %-13s[%-2d] %-32s actual %-10s read %-10s %s'
                  % (rid, i, nm, stored, val, why[:40]))
        if len(rows) > 12:
            print('   ... %d more' % (len(rows) - 12))

    if args.write:
        io.open(LIB, 'w', encoding='utf-8', newline='').write(
            json.dumps(lib, indent=2, ensure_ascii=False) + '\n')
        print('')
        print('column written to earnings-library.json — this is now the only '
              'writer, and the dashboard renders exactly these rows')


if __name__ == '__main__':
    main()
