# NQ 9:30 straddle: would Stop-Limit entries improve the fills? (study, 2026-09-27)

Status: **PREREGISTERED — written and committed before any run.** Results are appended
below the prereg in a later commit; nothing above the "Results" heading changes after
the prereg commit.

## 1. Question

The live desk enters the NQ 9:30 straddle with two OCO **stop-market** entries. On a fast
open the trigger print can gap past the stop, and the engine (like the exchange) charges
the gap plus slippage. A **Stop-Limit** entry caps that cost at `trigger ± N ticks`, at the
price of trades it never fills. Does any cap improve the book under the tester's
tick-accurate fill law?

This is an **execution study**, not a signal search. It compares entry order types on a
fixed strategy. It does not validate the strategy, and the answer is only as good as the
engine's fill model (see section 6).

## 2. Strategy (fixed, not tuned)

- `nq930` at the **desk's live config**, read through `desk_cfg("nq930")` from the live
  checkout's `homebase/config.json` on 2026-09-27: offset ±5.0 pts, SL 5.0 pts, TP 15.0 pts
  (RR 1:3), **ungated** (`gated: false`), unfilled entries cancelled 12:55 ET, open position
  flat 15:55 ET. The script asserts these values before it runs.
- Anchor = the last print before 09:30:00.000 ET; orders go live 85 ms later; brackets
  re-priced to the fill (the desk's `_move_brackets`); SL/TP are OSO on the entry.
- Size: **1 contract** (dollar figures are per contract; the engine fills the whole
  quantity at one price, so the book's 10 ct is exactly ×10 on every dollar figure, and WR,
  PF and Sharpe are unchanged).

## 3. Data window

- Research window 2021-01-01 → 2024-12-31 (`discipline` "research"). The NQ tick archive
  starts 2021-09-22, so the effective sample is 2021-09-22 → 2024-12-31.
- Sessions with coverage holes are skipped exactly as the tester runner skips them
  (CME half days clamped first).
- **2025+ is not loaded.** No per-use approval exists for it.
- Exposure note: this window is already ~300+ cells deep for the NQ 930-straddle family
  (burned-data ledger). This study adds 7 cells + 2 slippage lines on it, all on the same
  signal; it spends nothing new on 2025+.

## 4. Cells (7, fixed before the run)

All at **1 tick of slippage per side** on market and stop fills, **$4.00 per round turn**.

| # | Cell | Entry order |
|---|------|-------------|
| 0 | baseline | stop-market (today's desk; `entry_limit_ticks = 0`) |
| 1 | SL+1 | stop-limit, limit = trigger + 1 tick (buy) / − 1 tick (sell) |
| 2 | SL+2 | stop-limit, limit 2 ticks through the trigger |
| 3 | SL+3 | stop-limit, limit 3 ticks through |
| 4 | SL+4 | stop-limit, limit 4 ticks through |
| 5 | SL+6 | stop-limit, limit 6 ticks through |
| 6 | SL+8 | stop-limit, limit 8 ticks through |

Sensitivity lines (not candidates): the baseline at **0** and **2** ticks of slippage.

Stop-limit fill law (the engine's `stoplimit` kind):

1. It triggers on the first print at or through the trigger (buy: print ≥ trigger).
2. If that print is inside the limit (buy: print ≤ limit), it fills on that print at
   `min(print + slip, limit)` (sell: `max(print − slip, limit)`).
3. If the triggering print gapped past the limit, it rests as a limit at the limit price
   and needs a 1-tick penetration to fill (buy: a print ≤ limit − 1 tick), at the limit,
   no slip.
4. It is cancelled with the other entry at 12:55 ET. OCO: the first leg to **fill**
   cancels the other; a triggered-but-resting leg does not.
5. Brackets are sized from the trigger and re-priced to the actual fill, as today.

## 5. Metrics and decision rule

Per cell: filled trades, **missed** trades, WR, net $, avg $/trade, PF, Sharpe (the
report's weekday-grid Sharpe), maxDD $, and green years (of 2021 partial, 2022, 2023,
2024). Also per cell: **switched** sessions (the cell traded a different side or a
different entry print than the baseline) and the number of fills **capped at the limit**
on the baseline's own entry print (the part of any gain that rests on the fill model).

- **Missed** = a session where at least one entry leg triggered but no entry filled
  before the 12:55 cancel.

**Decision rule (fixed now).** A cell **helps** only if all three hold, each against the
baseline at the same 1 tick of slippage:

1. net $ ≥ the baseline's net $;
2. missed ≤ 15% of the baseline's filled trades;
3. the cell's net $ ≥ the baseline's net $ in **≥ 3 of the 4 calendar years**
   (2021 is Sep-Dec only).

If several cells help, the report names the **smallest N that helps** and does not pick
the best-of-7 by net (that would be a selection on this window). If none helps, the
verdict is "not supported under this fill model", not "dead". Either way, the live
answer needs live fills; the fill tracker does not exist yet.

## 6. Known limits of the answer (stated before the run)

- The engine's stop fill is `print + slip` on the trigger print. A stop-limit caps that
  at the limit, so when the trigger print sits inside the limit the model fills at
  `min(print + slip, limit)` — it assumes the limit gets filled whenever the print is
  inside it. At the real exchange a marketable limit behind the stop queue may not fill
  at its limit on a thin open. The "capped" count measures how much of any gain rests on
  that assumption.
- The resting limit's 1-tick penetration rule is the house law for all limits; it is a
  proxy for queue position, not a queue model.
- Live fill quality is unmeasured until the fill-quality tracker (plan Task 3) exists.

## Results

_(appended after the run)_
