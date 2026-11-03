# -*- coding: utf-8 -*-
r"""A RAW TAIL WHEN THE FENCES MISS. It asserts nothing, by design.

★★★★ THE FOUNDING CASE, 2026-11-03, TWO HOURS BEFORE A PRINT. The plan
for AMD rested on "the Outlook paragraph renders verbatim and Kyle reads
it". It did not render. There was no OUTLOOK block on the card at all,
so '$13 billion, plus or minus $300 million' -- the row that decides the
trade -- appeared nowhere: not as a hero row, not as quoted text.

TWO FENCES MISSED, NOT ONE. _OUTLOOK matches the word alone and AMD
heads the block 'Current Outlook'; and _block continues only through
bullets, 'For <period>' lead-ins and colon lines, while AMD writes its
outlook as PARAGRAPHS. Fixing the heading alone changes nothing across
124 documents -- measured, because the second fence still breaks at the
first line.

★★★ SO THE TAIL CLAIMS NOTHING, AND THAT IS THE ENTIRE DIFFERENCE FROM
THE MARKER THAT FAILED. The truncation marker made a statement about the
document -- 'this body is partial' -- and was wrong 14 times out of 14.
This says only: a heading matched, the fences did not, here are the next
few lines unparsed. The worst case is irrelevant text on screen, which
costs a glance; a false statement about a guidance block costs a trade.

★★ AND IT IS DISPLAY ONLY. prose_guidance is untouched, so no hero row
can resolve from anything quoted here. Measured additive across the
corpus: 16 documents gain a block, none loses one, and six of them gain
real forward guidance that was previously invisible -- Amazon's full Q4
bullets, Qualcomm's 'Revenues $9.7B - $10.5B', Seagate's 'Revenue of
$4.1 billion, plus or minus $100 million'.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells, sec                       # noqa: E402
from scraper import passthrough as PT                         # noqa: E402
from scraper import prose_guidance as PG                      # noqa: E402
from scraper import selector as S                             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, 'scraper', 'fixtures')
CORPUS = os.path.join(ROOT, 'earnings_scraper', 'state', 'html')

FAILED = []


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))
    if not ok:
        FAILED.append(msg)


def read(p):
    return io.open(p, encoding='utf-8', errors='replace').read()


def main():
    amd = os.path.join(FIX, 'AMD_2026Q2.html')
    if not os.path.exists(amd):
        check(False, 'AMD_2026Q2 fixture missing -- nothing asserted')
        return
    text = sec.to_text(read(amd))

    # ── the two fences that missed, both still missing ──────────────────
    check(not PT._OUTLOOK.match('Outlook ahead'),
          'the heading fence is still a fence: it does not match an '
          'arbitrary line that merely contains the word')
    check(bool(PT._OUTLOOK.match('Current Outlook')),
          "and it now matches 'Current Outlook', which is what this "
          'issuer calls the block')

    tail = PT.raw_tail(text, PT._OUTLOOK)
    check(bool(tail), 'the raw tail fires on a paragraph-shaped outlook')
    body = '\n'.join(tail)
    check('plus or minus $300 million' in body,
          'AND IT CARRIES THE GUIDE: the figure that was on no part of '
          'the card is now quoted verbatim')
    check('Non-GAAP gross margin is expected to be approximately 56%'
          in body,
          'including the margin guide from the same paragraph')
    check(len(tail) <= PT._RAW_TAIL + 1,
          'and it is capped at %d lines (%d) - over-running into the '
          'next heading is acceptable noise, unbounded output is not'
          % (PT._RAW_TAIL + 1, len(tail)))

    # ── it makes no claim ───────────────────────────────────────────────
    titles = [t for t, _b in PT.blocks(text)]
    raw = [t for t in titles if t.startswith('OUTLOOK - RAW')]
    check(len(raw) == 1 and 'FENCES DID NOT MATCH' in raw[0],
          'the block is labelled RAW and says the fences missed, so a '
          'quotation cannot be read as a parse: %r' % (raw or titles))

    # ── ★ NO HERO ROW MAY COME FROM IT ──────────────────────────────────
    print('')
    check(not PG.from_text(text),
          'prose_guidance still returns ZERO rows for this document - '
          'the raw tail is display, and the hero channel never sees it')
    rows = cells.from_html(read(amd))
    res = S.select(rows, 'AMD', prose_rows=PG.from_text(text),
                   source_text=text)
    prose = [f for f in res.get('found') or []
             if f.get('channel') == 'prose']
    check(not prose,
          'and no AMD hero resolves through the prose channel%s'
          % ('' if not prose else ' -- GOT %s' % [p['hero'] for p in prose]))
    card = S.card(res, 'AMD', 'Q2 2026', source_text=text)
    check('plus or minus $300 million' in card,
          'while the card DOES carry the guide text, which is the whole '
          'point of the change')

    # ── it fires only where a fenced block came back empty ──────────────
    print('')
    pltr = os.path.join(FIX, 'PLTR_2026Q3.html')
    if os.path.exists(pltr):
        t2 = sec.to_text(read(pltr))
        ts = [t for t, _b in PT.blocks(t2)]
        check('OUTLOOK' in ts and not [x for x in ts
                                       if x.startswith('OUTLOOK - RAW')],
              'a document whose fenced OUTLOOK already works keeps the '
              'parsed block and gains no raw one: %s' % ts)

    # ── additive over the corpus: nothing may LOSE a block ──────────────
    lost, gained, n = [], 0, 0
    for d in (FIX, CORPUS):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.html'):
                continue
            n += 1
            t3 = sec.to_text(read(os.path.join(d, fn)))
            ts = [x for x, _b in PT.blocks(t3)]
            if [x for x in ts if x.startswith('OUTLOOK - RAW')]:
                gained += 1
            # a raw tail must never replace a real one
            if ('OUTLOOK' in ts
                    and [x for x in ts if x.startswith('OUTLOOK - RAW')]):
                lost.append(fn)
    check(n >= 100, 'anti-vacuous: %d documents went through' % n)
    check(gained > 0,
          'anti-vacuous: %d documents actually carry a raw tail' % gained)
    check(not lost,
          'and no document shows BOTH a parsed outlook and a raw one%s'
          % ('' if not lost else ' -- %s' % lost))


main()
if FAILED:
    sys.exit(1)
