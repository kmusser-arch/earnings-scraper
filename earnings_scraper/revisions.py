"""Story identity and revision handling for the live wire.

★ WHY THIS EXISTS
The wire re-fires the same story. In a 21,660-message capture: 21,396
`first-publication`, 217 `minor-update`, 47 `update` — 264 revisions that carry
the SAME `id` as a story already seen. Without suppression each one pushes a
second card for a print Kyle has already read, and the second card can disagree
with the first, because the body may have changed between them.

But suppression must not be blind, and the three classes are not the same event:

  first-publication  score it, record the id
  minor-update       no new card, one quiet line — a typo or a tag fix
  update             no new card, but a LOUD line. The company revised its own
                     release, and that revision is itself a trade.

★ ROUTING KEY
`primary_instruments` carries exchange-qualified tickers — ['EQ:US:OWLT'] —
populated on 10,856 of 21,660 news_items. That is a STRUCTURED match decided
before any parsing, so it replaces headline scraping for the routing decision.
Headline matching stays as a fallback for the half of the wire that carries no
instruments, because a release can name the company without the field being set.
"""

import re

# 'EQ:US:OWLT' -> 'OWLT'. The prefix is asset class and venue; a two-part form
# ('US:OWLT') and a bare ticker both appear, so take the last segment.
_INSTRUMENT = re.compile(r'^(?:[A-Z]{2,4}:)*([A-Z][A-Z0-9.\-]{0,9})$')

FIRST = 'first-publication'
MINOR = 'minor-update'
UPDATE = 'update'


def tickers_from_instruments(item):
    """Tickers from `primary_instruments`, or [] when the field is absent.

    ★ Structured and free. Decided before the body is touched, which is the
    whole latency argument: the wire carries every matched source's body in
    full mode, but the DECISION to parse costs nothing.
    """
    out = []
    for raw in (item or {}).get('primary_instruments') or []:
        m = _INSTRUMENT.match(str(raw).strip().upper())
        if m:
            out.append(m.group(1))
    return out


def related_tickers(item):
    """Secondary mentions. Never the routing key on their own -- a story ABOUT
    a competitor names the competitor, and grading a card off that is a false
    positive. Reported so a near-miss is visible, not acted on.
    """
    out = []
    for raw in (item or {}).get('related_instruments') or []:
        m = _INSTRUMENT.match(str(raw).strip().upper())
        if m:
            out.append(m.group(1))
    return out


class RevisionLog(object):
    """Which story ids have been scored, and what to do when one returns.

    Deliberately in-memory and per-session: a restart SHOULD re-score, because
    the operator has not seen the card from a session they were not watching.
    Persisting this would silently swallow the first card after a crash.
    """

    def __init__(self):
        self.seen = {}          # id -> the publish_type first seen under
        self.revisions = []     # (id, publish_type, headline)

    def classify(self, item):
        """Returns (action, note).

        action is 'score', 'suppress-quiet' or 'suppress-loud'.
        """
        sid = (item or {}).get('id')
        ptype = (item or {}).get('publish_type') or FIRST
        headline = (item or {}).get('headline') or ''

        if not sid:
            # ★ No id, so no dedup is possible. Score it: a missed duplicate is
            # recoverable by eye, a missed print is not.
            return 'score', ('no story id on this message — cannot dedup, '
                             'scoring it')

        if sid not in self.seen:
            self.seen[sid] = ptype
            if ptype == FIRST:
                return 'score', None
            # A revision arriving with no prior sighting: the original was
            # published before this session connected. It is new TO US.
            return 'score', ('%s arrived without the original having been '
                             'seen this session — scoring it as the first '
                             'sighting' % ptype)

        self.revisions.append((sid, ptype, headline))
        if ptype == UPDATE:
            return 'suppress-loud', (
                '⚠ THE COMPANY REVISED ITS OWN RELEASE — publish_type '
                '"update" on a story already scored this session. No second '
                'card, but the revision is ITSELF a trade: pull the new body '
                'and compare it against the card you already read.')
        if ptype == MINOR:
            return 'suppress-quiet', (
                'minor-update on an already-scored story — no new card')
        return 'suppress-quiet', (
            're-publication (%s) of an already-scored story — no new card'
            % ptype)

    def summary(self):
        n_upd = sum(1 for _i, p, _h in self.revisions if p == UPDATE)
        return dict(scored=len(self.seen), revisions=len(self.revisions),
                    materialUpdates=n_upd)
