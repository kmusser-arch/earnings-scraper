# Scoring Rubric

Four categories. Each gets a score from −2 to +2 in 0.5 increments. The dashboard computes the weighted overall.

## Scale

| Score | Label | Criterion |
|---|---|---|
| +2 | Strong Beat | Crushed consensus AND bogey. Magnitude >1 stdev above expectations. Unambiguously positive. |
| +1 | Slight Beat | Beat consensus and mostly cleared bogey. Not a blowout. |
| 0 | Inline | Hit consensus, missed/hit bogey. No edge either way. |
| −1 | Slight Miss | Below consensus. Mixed with some offsets. |
| −2 | Major Miss | Well below consensus. No offsets. Unambiguously negative. |

Use 0.5 increments when the read is between categories. An inline print with a great KPI mix could be `+0.5`. A beat with one material red flag could be `+1.5`.

## Weights

| Category | Weight | Why |
|---|---|---|
| Current Quarter | 20% | The past. Matters but already in the stock to some degree. |
| Next Q Guidance | 30% | Forward demand read — most important for next 1–3 weeks of tape. |
| FY Guidance | 30% | Forward demand read — most important for multi-quarter positioning. |
| Narrative | 20% | Does this confirm or break the setup? Interprets the rest. |

## Category definitions

### 1. Current Quarter

Score the Q that was just reported. Focus on:
- Revenue vs consensus + bogey (magnitude and direction)
- EPS vs consensus + bogey
- Key KPIs vs consensus (subs, deliveries, cRPO, segment revs, margin)
- Segment beats/misses — are all segments pointing the same way?
- Margin trajectory
- Any one-time items distorting the print (flag but don't overweight)

**Weight the KPIs, not the EPS**, for growth stocks. A company can engineer EPS with tax rate; it cannot engineer a subscriber adds number.

### 2. Next Quarter Guidance

Compare guidance to the Next-Q consensus. This is the most actionable forward signal.

- Revenue guide (range → use the midpoint)
- EPS guide
- Margin guide
- Any qualitative commentary on demand, pricing, backlog

If the company does not give formal quarterly guidance (e.g., TSLA historically), score based on management tone from the release. Neutral tone = `0`, bullish commentary = `+1`, cautious commentary = `-1`. Do not default to −2 just because formal guidance is absent.

### 3. Full-Year Guidance

`action` field is the anchor: raise / maintain / cut / withdraw / initiate.

- `raise` → at least `+1`. If the raise magnitude crushes the bull-bogey threshold, `+2`.
- `maintain` → usually `0`. `+0.5` if maintaining was better than feared. `-0.5` if the market needed a raise.
- `cut` → at least `-1`. If the cut is sharp or driven by demand weakness, `-2`.
- `withdraw` → usually `-1` or `-2` depending on reason. Tariff/macro driven less punitive than company-specific.
- `initiate` → context-dependent; usually `0` to `+1` if in-line or above.
- `n/a` (company does not give FY) → score `0` unless commentary suggests a directional read.

### 4. Narrative

Did this print confirm or break the market narrative going in?

- Bulls validated → `+1` to `+2`
- Bears validated → `-1` to `-2`
- Mixed / no clear winner → `0`
- Narrative shifts (e.g., from "demand problem" to "execution") → note in the summary

Narrative is where you capture the reflexive stuff: positioning, sentiment, sector tone. If a stock is heavily shorted going in and the print is a beat, narrative is `+1` even if the beat was modest — because the setup amplifies the move.

## Overrides (from the earnings model instructions)

Apply these at the category level, NOT by changing the weights:

- **Guidance > Current Quarter.** If the current Q is a beat but the guide is a cut, the overall read is bearish. The guide scores should reflect that fully (i.e., the guide miss scores `-2`, not a hedged `-1`).
- **KPIs > EPS for growth stocks.** If EPS beats on a tax benefit but subs adds miss, current-quarter score is `-1`, not `+1`.
- **Margins > everything for profitability stories.** For a turnaround story where gross margin is the thesis, weight margin more heavily within the current-quarter score.

## Worked examples from the existing library

### INTC Q1 2026 — Overall +1.55 (Bullish)

- Current Quarter: `+2`. Rev $13.58B crushed $12.36B (+9.9%). EPS $0.29 vs $0.01. GM 41.0% vs 34.5%. Every segment beat. DCAI +22% YoY.
- Next Q Guidance: `+2`. Q2 mid $14.3B vs $13.04B. GM 39.0% clears 38% bull threshold. EPS $0.20 vs $0.09.
- FY Guidance: `+0.5`. No formal FY rev/EPS. OpEx guide slightly above est. Neutral-positive.
- Narrative: `+2`. Turnaround confirmed. 6th consecutive beat. NVIDIA DGX Rubin validation. Bears wrong.

Read: overwhelming beat with the guide clearing the highest Street threshold. +1.55 weighted makes sense — would have been +2 if FY guide was formal.

### TSLA Q1 2026 — Overall +0.6 (Bullish)

- Current Quarter: `+2`. Auto GM ex-credits 19.2% (best in 8 Qs) vs 17.7%. FCF +$1.44B vs −$1.86B expected ($3.3B delta). EPS $0.41 beat $0.35.
- Next Q Guidance: `0`. No formal quarterly guidance. Qualitative "maximum capacity utilization."
- FY Guidance: `0`. No FY numbers. Capex pace below implies H2 ramp risk.
- Narrative: `+1`. Margin recovery shifts narrative from "demand problem" to "execution." FSD subs +51% YoY. Energy weak.

Read: current-Q blowout but no forward guide to score. +0.6 reflects that reality. The stock went +4% in line with the score.

### NOW Q1 2026 — Overall +0.9 (Bullish, but market disagreed)

- Current Quarter: `+1`. Sub rev beat guide high. cRPO 21% CC beat guide but missed 21.5% buyside bogey.
- Next Q Guidance: `+1`. Q2 sub rev guide above consensus. But Q2 cRPO decel to 19.5%.
- FY Guidance: `+2`. Raised $205M — crushed bull $75M threshold.
- Narrative: `-1`. Beat+raise sold -12%. Market punishing Armis drag and vague Now Assist ACV.

Read: fundamentals scored clearly positive but the narrative was negative because the setup (SaaS sentiment + Q4'25 precedent + Armis drag) overwhelmed the print. The +0.9 overall is the fundamental read; the −12% stock move is the market read. **This divergence is exactly what the library is for** — it surfaces cases where the model is right but the tape disagrees, letting the user learn.

## Sanity checks before finalizing

- If Current Quarter is `+2` but Narrative is `-1`, explain why in the narrative summary. Usually this means setup/positioning is overwhelming the print.
- If Overall score is > `+1.5` but stock reaction is negative, that is a flag — either the score is wrong (missed a forward-looking negative) or the market is wrong (temporary). Note in the `notes` field which one you think it is.
- If three of four categories are `0`, the print is genuinely boring — do not force positive or negative on a boring print.
