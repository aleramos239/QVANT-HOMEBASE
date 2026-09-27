# Charts — Bar Replay (backend, Part A)

Date: 2026-09-27. Status: approved. In chat the user picked "Bar Replay: pick any past day since 2021 from our archive and play it forward bar by bar or at speed, with the position tool and even simulated trading" ("lets add 2, 5"). It was queued; it has now started in parallel.

## Today
The chart service has a whole-process replay mode (`python -m homebase.charts --replay DATE`, `homebase/charts/replay.py`). That is a separate server, not a feature of the live one.

## Part A: per-chart replay inside the LIVE chart service (this branch)

A chart can switch into replay mode without affecting other charts or the live feed.

- **Protocol (page → server over `/ws`):**
  - `{"op": "replay_start", "id": <stream id>, "date": "YYYY-MM-DD", "start_et": "HH:MM", "speed": 1|2|5|10|30|60|"bar"}`
  - `{"op": "replay_ctl", "id", "action": "play"|"pause"|"step"|"speed"|"jump", "speed"?: n, "to_et"?: "HH:MM"}`
  - `{"op": "replay_stop", "id"}` returns the chart to live.
- **Server → page:** the normal `history` message, cut at the replay cursor. Then the normal bar-update messages as the cursor advances, flagged `"replay": true`, plus `{"type": "replay_state", "id", "date", "cursor_ms", "speed", "playing", "done"}` once per second and on every change.
- **Data source:** the tick archive for that root and date, from the existing TickStore and History, using the same contract and bars as the charts. The cursor runs from the chosen ET start time. `speed` is a wall-clock multiplier over tick time; `"bar"` + `step` advances exactly one bar of the chart's own interval.
- **Isolation:**
  - Each replay stream belongs to one `/ws` connection and chart id.
  - It uses its own Hub/BarBuilder instance, never the live hub, and never records.
  - It never touches the desk link: no quotes are noted and no fan-out to trading.
- **Limits:**
  - At most 4 replay streams per connection and 8 per server.
  - Each stream's tick buffer holds one session.
  - A stream ends on disconnect or `replay_stop`.
- **Load:** tick loading runs off the event loop (`to_thread`). The first frame answers within the history time budget, using the same newest-first rule as deep history.
- **Allowed dates:** any archived session from 2021-09-22 to yesterday. A date with missing hours plays with gaps, marked the same way as history.
- **Studies:** indicators and studies work as they do live, computed by the replay hub for that stream.

**Discipline note:** Bar Replay is for the user's practice and viewing, so it is not gated by the research holdout. It does not compute performance metrics. Simulated trading in Part B will record results locally, labelled "practice", and never mix them with backtests.

## Tests (pytest, in-process, no network)
- start → history cut at the cursor
- play at speed n advances by n× wall time (injected clock)
- step advances exactly one bar for time, tick and range specs
- pause, jump and speed change
- stop returns to live
- limits
- isolation: the live hub and recorder are untouched; no desk or quote calls
- a missing-hour session
- replay of a 24/7 root (BTC) on a Saturday date
- only the replay routes; the Host allowlist is enforced on `/ws` (already present)

## Part B: page (after the screens build; its own plan)
- A toolbar **Replay** button, TradingView-style.
- Clicking the chart picks the start point; a date picker is also available.
- A floating control bar: ⏮ jump, ▶/⏸, ⏭ step, speed menu, date/time, and an exit ×.
- The chart dims beyond the cursor.
- Practice trading with Buy/Sell against the replay prices. Fills are simulated with the tester's fill law, with a P&L panel, and the results are kept locally.
