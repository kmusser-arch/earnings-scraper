# -*- coding: utf-8 -*-
"""POSITIONS CARRY THEIR FRAME, OR THERE IS A SIXTH.

★★★ AN INTEGER OFFSET IS MEANINGLESS WITHOUT THE TEXT IT WAS MEASURED IN,
and this project now has five frames:

    RAW         the document as the wire delivered it
    DEWRAPPED   hard wraps joined, so every offset after the first wrap moves
    STRIPPED    lines stripped independently, so every column moves
    KEPT        lines rstripped only, so columns hold
    DEWRAPPED2  dewrapped a second time -- the defect, not a frame

Five failures, none caught by vigilance:

    1. dewrap      pos emitted DEWRAPPED, persisted as RAW. AVGO's 21.7 at
                   1541 against a true 1635, and the clause read was the
                   CEO's previous sentence.
    2. cell_offset indent added twice, pos one character right of the figure
    3. the probe   label_idx from DEWRAPPED handed to a RAW document -- and
                   it reported the EXACT OPPOSITE of the true result
    4. heading     a blank-line rule applied in a frame that has no blanks
    5. derive      handed the caller's DEWRAPPED text and dewrapped it
                   AGAIN, so a priority-1 hero refused SILENTLY and the band
                   we had just built was suppressed with it

Vigilance failed five times and would fail a sixth. The fix is a TYPE.

★★ AND IT DOES NOT RAISE. An exception costs the whole card; a frame
violation is recorded and reported like any other finding, because the point
is to make the mistake VISIBLE, not to make it fatal at 4:31.
"""

RAW = 'RAW'
DEWRAPPED = 'DEWRAPPED'
STRIPPED = 'STRIPPED'
KEPT = 'KEPT'

FRAMES = (RAW, DEWRAPPED, STRIPPED, KEPT)

#: every cross-frame use seen this run, for the sweep to report
VIOLATIONS = []


class Framed(str):
    """A document that remembers which frame it is in.

    A str subclass, so every existing reader keeps working unchanged and
    nothing has to be rewritten to adopt it. What it adds is one question
    that could not be asked before: WHICH TEXT IS THIS?
    """

    frame = RAW

    def __new__(cls, value, frame=RAW):
        obj = str.__new__(cls, value)
        obj.frame = frame
        return obj


def frame_of(text):
    """The frame a document is in. Plain str is assumed RAW, as it was."""
    return getattr(text, 'frame', RAW)


def framed(text, frame):
    """Tag a document with its frame, preserving the text exactly."""
    return Framed(text, frame)


def expect(text, want, where):
    """Record a cross-frame use. Returns True when the frame is right.

    ★ RECORDS, NEVER RAISES. The defect this exists to catch produced a
    silent wrong answer; a loud wrong answer is the improvement, and a dead
    card is not.
    """
    got = frame_of(text)
    if got == want:
        return True
    VIOLATIONS.append(
        '%s expected %s text and was given %s' % (where, want, got))
    return False


def clear():
    del VIOLATIONS[:]
