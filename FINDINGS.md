# FINDINGS — the shapes this build keeps producing

Not a changelog. Each entry is a defect *shape* with its instances.

---

# PART I — PROTOCOLS

> **EVERY RULE IN THIS FILE HAS BEEN VIOLATED BY ITS OWN AUTHOR.
> NO PROTOCOL HAS BEEN.**
>
> **A RULE is a test you must remember to apply, and you remember when you
> are uncertain. A PROTOCOL is a step you run before knowing whether you
> need it.** Confidence is the OCCASION.

> ## ★★★★ THE DESIGN CRITERION: DOES FOLLOWING IT LEAVE AN ARTIFACT?
>
> **The artifact is the MECHANISM.** An artifact leaves evidence someone
> else can check, cannot be satisfied by believing you did it, and **its
> absence is detectable**. A judgement leaves no residue proving it was
> skipped.
>
> **If following a candidate protocol leaves no artifact, it is not a
> protocol — it is a rule, and it will be violated when its author is
> confident.** Test every new one against this before writing it down.
>
> Every protocol below produces one: a diff, a snapshot, a document
> excerpt, a red gate, a list, a named junction.

| # | protocol | run it |
|---|---|---|
| P1 | **TRACE FROM THE DOCUMENT** — open the release and find the figure before reading any code or any refusal reason | before diagnosing any refusal |
| P2 | **THE ONLY FAITHFUL PROBE OF AN EDIT IS THE EDIT** — apply, snapshot, revert, diff. A monkeypatched stand-in is a fifth frame | before quoting any delta |
| P3 | **REPORT-ONLY ON THE REAL EDIT, THEN REVERT AND CONFIRM THE TREE IS CLEAN** | before landing any reader change |
| P4 | **REVERT-AND-DIFF BEFORE ATTRIBUTING** — a recent visible change is the cheapest explanation for any metric move, and latent defects are invisible by construction | before blaming anyone's change |
| P5 | **DRIVE THE GATE RED** — an instrument is trustworthy only once it has been made to fail on purpose. Where it cannot be driven red, say so instead of reporting it green | before trusting any check |
| P6 | **NAME THE SAMPLE FRAME BEFORE QUOTING THE NUMBER** — and check the input size before explaining a surprising count | before quoting any number |
| P7 | **POISON THE BOUNDARY** — replace every field on the far side with an absurd value and confirm nothing moves. Grepping for names proves nothing about a path that builds a key dynamically | before claiming a boundary holds |
| P8 | **ASSERT THE BEHAVIOUR, NOT THE STRING** — *"every module that does X imports the canonicaliser"*, never *"no site mishandles `basis`"* | when writing any negative assertion |
| P9 | **BEFORE EXCLUDING A REGION, LIST WHAT LIVES INSIDE IT** — *"exclude this section"* conflates *do not match labels here* with *do not take values here*, and for a reconciliation block the correct answers are opposite | before any exclusion |
| P10 | **STATE THE ACCESS/INFORMATION TYPE AND THE JUNCTION** — naming the fact is not naming the fix. If no junction can be named, it is a trace request, not a prediction | before any access hypothesis |
| P11 | **WAS THIS FACT EVER COMPUTED ANYWHERE IN THE CALL PATH?** — and, for the author: does the code already implement this rule? | before writing any new rule |
| P12 | **BUCKET ON THE RICHEST AVAILABLE FIELD, NOT THE CHEAPEST** | before reporting any tally |

**P9 and P10 are new.** They are the protocol forms of two rules that were
violated by their authors: *"exclusion is two operations"* and *"price
jointly"*. Two others were already converted — *"a consistent reason and a
true reason are different claims"* became **P1**, and *"a name is not a
type"* became **P8**.

---

# PART II — RULES

Not a changelog. Each entry is a defect *shape* with its instances, kept
because every one of them recurred after being fixed once.

---

## ★★★ 1. THE DISCARD PATTERN — the correct answer is computed and thrown away

> **This codebase repeatedly computes the correct thing and throws it away
> before anyone can read it.** Every major fix in this stretch has been
> RECOVERY OF INFORMATION THAT ALREADY EXISTED, not new derivation.

| # | what was computed | where it was discarded |
|---|---|---|
| 1 | `sub_state` | computed, returned to nobody |
| 2 | the library `scraperRead` column | written by a scratchpad no gate invokes |
| 3 | `refresh_agreement` | recompute works, value never written |
| 4 | `pos` | cell coordinate computed by the grid, discarded before `provenance()` |
| 5 | the cell description `Q3 26 \| Non-GAAP` | computed by the grid, discarded at the same step as the coordinate |
| 6 | sgrid's `labels[i]` — the basis GROUP the chosen cell is in | returned the group **list** instead, so an audit found 'non-GAAP' in it whatever cell was picked: **false** evidence, not weak evidence |
| 7 | vtables' `classes[i]` — the selected column's period | classified every column since vtables was written, returned as a list, never indexed |

**STANDING TEST, before writing any new extraction logic:**

> **WAS THIS FACT EVER COMPUTED ANYWHERE IN THE CALL PATH?**
> If yes it is a **discard**, not a gap — and the fix is a **signature
> change**, not a new rule.

A parsing problem is fixed by better parsing. **A discard problem is fixed by
plumbing**, and it is cheaper, because the answer is already in the process
one frame up.

---

## ★★★ 2. PRECISION SHOULD LOWER THE SCORE

> **A measurement change that improves accuracy should be EXPECTED to lower
> the score. If precision makes a number go up, suspect it.**

Founding case, 2026-09-25. `pos` was moved from the row that matched to the
cell that was selected — strictly more accurate provenance. The audit got
*emptier*: basis evidence 1 → 0, all-vacuous MATCH rows 7 → 8.

**THE AUDIT GOT EMPTIER BECAUSE THE POSITION GOT MORE ACCURATE.** The first
number in this build to fall for a good reason.

---

## ★★★ 3. IN A TABLE, STRUCTURE CARRIES PERIOD AND BASIS — AND TEXT DOES NOT

> **"a cell is surrounded by digits, the words are in the header, and
> `_governing_sentence` cannot reach a column header from any position, at
> any offset, ever."**

A proof, not an observation. Every vocabulary built in this project is
textual, so every check built on `_governing_sentence` is structurally
incapable of verifying a table cell.

Consequence measured 2026-09-25: the basis check, which guards the most
expensive failure mode in the project — **CBRS, GAAP −7.0% while a
company-defined "core" beat +9.9%, and the tape traded GAAP** — has
**evidence on zero rows** and always did.

---

## ★★★ 4. CLOSURE CONFIRMS A VALUE, NOT A MECHANISM

**A row that is right by luck is worse than a row that is wrong, because
nothing will ever flag it.**

Founding case: **AVGO-2026Q3[8], Q3 Non-GAAP EPS, reclassified four times.**

| reading | verdict |
|---|---|
| false green | wrong |
| double-occurrence collision | wrong |
| genuine MATCH, grid-selected | not quite |
| **TWO ERRORS CANCELLED** | **the answer** |

`hgrid` was handed independently-stripped lines. AVGO's basis header sits at
indent 36, its rule at 25, its data row at 1 — three shifts on one table.
`GAAP` landed **by arithmetic coincidence** on the column that *is* GAAP,
`Non-GAAP` fell off the right-hand end entirely, and the correct column
survived the basis filter **as UNLABELLED rather than as MATCHING**, because
the filter keeps a column whose basis is `None`.

3.32 was right, and stayed 3.32 after the fix. **The assertion is not the
value — it is the transition from right-by-cancellation to right-by-evidence,
observable only in the cell description.**

---

## ★★ 5. REPORT-ONLY IS THE STANDING PROTOCOL FOR ANY READER CHANGE

**Apply → measure verdict/value/position deltas corpus-wide → revert →
confirm the tree is clean → then decide.**

