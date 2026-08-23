# Deep Pre-Earnings Research Playbook

Use this when the user did not provide a preview and you need to build the expectations baseline from scratch. The goal is to replicate the preview quality shown in the user's existing INTC / TSLA / NOW records.

## Target outputs

You are trying to produce the complete `preEarnings` object plus the context fields (`stockReactionFramework`, `overrides`, `notes`) with the same depth as a hand-built preview. Specifically:

1. **Revenue consensus + bogey** — two distinct numbers
2. **EPS consensus + bogey** — two distinct numbers (GAAP and non-GAAP if split)
3. **Key KPIs** — 4–8 business-specific metrics with consensus (and bogey where available)
4. **Next-quarter guidance expectations** — what the Street wants to hear
5. **Full-year guidance expectations** — current guide and what a raise/cut would look like
6. **Bull case** — 2–4 sentences, the most compelling long argument right now
7. **Bear case** — 2–4 sentences, the most compelling short argument right now
8. **What matters most** — the 1–3 metrics the stock will trade on
9. **What wins / what loses** — specific thresholds
10. **Market positioning** — price, market cap, fwd P/E, YTD, recent catalysts, implied move
11. **Analyst breakdown** — buy/hold/sell counts, avg PT, notable upgrades/downgrades

## Sources — preferred order

Use WebSearch with targeted queries. Prefer 2026-dated sources. Cross-check numbers across at least two sources before committing.

### 1. Consensus & segment expectations
- `"{TICKER} Q{Q} {YEAR} earnings consensus revenue EPS"` — picks up StreetAccount, Seeking Alpha previews, Benzinga
- `"{TICKER} Q{Q} {YEAR} preview analyst expectations"` — picks up Barron's, Bloomberg summaries
- `"{TICKER} earnings whisper number"` — picks up earningswhispers.com style buyside bogeys
- Visible Alpha, Zacks, Refinitiv consensus — often cited in sell-side previews

### 2. Individual analyst positioning
- `"{TICKER} price target raise lower {current month year}"` — recent PT changes
- `"{TICKER} downgrade upgrade"` — recent rating changes
- Look for notes from: HSBC, Wedbush, Morgan Stanley, Barclays, BofA, JPM, Citi, Bernstein, Evercore, Jefferies, Seaport, Gabelli, Oppenheimer, UBS, Goldman

### 3. Market positioning & recent catalysts
- `"{TICKER} stock price {current year}"` + YTD, 52-week range
- `"{TICKER} news {recent dates}"` — any catalyst in last 30 days
- `"{TICKER} implied move earnings"` — options-implied move
- `"{TICKER} short interest"` — if applicable
- Company investor-relations page for formal guidance language

### 4. Prior-quarter context
- Read the user's `earnings-library.json` first — the prior quarter may already be stored
- If not: `"{TICKER} Q{prior-Q} {year} earnings results stock reaction"`
- Focus on: what guidance they gave last quarter (is the current guide a raise or cut?), how the stock reacted (move size + direction), and what the narrative was at that time

## What to write in each field

### `bullCase` and `bearCase`
Be specific, not generic. "AI tailwinds" is useless. "NVIDIA DGX Rubin host CPU win validates server CPU thesis" is useful. Aim for named products, named customers, specific numbers, specific catalysts.

### `whatMattersMost`
Rank the metrics by how much they will move the stock. Usually 1–3 items. For growth stocks this is often a KPI (cRPO, subs adds, deliveries). For profitability stories this is margin. For turnarounds this is guidance direction.

### `whatWins` and `whatLoses`
Specific quantitative thresholds. "Beat on revenue" is not a threshold. "Revenue ≥$12.5B + Q2 guide ≥$13.2B + GM >35%" is a threshold. These thresholds drive the score in real time — you will compare actuals to these to assign −2/−1/0/+1/+2.

### Implied move
Options-implied move for the single earnings day. If you can't find it, state "unknown" rather than guess. Useful as a sanity check on reaction expectations.

### Positioning context → `notes` field
Stuff like "Stock at $392.50 going in, down 14% YTD from $498 ATH in Dec'25. P/E ~370x. Implied move ±10%." goes in the top-level `notes` field. This is read by your future self when comparing Q-over-Q.

## Quality bar

Before committing research to the record:

- **Two-source rule**: Every number (consensus rev, EPS, key KPI consensus) should be confirmed by at least two sources. If only one source has it, flag it as `"(source: Bloomberg, unconfirmed)"` inline.
- **Freshness rule**: If a number is from >2 weeks ago, search again — consensus moves on buyside revisions.
- **No made-up analysts**: If you cite a specific analyst name or firm, it must come from a real, retrievable source. Do not fabricate. If in doubt, aggregate ("consensus of 32 sell-side estimates") rather than cite a specific name.
- **Label inferred data**: If you infer a bogey from a range rather than find an explicit number, say so: `"Bogey ~$3.79B (inferred from top-decile estimates)"`.

## What to skip

- **Historical reminiscing.** Prior-quarter context is useful; the full 2-year history is not.
- **Sell-side model building.** You are capturing consensus, not building your own forecast.
- **Macro essays.** Keep macro color to one line in the bear case if it is actually load-bearing.
- **Disclaimers and hedging language.** "Expectations are always subject to change" wastes the user's time.

## Failure modes to avoid

1. **Stale consensus.** If the print is already out when you research, you may stumble into post-print coverage. Constrain searches with date filters (last 7 days).
2. **Conflating buyside and sellside.** Buyside bogey ≠ sellside consensus. They are usually different by several percent. Record both.
3. **One-source surface.** Do not just pull from one summary article. Cross-check.
4. **Research theater.** Do not spend 20 minutes researching a ticker the user is watching in real time. If you cannot produce a solid baseline in 5–7 focused searches, return what you have and flag the gaps. The scorecard is better partial than late.

## Output while researching

Tell the user what you are doing in one line: `"Pulling consensus + buyside bogeys for {TICKER} Q{Q} — 30 seconds."` Do not narrate every search. Surface the baseline when you have it, then proceed to the actuals parse.
