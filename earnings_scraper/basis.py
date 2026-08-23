"""Basis as a modifier: GAAP, non-GAAP, core, constant currency.

★ WHY THIS EXISTS
Allowing the INCOME STATEMENT zone was correct -- revenue and EPS live in its
line items -- but it admits the one region where GAAP and non-GAAP sit side by
side. WDC-2026Q4 states GAAP 64 times and non-GAAP 65; SNDK 82 and 52. The zone
therefore ALWAYS offers both, and basis has to be enforced by the same
two-directional symmetry as any other modifier.

★ THE BARE ROW IS THE DANGEROUS CLASS, NOT THE SAFE ONE
107 of 746 library rows name a basis (adj 61, non-GAAP 22, CC 15, ex-credits 3,
GAAP 2, organic 2, core 2). SIXTY more are bare rows on basis-sensitive
metrics -- "Q4 EPS Guide ($)", "Q1 Operating Income ($B)", "FY26 EPS ($)".
Bare does NOT mean "either basis is fine". It means the basis the street was
quoting, which is almost always non-GAAP. So a bare row takes the non-GAAP line
when both are offered, and never GAAP silently.

Founding cases, both already in the library:
  WDC   GAAP EPS $8.21 against a $3.29 street estimate -- a 150% false BEAT
  CBRS  GAAP missed 7.0% while company-defined "core" beat 9.9%, and the tape
        traded GAAP

★ 'adj' IS non-GAAP, and it is the most common spelling by far -- 61 of the 107.
A basis detector that knows "non-GAAP" but not "Adj" misses three fifths of the
rows that declare one.
"""

import re

NON_GAAP = 'non-GAAP'
GAAP = 'GAAP'
CORE = 'core'
CC = 'cc'
UNKNOWN = 'unknown'

#: metrics where the two bases routinely differ enough to flip a verdict
SENSITIVE = re.compile(
    r'\beps\b|earnings\s+per\s+share|gross\s+margin|\bgm\b|operating\s+income'
    r'|\bop\s+income\b|\boi\b|operating\s+margin|\bopm\b|\bebitda\b'
    r'|net\s+income', re.I)

_DECLARED = (
    # order matters: 'non-GAAP' must be tested before 'GAAP'
    (NON_GAAP, re.compile(r'non-?gaap|\badj\b|\badj\.|adjusted', re.I)),
    (CORE, re.compile(r'\bcore\b', re.I)),
    (CC, re.compile(r'\bcc\b|constant\s+currency|\bfxn\b|ex-?fx', re.I)),
    (GAAP, re.compile(r'\bgaap\b', re.I)),
)


def declared(row_name):
    """The basis a ROW demands, or None when it names none."""
    n = row_name or ''
    for label, pat in _DECLARED:
        if pat.search(n):
            return label
    return None


def is_sensitive(row_name):
    """True when this metric's two bases can differ enough to flip a verdict."""
    return bool(SENSITIVE.search(row_name or ''))


def _normalise(available):
    """Parser keys -> basis labels. 'adjusted' is non-GAAP."""
    out = {}
    for key, val in (available or {}).items():
        k = str(key)
        if k.lower() in ('adjusted', 'adj', 'non-gaap', 'nongaap'):
            out[NON_GAAP] = val
        elif k.lower() == 'gaap':
            out[GAAP] = val
        elif k.lower() == 'core':
            out[CORE] = val
        else:
            out.setdefault(UNKNOWN, val)
    return out


def select(row_name, available):
    """Pick the reading whose basis the row is entitled to.

    Returns (value, basis_read, note). `value` is None on refusal, and the note
    then says why. Every success records WHICH basis was taken, so a wrong one
    is visible on the card instead of inferred.
    """
    have = _normalise(available)
    if not have:
        return None, None, None

    want = declared(row_name)
    offers_both = GAAP in have and NON_GAAP in have

    if want:
        if want in have:
            return (have[want], want,
                    'basis %s, as the row demands' % want)
        # ★ Both directions. A non-GAAP row refuses a GAAP line, and refuses a
        # BARE line when the release distinguishes -- picking blindly there is
        # how WDC's GAAP $8.21 lands against a $3.29 non-GAAP street.
        if offers_both or any(k in have for k in (GAAP, NON_GAAP)):
            return (None, None,
                    '⛔ NOT GRADED — the row demands %s and the release states '
                    'only %s. Substituting a basis is the CBRS failure: GAAP '
                    'missed 7.0%% while "core" beat 9.9%%, and the tape traded '
                    'GAAP.' % (want, sorted(k for k in have if k != UNKNOWN)
                               or ['an unstated basis']))
        if UNKNOWN in have:
            return (have[UNKNOWN], UNKNOWN,
                    '⚠ basis NOT STATED in the release; the row demands %s. '
                    'Read anyway because no other basis is offered, but the '
                    'figure is unverified on basis.' % want)
        return None, None, None

    # ── a BARE row ─────────────────────────────────────────────────────────
    if NON_GAAP in have:
        return (have[NON_GAAP], NON_GAAP,
                'row names no basis; took NON-GAAP%s, which is the basis the '
                'street quotes' % (' (both were offered)' if offers_both
                                   else ''))
    if UNKNOWN in have:
        return (have[UNKNOWN], UNKNOWN,
                'row names no basis and the release states none')
    if GAAP in have:
        # ★ Never silently. GAAP is taken only when it is the ONLY thing on
        # offer, and the card says so.
        return (have[GAAP], GAAP,
                '⚠ row names no basis and the release offers only GAAP. Taken, '
                'but a bare row means the STREET basis, which is usually '
                'non-GAAP — check before trading it.')
    return None, None, None
