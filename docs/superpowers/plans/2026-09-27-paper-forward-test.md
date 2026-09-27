# Forward paper-testing on a chart (GC NFP + CPI straddle). Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The OOS-passed GC NFP + CPI 08:30 straddle runs forward on live data as PAPER inside the chart service. It never sends an order. It can be assigned to a GC chart like the 9:30 bot, and its paper results are tracked against the backtest.

**Architecture:** A `PaperRunner` in the chart service (`homebase/charts/paper.py`) sees the live GC ticks the service already receives and reads the event days from the live ForexFactory calendar the service already polls. After 08:30 on an event day it re-runs the **backtester's own** `run_session(GCNfpCpi(), tape_so_far, Costs())` on the ticks so far, at most once a second, in a thread. It publishes the state over `/ws` and stores the finished runs.
- Fills therefore follow the house tick law exactly, with parity by construction.
- The desk, the 9:30 bot and all brokers are untouched, so no desk restart is needed.

**Tech Stack:** Python 3 / FastAPI / pytest; the existing `homebase/backtest/engine.py` and `homebase/strategies/gc_nfpcpi.py`; plain-JS page modules; Node tests.

**Spec:** the design the user approved in chat on 2026-09-27 ("lets add 2", then "Simulated from live ticks"), copied here:

> **The strategy:** GC NFP + CPI straddle, the one that passed out-of-sample. It uses the saved spec: offset 2, SL 3, TP 6, 1 contract, firing at 8:30 ET on NFP and CPI days only. The ForexFactory calendar we already pull decides which days those are.
>
> **Where it runs:** simulated from live ticks. It never sends an order. At 8:30 it records the two stop entries it would have placed. Live GC ticks are then played against them using the same fill rules as the backtester, and the paper entry, exit and P&L are logged.
>
> **On the chart:** you assign "GC NFP/CPI (paper)" to a GC chart, like the 9:30 bot. You see its paper orders, fills and past paper runs, marked PAPER.
>
> **Tracking:** its paper results sit next to the backtest's: win rate, average per trade and number of trades so far.

## Global Constraints

- **No order, broker call or desk call anywhere in the paper path.** A test asserts that `paper.py` does not import the broker, desk, trading or DeskLink modules.
- **No extra market-data requests.** Use only ticks the chart service already streams for GC. Never call getChart for paper, because the Tradovate md budget is 180/h per login.
- **The chart service stays responsive.** `run_session` runs via `asyncio.to_thread`, at most 1/s, only between 08:29:50 and the strategy's flat time plus 1 minute on an event day. The tick buffer is bounded to that window.
- **Research discipline.** The "backtest" comparison figures come from the research window 2021-01-01..2024-12-31 only, computed once with the tester runner and cached. No automatic 2025+ run. The paper results themselves are new forward data, labelled "paper (forward)".
- **Event day rule:** the ForexFactory feed shows a USD, High-impact event at 08:30 ET whose title matches NFP (`Non-Farm Employment Change`) or CPI (`CPI m/m`, `CPI y/y`, `Core CPI m/m`). The strategy's static CSV calendar is used only for dates it contains. Log which rule matched.
- **Replay mode:** the runner is off unless the replay-only flag `--paper-day` forces a replayed date to count as an event day. This is for browser checks only.
- Never restart services from tests. Tests never open network connections and never write to `~/futures_ticks`.

---

### Task 1: PaperRunner in the chart service

**Files:**
- Create: `homebase/charts/paper.py`.
- Modify:
  - `homebase/charts/server.py`: wire the runner to the live tick path and the calendar, the `/ws` `{"type":"paper", ...}` messages, and the routes;
  - `homebase/charts/__main__.py`: `--paper-day`, replay only.
- Test: `tests/test_charts_paper.py`.

**Interfaces:**
- `GET /api/paper/strategies` returns `[{id:"gc_nfpcpi", name:"GC NFP/CPI (paper)", root:"GC", params:{offset_pts, sl_pts, tp_pts, qty}}]`.
- `GET /api/paper/history?strategy=gc_nfpcpi` returns

  ```
  {runs:[{date, event:"NFP"|"CPI"|"NFP+CPI", status:"traded"|"no_fill"|"no_data"|"error", legs:[{side, price}],
  entry?:{side, price, ts}, exit?:{price, ts, kind:"tp"|"sl"|"flat"}, pnl_usd?}], stats:{paper:{n, wr, avg, net},
  backtest:{window:"2021-2024", n, wr, avg, net}}}
  ```

- Live `/ws` push `{"type":"paper", strategy, date, state:"waiting"|"armed"|"in_trade"|"done", legs, entry, exit, pnl_usd}`, sent on every change and to new connections.
- Storage: `.state/charts/paper/runs.jsonl` (append-only; one line per finished run, rewritten if the day's run is re-finalised) and `backtest.json` (the cached comparison).

**Steps:**
- [ ] Tests first:
  - **Parity:** feed a real archived event day's GC ticks (from the archive via the existing TickStore test helpers, or a stored fixture) through PaperRunner. Its final result must equal `run_session` on the same tape exactly: legs, entry, exit and pnl.
  - **Event-day detection:** NFP, CPI and a non-event day, from calendar fixtures.
  - **No trading imports.**
  - **Throttle:** at most 1 run per second.
  - **Window:** no work outside the window.
  - **Persistence:** runs.jsonl round-trips across a restart mid-window, and the in-progress state is rebuilt from the buffered ticks.
  - **Replay flag:** `--paper-day` works only with `--replay`.
- [ ] Implement, then run the full pytest and node suites, and commit.

### Task 2: Paper algo on the chart

This task runs in `feat/charts-screens`, after the algo-per-chart Task 3.

**Files:**
- Modify:
  - `settings-dialog.js`: the Algo select also lists `/api/paper/strategies` for the chart's root, as "GC NFP/CPI (paper)";
  - `trade.js`: pure helpers for the paper state → lines/markers/badge;
  - the bot overlay in `tradelines.js`: reuse it, with PAPER styling;
  - `deskclient.js` or a small `paperclient.js`: `/ws` `paper` messages and the history fetch;
  - `charts.css`.
- Test: `tests/js/trade.test.mjs`.

**Behaviour:**
- **Badge:** a paper icon, the name, and a state pill (waiting, armed, in trade, done). It shows the event, e.g. "CPI", and today's paper P&L. It has **no Kill**, because nothing is live.
- **Stats line under the badge:** "Paper 3 · WR 67% · avg +$203 | Backtest 21–24: 76 · WR 68% · avg +$296".
- **Lines:** dashed read-only lines labelled "PAPER BUY STP …". The entry, exit and past runs are markers, like the bot's, with a PAPER tag in the tooltip.
- **Algo key:** an algo value `paper:gc_nfpcpi` is stored in layouts like a desk algo, and cleared only on a confirmed root mismatch.

**Steps:**
- [ ] Tests first for the helpers, then implement, browser-check with `--paper-day` in replay, and commit.
