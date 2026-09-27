# Strategy Tester — deep, tick-accurate backtesting on the chart page

Date: 2026-09-26 · Status: **APPROVED** by the user in chat ("YES, to both").

The user asked, with a screenshot of TradingView's Strategy Tester on the desk's NQ 9:30 Straddle:
"i want to be able to have like a deep backtesting like the tv pinescript backtesting, where i can see and
test our strategys and i can see the metrics etc."

Decisions stated in chat, which the user did not object to:
- Strategies are **Python, written once and shared with the desk**. There is no Pine interpreter.
- The date range **defaults to the research window 2021–2024**. 2025 and later sits behind an explicit
  switch, and each such run is logged as a spend.

## Why tick-accurate

The research proved that bar-based fills flatter stop-entry brackets:
- TradingView's intrabar path chose the target in 9/9 and 78/78 documented contradictions;
  `research/nq_930_straddle_ticks.py` `tv_path_outcome`.
- On real ticks, the NQ 9:30 straddle that TradingView shows at +$14.5k over 365 days is a losing coin
  flip over 2021–2024.

A tester the user can trust must replay the tape.

## What is reused (2026-09-26 code map)

| Piece | Source | How |
|---|---|---|
| Metrics | `~/ONYX TRADING/onyx/report/ledger.py` + `stats.py` (stdlib only) | **Vendored** into `homebase/backtest/stats/` with a provenance header. |
| Fill law | `research/nq_930_straddle_ticks.py` L22-31, the house law | **Generalised** into one engine; today it is copy-pasted per script. The law: a stop entry fills market-on-touch at `max/min(trigger, print) ± slip`, so a gap is paid. The target is a resting limit that needs **1-tick penetration** and fills at its price with no slip. The stop-loss fills touch/market with slip. Commission is flat per round turn. Ties at one `ts_ns` resolve in row order. |
| Tick cache | `research/dataset.py` per-session parquet tape (25× faster than gzip) | Same idea, homebase-owned cache (below). |
| Authoring shape, run bundle, chart drawing | `onyx/tester/api.py`, `web.py`, `_tester.html` | **Shape ported**: inputs / events / orders / plots, the run → status → bundle flow, markers + price lines. The 1-minute bar fill engine is **not** ported. |
| Holdout wall | `onyx/lab/holdout.py` (hard cut at 2025-08-01, budgeted spends) | Pattern ported (discipline below). |

## Strategy contract (`homebase/strategies/`, new)

One Python class per strategy, used by the tester now and by the desk later (see "Desk sharing").

- **Metadata:** `id`, `name`, `root`, `session_window` (ET start/end the strategy needs), and `inputs()`, a
  schema of `{key, label, type int|float|bool|choice, min, max, step, default}`.
- **Events:** `on_session(ctx)` at the window start; `on_time(ctx, et_time)` for scheduled times, e.g.
  09:30:00, 12:55, 15:55; `on_bar(ctx, bar)` for strategies that declare a bar size, with bars built from
  the same ticks.
- **Orders through `ctx`:**
  - `ctx.stop_entry(side, price, qty, sl=…, tp=…)`, `ctx.limit_entry(…)`, `ctx.market(side, qty, sl=…, tp=…)`;
  - `ctx.oco(a, b)`: the first fill cancels the other;
  - `ctx.cancel(order)`, `ctx.flatten()`;
  - `ctx.move_brackets_to_fill=True`: re-price SL/TP from the actual fill, like the desk's
    `_move_brackets`.
- **Plots** (optional): `ctx.plot(name, t, value)` and `ctx.hline(name, price)`, drawn on the chart with
  the run.

**v1 strategies:**

| id | what | source of truth |
|---|---|---|
| `nq930` | NQ 9:30 straddle: anchor = last print ≤ 09:30:00 ET; OCO stop entries at anchor ± offset (10); SL 5 / TP 15 pts from the fill; cancel unfilled 12:55; flat 15:55; optional ADX(14) daily trend gate ≥ 20 | the desk's `config.json` `nq930` + `engine._legs` + `gate.py` |
| `ym930` | the same family on YM (offset 20, SL 5, TP 15) | the desk's `ym930` |
| `nq10am` | NQ 10:00 30-minute candle continuation (top-quarter close, RR 1:0.75) | `homebase/rules.py` `nq_10am_continuation` |
| `gc_nfpcpi` | GC 08:30 NFP + CPI straddle: off 2 / SL 3 / TP 6 | `research/gc_0830_redfolder_straddle_ticks.py` + its event calendar CSV (copied into `homebase/strategies/data/`) |