It is what makes *"the defect is latent, not active"* a finding rather than a
hope. Most late-discovered regressions in this build were changes that
**MOVED** something rather than **FIXED** something.

**And name the sample frame before quoting the delta.** Zero-move on one
document is not zero-move on the corpus. The unstrip measured 0 of 102 rows
moving — but six of eight releases carry no indentation at all, so stripping
was a no-op there and the entire question lived on **two documents**.

---

## ★★ 6. A CHECK THAT APPLIES IS NOT A CHECK THAT CAN FAIL

Report coverage as **evidence-bearing rows**, never as declared rows. Every
extractable row *declares* a period; that is exactly why "all 34 have a live
period check because every row declares one" proved nothing.

    MATCH 34 = 26 with >=1 DISCRIMINATING check + 8 ALL-VACUOUS
    evidence-bearing rows: fence 20 - period 14 - basis 0

---

## ★★★ 7. A CHECK THAT **ACCEPTS** ON MISSING EVIDENCE CANNOT FAIL WHEN IT HAS NONE

`column_basis` returned `None` on an unlabelled column and the filter kept it
— `(column_basis(desc) or want) == want`. **Basis was not a weak instrument.
It was a no-op that reported as a check**, which is why `FALSE_MATCH 0` was
never news. All three checks defaulted to accept.

**And the semantics of absence change the moment the instrument works:**

| | absence means |
|---|---|
| before `cellAxes` | **we are blind** |
| after | **the column is genuinely unlabelled** — a fact about the document |

Landing the instrument without changing the default is building the
instrument and keeping the blindfold. **RULING, in the same commit:**

```
priority-1 hero + basis declared + column carries no basis word  ->  REFUSE
lower priority,  same conditions                                 ->  ACCEPT AND FLAG
```

Never accept silently. That is **the SNDK principle: on the row that decides
the trade, a refusal beats a wrong number.**

Each check now reports one of three states, and coverage is counted in
**EVIDENCE** rows only:

```
EVIDENCE   it had something to read and could have failed
ABSENT     the column exists and carries no such word
VACUOUS    nothing readable at all — blind, and saying so
```

---

## ★★★ 8. COORDINATES THAT DO NOT CARRY THEIR FRAME

Three instances, one shape. An integer position is meaningless without the
frame it was measured in, and the frames are **raw · dewrapped · stripped ·
kept** — with a monkeypatched stand-in as a fifth.

| # | what happened |
|---|---|
| 1 | `dewrap` — `pos` emitted in dewrapped space, persisted as original (AVGO 21.7 at 1541 against a true 1635) |
| 2 | `cell_offset` — indent added twice, `pos` one character right of the figure |
| 3 | the probe — `label_idx` from **dewrapped** space handed to a **raw** document, and it reported the **exact opposite** of the true result |

Vigilance has failed three times here and will fail again. **The fix is a
type: positions carry their frame, and a cross-frame use becomes a type error
rather than a plausible number.** Not urgent — on the list before a fourth
one lands somewhere it is not tested the same day.

**"THE ONLY FAITHFUL PROBE OF AN EDIT IS THE EDIT."** A monkeypatched
stand-in is a fifth frame. Adopted permanently.

---

## ★★★ 9. A CHECK THAT CONSULTS THE **POPULATION** INSTEAD OF THE **SELECTION**

Subtler than "the digits agree". That one compares the *wrong thing*; this one
compares against **everything**, so it cannot disagree.

Founding case: `sgrid` returned `groups` — the list of basis groups that
**exist** in the block. An audit reading it found `non-GAAP` among them
**whichever cell had been picked**. It reported `AGREE` on SNOW[5] and
SNOW[8]: not weak evidence, **false** evidence.

> **STANDING TEST FOR EVERY CHECK: WOULD ITS ANSWER CHANGE IF A DIFFERENT
> CELL HAD BEEN SELECTED?** If no, it is decorative regardless of how often it
> passes.

Run against all three checks, 11 grid-read rows, 33 sibling cells:

| check | discriminates between cells of the same row |
|---|---|
| `fence` | **0 of 11** — row-level, not cell-level. It can catch a value taken from the wrong *section*; it cannot catch a wrong *cell* |
| `basis` | 3 of 11 |
| `period` | 9 of 11 |

**And the instrument that runs this test was itself decorative twice before it
worked.** First it compared the check's *state* — a GAAP sibling and a
non-GAAP sibling both report `EVIDENCE`, so nothing ever moved. Then it ran
the stacked branch on vertical rows and relabelled period classes as basis
groups. Both versions produced clean-looking numbers.

---

## ★★★ 10. WHEN A FIELD CAN BE EMPTY FOR TWO REASONS, IT NEEDS TWO EMPTIES

`★theFourthState`, third instance. `basis = None` conflated:

| state | meaning | who it is about |
|---|---|---|
| `ABSENT_IN_DOCUMENT` | the grid ran, read the headers, found no basis word | **the release** |
| `UNREAD_BY_GRID` | the reader failed, or never looks for a basis at all | **us** |
| `NOT_DECLARED` | the spec never asked | the card |

They warrant **opposite responses**. Refusing a priority-1 hero because the
issuer printed no basis is the SNDK principle. Refusing it because *our own*
vertical reader never looks for a basis header would publish **a refusal with
false provenance** — worse than the defect the ruling exists to prevent.

The split immediately reclassified the corpus's only `ABSENT` row: HPE[16] is
`UNREAD_BY_GRID`, because `vtables`' strata are period classes and it never
looked for a basis at all.

---

## ★★★ 11. FALSE_MATCH FIRES — CALIBRATED BY INJECTION, ON A REAL ROW

`FALSE_MATCH` read 0 across every sweep, and a verdict that never fires looks
exactly like one that passes. The audit has **no confirmed positive** —
AVGO[8] was reclassified four times and ended as right-by-cancellation.

The sibling-cell audit found **no natural target**: across 11 grid-read rows
and 33 siblings, no cell's digits coincide with the selected one while its
axes differ. So the injection forges the coincidence on a real document:

```
HPE Q3 Revenue, real:    12,213 REPORTED · 10,678 SEQUENTIAL · 9,136 PY
forged (a flat year):    12,213 REPORTED · 10,678 SEQUENTIAL · 12,213 PY
```

**A flat year is not an exotic document.** It is one character of edit, and it
is what half the corpus looks like in a downturn — exactly when the wrong
column stops being detectable by magnitude.

| controls, disabled separately | verdict |
|---|---|
| forge the digits, do **not** force the column | `MATCH` — no fault |
| force the column, do **not** forge the digits | `MISMATCH` — caught by digits |
| **both** | **`FALSE_MATCH`** |

The value it would have published is `12.213` — **indistinguishable from the
correct answer by magnitude**, which is the whole reason the verdict exists.
The fixture on disk is never edited; the forge lives in memory.

---

## ★★★ 12. AN INSTRUMENT IS TRUSTWORTHY ONLY ONCE IT HAS BEEN MADE TO FAIL ON PURPOSE

Not "it passed". **Revert the condition and watch it go red.**

The regress is real and has no bottom by observation: `pos` needed a test, the
sweep needed a reconciliation, and the standing test for decorative checks
needed **three versions** — two of which produced clean-looking numbers.

> **A GATE NEVER DRIVEN RED IS AN UNVERIFIED CLAIM ABOUT A VERIFICATION.**
> Where a gate *cannot* be driven red, say so explicitly rather than reporting
> it green.

Forced failure is the terminator. It is the only reason `FALSE_MATCH` firing
means anything, and every reader guard in `test_crash_safety.py` is driven
red — including a check that the unguarded call genuinely raises, so the guard
is demonstrably what caught it rather than luck.

---

## ★★★ 13. WE HAVE BEEN HUNTING FALSE GREENS. **A FALSE REFUSAL** IS THE OTHER ONE

