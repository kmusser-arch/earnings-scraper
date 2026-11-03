# -*- coding: utf-8 -*-
r"""EVERY DUMP ROW CARRIES ITS PERIOD, AND A REPEATED LABEL SAYS WHICH IS OLD.

Apple's year-end release repeats the income statement inside a PRIOR-YEAR
non-GAAP reconciliation. Every column in that table is the September
BEFORE the one being reported and it sits under section '', so those rows
have no current-year sibling to lose the dedupe to. The card showed

    Net income   14,736      <- FQ4 2024 GAAP
    Net income   27,466      <- the quarter being reported

with nothing on the page to tell them apart. The parser knew the period
for both -- that is how the filter classified them -- and the display was
discarding it.

★ MARKED, NEVER DROPPED AND NEVER REORDERED. A filter can delete a good
row; a reorder hides the document's own sequence. Neither is needed once
the reader can see the date.

★★ THE ANTI-VACUOUS HALF IS THE REAL TEST. A marker that fires on every
row is as useless as one that never fires, and both would pass a check
that only looks for the word STALE somewhere in the output.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                     # noqa: E402
from scraper import prose_guidance as PG                    # noqa: E402
from scraper import selector as S                           # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scraper', 'fixtures', 'AAPL_2025Q4.html')

#: the five rows of the prior-year reconciliation, and the current-quarter
#: figure each one is mistakable for
PRIOR = {'Income before provision for income tax': '29,610',
         'Provision for income taxes': '14,874',
         'Net income': '14,736'}
#: ★ CONTROLS MUST BE ROWS THE PROFILE CANNOT PROMOTE. 'Total net sales'
#: was one of these until the FQ4 pre-earnings build mapped it as a hero,
#: at which point it left the dump body entirely and the assertion
#: "is not marked" searched an empty list and failed. The profile is LIVE
#: CONFIG and may map any label on any day; a display test that depends on
#: which rows happen to be heroes is testing the profile, not the display.
#: These two are income-statement lines no AAPL hero claims.
CURRENT = {'Net income': '27,466', 'Provision for income taxes': '5,338'}

#: and the promotion itself is now asserted, rather than assumed away
PROMOTED = ('F4Q Revenue ($M)', '102,466')


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def main():
    if not os.path.exists(FIXTURE):
        check(False, 'no FQ4 fixture -- the year-end shape is unverified '
                     'and this file asserts nothing')
        return
    html = io.open(FIXTURE, encoding='utf-8', errors='replace').read()
    rows = cells.from_html(html)
    res = S.select(rows, 'AAPL', prose_rows=PG.from_text(sec.to_text(html)))
    out = S.report(res, 'AAPL', 'FQ4', parser_rows=rows)
    body = [ln for ln in out.splitlines()
            if ln.startswith('     ') and not ln.startswith('  --')]

    # ── every row carries a period ───────────────────────────────────────
    bare = [ln for ln in body
            if not S._DATERE.search(ln) and 'not in release' not in ln]
    check(body and not bare,
          'all %d dump rows carry a period tag%s'
          % (len(body), '' if not bare else ' -- %d do NOT: %r'
             % (len(bare), bare[:2])))

    # ── the prior-year rows are tagged with the PRIOR September ──────────
    for lab, raw in sorted(PRIOR.items()):
        hit = [ln for ln in body if raw in ln]
        check(len(hit) == 1 and 'Sep 28, 2024' in hit[0],
              '%r (%s) is tagged %s'
              % (lab[:34], raw,
                 'Sep 28, 2024' if hit and 'Sep 28, 2024' in hit[0]
                 else 'WRONGLY: %r' % (hit[0].strip()[:60] if hit else None)))

    # ── and the repeated labels are marked, the fresh ones are not ───────
    for lab, raw in sorted(PRIOR.items()):
        if lab not in CURRENT:
            continue
        old = [ln for ln in body if raw in ln]
        check(old and 'STALE' in old[0],
              '%r repeats a label and the OLDER row is marked' % lab[:34])

    for lab, raw in sorted(CURRENT.items()):
        cur = [ln for ln in body if raw in ln]
        check(cur and all('STALE' not in ln for ln in cur),
              '%r (%s) is NOT marked - a marker that fires on the '
              'reported quarter is noise' % (lab[:30], raw))

    # ── a PROMOTED hero leaves the dump body, and that is correct ────────
    hero, raw = PROMOTED
    f = dict((h['hero'], h) for h in (res.get('found') or [])).get(hero)
    check(f is not None and f.get('raw') == raw,
          '%r is promoted to the hero block carrying %s%s'
          % (hero, raw,
             '' if f is not None and f.get('raw') == raw
             else ' -- GOT %r' % (f.get('raw') if f else None)))
    check(all(raw not in ln for ln in body),
          'and it does NOT also appear in the dump body - a row printed in '
          'both places would be counted twice by a reader')

    # ── ANTI-VACUOUS: the mark is rare, not universal ────────────────────
    n = sum(1 for ln in body if 'STALE' in ln)
    check(0 < n < len(body) // 4,
          'STALE marks %d of %d rows - present, and nowhere near all of '
          'them' % (n, len(body)))

    # ── and nothing was dropped or resequenced ───────────────────────────
    dump = S.current_quarter_rows(rows)
    claimed = set(str(f.get('label')) for f in (res.get('found') or []))
    check(len(body) == len([r for r in dump
                            if S.norm(r.get('label')) not in
                            set(S.norm(c) for c in claimed)]),
          'every surviving dump row still printed - the display MARKS, it '
          'does not filter')


main()
