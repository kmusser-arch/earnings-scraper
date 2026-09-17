# -*- coding: utf-8 -*-
"""The parallel column's safety properties — the ones that let it run live.

★★★ IT MUST NEVER TOUCH `actual`. That is the entire basis on which
replacement was rejected: of the rows where value_for produces a value, 27%
disagree with the hand read against 18% for the path already on the card. A
column that can silently edit the authoritative number is a replacement
wearing a different field name.

★★ IT MUST NEVER RAISE. This code runs inside score_release, which produces
the 4:15pm card. An extractor failure has to degrade to a refusalReason on one
row; a parallel column that can take down a print is worse than no column.

★ AND THE TWO FRAMES MUST NOT BE COMPARED ACROSS. `actual` is value_musd on a
fresh card and the row's STORED unit in the library, so HPE Q3 Revenue reads
12213.0 in one and 12.213 in the other. Comparing them directly marked a
MATCHING row as a disagreement -- a false red beside a correct number, which
is this column's one job done backwards. It was caught because four AVGO rows
disagreed by exactly 1000x, and 1000x is not a disagreement, it is a unit.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parallel as PAR      # noqa: E402
from earnings_scraper import parse as P           # noqa: E402
from earnings_scraper import registry as R        # noqa: E402
from earnings_scraper import score as S           # noqa: E402
from earnings_scraper.model import Model          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'releases')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def card_for(model, ticker, rid):
    body = io.open(os.path.join(FIX, '%s-2026-09-02.txt' % ticker),
                   encoding='utf-8').read()
    entry = model.prepare_from_record(model.record_by_id(rid))
    item = dict(msg_type='news_item', source='BUS', id='t-%s' % ticker,
                headline='%s Reports Results' % ticker, body=body)
    return S.score_release(P.parse_release(item), entry, model), entry, body


def main():
    model = Model()

    # ── the frame seam, asserted on the real numbers ─────────────────────
    b_spec = {'storedUnit': '$B', 'documentUnit': '$M'}
    check(PAR.agrees_on_card(12213.0, 12.213, b_spec) is True,
          'card $M 12213.0 and stored $B 12.213 are the SAME number')
    check(PAR.agrees(12213.0, 12.213) is False,
          'and comparing them in one frame correctly says they differ — '
          'which is why the two comparisons are separate functions')
    check(PAR.agrees_on_card(3.32, 2.68, {'storedUnit': '$'}) is False,
          'a per-share row compares as it is: 3.32 vs 2.68 disagrees')
    check(PAR.agrees_on_card(None, 1.0, b_spec) is None,
          'nothing to compare returns None, never False')

    # A TOLERANCE CANNOT SEE A CURRENCY SUBSTITUTION. ORCL prints "between
    # $1.83 and $1.91 in constant currency and between $1.85 and $1.93 in
    # USD" -- two legitimate midpoints 1% apart, identical in unit, period
    # and basis. max(0.02, 0.6%) passed them as AGREEMENT: a false green on
    # the column whose only job is visible disagreement.
    check(PAR.agrees(1.89, 1.87) is False,
          'USD 1.89 and constant-currency 1.87 DISAGREE — a 1% currency '
          'variant is not rounding')
    check(PAR.agrees(2.974, 2.97) is True,
          'but 2.974 and 2.97 still agree — one number at two precisions')
    check(PAR.agrees(84.0, 83.95) is True,
          'and 84.0 against 83.95 agrees, at the coarser printing')

    # ── it must not touch `actual` ───────────────────────────────────────
    card, entry, body = card_for(model, 'HPE', 'HPE-2026Q3')
    rows = card['keyKPIs']
    before = [r.get('actual') for r in rows]
    vals, refs = PAR.attach(rows, entry, body)
    after = [r.get('actual') for r in rows]
    check(before == after,
          '`actual` is byte-identical after attach (%d values, %d refusals)'
          % (vals, refs))

    # ── every extractable row is accounted for, none silently skipped ────
    pre = entry.get('keyKPIs') or []
    gaps = []
    for i, row in enumerate(rows):
        spec = R.spec_for(pre[i]) if i < len(pre) else None
        if not spec or R.status_of(spec) != 'EXTRACTABLE':
            continue
        if row.get('scraperRead') is None and not row.get('refusalReason'):
            gaps.append((pre[i].get('name') or '')[:40])
    check(not gaps,
          'every EXTRACTABLE row carries a value OR a named refusal (%d gaps)'
          % len(gaps))

    # ── it must not raise, whatever the extractor does ───────────────────
    import earnings_scraper.extract as X
    real = X.value_for

    def exploding(*a, **k):
        raise RuntimeError('deliberate')

    X.value_for = exploding
    try:
        r2 = [dict(actual=1.0) for _ in pre]
        v2, f2 = PAR.attach(r2, entry, body)
        raised = False
    except Exception:
        raised = True
    finally:
        X.value_for = real
    check(not raised, 'an exploding extractor does not propagate out of attach')
    named = [r for r in r2 if 'deliberate' in str(r.get('refusalReason') or '')]
    check(bool(named),
          'and the failure is RECORDED on the row as a refusalReason, not '
          'swallowed (%d row(s))' % len(named))
    check(all(r.get('actual') == 1.0 for r in r2),
          '`actual` survives an extractor explosion untouched')

    # ── refresh_agreement is idempotent ──────────────────────────────────
    rec = {'actuals': {'keyKPIs': [
        {'actual': 12.213, 'scraperRead': 12.213, 'agreesWithActual': None},
        {'actual': 3.32, 'scraperRead': 2.68, 'agreesWithActual': True},
        {'actual': None, 'scraperRead': 5.0, 'agreesWithActual': True},
    ]}}
    first = PAR.refresh_agreement(rec)
    second = PAR.refresh_agreement(rec)
    flags = [r['agreesWithActual'] for r in rec['actuals']['keyKPIs']]
    check(first == 3 and second == 0,
          'refresh corrects 3 flags then changes nothing on a second run')
    check(flags == [True, False, None],
          'and it reports agree / DISAGREE / nothing-to-compare correctly')


main()
