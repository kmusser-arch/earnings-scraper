---
name: earnings-scoring
description: The complete earnings scoring rubric, keyKPI ordering rules and pre-earnings build procedure for Kyle's earnings model. Canonical, version-controlled copy — supersedes any instructions living only in the Claude desktop app.
version: 1.0
created: 2026-08-17
source_of_truth: earnings-library.json (frameworks are embedded as top-level keys)
---

# Earnings Scoring — Canonical Rubric

**Read this with `earnings-library.json` open.** ~102 KB of this model already lives inside that file as top-level keys and is machine-readable:

| key | bytes | what it holds |
|---|---|---|
| `positioningFramework` | 12,149 | 6-component axis, bands, sign modifiers, interaction rule, validation record |
| `scenarioLadderFramework` | 7,768 | 4-checkpoint workflow, required-surprise tiers, reaction matrix |
| `overnightHoldFramework` | 31,739 | 4-condition test, whipsaw ratio, disqualifiers, case log |
| `beatMagnitudePatterns` | 36,967 | sector-grouped reaction bands, `allRows`, key findings |
| `branchAccuracyLog` | 10,423 | forward-written branch predictions vs realised reactions |
| `regimeFramework` | 1,690 | RISK-ON / CHOPPY / RISK-OFF multipliers |
| `schemaNotes` | 1,531 | field-level schema contract |

Do not duplicate those into code. **Read them at runtime** so a framework revision propagates without a code change.

---

## ⛔ THE FINDING THAT INVALIDATES A `_CQ_BANDS` KEYED ON CONSENSUS DELTA

A band function of the form `score = f(rev_pct_vs_consensus, eps_pct_vs_consensus)` **cannot reproduce the 76 accepted grades.** Proof from the library:

| record | cq grade | rev % vs **consensus** | rev % vs **bogey** |
|---|---|---|---|
| SNDK Q4 FY26 | **+1.0** | **+6.9%** | −5.6% |
| ALAB Q1 | **+1.0** | **+5.5%** | −3.6% |
| CRWV Q2 | **+1.5** | **+0.6%** | n/a |
| MRVL Q1 FY27 | **+1.5** | **+0.3%** | −3.3% |
| TSLA Q1 | **+2.0** | **+0.5%** | −0.5% |

SNDK beat consensus by 6.9% and scored **+1.0**. CRWV beat by 0.6% and scored **+1.5**. TSLA beat by 0.5% and scored **+2.0**. The consensus delta is close to uninformative.

**The discriminator is clearance of the BOGEY, applied to the ticker's PRIORITY-1 HERO KPI — not to revenue.** Empirical medians:

```
cq=+0.5   n= 9   median rev%bogey  -0.74%   range -11.1% .. +3.2%
cq=+1.0   n= 9   median rev%bogey  -0.73%   range  -5.6% .. +0.3%
cq=+1.5   n=10   median rev%bogey  +0.06%   range  -99.9% .. +6.1%
cq=+2.0   n=17   median rev%bogey  +1.32%   range  -99.9% .. +15.8%
```

Note +0.5 and +1.0 share the same median. **Bogey clearance alone does not separate them — the offsetting-flag count does.** The rubric below is therefore two-dimensional, and the last half-point is a judgment call that should stay deferred rather than guessed.

### ★ THE STEP-DOWN — how to handle a flag count above the band's `maxFlags`

The band table has no row for e.g. "clears bogey 0–2% with ≥2 flags", which is exactly where SNDK Q4 FY26 sits. **Confirmed 2026-08-18:**

```
score = base − 0.5 × max(0, flags − maxFlags)
```

**SNDK Q4 FY26 worked:** gross margin (its priority-1 hero) cleared bogey by **+0.71%** → base **+1.5** (`maxFlags` 1) → **2 flags** → `1.5 − 0.5 × (2 − 1)` = **+1.0**. Matches the accepted grade.

Apply the same step-down on the negative side and floor at −2.0. Report it as `stepDownApplied` and surface it on the card — it is a derived rule reconciling the published table with the pins, not an independently validated one.

### ★ Flags that a press release cannot settle
Three of the seven are not assessable from a PR alone: **segment sequential detail**, **price vs volume**, and **ARR/RPO vs order growth**. Report those as **NOT ASSESSABLE** rather than assuming absent — an unassessed flag can move the band, so silently treating it as zero biases every score upward.

