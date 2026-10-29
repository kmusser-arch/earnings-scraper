# -*- coding: utf-8 -*-
r"""Read a release. With --labels, collapse it to something pasteable.

★★★★★ THE BOTTLENECK IS NOT PARSING, IT IS READING. 64 tickers still need
hand-written label maps, and a map is written by looking at the labels the
issuer actually prints. Nobody can read 986 rows, so the maps do not get
written and the selector stays blind on 64 tickers.

--labels collapses a megacap release to roughly 120-160 unique labels,
grouped by the section they sit in, with one sample value each. It is
optimised for being read in one screen and pasted into chat, NOT for
completeness -- the full set is always one flag away.

    py scraper/parse_kpis.py release.html --labels
    py scraper/parse_kpis.py release.html --labels --section segment
    py scraper/parse_kpis.py release.html --labels --grep margin

★ SEGMENT CONTEXT IS SHOWN INLINE because three identical 'Net sales'
labels are useless without it -- that ambiguity is exactly what a label
map exists to resolve, so the dump has to make it visible.
"""

import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import cells                          # noqa: E402

#: period column header -> a short tag for the dump
_TAGS = (('twelve months', 'TTM'), ('ttm', 'TTM'),
         ('trailing twelve', 'TTM'),
         ('three months', '3M'), ('quarter ended', '3M'),
         ('nine months', '9M'), ('six months', '6M'),
         ('outlook', 'OUTLOOK'), ('guidance', 'OUTLOOK'),
         ('full-year', 'FY'), ('full year', 'FY'), ('year ended', 'FY'))


def _tag(row):
    hay = ('%s %s %s' % (row.get('table') or '', row.get('period') or '',
                         row.get('label') or '')).lower()
    for needle, tag in _TAGS:
        if needle in hay:
            return tag
    import re
    m = re.search(r'(?i)\bq([1-4])\b', hay)
    return 'Q%s' % m.group(1) if m else ''


#: HOW WIDE a period is. The sample value must come from the NARROWEST
#: most-recent column, not merely the most recent one.
#:
#: ★★★★ 9M IS NOT MORE RECENT THAN 3M, IT IS WIDER. Amazon's segment
#: table carries both, and taking "latest year wins" showed North America
#: net sales as 333,172 -- the nine-month figure -- where the quarter is
#: 112,852. This dump is what a human writes a label map FROM, so a
#: plausible-but-wrong sample gets a bad map confirmed by eye. It is the
#: recency failure aimed at the reader instead of the selector.
_WIDTH = {'3M': 0, 'Q1': 0, 'Q2': 0, 'Q3': 0, 'Q4': 0, 'OUTLOOK': 0,
          '9M': 1, '6M': 2, 'TTM': 3, 'FY': 4, '': 5}


def _width(row):
    return _WIDTH.get(_tag(row), 5)


def _basis(row):
    """GAAP / nonGAAP from the label prefix OR the column header.

    ★★ INTEL PUTS THE BASIS IN THE COLUMN. Its Business Outlook table
    heads two columns 'GAAP' and 'Non-GAAP' over one 'Gross margin' row,
    carrying 37.1 and 38.0. Keyed on the label alone the two collapse and
    the dump shows one of them -- hiding the split that the whole map
    exists to capture.
    """
    import re as _re
    lab = (row.get('label') or '')
    m = _re.match(r'(?i)^\s*(non-gaap|gaap)\b', lab)
    if m:
        return 'nonGAAP' if m.group(1).lower().startswith('non') else 'GAAP'
    # ★★★ THE COLUMN HEADER ALONE FIRST, and only then the table. Intel's
    # Business Outlook heading reads 'includes both GAAP and non-GAAP', so
    # searching the table text alongside the column stamped BOTH columns
    # nonGAAP and collapsed 37.1 and 38.0 into a single row -- hiding
    # exactly the split this fix exists to show.
    for hay in (row.get('period') or '', row.get('table') or ''):
        if _re.search(r'(?i)non-gaap', hay):
            return 'nonGAAP'
        if _re.search(r'(?i)\bgaap\b', hay):
            return 'GAAP'
    return None


def _year(row):
    import re
    ys = re.findall(r'\b(19|20)(\d{2})\b',
                    '%s %s' % (row.get('period') or '',
                               row.get('table') or ''))
    return max((int(a + b) for a, b in ys), default=0)


