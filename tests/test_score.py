"""Unit tests for the scoring primitives.

These need no library access. test_regression.py pins the rules against the
live records; this file pins the pieces those rules are built from.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import score as S, units as U         # noqa: E402
from earnings_scraper.parse import pct_delta, verdict_for    # noqa: E402


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, got))

    print('=== period classification ===')
    cases = [
        # (name, record_quarter, expected)
        ('Q4 Revenue ($M) ★', 'Q4 (FY26)', 'CURRENT_Q'),
        ('FQ4 Gross Margin (%) ★', 'Q4 (FY26)', 'CURRENT_Q'),
        ('FY26 AI Infrastructure Orders ($B) ★★', 'Q4 (FY26)', 'CURRENT_Q'),
        # No "Guid" in the name -- caught only by the period-token mismatch.
        ('Q1 FY27 Non-GAAP Gross Margin (%) ★★', 'Q4 (FY26)', 'NEXTQ_GUIDE'),
        ('FY27 Revenue + EPS Guide ★', 'Q4 (FY26)', 'FY_GUIDE'),
        ('F1Q Revenue Guide ($B) ★', 'Q4 (FY26)', 'NEXTQ_GUIDE'),
        ('3Q Adj EBITDA Guide ($B) ★', 'Q2', 'NEXTQ_GUIDE'),
        ('Auto GM ex-credits (%) ★', 'Q1', 'CURRENT_Q'),
    ]
    for name, rq, expected in cases:
        got = S._classify_period(name, rq)
        check('%-40s -> %s' % (name[:40], expected), got == expected, got)

    print()
    print('=== KPI-name unit resolution ===')
    check('($B) detected', U.unit_from_kpi_name('FQ4 Revenue ($B) ★') == '$B',
          U.unit_from_kpi_name('FQ4 Revenue ($B) ★'))
    check('($M) detected', U.unit_from_kpi_name('Q4 Revenue ($M) ★') == '$M')
    check('(%) is not a dollar magnitude',
          not U.is_dollar_magnitude('FQ4 Gross Margin (%) ★'))
    check('($B) IS a dollar magnitude',
          U.is_dollar_magnitude('FQ4 Revenue ($B) ★'))
    v, p = U.kpi_to_musd(9.5, 'FQ4 Revenue ($B) ★')
    check('9.5 $B -> 9500 $M', v == 9500.0 and p is None, v)
    v, p = U.kpi_to_musd(84.0, 'FQ4 Gross Margin (%) ★')
    check('84.0 % passes through unchanged', v == 84.0 and p is None, v)
    v, p = U.kpi_to_musd(9.5, 'FQ4 Revenue')
    check('no unit in name -> refuses', v is None and p is not None, p)

    print()
    print('=== the SNDK false-clear ===')
    # bogey 9.5 ($B) vs actual 8965 ($M). Compared raw this reads as a CLEAR.
    e, a = S._normalise_pair(9.5, 8965.0, 'FQ4 Revenue ($B) ★')
    check('normalised bogey is 9500', e == 9500.0, e)
    check('is correctly a MISS, not a clear', a < e, '%s < %s' % (a, e))
    check('raw comparison would have been wrong', 8965.0 > 9.5)

    print()
    print('=== undeclared revUnit refuses (error class D5) ===')
    v, p = U.normalise_expectation(16.825, None)
    check('null unit -> refuses', v is None and p is not None, p)
    v, p = U.normalise_expectation(16825, '$M')
    check('$M unit -> 16825', v == 16825.0 and p is None, v)

    print()
    print('=== units suppression (error class D6) ===')
    pct, flag = pct_delta(17252.0, 16.825)
    check('|pct| > 300 suppressed and flagged',
          pct is None and flag is not None, (flag or '')[:52])
    pct, flag = pct_delta(17252.0, 16825.0)
    check('normal delta passes', abs(pct - 2.54) < 0.02, pct)

    print()
    print('=== renderer-safe verdicts only ===')
    from earnings_scraper.config import VALID_VERDICTS
    for p in (25.0, 12.0, 6.0, 2.0, 0.0, -2.0, -25.0, None):
        v = verdict_for(p)
        check('verdict for %-6s = %-10s is renderer-safe' % (p, v),
              v in VALID_VERDICTS, v)

    print()
    print('=== band parsing from calibration ===')
    check('">= +2.0" matches 6.67',
          S._band_matches_clearance({'heroClearsBogeyPct': '>= +2.0'}, 6.67))
    check('">= +2.0" rejects 0.71',
          not S._band_matches_clearance({'heroClearsBogeyPct': '>= +2.0'}, 0.71))
    check('"0.0 to +2.0" matches 0.71',
          S._band_matches_clearance({'heroClearsBogeyPct': '0.0 to +2.0'}, 0.71))
    check('maxFlags read directly',
          S._band_max_flags({'maxFlags': 1}) == 1)
    check('"1-2" flags -> 2', S._band_max_flags({'flags': '1-2'}) == 2)
    check('">=3" flags -> 3', S._band_max_flags({'flags': '>=3'}) == 3)

    print()
    print('=== alignment assertion fails loudly ===')
    try:
        S.assert_alignment([{'name': 'a'}, {'name': 'b'}], [{'name': 'a'}])
        check('short array raises', False, 'no raise')
    except S.AlignmentError:
        check('short array raises AlignmentError', True)
    try:
        S.assert_alignment([{'name': 'a'}], [{'name': 'a'}])
        check('equal lengths pass', True)
    except S.AlignmentError:
        check('equal lengths pass', False, 'raised')

    print()
    print('=== the cap is a CEILING, not a value ===')
    rows = [dict(name='a', pctVsCons=-6.9, forward=False),
            dict(name='b', pctVsCons=-26.0, forward=False)]
    score, why = S._negative_band({}, {}, rows, -26.0,
                                  dict(marginDeclined=True))
    check('multi-line miss + margin decline -> -1.5', score == -1.5, why[:46])
    score, why = S._negative_band({}, {}, rows, -26.0, {})
    check('multi-line miss alone -> -1.0', score == -1.0, why[:46])
    score, why = S._negative_band({}, {}, [rows[0]], -6.9, {})
    check('single modest miss -> -0.5', score == -0.5, why[:46])
    score, why = S._negative_band({}, {}, [], -1.0, {})
    check('hero missed but no line missed consensus -> 0.0', score == 0.0)
    score, why = S._negative_band({}, {}, rows, -26.0,
                                  dict(ownGuideFailed=True,
                                       marginCollapse=True))
    check('major miss + own-guide + collapse -> -2.0', score == -2.0, why[:46])

    print()
    print('=== withdrawn / capped / ceiling DEFER, never auto-score ===')
    from earnings_scraper.parse import parse_guidance_action as pga
    from earnings_scraper.score import _DEFER_ACTIONS, _expects_no_guide
    defer_cases = [
        ('WITHDRAWN', 'For full year fiscal 2027 the company is withdrawing '
                      'its revenue guidance.'),
        ('WITHDRAWN', 'The company has discontinued its FY27 AI order target '
                      'guidance.'),
        ('CAPPED', 'For fiscal 2027 the company replaced its prior AI order '
                   'target guidance with meaningfully higher.'),
        ('CEILING', 'For fiscal 2027 guidance, we expect to compound at '
                    'roughly 30% annually.'),
    ]
    for expected, sent in defer_cases:
        got = (pga(sent).get('fy') or {}).get('action')
        check('%-10s detected' % expected, got == expected, got)
        check('%-10s is in the defer set' % expected, got in _DEFER_ACTIONS)

    score_cases = [
        ('RAISED', 'For full year fiscal 2027 the company raises its revenue '
                   'guidance to $76.5 billion from $68.0 billion.'),
        ('MAINTAINED', 'The company reaffirms its full year fiscal 2027 '
                       'revenue guidance of $68.0 billion.'),
        ('CUT', 'For fiscal 2027 the company lowered its revenue guidance to '
                '$60.0 billion.'),
    ]
    for expected, sent in score_cases:
        got = (pga(sent).get('fy') or {}).get('action')
        check('%-10s still scores (not deferred)' % expected,
              got == expected and got not in _DEFER_ACTIONS, got)

    print()
    print('=== absence is 0.0 for a non-guider, a deferral otherwise ===')
    for text, expected in [('None.', True), ('None. The only forward anchor '
                                             'is the $787M NOI series.', True),
                           ('No formal FY rev/EPS — watch OpEx', True),
                           ('n/a', True),
                           ('FY sub rev $15.53-15.57B. Bull = raise >$75M.',
                            False),
                           ('Currently $3.1-3.3B rev / $1.33-1.48 EPS', False),
                           (None, False), ('', False)]:
        got = _expects_no_guide(text)
        check('no-guide-expected(%r) -> %s' % (str(text)[:30], expected),
              got == expected, got)

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
