# -*- coding: utf-8 -*-
"""PROPERTY 1: degrade LOUDLY, do not refuse.

★ THE FOUNDING CASE. AVGO 2026-09-02 arrived over PRN as 9,498 characters
ending "(MORE TO FOLLOW)" with every financial-statement section absent, and
was scored as if whole. Part 1 CONTAINED the hero -- $16.7B AI semi revenue,
the $21.7B Q4 guide, revenue, EPS, segment revenue -- so refusing the card
would have cost the trader the most important number on the print at 4:15pm to
protect him from an appendix he was never going to read in ninety seconds.

So the card DEGRADES:
   1. a banner at the very top
   2. overall NOT EMITTED with reason 'partial source', a DISTINCT string
   3. 'source incomplete' on every unfilled row, never 'no candidate'
   4. every FILLED row kept -- it came from text that WAS present
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import completeness as CP

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'fixtures', 'releases')
CORPUS = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
          r'\tests\corpus')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    return io.open(path, encoding='utf-8').read()


def test_marker_is_decisive_alone():
    """★ The marker needs no corroboration. A 9,498-char body ending
    '(MORE TO FOLLOW)' is part 1 of N, full stop."""
    st = CP.assess(_read(os.path.join(FIX, 'AVGO-2026-09-02.txt')))
    assert st['truncated'] is True, 'AVGO must be flagged truncated'
    assert st['marker'] is not None, 'the marker must be captured, not just used'
    assert 'MORE' in st['marker'].upper()
    assert st['chars'] == 9498, st['chars']
    for section in ('income statement', 'balance sheet', 'cash flow'):
        assert section in st['missing'], section

    # a marker with NO other signal still condemns
    long_body = ('CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS\n'
                 'CONDENSED CONSOLIDATED BALANCE SHEETS\n'
                 'CONSOLIDATED STATEMENTS OF CASH FLOWS\n'
                 'RECONCILIATION OF GAAP TO NON-GAAP\n' + ('x' * 40000)
                 + '\n(MORE TO FOLLOW)')
    st2 = CP.assess(long_body)
    assert st2['short'] is False, 'not short'
    assert st2['missing'] == [], 'no sections missing'
    assert st2['truncated'] is True, 'the marker alone must be enough'


def test_complete_releases_are_not_condemned():
    """★ REFUSAL IS NOT FREE. The complete releases must pass clean -- a
    detector that flags everything is worth nothing."""
    paths = [os.path.join(FIX, 'HPE-2026-09-02.txt'),
             os.path.join(FIX, 'SNOW-2026-09-02.txt')]
    paths += [os.path.join(CORPUS, f) for f in ('APP-2026Q2.txt',
                                                'SNDK-2026Q4.txt',
                                                'WDC-2026Q4.txt')
              if os.path.exists(os.path.join(CORPUS, f))]
    assert len(paths) >= 4, 'need the corpus to make this test mean anything'
    for path in paths:
        st = CP.assess(_read(path))
        assert st['truncated'] is False, '%s wrongly condemned: %s' % (
            os.path.basename(path), st['reasons'])
        assert st['complete'] is True
        assert CP.banner(st) == [], 'no banner on a complete release'


def test_length_floor_alone_does_not_condemn():
    """★★ ANTI-VACUOUS. A short but STRUCTURALLY COMPLETE release must pass,
    or the floor is doing the work and the marker check is decoration.

    Every control that could independently condemn is disabled: no marker, and
    at most one missing section. Only length remains.
    """
    short_but_whole = ('ACME Q3 RESULTS\nRevenue $1,000\n'
                       'CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS\n'
                       'CONDENSED CONSOLIDATED BALANCE SHEETS\n'
                       'CONSOLIDATED STATEMENTS OF CASH FLOWS\n')
    st = CP.assess(short_but_whole)
    assert st['short'] is True, 'must actually be under the floor'
    assert st['marker'] is None, 'no marker -- that control is disabled'
    assert len(st['missing']) <= 1, st['missing']
    assert st['truncated'] is False, \
        'length alone must NOT condemn a structurally complete release'

    # and the dual: short PLUS two missing sections DOES condemn
    st2 = CP.assess('ACME Q3 RESULTS\nRevenue $1,000\n')
    assert st2['short'] is True
    assert st2['marker'] is None
    assert len(st2['missing']) >= 2
    assert st2['truncated'] is True, 'two corroborating signals must condemn'


def test_banner_names_what_is_missing():
    st = CP.assess(_read(os.path.join(FIX, 'AVGO-2026-09-02.txt')))
    lines = CP.banner(st)
    assert lines, 'a truncated source must produce a banner'
    head = lines[0]
    assert 'SOURCE INCOMPLETE' in head, head
    assert '9498' in head, head
    assert 'MORE' in head.upper(), head
    body = '\n'.join(lines)
    for section in ('income statement', 'balance sheet', 'cash flow'):
        assert section in body, section
    # ★ it must say a blank is the TEXT's fault, not the parser's
    assert 'TEXT was absent' in body


def test_row_reason_names_the_section():
    """★ 'this value lives in the cash flow' beats 'source incomplete'. The
    banner becomes a checklist of what to hand-read."""
    st = CP.assess(_read(os.path.join(FIX, 'AVGO-2026-09-02.txt')))
    cash = CP.row_reason('★ Buyback ($M)', st)
    assert 'cash flow' in cash, cash
    assert cash.startswith('source incomplete')
    fcf = CP.row_reason('FY26 Free Cash Flow ($B)', st)
    assert 'cash flow' in fcf, fcf
    shares = CP.row_reason('Diluted Shares (M)', st)
    assert 'income statement' in shares, shares
    # a row with no known home still gets the generic reason, never silence
    generic = CP.row_reason('★★★ Q3 AI Semi Revenue ($B)', st)
    assert generic and generic.startswith('source incomplete'), generic
    assert 'lives in' not in generic, 'do not claim a home we do not know'


def test_no_reason_on_a_complete_source():
    """★ A complete source must not stamp 'source incomplete' on anything --
    that would hide a real parser gap behind an ingestion excuse."""
    st = CP.assess(_read(os.path.join(FIX, 'SNOW-2026-09-02.txt')))
    assert CP.row_reason('★ Buyback ($M)', st) is None
    assert CP.row_reason('anything at all', st) is None


def test_the_two_non_emission_reasons_do_not_share_a_string():
    """★★ TWO DIFFERENT REASONS FOR THE SAME NON-EMISSION MUST NOT SHARE
    WORDING. 'narrative unknown on a PR-only run' means wait for the call.
    'partial source' means go read the wire's part 2. Different remedies."""
    path = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
            r'\render_scorecard.py')
    if not os.path.exists(path):
        return
    src = io.open(path, encoding='utf-8').read()
    assert 'PARTIAL SOURCE' in src, 'the partial-source reason must exist'
    assert 'narrative unknown on a PR-only run' in src, 'and so must the other'
    i = src.index('PARTIAL SOURCE')
    line = src[src.rindex('\n', 0, i) + 1:src.index('\n', i)]
    assert 'narrative' not in line.lower(), \
        'the two reasons must be distinct strings, not one blended message'


