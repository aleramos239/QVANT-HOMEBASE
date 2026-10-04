---
date: 2026-09-29
strategy: nq_open_long / nq_open_short
files: homebase/rules.py, homebase/engine.py (_move_brackets), homebase/config.py
---

# Strategy review: NQ 9:30 open long/short (2026-09-30 only)

A market entry at the 09:30 open with fixed brackets: TP 120 ticks (30 pts), SL 45 ticks
(11.25 pts). Long on some accounts, short on others. There is no signal logic.

## 1. Look-ahead bias: PASS
`_open_930` reads only the **closed** 09:29 bar (`bars[-1]`, as `MarketFeed.tick`
emits it). The feed closes that bar on the first 09:30 push, or 3 s after 09:30 in a
quiet market. The entry is a market order placed after that. No future data is used.

## 2. Repainting: N/A
Python rule on closed bars. No Pine.

## 3. Overfitting: N/A
No parameters are tuned, and there is no backtest. This is a discretionary one-day
directional trade, so it has no statistical edge claim, positive or negative.

## 4. Position sizing & risk: PASS (sizing is the user's call)
- The brackets go on **at entry**, as one broker-side Tradovate OSO (`place_bracket`). A
  dead app never leaves a naked position.
- After the fill, `_move_brackets` modifies both legs to fill ∓45 / ±120 ticks. If a
  modify fails, the original brackets (from the 09:29 close) stay working. The position
  stays protected, just a few ticks off the target distances.
- The quantity comes from the book, which the user sets. Risk per contract is $225 at the
  SL. Keep qty × $225 under each account's daily-loss limit, with room for slippage at
  the open.

## 5. Live-readiness: FAIL on hedging, the rest PASS
- The desk force-flattens at **15:55 ET** (`flat_et`). PASS.
- Microscalping: N/A. The TP is 30 pts away.
- **Multi-account hedging: FAIL.** Long 2 accounts and short 2 accounts at the same
  moment is exactly the cross-account hedge that prop firms, Apex included, prohibit.
  One of the candidate accounts is an Apex PA (funded) account. Breaking this rule can
  close the account and void payouts. The user must accept this risk knowingly.
- Booking conflicts:
  - Do **not** book the same account under both `nq_open_long` and `nq_open_short`. The
    two positions net to flat, while two bots each believe they hold a position.
  - Account `apex3265980000053` already runs `nq930_1030` (35 NQ) at 09:30. Two bots on
    one NQ position confuse Kill/Flatten, which read the account's net position. Book a
    different account.
- Timing: the order fires about 1–2 s after 09:30:00. The bar has to close, and the feed
  loop runs every 1 s. This is less exact than the straddle timer's 09:30:00.000.
- If the feed is down at the 09:29 close, **no trade** is placed, and the refusal is
  journaled. The accept window (09:29–09:31) means the desk never enters late.

## 6. Funnel sanity: N/A
One day, one signal per strategy.

## Verification
- `tests/test_feed_rules.py`: 5 new tests.
  - Levels at 45/120 ticks.
  - Fires only on the 09:29 close and only on 2026-09-30.
  - Both brackets move to the fill.
  - No move when the fill equals the reference price.
  - The strategies ship disabled and unbooked.
- Full suite: 2321 passed. One test fails, `test_m2_get_settings_carries_an_accounts_block`,
  but it fails the same way on the untouched code, because it reads this machine's real
  accounts.
- The tester parity pin is unchanged (byte-identical).

**Verdict: the mechanics are safe to run. The one blocker is the cross-account hedge,
which is a prop-firm rules risk, not a code risk. It is the account holder's decision.
Book separate accounts (not ...053, and never one account on both sides), then restart
the desk before 09:20 ET.**
