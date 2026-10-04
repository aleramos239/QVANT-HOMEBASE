# Heat map over stop type x stop size x reward:risk for the 09:30 direction signals (pre-registered 2026-10-02, BEFORE any run)

User: "run a heat map for these 4 plus the 4 volume based ones, between 10-30 based stops on 1:1,2,3 and also ATR based stops, 14 candle
lookback, on 1x, 1.5x, 2x, 2.5x, 3x also on 1:1,2,3; let me know if there is a variant with over 60% profitable".

## Signals (each: normal and inverse) — 6 signals, 12 directions
- wide-ladder imbalance `wimb` / `wimb_inv` (SPEC_wide.md), volume `flow` / `flow_inv` (SPEC_flow.md, 15-min pre-open f_delta),
  and (added, not asked for, cheap) top-10 `imb` / `imb_inv` (SPEC.md). Plus always-long / always-short controls on each
  signal's own day set. Entry exactly as before: market at 09:30:00, one trade a day, flat 15:58 ET, 2 NQ, tester cost law.

## Grid (per direction): 30 cells
- Fixed stop: 10, 15, 20, 25, 30 pts (steps of 5) x target = RR x stop with RR 1, 2, 3  -> 15 cells.
- ATR stop: 1, 1.5, 2, 2.5, 3 x ATR(14) x RR 1, 2, 3 -> 15 cells. ATR(14) = Wilder ATR over the last 14 COMPLETED 5-minute candles
  (the simulator's template ATR at tf = 5; the user did not name the candle size, 5 min is the template default) as of the
  09:30:00 entry; the stop distance is fixed from the fill and the target = RR x that distance.
- Size is fixed at 2 NQ in every cell, so dollar risk varies with the stop ($400 at 10 pts .. $1,200 at 30 pts).
- Window 2021-09-22..2024-12-31 only; 2025+ sealed.

## What gets reported
- Per cell: trades, win rate, net, profit factor, max drawdown, per-year net / win rate (stats), versus the always-long control cell.
- "Over 60% profitable": any cell whose win rate is above 60%, listed with its trades, net, and the same cell's control win rate.
- Multiple-testing note fixed now: 6 signals x 2 directions x 30 cells = 360 signal cells (+ 360 control cells), all on overlapping days and
  price paths. With ~780 trades per cell the win-rate noise is about +-1.8 points; the best of hundreds of cells will look better than the truth
  (winner's curse). A top cell is judged against null grids (shuffled signal) before it is believed; the null grids are run only for a signal
  that shows a cell above 60% win rate or a net > 0 cell clearly above its controls.
One run, no retune of the grid after seeing it.
