"""The noise filter. Pure functions, no I/O, nothing network-bound.

Nine layers, cheapest first. Anything that can HARD DROP runs before anything
that has to score, so the 94% of the wire that will never matter costs a set
lookup and a substring scan.

    L0  source triage        drop  EDG/PCR/ADD/UNDF outright
    L1  dedup                drop  same normalised headline inside the window
    L2  release-type gate    drop  readouts, remarks, appointments (TIER_Z)
    L3  vocabulary tier      score TIER_A +5 / TIER_B +2
    L5  homonym guard        drop  corporate share repurchases
    L6  instrument / topic   score +2 for a curated macro tag
    L4  novelty / delta      score +3 when a number CHANGED vs the ledger
    L7  calendar prior       relief on the floor inside a hot window
    L9  corroboration        mark a second independent source

L4 is deliberately numbered out of order: it is the strongest filter in the
list and it is the one that needs state, so it runs last among the scorers.
"""

import re
import time

from . import config


# --- normalisation -----------------------------------------------------------

_TICKER = re.compile(r'\$[A-Za-z][A-Za-z.\-]{0,5}\b')
_PREFIX = re.compile(
    r'^(?:mw|update|updated|correct(?:ed)?|exclusive|breaking|more|'
    r'press release|top news today)\s*[:\-]?\s*', re.I)
_SUFFIX = re.compile(r'\s*--\s*(?:wsj|marketwatch|barrons?\.com|market talk|'
                     r'ibd|update|\d+-)\s*$', re.I)
_PARENS = re.compile(r'\((?:more|cont|continued)\)', re.I)
_NONWORD = re.compile(r'[^a-z0-9 ]+')
_WS = re.compile(r'\s+')


def normalise(headline):
    """Collapse a headline to a dedup key.

    FTI republished ONE headline six times on 08/19 and DJN emitted the same
    Market Talk three times in the same second, each with a distinct message
    id. Deduping on id catches none of that.
    """
    h = (headline or '').lower()
    h = _TICKER.sub(' ', h)
    h = _PARENS.sub(' ', h)
    h = _SUFFIX.sub(' ', h)
    for _ in range(3):                       # "Update: MW ..." nests
        new = _PREFIX.sub('', h)
        if new == h:
            break
        h = new
    h = _NONWORD.sub(' ', h)
    return _WS.sub(' ', h).strip()


# --- number extraction (feeds L4) --------------------------------------------

_AMOUNT = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*(billion|bn|b|million|mm|m|trillion|tn|t)\b',
    re.I)
_MULT = {'trillion': 1e12, 'tn': 1e12, 't': 1e12,
         'billion': 1e9, 'bn': 1e9, 'b': 1e9,
         'million': 1e6, 'mm': 1e6, 'm': 1e6}


def extract_amounts(text):
    """Every dollar figure in the text, normalised to units.

    The founding case carried its own delta in plain language:
    "Current maximum size of $2B per operation will be at least $4B" -- both
    the old value and the new one in a single sentence.
    """
    out = []
    for num, unit in _AMOUNT.findall(text or ''):
        try:
            out.append(float(num.replace(',', '')) * _MULT[unit.lower()])
        except (ValueError, KeyError):
            continue
    return out


# Directional verbs only. 'from', 'up to', 'effective' and 'beginning' were
# in this tuple originally and appear in almost every English sentence on the
# wire, so the +1 they carried was not discriminating between anything.
_CHANGE_WORDS = (
    'increas', 'decreas', 'raise', 'raised', 'raising', 'cutting',
    'double', 'doubles', 'doubling', 'triple', 'expand', 'expands',
    'expanding', 'boost', 'boosts', 'reduce', 'reduces',
    'at least', 'to at least', 'revise', 'revised', 'new maximum',
)


# --- the verdict -------------------------------------------------------------

