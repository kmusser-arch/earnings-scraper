---
name: "earnings-scorer"
description: "End-to-end earnings evaluation for an intraday news trader. Trigger whenever the user pastes an earnings press release, shares actuals, mentions grading/scoring/analyzing an earnings print, references their earnings library or dashboard, or mentions a ticker with phrases like \"just reported,\" \"print is out,\" \"earnings dropped.\" Also trigger for pre-earnings research requests (consensus, bogeys, analyst expectations, positioning, sentiment) on a stock that reports soon — every pre-earnings build MUST include the numeric positioning axis and the if/then scenario ladder. Handles both paths — preview provided (score directly) and no preview (deep research first, then score). Persists the record to the user's earnings-library.json for the live dashboard. Lean toward triggering; missing a print is worse than running a redundant analysis."
---

# Earnings Scorer

End-to-end workflow: research (if needed) → score → persist → output. Prioritize speed. The user is an intraday trader who is often reading this on the tape while the stock is moving. Seconds matter.

## When to use

Trigger whenever the user:
- Pastes an earnings press release or earnings PR text
- Shares actuals (revenue, EPS, guidance) for a company
- Mentions "grade," "score," "analyze," "evaluate," "scorecard" in an earnings context
- References their earnings library, dashboard, or asks to update it
- Asks for pre-earnings research or what to watch for a reporting name
- Mentions a ticker with phrases like "just reported," "print is out," "earnings dropped"

When ambiguous, trigger anyway and clarify inside the workflow. Missing a print is worse than running a redundant analysis.

## ⚡ THE ONE RULE THAT OVERRIDES EVERYTHING

**On a PR paste, the full scorecard is the FIRST output, with ZERO tool calls before it.** Persist to the library, regenerate the dashboard and produce the push command only *after* the read is delivered. The user is watching the tape.

Pre-earnings builds are the opposite — those are done ahead of time, so completeness wins over speed there.

## Workflow

### Step 1: Identify ticker and quarter

Extract ticker + quarter + year. If ambiguous, ask one quick question. Do not proceed without these three anchors.

### Step 2: Read the existing library

Library location: `{workspace}/earnings-library.json` (check with `ls`/Glob before assuming a path).

Use it to:
- Pull the prior-quarter record for this ticker — needed for narrative alignment, guidance delta, Q/Q trajectory, and the prior-print positioning component
- Detect duplicates. **Q2 prints APPEND a new record with a distinct id — never overwrite a prior quarter.**
- **Read the top-level frameworks — they are the authoritative, version-controlled source for the rules summarized in this file:** `positioningFramework`, `scenarioLadderFramework`, `beatMagnitudePatterns`, `overnightHoldFramework`, `regimeFramework`

If the file does not exist, create `{ "version": 1, "lastUpdated": "", "records": [] }`.

### Step 3: Branch on whether a preview is provided

**Path A — Preview provided.** Use it as the expectations baseline.

**Path B — No preview.** Do deep pre-earnings research first (`references/research.md`): sell-side consensus, buyside bogeys, segment/KPI expectations, ratings + price targets, recent catalysts, prior-quarter reaction, implied move, positioning. State what you are searching for; do not research silently.

---

## ★ Step 3a — THE MANDATORY PRE-EARNINGS BLOCK

**Every pre-earnings build MUST include both of the following. They are not optional add-ons — the point is to understand the entire setup before the print hits.** A pre-earnings deliverable without them is incomplete.

### 3a-i. The numeric positioning axis

Six components, each **−2 to +2**, where **positive = MORE CROWDED LONG**.

```
raw     = sum of the six components        (−12 … +12)
score10 = (raw + 12) ÷ 24 × 10             (0 … 10)
```

| # | component | what it measures | corr vs reaction |
|---|---|---|---|
| 1 | **relativePerf** | RPS = stock return − SPX/sector return, same window, in points | −0.639 |
| 2 | **sellSide** | Buy share, spot vs average PT, raise cadence, Hold-count trend | −0.550 |
| 3 | **runIntoPrint** ★ | print-day move ÷ implied move — **the pre-paid veto** | **−0.832** |
| 4 | **optionsPosture** | skew, near-money put OI, net GEX, premium-selling flow | −0.359 |
| 5 | **squeezeFuel** | SI % of float, DTC, borrow (INVERTED) | −0.156 |
| 6 | **priorPrintPattern** | did the tape sell this ticker's good prints? | −0.462 |

Component rubrics, worked examples and the validation record live in `positioningFramework` in the library.

