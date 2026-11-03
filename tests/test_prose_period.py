# -*- coding: utf-8 -*-
r"""THE PROSE CHANNEL: one section, two periods, and who may read it.

Three pins, each with its own founding case from 2026-11-03.

★ 1. THE SPLIT-AND-STAMP. A single 'Outlook' heading carries both the
quarter guide and the full-year guide, separated only by the lines 'For
Q4 2026, we expect:' and 'For full year 2026:'. Stamping the whole
section with the heading's period put ~$8.5B -- the ANNUAL revenue guide
-- into a Q4 slot whose bogey is $2.65B. Nothing about that row looks
wrong: real number, right metric, right label, wrong period.

   PLTR's two income-from-operations heroes are the sharpest probe
   available, because they share a metric word and differ ONLY by
   sub-section. If subblocks() regresses they collapse onto one value.

★ 2. THE RESIDUE SEPARATOR. _prose_metric matches loosely, which is safe
only while the metric word is the WHOLE name. Measured over corpus +
fixtures: 21 loose matches carried a residue and ALL 21 WERE WRONG; 13
carried none and ALL 13 WERE RIGHT. 34 for 34 with no overlap, so it is
pinned here as a separator and not merely used as a filter.

★★ 3. select() MUST SURVIVE EVERY TICKER IN THE LIBRARY. `'expect' in
entry` on the None that dlm.get returns for an unmapped hero threw a
TypeError and took the whole card down for 24 tickers -- META, GOOGL,
NFLX, AVGO, IBM, DELL, NOW, CSCO, NKE -- across 47 of 121 corpus
documents. It shipped in a34c723 and no gate saw it, because
validate_maps walks only the 7 tickers that carry a documentLabelMap and
every fixture is one of those 7. A gate over 10% of the library said
PASS. This one walks all of it.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                       # noqa: E402
from scraper import prose_guidance as PG                      # noqa: E402
from scraper import selector as S                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, 'scraper', 'fixtures')
CORPUS = os.path.join(ROOT, 'earnings_scraper', 'state', 'html')

#: PLTR Q3 2026, read off the Outlook block of the filed 8-K exhibit.
#: Both ends, never a midpoint; $M, the unit the scaler emits.
PLTR_Q3 = {
    'Next-Q Revenue Guide ($M)':              (2649.0, 2653.0),
    'Next-Q Adj Income from Operations ($M)': (1640.0, 1644.0),
    'FY Revenue Guide ($M)':                  (8530.0, 8534.0),
    'FY Adj Income from Operations ($M)':     (5245.0, 5249.0),
    'FY Adj Free Cash Flow ($M)':             (4800.0, 5000.0),
}

#: hero names whose loose match MUST be refused: what is left after the
#: metric word is a segment or a transform, and the prose channel has no
#: vocabulary for either. Every one of these was resolving to a
#: consolidated figure before 2026-11-03.
REFUSE = ('AWS revenue growth y/y (%)',
          'North America revenue ($B)',
          'US Commercial Revenue Growth YoY (%)',
          'FY US Commercial Revenue Guide ($M)',
          'FY Revenue Guide Raise (% of prior guide)',
          'FY Revenue Guide CC Action (%)',
          'FY+1 capex framing ($B)')

#: and the ones that MUST still resolve: the metric word is the whole
#: name once period and unit decoration is stripped.
ALLOW = ('Next-Q Revenue Guide ($M)', 'Q2 Revenue Guide ($M)',
         'F4Q Revenue Guide ($M)', 'FY Revenue Guide ($M)',
         'Next-Q Adj Income from Operations ($M)',
         'FY Adj Income from Operations ($M)',
         'FY Adj Free Cash Flow ($M)')

FAILED = []


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))
    if not ok:
        FAILED.append(msg)


def read(path):
    return io.open(path, encoding='utf-8', errors='replace').read()


def main():
    pltr = os.path.join(FIX, 'PLTR_2026Q3.html')
    if not os.path.exists(pltr):
        check(False, 'PLTR_2026Q3 fixture missing -- this file asserts '
                     'nothing about the split')
        return
    html = read(pltr)
    text = sec.to_text(html)
    rows = PG.from_text(text)

    # ── 1. the reader stamps two periods from one heading ───────────────
    heads = [h for h, _b in PG.sections(text)]
    check(heads == ['Outlook'],
          'PLTR publishes ONE guidance heading, %r -- so the periods can '
          'only come from the lead-ins inside it' % (heads,))
    periods = sorted(set(r['period'] for r in rows))
    check(periods == ['FY2026', 'nextQGuidance'],
          'and the reader stamps BOTH periods out of that one section: %s'
          % periods)

    oi = [r for r in rows if r['metric'] == 'operatingIncome']
    check(len(oi) == 2 and oi[0]['low'] != oi[1]['low'],
          'the two income-from-operations bullets stay DISTINCT -- same '
          'metric word, different sub-block, different number %s'
          % [(r['period'], r['low']) for r in oi])

    # ── the hero rows, end to end ───────────────────────────────────────
    res = S.select(cells.from_html(html), 'PLTR', prose_rows=rows)
    got = dict((f['hero'], (f.get('low'), f.get('high')))
               for f in res.get('found') or [])
    for hero, want in sorted(PLTR_Q3.items()):
        check(got.get(hero) == want,
              '%-40s %s' % (hero, '%s-%s' % want
                            if got.get(hero) == want
                            else 'WANT %s GOT %s' % (want, got.get(hero))))

    # ★ THE INVERTED ONE. If the splitter stops splitting, the FY hero
    # takes the QUARTER's number and every assertion above still passes
    # except this pair -- which is why both ends are named explicitly.
    check(got.get('FY Adj Income from Operations ($M)')
          != got.get('Next-Q Adj Income from Operations ($M)'),
          'and the FY row is NOT the next-Q row wearing an FY label')

    # ── 2. the residue separator, 34 for 34 ─────────────────────────────
    print('')
    bad = [n for n in REFUSE if S._prose_metric(n, rows) is not None]
    check(not bad,
          'every hero whose name carries a SEGMENT or a TRANSFORM is '
          'refused by the loose match%s'
          % ('' if not bad else ' -- GOT %s' % bad))
    miss = [n for n in ALLOW if S._prose_metric(n, rows) is None]
    check(not miss,
          'and every hero that IS just the metric word still resolves%s'
          % ('' if not miss else ' -- REFUSED %s' % miss))
    # anti-vacuous: REFUSE must not be passing because the metrics are
    # absent from this document in the first place.
    have = set(r['metric'] for r in rows)
    check({'revenue', 'operatingIncome', 'freeCashFlow'} <= have,
          'anti-vacuous: the metrics those names reduce to ARE in this '
          "document (%s), so a refusal is the rule's work and not an "
          'empty candidate set' % sorted(have))

    # ── 3. select() survives EVERY ticker that has a profile ────────────
    print('')
    profiles, _mt = S.load_profiles()
    crashed, ran, resolved = [], 0, 0
    for d in (FIX, CORPUS):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.html'):
                continue
            tic = fn.split('_')[0].upper()
            if tic not in profiles:
                continue
            doc = read(os.path.join(d, fn))
            try:
                out = S.select(cells.from_html(doc), tic,
                               prose_rows=PG.from_text(sec.to_text(doc)))
                ran += 1
                resolved += len(out.get('found') or [])
            except Exception as exc:                          # noqa: BLE001
                crashed.append((tic, fn, repr(exc)[:70]))
    check(ran >= 100,
          'anti-vacuous: %d documents actually went through select() -- '
          'a clean run over an empty list is not a pass' % ran)
    check(not crashed,
          'select() returns a result for every one of them, mapped '
          'ticker or not%s'
          % ('' if not crashed else ' -- CRASHED %s' % crashed[:4]))
    check(resolved > 0,
          'and they resolve %d hero rows between them, so the run is '
          'doing work and not returning empty results quietly' % resolved)


main()
if FAILED:
    sys.exit(1)
