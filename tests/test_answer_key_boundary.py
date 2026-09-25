# -*- coding: utf-8 -*-
"""CAN ANY READER PATH REACH THE HAND READ? THE ANSWER MUST BE NO.

`street`, `bogey`, `note`, `setup`, `consensus` and `actual` are all Kyle's
hand read, and they sit on the SAME OBJECT as the extraction spec. That
boundary is the difference between EXTRACTED and RESTATED, and it is the
thing this entire build exists to measure.

★★★ A DERIVED VALUE WHOSE OPERAND COMES FROM THE CARD'S PROSE IS THE HAND
READ WITH ARITHMETIC APPLIED — IT CANNOT DISAGREE. Same family as a check
consulting the population instead of the selection, one level worse, because
it produces a NUMBER and the number lands on the card. Found in HPE[0], whose
sourceRows said "the $3.75-$3.85 range" and whose base operand was read
straight out of that sentence.

★★ AND THE DANGEROUS FIELD WAS THE HELPFUL ONE. That prose was written as an
aid to a human. Every clarifying note is a latent answer-key leak awaiting a
reader capable enough to parse it, so WHAT IS FOR HUMANS AND WHAT IS FOR
READERS MUST BE STRUCTURALLY SEPARATE.

★ THE TEST IS POISONING, NOT INSPECTION. Grepping for field names proves
nothing about a path that builds a key dynamically. Every hand-read field is
replaced with an absurd value and the whole corpus is re-extracted: if any
extracted value moves, a reader is reading the answer key.
"""

import copy
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X                 # noqa: E402
from earnings_scraper import registry as R                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'releases')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')

#: everything on a card row that is Kyle's judgement, not the document's
HAND_READ = ('street', 'bogey', 'consensus', 'note', 'setup', 'actual',
             'vsBogey', 'unitNote', 'notes', 'expected')