`vtables`' strata are period classes — it never looks for a basis header at
all. The strict arm would have blanked a **priority-1 hero** for a header
**our own reader never read**.

**Blindness misattributed to the issuer, wearing the costume of caution.**
Mid-print on a hero row it costs the read outright, and it is invisible
because refusals are *supposed* to look like that.

> `ABSENT_IN_DOCUMENT` must require **positive evidence that the reader
> looked** — never merely that it returned nothing.

`hgrid` claims it only where header text was actually resolved for that cell.
`sgrid` **never** claims it: its groups come from a lookback search, and a
lookback that finds nothing cannot tell *"the issuer printed no basis header"*
from *"the window was too short"* — the same reason a span needs a CLOSE, not
a LENGTH.

---

## ★★★ 14. A REFUSAL COSTS ONE CELL. AN EXCEPTION COSTS THE WHOLE CARD

**Which code paths get exercised is decided by which eight issuers we happened
to spec.** `block_cells_at` dropped the line index on the bare-`%` marker
path; SNOW attaches its percent to the figure so the corpus never reached it,
and SNDK and APP use the bare marker. It would have surfaced as an
`IndexError` **on a live print** — a ninth document, mid-print, on the card
that is needed right then.

Five reader call sites are guarded, plus an outer boundary on `value_for`, so
whatever escapes costs **one row**. The guard is **loud**: `readerCrashed` is
set and the refusal names the reader and the exception, because a blanket
try/except that swallows everything is how a defect lives for a year.

**And the pass found its own first defect.** A guard that lets execution fall
through to a less-specific reader converts a crash into a **wrong value**:
with `sgrid` raising, SNOW published **70.9 GAAP in place of 74.7 non-GAAP** —
the CBRS failure mode, delivered by the safety net. A basis-declaring row now
refuses rather than dropping through to the basis-blind prose pool.

---

## ★★★ 15. TWO INSTRUMENTS, TWO NUMBERS — NEVER ONE SUM

```
ROW-LEVEL  evidence:  fence 18              "taken from the right SECTION"
CELL-LEVEL evidence:  period 18 · basis 3   "the right CELL"
```

Summing them is the same category error as summing DECLARED with EVIDENCED:
two instruments answering different questions, added because both return a
boolean.

---

## ★★★ 16. ONLY ONE VERDICT LEAVES THE DENOMINATOR

`EXCLUDED` was doing four jobs. A row nobody ruled on is not an excused row.

| verdict | meaning | in the denominator? |
|---|---|---|
| `EXCLUDED` | closed list: `NOT_IN_PR` · `CALL_SOURCED` · `QUALITATIVE` | **no — the only exit** |
| `UNSPECD` | `NEEDS_REMAP`: issuer changed disclosure, our spec is stale | **yes — our gap** |
| `UNCLASSIFIED` | `NOT_EXTRACTABLE` for a reason not on the closed list | **yes — nobody ruled** |
| `NO_ANSWER_KEY` | a value was read, no hand read to compare | **yes — its own verdict** |

```
MATCH 34 · FALSE_MATCH 0 · MISMATCH 1 · LOST 0 · REFUSED 41
· UNSPECD 3 · UNCLASSIFIED 4 · NO_ANSWER_KEY 0 · EXCLUDED 19
[all 102 rows shown of 102; GRADED POPULATION 83 — only EXCLUDED leaves it]
```

EXCLUDED fell **26 → 19**. The seven that came back are ours.

---

## ★★★ 17. A FALLBACK MAY BE LESS CAPABLE. IT MAY NEVER BE LESS DISCRIMINATING

> **Degradation loses CAPABILITY, never CONSTRAINTS.** If a row declares
> basis / period / currency and the specialist was chosen **because** of that
> declaration, the fallback honours it or refuses.

Founding case: with `sgrid` raising, the crash guard dropped through to the
basis-blind prose pool and SNOW published **70.9 GAAP in place of 74.7
non-GAAP**. The safety net was delivering the failure mode it exists to
prevent. A crash costs one cell and announces itself; that cost the read and
hid inside a green cell.

**Not yet audited across the other fallback chains, on any axis.** Queued.

---

## ★★★ 18. A NEGATIVE FINDING FROM A BOUNDED SEARCH DESCRIBES THE BOUND

> Only an **exhaustive** or **explicitly terminated** search may assert
> absence.

`a-span-needs-a-CLOSE-not-a-LENGTH`, applied to an absence claim. `sgrid`
finds its basis groups by lookback, so it may never report
`ABSENT_IN_DOCUMENT` — a miss there cannot be told from a short window.
**To be checked wherever else we assert a negative.**

---

## ★★★ 19. AN EXCLUSION IS A DOCUMENT FACT OR A DELIBERATE POLICY

Anything that is a fact about **our card** is a defect and stays in the
denominator.

| row | ruling | in? |
|---|---|---|
| AVGO[12] Buyback | `EXCLUDED` / **`NOT_AUTOMATABLE`** — POLICY. The number *is* there and we choose not to take it (CLAUDE.md's cash-flow rule, founding case SNDK's $93.9B backlog). Never recorded as a document fact | out |
| AVGO[17], AVGO[18] | **`CARD_DEFECT`** — "INVERTED" means two different things | **in** |
| HPE[6] derived % | **`UNSPECD`** — derived-but-unsupported is unfinished work, identical in kind to `NEEDS_REMAP` | **in** |
| HPE[17] | **`CARD_DEFECT`** — a duplicate slot guarantees one of the two is wrong or blank | **in** |

**`oneConditionTwoNames`, n=15** — and this one is in the library, not the
code:

```
AMZN[5]            "inverted polarity"  = a SCORING SEMANTIC  -> HONOUR it
AVGO[17], AVGO[18] "INVERTED ROW"       = a DATA DEFECT       -> REPAIR it
```

Same word, opposite handling, and AVGO[18] is a ★★★ hero. **Neither is graded
until the split lands.** HPE[17] is a *semantic* duplicate, invisible to the
name-based duplicate check — so that class has no count.

---

## ★★★ 20. THE OPERATION IS READ OFF THE RECIPE, NOT ASSUMED TO BE THE ONE THAT EXISTS

The ratio path was the only derived path, so HPE[0] — a **PRODUCT** row —
had nowhere to go and refused with *"no candidate matched the declared
unit"*: **a refusal that described the wrong failure entirely.**

```
FY26 non-GAAP EPS guide    $3.75 to $3.85   (card row [3])
FY27 EPS growth framework   16% to 20%      (this release RAISED it from 12-16%)
->                         $4.35 to $4.62   midpoint 4.485
```

Exactly the two endpoints the card reached by hand.

**And the spec says `PRODUCT` while the arithmetic is a compound.** A literal
product is `3.75 x 0.16 = 0.60`. The operation performed is
`base x (1 + growth)`. Rather than silently reinterpret an authored word, it
is named `GROWTH_COMPOUND` and the discrepancy is recorded in `derivedFrom`.

---

## ★★★ 21. A DERIVED ROW'S VERDICT IS CAPPED BY ITS WEAKEST OPERAND

```
HPE[0]  published 4.485 as MATCH, derived from the FY26 EPS guide $3.75-$3.85
HPE[3]  IS THAT GUIDE — and it REFUSED
```

**Same figure, same document, same card: published via derivation, refused
via direct read**, and nothing on the card could see the disagreement.
`oneConditionTwoNames` **n=16**.

```
derived.verdict = min(operand verdicts)
an operand that is REFUSED / FALSE_MATCH / UNSPEC'D cannot yield MATCH
```

**It ships with derivation coverage, not after it.** Every derived row is an
all-vacuous MATCH — fence, basis and period have nothing structural to read on
a computed number — so **growing derivation grows the un-auditable set.** A
capability that increases the count of rows nothing can check is a liability
on its own terms.

