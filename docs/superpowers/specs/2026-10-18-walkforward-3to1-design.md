# Walk-forward 3:1 replaces the one unseen read (design, 2026-10-18)

The owner, 2026-10-18: "add walk forward optimization, still 75% IS and 25% OOS but month to month" — then "add it to the lab
completely, to the pipeline and the run settings in the panel, i want to start going off this … the metrics in the desk this will
be the new unseen days in the metrics card".

## The scheme — BLOCKS (changed 2026-10-18, the owner: "lets keep it the blocked version ... i dont want to use rolling")

Pick on 3 whole months, trade the next 1, then the next block: Jan–Mar pick → Apr trade, May–Jul pick → Aug trade. Every month is
in-sample or out-of-sample, never both. (The first version below was rolling; it is retired everywhere.)

## The first version (rolling, retired)

Rolling 3:1. Each step picks on the last 3 whole months and trades the pick on the next 1 month, then steps forward one month.
The stitched out-of-sample record is every test month joined, each month tested once and never overlapping.

| Step | Pick on (75 %) | Trade on (25 %) |
|---|---|---|
| 1 | Oct–Dec 2021 | Jan 2022 |
| 2 | Nov 2021–Jan 2022 | Feb 2022 |

## The owner's decisions (2026-10-18)

| Question | Answer |
|---|---|
| Window | **All data**: 2021-09-22 → today. Tuning windows reach into Jul 2025+, which ends "tune only on build days". |
| Pipeline | **The 3:1 walk-forward replaces stage 6** (the one test-days read). |
| Pick rule in the pipeline | **The pipeline's own pick** (the middle passing box by average trade, never the best), per 3-month window. |
| Desk card | **Replaces "Unseen days"** with the stitched 3:1 record. |
| Live settings | **Notify, the owner changes them.** The Desk says when this month's 3:1 pick differs from what runs; it never switches itself. |

This changes house law: CLAUDE.md, BLUEPRINT.md section 2 and the strategy-blueprint skill say the test days are read once,
only for a locked strategy. After this, every month after the first three is out-of-sample for its own pick, and there is no
single held-back read any more.

## 1. Engine (done 2026-10-18, uncommitted)

`homebase/backtest/walkforward.py`: `select_months` 1 (the 1:N schemes) or 3 (3:1, test_months must be 1). A 3-month window
is scored from the cell's own trades over those months (one run over the window). Every step is in the chain. The in-sample side
sums the overlapping windows: per-month net is the average leg month, Sharpe is the legs' mean, max drawdown the worst leg's.
`POST /api/tester/walkforward {select_months: 3, test_months: 1}`, `GET /walkforward-scheme?select_months=3&test_months=1`,
chat tool `walkforward(ratio="3:1")`, tester range pill "Walk-forward 3:1". Tests: `tests/test_backtest_walkforward.py`
(3:1 block), `tests/js/wfcompare.test.mjs`.

## 2. Lab

- The Lab's **Run settings** Range select (`static/charts/lab.js` `settingsHtml`) gains Walk-forward 3:1 (and the 1:N
  schemes), composing with the window as the tester pill does (`range.wf`). Range = All by default when 3:1 is picked.
- Run in the Lab starts the walk-forward over the Heat-map tab's axes; the result fills the Lab's results column: stitched OOS
  tiles, the in-sample side, the drop, the stitched equity, the step table (pick per month), and the List of trades.
- **The pick for this month** (see 4) is shown under the result.

## 3. Pipeline: stage 6 becomes the 3:1 walk-forward (built by the pipeline session, research/edge-library/ only)

- Stage 1's grid (144 cells per map: variant × stop × target) is run over **all days** once, in a new engine switch that opens
  both ranges (`l2sim.check_holdout`, `runner.seal` / `guard` learn an "all" kind; the build-only and test-only switches stay).
  The random-entry pool is run over all days the same way.
- For each test month M from the 4th whole month on: on months M-3..M-1 take the pipeline's own pick (`_holding` → `_pick`,
  the build-day rows judged on that window), trade it in month M. Stitch.
- Stage 6's stops, on the stitched record: **P6.1** net > $0; **4.4** the stitched record beats 95 % of random tables, each month
  matched against that month's pick's exit cell in the random pool (the same per-date draw as `lines.beats_random`); **P6.3** win
  rate ≥ realized-R:R breakeven + 3 points (`G.wr_rr` on the stitched nets).
- `test_reads.jsonl`'s one-read claim retires for stage 6 (each month is its own read). The book card shows the stitched record
  and the pick for this month.
- Stages 4 and 5 stay (proof on build days, the lock); the lock now freezes the **scheme** (grid + pick rule), not one box.

## 4. Desk card

- "Unseen days" on a promoted strategy's metrics card = the stitched 3:1 OOS record (net, trades, WR, PF, deepest drawdown,
  realized RR, Sharpe, equity curve, prop sim) from a tester walk-forward over all days on the strategy's Desk-changeable
  settings (`rec["settings"]`, 2–3 inputs) at its size, started automatically like `ensure_unseen` today, re-run when a new
  month completes.
- The walk-forward result carries `next`: the pick on the last 3 whole months = the pick for the current month. When it differs
  from the strategy's running inputs, the card shows a notice: "3:1 pick for <month>: <settings> (running: <settings>)". The owner
  changes the settings in the Desk Setup panel. Nothing switches by itself.
- A strategy with fewer than 2 or more than 3 changeable settings says so in place of the record (the tester grid takes 2–3 axes).

## Status (2026-10-18, uncommitted in the main checkout)

1. Engine: done, with `next` (the pick for the month after the window).
2. Desk card + notice: done. `deskresults.wf_*`, `tester_api.ensure_wf` / `wf_block`, `desklab.js` (title, states, pick note).
   A number setting is searched at its value and ±25 % (shortcut; the record's settings carry ranges, not grids). The search
   uses the tester's rule (best net per window), not the pipeline's middle pick. No strategy is on the Desk today (all 18
   archived), so nothing has started by itself yet. Desk **groups** still read the old test-days run (`ensure_unseen`).
3. Lab: done. Run settings › Heat map › Walk-forward (3:1, 1:1, 1:2, 1:3) + Run walk-forward; the result renders under it
   (both sides, the drop, next month's pick, the step table). A page reload does not bring the result back yet.
4. Pipeline stage 6: the pipeline session (`research/edge-library/` only).
5. House law text: CLAUDE.md waits for the owner's word; BLUEPRINT.md and the skills are the pipeline session's.

## Blocks + Lab views (2026-10-18, later)

Tester engine: `ROLL_STEP = 4` (blocks), `stitched_is.equity`, realized RR (`rr`, `rr_label`) in every side's stats. Desk card
ignores rolling jobs (`step_months` must be 4). Lab Range: "3:1 in-sample", "3:1 out-of-sample", "3:1 in + out-of-sample" (both
curves on one chart, the two sides in two columns); Block by block fold closed by default. Pipeline: the pipeline session
(`pipe_wf.py`, `pipeline.json walkforward.step_months 4`).
