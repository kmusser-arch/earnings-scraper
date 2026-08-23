"""HARD 10 — domain-implausible expected values.

Why this check exists
=====================
SNDK-2026Q4 stores an FQ4 Gross Margin bogey of 84.0 against a consensus of
81.5, for a MEMORY semiconductor. Memory gross margin runs roughly 30-40%. All
six numeric rows on that record are internally consistent at GM 81-85 and EPS
34-55, so it is a SYSTEMATIC transposition rather than a typo.

That is exactly the shape HARD 8 and HARD 9 cannot see: they compare bogey
against consensus, and here the two AGREE in scale. Internal consistency is not
plausibility. The only way to catch it is to test the value against what the
metric can physically be for that sector.

The check is deliberately conservative. It flags, it never corrects -- an
implausible expected value is marked unverified for a human to re-source
(non-negotiable 9), because guessing the intended figure is the same class of
error as inferring a missing unit.
"""

import re

# Sector-conditioned plausibility bands for percentage metrics. Wide on purpose:
# the goal is to catch an 84% memory gross margin, not to police a 3-point
# disagreement. lo/hi are inclusive.
_GROSS_MARGIN_BANDS = [
    # (sector pattern, lo, hi, why)
    (re.compile(r'memory|nand|dram|storage', re.I), 5.0, 70.0,
     'memory/storage gross margin runs ~20-55% across the cycle and has never '
     'printed above ~60%'),
    (re.compile(r'hardware|networking|consumer electronics|optical|'
                r'substrat|wafer|wfe|power & infrastructure|aerospace|'
                r'satellite|space', re.I), 5.0, 70.0,
     'hardware gross margin is bounded by bill-of-materials cost'),
    (re.compile(r'semiconductor|semis|ai accelerator|ai compute|ai connectivity',
                re.I), 10.0, 80.0,
     'fabless semis reach the 70s; a fab-owning semi does not'),
    (re.compile(r'software|saas|cybersecurity|adtech|data', re.I), 40.0, 95.0,
     'software gross margin is high but not 100%'),
    (re.compile(r'crypto|mining', re.I), -50.0, 80.0,
     'mining gross margin swings negative at low hash price'),
]

# Operating / EBITDA margin must be sector-conditioned too, and the ceiling is
# higher than intuition suggests. AppLovin's adj EBITDA margin genuinely printed
# 85% against 81% the prior year -- a flat 70% ceiling flags that as an error
# when it is real. EBITDA also excludes D&A, so it sits structurally above
# operating margin.
_OP_MARGIN_BANDS = [
    (re.compile(r'software|saas|adtech|data|cybersecurity|licensing|'
                r'brokerage|social', re.I), -100.0, 95.0,
     'software/adtech adj EBITDA margin reaches the high 80s'),
    (re.compile(r'memory|nand|dram|storage|hardware|networking|'
                r'consumer electronics|optical|substrat|wafer|wfe|'
                r'aerospace|satellite|space|power & infrastructure', re.I),
     -100.0, 70.0, 'hardware operating margin is bounded by cost of goods'),
    (re.compile(r'semiconductor|semis|ai accelerator|ai compute|'
                r'ai connectivity', re.I), -100.0, 80.0,
     'fabless semis reach the 70s'),
]
_OP_MARGIN_DEFAULT = (-100.0, 90.0)

_GROWTH_LO, _GROWTH_HI = -100.0, 500.0

# Metric-shape detectors, applied to the KPI name.
_IS_GROSS_MARGIN = re.compile(r'gross\s+margin', re.I)
_IS_OP_MARGIN = re.compile(r'(?:operating|op|ebitda)\s+margin', re.I)
_IS_GROWTH = re.compile(r'growth|comparable sales|comps|DBNRR|NRR', re.I)
_IS_PERCENT = re.compile(r'\(%\)|\(bps\)', re.I)


def _band_for_gross_margin(sector):
    for pat, lo, hi, why in _GROSS_MARGIN_BANDS:
        if pat.search(sector or ''):
            return lo, hi, why
    return None


