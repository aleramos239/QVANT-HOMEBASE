# Overnight brief: rinse the prop firms with $500 (owner, 2026-11-02)

Status: GO given 2026-11-02 evening ("it is very important that you do not stop until you achieve this").

## The goal in one line
Find a simple NQ New York-session setup + an account plan where **$500 of evals gives at least one payout of $1,000+**
as close to always as possible, ideally passing in ~5 trading days and paying 5-10 trading days after funding.
A real edge is welcome, NOT required: a losing rule that passes 2 of 5 accounts is fine if the payouts beat the fees.

## The owner's words (quote these verbatim in owner_said)
- Test months: "So you're permitted to touch the test months. That's all you're you have full freedom, full control."
- Heat maps / everything (answer to "can I quote it for heat maps too"): "And everything. Yeah, you have full freedom, full control. You're the boss."
- Simple rules: "Really looking for simple ideas as well to fully prevent overfitting. Like, maximum like VWAP and then maybe like a displacement filter."

## Added at the go (owner, 2026-11-02)
- Eval budget $500; $600-700 only if it must ("really try to stay within the 500").
- Aim for setups (or several setups together) that trade ~5 times a day, so each of 5 accounts gets one trade a day.
- 12 JJ Simon videos sent (9 new: KsfBGgX-CTM, -RI9cgic1tM, nvOaN6mRu-o, dJdBnSBJlgQ, sWJa8vRfPb8, KhooqEQK9bA,
  PMGhHCjYG5c, 0Ua-ffltO0I, 74CRg-mID5c; 3 noted before). Notes: research/edge-library/jj-simon/videos/, synthesis
  research/edge-library/prop_rinse_2026-11-02/jj_account_game.md.
- Do not stop until there is a strong result.

## Firms and accounts (verify every rule and price ONLINE tonight; prices change, sales are common)
| Firm / account | Rule file today | Note |
|---|---|---|
| Lucid Flex 25K | `lucid-flex-25k-dll@2026-10-19` | owner's favourite to start |
| LucidPro 25K | `lucid-pro-25k@2026-10-19` | no consistency on eval |
| FundedNext Rapid 25K (Pro and Daily) | NONE -> write `fundednext-rapid-25k@2026-11-02` | rules in F/2026-10-30-fundednext-futures-account-rules.md; payouts reputed good |
| Apex 50K legacy | `apex-legacy-50k@2026-10-11b` | payout terms were placeholders: confirm |
| Topstep 50K | NONE (removed 2026-10-11) -> write `topstep-50k@2026-11-02` | owner: compare against Lucid Flex 50K (`lucid-flex-50k@2026-10-11`), "the rules are pretty much the same" |
Not Alpha. Everything else 25K. Fees: eval price + activation/reset fees, each counted.

## What to build (simple only: 1-2 conditions a rule)
Families, all NQ, New York session around 09:30:
1. 09:30 straddle (offsets, fixed stops/targets incl. wide targets 1:3-1:5 with low win rates; first 15s/20s/1m candle; market with the candle). Drafts exist: `draft_nq_930_straddle`, `draft_nq_930_firstcandle_straddle`, the `straddle_930_study/` folder.
2. NY sweep: overnight / prior-day / Asia / London high-low taken at or after the open, then reverse or follow.
3. Candle sweep / candle break (1m, 5m, 15m first candles, previous candle at 09:30: `draft_nq_930_prevcandle_straddle`).
4. VWAP: session (18:00), RTH (09:30), anchored; touch / reclaim / band; timeframes 1m-15m.
5. Displacement filter: body vs ATR, range vs average range, volume vs average, one at a time.
6. FVG with the day's direction (the only family positive in earlier screens).
Prefer setups with MORE trades a day (2-4) so evals and payouts come fast; one trade a day starves taken-turn accounts
(F/2026-10-19-1000-plan-sizing-kelly-flex-vs-pro-coin-flip-geometry.md section 5).

Backtests: tick replay on THIS MAC only (never the Chicago server), full range 2021 -> today allowed, real costs
($4 RT/contract + 1 tick, also 2 ticks as the worse-fill check). Each rule's TRADE LIST is the input to the sims.

## The account plans to compare (each on each firm)
- **Take turns (cycle):** one strategy, trade 1 -> account 1, trade 2 -> account 2, ... trade 6 -> account 1 (the owner's main idea; JJ Simon's).
- **One strategy per account:** 5 different simple rules, one each.
- **Copy:** every account takes every trade (reference: losses all land together).
- **One at a time:** trade one account until it passes or busts, then the next (the owner thinks this is the safest).
- **Buffer route:** one account builds a buffer big enough for the max payout, then small winning days finish the
  consistency/day count by hand. Report: chance any account reaches that buffer within N days.
- **Hedged pair (reference only, see the caveat):** long on one firm, short on another at 09:30 (the owner's
  Lucid Flex 50K vs Topstep 50K example: 1:2, $2,000 risk, ~60% day 1, ~88% by day 2).

## The two answers the owner wants
A. **Already funded** (no evals): 5 funded accounts (LucidPro 25K, Lucid Flex 25K, FundedNext Rapid 25K; Lucid Flex 50K vs
   Topstep 50K; Apex 50K legacy): which plan gets **2 payouts**, the chance of 1 and of 2, days to each, $ paid.
B. **From evals, $500 budget:** how many evals $500 buys per firm, pass %, then payout % of the passed
   (e.g. "30% pass, 30% of those pay"), the chance that $500 gives at least one $1,000+ payout, days to it, and the
   money line: average payout minus all fees, per $500 batch (does repeating it make money?).

## How to judge (honest numbers, no luck)
- Simulate every plan on thousands of start days drawn from the real trade lists, all years; show it **by year**
  (no plan that only works in 2024). Sharpe if shown = traded days only.
- Each firm's real rules: drawdown type (EOD / intraday trailing, counts open losses on Lucid), daily loss limit,
  consistency %, minimum days, payout buffer/minimum/cap/split, max contracts.
- Report what costs, not just what wins: worst case per $500, chance of losing all $500.
- Nothing is "guaranteed": give the % and its range.

## Tools already here (reuse, do not rewrite)
- `homebase/backtest/propsim/` (rules/*.json, the app's prop sim) and the `prop_eval`, `prop-sim` skill.
- `research/edge-library/taught/jj_fifty_accounts.py` (50 accounts eval -> funded -> payouts; `--together` copy vs turns) and `jj_plan_speed.py`.
- Desk cycle groups (O/desk-account-cycle-groups-2026-10-25.md), Apex 5x300K cycle and FundedNext Rapid x5 sims
  (F/2026-10-25-apex-5x300k-cycle-..., F/2026-10-30-fundednext-rapid-pro-25k-x5-...), Vest rinse sim (F/2026-10-30-vest-5x5k-...).

## Limits for the night
- Pipeline stays OFF (no `pipeline_*`, no `bp.py pipe`, no payout pipeline or its lock file).
- No commit to main (main ships to the trading server by itself), nothing on the Desk, no live or paper account touched.
  Drafts go to `~/.homebase/strategies/`, scripts and outputs to `research/edge-library/prop_rinse_2026-11-02/`.
- The Mac stays awake; at most the machine's backtest cap at once.

## Morning report (one page, plain words)
1. The best plan for A and for B, each firm: a small table (pass %, payout %, chance of >=1 payout, days, $ net per $500).
2. The exact setup (rule, stop, target, size per account, which plan) so it can be run tomorrow.
3. What was tried and died, in one line each.
4. Saved as a finding note in the vault + a pointer in the memory index.