The cap governs the *verdict*, not the arithmetic: 4.485 and both operands
stay on the card. HPE[0] flipped MATCH → REFUSED and the all-vacuous set fell
6 → 5.

★ And it exposes something about the derivation itself: HPE[0]'s base operand
resolves from **the endpoints written in the `sourceRow` string**, not from
re-reading row [3]. It trusts the author's prose over the extractor. The cap
is what makes that visible.

---

## ★★★ 22. THE EXPECTED COLUMN RECORDS WHAT WAS EXPECTED, NEVER WHAT IS NOW KNOWN

HPE raised the FY27 framework **inside** this release, 12–16% → 16–20%.
Street $3.93 and bogey $4.00 were computed off 12–16% **because that is what
the street modelled before the raise. THE RAISE IS THE SURPRISE.** Recompute
street to $4.35–$4.62 and the +14.5% beat vanishes.

> **An expectation corrected after the fact is not more accurate, it is
> destroyed.** Surprise is the only quantity in this model that trades, and it
> is the difference between two timestamps.

`street` / `bogey` on any scored record are **immutable**, short of a sourcing
error that predates the print. A stale-looking note is prose to fix, never a
number to recompute.

---

## ★★★ 23. A REASON THAT MISDESCRIBED ITS FAILURE ONCE IS NOT EVIDENCE ABOUT ITS NEIGHBOURS

HPE[0] refused with *"no candidate matched the declared unit"* **and the unit
was never the problem** — the PRODUCT path did not exist, so a compound row
had nowhere to go and the refusal named the wrong failure.

Three rows in the same document emit messages under that heading. Traced, they
are **three different failures**:

| row | stated | actual |
|---|---|---|
| HPE[3] | *2 candidates tie on unit and role* | the two candidates are **$1.20–$1.30 (the Q4 guide)** and **$3.75–$3.85 (the FY guide)**. The spec declares `period: GUIDE_FY` — **the declared axis could separate them, and the tie-refusal fires before it is consulted** |
| HPE[8] | *no candidate matched the declared unit '$'* | the label matches the **"Use of non-GAAP financial measures" boilerplate**, which names the metric and prints no number. A definition, not a data row |
| HPE[12] | *no candidate matched the declared unit '$B'* | the guide is a **floor** — *"at least $3.75 billion"* — while the label also hits the Q3 **actual** FCF line. Not yet fully traced |

**Spec against the traced failure, never against the stated reason.**

---

## ★★★ 24. NO VALUE AND NO REASON IS THE ONE STATE SIX VERDICTS EXIST TO ABOLISH

A blank with no reason is indistinguishable from a row nobody tried, a
swallowed crash, and a deliberate refusal. **The writer now raises rather than
writing it**, and the guard is driven red in the suite.

---

## ★★★ 25. THE OPERAND IS EXTRACTED, NEVER READ OUT OF THE REFERENCE

> **A derived value whose operand comes from the card's prose is the hand read
> with arithmetic applied. IT CANNOT DISAGREE.**

Same family as a check consulting the population instead of the selection —
**one level worse, because it produces a NUMBER and the number lands on the
card.**

`card_row_value` preferred the endpoints written in the `sourceRow` sentence
(*"HPE-2026Q3 [3] … the $3.75-$3.85 range"*) *because the referenced row might
be refusing*. That is precisely the case where it must not substitute.

**And the dangerous field was the helpful one.** That prose was written as an
aid to a human. **Every clarifying note is a latent answer-key leak awaiting a
reader capable enough to parse it**, so what is for humans and what is for
readers must be structurally separate. `sourceRows` must be a structured
reference — record id plus row index, or an extraction spec. **Never prose.**

**Boundary confirmed by poisoning, not by inspection:** every hand-read field
(`street` · `bogey` · `consensus` · `note` · `setup` · `actual` · `vsBogey`)
replaced with an absurd value across 35 extractable rows on 3 documents, 16 of
them producing a value — **no extracted value moved.** Grepping for field
names would prove nothing about a path that builds a key dynamically.

---

## ★★★ 26. HPE[3] IS THE PROSE TWIN OF THE TABLE PROBLEM — NOT AN ORDERING BUG

Measured two independent ways: **consulting the declared period before the tie
check resolves 0 rows, not 5 or 6.** (And there are **17** tie refusals
corpus-wide, not 6 — my earlier count was the basis-declaring subset.)

The reason the declared axis cannot separate them:

```
clause : 'HPE is raising both GAAP diluted net EPS to be in the range of
          $2.93 to $3.03 and non-GAAP diluted net EPS(1) to be in the range
          of $3.75 to $3.85.'
class  : GUIDE_NEXT_Q        <- WRONG, and identical for both candidates
basis  : INFERRED            <- so the filter may RANK, never EXCLUDE
```

The period is in the **section heading directly above** — `Fiscal 2026 Full
Year Outlook` — and `_governing_sentence` stops at sentence punctuation, so
the classifier never sees it.

> **In a document, structure carries period and the sentence does not.**

Exactly the table finding, one surface over. For tables the answer was
`cellAxes`; for prose the equivalent is the **section heading the clause sits
under**, which `section_spans` already knows how to find and the period
classifier has never consulted. **The discard register, by sequencing and by
signature at once.**

---

## ★★★ 27. THE SPECIALIST'S REFUSAL IS THE ANSWER, NOT A REASON TO TRY SOMETHING WEAKER

Finding #17 again, in the derived path. The derivation refused with *"the BASE
operand did not resolve by EXTRACTION"* and the label path below overwrote it
with *"no candidate matched the declared unit '$'"* — **the third time a wrong
reason has hidden the real failure.**

A derived row is **not in the document**, so the label path cannot be right
about it. A refusal reason is a diagnostic **no test asserts**; asserting that
the stated reason matches the branch that produced it is now on the list.

---

## ★★★ 28. THE SECTION HEADING IS THE PERIOD — THE PROSE TWIN OF `cellAxes`

```
'$1.20 to $1.30'   sentence GUIDE_NEXT_Q / INFERRED
                   heading  'Fiscal 2026 Fourth Quarter Outlook'
                   -> GUIDE_NEXT_Q, EXPLICIT  -> DROPPED

'$3.75 to $3.85'   sentence GUIDE_NEXT_Q / INFERRED    <- WRONG
                   heading  'Fiscal 2026 Full Year Outlook'
                   -> GUIDE_FY, EXPLICIT      -> KEPT
```

Both sentences classified **identically** and both were **INFERRED**, so the
declared axis could only rank. The heading makes the evidence **EXPLICIT**,
which is what licenses exclusion.

**The close is a close, not a length:** walking up, the *first* heading found
**is** the section, by definition.

> **ORDER AND EVIDENCE HAD TO LAND TOGETHER.** Consulting the declared period
> before the tie check moved **0 of 102** rows on its own. The heading alone
> changes no classification on any row that already resolves. Together they
> move HPE[3] and HPE[0] — both priority-1 heroes — from REFUSED to MATCH,
> and nothing else in the corpus moves.

Standing question applied first: `_PERIOD_PHRASE` existed, `section_spans`
existed but needs a *declared* anchor, **a prose heading detector genuinely
did not** — so only that part was new, and it was measured before wiring.

---

## ★★★ 29. DISCARD #10 — THE RANGE ENDPOINTS, DROPPED AT THE RETURN

The range arm carries `rangeLow` / `rangeHigh` with the comment *"Both ends
travel with it: a band is information the midpoint discards"* — **and the
final return dropped them anyway.**

So a compound derived from a range row squared a midpoint:
**$4.41–$4.56 instead of the true $4.35–$4.62.** The band the ladder grades
against was being destroyed one frame from the caller.

---

## ★★★ 30. RE-ENTRY IS THE CLOSE — `depth` CANNOT CROSS A MODULE BOUNDARY

