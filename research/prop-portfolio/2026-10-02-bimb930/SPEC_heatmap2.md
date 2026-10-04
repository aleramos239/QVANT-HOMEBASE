# Heat map v2: $1,000-risk micro sizing + combined volume/orders signals + Sharpe (pre-registered 2026-10-02, BEFORE any run)

User: "re run it but make it so that every single trade is adjusted to risk as close to $1000 as possible with micros, also add two new maps,
combine the volume and orders, when they both agree enter ... then if more buy volume but more sell orders then long, vice versa for shorts, and
inverse - also include sharpe".

## Sizing (every cell, every trade)
- micros = clamp(round(1000 / (stop_distance_pts x $2)), 1, 170); stop distance = |entry fill - stop| from the fill (fixed 10..30 pts, or k x ATR14(5m)
  at 09:30). 170 micros = Apex Legacy 300K half-size cap (until the safety net); the number of capped trades is reported.
- Net per trade = gross(1 NQ, from the simulator; slippage is inside the fill prices) x micros/10  -  micros x $1.04 (Apex's published MNQ round-turn
  commission, the dearer of Tradovate / Rithmic as apex300.py uses). Dearer than the tester's $4/NQ ($0.40/micro): sizing in micros costs more.
  Sizing is applied offline: position size does not change fills in the simulator (it models no market impact).
- Metrics from the sized trades: net, win rate, PF, Sharpe (mean/sd x sqrt(252) of per-trade = per-day P&L), max drawdown (closed trades), expectancy,
  per-year the same, average micros, trades capped.

## Signals (all as in earlier specs; 2021-09-22..2024-12-31 only, entry 09:30:00 market, one trade a day, flat 15:58 ET)
- book top-10 `imb`/`imb_inv`, wide-ladder `wimb`/`wimb_inv`, volume `flow`/`flow_inv` (15-min pre-open f_delta), each with always-long/short controls.
- NEW combined (volume sign `v` = sum f_delta of the 15 pre-open minutes; orders sign `o` = sign of wide-ladder `wimb`, +1 = more resting size below = "more buy
  orders"; a day needs both valid and non-zero):
  * `agree`      : v and o both +1 -> LONG; both -1 -> SHORT; they disagree -> no trade.        `agree_inv`: the same days, opposite side.
  * `dis`        : v = +1 and o = -1 (more buy volume but more sell orders) -> LONG; v = -1 and o = +1 -> SHORT (volume decides); agree -> no trade.   `dis_inv`: same days, opposite side.
  * controls on the same day sets: `long_agree` / `short_agree` (always long / short on the agree days), `long_dis` / `short_dis`, `long_all` / `short_all` (all days with both signals).
  "Orders" uses the wide ladder (the "more orders above / below" version asked for last); the top-10 version is a one-word swap if wanted.

## Grid, as before (30 cells per direction): fixed stops 10/15/20/25/30 pts and 1/1.5/2/2.5/3 x ATR14(5m) stops, each at 1:1, 1:2, 1:3.
## Reported: the heat map (net, Sharpe, win rate vs breakeven, PF), any cell with win rate > 60%, top cells per year, signal cells vs their day-matched control.
Multiple-testing note: now ~600 signal cells and as many controls on overlapping days; the best cell is flattered by selection (a signal cell is only
interesting if it beats the control on the SAME days). No null grids unless a cell passes >60% win rate or clearly beats its control. One run, no retune.
