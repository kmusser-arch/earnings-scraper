# -*- coding: utf-8 -*-
r"""NO CELLS -> NO ROWS. NEVER FALL BACK TO PROSE. AND NEVER GRADE.

THE FOUNDING CASE, 2026-11-02, LIVE, ON A 12% IMPLIED MOVE. The listener's
8-K path ran parse -> score -> scorecard on the exhibit's STRIPPED TEXT.
sec.press_release returns text, so cells.from_html could never run, the
table scan returned {}, and an empty scan was treated as "try something
else" rather than "there is nothing here". The prose matcher took the
first "revenue ... $X billion" phrase in the document -- Palantir's U.S.
REVENUE bullet, 1937.0 -- paired it with a growth rate from a DIFFERENT
bullet (148%, U.S. commercial), named it 3Q Revenue, compared it to a
bogey of 2320 and printed "missed bogey".

Total revenue was 2,313,411. It CLEARED. The most important row of the
night was graded backwards.

★ THE PROSE MATCHER WAS NOT THE BUG. THE FALLBACK WAS. A blank row is
honest; a prose-derived row wearing a hero's name is not.

★★ AND THE CARD MUST NOT GRADE AT ALL. It had to be comparing against a
bogey to get the chance to be wrong about one. A card that prints
`Revenue 2,313,411` cannot grade it backwards.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                     # noqa: E402
from scraper import prose_guidance as PG                    # noqa: E402
from scraper import selector as S                           # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'scraper', 'fixtures')

#: the vocabulary of JUDGMENT. None of it belongs on a card that pulls
#: numbers. 'score' is here too -- the scraper has no opinion to score.
GRADING = ('bogey', 'missed', 'misses', 'clears', 'beat', 'beats',
           'branch', 'bracket', 'cohort', 'not graded', 'overall score',
           'fade zone')

#: what the selector returned on tonight's LIVE documents. Defect 3 was
#: AAPL iPhone, which the old scorer REFUSED because 'iPhone' resolved
#: twice -- 57,583 (three months) and 254,098 (twelve months) -- and it
#: had no period filter to run first.
LIVE = [('PLTR_2026Q3', 'Revenue', '2,313,411'),
        ('AAPL_2026Q4', 'iPhone', '57,583'),
        ('AAPL_2026Q4', 'Total net sales', '114,477')]


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def card_for(path, html):
    rows = cells.from_html(html)
    text = sec.to_text(html)
    res = S.select(rows, os.path.basename(path).split('_')[0],
                   prose_rows=PG.from_text(text))
    return rows, S.report(res, os.path.basename(path).split('_')[0], '',
                          source_text=text)


def main():
    fixtures = sorted(f for f in os.listdir(FIX) if f.endswith('.html'))
    if not fixtures:
        check(False, 'no fixtures -- this file asserts nothing')
        return

    # ── (c) THE NEGATIVE CONTROL. The exact input that produced 1937.0 ──
    pltr = os.path.join(FIX, 'PLTR_2026Q3.html')
    if os.path.exists(pltr):
        html = io.open(pltr, encoding='utf-8', errors='replace').read()
        stripped = sec.to_text(html)          # what press_release returned
        check('1.937 billion' in re.sub(r'\s+', ' ', stripped),
              'the stripped text DOES contain "$1.937 billion" - the '
              'tempting wrong answer is really in there, so a pass below '
              'means the fallback is gone, not that the bait is missing')
        rows = cells.from_html(stripped)
        check(not rows,
              'stripped TEXT yields ZERO cells (%d)' % len(rows))
        res = S.select(rows, 'PLTR', prose_rows=PG.from_text(stripped))
        found = res.get('found') or []
        vals = [str(f.get('raw')) for f in found]
        check(not found,
              'and ZERO hero rows resolve from it - not a wrong row, not '
              'a guessed row, ZERO%s'
              % ('' if not found else ' -- GOT %s' % vals))
        check(all('1937' not in v.replace(',', '') for v in vals),
              'nothing anywhere in the result equals 1937')

        # ★ AND THE ZERO-CELL CARD IS STILL USEFUL. Refusing to invent a
        # row must not mean refusing to show the release. The source
        # blocks are verbatim and need no tables at all.
        card = S.report(res, 'PLTR', '', source_text=stripped)
        check('>> HEADLINE' in card and 'NOT PARSED' in card,
              'a ZERO-CELL card still carries the verbatim source blocks')
        check('2.649' in card or 'Outlook' in card,
              "including the Outlook guidance, which never needed a table")
        check(not [ln for ln in card.splitlines()
                   if ln.startswith('ok ') or ln.startswith(' ~ ')],
              'and still shows NO hero rows')

    # ── (b) no grading vocabulary on any card ───────────────────────────
    dirty = []
    for fn in fixtures:
        html = io.open(os.path.join(FIX, fn), encoding='utf-8',
                       errors='replace').read()
        _rows, card = card_for(fn, html)
        low = card.lower()
        for word in GRADING:
            if re.search(r'\b%s\b' % re.escape(word), low):
                dirty.append((fn, word))
    check(not dirty,
          'no grading vocabulary on any of %d cards%s'
          % (len(fixtures), '' if not dirty else ' -- %r' % dirty[:4]))

    # ── (d) the live pins, so defect 3 cannot silently return ───────────
    for fn, label, raw in LIVE:
        path = os.path.join(FIX, '%s.html' % fn)
        if not os.path.exists(path):
            check(False, '%s missing -- %s unpinned' % (fn, label))
            continue
        html = io.open(path, encoding='utf-8', errors='replace').read()
        _rows, card = card_for(fn, html)
        hit = [ln for ln in card.splitlines()
               if ln.lstrip().startswith(('ok ', '~ '))
               and ln.split(None, 2)[1:2] == [label.split()[0]]]
        got = [ln for ln in card.splitlines() if raw in ln]
        check(bool(got),
              '%s %s resolves to %s' % (fn, label, raw)
              + ('' if got else ' -- NOT PRESENT ON THE CARD'))


main()
