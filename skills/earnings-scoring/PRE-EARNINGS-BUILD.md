---
name: pre-earnings-build
description: How a print gets prepared before it lands — hero-KPI selection and ordering, bogey sourcing, the numeric positioning axis, and the if/then scenario ladder. This is the half of the model the scraper cannot infer.
version: 1.0
created: 2026-08-17
---

# Pre-Earnings Build

**Completeness wins here, not speed.** This runs hours or days ahead of the print. Its entire purpose is that when the release crosses you are **matching a pre-written branch, not reasoning from scratch** — which is where the speed on the post-earnings side comes from.

A pre-earnings deliverable is incomplete without **both** the numeric positioning axis and the if/then ladder.

---

## STEP 1 — Pull the ticker's history first

```
prior = [r for r in library.records if r.ticker == TICKER]  # sort by reportDate desc
```

From the most recent prior record, extract and carry forward:

| what | why it matters |
|---|---|
| `preEarnings.keyKPIs` — **the exact list and order** | the starting point for this quarter's list; continuity is what makes cross-quarter comparison possible |
| `scores` (all four) + `overall` | the Q/Q trajectory — improving or deteriorating execution |
| `beatMagnitude.reactionPct` and `.impliedMove` | **how the tape treated the last print relative to what was priced** |
| `positioningAxis` | what the crowding was last time, and whether the pattern regime still holds |
| `callCommentary.missedInPR` | ★ **does this ticker withhold material figures from the PR?** A per-ticker structural habit |
| `branchMatched` | did the last ladder work, and by how much was it mis-sized |
| `tradeSummary.patternLessons` | Kyle's own execution lessons on this name |
| `sector` | **must be reused verbatim** or the dashboard splits the company card |

**Q2 prints APPEND a new record with a distinct id.** Never overwrite a prior quarter.

**If no prior record exists** (first-ever print for this ticker), say so explicitly, set `bogeyReliability` accordingly, and expect wider error bars. NBIS, CSCO and WDC were all first records and all four backfilled prints in that week mis-sized the reaction.

---

## STEP 2 — Select and order the keyKPIs. This is the piece a scraper cannot infer.

### Selection

Load `ticker-profiles.json → profiles[TICKER]`. If it exists, its `priority: 1` entries **are** the graded set. If it does not exist, build one — and the question you are answering is:

> **What single number, if it comes in wrong, breaks this stock regardless of everything else?**

That is the hero KPI. It is almost never revenue. Worked examples from the library:

| ticker | hero KPI | why |
|---|---|---|
| MSFT | Azure constant-currency growth | the whole multiple rests on it |
| AMZN | AWS growth + margin | ditto |
| META | **FY capex guide — reverse polarity** | higher capex is bearish here |
| ANET | FY revenue guide % + **deferred revenue, reverse polarity** | a deferred build is bearish, not bullish backlog |
| CRWV | **adjusted operating income** | the line the bear case says cannot inflect |
| NBIS | **adjusted EBITDA**, then **ACV per MW** | revenue beat 2% and the stock rose 34% |
| CBRS | **hardware revenue** | it markets itself as a chip challenger; hardware −23% YoY inverts the story |
| CSCO | **non-GAAP gross margin** | beat revenue and EPS, guided FY 6–9.5% above consensus, fell 8.4% on margin |
| APP | **next-Q adj EBITDA guide** | the bogey equalled street, so anything below street was a real miss |

### ★★ PERSIST THE PROFILE. THIS IS A REQUIRED WRITE, NOT AN OPTIONAL ONE.

**Write or update `ticker-profiles.json` before the print.** Each entry: `{name, priority, appliesTo, beatBand, missBand, unit, notes, interpretation?}`. `appliesTo` is one of `currentQuarter` / `nextQGuidance` / `fyGuidance` / `narrative`. Use `interpretation` for `reverse-polarity`, `unpriced-upside`, `binary`, `conditional`, `basis-trap`, `cap-the-model-watch`.

