# HANDOFF — paste this into VS Code

You are finishing an earnings-scoring scraper for Kyle, an intraday news trader. The complete model already exists on disk in this repo. **Read these five files before writing any code:**

```
CLAUDE.md                                    ← project rules, auto-loaded
skills/earnings-scoring/SKILL.md             ← the scoring rubric, all four categories
skills/earnings-scoring/calibration.json     ← machine-readable bands + 69 pinning records
skills/earnings-scoring/PRE-EARNINGS-BUILD.md ← how a card is built (context for what you're reading)
skills/earnings-scoring/LESSONS.md           ← ~20 earned rules with founding cases
skills/earnings-scoring/SCRAPER-CONTRACT.md  ← ★ THE INTERFACE SPEC — exact JSON paths, verified
```

`SCRAPER-CONTRACT.md` is the one you implement against. Everything below is the summary; that file has the verified field paths.

---

## THE ARCHITECTURE

**The pre-earnings record IS the config file.** There is no separate config. Each morning, Kyle and Claude (in the desktop app) write a record into `earnings-library.json` with `status: "PRE-EARNINGS"` containing the consensus, the bogeys, the keyKPI list **in a load-bearing order**, the positioning axis and a scenario ladder. That afternoon the scraper reads it and grades against it.

**The scraper is always downstream of that build. It cannot score a name with no card — and must not try.**

| when | who | what |
|---|---|---|
| morning | Kyle + Claude desktop | card written to `earnings-library.json`, profile written to `ticker-profiles.json` |
| 4:00 PM | Kyle + Claude desktop | lock positioning component 3 from the **official** print-day close |
| ~4:05 PM | **scraper, alone** | extract → grade Current Quarter → deltas → match branch → pop the card |
| 4:30–5:00 PM | Kyle + Claude desktop | call → narrative score, `callCommentary`, persist, both gates, push |

## RUNTIME INPUTS — three JSON files, never markdown

```python
LIB  = json.load(open("earnings-library.json",  encoding="utf-8"))  # 76 records + 9 framework keys
PROF = json.load(open("ticker-profiles.json",   encoding="utf-8"))["profiles"]  # 57 tickers
CAL  = json.load(open("skills/earnings-scoring/calibration.json", encoding="utf-8"))
```

Read the frameworks out of the library at runtime — **never copy them into code**, so a revision propagates without a code change:

```python
POSN, LADDER, MAGN = LIB["positioningFramework"], LIB["scenarioLadderFramework"], LIB["beatMagnitudePatterns"]
OVN, REGIME, ACC   = LIB["overnightHoldFramework"], LIB["regimeFramework"], LIB["branchAccuracyLog"]
```

---

## ⛔ THE FINDING THAT INVALIDATES A CONSENSUS-DELTA BAND FUNCTION

`score = f(rev_pct_vs_consensus, eps_pct_vs_consensus)` **cannot reproduce the accepted grades.** Proof from the library:

| record | grade | rev vs **consensus** | rev vs **bogey** |
|---|---|---|---|
| SNDK Q4 FY26 | **+1.0** | **+6.9%** | −5.6% |
| ALAB Q1 | **+1.0** | **+5.5%** | −3.6% |
| CRWV Q2 | **+1.5** | **+0.6%** | n/a |
| MRVL Q1 FY27 | **+1.5** | **+0.3%** | −3.3% |
| TSLA Q1 | **+2.0** | **+0.5%** | −0.5% |

**The discriminator is clearance of the BOGEY, applied to the ticker's PRIORITY-1 HERO KPI from `ticker-profiles.json` — not revenue.** Empirical medians by band: +2.0 → **+1.32%** vs bogey · +1.5 → **+0.06%** · +1.0 → **−0.73%** · +0.5 → **−0.74%**.

Note +0.5 and +1.0 share the same median. Bogey clearance alone does not separate them — **an offsetting-flag count does**, so the rubric is two-dimensional.

---

## SCORING — implement in this order

