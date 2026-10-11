# Order-flow indicators: Level 2 history + tick upgrades (design)

Date: 2026-10-11 · Status: DRAFT for the owner's review · Scope: Homebase Charts page only
(`homebase/static/charts/*`, `homebase/charts/*`). Not Pine, not Lab blocks, not the backtester.

## 1. What the owner asked for

"Add more indicators with the Level 2 data or upgrade the ones we have, also the ones that use tick
data. Do all of them, take your time, do it properly." The owner then picked all eleven items below.

Nothing here feeds a strategy. These are chart-reading aids; no edge is claimed. Any strategy idea
built on one of them goes through the pipeline like every other idea.

## 2. The eleven items

| # | Indicator | Kind | Where it draws |
|---|---|---|---|
| 1 | **Big orders** (upgrade): lines persist on history, start and end where the order did, end state shown (traded / pulled / faded) | book | price pane |
| 2 | **Imbalance** (upgrade): a pane line over time, top 1 / 5 / 10 levels; the legend gauge stays | book | own pane |
| 3 | **Liquidity heatmap** (upgrade): executed trades as bubbles on top | book + ticks | behind candles |
| 4 | **Footprint** (upgrade): stacked imbalances, unfinished auctions, delta number per bar | ticks | price pane |
| 5 | **Volume profile** (upgrade): prior-day profile, with VAH / VAL / POC extended as lines | ticks | right edge + lines |
| 6 | **Big prints** (upgrade): bubble size scaled by size; sweeps flagged | ticks | price pane |
| 7 | **Absorption** (new): heavy volume traded into a level whose resting size held | book + ticks | price pane markers |
| 8 | **Pulled liquidity** (new): big resting orders that vanished before price got there | book | price pane markers |
| 9 | **Depth pane** (new): total bid vs ask size (top 10) in a pane, plus a **Microprice** line on price | book | own pane + price pane |
| 10 | **Delta divergence** (new): price makes a new swing extreme, cumulative delta does not | ticks | price pane markers |
| 11 | **Tape speed** (new): prints per second, with a burst line | ticks | own pane |

## 3. What the code and data allow (measured, not assumed)

- **The page never receives raw prints.** It gets bar-level `fp` (volume per price) and `big` (single
  prints >= `BIG_MIN` = 10 contracts) only. Anything print-level must be computed on the server.
- **Live book:** `{type:'depth', root, ts, bids, offers}`, top 20 levels per side, <= 10 per second
  per root (`homebase/charts/depth.py`). Any root with a chart on it is subscribed.
- **Recorded book:** `~/futures_depth/<ROOT>/<year>/<date>_<contract>.depth.jsonl.gz`, lines
  `{"t","b","a"}`, top 10 levels, <= 4 per second, **NQ and ES only, since 2026-09-25**. The existing
  `HistoryPool` loader keeps the last book per second.
- **Existing book history API** (`/api/depth/history`) merges bid and ask into one size per cell, so it
  cannot answer "which side". It stays as is (it feeds the heatmap).
- **Ticks:** archive `~/futures_ticks/<ROOT>/<year>/<date>_<contract>.csv.gz`
  (`ts_ms, price, size, bid, ask, id`), read by `store.py`. The chart service does **not** read
  `flow_tape` / `flow_1m` parquet and there is no pandas/pyarrow in its venv: this design does not add one.
- **Studies** (`studies.py`, `studies_ta.py`) receive the full server-side `Bar` (`fp`, `buy`, `sell`,
  `big`, `n`, `pv`) even though the wire omits some; they return one value per bar in `sv[key]`.
- **Cell.js** has three render paths: own-pane series (server `sv` or client-computed), price-pane
  layers/markers, and per-chart overlays (`page.overlays`, as `l2layer.js` and `liquidity.js` do).
- **Uncommitted work by other sessions** sits in `catalog.js`, `cell.js`, `app.js`, `server.py`,
  `studies_ta.py`, `charts.html` (fvg / wk / mo / topen / orb / chart types / alerts). Hence rule 7.1.

## 4. Architecture

### 4.1 One book tracker, server-side, single source of truth

New module `homebase/charts/bookflow.py`, pure and deterministic (no clock, no I/O):

```
BookTracker(root, tick_size)
  .on_book(ts_ms, bids[:10], offers[:10])      # sampled to <= 1 Hz by the caller
  .on_print(ts_ms, price, size, side)          # side +1 buyer lifted the ask, -1 seller hit the bid
  -> emits: Sample (1 per second), Episode open/update/close
```

