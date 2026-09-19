# -*- coding: utf-8 -*-
"""Join a release that arrived in parts — WITHOUT ever claiming it is whole.

★★★ THE PIPELINE ALREADY ANSWERED THE QUESTION WE SPENT DAYS ON. We tried to
pair continuation pages by WIRE KEY and measured every candidate away: shared
timestamp 58% false positive, 100ms proximity 25.4%, cross-id unusable. But
both ORCL files were already resolved to ORCL by primary_instruments and
already named for the same date:

    20260910-161341-ORCL.json   part 1, ends '(MORE TO FOLLOW)'
    20260910-161605-ORCL.json   part 2, 28 grid-readable rows

TICKER AND DATE ARE THE KEY. The wire key was answering 'do these belong
together' when the resolution step had already answered it. No base rate, no
timing heuristic, no capture needed.

★★ AND THE JOIN NEVER CLEARS truncated. ORCL's part 1 income statement ends at
Hardware and part 2's supplemental grid STARTS at Hardware -- they do not abut,
so pages are missing BETWEEN them. A join that reported 'complete' would be a
silent corruption of exactly the kind three weeks of work has been spent
avoiding; one that reports 'joined, still incomplete' is honest and strictly
more useful than either part alone. So truncation is STICKY: if any part
carried a continuation marker, the joined document stays truncated, and the
banner keeps telling the reader that a blank may be an absent page rather than
a parser failure.

★ WHAT THE JOIN DOES NOT BUY, MEASURED RATHER THAN ASSUMED. Part 2 holds
19,345 / 7,388 / 4,219 -- ORCL's Q1 total revenue, OCI/IaaS revenue and cloud
applications revenue -- and joining does NOT make them extractable. Part 2
begins MID-TABLE, at the supplemental grid's Hardware row, and that grid's
column header is in the pages that never arrived. Without a header there is
nothing to say which column is the FY total and which is FY27 Q1, and the
correct answer is to refuse.

★★★ WHAT IT DOES BUY IS THE REFUSAL. Before the seam existed the horizontal
reader walked up across the join, borrowed part 1's income-statement header,
and returned 16,058 for the row whose answer is 19,345 -- right metric, wrong
column, from a header belonging to a different table. The join creates that
hazard and the seam closes it. A joined document is worth having because it
holds more text and refuses honestly, not because it fills those three rows.
"""

import io
import json
import os
import re

from . import completeness

#: pending files are named YYYYMMDD-HHMMSS-TICKER.json
SEAM = ('   [PART BOUNDARY] The parts of this release do not abut and pages '
        'are missing between them, so no table header above this line governs '
        'any row below it.')

NAME = re.compile(r'^(\d{8})-(\d{6})-([A-Z][A-Z0-9.\-]{0,9})\.json$')


def parse_name(filename):
    """(date, time, ticker) or None."""
    m = NAME.match(os.path.basename(filename or ''))
    return (m.group(1), m.group(2), m.group(3)) if m else None


def body_of(path):
    try:
        with io.open(path, encoding='utf-8') as fh:
            return ((json.load(fh).get('rawItem') or {}).get('body') or '')
    except Exception:                                   # noqa: BLE001
        return ''



#: a release names its issuer in an exchange-qualified form near the top
_BODY_TICKER = re.compile(
    r'\((?:NASDAQ|NYSE|NYSE\s+American|OTC|AMEX)[:\s]+\s*([A-Z]{1,6})\s*\)',
    re.I)

#: how much of the body to read for the issuer's own ticker
TICKER_WINDOW = 4000


def body_ticker(body):
    """Exchange-qualified tickers the body names, as a set.

    Empty when the body names none -- a continuation page begins mid-table
    and names nothing, which is not a disagreement.
    """
    return {m.group(1).upper()
            for m in _BODY_TICKER.finditer((body or '')[:TICKER_WINDOW])}


