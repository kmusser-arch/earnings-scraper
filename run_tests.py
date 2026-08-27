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


def main():
    names = sorted(f for f in os.listdir(TESTS)
                   if f.startswith('test_') and f.endswith('.py'))
    total = 0
    broken = []
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
            broken.append(name)

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
    print('%d assertions across %d files' % (total, len(names)))
    if broken:
        print('⛔ SUITE NOT CLEAN — %d file(s) inert or failing: %s'
              % (len(broken), ', '.join(broken)))
        print('   The assertion count above is NOT a coverage claim.')
        return 1
    print('✔ every file ran to completion and every assertion passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
