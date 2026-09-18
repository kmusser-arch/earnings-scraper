# -*- coding: utf-8 -*-
"""The machine read, attached to every live print as a PARALLEL column.

★★★ IT NEVER TOUCHES `actual`. `actual` is the hand-read, authoritative
column; this writes scraperRead beside it so a disagreement is VISIBLE rather
than silent. Replacement was measured and rejected: of the rows where
value_for produces a value, 27% disagree with the hand read, against 18% for
the path already on the card -- it fills MORE and it fills WORSE. The 3x3
matrix that separates those two is the standing sweep format.

★★ AND IT CAN NEVER BREAK A PRINT. Every read is wrapped: an exception in the
extractor becomes a refusalReason on that one row. A parallel column that can
take down a 4:15pm card is worse than no column, and this code runs inside the
path that produces the card.

★ THE CARD AND THE LIBRARY SPELL `actual` IN DIFFERENT UNITS -- $M on a
fresh card, the row's stored unit in the library -- so the comparison is
written twice, agrees() and agrees_on_card(). Comparing across that seam
marks a matching row as a disagreement.

★ agreesWithActual IS AGREEMENT WITH WHAT THE CARD SHOWS, and at print time
that is the OLD path's read, not a hand read -- the hand read does not exist
until Kyle scores the print. So the flag is honest the moment it is written
and becomes the out-of-sample measure only after scoring, which is why
refresh_agreement() exists and is idempotent. Reading the print-time flag as
accuracy against the answer key would be the in-sample number wearing a live
label.
"""

import datetime

from . import extract
from . import registry
from . import tables

#: one conversion point. Scaling at call sites produced 11600.0 against 11.6.
_TO_MUSD = {'$B': 1000.0, '$M': 1.0, '$K': 0.001}

KINDS = ('TABLE', 'PROSE', 'WRAPPED', 'RANGE', 'HEADLINE')

FIELDS = ('scraperRead', 'extractionKind', 'refusalReason',
          'agreesWithActual', 'extractedAt')


def _now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def record_period(entry):
    """(fiscalQuarter, fiscalYear) as ints, from the DERIVED fields only.

    The raw `quarter` spells itself fifteen ways and `year` three; parsing
    them at the point of use is what made one field mean three things.
    """
    q = (entry or {}).get('fiscalQuarter')
    y = (entry or {}).get('fiscalYear')
    return (q if isinstance(q, int) else None,
            y if isinstance(y, int) else None)


def in_stored_unit(got, spec):
    """The machine read expressed in the row's STORED unit, or None."""
    v = got.get('value')
    if not isinstance(v, (int, float)):
        return None
    s_unit = (spec.get('storedUnit') or spec.get('documentUnit') or '').strip()
    f = _TO_MUSD.get(s_unit)
    if f is None:
        return round(v, 6)                     # per-share or percent
    musd = got.get('value_musd')
    if musd is None:
        d = _TO_MUSD.get((spec.get('documentUnit') or '').strip())
        musd = v * d if d else None
    return None if musd is None else round(musd / f, 6)


def kind_of(got, spec, text, lines):
    """What ACTUALLY answered — never what the row declared.

    A provenance field that reports the intention instead of the event is the
    assertion copied into the evidence, which defeats the column.
    """
    if got.get('rangeLow') is not None or got.get('rangeHigh') is not None:
        return 'RANGE'
    pos = got.get('lpos')
    if isinstance(pos, int):
        try:
            if tables.row_value_cells(lines, text.count(chr(10), 0, pos)):
                return 'TABLE'
        except Exception:
            pass
    declared = [k for k in (registry.where_kind(spec) or []) if k in KINDS]
    for k in ('WRAPPED', 'HEADLINE', 'PROSE'):
        if k in declared:
            return k
    return 'PROSE'


def refusal_of(got):
    why = (got or {}).get('why') or 'no value resolved'
    cands = (got or {}).get('candidates') or []
    if cands and 'candidate' not in why:
        why = '%s — candidates: %s' % (why, ', '.join(str(c)
                                                      for c in cands[:6]))
    return why[:400]


def _printed_digits(v):
    """Significant digits in the value AS PRINTED, via its shortest repr."""
    t = repr(float(v))
    if t.endswith('.0'):
        t = t[:-2]
    return extract.sig_digits(t)