`card_row_value` resolves an operand by calling `value_for`, which may derive
again. **`value_for` takes no `depth` parameter**, so counting frames guarded
nothing: a card row whose `sourceRows` pointed at itself would have recursed
until the interpreter gave up. **An exception costs the whole card.**

The guard is a set of rows *currently being resolved* — the cycle is detected
by **re-entry**, not by counting. Same shape as a-span-needs-a-CLOSE.

---

## ★★★ 31. SURFACE 3 — `ticker-profiles.json`

**A boundary test proves the boundary it crossed.**

| surface | status |
|---|---|
| library record hand-read fields | **proven clean** by poisoning |
| prose inside `extraction` | **was leaking** — closed |
| `ticker-profiles.json` notes | **fenced** (below) |
| anything else read at runtime | **enumerated: nothing.** No reader module opens a file |

`globalDocumentLabelMap` does live in that file beside 279 hero entries, **198
of which carry three or more figures in `notes`** — street levels, whispers,
bogeys, implied ramps; MDB's Atlas growth note carries thirty.

**But nothing passes `global_map`**, so the path is **latent, not active.**
Fenced anyway, because the `sourceRows` leak was also latent right up until a
reader became capable enough to parse it: `structural_only()` is an allowlist
of keys a reader may act on, and `prose_fields()` reports what it dropped so
the mixing stays visible rather than being silently discarded.

---

## ★★★ 32. PRICE IN ISOLATION TO AVOID WASTE — BUT A ZERO MEANS "WORTHLESS ALONE"

```
consult the declared period before the tie check, alone  ->  0 of 102
the section heading, alone                               ->  0 classifications
BOTH                                                     ->  two priority-1 heroes
```

An isolated ablation **cannot detect a fix whose two halves are each inert
alone.** Following the "worth nothing" ruling literally would have left both
rows refusing.

> **A fix that supplies ACCESS and a fix that supplies the INFORMATION are
> always a pair.** Neither moves a number without the other, and ablation
> scores both zero. Price them jointly or not at all.

When a price comes back 0, say what it would be worth **paired** before
dropping it.

---

## ★★★ 33. A SILENT BAND COMPRESSION IS A SILENT BRANCH REASSIGNMENT

The scenario ladder grades on numeric triggers **at band endpoints**. A band
collapsed to its midpoint moves those endpoints **inward**, so a print that
should match branch A matches branch B — **and the ladder still reports a
clean match.** That is a trade, not a rounding error.

> **A derived or guided band is published with BOTH ENDPOINTS, or the row is
> REFUSED. Never a midpoint alone.**

Wired at `value_for`'s outer boundary so it covers every return path;
`reasonCode: BAND_COLLAPSED`. 16 band rows publish both ends, 2 declare
`POINT` and have no band to lose, 0 reach the card as a bare midpoint.

---

## ★★★ 34. THE REFUSAL-REASON GATE — THE ONLY CLASS THAT SURVIVES A GREEN SUITE

The row refuses either way, the count is unchanged, the suite stays green,
and **the message sends the next person to the wrong cause.**

| row | said | was |
|---|---|---|
| HPE[0] | *no candidate matched the declared unit* | the PRODUCT path did not exist |
| HPE[3] | *candidates tie on unit and role* | the declared period would have separated them |
| derived | the unit was wrong | a generalist overwrote the specialist's reason |

It cost the HPE[3] ordering hypothesis and two traces, and the third instance
surfaced **while the test for the second was being written.**

**Prose cannot be checked; a code can.** Every refusal now carries a
`reasonCode`, and `reasons.verify()` **re-derives the claim from the
document** — a derived row may not blame the label path, a tie presupposes a
label hit, a PERIOD refusal presupposes a declared period. 39 refusals
checked corpus-wide, 0 misdescribed, and the sweep **refuses to write** a
misdescribed refusal.

**It matters most where we have no spec.** On an issuer nobody prepared,
refusals are the normal case, and a wrong reason is how a live mis-diagnosis
happens with the print moving.

---

## ★★★ 32 (REPLACES THE EARLIER FORM). A ZERO IS A QUESTION

The earlier rule — *"price them jointly where they address the same root from
different surfaces"* — **requires knowing they are a pair in advance, which is
the insight the measurement was supposed to produce.** The pair was found by
luck of sequencing, not by method. Neither of us gets to claim the method
caught it.

> **A ZERO IS A QUESTION: WHAT WOULD ALSO HAVE TO BE TRUE FOR THIS TO MATTER,
> AND IS IT TRUE TODAY?**
>
> **ACCESS fix** (ordering, sequencing, plumbing)
> → is the information it grants access to actually **correct** today?
> **INFORMATION fix** (a new classifier, a new evidence source)
> → can anything **reach** it today?

Retroactively: the reordering is an ACCESS fix, and *"is the declared period
ever classified correctly?"* answers **NO** — HPE[3]'s clause classifies
`GUIDE_NEXT_Q` for **both** candidates. **The pair was visible from the zero**
without the heading probe existing first.

---

## ★★★ 35. THE FALLBACK-CHAIN AUDIT — AND WHAT IT DID NOT COVER

63 (row × specialist) chains forced to fail across 8 documents and 5
specialists:

```
REFUSES when the specialist fails    28   correct
SAME VALUE from another path         35   benign TODAY
★ DIFFERENT VALUE                     0   no wrong number in green
```

**But the crash case is not the live case.** Forcing a specialist to *raise*
tests the crash guard. The generalised SNOW is the row that never reaches the
specialist at all: **6 rows declare a basis and take a PROSE value**, three of
them ★★★ heroes, with `basisCheck = VACUOUS` and nothing verifying the basis.

---

## ★★★ 36. A SUBSTRING TEST FOR A TOKEN WHOSE NEGATION CONTAINS IT

```python
has_non  = 'non-gaap' in low
has_gaap = 'gaap' in low        # ALWAYS TRUE WHEN has_non IS
```

Every non-GAAP-only clause therefore read as naming **both** bases, which the
check scores `VACUOUS`. **The basis check could never find non-GAAP evidence
in prose** — which is most of where it lives. Fixed with
`(?<!non-)(?<!non )gaap`. **Severity: MEDIUM-HIGH** — it publishes no wrong
number, but it is why basis evidence sat near zero.

---

## ★★★ 37. THE QUALIFIER LEADS THE VALUE — THE MIRROR OF THE CURRENCY RULE

`currency_spans` exists because a currency qualifier **trails** its figure
(*"13% growth, or 12% in constant currency"*, measured 29 to 4). A **basis**
qualifier **leads** it:

```
'Q1 GAAP earnings per share increased to $1.56, and non-GAAP earnings
 per share climbed to $1.92'
```

So the governing basis is the **last basis word before the value, inside its
own sentence**. The mechanism was built for one axis and never for the other,
which is why a clause naming both bases scored `VACUOUS` — **the discard
register answered this before any new rule was written.** Measured on the six
prose-basis rows: **3 AGREE, 0 CONTRADICT, 3 silent.**

Basis evidence: **0 → 3 → 5 → 8** across this session.

---

## ★★★ 38. `basis` CARRIES PROSE — SURFACE 2 WAS NOT FULLY CLOSED

```
ORCL[7]   basis = 'non-GAAP. ★ reconciliation row is RAGGED — header
                   declares 6 cols, row supplies 4 ...'
ADBE[12]  basis = 'non-GAAP ($2,974). ★ GAAP is $2,354 and appears FIRST,
                   in the SAME PROSE SENTENCE: ...'
```

**ADBE[12]'s `basis` field contains the answer.** My poison pass did not reach
it because `basis` is a *structural* key — on my own allowlist — and the leak
is prose **inside** a field a reader must act on. **I called surface 2 closed
and it was not.**

`basis_token()` reads the leading declaration defensively. **The field is
Kyle's to split. Severity: HIGH** — it is an oracle inside a key the matcher
consults.

---

