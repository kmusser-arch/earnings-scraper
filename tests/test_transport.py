# -*- coding: utf-8 -*-
"""TRANSPORT — the chain from a wire frame to a persisted card.

★★★ THE LARGEST UNTESTED SURFACE, AND THE ONLY FAILURE THAT COSTS THE WHOLE
EVENT RATHER THAN A CELL. Everything else in this suite assumes a body string
has already arrived. Nothing asserted that one ever does.

The chain has two legs and only one can be tested offline:

    NETWORK    client -> subscribe(mode=full) -> frames        needs the wire
    IN-PROCESS frame -> handle() -> detect -> parse -> score
               -> card -> _persist -> pending/*.json           tested HERE

★★ AND IT IS TESTED ON REAL FRAMES, NOT INVENTED ONES. Ten captured wire
items sit in state/pending; MRVL's carries every field the gateway sends --
format_id, publish_type, first/last_published_time, related_instruments,
teaser, topics -- because it came off BusinessWire. An invented dict tests
the shape I imagined, which is the frame problem in a different costume.

★ SILENCE IS THE FAILURE WE CANNOT DIAGNOSE WHILE A PRINT IS MOVING, so each
rejection path is driven and shown to SAY something: a bodyless watched
ticker, an off-watchlist hit, a duplicate id, a non-news frame, a foreign
source. A card of honest refusals is a PASS. A quiet return is not.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(HERE, '..', 'earnings_scraper', 'state', 'pending')

FULL_FIELDS = {'format_id', 'publish_type', 'received_time',
               'primary_instruments'}


def check(ok, msg):
    print('%s %s' % ('PASS' if ok else 'FAIL', msg))


def real_frames():
    """Every captured wire item that carries a body, with its card."""
    out = []
    if not os.path.isdir(PENDING):
        return out
    for name in sorted(os.listdir(PENDING)):
        if not name.endswith('.json'):
            continue
        try:
            d = json.load(io.open(os.path.join(PENDING, name),
                                  encoding='utf-8'))
        except ValueError:
            continue
        item = d.get('rawItem')
        if isinstance(item, dict) and (item.get('body') or '').strip():
            out.append((name, item, d.get('card') or {}))
    return out


def main():
    frames = real_frames()
    check(len(frames) >= 5,
          'SAMPLE FRAME: %d captured wire items with bodies — a transport '
          'test on one frame proves one frame' % len(frames))
    if not frames:
        return

    rich = [n for n, f, _c in frames if FULL_FIELDS <= set(f)]
    check(rich,
          '%d of them carry the FULL gateway field set — so this is the real '
          'frame shape, not one I invented' % len(rich))

    from earnings_scraper import config, detect
    from earnings_scraper import listener as LS

    # ── routing: ticker extraction off real frames ───────────────────────
    routed, misses = 0, []
    for name, item, card in frames:
        want = (card.get('ticker') or '').upper()
        tickers, _src = detect.extract_tickers(item, {})
        if want and want in [t.upper() for t in tickers]:
            routed += 1
        else:
            misses.append((name, want, tickers))
    check(not misses,
          'every frame routes to the ticker its card was written for (%d of '
          '%d)%s' % (routed, len(frames),
                     '' if not misses else ' — misses: %s' % misses[:3]))

    cls_ok = [n for n, f, _c in frames if detect.classify(f)['is_earnings']]
    check(len(cls_ok) == len(frames),
          'and every one classifies as an earnings item (%d of %d)'
          % (len(cls_ok), len(frames)))

    # ── ★ THE FULL CHAIN, into a THROWAWAY state dir ─────────────────────
    tmp = tempfile.mkdtemp(prefix='transport-')
    real_pending = config.PENDING_DIR
    config.PENDING_DIR = os.path.join(tmp, 'pending')
    try:
        _name, item, _card = frames[-1]
        lst = LS.Listener(dict(entries={}, frameworks={}, today=''),
                          popup=None, verbose=False, log_hits=False)
        lst.backfill_enabled = False

        lst.handle(dict(item))
        check(lst.stats['off_watchlist'] == 1,
              'an off-watchlist print is COUNTED (%d), not silently dropped'
              % lst.stats['off_watchlist'])

        lst.handle({'msg_type': 'heartbeat'})
        lst.handle({'msg_type': 'news_item', 'source': 'FTI', 'id': 'x'})
        check(lst.stats['wire_items'] == 1,
              'a heartbeat frame and a non-wire source are filtered before '
              'any work (wire_items still %d)' % lst.stats['wire_items'])

        # ★ MEASURE THE RIGHT COUNTER. `wire_items` increments BEFORE the
        # seen-id check, so it counts duplicates by design — it is "frames
        # off the wire", not "frames worked". The dedup is observable one
        # stage later, at off_watchlist.
        before = dict(lst.stats)
        lst.handle(dict(item))
        check(lst.stats['off_watchlist'] == before['off_watchlist']
              and lst.stats['candidates'] == before['candidates'],
              'a repeat of the same item id does not re-enter the chain '
              '(off_watchlist still %d) — a second card can DISAGREE with '
              'the first' % lst.stats['off_watchlist'])
        check(lst.stats['wire_items'] == before['wire_items'] + 1,
              'while wire_items DOES count it (%d) — that counter is frames '
              'off the wire, not frames worked, and reading it as dedup '
              'evidence would have been the wrong observable'
              % lst.stats['wire_items'])

        # ── ★ A BODYLESS WATCHED TICKER MUST SHOUT ───────────────────────
        watched = (_card.get('ticker') or 'MRVL').upper()
        lst2 = LS.Listener(dict(entries={watched: {'ticker': watched}},
                                frameworks={}, today=''),
                           popup=None, verbose=False, log_hits=False)
        bodyless = dict(item, body='', id='bodyless-1')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            lst2.handle(bodyless)
        out = buf.getvalue()
        check('NO BODY' in out and 'mode' in out.lower(),
              'a WATCHED ticker arriving with no body prints the STOP banner '
              '— no card is possible from a headline')
        check(lst2.stats.get('bodyless') == 1,
              'and it is counted (%s), so a run can be asked afterwards'
              % lst2.stats.get('bodyless'))

        # ── liveness: IDLE and QUIET must look different ──────────────────
        lst3 = LS.Listener(dict(entries={}, frameworks={}, today=''),
                           popup=None, verbose=False, log_hits=False)
        lst3.first_frame_deadline = 0.0
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            lst3.tick()
        check(buf2.getvalue().strip(),
              'the first-frame watchdog SPEAKS when nothing has arrived: %r'
              % buf2.getvalue().strip()[:58])
        lst3.first_frame_at = 1.0
        lst3._dead_warned = False
        buf3 = io.StringIO()
        with contextlib.redirect_stdout(buf3):
            lst3.tick()
        check(buf3.getvalue() != buf2.getvalue(),
              'and a wire that IS delivering reports differently — an idle '
              'wire and a quiet one were indistinguishable for four hours')

        # ── ★ THE PERSIST LEG ────────────────────────────────────────────
        path = lst._persist({'ticker': 'ZZZ', 'scores': {}}, item)
        check(path and os.path.exists(path),
              'a card persists to a sidecar file (%s)'
              % (os.path.basename(path) if path else None))
        back = json.load(io.open(path, encoding='utf-8'))
        check(back.get('rawItem', {}).get('id') == item.get('id'),
              'the RAW FRAME is stored with it, so any card can be replayed '
              'against the exact bytes that produced it')
        check((back.get('rawItem', {}).get('body') or '')
              == (item.get('body') or ''),
              'body preserved byte for byte (%d chars) — a re-read of a '
              'persisted frame is the same document'
              % len(back.get('rawItem', {}).get('body') or ''))

        # ★ ANTI-VACUOUS: persistence must fail VISIBLY, not silently.
        config.PENDING_DIR = os.path.join(tmp, 'pending', 'file.txt', 'sub')
        io.open(os.path.join(tmp, 'pending', 'file.txt'), 'w').write('x')
        buf4 = io.StringIO()
        with contextlib.redirect_stdout(buf4):
            bad = lst._persist({'ticker': 'ZZZ'}, item)
        check(bad is None and 'persist' in buf4.getvalue().lower(),
              'an unwritable sidecar path returns None AND says so (%r) '
              'rather than reporting success'
              % buf4.getvalue().strip()[:52])
    finally:
        config.PENDING_DIR = real_pending
        shutil.rmtree(tmp, ignore_errors=True)

    print('NOTE   the NETWORK leg is untested here BY CONSTRUCTION: the '
          'client, the')
    print('       subscription mode, and whether frames arrive at all. That '
          'needs the')
    print('       wire. If nothing appears at 4:31, suspect transport before '
          'extraction.')


main()


def one_canonicaliser():
    """★★★ EVERY SPEC-SOURCED BASIS COMPARISON GOES THROUGH ONE FUNCTION.

    'non-GAAP' and 'NON_GAAP' are one condition with two names, n=17, across
    FIVE call sites. It was fixed three times — in the audit, then the two
    grid readers, then the two evidence comparisons — each time where it was
    NOTICED rather than everywhere it OCCURS. The moment the library
    normalised to the underscore form it refused three graded rows, two of
    them heroes.

    ★ A NEGATIVE SCAN FOR THE WORD 'basis' DOES NOT WORK, and finding that
    out was the point: the token names FOUR different things here — the GAAP
    axis, period_basis's EXPLICIT/INFERRED, score.py's unit scale, and
    basisLocation. My first scan flagged all four and called them defects.
    parse.py and tables.py compare a DOCUMENT-derived basis against a
    literal, which never meets a spec value at all.

    So this asserts POSITIVELY: every module that compares a SPEC basis
    imports the canonicaliser and uses it.
    """
    root = os.path.join(HERE, '..', 'earnings_scraper')
    # modules that read `spec['basis']` / columnAxes want and compare it
    SPEC_BASIS_CONSUMERS = ('hgrid.py', 'sgrid.py', 'extract.py', 'sweep.py')
    missing = []
    for f in SPEC_BASIS_CONSUMERS:
        text = io.open(os.path.join(root, f), encoding='utf-8').read()
        if 'canonical_basis' not in text:
            missing.append(f)
    check(not missing,
          'all %d modules that compare a SPEC basis use the canonicaliser: '
          '%s' % (len(SPEC_BASIS_CONSUMERS), missing or 'none missing'))

    from earnings_scraper import vocab as V
    check(V.canonical_basis('NON_GAAP') == V.canonical_basis('non-GAAP')
          == V.canonical_basis('Non-GAAP') == 'non-GAAP',
          'and all three spellings present in the library resolve to one '
          'value')
    check(V.canonical_basis('GAAP') == 'GAAP'
          and V.canonical_basis('nonsense') is None,
          'while GAAP stays GAAP and an unknown token returns None rather '
          'than silently becoming one of them')

    # ★ AND THE LIBRARY ITSELF IS CHECKED, not just the code.
    lib = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents',
                       'Claude', 'Projects', 'earnings Model',
                       'earnings-library.json')
    if os.path.exists(lib):
        spellings = set()
        for rec in json.load(io.open(lib, encoding='utf-8'))['records']:
            for row in (rec.get('preEarnings') or {}).get('keyKPIs') or []:
                b = (row.get('extraction') or {}).get('basis')
                if b:
                    spellings.add(b)
        unknown = [b for b in spellings if V.canonical_basis(b) is None]
        check(not unknown,
              'every basis spelling in the library resolves (%s)%s'
              % (sorted(spellings),
                 '' if not unknown else ' UNKNOWN: %s' % unknown))


one_canonicaliser()


def heading_on_unseen_shapes():
    """★★★ WHICH CODE PATHS GET EXERCISED IS DECIDED BY WHICH ISSUERS WE
    HAPPENED TO SPEC.

    is_heading judged a heading by LINE LENGTH. MDB hard-wraps at ~66
    characters, so 54 of its lines passed — and heading_above would have
    handed the period classifier
    '-- Revenue: Total revenue was $771.8 million for the second quarte'
    as the section a value sits under. The eight spec'd documents are
    DOUBLE-SPACED, so the corpus could never have shown it. MDB has no spec
    and was never scored; it is only in this suite as a captured FRAME.

    Three structural discriminators, no word list — and the blank-line one
    is applied only where blank lines exist to apply it, because the
    DEWRAPPED frame has none.
    """
    from earnings_scraper import extract as X2

    mdb = os.path.join(PENDING, '20260901-160503-MDB.json')
    hpe = os.path.join(HERE, 'fixtures', 'releases', 'HPE-2026-09-02.txt')
    if not (os.path.exists(mdb) and os.path.exists(hpe)):
        print('SKIP MDB frame or HPE fixture not reachable')
        return

    body = json.load(io.open(mdb, encoding='utf-8'))['rawItem']['body']
    lines = body.split(chr(10))
    loose = [l for l in lines if X2.is_heading(l)]
    tight = [lines[k].strip() for k in range(len(lines))
             if X2.is_section_heading(lines, k)]
    check(len(loose) > 40 and len(tight) < 12,
          'MDB: line-length alone calls %d lines headings; structurally it '
          'is %d' % (len(loose), len(tight)))
    check('Third Quarter Fiscal 2027 Guidance' in tight
          and 'Full Year Fiscal 2027 Guidance' in tight,
          'and the ones that survive are the PERIOD-BEARING sections a '
          'classifier needs')
    check(not [t for t in tight if t.startswith('--')],
          'no data bullet survives — a data point is not a section')

    hb = io.open(hpe, encoding='utf-8').read()
    hl = hb.split(chr(10))
    kept = [hl[k].strip() for k in range(len(hl))
            if X2.is_section_heading(hl, k) and 'Outlook' in hl[k]]
    check(len(kept) >= 3,
          'and HPE keeps its Outlook headings (%s) — the tightening must '
          'not cost the row it was built for' % kept[:3])

    # ── ★ THE DEWRAPPED FRAME HAS NO BLANK LINES ─────────────────────────
    src, _segs = X2.dewrap_mapped(hb)
    pos = src.find('3.75 to $3.85')
    check(X2.heading_above(src, pos) == 'Fiscal 2026 Full Year Outlook',
          'the heading is still found in the DEWRAPPED frame, where the '
          'blank-line test cannot discriminate and is not applied')

    # ── ★ AND derive() GETS THE ORIGINAL DOCUMENT, NOT A FRAME ───────────
    lib = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents',
                       'Claude', 'Projects', 'earnings Model',
                       'earnings-library.json')
    if not os.path.exists(lib):
        return
    rec = {r['id']: r for r in json.load(io.open(lib, encoding='utf-8'))
           ['records']}['HPE-2026Q3']
    out = X2.value_for(hb, rec['preEarnings']['keyKPIs'][0], record=rec) or {}
    check(out.get('value') == 4.485
          and (out.get('rangeLow'), out.get('rangeHigh')) == (4.35, 4.62),
          'HPE[0] derives %s with its band $%s-$%s — derive() re-enters '
          'value_for, which dewraps what it is handed, so passing the '
          'CALLER FRAME dewrapped a second time and every offset in the '
          'operand read shifted. Frame defect n=5.'
          % (out.get('value'), out.get('rangeLow'), out.get('rangeHigh')))


heading_on_unseen_shapes()


def frame_type():
    """★★★ POSITIONS CARRY THEIR FRAME, OR THERE IS A SIXTH.

    Five failures, none caught by vigilance: dewrap (pos emitted DEWRAPPED,
    persisted as RAW), cell_offset (indent added twice), the probe (a
    DEWRAPPED line index handed to a RAW document, reporting the EXACT
    OPPOSITE of the truth), the heading rule (blank lines in a frame that
    has none), and derive (handed already-dewrapped text and dewrapping it
    AGAIN, refusing a priority-1 hero SILENTLY).

    ★ IT RECORDS, IT DOES NOT RAISE. An exception costs the whole card; the
    point is to make the mistake VISIBLE, not fatal at 4:31.
    """
    from earnings_scraper import extract as X3
    from earnings_scraper import frames as F

    hpe = os.path.join(HERE, 'fixtures', 'releases', 'HPE-2026-09-02.txt')
    lib = os.path.join('C:' + os.sep, 'Users', 'Trader', 'Documents',
                       'Claude', 'Projects', 'earnings Model',
                       'earnings-library.json')
    if not (os.path.exists(hpe) and os.path.exists(lib)):
        print('SKIP fixture or library not reachable')
        return
    body = io.open(hpe, encoding='utf-8').read()
    rec = {r['id']: r for r in json.load(io.open(lib, encoding='utf-8'))
           ['records']}['HPE-2026Q3']
    row = rec['preEarnings']['keyKPIs'][0]

    check(F.frame_of(body) == F.RAW,
          'a plain str is assumed RAW, so nothing had to be rewritten to '
          'adopt the type')
    src, _segs = X3.dewrap_mapped(body)
    check(F.frame_of(src) == F.DEWRAPPED and str(src) == str(src),
          'and dewrap_mapped TAGS its output %s while returning the same '
          'text' % F.frame_of(src))

    # ── the correct path reports nothing ─────────────────────────────────
    F.clear()
    good = X3.value_for(body, row, record=rec) or {}
    check(good.get('value') == 4.485 and not F.VIOLATIONS,
          'the RAW path reads 4.485 and records NO violation')

    # ── ★ DRIVEN RED: the exact n=5 defect ───────────────────────────────
    F.clear()
    bad = X3.value_for(src, row, record=rec) or {}
    check(bad.get('value') is None and F.VIOLATIONS,
          'handing value_for DEWRAPPED text still refuses the row — but now '
          'it is NAMED: %r' % (F.VIOLATIONS[0] if F.VIOLATIONS else None))
    check(any('derive' in v for v in F.VIOLATIONS),
          'and the inner call is named too, so the frame is traceable to '
          'the function that crossed it: %s' % F.VIOLATIONS[1:2])
    F.clear()

    # ★ ANTI-VACUOUS: expect() must also PASS, or every check above holds
    # on a function that always complains.
    check(F.expect(body, F.RAW, 'probe') is True and not F.VIOLATIONS,
          'expect() returns True and records nothing on a matching frame — '
          'a check, not a blanket')
    check(F.expect(src, F.RAW, 'probe') is False and len(F.VIOLATIONS) == 1,
          'and False exactly once on a mismatch')
    F.clear()


frame_type()


def one_vocabulary_and_typed_spans():
    """★★★★ ONE LIST, READ AT RUNTIME — and a span that knows how it closed.

    Two rangeForm vocabularies existed: nine values authored into
    ticker-profiles.json and five hardcoded in vocab.py. The validator
    refused a form the author had already blessed. THE DRIFT WAS THE DEFECT,
    NOT EITHER LIST, and syncing is what produced it — so the code derives
    the list from the data, per this project's own rule that frameworks live
    in the data so a revision propagates without a code change.

    And a-span-needs-a-CLOSE is at SIX violations, one inside the code
    enforcing it. Same evidence that justified the frame type at n=5, so the
    same shape: a tuple subclass that remembers, adopted without rewriting
    anything, RECORDING rather than RAISING.
    """
    from earnings_scraper import spans as S
    from earnings_scraper import vocab as V

    forms = V._range_forms()
    check(V.range_form_source() == 'data',
          'the rangeForm vocabulary is read FROM THE DATA (%s), not '
          'duplicated in code' % V.range_form_source())
    check('PLUS_MINUS_PCT' in forms and 'FLOOR' in forms
          and 'CEILING' in forms and 'APPROXIMATE' in forms,
          'so the four forms the author added are accepted WITHOUT a code '
          'change (%d values)' % len(forms))
    check(bool(V.violations({'rangeForm': 'WOBBLE'})),
          'while an unknown form is still refused — derived, not disabled')

    # ★ ANTI-VACUOUS: the fallback must be NAMED, not silent.
    check(len(forms) > len(V._CLOSED['rangeForm']),
          'and the derived list is LARGER than the hardcoded fallback (%d vs '
          '%d), so this test would fail if derivation silently fell back'
          % (len(forms), len(V._CLOSED['rangeForm'])))

    # ── the Span type, DRIVEN RED ────────────────────────────────────────
    doc = 'Guidance Summary\nThird-Quarter Guidance\nRevenue $1.0\n'
    S.clear()
    empty = S.Span(0, 17, S.BY_HEADING, 'Guidance Summary')
    check(not S.check(empty, doc, 'probe') and S.VIOLATIONS,
          'a span holding only its own heading is REFUSED: %r'
          % (S.VIOLATIONS[0][:64] if S.VIOLATIONS else None))
    S.clear()
    zero = S.Span(10, 10, S.BY_HEADING)
    check(not S.check(zero, doc, 'probe')
          and 'ZERO-WIDTH' in S.VIOLATIONS[0],
          'a zero-width fence is REFUSED')
    S.clear()
    bylen = S.Span(0, 40, S.BY_LENGTH)
    check(not S.check(bylen, doc, 'probe')
          and any('LENGTH' in v for v in S.VIOLATIONS),
          'and a span closed by a LENGTH is refused even when it holds '
          'content — a length is a guess about a document nobody read')
    S.clear()
    good = S.Span(0, len(doc), S.BY_HEADING, 'Guidance Summary')
    check(S.check(good, doc, 'probe') and not S.VIOLATIONS,
          'while a terminator-closed span with content PASSES — a check, '
          'not a blanket')
    check(good.width == len(doc) and tuple(good) == (0, len(doc)),
          'and it still unpacks as a plain (lo, hi) tuple, so nothing had '
          'to be rewritten to adopt it')
    S.clear()


one_vocabulary_and_typed_spans()
