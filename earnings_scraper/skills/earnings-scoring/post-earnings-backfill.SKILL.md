---
name: post-earnings-backfill
description: Weekday 7:30 AM ET — find PRE-EARNINGS records whose report date has passed, research actuals, INDEPENDENTLY VERIFY every figure via a subagent audit before writing, then persist actuals, beat magnitudes, matched branch, call notes and reaction. One-line no-op when nothing is pending.
---

You are completing post-earnings scorecards for Kyle, an intraday news trader, in his local project "earnings Model".

WORKSPACE: `C:\Users\Trader\Documents\Claude\Projects\earnings Model`
In bash this folder is mounted under `/sessions/<session>/mnt/earnings Model/` — run `ls /sessions/*/mnt/` to find the exact path.

**KYLE'S STANDING REQUIREMENT: everything is double-checked BEFORE it is uploaded into the library.** Step 4 is a hard gate. Do not skip it, and do not write a record you could not verify.

## STEP 0 — THE GATE. Do this first and be willing to stop.

Read `earnings-library.json`. Find every record where:
- `status` is `PRE-EARNINGS` (case-insensitive), AND
- `reportDate` is strictly BEFORE today

**If there are none, output exactly one line — `No pending post-earnings scorecards. N records in library, next scheduled print: <ticker> <date> or none.` — and STOP. Do not research. Do not touch any files.** Most days this is the correct outcome; a clean no-op is a success, not a failure.

Also collect records already scored but with `stockReaction.pctChangeNextDay == null` — those need reaction backfill only, and still go through Step 4.

## STEP 1 — Load the frameworks before grading

From the top level of `earnings-library.json` read: `positioningFramework`, `scenarioLadderFramework`, `beatMagnitudePatterns`, `overnightHoldFramework`, `regimeFramework`. Read `ticker-profiles.json` → `profiles[TICKER]` for hero-KPI overrides.

For each pending record read its own `preEarnings` block (especially `keyKPIs` IN ORDER, `revConsensus`/`revBogey`, `epsConsensus`/`epsBogey`), its `positioningAxis`, and its pre-written `scenarioLadder`.

## STEP 2 — Research the actual results

Use WebSearch and web_fetch to find, per ticker and quarter:
1. Actual reported figures for every KPI in `preEarnings.keyKPIs`, in the same order
2. Forward guidance actually given (next quarter and full year), with the RANGE and the MIDPOINT
3. Earnings-call content — management quotes, anything NOT in the press release, analyst Q&A, and any dollar-anchored multi-year or contracted disclosure
4. Stock reaction: print-day close, after-hours settle %, next-day open, **next-day CLOSE %**
5. Incremental analyst activity — PT and rating changes in the 24h after the print

**Never fabricate a number.** Unverifiable → `null` plus a note.

## ★ STEP 3 — Draft the grade

Four categories, each −2 to +2 in 0.5 steps: Current Quarter (20%), Next Q Guidance (30%), FY Guidance (30%), Narrative (20%). Overall = weighted average. ≥+0.5 Bullish, ≤−0.5 Bearish.

- **Grade against BOGEY, STREET and the company's own GUIDE as three separate columns.** 🟢 clears bogey · 🟡 beats street but misses bogey = FADE ZONE · 🔴 misses street.
- **Hero-KPI override:** a priority-1 hero KPI at ±2 dominates its category; a hero-KPI MISS on the current quarter CAPS Current Quarter at 0 even with a revenue/EPS beat; any priority-1 KPI at ±2 pulls Narrative by ≥1 point. Respect `interpretation: reverse-polarity`.
- **A company that never gives FY guidance scores 0 on absence — do not penalise it.**
- **Positioning never changes `scores.overall`.** Compute `positioningAxis.adjustedScore = scores.overall + signModifier` separately.
- **Name which pre-written `scenarioLadder` branch the print matched** and whether the realised reaction fell inside its `expectedReaction` range. If nothing matched, say so — that is itself a finding.

## ★★ STEP 4 — INDEPENDENT VERIFICATION BEFORE WRITE. HARD GATE.

Nothing is written until this passes. **Every failure in this library's history has been a DATA error, not a write error** — so verify the numbers, not the plumbing.

### 4a. Two-source rule on every figure that will be stored