class Verdict:
    __slots__ = ('action', 'tier', 'score', 'floor', 'reasons', 'drop_reason',
                 'key', 'amounts', 'corroborated')

    def __init__(self):
        self.action = 'DROP'
        self.tier = None
        self.score = 0.0
        self.floor = config.ALERT_FLOOR
        self.reasons = []
        self.drop_reason = None
        self.key = None
        self.amounts = []
        self.corroborated = False

    @property
    def alert(self):
        return self.action == 'ALERT'

    def __repr__(self):
        if self.action == 'DROP':
            return '<Verdict DROP %s>' % (self.drop_reason,)
        return '<Verdict %s tier=%s %.1f/%.1f %s>' % (
            self.action, self.tier, self.score, self.floor,
            ' '.join(self.reasons))


def _compile(vocab):
    """Word-boundary matchers, with acronyms held case-sensitive.

    Plain substring matching is not survivable here: 'tga' inside "mortgage"
    scored every MBA survey in the feed as Tier-A on the first replay, and
    'tips' would do the same to any headline offering advice.
    """
    plain = sorted((w for w in vocab if w not in config.ACRONYMS),
                   key=len, reverse=True)
    acro = sorted(w for w in vocab if w in config.ACRONYMS)
    # The trailing 's?' is load-bearing. Without it 'buyback' does not match
    # "Treasury Increases Buybacks" -- the plural is how every outlet writes
    # the headline, and a bare boundary silently misses all of them.
    p = re.compile(r'(?<![a-z0-9])(%s)s?(?![a-z0-9])'
                   % '|'.join(re.escape(w) for w in plain)) if plain else None
    a = re.compile(r'\b(%s)\b' % '|'.join(w.upper() for w in acro)) if acro else None
    return p, a


_A_PAT = _compile(config.TIER_A)
_B_PAT = _compile(config.TIER_B)
_Z_PAT = _compile(config.TIER_Z)
_SOV_PAT = _compile(config.SOVEREIGN_CONTEXT)
_CORP_PAT = _compile(config.CORPORATE_TELLS)


def _hits(text, pats):
    """text is (lowercased, original-case). Returns matched terms, longest
    first, so 'liquidity support' reports ahead of 'buyback'."""
    lower, raw = text
    plain, acro = pats
    out = []
    if plain:
        out.extend(m.group(1) for m in plain.finditer(lower))
    if acro:
        out.extend(m.group(1).lower() for m in acro.finditer(raw))
    return out


def _text_of(item):
    """headline + teaser + body, with exact repeats dropped.

    HAM sets teaser == headline on every squawk. Concatenating both makes
    extract_amounts() report each figure twice, which is harmless for matching
    and wrong for anything that reads v.amounts.
    """
    segs, seen_seg = [], set()
    for seg in (item.get('headline'), item.get('teaser'), item.get('body')):
        if seg and seg not in seen_seg:
            seen_seg.add(seg)
            segs.append(seg)
    raw = ' '.join(segs)
    return raw.lower(), raw


def _continuation(src, seen, now):
    """The most recent story still open for this source, or None.

    Same-source is the precision guard. A different outlet writing about the
    same event is commentary; the SAME desk posting again inside ten minutes
    is finishing a sentence it started -- which is literally what HAM did with
    "(more) US Treasury: Change is effective September 9."
    """
    if seen is None:
        return None
    best, best_t = None, 0.0
    for key, row in seen.items():
        if not key.startswith('#story:'):
            continue
        if row.get('src') != src:
            continue
        # cont_t advances only on a real ALERT or ENRICH. row['t'] slides on
        # every suppressed mention, and measuring the continuation window off
        # it held the window open all morning -- long enough for six unrelated
        # HAM squawks ($COSM results, a $ZSTK deal) to attach themselves to
        # the buyback story and invent a 2B->1B delta out of one of them.
        ct = row.get('cont_t', row['t'])
        if (now - ct) > config.CONTINUATION_WINDOW_S:
            continue
        if ct > best_t:
            best, best_t = key[len('#story:'):], ct
    return best


