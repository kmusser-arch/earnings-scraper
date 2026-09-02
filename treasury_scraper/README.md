# Treasury / macro headline monitor

Built around one question: **why was the 2026-08-19 long-end buyback expansion
missed?**

The answer is in this repo. `news.log` — 39 MB, UTF-16LE, sitting uncommitted
since the evening of the 19th — contains the whole event:

| ET | src | headline |
|---|---|---|
| **08:36:18** | **HAM** | `$SPY U.S. Treasury increasing size of liquidity support buyback operations for longer-dated nominal coupon securities` |
| 08:37:11 | HAM | `(more) US Treasury: Change is effective September 9.` |
| **08:38:40** | **HAM** | `Current maximum size of $2B per operation will be at least $4B` |
| 08:44:10 | HAM | `$TLT $TBT Bond prices rising as yields tumble` ← tape moves |
| 08:48:18 | SIN | `U.S. Treasury doubles buyback operation size for long-dated bonds` |
| 08:52:27 | FLY | `US Treasury announces increased sizes of nominal long-end purchases` |
| 09:08:18 | WSJ | `Bond Yields Drop After Treasury Says It Will Increase Buybacks` |

**Hammerstone led the Wall Street Journal by 32 minutes**, and led the visible
tape move by eight. The trade was not missed for lack of a scraper. It was
missed because 37,760 messages went past that day and nothing separated the
three that mattered from the rest.

## Why this is not a 1-second scraper

`home.treasury.gov` was measured, not assumed:

```
index   200  ttfb 9.21s / 10.25s / 9.22s
leaf    200  ttfb 8.32s
404     404  ttfb 38.39s
If-None-Match -> 200, never 304

Server-Timing: cdn-cache; desc=REVALIDATE, edge; dur=9021, origin; dur=4
```

The origin answers in **4 milliseconds**; Akamai adds **nine seconds** to
every request and ignores our validators. Polling at 1 Hz would keep ten
identical requests in flight at all times, each returning the same edge-stale
HTML, and would be rate-limited inside a minute.

Press-release slugs *are* sequential (`sb0400` exists, `sb0450` does not), so
probing the next id ahead of the index is tempting — but a miss costs 38
seconds and returns a WAF page, which is strictly slower than reading the
index and far more likely to get the IP blocked.

So the wire is the primary path and treasury.gov is the confirmation path.
Sub-second versus eight seconds is not a tuning question.

## The filter

Ten layers, cheapest first, in `noise.py`.

| | layer | effect |
|---|---|---|
| L0 | source triage | EDG+DJN are 74% of the wire; neither originates an alert |
| L1 | dedup | normalised headline — FTI republished one headline 6× |
| L2 | release-type gate | readouts, remarks, ratings actions, sell-side PTs |
| L3 | vocabulary tier | Tier-A +5 / Tier-B +2, word-boundary matched |
| L4 | **novelty ledger** | +3 only when a number **changed** vs. known state |
| L5 | homonym guard | corporate share repurchases ≠ Treasury buybacks |
| L6 | instrument / topic | free curated tags: `EQ:US:SPY`, `tsy`, `bon`, `irt` |
| L7 | calendar prior | floor relief inside a scheduled announcement window |
| L8 | **story cooldown** | sliding; one event, not twelve outlets' headlines |
| L9 | corroboration | a second independent source confirms, never re-alerts |
| L10 | **continuation attach** | same-desk figures join an open story |

Three of those are worth more than the other seven.

**L4 — the ledger.** "Increased sizes" is only news against the size that was
standing before it. The ledger is seeded at `$2B`, so the release reads as
`2B->4B (+100%)`. A restatement of a known figure is dropped outright. This is
the same discipline as grading a print against the bogey rather than zero:
the headline is not the news, the delta is.

**L5 — the homonym.** In the same 45-minute window the wire carried SK Hynix
($29B), Curtiss-Wright ($100M), John Marshall Bancorp and Ipsos — all share
repurchases. "Buyback" is overwhelmingly a corporate word; it is macro only
alongside a sovereign-debt word.

**L10 — continuation.** The single best argument against keyword filtering is
on the tape at 08:38:40:

> `$SPY US Treasury: Current maximum size of $2B per operation will be at
> least $4B per operation`

That is the entire trade — old ceiling, new ceiling, the doubling — and it
contains **no Tier-A keyword at all**. Read alone it is unclassifiable. Read
as the third message of an open story from the same desk, it is the only one
that mattered.

## Result on the real capture

```
messages parsed           21660
  dropped at L0               651     3.0%
  dropped at L1                31     0.1%
  dropped at L2              1426     6.6%
  dropped at L3             19318    89.2%
  dropped at L5                46     0.2%
  CONFIRM (dup, 2nd src)       56
  ENRICH  (attached fig)        1
  ALERT   (popup)               8    0.04% of the wire
```

Eight alerts across two days, and all eight are distinct tradeable events —
the buyback headline, the `$2B→$4B` figure, two separate analytical reads on
the doubling, and four Canada-tariff developments. The founding case fires
**first, at 08:36:18, scoring 10.0**.

## Use

```powershell
py -m treasury_scraper replay news.log     # acceptance test on real tape
py -m treasury_scraper run -u kmusser --prod   # the wire (primary)
py -m treasury_scraper poll                # treasury.gov (confirmation)
py -m treasury_scraper probe               # re-measure the Akamai edge
py -m treasury_scraper ledger              # show / set known values
py tests/test_treasury_noise.py            # regression pins
```

**Before the September 9 effective date**, set the ledger so the next change
is measured from the right base:

```powershell
py -m treasury_scraper ledger --set buyback_op_max 4000000000
```

## Tuning knobs, and what they cost

`STORY_COOLDOWN_S` was swept against the capture: `1800 -> 27 alerts`,
`3600 -> 22`, `7200 -> 7`. It defaults to 7200. Lower it if you would rather
be told that a story you already know about is still developing.

`ALERT_FLOOR` is 6.0, dropping to 4.0 inside a hot window — **for Tier-A
only**. Tier-B keeps the full floor; relief on Tier-B is what let
`$TGT exec notes ... tariffs` fire at 4.0 on an early replay.

## Known limits

- Tier-B (tariffs, sanctions) is tuned far more loosely than Tier-A. Four of
  the eight surviving alerts are Canada-tariff items. That is a judgement
  call, not a validated setting — there is one macro event in this capture,
  so **Tier-A is pinned to a sample of one.**
- `_now_et()` computes the DST offset by month rather than from a tz
  database. It is used only to pick a 50-minute poll window, so a wrong hour
  on a shoulder date changes nothing that matters — but do not reuse it for
  timestamping.
- The poller parses the index with a regex, and Akamai serves that page
  minified with unquoted attributes. `warm()` now **raises** when it parses
  zero slugs rather than running forever in silence — a parser matching
  nothing is indistinguishable from a quiet news day, which is the worst
  failure mode available here. The same applies to the leaf template: the
  release body is read from the article region, because the site nav contains
  a "Readouts" link that otherwise made L2 drop every release on the site.
