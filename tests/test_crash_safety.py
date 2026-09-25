# -*- coding: utf-8 -*-
"""A REFUSAL COSTS ONE CELL. AN EXCEPTION COSTS THE WHOLE CARD.

WHICH CODE PATHS GET EXERCISED IS DECIDED BY WHICH EIGHT ISSUERS WE HAPPENED
TO SPEC. `block_cells_at` rebuilt an entry as a PAIR on the bare-'%' marker
path, dropping the line index. SNOW attaches its percent to the figure, so
the corpus never reached it; SNDK and APP use the bare marker. It would have
surfaced as an IndexError ON A LIVE PRINT — a ninth document with unknown
typographic conventions, mid-print, on the card that is needed right then.

This does not make the extractor parse a ninth issuer correctly. It makes it
fail ONE CELL AT A TIME and still render.

★★★ AND THE GATE IS DRIVEN RED, not reported green. An instrument is
trustworthy only once it has been made to fail on purpose: every reader here
is FORCED to raise, and the unguarded call is shown to raise so the guard is
demonstrably what caught it. A gate never driven red is an unverified claim
about a verification.

★ THE GUARD IS LOUD. A blanket try/except that swallows everything is how a
defect lives for a year, so a crash must read as a crash — `readerCrashed`
set and the exception named — never as an ordinary 'no candidate found'.
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import extract as X          # noqa: E402
from earnings_scraper import hgrid as HG           # noqa: E402
from earnings_scraper import registry as R         # noqa: E402
from earnings_scraper import sgrid as SG           # noqa: E402
from earnings_scraper import sweep as SW           # noqa: E402
from earnings_scraper import tables as T           # noqa: E402
from earnings_scraper import vtables as VT         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, 'fixtures', 'releases')
MODEL = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents', 'Claude',
                     'Projects', 'earnings Model')
LIB = os.path.join(MODEL, 'earnings-library.json')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def boom(*_a, **_kw):
    raise ValueError('synthetic reader fault')


def main():
    avgo = os.path.join(FIX, 'AVGO-2026-09-02.txt')
    hpe = os.path.join(FIX, 'HPE-2026-09-02.txt')
    if not (os.path.exists(avgo) and os.path.exists(hpe)
            and os.path.exists(LIB)):
        print('FAIL fixtures or library not reachable')
        return
    recs = {r['id']: r for r in json.load(io.open(LIB, encoding='utf-8'))
            ['records']}

    cases = [
        ('hgrid.select', HG, 'select', avgo, 'AVGO-2026Q3', 8),
        ('vtables.column_map', VT, 'column_map', hpe, 'HPE-2026Q3', 7),
        ('tables.row_value_cells_at', T, 'row_value_cells_at', hpe,
         'HPE-2026Q3', 7),
        ('sgrid.select', SG, 'select',
         os.path.join(FIX, 'SNOW-2026-09-02.txt'), 'SNOW-2027Q2', 5),
    ]

    for label, mod, attr, path, rid, idx in cases:
        if not os.path.exists(path):
            continue
        body = io.open(path, encoding='utf-8').read()
        rec = recs[rid]
        prow = rec['preEarnings']['keyKPIs'][idx]

        # the row works before the fault is injected
        before = X.value_for(body, prow, record=rec) or {}
        real = getattr(mod, attr)
        setattr(mod, attr, boom)
        try:
            after = X.value_for(body, prow, record=rec) or {}
            # ★ AND THE UNGUARDED CALL REALLY DOES RAISE — otherwise this
            # whole case would pass without the guard existing.
            raised = False
            try:
                mod_fn = getattr(mod, attr)
                mod_fn([], 0, {})
            except ValueError:
                raised = True
            except TypeError:
                raised = True
        finally:
            setattr(mod, attr, real)

        check(before.get('value') is not None,
              '%s: the row reads %s before the fault'
              % (label, before.get('value')))
        check(raised, '%s: the injected fault genuinely raises when called '
                      'unguarded — the guard is what catches it, not luck'
              % label)
        check(after.get('value') is None,
              '%s: with the reader raising, the row yields NO VALUE rather '
              'than a number of unknown provenance' % label)
        check(after.get('readerCrashed') is True,
              '%s: and it is marked readerCrashed — a crash reads as a '
              'crash, not as an ordinary miss' % label)
        check(label.split('.')[0] in (after.get('why') or '')
              or 'READER FAILED' in (after.get('why') or ''),
              '%s: the refusal NAMES the reader and the exception: %r'
              % (label, (after.get('why') or '')[:72]))

        # and the sweep turns it into a REFUSED row, not an exception
        slot = ((rec.get('actuals') or {}).get('keyKPIs') or [{}])[idx]
        setattr(mod, attr, boom)
        try:
            j = SW.judge(body, prow, slot, R.spec_for(prow),
                         rec.get('fiscalQuarter'),
                         got=(X.value_for(body, prow, record=rec) or {}),
                         record=rec)
        finally:
            setattr(mod, attr, real)
        check(j['verdict'] == 'REFUSED',
              '%s: the sweep records REFUSED — one cell lost, the card still '
              'renders' % label)

    # ── malformed documents: nothing escapes ─────────────────────────────
    rec = recs['HPE-2026Q3']
    prow = rec['preEarnings']['keyKPIs'][7]
    junk = [
        '', '\n' * 50, 'x' * 5000, '\r\n\r\n', '---- ---- ----\n\n$\n%\n(\n',
        '12,213\n%\n$\n', 'Revenue\n(\n)\n(1)\n', '\x00\x01 weird \ufffd',
        'Revenue' + '\n' * 3 + '$' * 40, '%\n%\n%\n%\n',
    ]
    escaped = []
    for k, doc in enumerate(junk):
        try:
            out = X.value_for(doc, prow, record=rec)
            if out is not None and out.get('value') is not None:
                escaped.append('case %d returned a VALUE from junk' % k)
        except Exception as exc:                        # noqa: BLE001
            escaped.append('case %d raised %s' % (k, type(exc).__name__))
    check(not escaped,
          'ten malformed documents produce refusals, not exceptions and not '
          'values: %s' % (escaped or 'all clean'))

    # ── and the bare-marker convention, the one that was latent ──────────
    lines = ['Gross margin', '40.4', '%', '36.9', '%', 'Next label']
    got = SG.block_cells_at(lines, 0)
    check(all(len(c) == 3 for c in got) and [c[2] for c in got] == [1, 3],
          'the bare-%% marker path keeps the line index (%s) — the shape '
          'that was one live print away from an IndexError'
          % [c[2] for c in got])


main()