def agrees(hand, machine):
    """None when there is nothing to compare, else the comparison.

    ★ DECIDED BY ROUNDING CONSISTENCY, NOT BY A TOLERANCE. Two values agree
    when they agree within half the last significant digit of the COARSER
    printing -- a property of how the issuer printed them rather than a
    constant someone chose.

    A TOLERANCE CANNOT DO THIS JOB. ORCL prints "between $1.83 and $1.91 in
    constant currency and between $1.85 and $1.93 in USD", so the row has two
    legitimate midpoints one percent apart, and unit, period and basis are
    identical across them. Currency variants differ by ~1% and GAAP against
    non-GAAP by 20-40%, so any tolerance wide enough to absorb rounding is
    wide enough to absorb a currency substitution. The old max(0.02, 0.6%)
    passed 1.89 against 1.87 as agreement -- a false green on the column
    whose only job is visible disagreement.

    BOTH SIDES MUST ALREADY BE IN THE SAME FRAME; see agrees_on_card.
    """
    if not isinstance(hand, (int, float)) or \
            not isinstance(machine, (int, float)):
        return None
    return bool(extract.same_number(float(hand), _printed_digits(hand),
                                    float(machine), _printed_digits(machine)))


def agrees_on_card(card_actual, machine_stored, spec):
    """The same comparison, in the CARD's frame.

    THE FIELD `actual` NAMES TWO UNITS. On a live card build_kpi_rows writes
    value_musd, so a $B row shows 12213.0; in the library the hand read is in
    the STORED unit, so the same row shows 12.213. They agree, and comparing
    them across the seam marked a matching row as a DISAGREEMENT -- a false
    red beside a correct number, which is this column's one job done
    backwards.

    Magnitude rows are compared in $M. Per-share and percent rows carry no
    scale on either side and compare as they are.
    """
    if not isinstance(card_actual, (int, float)) or \
            not isinstance(machine_stored, (int, float)):
        return None
    # ★ COMPARE IN THE STORED UNIT, NOT IN $M. Scaling 2.97 up to 2970.0
    # turns 3 printed digits into 4 and makes the rounding rule reject a
    # matching pair. The card's $M value comes DOWN into the frame both
    # numbers were printed in; the machine value is left as printed.
    f = _TO_MUSD.get((spec.get('storedUnit')
                      or spec.get('documentUnit') or '').strip())
    card = card_actual / f if f else card_actual
    return agrees(card, machine_stored)


def attach(kpi_rows, entry, text):
    """Write the parallel column onto each row of a freshly built card.

    Returns (values, refusals). `actual` is never read for writing and never
    modified.
    """
    pre = (entry or {}).get('keyKPIs') or []
    lines = [l.strip() for l in (text or '').split(chr(10))]
    rq, ry = record_period(entry)
    rec = dict(fiscalQuarter=rq, fiscalYear=ry)
    stamp = _now()
    values = refusals = 0

    for i, out_row in enumerate(kpi_rows or []):
        if not isinstance(out_row, dict) or i >= len(pre):
            continue
        spec = registry.spec_for(pre[i])
        if registry.status_of(spec) != 'EXTRACTABLE':
            continue
        out_row['extractedAt'] = stamp
        try:
            got = extract.value_for(text, pre[i], record=rec) or {}
            sr = in_stored_unit(got, spec)
        except Exception as exc:           # noqa: BLE001 - see module docstring
            # A PARALLEL COLUMN MUST NEVER TAKE DOWN A PRINT.
            out_row['scraperRead'] = None
            out_row['extractionKind'] = None
            out_row['refusalReason'] = ('extractor raised %s: %s'
                                        % (type(exc).__name__, exc))[:400]
            out_row['agreesWithActual'] = None
            refusals += 1
            continue
        if sr is None:
            out_row['scraperRead'] = None
            out_row['extractionKind'] = None
            out_row['refusalReason'] = refusal_of(got)
            out_row['agreesWithActual'] = None
            refusals += 1
            continue
        out_row['scraperRead'] = sr
        out_row['extractionKind'] = kind_of(got, spec, text, lines)
        out_row['refusalReason'] = None
        out_row['agreesWithActual'] = agrees_on_card(
            out_row.get('actual'), sr, spec)
        values += 1

    return values, refusals


def refresh_agreement(record):
    """Recompute agreesWithActual after `actual` has been hand-corrected.

    Idempotent, and the ONLY way the flag becomes an out-of-sample measure:
    at print time it compares against the old path's read, because the hand
    read does not exist yet.
    """
    rows = ((record or {}).get('actuals') or {}).get('keyKPIs') or []
    changed = 0
    for row in rows:
        if not isinstance(row, dict) or 'scraperRead' not in row:
            continue
        was = row.get('agreesWithActual')
        now = agrees(row.get('actual'), row.get('scraperRead'))
        if was != now:
            row['agreesWithActual'] = now
            changed += 1
    return changed
