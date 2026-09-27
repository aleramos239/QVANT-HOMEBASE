# Fills, timeframe hotkeys, burst radar, parameter heat-map. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five items the user picked on 2026-09-27:
1. timeframe hotkeys;
2. a cross-market burst radar;
3. a live fill-quality tracker for the 9:30 bot;
4. a parameter heat-map in the Strategy Tester;
5. a Stop-Limit-entry study for the 9:30 straddle on the research window.

**Architecture:** Each task is independent and has its own branch/worktree (routing below).
- The page tasks follow the plain-IIFE pattern, with pure logic Node-tested.
- The tester/engine work reuses `homebase/backtest/*` and keeps the tick house law.
- The desk change is limited to the read-only `homebase/bothistory.py`.

**Tech Stack:** Python 3 / FastAPI / pytest; plain JS + Lightweight Charts 5.2.1; Node 26.

**Spec:** the user's chat of 2026-09-27, copied here.
- "lets make hot keys for timeframe, 5, 4, i like 1 but what would it be for, would there be a wat ro be able to improve fills".
- Then "Both" to: the fill tracker (#1), plus a Strategy Tester study of Stop-Limit entries for the 9:30 bot on 2021-2024 ticks (how many ticks of limit protection cost how many missed trades).
- #5 is the burst radar: a strip showing which of the 11 instruments are moving abnormally right now ("CL 4.2× normal"); click one to open it on the selected chart.
- #4 is the parameter heat-map: test a grid of settings (e.g. offset × SL × TP) on the research window only, colour each cell by net and Sharpe, and count how many looks have been taken.
- Timeframe hotkeys work TradingView-style. Typing a number with the chart selected opens a small interval box ("5" → 5m, "30s", "1h", "4h", "d"). Enter applies it to the selected chart and Esc cancels. Nothing fires while an input is focused.

## Global Constraints

- **Research discipline:** tester, heat-map and study runs use the research window 2021-01-01..2024-12-31 only. 2025+ is never used automatically. Every heat-map grid counts toward a visible "looks" counter, stored per strategy.
- **Tester numbers keep the house law:**
  - a stop fills on touch and pays the gap, plus the configured slippage;
  - a limit/TP needs a 1-tick penetration;
  - $4 per round trip per contract;
  - `tick_cmp` epsilon comparisons;
  - the weekday-grid Sharpe.
- Never place orders; tests never open broker connections and never write to `~/futures_ticks`. Never restart services from a task; the controller deploys.
- The desk change is read-only analysis (`bothistory.py`). It must not touch placement, the timer, the engine fire path or the order bodies. It ships with the next approved desk restart.
- Lucide icons only. Look like TradingView. No native dialogs. Keep `?v=4`.

## Routing

| Task | Branch / worktree | After |
|---|---|---|
| 1 Timeframe hotkeys | `feat/charts-screens` / `.worktrees/screens` | algo-per-chart Task 3 |
| 2 Burst radar | `feat/charts-screens` | Task 1 |
| 3 Fill tracker | desk part on `feat/desk-fills` (from main), page part on screens | — |
| 4 Parameter heat-map | `feat/charts-tester` / `.worktrees/tester` | screens Task 10 |
| 5 Stop-Limit study | `research/stoplimit-entry` / `.worktrees/study` (from main) | — (now) |

---

### Task 1: Timeframe hotkeys (UI)

**Files:** `homebase/static/charts/app.js` (the key handler), a pure `parseInterval(text)` in `catalog.js` (Node-tested), `charts.css`.

**Behaviour:**
- A digit keypress on the page opens a small box near the selected chart's top-left and seeds it with that digit, unless an input, select, textarea or contenteditable has focus, or a dialog or menu is open.
- **Accepted input:**
  - `N` = N minutes;
  - `Ns` = seconds;
  - `Nm` = minutes;
  - `Nh` = hours;
  - `d`/`D`/`1d` = daily;
  - `w` = weekly, only if the catalog has it.
- **Keys:** Enter applies the interval to the SELECTED chart only, through the same path the toolbar interval buttons use. Esc or blur cancels.
- **Invalid or unsupported input** shows "Not available" in the box and applies nothing.
- **Interaction with Bar Replay's Space/→ keys (replay branch):** digits never collide with them.

`parseInterval` is tested for every form plus the invalid ones.

### Task 2: Burst radar (UI + a small chart-service read)

**Files:** `homebase/charts/bursts.py` / `server.py` (expose the current per-root activity ratio), `homebase/static/charts/radar.js`, `charts.html`, `charts.css`.

**Behaviour:**
- **Data:** a thin strip under the toolbar lists every root with its live activity ratio versus its normal level for this time of day. The ratio is what the burst detector already computes: ticks in the last 30 s ÷ the 60-min median. It comes from `/api/bursts/now` or a `/ws` push every 2 s, from data the service already has, with no new md requests.
- **Colours:** grey < 2×, amber 2–4×, red ≥ 4×, sorted by ratio.
- **Click:** a chip loads that root on the selected chart.
- **Collapse:** the strip can be collapsed, and that is remembered in localStorage with try/catch.

### Task 3: Fill-quality tracker (desk read + page)

- **Desk (`bothistory.py` only).** Each run gains:
  - `fire_ms`: the timer's fire time, 09:30:00.000 ET;
  - `placed_ms`: the journal ts of `placed`;
  - `latency_ms` = placed_ms − fire_ms;
  - per filled leg, `slip_ticks`: the entry fill vs its stop trigger, and an SL exit vs its stop price, signed so that positive means worse for us;
  - `gap_through`: true when the SL fill is ≥ 2 ticks beyond its stop.

  Tests use journal fixtures, including missing fields.
- **Page:** a "Fills" tab in the bottom panel lists, per live run: date, account, latency, entry slip, exit slip, and gap-through. A summary row shows the running average entry and exit slip in ticks and in $, and the median latency. It compares them with the backtest assumption: the engine's `Costs.slippage_ticks` per side (default 1.0).

### Task 4: Parameter heat-map (tester)

**Files:**
- `homebase/charts/tester_api.py` and `homebase/backtest/runner.py`: a grid run endpoint. Its inputs are one strategy, 2 or 3 parameters with value lists (max 60 cells), and the research window only. It runs the cells in a worker thread pool bounded to 2, and records the look count.
- `testerui.js` / `tester.js`: a "Heat-map" sub-tab. It shows a grid coloured by net $ with Sharpe in each cell. Clicking a cell loads that cell's full report.
- **Looks counter:** "looks this strategy: 184 — expect ~9 lucky cells at 5%". The counter lives in `.state/tester/looks.json`.

**Tests:** grid expansion; the 60-cell cap; that the window is forced to 2021-2024; persistence of the looks count; and that a cell's numbers equal a single run with the same params.

### Task 5: Stop-Limit entry study (research, engine + report)

**Files:**
- `homebase/backtest/engine.py`: a new order kind `stoplimit`. Its rules:
  - it triggers on the first print at or through the trigger;
  - if that print is inside the limit, it fills at min(print + slip, limit) for a buy (mirrored for a sell);
  - if the triggering print gapped past the limit, it rests as a limit at the limit price, and needs a 1-tick penetration to fill;
  - it is cancelled with the other entries at cancel_et.
- `homebase/strategies/straddle.py`: an input `entry_limit_ticks` (0 = stop-market, the default and unchanged behaviour).
- Tests: every rule, plus that the default is byte-identical to today's results. The golden parity must stay 21/21.

**The study itself:**
- nq930 at the DESK's live config (read via `desk_cfg`), 2021-2024.
- Seven cells: stop-market, and `entry_limit_ticks` ∈ {1, 2, 3, 4, 6, 8}.
- For each cell: filled trades, missed trades (triggered but never filled), WR, net $, avg $/trade, PF, Sharpe, maxDD, and green years.
- Also slippage sensitivity at 0, 1 and 2 ticks for the stop-market baseline.
- **Deliverables:**
  - the report goes to `docs/research/2026-09-27-nq930-stoplimit-entry-study.md` in the worktree;
  - one vault finding note following the vault conventions;
  - 7 cells prereg'd and written into the report BEFORE running.
- No 2025+ data.
