---
name: scraper-contract
description: The read/write interface between the pre-earnings record and the scraper. Exact JSON paths, verified against live records. The scraper never parses markdown at runtime.
version: 1.0
created: 2026-08-17
---

# Scraper Contract

## The core idea: the pre-earnings record IS the scraper's config file

There is no separate config. When a pre-earnings build runs, it writes a record into `earnings-library.json` with `status: "PRE-EARNINGS"`. That record contains **the consensus, the bogeys, the keyKPI list in its load-bearing order, the positioning axis and the scenario ladder.** At print time the scraper reads it and grades against it.

**Consequence: the scraper is always DOWNSTREAM of the pre-earnings build. It cannot score a name that has no card.** See the no-card rule below — that is a feature, not a limitation.

---

## ⚠️ Record counts move. Verify against the live file, never against this doc.

As of 2026-08-18: **76 records** in `records[]`, **3** in `abandonedRecords[]` (DUOL/OKTA/LULU pre-earnings cards that were never scored — archived so `watch` stops indexing them), **57 profiles**, **7 null `revUnit`**, **69 half-step records** in the pinning set.

If you measure a different number, the library moved — it is a live file. **Trust the file, not this document.** The one thing that must stay in sync is `calibration.json.recordsUsed` versus the count of half-step scored records; if those diverge, regenerate the calibration rather than adjusting the tests.

## Two audiences, two formats. Do not confuse them.

| audience | reads | when |
|---|---|---|
| **The Claude Code agent** | `CLAUDE.md`, `SKILL.md`, `PRE-EARNINGS-BUILD.md`, `LESSONS.md` | while writing code, and while doing a pre-earnings build |
| **The scraper at runtime** | `earnings-library.json`, `ticker-profiles.json`, `calibration.json` | every run |

**The scraper never parses markdown.** All three runtime files are JSON. Everything it needs is already machine-readable:

```python
LIB   = json.load(open("earnings-library.json"))     # records + 7 framework keys
PROF  = json.load(open("ticker-profiles.json"))["profiles"]
CAL   = json.load(open("calibration.json"))          # bands + 69 pinning records
```

---

## STEP 1 — `watch`, pre-market. Build the index.

```python
def build_index(lib, today):
    """Returns {TICKER: record} for every card that reports today and is not yet scored."""
    idx = {}
    for r in lib["records"]:
        if str(r.get("status","")).upper() != "PRE-EARNINGS":  # uppercase — see the status trap
            continue
        if r.get("reportDate") != today:
            continue
        idx[r["ticker"]] = r
    return idx
```

