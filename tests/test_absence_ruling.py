# -*- coding: utf-8 -*-
"""A CHECK THAT ACCEPTS ON MISSING EVIDENCE CANNOT FAIL WHEN IT HAS NONE.

That is why FALSE_MATCH 0 was never news. `column_basis` returned None on an
unlabelled column and the filter kept it -- `(column_basis(desc) or want) ==
want` -- so basis was not a weak instrument, it was a no-op that reported as
a check.

★★★ AND THE FIX CHANGES WHAT ABSENCE MEANS.

    BEFORE   absence meant WE ARE BLIND
    NOW      absence means THE COLUMN IS GENUINELY UNLABELLED

The second is a real signal about the document. Landing cellAxes without
changing the default would be building the instrument and keeping the
blindfold, so the ruling lands in the same commit:

    priority-1 hero + basis declared + column carries no basis word -> REFUSE
    lower priority, same conditions            -> ACCEPT AND FLAG

★★ THE STRICT ARM FIRES ON ZERO CORPUS ROWS TODAY, so it is driven here
directly. A rule that can never fire is decorative, and silently so.

★ WHAT THIS RULING CANNOT TELL APART: a column the issuer left unlabelled
from a column our own grid failed to read. Both arrive as basis=None. The
unstrip removed one known cause of the second; nothing rules it out.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import priority as PR        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AVGO = os.path.join(HERE, 'fixtures', 'releases', 'AVGO-2026-09-02.txt')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    # ── priority is AUTHORED, never inferred by a fuzzy binder ───────────
    graded = [{'name': u'\u2605\u2605\u2605 The hero'}, {'name': u'\u2605 A row'}]
    flat = [{'name': u'\u2605 One'}, {'name': u'\u2605 Two'}]
    check(PR.card_uses_star_scale(graded) and not PR.card_uses_star_scale(flat),
          'a card grades with stars only when it uses MORE THAN ONE level — '
          'SNDK, APP and WDC mark every row ★ and express nothing')
    check(PR.row_priority(graded[0], None, graded) == 1
          and PR.row_priority(graded[1], None, graded) == 2,
          'on a graded card ★★★ is priority-1 and ★ is supporting')
    check(PR.row_priority(flat[0], None, flat) is None,
          'on an ungraded card the answer is UNKNOWN, not "not a hero" — '
          'reading a star count there would manufacture a priority the '
          'author never expressed')
    check(PR.row_priority(flat[0], {'priority': 1}, flat) == 1,
          'and an explicit spec priority wins outright, which is the only '
          'way the strict arm can reach SNDK today')

    if not os.path.exists(AVGO) or not os.path.exists(LIB):
        print('SKIP fixture or library not reachable')
        return
    body = io.open(AVGO, encoding='utf-8').read()
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}
    rec = recs['AVGO-2026Q3']
    prow = rec['preEarnings']['keyKPIs'][8]

    # ── the real row, whose column IS labelled, is untouched ─────────────
    out = X.value_for(body, prow, record=rec) or {}
    check(out.get('value') == 3.32 and out.get('basisEvidence') == 'AGREES',
          'AVGO[8] reads 3.32 with basisEvidence=%r — the column names its '
          'basis, so no arm of the ruling applies'
          % out.get('basisEvidence'))

    # ── THE STRICT ARM, DRIVEN. Zero corpus rows reach it. ───────────────
    # The anti-vacuous requirement: disable EVERY control that could produce
    # the expected outcome independently. Here that means the row must read
    # a value successfully, on a labelled-basis spec, and fail ONLY because
    # the column carries no basis word.
    import earnings_scraper.hgrid as HG
    real = HG.cell_axes

    def blind(desc):
        got = real(desc)
        # ★ THE GRID RAN AND THE ISSUER NAMED NO BASIS. Both halves matter:
        # basis=None alone is the state a reader that never looked also
        # reports, and those two warrant opposite responses.
        got['basis'] = None
        got['basisState'] = 'ABSENT_IN_DOCUMENT'
        return got

    # AVGO[8] is authored '★ Q3 Non-GAAP EPS' -- ONE star, so it is a
    # supporting row. The strict arm needs a priority-1 name, and saying so
    # here is the point: NO corpus row reaches this arm today.
    hero = dict(prow, name=u'★★★ Q3 Non-GAAP EPS ($)')
    check(PR.row_priority(hero, None, rec['preEarnings']['keyKPIs']) == 1
          and PR.row_priority(prow, None,
                              rec['preEarnings']['keyKPIs']) == 2,
          'AVGO[8] as authored is a SUPPORTING row (1 star); the strict arm '
          'is driven on a priority-1 name because no corpus row reaches it')
    HG.cell_axes = blind
    try:
        strict = X.value_for(body, hero, record=rec) or {}
    finally:
        HG.cell_axes = real
    check(strict.get('value') is None
          and strict.get('basisEvidence') == 'ABSENT_IN_DOCUMENT',
          'with the column unlabelled, a priority-1 row REFUSES instead of '
          'publishing: %r' % (strict.get('why') or '')[:78])
    check('priority-1' in (strict.get('why') or ''),
          'and the refusal says WHY in the row, not in a log')

    # ── THE LENIENT ARM: same conditions, lower priority ─────────────────
    lower = dict(prow, name=u'\u2605 Q3 Non-GAAP EPS ($)')
    HG.cell_axes = blind
    try:
        soft = X.value_for(body, lower, record=rec) or {}
    finally:
        HG.cell_axes = real
    check(soft.get('value') == 3.32
          and soft.get('basisEvidence') == 'ABSENT_IN_DOCUMENT',
          'a supporting row publishes the value AND carries basisEvidence=%r '
          '— accepted and flagged, never accepted silently'
          % soft.get('basisEvidence'))
    check(soft.get('rowPriority') == 2,
          'with the priority it was judged on recorded beside it (%s), so '
          'the decision can be re-read rather than re-derived'
          % soft.get('rowPriority'))

    # ── ★★★ THE TWO EMPTIES, TOLD APART ─────────────────────────────────
    # A reader that never looked reports the same basis=None as a document
    # that says nothing. Refusing a hero row because OUR grid never read a
    # header would publish a refusal with false provenance — a worse defect
    # than the one the ruling exists to prevent.
    def unread(desc):
        got = real(desc)
        got['basis'] = None
        got['basisState'] = 'UNREAD_BY_GRID'
        return got

    HG.cell_axes = unread
    try:
        gap = X.value_for(body, hero, record=rec) or {}
    finally:
        HG.cell_axes = real
    check(gap.get('value') == 3.32
          and gap.get('basisEvidence') == 'UNREAD_BY_GRID',
          'the SAME priority-1 row PUBLISHES when the emptiness is OURS '
          '(%s) — the ruling refuses on a fact about the release, never on '
          'a gap in the reader' % gap.get('basisEvidence'))

    # ── and a CONTRADICTION refuses at any priority ──────────────────────
    def wrong(desc):
        got = real(desc)
        got['basis'] = 'GAAP'
        return got

    HG.cell_axes = wrong
    try:
        con = X.value_for(body, lower, record=rec) or {}
    finally:
        HG.cell_axes = real
    check(con.get('value') is None
          and con.get('basisEvidence') == 'CONTRADICTS',
          'a column that contradicts the declared basis refuses REGARDLESS '
          'of priority: %r' % (con.get('why') or '')[:70])


main()
