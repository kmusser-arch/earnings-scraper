"""Operating income, and the three-state precedence contract.

OI was the last unextracted metric with graded heroes riding on it: 11 rows,
4 of them ★, three of those four AMZN -- where operating income IS the hero and
the Q2 guide's $22B midpoint against a $23.85B Q1 base was the whole trade.
Adjusted EBITDA had a parser; operating income did not.

Three guards carry over from the revenue and margin work, and one is new:

  * a SEGMENT row ("Cloud OI ($B)") never takes the company figure
  * a row naming its BASIS gets that basis or nothing (the CBRS rule)
  * a GUIDE range grades on its MIDPOINT, not its high end
  * a company-level figure is one whose clause carries no SUBJECT -- which is
    how "Google Cloud operating income" is told from "Operating income"

The precedence block pins a contract that looks like a bug: returning None for a
non-NEW novelty is CORRECT, because render() keys its NOT-APPLICABLE state on
this value being falsy.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import gate, parse as P            # noqa: E402
from earnings_scraper import score as S                  # noqa: E402
from earnings_scraper import scorecard                    # noqa: E402
from earnings_scraper.model import Model                  # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:38]))
    if not ok:
        FAIL[0] += 1


def card(model, rid, body):
    entry = model.prepare_from_record(model.record_by_id(rid))
    return S.score_release(P.parse_release(
        dict(msg_type='news_item', source='BUS', id=rid,
             headline='%s Reports Results' % rid, body=body)), entry, model)


def main():
    model = Model()

    print('=== the row predicate, and the unit that settles a mixed name ===')
    for name, is_oi in [('Q1 Operating Income ($B)', True),
                        ('Q1 Adj OI ($B)', True),
                        ('Q3 OI Guide ($B)', True),
                        ('Q2 Adjusted Operating Income ($M)', True),
                        ('Income from Operations ($B)', True),
                        ('Q2 Adj Op Income ($B) / margin (%)', True),
                        ('Q1 Operating Margin (%)', False),
                        ('Q1 Revenue ($B)', False)]:
        check('%-38s -> %s' % (name, is_oi),
              S.is_op_income_row(name) is is_oi)
    mixed = 'Q2 Adj Op Income ($B) / margin (%)'
    check('a mixed income/margin name reads as the INCOME line',
          S.is_op_income_row(mixed)
          and __import__('earnings_scraper.units', fromlist=['x'])
          .is_dollar_magnitude(mixed))

    print('')
    print('=== the basis a row demands ===')
    for name, want in [('Q1 Adj OI ($B)', 'non-GAAP'),
                       ('Adj Op Income ($B)', 'non-GAAP'),
                       ('Q2 Adjusted Operating Income ($M)', 'non-GAAP'),
                       ('Non-GAAP Operating Income ($B)', 'non-GAAP'),
                       ('GAAP Operating Income ($B)', 'GAAP'),
                       ('Q1 Operating Income ($B)', None)]:
        check('%-34s demands %s' % (name, want),
              S.op_income_basis(name) == want, S.op_income_basis(name))

    print('')
    print('=== company vs subject-qualified, in prose ===')
    for probe, want in [
            ('Operating income was $23.9 billion.', 23900.0),
            ('In the first quarter, operating income was $23.9 billion.',
             23900.0),
            ('Total operating income of $23.9 billion.', 23900.0),
            ('Consolidated operating income of $23.9 billion.', 23900.0),
            ('Income from operations was $2.54 billion.', 2540.0),
            ('Operating profit reached $1.1 billion.', 1100.0),
            ('Google Cloud operating income was $3.2 billion.', None),
            ('AWS operating income was $14.2 billion.', None),
            ('Data Center segment operating income was $1.1 billion.', None),
            ('We expect operating income of $24.0 billion next quarter.',
             None)]:
        got = P.parse_op_income(probe)
        vals = {v['value_musd'] for v in got.values()}
        check('%-52s -> %s' % (probe[:52], want),
              (vals == {want}) if want is not None else (got == {}),
              vals or 'refused')

    print('')
    print('=== a newline ends a clause, like a full stop ===')
    # parse_release joins headline + teaser + body and a wire headline has no
    # terminating period, so the body's FIRST sentence would otherwise be judged
    # against the headline.
    joined = P.parse_release(dict(
        msg_type='news_item', source='BUS', id='x',
        headline='Amazon.com Announces First Quarter Results',
        body='Operating income increased to $23.9 billion.\n'))
    check('a first-line figure survives the headline join',
          any(v['value_musd'] == 23900.0
              for v in (joined.get('opIncome') or {}).values()),
          joined.get('opIncome'))
    two_line = P.parse_op_income(
        'Net sales increased 17% to $181.5 billion in the first quarter.\n'
        'Operating income increased to $23.9 billion in the first quarter.\n')
    check('and a figure at the start of a LATER line does too',
          any(v['value_musd'] == 23900.0 for v in two_line.values()),
          two_line)

    print('')
    print('=== AMZN-2026Q1: the hero and the guide that was the trade ===')
    body = ('Net sales increased 17% to $181.5 billion in the first quarter.\n'
            'Operating income increased to $23.9 billion in the first '
            'quarter.\n'
            'For the second quarter, the company expects net sales of $194.0 '
            'billion to $199.0 billion and operating income of between $20.0 '
            'billion and $24.0 billion.\n')
    c = card(model, 'AMZN-2026Q1', body)
    hero, guide = c['keyKPIs'][5], c['keyKPIs'][7]
    check('[5] the OI hero extracts', hero['actual'] == 23900.0,
          hero['actual'])
    check('    and clears its 22.75 bogey', hero['vsBogey'] == 'CRUSH',
          hero['vsBogey'])
    check('[7] the Q2 guide takes the MIDPOINT 22, not the high end 24',
          guide['actual'] == 22000.0, guide['actual'])
    check('    which grades a MISS against a 22.9 midpoint consensus',
          guide['vsBogey'] == 'MISS', guide['vsBogey'])
    check('    and the note states the range it came from',
          '20000' in guide['vsConsNote'] and '24000' in guide['vsConsNote'],
          guide['vsConsNote'][:40])
    check('    read from the guidance sentence, not the reported figure',
          guide['extractionSource'] == 'prose (guidance)',
          guide['extractionSource'])

    print('')
    print('=== the CBRS rule: a demanded basis is not substituted ===')
    ok = card(model, 'INTC-2026Q2',
              'Non-GAAP operating income of $2.77 billion.\n')
    check('an Adj OI row takes the non-GAAP figure',
          ok['keyKPIs'][6]['actual'] == 2770.0, ok['keyKPIs'][6]['actual'])
    bad = card(model, 'INTC-2026Q2',
               'GAAP operating income of $0.9 billion.\n')
    row = bad['keyKPIs'][6]
    check('and refuses when only GAAP is stated', row['actual'] is None,
          row['actual'])
    # ★ The inline basis check was replaced by the shared basis.select(), so the
    # source label and wording now come from one place for EPS, margins, OI and
    # EBITDA alike. That inline version knew 'non-gaap' and 'gaap' but NOT
    # 'adj' -- 61 of the 107 rows that declare a basis.
    check('    naming the refusal',
          row['extractionSource'] == 'basis-refused',
          row['extractionSource'])
    check('    and saying which basis was available',
          'GAAP' in row['vsConsNote'] and 'NOT GRADED' in row['vsConsNote'],
          row['vsConsNote'][:38])
    check('    and citing the CBRS founding case',
          'CBRS' in row['vsConsNote'])

    print('')
    print('=== a segment OI row is a different metric ===')
    only_co = card(model, 'GOOGL-2026Q2',
                   'Operating income was $39.4 billion.\n')
    check('Cloud OI refuses the company figure',
          only_co['keyKPIs'][3]['actual'] is None,
          only_co['keyKPIs'][3]['actual'])
    check('while the company row takes it',
          only_co['keyKPIs'][8]['actual'] == 39400.0,
          only_co['keyKPIs'][8]['actual'])
    both = card(model, 'GOOGL-2026Q2',
                'Operating income was $39.4 billion.\n'
                'Google Cloud operating income was $3.2 billion.\n')
    check('Cloud OI reads its own line when stated',
          both['keyKPIs'][3]['actual'] == 3200.0,
          both['keyKPIs'][3]['actual'])
    check('    and records that it came from the segment line',
          'segment OI' in (both['keyKPIs'][3]['extractionSource'] or ''),
          both['keyKPIs'][3]['extractionSource'])
    check('the two rows never share a value',
          both['keyKPIs'][3]['actual'] != both['keyKPIs'][8]['actual'])

    print('')
    print('=== $M units are not rescaled into $B ===')
    crwv = card(model, 'CRWV-2026Q2',
                'Adjusted operating income of $267 million.\n')
    check('CRWV reads 267 against a 66 consensus',
          crwv['keyKPIs'][1]['actual'] == 267.0, crwv['keyKPIs'][1]['actual'])

    print('')
    print('=== every OI row in the library is now reachable by name ===')
    import re
    total = reachable = heroes = 0
    for r in model.records:
        for k in ((r.get('preEarnings') or {}).get('keyKPIs')) or []:
            nm = k.get('name') or ''
            if not re.search(r'\bOI\b|operating income|op income', nm, re.I):
                continue
            total += 1
            if S.is_op_income_row(nm):
                reachable += 1
                heroes += ('★' in nm)
    check('all 11 rows match the predicate', total == reachable and total == 11,
          '%d of %d' % (reachable, total))
    check('4 of them are graded heroes', heroes == 4, heroes)

    print('')
    print('=== precedence has THREE states, and None reaches the third ===')
    fw = gate.framework_from(model)
    tsla = model.record_by_id('TSLA-2026Q1')
    check('TSLA novelty is NONE',
          (tsla.get('forwardCommitment') or {}).get('novelty') == 'NONE')
    check('so precedence_for_record returns None -- by design',
          scorecard.precedence_for_record(model, tsla) is None)
    txt = scorecard.render_record(model, tsla, fw)
    check('and render() prints NOT APPLICABLE, not a warning',
          'NOT APPLICABLE' in txt and 'PRECEDENCE NOT EVALUATED' not in txt)
    check('    stating that rule 1 overrides NEW only',
          'overrides NEW only' in txt)
    amzn = scorecard.precedence_for_record(model, model.record_by_id(
        'AMZN-2026Q1'))
    check('a NEW novelty DOES get an evaluated verdict',
          isinstance(amzn, dict) and amzn.get('rule') == 2, amzn)
    sndk_txt = scorecard.render_record(model,
                                       model.record_by_id('SNDK-2026Q4'), fw)
    check('and the rule-1 override still fires on SNDK',
          'OVERRIDDEN by precedence rule 1' in sndk_txt)

    print('')
    print('=== the cyclical predicate is the VALIDATED one ===')
    check('pattern is semiconduct|memory|hardware|storage',
          gate._CYCLICAL_SECTOR.pattern
          == r'semiconduct|memory|hardware|storage',
          gate._CYCLICAL_SECTOR.pattern)
    for sector, want in [('Semiconductors / Memory', True),
                         ('IT Services / Hardware', True),
                         ('Consumer Discretionary — Autos', False),
                         ('Chemicals', False),
                         ('Copper Mining', False),
                         ('Oil Refining', False)]:
        check('%-34s cyclical=%s' % (sector, want),
              bool(gate._CYCLICAL_SECTOR.search(sector)) is want)
    overrides = [r['id'] for r in model.records
                 if (scorecard.precedence_for_record(model, r) or {})
                 .get('overridesNovelty')]
    check('it still yields 1 TP / 0 FP across the library',
          overrides == ['SNDK-2026Q4'], overrides)

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


if __name__ == '__main__':
    sys.exit(main())
