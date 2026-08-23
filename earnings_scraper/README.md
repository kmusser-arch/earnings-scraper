# Earnings wire scraper

Watches PRN / BUS / NFI / ASW / PZM on the SHEL News Gateway, catches earnings
releases for the names you paste each morning, grades them against the earnings
model, and pops a full report card.

Wire → visible card is **~90–120 ms**, of which the analytical pipeline is
**under 1 ms**; the rest is Tk drawing the window.

## Daily use

```powershell
cd C:\Users\Trader\Desktop\shelnewsapi

# 1. Pull first — the card may have been written minutes ago in Cowork.
cd "C:\Users\Trader\Documents\Claude\Projects\earnings Model"; git pull --rebase; cd -

# 2. Pre-market. Paste the day's names, finish with Ctrl+Z then Enter.
py -m earnings_scraper watch

# 3. Go live and leave it running.
py -m earnings_scraper run -u kmusser --prod
```

| Command | Purpose |
|---|---|
| `show` | reprint the watchlist and its warm-up report |
| `selftest -t CSCO --expect-cq 1.0` | grade a synthetic release against a real card |
| `selftest --record SNDK-2026Q4 --popup` | pin an exact record, render the card |
| `replay news.log` | replay a captured feed end to end |
| `run --no-popup` | terminal output only |

## Paths — live data is never copied

The two live files are read by **absolute path** at runtime. A local copy goes
stale the moment a new pre-earnings card is written.

```
LIB_DIR = C:\Users\Trader\Documents\Claude\Projects\earnings Model
  earnings-library.json     <- live, absolute
  ticker-profiles.json      <- live, absolute
skills/earnings-scoring/calibration.json   <- local, versioned with the code
```

Override with `EARNINGS_LIB_DIR`. Frameworks are read out of the library at
runtime and never duplicated into code, so a framework revision propagates
without a code change.

## The card is the config file

There is no separate config. `watch` indexes records where
`status.upper() == "PRE-EARNINGS"` **and** `reportDate == today`, then resolves
each ticker's priority-1 hero KPI from `ticker-profiles.json` and pulls its
consensus, bogeys and `keyKPIs` in order. That takes ~20 ms and leaves the whole
expected column resident, so the print-time path touches no disk and no network.

`abandonedRecords[]` is never indexed and never counted in `records[]`.

## ★ The no-card rule

A pasted ticker with no card reporting today is `NO_CARD`: the numbers are
extracted and **displayed**, nothing is graded, and the card is a red alert.
There is no fallback to the most recent record and no fallback to revenue.
Missing profile is `NO_PROFILE` and refuses identically.

A confidently wrong grade is worse than a blank because it propagates into
`beatMagnitude` and `branchAccuracyLog` and corrupts the model's own
cross-sectional statistics.

## Scoring

**Current Quarter** grades on clearance of the **bogey** on the ticker's
priority-1 hero KPI, modified by an **offsetting-flag count**. Neither axis is
revenue or consensus — a consensus-delta function provably cannot reproduce the
accepted grades.

- **The hard cap runs first.** A priority-1 hero KPI that misses caps Current
  Quarter at 0.0 — as a **ceiling**, not a value. The negative bands still
  decide how far below it lands.
- **Reverse-polarity** heroes score inverted.
- **Next-Q** and **FY** grade the guide midpoint vs bogey then consensus.
  FY keys on the ACTION — `raises` / `reaffirms` / `lowers` read from the
  release, plus a stated prior range — because the FY band is an action table,
  not a delta table.
- **Absence is 0.0, not a deferral** — but only for a company that does not
  guide. The card's `fyGuideExpected` / `nextQGuideExpected` decides: "None." or
  "No formal FY rev/EPS" scores a neutral 0.0, whereas an expected guide that
  the release withheld defers, because guidance withheld from the PR means the
  call is the event.
- **★ Withdrawn / capped / ceiling DEFER, never score.** A withdrawn metric, a
  capped roadmap or a volunteered growth ceiling is in the "must NOT be
  automated" list: the weight depends on whether the retired number was the one
  carrying the story, which needs the call. `−2.0` is the rarest value in the
  model (1 of 76 for `fyGuidance`), so auto-assigning it from a regex is the
  wrong direction of error. These route to the widened bracket with
  `status: SCORED-PR-ONLY` and the reason stated.
