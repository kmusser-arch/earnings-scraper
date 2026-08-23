"""End-to-end: wire item -> detect -> parse -> score -> card.

The live library currently holds no PRE-EARNINGS records, so this builds a
fixture library containing one -- derived from CSCO's real card, with real
consensus and a real keyKPI list -- and drives the whole pipeline through it.

Proves: today's index, the NO_CARD refusal, ticker resolution, index-aligned
KPIs, forward-slot protection, and the latency of the hot path.
"""

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import listener as listener_mod, watchlist as wl_mod  # noqa: E402
from earnings_scraper.model import Model                                    # noqa: E402

TODAY = '2026-08-18'

PR_BODY = """
SAN JOSE, Calif. -- Cisco Systems, Inc. (NASDAQ: CSCO) today reported fourth
quarter results. Total revenue of $17.25 billion, up 18% year over year. GAAP
diluted earnings per share of $0.97; non-GAAP diluted earnings per share of
$1.22. Non-GAAP gross margin of 66.3%, down 210 basis points year over year.
Non-GAAP operating margin of 35.9%.

For the first quarter of fiscal 2027, Cisco expects revenue of $18.1 billion to
$18.3 billion. For full year fiscal 2027, Cisco expects revenue of
$76.5 billion to $77.5 billion.

Cisco will host a conference call at 4:30 p.m. Condensed consolidated statements
of operations follow.
"""

DECOYS = [
    ('PZM', 'EHang to Report Second Quarter 2026 Unaudited Financial Results '
            'on Tuesday, August 25, 2026', ''),
    ('PRN', 'ColorTokens Named a Leader in Q3 2026 Microsegmentation Vendor '
            'Evaluation By Independent Research Firm', ''),
    ('BUS', 'ROSEN Encourages Acme Investors to Secure Counsel - Class Action',
     'investors who purchased $5.0 million of securities'),
]