def test_wired_into_the_scorer():
    """★ The module existing is not the module running."""
    src = io.open(os.path.join(ROOT, 'earnings_scraper', 'score.py'),
                  encoding='utf-8').read()
    assert 'completeness_mod.assess' in src, 'assess must be called'
    assert 'completeness_mod.row_reason' in src, 'rows must be reasoned'
    assert 'completeness_mod.banner' in src, 'the banner must reach the card'
    assert 'sourceComplete' in src, 'the card must carry the verdict'
    # ★ property 4: a filled row is never blanked to punish the source
    i = src.index('completeness_mod.row_reason')
    window = src[i - 500:i]
    assert "row.get('actual') is not None" in window and 'continue' in window, \
        'filled rows must be skipped, never blanked'


def test_banner_reaches_the_top_of_the_card():
    """★ ABOVE the hero table, not below it. A warning under the numbers is a
    warning read after the trade."""
    path = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
            r'\render_scorecard.py')
    if not os.path.exists(path):
        return
    src = io.open(path, encoding='utf-8').read()
    assert src.index('sourceBanner') < src.index('L.append("HERO KPIs")'), \
        'the banner must be emitted before the hero table'


def test_a_sharper_reason_survives_truncation():
    """★★ PROPERTY 4 EXTENDS TO REASONS. 'forward-period slot (FY_GUIDE)'
    describes a blank that would be blank on a COMPLETE release too.
    Overwriting it with 'source incomplete' loses information AND blames the
    wire for a refusal the parser made correctly."""
    keep = [
        'forward-period slot (FY_GUIDE) - not filled from reported',
        'forward-period slot (NEXTQ_GUIDE) - not filled from reported',
        'not found in release | consensus is text, grade manually',
        'period mismatch: found GUIDE_NEXT_Q, row wants REPORTED',
        'scale: actual 1588 vs street 30.5 = 52.07x',
        'qualified margin row (product) - the release states a total',
    ]
    for reason in keep:
        assert CP.reason_is_absence(reason) is False, reason

    replace = ['not found in release', 'no candidate', '', None]
    for reason in replace:
        assert CP.reason_is_absence(reason) is True, repr(reason)


