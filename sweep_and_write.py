# -*- coding: utf-8 -*-
"""THE single sweep and THE single writer.

The extractor emits the column, this writes it into the library, the
dashboard renders what was emitted, and the counts below are counts of those
same rows. Until this held, three numbers described the corpus and none of
them described the artifact on Kyle's screen.

Run it with --write to update the library column; without, it reports only.

★ EVERY REPORT CARRIES ITS DENOMINATOR, and all six verdicts are printed
every time -- including the zeros. A headline that quoted three of six
buckets went a week without anyone noticing the other three existed.
"""

import argparse
import collections
import io
import json
import os
import sys

import datetime                                   # noqa: E402
RUN_AT = datetime.date.today().isoformat()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import parallel as PAR       # noqa: E402
from earnings_scraper import firstfire as FF      # noqa: E402
from earnings_scraper import frames as FR         # noqa: E402
from earnings_scraper import spans as SP          # noqa: E402
from earnings_scraper import priority as PRIO     # noqa: E402
from earnings_scraper import vocab as VOC         # noqa: E402
from earnings_scraper import reasons as RE        # noqa: E402
from earnings_scraper import registry as R         # noqa: E402
from earnings_scraper import sweep as SW           # noqa: E402

MODEL = r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
LIB = os.path.join(MODEL, 'earnings-library.json')
PEND = os.path.join(HERE, 'earnings_scraper', 'state', 'pending')
FIX = os.path.join(HERE, 'tests', 'fixtures', 'releases')
CORPUS = os.path.join(MODEL, 'tests', 'corpus')

CASES = [
    ('ORCL-2027Q1', os.path.join(PEND, '20260910-161341-ORCL.json'), 'raw'),
    ('ADBE-2026Q3', os.path.join(PEND, '20260910-160500-ADBE.json'), 'raw'),
    ('AVGO-2026Q3', os.path.join(FIX, 'AVGO-2026-09-02.txt'), 'txt'),
    ('HPE-2026Q3', os.path.join(FIX, 'HPE-2026-09-02.txt'), 'txt'),
    ('SNOW-2027Q2', os.path.join(FIX, 'SNOW-2026-09-02.txt'), 'txt'),
    ('APP-2026Q2', os.path.join(CORPUS, 'APP-2026Q2.txt'), 'txt'),
    ('SNDK-2026Q4', os.path.join(CORPUS, 'SNDK-2026Q4.txt'), 'txt'),
    ('WDC-2026Q4', os.path.join(CORPUS, 'WDC-2026Q4.txt'), 'txt'),
]