def check_expectation(name, value, sector):
    """One expected value. Returns a finding dict, or None when plausible."""
    if not isinstance(value, (int, float)):
        return None
    name = name or ''

    if _IS_GROSS_MARGIN.search(name):
        band = _band_for_gross_margin(sector)
        if band:
            lo, hi, why = band
            if not (lo <= value <= hi):
                return dict(metric='grossMargin', name=name, value=value,
                            low=lo, high=hi, sector=sector, why=why)
        return None

    if _IS_OP_MARGIN.search(name) and _IS_PERCENT.search(name):
        lo, hi, why = _OP_MARGIN_DEFAULT[0], _OP_MARGIN_DEFAULT[1],             'operating margin outside a physically reachable band'
        for pat, blo, bhi, bwhy in _OP_MARGIN_BANDS:
            if pat.search(sector or ''):
                lo, hi, why = blo, bhi, bwhy
                break
        if not (lo <= value <= hi):
            return dict(metric='operatingMargin', name=name, value=value,
                        low=lo, high=hi, sector=sector, why=why)
        return None

    if _IS_GROWTH.search(name) and _IS_PERCENT.search(name):
        if not (_GROWTH_LO <= value <= _GROWTH_HI):
            return dict(metric='growth', name=name, value=value,
                        low=_GROWTH_LO, high=_GROWTH_HI, sector=sector,
                        why='growth rate outside a plausible band')
    return None


def check_record(rec):
    """HARD 10 over one record's EXPECTED column.

    Checks consensus and bogey on every numeric keyKPI. Deliberately does NOT
    check actuals -- a surprising actual is news, an impossible expectation is
    a data error.
    """
    findings = []
    sector = rec.get('sector') or ''
    pe = rec.get('preEarnings') or {}
    for i, kpi in enumerate(pe.get('keyKPIs') or []):
        name = kpi.get('name') or ''
        for column in ('consensus', 'bogey'):
            f = check_expectation(name, kpi.get(column), sector)
            if f:
                f.update(recordId=rec.get('id'), ticker=rec.get('ticker'),
                         column=column, kpiIndex=i)
                findings.append(f)

    # A systematic transposition shows up as BOTH columns failing on the same
    # row -- that is the SNDK signature and it is worth calling out, because
    # bogey-vs-consensus agreement is exactly what blinds HARD 8 and HARD 9.
    by_row = {}
    for f in findings:
        by_row.setdefault(f['kpiIndex'], []).append(f['column'])
    for idx, cols in by_row.items():
        if len(cols) >= 2:
            for f in findings:
                if f['kpiIndex'] == idx:
                    f['systematic'] = True
                    f['blindSpot'] = (
                        'both columns implausible and mutually consistent — '
                        'HARD 8/9 compare bogey against consensus and cannot '
                        'see this')
    return findings


def audit(model):
    """HARD 10 across the library. Returns (findings, summary)."""
    findings = []
    for rec in model.records:
        findings.extend(check_record(rec))
    summary = dict(
        recordsChecked=len(model.records),
        findings=len(findings),
        recordsFlagged=len({f['recordId'] for f in findings}),
        systematic=len({f['recordId'] for f in findings
                        if f.get('systematic')}))
    return findings, summary


def format_report(findings, summary):
    lines = ['HARD 10 — domain-implausible expected values',
             '',
             'records checked   %d' % summary['recordsChecked'],
             'findings          %d across %d record(s)'
             % (summary['findings'], summary['recordsFlagged']),
             'systematic        %d record(s) with BOTH columns implausible '
             '(HARD 8/9 blind spot)' % summary['systematic'],
             '']
    if not findings:
        lines.append('PASS — no implausible expected values.')
        return '\n'.join(lines)
    lines.append('%-14s %-5s %-34s %-10s %-9s %s'
                 % ('RECORD', 'COL', 'KPI', 'VALUE', 'BAND', 'SECTOR'))
    lines.append('-' * 104)
    for f in sorted(findings, key=lambda x: (x['recordId'], x['kpiIndex'])):
        lines.append('%-14s %-5s %-34s %-10s %-9s %s%s'
                     % (f['recordId'], f['column'][:5], f['name'][:34],
                        f['value'], '%g-%g' % (f['low'], f['high']),
                        (f['sector'] or '')[:26],
                        '  ★SYSTEMATIC' if f.get('systematic') else ''))
    lines.append('')
    lines.append('These are FLAGGED, never corrected. Mark the row '
                 'unverified: true and re-source the preview.')
    return '\n'.join(lines)