Defaults equal the desk's live geometry; a pytest pins that.

## Engine (`homebase/backtest/`, new)

- **`tape.py`:** loads a root's session ticks from `~/futures_ticks/<ROOT>/<YYYY>/` (read-only; the front
  contract = the file with the most ticks for that session, the research rule).
  - Cache: per session, a parquet file of `ts_ns, price, size` under
    `~/futures_derived/homebase_tape/<ROOT>/<date>.parquet`, built on first use.
  - **Coverage check:** any clock hour inside the strategy's `session_window` with zero ticks → the session
    is **skipped and listed** in the report ("3 sessions skipped: missing 13:00–15:00 ET"). This covers the
    known Massive holes.
- **`engine.py`:** one strict-order pass over a session's prints per run.
  - Orders: stop / limit / market, OCO groups, OSO brackets, SL/TP re-priced to the fill.
  - Fills follow the house law exactly. Commission (default $4.00 RT) and slippage (default 1 tick per
    side on market/stop fills, 0 on limits) are inputs.
  - Scheduled cancels and flats happen at the first print at or after the time.
  - Records per trade: entry/exit time and price, side, qty, gross $, commission, net $, MAE/MFE (points
    and $), bars and seconds in trade, exit reason (`tp` / `sl` / `time` / `eod`).