def test_end_to_end_the_avgo_card_degrades():
    """★ THE MODULE EXISTING IS NOT THE MODULE RUNNING, and a unit test on
    assess() is not a test that the CARD changed. Scores the real fixture."""
    import earnings_scraper.parse as P
    import earnings_scraper.score as S
    from earnings_scraper.model import Model

    body = _read(os.path.join(FIX, 'AVGO-2026-09-02.txt'))
    model = Model()
    entry = model.prepare_from_record(model.record_by_id('AVGO-2026Q3'))
    item = dict(msg_type='news_item', source='BUS', id='fixture-AVGO',
                headline='AVGO Reports Results', body=body)
    card = S.score_release(P.parse_release(item), entry, model)

    # 1. the banner reached the card
    assert card.get('sourceComplete') is False
    assert card.get('sourceBanner'), 'no banner on the card'
    assert 'SOURCE INCOMPLETE' in card['sourceBanner'][0]

    rows = card['keyKPIs']
    filled = [r for r in rows if r.get('actual') is not None]
    blank = [r for r in rows if r.get('actual') is None]

    # 4. FILLED ROWS ARE KEPT. Part 1 carried the hero; refusing the card
    #    would have cost the trader the most important number on the print.
    assert len(filled) >= 7, 'good rows were blanked to punish the source'
    hero = next(r for r in rows if 'AI Semi Revenue' in (r['name'] or '')
                and 'Q3' in (r['name'] or ''))
    assert hero.get('actual') == 16700.0, hero.get('actual')
    assert not hero.get('sourceIncomplete'), 'a filled row is not incomplete'

    # 3. blank rows are stamped -- but only the ones with nothing better
    stamped = [r for r in blank if r.get('sourceIncomplete')]
    assert stamped, 'no row was stamped source-incomplete'
    for row in stamped:
        assert 'source incomplete' in row['ungradedReason']
    kept = [r for r in blank if not r.get('sourceIncomplete')]
    assert kept, 'every blank was restamped -- the guard is not running'
    for row in kept:
        assert 'source incomplete' not in (row['ungradedReason'] or ''), \
            row['name']

    # ★ the sharper section-level reason where the value's home is known
    buyback = next(r for r in rows if 'Buyback' in (r['name'] or ''))
    assert 'cash flow' in buyback['ungradedReason'], \
        buyback['ungradedReason']


def test_end_to_end_a_complete_card_is_untouched():
    """★ MUTUALLY CONCEALING DEFECTS. If the truncation stamp leaked onto a
    complete release it would hide every real parser gap behind an ingestion
    excuse -- and the gap would never be found again."""
    import earnings_scraper.parse as P
    import earnings_scraper.score as S
    from earnings_scraper.model import Model

    body = _read(os.path.join(FIX, 'SNOW-2026-09-02.txt'))
    model = Model()
    entry = model.prepare_from_record(model.record_by_id('SNOW-2027Q2'))
    item = dict(msg_type='news_item', source='BUS', id='fixture-SNOW',
                headline='SNOW Reports Results', body=body)
    card = S.score_release(P.parse_release(item), entry, model)

    assert card.get('sourceComplete') is True
    assert not card.get('sourceBanner'), 'banner on a complete release'
    for row in card['keyKPIs']:
        assert not row.get('sourceIncomplete'), row['name']
        assert 'source incomplete' not in (row.get('ungradedReason') or ''), \
            row['name']