- **Expectations are read from STRUCTURED sources only** — a period-classified
  `keyKPIs` slot, or `fyExpectations` / `q2Expectations` carrying
  `revenue` + `revenueUnit`. Prose is never regexed: `fyGuideExpected` on
  NOW-2026Q1 reads "FY sub rev $15.53-15.57B", which is **subscription**
  revenue, and grading a total-revenue guide against it is error class D4.
  `q2Expectations` is a bare string on some records — always isinstance-check.
- **Narrative is always `None`** on a PR run, so `overall` is never emitted as a
  point estimate. What the card shows instead is the PR-only decision gate.

## The PR-only decision gate

Narrative carries weight 0.20 and is bounded [-2, +2], so it can move `overall`
by at most ±0.40. A PR-only run therefore knows `overall` to within an exactly
0.80-wide bracket:

```
partial = 0.20*CQ + 0.30*NextQ + 0.30*FY
overall in [partial - 0.40, partial + 0.40]     <- exact, not estimated
```

Bands and base rates load from `earnings-library.json -> prOnlyGateFramework`,
never hardcoded. Verify with `py pr_only_gate.py` — it must reproduce
n=29/1/27 and mean -3.80%.

| band | test | n | outcome |
|---|---|---|---|
| `DECISIVE_BULLISH` | `partial - 0.40 >= +0.50` | 29 | 79% up, mean **+9.79%** |
| `DECISIVE_BEARISH` | `partial + 0.40 <= -0.50` | 1 | **n=1 — no base rate exists** |
| `STAY_FOR_CALL` | bracket straddles | 27 | **78% DOWN, mean -3.80%** |

**`STAY_FOR_CALL` is a short-side signal, not "wait and see".** When the PR alone
cannot settle the read, the tape resolves it down 21 times in 27 — ambiguity is
bearish, because clean prints are unambiguous. But the 22% that go up average
**+13.6%** (NBIS +34.14, QCOM +15.00, AMZN +10.00), so the base rate and the
tail are always rendered together and never separately.

### Three things the gate deliberately does NOT do

- **No renormalization.** Rescaling the three known categories to 25/37.5/37.5
  was tested and rejected: it flips 6 of 76 labels, and CSCO-2026Q4 goes
  +0.35 Neutral -> **+0.81 BULLISH on a stock that fell 8.40%**. Narrative is
  where "cleared revenue and EPS, market graded gross margin" lives.
- **No positioning modifier.** Only 6 of the 29 `DECISIVE_BULLISH` records carry
  a positioning score, so good-print/bad-tape is untested in the cohort that
  matters. Positioning is shown as context, labelled, and never applied.
  `adjustedScore` is deliberately absent.
- **No point estimate.** `overallPoint` is always `None`.

Containment is asserted on **every run** — it is arithmetically guaranteed, so
`BracketContainmentError` means a real bug, not an edge case.

### The tail separator — `forwardCommitment.novelty`

**The $-anchor direction hypothesis is FALSIFIED and is not implemented.**
$-anchored n=3 mean +10.71% vs not-anchored n=3 mean +3.99% — overlapping. SNDK
carries the largest anchor in the library ($93.9B contracted minimum with floor
pricing) and **fell 6.81%**; QCOM disclosed a hyperscaler deal with **no dollar
figure** and rose 15.00%. A dollar figure is a **magnitude dampener** — within
the down-cohort SNDK's −6.81% is the smallest decline against WDC's −13.03% on a
structurally identical setup — but it never set direction.

What separates the tail is **novelty**. Not "is there a big number" but "is there
a NEW commitment, and can I locate it."

Precedence, in order:

| # | condition | verdict |
|---|---|---|
| **1** | cyclical sector **+** peak-cycle language **+** inline-vs-bogey | **PEAK-CYCLE FADE WINS** — NEW overridden, the short stays live |
| **2** | `NEW` | **SHORT VOID** — long permissive, unsized (n=5) |
| **3** | `NEW-BUT-SPEND` | **REINFORCES** — a capex commitment is a *cost* (SPCX −12.00%) |
| **4** | `ABSENT` `WITHDRAWN` `OMITTED` `FLAT` `WEAK` | **REINFORCES** — n=6, up 1/6, mean −11.02% |
| **5** | `NONE` | no signal — the TSLA exception rose on an unrelated axis (FCF) |