def classify(item, ledger=None, seen=None, now=None, hot=None):
    """Score one wire item or one treasury.gov release.

    `item` is the gateway message shape: headline / teaser / body / source /
    primary_instruments / topics. The treasury.gov poller emits the same shape
    with source='GOV' so both paths share this one filter.
    """
    v = Verdict()
    now = time.time() if now is None else now
    src = (item.get('source') or '').upper()
    text = _text_of(item)
    v.key = normalise(item.get('headline'))

    # L0 -- source triage. 74% of the wire leaves here for one set lookup.
    if src in config.NEVER_ALERT:
        v.drop_reason = 'L0 source %s never alerts' % src
        return v
    if not v.key:
        v.drop_reason = 'L0 empty headline'
        return v

    # L1 -- dedup on the normalised headline.
    if seen is not None:
        prev = seen.get(v.key)
        if prev is not None and (now - prev['t']) < config.DEDUP_WINDOW_S:
            # L9 -- a DIFFERENT source repeating it is corroboration, not
            # noise. It still does not re-alert, but it is worth recording.
            if src != prev.get('src'):
                prev.setdefault('srcs', []).append(src)
                v.corroborated = True
                v.action = 'CONFIRM'
                v.drop_reason = 'L1 dup (corroborates %s)' % prev.get('src')
            else:
                v.drop_reason = 'L1 dup of %s %.0fs ago' % (
                    prev.get('src'), now - prev['t'])
            return v

    # L2 -- release-type gate. Ceremonial and personnel releases, dropped even
    # when a Tier-A word rides along in the body.
    z = _hits(text, _Z_PAT)
    if z:
        v.drop_reason = 'L2 tier-Z %r' % z[0]
        return v

    # L3 -- vocabulary tier.
    a = _hits(text, _A_PAT)
    b = _hits(text, _B_PAT)
    if a:
        v.tier = 'A'
        v.score += 5.0
        v.reasons.append('A:%s' % a[0])
    elif b:
        v.tier = 'B'
        v.score += 2.0
        v.reasons.append('B:%s' % b[0])
    else:
        # L10 -- CONTINUATION ATTACH. The strongest argument against keyword
        # filtering, straight off the 08/19 tape:
        #
        #   08:38:40 HAM "$SPY US Treasury: Current maximum size of $2B per
        #                 operation will be at least $4B per operation"
        #
        # That is the whole trade -- the old ceiling, the new ceiling, the
        # doubling -- and it contains NO Tier-A term. Read alone it is
        # unclassifiable. Read as the third message of an open story from the
        # same desk, it is the only one that mattered.
        #
        # So: while a story is open, figures from the SAME source attach to it
        # instead of being dropped. They enrich the open card; they do not
        # raise a second alarm.
        fam = _continuation(src, seen, now)
        # Same source plus a dollar sign is NOT enough -- HAM posts a figure
        # every few minutes. The item must also still be topically adjacent to
        # the open story, which for debt_supply means a sovereign-debt word.
        if fam and _hits(text, _SOV_PAT):
            v.amounts = extract_amounts(text[0])
            if v.amounts or _PARENS.search(item.get('headline') or ''):
                v.tier = 'cont'
                v.action = 'ENRICH'
                v.reasons.append('cont:%s' % fam)
                if ledger is not None and v.amounts:
                    d = ledger.delta('buyback', v.amounts, text[0]) \
                        if fam == 'debt_supply' else None
                    if d:
                        v.reasons.append('delta:%s' % d)
                st = seen.get('#story:' + fam)
                if st is not None:
                    st['cont_t'] = now
                    st['figs'].update(round(x) for x in v.amounts)
                return v
        v.drop_reason = 'L3 no tier vocabulary'
        return v

    # L5 -- the homonym guard. "buyback" without a sovereign-debt word is a
    # share repurchase, and share repurchases were four of the five buyback
    # headlines in the founding 45-minute window.
    if any('buyback' in w or 'repurchase' in w for w in a):
        if _hits(text, _CORP_PAT):
            v.drop_reason = 'L5 corporate repurchase'
            return v
        if not _hits(text, _SOV_PAT):
            v.drop_reason = 'L5 buyback without sovereign context'
            return v
        v.reasons.append('sovereign')

    # L0b -- only the fast desks may originate an alert. Everyone else can
    # confirm. DJN carried this story 32 minutes late; it will never be the
    # reason we take the trade.
    if src in config.FAST_SOURCES:
        v.score += 2.0
        v.reasons.append('fast:%s' % src)
    elif src == 'GOV':
        # +2, not +3. At +3 a bare Tier-B release cleared the floor on the
        # authority of the source alone, and treasury.gov published two Iran
        # sanctions notices that paged as if they were debt-management news.
        # Tier-B must not be able to reach the floor unaided: 2 (tier) + 2
        # (gov) + 1 (change verb) = 5, below the 6.0 floor, so a second-order
        # topic now needs a macro instrument or topic tag to interrupt anyone.
        v.score += 2.0
        v.reasons.append('gov')

    # L6 -- curated tags. Free classification, better than our keyword list.
    if config.MACRO_INSTRUMENTS.intersection(item.get('primary_instruments') or ()):
        v.score += 2.0
        v.reasons.append('instr')
    if config.MACRO_TOPICS.intersection(item.get('topics') or ()):
        v.score += 2.0
        v.reasons.append('topic')

    # L4 -- NOVELTY. The strongest filter here, and the one the 08/19 trade
    # actually turned on: "increased sizes" is only news against the size that
    # was standing before it. Treasury restates its existing operating
    # parameters constantly; a restatement must not fire.
    v.amounts = extract_amounts(text[0])
    if ledger is not None and v.tier == 'A':
        delta = ledger.delta(a[0], v.amounts, text[0])
        if delta is not None:
            v.score += 3.0
            v.reasons.append('delta:%s' % delta)
        elif v.amounts and ledger.is_restatement(a[0], v.amounts):
            v.drop_reason = 'L4 restates known value'
            return v
    if any(w in text[0] for w in _CHANGE_WORDS):
        v.score += 1.0
        v.reasons.append('change-verb')

    # L7 -- calendar prior. Inside a scheduled announcement window the bar for
    # interrupting comes down.
    # Relief is for Tier-A only. A Tier-B item scoring 4.0 has no business
    # interrupting a trader just because the clock is in a hot window -- that
    # is how "$TGT exec notes ... tariffs" fired on the first replay.
    if hot and v.tier == 'A':
        v.floor -= config.HOT_FLOOR_RELIEF
        v.reasons.append('hot')

    if seen is not None:
        seen[v.key] = {'t': now, 'src': src, 'srcs': [src]}

    v.action = 'ALERT' if v.score >= v.floor else 'LOG'

    # L8 -- STORY COOLDOWN. The single largest remaining noise class once the
    # vocabulary is clean: one event, twelve outlets, twelve distinct
    # headlines. Demote repeats on the same CONCEPT to CONFIRM, but never
    # demote one that carries a figure we have not seen -- the follow-up
    # carrying "$2B -> at least $4B" is the message the trade sizes on.
    if v.action == 'ALERT' and seen is not None:
        term = (a or b)[0]
        concept = config.STORY_FAMILY.get(term, term)
        if concept:
            skey = '#story:' + concept
            story = seen.get(skey)
            fresh_figure = bool(v.amounts) and (
                story is None
                or any(round(x) not in story['figs'] for x in v.amounts))
            if story and (now - story['t']) < config.STORY_COOLDOWN_S \
                    and not fresh_figure and 'delta' not in ' '.join(v.reasons):
                v.action = 'CONFIRM'
                v.corroborated = True
                v.drop_reason = 'L8 story cooldown (%s, %.0fm in)' % (
                    concept, (now - story['t']) / 60.0)
                story.setdefault('srcs', []).append(src)
                # SLIDING, not fixed. The cooldown measures silence since the
                # last mention, not time since the first alert. Fixed-window
                # suppression let the 08/19 buyback story re-alert thirteen
                # times between 09:08 and 14:07 as each 30-minute window
                # lapsed and the next outlet published. A story is over when
                # the wire stops talking about it.
                story['t'] = now
                return v
            if story is None:
                seen[skey] = story = {'t': now, 'src': src, 'srcs': [src],
                                      'figs': set()}
            story['cont_t'] = now
            story['figs'].update(round(x) for x in v.amounts)
            if fresh_figure:
                v.reasons.append('new-figure')

    return v