### Step 1: select the graded metric
```python
prof   = PROF.get(ticker)                    # if None -> NO_PROFILE, refuse to grade
heroes = [h for h in prof["heroKPIs"]
          if h.get("priority") == 1 and h.get("appliesTo") == "currentQuarter"]
```
**That metric, not revenue, is what Current Quarter grades on.** Respect `interpretation: "reverse-polarity"` — META capex and ANET deferred revenue score inverted.

### Step 2: THE HARD CAP — apply BEFORE the band lookup
**A priority-1 hero KPI that MISSES caps Current Quarter at 0.0, regardless of revenue or EPS beats.**
Founding cases: APP Q2 2026 (margin missed → capped, then −1.5 on the own-guide failure); CBRS Q2 2026 (hardware −26% vs estimate → −1.5 despite a +9.9% "core" revenue beat).

### Step 3: count offsetting flags — each is one flag
- a second priority-1 hero KPI missed its bogey
- gross or operating margin declined **year-over-year**
- a segment declined **>20% sequentially**
- growth was majority **price rather than volume**
- ARR/RPO growth lags order or revenue growth by **>20pp**
- the reported figure landed **at or below the company's own guide top**
- a **GAAP vs non-GAAP basis gap** materially changes the sign

### Step 4: Current Quarter band
| score | condition |
|---|---|
| **+2.0** | hero clears bogey **≥+2%**, **0 flags** |
| **+1.5** | clears bogey **0 to +2%**, **≤1 flag** — or ≥+2% with exactly 1 flag |
| **+1.0** | **beats consensus, misses bogey by 0 to −5%**, 1–2 flags |
| **+0.5** | beats consensus, misses bogey, **≥3 flags** |
| **0.0** | inline **or hero KPI missed (hard cap)** |
| **−0.5** | modest consensus miss on one graded line |
| **−1.0** | consensus miss on hero KPI **and** one other line |
| **−1.5** | multi-line consensus miss **AND** failure of the company's **own** guidance range |
| **−2.0** | hero major miss + own-guide failure + margin collapse |

### Step 5: Next-Q Guidance (weight 30%)
Grade the **guide midpoint** vs bogey, then consensus.
`+2.0` ≥+3% vs bogey · `+1.5` 0 to +3% · `+1.0` **beats consensus, misses bogey** (🟡 fade zone) · `+0.5` +0 to +1% vs consensus · `0.0` inline, **or no guidance from a company that does not guide — do NOT penalise an absence** · `−0.5` −0 to −2% · `−1.0` −2 to −5% · `−1.5` >−5% · `−2.0` miss + margin down + a withdrawn number.

- **A zero-premium bogey is a real bar.** APP Q2: bogey $1.75B *equalled* street $1.75B; they guided $1.725B and it was worth −1.0.
- **Grade the margin guide's DIRECTION, not its level.** CSCO guided Q1 GM *below* the quarter just reported.

### Step 6: FY Guidance (weight 30%)
`+2.0` RAISED, mid ≥+3% vs consensus · `+1.5` raised 0 to +3% · `+1.0` raised to roughly consensus · `+0.5` **raised a non-P&L metric only** (NBIS: FY26 P&L reaffirmed, contracted power raised >4GW→5GW) · `0.0` maintained, **or none given by a quarterly guider** · `−0.5` reaffirmed where a raise was expected, **or a metric withdrawn** · `−1.0` trimmed · `−1.5` cut · `−2.0` withdrawn on company-specific weakness.

### Step 7: Narrative (weight 20%) — ★ ALWAYS DEFER ON A PR
```python
scores["narrative"] = None
reason = "PR-only; narrative requires the call"
record["status"] = "SCORED-PR-ONLY"
```
**This is permanent, not a stopgap.** Narrative is call content. Last quarter's decisive items were all call- or footnote-only: SNDK's $93.9B contracted minimum revenue, CSCO's withdrawn AI-order target, WDC's refusal to put a dollar figure on "increasing visibility."

