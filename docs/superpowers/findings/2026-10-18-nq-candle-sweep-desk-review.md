# Strategy review: NQ CANDLE SWEEP (micro) -- `~/.homebase/strategies/nq_candle_sweep_desk.py` (2026-10-18)

Lab draft `draft_nq_candle_sweep_desk`, heading to the Desk switched OFF, shadow, no account. NQ prices, MNQ orders, own size
round(risk / (stop x $2)) in 1..10 micros (risk $500); 15-minute candles from 1-minute bars; at the 09:45-10:45 closes a candle that
sweeps the previous candle's low (high) and closes back into its body = long (short), only long above / short below the 1-hour EMA 50;
stop at the sweeping candle's extreme (floor 0.25 x ATR14 of the day's 15-minute candles), target rr x the stop (0.5 default; 0.75 / 1 in
the Setup panel); one trade at a time; stop for the day once the day is in profit; flat 15:58. The EMA's earlier sessions come from the
new `ctx.hourly` feed (`needs_hourly` = 30 sessions, main c1e3e589); today's hours from 00:00 out of its own bars.
Backtests (all data 2021-09-22 -> 2026-10-16, $1 a micro round turn, 1 tick slippage): 0.5R 882 trades +$6,784 PF 1.05 t 0.66;
0.75R 890 +$15,648 PF 1.09 t 1.24; 1R 900 +$25,612 PF 1.13 t 1.75. Parity with the research rule (grid
20261018-160546-...-b1dd, stop once in profit, same sizing): 849 of 878 trades identical at 0.5R, 870 of 900 at 1R; the rest come from
the EMA's missing 18:00-24:00 hours of the evening before (a session that opens the evening before cannot be booked on the Desk).

## 1. Look-ahead bias -- PASS
- Decisions read closed 1-minute bars only (the 15-minute candle closes on its last minute; previous candle and ATR are closed candles).
- The EMA reads 1-hour closes of hours that have ENDED by the decision (`_ema`, `(k + 1) * HOUR <= t_ns`) and the earlier sessions'
  closes from `ctx.hourly`, which never holds today or later (backtest/hourly.py: only sessions before the date; tests).
- The day's result is counted from the minute a trade went flat in: the past only.

## 2. Repainting -- N/A (Python, bar-close decisions)

## 3. Overfitting -- FAIL (risk to accept)
- The sweep family was looked at in about 35+ versions; the EMA 50 and the target were picked on the 3:1 blocks' in-sample months,
  but "stop once in profit" was chosen after seeing the out-of-sample months (hindsight).
- **The default 0.5R is the weakest choice: t 0.66 over all data, out-of-sample (research) +$2.2k, t 0.45.** 1R is the strongest
  (t 1.75 all data). Shorts are about flat at every target; the longs carry it.

## 4. Position sizing & risk -- FLAG
- Risk per trade ~$495 (median); one trade risked $2,004 (1 micro on a 1,002-point stop, the April 2025 tariff week); worst trade -$651.
- Worst day -$1,735; days at or below -$1,200: 3 in five years (all three targets). A $1,200 daily limit would be breached on those days.
- **Proposed before any funded account (not applied):** skip a trade whose 1-micro risk exceeds 1.5 x risk; a day loss stop at -$1,000.
- Brackets go with the entry and are moved to the fill (the Desk's own path). The account's size caps the micros. The day's result is
  the runner's shadow view, not the account's fills.
- **The feed:** until the Desk runner is restarted on main c1e3e589 it does not send `ctx.hourly`; the script then has fewer than 50
  closes and takes no trade (fail-safe). After the restart, an unreadable or stale feed stops the day (as the daily bars do).

## 5. Live-readiness (Lucid) -- PASS
- Flat 15:58 ET. Median hold 581 s (0.5R) / 918 s / 1,282 s; under 5 s: 5 trades with 0.8 % of the profit -- not microscalping. One
  direction, one account.

## 6. Funnel -- PASS
- About 14 trades a month; trades on about 63 % of days.

## Verdict
**Safe to put on the Desk switched OFF, in shadow, with no account.** Before booking a funded account: the risk cap and day loss stop of
check 4, and weigh check 3 -- at its 0.5R default the edge is not distinguishable from zero (t 0.66); 1R is the setting with an edge on
these numbers.