Each actual, each guidance figure and each reaction percentage needs **two independent sources**, or it is marked `unverified: true` and excluded from `beatMagnitude`. The company's own press release or 8-K is always the preferred primary source — fetch it rather than relying on a summary article.

### 4b. Hunt these specific error classes — all have actually occurred here

1. **★ THE EXPECTED COLUMN IS AS ERROR-PRONE AS THE ACTUAL COLUMN.** An AAPL record stored Greater China consensus at $21.5B when the real street figure was $19.0B, and consequently graded a **7.9% BEAT as the print's "biggest bear vector."** Re-verify consensus and bogey figures, not just reported results. Kyle's instinct that "the numbers look off" was right, and the error was on the expectations side.
2. **★ SIGN FLIPS AND WRONG-DAY REACTIONS.** A PLTR record stored −1.37% when that was the print-day **+1.36% with a flipped sign**; the true next-day reaction was **−6.93%**. Always confirm: is this figure the print-day move, the after-hours settle, or the next-day close? They are three different numbers and only the next-day close belongs in `pctChangeNextDay`.
3. **★ AFTER-HOURS vs NEXT-DAY CLOSE CONFLATION.** ZS and SNOW both carry unresolved conflicts where one source implies no overnight move and another implies ~47% of the move happened overnight — **opposite conclusions from the same print.** When sources disagree, store BOTH with a `conflict` note. Never silently pick one.
4. **★ DO NOT INFER A LEGEND FROM NUMERIC PLAUSIBILITY.** An AMD bogey-sheet column reading "140%" was taken as front-week implied vol; it was YTD move. It produced a **false confirmation** because AMD's real ATM IV happened to be 137.3%. If a column header is not legible, say so — do not guess from the value looking reasonable.
5. **UNITS MISMATCHES.** Computed deltas have hit +103,882% and −99.9% from mixed $M/$B or GAAP/non-GAAP bases. Suppress anything beyond ±300%, tag `pctFlag`, and re-check the units.
6. **DEFINITIONAL MISMATCHES.** A consensus line that measures something different from the reported line yields a false beat or false miss (e.g. a "cash & equivalents" consensus against a company that manages cash across cash + marketable securities). Flag and DO NOT grade a mismatched line.
7. **GAAP/NON-GAAP HEADLINE TRAPS.** A one-off mark-to-market gain can make headline EPS look like a huge beat against a non-GAAP consensus. Identify the comparable basis explicitly.

### 4c. Subagent audit — mandatory

Launch a **general-purpose subagent** with the drafted record and the source URLs, instructed to:
- Independently re-verify every stored figure against primary sources, **including the consensus and bogey columns**
- Confirm `actuals.keyKPIs` is index-aligned 1:1 with `preEarnings.keyKPIs` and that each `actual` is genuinely populated, not blank
- Recompute the weighted average and confirm it equals the stored `scores.overall`
- Recompute every `pctVsCons` / `pctVsBogey` / `pctVsGuide` independently
- Confirm the reaction figure is the **next-day close**, not the print-day move or the AH settle
- Report every discrepancy without deferring to the draft

Resolve every discrepancy before writing. If a conflict cannot be resolved, store both values with a `conflict` note and surface it to Kyle in the output.

### 4d. Sanity checks that catch silent nonsense

- Does the reaction sign agree with the overall score? If a strongly positive score has a sharply negative reaction, that is either a real divergence worth recording or a data error — determine which and say so.
- Is the realised reaction inside the matched branch's expected range?
- Does the print-day move ÷ implied move reproduce `positioningAxis.components.runIntoPrint`?
- Is `sector` identical to that ticker's other quarters? A mismatch splits the company card.

## STEP 5 — Write the record

Set `status` to `SCORED-POST-CALL` (or `SCORED-PR-ONLY` if no call content was found), `updatedAt` to today.

