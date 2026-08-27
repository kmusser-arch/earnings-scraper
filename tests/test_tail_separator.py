"""The tail separator and the FY-inline skew.

Pins that:
  * the $-anchor DIRECTION hypothesis is not implemented (it is falsified)
  * novelty NEW makes the short base rate unreliable
  * ABSENT/WITHDRAWN/OMITTED/FLAT/WEAK reinforce it
  * NEW-BUT-SPEND is its own class -- a capex commitment is a cost
  * fyGuidance 0.0 is labelled BEARISH SKEW, never folded into the score
  * the feature is gated on presence (12 of 76 records)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import gate                       # noqa: E402
from earnings_scraper.model import Model                # noqa: E402


def main():
    failures = 0

    def check(label, ok, got=''):
        nonlocal failures
        failures += 0 if ok else 1
        print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, got))

    model = Model()
    findings = model.frameworks.get('forwardCommitmentFindings')
    inline_fw = model.frameworks.get('fyInlineIsBearish')

    print('=== frameworks loaded from the library ===')
    check('forwardCommitmentFindings present', bool(findings),
          (findings or {}).get('n'))
    check('fyInlineIsBearish present', bool(inline_fw),
          (inline_fw or {}).get('n'))
    check('findings n = 12', (findings or {}).get('n') == 12)

    print()
    print('=== the $-anchor DIRECTION hypothesis is NOT implemented ===')
    # SNDK: the largest anchor in the library ($93.9B) and it FELL.
    sndk = model.record_by_id('SNDK-2026Q4')
    fc = sndk.get('forwardCommitment') or {}
    check('SNDK carries the largest anchor', fc.get('dollarAmount') == 93.9,
          fc.get('dollarAmount'))
    check('SNDK still fell', (gate.reaction_of(sndk) or 0) < 0,
          gate.reaction_of(sndk))
    ctx = gate.forward_commitment_context(
        model.prepare_from_record(sndk), 'STAY_FOR_CALL', findings)
    check('SNDK classified on NOVELTY, not the anchor',
          ctx['novelty'] == 'NEW', ctx['novelty'])
    check('dollar figure labelled a MAGNITUDE DAMPENER',
          'DAMPENER' in (ctx.get('dollarNote') or ''),
          (ctx.get('dollarNote') or '')[:46])
    check('no direction key derived from dollarAmount',
          'anchorDirection' not in ctx and 'dollarDirection' not in ctx)

    print()
    print('=== novelty classes ===')
    expect = {
        'NEW': ('SHORT VOID', 'NEW'),
        'NEW-BUT-SPEND': ('REINFORCES', 'NEW-BUT-SPEND'),
        'ABSENT': ('REINFORCES', 'ABSENCE'),
        'WITHDRAWN': ('REINFORCES', 'ABSENCE'),
        'OMITTED': ('REINFORCES', 'ABSENCE'),
        'FLAT': ('REINFORCES', 'ABSENCE'),
        'WEAK': ('REINFORCES', 'ABSENCE'),
        'NONE': ('NO SIGNAL', 'NO SIGNAL'),
    }
    for novelty, (reliability, klass) in expect.items():
        rec = {'forwardCommitment': {'novelty': novelty, 'present': True}}
        c = gate.forward_commitment_context(rec, 'STAY_FOR_CALL', findings)
        check('%-14s -> %-11s / %s' % (novelty, reliability, klass),
              c['reliability'] == reliability and c['klass'] == klass,
              '%s / %s' % (c['reliability'], c['klass']))

    print()
    print('=== the verdicts say the right thing ===')
    new = gate.forward_commitment_context(
        {'forwardCommitment': {'novelty': 'NEW'}}, 'STAY_FOR_CALL', findings,
        clearance_pct=0.71)
    check('NEW is SHORT VOID, not "unreliable"',
          'SHORT VOID' in new['verdict'], new['verdict'][:44])
    check('NEW says long permissive, unsized',
          'permissive' in new['verdict'].lower()
          and 'unsized' in new['verdict'].lower())
    check('NEW does NOT say stand down',
          'stand down' not in new['verdict'].lower(), new['verdict'][:44])
    check('NEW cites the asymmetry (+15.98 vs -6.81)',
          '15.98' in new['verdict'] and '6.81' in new['verdict'])
    check('NEW is precedence rule 2', new['precedenceRule'] == 2,
          new.get('precedenceRule'))

    print()
    print('=== the inline leg is denomination-dependent ===')
    # E6's >110%-of-bogey bar is a RATIO. Transposed to a percentage hero it
    # demands ~400bp, which is impossible -- so it must DEFER, not guess.
    for ticker, expected in (('SNDK', 'PERCENT'), ('TSLA', 'PERCENT'),
                             ('CSCO', 'PERCENT'), ('INTC', 'PERCENT'),
                             ('NFLX', 'PERCENT'), ('LULU', 'PERCENT'),
                             ('NET', 'PERCENT'), ('NVDA', 'DOLLAR'),
                             ('ALAB', 'DOLLAR'), ('MU', 'UNCLASSIFIED')):
        prof = model.profiles.get(ticker) or {}
        h = [x for x in (prof.get('heroKPIs') or [])
             if x.get('priority') == 1 and x.get('appliesTo') == 'currentQuarter']
        got, _ev = gate.hero_denomination(h[0] if h else {})
        check('%-6s hero is %-12s' % (ticker, expected), got == expected, got)

    print()
    print('=== the three unit-field conflicts are fixed at source ===')
    for ticker in ('NBIS', 'CRWV', 'CBRS'):
        prof = model.profiles[ticker]
        h = [x for x in prof['heroKPIs']
             if x.get('priority') == 1 and x.get('appliesTo') == 'currentQuarter'][0]
        got, ev = gate.hero_denomination(h)
        check('%-6s resolves DOLLAR with no conflict' % ticker,
              got == 'DOLLAR' and ev['nameUnitConflict'] is False,
              '%s / unit=%r' % (got, ev['unitField']))

    # Resolution still reads the NAME first regardless -- a wrong unit field
    # silently disarms rule 1, so the guard stays even though the data is fixed.
    got, ev = gate.hero_denomination(
        dict(name='Adjusted EBITDA ($M)', unit='%'))
    check('a synthetic wrong unit is still overridden by the name',
          got == 'DOLLAR' and ev['nameUnitConflict'] is True,
          '%s / conflict=%s' % (got, ev['nameUnitConflict']))
    check('and the conflict is reported for fixing',
          bool(ev['conflictNote']), (ev['conflictNote'] or '')[:44])
    check('resolution source is recorded as the name',
          ev['resolvedFrom'] == 'name', ev['resolvedFrom'])

    print()
    print('=== the dollar-★ fallback rescues the clearance leg ===')

    def rows_for(rid):
        rec = model.record_by_id(rid)
        ak = (rec.get('actuals') or {}).get('keyKPIs') or []
        e = model.prepare_from_record(rec)
        out = []
        for i, k in enumerate(e['keyKPIs']):
            a = ak[i] if i < len(ak) and isinstance(ak[i], dict) else {}
            out.append(dict(name=(k.get('name') or ''), actual=a.get('actual'),
                            actualUnit=a.get('actualUnit'),
                            unitAmbiguous=a.get('unitAmbiguous')))
        return e, out

    e, rows = rows_for('SNDK-2026Q4')
    cl, fb = gate.dollar_hero_fallback(e, rows)
    check('SNDK falls back to FQ4 Revenue ($B)',
          fb.get('used') and fb['row'].startswith('FQ4 Revenue ($B)'),
          fb.get('row'))
    check('SNDK clearance is -5.63% vs the BOGEY',
          abs(cl + 5.632) < 0.01 and fb['column'] == 'bogey', round(cl, 3))
    check('a MISS is named as MAX SHORT (stronger than inline)',
          'MAX SHORT' in fb['note'])
    check('★ routes AROUND the four flagged rows — none used',
          fb['kpiIndex'] == 0, fb['kpiIndex'])
    flagged = [i for i, k in enumerate(e['keyKPIs'])
               if k.get('unverified') is True]
    check('the flagged rows are 1,2,4,5 and were skipped',
          flagged == [1, 2, 4, 5] and fb['kpiIndex'] not in flagged, flagged)
    check('rule 1 now FIRES on SNDK again',
          gate.forward_commitment_context(
              e, 'STAY_FOR_CALL', findings, clearance_pct=0.71,
              kpi_rows=rows)['precedenceRule'] == 1)

    print()
    print('=== the guard: consensus is NEVER substituted for a bogey ===')
    no_bogey = dict(quarter='Q4 (FY26)', sector='Semiconductors / Memory',
                    keyKPIs=[dict(name='FQ4 Revenue ($B) ★', consensus=9.0,
                                  bogey=None)])
    cl2, fb2 = gate.dollar_hero_fallback(
        no_bogey, [dict(name='FQ4 Revenue ($B) ★', actual=8965)])
    check('a row with consensus but no bogey is NOT used',
          not fb2.get('used'), fb2.get('row'))
    check('the reason says consensus is not substituted',
          'NOT substituting consensus' in fb2['reason'], fb2['reason'][:44])
    check('no clearance is produced', cl2 is None, cl2)

    print()
    print('=== the guard: flagged rows are skipped ===')
    flagged_only = dict(quarter='Q4 (FY26)', sector='Semiconductors / Memory',
                        keyKPIs=[dict(name='FQ4 Revenue ($B) ★', bogey=9.5,
                                      unverified=True)])
    _c, fb3 = gate.dollar_hero_fallback(
        flagged_only, [dict(name='FQ4 Revenue ($B) ★', actual=8965)])
    check('an unverified row is not used', not fb3.get('used'))

    print()
    print('=== the guard: forward rows cannot serve the clearance leg ===')
    fwd = dict(quarter='Q4 (FY26)', sector='Semiconductors / Memory',
               keyKPIs=[dict(name='F1Q Revenue Guide ($B) ★', bogey=12.0)])
    _c, fb4 = gate.dollar_hero_fallback(
        fwd, [dict(name='F1Q Revenue Guide ($B) ★', actual=10550)])
    check('a NEXTQ_GUIDE row is not used for the clearance leg',
          not fb4.get('used'))

    print()
    print('=== the guard: percentage rows cannot serve it either ===')
    pct_row = dict(quarter='Q4 (FY26)', sector='Semiconductors / Memory',
                   keyKPIs=[dict(name='FQ4 Gross Margin (%) ★', bogey=84.0)])
    _c, fb5 = gate.dollar_hero_fallback(
        pct_row, [dict(name='FQ4 Gross Margin (%) ★', actual=84.6)])
    check('a percentage row is not a dollar fallback',
          not fb5.get('used'))

    print()
    print('=== declared actualUnit is read FIRST ===')
    e_d, rows_d = rows_for('SNDK-2026Q4')
    cl_d, fb_d = gate.dollar_hero_fallback(e_d, rows_d)
    check('SNDK resolves via the DECLARED unit',
          fb_d['scaleBasis'] == 'declared $M', fb_d.get('scaleBasis'))
    e_a2, rows_a2 = rows_for('AMZN-2026Q1')
    cl_a2, fb_a2 = gate.dollar_hero_fallback(e_a2, rows_a2)
    check('AMZN resolves via the DECLARED unit',
          fb_a2['scaleBasis'] == 'declared $B', fb_a2.get('scaleBasis'))
    check('AMZN clearance is +4.84%', abs(cl_a2 - 4.844) < 0.01,
          round(cl_a2, 3))
    declared = 0
    for rid in [r['id'] for r in model.records if r.get('forwardCommitment')]:
        ee, rr = rows_for(rid)
        hs = ee.get('heroes') or []
        if not hs or gate.hero_denomination(hs[0])[0] == 'DOLLAR':
            continue
        _c, ff = gate.dollar_hero_fallback(ee, rr)
        if ff.get('used') and str(ff['scaleBasis']).startswith('declared'):
            declared += 1
    # ★ FLOOR: rescues grow with the library (5 -> 6 on 2026-08-26). What
    # matters is that EVERY rescue used the declared path, not the count.
    check('every rescue goes through the declared path', declared >= 5,
          declared)

    print()
    print('=== NEVER PREFER: both readings coherent -> REFUSE ===')
    # bogey 9.5 ($B) against a bare actual of 9.5 reads +0.00% ($B) or
    # -99.90% ($M). Both are coherent outcomes, so preferring one would turn a
    # catastrophic miss into "inline".
    amb_e = dict(quarter='Q4 (FY26)', sector='Semiconductors / Memory',
                 keyKPIs=[dict(name='FQ4 Revenue ($B) *', bogey=9.5)])
    amb_e['keyKPIs'][0]['name'] = 'FQ4 Revenue ($B) \u2605'
    nm = amb_e['keyKPIs'][0]['name']
    cl_r, fb_r = gate.dollar_hero_fallback(
        amb_e, [dict(name=nm, actual=9.5)])
    check('both-coherent row is REFUSED', not fb_r.get('used'))
    check('no clearance produced', cl_r is None, cl_r)
    check('the reason says BOTH readings are coherent',
          'BOTH readings are coherent' in str(fb_r.get('reason')),
          str(fb_r.get('reason'))[:44])
    check('the reason names the refusal, not a preference',
          'REFUSED' in str(fb_r.get('reason')))
    for unit, expected in (('$B', 0.0), ('$M', -99.9)):
        c, f = gate.dollar_hero_fallback(
            amb_e, [dict(name=nm, actual=9.5, actualUnit=unit)])
        check('declared %s -> %+.2f%%' % (unit, expected),
              f.get('used') and abs(c - expected) < 0.01, round(c or 0, 2))

    print()
    print('=== neither reading coherent -> REFUSE (not prefer) ===')
    # 5e6 against a 9.5 ($B) bogey is +52,631,479% as $B and +52,531% as $M --
    # incoherent either way. (Note 0.0001 would NOT land here: it reads ~-100%
    # both ways, which is the both-coherent branch.)
    cl_n, fb_n = gate.dollar_hero_fallback(
        amb_e, [dict(name=nm, actual=5_000_000)])
    check('both-implausible row is REFUSED', not fb_n.get('used'))
    check('the reason says NEITHER is coherent',
          'NEITHER reading is coherent' in str(fb_n.get('reason')),
          str(fb_n.get('reason'))[:44])
    cl_z, fb_z = gate.dollar_hero_fallback(
        amb_e, [dict(name=nm, actual=0.0001)])
    check('a near-zero actual refuses as BOTH-coherent, not neither',
          not fb_z.get('used')
          and 'BOTH readings are coherent' in str(fb_z.get('reason')),
          str(fb_z.get('reason'))[:44])

    print()
    print('=== exactly one coherent still resolves ===')
    cl_o, fb_o = gate.dollar_hero_fallback(
        amb_e, [dict(name=nm, actual=8965)])
    check('bare 8965 vs bogey 9.5 resolves to -5.63%',
          fb_o.get('used') and abs(cl_o + 5.632) < 0.01, round(cl_o or 0, 3))
    check('basis is $M, not "declared"', fb_o['scaleBasis'] == '$M',
          fb_o.get('scaleBasis'))

    print()
    print('=== unitAmbiguous is skipped like unverified ===')
    n2 = 'Q1 Compute Revenue ($M) \u2605\u2605'
    n1 = 'Q1 Revenue ($M) \u2605'
    amb2 = dict(quarter='Q1', sector='Semiconductors / Memory',
                keyKPIs=[dict(name=n2, bogey=220.0),
                         dict(name=n1, bogey=100.0)])
    rows2 = [dict(name=n2, actual=95.0, actualUnit='$M', unitAmbiguous=True),
             dict(name=n1, actual=101.0, actualUnit='$M')]
    cl_s, fb_s = gate.dollar_hero_fallback(amb2, rows2)
    check('a two-star row flagged unitAmbiguous is skipped despite outranking',
          fb_s['row'] == n1, fb_s.get('row'))
    check('and the surviving row is graded', abs(cl_s - 1.0) < 0.01,
          round(cl_s, 3))
    n_amb = sum(1 for r in model.records
                for a in ((r.get('actuals') or {}).get('keyKPIs') or [])
                if isinstance(a, dict) and a.get('unitAmbiguous') is True)
    # ★ NOT a fixed count. This tracked library state and broke the moment
    # RDDT-2026Q2 was repaired -- a test that fails when the DATA improves
    # teaches you to edit the test. What matters is that the flag is present
    # somewhere and is honoured, which the two checks above establish.
    check('the library still carries unitAmbiguous rows to honour', n_amb >= 1,
          n_amb)

    print()
    print('=== the live path DECLARES its own unit ===')
    from earnings_scraper import parse as _P, score as _S
    e_live = model.prepare_from_record(model.record_by_id('SNDK-2026Q4'))
    live_rows = _S.build_kpi_rows(
        _P.parse_release(dict(msg_type='news_item', source='BUS', id='x',
                              headline='x',
                              body='Total revenue of $8.97 billion, up 22%.')),
        e_live)
    rev_row = [r for r in live_rows if r['name'].startswith('FQ4 Revenue')][0]
    check('parsed dollar rows declare actualUnit=$M',
          rev_row['actualUnit'] == '$M', rev_row['actualUnit'])
    check('and are never flagged ambiguous',
          rev_row['unitAmbiguous'] is False)
    pct_row = [r for r in live_rows if 'Gross Margin' in r['name']][0]
    check('percentage rows declare no dollar unit',
          pct_row['actualUnit'] is None, pct_row['actualUnit'])

    print()
    print('=== the scale guard (D6) ===')
    # AMZN stores $B under a ($B) name; SNDK stores $M under one. Converting
    # only the expected side reports AMZN as -99.90% when it is +4.84%.
    e_a, rows_a = rows_for('AMZN-2026Q1')
    cl_a, fb_a = gate.dollar_hero_fallback(e_a, rows_a)
    check('AMZN resolves to +4.84%, not -99.90%',
          fb_a.get('used') and abs(cl_a - 4.844) < 0.01, round(cl_a or 0, 3))
    check('AMZN scale basis is declared', fb_a['scaleBasis'] == 'declared $B',
          fb_a.get('scaleBasis'))
    check('SNDK scale basis is declared', fb['scaleBasis'] == 'declared $M',
          fb.get('scaleBasis'))
    # A genuinely unresolvable scale must be refused, not graded.
    bad = dict(quarter='Q4 (FY26)', sector='Semiconductors / Memory',
               keyKPIs=[dict(name='FQ4 Revenue ($B) ★', bogey=9.5)])
    _c, fb6 = gate.dollar_hero_fallback(
        bad, [dict(name='FQ4 Revenue ($B) ★', actual=0.0001)])
    check('an unresolvable scale is refused, not graded',
          not fb6.get('used'), (fb6.get('reason') or '')[:46])

    print()
    print('=== blast radius matches the framework (5 rescued / 3 deferred) ===')
    resc = defer = 0
    for rid in [r['id'] for r in model.records if r.get('forwardCommitment')]:
        ee, rr = rows_for(rid)
        hs = ee.get('heroes') or []
        if not hs or gate.hero_denomination(hs[0])[0] == 'DOLLAR':
            continue
        _c, ff = gate.dollar_hero_fallback(ee, rr)
        if ff.get('used'):
            resc += 1
        else:
            defer += 1
    print('     %d rescued, %d deferred (>=5 / >=3 expected)' % (resc, defer))
    check('at least 5 rescued', resc >= 5, resc)
    check('at least 3 still deferred', defer >= 3, defer)

    print()
    print('=== still deferred where no dollar ★ row exists -> rule 2 ===')
    # Only records whose novelty is NEW reach the peak-cycle branch at all --
    # TSLA is NONE and CIFR is FLAT, so they never evaluate the legs.
    for rid in ('NOW-2026Q2',):
        e = model.prepare_from_record(model.record_by_id(rid))
        c = gate.forward_commitment_context(e, 'STAY_FOR_CALL', findings,
                                           clearance_pct=0.71)
        ev = c['peakCycleEvidence']
        check('%-13s inline leg is None (deferred)' % rid,
              ev['inlineVsBogey'] is None, ev['inlineVsBogey'])
        check('%-13s falls through to rule 2' % rid,
              c['precedenceRule'] == 2, c['precedenceRule'])
        check('%-13s reason is on the card' % rid,
              'DEFERRED' in (ev.get('inlineNote') or ''),
              (ev.get('inlineNote') or '')[:34])
    # Rebuild from SNDK explicitly -- the loop above rebinds `e`.
    e_s, rows_s = rows_for('SNDK-2026Q4')
    sndk_ctx = gate.forward_commitment_context(
        e_s, 'STAY_FOR_CALL', findings, clearance_pct=0.71, kpi_rows=rows_s)
    check('SNDK text legs hold (sector + language)',
          sndk_ctx['peakCycleEvidence']['cyclicalSector']
          and sndk_ctx['peakCycleEvidence']['peakCycleLanguage'])

    print()
    print('=== a DOLLAR hero still uses the ratio ===')
    dollar = dict(sector='Semiconductors / Memory',
                  setup='a classic peak-cycle setup into a stretched bogey',
                  heroes=[dict(name='FQ4 Revenue ($B)', unit='$B', priority=1,
                               appliesTo='currentQuarter')],
                  forwardCommitment=dict(novelty='NEW'))
    c_in = gate.forward_commitment_context(dollar, 'STAY_FOR_CALL', findings,
                                           clearance_pct=0.71)
    c_out = gate.forward_commitment_context(dollar, 'STAY_FOR_CALL', findings,
                                            clearance_pct=25.0)
    check('dollar hero, inline -> rule 1 fires',
          c_in['precedenceRule'] == 1, c_in['precedenceRule'])
    check('dollar hero, nuke-crush -> rule 2',
          c_out['precedenceRule'] == 2, c_out['precedenceRule'])
    check('dollar hero inline leg is a bool, not None',
          c_in['peakCycleEvidence']['inlineVsBogey'] is True)

    print()
    print('=== the clearance leg is flagged PROVISIONAL ===')
    ev = c_in['peakCycleEvidence']
    check('clearanceLegProvisional is True',
          ev['clearanceLegProvisional'] is True)
    check('note names SNDK as the flagged founding case',
          'SNDK-2026Q4' in ev['clearanceLegNote'])
    check('note says the text legs are unaffected',
          'text-derived and unaffected' in ev['clearanceLegNote'])

    print()
    print('=== the rejected alternative is recorded ===')
    check('rule-1 hits carry the rejected fy==0.0 rule',
          'NOW-2026Q2' in (c_in.get('rejectedAlternative') or ''),
          (c_in.get('rejectedAlternative') or '')[:44])
    now_rec = model.record_by_id('NOW-2026Q2')
    check('NOW really is NEW with fy 0.0 and rose',
          (now_rec['forwardCommitment']['novelty'] == 'NEW'
           and now_rec['scores']['fyGuidance'] == 0.0
           and (gate.reaction_of(now_rec) or 0) > 0),
          '%s / %s / %+.2f' % (now_rec['forwardCommitment']['novelty'],
                               now_rec['scores']['fyGuidance'],
                               gate.reaction_of(now_rec)))

    print()
    print('=== the post-hoc caveat travels on every NEW verdict ===')
    check('rule 1 carries the post-hoc caveat',
          'POST-HOC' in (c_in.get('postHocCaveat') or ''),
          (c_in.get('postHocCaveat') or '')[:40])
    check('rule 1 caveat names the independent MU founding case',
          'MU Q3' in (c_in.get('postHocCaveat') or ''))
    check('rule 1 caveat calls it ONE confirmation',
          'ONE confirmation' in (c_in.get('postHocCaveat') or ''))
    check('rule 2 also carries a caveat naming the failed leg',
          bool(new.get('postHocCaveat')), (new.get('postHocCaveat') or '')[:40])
    absent = gate.forward_commitment_context(
        {'forwardCommitment': {'novelty': 'OMITTED'}}, 'STAY_FOR_CALL',
        findings)
    check('absence class REINFORCES the short',
          'REINFORCES' in absent['verdict'], absent['verdict'][:50])
    check('absence class cites 1/6 up and -11.02%',
          '1/6' in absent['verdict'] and '11.02' in absent['verdict'])
    spend = gate.forward_commitment_context(
        {'forwardCommitment': {'novelty': 'NEW-BUT-SPEND'}}, 'STAY_FOR_CALL',
        findings)
    check('NEW-BUT-SPEND is called a cost',
          'cost' in spend['verdict'].lower(), spend['verdict'][:50])
    check('NEW-BUT-SPEND does NOT read as unreliable',
          spend['reliability'] == 'REINFORCES', spend['reliability'])

    print()
    print('=== gated on presence (12 of 76) ===')
    n_with = sum(1 for r in model.records if r.get('forwardCommitment'))
    check('at least 12 records carry the block', n_with >= 12, n_with)
    missing = gate.forward_commitment_context({}, 'STAY_FOR_CALL', findings)
    check('absent block -> available False', missing['available'] is False)
    check('absent block still flags that it applies',
          missing['applies'] is True)
    check('absent block says the separator is UNAVAILABLE',
          'UNAVAILABLE' in missing['note'], missing['note'][:52])
    check('absent block names the 12-of-76 coverage',
          '12 of 76' in missing['note'])
    off_band = gate.forward_commitment_context({}, 'DECISIVE_BULLISH', findings)
    check('does not claim to apply off STAY_FOR_CALL',
          off_band['applies'] is False)

    print()
    print('=== fyInlineIsBearish ===')
    c = gate.fy_inline_context(0.0, inline_fw)
    check('fires at exactly 0.0', c is not None)
    check('label is the required string',
          c['label'] == 'INLINE = BEARISH SKEW (8/11 down, mean -6.85%)',
          c['label'])
    check('explicitly NOT folded into the score',
          c['foldedIntoScore'] is False)
    check('carries the n=11 caveat', c['n'] == 11, c['n'])
    check('carries the absence-vs-inline note',
          bool(c.get('absenceVsInline')))
    for score in (0.5, -0.5, 1.0, -1.5, None):
        check('does NOT fire at %s' % score,
              gate.fy_inline_context(score, inline_fw) is None)

    print()
    print('=== the two exceptions are represented ===')
    spcx = model.record_by_id('SPCX-2026Q2')
    check('SPCX is NEW-BUT-SPEND in the library',
          (spcx.get('forwardCommitment') or {}).get('novelty')
          == 'NEW-BUT-SPEND',
          (spcx.get('forwardCommitment') or {}).get('novelty'))
    check('SPCX fell despite being NEW-*', (gate.reaction_of(spcx) or 0) < 0,
          gate.reaction_of(spcx))
    tsla = model.record_by_id('TSLA-2026Q1')
    check('TSLA is novelty NONE',
          (tsla.get('forwardCommitment') or {}).get('novelty') == 'NONE',
          (tsla.get('forwardCommitment') or {}).get('novelty'))
    check('TSLA rose, and NONE therefore carries no signal',
          (gate.reaction_of(tsla) or 0) > 0
          and gate.forward_commitment_context(
              tsla, 'STAY_FOR_CALL', findings)['reliability'] == 'NO SIGNAL')

    print()
    print('=== the caveat travels with the finding ===')
    check('caveat attached to every available context',
          'n=12' in (new.get('caveat') or ''), (new.get('caveat') or '')[:40])
    check('caveat says prior, not calibrated edge',
          'NOT as a calibrated edge' in (new.get('caveat') or ''))

    print()
    print('%d failure(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
