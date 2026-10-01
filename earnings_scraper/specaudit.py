# -*- coding: utf-8 -*-
r"""ASSERT EVERY AUTHORED STRING AGAINST THE DOCUMENT IT CLAIMS TO MATCH.

★★★ ABSENT MEANS DEFECT, NOT RISK. The MU F4Q26 card carried two strings
that do not occur anywhere in Micron's release:

    sectionAnchor   'FQ1-27 GUIDANCE'               0 occurrences
    spanTerminator  'The following table reconciles' 0 occurrences

Both were authored from the earnings DECK, which is a different document
from the press release. Nothing failed, nothing warned: the fence simply
covered the whole release and every row refused for an unrelated-looking
reason. One lookup against the prior quarter's exhibit would have caught
both before the print.

★★ AND A STRING THAT IS PRESENT IS NOT THEREBY CORRECT. This checks
PRESENCE and COUNT, which is the cheap half. A terminator that occurs three
times fences somewhere, just not necessarily where the author meant -- so
the count is reported rather than reduced to a boolean, because 'found 3'
and 'found 1' warrant different responses and a tick mark hides that.

This is the machine half of non-negotiable 0c. It cannot tell whether the
right NUMBER sits inside the fence; only a read can.
"""

from . import corpus
from . import extract
from . import registry

#: the authored strings that must occur in the document VERBATIM. Every one
#: is matched by the reader as a literal substring, case-insensitively.
#:
#: ★★★ documentLabelS, PLURAL, AND THE SINGULAR HERE WAS A REAL DEFECT.
#: The first cut of this auditor listed 'documentLabel'. Every one of the
#: 111 spec'd rows in the library writes 'documentLabels', so the auditor
#: checked ZERO labels and reported "21 of 79 absent" on anchors and
#: terminators alone -- a clean-looking number over a field it never read.
#: Exactly the failure this module exists to catch, in the module itself:
#: a check that cannot fail is not a check.
MATCHED_FIELDS = ('sectionAnchor', 'spanTerminator', 'spanStartAfter',
                  'documentLabels', 'documentLabel')


def authored_strings(record):
    """[(row, field, value)] for every literal the spec will look for."""
    out = []
    rows = (record.get('preEarnings') or {}).get('keyKPIs') or []
    for i, row in enumerate(rows):
        spec = registry.spec_for(row) or {}
        for field in MATCHED_FIELDS:
            val = spec.get(field)
            if val is None:
                continue
            for one in (val if isinstance(val, (list, tuple)) else [val]):
                if isinstance(one, str) and one.strip():
                    out.append((i, field, one))
    return out


def audit(record, text):
    """[(row, field, value, count)] — how often each literal occurs.

    count == 0 is the defect. Everything else is reported as a number and
    judged by the reader.
    """
    low = (text or '').lower()
    return [(i, f, v, low.count(v.lower()))
            for i, f, v in authored_strings(record)]


def exhibit_for(record, ticker=None, prior=False, out_dir=None):
    """The cached exhibit this record should be audited against, or None.

    prior=False  the SAME quarter -- re-verifying a spec that already ran
    prior=True   the quarter BEFORE -- what non-negotiable 0c requires when
                 a spec is being AUTHORED and its own document does not
                 exist yet
    """
    rid = record.get('id') or ''
    ticker = ticker or (rid.rsplit('-', 1)[0] if '-' in rid else rid)
    docs = corpus.load(ticker, out_dir)          # newest filing first
    if not docs:
        return None
    on = record.get('reportDate')
    if not on:
        return docs[1] if (prior and len(docs) > 1) else docs[0]
    same = [d for d in docs if (d.get('filingDate') or '') == on]
    if not prior:
        return same[0] if same else None
    earlier = [d for d in docs if (d.get('filingDate') or '') < on]
    return earlier[0] if earlier else None


def fenced_regions(record, text):
    """[(row, anchor, startAfter, terminator, [(start,end,body)...])] per row.

    ★★★★ "DID MY STRING APPEAR" IS THE CHEAP QUESTION. THIS IS THE REAL ONE.

    SNOW's anchor PASSED the presence audit and still fenced the wrong
    region: the row wanted product revenue of $1,491.9M and the tied
    candidates were 828 and 829, the CUSTOMER COUNTS. Presence is necessary
    and not sufficient, and nothing short of looking at what falls inside
    the fence can tell the two apart.

    ★ A ROW WITH NO ANCHOR IS NOT AN EMPTY FENCE, IT IS THE WHOLE DOCUMENT.
    Reported as such, because 'no fence' and 'a fence that found nothing'
    are opposite problems: the first searches everything and ties, the
    second searches nothing and refuses.
    """
    out = []
    rows = (record.get('preEarnings') or {}).get('keyKPIs') or []
    for i, row in enumerate(rows):
        spec = registry.spec_for(row) or {}
        if registry.status_of(spec) != 'EXTRACTABLE':
            continue
        anchor = spec.get('sectionAnchor')
        term = spec.get('spanTerminator')
        if not anchor:
            out.append((i, None, spec.get('spanStartAfter'), term,
                        [(0, len(text or ''), None)]))
            continue
        # ★★★ spanStartAfter, AND LEAVING IT OUT MADE THIS DUMP A LIE.
        # The reader passes it (extract.py:1670); the first cut of this
        # function did not, so a two-level fence -- anchor pins the TABLE,
        # spanStartAfter pins the region INSIDE it -- would have been
        # dumped at its UNTIGHTENED width and reported as still broken.
        # An authoring check that does not read the field the author just
        # set is the documentLabel/documentLabels defect a third time.
        spans = extract.section_spans(text, anchor, term,
                                      spec.get('spanStartAfter')) or []
        out.append((i, anchor, spec.get('spanStartAfter'), term,
                    [(s[0], s[1], (text or '')[s[0]:s[1]]) for s in spans]))
    return out


def dump_fences(record, text, log=None, width=96, head=0):
    """Print what actually falls inside each row's fence."""
    log = log if log is not None else print
    rows = (record.get('preEarnings') or {}).get('keyKPIs') or []
    for i, anchor, startafter, term, spans in fenced_regions(record, text):
        name = ((rows[i] or {}).get('name') or '')[:46]
        log('')
        log('-' * width)
        log('[%-2d] %s' % (i, name))
        log('     anchor     %r' % (anchor,))
        log('     startAfter %r' % (startafter,))
        log('     terminator %r' % (term,))
        if anchor is None:
            log('     ** NO ANCHOR — this row searches the WHOLE document **')
            continue
        if not spans:
            log('     ** 0 SPANS — the anchor is not in this document **')
            continue
        log('     %d span(s)' % len(spans))
        for k, (a, b, body) in enumerate(spans):
            lines = (body or '').split(chr(10))
            shown = lines[:head] if head else lines
            log('     --- span %d: chars %d..%d, %d lines%s ---'
                % (k + 1, a, b, len(lines),
                   '' if not head else ' (first %d)' % head))
            for ln in shown:
                log('       | %s' % ln[:width - 9])


def report(record, text, log=None):
    """Print the audit for one record. Returns (missing, total)."""
    log = log if log is not None else print
    rows = audit(record, text)
    missing = [r for r in rows if r[3] == 0]
    for i, field, val, n in rows:
        if n == 0:
            log('      [%-2d] %-15s ABSENT    %r' % (i, field, val[:52]))
    return len(missing), len(rows)
