# Live Charts — design (Build 1 of the homebase terminal)

Date: 2026-09-25 · Status: approved in chat, awaiting spec review

## Goal

Turn homebase into our own trading terminal, MultiCharts/TradingView style,
fed by live ticks from the broker login (Apex eval). Build 1 = charts only:
multi-chart layouts, any timeframe, indicators, order flow. Nothing in Build 1
can send an order.

Roadmap (each its own spec):
1. **Live charts** (this doc)
2. **Trading from the chart** — click-trading, our orders/fills/brackets drawn
   on the chart, DOM ladder. Chart asks the trading engine; only the engine
   ever talks to the broker.
3. **Tick backtester** — replays archive ticks through the SAME bar builder,
   studies and strategy rules the live side uses (backtest = live by
   construction; bars are never trusted for stop-entry brackets).
4. **Automation** — strategies built in the terminal: backtest → shadow → live.

## Shape: one app, two programs

The user sees ONE app: the homebase dashboard gains a **Charts** tab. Under
the hood the charts run in a **separate process** (`homebase.charts`, own
launchd job `com.ramosquant.homebase-charts`, port **8852**), and the tab
embeds it.

Why: the NQ open prints thousands of trades per second at exactly the moment
the trading engine must fire at 09:30:00.000. Chart work (bars, footprint,
indicators, pushing to browsers) must never delay an order, and a chart crash
must never take the trading engine down. The trading process (:8850) is not
modified in Build 1 except for the nav tab.

Same repo, same look (`shadcn.css`), same shared modules (`broker/`,
`marketdata.py`, `symbols.py`, `contracts.py`, `secrets_store.py`).

## Pipeline

```
Tradovate md socket — ONE Tick subscription per root, shared by every chart
  → recorder.py   append each tick to today's session file (crash-safe)
  → store.py      one read API over: today's file + ~/futures_ticks archive
  → bars.py       pure: ticks → bars (+ footprint cells) for any bar type
  → studies.py    pure, incremental: indicators on bars/ticks
  → hub.py        one live stream per (root, bar type); fan out to all charts
  → server.py     FastAPI :8852 — page, history API, /ws
  → static/charts.html   grid of Lightweight Charts + canvas footprint layer
```

New package `homebase/charts/`, one job per file:

| file | job | depends on |
|---|---|---|
| `tick.py` | `Tick` dataclass (ts_ms, price, size, bid, ask, side) + side classifier | — |
| `recorder.py` | md Tick subscription → today's session file; gap refill on restart | `marketdata`, `tick` |
| `store.py` | `ticks(root, session)` / `sessions(root)` over archive + today; session cache | `tick`, `paths` |
| `bars.py` | `BarBuilder(spec)`: feed ticks → closed + developing bars, footprint | `tick` |
| `studies.py` | incremental indicators; registry by name | `bars` |
| `hub.py` | live subscriptions, fan-out, coalescing to the browser | all above |
| `server.py` | HTTP + websocket, layouts API | `hub`, `store` |

`bars.py` and `studies.py` are pure (no I/O, no clock) so Build 3's
backtester imports them unchanged.

## Data

**Live.** One md socket, one `md/getChart` `Tick` subscription per watched
root = one chart request per root, however many charts are open. Rate budget
(180 chart requests/hour/login, bursts penalize the whole hour) is respected:
subscriptions are made once and reused; reconnects back off; a penalty reply
is honored with its p-ticket (same handling as `ticks.py`/`feed.py`).

**Which login.** The Apex eval login, on its own md socket — **pending the
spike below**. Fallback: the live login's md.

**Recording.** The recorder writes every tick of the session (from the 18:00
ET open) to `~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.live.csv.gz`
(same columns as the archive: `ts_ms,price,size,bid,ask,bid_size,ask_size,id`),
flushed every second. So a chart always has today's full session without
paging the broker. The nightly `homebase.ticks` job is unchanged in Build 1
(it stays the source of truth; replacing it with the recorder is a later,
separate decision).

**Restart gap.** On (re)connect mid-session, the gap since the last recorded
tick is refilled by paging tick history backwards from now, paced like
`ticks.py` (21 s/page), at most 20 pages, and only while this process has
spent < 60 chart requests this hour (the other 120 stay free for the trading
process). No refill 09:20–09:35 ET — it waits. Whatever the 20 pages don't
reach is recorded as a **gap** (`<date>_<contract>.live.gaps`, a JSON list; not
`.json`, which research loaders glob as archive manifests) and shaded on
the chart; the nightly archive fills it for later sessions.

**History.** Past sessions come from the local files only (zero broker
cost). Per session ONE source is used, never a merge (Massive and Tradovate
tick ids are different spaces): a complete archive file beats the live file,
which beats an incomplete archive file; on a roll day the contract with the
most ticks wins. The first read of a session builds its 1-minute bars
(with footprint) into a pickle cache under `homebase/.state/charts/cache/`;
every time bar ≥ 1 m is resampled from that cache, so a 60-session daily
chart never re-reads ticks. No new dependencies.

