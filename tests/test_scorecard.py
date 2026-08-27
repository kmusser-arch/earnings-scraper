"""The scorecard adapter.

Pins that the scraper emits render_scorecard.render() VERBATIM and formats
nothing itself. The load-bearing assertion is the byte-identity check: if the
scraper ever grows a second formatter, that check is what fails.
"""

import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import config, gate, scorecard             # noqa: E402
from earnings_scraper import parse as P, score as S              # noqa: E402
from earnings_scraper.model import Model                         # noqa: E402

BODY = (
    'Sandisk Corporation (NASDAQ: SNDK) today reported fourth quarter '
    'results. Total revenue of $8.97 billion, up 22% year over year. '
    'Non-GAAP diluted earnings per share of $39.25. Non-GAAP gross margin of '
    '84.6%, up 380 basis points year over year.\n\n'
    'For the first quarter of fiscal 2027, the company expects revenue of '
    '$10.4 billion to $10.7 billion.\n'
    'Condensed consolidated statements of operations follow.'
)


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-56s %s' % ('PASS' if ok else 'FAIL', label, got))

    model = Model()
    fw = gate.framework_from(model)

    print('=== the renderer is loaded, not reimplemented ===')
    mod = scorecard.renderer()
    check('loaded from the model repo by absolute path',
          os.path.dirname(mod.__file__) == config.LIB_DIR,
          os.path.basename(mod.__file__))
    check('render() is the entry point', callable(getattr(mod, 'render', None)))
    check('no local formatter exists in the package',
          not hasattr(scorecard, 'render') or
          scorecard.render_card.__module__ == 'earnings_scraper.scorecard')

    # ★ The whole point: our adapter must reproduce the reference CLI byte for
    # byte when handed the same record.
    print()
    print('=== byte-identical to `py render_scorecard.py SNDK-2026Q4` ===')
    ref = subprocess.run(
        [sys.executable, 'render_scorecard.py', 'SNDK-2026Q4'],
        cwd=config.LIB_DIR, capture_output=True, text=True, encoding='utf-8')
    # The reference CLI passes no precedence, so compare like for like.
    ours = mod.render(model.record_by_id('SNDK-2026Q4'), fw, None)
    check('reference CLI ran', ref.returncode == 0,
          (ref.stderr or '')[:40])
    check('byte-identical', ours.rstrip('\n') == (ref.stdout or '').rstrip('\n'),
          'len %d vs %d' % (len(ours), len(ref.stdout or '')))

    print()
    print('=== the scraper card goes through render() ===')
    rec = model.record_by_id('SNDK-2026Q4')
    entry = model.prepare_from_record(rec)
    card = S.score_release(
        P.parse_release(dict(msg_type='news_item', source='BUS', id='x',
                             headline='Sandisk Corporation Reports Fourth '
                                      'Quarter Fiscal 2026 Results',
                             body=BODY)), entry, model)
    out = scorecard.render_card(card, entry, fw)
    check('a card is produced', bool(out))
    check('header matches the locked format',
          out.splitlines()[0].endswith('— EARNINGS SCORECARD'),
          out.splitlines()[0][-30:])
    check('HERO KPIs table is first', 'HERO KPIs' in out.splitlines()[2])

    print()
    print('=== deferrals render as explicit markers, never blanks ===')
    check('narrative is DEFERRED', '4. Narrative Check: —' in out)
    check('the deferral marker text is present',
          '⟨DEFERRED — needs the call⟩' in out)
    check('key takeaways are DEFERRED',
          'takeaways require synthesis, not extraction' in out)
    check('scored categories say the read was not supplied',
          '⟨one-sentence read not supplied⟩' in out)
    check('no invented prose — summaries were passed empty',
          scorecard.record_from_card(card, entry)['summaries'] == {})
    check('takeaways passed empty',
          scorecard.record_from_card(card, entry)['takeaways'] == [])
    check('narrative score passed as None',
          scorecard.record_from_card(card, entry)['scores']['narrative'] is None)

    print()
    print('=== _display_actual: the unit the NAME declares ===')
    # 8965 ($M) printed raw beside a 9.50 bogey is the AMZN misread.
    rev_line = [l for l in out.splitlines() if 'FQ4 Revenue ($B)' in l][0]
    check('revenue shown in $B beside a $B bogey', '($B)' in rev_line,
          rev_line.strip()[-24:])
    check('and NOT as a raw $M magnitude', '8970' not in rev_line
          and '8965' not in rev_line, rev_line.strip()[-24:])

    print()
    print('=== flags are read from EITHER side of the pair ===')
    built = scorecard.record_from_card(card, entry)
    pre, act = built['preEarnings']['keyKPIs'], built['actuals']['keyKPIs']
    check('pre and actual arrays stay aligned 1:1',
          len(pre) == len(act) == len(entry['keyKPIs']),
          '%d/%d' % (len(pre), len(act)))
    flagged_pre = [i for i, k in enumerate(pre) if k.get('unverified')]
    flagged_act = [i for i, k in enumerate(act) if k.get('unverified')]
    check('unverified mirrored onto both sides',
          flagged_pre == flagged_act == [1, 2, 4, 5], flagged_pre)
    check('render marks them', out.count('⚠unverified') == 4,
          out.count('⚠unverified'))
    # A flag on only the ACTUAL side must still surface.
    c2 = dict(card)
    c2['keyKPIs'] = [dict(r) for r in card['keyKPIs']]
    c2['keyKPIs'][0]['unitAmbiguous'] = True
    b2 = scorecard.record_from_card(c2, entry)
    check('an actual-side unitAmbiguous propagates to pre',
          b2['preEarnings']['keyKPIs'][0]['unitAmbiguous'] is True)

    print()
    print('=== prose columns are capped, alignment survives ===')
    # SNDK's LTA row stores a whole sentence in street and bogey.
    prose_line = [l for l in out.splitlines()
                  if 'Multi-year contracted' in l][0]
    check('the qualitative row is truncated', '…' in prose_line or
          '...' in prose_line, prose_line.strip()[:44])
    # The cap is what holds the columns at FIXED offsets: metric [3:43],
    # street [44:54], bogey [55:65]. One uncapped prose cell shifts every
    # column to its right on that row and the table stops being readable.
    # NB: exclude the legend, which starts with three spaces and carries the
    # same glyphs. It is identified by the '=' gloss ("🟢 CLEAR = clears
    # bogey"), which no data row has.
    hero_lines = [l for l in out.splitlines()
                  if l.startswith('   ') and ' = ' not in l
                  and ('🟡' in l or '🟢' in l or '🔴' in l
                       or 'ungraded' in l)]
    check('found the hero data rows', len(hero_lines) == 7, len(hero_lines))
    bad = [l[3:20] for l in hero_lines
           if len(l[44:54]) != 10 or len(l[55:65]) != 10
           or l[43] != ' ' or l[54] != ' ']
    check('street/bogey cells sit at fixed 10-wide offsets on every row',
          not bad, bad)
    check('even the prose row respects the offsets',
          len(prose_line[44:54]) == 10 and len(prose_line[55:65]) == 10,
          '%r %r' % (prose_line[44:54], prose_line[55:65]))

    print()
    print('=== precedence is PASSED to render, never re-derived there ===')
    prec = scorecard.precedence_from_card(card)
    check('a verdict dict is built from the gate', isinstance(prec, dict), prec)
    check('rule 1 on SNDK', prec['rule'] == 1, prec.get('rule'))
    check('verdict carried through', prec['verdict'] == 'REINFORCES',
          prec.get('verdict'))
    check('overridesNovelty set', prec['overridesNovelty'] is True)
    check('detail names all three legs',
          all(x in prec['detail'] for x in ('cyclical sector',
                                            'peak-cycle language',
                                            'inline vs bogey')),
          prec['detail'][:44])
    check('detail names the dollar-★ fallback and its basis',
          'dollar ★ row' in prec['detail'] and 'declared' in prec['detail'])
    check('the peak-cycle quote is trimmed to word boundaries',
          '…' in prec['detail'] and 'ev guide' not in prec['detail'],
          prec['detail'][prec['detail'].find('peak-cycle'):][:52])

    print()
    print('=== render STRIKES the novelty line when overridden ===')
    check('novelty line still printed', 'forwardCommitment.novelty = NEW' in out)
    check('⛔ OVERRIDDEN by precedence rule 1', '⛔ OVERRIDDEN by precedence '
          'rule 1: REINFORCES' in out)
    check('the detail text appears under it', prec['detail'] in out)
    check('and it says to ignore the line above',
          'Ignore the novelty line above' in out)
    check('the bare SHORT VOID no longer stands unqualified',
          'PRECEDENCE NOT EVALUATED' not in out)

    print()
    print('=== passing nothing produces the explicit warning ===')
    bare = mod.render(scorecard.record_from_card(card, entry), fw, None)
    check('unqualified novelty is called out',
          'PRECEDENCE NOT EVALUATED' in bare)
    check('and says the line is UNQUALIFIED', 'UNQUALIFIED' in bare)
    check('so the conflict cannot render silently',
          '⛔ OVERRIDDEN' not in bare)

    print()
    print('=== a non-override still reports that it was evaluated ===')
    nbis = model.record_by_id('NBIS-2026Q2')
    e2 = model.prepare_from_record(nbis)
    c2 = S.score_release(
        P.parse_release(dict(msg_type='news_item', source='BUS', id='y',
                             headline='Nebius Reports Q2 2026 Results',
                             body=BODY)), e2, model)
    p2 = scorecard.precedence_from_card(c2)
    if p2:
        check('rule 2 does not override', p2['overridesNovelty'] is False,
              p2.get('rule'))
        o2 = scorecard.render_card(c2, e2, fw)
        check('render says "evaluated: no override"',
              'evaluated: no override' in o2)
        check('and does NOT print the not-evaluated warning',
              'PRECEDENCE NOT EVALUATED' not in o2)
    else:
        check('no precedence for a non-NEW record -> None', True, 'None')

    print()
    print('=== branchMatched workaround is GONE ===')
    import inspect
    src = inspect.getsource(scorecard)
    check('_branch_or_none helper removed', '_branch_or_none' not in src)
    check('the block is passed through as-is',
          "branchMatched=card.get('branchMatched')" in src)
    check('the scraper claims no branch (component 3 is locked by hand)',
          card['branchMatched'] is None, card.get('branchMatched'))
    check('render prints ⟨none recorded⟩, not ⟨unnamed⟩',
          'branch matched: ⟨none recorded⟩' in out
          and '⟨unnamed⟩' not in out)
    check('the reason moves to diagnostics',
          any('component 3' in d for d in scorecard.diagnostics(card)))

    print()
    print('=== diagnostics are ADDITIVE, not a restatement ===')
    diag = scorecard.diagnostics(card)
    check('diagnostics produced', bool(diag), len(diag))
    joined = '\n'.join(diag)
    check('HARD 10 appears only in diagnostics',
          'HARD 10' in joined and 'HARD 10' not in out)
    # The precedence VERDICT now renders inside the locked block, so it is no
    # longer diagnostics-only. What must not happen is diagnostics restating it.
    check('diagnostics do NOT restate the verdict text',
          'PEAK-CYCLE FADE WINS' in out
          and 'PEAK-CYCLE FADE WINS' not in joined)
    check('diagnostics carry only the supporting evidence',
          'clearance leg via' in joined and 'POST-HOC' in joined)
    check('diagnostics point at the card for the verdict itself',
          'verdict shown in the card above' in joined)
    check('the rendered block is not modified by diagnostics',
          scorecard.render_card(card, entry, fw) == out)

    print()
    print('=== ⚡ the asymmetric event flag is carried forward ===')
    n_flag = sum(1 for r in model.records if r.get('asymmetricEventFlag'))
    n_watch = sum(1 for r in model.records if r.get('asymmetricEventWatch'))
    # ★ FLOOR, not an exact pin: 22 when written, 23 after 2026-08-26.
    check('library carries at least 22 flags', n_flag >= 22, n_flag)
    check('and 5 weaker "watch" entries', n_watch == 5, n_watch)

    amd = model.record_by_id('AMD-2026Q1')
    e_amd = model.prepare_from_record(amd)
    check('prepare_from_record EXPOSES the flag',
          e_amd.get('asymmetricEventFlag') is not None)
    check('and the weaker watch field too',
          'asymmetricEventWatch' in e_amd)
    c_amd = S.score_release(
        P.parse_release(dict(msg_type='news_item', source='BUS', id='z',
                             headline='AMD Reports Q1 Results',
                             body='Total revenue of $7.44 billion, up 36%.')),
        e_amd, model)
    o_amd = scorecard.render_card(c_amd, e_amd, fw)
    check('the flag is passed into the record',
          scorecard.record_from_card(c_amd, e_amd)['asymmetricEventFlag']
          is not None)
    check('it renders at the very TOP, above HERO KPIs',
          o_amd.splitlines()[2].startswith('⚡ ASYMMETRIC EVENT FLAG'),
          o_amd.splitlines()[2][:34])
    check('above the hero table',
          o_amd.index('ASYMMETRIC EVENT FLAG') < o_amd.index('HERO KPIs'))

    # A record with no flag must not grow one.
    check('a record without a flag renders none',
          'ASYMMETRIC EVENT FLAG' not in out)
    # ★ Carried forward, never DETECTED -- firing it needs the three B6 gates
    # on a vague-but-quantitative forward claim, which is narrative judgment.
    import inspect
    src = inspect.getsource(S) + inspect.getsource(scorecard)
    check('nothing in the scraper DETECTS a flag from the release',
          'asymmetricEventFlag=' not in src.replace(
              "asymmetricEventFlag=entry.get('asymmetricEventFlag')", ''),
          'carried forward only')

    print()
    print('=== a missing renderer REFUSES rather than formatting locally ===')
    saved = scorecard._MODULE
    scorecard._MODULE = None
    real = config.LIB_DIR
    try:
        config.LIB_DIR = os.path.join(real, 'does-not-exist')
        try:
            scorecard.renderer()
            check('raises RendererMissing', False, 'no raise')
        except scorecard.RendererMissing as exc:
            check('raises RendererMissing', True)
            check('the message refuses to format locally',
                  'parallel formatter' in str(exc), str(exc)[:44])
    finally:
        config.LIB_DIR = real
        scorecard._MODULE = saved

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