## ★★★ 39. A BROKEN ESCAPE IS A SILENT REGEX

`\b` written through a shell heredoc became a literal **BACKSPACE** inside
`basis_token`'s pattern. The regex stopped matching, `_same_basis` returned
False, and **two rows reported `FALSE_MATCH` for a reason that was mine, not
the document's** — the verdict's first real fire was a false one.

Earlier patches asserted `chr(8) not in s`; later ones stopped. The assertion
is now a **repo-wide test**, with an anti-vacuous half proving the scanner can
see a control character when one is there.

---

## ★★★ 40. CAPABILITIES WERE BUILT PER-AXIS AND NEVER GENERALISED

Three separate findings are one finding:

| capability | existed for | missing for |
|---|---|---|
| whole-token matching | labels | **basis** → `'gaap' in low` |
| qualifier spans | currency | **basis** → nothing until this week |
| prose policing | `extraction` as a key | **`basis`, a key on the allowlist** |

**The axis with the worst historical cost in this project received the least
engineering.** That is why basis sat near zero all session while fence and
period climbed. **0 → 3 → 5 → 8** is the recovery.

**The predictive pass, run once as asked — no new gap.** `unit` looked bare on
a name-based inventory and is not: `denomination()` reads it from the table
header (18 of 37 values), `denominationFinding` records a disagreement with
`documentUnit` (5 rows), and `unitUnverified` flags the unchecked case (2
rows). **Differently-named mechanisms, same coverage.** `fence` is row-level
by nature — 0 of 11 on the sibling test — and gains nothing from a cell-level
mechanism. **We stop here.**

---

## ★★★ 41. AN ALLOWLIST BY NAME WAS THE VULNERABILITY

> **A FIELD IS STRUCTURAL BY ITS CONTENT, NOT BY ITS NAME.**

`structural_only` fenced the global map **by key** — and prose crossed into
`basis`, a key on that very allowlist. Six rows carried prose there and
**five contained the answer value** (ORCL[12]: `'non-GAAP (8,151)…'` against a
stored actual of 8.151).

`vocab.violations()` now validates every matcher field against a **closed
vocabulary**, and a violation refuses **one row** with `SPEC_INVALID` —
loudly, with its own code — rather than raising and costing the card.

**The first thing it caught: two spellings of one value.** `non-GAAP` on 14
rows, `NON_GAAP` on 5 — inside the field cleaned this week, and
`_same_basis` did not normalise underscores, so five rows failed the basis
comparison silently. `oneConditionTwoNames`, **n=17**. One canonicaliser now,
not a second normalisation rule. Library-wide violations today: **0**.

---

## ★★★ 42. THE DEFINITIONAL BLOCK — LABELS ONLY, CLOSED AT THE NEXT HEADING

> *"Exclude this section"* conflates **do not MATCH LABELS here** with **do
> not TAKE VALUES here**, and for the reconciliation block the correct
> answers are **opposite**: its labels are definitional noise, its values are
> the authority.

So `RECONCILIATION` is deliberately **absent** from the pattern, and the span
governs **label matching only**.

```
4 spans across 8 documents · digit density 0.0% – 0.6%
39 label hits fall inside, across 10 rows
0 of 102 corpus rows change value or verdict
```

The digit density **is** the check that no reconciliation table was caught:
a definitional block prints no figures. Worth more on a document nobody has
spec'd than on these eight — which is why it ships with a zero.

**It immediately made one reason true:** AVGO[6] moved `UNIT_MISMATCH` →
`NO_LABEL`. It was never a unit problem; its only label hit was in the
boilerplate. **And the reason gate caught itself going stale** — it still
counted those hits and called the new claim false, until it was taught the
same filter. A gate that drifts from its own reader is the thing it exists to
prevent.

---

## ★★★ 43. REVERT BEFORE ATTRIBUTING

> **Before attributing a regression to a change, REVERT THAT CHANGE ALONE
> AND CONFIRM THE METRIC RETURNS.**

MATCH fell 36 → 33 the moment Kyle normalised `basis` to `NON_GAAP`. I was
one sentence from reporting *"your cleanup cost three rows."* It did not: it
**exposed five call sites that were never consistent**, three of them masked
by a single spelling in the data. Had that stood, the fix would have been
reverted and five `basis` fields **containing the answer value** put back into
a matcher field — to protect three MATCHes that were never real.

**And it is systematic, not bad luck.** A recent, visible, plausible change is
the cheapest available explanation for any metric move, and latent defects are
invisible by construction. **The explanation that costs least to reach is the
one that gets reached.** Applies in both directions.

---

## ★★★ 44. A NAME IS NOT A TYPE — AND THE SOUND FORM OF THE ASSERTION

| | |
|---|---|
| **UNSOUND** | *"no site mishandles `basis`"* — requires knowing every site |
| **SOUND** | *"every module that compares a spec basis imports the canonicaliser"* + *"every spelling in the library resolves"* |

The sound form enumerates the **behaviour**, not the **string**.

My first attempt was the unsound one: a negative scan for the token `basis`,
which in this codebase names **four different things** — the GAAP axis,
`period_basis`'s EXPLICIT/INFERRED, `score.py`'s unit scale, and
`basisLocation`. It flagged all four as defects. `parse.py` and `tables.py`
compare a *document*-derived basis against a literal and never meet a spec
value at all.

**Same finding as the allowlist:** an allowlist by name assumed a field held
structure; a negative scan by name assumed a token held one meaning. Both
trusted a string to stand for a behaviour.

---

## ★★★ 45. A CONSISTENT REASON AND A TRUE REASON ARE DIFFERENT CLAIMS

The reason gate verifies **presuppositions** — a tie presupposes a label hit.
It proves **consistency, not root cause**. AVGO[6] moved `UNIT_MISMATCH` →
`NO_LABEL` only when the boilerplate filter landed; **the gate had passed it
as consistent the whole time.** Only the first claim is gated, so every
refusal still has to be traced.

---

## ★★★ 46. WHICH CODE PATHS GET EXERCISED IS DECIDED BY WHICH ISSUERS WE SPEC'D

`is_heading` judged by **line length**. MDB hard-wraps at ~66 characters, so
**54 of its lines passed**, and the period classifier would have been handed

```
-- Revenue: Total revenue was $771.8 million for the second quarte
```

as the section a value sits under. **All eight spec'd documents are
double-spaced**, so the corpus could never have shown it. MDB is in the repo
only as a captured *frame*.

Three structural discriminators, no word list — blank-line adjacency, not a
bullet, carries no figure. **MDB 54 → 8**, and what survives is
`Third Quarter Fiscal 2027 Guidance` and `Full Year Fiscal 2027 Guidance`.

★ **And the blank-line test is applied only where blank lines exist**: the
dewrapped frame has almost none, and requiring adjacency there silently lost
HPE's `Fiscal 2026 Full Year Outlook`.

---

## ★★★ 47. FRAME DEFECT n=5 — DEWRAPPED TWICE

`derive()` re-enters `value_for` to resolve a card-row operand, and
`value_for` **dewraps what it is handed**. It was being passed the caller's
already-dewrapped `src`, so the operand's own read happened in a
**doubly-dewrapped** frame and every offset shifted. HPE[3] resolved
standalone and refused as an operand; the derived hero above it refused with
it.

Frames now: **raw · dewrapped · stripped · kept · dewrapped-twice.**
The fix is the original document, not the caller's frame.

---

## ★★★ 48. THE GUIDE SECTION LEVER — MEASURED ON THE HELD-OUT FIVE

Kyle's four new blocks turn an existing metric label into a guide row. Read
as `guidance.py` and run against the five held-out tickers:

```
13 guide sections found across 8 of 10 captured documents
 8 of 13 resolve a period (GUIDE_FY / GUIDE_NEXT_Q)
10 of 10 forward rows reach a guide section — none is un-located
 0 of 10 publish a value
```

