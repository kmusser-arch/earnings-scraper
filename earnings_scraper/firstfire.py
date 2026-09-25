# -*- coding: utf-8 -*-
"""WHICH REFUSAL CODES HAVE EVER MET REAL PROSE?

★★★ A REFUSAL CAN BE CORRECT WHILE ITS DIAGNOSIS IS UNVALIDATED. The reason
gate verifies a code's claim against the document in front of it. It says
nothing about that code's fitness for a document it has never seen.

The corpus exercises 4 of 14 codes. Ten have only ever fired on synthetic
input. On an issuer nobody prepared they will fire for real, and there is a
large practical difference between a code that has refused correctly thirty
times and one meeting real text for the first time WHILE THE PRINT IS MOVING.

So any code firing for the first time on a real document carries
`firstFire: true` on the card. It costs a counter, and it says which refusals
to hand-check before any of it informs a trade.

★ THE LEDGER IS ABOUT REAL DOCUMENTS ONLY. Tests drive codes synthetically
to prove they can fire; that is not evidence the code works on prose, so the
test path never marks the ledger.
"""

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, 'state', 'reason_codes_seen.json')


def _load():
    try:
        return json.load(io.open(LEDGER, encoding='utf-8'))
    except (IOError, OSError, ValueError):
        return {}


def seen_codes():
    """{code: {firstSeenAt, document, count}} for codes that met real prose."""
    return _load()


def is_first(code, ledger=None):
    """Has this code never fired on a real document before?"""
    if not code:
        return False
    return code not in (ledger if ledger is not None else _load())


def mark(code, document, when=None, ledger=None):
    """Record that `code` fired on a real document. Returns True if FIRST."""
    if not code:
        return False
    data = ledger if ledger is not None else _load()
    first = code not in data
    if first:
        data[code] = dict(firstSeenAt=when or '', document=document, count=1)
    else:
        data[code]['count'] = int(data[code].get('count') or 0) + 1
    if ledger is None:
        save(data)
    return first


def save(data):
    try:
        os.makedirs(os.path.dirname(LEDGER))
    except OSError:
        pass
    io.open(LEDGER, 'w', encoding='utf-8', newline='').write(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + '\n')


def unfired(all_codes, ledger=None):
    """Codes that have NEVER met real prose -- the ones to watch on a print.

    Takes the in-memory ledger when a run is in progress: reading the file
    back mid-run reports every code as unfired and is the kind of stale
    instrument this build keeps catching.
    """
    data = ledger if ledger is not None else _load()
    return sorted(c for c in all_codes if c not in data)
