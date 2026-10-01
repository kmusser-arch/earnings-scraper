# -*- coding: utf-8 -*-
"""A FIELD IS STRUCTURAL BY ITS CONTENT, NOT BY ITS NAME.

★★★ AN ALLOWLIST BY NAME WAS THE VULNERABILITY. `structural_only` fenced the
global label map by KEY, and prose crossed anyway — into `basis`, a key on
that very allowlist. Five of six `basis` fields carried the ANSWER VALUE:

    ORCL[12]  'non-GAAP (8,151) — GAAP is 6,728'   stored actual 8.151
    ADBE[12]  'non-GAAP ($2,974). ★ GAAP is $2,354...'

So every field a matcher acts on is validated against a CLOSED VOCABULARY at
load, and anything else fails loudly. Not by trusting a key again — including
the ones just cleaned.

★★ AND THE FIRST THING IT CAUGHT WAS TWO SPELLINGS OF ONE VALUE: `non-GAAP`
on 14 rows and `NON_GAAP` on 5. oneConditionTwoNames, n=17, inside the field
that was cleaned this week. A validator that normalises is why that is a
report rather than five silent basis-check failures.

★ FAILING LOUDLY IS NOT RAISING. A raise costs the card; a violation refuses
ONE ROW with reasonCode SPEC_INVALID and is printed by the sweep.
"""

#: canonical value -> the spellings seen in the wild
_BASIS = {'non-GAAP': ('non-gaap', 'nongaap', 'non gaap'),
          'GAAP': ('gaap',),
          'core': ('core',),
          'adjusted': ('adjusted', 'adj'),
          'cash': ('cash',)}

_CLOSED = {
    'period': ('REPORTED', 'GUIDE_NEXT_Q', 'GUIDE_FY', 'FY_GUIDE'),
    'currencyBasis': ('USD', 'CONSTANT_CURRENCY', 'REPORTED'),
    'tableLayout': ('HORIZONTAL', 'VERTICAL'),
    # ★★★★ DERIVED AT RUNTIME, NEVER DUPLICATED. See _range_forms() below:
    # this entry is a FALLBACK for when the data file is unreachable, and
    # the authoritative list lives in ticker-profiles.json.
    'rangeForm': ('POINT', 'SEPARATOR', 'BETWEEN_AND', 'COLUMNS',
                  'PLUS_MINUS'),
    'specState': ('EXTRACTABLE', 'NOT_EXTRACTABLE', 'NEEDS_REMAP'),
    'basisLocation': ('COLUMN_HEADER', 'ROW_LABEL', 'SECTION'),
    'exclusionClass': ('NOT_IN_PR', 'CALL_SOURCED', 'QUALITATIVE',
                       'NOT_AUTOMATABLE'),
    'rowDisposition': ('CARD_DEFECT', 'UNSPECD'),
    # ★★★★ documentUnit HAD NO CLOSED LIST, so 'USD_B' / 'PCT' / 'USD' passed
    # validation and then matched nothing. unit_class only recognises '%' and
    # a leading '$'. ZERO VIOLATIONS MEANT ZERO FIELDS CHECKED, and that is
    # what made a pre-flight report a live card clean three hours before a
    # print on which every row refused.
    'documentUnit': ('$', '$B', '$M', '$K', '%', 'count', 'customers',
                     'MW / count'),
    'storedUnit': ('$', '$B', '$M', '$K', '%', 'count', 'customers',
                   'MW / count'),
}

#: a matcher field may never be this long -- prose, not a declaration
MAX_TOKEN = 24


def canonical_basis(value):
    """The canonical basis for any accepted spelling, or None."""
    if value is None:
        return None
    t = str(value).strip().lower().replace('_', '-')
    for canon, forms in _BASIS.items():
        for f in forms:
            if t == f or t == f.replace('-', ' ') or t == f.replace('-', ''):
                return canon
    return None


#: cache: the data file is read once, not on the hot path
_RANGE_FORMS = [None]


def _range_forms():
    """The rangeForm vocabulary, READ FROM THE DATA rather than duplicated.

    ★★★★ THE FRAMEWORKS LIVE IN THE DATA, NOT IN CODE. Two rangeForm lists
    existed -- nine values authored into ticker-profiles.json and five
    hardcoded here -- and the validator caught its own toolchain refusing a
    form the author had already blessed. THE DRIFT WAS THE DEFECT, NOT
    EITHER LIST, so there is now one list and this reads it.

    ★ SYNCING IS WHAT PRODUCED THE DRIFT, so nothing is synced: a revision in
    the data propagates with no code change, which is the whole point of the
    project's framework rule.
    """
    if _RANGE_FORMS[0] is not None:
        return _RANGE_FORMS[0]
    forms = None
    try:
        from . import config
        import io as _io
        import json as _json
        gmap = (_json.load(_io.open(config.PROFILES_PATH, encoding='utf-8'))
                .get('globalDocumentLabelMap') or {})
        block = gmap.get(chr(0x2605) + 'guidanceRangeForms') or {}
        closed = block.get(chr(0x2605) + 'CLOSED_LIST_AUTHORITATIVE') or {}
        vals = closed.get('values')
        if isinstance(vals, list) and vals:
            forms = tuple(str(v) for v in vals)
    except Exception:                                   # noqa: BLE001
        forms = None
    # ★ THE FALLBACK IS NAMED, NOT SILENT. A vocabulary that quietly
    # narrowed because a file was unreachable would refuse authored forms
    # and report them as spec defects.
    _RANGE_FORMS[0] = forms or _CLOSED['rangeForm']
    _RANGE_FORMS.append('data' if forms else 'FALLBACK — data unreachable')
    return _RANGE_FORMS[0]