**The section lever works. The residue is one field per row, not structure:**

| refusal | n | the hand work |
|---|---|---|
| `BAND_COLLAPSED` | 4 | the value is FOUND; the range parser does not recover both endpoints from that layout |
| `UNIT_MISMATCH` | 4 | `documentUnit` guessed from the row name; the issuer uses another denomination |
| `CANDIDATE_TIE` | 1 | needs a narrower fence |
| `NO_LABEL` | 1 | needs the issuer's literal wording |

★ **"Section found, read nothing" was my own mislabel.** I bucketed by
`value is None` without reading the reason — they *read* and were then
*refused by a guard*. The reason gate exists for exactly that and I did not
consult it. `BAND_COLLAPSED` first-fires on real prose here, which is what
the first-fire ledger was built to surface.

★★ **And the vocabulary validator refused a spec this module generated.**
Six of ten forward rows failed `SPEC_INVALID` because `guidance.py` wrote
`period: UNRESOLVED`. **UNRESOLVED is not a period, it is the absence of
one** — declaring it declares a period we do not have, and an inferred period
may RANK, never EXCLUDE. It is now `periodHint`. The validator catching its
own toolchain is the strongest evidence it works.

★★★ **And the precedence already existed.** `period.py` has carried
`_QUARTER_SCOPE` and `_WHOLE_YEAR` since the classifier was built, with
`_WHOLE_YEAR` deliberately *"full year / full fiscal / annual"* and **not** a
bare *"fiscal year"* — because in `Fourth Quarter Fiscal Year 2026 Business
Outlook` the year **qualifies** the quarter rather than competing with it. A
second pair written in `guidance.py` would have made that heading UNRESOLVED.
**Was this fact ever computed anywhere in the call path?** It was.

One widening, in one place: `_QUARTER_SCOPE` now allows a hyphen, so DELL's
`Third-Quarter Guidance` dates.

★ **And a span needs a close — including in code I had just written.**
`guide_sections` computes `(lo, hi)` and the first `specs_for` passed only the
heading NAME, so `section_spans` re-derived a fence with no terminator: MDB's
716-character guidance section became 3,192 characters running to the end of
the document. The close was computed and discarded one line before it was
needed.

---

## ★★★ 49. FRAME TYPE — POSITIONS CARRY THEIR FRAME

Five failures, none caught by vigilance, and vigilance would have failed a
sixth. `frames.py` is a `str` subclass that remembers which frame a document
is in, so nothing had to be rewritten to adopt it.

```
dewrap_mapped()  ->  tags its output DEWRAPPED
derive()         ->  declares it expects RAW
value_for()      ->  declares it expects RAW
```

**It records, it does not raise.** An exception costs the whole card; the
point is to make the mistake visible, not fatal at 4:31. The sweep refuses to
write when a violation is recorded.

Driven red on the exact n=5 defect: handing `value_for` dewrapped text now
reports *"value_for expected RAW text and was given DEWRAPPED"* and names the
inner call too, instead of silently refusing a priority-1 hero.

---

## ★★★ 50. BOTH PREDICTIONS PRICED ZERO — AND A ZERO IS A QUESTION

Kyle predicted `denomination` (an ACCESS fix) and range-form detection (an
INFORMATION fix) would each pay alone.

```
ARM              forward  refused  READS  AGREES
baseline            10      10       0      0
+denomination       10      10       0      0
+rangeForm          10      10       0      0
BOTH                10      10       0      0
```

**Neither paid, alone or together.** He was on record; the answer is that the
*type* of each was misdiagnosed, which is exactly what he said the failure
would mean.

**`UNIT_MISMATCH` × 4 is not a unit problem.** `denomination()` returns the
correct `$B` for DELL's guidance section — the information is right and
reachable, and the rows still refuse. The fix reached correct information and
the blocker was elsewhere.

**`BAND_COLLAPSED` × 4 is not a detection problem.** MRVL prints

```
Net revenue is expected to be $3.150 billion +/- 5%.
```

The form **is** detected as `PLUS_MINUS`. What is missing is that this is a
**PERCENTAGE delta**, not an absolute one — `centre ± (centre × pct)`. Kyle's
block lists `"$29.4B +/- $500M"`, an absolute delta. **A percentage-delta
plus-minus is a seventh form**, and it is genuinely new information rather
than an access or detection gap.

★ And the validator refused my detector too: `FLOOR` / `CEILING` /
`APPROXIMATE` are in Kyle's block but not in `vocab._CLOSED['rangeForm']`, so
`+rangeForm` produced a `SPEC_INVALID`. **Second time the vocabulary has
caught its own toolchain.**

---

## ★★★ 51. RE-DERIVED IN IGNORANCE — A NEW FORM OF THE DISCARD PATTERN

Not *"computed and discarded"* but **"re-derived in ignorance, and worse"**.
Kyle authored a `periodDisambiguation` pair into the data that `period.py`
had implemented more carefully since the classifier was built. Same root, and
the waste lands on the **authoring** side.

> **Before authoring a rule into the data, ask whether the code already
> implements it.**

And the companion, which cost the first real fire of a first-fire code:

> **When bucketing a result, bucket on the RICHEST available field, not the
> cheapest.** I bucketed by `value is None` when `reasonCode` was sitting
> right there.

---

## ★★★ 52. ONE VOCABULARY, READ AT RUNTIME

Two `rangeForm` lists existed: nine values authored into
`ticker-profiles.json`, five hardcoded in `vocab.py`. The validator refused a
form the author had already blessed. **The drift was the defect, not either
list — and syncing is what produced it.**

`vocab._range_forms()` now reads `★CLOSED_LIST_AUTHORITATIVE` from the data,
per this project's own rule that frameworks live in the data so a revision
propagates without a code change. The hardcoded tuple survives only as a
**named** fallback: `range_form_source()` reports `data` or
`FALLBACK — data unreachable`, because a vocabulary that quietly narrowed
would refuse authored forms and report them as spec defects.

---

## ★★★ 53. THE SPAN TYPE — SIX VIOLATIONS, ONE INSIDE THE ENFORCEMENT

```
1  spans                zero-width fences
2  absence claims       a bounded search describes its BOUND
3  recursion            a depth count is a length; re-entry is the close
4  headings             is_heading by LINE LENGTH; MDB wraps at 66
5  its own enforcement  guide_sections computed (lo,hi); specs_for passed
                        only the heading NAME — MDB 716 -> 3,192
6  heading adjacency    DELL's stacked headings -> 18, 49, 51, 75 chars
```

`Span` is a `tuple` subclass that remembers **how it was closed** and whether
it **holds content below its heading** — adopted without rewriting anything,
recording rather than raising. Driven red on all three failure modes:
zero-width, heading-only, and closed-by-length.

**The invariant: an empty span is not a section, and a close must close after
the content.**

---

## ★★★ 54. THE TRACE STARTS FROM THE DOCUMENT — UNIT_MISMATCH × 4

Traced from the release rather than from the code or the reason:

```
DELL[16] 'Q3 FY27 Revenue Guide ($B)'   hand 49.0
document   'Q3FY27 (% Y/Y) Revenue $ 49.0 81 %'      at 3271
span       'Third-Quarter Guidance' 3152..3339        value INSIDE
denomination at that point            ('$B', '(in billions, ...)')
verdict    UNIT_MISMATCH
```

**The value is inside the fence, the denomination is correct, and the row
still refuses.** DELL[4] `$192.0 billion` and DELL[5] `$25.50` are likewise
printed plainly, three times each.

**The true root: `_unit_ok` tests the CANDIDATE for a magnitude word and
never consults the denomination the table header supplies.** A bare cell
`$ 49.0` under `(in billions, except percentages…)` carries no magnitude word
of its own, so a `$B` row rejects it.