**Bands and sign modifier:** ≥8.0 🔴 SEVERELY CROWDED (−0.75) · 6.5–7.9 🟠 CROWDED (−0.40) · 4.0–6.4 ⚪ BALANCED (0) · 2.5–3.9 🟢 DE-RISKED (+0.40) · <2.5 🔵 HATED (+0.75)

`adjustedScore = scores.overall + signModifier`. **Never modify `scores.overall`** — the fundamental score stays pure so the adjustment remains testable.

**Four hard rules:**

1. **INGEST THE SHEET SCORE.** TMTB and buyside bogey sheets publish an explicit positioning score in the header, 0–10, **same polarity** (higher = more crowded). When present it is the authoritative anchor for components 1–2 — record it verbatim in `positioningAxis.externalScore` and do not re-derive it. **But never trade off it alone:** the sheet score correlates only +0.066 with reaction, because it is fixed 1–3 days early and cannot contain component 3.
2. **RUN-INTO-PRINT IS THE STRONGEST SIGNAL IN THE SYSTEM** at −0.832 — stronger than the entire fundamental scorecard. It is one division. Compute it first.
3. **TWO-TIMEFRAME RULE** (component 1). When the 1-year and last-5-session windows disagree, **the short window governs** — it identifies the marginal holder.
4. **REGIME GATE** (component 6). Score 0 unless the prior-print pattern was established in the *same* chart/multiple regime being traded now.

**Short interest is a weak standalone crowding proxy** (−0.156) — convert arb, GC borrow and low DTC all break it. Keep it for context; do not lean on it.

At T−1, components **1, 2, 5 and 6** are knowable. Compute a provisional `score10` and mark `confidence` honestly (`HIGH` only at 6/6). Component 3 gets locked at 4:00 PM, component 4 from the chain.

### 3a-ii. The if/then scenario ladder

Read the required-surprise tier off the provisional positioning band:

| positioning | the print MUST deliver | an INLINE guide means | default bias |
|---|---|---|---|
| **≥8.0** 🔴 | an UNMODELED DISCLOSURE **and** runIntoPrint < +2 | SELL, −5% to −10% | FADE |
| **6.5–7.9** 🟠 | guide >+3% vs **BOGEY** and not pre-paid | SELL, −2% to −5% | FADE unless a real raise |
| **4.0–6.4** ⚪ | normal beat, guide ≥ bogey | flat to −3% | fundamentals govern |
| **2.5–3.9** 🟢 | any clean bogey clear | absorbed, ~flat | LONG on any clear |
| **<2.5** 🔵 | almost nothing | rallies anyway | LONG, downside absorbed |

Then write **4–6 branches** into `scenarioLadder`:

```json
{"branch":"BULL — guide crush","trigger":"NUMERIC, on the hero KPI and/or guide lines, stated vs BOGEY and vs street",
 "positioningContext":"which tier, and whether the escape clause is armed","expectedReaction":"a RANGE from the matrix cell",
 "tradeType":"momentum continuation | overreaction fade | reversal | no trade","stayForCall":"yes/no + why",
 "overnightEligible":"per overnightHoldFramework","basedOn":"which matrix cell, and n"}
```

**Branch-writing rules:**
- **Every trigger is a NUMBER, not an adjective.**
- Always state the **bogey delta AND the street delta** — the same headline pays roughly 5x more against bogey than against street.
- **Always include an INLINE branch.** Inline is the modal outcome, and at crowded positioning it is a short.
- Include a **call-only branch** for any ticker that has withheld guidance from the PR before (per-ticker habit; track it).
- Axis 2 is always the ticker's **priority-1 hero KPI plus the guide lines — never a generic revenue column.** Revenue-vs-bogey once filed a +17% print as a coin flip because revenue printed +0.03% while the move came from an unmodeled forward disclosure.

### 3a-iii. The two highest-conviction cells

- **CROWDED ≥7 + NO guidance delta → 3 for 3 DOWN, median −12%.** Marginal buyer is gone *and* the company handed the market nothing to reprice on. Best short setup in the library, and it is knowable at T−1 from the ticker's guidance habit.
- **DE-RISKED <4 + guide >+3% vs bogey → 3 for 3 UP, tight +8.4% to +13.1%.** A marginal buyer exists and the raise gives them the reason. The tight band makes this the cell to *size*.

**Caveat to state honestly:** matrix cells are n=1 to 3. Frame branches with them; do not size off them. The full matrix is in `scenarioLadderFramework.REACTION MATRIX`.

### 3a-iv. The 4:00 PM lock (same-day, before the PR)

- **Lock component 3** — print-day move ÷ implied move. **It only exists now.**
- Lock component 4 from the chain.
- Recompute `score10`. If it crossed 7.0, the crowded-long escape clause is armed.
- **If component 3 = +2, downgrade every bullish branch one notch before the PR crosses.**

