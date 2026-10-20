# Review: NQ 15-min FVG on the side of the 09:30 open, no limit (2026-10-19)

Files: `~/.homebase/strategies/nq_fvg_oside_15_r075.py`, `nq_fvg_oside_15_r1.py` (identical but `rr` 0.75 / 1.0). Lab copies of the engine
family `fvg_oside` (`research/edge-library/engine/families/fvg_oside.py`), sheets `owner_fvg_oside_15_a1m3_nl_r075` / `_nl_r1`.
Going to the Desk OFF / shadow / no account.

Parity (tester, build days, 1 MNQ, $1 RT + 1 tick) vs the engine study (1 NQ, $4 RT + 1 tick):
r075 1,669 vs 1,661 trades, 61.2 vs 61.5 % win, long/short even in both, 2023 the losing year in both; r1 1,660 vs 1,652, 54.0 vs 54.1 %.
Runs `20261019-220349-draft_nq_fvg_oside_15_r075-350b`, `20261019-220427-draft_nq_fvg_oside_15_r1-b6ea`. Differences: flat 15:55 (Desk cap) vs 15:58.

## 1. Look-ahead bias — PASS
Every decision is taken in `_close15` at a 15-minute close from bars that have closed: the side is that close (`c3`) against the 09:30
minute's open (`open_px`, set from the bar that starts at 09:30); the gap is the three newest closed 15-minute bars, all starting at or after
09:30 (`t_ns >= open_ns + 45 min`); the stop reads the 14 newest closed 1-minute bars (`_atr1`, the bar that just closed included). The
limit is placed after that close, only on the passive side of the last print. The engine family has the same rule and synthetic tests
(`engine/tests/test_fvg_oside.py`, 9 tests).

## 2. Repainting — N/A
Python on closed bars; nothing is redrawn after the close.

## 3. Overfitting — FAIL (risk, not a code bug)
About 30 variants of this one idea were read on 2026-10-19 (5 vs 15-min bars; middle-candle, tf-ATR and 1-min-ATR stops at 1 / 2 / 2.5 / 3x;
targets 0.5 .. 1.875; 1 a day vs no limit). The 3x 1-min ATR, 15-min bars and no limit were all chosen after seeing build-day results.
The 3:1 block walk-forward passed P6.1-P6.4 for both sheets, but its unseen months (2025-07-01 .. 2026-09-22) had already been read for
the 1-a-day version of the same rule, so they are not fully blind. Inputs a person can change: 3 (atr_mult, rr, max_trades); no filters.

## 4. Position sizing & risk — WARN
Stop = 3 x 1-min ATR: median 30.5 pts, 99th percentile 99 pts, max 516 pts (2025-04-07) = $1,032 on ONE micro. Worst build-day trade
-$3,979 on NQ = about -$398 on one micro. Before any account: set the Desk's "most at risk per trade" (about $250 on one micro would skip the
widest ~1 % of stops) and size in micros only. Brackets: the stop and target ride on the entry (`limit_entry(..., sl=, tp=)`,
`move_brackets_to_fill`), so they are at the broker from the fill.

## 5. Live-readiness — FAIL for an account (shadow is fine)
- The entry is a LIMIT order. The Desk door refuses it: "Limit entries are not built yet." (`homebase/labrun/door.py`). It cannot be booked
  on any account until limit entries are built. Shadow only.
- Flat 15:55 ET (before Lucid's 16:10): PASS.
- Microscalping: median hold 12-18 min; trades under 5 s are 0.3 % of trades and 0.15 % of profit: PASS.
- One position at a time, one market: no hedging inside the strategy. Do not run both rows on the same account (one strategy per market per
  account is the Desk's rule anyway).

## 6. Funnel — PASS
About 1.75 trades a trading day (37 a month); 94 % of days trade.

## Verdict
Safe to put on the Desk OFF, in shadow, with no account. Not bookable until the Desk takes limit entries; before then, a per-trade risk cap
and paper first. Watch the shadow's "Matched the backtest" lines for the first weeks.