**Rule 2 is a tradeable asymmetry, not ambiguity.** With `NEW-BUT-SPEND` split
out, NEW is 4/5 up at mean **+11.43%**, and the payoff is lopsided: mean up-case
**+15.98%** against a single down-case of **−6.81%**. "Stand down" would discard a
permissive long with favourable asymmetry — so the verdict is that the *short* is
void, with the long permissive but explicitly **unsized** at n=5.

**Rule 1 resolves the SNDK collision.** SNDK is the one NEW case that fell, and
it carries cyclical sector (Semiconductors / Memory) **and** explicit peak-cycle
language **and** inline-vs-bogey — the Peak-Cycle Buyside-Inline Fade, whose
founding case is MU Q3 FY26 in the same sector. Two rules pointed opposite ways;
rule 1 says which wins.

Three implementation details that matter:

- **The peak-cycle phrase must be tight.** SNDK's lives in
  `scenarioLadder[].basedOn` ("peak-cycle buyside-inline fade"). A loose
  `/cycle|peak/` test false-positives on QCOM, whose record is full of *cycle
  bottom* / *trough* / *inventory bottoming* — the opposite reading — and on NOW,
  which carries "vs >50% at peak" in a growth-rate sense plus "sales-cycle".
- **Only pre-print fields are read.** `_pre_print_text` covers `preEarnings.*`,
  `stockContext`, `positioningAxis` and the scenario ladder. Reading `summaries`,
  `callCommentary` or `actuals` would make the rule work in backtest and fail
  live.
- **Sector alone is insufficient.** QCOM is also Semiconductors and rose 15.00%;
  the language leg is what separates them. Verified 1 true positive, 0 false
  positives across the NEW cohort with clearance held constant.

#### The inline leg is denomination-dependent

E6's ">110% of bogey" is a **ratio**, derived on MU — a dollar/volume hero. It
does not transpose: a 40.0% gross-margin bogey × 1.10 = 44.0%, a **+400bp beat**,
which is not a high bar but an impossibility.

| hero denomination | inline leg |
|---|---|
| dollar / volume | ratio — clearance above **+10%** breaks the override |
| **percentage** | **DEFERRED (`None`)** → falls through to rule 2, reason on the card |
| unclassified | deferred, same treatment |

The library has no calibrated nuke-crush threshold in basis points, so inventing
one would be fabricating the single number the override turns on.

**The dollar-★ fallback** keeps rule 1 reachable without inventing anything. When
the hero is percentage-denominated, the clearance leg is graded on the
**highest-priority dollar-denominated ★ row** that has a numeric bogey and is not
flagged unverified. That reuses E6's ratio on the metric type E6 was derived on.

On SNDK it lands on `FQ4 Revenue ($B)` — bogey 9.5 against 8.965B, a **−5.63%
MISS** against the buyside bogey, which E6 grades **MAX SHORT** (stronger than
inline). That row is *not* one of the four flagged implausible, so the fallback
**routes around** the unverified GM and EPS rows rather than depending on them.

Blast radius, matching the framework: **5 rescued, 3 still deferred** across the
12-record cohort (15 / 16 library-wide).

Guards, all tested:

- **Consensus is never substituted for a missing bogey** — that would silently
  change which of the three grading columns the rule reads.
- Rows flagged `unverified: true` are skipped.
- Forward-period rows cannot serve the clearance leg (grading a next-quarter
  guide as "the print landed inline" is error class 6).
- Percentage rows cannot serve as the dollar fallback.
- Scope is the **clearance leg only** — never hero selection, never Current
  Quarter grading.

**Units: declared first, then refuse.** Stored actuals are not consistent about
scale — SNDK keyKPI[0] is `FQ4 Revenue ($B)` with an actual of `8965` (`$M`),
while AMZN `Q1 Operating Income ($B)` has `23.852` (`$B`). The library now
declares `actualUnit` on 126 of the 212 dollar ★ rows and flags 4
`unitAmbiguous`, so resolution order is:

1. **`actualUnit` declared** → use it. Nothing to resolve, nothing to refuse.
   All 5 rescues in the cohort take this path (`declared $M` / `declared $B`).
2. **Not declared** → compute both readings. Use one *only* if exactly one is
   **coherent**; otherwise **refuse the row** and try the next candidate.
3. **`unitAmbiguous: true`** → skipped exactly like `unverified`.

A reading is *coherent* if it describes an outcome a business could print:
−99.90% is coherent (revenue really can collapse), +94,263% is not.

**★ Never prefer.** When both readings are coherent the row is refused, because a
real collapse and a unit error are then indistinguishable. A 9.5 (`$B`) bogey
against a bare actual of `9.5` reads as either **+0.00%** (inline) or **−99.90%**
(a collapse) — both coherent — and preferring one would turn a catastrophic miss
into "inline", the worst direction for this error to run. Declaring the unit
resolves that same row deterministically either way.

The live path never hits the ambiguity: the parser normalises every dollar
magnitude to `$M`, so `build_kpi_rows` **declares** `actualUnit='$M'` rather than
leaving it to be resolved.

The four `unitAmbiguous` rows in the library are genuinely misaligned — each
one's note describes a different metric than its row name (AKAM's bogey was for
total Cloud Computing, RDDT's note is about DAU on an Adj EBITDA row). Skipping
them is correct, and a flagged ★★ row is skipped even when it outranks the
candidate that gets used.

`HARD 11` in `validate_library.py` enforces declaration on `($B)`/`($M)` names
only — EPS is excluded, the same false-positive discipline the plausibility bands
needed.

**Denomination is resolved from the KPI NAME first**, with the profile's `unit`
field only as a fallback — because `unit` is **wrong on three profiles**: NBIS,
CRWV and CBRS all declare `%` while their names read `Adjusted EBITDA ($M)`,
`Adjusted Operating Income ($M)` and `Hardware Revenue ($M)`. Those are dollar
heroes; trusting `unit` would defer them for no reason. The conflict is reported
on the card so it can be fixed at source.

Resolved across 58 profiles: **20 percentage** (recorded in the framework), 25
dollar/volume, 3 unclassified.

Denomination is resolved from the **NAME** first, with `unit` as a hint only.
NBIS, CRWV and CBRS previously declared `%` on dollar heroes and are now fixed at
source — the name-first rule stays regardless, because a wrong unit field
silently disarms rule 1.

#### ⚠️ Rule 1's clearance leg is PROVISIONAL

SNDK-2026Q4 — rule 1's founding case — has a domain-implausible expected column
(FQ4 GM bogey 84.0 / consensus 81.5 for a memory semi, where GM runs ~30–40%),
and four rows are now unverified. The **sector and peak-cycle legs are
text-derived and unaffected**; the clearance leg is not validated until the
preview is re-sourced. Every rule-1 evidence block carries
`clearanceLegProvisional: True` with that note.

**★ The post-hoc caveat travels with every NEW verdict.** The separating rule was
selected *after* seeing which record fell — 1 TP, 0 FP on n=5. What keeps it out
of pure curve-fitting is that Peak-Cycle Buyside-Inline Fade already existed in
`LESSONS.md` with an **independent** founding case (MU Q3 FY26) predating this
test. Treat rule 1 as **one confirmation, not a validated hierarchy**; the next
cyclical peak-cycle NEW print is the real test. Rule 2 carries its own caveat
naming which leg of rule 1 failed, so the reader can second-guess it.

Also recorded on the card: **`fyGuidance == 0.0` was tested as the precedence
rule and REJECTED** — it false-positives on NOW-2026Q2, which was NEW with
fy 0.0 and rose +4.80%.

An existing commitment that goes **unmentioned** grades with the absences, not
the disclosures: CBRS's $20B OpenAI master agreement was absent from the PR, the
10-Q *and* the call. **Omission is an action.**