The **same class** runs in two places, fed the same normalised input (top 10 levels, one book per
second), so live and history agree by construction:

- **Live:** hooked in beside `depth` and `on_live` in `server.py`; emits to pages over the existing
  `/ws` as new message types `booksample` and `bookevent`, to connections with a chart on that root
  (same `Fanout` pattern as `depth`).
- **History:** a new `HistoryPool.book(root, from_ms, to_ms)` child process replays the recorded depth
  files plus the tick archive for the window through the tracker and returns samples + episodes.
  Same executor/pool, same `busy` 503, same `paused_reason` gate (09:20-09:35 ET and 08:29:30-08:31:00 ET
  on weekdays) as `/api/depth/history`.

Why not compute in JS: two implementations of a stateful tracker drift. Episodes need a trailing median
and print matching; they are written once.

### 4.2 The tracker's outputs

**Sample** (every second): `t, bid10, ask10` (summed size of the top 10 each side), `imb1, imb5, imb10`
(= (bid - ask) / (bid + ask) over that many levels, signed, -1..1), `micro` (top-of-book size-weighted
mid: (bid_px x ask_sz + ask_px x bid_sz) / (bid_sz + ask_sz)), `spread` (ticks).

**Episode** (one resting order level over its life): a level on one side whose displayed size reached
`ratio` = size / (median size of that side's levels over the trailing 60 s) >= `RATIO_FLOOR` (2.0).
Fields: `id` (deterministic: `<side><price><start_ms>`), `side` (`b`/`a`), `price`, `t0`, `t1`
(null while open), `peak`, `ratio` (peak ratio), `traded` (contracts printed at that price against it
during the episode), `end` (`traded` | `pulled` | `faded` | `open`), `dist0` (ticks from the touch when
it first qualified). The client filters by its own `multiple` (>= RATIO_FLOOR), so one tracker serves
every instance's setting.

End classification (parameters in one `TUNING` dict, first-guess, owner reviews):
- **pulled**: size fell >= 80 % within 2 s while `traded` < 20 % of the size removed **and** the touch
  was within 4 ticks of the level at that moment (liquidity withdrawn as price approached).
- **traded**: the level was consumed by prints (`traded` >= 60 % of the peak) or price traded through it.
- **faded**: anything else (drifted away, slowly reduced, or price left without testing it).

**Absorption** (an episode with a flag, not a separate pass): while the episode was alive,
`traded` >= max(2 x start size, `ABS_MIN_MULT` x trailing median level size) **and** price never printed
beyond the level by more than 1 tick **and** the level was still displayed (>= 50 % of start size) at the
end of the window or was refilled. The flag is set when the condition first holds and the marker is
drawn at that time (no repaint).

### 4.3 Bar-level tick fields (server, `bars.py`)

`Bar` gains four fields (`te`, `span`, `sw`, `bub`); `CACHE_VERSION` in `history.py` is bumped so old `.m1.pkl`
caches rebuild (otherwise they silently carry defaults); `Bar.merge` and `copy` are extended:

- `span`: a time bar's length in ms (0 for tick / range bars), so tape speed has the bar's real length.

- `te`: ms of the bar's last print (gives the bar's real duration; used by tape speed).
- `sw`: sweeps, `[[ts_ms, px_from, px_to, size, side], ...]`. A sweep = two or more prints with the same side and
  the same millisecond stamp spanning >= 2 price levels (one aggressor order walking the book). Measured against
  the research `flow_1m` sweep columns on the days read in the prototype: with millisecond stamps and no order
  ids this rule finds about 0.7x the research sweep volume (the research code groups by order id, which the
  chart archive does not have). The chart's sweeps are therefore a subset: a drawn sweep is a real multi-level
  walk, a missing one may be a sweep the stamps cannot show. Stated in the indicator's description.
- `bub`: aggregated trade bubbles, `[[ts_s, px, size, side], ...]` aggregated per (second, price, side),
  >= 3 contracts, capped at 60 per bar (largest kept, ties by time then price). `sw` and `bub` ride on their
  own `flow` flag of the bar wire (`sub` / `older` carry `"flow"`, default true; a chart asks for it only while a
  bubble or sweep option is on), not on `big`: measured on NQ 2026-10-08 (1,379 one-minute bars) the big prints
  alone are 0.21 MB, the bars with the footprint 1.10 MB and with sweeps and bubbles 2.46 MB. Charts without
  those options pay nothing. Bubbles and sweeps are per bar: a bar boundary inside one second (only possible on
  an out-of-order tape, or at a minute boundary) splits one, and each piece under the minimum is dropped.

