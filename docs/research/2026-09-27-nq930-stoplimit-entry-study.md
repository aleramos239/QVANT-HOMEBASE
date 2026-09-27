# NQ 9:30 straddle: would Stop-Limit entries improve the fills? (study, 2026-09-27)

Status: **PREREGISTERED** (commit ef7a8d1, before any run) — **RESULTS appended below.**
Nothing above the "Results" heading changed after the prereg commit except this status line.

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

Run 2026-09-27 on the prereg commit's rules (engine commit 867fbce), script
`docs/research/nq930_stoplimit_study.py`, raw numbers in
`docs/research/2026-09-27-nq930-stoplimit-entry-study.json`.

- Sample: 825 NQ sessions 2021-09-22 → 2024-12-31, 2 skipped for coverage holes, 823
  trades in every cell. 2025+ not loaded (the script asserts it).
- Live desk config confirmed through `desk_cfg`: off 5 / SL 5 / TP 15, ungated, cancel
  12:55, flat 15:55.
- **Default is byte-identical:** the baseline trade ledger from this branch (default
  inputs, and `entry_limit_ticks = 0`) hashes the same as the ledger from `main`'s engine
  (sha256 `456ba86e…`). Golden parity 22/22 (21 sessions + the fixture check).

Per contract, $4 round turn. RR is the realised avg win : avg loss (1:2.70 in every
stop-limit cell). "Capped" = fills on the baseline's own entry print at a better price.
"Switched" = a different entry print than the baseline (every one the same side,
filled later on the resting limit).

| cell | filled | missed | switched | capped | WR | net $ | avg $/trade | PF | Sharpe | t | maxDD $ | green yrs | yrs ≥ base | helps (rule) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (stop-market, 1 t) | 823 | 0 | – | – | 26.9% | −652 | −0.79 | 0.99 | −0.07 | −0.13 | −5,779 | 2/4 | – | – |
| SL+1 | 823 | 0 | 19 | 61 | 26.7% | −1,027 | −1.25 | 0.98 | −0.11 | −0.20 | −6,159 | 2/4 | 3 | no |
| SL+2 | 823 | 0 | 14 | 5 | 26.9% | −627 | −0.76 | 0.99 | −0.07 | −0.12 | −5,774 | 2/4 | 4 | yes |
| SL+3 | 823 | 0 | 9 | 5 | 26.9% | −652 | −0.79 | 0.99 | −0.07 | −0.13 | −5,784 | 2/4 | 3 | yes (tie) |
| SL+4 | 823 | 0 | 8 | 1 | 26.9% | −637 | −0.77 | 0.99 | −0.07 | −0.12 | −5,774 | 2/4 | 4 | yes |
| SL+6 | 823 | 0 | 3 | 3 | 27.0% | −247 | −0.30 | 1.00 | −0.03 | −0.05 | −5,784 | 2/4 | 3 | yes |
| SL+8 | 823 | 0 | 2 | 1 | 26.9% | −647 | −0.79 | 0.99 | −0.07 | −0.13 | −5,784 | 2/4 | 3 | yes |
| *baseline, 0 t slip* | 823 | 0 | – | – | 27.8% | +5,668 | +6.89 | 1.09 | 0.60 | 1.10 | −3,368 | 2/4 | – | – |
| *baseline, 2 t slip* | 823 | 0 | – | – | 25.5% | −8,177 | −9.94 | 0.88 | −0.86 | −1.59 | −9,904 | 1/4 | – | – |

Net by year ($, per contract):

| cell | 2021 (Sep-Dec) | 2022 | 2023 | 2024 |
|---|---|---|---|---|
| baseline | −894 | −2,290 | +610 | +1,922 |
| SL+1 | −889 | −2,680 | +615 | +1,927 |
| SL+2 | −894 | −2,285 | +610 | +1,942 |
| SL+3 | −894 | −2,295 | +610 | +1,927 |
| SL+4 | −894 | −2,285 | +610 | +1,932 |
| SL+6 | −894 | −2,295 | +610 | +2,332 |
| SL+8 | −894 | −2,295 | +610 | +1,932 |
| baseline 0 t | −624 | −155 | +2,760 | +3,687 |
| baseline 2 t | −1,164 | −4,905 | −2,350 | +242 |

