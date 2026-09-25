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
