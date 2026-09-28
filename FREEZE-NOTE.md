# WHAT THE SCRAPER DOES ON A DOCUMENT IT HAS NEVER SEEN

Written 2026-09-28, before MU. **Frozen at `c919b18`.** Not a prediction about
MU — a description of what *wrong* looks like, so a blank cell at 4:31 can be
trusted or not without reading code.

---

## 1. THE ONE THING THAT MATTERS

**It is not reading a new issuer. It is reading a new DOCUMENT against a spec
you wrote before the document existed.** Every label, fence, basis, period and
unit comes off the card. The scraper knows nothing about MU that you did not
author.

So the failure mode is not "it misunderstood Micron." It is **"the label you
wrote is not the string Micron printed."** That is `NO_LABEL`, and it is the
most likely single outcome on any row.

---

## 2. WHAT IT WILL FILL, ROUGHLY

On the eight spec'd releases, of 76 extractable rows:

```
FILLED             37   48.7%
CANDIDATE_TIE      16   21.1%
UNIT_MISMATCH      12   15.8%
NO_LABEL            9   11.8%
PERIOD              2    2.6%
```

**Expect worse than 49% on MU**, for one structural reason: those eight specs
were written *against* their documents, over weeks, by looking at what failed.
MU's was written blind. I would not be surprised by 25–40% filled, and I would
not call 20% a malfunction.

**A row that fills is worth more than the fill rate suggests.** Every filled
row carries a verdict, three provenance checks, and a reason. A row that
refuses costs you that cell and nothing else.

---

## 3. WHAT IT WILL REFUSE, AND WHETHER TO TRUST THE BLANK

**Trust the blank** — these mean the document did not say what the card
expected:

| code | what it means | seen on real prose |
|---|---|---|
| `NO_LABEL` | your label string is not in the release | **yes**, 9× |
| `CANDIDATE_TIE` | several numbers fit and no declared axis separates them | **yes**, 16× |
| `PERIOD` | the figure sits in a clause the issuer marked another period | **yes**, 2× |
| `UNIT_MISMATCH` | label found, no nearby number in the declared unit | **yes**, 12× |

**Hand-check the blank** — these have *never* fired on real prose. Eleven of
fifteen codes. Any of them appears with `firstFire: true` on the card and in a
banner in the sweep output:

```
ALL_DELTA · BAND_COLLAPSED · BASIS · BASIS_ABSENT · BASIS_CONTRADICTS
CURRENCY · DERIVED_OPERAND · NO_LABEL_AFTER_FILTERS · READER_CRASHED
SPEC_INVALID · SPEC_STATE
```

**The four I would actually expect to see first on MU:**

1. **`BASIS_ABSENT` / `BASIS_CONTRADICTS`** — MU is a memory name with heavy
   non-GAAP adjustment, and the basis machinery is **six days old**. It has 8
   evidence-bearing rows of experience, all on documents it was built against.
2. **`SPEC_INVALID`** — fires if any MU spec field is outside its closed
   vocabulary. Most likely on `basis` (two spellings exist in the library) or a
   `rangeForm` you have not used before. **This one is cheap to pre-empt:** run
   the sweep against the MU card *before* the print and it will tell you.
3. **`BAND_COLLAPSED`** — any guided range row that parses a midpoint but not
   both ends. Refusing is correct here; a collapsed band silently reassigns a
   ladder branch.
4. **`NO_LABEL_AFTER_FILTERS`** — a label found but killed by a `disqualify`
   token or the definitional-block filter. If you see this, the label exists
   and something else rejected it — usually the most fixable refusal.

---

## 4. WHAT A CRASH LOOKS LIKE

**Designed behaviour: one cell, with a reason.** Five reader call sites are
guarded plus an outer boundary on `value_for`. A crash produces:

```
value       None
reasonCode  READER_CRASHED       <- firstFire, never seen on real prose
why         READER FAILED in <reader>: <ExcType>: <message>
verdict     REFUSED
```

The card still renders. Every other row is unaffected.

**If a guard misses one**, the failure is *above* `value_for` — in the scorer,
the renderer, or the writer. Symptoms, in order of likelihood:

- **the sweep exits with a traceback and writes nothing** — the library keeps
  its previous contents; nothing is corrupted, you have no scraper column
- **`validate_library.py` exits non-zero** — the write happened and produced
  something malformed; **do not push**
- **a card renders but a tab throws on click** — `render_test.js` catches this
  class; if it passed, this is unlikely

**What I have never tested:** MU's document reaching the scraper at all. The
fetch, the wire format, the ticker match, the pending-file write. Everything
above assumes a body string arrives. **If nothing appears at 4:31, suspect
transport before extraction.**

---

## 5. WHAT CANNOT BE WRONG, AND WHAT CAN

**Cannot be wrong (structurally prevented):**

- a value published without a reason when it fails — the writer **raises**
- a refusal whose stated cause contradicts the document — the writer **raises**
- a band published as a bare midpoint — the row refuses
- `street` / `bogey` / `consensus` / `note` reaching any extracted value —
  poisoned and measured, no value moved
- a crash in one reader producing a value from a weaker one that ignores the
  declared basis — the row refuses instead

**Can still be wrong:**

- **the right digits from the wrong cell where no axis discriminates.**
  `FALSE_MATCH` has fired exactly once, by injection. 6 of 36 MATCH rows are
  all-vacuous — nothing checked them.
- **a `MATCH` that agrees with a hand read that is itself wrong.** The
  expected column is as error-prone as the actual column.
- **`basis` on a prose row with no basis word before the value** — 3 of 6 such
  rows resolve today, 3 are silent.
- **any of the eleven unfired codes behaving badly in a way the corpus could
  not show.** That is what `firstFire` is for.

---

## 6. THE ONE-LINE PROTOCOL FOR WEDNESDAY

> **Hand-check every `firstFire` refusal against the release. Take the other
> refusals at face value. Treat any filled row whose `sweepChecks` show
> `evidenceCount: 0` as unverified, however right the number looks.**
