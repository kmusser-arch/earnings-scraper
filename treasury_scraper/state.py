"""Persistent state: the novelty ledger (L4) and the calendar prior (L7).

THE LEDGER IS THE POINT. Treasury restates its own operating parameters
constantly -- every buyback schedule, every auction announcement, every
refunding statement republishes numbers that have not moved. A keyword filter
fires on all of them. A ledger fires only when a number CHANGED.

This is the same discipline as grading a print against the bogey rather than
against zero: the headline is not the news, the delta is.
"""

import datetime
import json
import os

from . import config

# Concept keys. Several Tier-A terms describe the same underlying parameter, so
# they collapse onto one ledger row -- otherwise "liquidity support" and
# "buyback" would each carry their own stale copy of the same number.
CONCEPTS = {
    'liquidity support': 'buyback_op_max',
    'buyback': 'buyback_op_max',
    'buy-back': 'buyback_op_max',
    'repurchase operation': 'buyback_op_max',
    'auction size': 'auction_size',
    'auction sizes': 'auction_size',
    'nominal coupon': 'auction_size',
    'coupon issuance': 'auction_size',
    'quarterly refunding': 'refunding_total',
    'refunding': 'refunding_total',
    'marketable borrowing': 'borrowing_estimate',
    'financing estimates': 'borrowing_estimate',
    'cash balance': 'tga_target',
    'tga': 'tga_target',
    'debt limit': 'debt_limit',
}

# Seed state as it stood the morning of 2026-08-19, BEFORE the announcement.
# The maximum liquidity-support buyback operation was $2B. The release took it
# to "at least $4B" -- a +100% delta, which is exactly what L4 is built to see.
SEED = {
    'buyback_op_max': {'value': 2.0e9, 'asof': '2026-08-19',
                       'note': 'pre-announcement max per operation'},
}

# A number has to move by more than this to count as news. Rounding in a
# headline ("about $4 billion") must not fire on its own.
MATERIAL_PCT = 0.05


class Ledger:
    def __init__(self, path=None):
        self.path = path or config.LEDGER_PATH
        self.rows = dict(SEED)
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as fh:
                self.rows.update(json.load(fh))
        except (OSError, ValueError):
            pass                              # seed-only is a valid cold start

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(self.rows, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.path)            # never leave a torn ledger

    # --- the L4 gate ---------------------------------------------------------

    def concept(self, term):
        return CONCEPTS.get(term)

    def delta(self, term, amounts, text=''):
        """Describe the change, or None if nothing moved.

        Returns a short string like '2.0B->4.0B (+100%)' that goes straight
        into the alert line, because the size of the move IS the trade.
        """
        c = self.concept(term)
        if not c or not amounts:
            return None
        row = self.rows.get(c)
        if row is None:
            return 'new:%s' % _fmt(max(amounts))
        old = row.get('value')
        if not old:
            return None
        # Prefer the largest figure quoted -- a release that says "$2B will be
        # at least $4B" carries both, and the new ceiling is the one that
        # matters. Ignore anything at or below the standing value.
        candidates = [a for a in amounts
                      if abs(a - old) / old > MATERIAL_PCT and a > old * 0.2]
        if not candidates:
            return None
        new = max(candidates)
        if new == old:
            return None
        return '%s->%s (%+.0f%%)' % (_fmt(old), _fmt(new),
                                     (new - old) / old * 100.0)

    def is_restatement(self, term, amounts):
        """True when every figure quoted is one we already knew."""
        c = self.concept(term)
        row = self.rows.get(c) if c else None
        if not row or not amounts:
            return False
        old = row.get('value')
        if not old:
            return False
        return all(abs(a - old) / old <= MATERIAL_PCT for a in amounts)

    def record(self, term, value, asof=None, note=''):
        c = self.concept(term)
        if not c:
            return None
        self.rows[c] = {
            'value': float(value),
            'asof': asof or datetime.date.today().isoformat(),
            'note': note,
        }
        return c


def _fmt(v):
    for unit, mult in (('T', 1e12), ('B', 1e9), ('M', 1e6)):
        if abs(v) >= mult:
            return '%.4g%s' % (v / mult, unit)
    return '%.0f' % v


# --- L7: the calendar prior --------------------------------------------------

def _parse_hhmm(s):
    h, m = s.split(':')
    return int(h) * 60 + int(m)


def is_hot(now_et=None):
    """True inside a scheduled-announcement window.

    Quarterly refunding is the 1st Wednesday of Feb/May/Aug/Nov at 08:30 ET;
    buyback schedules and auction results cluster at 11:00 and 15:00. Inside
    those windows the poller runs hot and the alert floor drops.
    """
    now = now_et or _now_et()
    if now.weekday() >= 5:
        return False
    minute = now.hour * 60 + now.minute
    for lo, hi in config.HOT_WINDOWS_ET:
        if _parse_hhmm(lo) <= minute <= _parse_hhmm(hi):
            return True
    return False


def is_qra_day(now_et=None):
    """1st Wednesday of a refunding month -- the highest-value day of the
    quarter for this feed, and worth running hot all morning."""
    now = now_et or _now_et()
    return (now.month in config.QRA_MONTHS
            and now.weekday() == 2 and now.day <= 7)


def poll_interval(now_et=None):
    now = now_et or _now_et()
    if is_qra_day(now) or is_hot(now):
        return config.HOT_INTERVAL_S
    return config.COLD_INTERVAL_S


def _now_et():
    # ET without a tz database dependency: the wire timestamps in news.log are
    # UTC and the desk reads ET, so this is the one conversion that matters.
    utc = datetime.datetime.now(datetime.timezone.utc)
    offset = 4 if 3 <= utc.month <= 10 else 5      # DST, close enough for a
    return utc - datetime.timedelta(hours=offset)  # 50-minute poll window


class SeenCache(dict):
    """L1 dedup cache with a bounded footprint."""

    def __init__(self, path=None, limit=5000):
        super().__init__()
        self.path = path or config.SEEN_PATH
        self.limit = limit

    def prune(self, now):
        if len(self) <= self.limit:
            return
        cutoff = now - config.DEDUP_WINDOW_S
        for k in [k for k, v in self.items() if v['t'] < cutoff]:
            del self[k]
