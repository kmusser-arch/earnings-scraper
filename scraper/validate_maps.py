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

    npass = nfail = nunver = nofix = 0
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
                print('   PASS        %-46s %s  %s'
                      % (hero[:46], str(shown)[:14], f.get('period') or ''))
                npass += 1
            elif hero in missing and declared_absent:
                print('   PASS        %-46s (declared not in release)'
                      % hero[:46])
                npass += 1
            else:
                print('   FAIL        %-46s did not resolve' % hero[:46])
                nfail += 1
        print('')

    print('=' * 70)
    print('PASS %d   FAIL %d   UNVERIFIED %d   NO FIXTURE %d'
          % (npass, nfail, nunver, nofix))
    return 1 if nfail else 0


if __name__ == '__main__':
    sys.exit(main())
