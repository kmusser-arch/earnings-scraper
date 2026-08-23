# earnings Model — project instructions

You are working on Kyle's earnings evaluation model. He is an **intraday news trader**: lead with the answer, no preamble, no disclaimers, structured output over prose.

## Read these before doing anything

| file | what it is |
|---|---|
| `skills/earnings-scoring/SKILL.md` | **the scoring rubric** — four categories, −2..+2 bands, keyKPI ordering, bogey ladder, verification gates |
| `skills/earnings-scoring/calibration.json` | machine-readable bands + **69 half-step records** for test pinning + 6 regression cases |
| `skills/earnings-scoring/PRE-EARNINGS-BUILD.md` | **how a print gets prepared** — hero-KPI selection, positioning axis, scenario ladder |
| `skills/earnings-scoring/LESSONS.md` | **~20 earned rules** with founding cases. These are the edge. Apply them; do not re-derive them |
| `earnings-library.json` | 76 records **+ ~102 KB of frameworks as top-level keys** — read them at runtime, never duplicate into code |
| `ticker-profiles.json` | **57 hero-KPI profiles — one per ticker in the library.** **Determines what gets graded for each ticker** |

## The frameworks live in the data, not in code

`positioningFramework` · `scenarioLadderFramework` · `overnightHoldFramework` · `beatMagnitudePatterns` · `branchAccuracyLog` · `regimeFramework` · `schemaNotes` are all top-level keys in `earnings-library.json`. Load them at runtime so a framework revision propagates without a code change.

## Two modes

**PRE-EARNINGS (ahead of the print — completeness wins).** Follow `PRE-EARNINGS-BUILD.md`. Output must include the numeric positioning axis and a 4–6 branch if/then ladder with numeric triggers. A pre-earnings deliverable without both is incomplete.

**POST-EARNINGS (print is out — speed wins).** Full scorecard is the **first** output with **zero tool calls before it**. Persist, validate, regenerate and push only after the read is delivered.

## ★ The hero-KPI profile is an OUTPUT of the pre-earnings build, not a lookup

Every pre-earnings build **must write or update `ticker-profiles.json`** for that ticker. It is not optional and it is not a separate task — identifying the hero KPI *is* the build.

**Why this is enforced:** 34 of 57 tickers had a scored record but no profile, because the builds identified the hero KPIs (marked `★★★` in `preEarnings.keyKPIs`) and never persisted them. Without a profile the scorer falls back to **revenue**, and revenue-based grading provably cannot reproduce the accepted grades — SNDK beat consensus by 6.9% and scored **+1.0**; TSLA beat by 0.5% and scored **+2.0**.

`validate_library.py` **HARD 7** now fails when a ticker has a record but no profile. 32 profiles were back-derived from `★` markers on 2026-08-17 and carry `needsReview: true` — **confirm them at that ticker's next pre-earnings build.**

## Non-negotiables

0. **Write the ticker profile as part of every pre-earnings build.** See above.
1. **`actuals.keyKPIs` must be index-aligned 1:1 with `preEarnings.keyKPIs`.** The dashboard maps them positionally. A mismatch silently blanks the grid *while still rendering*. Build the actuals array by iterating the pre-earnings order; never from parse order.
2. **Never populate a forward-period KPI from reported actuals.** Classify the slot's period before matching the metric word.
3. **A priority-1 hero KPI miss caps Current Quarter at 0.0**, regardless of revenue or EPS beats. Apply before the band lookup.
4. **`scores.overall` is never modified by positioning.** `positioningAxis.adjustedScore = overall + signModifier` is a separate field.
5. **Grade against bogey, street and the company's own guide as three columns.** 🟢 clears bogey · 🟡 beats street misses bogey = FADE ZONE · 🔴 misses street.
6. **`pctChangeNextDay` is the next-day regular-session close.** Never the print-day move, never the after-hours settle.
7. **Never fabricate a category score.** `None` with a stated reason. A fabricated score propagates into `beatMagnitude` and `branchAccuracyLog` and corrupts the model's own statistics.
8. **Never fabricate `tradeSummary`.** Set `tradeSummaryPending: true`.
9. **Two independent sources or the field is `unverified: true`** and excluded from `beatMagnitude`. **The expected column is as error-prone as the actual column.**
10. **`sector` must match that ticker's other quarters** or the dashboard splits the company card.

## Verification — both gates, every write

```powershell
py validate_library.py    # must exit 0
node render_test.js       # 0 card / 0 openModal / 0 setTab failures
py regen_standalone.py    # rebuild the self-contained dashboard
```

⚠️ **On this machine Python is `py`, not `python`** — the Windows launcher. All `.ps1` scripts probe `py` → `python` → `python3` and use whichever answers.

`render_test.js` walks `cardHtml → openModal → setTab` for every record and every tab **that record offers**. An earlier harness called `renderTab()` directly, reported "0 failures", and shipped three cards that threw on click. **A test asserting no exception at an inner function is not a test that the feature works.**

Then regenerate `dashboard-standalone.html`: replace the fetch block with `LIBRARY = EMBEDDED_LIBRARY;`, insert `const EMBEDDED_LIBRARY = <library json>;` after the `let LIBRARY = {...}` line, and replace the object literal assigned to `const PROFILES` with `ticker-profiles.json`'s `profiles` object.

## Locked output format — do not change it between prints

```
[COMPANY] — EARNINGS SCORECARD

⚡ ASYMMETRIC EVENT FLAG        (only if it fires — at the very TOP)

HERO KPIs — street | bogey | actual        (table, FIRST)

Overall Score: X.XX (Bullish / Neutral / Bearish)   · positioning-adjusted X.XX

1. Current Quarter: [score]        — one sentence
2. Next Quarter Guidance: [score]  — one sentence, above/inline/below
3. Full-Year Guidance: [score]     — one sentence, raised/maintained/cut
4. Narrative Check: [score]        — one sentence, confirmed or broke the setup

5. Key Takeaways                   — 3–5 bullets, only what moves the stock
6. Stock Reaction Framework        — direction, what overrides it, and WHICH BRANCH MATCHED
```

If a read cannot compress to one sentence per category, the score is wrong or the data is incomplete.

## What must NOT be automated

Score these `None` with a reason. Every one mattered more than the arithmetic last quarter:

- a figure buried in the **cash-flow statement or balance sheet** (SNDK's $93.9B backlog)
- **GAAP vs a company-defined non-GAAP basis** (CBRS: GAAP missed 7.0% while "core" beat 9.9% — the tape traded GAAP)
- a large **one-off gain** inflating headline EPS (WDC GAAP $8.21 vs a $3.29 street estimate)
- **definitional mismatches** between a consensus line and the reported line
- **withdrawn metrics, capped roadmaps, volunteered ceilings**
- **anything requiring the call** — Narrative, generally. On a PR-only run set `status: "SCORED-PR-ONLY"` and grade three categories.

## Repo hygiene

`.gitignore` already excludes `.env` and `secrets.json` — API keys go there. PowerShell: `serve-dashboard.ps1` (localhost view) · `sync-before-scoring.ps1` (pull + preflight) · `score-and-publish.ps1` (both gates + regen + push) · `regen_standalone.py`. The older `.sh` versions remain for reference.
