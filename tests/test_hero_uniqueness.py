# -*- coding: utf-8 -*-
"""Hero resolution on THREE axes, and a non-unique match is a failure.

★ WHAT WAS WRONG
`hero_scope()` is a SUBJECT guard -- "is this the Auto segment or the company?"
-- and it works as one. It was being used as a ROW RESOLVER, which it is not.
Because _GENERIC_TOKENS deliberately strips every metric word (revenue, eps,
margin, gm, ebitda) so that independently-written names still match, the scope
of "Q4 Adj EPS ($)" and of "Q4 Total Revenue ($B)" are BOTH empty -- and empty
equals empty.

Measured across the library, subject alone gave:
    33 records resolved uniquely · 27 matched MORE THAN ONE row · 5 matched none
ORCL's EPS hero matched 7 rows including revenue, FCF and gross margin. TSLA's
"Auto GM ex-credits" matched "Auto Revenue ex-credits YoY" -- identical scope
{auto, ex, credits}, different metric.

★ THE FIX IS THREE AXES, and the third was free
    subject  hero_scope()          -- already existed
    metric   hero_metric_kind()    -- recovered from the words scope discards
    period   appliesTo             -- the PROFILE ALREADY DECLARED IT
        33 unique  ->  37 (metric)  ->  56 (period).  1 ambiguous, 8 refused.

★ AND A NON-UNIQUE MATCH IS A REFUSAL
Seven matches is not a partial success. Taking the first grades a random metric;
taking none silently falls back to revenue, and revenue provably cannot
reproduce the accepted grades -- SNDK beat consensus 6.9% and scored +1.0 while
TSLA beat 0.5% and scored +2.0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import score as S                      # noqa: E402
from earnings_scraper.model import Model                     # noqa: E402
from earnings_scraper.scorecard import row_name              # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:32]))
    if not ok:
        FAIL[0] += 1


def main():
    m = Model()

    print('=== markers and RANK tokens are not part of a name ===')
    for raw, want in ((u'\U0001F525 #1 Q4 Adj EPS ($)', 'eps'),
                      (u'\U0001F525 #2 HBM Revenue / 2027 Supply', 'revenue'),
                      (u'Q1 Revenue ($B) ★★★', 'revenue'),
                      (u'\U0001F525 Auto GM ex-credits (THE KPI)',
                       'grossMargin')):
        check('%-34s -> %s' % (raw[:34], want),
              S.hero_metric_kind(raw) == want, S.hero_metric_kind(raw))

    print('')
    print('=== the metric axis, including the abbreviations ===')
    for nm, want in (('Auto GM ex-credits (%)', 'grossMargin'),
                     ('Adj EBITDA Margin (%)', 'ebitdaMargin'),
                     ('2Q Adj EBITDA ($B)', 'ebitda'),
                     ('Non-GAAP Op Margin (%)', 'opMargin'),
                     ('Q1 Operating Income ($B)', 'opIncome'),
                     ('FY27 FCF Guide ($B)', 'fcf'),
                     ('cRPO ($M)', 'rpo'),
                     ('Q3 ARR ($M)', 'arr'),
                     ('Total Backlog ($B)', 'backlog'),
                     ('Q1 Revenue ($B)', 'revenue')):
        check('%-32s -> %-13s' % (nm, want),
              S.hero_metric_kind(nm) == want, S.hero_metric_kind(nm))

    print('')
    print('=== "Op Margin" was UNRECOGNISED, and None matched everything ===')
    # This is why a REVENUE hero matched "Non-GAAP Op Margin (%)" on MDB-2027Q1
    # and GTLB-2027Q1: the row's kind came back None, and None was permissive.
    check('a revenue hero no longer matches an Op Margin row',
          not S.hero_scope_matches('Q1 Revenue ($M)',
                                   'Non-GAAP Op Margin (%)'))

    print('')
    print('=== TSLA: same subject, different metric, must NOT match ===')
    gm, rev = 'Auto GM ex-credits (%)', 'Auto Revenue ex-credits YoY'
    check('the two share an identical SUBJECT scope',
          S.hero_scope(gm) == S.hero_scope(rev), sorted(S.hero_scope(gm)))
    check('    so subject alone cannot tell them apart',
          S.hero_scope(gm) == S.hero_scope(rev))
    check('    but the metric axis splits them',
          not S.hero_scope_matches(gm, rev))
    check('    while the GM row still matches its own hero',
          S.hero_scope_matches(gm, u'\U0001F525 Auto GM ex-credits (THE KPI)'))

    print('')
    print('=== the period axis comes from the profile, not from wording ===')
    check('currentQuarter takes the reported row',
          S.hero_period_matches('currentQuarter', 'Q1 Revenue ($M)', 'Q1'))
    check('    and refuses the guide row',
          not S.hero_period_matches('currentQuarter',
                                    'Q2 Revenue Guide ($M)', 'Q1'))
    check('nextQGuidance takes the guide row',
          S.hero_period_matches('nextQGuidance',
                                'Q2 Revenue Guide ($M)', 'Q1'))
    check('narrative constrains no period',
          S.hero_period_matches('narrative', 'anything at all', 'Q1'))
    check('an absent appliesTo constrains no period',
          S.hero_period_matches(None, 'anything at all', 'Q1'))

    print('')
    print('=== a non-unique match REFUSES, and says why ===')
    # Both scope to nothing, are both `revenue`, and both sit in CURRENT_Q --
    # 'total' is a generic token, so nothing distinguishes them. ("restated"
    # would NOT be ambiguous: it is a distinguishing qualifier and splits them.)
    names = ['Q1 Revenue ($M)', 'Q1 Total Revenue ($B)']
    idx, why = S.resolve_hero_row('Q1 Revenue ($M)', names)
    check('two matches -> no index', idx is None, idx)
    check('    and the reason says AMBIGUOUS', 'AMBIGUOUS' in (why or ''),
          (why or '')[:30])
    idx, why = S.resolve_hero_row('Nothing Like It (%)', ['Q1 Revenue ($M)'])
    check('no match -> no index', idx is None, idx)
    check('    and the reason names the revenue fallback it refused',
          'revenue' in (why or ''), (why or '')[:34])
    idx, why = S.resolve_hero_row('Q1 Revenue ($M)',
                                  ['Q1 Revenue ($M)', 'Q1 Adj EPS ($)'])
    check('one match -> that index, no reason', (idx, why) == (0, None),
          (idx, why))

    print('')
    print('=== the whole library, on all three axes ===')
    uniq = amb = none = 0
    for rec in m.records:
        try:
            entry = m.prepare_from_record(rec)
        except Exception:
            continue
        hero = entry.get('heroName')
        if not hero:
            continue
        first = (entry.get('heroes') or entry.get('allHeroes') or [{}])[0]
        names = [row_name(pk) or '' for pk in
                 ((rec.get('preEarnings') or {}).get('keyKPIs')) or []]
        hits = [i for i, nm in enumerate(names)
                if S.hero_scope_matches(hero, nm)
                and S.hero_period_matches(first.get('appliesTo'), nm,
                                          rec.get('quarter'))]
        if len(hits) == 1:
            uniq += 1
        elif hits:
            amb += 1
        else:
            none += 1
    print('     unique %d · ambiguous %d · refused %d' % (uniq, amb, none))
    check('at least 56 records resolve to exactly ONE row', uniq >= 56, uniq)
    check('at most 1 record is still ambiguous', amb <= 1, amb)
    check('    (subject alone gave 33 unique and 27 ambiguous)', uniq > 33)

    print('')
    print('=== the 8 refusals are PROFILE/GRID mismatches, not bugs ===')
    # Each names a metric the grid does not carry: CRWV's hero is operating
    # income and its grid has EBITDA; AEHR's is gross margin and its grid has
    # none. Refusing is correct -- these are profiles to confirm at the next
    # pre-earnings build, which is exactly what needsReview marks.
    for rid, missing_kind in (('CRWV-2026Q1', 'opIncome'),
                              ('AEHR-2026Q4', 'grossMargin'),
                              ('APP-2026Q2', 'ebitdaMargin')):
        rec = m.record_by_id(rid)
        entry = m.prepare_from_record(rec)
        kinds = {S.hero_metric_kind(row_name(pk) or '') for pk in
                 ((rec.get('preEarnings') or {}).get('keyKPIs')) or []}
        check('%-13s hero wants %-13s grid has none' % (rid, missing_kind),
              S.hero_metric_kind(entry['heroName']) == missing_kind
              and missing_kind not in kinds, sorted(k for k in kinds if k))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
