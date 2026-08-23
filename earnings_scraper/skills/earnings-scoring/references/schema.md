# Earnings Library Record Schema

The earnings library is a JSON file at `{workspace}/earnings-library.json` with this structure:

```json
{
  "version": 1,
  "lastUpdated": "2026-04-23",
  "records": [ ... ]
}
```

Each record in `records` has the following shape. Fields marked (required) must exist even if null.

## Top-level

| Field | Type | Description |
|---|---|---|
| `id` | string (required) | `{TICKER}-{YEAR}{QUARTER}` e.g. `NVDA-2026Q2` |
| `ticker` | string (required) | Uppercase |
| `company` | string | Full legal name |
| `sector` | string | Free-text sector label (e.g., "Semiconductors", "Software / SaaS") |
| `quarter` | string (required) | `Q1` / `Q2` / `Q3` / `Q4` |
| `year` | number (required) | 4-digit year |
| `reportDate` | string (required) | ISO date `YYYY-MM-DD` |
| `timing` | string | `BMO` / `AMC` / `Mid-day` |
| `tags` | string[] | Free-form tags like `["semis", "AI", "large-cap"]` |
| `preEarnings` | object | Expectations baseline — see below |
| `actuals` | object | What was reported — see below |
| `scores` | object | Four category scores — see below |
| `summaries` | object | One-sentence summary per score category |
| `takeaways` | string[] | 3–6 key takeaways, each a single line |
| `expectedDirection` | string | `up` / `down` / `sideways` / `choppy` / `n/a` |
| `stockReactionFramework` | string | Free-text framework paragraph |
| `overrides` | string | Things that could override the direction (positioning, expectations) |
| `stockReaction` | object | Actual stock reaction — fill after the move |
| `notes` | string | Free-form notes |
| `createdAt` | string | ISO date |
| `updatedAt` | string | ISO date |

## preEarnings

```json
{
  "revConsensus": 3.74,        // number or null, in billions unless otherwise noted
  "revBogey": 3.79,            // whisper / buyside bogey
  "epsConsensus": 0.97,        // non-GAAP by default
  "epsBogey": 1.05,
  "keyKPIs": [
    { "name": "Subscription Revenue ($B)", "consensus": 3.65, "bogey": 3.695 },
    { "name": "cRPO Growth CC (%)", "consensus": 20.0, "bogey": 21.5 }
  ],
  "nextQGuideExpected": "Q2 sub rev ~$3.75B consensus...",
  "fyGuideExpected": "FY sub rev $15.53-15.57B (19.5-20% CC)...",
  "bullCase": "Fastest growing large-cap SaaS...",
  "bearCase": "SaaS valuation reset...",
  "whatMattersMost": "cRPO growth CC — THE metric, must hit 20%+...",
  "whatWins": "cRPO ≥21% CC...",
  "whatLoses": "cRPO <20% CC..."
}
```

Numbers are in the company's natural unit — usually billions for revenue, dollars for EPS, percent for margins. If a KPI is in a different unit, include the unit in the `name` field (`"Deliveries (units)"`, `"Energy Storage (GWh)"`).

`keyKPIs` is an array — the order matters because the actuals `keyKPIs` array pairs up by index.

## actuals

```json
{
  "revenue": 3.770,
  "eps": 0.97,                  // non-GAAP by default
  "grossMargin": "79.5%",       // string with unit OR number
  "opMargin": "32%",
  "keyKPIs": [
    { "actual": 3.671 },
    { "actual": 21.0 }
  ],
  "nextQGuidance": {
    "revenue": 3.8175,          // midpoint of range if a range is given
    "eps": null,
    "commentary": "Range $3.815-3.82B (21-21.5% CC)..."
  },
  "fyGuidance": {
    "revenue": 15.755,
    "eps": null,
    "commentary": "Raised $205M at midpoint...",
    "action": "raise"            // raise / maintain / cut / withdraw / initiate / n/a
  }
}
```

`keyKPIs` must be the same length as `preEarnings.keyKPIs`. Use `{ "actual": null }` for any KPI where the actual is not available.

## scores

```json
{
  "currentQuarter": 1,   // -2 to +2, in 0.5 increments
  "nextQGuidance": 1,
  "fyGuidance": 2,
  "narrative": -1
}
```

The dashboard computes the overall as a weighted average (20/30/30/20) — do NOT pre-compute and store an `overall` field.

## summaries

One sentence per category. Max ~25 words.

```json
{
  "currentQuarter": "Sub rev $3.671B beat guide high ($3.655B) by $16M. cRPO 21% CC beat guide but missed buyside 21.5% bogey.",
  "nextQGuidance": "Q2 sub rev guide above consensus but cRPO decel to 19.5% CC.",
  "fyGuidance": "FY sub rev raised $205M — crushed bull threshold.",
  "narrative": "Beat+raise sold -12%. Market punishing Armis drag and vague Now Assist ACV."
}
```

## stockReaction

Fill after the move lands. For pre-market / first-print records, leave fields `null` and update later.

```json
{
  "preMarketHigh": null,
  "preMarketLow": null,
  "openPx": null,
  "closePx": null,
  "pctChangeNextDay": -12,
  "volume": null,
  "notes": "Severe selloff despite beat+raise..."
}
```

`pctChangeNextDay` is the single most-used field — populate it when you can.

## Example records

The user's existing `earnings-library.json` in the `earnings Model` folder contains three reference records (INTC, TSLA, NOW Q1 2026). Read that file for canonical examples of every field in use.