---

## 1. CURRENT QUARTER (weight 20%)

**Step 1 — select the graded metric.** Load `ticker-profiles.json → profiles[TICKER]`. Take the `priority: 1` entry whose `appliesTo == "currentQuarter"`. **That metric, not revenue, is what you grade.**

**If no profile exists → `NO_PROFILE`. REFUSE TO GRADE.** Do not fall back to revenue.

> ⚠️ **Corrected 2026-08-18.** An earlier revision of this line said "fall back to revenue and set `confidence: 'no-profile'`", which contradicted `CLAUDE.md`, `HANDOFF.md` and `SCRAPER-CONTRACT.md` — and contradicted the finding at the top of this file. Revenue-based grading provably cannot reproduce the accepted grades, so a revenue fallback produces a **confidently wrong** score, which is worse than a blank because it propagates into `beatMagnitude` and `branchAccuracyLog`. **Refuse, alert, display the raw numbers ungraded.**
>
> This should rarely fire in practice: `validate_library.py` **HARD 7** fails when a ticker has a record but no profile, and all 57 tickers in the library are covered. `NO_PROFILE` means a genuinely new ticker with no pre-earnings build — which is also a `NO_CARD`.

**Step 2 — compute clearance on three columns** (bogey / consensus / the company's own guide), in that order of authority:

```
clearance = (actual - bogey) / bogey        # if a bogey exists
            (actual - consensus) / consensus  # else, and flag lower authority
```

**Step 3 — count offsetting flags.** Each of these is one flag:

- a second priority-1 hero KPI missed its bogey
- gross or operating margin declined **year-over-year**
- a segment declined **>20% sequentially**
- growth was majority **price rather than volume** (if disclosed)
- ARR / RPO growth lags order or revenue growth by **>20 percentage points**
- the reported figure landed **at or below the company's own guide top** (i.e. it did not exceed its own range)
- a **GAAP vs non-GAAP or company-defined-metric basis gap** materially changes the sign

**Step 4 — the band:**

| score | condition |
|---|---|
| **+2.0** | hero KPI clears bogey by **≥+2%** AND **0 flags** |
| **+1.5** | hero KPI clears bogey by **0% to +2%** AND **≤1 flag** — or clears by ≥+2% with exactly 1 flag |
| **+1.0** | hero KPI **beats consensus but misses bogey by 0 to −5%**, with **1–2 flags** |
| **+0.5** | beats consensus, misses bogey, **≥3 flags** — or clears bogey with a hero-KPI-neutral profile |
| **0.0** | inline, **or a priority-1 hero KPI MISSED with nothing else wrong** (see the cap rule) |
| **−0.5** | modest consensus miss on one graded line |
| **−1.0** | consensus miss on the hero KPI **and** one other graded line |
| **−1.5** | consensus miss on multiple lines **AND** a failure of the company's **own guidance range** |
| **−2.0** | hero KPI major miss **plus** own-guide failure **plus** margin collapse |

### ★ THE HARD CAP RULE — a CEILING, not a value. Implement it before the band.
**A priority-1 hero KPI that MISSES on the current quarter caps Current Quarter at 0.0, regardless of a revenue or EPS beat.**

> ⚠️ **Clarified 2026-08-18.** "Caps at 0.0" means **0.0 is the CEILING — the negative bands still apply beneath it.** Implementing it as an assigned *value* scores APP and CBRS at 0.0 against their accepted −1.5.
>
> ```
> cq = min(band_lookup(clearance, flags), 0.0)   # ceiling, not assignment
> ```
>
> Founding cases, both of which reach **−1.5** *through* the cap, not at it:
> - **APP Q2 2026** — adj EBITDA margin missed (cap fires) → then multi-line consensus miss **plus** adjusted EBITDA below the LOW END of its own guide range → −1.5.
> - **CBRS Q2 2026** — hardware revenue −26% vs estimate and −23% YoY (cap fires) → then multi-line miss **plus** a second consecutive sequential core-margin decline → −1.5 despite a +9.9% company-defined "core" revenue beat.

### ★ Reverse-polarity metrics
Respect `interpretation: "reverse-polarity"` in the profile. META capex and ANET deferred revenue score **inverted** — a build is bearish, not bullish backlog.

---

## 2. NEXT-QUARTER GUIDANCE (weight 30%) — your first deferred branch

Grade the **guide midpoint** against bogey, then consensus. Weight 30% because guidance outranks the current quarter.

| score | condition |
|---|---|
| **+2.0** | guide mid clears bogey by **≥+3%**, and the margin/EPS line also clears |
| **+1.5** | clears bogey by **0 to +3%** |
| **+1.0** | **beats consensus by ≥+1% but misses bogey** — 🟡 the fade zone; positive on fundamentals, dangerous on positioning |
| **+0.5** | beats consensus by **0 to +1%**, or a split where revenue misses bogey and margin clears |
| **0.0** | inline with consensus — **or no guidance given at all by a company that does not guide** (do NOT penalise an absence) |
| **−0.5** | misses consensus by **0 to −2%** |
| **−1.0** | misses consensus by **−2% to −5%** |
| **−1.5** | misses consensus by **>−5%** on the primary line |
| **−2.0** | misses consensus **and** guides margin down **and** withdraws or cuts a previously issued number |

**Additional rules:**
- **A zero-premium bogey is a real bar.** When bogey == consensus (APP Q2 2026: 3Q EBITDA bogey $1.75B and street $1.75B), *anything below street is a genuine miss, not noise.* They guided $1.725B and it was worth −1.0.
- **Grade the margin guide's DIRECTION, not just its level.** WDC F1Q27 guided GM 55–56%, which cleared a 55% bogey — but incremental GM decelerated 84–85% → 80–81% and the market graded the deceleration. CSCO Q1 FY27 guided GM *below* the quarter just reported.
- **A reaffirm is a −1 for tickers whose bull case is scale economics.** CRWV Q1 2026 reaffirmed FY and fell 10%; Q2 raised and rose 19.28%. Check `ticker-profiles.json` for `interpretation: "binary"` on the FY guide line.

---

## 3. FULL-YEAR GUIDANCE (weight 30%) — your second deferred branch

| score | condition |
|---|---|
| **+2.0** | **RAISED** and the new range mid sits **≥+3%** above consensus |
| **+1.5** | RAISED, mid **0 to +3%** above consensus |
| **+1.0** | RAISED but only to roughly consensus; or raised on some metrics and held on others |
| **+0.5** | raised a **non-P&L** metric only (capacity, backlog, units) while holding revenue — NBIS Q2 2026: FY26 reaffirmed on every P&L line, contracted power raised >4GW → 5GW |
| **0.0** | **maintained / reaffirmed** — *and* the neutral score for a company that guides quarterly only and gave no FY figure |
| **−0.5** | reaffirmed where a raise was the expectation, or a metric was **withdrawn** while the number itself held |
| **−1.0** | trimmed one line |
| **−1.5** | cut the range |
| **−2.0** | withdrawn entirely on company-specific weakness (macro/tariff withdrawal scores less punitively, −1.0 to −1.5) |

**★ The withdrawal rule.** Retiring a metric while staying verbally bullish is a **bearish action**, not a neutral reporting change. CSCO Q4 FY26 discontinued its FY27 AI *order* target — the escalating number ($5B → ~$9B → $9.3B delivered) that drove the entire FY26 re-rate — and replaced it with "meaningfully higher." Score it in **Narrative**, and mark FY Guidance down if the withdrawn metric was the one carrying the story.

---

## 4. NARRATIVE (weight 20%) — your third deferred branch, and the least automatable

This is where the money was made this quarter, and it is **call content, not PR content**. Be honest about this in code: if you have only the press release, Narrative should stay `None` with `reason: "PR-only; narrative requires call"`, and the record's `status` should be `SCORED-PR-ONLY`.

| score | condition |
|---|---|
| **+2.0** | a **$-anchored multi-year contracted disclosure** measured against the **current run rate**: >2x = model rebuild. NBIS Q2 2026 — four deals >$1B TCV at $20–25M ACV/MW against a $12M/MW base, short-term at $40–50M/MW |
| **+1.5** | a genuine unmodeled disclosure with a dollar anchor but weaker terms, or a named-customer step-change |
| **+1.0** | a documented negative pattern **breaking**, or a margin inflection proving a contested thesis (CRWV Q2 2026) |
| **+0.5** | a $-anchored disclosure that **also caps the model** — SNDK Q2 2026: $93.9B minimum revenue and $16.5B guarantees, but pricing with **floors AND CEILINGS**, ~80% NBM gross margin (dilutive), and FY27 bit growth **cut** to fund NBM inventory |
| **0.0** | confirms the existing story; nothing added or removed |
| **−0.5** | a vague forward claim with **no dollar anchor** where one was expected |
| **−1.0** | management declines to quantify the thing the market is asking about |
| **−1.5** | **ACTION cap-the-model**: a metric withdrawn, a roadmap line removed, a growth ceiling volunteered, or capex raised with no dollar anchor — while words stay bullish. APP Q2 2026 volunteered "compound at roughly 30% annually" **on a miss quarter** while printing 53%. CSCO Q4 FY26 withdrew the AI order target |
| **−2.0** | the core thesis is broken or a structural negative is newly disclosed |

### The disclosure-quality gates (use these to pick between +2.0, +0.5 and −0.5)

**Disbelieved Re-Rate — 3 gates, needs all three:** NAMED customers · $-anchored BACKLOG · FY+1 revenue BOOKED.
- SNDK Q2 2026: 2 of 3 (customers withheld) → +0.5, not +2.0
- CRWV Q2 2026: 0 of 3 ($25B unattributed) → rose on margin proof, not contract disclosure
- WDC Q4 FY26: 0 of 3 (one signed LTA, "increasing visibility") → −1.5

**SCA Catalyst Override** (overrides a peak-cycle fade): ≥5-year take-or-pay · $100B+ cumulative backlog · ≥10% cash deposits · floor pricing. MU Q3 2026 is the founding case (+17%).

**★ Read $-anchored disclosures for CEILINGS as well as floors.** A ceiling caps upside participation and the market prices both. This is why SNDK's $93.9B produced a −6.81% close.

---

## 5. OVERALL

```
overall = 0.20*currentQuarter + 0.30*nextQGuidance + 0.30*fyGuidance + 0.20*narrative
```

Round to 2dp. `≥ +0.5` Bullish · `≤ −0.5` Bearish · else Neutral. **Steps of 0.5 only.**

⚠️ **7 legacy records use non-half-step scores** — MDB +1.4, DELL +1.9, CRDO +1.6, PANW +1.9, AVGO +1.4, CRWD +0.7, ORCL +1.7. Exclude them from any test that fits the band function.

**`scores.overall` is NEVER modified by positioning.** Compute `positioningAxis.adjustedScore = scores.overall + signModifier` as a separate field. That separation is what makes the adjustment testable.

---

## 6. ★ keyKPIs — SOURCING AND ORDERING. THIS IS THE LOAD-BEARING PIECE.

`dashboard.html → tabActuals()` maps the two arrays **POSITIONALLY**:

```js
var kpiRows=(pre.keyKPIs||[]).map(function(k,i){
  var ak = act.keyKPIs && act.keyKPIs[i] ? act.keyKPIs[i] : {};
```

It iterates `preEarnings.keyKPIs` and looks up `actuals.keyKPIs[i]` **by index**. Consequences:

- **`actuals.keyKPIs` missing** → every row renders blank with a default INLINE verdict, **and the tab still returns a healthy character count.** This silently broke 12 records before a validator caught it.
- **Length mismatch** → rows past the shorter array blank out.
- **Different order** → actuals attach to the WRONG KPI. Worse than blank, because it looks correct.

### The rules

1. **`len(actuals.keyKPIs) == len(preEarnings.keyKPIs)`, always.** `validate_library.py` HARD 2 enforces it. Your scraper must fail loudly rather than write a mismatch.
2. **Build the actuals array by ITERATING `preEarnings.keyKPIs` in its stored order** and resolving each one. Never build it from the parse order of the press release. That is how you filed a Q4 actual into an `FY27 Revenue + EPS Guide` slot.
3. **A KPI you cannot resolve gets a placeholder, not a skip:** `{"actual": null, "vsCons": "N/A", "vsBogey": "—", "vsConsNote": "not found in release"}`. Position is preserved.
4. **★ NEVER populate a forward-period KPI from reported actuals.** Classify each `preEarnings.keyKPIs[i].name` by period first:
   - name contains `FY` **and** `Guid` → `FY_GUIDE`
   - name contains `Guid` or `Outlook` → `NEXTQ_GUIDE`
   - **★ name carries a period token that differs from the record's own `quarter`/`year` → FORWARD, regardless of wording**
   - else → `CURRENT_Q`

   A `CURRENT_Q` parse may only fill a `CURRENT_Q` slot. **Match on the classified period BEFORE matching on the metric word.**

   > ⚠️ **The word test alone is NOT sufficient — added 2026-08-18.** `CSCO-2026Q4` carries a KPI named **`Q1 FY27 Non-GAAP Gross Margin (%) ★★`**. It contains no "Guid" and no "Outlook", so the word test classifies it `CURRENT_Q` — and the hero matcher then binds the graded current-quarter metric to **next quarter's guide slot.** That is the same class of bug as filing a Q4 actual into an `FY27 Revenue + EPS Guide` slot, just harder to see.
   >
   > **The fix: extract any period token from the name and compare it to the record's own quarter.** `CSCO-2026Q4` has `quarter: "Q4 (FY26)"`; the KPI says `Q1 FY27`. Different period → FORWARD. Run this test *before* the word test, because it catches the cases the word test misses.
5. **Verdict strings the renderer recognises:** `BEAT`, `MISS`, `INLINE`, `CRUSH`, `DEMOLISH`, `NUKE-BEAT`, `NUKE-MISS`, `STRONG BEAT`, `MAJOR MISS`, `N/A`, `—`. Anything else silently renders as INLINE.
6. Each entry also carries `pctVsCons`, `pctVsBogey`, `pctVsGuide` for the beat-magnitude analytics. **Suppress any value beyond ±300% and set `pctFlag`** — a units or definition mismatch, not a real delta.

7. **★ THE WITHIN-ROW UNITS TRAP — resolve the row's unit before any arithmetic.** The unit lives in the KPI **name**, and within a single row the bogey and the stored actual can be in **different units**:

   ```
   SNDK-2026Q4 keyKPIs[0]
     name          "FQ4 Revenue ($B) ★"
     bogey          9.5           <- $B
     actual         8965          <- $M
     actualUnit    "$M"           <- now declared explicitly
     expectedUnit  "$B"
     pctVsBogey    -5.6           <- CORRECT, computed after unit resolution
   ```

   Compared raw, `(8965 − 9.5) / 9.5` = **+94,268%** — a 5.6% miss reads as an enormous clear. That does not just corrupt the percentage; **it silently changes the offsetting-flag count, which changes the band.**

   **18 rows across 8 records** carried this disagreement (HOOD, AXTI, KLAC, STX, TER, APP, SNDK and one other). All 18 now carry explicit `actualUnit`, `expectedUnit` and a `unitNote`, and **`validate_library.py` HARD 8** fails on any new occurrence. **Trust the stored `pct*` fields; never recompute from raw fields without resolving the row's unit first.**

### The ORDER itself (how a pre-earnings build sequences them)

Ordered by **what decides the print**, not by income-statement convention:

1. **Current-quarter hero KPI** — the ticker's priority-1 metric
2. Current-quarter revenue
3. Current-quarter EPS or the profitability line
4. Current-quarter margin
5. **Next-quarter guide — the primary line** (usually revenue)
6. **Next-quarter guide — the margin or EPS line**
7. FY guide line, if the company guides annually
8. **Qualitative / unmodeled-disclosure watch item, always LAST**

Mark hero KPIs with `★` in the `name` (`★` = priority 1, `★★` = the trade, `★★★` = the whole thesis). The renderer uses them for emphasis and the analytics use them to select the graded set.

⚠️ **On Windows, prewarm the `★` glyph** — font fallback on it cost 200 ms of first-render lag.

---

## 7. Where bogeys come from — the fallback ladder

Grading is only as good as the expectations column, and **the expected column is as error-prone as the actual column.** An AAPL record once stored Greater China consensus at $21.5B against a real $19.0B and graded a **7.9% beat as the print's biggest bear vector.**

**Authority order:**

1. **Kyle's buyside bogey sheet** (TMTB-style). Canonical. Also carries a **positioning score 0–10 in the header** — same polarity as ours, higher = more crowded. Record it in `positioningAxis.externalScore`; it is the authoritative anchor for positioning components 1–2.
2. **Bloomberg preview** — consensus, implied move, relative performance line.
3. **Published sell-side consensus**, multi-provider. When providers disagree, **store every value and do not resolve**. FQ1 consensus for SNDK had four values ($10.37B / $10.4B / $10.82B / $11.16B) and the sign of the guide delta flipped depending on the choice.
4. **Reconstruct** — set `bogeyReliability: "DERIVED"` and grade primarily vs consensus. One documented method only: apply the ticker's own historical beat-vs-guide cadence to the current guide, and cross-check against published sell-side high-end bars.

**Never grade against a single unverified figure.** Two independent sources or the field is marked `unverified: true` and excluded from `beatMagnitude`.

⚠️ **`revUnit` is null on 7 of 76 records** (`$B` on 58, `$M` on 14). Refusing to grade those rather than inferring is correct. Inferring `$B` from magnitude is the same failure shape as reading a sheet column header of "140%" as implied vol when it was YTD move — which produced a **false confirmation** because the real ATM IV happened to be 137.3%. **Do not infer a unit or a legend from numeric plausibility.**

---

## 8. What the scraper must NOT decide

Score these `None` with a reason rather than guessing. Every one of them mattered more than the arithmetic last quarter:

| judgment call | real case |
|---|---|
| A figure buried in the **cash-flow statement or balance sheet** | SNDK's $1,938M of NBM prepayments and $1,242M contract liabilities — the $93.9B was call-only |
| **GAAP vs company-defined non-GAAP basis** | CBRS GAAP revenue **missed 7.0%** while "core" beat 9.9%. An aggregator published a fake "+8.09% surprise" comparing a GAAP estimate to a core actual. **The tape traded GAAP.** |
| A large **one-off gain** inflating headline EPS | WDC GAAP EPS $8.21 vs a $3.29 street estimate — a $2,050M mark-to-market gain on a retained stake. Comparable was non-GAAP $3.56 |
| **Definitional mismatch** between a consensus line and the reported line | a "cash & equivalents" consensus against a company managing cash across cash + marketable securities |
| **Withdrawn metrics, capped roadmaps, volunteered ceilings** | CSCO's AI order target; APP's 30% compound target |
| **Anything requiring the call** | Narrative, generally |

**A fabricated category score propagates into `beatMagnitude` and `branchAccuracyLog` and corrupts the model's own cross-sectional statistics. A blank is strictly better.** Your instinct here was right.

---

## 9. Mandatory blocks on a post-earnings write

Each one backs a dashboard tab that renders empty without it:

- `actuals.keyKPIs` — index-aligned per §6
- `callCommentary` — `{summary, missedInPR, callOnlyKPIs, incrementalAnalystActivity, keyQuotes, tradingImplication}`. `missedInPR`, `incrementalAnalystActivity`, `keyQuotes` **must be lists**
- `beatMagnitude` — `{revPctVsCons, revPctVsBogey, epsPctVsCons, epsPctVsBogey, score, reactionPct, impliedMove, reactionVsImplied}`
- `stockReaction` — `{afterHours, openPx, closePx, pctChangeNextDay, direction, notes}`. **`pctChangeNextDay` is the NEXT-DAY REGULAR-SESSION CLOSE**, never the print-day move and never the AH settle. Three of four reaction figures supplied from memory last week were one of the wrong two
- `positioningAxis` — carried forward with component 3 locked
- `verification` — `{twoSourceConfirmed, unverified, conflicts, subagentAuditRun, discrepanciesFound, auditedAt}`
- `tradeSummary` — **never fabricate.** Set `tradeSummaryPending: true`
- `sector` — **identical to that ticker's other quarters** or the dashboard splits the company card

## 10. Verification gates — both must pass before a write is accepted

```powershell
py validate_library.py    # must exit 0
node render_test.js           # 0 card / 0 openModal / 0 setTab failures
```

`render_test.js` walks `cardHtml → openModal → setTab` for every record and every tab **that record offers** (pre-earnings and scored records have different tab lists). An earlier harness called `renderTab()` directly and reported "0 failures" while shipping three cards that threw on click. **A test asserting no exception at an inner function is not a test that the feature works.**

Then regenerate `dashboard-standalone.html`: replace the fetch block with `LIBRARY = EMBEDDED_LIBRARY;`, insert `const EMBEDDED_LIBRARY = <library json>;` after the `let LIBRARY = {...}` line, and replace the object literal assigned to `const PROFILES` with `ticker-profiles.json`'s `profiles` object.

---

## 11. Test-pinning guidance

- Fit and pin against the **69 half-step records**; exclude the 7 legacy non-half-step ones.
- Pin `overall` against the weighted average — `validate_library.py` HARD 1 already checks this.
- **Do not fit to any record where `abs(pctVsBogey) >= 300`** — those are unit mismatches carrying a `pctFlag`.
- Highest-value regression cases, because each isolates one rule:
  - **SNDK Q4 FY26** — cq **+1.0** on a +6.9% consensus beat. Pins "bogey, not consensus."
  - **TSLA Q1** — cq **+2.0** on a +0.5% consensus beat. Pins "hero KPI, not revenue."
  - **APP Q2 2026** — cq **−1.5**. Pins the hero-margin cap *and* the own-guide-range failure.
  - **CBRS Q2 2026** — cq **−1.5** despite a +9.9% "core" beat. Pins the GAAP-basis rule.
  - **CSCO Q4 FY26** — nq **+1.0** / fy **+0.5** / narrative **−1.5** on a guide 6–9.5% above consensus. Pins the withdrawal rule.
  - **NBIS Q2 2026** — fy **+0.5** on a full reaffirm with one non-P&L raise. Pins the reaffirm band.


---

## ★ PERSIST THE FLAG COUNT — the band has TWO inputs and only one was ever written down

The Current-Quarter band is a lookup on **(hero-bogey clearance, offsetting-flag count)**. For 76 records
the clearance is recoverable from stored fields but **the flag count is not stored anywhere** — it lived in
the reasoning and evaporated. Consequence: **0 of 69 half-step records can have their band mechanically
verified**, and the regression suite is stuck at 5 hand-verified cases against a 69-record sample.

**Every scored record MUST now write, at the moment of grading:**

```json
"flagAudit": {
  "flagCount": 2,
  "flagsIdentified": ["marginDownYoY", "atOrBelowOwnGuideTop"],
  "notAssessableFromPR": ["segmentDown20Sequential"],
  "derivation": "OBSERVED at grading time",
  "usableForTestPinning": true
}
```

`derivation: "OBSERVED at grading time"` + `usableForTestPinning: true` is the ONLY combination that
admits a record to the pinning set. The `flagAudit` blocks written on 2026-08-18 are all marked
`DERIVED` / `usableForTestPinning: false` — they are a prior for review, not test data.

**Do not backfill by solving for the flag count that reproduces the accepted grade.** That fits the rubric
to itself and produces a suite that cannot fail. Earn the sample forward.

### The 7 flags, and which a PR can actually support

| flag | computable from a PR? |
|---|---|
| `secondHeroMissedBogey` | ✅ from aligned keyKPI verdicts |
| `marginDownYoY` | ✅ if the YoY margin is in the release |
| `atOrBelowOwnGuideTop` | ✅ against the prior guide |
| `gaapBasisGap` | ✅ both bases are in the release |
| `segmentDown20Sequential` | ❌ needs the segment table / the call |
| `growthPriceNotVolume` | ❌ needs mix disclosure |
| `arrRpoLagsOrders` | ❌ needs both series |

**Three of seven require the call.** A PR-only run can assess at most 4 — so a PR-only flag count is a
FLOOR, never a final value. Score `status: "SCORED-PR-ONLY"` and re-run the band after the call.

## Validator HARD 9 — unit-agnostic ratio check

HARD 8 keys off a `($B)`/`($M)` token and fires only when the two sides carry conflicting tokens. It missed
**BE-2026Q1**, where `Total Backlog ($B)` held `0.751` against a `$21.0B` bogey — $751M of **revenue**
mis-parked in the backlog slot (rule 2), `vsBogey: null`, never graded, invisible for months. HARD 9 flags
any expected/actual pair off by **>20x or <0.05x** regardless of how the name is written. Suppress a
legitimate one with `pctFlag: true` and a `unitNote` — never by editing the number to look plausible.
