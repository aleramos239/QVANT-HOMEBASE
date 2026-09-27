# Strategy Tester: walk-forward, compare two runs, Monte Carlo. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three Strategy Tester additions the user picked on 2026-09-27: #6 built-in walk-forward, #8 compare two runs, and #5 Monte Carlo.

**Architecture:**
- All three reuse `homebase/backtest/*` (runner, report, stats, propsim) and the tester API/UI on `feat/charts-tester`.
- Monte Carlo and compare are pure computations over finished bundles.
- Walk-forward runs cells through the heat-map's grid machinery, with its global 2-process cap and its 09:20–09:35 ET no-start window.

**Tech Stack:** Python 3 / FastAPI / pytest; plain JS; Node 26.

**Spec:** the user's picks, as offered in chat on 2026-09-27:
- **#5 Monte Carlo on any result:** it reshuffles the backtest's trades thousands of times and shows the range of drawdowns you could have had, the risk of ruin, and the odds of passing a prop eval. The backtest shows one path, and this shows how lucky that path was.
- **#6 built-in walk-forward:** the user's preferred rolling scheme, 1 month to pick the settings and 3 months to test them, becomes one button in the tester, with the stitched results.
- **#8 compare two runs:** put two runs side by side with their equity curves overlaid and a table of the differences.

## Global Constraints

- The research window is 2021-01-01..2024-12-31 only, forced server-side for walk-forward. Monte Carlo and compare only read bundles that already exist.
- **Walk-forward counts looks honestly.** Every cell evaluated in each selection month adds to the heat-map's looks counter (`.state/tester/looks.json`).
- The house fill law is unchanged. Monte Carlo resamples trade P&L only; it never re-simulates fills.
- The live desk shares the machine. Keep the global cap of 2 backtest processes and no starts from 09:20 to 09:35 ET on weekdays. Monte Carlo runs off the event loop (a thread), bounded to ≤ 10,000 paths and ≤ 2 s.
- Lucide icons only. Look like TradingView. No native dialogs. Keep `?v=4`. Dollar metrics plus Sharpe in every table, and RR written as "1:X".

---

### Task 1: Monte Carlo (pure + UI)

- **Code:** `homebase/backtest/stats/montecarlo.py`, a pure function taking the trade P&L list, `paths` (default 5,000), `seed`, the starting balance, the prop rules (optional; reuse `propsim`) and the ruin threshold. It returns:
  - percentiles (5/25/50/75/95) of max drawdown $, final net $ and longest losing streak;
  - P(ruin);
  - P(prop pass), if rules are given;
  - a histogram of the max-DD.
- **Resampling:** both a bootstrap with replacement and a shuffle without replacement, selectable. The default is shuffle, which keeps the same trades in a different order.
- **Route:** `POST /api/tester/montecarlo {run_id, paths, mode, seed}`, over an existing run bundle.
- **UI:** a "Monte Carlo" section in the Overview sub-tab showing percentile tiles and a small DD histogram, headed "the backtest's actual path: DD −$X (percentile P)".
- **Tests:** a deterministic seed; known small cases (for example all-positive trades mean DD 0); the shuffle keeps the sum; bootstrap percentiles are in a sane range; and a 10,000-path run finishes in under 2 s on 1,000 trades.

### Task 2: Compare two runs (UI + small API)

- **Picking runs:** in Recent runs, a checkbox on each row. With 2 checked, a "Compare" button opens a Compare sub-tab.
- **Contents:** equity curves overlaid (run A blue, run B orange, on the same time axis), with the drawdowns underneath. A diff table covers net, PF, WR, Sharpe, maxDD, avg trade, trades, green years and the prop pass, showing A, B and Δ, with the better value highlighted.
- A **params diff** row lists the inputs that differ.
- If a run is a holdout run, it carries a "holdout" badge.
- **Tests:** pure diff and table helpers in `tester.js` (Node).

### Task 3: Walk-forward (backend + UI)

- **Scheme (the user's):** a rolling window with 1 month to SELECT and the next 3 months to TEST, stepping monthly. In each selection month, every cell of a user-given grid (≤ 60 cells) is run and the best is picked by a chosen metric (default: net $, needing ≥ 5 trades). That cell's params then run on the following 3 months, out-of-sample within 2021-2024.
- **Output:**
  - the stitched OOS equity;
  - a table per step (select month, chosen params, the selected cell's in-sample result, the OOS result);
  - the stitched stats (net, PF, WR, Sharpe, maxDD);
  - a stability count: how often the chosen params change.
- **Looks:** each step's grid adds its cell count to the looks counter.
- **Runtime:** it reuses the grid runner and the slot cap, with progress through the existing job/poll path.
- **Tests:**
  - the window stepping (month boundaries, the last partial window dropped);
  - the selection tie-break (deterministic);
  - stitching (no overlapping test months);
  - a small end-to-end run on a 2-cell grid over 5 months, with fixture tapes or a mocked runner;
  - the research window enforced.
