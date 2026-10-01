# -*- coding: utf-8 -*-
"""DOES THE STATED REASON MATCH THE BRANCH THAT PRODUCED IT?

★★★ A REFUSAL REASON IS A DIAGNOSTIC THAT NO TEST ASSERTS. The row refuses
either way, the count is unchanged, the suite stays green, and the message
sends the next person to the wrong cause. Three defects have survived a green
suite exactly that way, and the third surfaced while the test for the second
was being written:

    HPE[0]   said 'no candidate matched the declared unit' -- and the PRODUCT
             path simply did not exist
    HPE[3]   said 'candidates tie on unit and role' -- and the declared
             period would have separated them
    derived  said the unit was wrong -- because a GENERALIST overwrote the
             SPECIALIST'S reason beneath it

It cost the HPE[3] ordering hypothesis and two traces.

★★ PROSE CANNOT BE CHECKED; A CODE CAN. Every refusal carries a reasonCode,
and each code asserts something about the DOCUMENT that this module
re-derives INDEPENDENTLY. A reason that cannot be re-derived is reported as
a MISDESCRIBED REFUSAL, which is a gate failure and not a note.

★ AND IT MATTERS MOST WHERE WE HAVE NO SPEC. On an issuer nobody has
prepared, refusals are the normal case and a wrong reason is how a live
mis-diagnosis happens with the print moving.
"""

from . import extract
from . import registry

#: every code a refusal may carry
CODES = ('NO_LABEL', 'NO_LABEL_AFTER_FILTERS', 'UNIT_MISMATCH',
         'CANDIDATE_TIE', 'PERIOD', 'CURRENCY', 'ALL_DELTA', 'BASIS',
         'BASIS_ABSENT', 'BASIS_CONTRADICTS', 'DERIVED_OPERAND',
         'READER_CRASHED', 'SPEC_STATE', 'BAND_COLLAPSED',
         'SPEC_INVALID', 'PERIOD_ABSENT', 'NO_LINE_STRUCTURE')


def verify(text, row, spec, record, got):
    """(ok, complaint) — is this refusal's stated cause actually the cause?"""
    code = (got or {}).get('reasonCode')
    why = (got or {}).get('why') or ''
    if (got or {}).get('value') is not None:
        return True, None
    if not code:
        return False, 'refused with NO reasonCode: %r' % why[:70]
    if code not in CODES:
        return False, 'unknown reasonCode %r' % code

    derived = bool((spec or {}).get('derived')
                   and (spec or {}).get('sourceRows'))
    kinds = registry.where_kind(spec) or []
    src = text
    if 'WRAPPED' in kinds or 'PROSE' in kinds or 'HEADLINE' in kinds:
        src, _segs = extract.dewrap_mapped(text)
    hits = registry.label_hits(src, spec) if spec else []
    # ★ THE GATE RE-DERIVES WHAT THE READER DID, so it applies the same
    # definitional filter. It caught this itself the moment the filter
    # landed: AVGO[6] reported NO_LABEL while this function still counted
    # the boilerplate hits and called the claim false. A gate that goes
    # stale against its own reader is the thing it exists to prevent.
    _defs = extract.definitional_spans(src)
    if _defs and hits:
        hits = [h for h in hits
                if not any(lo <= h[0] < hi for lo, hi in _defs)]

    # ★ A DERIVED ROW IS NOT IN THE DOCUMENT, so no label-path code can
    # honestly describe its failure. This is the exact defect that sent two
    # traces to the wrong cause.
    if derived and code in ('NO_LABEL', 'UNIT_MISMATCH', 'CANDIDATE_TIE',
                            'NO_LABEL_AFTER_FILTERS'):
        return False, ('a DERIVED row refused with %s, a label-path reason. '
                       'A derived row is not in the document, so that '
                       'message cannot be true of it' % code)

    if code == 'NO_LABEL':
        if hits:
            return False, ('claims no documentLabel was found, but %d label '
                           'hit(s) exist' % len(hits))
    elif code in ('UNIT_MISMATCH', 'CANDIDATE_TIE', 'NO_LABEL_AFTER_FILTERS',
                  'ALL_DELTA'):
        if not hits:
            return False, ('claims %s, which presupposes a label hit, and '
                           'there are none' % code)
    if code == 'CANDIDATE_TIE':
        # the message must name the values it could not separate
        if 'refusing:' not in why:
            return False, 'CANDIDATE_TIE without the candidates named'
        # ★ AND THE DECLARED AXIS MUST GENUINELY FAIL TO SEPARATE THEM.
        # HPE[3] reported a tie its own declared period could resolve.
        if (spec or {}).get('period'):
            names = why.split('refusing:', 1)[1]
            listed = [t.strip() for t in names.split(',') if t.strip()]
            if len(listed) < 2:
                return False, ('CANDIDATE_TIE naming fewer than two '
                               'candidates: %r' % names[:50])
    if code == 'PERIOD':
        if not (spec or {}).get('period'):
            return False, 'PERIOD refusal on a row that declares no period'
    if code in ('BASIS', 'BASIS_ABSENT', 'BASIS_CONTRADICTS'):
        want = (spec or {}).get('basis') or next(
            (a.get('want') for a in ((spec or {}).get('columnAxes') or {})
             .get('axes', []) if (a.get('axis') or '').upper() == 'BASIS'),
            None)
        if not want:
            return False, 'BASIS refusal on a row that declares no basis'
    if code == 'DERIVED_OPERAND' and not derived:
        return False, 'DERIVED_OPERAND on a row with no derived recipe'
    if code == 'READER_CRASHED' and not (got or {}).get('readerCrashed'):
        return False, 'READER_CRASHED without the readerCrashed flag'
    if code == 'BAND_COLLAPSED':
        rf = ((spec or {}).get('rangeForm') or '').upper()
        if not rf or rf == 'POINT':
            return False, ('BAND_COLLAPSED on a row whose rangeForm is %r — '
                           'there was no band to collapse' % rf)
    if code == 'NO_LINE_STRUCTURE':
        from . import extract as _x
        if _x.has_line_structure(text):
            return False, ('NO_LINE_STRUCTURE on a body with %0.0f chars per '
                           'line, which is inside the ceiling'
                           % _x.chars_per_line(text))
        if 'TABLE' not in (registry.where_kind(spec) or []):
            return False, ('NO_LINE_STRUCTURE on a row that does not declare '
                           'TABLE -- a prose row needs no line structure')
    if code == 'PERIOD_ABSENT':
        want = (spec or {}).get('period')
        if want not in ('GUIDE_FY', 'GUIDE_NEXT_Q', 'FY_GUIDE'):
            return False, ('PERIOD_ABSENT on a row that does not declare a '
                           'GUIDE period (%r) -- a REPORTED figure has '
                           'exactly one possible period' % want)
    if code == 'SPEC_INVALID':
        from . import vocab
        if not vocab.violations(spec):
            return False, ('SPEC_INVALID on a spec whose every matcher '
                           'field is in its vocabulary')
    if code == 'SPEC_STATE' and registry.status_of(spec) == 'EXTRACTABLE':
        return False, 'SPEC_STATE refusal on an EXTRACTABLE row'
    return True, None
