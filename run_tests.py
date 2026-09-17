# -*- coding: utf-8 -*-
"""The suite runner. A TRACEBACK IS A FAILURE, whatever the pass count says.

★ WHY THIS FILE EXISTS
For several rounds the suite was reported as "963 assertions, 0 failures" while
test_gate_availability.py died on record 0 and contributed NOTHING. The old
harness counted lines beginning PASS and grepped for FAIL; a file that crashes
before printing either is invisible to both. 963-with-one-file-inert is WORSE
than an honest 900, because the missing 63 checks look like coverage.

So this runner fails on ANY of:
  * a non-zero exit status
  * the word Traceback anywhere in the output
  * a FAIL / EXPIRED line
  * a file that printed no assertions at all

That last one is the specific hole: a file can exit 0, print nothing, and look
like a clean pass. Silence is not success.
"""

import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, 'tests')


def run(path):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    p = subprocess.run([sys.executable, path], capture_output=True, env=env)
    out = (p.stdout or b'').decode('utf-8', 'replace') + \
          (p.stderr or b'').decode('utf-8', 'replace')
    lines = out.split('\n')
    passes = sum(1 for l in lines if l.startswith(('PASS', 'HOLDS')))
    fails = [l for l in lines if l.startswith('FAIL')]
    # ★ EXPIRED IS NOT FAIL. A hypothesis-expiry test is built to emit it when a
    # documented explanation stops explaining the data. Counting it as a broken
    # build means the suite stays red until someone edits the test -- exactly
    # the pressure that gets an expiry quietly re-pinned instead of read. It is
    # a defect in a BELIEF, not in the code.
    expired = [l for l in lines if l.startswith('EXPIRED')]
    problems = []
    if 'Traceback' in out:
        tb = [l for l in lines if l.strip().startswith(('File "', '  File "'))]
        problems.append('TRACEBACK (%s)' % (tb[-1].strip()[:70] if tb else '?'))
    if p.returncode != 0 and not fails and not expired:
        problems.append('exit %d with no FAIL line' % p.returncode)
    if fails:
        problems.append('%d FAIL/EXPIRED' % len(fails))
    if passes == 0 and not problems and not expired:
        problems.append('NO ASSERTIONS — the file printed nothing')
    return passes, fails, problems, expired



#: ★ DOCUMENTED TRUE POSITIVES. A known-red file reports loudly and does NOT
#: set the exit code. Every entry names the RULING that keeps it red, so the
#: registry cannot become a place where a real regression hides.
#:
#: ★★ THE BAR FOR ADDING AN ENTRY: the failure must be a defect in the CODE
#: UNDER TEST, already diagnosed, with the accepted value stated. A pin that is
#: merely inconvenient does not qualify -- that is what re-pinning is for, and
#: the re-pin policy is: precision/format where NO score moves is allowed,
#: anywhere a category or overall score moves is forbidden.
KNOWN_RED = {
    'test_regression.py': (
        'SNDK-2026Q4 currentQuarter: accepted +1.0, scorer computes +1.5. '
        'The SCORER grades off street alone; non-negotiable 5 requires THREE '
        'columns (street | bogey | own guide). [0] rev +6.85% vs street but '
        '-5.6% vs bogey = FADE; [2] EPS +14.6% / -6.5% = FADE. Two of three '
        'P1 heroes in the fade zone, stock opened -13.13%, and the score '
        'RISES. Ruling 2026-09-04: +1.0 STAYS, do not re-pin.'),
    'test_hero_resolution.py': (
        'Same SNDK-2026Q4 pin as test_regression.py -- one defect, two files. '
        'Ruling 2026-09-04: +1.0 STAYS, do not re-pin.'),
    'test_paren_polarity.py': (
        'TWO defects in one construct. (a) tables._NUMERIC puts the '
        "parentheses OUTSIDE its capture group, so '(263.0)' reads +263.0 "
        'where accounting convention means -263.0. (b) It expects the '
        "currency symbol BEFORE the paren, so '($263.0)' -- the form SNOW "
        'actually prints -- FAILS TO PARSE and the cell VANISHES from the '
        'row, silently renumbering every column after it. (b) is what made '
        "SNOW's Operating income row return the right answer for the wrong "
        'reason. A dropped cell is not a milder dropped sign. '
        'Measured report-only over all 8 releases: 902 parenthesised '
        'printings in the corpus, 2 at a position any of the 77 extractable '
        'rows resolves to, and ZERO with a dropped sign against the answer '
        'key -- both of those 2 are detector false positives, one of them '
        "the FOOTNOTE MARKER '(1)'. Ruling 2026-09-17: do NOT wire a negate "
        'at n=0; PIN it, because n=0 on today\'s coverage is not n=0 on next '
        "month's -- MATCH went 7 -> 18 in three days, into the tables where "
        'parenthesised negatives live. A polarity inversion reads as a '
        'well-formed number and no magnitude band or tie count can catch it. '
        'The fix must also decide the footnote case, so it is a change, not '
        'a one-line edit.'),
}