MANDATORY blocks — each backs a dashboard tab that renders empty without it:
- **`actuals.keyKPIs` index-aligned 1:1 with `preEarnings.keyKPIs`** — same order, same length. The dashboard maps them POSITIONALLY, so a missing or mismatched array **silently blanks the Actual-vs-Expected grid while still rendering**. Build the array against the pre-earnings order; never from memory of the print. Each entry: `{actual, vsCons, vsBogey, vsConsNote, vsBogeyNote, pctVsCons, pctVsBogey, pctVsGuide}`. Verdict strings the renderer recognises: `BEAT`, `MISS`, `INLINE`, `CRUSH`, `DEMOLISH`, `NUKE-BEAT`, `NUKE-MISS` — anything else renders as INLINE.
- **`callCommentary`** — `{summary, missedInPR, callOnlyKPIs, incrementalAnalystActivity, keyQuotes, tradingImplication}`. `missedInPR`, `incrementalAnalystActivity`, `keyQuotes` MUST be lists.
- **`beatMagnitude`** — `{revPctVsCons, revPctVsBogey, epsPctVsCons, epsPctVsBogey, score, reactionPct, impliedMove}`.
- **`stockReaction`** — `{afterHours, openPx, closePx, pctChangeNextDay, direction, notes}`.
- **`positioningAxis`** — carry forward, add `postPrintReview` on whether the axis called the reaction.
- **`branchMatched`** — `{branch, triggerHit, expectedReaction, actualReaction, insideRange}`.
- **`verification`** — `{twoSourceConfirmed: [...], unverified: [...], conflicts: [...], subagentAuditRun: true, discrepanciesFound: [...], auditedAt}`. **This block is required. It is the audit trail Kyle asked for.**
- **`scores`**, **`scoreLabels`**, **`summaries`** (one sentence each), **`takeaways`** (3–5 bullets), **`stockReactionFramework`**.

**Do NOT invent `tradeSummary`** — that is Kyle's own execution review. Set `tradeSummaryPending: true`.

## STEP 6 — Post-write structural verification

1. `python3 validate_library.py` — must exit 0. Fix hard defects before continuing.
2. `node render_test.js` — walks cardHtml → openModal → setTab for every record and every tab that record offers. Must report 0 card, 0 openModal, 0 setTab failures. **A test proving a tab renders is NOT sufficient — assert it contains data.** Three cards once shipped un-openable while a weaker harness reported zero failures.
3. Regenerate `dashboard-standalone.html`: read `dashboard.html`, replace

```
    // Cache-bust each load so we always get latest committed JSON
    const res = await fetch('./earnings-library.json?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    LIBRARY = await res.json();
```

with `    LIBRARY = EMBEDDED_LIBRARY; // self-contained build`, insert `const EMBEDDED_LIBRARY = <library json>;` immediately after `let LIBRARY = { version: 2, lastUpdated: "loading...", records: [] };`, and replace the object literal assigned to `const PROFILES` with `ticker-profiles.json`'s `profiles` object.

## STEP 7 — Output

Lead with a compact table: ticker · quarter · overall · positioning-adjusted · branch matched · expected range · actual reaction · inside range.

Then per ticker, ≤150 words: the decisive number, what the call added or withheld, whether the framework called it. Kyle reads this before the open — lead with the answer, no preamble, no disclaimers.

Then a **VERIFICATION section**, always, even when clean: figures confirmed by two sources, figures left unverified, source conflicts stored, and every discrepancy the subagent audit caught. If the audit found nothing, say so explicitly.

Close with anything needing Kyle's input (trade summaries pending, unresolved conflicts, unpopulated positioning components) and the one-paste push command:

```powershell
cd "C:\Users\Trader\Documents\Claude\Projects\earnings Model"; git pull --rebase; git add -A; git commit -m "Post-earnings backfill <date>: <tickers>"; git push
```

## Standing analytical rules — apply, do not re-derive

- **Unmodeled disclosures have no consensus denominator.** Measure against the CURRENT RUN RATE, not consensus (>2x = model rebuild).
- **Guidance withheld from the PR = the call is the event.** Track as a per-ticker habit.
- **PR-vs-CALL score divergence is a first-class metric.** Log the delta.
- **Peak-cycle buyside-inline fade:** at stretched cycle positioning, inline against a stretched bogey is a sell.
- **Fade patterns are REGIME-CONDITIONAL.** Before citing a base rate, ask whether it was set in the same chart/multiple regime.
- **Deposits without a total contract value are a setup signal, not the trade.**
- **Run-Into-Print (print-day move ÷ implied move) is the strongest single signal in the system at −0.832.** Always record it.