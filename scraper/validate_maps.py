# -*- coding: utf-8 -*-
r"""Run every documentLabelMap entry against its stored release.

★★★★★ "ADDED TO THE CONFIG" AND "RESOLVES" ARE DIFFERENT STATES, AND ONLY
ONE IS DONE. The first label maps written for this repo made two
priority-1 Intel rows WORSE than having no map at all, in three separate
ways, all silent:

    basis token   the map says "nonGAAP", the reader derives "NON_GAAP"
    label prefix  the map writes "Non-GAAP gross margin percentage"; rows
                  are keyed on the basis-stripped core
    unit          the map's unit is the DOCUMENT's and the hero's is the
                  CARD's. Checking 112,852 against the hero's $B warned on
                  the one row that was right.

So both sides are normalised here before anything is compared, and a
hero/document unit mismatch is NEVER a warning on its own.

★ A MAP WITHOUT A FIXTURE IS UNVERIFIED, NOT PASSING. Entries flagged
needsVerification (currently all of RBLX, inferred from a letter format
nobody has parsed) are reported as UNVERIFIED until a release is stored.
Adobe silently stopped reporting 'Digital Media ARR' and a stale alias
matches nothing while looking perfectly fine.

    py scraper/validate_maps.py
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                     # noqa: E402
from scraper import prose_guidance as PG                    # noqa: E402
from scraper import selector as S                           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, 'fixtures')


def fixture_for(ticker):
    """The newest stored release for a ticker, or None."""
    if not os.path.isdir(FIXTURES):
        return None
    hits = sorted(f for f in os.listdir(FIXTURES)
                  if re.match(r'(?i)^%s_' % re.escape(ticker), f)
                  and f.lower().endswith(('.htm', '.html')))
    return os.path.join(FIXTURES, hits[-1]) if hits else None


def check_value(entry, f):
    """(state, detail) for one RESOLVED hero. Five states, never four.

    THE WHOLE POINT OF `expect`. Before this, PASS meant "resolved to
    something" -- the hero key was present in `found` and the value was
    PRINTED, never compared. Candidate B changed five figures in this very
    file, among them ADBE adjusted EPS from 6.13 to 5.96, and the summary
    line came back byte-identical: PASS 22 FAIL 9 UNVERIFIED 2. A harness
    that cannot report a wrong value is not a harness, and this one had
    been clearing every selector change for a session.

    UNPINNED IS ITS OWN STATE AND MUST STAY ITS OWN STATE. Folding a
    resolved-but-unpinned entry into PASS is the identical defect at
    smaller scale -- it would report 17 unchecked entries as verified.
    """
    exp = entry.get('expect')
    if entry.get('expectUnverified'):
        return 'UNVERIFIED', 'expect not sourced to a document'
    # A GUIDE RANGE IS TWO NUMBERS AND IS PINNED AS TWO NUMBERS. Intel's
    # Q4 outlook is '$15.0 - $16.0' in ONE cell; the library stores 15.5,
    # but that midpoint is chat's arithmetic and appears nowhere in the
    # release. Pinning the midpoint here would make the parser's job to
    # derive it, and the WIDTH is the tradeable part -- this guide is 9.0%
    # below street and the worst-scoring row on the print.
    rng = entry.get('expectRange')
    if rng is not None:
        if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            return 'WRONG-VALUE', 'expectRange %r is not [low, high]' % (rng,)
        lo, hi = f.get('low'), f.get('high')
        if lo is None or hi is None:
            return 'WRONG-VALUE', ('expected %s - %s, got no range (raw %r)'
                                   % (rng[0], rng[1], str(f.get('raw'))[:24]))
        if (abs(lo - float(rng[0])) <= max(0.005, abs(float(rng[0])) * 1e-9)
                and abs(hi - float(rng[1])) <= max(0.005,
                                                   abs(float(rng[1])) * 1e-9)):
            return 'PASS', ''
        return 'WRONG-VALUE', ('expected %s - %s, got %s - %s'
                               % (rng[0], rng[1], lo, hi))
    if exp is None:
        return 'UNPINNED', 'resolved, no expect to check against'
    got = f.get('value')
    if got is None:
        return 'WRONG-VALUE', ('expected %s, no numeric value (raw %r)'
                               % (exp, str(f.get('raw'))[:24]))
    try:
        got = float(got)
        exp = float(exp)
    except (TypeError, ValueError):
        return 'WRONG-VALUE', 'expect %r is not numeric' % (exp,)
    # tight enough that 5.96 never passes for 6.13, loose enough that a
    # float repr never fails for itself
    if abs(got - exp) <= max(0.005, abs(exp) * 1e-9):
        return 'PASS', ''
    return 'WRONG-VALUE', 'expected %s, got %s' % (
        entry.get('expect'), f.get('raw') or got)


def main():
    profiles, mtime = S.load_profiles()
    if not profiles:
        print('NO PROFILES LOADED - a validator with no config asserts '
              'nothing')
        return 2

    mapped = [(t, p) for t, p in sorted(profiles.items())
              if p.get('documentLabelMap')]
    print('ticker-profiles.json: %d tickers, %d with a documentLabelMap'
          % (len(profiles), len(mapped)))
    print('fixtures: %s' % (', '.join(sorted(os.listdir(FIXTURES)))
                            if os.path.isdir(FIXTURES) else 'NONE'))
    print('')

    npass = nfail = nunver = nofix = nwrong = nunpin = 0
    for ticker, prof in mapped:
        dlm = prof.get('documentLabelMap') or {}
        path = fixture_for(ticker)
        if path is None:
            unver = [k for k, v in dlm.items()
                     if isinstance(v, dict) and v.get('needsVerification')]
            print('%-6s NO FIXTURE - %d entr%s cannot be checked%s'
                  % (ticker, len(dlm), 'y' if len(dlm) == 1 else 'ies',
                     ' (%d flagged needsVerification)' % len(unver)
                     if unver else ''))
            nunver += len(unver)
            nofix += len(dlm) - len(unver)
            continue

        html = io.open(path, encoding='utf-8', errors='replace').read()
        rows = cells.from_html(html)
        prose = PG.from_text(sec.to_text(html))
        res = S.select(rows, ticker, profiles=profiles, prose_rows=prose)
        got = dict((f['hero'], f) for f in (res.get('found') or []))
        missing = set(n['hero'] for n in (res.get('notInRelease') or []))

        print('%-6s %s' % (ticker, os.path.basename(path)))
        # ★★★ `table` WAS DROPPED FROM THE SCHEMA AND MUST NOT RETURN.
        # It carried strings the parser never emits -- the INTC map said
        # 'Supplemental Reconciliations of GAAP Actuals to Non-GAAP
        # Actuals' where the parser emits 'n-GAAP measures, and the reasons
        # why management believes' -- and nothing read it, so 10/10 passed
        # while the field was fiction. A field that disagrees with reality
        # and is never consulted READS AS VERIFICATION, which is worse than
        # having no field at all.
        dead = [h for h, e in dlm.items()
                if isinstance(e, dict) and 'table' in e]
        if dead:
            print('   FAIL        `table` is not in the schema: %s'
                  % [h[:34] for h in dead])
            nfail += len(dead)
        for hero, entry in sorted(dlm.items()):
            if not isinstance(entry, dict):
                continue
            if entry.get('needsVerification'):
                print('   UNVERIFIED  %s' % hero[:58])
                nunver += 1
                continue
            # an entry that DECLARES the figure is absent is satisfied by
            # the hero being absent -- that is the entry resolving, not
            # failing
            declared_absent = (entry.get('channel') == 'call'
                               or not entry.get('documentLabels')
                               and entry.get('channel') != 'prose')
            if hero in got:
                f = got[hero]
                shown = (f.get('raw') or f.get('value'))
                state, why = check_value(entry, f)
                print('   %-11s %-46s %s  %s'
                      % (state, hero[:46], str(shown)[:14],
                         f.get('period') or ''))
                if why:
                    print('               -> %s' % why)
                if state == 'PASS':
                    npass += 1
                elif state == 'WRONG-VALUE':
                    nwrong += 1
                elif state == 'UNPINNED':
                    nunpin += 1
                else:
                    nunver += 1
            elif hero in missing and declared_absent:
                print('   PASS        %-46s (declared not in release)'
                      % hero[:46])
                npass += 1
            else:
                print('   FAIL        %-46s did not resolve' % hero[:46])
                nfail += 1
        print('')

    print('=' * 70)
    print('PASS %d   WRONG-VALUE %d   FAIL %d   UNPINNED %d'
          '   UNVERIFIED %d   NO FIXTURE %d'
          % (npass, nwrong, nfail, nunpin, nunver, nofix))
    if nunpin:
        print('%d resolved entr%s carr%s no `expect` -- PRINTED, NOT CHECKED.'
              % (nunpin, 'y' if nunpin == 1 else 'ies',
                 'ies' if nunpin == 1 else 'y'))
    return 1 if (nfail or nwrong) else 0


if __name__ == '__main__':
    sys.exit(main())
