# -*- coding: utf-8 -*-
r"""ONE RELEASE, ONE CARD. The fuller frame SUPERSEDES; it never appends.

★★★★ 'FIRST WINS' IS THE WRONG RULE AND 2026-11-02 PROVED IT. Two pairs
of frames reached the terminal that night and in BOTH pairs the EARLIER
frame was the truncated one. Keeping the first and dropping the rest
keeps the worst of each pair; printing both leaves the trader comparing
two cards for one print and deciding which to believe, under time
pressure, which is the decision this pipeline exists to remove.

★★★ AND THE MESSAGE ID CANNOT KEY IT. The same release crosses on two
services with two different ids, and the 8-K is a third delivery of the
same thing. _seen_ids and revisions.classify both key on the MESSAGE, so
neither can see that three frames are three views of one print.

★★ A HEADING WITH NOTHING UNDER IT IS NOT 'NONE WAS GIVEN'. 'OUTLOOK'
followed by silence reads as the company having declined to guide. On a
guidance-cadence name that is a trade-deciding misread, and the truth
was a body that had not finished arriving. The card says which.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper.listener import Listener, _wire_card   # noqa: E402

FAILED = []


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))
    if not ok:
        FAILED.append(msg)


class Fake(Listener):
    """A Listener with the network, the popup and the disk removed."""

    def __init__(self):
        self.watchlist = {'entries': {}}
        self.entries = {}
        self.model = None
        self._seen_ids = set()
        self._frames = {}
        self.stats = {}
        self.popup = None
        self.on_card = None
        self.verbose = False
        self.log_hits = False
        self.backfill_enabled = False
        self.emitted = []

    def _persist(self, card, item):
        return None

    def _backfill_async(self, card, item, path):
        return None

    def _print_summary(self, card):
        return None

    def _emit(self, card, item):
        before = len(self.emitted)
        Listener._emit(self, card, item)
        if len(self.emitted) == before and card.get('releaseKey'):
            self.emitted.append(card)


def frame(ticker, day, body, source=None):
    c = {'ticker': ticker, 'quarter': day, 'rendered': body}
    if source:
        c['documentSource'] = source
    return c


def run(listener, cards):
    """Feed frames in order; return the ones that reached the trader."""
    got = []
    for c in cards:
        listener.on_card = lambda card: got.append(card)
        listener._emit(c, {})
    return got


def main():
    SHORT = 'PLTR  WIRE\n>> OUTLOOK\n'
    FULL = SHORT + ('>> Revenue of between $2.649 - $2.653 billion.\n' * 4)

    # ── 1. the truncated frame arrives FIRST, as it did ─────────────────
    lis = Fake()
    got = run(lis, [frame('PLTR', '2026-11-02', SHORT),
                    frame('PLTR', '2026-11-02', FULL)])
    check(len(got) == 2 and got[1]['rendered'] == FULL,
          'the fuller frame reaches the trader even though it came '
          'SECOND (%d frames through)' % len(got))
    check(got[1].get('supersedes') is True,
          'and it is marked as superseding, so the display replaces the '
          'card rather than opening another')
    check(got[0]['releaseKey'] == got[1]['releaseKey'],
          'both carry the SAME releaseKey (%r) - which is how the display '
          'knows they are one print' % got[1].get('releaseKey'))

    # ── 2. a frame that adds nothing is dropped, silently ───────────────
    lis = Fake()
    got = run(lis, [frame('PLTR', '2026-11-02', FULL),
                    frame('PLTR', '2026-11-02', SHORT),
                    frame('PLTR', '2026-11-02', FULL)])
    check(len(got) == 1,
          'once the fullest frame is out, a shorter one and an identical '
          'one are both dropped (%d through, want 1)' % len(got))
    check(lis.stats.get('superseded') == 2,
          'and the drops are COUNTED, not invisible (%r)'
          % lis.stats.get('superseded'))

    # ── 3. the 8-K outranks any wire frame, however long ────────────────
    lis = Fake()
    got = run(lis, [frame('PLTR', '2026-11-02', FULL * 50),
                    frame('PLTR', '2026-11-02', SHORT, source='SEC-8K')])
    check(len(got) == 2 and got[1].get('documentSource') == 'SEC-8K',
          'a parsed 8-K supersedes a LONGER wire frame - hero rows beat '
          'word count, which raw length alone would get backwards')

    # ── 4. two different releases are two cards ─────────────────────────
    lis = Fake()
    got = run(lis, [frame('PLTR', '2026-11-02', FULL),
                    frame('AAPL', '2026-11-02', FULL),
                    frame('PLTR', '2026-11-03', FULL)])
    check(len(got) == 3,
          'a different ticker, and the same ticker on a different day, '
          'are separate releases and each gets its own card (%d)'
          % len(got))
    check(len({c['releaseKey'] for c in got}) == 3,
          'three distinct releaseKeys')

    # ── 5. a heading with no figures SAYS SO ────────────────────────────
    print('')
    card = _wire_card('PLTR', {'headline': 'Palantir Reports Q3 2026',
                               'body': 'Outlook\nFor Q4 2026, we expect:\n'})
    check('no figures under this heading' in card,
          'an OUTLOOK heading with no figures under it SAYS SO, rather '
          'than leaving silence that reads as "no guidance given"')
    check('NOT a statement that none was given' in card,
          'and it states only the fact, making no claim about WHY - a '
          'truncated body and a prose lead-in to a guidance TABLE read '
          'identically as text, and 14 of 14 blocks that looked '
          'truncated were really table lead-ins')
    # ★ THE INVERTED ONE. A real guidance block must NOT be slandered as
    # partial, or the warning stops meaning anything.
    full = _wire_card('PLTR', {
        'headline': 'Palantir Reports Q3 2026',
        'body': 'Outlook\nFor Q4 2026, we expect:\n'
                '•  Revenue of between $2.649 - $2.653 billion.\n'})
    check('PARTIAL FRAME' not in full,
          'and a block that DID arrive with its figures is not labelled '
          'partial - a warning that fires on good frames is noise')
    check('2.649' in full,
          'anti-vacuous: that block really is on the card (so the check '
          'above is not passing on an empty render)')


main()
if FAILED:
    sys.exit(1)