- **`report.py`:** the vendored `stats` plus wrappers.
  - The TradingView-parity performance summary with **All / Long / Short** columns: net P&L ($ and %), gross
    profit/loss, commission paid, max drawdown ($ and %), max run-up, profit factor, # trades, win rate,
    avg trade $, avg win / avg loss $, ratio shown as **RR 1:X**, largest win/loss, avg time in trade, max
    consecutive losses.
  - Also **Sharpe** (daily P&L × √252), Sortino, the **t-stat** of the per-trade mean, expectancy.
  - Year and month tables, and equity and drawdown series.
  - Every money figure is in dollars (the user's rule: dollar metrics + Sharpe in every table).
- **`runner.py`:** runs `strategy × inputs × range` in a **separate process**, never in the chart service's
  event loop. It reports progress (sessions done / total) and writes a run bundle under
  `homebase/.state/tester/runs/<id>/` (`run.json` meta + inputs + range + coverage + report,
  `trades.json`, `equity.json`, `plots.json`). One run at a time; a new run queues; runs can be
  cancelled.
- **`discipline.py`** (the user's data rules, shown on every report):
  - **Ranges:** `Research window 2021–2024` (default), `IS months only (Jan/Apr/Jul/Oct)`, and `Custom`.
  - Any range reaching **2025-01-01 or later** needs the **Holdout** switch plus a one-line reason. Each
    such run appends `{ts, strategy, inputs, range, reason}` to `homebase/.state/tester/spends.jsonl`, and
    the report carries a red `Includes holdout` badge.
  - The assistant folds spends into the burned-data ledger note; the app never edits the vault.

## Chart service API (`homebase/charts/server.py`)

- `GET /api/tester/strategies` → the list with input schemas and defaults.
- `POST /api/tester/run` `{strategy, inputs, range, qty, commission, slippage_ticks, holdout?: {reason}}` →
  `{id}`. Uses the Origin check (`browser_write_ok`) and validates against the schema and the discipline.
- `GET /api/tester/run/{id}` → status and progress. `POST /api/tester/run/{id}/cancel`.
- `GET /api/tester/run/{id}/bundle` → report, trades, equity, plots, coverage.
- `GET /api/tester/runs` → recent runs (newest first), so a run the assistant starts from a script also
  shows up on the page.

## Page (bottom panel, the same panel as chart trading's Positions/Orders tabs)

- **Header row** (TradingView layout):
  - a strategy select;
  - an inputs gear (a dialog built from the schema);
  - a range select with a custom date picker;
  - qty, commission, slippage;
  - the `Holdout` switch (off; turning it on asks for the reason inline);
  - `Run`. It becomes `Update report` once any input changes after a run.
  - A progress bar while running.
- **Overview tab:**
  - tiles: Net P&L $ (%), Max drawdown $ (%), Win rate (n/N), Profit factor, Sharpe, Avg trade $, RR 1:X,
    t-stat;
  - an equity curve and drawdown (a small Lightweight Charts pane, TradingView's teal line/area);
  - badges: data coverage, holdout, fill law ("tick replay").
- **Performance summary tab:** the full table, All / Long / Short.
- **List of trades tab:** sortable table. Clicking a row scrolls and zooms the main chart to the trade and
  selects it.
- **Properties tab:** inputs, range, costs, sessions used and skipped, and the engine version.
- **On the chart** of the strategy's root, while a run is loaded:
  - entry ▲/▼ and exit ● markers, with the net $ on exit;
  - the selected trade's entry, SL and TP as short price lines, and a dashed connector from entry to exit;
  - the strategy's plots/hlines;
  - a `Hide trades` toggle in the panel.

## Desk sharing (staged, because the desk is live)

- **v1:** the tester runs `homebase/strategies/*`. The desk keeps its own execution code **unchanged**.
  Parity tests pin that the strategy defaults equal the desk's `config.json` geometry, and that
  `nq930.legs(anchor)` equals `engine._legs` on sample anchors.
- **Later (a separate, user-approved build):** the desk's `_legs` / `rules.RULES` delegate to the same
  classes, so there is literally one definition. This touches the live desk and needs its own review, a
  restart window and the user's OK.

## Validation

- **Golden parity:** the tester's `nq930` over a fixed list of ~20 research-window sessions reproduces
  `research/nq_930_straddle_ticks.py` **trade by trade** (entry side, fill price, exit reason and price,
  net $) at the same slippage and commission. The fixture is generated once from the research script, a
  read-only use of the archive, and committed small.
- **Unit tests:** every fill-law case (gap-through stop entry, TP touch without penetration = no fill, SL
  slip, same-`ts_ns` ties in row order, OCO cancel, bracket re-price, scheduled cancel/flat, a session
  with a missing hour skipped).
- **Metrics:** vendored stats tests plus a hand-computed ledger.
- **Discipline:** a 2025 range without the switch is refused; with it, a spend line is written.
- **Performance target:** a full 2021–2024 `nq930` run with a warm cache in **≤ 30 s**. The first run builds
  the cache and shows its own progress.

## Out of scope (v1)

- Pine execution.
- Parameter grids / optimisation.
- Monte Carlo and prop-eval pass rates (Onyx `propsim` is a candidate follow-up).
- Portfolios of strategies.
- A live-versus-backtest overlay of the desk's real fills (follow-up).
- Level 2 based strategies.
- The ADX trend gate reads daily H/L/C from the tape cache (our own archive), not
  the broker's own daily bars the way the desk's running gate does; the two can
  disagree on a day the two sources price differently (known limit, final fix
  wave 2026-09-26).

## Prop-eval pass rate (added 2026-09-26, user picked it: "lets add … 5")

- **Engine**: vendor `~/ONYX TRADING/onyx/report/propsim.py` (pure stdlib, seeded, deterministic) and its rules
  directory into `homebase/backtest/propsim/` with a provenance header — Monte Carlo i.i.d. day bootstrap over
  the weekday grid of the run's **daily net P&L** (0-trade weekdays included), Wilson CIs, eval pass / bust /
  timeout, days-to-pass percentiles, funded payout + expected cheque. The "days drawn independently"
  caveat is shown on every result (it is the friendly end of the band).
- **Evals** (updated 2026-09-27): two, and other accounts map onto them — `lucid-flex-50k@2026-09-27.json`
  (the DEFAULT; 50% consistency ON TOP OF a 2-trading-day minimum, reaffirmed by the account holder 2026-09-27,
  numbers unchanged from the 2026-08 snapshot, which stays on disk so older runs reproduce) and
  `lucid-pro-50k@2026-09-27.json` (Flex with `consistency: null` and `eval_min_days: 1` — passable in a single
  day; every other number inherited from Flex, `"confirmed": false`, so the page labels it `unconfirmed rules`).
  The Apex placeholder was deleted: invented numbers are worse than no file. Rule files are JSON, one family per
  eval; the picker offers the newest version per family, older snapshots stay loadable. Selectable per run from
  an **Eval** picker shown beside the prop-eval tiles (and in the inputs dialog).
- **Report**: a `Prop eval` block in the Overview tab — tiles `Eval pass %` (with 95% CI), `Bust %`, `Median days
  to pass`, `Funded: expected cheque $` — plus the rule set name; computed in the runner after the backtest
  (≤ 3 s at the notebook's default path count), stored in the bundle (`propsim.json`).
- **Tests**: the vendored module's determinism (same seed → same numbers); a hand-built ledger that must
  always pass / always bust; rule-file loading and the unconfirmed label.
