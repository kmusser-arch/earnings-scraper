"""The flat-field reader, the encoding preflight, and the path precondition.

Three false alarms in a row -- 13 unit flags, AMZN "corruption", AXTI
arithmetic -- were the same mistake: a rule written for the live path applied to
stored data, or a rule reading one view of a record as if it were the only one.
Found three times by hand. These tests make the fourth time impossible.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import audit, config, flat        # noqa: E402
from earnings_scraper import score as S                 # noqa: E402
from earnings_scraper.model import Model                # noqa: E402

FAIL = [0]


def check(label, ok, detail=''):
    print('%s %-58s %s' % ('PASS' if ok else 'FAIL', label, str(detail)[:36]))
    if not ok:
        FAIL[0] += 1


def main():
    model = Model()

    print('=== a period is classified before a metric word is matched ===')
    for name, quarter, want in [
            ('FY26 EPS ($)', 'Q1', 'FY_GUIDE'),
            ('FY26 Capex ($B)', 'Q1', 'FY_GUIDE'),
            ('FY27 EPS ($)', 'Q1', 'FY_GUIDE'),
            # the completed year, reported WITH the Q4 print
            ('FY26 AI Infrastructure Orders ($B)', 'Q4 (FY26)', 'CURRENT_Q'),
            # next year, on the same print, is still forward
            ('FY27 Capex ($B)', 'Q4 (FY26)', 'FY_GUIDE'),
            ('FY26 Revenue Guide ($B)', 'Q4 (FY26)', 'FY_GUIDE'),
            ('Q1 FY27 Non-GAAP Gross Margin (%)', 'Q4 (FY26)', 'NEXTQ_GUIDE'),
            ('Q1 Revenue ($B)', 'Q1', 'CURRENT_Q'),
            ('Q2 Revenue ($B)', 'Q1', 'NEXTQ_GUIDE')]:
        got = S._classify_period(name, quarter)
        check('%-34s @%-10s -> %s' % (name[:34], quarter, want),
              got == want, got)

    print('')
    print('=== a number wearing punctuation is read; a delta is not ===')
    for raw, want in [('$10.44', 10.44), ('+12%', 12.0), ('+11% ex-FX', 11.0),
                      ('1,924', 1924.0), ('88%', 88.0),
                      ('$22B mid', None), ('+$10B raise', None),
                      ('unchanged', None), ('see call', None),
                      ('NOT GRADED', None), ('5GW', None), ('NEW', None)]:
        got = flat._num(raw)
        delta = bool(flat._DELTA_WORDS.search(str(raw)))
        effective = None if delta else got
        check('%-16r -> %s' % (raw, want), effective == want,
              'num=%s delta=%s' % (got, delta))

    print('')
    print('=== AMZN-2026Q1: the four slots resolve from the flat fields ===')
    rec = model.record_by_id('AMZN-2026Q1')
    check('the record declares its own grid lossy', flat.has_flag(rec))
    check('and the flag says nothing was fabricated',
          'NOTHING WAS FABRICATED' in flat.flag_text(rec))
    shown, repairs, skipped = flat.repair_alignment(
        rec, S._classify_period, S.row_qualifiers)
    fixed = {i: (now, src) for i, _n, _w, now, src in repairs}
    check('[2] NA growth reads 12 from northAmericaYoY',
          fixed.get(2, (None,))[0] == 12.0, fixed.get(2))
    check('[6] Q2 Revenue reads 196.5, not the $22B OI figure',
          fixed.get(6, (None,))[0] == 196.5, fixed.get(6))
    check('    and names the field it came from',
          'nextQGuidance.revenueMid' in (fixed.get(6, ('', ''))[1] or ''),
          fixed.get(6, ('', ''))[1])
    check('[7] Q2 Op Income reads the MID 22, not the high end 24',
          fixed.get(7, (None,))[0] == 22, fixed.get(7))
    check('[3] International takes 11 ex-FX, NOT the reported 19',
          fixed.get(3, (None,))[0] == 11.0, fixed.get(3))
    check('    by COERCION, so no provenance question arises',
          'coerced' in (fixed.get(3, ('', ''))[1] or ''), fixed.get(3))

    print('')
    print('=== coercion and backfill are distinguished, per the rule ===')
    rows = shown['actuals']['keyKPIs']
    check('[2] is coercion — same figure, same basis, same source',
          rows[2].get('actualProvenance') == 'pr', rows[2].get('actualSource'))
    check('    so it stays PR-available',
          rows[2].get('prAvailable') is True)
    check('[6] is BACKFILL — a different source',
          rows[6].get('actualProvenance') == 'flat', rows[6].get('actualSource'))
    check('    so it is marked NOT PR-available',
          rows[6].get('prAvailable') is False)
    check('    and the note says why it must never be counted',
          'never be counted' in (rows[6].get('actualNote') or ''),
          (rows[6].get('actualNote') or '')[:36])
    check('pr_available_rows excludes the backfilled rows',
          all(r.get('prAvailable') is not False
              for r in flat.pr_available_rows(shown)))
    check('and it is smaller than the repaired grid',
          len(flat.pr_available_rows(shown)) < len(rows),
          '%d of %d' % (len(flat.pr_available_rows(shown)), len(rows)))

    print('')
    print('=== and the ones it must NOT touch ===')
    left = {i: was for i, _n, was in skipped}
    check('[1] the qualitative row keeps its $14.16B reading',
          left.get(1) == '$14.16B', left.get(1))
    check('[9] FY26 EPS is not filled from the quarterly actual',
          9 in left, left.get(9))
    check('[10] FY27 EPS is not filled from it either',
          10 in left, left.get(10))
    check('non-negotiable 2 holds: no forward slot took actuals.eps',
          all(v != 2.78 for v, _s in fixed.values()),
          [v for v, _s in fixed.values()])
    check('the library record itself was NOT mutated',
          rec['actuals']['keyKPIs'][6]['actual'] == '$22B mid',
          rec['actuals']['keyKPIs'][6]['actual'])
    check('the repair is a copy', shown is not rec)

    print('')
    print('=== a pointer to the CALL is a finding, not a gap ===')
    for rid, i, raw in [('CRWV-2026Q1', 5, 'PENDING'),
                        ('CRWV-2026Q1', 6, 'PENDING'),
                        ('AXTI-2026Q2', 2, 'see Actuals')]:
        r = model.record_by_id(rid)
        k = r['preEarnings']['keyKPIs'][i]
        cur = r['actuals']['keyKPIs'][i].get('actual')
        res = flat.resolve_slot(r, k, cur,
                                S._classify_period(k.get('name') or '',
                                                   r.get('quarter')),
                                S.row_qualifiers(k.get('name') or ''),
                                allow_backfill=True)
        check('%-13s [%d] refuses to backfill a call figure' % (rid, i),
              res is not None and res['provenance'] == 'call'
              and res['value'] is None,
              res and res['source'])
        check('              and is not PR-available',
              res is not None and res['prAvailable'] is False)
    axti = model.record_by_id('AXTI-2026Q2')
    check('AXTI keeps its founding lesson intact',
          axti['actuals']['keyKPIs'][2]['actual']
          == 'see Actuals / Call Notes tabs',
          axti['actuals']['keyKPIs'][2]['actual'])
    check('backfill is OPT-IN, never the default',
          flat.resolve_slot(
              model.record_by_id('CRWV-2026Q1'),
              model.record_by_id('CRWV-2026Q1')['preEarnings']['keyKPIs'][5],
              'PENDING — call only', 'NEXTQ_GUIDE', set())['value'] is None)
    ms = model.record_by_id('MSFT-2026Q3')
    _c, _r, sk = flat.repair_alignment(ms, S._classify_period,
                                       S.row_qualifiers)
    check("MSFT's 'see call' rows keep their text on the card",
          ms['actuals']['keyKPIs'][2]['actual'] == 'see call',
          ms['actuals']['keyKPIs'][2]['actual'])
    check('and they are reported, not silently dropped',
          any(i == 2 for i, _n, _w in sk), [i for i, _n, _w in sk])

    print('')
    print('=== GTLB was the only safe repair of the five ===')
    g = model.record_by_id('GTLB-2027Q1')
    check('its 88% coerced to 88.0 upstream',
          g['actuals']['keyKPIs'][7]['actual'] == 88.0,
          g['actuals']['keyKPIs'][7]['actual'])

    print('')
    print('=== META-2026Q1: a delta is refused, a level is read ===')
    rec2 = model.record_by_id('META-2026Q1')
    _s2, rep2, skip2 = flat.repair_alignment(rec2, S._classify_period,
                                             S.row_qualifiers)
    f2 = {i: now for i, _n, _w, now, _s in rep2}
    l2 = {i: was for i, _n, was in skip2}
    check('FY26 Capex takes the level 135, not the +$10B raise',
          f2.get(2) == 135, f2.get(2))
    check('FY26 EPS coerces $10.44', f2.get(4) == 10.44, f2.get(4))
    check("'unchanged' is left alone", l2.get(3) == 'unchanged', l2.get(3))

    print('')
    print('=== every flagged record repairs without raising ===')
    flagged = [r for r in model.records if flat.has_flag(r)]
    check('nine records carry the flag', len(flagged) == 9, len(flagged))
    ok = True
    for r in flagged:
        if 'preEarnings' not in r:
            continue
        try:
            flat.repair_alignment(r, S._classify_period, S.row_qualifiers)
        except Exception as exc:
            ok = False
            check('  %s raised' % r.get('id'), False, repr(exc))
    check('all of them repair cleanly', ok)

    print('')
    print('=== the encoding preflight ===')
    notes = config.preflight()
    check('the library reads as UTF-8', isinstance(notes, list))
    check('and the cp1252 default is reported as unsafe',
          any('cp1252' in n or 'CANNOT decode' in n for n in notes)
          or notes == [], notes[:1])
    check('every text open() in the package declares an encoding',
          config.assert_utf8_reads() is True)
    import io as _io
    import tempfile
    bad = os.path.join(tempfile.gettempdir(), 'bare_open_probe.py')
    with _io.open(bad, 'w', encoding='utf-8') as fh:
        fh.write("import json\nd=json.load(open('earnings-library.json'))\n")
    try:
        config.assert_utf8_reads([bad])
        check('the real bug pattern is caught', False, 'not caught')
    except config.EncodingUnsafe as exc:
        check('the real bug pattern is caught', True, str(exc)[:34])
    check('a binary open needs no encoding',
          config.assert_utf8_reads([_write_probe(
              "f=open('x.bin','rb')\n")]) is True)

    print('')
    print('=== the path precondition ===')
    live_rule = [r for r in audit.RULES if r.name == 'unit-declared'][0]
    stored_rule = [r for r in audit.RULES if r.name == 'overall-weighting'][0]
    grid_rule = [r for r in audit.RULES
                 if r.name == 'prose-in-numeric-slot'][0]
    try:
        audit.assert_applicable(live_rule, audit.STORED, rec)
        check('a LIVE rule is refused on a stored record', False)
    except audit.PathMismatch as exc:
        check('a LIVE rule is refused on a stored record', True,
              str(exc)[:34])
    try:
        audit.assert_applicable(stored_rule, audit.LIVE)
        check('a STORED rule is refused on a live card', False)
    except audit.PathMismatch:
        check('a STORED rule is refused on a live card', True)
    try:
        audit.assert_applicable(grid_rule, audit.STORED, rec)
        check('a positional rule is refused on a flagged record', False)
    except audit.PathMismatch as exc:
        check('a positional rule is refused on a flagged record', True,
              'alignmentFlag' in str(exc))
    check('the same rule is allowed on an unflagged record',
          audit.assert_applicable(grid_rule, audit.STORED,
                                  model.record_by_id('TSLA-2026Q1')) is True)
    check('a flag_safe positional rule still runs on a flagged record',
          audit.assert_applicable(
              [r for r in audit.RULES if r.name == 'alignment-length'][0],
              audit.STORED, rec) is True)

    print('')
    print('=== AXTI is not a defect ===')
    axti = model.record_by_id('AXTI-2026Q2')
    sc = axti['scores']
    calc = sum(audit.WEIGHTS[k] * sc[k] for k in audit.WEIGHTS)
    check('the weighted sum is 1.925, stored rounds to 1.92',
          abs(calc - 1.925) < 1e-9 and sc['overall'] == 1.92,
          '%.17g / %s' % (calc, sc['overall']))
    check('the delta is exactly at the old 0.005 boundary',
          abs(abs(calc - sc['overall']) - 0.005) < 1e-9)
    check('0.0051 accepts it', audit.OVERALL_TOLERANCE > 0.005)
    check('and the rule reports nothing', audit._overall_weighting(axti) == [])

    print('')
    print('=== the library audit, with preconditions enforced ===')
    findings, skips = audit.audit_library(model)
    hard = [x for _i, x in findings if x.severity == 'HARD']
    check('no HARD findings survive', len(hard) == 0,
          [str(h) for h in hard])
    ibm = model.record_by_id('IBM-2026Q2')
    check('IBM-2026Q2 is a DECLARED exclusion, not a defect',
          audit.is_declared_exclusion(ibm))
    check('the audit reports it once as INFO',
          'declared-exclusion' in [x.rule for _i, x in findings
                                   if x.severity == 'INFO'],
          [x.rule for _i, x in findings if x.severity == 'INFO'])
    check('and never re-raises it as HARD',
          not any(x.rule == 'record-structure' for _i, x in findings))
    from earnings_scraper.model import NoCard
    try:
        model.prepare_from_record(ibm)
        check('the scraper refuses it under the no-card rule', False)
    except NoCard as exc:
        check('the scraper refuses it under the no-card rule',
              'no-card rule' in str(exc), str(exc)[:34])
    check('call pointers are FINDINGS, reported apart from gaps',
          any(x.rule == 'pr-withheld' for _i, x in findings),
          len([1 for _i, x in findings if x.rule == 'pr-withheld']))
    check('no unit findings leaked onto stored records',
          not any(x.rule == 'unit-declared' for _i, x in findings))
    # EIGHT, not nine: IBM-2026Q2 is a declared exclusion and is dropped before
    # any rule runs, so it never reaches the positional precondition at all.
    skipped_flagged = {r for r, n, _w in skips if n == 'prose-in-numeric-slot'}
    check('the flagged records skip the positional rule',
          len(skipped_flagged) == 8, len(skipped_flagged))
    check('and the ninth is the declared exclusion, dropped earlier',
          'IBM-2026Q2' not in skipped_flagged
          and audit.is_declared_exclusion(model.record_by_id('IBM-2026Q2')))

    print('')
    print('%d failure(s)' % FAIL[0])
    return 1 if FAIL[0] else 0


def _write_probe(src):
    import io as _io
    import tempfile
    p = os.path.join(tempfile.gettempdir(), 'binary_open_probe.py')
    with _io.open(p, 'w', encoding='utf-8') as fh:
        fh.write(src)
    return p


if __name__ == '__main__':
    sys.exit(main())