### 4.4 Client

New modules, each Node-testable the same way as `dom.js` (IIFE, `need()` dependency pattern, exports):

- `bookstore.js` (`HBBookStore`): per root, the sample ring + episode map; `fetchHistory(root, from, to)`
  against the new endpoint, `onSample` / `onEvent` from the ws, `meanAt(bar0, bar1, key)` for pane series.
  Single place the three book indicators and both marker overlays read from.
- `bookevents.js` (`HBBookEvents`): one overlay for items 1, 7, 8: episode segments (item 1), absorption
  and pulled markers. Replaces the live-only math in `l2layer.js` for the Big-orders line (the legend
  gauge stays there).
- Existing modules get small hunks only: `catalog.js` (entries + params), `cell.js` (a `bookseries` /
  `marker` case), `primitives.js` (footprint extras, profile prior), `liquidity.js` (bubbles), `app.js`
  (route the new ws messages, push the overlay), `charts.html` (script tags; `?v=` bump last).

### 4.5 Per item

1. **Big orders:** drawn from episodes (history + live). A line runs from `t0` to `t1` (to the right edge
   while open). Colour by side; the end state is a small cap at `t1`: traded = solid, pulled = hollow,
   faded = none. Params: `multiple` (existing), `minSeconds` (hide episodes shorter than this, default 5).
   Reload no longer loses them. Roots without recorded depth show live-session episodes only.
2. **Imbalance over time:** a NEW indicator "Book imbalance (over time)" in its own pane (histogram, green
   bid-heavy / red ask-heavy), param `levels` (1 / 5 / 10, default 10), value = mean of the 1 s samples inside
   the bar. The existing `imbalance` indicator (legend gauge) is left exactly as it is: no migration, nothing
   saved changes.
3. **Heatmap bubbles:** param `bubbles` (off by default) and `bubbleMin` (contracts, default 10). Circles
   sized by size, green buy / red sell, drawn in the heatmap layer from `bub`.
4. **Footprint extras** (client only, from `b.fp`, drawn only while the footprint is readable):
   - *Stacked imbalance*: >= `stack` (default 3) diagonal imbalances in a row on one side get a bracket.
   - *Unfinished auction*: at the bar's high, volume on **both** bid and ask at the top price (and at the
     low, both at the bottom price) gets a small triangle; zero on one side is a finished auction, no mark.
   - *Delta number*: the bar's delta printed under the bar.
5. **Profile prior:** `Profile` keeps the previous session's volume dict and the `profile` message gains
   `prev: {poc, vah, val, rows}`. The right edge draws it as a faint ghost histogram next to the current
   one; params `prior` (bool) and `lines` (bool, VAH / VAL / POC as extended lines, naked POC dashed).
6. **Big prints:** bubble radius scaled by size; sweeps drawn as a vertical span from `px_from` to `px_to`
   with a chevron, param `sweeps` (bool), `min` (existing).
7. **Absorption:** marker at the time the flag set, at the level, coloured by the absorbing side
   (bid absorbing sells = green). Params `multiple` (default 3 x median) and `minSeconds`.
8. **Pulled liquidity:** small cross at `t1` at the level; params `multiple` (default 5) and `minSeconds`.
   The approach distance (the touch within 4 ticks of the level when it was withdrawn) is the tracker's own
   `pull_ticks`, not a chart param.
9. **Depth pane:** two lines (bid10 green, ask10 red) in an own pane, bar-mean of samples. **Microprice**
   is its own price-pane line (bar-mean of `micro`), so it can be switched independently.
10. **Delta divergence:** a server study (`studies_flow.py`, `DeltaDiv`) using `bar.buy - bar.sell`:
    cumulative delta reset per session; a swing high/low (`swing` bars each side, default 5) is compared
    with the previous swing in the same direction. Higher price high with lower cumulative-delta high =
    bearish; lower price low with higher cumulative-delta low = bullish. Marker sits on the swing bar but
    is only emitted once the swing is confirmed (`swing` bars later): it never repaints and is honest
    about its delay.
