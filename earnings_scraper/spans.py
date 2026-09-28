# -*- coding: utf-8 -*-
"""A SPAN NEEDS A CLOSE, NOT A LENGTH — and now it is a type.

★★★ SIX VIOLATIONS, ONE OF THEM INSIDE THE CODE ENFORCING THE RULE:

    1. spans            zero-width fences: an anchor with no terminator
    2. absence claims   a bounded search describes its BOUND, not the
                        document -- sgrid may never report ABSENT_IN_DOCUMENT
    3. recursion        a depth count is a length; re-entry is the close
    4. headings         is_heading by LINE LENGTH, and MDB wraps at 66
    5. its own enforcement
                        guide_sections computed (lo, hi) and specs_for passed
                        only the heading NAME, so section_spans re-derived a
                        fence with no terminator: MDB's 716-character section
                        became 3,192 running to the end of the document
    6. heading adjacency
                        DELL stacks its guidance headings, so closing at the
                        VERY NEXT one gave spans of 18, 49, 51 and 75
                        characters -- the heading and nothing else

Same evidence that justified the frame type at n=5, and the frame type proved
the shape works: a subclass that remembers, adopted without rewriting
anything, RECORDING rather than RAISING because an exception costs the whole
card.

THE INVARIANT: an empty span is not a section, and a close must close AFTER
the content.
"""

BY_TERMINATOR = 'TERMINATOR'
BY_HEADING = 'HEADING'
BY_DOCUMENT_END = 'DOCUMENT_END'
BY_LENGTH = 'LENGTH'

#: every span this run that was closed by a LENGTH or arrived empty
VIOLATIONS = []


class Span(tuple):
    """(lo, hi) that remembers HOW it was closed and whether it holds content.

    A tuple subclass, so every existing `lo, hi = span` keeps working and
    nothing has to be rewritten to adopt it -- the same adoption path the
    frame type took.
    """

    closedBy = BY_DOCUMENT_END
    label = ''

    def __new__(cls, lo, hi, closed_by=BY_DOCUMENT_END, label=''):
        obj = tuple.__new__(cls, (lo, hi))
        obj.closedBy = closed_by
        obj.label = label
        return obj

    @property
    def width(self):
        return self[1] - self[0]

    def holds_content(self, text, minimum=1):
        """Does anything but the heading itself sit inside?

        ★ AN EMPTY SPAN IS NOT A SECTION. DELL's stacked headings produced
        four spans that contained their own heading and nothing else, and
        four guide rows then refused for want of a value that was never
        inside the fence.
        """
        body = (text or '')[self[0]:self[1]]
        lines = [x for x in body.split(chr(10))[1:] if x.strip()]
        return len(lines) >= minimum


def check(span, text, where):
    """Record a span that cannot be trusted. Returns True when it can.

    RECORDS, NEVER RAISES -- an exception costs the whole card, and the point
    is to make the mistake visible rather than fatal at 4:31.
    """
    lo, hi = span[0], span[1]
    closed = getattr(span, 'closedBy', BY_DOCUMENT_END)
    ok = True
    if hi <= lo:
        VIOLATIONS.append('%s: ZERO-WIDTH span at %d' % (where, lo))
        ok = False
    elif not Span(lo, hi, closed).holds_content(text):
        VIOLATIONS.append(
            '%s: span %d..%d holds no content below its heading -- an empty '
            'span is not a section' % (where, lo, hi))
        ok = False
    if closed == BY_LENGTH:
        VIOLATIONS.append(
            '%s: span %d..%d was closed by a LENGTH. A length is a guess '
            'about a document nobody read; a terminator is a string the '
            'issuer printed.' % (where, lo, hi))
        ok = False
    return ok


def clear():
    del VIOLATIONS[:]