def _section_name(heading):
    """A short, human name for a table heading.

    EDGAR gives the text immediately before the <table>, which is often the
    tail of the previous paragraph. Keep the recognisable end of it.
    """
    import re as _re
    t = ' '.join((heading or '').split())
    # ★★ EDGAR HANDS BACK THE TAIL OF THE PREVIOUS PARAGRAPH, so the
    # heading often starts mid-sentence -- 'ned investments in capacity and
    # working capital...'. Start from the LAST recognisable statement title
    # instead; the prose before it is never the table's name.
    titles = list(_re.finditer(
        r'(?i)\b(consolidated|condensed|supplemental|segment|business\s+'
        r'outlook|reconciliation[s]?|statements?\s+of|selected\s+financial'
        r'|financial\s+(?:highlights|information)|balance\s+sheets?'
        r'|business\s+unit|operating\s+segment)\b', t))
    if titles:
        t = t[titles[-1].start():]
    else:
        for marker in ('INC.', 'Inc.', 'Corporation'):
            i = t.rfind(marker)
            if i >= 0:
                t = t[i + len(marker):].strip(' .,-')
                break
    # ★ THE FRONT of the remainder, not the back. Taking the last 70
    # characters cut 'Consolidated Sta|tements of Operations' in half and
    # produced a section header no one could recognise.
    return (t[:70] or 'ungrouped').strip()


def labels_view(rows, section=None, grep=None, max_lines=200):
    """[(section, [(label, tags, sample, segment)])] in document order."""
    order, groups = [], {}
    for r in rows:
        sec = _section_name(r.get('table'))
        key = (sec, r.get('section') or '', r.get('label') or '',
               _basis(r))
        if sec not in groups:
            groups[sec] = {}
            order.append(sec)
        g = groups[sec]
        if key not in g:
            g[key] = {'tags': [], 'best': None, 'n': 0}
        e = g[key]
        e['n'] += 1
        t = _tag(r)
        if t and t not in e['tags']:
            e['tags'].append(t)
        # NARROWEST first, then most recent within that width
        if e['best'] is None or (
                (_width(r), -_year(r)) < (_width(e['best']),
                                          -_year(e['best']))):
            e['best'] = r

    out, shown = [], 0
    for sec in order:
        g = groups[sec]
        # ★ a label seen once in a tiny section is a prose fragment, not a
        # table row -- the dump exists to show STRUCTURE
        if len(g) < 3:
            g = dict((k, v) for k, v in g.items() if v['n'] > 1)
        if section and section.lower() not in sec.lower():
            continue
        merged = {}
        for (_s, seg, label, basis), e in g.items():
            if grep and grep.lower() not in label.lower():
                continue
            sample = (e['best'] or {}).get('raw') or ''
            mk = (seg, label, ','.join(e['tags']))
            merged.setdefault(mk, []).append((basis, sample))
        items = []
        for (seg, label, tags), variants in merged.items():
            if len(variants) > 1 and any(b for b, _v in variants):
                # ★ BOTH BASES, SIDE BY SIDE. Showing one would hide the
                # split the map exists to capture.
                sample = ' / '.join(
                    '%s %s' % (v, b) if b else str(v)
                    for b, v in sorted(variants, key=lambda x: str(x[0])))
            else:
                sample = variants[0][1]
            items.append((label, tags, sample, seg))
        if not items:
            continue
        if shown + len(items) + 2 > max_lines:
            out.append((sec, items[:max(0, max_lines - shown - 2)]))
            break
        shown += len(items) + 2
        out.append((sec, items))
    return out


def render(view):
    lines = []
    for sec, items in view:
        lines.append('')
        lines.append('== %s ==' % sec)
        for label, tags, sample, seg in items:
            # quarter tags collapse: a trend column set reads [Q1..Q3]
            parts = tags.split(',') if tags else []
            qs = [p for p in parts if p.startswith('Q')]
            rest = [p for p in parts if not p.startswith('Q')]
            if len(qs) > 2:
                qs = ['%s..%s' % (qs[0], qs[-1])]
            tag = ('[%s]' % ','.join(rest + qs)) if parts else ''
            # a cash-flow sub-heading can run 60 characters; the dump is
            # for reading, and the full string is in the parser output
            ctx = (' [%s]' % seg.rstrip(':')[:26]) if seg else ''
            lines.append('  %-44s %-10s %28s%s'
                         % (label[:44], tag[:14], sample[:28], ctx))
    return '\n'.join(lines).strip('\n')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--labels', action='store_true')
    ap.add_argument('--section', default=None)
    ap.add_argument('--grep', default=None)
    ap.add_argument('--max', type=int, default=200)
    args = ap.parse_args(argv)

    html = io.open(args.path, encoding='utf-8', errors='replace').read()
    rows = cells.from_html(html)
    if not args.labels:
        for r in rows:
            print('%s | %s | %s | %s' % (r['table'][:28], r['label'][:40],
                                         r['period'][:24], r['raw']))
        return 0
    view = labels_view(rows, args.section, args.grep, args.max)
    text = render(view)
    print(text)
    print('')
    print('-- %d unique labels in %d sections, from %d parsed cells'
          % (sum(len(i) for _s, i in view), len(view), len(rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