def range_form_source():
    """Where the rangeForm vocabulary came from, for the sweep to report."""
    _range_forms()
    return _RANGE_FORMS[1] if len(_RANGE_FORMS) > 1 else 'unknown'


#: routing fields where a LIST is an ORDERED PREFERENCE, not a permission set
ROUTING_FIELDS = ('whereKind', 'where')


def routing_breadth(spec):
    """[(field, values)] for every routing field declaring more than one kind.

    ★★★ A LIST IN A ROUTING FIELD IS AN ORDERED PREFERENCE, NOT A SET OF
    PERMISSIONS. WHEN UNSURE, DECLARE ONE. A single declaration that refuses
    NAMES THE BRANCH IT TRIED; breadth takes the first branch and hides which
    one ran. A refusal is diagnostic; a silent wrong branch is not.

    ★ SURFACED, NEVER REFUSED. Breadth is not invalid -- 29 of 76 rows
    declare it and 20 of them read correctly. This turns the habit into an
    ARTIFACT the author can see rather than a judgement they must remember.
    """
    out = []
    for f in ROUTING_FIELDS:
        v = (spec or {}).get(f)
        if isinstance(v, list) and len(v) > 1:
            out.append((f, list(v)))
    return out


#: fields a reader iterates: a bare string there is one anchor, not a list
LIST_FIELDS = ('sectionAnchor', 'spanTerminator', 'documentLabels',
               'disqualify', 'excludeSections', 'sourceRows',
               'spanStartAfter')


def shape_warnings(spec):
    """[(field, value)] for list-fields authored as a bare string.

    ★★★★ THE VALIDATOR CHECKED VOCABULARIES AND NOT SHAPES. A bare string
    where a LIST is expected passes every vocabulary test and is then
    ITERATED AS CHARACTERS: MU's live card produced 47 spans instead of one,
    the fence landing wherever a letter appeared. registry.where_kind has
    coerced a string to a single-element list since it was written;
    section_spans never did.

    ★ WARNED, NOT REFUSED. The reader now coerces, so the card works --
    refusing here would blank nine rows over a shape the code handles. The
    warning exists so the authoring habit is visible, not so it is punished.
    """
    return [(f, str(spec.get(f))[:60]) for f in LIST_FIELDS
            if isinstance(spec.get(f), str)]


#: matcher fields a reader ACTS on. Any without a closed list is UNVALIDATED.
MATCHER_FIELDS = ('basis', 'period', 'currencyBasis', 'tableLayout',
                  'rangeForm', 'specState', 'basisLocation', 'exclusionClass',
                  'rowDisposition', 'documentUnit', 'storedUnit',
                  'documentLabels', 'sectionAnchor', 'spanTerminator',
                  'disqualify', 'whereKind', 'sourceRows', 'derived',
                  'requiresRangePair', 'priority')


def coverage(spec):
    """(checked, declared, unvalidated) for one spec.

    ★★★★ 'N VIOLATIONS' IS MEANINGLESS WITHOUT 'ACROSS M FIELDS OF K
    DECLARED'. documentUnit had no closed list, so it contributed zero
    violations because zero of its values were checked -- and a pre-flight
    reported a live card clean on that basis. Same shape as basis evidence
    reading healthy because it was not looking.

    A PREFLIGHT THAT CANNOT BE TRUSTED IS WORSE THAN NONE, so any matcher
    field without a closed list is NAMED UNVALIDATED rather than silently
    passing.
    """
    declared = [f for f in MATCHER_FIELDS if (spec or {}).get(f) is not None]
    checked = [f for f in declared if f in _CLOSED or f == 'basis']
    unvalidated = [f for f in declared if f not in checked]
    return checked, declared, unvalidated


def violations(spec):
    """[(field, value, why)] for every matcher field that is not a token."""
    out = []
    if not spec:
        return out
    for field, allowed in _CLOSED.items():
        if field == 'rangeForm':
            allowed = _range_forms()
        v = spec.get(field)
        if v is None:
            continue
        if not isinstance(v, str) or v not in allowed:
            out.append((field, str(v)[:60],
                        'not in the closed vocabulary %s' % (allowed,)))
    b = spec.get('basis')
    if b is not None:
        if not isinstance(b, str):
            out.append(('basis', str(b)[:60], 'not a string'))
        elif len(b) > MAX_TOKEN:
            out.append(('basis', b[:60],
                        'longer than %d characters — a declaration, not a '
                        'paragraph. Prose belongs in basisNote, which no '
                        'reader may touch' % MAX_TOKEN))
        elif canonical_basis(b) is None:
            out.append(('basis', b,
                        'not a recognised basis token %s'
                        % (tuple(_BASIS),)))
    return out