def test_provenance_is_permanent_and_names_the_issuer():
    """★★ A TRADING FACT, NOT A BUILD FACT. AVGO's AI-semi revenue appears in
    NO table in the COMPLETE release -- the segment table carries
    Semiconductor Solutions and Infrastructure Software only. $16.7B and
    $21.7B live exclusively in prepared remarks, in part 1 and in the full
    document alike. A quote source there is the CEILING, not a gap.

    So the note must read as a property of Broadcom, and must survive the
    truncation pass without being reworded into a missing table source.
    """
    import earnings_scraper.parse as P
    import earnings_scraper.score as S
    from earnings_scraper.model import Model

    body = _read(os.path.join(FIX, 'AVGO-2026-09-02.txt'))
    model = Model()
    entry = model.prepare_from_record(model.record_by_id('AVGO-2026Q3'))
    item = dict(msg_type='news_item', source='BUS', id='prov-AVGO',
                headline='AVGO Reports Results', body=body)
    card = S.score_release(P.parse_release(item), entry, model)
    rows = card['keyKPIs']

    tagged = [r for r in rows if r.get('provenanceNote')]
    names = [r['name'] for r in tagged]
    assert len(tagged) == 2, names

    for row in tagged:
        assert 'prepared remarks only' in row['provenanceNote']
        assert 'no table source exists' in row['provenanceNote']
        # ★ it must NOT read as a fixable gap
        assert 'truncat' not in row['provenanceNote'].lower(), row['name']
        assert row.get('extractionSource') == 'quote', row.get(
            'extractionSource')
        assert row.get('actual') is not None, 'the note is not an excuse'

    # the hero and the next-quarter guide, and nothing else
    assert any('Q3 AI Semi Revenue' in n for n in names), names
    assert any('AI Semi Revenue Guide' in n for n in names), names


def test_provenance_does_not_leak_across_the_modifier_axis():
    """★ KEY 2 OWNS THIS. 'Non-AI Semi Revenue' has a token set that is a
    SUPERSET of the AI hero's, so token containment alone tagged it -- and the
    negation is the entire difference between the two metrics. The modifier
    matcher already decides this symmetrically; the provenance pass asks it
    rather than re-deriving the rule."""
    import earnings_scraper.parse as P
    import earnings_scraper.score as S
    from earnings_scraper.model import Model

    body = _read(os.path.join(FIX, 'AVGO-2026-09-02.txt'))
    model = Model()
    entry = model.prepare_from_record(model.record_by_id('AVGO-2026Q3'))
    item = dict(msg_type='news_item', source='BUS', id='prov-AVGO',
                headline='AVGO Reports Results', body=body)
    card = S.score_release(P.parse_release(item), entry, model)

    for row in card['keyKPIs']:
        name = row.get('name') or ''
        if 'Non-AI' in name or 'non-AI' in name:
            assert not row.get('provenanceNote'), \
                'the AI note leaked onto the negated metric: %s' % name
    # ★ AND IT MUST NOT LEAK ACROSS THE PERIOD AXIS. Pinned on rowPeriod, not
    # on a name substring: my first version of this check asserted against
    # 'FY26 AI Semi' and caught 'Q4 FY26 AI Semi Revenue Guide', which is the
    # legitimately-tagged NEXT-QUARTER row. The profile carries provenance for
    # currentQuarter and nextQuarter only, so FY_GUIDE rows must be clean.
    for row in card['keyKPIs']:
        if row.get('rowPeriod') == 'FY_GUIDE':
            assert not row.get('provenanceNote'),                 'leaked onto a full-year slot: %s' % row['name']


def test_no_provenance_on_tickers_without_one():
    """★ REFUSAL IS NOT FREE, and neither is a note. A profile with no
    provenanceNote must produce no notes at all."""
    import earnings_scraper.parse as P
    import earnings_scraper.score as S
    from earnings_scraper.model import Model

    model = Model()
    for tk, rid in (('SNOW', 'SNOW-2027Q2'), ('HPE', 'HPE-2026Q3')):
        body = _read(os.path.join(FIX, '%s-2026-09-02.txt' % tk))
        entry = model.prepare_from_record(model.record_by_id(rid))
        item = dict(msg_type='news_item', source='BUS', id='prov-%s' % tk,
                    headline='%s Reports' % tk, body=body)
        card = S.score_release(P.parse_release(item), entry, model)
        for row in card['keyKPIs']:
            assert not row.get('provenanceNote'), '%s: %s' % (tk, row['name'])


def main():
    """★ THE RUNNER COUNTS PRINTED PASSES. A file that asserts silently is
    indistinguishable from a file that does nothing -- that is exactly the
    failure mode run_tests.py exists to catch."""
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_') or not callable(fn):
            continue
        try:
            fn()
        except AssertionError as exc:
            print('FAIL %-52s %s' % (name, exc))
            failures += 1
            continue
        print('PASS %s' % name)
    print('')
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