11. **Tape speed:** own-pane histogram of prints per second per bar (`n` / (`te` - first print), min 1 s),
    a dashed burst line at 3 x the median of the last 200 bars; bars at or above it are highlighted.

## 5. Data limits the owner should know

- Book-history indicators (1, 2, 7, 8, 9 and the history part of 3) have **12 days of NQ and ES**
  (2026-09-25 on), growing a day at a time. Other roots work live only.
- Recorded depth is **10 levels at <= 1 Hz** after the loader. A pull that happens and reverses inside
  one second is invisible; episodes shorter than ~2 s are unreliable. Hence `minSeconds` defaults.
- The 09:20-09:35 ET and 08:29:30-08:31:00 ET gates apply to the history endpoint (503 `paused`); the
  chart shows live data and fills history after the window.
- Imbalance, depth and microprice from history are 1 s samples, bar-averaged; for tick / range / volume
  bars the sample store is read by the bar's `ms` span.

## 6. Build order (each part ships and is tested on its own)

- **Plan A, server (no visible change until B):** `bookflow.py` (tracker), `bookhist.py` + `/api/book/history`,
  `booklive.py` + the depth / hub taps, `Bar` fields `te` / `span` / `sw` / `bub` (+ cache bump),
  `studies_flow.py` (`ddiv`, `tspeed`), `Profile.prev`.
- **Plan B, client:** `bookstore.js`, `flowmath.js`, `flowdefs.js`, `bookevents.js`, `flowlayer.js` and the
  small hunks in `catalog.js`, `cell.js`, `app.js`, `primitives.js`, `charts.html`. Ships all eleven items.

## 7. Constraints and rules

7.1 **Isolation.** Work in a new worktree off `main` (`.worktrees/orderflow-plus`). Other sessions have
uncommitted edits in `catalog.js`, `cell.js`, `app.js`, `server.py`, `studies_ta.py`, `charts.html`; new
logic goes in new modules and the hunks in those files stay small. The `?v=` bump in `charts.html` /
`backtest.html` is the last rebase step. `backtest.html` does not load the L2 modules: these indicators
are Charts-page only unless added there on purpose.
7.2 **Restart gate.** Python changes need a chart-service restart, which cancels running tester jobs:
check and restart in one gated command, only after merge, and check `desk_status` first.
7.3 **No new dependency.** No pandas/pyarrow in the chart service.
7.4 **Caps.** `MAX_STUDIES = 16`; history response <= 2 MB; `bub` <= 60 per bar; the book endpoint
refuses a second request while busy (503), like the depth history.
7.5 **No behaviour change by default.** New params default off where they add visual weight; existing
saved charts look the same on load. Big orders gains the history segments (default on: that is the upgrade).

## 8. Tests and acceptance

- `tests/test_bookflow.py`: synthetic books and prints for each end state (traded / pulled / faded),
  absorption true and false cases, ratio and trailing-median edges, the sample maths, and determinism:
  replaying one recorded NQ day through the history path and through a simulated live feed gives
  identical episodes.
- `tests/test_charts_bars.py`: `te`, `sw`, `bub` on synthetic ticks; sweep rule checked against a real
  day (reported number, see 4.3); cache version bump covered.
- `tests/test_charts_studies_ta.py`: `DeltaDiv` (confirmation delay, no repaint, session reset) and
  tape speed.
- `tests/js/bookstore.test.mjs`, `bookevents.test.mjs`, footprint-extras and profile-prior math tests.
- Live check in the preview on a recorded NQ day: each of the eleven drawn, screenshot per item;
  the gate window shows `paused`, not an error.
- Whole suites green: `.venv/bin/python -m pytest -q tests/test_charts_*.py` and
  `node --test tests/js/*.test.mjs`.

## 9. Out of scope

Recording more roots' depth (an env switch, `HOMEBASE_DEPTH_ROOTS`; costs disk, owner's call), deeper
than 10 recorded levels, strategy blocks or Lab filters from these, Pine versions, alerts on events.

## 10. Decisions made for the owner (flip any)

- Episodes and series computed once in Python (not JS), so live and history cannot disagree.
- Imbalance moves to its own pane (history needs one); the legend gauge stays.
- Bubbles use a new aggregated `bub` field (real Bookmap-style bubbles) rather than the sparse
  >= 10-contract `big` prints.
- Absorption / pulled definitions are first guesses with the numbers in one `TUNING` dict; the owner
  reviews them on real days before they are trusted.
