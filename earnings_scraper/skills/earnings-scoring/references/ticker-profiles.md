# Ticker Profiles — Hero KPI Override System

Some stocks are driven by a single metric, not headline EPS or revenue. This system lets you score them correctly.

## Core problem

Default weighting:
- Current Quarter 20% | Next Q Guide 30% | FY Guide 30% | Narrative 20%

This fails for stocks where **one line in the release IS the print**:
- AMZN → AWS growth
- MSFT → Azure CC growth
- NVDA → Next-Q revenue guide
- META → FY capex guide
- NFLX → Operating margin guide

A strong EPS beat + weak hero KPI can still send the stock down 5-10%. The scorecard must reflect that.

## How it works

1. **Before scoring**, read `ticker-profiles.json` in the workspace folder.
2. **Look up the ticker**. If a profile exists, extract:
   - `heroKPIs[]` — the metrics that drive the stock
   - Each KPI has a `priority` (1 = critical, 2 = important, 3 = secondary)
   - Each KPI optionally has `appliesTo` — which score category it overrides (`currentQuarter`, `nextQGuidance`, `fyGuidance`, `narrative`). Default is `currentQuarter`.
3. **Score the hero KPI first**, then apply override rules.

## Override rules

### Rule 1 — Priority-1 hero KPI dominates its target category

If a priority-1 KPI applies to Current Quarter:
- **Hero KPI scores +2** → Current Quarter = +2, regardless of EPS/revenue.
- **Hero KPI scores -2** → Current Quarter caps at **0**, even with an EPS/rev beat.
- **Hero KPI scores ±1** → Current Quarter blends toward it (weighted 70% hero / 30% other).

Same logic for Next Q Guidance or FY Guidance if the KPI `appliesTo` those categories.

### Rule 2 — Multiple priority-1 KPIs

If a ticker has 2+ priority-1 hero KPIs in the same category, average them. Both must beat for a +2; one miss caps at 0.

Example: GOOGL has Search growth + Cloud growth, both priority-1. Cloud beats, Search misses → Current Quarter = 0, not +1.

### Rule 3 — Narrative amplification

If any priority-1 hero KPI scores +2 or -2, push the Narrative score toward that direction by at least 1 point. Extreme hero moves reshape the story even when other metrics are fine.

### Rule 4 — Qualitative hero KPIs (commentary items)

Some KPIs are qualitative ("Azure AI commentary", "Robotaxi timeline"). Score these by:
- **+2** — explicit upside surprise, new concrete detail, bullish forward tone
- **+1** — incrementally positive, reiterates or slight upgrade
- **0** — in line with prior tone, no new info
- **-1** — softer tone, caveats, delays
- **-2** — explicit walk-back, timeline slip, negative surprise

### Rule 5 — `interpretation` field

Some KPIs have an `interpretation` note in the profile that reverses normal polarity. Example: META's capex guide — a *higher* capex print is often bearish for the stock short-term. Respect the interpretation, not the raw beat/miss math.

## Beat/miss bands

Each KPI has `beatBand` and `missBand` — the threshold for scoring +1 vs +2 and -1 vs -2.

Example: MSFT Azure CC growth, `beatBand: 100` (bps):
- Consensus 29% → Actual 31% = +200bps above = **+2 (strong beat)**
- Actual 30% = +100bps above = **+1 (beat)**
- Actual 29% = in line = **0**
- Actual 28% = -100bps = **-1 (slight miss)**
- Actual 27% = -200bps = **-2 (major miss)**

## Workflow integration

Drop this into Step 5 of the skill:

```
Step 5a — Load ticker profile
- Read {workspace}/ticker-profiles.json
- Look up ticker. If no profile exists, proceed with default weighting.
- If profile exists, extract hero KPIs + priorities + appliesTo.

Step 5b — Score hero KPIs first
- For each hero KPI, compare actual vs consensus/prior
- Score each -2 to +2 using beatBand/missBand

Step 5c — Apply overrides
- For each affected category, apply Rule 1 or Rule 2
- Apply Rule 3 (narrative amplification) if any priority-1 KPI is ±2

Step 5d — Score remaining categories
- Current Quarter / Next Q / FY / Narrative scored normally where no override applies

Step 5e — Document the override in the output
- In Key Takeaways, explicitly call out which hero KPI drove the score
- Example: "AWS growth printed 19.2% vs 17.8% consensus — hero KPI override lifts Current Quarter to +2 despite in-line headline EPS."
```

## Editing profiles

The user owns `ticker-profiles.json`. When the user says "add profile for X" or "update AMZN hero KPI":
1. Read the current file
2. Add/update the ticker entry
3. Bump `lastUpdated` to today's date
4. Write back

When adding a new ticker profile, ask the user:
- What are the 1-3 metrics that move this stock?
- Which matter for current-quarter read vs forward guidance?
- What's the typical beat/miss band (in % pts or bps)?

If the user does not know, make a reasonable first pass based on the story type (growth / margin / consumption / turnaround) and flag the thresholds as "anchors — edit after first print."

## Failure modes to avoid

- **Don't override when there's no profile.** Default weighting is correct for most stocks.
- **Don't stack overrides.** One Rule-1 override per category. Don't let Narrative amplification (Rule 3) push past ±2.
- **Don't fabricate consensus for the hero KPI.** If you cannot find a sell-side number for the hero KPI, note "consensus for AWS growth ~17.5% (Street estimate range 17-18%)" and score conservatively.
- **Don't ignore qualitative KPIs.** Tone and commentary matter as much as numbers for TSLA, NVDA, MSFT calls.