**Trade side (buy/sell aggressor).** With a sane quote (bid ≤ ask): price ≥
ask → buy, price ≤ bid → sell. Inside the spread, no quote, or a crossed quote
(the feed does send bid > ask — seen in the 2026-09-24 NQ file) → tick rule
(up-tick buy, down-tick sell, same → previous side).
Massive-backfilled sessions have no bid/ask → tick rule only, and the chart
labels footprint/delta on those sessions as **approximate**.

**Sessions.** CME session: 18:00 ET (D-1) → 17:00 ET (D), same convention as
`ticks.py`. Front month via `symbols.resolve_contract()`; history across a
roll stitches contracts by session with no back-adjustment in Build 1.

## Charts (v1 features)

- **Layouts**: grid of 1–6 charts (1, 2, 2×2, 3×2), each with its own symbol
  and bar type; layouts saved by name (`.state/charts/layouts.json`).
- **Bar types**: time (5s, 15s, 30s, 1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h, 4h,
  1D), tick (N trades), volume (N contracts), range (N ticks).
- **Symbols**: any root the archive/recorder covers (NQ ES YM RTY GC SI CL …);
  Build 1 records the same 10 roots as the nightly archive live (NQ ES YM RTY
  GC SI CL ZN NG HG) by default; `--roots` narrows it.
- **Indicators (studies)**: session VWAP (+ optional bands), EMA, SMA, VWMA,
  ADX/DI, session levels (prior day H/L/C, overnight H/L, RTH open), volume.
  Parameters editable per chart.
- **Order flow**: footprint (bid × ask volume per price, per bar; imbalance
  highlight at a configurable ratio, default 3:1), bar delta and cumulative
  delta (session-reset) panes, big-print markers (single trade ≥ N contracts),
  session volume profile (POC, value area 70%).
- **Live behavior**: the developing bar and its indicators update in place;
  updates to the browser are coalesced to ≤ 4/second per chart so a fast open
  never floods the page. Every closed bar is final and identical to what a
  reload would rebuild from the recorded ticks.
- **Status strip**: feed connected / last tick age / recorder lag / budget
  used this hour — so a stale chart is never mistaken for a quiet market.

Footprint renders only when zoomed in far enough to read it (else normal
candles). The charts page vendors **Lightweight Charts v5** (panes for
volume/delta/ADX; series primitives for footprint and profile); the
dashboard keeps its v4 copy. Tick/volume/range bars are drawn on an evenly
spaced axis (many can share one second) with real times in the labels.
Times display in ET.

**Replay mode.** `python -m homebase.charts --replay 2026-09-24 --speed 20`
plays an archived session through the exact live path (classifier → bars →
studies → websocket) with a replay clock and NO recording — for testing now
and on weekends.

## Failure handling

- md socket drops → auto-reconnect with backoff (never hammer the auth
  endpoint; p-captcha lesson), resubscribe, refill the gap; the chart shows a
  "reconnecting" banner and a gap marker, never silently frozen data.
- Recorder file write fails → feed keeps running, status strip goes red.
- Chart process dies → launchd restarts it; the trading process is
  unaffected (separate process, no shared state).
- Session roll at 17:00/18:00 ET → close files, reset session studies, open
  the next session file.

## Testing

- `bars.py`: every bar type from a fixed tick fixture; **live-vs-rebuild
  equality** — feeding ticks one at a time must yield exactly the bars a bulk
  build yields.
- `studies.py`: incremental value == full recompute on the same bars; VWAP
  and ADX pinned against the research formulas (ADX via existing `gate.py`).
- Side classifier: bid/ask cases, tick-rule fallback, ties.
- `store.py`: archive + live file merge, dedupe by tick id, session bounds,
  cache equals source (diff check — the unstable-sort lesson).
- `recorder.py`/`hub.py`: fake md socket (like `FakeAdapter`) — reconnect,
  gap refill decision (≤20 pages vs MinuteBar fallback), fan-out, coalescing.
- End-to-end: the page loads a 2×2 layout from the archive in the browser
  preview; a replayed session streams into it.

## Spike before the plan (run outside trading hours)

Open a second md socket on the Apex eval login while the trading process's
socket is connected, and confirm both keep streaming for 10 minutes (the
first is not kicked, no auth errors). Result decides the login. Do NOT run
during 09:00–16:00 ET on a trading day.

## Out of scope for Build 1

Order entry of any kind, DOM ladder, drawing tools, alerts, Pine import,
back-adjusted continuous contracts, replacing the nightly tick job,
multi-monitor pop-out windows.