### Step 8: Overall
```python
overall = 0.20*cq + 0.30*nq + 0.30*fy + 0.20*narr   # None if ANY category is None
```
Steps of **0.5 only**. `≥+0.5` Bullish · `≤−0.5` Bearish · else Neutral.
**`scores.overall` is NEVER modified by positioning** — `positioningAxis.adjustedScore = overall + signModifier` is a separate field.

---

## keyKPIs — THE LOAD-BEARING PIECE

`dashboard.html → tabActuals()` maps the two arrays **POSITIONALLY**:
```js
var kpiRows=(pre.keyKPIs||[]).map(function(k,i){ var ak = act.keyKPIs && act.keyKPIs[i] ? act.keyKPIs[i] : {};
```

1. **`len(actuals.keyKPIs) == len(preEarnings.keyKPIs)`, always.** A missing array renders blank rows with default INLINE verdicts **and still returns a healthy character count** — this silently broke 12 records.
2. **Build the actuals array by ITERATING `preEarnings.keyKPIs` in its stored order.** Never from the parse order of the press release.
3. **Unresolved KPI → placeholder, never a skip:** `{"actual": null, "vsCons": "N/A", "vsBogey": "—", "vsConsNote": "not found in release"}`.
4. **★ NEVER populate a forward-period KPI from reported actuals.** Classify the slot's period first, then match the metric word:
   - name has `FY` **and** `Guid` → `FY_GUIDE`
   - name has `Guid` or `Outlook` → `NEXTQ_GUIDE`
   - else → `CURRENT_Q`
   A `CURRENT_Q` parse may **only** fill a `CURRENT_Q` slot.
5. **Verdict strings the renderer recognises:** `BEAT` `MISS` `INLINE` `CRUSH` `DEMOLISH` `NUKE-BEAT` `NUKE-MISS` `STRONG BEAT` `MAJOR MISS` `N/A` `—`. **Anything else silently renders as INLINE.**
6. **Suppress any `pct*` beyond ±300% and set `pctFlag`** — a units or definition mismatch, not a real delta.

Entry shape to write:
```json
{"actual": 17252, "vsCons": "BEAT", "vsBogey": "N/A",
 "pctVsCons": 2.5, "pctVsBogey": null,
 "vsConsNote": "🟢 +2.5% vs $16.82-16.83B, above its own guide high end; +18% YoY",
 "vsBogeyNote": "🟢 clean beat"}
```

---

## THREE TRAPS IN THE DATA

**1. `score10` vs `score10Estimate` are different keys.** Read `score10` first, fall back to `score10Estimate`, and **surface `confidence` on the card** so a 1/6 estimate never displays as though it were 6/6.

**2. Compare `status.upper()`.** A lowercase `'pre-earnings'` made the dashboard's `isPre` false, and because **`null >= 0` is `true` in JavaScript** the header called `.toFixed()` on null and three cards became un-openable.

**3. `revUnit` is null on 7 records** (`$B` on 58, `$M` on 14). **Refuse to grade those.** Do not infer `$B` from magnitude — that is the same failure shape as reading a sheet column header of "140%" as implied vol when it was YTD move, which produced a *false confirmation* because the real IV happened to be 137.3%.

---

## ★ THE NO-CARD RULE

```python
if ticker not in index:
    alert(f"{ticker}: NO PRE-EARNINGS CARD — CANNOT SCORE")
    return  # do NOT fall back to revenue. Do NOT grade.
```

Extract and **display** the raw numbers, grade nothing, alert. That is still valuable — it is the coverage the scraper exists to provide. A confidently wrong grade is worse than a blank because it propagates into `beatMagnitude` and `branchAccuracyLog` and corrupts the model's own cross-sectional statistics.

Same for a missing profile → `NO_PROFILE`, refuse to grade.

---

## WHAT THE SCRAPER MUST NEVER DECIDE

