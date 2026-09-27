# Bar Replay on the chart page (Part B). Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The page half of per-chart Bar Replay:
- a TradingView-style Replay button;
- start-point picking;
- a floating control bar;
- the chart dimmed past the cursor;
- practice trading against replay prices, which never reaches the desk.

**Architecture:**
- A new browser module `replayui.js` (`HBReplayUI`) and a pure `replay.js` (`HBReplay`, Node-tested).
- They use the live chart service's existing `/ws` replay protocol (`replay_start` / `replay_ctl` / `replay_stop` → `history` cut at the cursor, `"replay": true` bar updates, `replay_state`). That backend is merged and live (`homebase/charts/barreplay.py`).
- Practice trading is a pure simulator in `replay.js`, using the tester's tick fill law. Its results are kept in localStorage labelled "practice".

**Tech Stack:** plain-JS IIFEs; Lightweight Charts 5.2.1; Node 26 (`node --test tests/js/*.test.mjs`).

**Spec:** `docs/superpowers/specs/2026-09-27-charts-bar-replay-design.md` §Part B (approved), plus the protocol in §Part A.

## Global Constraints

- **A chart in replay can never send a real order.** While a cell is in replay:
  - its Buy/Sell block, chart-menu trading items, the order panel and draggable order lines are replaced by the PRACTICE equivalents or hidden;
  - no `/api/desk/*` call and no `HBDeskClient.send` may originate from that cell;
  - the cell's real `trade.on` is forced off for the duration and restored to OFF (never on) on exit.
- Replay never touches the research holdout and shows no backtest metrics. Practice results are labelled "practice" and never mixed with tester results.
- The limits are the server's: 2 replays per connection and 4 per server. Show the server's refusal text as-is.
- Lucide icons only. Look like TradingView. No native dialogs. The asset cache-bust stays `?v=4`. localStorage only through try/catch.
- Never start or stop servers. The controller does browser checks against the replay dev server.

---

### Task 1: Replay controls (UI)

**Files:**
- Create: `homebase/static/charts/replay.js` (pure), `homebase/static/charts/replayui.js`.
- Modify:
  - `charts.html`: a toolbar button `#tbReplay` (Lucide `history`, label "Replay") after `#tbIndicators`; script tags with `?v=4`;
  - `app.js` / `cell.js`: the ws op plumbing per cell id, reusing how cells already subscribe;
  - `icons.js` (Lucide `history`, `play`, `pause`, `skip-forward`, `skip-back`, `x`), `charts.css`.
- Test: `tests/js/replay.test.mjs`.

**Behaviour:**
- **Starting:** clicking Replay arms "pick a start": the cursor becomes a vertical line that follows the mouse on the selected chart. A click there picks the start (that bar's ET date and time). A small date field in the bar also lets you type a date (2021-09-22 to yesterday) and a time.
- **Start → `replay_start`** with the cell's stream id, the date, `start_et` and speed `"bar"`.
- **Floating control bar** at the bottom-centre of the cell. It holds:
  - ⏮ "Jump to…" (time field → `replay_ctl jump`);
  - ▶/⏸ (`play` / `pause`);
  - ⏭ step (`step`, one bar);
  - a speed menu (1×, 2×, 5×, 10×, 30×, 60×, Bar);
  - the replay date and time (from `replay_state.cursor_ms`, ET);
  - × exit (`replay_stop`).
- **Dimming:** everything to the right of the cursor is dimmed (a translucent overlay from the cursor's x to the right edge, repositioned on scroll and zoom). The legend shows a "REPLAY" pill.
- **Keyboard:** Space plays/pauses and → steps, only while the cell is selected and no input is focused.
- **Ending:** a stream ends when the server says so (`done`), on exit, or on a symbol/interval change. On a symbol/interval change, ask once through the page dialog: "Leave replay?".
- **Pure `replay.js`:** `parseState(msg)`, `fmtCursor(ms)` (ET), `validStart(date, time, today)`, `speedLabel(s)`, and the ws op builders `startOp`, `ctlOp`, `stopOp`.
- **Safety:** this task hides the real trading UI on a replay cell (see Global Constraints). Practice trading comes in Task 2.

- [ ] Tests first for the pure helpers. Implement. Commit.

### Task 2: Practice trading in replay

**Files:**
- Modify: `replay.js` (the simulator), `replayui.js` (the practice block, lines, P&L strip), `charts.css`.
- Test: `tests/js/replay.test.mjs`.

**Behaviour:**
- **Practice controls:** a replay cell shows a PRACTICE Buy/Sell block with a qty field. It uses the same look as the real block but has an amber "PRACTICE" tag. Market, Limit and Stop orders are available from the block and the chart menu. SL/TP ticks come from the global prefs.
- **Fills use the tester's tick fill law, fed by the replay ticks/bars as they arrive:**
  - a Market order fills at the next trade;
  - a stop entry fills on touch and pays the gap;
  - a limit/target needs a 1-tick penetration;
  - a stop-loss fills on touch;
  - $4 per round trip;
  - tick-grid comparisons use an epsilon, as in the backend (`homebase/backtest/engine.py`).

  Mirror those rules exactly, and cite the backend lines in comments.
- **P&L strip:** it shows the open P&L, the realised P&L and the trade count for the session. On exit, the session is saved in localStorage key `hb.practice` as `{date, root, trades[], net}` (the last 200 sessions).
- **Lines:** the practice position, orders and SL/TP lines can be dragged; the practice order lines have ×.
- **Isolation:** there is no desk call anywhere in the practice path. A test asserts that the simulator module has no reference to the desk client.

- [ ] Tests first for the fill law (each rule, gap-through stop, 1-tick penetration, epsilon) and the P&L. Implement. Commit.