So Kyle's access instinct was right about *which fact* — `denomination()` —
and wrong about *which junction*. It is not `documentUnit` on the spec, which
was already correct. It is the candidate unit test.

★ AAPL[3] is a different row entirely: `F4Q Revenue Guide (% YoY)` with a
hand read of `10.0`, a **percent growth** figure, in a section that prints
only dollars. Its three `10` matches are coincidental digits inside a dollar
table. That row is probably derived or not-in-PR, **not** a unit failure —
one bucket, two unrelated causes, which is why the trace had to run.

---

## ★★★ 55. THE _unit_ok FIX DOES NOT EXIST — TRACED, NOT REASONED

Predicted junction: `_unit_ok` rejects a bare `$ 49.0` for want of a
magnitude word. **Traced from the document, it does not.**

```
DELL[16]  hand 49.0
document  'Q3FY27 (% Y/Y) Revenue $ 49.0 81 %'   at 3233
fence     'Third-Quarter Guidance' 3152..3339     label hit INSIDE (1 of 47)
candidates on that window            3, 27, 49.0, 81
_unit_ok('49.0', '$B')               TRUE
verdict                              UNIT_MISMATCH, candidates []
```

**`49.0` passes the unit test.** Eliminated in turn, each by substitution:
`_unit_ok` · the section anchor · `rangeForm` · `whereKind` · the label set.
All four variants return byte-identical refusals. The blocker sits between
the surviving label hits and the candidate pool, and is not yet named.

> **So there is no loosening to make, and the AAPL[3] FALSE_MATCH risk does
> not arise from this fix.** That is a fourth outcome the three-way
> prediction did not contain: **the fix was never available.**

★ And the trace found something else: `Q3FY27` yields candidates **3** and
**27**. A period token is being read as a magnitude, inside the fence.

**AAPL[3], dispositioned from the document:** `F4Q Revenue Guide (% YoY)`,
hand read `10.0`. The release contains **no percent revenue-growth guide at
all** — its only guidance language is a disclaimer about reconciling non-GAAP
guidance. `NOT_IN_PR` / `CALL_SOURCED`. The row asks for a figure the release
does not print, and its three `10` matches are coincidental digits in a
dollar table.

**One refusal bucket, five unrelated causes now** — HPE[3]/[8]/[12], AVGO[6],
DELL × 3, AAPL[3]. **A refusal code is a bucket, not a cause**, and every
split has been visible only from the document. That is the evidence for P1.

---

## ★★★ 56. THE JUNCTION, NAMED — `clip()` RETURNS AN EMPTY WINDOW

```
DELL[16]  label 'Revenue'   hit 3233..3240, INSIDE the fence, not disqualified
raw window  src[3240:3500]  '$ 49.0 81 % GAAP diluted EPS $ 6.10 168 % ...'
clip(raw, ['PROSE','RANGE','TABLE'])   ->   ''
candidates('')                         ->   []
verdict                                ->   UNIT_MISMATCH, candidates []
```

**The pool is empty by construction, and the refusal blames the unit.**

★ **And `clip`'s own docstring names this defect, one layout over:** *"in a
vertically exploded table [a blank line] separates two cells of the SAME
row… So the prose rule clipped all four guide windows to '' and the selector
refused a candidate set that was empty by construction."* It was fixed for
ADBE by routing on `tabular` — and `tabular` requires `PROSE` to be **absent**
from `whereKind`.

> **`whereKind` is a ROUTING declaration, and declaring all three is worse
> than declaring one.** A generator — or an author who is unsure — that lists
> `['PROSE','RANGE','TABLE']` to be safe gets the prose stop rule and an
> empty window. **Breadth in a routing field is not caution; it is a
> selection of the first branch.**

★★ **This is not the whole blocker.** With `whereKind=['TABLE']` alone the
row still refuses, by a different path — the table pass requires a parseable
row at the label hit. **Two junctions on one row**, and only the first is
named. The second is the next trace.

---

## ★★★ 57. FISCAL-PERIOD NOTATION DECOMPOSES INTO CANDIDATES

`Q3FY27` yields candidates **3** and **27**, inside the fence a guide row
selects.

Not a DELL quirk — the notation is universal in this market: `Q3FY27` ·
`FQ1-27` · `1Q26` · `FY2027` · `2Q FY26` · `4Q25`. **Every one decomposes
into small integers that look like levels**, and they sit in exactly the
region a guide row fences to. A polluted pool produces `CANDIDATE_TIE`, the
largest refusal bucket on the held-out set.

**Convention-based, so worth more on a ninth issuer than on the corpus** —
the same property as the boilerplate exclusion.

Discard question, asked first: `★periodMarkers` exists in
`globalDocumentLabelMap` and `period.py` carries `_QUARTER_SCOPE` — **one of
them may already recognise the token and simply not be consulted before
candidate selection.** Junction not yet named; this is a trace request, not a
prediction.

---

## ★★★ 58. A LIST IN A ROUTING FIELD IS AN ORDERED PREFERENCE, NOT A SET OF PERMISSIONS

> **WHEN UNSURE, DECLARE ONE.** A single declaration that refuses **names the
> branch it tried**. Breadth takes the first branch and hides which one ran.
> **A refusal is diagnostic; a silent wrong branch is not.**

**And the library said so all along:** `whereKindIsAPreferenceOrder: True` is
authored on the spec. The code read the list as a **set** — `prefers_table`
required `PROSE` to be *absent* before it would prefer the table.

```
76 spec'd rows · 29 declare more than one kind · 9 of those refused
ADBE[6] 'TABLE/PROSE'  REFUSED  ->  MATCH 6.13   (hand 6.13)
ADBE[7] 'TABLE/PROSE'  REFUSED  ->  MATCH 6.76   (hand 6.76)
ADBE[12]                MATCH 2.97 ->  MATCH 2.974  (more precise)
MATCH 36 -> 38, zero regressions
```

**Third instance of a fact present in the system and not consulted** — after
`period.py`'s precedence and the range endpoints.

★ **The validator now SURFACES routing breadth rather than refusing it** —
29 rows, 7 of them refusing, printed with the branch they declared. Breadth
is not invalid; 20 of the 29 read correctly. This turns the habit into an
**artifact the author can see** instead of a judgement they must remember.

---

## ★★★ 59. A DOCSTRING IS A JUDGEMENT, NOT AN ARTIFACT

Twice this month a function **documented the defect it then committed**:

- `clip()` — *"the prose rule clipped all four guide windows to '' and the
  selector refused a candidate set that was empty by construction"* — and it
  did exactly that to DELL, because the fix routed on `tabular`, which
  requires PROSE to be absent.
- the range arm — *"both ends travel with it: a band is information the
  midpoint discards"* — and the return dropped them one frame from the
  caller.

> **WRITING A DEFECT DOWN IS NOT PREVENTING IT.** A docstring leaves no
> residue when ignored, which is the artifact criterion applied to comments:
> **if a docstring states an invariant, the invariant needs a test, or the
> docstring is decoration.**

---

## ★★★ 60. THE GUIDE GENERATOR READS SIX AND GETS FOUR WRONG

With one routing kind per spec and no invented `rangeForm`, the held-out
forward rows move **0 → 6 reads**. Two agree. **Four publish a wrong value:**

```
DELL[4]  FY27 Revenue Guide    read 49.0   hand 192.0   <- took the Q3 figure
MDB[2]   FY27 Revenue Guide    read 761.0  hand 3.01
MRVL[0]  FY27+FY28 DC Revenue  read 5.0    hand 60.0
```

DELL[4] is the sharp one: an **FY** row took the **Q3** number, out of a
`Guidance Summary` section whose period is `UNRESOLVED`. `periodHint` ranks
and never excludes — correctly, by the standing rule — so nothing stopped it.

**Two right and four wrong is worse than six refusals.** The generator stays
a measurement tool and is not wired into `value_for`. **Reading more is not
progress until the period can exclude.**
