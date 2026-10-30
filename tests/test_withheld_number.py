# -*- coding: utf-8 -*-
r"""A WITHHELD NUMBER IS A FINDING, AND RESOLVING IT IS A DEFECT.

Intel was asked for 2027 capex and declined to give one: "we expect 2027
gross capital spending to be up strongly", and Zinsner on the call, "we
haven't exactly locked into the number." 2026 remains $20B; an analyst
floated $30B and management did not confirm it.

In this model that refusal is a SCORED EVENT -- it sits on the
do-not-automate list under withdrawn metrics, capped roadmaps and
volunteered ceilings. If the scraper ever returns a figure for that row it
has not gained coverage, it has converted a deliberate refusal into a data
point, and the number it returns will be 20 or 30: both present in the
document's orbit, neither guided.

★ THIS IS AN INVERTED TEST. Every other check in the suite asserts that
something resolves. This one asserts that something does NOT, which is why
it carries its own positive control: a test that passes because nothing
ever resolves would pass on a completely broken selector.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                     # noqa: E402
from scraper import prose_guidance as PG                    # noqa: E402
from scraper import selector as S                           # noqa: E402
from scraper import validate_maps as VM                     # noqa: E402

TICKER = 'INTC'
WITHHELD = 'FY+1 capex'


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    path = VM.fixture_for(TICKER)
    if not path:
        check(False, 'no %s fixture -- this assertion cannot run' % TICKER)
        return
    html = io.open(path, encoding='utf-8', errors='replace').read()
    rows = cells.from_html(html)
    res = S.select(rows, TICKER, prose_rows=PG.from_text(sec.to_text(html)))

    found = dict((f['hero'], f) for f in (res.get('found') or []))
    missing = dict((n['hero'], n) for n in (res.get('notInRelease') or []))

    hero = ([h for h in found if h.startswith(WITHHELD)]
            + [h for h in missing if h.startswith(WITHHELD)])
    check(len(hero) == 1,
          'the withheld row is present in the profile at all (%d match%s) '
          '- a renamed hero would make every assertion below vacuous'
          % (len(hero), '' if len(hero) == 1 else 'es'))
    if len(hero) != 1:
        return
    name = hero[0]

    # ── the inversion ────────────────────────────────────────────────────
    got = found.get(name)
    check(got is None,
          'the withheld number does NOT resolve%s'
          % ('' if got is None
             else ' -- RESOLVED TO %r FROM %r, which is a defect, not '
                  'coverage' % (got.get('raw'), got.get('label'))))
    check(name in missing,
          'and it is reported as an ABSENCE rather than dropped - a '
          'silently missing hero is how a declined guide stops being '
          'visible at all')
    if name in missing:
        check(missing[name].get('channel') == 'call',
              "the absence is attributed to the CALL, not the release - "
              '"ask the transcript" and "the company did not say" are '
              'different findings (got %r)'
              % missing[name].get('channel'))

    # ── POSITIVE CONTROL: this file must not pass on a dead selector ─────
    check(len(found) >= 3,
          'while OTHER %s heroes still resolve (%d of %d) - without this '
          'the inversion above would pass on a selector that returns '
          'nothing for anything'
          % (TICKER, len(found), len(found) + len(missing)))


main()