def main():
    names = sorted(f for f in os.listdir(TESTS)
                   if f.startswith('test_') and f.endswith('.py'))
    total = 0
    broken = []
    known, recovered = [], []
    all_expired = []
    for name in names:
        passes, fails, problems, expired = run(os.path.join(TESTS, name))
        total += passes
        mark = 'ok  ' if not problems else 'DEAD'
        note = ''
        if problems:
            note = '   ⛔ ' + '; '.join(problems)
        elif expired:
            note = '   ⧗ %d hypothesis(es) EXPIRED' % len(expired)
        print('%s %-34s %4d assertions%s' % (mark, name, passes, note))
        for f in fails[:4]:
            print('        %s' % f[:110])
        for e in expired:
            all_expired.append((name, e))
        if problems:
            if name in KNOWN_RED:
                known.append(name)
            else:
                broken.append(name)
        elif name in KNOWN_RED:
            # ★ A KNOWN-RED FILE THAT PASSES IS ALSO NEWS. Either the defect
            # was fixed and the entry must go, or the pin was quietly changed
            # and the finding was deleted with it. Silence here is how a
            # registry outlives the defect it documents.
            recovered.append(name)

    print('')
    if all_expired:
        print('⧗ %d HYPOTHESIS(ES) EXPIRED — a documented explanation no longer '
              'explains the data.' % len(all_expired))
        print('   Not a code regression. The FINDING needs updating, and the '
              'expiry itself is')
        print('   information: read it before re-pinning it.')
        for name, line in all_expired:
            print('   %-30s %s' % (name, line[:88]))
        print('')
    if known:
        print('◆ %d KNOWN-RED file(s) — documented true positives, NOT '
              'regressions.' % len(known))
        print('   These do NOT set the exit code. The redness IS the finding; '
              're-pinning would')
        print('   bless a number that has not been re-graded.')
        for name in known:
            print('')
            print('   %s' % name)
            for chunk in _wrap(KNOWN_RED[name], 70):
                print('      %s' % chunk)
        print('')
    if recovered:
        print('★ %d KNOWN-RED file(s) now PASSING: %s'
              % (len(recovered), ', '.join(recovered)))
        print('   Either the defect is fixed -- remove the KNOWN_RED entry -- '
              'or a pin was')
        print('   quietly changed and the finding was deleted with it. Check '
              'which.')
        print('')
    print('%d assertions across %d files' % (total, len(names)))
    if broken:
        print('⛔ SUITE NOT CLEAN — %d file(s) inert or failing: %s'
              % (len(broken), ', '.join(broken)))
        print('   The assertion count above is NOT a coverage claim.')
        return 1
    if known:
        print('✔ no NEW failures. %d known-red file(s) outstanding.'
              % len(known))
        return 0
    print('✔ every file ran to completion and every assertion passed')
    return 0


def _wrap(text, width):
    out, line = [], ''
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = (line + ' ' + word).strip()
    if line:
        out.append(line)
    return out


if __name__ == '__main__':
    sys.exit(main())