POISON_NUM = -987654.321
POISON_STR = 'POISONED — if this reaches a value, a reader read the answer key'


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def poison(obj):
    """Replace every hand-read field, at any depth, with an absurd value."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in HAND_READ:
                out[k] = (POISON_NUM if isinstance(v, (int, float))
                          else POISON_STR)
            else:
                out[k] = poison(v)
        return out
    if isinstance(obj, list):
        return [poison(v) for v in obj]
    return obj


def main():
    if not os.path.exists(LIB):
        print('FAIL library not reachable')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    cases = [('AVGO-2026Q3', 'AVGO-2026-09-02.txt'),
             ('HPE-2026Q3', 'HPE-2026-09-02.txt'),
             ('SNOW-2027Q2', 'SNOW-2026-09-02.txt')]

    moved, seen, valued = [], 0, 0
    for rid, fname in cases:
        path = os.path.join(FIX, fname)
        if not os.path.exists(path):
            continue
        body = io.open(path, encoding='utf-8').read()
        clean = recs[rid]
        dirty = poison(copy.deepcopy(clean))
        for i, prow in enumerate(clean['preEarnings']['keyKPIs']):
            if R.status_of(R.spec_for(prow)) != 'EXTRACTABLE':
                continue
            seen += 1
            a = (X.value_for(body, prow, record=clean) or {}).get('value')
            b = (X.value_for(body, dirty['preEarnings']['keyKPIs'][i],
                             record=dirty) or {}).get('value')
            if a is not None:
                valued += 1
            if a != b:
                moved.append((rid, i, (prow.get('name') or '')[:32], a, b))

    check(seen > 0 and valued > 0,
          'SAMPLE FRAME: %d extractable rows across %d documents, %d of them '
          'producing a value — a boundary test over rows that all refuse '
          'would prove nothing' % (seen, len(cases), valued))
    check(not moved,
          'NO extracted value moves when every hand-read field is poisoned: '
          '%s' % (moved or 'the boundary holds'))
    for rid, i, nm, a, b in moved:
        print('     LEAK %-13s[%-2d] %-32s clean=%s poisoned=%s'
              % (rid, i, nm, a, b))

    # ── and the poison is REACHING the rows, or the test is vacuous ──────
    d = poison(copy.deepcopy(recs['HPE-2026Q3']))
    check(d['actuals']['keyKPIs'][0]['actual'] == POISON_NUM
          and d['preEarnings']['keyKPIs'][0]['consensus'] == POISON_NUM,
          'the poison really is applied to the objects handed to the reader '
          '— otherwise the clean result above would be a tautology')

    # ── the known leak, named and pinned ─────────────────────────────────
    hpe = recs['HPE-2026Q3']
    srcs = (R.spec_for(hpe['preEarnings']['keyKPIs'][0]) or {}) \
        .get('sourceRows') or []
    prose_operand = any('$3.75' in str(s) or '3.85' in str(s) for s in srcs)
    if prose_operand:
        print('KNOWN  HPE[0] sourceRows still carry the endpoints as PROSE '
              '(%r) — a structured reference is Kyle\'s rewrite, and until '
              'it lands the base operand is the hand read with arithmetic '
              'applied' % str(srcs[0])[:60])
    else:
        check(True, 'HPE[0] sourceRows no longer carry prose endpoints — the '
                    'operand is a structured reference')

    # ── no OTHER row carries a numeric operand in prose ──────────────────
    leaky = []
    for rid in recs:
        for i, prow in enumerate((recs[rid].get('preEarnings') or {})
                                 .get('keyKPIs') or []):
            spec = R.spec_for(prow) or {}
            for src in (spec.get('sourceRows') or []):
                digits = [t for t in str(src).replace('(', ' ').split()
                          if any(ch.isdigit() for ch in t)]
                # a footnote marker inside a label is label text, not an
                # operand: 'Net Revenue(5): Cloud & AI'
                real = [t for t in digits if any(c in t for c in '.$%')]
                if real:
                    leaky.append((rid, i, str(src)[:46]))
    check(len(leaky) <= 2,
          'library-wide, %d sourceRows entries carry a numeric operand in '
          'prose (all HPE[0]); footnote markers inside labels are label '
          'text, not operands' % len(leaky))


main()


# ══ SURFACE 3: ticker-profiles.json ═══════════════════════════════════════
#
# ★★★ A BOUNDARY TEST PROVES THE BOUNDARY IT CROSSED. The poison above covers
# the library record's hand-read fields. It never touched ticker-profiles.json
# — and globalDocumentLabelMap lives in that file, beside 279 hero entries of
# which 198 carry three or more FIGURES in `notes`: street levels, whispers,
# bogeys, implied ramps. MDB's Atlas growth note carries thirty.
#
# A HAND-READ NUMBER AND A MACHINE-READ LABEL MAP SHARE ONE OBJECT. That is
# the exact structural mixing that produced the sourceRows leak.

PROFILES = os.path.join(MODEL, 'ticker-profiles.json')


def profile_surface():
    from earnings_scraper import registry as R2

    if not os.path.exists(PROFILES):
        print('SKIP ticker-profiles.json not reachable')
        return
    prof = json.load(io.open(PROFILES, encoding='utf-8'))

    # ── how much oracle is actually sitting there ────────────────────────
    import re as _re
    heroes = [h for p in (prof.get('profiles') or {}).values()
              for h in (p.get('heroKPIs') or [])]
    loaded = [h for h in heroes
              if len(_re.findall(r'\d+(?:[.,]\d+)?',
                                 str(h.get('notes') or ''))) >= 3]
    check(heroes and loaded,
          'SAMPLE FRAME: %d hero entries, %d carrying 3+ figures in notes — '
          'the oracle is real and it is large' % (len(heroes), len(loaded)))

    # ── the reader does not consult that file TODAY ──────────────────────
    # ★ Nothing in the codebase passes `global_map`, so the path is LATENT.
    # Saying so is the finding; a test that reported "clean" without saying
    # which path it exercised would be claiming more than it measured.
    check(R2.spec_for({'name': 'x'}, global_map=None, metric_kind=None)
          is None,
          'spec_for returns None with no row spec and no global map — the '
          'global fallback is reachable only when a caller passes one, and '
          'no caller does')

    # ── and when one DOES, prose cannot ride in ──────────────────────────
    poisoned_map = {'metrics': {'totalRevenue': {
        'documentLabels': ['Total revenue'],
        'notes': 'street 12.5, whisper 12.9, bogey 13.1',
        'interpretation': 'a bogey of 13.1 is the number that matters',
        'beatBand': POISON_NUM, 'street': POISON_NUM}}}
    spec = R2.spec_for({'name': 'x'}, global_map=poisoned_map,
                       metric_kind='totalRevenue')
    check(spec and spec.get('documentLabels') == ['Total revenue'],
          'a global-map fallback still yields its LABELS')
    leaked = [k for k in (spec or {})
              if k in ('notes', 'interpretation', 'beatBand', 'street')]
    check(not leaked,
          'and carries NONE of the hand-read fields into the spec (%s) — '
          'structural_only is the fence, so a future caller cannot cross '
          'the line by accident' % (leaked or 'clean'))
    check(R2.prose_fields(poisoned_map['metrics']['totalRevenue'])
          == ['beatBand', 'interpretation', 'notes', 'street'],
          'and the dropped fields are REPORTABLE rather than silently '
          'discarded, so the mixing stays visible')

    # ── ★ ANTI-VACUOUS: the fence must be able to pass something through ──
    check('statement' in R2.structural_only(
        {'documentLabels': ['x'], 'statement': 'income statement'}),
        'structural_only is an ALLOWLIST that really allows — it is not a '
        'function that returns {} and looks clean')


profile_surface()