At the book's 10 contracts every dollar figure is ×10 (e.g. baseline −$6,520, maxDD
−$57,790); WR, PF, Sharpe and t are unchanged.

Descriptive (not a cell): how far past the trigger the triggering print sat, on the 823
baseline entries: **0 ticks 743 (90.3%)**, 1 tick 61 (7.4%), 2 ticks 5, 3 ticks 5,
4-10 ticks 9 (2.3% at 2+ ticks; max 10).

Where each cell's difference from the baseline comes from:

| cell | capped fills: net change | switched fills: net change | trades whose outcome flipped |
|---|---|---|---|
| SL+1 | +$10 on 61 fills (1 tick better = $305 of entry price) | −$385 on 19 | 3 |
| SL+2 | +$5 on 5 | +$20 on 14 | 2 |
| SL+3 | $0 on 5 | $0 on 9 | 2 (one each way) |
| SL+4 | $0 on 1 | +$15 on 8 | 2 |
| SL+6 | −$5 on 3 | +$410 on 3 | 1 |
| SL+8 | $0 on 1 | +$5 on 2 | 0 |

### Verdict against the preregistered rule

By the letter of the rule, **SL+2 is the smallest cell that "helps"** (SL+3, 4, 6 and 8
also pass; SL+1 fails on net). But the rule has no minimum effect size and passes ties:
SL+2's "gain" is +$25 over 823 trades ($0.03 a trade), and every cell's difference comes
from 0-3 trades whose outcome flipped (SL+6's +$405 is one trade). **Plain reading: a
Stop-Limit entry makes no measurable difference to the NQ 9:30 straddle under this fill
model.** Not supported as an improvement; not refuted as harmful either (except SL+1,
slightly negative).

### Why it makes no difference (plain English)

1. **The open rarely gaps the trigger.** Nine entries in ten trigger on a print exactly
   at the stop price, so a stop-limit fills at the same price as the stop-market.
2. **The desk moves the bracket to the fill.** SL and TP sit a fixed distance from the
   actual fill, so every trade wins +15 pts or loses −5 pts (minus exit slip and
   commission; the rare 15:55 time exit aside) whatever the entry price was. A better entry only shifts the bracket; it
   does not add dollars. SL+1 got 61 entries one tick better ($305 of price) and that
   was worth $10 of P&L.
3. **When the trigger does gap past the limit, price comes straight back.** No cell
   missed a single trade: every gapped order filled on the whip-back, median ~40-60 ms
   later (max ~142 s). The whip-back fills are slightly worse on average at SL+1
   (−$385 on 19): when price snaps back through the limit the breakout was weaker.
4. **What does move the result is slippage itself**, and most of that is on the
   protective stop, which a stop-limit entry does not touch: 0 / 1 / 2 ticks per side
   gives +$5,668 / −$652 / −$8,177 per contract, roughly $7k per tick over 823 trades.

### Caveats

- **The model fixes touch slippage at 1 tick.** On a touch print the stop-market pays
  trigger + 1 tick and a stop-limit N ≥ 1 pays the same. If live stop entries routinely
  slip 2+ ticks (a queue behind the stop run), a +1/+2 tick limit could cap that — and
  could then miss trades the engine cannot see. This study cannot answer that; only live
  fills can.
- **Capped fills assume the limit fills whenever the print is inside it.** A real
  marketable limit behind the stop queue may not. Here that affected 1-61 fills per cell
  and was worth ≤ $10, so it does not change the verdict.
- **Resting fills use the house 1-tick penetration rule**, a proxy for queue position,
  not a queue model.
- **Live fill quality is unmeasured** until the fill-quality tracker (plan Task 3)
  exists. That is the next evidence, not another backtest.
- The baseline's own result on this window (PF 0.99, t −0.13) is context, not a new
  verdict on the strategy: the 2021-24 window is ~300+ cells deep for this family, and
  this study was about the entry order, not the signal.
- The study adds 7 cells + 2 slippage lines of exposure on 2021-24 for the NQ
  930-straddle family (same signal, execution variants only).

**Recommendation:** keep the desk on stop-market entries. Revisit only if the fill tracker
shows routine entry slippage of 2+ ticks.