**Gated on presence.** Only 12 of 76 records carry a `forwardCommitment` block.
When it is missing the card says the separator is **UNAVAILABLE** and that the
short base rate therefore carries its full unseparated tail risk — it never
implies a neutral reading. n=12, hand-classified: a strong prior to test forward,
not a calibrated edge, and never folded into any score.

### FY inline is bearish

When `fyGuidance` resolves to **0.0** the card labels it
**"INLINE = BEARISH SKEW (8/11 down, mean −6.85%)"**. A neutral FY category score
is a bearish *outcome* signal: FY carries 30% weight and is graded against a bar
the market already raised, so landing inline is the absence of the raise that was
priced — the Peak-Cycle Buyside-Inline Fade rule extended from category level to
outcome level. Cohort context only, never folded into the score, same discipline
as the positioning line.

This also confirms the earlier absence-is-0.0 fix: absence-of-guide (n=5, mean
−7.32%) and inline-at-expectations (n=6, mean −6.45%) are statistically
indistinguishable at this n, so scoring both 0.0 is safe.

### The widened bracket

`evaluate` needs all three of CQ / NextQ / FY, which is what the published base
rates were measured on. When a category defers, `evaluate_partial` generalises
the same exact arithmetic — `swing = sum of unknown weights x 2` — and marks
`cohortApplies: False` with no base rate attached, so the published rates are
never misapplied to a wider bracket.

### One derived rule, flagged on every card

The published band table has no row for "clears bogey 0–2% with ≥2 flags", which
is exactly where SNDK-2026Q4 (+1.0) sits. The rule that reconciles the table
with the pinned grades is

```
score = base_band − 0.5 × max(0, flags − band.maxFlags)
```

| record | hero clearance | base | flags | result | pinned |
|---|---|---|---|---|---|
| TSLA-2026Q1 | +6.67% vs bogey | +2.0 (max 0) | 0 | **+2.0** | +2.0 |
| SNDK-2026Q4 | +0.71% vs bogey | +1.5 (max 1) | 2 | **+1.0** | +1.0 |
| CSCO-2026Q4 | +2.53% vs cons | +2.0 (max 0) | 2 | **+1.0** | +1.0 |

This is an **inference, not a documented rule**. It is isolated in
`score.DERIVED_STEP_DOWN`, surfaced on every card as `stepDownApplied`, and
shown in the pop-up in purple so it gets reviewed rather than trusted.

### Flags the release cannot settle

Three of the seven offsetting flags need data a press release rarely carries —
segment sequential detail, price-vs-volume split, ARR/RPO versus order growth.
Those are reported as **NOT ASSESSABLE** on the card rather than assumed absent,
because an unassessed flag can move the band.

## Error classes enforced

- **D5 — never infer from plausibility.** `revUnit` is null on 7 of 76 records.
  Parsed actuals normalise to $M, so grading revenue needs the stored unit; when
  it is null the scorer **refuses that line** and says so.
- **D5, again, at KPI level.** The unit lives in the KPI *name*, and within one
  row the bogey and the stored actual can disagree: SNDK keyKPI[0] is
  `FQ4 Revenue ($B)` with bogey `9.5` against a stored actual of `8965` — $B
  versus $M. Compared raw, a **−5.6% miss reads as a clean clear**. Every row
  resolves its name's unit before comparing.
- **D6 — units mismatches.** Any computed percentage beyond ±300% is suppressed
  and flagged.
- **Definitional mismatch / forward slots.** A `CURRENT_Q` parse may only fill a
  `CURRENT_Q` slot. The documented FY/Guid word test is **not sufficient**:
  CSCO-2026Q4 carries `Q1 FY27 Non-GAAP Gross Margin (%) ★★`, which contains no
  "Guid" and so classifies as current — binding the graded metric to next
  quarter's guide. Period *tokens* are also compared against the record's own
  quarter.
- **D3/D7 — GAAP vs non-GAAP.** Parsed into separate fields, never merged; the
  spread is reported, and a basis gap that flips the sign versus consensus counts
  as an offsetting flag.
- **Alignment.** `actuals.keyKPIs` is built by iterating `preEarnings.keyKPIs` in
  stored order; unresolved slots get placeholders, never skips. A length mismatch
  raises `AlignmentError` and **no card is emitted** — the silent failure that
  broke 12 records while the render test passed.