def body_of(path, kind):
    if kind == 'raw':
        return ((json.load(io.open(path, encoding='utf-8'))
                 .get('rawItem') or {}).get('body') or '')
    return io.open(path, encoding='utf-8').read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--write', action='store_true',
                    help='write scraperRead and sweepVerdict into the library')
    args = ap.parse_args()

    FR.clear()
    SP.clear()
    lib = json.load(io.open(LIB, encoding='utf-8'))
    recs = {r['id']: r for r in lib['records']}

    counts = collections.Counter()
    rows_seen = 0
    detail = []
    vacuous = []
    silent = []
    misdescribed = []
    firstfires = []
    broad = []
    ledger = FF.seen_codes()

    for rid, path, kind in CASES:
        if not os.path.exists(path):
            print('   SKIP %s (source absent)' % rid)
            continue
        body = body_of(path, kind)
        rec = recs[rid]
        q = rec.get('fiscalQuarter')
        pre = rec['preEarnings'].get('keyKPIs') or []
        act = rec.setdefault('actuals', {}).setdefault('keyKPIs', [])
        while len(act) < len(pre):
            act.append({})

        for i, prow in enumerate(pre):
            if not isinstance(act[i], dict):
                continue
            spec = R.spec_for(prow)
            slot = act[i]
            rows_seen += 1
            got = (X.value_for(body, prow, record=rec) or {}
                   if R.status_of(spec) == 'EXTRACTABLE' else {})
            j = SW.judge(body, prow, slot, spec, q, got=got or None,
                         record=rec)
            counts[j['verdict']] += 1
            ck = j.get('checks') or {}
            if j['verdict'] == 'MATCH':
                if ck.get('evidenceCount'):
                    counts['_auditable'] += 1
                else:
                    counts['_vacuous'] += 1
                    vacuous.append((rid, i, (prow.get('name') or '')[:32], ck))
                for c in ('fence', 'basis', 'period'):
                    if ck.get(c) == SW.EVIDENCE:
                        counts['_ev:' + c] += 1
                    elif ck.get(c) == SW.ABSENT:
                        counts['_ab:' + c] += 1
            detail.append((rid, i, (prow.get('name') or '')[:32],
                           slot.get('actual'), j['value'], j['verdict'],
                           j.get('reason') or ''))
            # ★★★ NO VALUE AND NO REASON IS THE ONE STATE THE SIX-VERDICT
            # SCHEME EXISTS TO ABOLISH. A blank with no reason is
            # indistinguishable from a row nobody tried, from a crash that
            # was swallowed, and from a deliberate refusal. It must be an
            # ASSERTION FAILURE at the writer, never a quiet blank on a card.
            if j['value'] is None and not (j.get('reason') or '').strip():
                silent.append((rid, i, (prow.get('name') or '')[:40],
                               j['verdict']))
            # ★★★ A REFUSAL REASON IS A DIAGNOSTIC NO TEST ASSERTS, so the
            # sweep asserts it. Three defects survived a green suite behind
            # a message that described the wrong cause.
            # ★ FIRST-FIRE. A code meeting real prose for the first time is
            # a refusal to HAND-CHECK before it informs anything, however
            # correct the gate says its claim is.
            _code = (got or {}).get('reasonCode')
            _first = False
            if _code:
                _first = FF.mark(_code, rid, when=RUN_AT, ledger=ledger)
                if _first:
                    firstfires.append((rid, i, (prow.get('name') or '')[:38],
                                       _code))
            for _f, _vals in VOC.routing_breadth(spec):
                broad.append((rid, i, (prow.get('name') or '')[:32], _f,
                              '/'.join(_vals), j['verdict']))
            if got:
                _ok, _c = RE.verify(body, prow, spec, rec, got)
                if not _ok:
                    misdescribed.append((rid, i,
                                         (prow.get('name') or '')[:38],
                                         got.get('reasonCode'), _c))
            if args.write:
                slot['scraperRead'] = j['value']
                slot['sweepVerdict'] = j['verdict']
                slot['sweepReason'] = j.get('reason')
                slot['pos'] = j.get('pos')
                slot['agreesWithActual'] = PAR.agrees(slot.get('actual'),
                                                      j['value'])
                # ★ THE EVIDENCE TRAVELS WITH THE ROW. A verdict without it
                # cannot be told apart from a verdict nothing checked.
                slot['sweepChecks'] = {k: v for k, v in
                                       (j.get('checks') or {}).items()
                                       if k in ('fence', 'basis', 'period',
                                                'evidenceCount', 'notes')}
                slot['basisEvidence'] = (got or {}).get('basisEvidence')
                slot['reasonCode'] = _code
                slot['firstFire'] = _first or None

    # ★★★ NON-NEGOTIABLE 0b, LIBRARY-WIDE. The extraction spec is an output
    # of every pre-earnings build: the same information the build already
    # gathers, read out of the prior quarter's release and not written down.
    # SOFT by request -- the author is the one tripping it while coverage
    # builds one earnings season at a time, and a blocked build is worse
    # than a visible count.
    # ★★★★ 'N VIOLATIONS' IS MEANINGLESS WITHOUT 'ACROSS M FIELDS OF K
    # DECLARED'. documentUnit had no closed list, so it contributed zero
    # violations because zero of its values were checked.
    _chk = _dec = 0
    _unval = collections.Counter()
    for _rec in lib['records']:
        for _r in ((_rec.get('preEarnings') or {}).get('keyKPIs') or []):
            _sp = _r.get('extraction')
            if not _sp:
                continue
            _c, _d, _u = VOC.coverage(_sp)
            _chk += len(_c)
            _dec += len(_d)
            for _f in _u:
                _unval[_f] += 1

    _p1 = _miss = _recs = _trip = 0
    for _rec in lib['records']:
        _pre = (_rec.get('preEarnings') or {}).get('keyKPIs') or []
        _ones = [r for r in _pre
                 if PRIO.row_priority(r, r.get('extraction'), _pre) == 1]
        if not _ones:
            continue
        _recs += 1
        _p1 += len(_ones)
        _m = [r for r in _ones if not r.get('extraction')]
        _miss += len(_m)
        _trip += 1 if _m else 0

    print('=' * 100)
    print('SWEEP — one writer, all six verdicts, denominator attached')
    print('=' * 100)
    print(SW.report(counts, rows_seen))
    if _dec:
        print('   SPEC VALIDATION COVERAGE — %d of %d declared matcher fields '
              'CHECKED (%.0f%%)' % (_chk, _dec, 100.0 * _chk / _dec))
        if _unval:
            print('      UNVALIDATED (no closed list, so silently passing): '
                  '%s' % ', '.join('%s x%d' % kv
                                   for kv in _unval.most_common(6)))
    if _p1:
        print('   NON-NEGOTIABLE 0b — extraction spec on every priority-1 '
              'row: %d of %d MISSING across %d record(s) (%d clean). SOFT.'
              % (_miss, _p1, _trip, _recs - _trip))
    # ★★ THE SPLIT IS PART OF THE SWEEP NOW, not a separate script. Report
    # coverage as EVIDENCE-BEARING ROWS, never as declared rows.
    print('   MATCH %d = %d with >=1 DISCRIMINATING check + %d ALL-VACUOUS'
          % (counts['MATCH'], counts['_auditable'], counts['_vacuous']))
    # ★★★ TWO NUMBERS, NEVER ONE. fence answers 'taken from the right
    # SECTION'; period and basis answer 'the right CELL'. Summing them is
    # the same category error as summing DECLARED with EVIDENCED -- two
    # instruments answering different questions, added because both return
    # a boolean. The sibling-cell audit settles it: fence discriminates
    # between cells of the same row on 0 of 11 rows.
    print('   ROW-LEVEL  evidence:  fence %d          (right SECTION)'
          % counts['_ev:fence'])
    print('   CELL-LEVEL evidence:  period %d · basis %d   (right CELL)'
          % (counts['_ev:period'], counts['_ev:basis']))
    print('   column states NO basis word (flagged, not silent): %d'
          % counts['_ab:basis'])
    if vacuous:
        print('   the all-vacuous MATCHes:')
        for rid, i, nm, ck in vacuous:
            print('      %-13s[%-2d] %-32s fence=%-8s basis=%-8s period=%s'
                  % (rid, i, nm, ck.get('fence'), ck.get('basis'),
                     ck.get('period')))
    print('')
    for v in SW.VERDICTS:
        rows = [d for d in detail if d[5] == v]
        if not rows:
            continue
        print('-' * 100)
        print('%s — %d of %d' % (v, len(rows), rows_seen))
        for rid, i, nm, stored, val, _v, why in rows[:12]:
            print('   %-13s[%-2d] %-32s actual %-10s read %-10s %s'
                  % (rid, i, nm, stored, val, why[:40]))
        if len(rows) > 12:
            print('   ... %d more' % (len(rows) - 12))

    if firstfires:
        print('')
        print('★ FIRST FIRE — %d refusal code(s) met real prose for the '
              'first time in this run.' % len(firstfires))
        print('   HAND-CHECK THESE AGAINST THE RELEASE before any of it '
              'informs a trade:')
        for rid, i, nm, code in firstfires:
            print('   %-13s[%-2d] %-38s %s' % (rid, i, nm, code))
    _unfired = FF.unfired(RE.CODES, ledger)
    if _unfired:
        print('')
        print('   codes that have STILL never met real prose (%d of %d): %s'
              % (len(_unfired), len(RE.CODES), ', '.join(_unfired)))

    if broad:
        _ref = [b for b in broad if b[5] in ('REFUSED', 'LOST')]
        print('')
        print('ROUTING BREADTH — %d row(s) declare more than one layout kind'
              ' (%d of them refusing)' % (len(broad), len(_ref)))
        print('   A list in a routing field is an ORDERED PREFERENCE, not a '
              'set of permissions.')
        print('   When unsure, declare one: a single declaration that '
              'refuses NAMES the branch.')
        for rid, i, nm, f, vals, v in _ref[:10]:
            print('   %-13s[%-2d] %-32s %s=%s  %s' % (rid, i, nm, f, vals, v))

    if SP.VIOLATIONS:
        print('')
        print('SPAN VIOLATIONS — %d span(s) that cannot be trusted'
              % len(SP.VIOLATIONS))
        print('   A span needs a CLOSE, not a LENGTH; an empty span is not '
              'a section.')
        for v in sorted(set(SP.VIOLATIONS))[:12]:
            print('   %s' % v)

    if FR.VIOLATIONS:
        print('')
        print('=' * 100)
        print('FRAME VIOLATIONS — %d cross-frame use(s) this run'
              % len(FR.VIOLATIONS))
        print('   An offset is meaningless without the text it was measured '
              'in. Five defects')
        print('   came from this and none was caught by vigilance.')
        for v in sorted(set(FR.VIOLATIONS)):
            print('   %s' % v)
        raise SystemExit('refusing to write across a frame boundary')

    if misdescribed:
        print('')
        print('=' * 100)
        print('GATE FAILURE — %d refusal(s) state a cause that cannot be '
              're-derived' % len(misdescribed))
        print('   The row refuses either way and the count is unchanged, '
              'which is exactly')
        print('   how three defects survived a green suite.')
        for rid, i, nm, code, c in misdescribed:
            print('   %-13s[%-2d] %-38s %-18s %s' % (rid, i, nm, code, c))
        raise SystemExit('refusing to write a misdescribed refusal')

    if silent:
        print('')
        print('=' * 100)
        print('ASSERTION FAILURE — %d row(s) reached the writer with NO VALUE '
              'AND NO REASON' % len(silent))
        print('   That is the one state six verdicts exist to abolish: '
              'indistinguishable from')
        print('   a row nobody tried, a swallowed crash, and a deliberate '
              'refusal.')
        for rid, i, nm, v in silent:
            print('   %-13s[%-2d] %-40s verdict=%s' % (rid, i, nm, v))
        raise SystemExit('refusing to write a silent blank')

    if args.write:
        FF.save(ledger)
        io.open(LIB, 'w', encoding='utf-8', newline='').write(
            json.dumps(lib, indent=2, ensure_ascii=False) + '\n')
        print('')
        print('column written to earnings-library.json — this is now the only '
              'writer, and the dashboard renders exactly these rows')


if __name__ == '__main__':
    main()
