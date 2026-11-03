# -*- coding: utf-8 -*-
r"""THE CARD. THREE SECTIONS, PERIOD-GROUPED, PRESET KPIs UNDER EACH.

★★★★ IT PULLS NUMBERS AND SHOWS THEM. No street, no bogey, no
CLEARS/MISSES, no branch, no base rate, no bracket width, no direction,
no magnitude. Every one of those is a judgment, and judgment happens in
chat, not here.

★★★ AND THE UNIT ON THE CARD IS THE DOCUMENT'S, NEVER CONVERTED. _scale
normalises a 'billion' to 1000s of millions so the table and prose
channels can be compared in one unit. Printing THAT under a label
reading ($B) renders the next-quarter guide as 2,649-2,653 -- the right
figure out by a factor of a thousand, on the single most-read line of
the night. The card shows '$2.649 - $2.653 billion', which is what
Palantir wrote.

★★ A KPI THAT DID NOT RESOLVE IS STILL LISTED. The preset set is the
preset set; a hero missing from a print IS the read, and a card that
drops it silently looks like a clean sheet.
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                       # noqa: E402
from scraper import prose_guidance as PG                      # noqa: E402
from scraper import selector as S                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, 'scraper', 'fixtures')
CORPUS = os.path.join(ROOT, 'earnings_scraper', 'state', 'html')

#: the vocabulary of JUDGMENT. None of it belongs on a card that pulls
#: numbers.
GRADING = ('bogey', 'missed', 'misses', 'clears', 'beat', 'beats',
           'branch', 'bracket', 'cohort', 'not graded', 'overall score',
           'fade zone', 'base rate', 'street')

#: the blocks that moved behind --full
DIAGNOSTIC = ('SCRAPER DIAGNOSTICS', 'UNCLASSIFIED', 'OVERFLOW',
              'everything else printed', 'heroes in profile')

#: PLTR Q3 2026 -- the figure AS PRINTED, with the document's own scale
#: word. Sourced from the Outlook block of the filed exhibit, not from
#: what the card happened to emit.
PRINTED = (('Next-Q Revenue Guide ($M)',              '$2.649 - $2.653 billion'),
           ('Next-Q Adj Income from Operations ($M)', '$1.640 - $1.644 billion'),
           ('FY Revenue Guide ($M)',                  '$8.530 - $8.534 billion'),
           ('FY Adj Income from Operations ($M)',     '$5.245 - $5.249 billion'),
           ('FY Adj Free Cash Flow ($M)',             '$4.8 - $5.0 billion'),
           ('Q3 Revenue ($K)',                        '2,313,411'),
           ('Adj EPS ($)',                            '0.44'))

FAILED = []


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))
    if not ok:
        FAILED.append(msg)


def read(path):
    return io.open(path, encoding='utf-8', errors='replace').read()


def build(path, ticker):
    html = read(path)
    text = sec.to_text(html)
    rows = cells.from_html(html)
    res = S.select(rows, ticker, prose_rows=PG.from_text(text))
    return res, rows, text


def main():
    pltr = os.path.join(FIX, 'PLTR_2026Q3.html')
    if not os.path.exists(pltr):
        check(False, 'PLTR_2026Q3 fixture missing -- this file asserts '
                     'nothing')
        return
    res, rows, text = build(pltr, 'PLTR')
    card = S.card(res, 'PLTR', 'Q3 2026', source_text=text)

    # ── 1. three sections, in this order, and no fourth ─────────────────
    heads = [ln for ln in card.splitlines()
             if ln and ln == ln.upper() and not ln.startswith((' ', '>>'))
             and not any(ch.isdigit() for ch in ln)]
    check(heads == ['CURRENT QUARTER', 'NEXT QUARTER', 'FULL YEAR'],
          'the card has exactly three sections, in order: %s' % heads)

    # ── 2. the unit is the DOCUMENT'S, never the normalised number ──────
    print('')
    for hero, want in PRINTED:
        label = S._card_label(hero)
        line = next((ln for ln in card.splitlines()
                     if ln.strip().startswith(label)), None)
        got = line.replace(label, '', 1).strip() if line else None
        check(got == want,
              '%-40s %s' % (label,
                            want if got == want
                            else 'WANT %r GOT %r' % (want, got)))
    # ★ THE INVERTED ONE. The normalised figure must appear NOWHERE: it
    # is the same number with the decimal point moved three places, and
    # on a card it is indistinguishable from a correct reading.
    flat = card.replace(',', '')
    check('2649' not in flat and '8530' not in flat and '5245' not in flat,
          'and the NORMALISED figure (2649 / 8530 / 5245) appears nowhere '
          'on the card - a $B label over a $M number is a 1000x error '
          'that reads as a clean row')

    # ── 3. every preset KPI is listed, resolved or not ──────────────────
    print('')
    profiles, _mt = S.load_profiles()
    heroes = [h['name'] for h in profiles['PLTR']['heroKPIs']]
    periodic = [h['name'] for h in profiles['PLTR']['heroKPIs']
                if h.get('appliesTo') in ('currentQuarter', 'nextQGuidance',
                                          'fyGuidance')]
    absent = [n for n in periodic if S._card_label(n) not in card]
    check(not absent,
          'all %d of the profile KPIs that carry a period are listed, '
          'resolved or blank%s'
          % (len(periodic), '' if not absent else ' -- MISSING %s' % absent))
    check(len(periodic) < len(heroes),
          'anti-vacuous: PLTR has %d heroes and %d of them carry a '
          'period, so the check above is not comparing a list to itself'
          % (len(heroes), len(periodic)))
    # the ones with no period are OFF the card but still COUNTED
    check(re.search(r'\d+ narrative rows?, no period section', card),
          'and a hero on no period is NAMED in the status line - '
          '"off-card (no period)" read like a silent drop; it is the '
          'narrative hero, and it still counts against the profile')

    # ── 4. no judgment, no diagnostics, on ANY card in the corpus ───────
    print('')
    dirty, diag, built = [], [], 0
    for d in (FIX, CORPUS):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.html'):
                continue
            tic = fn.split('_')[0].upper()
            if tic not in profiles:
                continue
            r, _rows, t = build(os.path.join(d, fn), tic)
            c = S.card(r, tic, '', source_text=t)
            built += 1
            # ★★★ THE SCRAPER'S WORDS, NOT THE COMPANY'S. ServiceNow's
            # own headline is 'ServiceNow beats high end of guidance
            # across all Q1 2026 topline growth and profitability
            # metrics' -- quoted verbatim under a banner that says NOT
            # PARSED. Scanning that for the word 'beats' asserts that no
            # issuer ever writes it, which is not a property of this
            # code and is false besides. The rule is that the SCRAPER
            # has no opinion; a quotation is not an opinion.
            mine = [ln for ln in c.splitlines()
                    if not ln.lstrip().startswith('>>')]
            low = '\n'.join(mine).lower()
            for w in GRADING:
                if re.search(r'\b%s\b' % re.escape(w), low):
                    dirty.append((fn, w))
            for w in DIAGNOSTIC:
                if w.lower() in low:
                    diag.append((fn, w))
    check(built >= 100,
          'anti-vacuous: %d cards were actually built' % built)
    check(not dirty,
          'no grading vocabulary on any of %d cards%s'
          % (built, '' if not dirty else ' -- %r' % dirty[:4]))
    check(not diag,
          'and no diagnostics block on any of them%s'
          % ('' if not diag else ' -- %r' % diag[:4]))

    # ── 5. the default must be SHORTER than --full ──────────────────────
    print('')
    full = S.report(res, 'PLTR', 'Q3 2026', parser_rows=rows,
                    source_text=text)
    check(len(card.splitlines()) < len(full.splitlines()),
          'the default card is SHORTER than --full: %d lines vs %d - the '
          'whole point was fewer lines, and a "simplified" view that '
          'grew is the thing this was asked to replace'
          % (len(card.splitlines()), len(full.splitlines())))
    check('>> HEADLINE' in card and 'Outlook' in card,
          'and it still carries the verbatim source blocks, which are '
          'the only thing on a table-less release that can be read')


main()
if FAILED:
    sys.exit(1)
