# Strategy review: NQ CANDLE BREAK (micro) -- `~/.homebase/strategies/nq_candle_break_desk.py` (2026-10-18)

Lab draft `draft_nq_candle_break_desk`, heading to the Desk switched OFF, shadow, no account. NQ prices, MNQ orders, own size
round(risk / (stop x $2)) in 1..10 micros (risk $500), 15-minute candles built from 1-minute bars, a close beyond the previous candle's
wick entered with it at the 09:45-10:45 closes, stop at the candle's extreme (floor 0.25 x ATR14 of the day's 15-minute candles), target
rr x the stop (0.5 default; 0.75 / 1 in the Setup panel), one trade at a time, stop for the day once the day is in profit, flat 15:58.
Backtests (all data 2021-09-22 -> 2026-10-16, $1 a micro round turn, 1 tick slippage): 0.5R 1,653 trades +$25,626 PF 1.10 t 1.84;
0.75R 1,678 +$45,286 PF 1.14 t 2.62; 1R 1,669 +$63,429 PF 1.17 t 3.19. Parity with the research rule: 1,651 of 1,652 trades identical.

## 1. Look-ahead bias -- PASS
- A decision reads only closed 1-minute bars: the 15-minute candle closes on the minute that ends on a 15-minute boundary (line 88);
  the previous candle and the ATR are closed candles (`_finish`, lines 105-114). The market order fills after the placement latency.
- The day's result is counted from the minute the trade went flat in (lines 63-74, 77-78): the past only.

## 2. Repainting -- N/A (Python, bar-close decisions; nothing redrawn)

## 3. Overfitting -- FAIL (risk to accept, not a code bug)
- About 35+ versions of the sweep / break family were looked at on NQ NY morning. The plain no-cap break FAILED its one-time unseen
  read (2026-10-18: PF 1.04, second half -$8.4k).
- The settings come from the 3:1 block walk-forward's in-sample months (good), but **"stop once in profit" was chosen after seeing the
  out-of-sample months** (hindsight). The default 0.5R is the weakest choice out of sample (15 months +$11.0k, t 1.57); 0.75R / 1R were
  stronger there (t 1.79 / 1.65 with the stop rule; t 2.08 / 1.89 without it).
- 4 of the 15 out-of-sample months overlap the failed unseen read. Only new days can confirm it: shadow first.

## 4. Position sizing & risk -- FLAG
- Risk per trade ~$500 (median); max $1,142 on one trade; worst trade -$664 (0.5R). Brackets are attached with the entry and moved to the
  fill (`move_brackets_to_fill`): a modify after the fill (the Tradovate "200 is not done" lesson) -- the Desk's own path, as for every
  Lab strategy.
- "Stop once in profit" lets a day keep trading after losses: worst day -$1,700; days at or below -$1,200: 7 (0.5R), 11 (0.75R),
  14 (1R) in five years. On an account with a $1,200 daily loss limit (LucidPro 50K / LucidFlex DLL) those days breach it, and Lucid
  counts open losses.
- **Proposed fix before any funded account (not applied):** a day loss stop in the script (no new trade once the day is at or below
  -2 x risk, i.e. -$1,000), and/or a cap that skips a trade whose 1-micro risk exceeds 1.5 x risk.
- The account's size on the Desk caps the micros (at most 10); the script counts the day with its own size, so a smaller account size
  changes the dollars but not the stop decisions.
- The day's result is the runner's shadow view (target / stop prices), not the account's real fills.

## 5. Live-readiness (Lucid) -- PASS
- Flat 15:58 ET (before 16:10). Median hold 742 s (0.5R) / 1,252 s / 1,712 s; holds under 5 s: 10 trades (0.6 %) with 0.5 % of the
  profit -- not microscalping. One direction at a time, one account: no hedging.

## 6. Funnel -- PASS
- About 27 trades a month (5.5 a week), 95 % of days trade.

## Verdict
**Safe to put on the Desk switched OFF, in shadow, with no account.** Before booking a funded account: add the day loss stop of check 4
(or book it only where the daily limit is above $1,700), and let shadow / paper days confirm it -- check 3 says the build-and-pick numbers
alone do not.