---

### Step 4: Parse the press release (actuals)

Extract: revenue, EPS (GAAP and non-GAAP), gross/operating margin, segment revenue, business-specific KPIs, next-quarter guidance, full-year guidance (raise/maintain/cut/withdraw/initiate), buyback/dividend changes, restructuring or one-time items.

Flag large GAAP/non-GAAP gaps explicitly — the market usually ignores GAAP noise but headlines trip algos in the first minute.

**Watch for definitional mismatches before grading a line.** A consensus figure that measures something different from the reported line produces a false beat or false miss. Flag and do not grade.

### Step 5: Score the four categories

| Category | Weight | Range |
|---|---|---|
| Current Quarter | 20% | −2 to +2 |
| Next Q Guidance | 30% | −2 to +2 |
| FY Guidance | 30% | −2 to +2 |
| Narrative | 20% | −2 to +2 |

Overall = weighted average. Steps of 0.5. ≥+0.5 Bullish · ≤−0.5 Bearish. Keep each category summary to **one sentence**.

Weighted overrides: guidance > current quarter · KPIs > EPS for growth stocks · margins for profitability stories. Apply to the category scores themselves, not by re-weighting.

**Grade against BOGEY, STREET and the COMPANY'S OWN GUIDE as three separate columns:** 🟢 clears bogey · 🟡 beats street but misses bogey = **FADE ZONE** · 🔴 misses street.

#### Step 5a: Load the ticker profile (hero KPI override)

Read `{workspace}/ticker-profiles.json`. See `references/ticker-profiles.md`. Rules:
- A priority-1 hero KPI at ±2 dominates its target category
- A hero KPI **miss** on the current quarter **caps Current Quarter at 0**, even with a revenue/EPS beat
- Any priority-1 KPI at ±2 pulls Narrative by at least 1 point
- Respect `interpretation` fields that reverse polarity (e.g. META capex, ANET deferred revenue)

If there is no profile, proceed with default weighting and offer to add one.

### Step 6: Build the record

Use `references/schema.md`. Unknown fields stay `null` or `""` — **never fabricate**. Label research-sourced fields in `notes`.

`id` = `{TICKER}-{YEAR}{QUARTER}`.

**Blocks that are MANDATORY on a post-earnings write** (each one has a dashboard tab that renders empty without it):

- **`actuals.keyKPIs` index-aligned 1:1 with `preEarnings.keyKPIs`** — same order, same length. The dashboard maps them **POSITIONALLY**, so a missing or mismatched array silently blanks the Actual-vs-Expected grid *while still rendering*. Pull the pre-earnings KPI order FIRST, then build the actuals array against it. Each entry: `{actual, vsCons, vsBogey, vsConsNote, vsBogeyNote}`, plus `pctVsCons` / `pctVsBogey` / `pctVsGuide` for the beat-magnitude analytics (suppress values beyond ±300% as unit mismatches and tag `pctFlag`).
- **`callCommentary`** — 5 fields; `missedInPR`, `incrementalAnalystActivity` and `keyQuotes` must be LISTS.
- **`tradeSummary`** — plan vs actual vs lessons vs forward; `catalystOverrides`, `whatIGotRight`, `whatIGotWrong`, `patternLessons` must be LISTS.
- **`positioningAxis`** — carried forward from the pre-earnings build with component 3 locked.
- **`beatMagnitude`** — `revPctVsCons`, `revPctVsBogey`, `score`, `reactionPct`, `impliedMove`.

### Step 7: Write to the library, then VERIFY

1. Append or replace the record, bump `lastUpdated`, write back pretty-printed.
2. **Run `{workspace}/validate_library.py`.** It must exit 0. It checks stored `overall` against the weighted average, the positional KPI alignment, list-typed fields the renderer `.map()`s, sector drift, positioning-axis internal consistency, and grids that are aligned but contain no actual values.
3. **Run the DOM-stub render test** over every card and every tab.
4. Regenerate `dashboard-standalone.html` (embed the library, refresh `PROFILES`).
5. Provide the one-paste push command.

**A render test that only proves tabs *render* is not sufficient — assert they contain DATA.** That blind spot once let 12 blank Actual-vs-Expected grids through.

### Step 8: Output