- **The status trap.** `status` is compared case-insensitively; a lowercase
  `pre-earnings` is still indexed.
- **`score10` vs `score10Estimate`.** Read in that order, and a partial estimate
  is labelled with its `componentsScored` so a 1/6 never displays as 6/6.
- **Verdicts.** Only renderer-recognised strings are emitted.
- **Positioning** never enters `scores.overall`; `adjustedScore` is separate.

## The card comes from ONE renderer

```python
from earnings_scraper import scorecard
text = scorecard.render_card(card, entry, framework)   # verbatim
```

**There is no formatter in this package.** The scraper builds a record dict,
calls `render_scorecard.render(rec, framework)`, and emits the result verbatim.
`render_scorecard.py` is loaded from the model repo by **absolute path** — not
copied — for the same reason the library is.

A second formatter would drift from the chat path within a print or two, and the
whole point of the locked format is that identical input gives byte-identical
output on both paths. `test_scorecard.py` asserts exactly that against
`py render_scorecard.py SNDK-2026Q4`, so growing a parallel formatter breaks the
suite.

The pop-up displays that text in a monospace widget and paints lines by leading
marker; it builds no layout. Everything it used to assemble by hand — hero table,
the four categories, the KPI grid, the gate block — was a restatement of exactly
this text.

**Left for the call, rendered as explicit markers:** narrative score, the four
one-sentence reads, key takeaways. `summaries` is passed `{}`, `takeaways` `[]`
and `scores.narrative` `None`, so render() emits `⟨DEFERRED — needs the call⟩`
and `⟨one-sentence read not supplied⟩` rather than blanks or invented prose.

Three details from testing, all pinned:

- **Flags sit on either side of the pre/actual pair.** `unverified` and
  `unitAmbiguous` are mirrored onto both sides of every row before rendering,
  because render() checks either and the library carries them either way.
- **`_display_actual` prints the unit the row NAME declares.** SNDK stores
  `8965` (`$M`) under a `($B)` name; printing that raw beside a `9.50` bogey is
  the exact misread that broke the AMZN clearance. The row shows `8.97 ($B)`.
- **Prose columns are capped.** SNDK's LTA row stores whole sentences in the
  street and bogey slots. Capping holds street/bogey at fixed 10-wide offsets
  ([44:54] and [55:65]) on every row including the prose one — one uncapped cell
  shifts every column to its right.

### Diagnostics are additive, never a restatement

Appended *below* the rendered block, so the rendered region stays byte-comparable
to the chat path: HARD 10 findings, precedence-rule detail and its post-hoc
caveat, the clearance-leg basis, offsetting-flag counts, the not-assessable list,
problems and deferrals.

### Precedence is passed in, never re-derived

`render(rec, framework, precedence)` takes the gate's verdict as a third
argument:

```python
{"rule": 1, "verdict": "REINFORCES", "overridesNovelty": True, "detail": "..."}
```

The gate owns the logic; render only displays it. On a rule-1 record the novelty
line is struck:

```
forwardCommitment.novelty = NEW → SHORT VOID — long permissive, unsized (n=5)
⛔ OVERRIDDEN by precedence rule 1: REINFORCES
   cyclical sector (Semiconductors / Memory) · peak-cycle language: "…peak-cycle
   buyside-inline fade…" · inline vs bogey −5.58% · clearance leg via the
   dollar ★ row FQ4 Revenue ($B) ★ (declared $M)
   → PEAK-CYCLE FADE WINS. The short STAYS LIVE. Ignore the novelty line above.
```

Pass nothing and render prints **`⚠ PRECEDENCE NOT EVALUATED — this line is
UNQUALIFIED`**, so a bare `SHORT VOID` can no longer render silently on a record
where rule 1 fires. `precedence_from_card` returns `None` only when the gate
genuinely did not evaluate precedence — every novelty class except `NEW` never
reaches the peak-cycle legs.

### No branch is claimed — by design, permanently

The scraper passes `branchMatched=None` even when a ladder exists, so render
prints `⟨none recorded⟩`, and the reason goes to diagnostics. This is the
permanent state of the PR-only path, not a stopgap.

