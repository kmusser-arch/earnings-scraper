# FINDINGS — the shapes this build keeps producing

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