def issuer_disagrees(path, body):
    """The reason this part must not join, or None.

    ★ THE BODY IS THE ONLY INDEPENDENT WITNESS. One capture in the set is
    filed as AAPL, resolved by the WIRE as AAPL, and carries a Western
    Digital release -- so primary_instruments cannot be the check, because
    primary_instruments is the field that is wrong.
    """
    got = parse_name(path)
    if not got:
        return None
    ticker = got[2].upper()
    named = body_ticker(body)
    if named and ticker not in named:
        return ('filename claims %s and the body names %s'
                % (ticker, '/'.join(sorted(named))))
    return None


def siblings(path):
    """Every pending file for the SAME ticker and date, in wire order.

    Ordered by the timestamp in the filename, which is the order the parts
    were published -- not by any property of their contents.
    """
    got = parse_name(path)
    if not got:
        return [path]
    date, _time, ticker = got
    folder = os.path.dirname(os.path.abspath(path))
    out = []
    for name in os.listdir(folder):
        p = parse_name(name)
        if p and p[0] == date and p[2] == ticker:
            out.append((p[1], os.path.join(folder, name)))
    out.sort()
    return [p for _t, p in out] or [path]


def join(path, separator='\n'):
    """The release, assembled from its parts, with an honest completeness read.

    Returns dict(text, parts, joined, truncated, marker, missing, note).
    `truncated` is STICKY: a join can reduce what is missing, never declare
    the document whole.
    """
    paths = siblings(path)
    bodies = [(p, body_of(p)) for p in paths]
    bodies = [(p, b) for p, b in bodies if b]

    # ★ THE BODY'S ISSUER MUST MATCH THE FILENAME'S TICKER. The join keys on
    # the filename; a capture whose body names a different issuer would be
    # joined into the wrong release, and one such capture exists in the set.
    rejected = []
    kept = []
    for p, b in bodies:
        why = issuer_disagrees(p, b)
        if why:
            rejected.append((os.path.basename(p), why))
        else:
            kept.append((p, b))
    if rejected and not kept:
        return dict(text='', parts=[], joined=0, truncated=True, marker=None,
                    missing=[], rejectedParts=rejected,
                    note='every part was refused: %s' % rejected[0][1])
    bodies = kept
    if not bodies:
        return dict(text='', parts=[], joined=0, truncated=True,
                    marker=None, missing=[], note='no readable body')

    per = [(p, b, completeness.assess(b)) for p, b in bodies]
    any_marker = next((a.get('marker') for _p, _b, a in per if a.get('marker')),
                      None)

    if len(per) == 1:
        p, b, a = per[0]
        return dict(text=b, parts=[os.path.basename(p)], joined=1,
                    rejectedParts=rejected,
                    truncated=bool(a.get('truncated')),
                    marker=a.get('marker'), missing=a.get('missing') or [],
                    note=None)

    # ★★★ THE SEAM IS A HARD STOP FOR EVERY READER THAT WALKS UPWARD.
    # Part 2 begins MID-TABLE -- ORCL's supplemental grid starts at its
    # Hardware row with no column header, because the header is in the pages
    # that never arrived. Without this sentence the horizontal reader walks
    # up across the join, borrows part 1's income-statement header and reads
    # 16,058 for a row whose answer is 19,345: a wrong value, well formed,
    # with a plausible header behind it. The seam is written as PROSE because
    # prose is what every close in this codebase stops at.
    text = (separator + SEAM + separator).join(b for _p, b, _a in per)
    after = completeness.assess(text)
    # ★ STICKY. Pages are missing BETWEEN the parts -- ORCL's part 1 ends at
    # Hardware on the income statement and part 2 begins at Hardware on the
    # supplemental grid -- so the parts do not abut and no amount of joining
    # makes the document whole.
    truncated = True if any_marker else bool(after.get('truncated'))
    note = ('joined %d part(s) for this ticker and date; STILL INCOMPLETE — '
            'part %d ended with %r and the parts are not known to abut'
            % (len(per), 1, any_marker)) if any_marker else None
    return dict(text=text, parts=[os.path.basename(p) for p, _b, _a in per],
                rejectedParts=rejected,
                joined=len(per), truncated=truncated, marker=any_marker,
                missing=after.get('missing') or [], note=note)