```
[COMPANY] — EARNINGS SCORECARD

⚡ ASYMMETRIC EVENT FLAG (only if it fires — goes at the very TOP)

HERO KPIs — street | bogey | actual   (table, first)

Overall Score: X.XX (Bullish / Neutral / Bearish)

1. Current Quarter: [score]   — one sentence
2. Next Quarter Guidance: [score]   — one sentence, above/inline/below
3. Full-Year Guidance: [score]   — one sentence, raised/maintained/cut
4. Narrative Check: [score]   — one sentence, confirmed or broke the setup

5. Key Takeaways — 3–5 bullets max
6. Stock Reaction Framework — expected direction and what could override it
```

**FORMAT IS LOCKED. Do not change it between prints.** The asymmetric flag goes at the top when it fires, then the hero KPI table with street / bogey / actual, then the four categories. On a post-earnings scorecard, also name **which pre-written branch the print matched**.

Follow with the library-updated count and a link to the file.

## Speed rules

- Lead with the score and direction.
- No disclaimers, no boilerplate, no "it depends."
- A missing number is flagged "pending" on that category — never block the full scorecard.
- If a read cannot compress to one sentence, the score is wrong or the data is incomplete.
- **Give the ENTIRE scorecard, every time.** Partial output is not faster, it is unusable.

## Standing analytical rules

These are earned lessons. Apply them; do not re-derive them.

- **⚡ Asymmetric Event Flag** — a vague-but-quantitative forward claim lacking a dollar anchor fires the flag. 3 gates: MAGNITUDE, HORIZON, FORCEFUL, plus unambiguous direction. Bidirectional. The flag exists to change behaviour: **stay for the call.**
- **Guidance withheld from the PR = stay for the call.** Track per ticker. A PR with actuals but no forward guide is a decoy; the call is the event.
- **PR-vs-CALL score divergence** is a first-class metric. Score the PR, re-score after the call, log the delta. It has predicted direction better than the PR score alone.
- **Peak-cycle buyside-inline fade** — at stretched cycle positioning, inline with a stretched bogey is a sell; only a nuke-crush (>110% of bogey) saves it.
- **SCA catalyst override** — multi-year (≥5yr) take-or-pay agreements with $100B+ cumulative backlog, ≥10% cash deposits and floor pricing override the peak-cycle fade.
- **ACTION cap-the-model** — founder-CEOs can cap the model through *actions* (removed roadmap language, delayed timelines, capex with no dollar anchor) while sounding bullish. Actions beat words. Diff the shareholder deck.
- **Guidance hierarchy scalp rule** — a weak forward guide means scalp only, never hold, even on a good quarter.
- **Chart-confluence override** — single-name plus sector-ETF daily setup beats a negative fundamental base rate. **Fade patterns are REGIME-CONDITIONAL.** Before citing any base rate, ask whether it was established in the regime being traded now.
- **Hold duration must inherit the entry thesis** — a multi-day structural setup implies a multi-day hold.
- **Unmodeled disclosures have no consensus denominator.** Measure them against the **current run rate**, not consensus (>2x run-rate = model rebuild). This is the AMD Q1 (+17%) vs AMD Q2 (−8%) differentiator.
- **Overnight holds** pay only when the after-hours session could not finish pricing the print. Direction-agnostic. Vetoes: PR-legible in one line, already pre-paid the implied move, AH settle ≥1.5x implied, whipsaw ratio >3x.

## Edge cases

- **BMO / mid-day prints** — set `timing` accordingly.
- **Corp actions** — tag them; do not let the noise move core category scores.
- **Company never guides** (e.g. TSLA) — score Next Q `0` on neutral tone rather than penalizing an absence. Narrative captures the tone.
- **FY guide withdrawn** — `−1` or `−2` by reason; macro/tariff uncertainty scores less punitively than company-specific weakness.
- **Paper / not-traded prints** — tag `paper-test`. They feed the reaction matrix but stay out of trade-summary stats. These are valuable: they fill matrix cells the user's normal universe never reaches.

## Prior quarter comparison

If a prior quarter exists, close with:

```
Q-over-Q shift:
- Score: +X.X → +Y.Y
- Positioning: X.X → Y.Y
- Key narrative change: one sentence
- Guidance trajectory: raising / steady / cutting
```

## Files and sources of truth

- `SKILL.md` — this file, the workflow entry point
- **`{workspace}/earnings-library.json` → `positioningFramework` and `scenarioLadderFramework`** — the authoritative, version-controlled detail behind Step 3a (component rubrics, worked examples, the full reaction matrix, validation record, open questions). Read these in Step 2.
- `references/schema.md` — exact JSON schema for library records
- `references/research.md` — deep research playbook when no preview is on hand
- `references/scoring.md` — scoring rubric, weighting, worked examples
- `references/ticker-profiles.md` — hero KPI override system; companion to `{workspace}/ticker-profiles.json`
- `{workspace}/validate_library.py` — must exit 0 after every write

