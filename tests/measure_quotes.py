# -*- coding: utf-8 -*-
"""Three measurements before any quote reader is wired.

  (1) how many values live ONLY in quotes (nowhere else in the document)
  (2) do quote values classify cleanly under KEY 1
  (3) the quote-vs-table conflict count: same metric in both, differing values

Report-only. Nothing is wired from this.
"""

import io
import os
import re
import sys

sys.path.insert(0, r'c:\Users\Trader\Desktop\shelnewsapi')

from earnings_scraper import period as PD

QUOTE = re.compile(r'"([^"]{40,900})"')
#: a dollar or percent figure with its magnitude word
FIG = re.compile(r'\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|B\b|M\b)?'
                 r'|([\d,]+(?:\.\d+)?)\s*%')
BARE = re.compile(r'^\s*\(?\$?\s?(\d[\d,]*(?:\.\d+)?)\)?\s*%?\s*$')

FIX = 'tests/fixtures/releases'
C = (r'C:\Users\Trader\Documents\Claude\Projects\earnings Model'
     r'\tests\corpus')

sources = [(os.path.join(FIX, '%s-2026-09-02.txt' % t), t)
           for t in ('AVGO', 'HPE', 'SNOW')]
sources += [(os.path.join(C, f), f[:-4]) for f in sorted(os.listdir(C))
            if f.endswith('.txt')]


def to_musd(num, unit):
    v = float(num.replace(',', ''))
    u = (unit or '').lower()
    if u.startswith('b'):
        return v * 1000.0
    if u.startswith('m'):
        return v
    return v


def figures(text):
    """[(value_musd_or_pct, raw, is_pct)] found in `text`."""
    out = []
    for m in FIG.finditer(text):
        if m.group(3) is not None:
            out.append((float(m.group(3).replace(',', '')), m.group(0), True))
        else:
            out.append((to_musd(m.group(1), m.group(2)), m.group(0), False))
    return out


print('=' * 74)
print('(1) VALUES THAT LIVE ONLY IN QUOTES')
print('=' * 74)
only_quote_total = 0
quote_vals_total = 0
per_doc = {}

for path, label in sources:
    body = io.open(path, encoding='utf-8').read()
    lines = body.splitlines()
    bare_nums = set()
    for ln in lines:
        mm = BARE.match(ln)
        if mm:
            try:
                bare_nums.add(round(float(mm.group(1).replace(',', '')), 3))
            except ValueError:
                pass

    quotes = list(QUOTE.finditer(body))
    outside = body
    for m in reversed(quotes):
        outside = outside[:m.start()] + ' ' * (m.end() - m.start()) \
            + outside[m.end():]

    only, total = [], 0
    for m in quotes:
        for val, raw, is_pct in figures(m.group(1)):
            total += 1
            # does the same figure appear OUTSIDE the quotes, or as a table cell?
            cands = {round(val, 3), round(val / 1000.0, 3),
                     round(val * 1000.0, 3)}
            in_table = bool(cands & bare_nums)
            txt_forms = {'%g' % val, '%g' % (val / 1000.0), '%.1f' % val,
                         '%.1f' % (val / 1000.0), '%.3f' % (val / 1000.0)}
            in_prose = any(f in outside for f in txt_forms if len(f) > 2)
            if not in_table and not in_prose:
                only.append((val, raw, is_pct))
    per_doc[label] = (len(only), total, only, quotes, body, bare_nums, outside)
    only_quote_total += len(only)
    quote_vals_total += total
    print('   %-14s %2d quote span(s) · %2d figures · %2d ONLY in a quote'
          % (label, len(quotes), total, len(only)))
    for val, raw, is_pct in only[:6]:
        print('        %-14s %s' % (raw.strip(), '(pct)' if is_pct else '($M)'))

print('')
print('   TOTAL: %d of %d quote figures exist nowhere else'
      % (only_quote_total, quote_vals_total))

print('')
print('=' * 74)
print('(2) DO QUOTE VALUES CLASSIFY CLEANLY UNDER KEY 1?')
print('=' * 74)
clean = murky = 0
for label, (n_only, total, only, quotes, body, bare, outside) in per_doc.items():
    reg = PD.build_register(body)
    if not quotes:
        continue
    print('   --- %s ---' % label)
    for m in quotes:
        span = m.group(1)
        # classify each SENTENCE of the quote independently
        for sent in re.split(r'(?<=[.!?])\s+', span):
            figs = figures(sent)
            if not figs:
                continue
            cls, src = PD.classify_at(body, m.start(), fragment=sent,
                                      register=reg)
            if cls == PD.UNRESOLVED:
                murky += 1
            else:
                clean += 1
            print('       %-13s via %-9s %s'
                  % (cls, src, ' '.join(sent.split())[:62]))
print('')
print('   clean %d · UNRESOLVED %d' % (clean, murky))

print('')
print('=' * 74)
print('(3) QUOTE-VS-TABLE CONFLICT: same figure rounded differently')
print('=' * 74)
conflicts = 0
for label, (n_only, total, only, quotes, body, bare, outside) in per_doc.items():
    for m in quotes:
        for val, raw, is_pct in figures(m.group(1)):
            if is_pct:
                continue
            # a table cell within 2% but NOT equal -> the rounded-quote case
            near = [b for b in bare
                    if b and abs(b - val) > 0.051
                    and abs(b - val) / max(abs(val), 1.0) < 0.02]
            if near:
                conflicts += 1
                print('   %-8s quote %-12s vs table %s  (%.2f%% apart)'
                      % (label, raw.strip(), sorted(near)[:3],
                         100.0 * abs(sorted(near)[0] - val) / abs(val)))
print('')
print('   TOTAL quote-vs-table conflicts: %d' % conflicts)
