"""Configuration for the earnings wire scraper.

Latency budget: everything here is read once at startup. Nothing is touched on
the hot path (a press release arriving on the wire).

PATH RULE
=========
The two LIVE data files stay in the model repo and are read by ABSOLUTE path at
runtime. They are never copied here -- a copy goes stale the moment a new
pre-earnings card is written. `calibration.json` is local, because it is
versioned alongside the code that reads it.
"""

import io
import os

# The five press-wire sources. All are Newsware aggregator feeds under the
# single NEWS_Presswires entitlement, and none set strip_body -- so
# mode='full' returns real article bodies we can parse numbers out of.
WIRE_SOURCES = ['PRN', 'BUS', 'NFI', 'ASW', 'PZM']

WIRE_NAMES = {
    'PRN': 'PR Newswire',
    'BUS': 'BusinessWire',
    'NFI': 'Newsfile',
    'ASW': 'AccessWire',
    'PZM': 'Globe Newswire',
}

# --- LIVE data: absolute path, never copied ------------------------------------
LIB_DIR = os.environ.get(
    'EARNINGS_LIB_DIR',
    r'C:\Users\Trader\Documents\Claude\Projects\earnings Model',
)
LIBRARY_PATH = os.path.join(LIB_DIR, 'earnings-library.json')
PROFILES_PATH = os.path.join(LIB_DIR, 'ticker-profiles.json')

# --- Local data: versioned with the code --------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
CALIBRATION_PATH = os.path.join(
    _ROOT, 'skills', 'earnings-scoring', 'calibration.json')

STATE_DIR = os.environ.get('EARNINGS_STATE_DIR', os.path.join(_HERE, 'state'))
WATCHLIST_PATH = os.path.join(STATE_DIR, 'watchlist.json')
HITS_DIR = os.path.join(STATE_DIR, 'hits')
PENDING_DIR = os.path.join(STATE_DIR, 'pending')

# Scoring weights. Overridden by calibration.json at runtime; these are only
# the fallback if that file is unreadable.
WEIGHTS = {
    'currentQuarter': 0.20,
    'nextQGuidance': 0.30,
    'fyGuidance': 0.30,
    'narrative': 0.20,
}

# Verdict strings the dashboard renderer recognises. ANYTHING ELSE silently
# renders as INLINE, so never emit a verdict outside this set.
VALID_VERDICTS = {
    'BEAT', 'MISS', 'INLINE', 'CRUSH', 'DEMOLISH', 'NUKE-BEAT', 'NUKE-MISS',
    'STRONG BEAT', 'MAJOR MISS', 'N/A', '—',
}

# Suppress computed percentages beyond this magnitude -- per error class D6,
# these indicate a $M/$B or GAAP/non-GAAP units mismatch, not a real surprise.
PCT_SUPPRESS_THRESHOLD = 300.0

# Detection tuning. An actual earnings release reports figures; a scheduling
# notice does not. This is the strongest single discriminator.
MIN_FINANCIAL_FIGURES = 2

# mode='full' is mandatory -- headlines mode carries no body at all.
DEFAULT_MODE = 'full'

# ── The flag step-down (see score.py for the full derivation) ─────────────────
# Each offsetting flag beyond a band's own maxFlags allowance costs half a
# point. This is a DERIVED rule, not a documented one: the published band table
# has no row for "clears bogey 0-2% with >=2 flags", which is exactly where
# SNDK-2026Q4 (+1.0) sits. Documented in score.py:DERIVED_STEP_DOWN.
FLAG_STEP_DOWN = 0.5

# ── startup assertion: the locale default cannot read this library ──────────
#
# ★ THE MOST EXPENSIVE DEFECT FOUND IN THIS PROJECT, and it was one missing
# keyword argument. validate_library.py line 5 was
#
#     d = json.load(open('earnings-library.json'))
#
# On Windows a bare open() decodes with the ANSI codepage. Here that is cp1252,
# which cannot decode earnings-library.json -- it dies on byte 0x8f at position
# 3411, before a single check runs. So the gate CLAUDE.md declares mandatory
# ("py validate_library.py # must exit 0") had NEVER executed on this machine,
# and every write since had been landing unvalidated. It exited non-zero with a
# traceback, which reads like a broken script rather than a skipped gate.
#
# This package opens every file with an explicit encoding. The assertion below
# exists because being correct is not the same as being able to PROVE it: it
# demonstrates, at import, that a bare open() on this machine would fail on this
# data -- so any tool in the toolchain that omits the keyword is unsafe, and the
# failure is announced here rather than discovered months later.

class EncodingUnsafe(Exception):
    """The library cannot be read as UTF-8, or the platform default is unsafe."""


def preflight(path=None, strict=True):
    """Prove the library is UTF-8 readable and that a bare open() would not be.

    Returns a list of diagnostic strings (empty when the platform default is
    also safe). Raises EncodingUnsafe when the file cannot be read as UTF-8 at
    all, which is unrecoverable -- there is no second encoding to try.
    """
    import locale

    target = path or LIBRARY_PATH
    notes = []

    try:
        with io.open(target, encoding='utf-8') as fh:
            fh.read(8192)
    except FileNotFoundError:
        return ['preflight: %s not found -- cannot verify encoding' % target]
    except UnicodeDecodeError as exc:
        raise EncodingUnsafe(
            'earnings-library.json is not valid UTF-8 (%s). Refusing to guess a '
            'second encoding: a mis-decoded library is worse than no library.'
            % exc)

    default = locale.getpreferredencoding(False)
    try:
        with io.open(target, encoding=default) as fh:
            fh.read()
        return notes
    except (UnicodeDecodeError, LookupError):
        notes.append(
            'ENCODING: this machine\'s default is %s, which CANNOT decode the '
            'library. Every open() must pass encoding="utf-8" -- a bare open() '
            'raises before reading, which is how validate_library.py silently '
            'never ran.' % default)
    return notes


def assert_utf8_reads(module_paths=None):
    """Every open() in this package declares an encoding. Fails loudly if not.

    Parsed with `ast`, not matched with a regex: the first version flagged the
    words "a bare open(" inside these very docstrings. An invariant checker that
    reports its own prose is worse than none -- it trains you to ignore it.
    """
    import ast
    import glob

    bad = []
    for f in (module_paths or glob.glob(os.path.join(_ROOT, 'earnings_scraper',
                                                     '*.py'))):
        with io.open(f, encoding='utf-8') as fh:
            src = fh.read()
        for node in ast.walk(ast.parse(src, filename=f)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.id if isinstance(fn, ast.Name)
                    else fn.attr if isinstance(fn, ast.Attribute) else None)
            if name not in ('open',):
                continue
            if any(k.arg == 'encoding' for k in node.keywords):
                continue
            # a binary-mode open needs no encoding
            mode = (node.args[1].value if len(node.args) > 1
                    and isinstance(node.args[1], ast.Constant) else '')
            if 'b' in str(mode):
                continue
            bad.append('%s:%d' % (os.path.basename(f), node.lineno))
    if bad:
        raise EncodingUnsafe(
            'text open() without encoding= in %d place(s): %s'
            % (len(bad), ', '.join(bad)))
    return True
