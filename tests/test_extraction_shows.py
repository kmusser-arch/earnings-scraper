# -*- coding: utf-8 -*-
"""EXTRACTION WORK BECOMES VISIBLE: fill the rows and the category scores.

★★★ THIS TEST EXISTS BECAUSE I REPORTED THE OPPOSITE. I said HPE showed 11 of
11 rows extracted and currentQuarter still deferring, which would mean the
scorer could never show extraction work and every downstream improvement was
invisible. It was my PROBE: it called the deferral-text helper directly,
ignoring that the helper only ever runs when the score is None. HPE-2026Q3 is
SCORED-FULL with currentQuarter 2.0 and was not deferring at all.

★★ THE REAL QUESTION WAS STILL WORTH ANSWERING, AND THIS IS THE ANSWER. Take
the live card, count what the scraper filled, inject the hand reads for the
rows it missed, and re-grade:

    HPE   3 -> 13 rows    currentQuarter  None -> 2.0
    SNOW  2 -> 11 rows                    1.5  -> 1.5
    AVGO  7 -> 16 rows                    1.0  -> 1.0

HPE's 2.0 is exactly the score the record carries by hand. The deferral is
data-dependent and correct: the scorer is waiting for numbers, and it produces
the right answer the moment it has them.

★ SO THE ONLY THING BETWEEN THE SCRAPER AND A SCORED CARD IS ACTUALS. That is
worth a permanent test rather than a remembered result, because the claim it
replaces was believed by both of us for a day and nearly reordered the work.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse as P                # noqa: E402
from earnings_scraper import score as S                # noqa: E402
from earnings_scraper.model import Model               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'releases')
MODEL = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
LIB = os.path.join(MODEL, 'earnings-library.json')

CASES = [('HPE', 'HPE-2026Q3', 2.0), ('SNOW', 'SNOW-2027Q2', 1.5),
         ('AVGO', 'AVGO-2026Q3', 1.0)]


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not os.path.exists(LIB):
        print('FAIL library not reachable')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    model = Model()

    for ticker, rid, want in CASES:
        path = os.path.join(FIX, '%s-2026-09-02.txt' % ticker)
        if not os.path.exists(path):
            print('FAIL %s fixture missing' % ticker)
            continue
        body = io.open(path, encoding='utf-8').read()
        entry = model.prepare_from_record(model.record_by_id(rid))
        parsed = P.parse_release(dict(msg_type='news_item', source='BUS',
                                      id='t-%s' % ticker,
                                      headline=ticker, body=body))
        card = S.score_release(parsed, entry, model)
        rows = card['keyKPIs']
        before = sum(1 for r in rows if isinstance(r.get('actual'),
                                                   (int, float)))

        hand = (recs[rid].get('actuals') or {}).get('keyKPIs') or []
        for i, row in enumerate(rows):
            h = hand[i] if i < len(hand) and isinstance(hand[i], dict) else {}
            if isinstance(h.get('actual'), (int, float)) and \
                    not isinstance(row.get('actual'), (int, float)):
                row['actual'] = h['actual']
                row['actualUnit'] = h.get('actualUnit')
                row['extractionSource'] = 'injected-hand-read'
        after = sum(1 for r in rows if isinstance(r.get('actual'),
                                                  (int, float)))

        graded = S.grade_current_quarter(parsed, entry, rows, model, None)
        got = (graded or {}).get('score')
        check(after > before,
              '%s: injecting the hand reads fills %d rows, up from %d'
              % (ticker, after, before))
        check(got == want,
              '%s: currentQuarter grades %s with the rows filled — the score '
              'the record carries by hand' % (ticker, want))

    # ── and the deferral is about NUMBERS, not the call ──────────────────
    hpe = os.path.join(FIX, 'HPE-2026-09-02.txt')
    if os.path.exists(hpe):
        entry = model.prepare_from_record(model.record_by_id('HPE-2026Q3'))
        parsed = P.parse_release(dict(msg_type='news_item', source='BUS',
                                      id='t', headline='HPE',
                                      body=io.open(hpe,
                                                   encoding='utf-8').read()))
        card = S.score_release(parsed, entry, model)
        check((card.get('scores') or {}).get('currentQuarter') is None,
              'HPE defers on the UNAIDED read — 3 rows of 18 is not a score')
        check((card.get('scores') or {}).get('narrative') is None,
              'and narrative defers too, but for a reason no extraction can '
              'change')


main()