**Why this rule exists.** On 2026-08-17 an audit found **34 of 57 tickers had a scored record but no profile.** The builds had done the work — the hero KPIs were sitting right there marked `★★★` in `preEarnings.keyKPIs` (MU's read literally `🔥 #1 F4Q (Aug) EPS GUIDE ★★★ (THE TRADE)`) — and none of it was persisted where the scorer looks. 32 were back-derived from those markers and carry `needsReview: true`; AEHR and IBM had to be authored from their actuals and takeaways because their records have **no `preEarnings` block at all.**

Without a profile the scorer falls back to revenue, which §1 of `SKILL.md` proves cannot reproduce the grades. **`validate_library.py` HARD 7 now fails on a missing profile**, so the gap cannot silently recur.

**If the ticker already has a `needsReview: true` profile, confirming or correcting it is part of this build.**

### Ordering — load-bearing, because the dashboard maps positionally

Order by **what decides the print**, not by income-statement convention:

1. Current-quarter **hero KPI**
2. Current-quarter revenue
3. Current-quarter EPS or the profitability line
4. Current-quarter margin
5. **Next-quarter guide — primary line** (usually revenue)
6. **Next-quarter guide — margin or EPS line**
7. FY guide line, if the company guides annually
8. **Qualitative / unmodeled-disclosure watch item — ALWAYS LAST**

Mark with `★` in the name: `★` priority 1 · `★★` the trade · `★★★` the whole thesis. Prewarm the glyph on Windows — font fallback on `★` cost 200 ms of first render.

**Keep the prior quarter's order wherever the KPI still applies.** Continuity is what makes the cross-quarter Hero KPI view work.

---

## STEP 3 — Source the bogeys

Authority order, and record which one you used in `bogeyMethod` and `bogeyReliability`:

1. **Kyle's buyside bogey sheet** (TMTB-style). Canonical. **Also read the header** — it carries YTD move, implied move and a **positioning score 0–10, same polarity as ours** (higher = more crowded). Store it in `positioningAxis.externalScore`.
2. **Bloomberg preview** — consensus, implied move, and the relative-performance line (`Shares up X% in past year vs SPX up Y%`) which feeds positioning component 1 directly.
3. **Published sell-side consensus, multi-provider.** When they disagree, **store every value and do not resolve.** SNDK's FQ1 consensus had four values and the sign of the guide delta flipped depending on which you picked.
4. **Reconstruct** — one documented method only: apply the ticker's own historical beat-vs-guide cadence to the current guide, cross-checked against published sell-side high-end bars. Set `bogeyReliability: "DERIVED"` and grade primarily vs consensus.

**Record the three columns separately for every KPI:** `consensus`, `bogey`, and the company's own guide. They are three different bars and the grading needs all three.

⚠️ **Never infer a unit or a legend from numeric plausibility.** A sheet column reading "140%" was taken as implied vol; it was YTD move — and it produced a **false confirmation** because the real ATM IV happened to be 137.3%. `revUnit` is null on 7 of 76 records; refuse to grade those rather than inferring.

---

## STEP 4 — Score the positioning axis

Six components, each **−2 to +2**, where **positive = MORE CROWDED LONG**.

```
raw     = sum(components)                 # -12 .. +12
score10 = round((raw + 12) / 24 * 10, 1)  # 0 .. 10
```

| # | component | measures | corr vs reaction |
|---|---|---|---|
| 1 | `relativePerf` | RPS = stock return − SPX/sector return, same window, in points | −0.639 |
| 2 | `sellSide` | Buy share, **spot vs average PT**, raise cadence, Hold-count trend | −0.550 |
| 3 | `runIntoPrint` ★ | **print-day move ÷ implied move** — the pre-paid veto | **−0.832** |
| 4 | `optionsPosture` | skew, near-money put OI, net GEX, premium-selling flow | −0.359 |
| 5 | `squeezeFuel` | SI % of float, DTC, borrow — **inverted** | −0.156 |
| 6 | `priorPrintPattern` | did the tape sell this ticker's good prints? | −0.462 |

Per-component rubrics are in `earnings-library.json → positioningFramework.components`.

**Bands / sign modifier:** ≥8.0 🔴 SEVERELY CROWDED (−0.75) · 6.5–7.9 🟠 CROWDED (−0.40) · 4.0–6.4 ⚪ BALANCED (0) · 2.5–3.9 🟢 DE-RISKED (+0.40) · <2.5 🔵 HATED (+0.75)

### Five hard rules

1. **Component 3 is the strongest signal in the system (−0.832), stronger than the entire fundamental scorecard.** It is one division. Compute it first.
2. **★ NEVER lock component 3 from an intraday snapshot.** Use the **official close**, from two independent OHLC sources. If the print is same-day, mark it `PENDING` rather than guessing. Two locks were set from intraday prints that reversed by the close — one had the sign inverted, which poisoned an entire read.
3. **Two-timeframe rule** (component 1): when the 1-year and last-5-session windows disagree, **the short window governs** — it identifies the marginal holder.
4. **Regime gate** (component 6): score 0 unless the prior-print pattern was established in the **same chart/multiple regime** being traded now.
5. **Short interest is a weak standalone proxy** (−0.156). Convert arb, GC borrow and low days-to-cover all break it. Keep for context; do not lean on it.

At T−1, components **1, 2, 5 and 6** are knowable. Compute a provisional score and mark `confidence` honestly (`HIGH` only at 6/6). Component 3 locks at 4:00 PM, component 4 from the chain.

### The sheet score is an anchor, not a substitute
When Kyle's sheet carries a positioning score, it is authoritative for components 1–2 — record it verbatim, do not re-derive. **But never trade off it alone: it correlates only +0.066 with reaction**, because it is fixed 1–3 days early and cannot contain component 3. ANET and ALAB both scored exactly **7** on the same sheet; ANET went **+12%** and ALAB **−2%**.

---

## STEP 5 — Write the if/then ladder

Read the required-surprise tier off the provisional positioning band:

| positioning | the print MUST deliver | an INLINE guide means | default |
|---|---|---|---|
| **≥8.0** 🔴 | an UNMODELED DISCLOSURE **and** runIntoPrint < +2 | SELL, −5% to −10% | FADE |
| **6.5–7.9** 🟠 | guide >+3% vs **bogey**, not pre-paid | SELL, −2% to −5% | FADE unless a real raise |
| **4.0–6.4** ⚪ | normal beat, guide ≥ bogey | flat to −3% | fundamentals govern |
| **2.5–3.9** 🟢 | any clean bogey clear | absorbed, ~flat | LONG on any clear |
| **<2.5** 🔵 | almost nothing | rallies anyway | LONG |

Then write **4–6 branches**:

```json
{"branch":"BULL — guide crush",
 "trigger":"NUMERIC, on the hero KPI and/or guide lines, stated vs BOGEY and vs street",
 "positioningContext":"which tier, and whether the escape clause is armed",
 "expectedReaction":"a RANGE, sourced from the matrix cell",
 "tradeType":"momentum continuation | overreaction fade | reversal | no trade",
 "stayForCall":"yes/no + why",
 "overnightEligible":"per overnightHoldFramework",
 "basedOn":"which matrix cell, and n"}
```

**Rules:**
- **Every trigger is a NUMBER, not an adjective.**
- Always state the **bogey delta AND the street delta** — the same headline pays roughly 5x more against bogey.
- **Always include an INLINE branch.** Inline is the modal outcome, and at crowded positioning it is a short.
- Include a **call-only branch** for any ticker that has withheld guidance from the PR before.
- **★ NAME THE SINGLE METRIC THE MARKET WILL GRADE**, and measure the required surprise on *that* line. If no published consensus exists for it, say so — that absence is itself a red flag. CSCO cleared the crowded gate by 6–9.5% on revenue and EPS and fell 8.4%, because the graded metric was gross margin.

### The two highest-conviction cells

- **CROWDED ≥7 + NO guidance delta → 3 for 3 DOWN, median −12%.** Marginal buyer gone *and* nothing handed to the market to reprice on. Knowable at T−1 from the ticker's guidance habit.
- **DE-RISKED <4 + guide >+3% vs bogey → 3 for 3 UP, tight +8.4% to +13.1%.** The tight band makes this the cell to **size**.

⚠️ **Both bands understate when an accelerant is stacked on top.** NBIS (+34.14%) had extreme squeeze fuel; CRWV (+19.28%) had a documented multi-quarter fade pattern reversing. Widen materially in those cases.

⚠️ Matrix cells are **n=1 to 3**. Frame branches with them; do not size off them.

---

## STEP 6 — The 4:00 PM lock (same day, before the release)

- **Lock component 3** — print-day move ÷ implied move, from the official close. It only exists now.
- Lock component 4 from the chain.
- Recompute `score10`. If it crossed 7.0 the crowded-long escape clause is armed.
- **If component 3 = +2, downgrade every bullish branch one notch before the PR crosses.**
- **Check the mechanical supply calendar** — IPO lockup tranches, index rebalances, 10b5-1 windows. CBRS lost an extra 5.21% on day two when 36.4M shares came off lockup at 6:00 am; that date was contractual and published.

---

## Record shell a pre-earnings build produces

```json
{"id":"{TICKER}-{YEAR}Q{N}","ticker":"","company":"","sector":"<must match prior quarters>",
 "quarter":"","year":"","reportDate":"YYYY-MM-DD","timing":"AMC|BMO|Mid-day",
 "status":"PRE-EARNINGS",
 "tags":[],"marketRegime":"",
 "preEarnings":{"revConsensus":null,"revBogey":null,"revUnit":"$B|$M","epsConsensus":null,"epsBogey":null,
   "revNote":"","epsNote":"","impliedMove":"","bogeyMethod":"","bogeyReliability":"",
   "keyKPIs":[{"name":"... ★","consensus":null,"bogey":null,"note":""}],
   "whatMattersMost":"","setup":"","bullCase":"","bearCase":"","whatWins":"","whatLoses":"","largeMoveCatalysts":[]},
 "positioningAxis":{"components":{},"raw":0,"score10":0,"band":"","signModifier":0,
   "confidence":"PRE-PRINT","componentsScored":"4/6","pendingLock":[],"externalScore":null,"rationale":""},
 "scenarioLadder":[],
 "scores":{"currentQuarter":null,"nextQGuidance":null,"fyGuidance":null,"narrative":null,"overall":null},
 "actuals":null,"createdAt":"","updatedAt":"","notes":""}
```

⚠️ **`status` must be the string `PRE-EARNINGS`.** A lowercase `pre-earnings` once made `isPre` false in the renderer, and because `null >= 0` is **true** in JavaScript the modal header called `.toFixed()` on null and three cards became un-openable. `isPreEarnings()` now guards it, but write it uppercase.