| judgment | founding case |
|---|---|
| a figure buried in the **cash-flow statement or balance sheet** | SNDK's $93.9B — call-only, while $1,938M of prepayments sat in the cash-flow statement |
| **GAAP vs a company-defined non-GAAP basis** | CBRS GAAP revenue **missed 7.0%** while "core" beat 9.9%. An aggregator published a fake "+8.09% surprise" comparing a GAAP estimate to a core actual. **The tape traded GAAP** |
| a large **one-off gain** in headline EPS | WDC GAAP $8.21 vs a $3.29 street estimate — a $2,050M mark-to-market gain. Comparable was non-GAAP $3.56 |
| **withdrawn metrics / volunteered ceilings** | CSCO retired its FY27 AI order target; APP volunteered a 30% growth cap on a miss quarter |
| **narrative, always** | call content by nature |

---

## WRITE-BACK AND GATES

Fields the scraper writes: `status="SCORED-PR-ONLY"`, `actuals`, `actuals.keyKPIs` (index-aligned), `scores.*` (narrative `None`), `beatMagnitude`, `branchMatched`, `tradeSummaryPending=True`, `updatedAt`.

**Do not write into `earnings-library.json` until both gates pass:**
```powershell
py validate_library.py    # must exit 0 — 7 HARD checks
node render_test.js           # 0 card / 0 openModal / 0 setTab failures
```
Safer: write a sidecar `pending/{id}.json`, run the gates against a merged copy, merge only on green. Then `.\score-and-publish.ps1 "message"` — it runs both gates, regenerates the standalone, and refuses to push on failure.

⚠️ **`render_test.js` walks `cardHtml → openModal → setTab`.** An earlier harness called `renderTab()` directly, reported "0 failures", and shipped three cards that threw on click. **A test asserting no exception at an inner function is not a test that the feature works.**

---

## IMPLEMENTATION TASKS

1. **Replace `_CQ_BANDS`** with the two-dimensional rule above — bogey clearance on the hero KPI × offsetting-flag count. Import bands from `calibration.json`; do not hardcode.
2. **Implement the hard cap** before the band lookup.
3. **Fill `nextQGuidance` and `fyGuidance`** per Steps 5–6. Where a numeric guide midpoint cannot be parsed, defer that category with a reason rather than guessing — `nextQGuideExpected` is **prose** on older records.
4. **Leave `narrative` deferred permanently.** Keep the `PARTIAL` banner for that one category; drop `PROVISIONAL CALIBRATION` once the bands are in.
5. **Add regression tests** pinning against `calibration.json`'s 69 half-step records. Exclude the 7 legacy non-half-step grades (MDB +1.4, DELL +1.9, CRDO +1.6, PANW +1.9, AVGO +1.4, CRWD +0.7, ORCL +1.7).

**Six named regression cases, each isolating one rule:**

| record | pins |
|---|---|
| **SNDK-2026Q4** cq **+1.0** | bogey, not consensus — a +6.9% consensus beat scored only +1.0 |
| **TSLA-2026Q1** cq **+2.0** | hero KPI, not revenue — a +0.5% consensus beat scored +2.0 |
| **APP-2026Q2** cq **−1.5** | the hero-margin hard cap **and** the own-guide-range failure |
| **CBRS-2026Q2** cq **−1.5** | the GAAP-basis rule — a +9.9% "core" beat does not rescue a 7.0% GAAP miss |
| **CSCO-2026Q4** nq **+1.0** / fy **+0.5** / narr **−1.5** | the withdrawal rule — a guide 6–9.5% above consensus still scores narrative −1.5 |
| **NBIS-2026Q2** fy **+0.5** | the reaffirm band — a full P&L reaffirm with one non-P&L raise is +0.5, not +1.0 |

---

## ONE CALIBRATION WARNING TO SURFACE IN THE UI

The model's own scorecard: **direction 3 of 3, trigger identification 3 of 3, magnitude inside range 0 of 3** on forward-written branches; 3 of 4 and 0 of 4 on the backfilled week. Both de-risked cases were under-sized and both crowded cases were under-sized in the other direction.

**Trigger logic works; magnitude calibration does not.** Never present an `expectedReaction` range as high-confidence — label it a framing range and show its `basedOn` n-count. Most matrix cells are n=1 to 3.