**Pull first.** The pre-earnings card may have been written minutes ago in Cowork. `git pull --rebase` before `watch` or you index a stale library. (`.\sync-before-scoring.ps1` does this and prints today's cards with their KPI count, revUnit, positioning and ladder status.)

⚠️ **The status trap.** Compare `status.upper() == "PRE-EARNINGS"`. A lowercase `'pre-earnings'` once made the dashboard's `isPre` false, and because **`null >= 0` is `true` in JavaScript** the header called `.toFixed()` on null and three cards became un-openable. Be case-insensitive on read; write it uppercase.

---

## STEP 2 — What to pull out of the record. Verified paths.

For each indexed ticker, extract exactly this. Paths confirmed against `DUOL-2026Q1` and `CSCO-2026Q4`.

### The graded set — order is load-bearing

```
record.preEarnings.keyKPIs   → list, ORDER MATTERS, entry shape:
    { "name": "DAU YoY Growth (%) ★",   # ★ / ★★ / ★★★ encode priority
      "consensus": 26,
      "bogey": 28,
      "note": "★★★ HERO KPI #1 — THE swing factor..." }
```

**Store the index with each KPI.** Your actuals array must come back index-aligned 1:1 — the dashboard maps positionally. Iterate this list; never build from parse order.

### Headline expectations

```
record.preEarnings.revConsensus      float
record.preEarnings.revBogey          float
record.preEarnings.revUnit           "$B" | "$M" | null   ← refuse to grade if null
record.preEarnings.epsConsensus      float
record.preEarnings.epsBogey          float
record.preEarnings.epsUnit           "$"
record.preEarnings.impliedMove       str, e.g. "±15.6% (~±$17)"   ← parse the leading number
```

⚠️ **`revUnit` is null on 7 of 76 records.** Refusing to grade those is correct. Do not infer `$B` from magnitude — that is the same failure shape as reading a sheet column header of "140%" as implied vol when it was YTD move, which produced a false confirmation because the real IV happened to be 137.3%.

### Forward expectations — these feed categories 2 and 3

```
record.preEarnings.nextQGuideExpected   str
record.preEarnings.fyGuideExpected      str
record.preEarnings.q2Expectations       dict  (schema varies by ticker — read defensively)
record.preEarnings.fyExpectations       dict  (      "                              )
```

⚠️ These are **prose or loosely-shaped dicts on older records.** Newer records carry numeric mids. Where you cannot parse a numeric midpoint, defer that category rather than guessing.

### Positioning

```
record.positioningAxis.components        dict of the 6 named components, int -2..+2
record.positioningAxis.score10           float   (6/6 confidence)
record.positioningAxis.score10Estimate   float   (partial — note the different key)
record.positioningAxis.signModifier      float
record.positioningAxis.confidence        "HIGH" | "LOW" | "PRE-PRINT" | "LOCKED (4:00 PM)" | "UNSCORED"
record.positioningAxis.componentsScored  "1/6" ... "6/6"
record.positioningAxis.externalScore     {value, source, provider} | null
```

⚠️ **`score10` vs `score10Estimate` are different keys.** Read `score10` first, fall back to `score10Estimate`, and surface the `confidence` on the card so a 1/6 estimate is never displayed as though it were 6/6.

### The ladder

```
record.scenarioLadder    list of branches:
    { "branch", "trigger", "positioningContext",
      "expectedReaction", "tradeType", "stayForCall",
      "overnightEligible", "basedOn" }
```

⚠️ **Only 3 of 76 records currently have a ladder.** When absent, show the required-surprise tier from `scenarioLadderFramework` instead and label it as a tier, not a matched branch.

### The profile — what to grade

```
PROF[ticker].heroKPIs   → [{ "name", "priority", "appliesTo", "beatBand", "missBand", "unit",
                             "notes", "interpretation"? }]
PROF[ticker].needsReview  bool   ← 34 profiles are DERIVED (32 back-derived + AEHR/IBM authored). Surface this on the card.
```

Take the `priority == 1` entry whose `appliesTo == "currentQuarter"`. **That metric, not revenue, is what Current Quarter grades on.**

### Context worth showing on the card

```
record.stockContext.priceAtReport      float
record.stockContext.ytdPerformance     str
record.stockContext.analystSentiment   str
record.priorQuarter.{quarter,reportDate,revenue,eps,stockReaction,note}
record.preEarnings.whatMattersMost     str
record.preEarnings.whatWins / whatLoses
record.marketRegime.regime             "RISK-ON" | "CHOPPY" | "RISK-OFF"
```

`priorQuarter.stockReaction` is the one-line history — DUOL's reads `"-24% AH on Feb 26"`. Put it on the card.

---

## STEP 3 — ★ THE NO-CARD RULE

```python
if ticker not in index:
    alert(f"{ticker}: NO PRE-EARNINGS CARD — CANNOT SCORE")
    return  # do NOT fall back to revenue. Do NOT grade.
```

**Never fall back to revenue-based grading.** `SKILL.md` §1 proves it cannot reproduce the accepted grades — SNDK beat consensus 6.9% and scored +1.0, TSLA beat 0.5% and scored +2.0. A confidently wrong grade is worse than a blank, because it propagates into `beatMagnitude` and `branchAccuracyLog` and corrupts the model's own cross-sectional statistics.

The correct output for an unprepared name is: **extract and display the raw numbers, grade nothing, alert that no card exists.** That is still useful — it is the coverage the scraper exists to provide.

---

## STEP 4 — Grade, then write back

Apply `SKILL.md` §1–5. Import the bands from `calibration.json` rather than hardcoding them.

Fields the scraper writes:

```
record.status                = "SCORED-PR-ONLY"      # never SCORED-POST-CALL from a PR alone
record.actuals               = {...}                  # top-level parsed figures
record.actuals.keyKPIs       = [...]                  # INDEX-ALIGNED 1:1, same length, same order
record.scores.currentQuarter = float
record.scores.nextQGuidance  = float | None + reason
record.scores.fyGuidance     = float | None + reason
record.scores.narrative      = None  + "PR-only; narrative requires the call"
record.scores.overall        = weighted avg, or None if any category is None
record.beatMagnitude         = {revPctVsCons, revPctVsBogey, epsPctVsCons, epsPctVsBogey,
                                score, reactionPct: None, impliedMove}
record.branchMatched         = {branch, triggerHit, expectedReaction, actualReaction: None}
record.tradeSummaryPending   = True
record.updatedAt             = today
```

`actuals.keyKPIs` entry shape — copy this exactly:

```json
{"actual": 17252, "vsCons": "BEAT", "vsBogey": "N/A",
 "pctVsCons": 2.5, "pctVsBogey": null,
 "vsConsNote": "🟢 +2.5% vs $16.82-16.83B, above its own guide high end; +18% YoY",
 "vsBogeyNote": "🟢 clean beat"}
```

Verdict strings the renderer recognises: `BEAT` `MISS` `INLINE` `CRUSH` `DEMOLISH` `NUKE-BEAT` `NUKE-MISS` `STRONG BEAT` `MAJOR MISS` `N/A` `—`. **Anything else silently renders as INLINE.** Unresolved KPIs get `{"actual": null, "vsCons": "N/A", "vsBogey": "—", "vsConsNote": "not found in release"}` — a placeholder, never a skip, so position is preserved.

Suppress any `pct*` beyond ±300% and set `pctFlag` — that is a units or definition mismatch, not a real delta.

**Do not write to `earnings-library.json` until both gates pass:**

```powershell
py validate_library.py    # must exit 0
node render_test.js           # 0 card / 0 openModal / 0 setTab failures
```

Safer pattern: write a **sidecar** (`pending/{id}.json`), run the gates against a merged copy, and only merge into the library on green.

---

## The daily sequence

| when | who | what |
|---|---|---|
| **T−1 / morning of** | Kyle + Cowork | Pre-earnings build → record with `status: PRE-EARNINGS`, keyKPIs ordered, bogeys, positioning 4/6, ladder. **Writes the ticker profile.** Commit + push |
| **pre-market** | scraper | `git pull` → `watch` → load 2.9 MB library, index today's cards (19 ms) |
| **4:00 PM** | Kyle + Cowork | **Lock positioning component 3** — print-day move ÷ implied move, from the OFFICIAL close, two sources. If it is +2, downgrade every bullish branch one notch |
| **~4:02–4:05 PM** | scraper | Print crosses → match ticker → extract → grade 3 categories → match branch → pop the card. Narrative deferred |
| **4:30–5:00 PM** | Kyle + Cowork | Call → narrative score, `callCommentary`, PR-vs-call delta → persist, validate, regenerate, push |

**Component 3 is the one input the scraper cannot self-serve** — it needs the official print-day close, and per `LESSONS.md` A2 an intraday snapshot is not acceptable. Two locks were set from intraday prints that reversed by the close; one had the sign inverted and poisoned the whole read.

---

## What the scraper must never decide

Defer these to the call and to Cowork. Every one mattered more than the arithmetic last quarter:

| judgment | founding case |
|---|---|
| A figure buried in the **cash-flow statement or balance sheet** | SNDK's $93.9B of contracted minimum revenue — call-only, while $1,938M of prepayments sat in the cash-flow statement |
| **GAAP vs a company-defined non-GAAP basis** | CBRS GAAP revenue **missed 7.0%** while "core" beat 9.9%. An aggregator published a fake "+8.09% surprise" comparing a GAAP estimate to a core actual. **The tape traded GAAP** |
| A large **one-off gain** in headline EPS | WDC GAAP $8.21 vs a $3.29 street estimate — a $2,050M mark-to-market gain |
| **Withdrawn metrics** | CSCO retired its FY27 AI order target — the number that drove the entire re-rate |
| **Narrative, always** | it is call content by nature |

---

## Minimum viable read — copy this

```python
import json, datetime

LIB  = json.load(open("earnings-library.json",  encoding="utf-8"))
PROF = json.load(open("ticker-profiles.json",   encoding="utf-8"))["profiles"]
CAL  = json.load(open("calibration.json",       encoding="utf-8"))

today = datetime.date.today().isoformat()
index = {r["ticker"]: r for r in LIB["records"]
         if str(r.get("status","")).upper() == "PRE-EARNINGS"
         and r.get("reportDate") == today}

def prepare(ticker):
    rec = index.get(ticker)
    if rec is None:
        return {"error": "NO_CARD", "message": f"{ticker}: no pre-earnings card — cannot score"}
    pe   = rec.get("preEarnings") or {}
    prof = PROF.get(ticker)
    if prof is None:
        return {"error": "NO_PROFILE", "message": f"{ticker}: no hero-KPI profile — would fall back to revenue"}

    heroes = [h for h in prof["heroKPIs"]
              if h.get("priority") == 1 and h.get("appliesTo") == "currentQuarter"]
    pa = rec.get("positioningAxis") or {}

    return {
        "record_id":  rec["id"],
        "kpis":       [(i, k["name"], k.get("consensus"), k.get("bogey"))
                       for i, k in enumerate(pe.get("keyKPIs") or [])],   # ORDER PRESERVED
        "revUnit":    pe.get("revUnit"),           # None -> refuse to grade
        "impliedMove": pe.get("impliedMove"),
        "hero":       heroes[0]["name"] if heroes else None,
        "posn":       pa.get("score10", pa.get("score10Estimate")),
        "posn_conf":  pa.get("confidence"),
        "ladder":     rec.get("scenarioLadder") or [],
        "needsReview": bool(prof.get("needsReview")),
        "prior":      rec.get("priorQuarter"),
        "watch":      pe.get("whatMattersMost"),
    }
```

Frameworks are read from the library at runtime — **never duplicated into code** — so a framework revision propagates without a code change:

```python
POSN   = LIB["positioningFramework"]
LADDER = LIB["scenarioLadderFramework"]
MAGN   = LIB["beatMagnitudePatterns"]
OVN    = LIB["overnightHoldFramework"]
REGIME = LIB["regimeFramework"]
ACC    = LIB["branchAccuracyLog"]
```

---

## One calibration warning to surface in the UI

The model's own scorecard: **direction 3 of 3, trigger identification 3 of 3, magnitude inside range 0 of 3** on forward-written branches, and 3 of 4 / 0 of 4 on the backfilled week. Both de-risked cases were under-sized and both crowded cases were under-sized in the other direction.

**Trigger logic works; magnitude calibration does not.** Do not present an `expectedReaction` range as high-confidence. Label it as a framing range with its `basedOn` n-count visible — most matrix cells are n=1 to 3.

---

# ADDENDUM 2026-08-20 — the PR-only decision gate

## The question the contract never answered

The scraper reads a press release. It cannot know Narrative. So what does it output?

Previously: nothing. `narrative = None` meant `overall` was never emitted, and a run produced
three category scores with no verdict. Correct, and useless at 4:01 PM.

## What was tested and REJECTED

Renormalizing the three known categories to 25 / 37.5 / 37.5. It **flips 6 of 76 labels**, and the
flips are in the worst possible direction:

| record | 4-cat | 3-cat renormalized | actual reaction |
|---|---|---|---|
| **CSCO-2026Q4** | +0.35 Neutral | **+0.81 BULLISH** | **−8.40%** |
| **RDDT-2026Q2** | −0.00 Neutral | **+0.50 BULLISH** | **−12.00%** |

Narrative is where *"cleared revenue and EPS by 6–9.5%, market graded gross margin"* lives.
Rescaling the remainder deletes precisely the signal that mattered. **Do not renormalize.**

## What to output instead — the bracket

Narrative has weight 0.20 and is bounded [−2, +2]. It can move `overall` by **at most ±0.40**.

```
partial = 0.20*CQ + 0.30*NextQ + 0.30*FY
overall ∈ [partial − 0.40, partial + 0.40]        ← exact, not estimated
```

Containment verified on all 76 records. It is arithmetically guaranteed — **a containment failure is
a genuine bug, so assert it on every run.**

| band | test | n | outcome |
|---|---|---|---|
| `DECISIVE_BULLISH` | `partial − 0.40 ≥ +0.50` | 29 | 83% up, mean **+9.79%** |
| `DECISIVE_BEARISH` | `partial + 0.40 ≤ −0.50` | 1 | **n=1 — no base rate. Do not trade it as one.** |
| `STAY_FOR_CALL` | bracket straddles | 27 | **78% DOWN, mean −3.80%** |

Reference implementation: **`pr_only_gate.py`**, loading its bands from
`earnings-library.json → prOnlyGateFramework`. Never hardcode the table.

## ★ The finding that matters most

**`STAY_FOR_CALL` is not "wait and see" — it is a 78% short-side signal.** When the PR alone cannot
settle the read, the tape resolves it down 21 times in 27. Ambiguity is bearish, because clean prints
are unambiguous.

**But the 22% that go up, go up violently:** NBIS +34.14, QCOM +15.00, AMZN +10.00, NOW +4.80,
TSLA +4.00 — mean of the up-cases ≈ +13.6% against a mean down-case near −7%. A naked short into the
call carries unbounded tail risk. **Report the base rate and the tail together, always.**

## ★ Why the tail is not yet separable — and the field that fixes it

The `$`-anchor hypothesis (SNDK's $93.9B contracted minimum vs WDC's "increasing visibility",
same night, same sector, both ~−5.4% into the print, −6.81% vs −13.03%) **could not be tested.**
A dollars-in-billions regex fires on **26 of 26** records, because every release contains a revenue
figure in billions. Zero discriminating power. `asymmetricEventFlag` is populated on 3 of 27.

A `$` figure in the revenue line and a `$` figure in a multi-year take-or-pay commitment are
**indistinguishable to text search.** They must be captured as structured data at scoring time — see
`earnings-library.json → forwardCommitmentSchema`. Twelve records (the full STAY_FOR_CALL tail plus
both halves of the SNDK/WDC pair) would constitute the whole experiment.

## Two things the decisive-bullish failures are NOT evidence for

`NOW −12.00`, `PLTR −6.93`, `ALAB ×2`, `MRVL −2.00`, `CRM +0.00` are all good-print/bad-tape.
Positioning is the obvious suspect. **Only 6 of those 29 records carry a positioning score, so it is
untested — do not assert it, and do not let the scraper apply a positioning modifier it cannot
validate.** Raising positioning coverage above ~20/29 in that cohort is what would settle it.

## Verified JSON paths (corrected)

```
reaction     : r.stockReaction.pctChangeNextDay      ← NESTED. fallback r.beatMagnitude.reactionPct
scores       : r.scores.{currentQuarter,nextQGuidance,fyGuidance,narrative,overall}
weights      : CQ 0.20 · NextQ 0.30 · FY 0.30 · Narrative 0.20
               (reproduces the stored overall EXACTLY on all 76 records — 0 discrepancies)
flag audit   : r.flagAudit.{flagCount,flagsIdentified,notAssessableFromPR,usableForTestPinning}
```