`branchAccuracyLog`, both windows:

| | result |
|---|---|
| direction correct | **6 of 7** |
| trigger identification | **3 of 3** |
| magnitude inside range | **0 of 7** |

Direction and trigger are the parts that work, and both already come from the
fundamental scorecard on the card at 4:01. Positioning **component 3**
(print-day move ÷ implied move) feeds only the **magnitude** estimate — the one
output that has never landed inside its range.

So the scraper takes **no price dependency**. Fetching an official close would
buy the model's weakest output at the cost of a network call on the hot path, and
the cheap version is forbidden anyway: LESSONS A2 rules out an intraday snapshot,
and the two locks set from one poisoned the whole read — SNDK's +10.65% snapshot
against a −5.40% verified close forecast −12% to −20% on a print that fell 6.81%.

render() now handles a null `branch` itself, so the earlier workaround here is
gone.

If `render_scorecard.py` cannot be loaded, the card reports
`⛔ RENDERER UNAVAILABLE` and **no local formatting is attempted** — that refusal
is the drift guard.

## HARD 10 — domain-implausible expected values

```powershell
py -m earnings_scraper audit
```

HARD 8 and HARD 9 compare bogey against consensus, so they are **blind** when
both columns are wrong *and mutually consistent*. That is the SNDK signature:
FQ4 GM bogey 84.0 / consensus 81.5 for a memory semi, internally consistent
across all six numeric rows — a systematic transposition, not a typo. Internal
consistency is not plausibility.

HARD 10 tests each expected value against what the metric can physically be for
that sector. It runs on every graded card and surfaces as a red banner.

It **flags, never corrects** — an implausible expectation is marked unverified
for a human to re-source, because guessing the intended figure is the same class
of error as inferring a missing unit.

Bands are sector-conditioned, and deliberately wide. Getting the ceiling wrong
in the other direction is what makes a check like this useless: a flat 70% cap on
EBITDA margin flags AppLovin's genuine 85% (81% the prior year) as an error, and
Cisco's real 66.3% gross margin must not flag either. Current audit: **4 findings
on 1 record of 76** — SNDK only.

## Nothing is written to the library

Cards are written as sidecars to `earnings_scraper/state/pending/`. The library
is only written after both gates pass:

```powershell
py validate_library.py    # must exit 0
node render_test.js       # 0 card / 0 openModal / 0 setTab failures
```

## Calibration warning shown in the UI

Branch magnitude calibration is **0 of 3** forward-written and **0 of 4**
backfilled, while direction and trigger identification are 3 of 3. Any
`expectedReaction` is therefore labelled a **framing range**, never a forecast,
and most matrix cells are n=1–3.

## mode='full' is mandatory

Verified against the captured `news.log`: in headlines mode wire items carry no
`body` at all — 0 of 641 lines had one — and the `teaser` truncates at ~140
characters, mid-sentence, before any figures. `listener.subscribe` raises on any
other mode.

## What the feed forces on the design

- **No earnings topic code exists.** PRN tags items `prel`/`sn`/`pr`,
  BusinessWire `cw`/`company_announcement`, Globe Newswire `cnw`. Detection is
  headline + body driven.
- **`primary_instruments` is frequently empty**, so ticker resolution falls back
  to exchange tags then company-name matching against the watchlist.
- **Signal is sparse.** 1 real earnings release in 91 wire items; 12 were
  class-action notices. `"EHang to Report Q2 Results on August 25"` is a
  scheduling notice and must never fire — the discriminator is that a real
  release *states figures*, since a genuine one also says "will host a call".

## Tests

```powershell
py tests\test_detect.py      # detection + ticker resolution, real log cases
py tests\test_parse.py       # parser, against real CSCO figures
py tests\test_score.py       # scoring primitives, units, bands, the ceiling
py tests\test_regression.py  # pins the rules against the LIVE library
py tests\test_pipeline.py    # wire -> card end to end, on a fixture card
```

`test_regression.py` also asserts the one invariant that must hold:
`calibration.json.recordsUsed == the half-step pinning-set size`. Counts move —
trust the live file over any doc. **If they diverge, regenerate the calibration
rather than adjusting the tests.**