def build_fixture(tmp):
    """A library with ONE PRE-EARNINGS card reporting today."""
    real = Model()
    csco = real.record_by_id('CSCO-2026Q4')

    card = json.loads(json.dumps(csco))          # deep copy
    card['id'] = 'CSCO-FIXTURE'
    card['status'] = 'pre-earnings'              # lowercase ON PURPOSE
    card['reportDate'] = TODAY
    for key in ('actuals', 'scores', 'scoreLabels', 'summaries', 'takeaways',
                'callCommentary', 'stockReaction', 'beatMagnitude',
                'branchMatched', 'verification', 'tradeSummary'):
        card.pop(key, None)

    lib = dict(version=real.library.get('version'),
               lastUpdated=real.library.get('lastUpdated'),
               records=[card],
               abandonedRecords=[dict(id='ORPHAN-1', ticker='DUOL',
                                      status='PRE-EARNINGS',
                                      reportDate=TODAY)])
    for k, v in real.frameworks.items():
        lib[k] = v

    lib_path = os.path.join(tmp, 'earnings-library.json')
    with open(lib_path, 'w', encoding='utf-8') as fh:
        json.dump(lib, fh, ensure_ascii=False)
    prof_path = os.path.join(tmp, 'ticker-profiles.json')
    shutil.copyfile(real.profiles_path, prof_path)
    return lib_path, prof_path


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-54s %s' % ('PASS' if ok else 'FAIL', label, got))

    tmp = tempfile.mkdtemp(prefix='earnscrape-')
    try:
        lib_path, prof_path = build_fixture(tmp)
        model = Model(library_path=lib_path, profiles_path=prof_path)

        print('=== index ===')
        idx = model.index_for(TODAY)
        check('lowercase "pre-earnings" still indexed (status trap)',
              'CSCO' in idx, sorted(idx))
        check('abandonedRecords NOT indexed', 'DUOL' not in idx)
        check('a different date indexes nothing',
              model.index_for('2026-01-01') == {})

        print()
        print('=== watch ===')
        wl = wl_mod.build('CSCO\nZZZZ', today=TODAY, model=model)
        check('CSCO gradeable', wl['entries']['CSCO'].get('error') is None)
        check('ZZZZ is NO_CARD',
              wl['entries']['ZZZZ'].get('error') == 'NO_CARD')
        check('hero KPI resolved',
              wl['entries']['CSCO'].get('heroName') is not None,
              wl['entries']['CSCO'].get('heroName'))
        check('keyKPI order preserved',
              len(wl['entries']['CSCO']['keyKPIs']) == 5,
              len(wl['entries']['CSCO']['keyKPIs']))

        print()
        print('=== wire pipeline ===')
        cards = []
        lst = listener_mod.Listener(wl, popup=None, on_card=cards.append,
                                    verbose=False, log_hits=False, model=model)

        for wire, headline, body in DECOYS:
            lst.handle(dict(msg_type='news_item', source=wire, id='d-' + wire,
                            headline=headline, body=body,
                            primary_instruments=[]))
        check('3 decoys all rejected', lst.stats['rejected'] == 3,
              lst.stats['rejected'])
        check('no cards from decoys', len(cards) == 0)

        item = dict(msg_type='news_item', source='BUS', id='real-1',
                    headline='Cisco Systems, Inc. Reports Fourth Quarter and '
                             'Fiscal Year 2026 Results',
                    body=PR_BODY, primary_instruments=[])
        t0 = time.perf_counter()
        lst.handle(item)
        elapsed = (time.perf_counter() - t0) * 1000

        check('one card produced', len(cards) == 1, len(cards))
        if not cards:
            print('%d failure(s)' % (failures or 1))
            return 1
        card = cards[0]

        check('ticker resolved with no primary_instruments',
              card['ticker'] == 'CSCO', card.get('tickerSource'))
        # Threshold set from measurement, not aspiration. On the real corpus
        # parse costs 11-18 ms and it scales with BODY SIZE against the prose
        # regexes -- WDC skips the table scan entirely and still takes 13 ms.
        # The render is ~90 ms, so parsing is not the bottleneck and a tight
        # bound here only buys a flaky test.
        check('hot path under 25 ms', elapsed < 25.0, '%.2f ms' % elapsed)
        check('currentQuarter graded +1.0',
              card['scores']['currentQuarter'] == 1.0,
              card['scores']['currentQuarter'])
        check('narrative is None', card['scores']['narrative'] is None)
        check('overall is None', card['overall'] is None)
        check('status SCORED-PR-ONLY', card['status'] == 'SCORED-PR-ONLY',
              card['status'])
        check('keyKPIs aligned 1:1', len(card['keyKPIs']) == 5,
              len(card['keyKPIs']))

        fwd = [k for k in card['keyKPIs'] if k['forward']]
        check('forward slots detected', len(fwd) == 2,
              [k['name'][:28] for k in fwd])
        gm_fwd = [k for k in card['keyKPIs']
                  if 'Q1 FY27' in k['name']]
        check('Q1 FY27 margin slot NOT filled from Q4 actual',
              gm_fwd and gm_fwd[0]['actual'] is None,
              gm_fwd[0]['actual'] if gm_fwd else 'missing')
        fy_slot = [k for k in card['keyKPIs'] if 'FY27 Revenue' in k['name']]
        check('FY27 guide slot uses FY guidance midpoint',
              fy_slot and fy_slot[0]['actual'] == 77000.0,
              fy_slot[0]['actual'] if fy_slot else 'missing')

        print()
        print('=== NO_CARD wire path ===')
        cards.clear()
        item2 = dict(msg_type='news_item', source='PRN', id='real-2',
                     headline='Zzzz Corp (NASDAQ: ZZZZ) Reports Second '
                              'Quarter 2026 Results',
                     body='Total revenue of $88.0 million, up 12%. Non-GAAP '
                          'diluted earnings per share of $0.31. Gross margin '
                          'of 61.2%. Condensed consolidated statements of '
                          'operations follow.',
                     primary_instruments=['EQ:US:ZZZZ'])
        lst.handle(item2)
        check('NO_CARD card emitted', len(cards) == 1, len(cards))
        if cards:
            nc = cards[0]
            check('marked NO_CARD', nc.get('error') == 'NO_CARD', nc.get('error'))
            check('no scores at all', 'scores' not in nc)
            check('raw figures still shown',
                  bool(nc.get('rawFigures')), list(nc.get('rawFigures') or {}))
        check('stats count it as no_card', lst.stats['no_card'] == 1,
              lst.stats)

        print()
        print('=== alignment failure is loud ===')
        broken = dict(wl['entries']['CSCO'])
        broken['keyKPIs'] = list(broken['keyKPIs']) + [
            {'name': 'phantom KPI with no resolver', 'consensus': 1}]
        from earnings_scraper import parse as parse_mod, score as score_mod
        parsed = parse_mod.parse_release(item)
        rows = score_mod.build_kpi_rows(parsed, broken)
        check('a phantom KPI still gets a placeholder row',
              len(rows) == 6 and rows[-1]['actual'] is None, len(rows))
        try:
            score_mod.assert_alignment(broken['keyKPIs'], rows[:-1])
            check('truncated rows raise', False, 'no raise')
        except score_mod.AlignmentError:
            check('truncated rows raise AlignmentError', True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
