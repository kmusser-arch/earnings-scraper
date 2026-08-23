"""How often does the gate actually fire on a realistic press release?

An earlier run of this measurement used ONE ticker's press-release body against
all 76 records, so every guidance figure was wrong for every ticker but one, and
it concluded "the gate never fires". That was a harness artifact.

This builds a per-record body from THAT record's own stored actuals and
guidance -- the numbers a real release for that company would carry -- and
reports gate availability plus which category blocks it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earnings_scraper import gate, parse as P, score as S      # noqa: E402
from earnings_scraper.model import Model, NoProfile            # noqa: E402


def body_for(rec, entry):
    """A press release as this company would have written it.

    Figures come from the record's stored actuals; guidance comes from the FY
    and next-Q expectation blocks, so the release is internally consistent with
    the card it will be graded against.
    """
    ac = rec.get('actuals') or {}
    lines = []

    rev, unit = ac.get('revenue'), ac.get('revenueUnit') or '$M'
    if isinstance(rev, (int, float)):
        if unit == '$M' and rev >= 1000:
            lines.append('Total revenue of $%.2f billion' % (rev / 1000.0))
        elif unit == '$B':
            lines.append('Total revenue of $%.2f billion' % rev)
        else:
            lines.append('Total revenue of $%.1f million' % rev)
        yoy = ac.get('revGrowthYoY')
        if isinstance(yoy, (int, float)):
            lines[-1] += ', %s %.1f%% year over year' % (
                'up' if yoy >= 0 else 'down', abs(yoy))
        lines[-1] += '.'

    if isinstance(ac.get('gaapEPS'), (int, float)):
        lines.append('GAAP diluted earnings per share of $%.2f.' % ac['gaapEPS'])
    if isinstance(ac.get('nonGaapEPS'), (int, float)):
        lines.append('Non-GAAP diluted earnings per share of $%.2f.'
                     % ac['nonGaapEPS'])
    if isinstance(ac.get('nonGaapGm'), (int, float)):
        line = 'Non-GAAP gross margin of %.1f%%' % ac['nonGaapGm']
        bps = ac.get('nonGaapGmYoYbps')
        if isinstance(bps, (int, float)):
            line += ', %s %d basis points year over year' % (
                'down' if bps < 0 else 'up', abs(int(bps)))
        lines.append(line + '.')

    # Guidance, from the structured expectation blocks.
    def guide_sentence(label, block, verb):
        if not isinstance(block, dict):
            return None
        rv, ru = block.get('revenue'), block.get('revenueUnit')
        if not isinstance(rv, (int, float)) or not ru:
            return None
        v = rv / 1000.0 if ru == '$M' and rv >= 1000 else rv
        u = 'billion' if (ru == '$B' or (ru == '$M' and rv >= 1000)) else 'million'
        return ('For %s, the company %s revenue of $%.2f %s to $%.2f %s.'
                % (label, verb, v * 0.99, u, v * 1.01, u))

    pe = rec.get('preEarnings') or {}
    nq = guide_sentence('the next quarter', pe.get('q2Expectations'), 'expects')
    if nq:
        lines.append(nq)
    fy = guide_sentence('full year fiscal %s' % (rec.get('year') or '2027'),
                        pe.get('fyExpectations'), 'reaffirms its guidance for')
    if fy:
        lines.append(fy)

    lines.append('Condensed consolidated statements of operations follow.')
    return '\n'.join(lines)


def main():
    model = Model()
    import collections
    avail = collections.Counter()
    blocked = collections.Counter()
    widths = collections.Counter()
    bands = collections.Counter()

    for rec in model.records:
        try:
            entry = model.prepare_from_record(rec)
        except NoProfile:
            avail['NO_PROFILE (refused)'] += 1
            continue
        item = dict(msg_type='news_item', source='BUS', id=rec['id'],
                    headline='%s Reports %s Results'
                             % (rec['ticker'], rec.get('quarter') or ''),
                    body=body_for(rec, entry))
        parsed = P.parse_release(item)
        try:
            card = S.score_release(parsed, entry, model)
        except Exception as exc:
            avail['scoring error: %s' % type(exc).__name__] += 1
            continue

        g = card.get('gate') or {}
        if g.get('cohortApplies'):
            avail['gate fires, cohort APPLIES'] += 1
        elif g.get('band'):
            avail['widened bracket (cohort N/A)'] += 1
        else:
            avail['no bracket at all'] += 1
        bands[g.get('band')] += 1
        if g.get('bracketWidth') is not None:
            widths[g['bracketWidth']] += 1
        for k in ('currentQuarter', 'nextQGuidance', 'fyGuidance'):
            if card['scores'][k] is None:
                blocked[k] += 1

    total = len(model.records)
    print('=== gate availability on per-record realistic bodies (n=%d) ===' % total)
    for k, v in avail.most_common():
        print('  %-32s %3d  (%.0f%%)' % (k, v, v / total * 100))
    print('')
    print('which category is still None:')
    for k, v in blocked.most_common():
        print('  %-20s %3d  (%.0f%%)' % (k, v, v / total * 100))
    print('')
    print('bracket widths:')
    for k, v in sorted(widths.items()):
        print('  %-6s %3d' % (k, v))
    print('')
    print('bands:')
    for k, v in bands.most_common():
        print('  %-22s %3d' % (k, v))

    fires = avail['gate fires, cohort APPLIES']
    print('')
    print('CONCLUSION: cohort-applicable gate on %d of %d (%.0f%%); '
          'the rest get an exact widened bracket with no base rate.'
          % (fires, total, fires / total * 100))
    return 0


if __name__ == '__main__':
    sys.exit(main())
