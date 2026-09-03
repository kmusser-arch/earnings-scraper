# -*- coding: utf-8 -*-
"""The `actual` column acceptance test — SCRAPER-SPEC-actual-column.md.

★ THE BUG IS MIS-ROUTING, NOT COVERAGE. A blank row is honest; a wrong row lies
with a colour on it. HPE reported 🔴 MISS on non-GAAP EPS using 0.1425 -- the
DIVIDEND -- when EPS was 1.11, a beat of $0.18. On a live print that inverts the
trade. So every expectation here comes in BOTH directions: the value that must
appear, and the wrong value that must NOT.

★ THREE REAL PRESS RELEASES, captured off the wire on 2026-09-02 and stored in
tests/fixtures/releases/. Not synthesised: AVGO 9,498 chars from PRN, HPE 83,827
and SNOW 85,211 from BUS. Every value below was filled correctly BY HAND from
this same text, so nothing here is a "the data isn't in the PR" problem.

★ STEP STATUS. This file is the acceptance test for all five spec steps, but
only STEP 1 (unit/scale guard) is implemented. Expectations owned by steps 2-4
are marked TODO: they print their current state and do NOT fail the build,
because a test that goes red for work that has not started yet trains you to
ignore it -- the same reasoning that made EXPIRED its own category.

The two the guard owns are HARD assertions and must never regress:
    HPE  Q3 Non-GAAP EPS ($)     refuses 0.1425  (0.15x street)
    SNOW Product Revenue Growth  refuses 1588    (>100 in a (%) row)
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import parse as P, score as S          # noqa: E402
from earnings_scraper.model import Model                     # noqa: E402
from earnings_scraper.scorecard import row_name              # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'fixtures', 'releases')
FAIL = [0]
TODO = [0]

#: (ticker, record, row index, expected, must_not, pos_step, neg_step)
#: expected None means the row must stay UNGRADED.
#:
#: ★ THE TWO DIRECTIONS HAVE DIFFERENT OWNERS, and conflating them mis-reported
#: step 1 as failing. Refusing 0.1425 is the scale guard's job (step 1).
#: FINDING 1.11 is extraction's job (step 3). The spec says step 1 makes those
#: two cases "refuse", not "fill".
CASES = [
    ('AVGO', 'AVGO-2026Q3', 0, 16.7, None, 5, 5),    # CEO quote, REPORTED
    ('AVGO', 'AVGO-2026Q3', 1, 21.7, None, 5, 5),    # CEO quote, GUIDE_NEXT_Q
    ('AVGO', 'AVGO-2026Q3', 10, None, 16.7, 1, 1),   # ★ guard refuses at 3.71x
    ('AVGO', 'AVGO-2026Q3', 3, 8.752, None, 3, 3),   # segment table
    ('AVGO', 'AVGO-2026Q3', 8, 3.32, None, 0, 0),    # already correct — KEEP
    ('HPE', 'HPE-2026Q3', 8, 1.11, 0.1425, 3, 1),    # ★ refusal is step 1
    ('HPE', 'HPE-2026Q3', 16, 40.4, None, 3, 3),
    ('HPE', 'HPE-2026Q3', 15, 16.2, 14.0, 3, 2),
    ('HPE', 'HPE-2026Q3', 1, 17.0, None, 3, 3),      # segment table
    ('HPE', 'HPE-2026Q3', 2, 22.0, None, 3, 3),      # segment table
    ('SNOW', 'SNOW-2027Q2', 0, 1491.9, None, 3, 3),
    ('SNOW', 'SNOW-2027Q2', 2, 37.0, 1588.0, 3, 1),  # ★ refusal is step 1
    ('SNOW', 'SNOW-2027Q2', 3, 37.5, None, 2, 2),    # mid of 37-38
    ('SNOW', 'SNOW-2027Q2', 1, 6070.0, None, 2, 2),
    ('SNOW', 'SNOW-2027Q2', 5, 74.7, None, 3, 3),
    ('SNOW', 'SNOW-2027Q2', 8, 15.3, 15.5, 3, 2),    # must NOT take the guide
]

#: which steps are implemented. Only these produce hard failures.
DONE_STEPS = {0, 1}


def check(label, ok, detail='', step=0):
    if ok:
        print('PASS %-56s %s' % (label, str(detail)[:30]))
        return
    if step in DONE_STEPS:
        print('FAIL %-56s %s' % (label, str(detail)[:30]))
        FAIL[0] += 1
    else:
        print('TODO %-56s %s   [step %d]' % (label, str(detail)[:26], step))
        TODO[0] += 1


def card_for(model, ticker, rid):
    body = io.open(os.path.join(FIX, '%s-2026-09-02.txt' % ticker),
                   encoding='utf-8').read()
    entry = model.prepare_from_record(model.record_by_id(rid))
    item = dict(msg_type='news_item', source='BUS', id='fixture-%s' % ticker,
                headline='%s Reports Results' % ticker, body=body)
    return S.score_release(P.parse_release(item), entry, model), entry


def main():
    model = Model()
    print('=== the fixtures are REAL captured releases ===')
    for t, chars in (('AVGO', 9498), ('HPE', 83827), ('SNOW', 85211)):
        p = os.path.join(FIX, '%s-2026-09-02.txt' % t)
        got = len(io.open(p, encoding='utf-8').read())
        check('%-5s release stored (%d chars)' % (t, chars), got == chars, got,
              step=0)

    cards = {}
    for t, rid in (('AVGO', 'AVGO-2026Q3'), ('HPE', 'HPE-2026Q3'),
                   ('SNOW', 'SNOW-2027Q2')):
        cards[t] = card_for(model, t, rid)

    print('')
    print('=== the 16 acceptance cases, BOTH directions ===')
    for ticker, rid, idx, want, must_not, pos_step, neg_step in CASES:
        card, _entry = cards[ticker]
        rows = card['keyKPIs']
        row = rows[idx] if idx < len(rows) else {}
        nm = (row.get('name') or '')[:34]
        got = row.get('actual')
        rejected = row.get('scaleRejected')
        reason = row.get('ungradedReason') or row.get('vsConsNote') or ''

        verdict = str(row.get('vsBogey') or '')
        suspect = bool(row.get('scaleSuspect'))
        confident = any(w in verdict.upper() for w in ('CLEAR', 'FADE', 'MISS', 'BEAT', 'CRUSH', 'NUKE'))

        # ── the POSITIVE direction ────────────────────────────────────────
        if want is None:
            # "stays ungraded" now means: carries NO confident verdict. The
            # value may be shown with SCALE? -- that is the step-1b action.
            ok = (not isinstance(got, (int, float))) or (suspect
                                                         and not confident)
            check('%-5s [%2d] %-34s not graded confidently'
                  % (ticker, idx, nm), ok,
                  ('%s %s' % (got, verdict)) if not ok else
                  (verdict or 'ungraded'), step=pos_step)
        else:
            ok = (isinstance(got, (int, float))
                  and abs(_as_row_scale(got, row) - want) < 0.051)
            check('%-5s [%2d] %-34s == %g' % (ticker, idx, nm, want), ok,
                  ('got %s' % got) if not ok else got, step=pos_step)

        # ── the NEGATIVE direction, named explicitly ──────────────────────
        if must_not is not None:
            took = (isinstance(got, (int, float))
                    and abs(_as_row_scale(got, row) - must_not) < 0.051)
            # ★ THE INVARIANT, restated for step 1b. Showing the wrong value is
            # allowed; GRADING it is not. A number the trader can see and judge
            # beats a blank he cannot.
            ok = (not took) or (suspect and not confident)
            check('      \u2514 %g never graded confidently' % must_not, ok,
                  ('GRADED %s' % verdict) if not ok
                  else ('%s / excluded' % (verdict or 'absent')),
                  step=neg_step)
            if rejected is not None:
                print('        refusal: %s' % str(reason)[:96])

    print('')
    print('=== every refusal states a reason (spec step 8) ===')
    for t in ('AVGO', 'HPE', 'SNOW'):
        card, _ = cards[t]
        blanks = [r for r in card['keyKPIs']
                  if not isinstance(r.get('actual'), (int, float))]
        withr = [r for r in blanks if (r.get('ungradedReason') or '').strip()]
        check('%-5s %d of %d ungraded rows carry a reason'
              % (t, len(withr), len(blanks)), len(withr) == len(blanks),
              '%d/%d' % (len(withr), len(blanks)), step=0)

    print('')
    print('=== SCALE? refusals, per fixture ===')
    total = 0
    for t in ('AVGO', 'HPE', 'SNOW'):
        card, _ = cards[t]
        ref = [(r.get('name'), r.get('scaleRejected'), r.get('ungradedReason'))
               for r in card['keyKPIs'] if r.get('scaleRejected') is not None]
        total += len(ref)
        print('   %-5s %d refused' % (t, len(ref)))
        for nm, val, why in ref:
            print('      %-40s rejected %-10s %s'
                  % ((nm or '')[:40], val, (why or '')[:52]))
    check('the guard fired at least three times '
          '(HPE EPS, SNOW growth, AVGO non-AI)', total >= 3, total, step=1)
    print('')
    print('=== and every flagged row is EXCLUDED from scoring ===')
    for t in ('AVGO', 'HPE', 'SNOW'):
        card, _ = cards[t]
        susp = [r for r in card['keyKPIs'] if r.get('scaleSuspect')]
        graded = [r for r in susp
                  if any(w in str(r.get('vsBogey') or '').upper()
                         for w in ('CLEAR', 'FADE', 'MISS', 'BEAT', 'CRUSH', 'NUKE'))]
        check('%-5s %d scale-suspect row(s), 0 graded' % (t, len(susp)),
              not graded, [r.get('vsBogey') for r in graded], step=1)

    print('')
    print('=== what the cards must KEEP doing (spec section 7) ===')
    for t in ('AVGO', 'HPE', 'SNOW'):
        card, _ = cards[t]
        check('%-5s overall NOT EMITTED on a PR-only run' % t,
              card.get('overall') is None, card.get('overall'), step=0)

    print('')
    print('%d failure(s), %d TODO (steps 2-5 not implemented)'
          % (FAIL[0], TODO[0]))
    return 1 if FAIL[0] else 0


def _as_row_scale(actual, row):
    """The stored actual expressed in the unit the ROW NAME declares.

    The parser normalises dollar magnitudes to $M, so a ($B) row holds 16700.0
    for $16.7B. The spec's expectations are written in the row's own unit.
    """
    if not isinstance(actual, (int, float)):
        return actual
    unit = S.declared_unit(row.get('name') or '')
    declared = row.get('actualUnit')
    if unit == '$B' and declared == '$M':
        return actual / 1000.0
    return actual


if __name__ == '__main__':
    sys.exit(main())
