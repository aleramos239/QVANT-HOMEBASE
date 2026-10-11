# Order-flow indicators, Plan A (server) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The chart service learns the order-book's life (episodes + samples, live and from recorded files), and its bars carry the tick fields (time span, sweeps, trade bubbles) the new indicators need, with two new flow studies and a prior-session profile.

**Architecture:** One pure, deterministic `BookTracker` is fed the same two streams everywhere it runs: the book lines the recorder writes (live: a tap beside the recorder; history: the recorded `*.depth.jsonl.gz` replayed) and the classified prints (live: a hub tap; history: the tick archive). Bars gain `te`, `span`, `sw`, `bub`. Two studies (`ddiv`, `tspeed`) read them. Nothing in this plan changes what a page shows; Plan B draws it.

**Tech Stack:** Python 3.14 (`.venv`), FastAPI chart service (port 8852), pytest. No new dependency (no pandas / pyarrow in the chart service).

**Spec:** `docs/superpowers/specs/2026-10-11-orderflow-indicators-design.md` (read §3, §4.1-4.3, §7). Prototype notes, calibration and all numbers below were measured on two real NQ days (2026-10-07, 2026-10-08).

## Global Constraints

- Work in a worktree off `main`: `git worktree add .worktrees/orderflow-plus -b feat/orderflow-plus main` (spec 7.1). Other sessions have uncommitted edits in `homebase/charts/server.py` (and in the page files used by Plan B): keep every hunk in them small, anchored by function name, and rebase the `?v=` bumps last.
- Do **not** restart the chart service from a task. Python changes go live only after merge, with a gated restart (a restart cancels running tester jobs: check `desk_status` and restart in one command; spec 7.2). Do not commit or push beyond the worktree branch unless the owner asks.
- No new dependency in the chart service (spec 7.3). `MAX_STUDIES` stays 16; the book history answer is at most 2 MB; `bub` is at most 60 rows a bar (spec 7.4).
- The book history endpoint refuses a second request while one runs (503 `busy`) and answers 503 inside the paused windows (09:20-09:35 ET, and 08:29:30-08:31:00 ET on weekdays), exactly like `/api/depth/history`.
- Every number in `bookflow.TUNING`, `OPEN_RATIO`, `CLOSE_RATIO` is a first guess, kept in one place for the owner to review on real days.
- No strategy claim is made from any of these indicators (they are chart-reading aids).
- Test commands use the repo venv: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest` (the system python has no pytest).

## Review Focus

- A root with **no recorded depth** (everything but NQ/ES, and NQ/ES before 2026-09-25): `/api/book/history` answers 200 with empty `samples` / `episodes`, never an error (test in Task 6; `BookHistory` itself in Task 4).
- A **crossed or empty book line** (bids or offers missing): the tracker keeps going; microprice and spread are `null` (test in Task 3, again through `BookLive` in Task 5).
- **The 18:00 ET roll while live**: the old session's open levels are closed (`faded`) and a fresh tracker starts; nothing from the old day leaks (test in Task 5).
- **Prints with no book yet** (feed starts, first print before first book): no crash, no phantom episode (tests in Tasks 3 and 5).
- **Out-of-order or duplicate ticks** across a minute boundary: bubbles and sweeps are per bar; a one-second group split by a bar boundary is below the minimum in both pieces and is dropped (documented in the hub test, Task 1).
- A **page that does not say `flow`** (an older page, or a test client): it gets the new `sw` / `bub` keys too and ignores them (`flow` defaults true on the wire); `fp=False, big=False, flow=False` is byte-identical to the old lean payload (tests in Task 1).

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `homebase/charts/bookflow.py` | Create | `BookTracker`: samples + order-level episodes, pure |
| `homebase/charts/bookhist.py` | Create | `BookHistory` (replay of recorded days), `child_book`, `BookPool` |
| `homebase/charts/booklive.py` | Create | `BookLive`: per-root live tracker, fan-out to pages |
| `homebase/charts/studies_flow.py` | Create | `DeltaDiv` (`ddiv`), `TapeSpeed` (`tspeed`), wire keys |
| `homebase/charts/bars.py` | Modify | `Bar.te / span / sw / bub`, `wire(flow=)` |
| `homebase/charts/history.py` | Modify | `CACHE_VERSION` 1 -> 2 |
| `homebase/charts/studies.py` | Modify | `make()` routes flow names; `Profile.prev` |
| `homebase/charts/hub.py` | Modify | `warm_bars`, `Hub.taps`, `payload / older` take `flow` |
| `homebase/charts/depth.py` | Modify | `Depth.tap` |
| `homebase/charts/depthgrid.py` | Modify | `HistoryPool._run` (shared by `BookPool`) |
| `homebase/charts/server.py` | Modify | `/api/book/history`, live wiring, `flow` on `sub` / `older` |
| `tests/test_bookflow.py`, `test_bookhist.py`, `test_booklive.py`, `test_charts_book_server.py`, `test_charts_depth_tap.py`, `test_charts_studies_flow.py`, `test_charts_bars_flow.py` | Create | new behaviour |
| `tests/test_charts_bars.py`, `test_charts_hub.py`, `test_charts_server.py` | Modify | four existing tests that pin the exact wire keys / the `payload` signature |

---

### Task 1: Bar tick fields (`te`, `span`, sweeps, bubbles) and the flow wire flag

**Files:**
- Modify: `homebase/charts/bars.py`, `homebase/charts/history.py`, `homebase/charts/hub.py` (`Stream.payload`, `Hub.older`), `homebase/charts/server.py` (`flow` on `sub` and `older`)
- Create: `tests/test_charts_bars_flow.py`
- Modify (four existing tests that pin the exact wire keys or the `payload` signature): `tests/test_charts_bars.py`, `tests/test_charts_hub.py`, `tests/test_charts_server.py` (two tests)

**Interfaces:**
- Produces: `Bar.te: int` (ms of the last print), `Bar.span: int` (a time bar's length in ms, 0 for tick / range bars), `Bar.sw: list[[ts_ms, px_from, px_to, size, side]]`, `Bar.bub: list[[sec, px, size, side]]`, `Bar.seal(tick_size)`, `bars.BUB_CAP = 60`, `bars.BUB_MIN = 3`, `bars.SWEEP_TICKS = 2`; `Bar.wire(tick_size, fp=True, big=True, flow=True)` adds `"sw"` and `"bub"` (between `"big"` and `"fp"`) when `flow`; `Stream.payload(fp, big, flow)` and `Hub.older(s, before_ms, fp, big, flow)`; ws `sub` / `older` read `"flow"` (default true, so an old page is unchanged).
- Consumes: `Tick(ts_ms, price, size, side, id=0)` from `homebase/charts/tick.py`.

Rules (spec 4.3, calibrated on two real NQ days): a **sweep** is two or more prints with the same side and the same millisecond that span 2 or more price rows (`SWEEP_TICKS = 2`; it is about 0.7 x the volume of the research order-id sweeps, because the feed's stamp is one millisecond). A **bubble** is the contracts printed in one second, at one price, on one side, kept when at least `BUB_MIN = 3`, the 60 (`BUB_CAP`) largest per bar (a tie is broken by time, then price). Sweeps and bubbles are per bar. `flow` is its own flag, apart from `big`, because a session of 1-minute bars with the footprint is 1.1 MB without sweeps and bubbles and 2.5 MB with them (Step 7), and the page asks for them only when a bubble / sweep option is on. `CACHE_VERSION` goes to 2 so the `.m1.pkl` caches are rebuilt with the new fields.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_charts_bars_flow.py`:

```python
"""The tick fields a Bar carries for the order-flow indicators: te, span, sweeps (sw), bubbles (bub)."""
from __future__ import annotations

import random

from homebase.charts.bars import BUB_CAP, BarSpec, build, resample
from homebase.charts.tick import BUY, SELL, Tick

TS = 0.25
BASE = 1_760_000_040_000          # a whole minute (a multiple of 60 000 ms)
M1 = BarSpec.parse("time:60")


def T(ms, price, size=1, side=BUY):
    return Tick(BASE + ms, price, size, side)


def test_te_is_the_last_print_and_span_the_time_bars_length():
    closed, cur = build([T(0, 100.0), T(1500, 100.25), T(61_000, 101.0)], M1, TS)
    assert closed[0].te == BASE + 1500 and closed[0].span == 60_000
    assert cur.te == BASE + 61_000 and cur.span == 60_000
    tick_bars, _ = build([T(i * 10, 100.0) for i in range(6)], BarSpec.parse("tick:3"), TS)
    assert tick_bars[0].span == 0


def test_a_sweep_is_one_aggressor_walking_levels_inside_one_millisecond():
    ticks = [T(0, 100.0, 1), T(0, 100.25, 2), T(0, 100.75, 5),       # one ms, one side, 4 ticks wide
             T(5, 101.0, 4), T(5, 101.0, 3),                          # same ms and level twice: not a sweep
             T(9, 101.0, 1, SELL), T(9, 100.75, 1, SELL),             # two levels (1 tick): not a sweep
             T(20, 100.0, 1)]
    closed, cur = build(ticks, M1, TS)
    assert cur.wire(TS)["sw"] == [[BASE, 100.0, 100.75, 8, BUY]]
    closed, _ = build(ticks + [T(61_000, 100.0)], M1, TS)
    assert closed[0].sw == [[BASE, 100.0, 100.75, 8, BUY]]            # sealed with the bar


def test_bubbles_are_second_price_side_totals_of_at_least_three_largest_sixty_kept():
    ticks = [T(0, 100.0, 1), T(400, 100.0, 2), T(999, 100.0, 1, SELL),       # 100.0 buy 3 in second 0; the sell is 1
             T(1000, 100.0, 2), T(1100, 100.25, 9, SELL)]                    # second 1: buy 2 (below min), sell 9
    closed, cur = build(ticks + [T(61_000, 100.0)], M1, TS)
    sec0 = BASE // 1000
    assert closed[0].bub == [[sec0, 100.0, 3, BUY], [sec0 + 1, 100.25, 9, SELL]]
    many = [T(s * 1000, 100.0 + (s % 50) * TS, 3 + s % 7) for s in range(55)] + [T(s * 1000 + 500, 90.0, 40) for s in range(30)]
    bar, _ = build(many + [T(61_000, 100.0)], M1, TS)
    assert len(bar[0].bub) == BUB_CAP
    assert min(b[2] for b in bar[0].bub) >= 3
    assert sum(1 for b in bar[0].bub if b[2] == 40) == 30           # the big ones all stayed


def test_wire_carries_sw_and_bub_with_the_flow_flag_and_not_without():
    closed, _ = build([T(0, 100.0, 12), T(0, 100.5, 3), T(61_000, 100.0)], M1, TS)
    w = closed[0].wire(TS)
    assert "sw" in w and "bub" in w and "big" in w
    lean = closed[0].wire(TS, flow=False)
    assert "sw" not in lean and "bub" not in lean and "big" in lean
    assert "sw" in closed[0].wire(TS, big=False)


def test_resampled_bubbles_and_sweeps_equal_the_direct_build_on_an_ordered_tape():
    rng = random.Random(7)
    ticks, t = [], 0
    for _ in range(12000):
        t += rng.choice([0, 0, 1, 3, 40, 300, 900])
        ticks.append(T(t, 100.0 + rng.randint(0, 12) * TS, rng.randint(1, 15), rng.choice([BUY, SELL])))
    cut = ticks[-1].ts_ms + 1
    ticks.append(Tick(cut + 120_000, 100.0, 1, BUY))
    m1, _ = build(ticks, M1, TS)
    direct, _ = build(ticks, BarSpec.parse("time:300"), TS)
    via = resample(m1, BarSpec.parse("time:300"))
    n = min(len(direct), len(via)) - 1
    assert n >= 3
    for a, b in zip(direct[:n], via[:n]):
        assert a.sw == b.sw and a.bub == b.bub and a.te == b.te and a.span == b.span


def test_copy_keeps_the_developing_state_and_never_shares_it():
    _, cur = build([T(0, 100.0, 2), T(0, 100.25, 1)], M1, TS)      # one tick wide so far: no sweep
    c = cur.copy()
    c.add(T(0, 101.0, 4), TS)
    assert cur.wire(TS)["sw"] == [] and c.wire(TS)["sw"] == [[BASE, 100.0, 101.0, 7, BUY]]
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_bars_flow.py`
Expected: FAIL (`ImportError: cannot import name 'BUB_CAP' from 'homebase.charts.bars'`).

- [ ] **Step 3: Implement `bars.py` and bump the cache version**

Apply to `homebase/charts/bars.py`:

```diff
--- a/homebase/charts/bars.py
+++ b/homebase/charts/bars.py
@@ -20,6 +20,9 @@
 
 KINDS = ("time", "tick", "volume", "range")
 BIG_MIN = 10        # prints of >= this many contracts are kept per bar
+SWEEP_TICKS = 2     # a burst of same-side prints inside one millisecond that spans >= this many ticks is a sweep
+BUB_MIN = 3         # trade bubbles: contracts printed in one second at one price on one side, at least this many
+BUB_CAP = 60        # ... and at most this many per bar (the largest)
 
 
 @dataclass(frozen=True)
@@ -44,6 +47,13 @@
         return self.kind == "time" and self.size % 60 == 0
 
 
+def _cap_bubbles(rows: list) -> list:
+    """The BUB_CAP largest bubbles, in time order; a tie on size is broken by time then price, so the same prints
+    always keep the same rows however the bar was assembled."""
+    rows.sort(key=lambda r: (-r[2], r[0], r[1], r[3]))
+    return sorted(rows[:BUB_CAP], key=lambda r: (r[0], r[1], r[3]))
+
+
 @dataclass
 class Bar:
     t: int                  # start, epoch ms (time: bucket start; others: first trade)
@@ -61,6 +71,12 @@
     fp: dict = field(default_factory=dict)    # price in ticks -> [sell at bid, buy at ask]
     big: list = field(default_factory=list)   # [ts_ms, price, size, side], size >= BIG_MIN
     closed: bool = False
+    te: int = 0                                # ms of the bar's last print
+    span: int = 0                              # a time bar's length in ms (0: a tick / volume / range bar)
+    sw: list = field(default_factory=list)     # sweeps: [ts_ms, price_from, price_to, size, side]
+    bub: list = field(default_factory=list)    # bubbles: [sec, price, size, side], sealed (see seal())
+    _bd: dict = field(default_factory=dict, repr=False, compare=False)   # developing bubbles: (sec, tick, side) -> size
+    _g: object = field(default=None, repr=False, compare=False)          # the sweep group in progress
 
     @classmethod
     def open_at(cls, t: int, session: str, price: float) -> "Bar":
@@ -93,12 +109,43 @@
             cell[0] += q
         if q >= BIG_MIN:
             self.big.append([tk.ts_ms, p, q, tk.side])
+        if tk.ts_ms > self.te:
+            self.te = tk.ts_ms
+        bk = (tk.ts_ms // 1000, k, 1 if tk.side > 0 else -1)
+        self._bd[bk] = self._bd.get(bk, 0) + q
+        g = self._g
+        if g is not None and g[0] == tk.ts_ms and g[1] == tk.side:
+            g[2] = min(g[2], k)
+            g[3] = max(g[3], k)
+            g[4] += q
+            g[5] += 1
+        else:
+            self._flush_group(tick_size)
+            self._g = [tk.ts_ms, tk.side, k, k, q, 1]
+
+    def _flush_group(self, tick_size: float) -> None:
+        g, self._g = self._g, None
+        if g is not None and g[5] >= 2 and g[3] - g[2] >= SWEEP_TICKS:
+            self.sw.append([g[0], round(g[2] * tick_size, 6), round(g[3] * tick_size, 6), g[4], g[1]])
+
+    def seal(self, tick_size: float) -> None:
+        """The bar is closed: finish the sweep group and fold the developing bubbles into the capped list."""
+        self._flush_group(tick_size)
+        self.bub = self._bubbles(tick_size)
+        self._bd = {}
 
+    def _bubbles(self, tick_size: float) -> list:
+        rows = [list(x) for x in self.bub]
+        rows += [[s, round(k * tick_size, 6), q, side] for (s, k, side), q in self._bd.items() if q >= BUB_MIN]
+        return _cap_bubbles(rows)
+
     def copy(self) -> "Bar":
         return Bar(self.t, self.session, self.o, self.h, self.l, self.c, self.v,
                    self.buy, self.sell, self.n, self.pv, self.p2v,
                    {k: list(c) for k, c in self.fp.items()},
-                   [list(x) for x in self.big], self.closed)
+                   [list(x) for x in self.big], self.closed, self.te, self.span,
+                   [list(x) for x in self.sw], [list(x) for x in self.bub], dict(self._bd),
+                   list(self._g) if self._g else None)
 
     def merge(self, other: "Bar") -> None:
         """Absorb the NEXT bar in time (resampling)."""
@@ -116,16 +163,27 @@
             cell[0] += s
             cell[1] += b
         self.big.extend(list(x) for x in other.big)
+        self.te = max(self.te, other.te)
+        self.sw.extend(list(x) for x in other.sw)
+        self.bub = _cap_bubbles([list(x) for x in self.bub] + [list(x) for x in other.bub])
+        for bk, q in other._bd.items():
+            self._bd[bk] = self._bd.get(bk, 0) + q
+        self._g = list(other._g) if other._g else None
 
-    def wire(self, tick_size: float, fp: bool = True, big: bool = True) -> dict:
+    def wire(self, tick_size: float, fp: bool = True, big: bool = True, flow: bool = True) -> dict:
         """JSON for the page: t = ET wall-clock seconds (the axis shows ET),
-        ms = the real start in epoch ms. fp / big False: without the footprint /
-        the big prints (a chart that draws neither does not ask for them)."""
+        ms = the real start in epoch ms. fp / big / flow False: without the footprint / the big prints / the
+        sweeps and trade bubbles (a chart that draws none of them does not ask for them)."""
         d = {"t": et_wall_s(self.t), "ms": self.t, "s": self.session,
              "o": self.o, "h": self.h, "l": self.l, "c": self.c,
              "v": self.v, "d": self.delta, "n": self.n}
         if big:
             d["big"] = self.big
+        if flow:
+            d["sw"] = self.sw + ([[self._g[0], round(self._g[2] * tick_size, 6), round(self._g[3] * tick_size, 6),
+                                   self._g[4], self._g[1]]]
+                                 if self._g and self._g[5] >= 2 and self._g[3] - self._g[2] >= SWEEP_TICKS else [])
+            d["bub"] = self._bubbles(tick_size) if self._bd else self.bub
         if fp:
             d["fp"] = [[round(k * tick_size, 6), s, b] for k, (s, b) in sorted(self.fp.items())]
         return d
@@ -168,6 +226,8 @@
                 # and a rebuild from the recorded ticks files it in its own bar.
                 return closed
             self.cur = Bar.open_at(t, self._sess, tk.price)
+            if self.spec.kind == "time":
+                self.cur.span = self.spec.size * 1000
         self.cur.add(tk, self.tick_size)
         if self._full(self.cur):
             closed.append(self._close())
@@ -214,6 +274,7 @@
     def _close(self) -> Bar:
         b, self.cur = self.cur, None
         b.closed = True
+        b.seal(self.tick_size)
         return b
 
 
@@ -244,6 +305,7 @@
                 out.append(cur)
             cur = m.copy()
             cur.t = t
+            cur.span = n
             cur.closed = True
         else:
             cur.merge(m)
```

`homebase/charts/history.py`:

```diff
--- a/homebase/charts/history.py
+++ b/homebase/charts/history.py
@@ -29,7 +29,7 @@
 from .store import TickStore
 
 M1 = BarSpec("time", 60)
-CACHE_VERSION = 1
+CACHE_VERSION = 2
 WATCH_DAYS = 35         # sessions this recent are watched for a fill landing in their files (the tick job merges
                         # live recordings 30 days back, ticks.LIVE_LOOKBACK_DAYS); older ones only change by hand
```

- [ ] **Step 4: Thread `flow` through the hub and the service**

`homebase/charts/hub.py` (`Stream.payload` and `Hub.older`; the other hub hunks are Tasks 2 and 6):

```diff
--- a/homebase/charts/hub.py
+++ b/homebase/charts/hub.py
@@ -123,16 +123,16 @@
         self.studies[key] = st
         self.values[key] = [st.push(b) for b in self.bars]
 
-    def payload(self, fp: bool = True, big: bool = True) -> dict:
+    def payload(self, fp: bool = True, big: bool = True, flow: bool = True) -> dict:
         """The history message: the most recent HISTORY_MAX bars, every
         study's values sliced to match. A subscriber's cursor is still
         len(self.bars), so its updates continue where this ends. fp / big:
-        whether the bars carry their footprint / big prints (Bar.wire)."""
+        whether the bars carry their footprint / big prints / sweeps and bubbles (Bar.wire)."""
         ts, live = self.tick_size, self.builder.cur
         first = max(0, len(self.bars) + (live is not None) - HISTORY_MAX)
-        bars = [b.wire(ts, fp, big) for b in self.bars[first:]]
+        bars = [b.wire(ts, fp, big, flow) for b in self.bars[first:]]
         if live is not None:
-            bars.append(live.wire(ts, fp, big))
+            bars.append(live.wire(ts, fp, big, flow))
         studies = {k: self.values[k][first:] + ([st.preview(live)] if live is not None else [])
                    for k, st in self.studies.items()}
         return {"root": self.root, "spec": self.spec.key, "tick_size": ts, "point_value": point_value(self.root),
@@ -364,7 +364,7 @@
         """The stream a chart (conn, chart id) is subscribed to."""
         return next((s for s in self.streams.values() if sub in s.subs), None)
 
-    def older(self, s: Stream, before_ms: int, fp: bool = True, big: bool = True) -> dict:
+    def older(self, s: Stream, before_ms: int, fp: bool = True, big: bool = True, flow: bool = True) -> dict:
         """Worker thread: scroll-back. The next chunk of COMPLETED sessions strictly before before_ms (the
         page's first bar), newest first, until sessions_back(spec) sessions or HISTORY_MAX bars (a session
         that does not fit gives its newest bars; the next request continues before them), or BUILD_BUDGET_S
@@ -415,7 +415,7 @@
             st = make(k, s.tick_size)
             studies[k] = [st.push(b) for b in chunk]
             repair[k] = [st.push(b) for b in ahead]
-        return {"bars": [b.wire(s.tick_size, fp, big) for b in chunk], "studies": studies, "repair": repair,
+        return {"bars": [b.wire(s.tick_size, fp, big, flow) for b in chunk], "studies": studies, "repair": repair,
                 "sessions": infos, "done": i == 0 and not trimmed}
 
     def drop_conn(self, conn) -> None:
```

`homebase/charts/server.py` (the file carries other sessions' uncommitted edits: apply these six edits by hand, anchored by the function names):

```diff
--- a/homebase/charts/server.py
+++ b/homebase/charts/server.py
@@ -1073,7 +1073,7 @@
                                 # interval switch is never blocked by the old stream's still-running chunk
     older_tasks: set = set()    # the answering tasks, referenced until they finish
 
-    def ask_older(conn: Conn, cid: str, before, fp: bool = True, big: bool = True) -> None:
+    def ask_older(conn: Conn, cid: str, before, fp: bool = True, big: bool = True, flow: bool = True) -> None:
         """A chart scrolled back to its first bar ({"op": "older", "id", "before": that bar's ms}): build the
         next chunk of older sessions off the loop and answer {"type": "older", "id", "before", "bars",
         "studies", "repair", "sessions", "done"}, or with an "error" (the page waits, then may ask again).
@@ -1091,13 +1091,14 @@
             conn.send({"type": "older", "id": cid, "before": before, "error": "busy"})
             return
         older_busy.add(key)
-        task = asyncio.create_task(answer_older(conn, cid, key, s, before, fp, big))
+        task = asyncio.create_task(answer_older(conn, cid, key, s, before, fp, big, flow))
         older_tasks.add(task)
         task.add_done_callback(older_tasks.discard)
 
-    async def answer_older(conn: Conn, cid: str, key: tuple, s: Stream, before: int, fp: bool, big: bool) -> None:
+    async def answer_older(conn: Conn, cid: str, key: tuple, s: Stream, before: int, fp: bool, big: bool,
+                           flow: bool = True) -> None:
         try:
-            ans = await asyncio.to_thread(hub.older, s, before, fp, big)
+            ans = await asyncio.to_thread(hub.older, s, before, fp, big, flow)
         except Exception as e:  # noqa: BLE001 — a failed chunk is the page's to retry, never the socket's end
             log(f"older {cid} ({s.root} {s.spec.key}): {type(e).__name__}: {e}")
             ans = {"error": str(e) or type(e).__name__}
@@ -1834,7 +1835,8 @@
                     continue
                 if op == "older":
                     if not replays.ask_older(conn, cid, msg.get("before")):
-                        ask_older(conn, cid, msg.get("before"), bool(msg.get("fp", True)), bool(msg.get("big", True)))
+                        ask_older(conn, cid, msg.get("before"), bool(msg.get("fp", True)), bool(msg.get("big", True)),
+                                  bool(msg.get("flow", True)))
                     continue
                 if op == "replay_start":
                     if await replays.start(conn, cid, msg, live=hub.stream_of((conn, cid))):
@@ -1881,7 +1883,8 @@
                     # fp / big: a chart that draws no footprint / no big prints asks for its bars without
                     # them (cell.js need()); a sub that says nothing gets both, as before
                     conn.send({"type": "history", "id": cid,
-                               **s.payload(bool(msg.get("fp", True)), bool(msg.get("big", True)))})
+                               **s.payload(bool(msg.get("fp", True)), bool(msg.get("big", True)),
+                                           bool(msg.get("flow", True)))})
                     if depth is not None:
                         depth.view((conn, cid), root, conn.send, room)   # after `history`: depth follows it
                 except Exception as e:  # noqa: BLE001 — an unexpected failure building the
```

- [ ] **Step 5: Update the four existing tests that pin the wire keys or the `payload` signature**

`tests/test_charts_bars.py::test_wire_leaves_out_the_footprint_and_the_big_prints_only_when_asked_to`; `tests/test_charts_hub.py` (the decimal-tick replay test: its tape is out of order on purpose, so a bubble's second can fall in two minute bars and be below the minimum in each; an in-order tape is tested in Step 1); `tests/test_charts_server.py::test_footprint_and_big_prints_come_only_when_the_chart_asks_for_them` and `::test_a_failed_subscribe_leaves_no_orphaned_stream_or_pending_update` (its monkeypatched `payload` now takes `flow`):

```diff
--- a/tests/test_charts_bars.py
+++ b/tests/test_charts_bars.py
@@ -125,7 +125,8 @@
 def test_wire_leaves_out_the_footprint_and_the_big_prints_only_when_asked_to():
     closed, _ = build([T(M, 100.0, 12, SELL), T(M + 1, 100.25, 3)], BarSpec("tick", 2), TS)
     full = closed[0].wire(TS)
-    assert list(full)[-2:] == ["big", "fp"] and full["big"] == [[M, 100.0, 12, SELL]]     # as it always was
-    assert closed[0].wire(TS, fp=False, big=False) == {k: v for k, v in full.items() if k not in ("fp", "big")}
+    assert list(full)[-4:] == ["big", "sw", "bub", "fp"] and full["big"] == [[M, 100.0, 12, SELL]]
+    assert closed[0].wire(TS, fp=False, big=False, flow=False) == {k: v for k, v in full.items() if k not in ("fp", "big", "sw", "bub")}
     assert closed[0].wire(TS, fp=False) == {k: v for k, v in full.items() if k != "fp"}
     assert closed[0].wire(TS, big=False) == {k: v for k, v in full.items() if k != "big"}
+    assert closed[0].wire(TS, flow=False) == {k: v for k, v in full.items() if k not in ("sw", "bub")}
```

```diff
--- a/tests/test_charts_hub.py
+++ b/tests/test_charts_hub.py
@@ -624,7 +624,10 @@
         s = hub.prepare("GC", spec, []).stream
         closed, cur = build(tape, spec, 0.1, "GC")
         got, want = s.bars + [s.builder.cur], closed + [cur]
-        assert [b.wire(0.1) for b in got] == [b.wire(0.1) for b in want]
+        # (bubbles aside: rough_rows is out of order on purpose, so one second's prints can fall in two 1-minute bars
+        # and be below the bubble minimum in each; an in-order tape is tested in test_charts_bars_flow.py)
+        nob = lambda b: {k: v for k, v in b.wire(0.1).items() if k != "bub"}
+        assert [nob(b) for b in got] == [nob(b) for b in want]
         assert [b.closed for b in got] == [b.closed for b in want]
         assert [b.pv for b in got] == pytest.approx([b.pv for b in want], rel=1e-12)
         assert [b.p2v for b in got] == pytest.approx([b.p2v for b in want], rel=1e-12)
```

```diff
--- a/tests/test_charts_server.py
+++ b/tests/test_charts_server.py
@@ -746,11 +746,11 @@
     orig_payload = Stream.payload
     calls = [0]
 
-    def payload(self, fp=True, big=True):
+    def payload(self, fp=True, big=True, flow=True):
         calls[0] += 1
         if calls[0] == 1:
             raise RuntimeError("payload boom")
-        return orig_payload(self, fp, big)
+        return orig_payload(self, fp, big, flow)
 
     monkeypatch.setattr(Stream, "payload", payload)
 
@@ -1711,8 +1711,11 @@
         return [b for b in m["bars"] if b["s"] != D.isoformat()]
 
     def lean(bars):
-        return [{k: v for k, v in b.items() if k not in ("fp", "big")} for b in bars]
+        return [{k: v for k, v in b.items() if k not in ("fp", "big", "sw", "bub")} for b in bars]
 
+    def no_flow(bars):
+        return [{k: v for k, v in b.items() if k not in ("sw", "bub")} for b in bars]
+
     with TestClient(app, base_url="http://127.0.0.1:8852") as client, client.websocket_connect("/ws", headers={"host": "localhost:8852"}) as ws:
         ws.send_json({"op": "sub", "id": "c1", "root": "NQ", "spec": "time:60"})
         full = next_of(ws, "history")
@@ -1724,15 +1727,19 @@
 
         ws.send_json({"op": "sub", "id": "c1", "root": "NQ", "spec": "time:60", "fp": False, "big": False})
         bare = next_of(ws, "history")
-        assert all("fp" not in b and "big" not in b for b in bare["bars"])
+        assert all("fp" not in b and "big" not in b and "sw" in b and "bub" in b for b in bare["bars"])   # flow said nothing: kept
+        assert past(bare) == [{k: v for k, v in b.items() if k not in ("fp", "big")} for b in past(full)]
+        ws.send_json({"op": "sub", "id": "c1", "root": "NQ", "spec": "time:60", "fp": False, "big": False, "flow": False})
+        bare = next_of(ws, "history")
+        assert all(not ({"fp", "big", "sw", "bub"} & set(b)) for b in bare["bars"])
         assert past(bare) == lean(past(full))
-        ws.send_json({"op": "older", "id": "c1", "before": bare["bars"][0]["ms"], "fp": False, "big": False})
+        ws.send_json({"op": "older", "id": "c1", "before": bare["bars"][0]["ms"], "fp": False, "big": False, "flow": False})
         bare_older = next_of(ws, "older")
         assert bare_older == {**full_older, "bars": lean(full_older["bars"])}
 
         ws.send_json({"op": "sub", "id": "c1", "root": "NQ", "spec": "time:60", "fp": True, "big": False})
         only_fp = next_of(ws, "history")
-        assert all("fp" in b and "big" not in b for b in only_fp["bars"])
+        assert all("fp" in b and "big" not in b and "sw" in b and "bub" in b for b in only_fp["bars"])
 
 
 def test_a_second_older_request_while_one_builds_gets_busy_not_silence(tmp_path, monkeypatch):
```

- [ ] **Step 6: Run the bar, hub, server and history tests**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_bars.py tests/test_charts_bars_flow.py tests/test_charts_hub.py tests/test_charts_server.py tests/test_charts_history.py`
Expected: PASS (`test_charts_bars_flow.py`: 6 tests).

- [ ] **Step 7: Measure the payload and put the number in the commit message**

Run in the worktree:
```bash
/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python - <<'PY'
import json, datetime as dt
from homebase.charts.store import ARCHIVE, TickStore
from homebase.charts.bars import BarSpec, build
s = TickStore(ARCHIVE).load('NQ', dt.date(2026, 10, 8))
closed, _ = build(s.ticks, BarSpec.parse('time:60'), 0.25)
f = lambda **k: len(json.dumps([b.wire(0.25, **k) for b in closed], separators=(',', ':')))
print('1m bars', len(closed), 'full', f(), 'no flow', f(flow=False), 'big only', f(fp=False, flow=False))
PY
```
Expected (measured on the prototype): `1m bars 1379 full 2455626 no flow 1102286 big only 213656` (bytes). The sweeps and bubbles are 1.35 MB of that, six times the big-print rows, which is why `flow` is its own flag.

- [ ] **Step 8: Commit**

```bash
git add homebase/charts/bars.py homebase/charts/history.py homebase/charts/hub.py homebase/charts/server.py tests/test_charts_bars_flow.py tests/test_charts_bars.py tests/test_charts_hub.py tests/test_charts_server.py
git commit -m "feat(charts): bars carry te / span / sweeps / trade bubbles; flow flag on sub and older; cache v2" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 2: Two flow studies (`ddiv`, `tspeed`) and the prior-session profile

**Files:**
- Create: `homebase/charts/studies_flow.py`, `tests/test_charts_studies_flow.py`
- Modify: `homebase/charts/studies.py` (`make()` routes the flow names; `Profile.prev_vol` + `"prev"` in `Profile.value`), `homebase/charts/hub.py` (`warm_bars` knows the flow names), `tests/test_charts_bars_flow.py` (one test appended)

**Interfaces:**
- Consumes: Task 1's `Bar.te`, `Bar.span`; `studies_ta.make_ta_num` (the same number-parsing helper the technical studies use) and `studies._Study`-style `initial() / step(state, bar) -> (state, value) / preview(bar)`.
- Produces: study keys `ddiv:<n>` (n 1..50, default 5) and `tspeed:<n>` (n 20..2000, default 200). `ddiv` emits `{"dir": 1|-1, "ago": n, "px": float}` on the bar after a confirmed divergence and `None` otherwise (a developing bar never emits). `tspeed` emits `{"rate": prints_per_second, "burst": float | None, "hot": float | None}`: `rate` = the bar's print count over `max(1 s, its length)` (a closed time bar's `span`, else `te - t` of a developing or tick bar); `burst` = 3 x the median of the last `n` closed bars' rates (once 10 exist, else `None`); `hot` = the rate when it is at or above `burst`, else `None`. `Profile.value()` gains `"prev"` (the finished session's profile) when there is one; `warm_flow(name, rest) -> int` (ddiv `4n+2`, tspeed `n+1`) feeds `hub.warm_bars`.

A divergence is: a swing high (the highest of `2n + 1` bars) above the previous swing high while the session's cumulative delta at it is *lower* than at the previous one (bearish, `dir -1`); a swing low below the previous swing low on a *higher* cumulative delta (bullish, `dir +1`). A swing is known only `n` bars later, so the marker is emitted on the confirming bar with `ago = n`, and only a closed bar can emit it (spec 4.6). A new session resets the cumulative delta and the swings.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_charts_studies_flow.py`:

```python
"""DeltaDiv and TapeSpeed (studies_flow.py): the Study contract and the two rules, on hand-made bars."""
from __future__ import annotations

import pytest

from homebase.charts.bars import Bar
from homebase.charts.hub import warm_bars
from homebase.charts.studies import make
from homebase.charts.studies_flow import DeltaDiv, TapeSpeed

MIN = 60_000


def bar(i, h, l, buy=0, sell=0, session="2026-10-09", n=10, closed=True, te=None, span=MIN):
    b = Bar.open_at(i * MIN, session, (h + l) / 2)
    b.h, b.l, b.buy, b.sell, b.n, b.closed = h, l, buy, sell, n, closed
    b.te, b.span = (i * MIN + 30_000) if te is None else te, span
    return b


def run(study, bars):
    return [(study.preview(b), study.push(b)) for b in bars]


def test_bearish_divergence_is_emitted_n_bars_later_and_only_by_a_closed_bar():
    # swing high 10 at bar 2 (cum delta +20), higher swing high 12 at bar 7 on LOWER cum delta (+20 +10 -40 ...)
    hs = [5, 6, 10, 6, 5, 6, 9, 12, 9, 6, 5, 5]
    flows = [(20, 0)] * 3 + [(0, 10)] * 3 + [(0, 30)] * 6
    bars = [bar(i, h, h - 1, *f) for i, (h, f) in enumerate(zip(hs, flows))]
    out = run(DeltaDiv(2), bars)
    hits = [(i, push) for i, (_, push) in enumerate(out) if push]
    assert hits == [(9, {"dir": -1, "ago": 2, "px": 12})]       # bar 7's swing, confirmed by bar 9
    assert all(pre is None for pre, _ in out)                   # the developing bar never draws one


def test_bullish_divergence_and_a_higher_low_on_higher_delta_is_not_one():
    ls = [10, 9, 5, 9, 10, 9, 6, 4, 6, 9, 10, 10]
    flows = [(0, 20)] * 3 + [(10, 0)] * 3 + [(40, 0)] * 6        # cum delta rises while price makes a lower low
    bars = [bar(i, l + 1, l, *f) for i, (l, f) in enumerate(zip(ls, flows))]
    hits = [v for _, v in run(DeltaDiv(2), bars) if v]
    assert hits == [{"dir": 1, "ago": 2, "px": 4}]
    agree = [bar(i, l + 1, l, 10, 0) for i, l in enumerate(ls)]   # delta keeps rising with price: no divergence
    assert [v for _, v in run(DeltaDiv(2), agree) if v and v["dir"] == -1] == []


def test_a_new_session_resets_the_cumulative_delta_and_the_swings():
    d = DeltaDiv(1)
    d.push(bar(0, 5, 4, 100, 0))
    assert d.state[0] == "2026-10-09" and d.state[1] == 100
    d.push(bar(1, 5, 4, 10, 0, session="2026-10-10"))
    assert d.state[0] == "2026-10-10" and d.state[1] == 10 and d.state[3] is None


def test_tape_speed_rate_burst_and_hot():
    t = TapeSpeed(20)
    last = None
    for i in range(12):
        last = t.push(bar(i, 10, 9, n=60 if i < 11 else 600))
    assert last == {"rate": 10.0, "burst": 3.0, "hot": 10.0}
    quiet = t.preview(bar(12, 10, 9, n=30))
    assert quiet["hot"] is None and quiet["rate"] == 0.5


def test_tape_speed_uses_the_elapsed_time_of_a_developing_bar_and_one_second_at_least():
    t = TapeSpeed(20)
    dev = bar(0, 10, 9, n=90, closed=False, te=45_000)            # 45 s into its minute
    assert t.preview(dev)["rate"] == pytest.approx(2.0)
    one = bar(0, 10, 9, n=5, closed=False, te=100)
    assert t.preview(one)["rate"] == 5.0                          # under a second counts as one second
    assert t.preview(bar(0, 10, 9, n=0)) is None


def test_the_wire_keys():
    assert isinstance(make("ddiv"), DeltaDiv) and make("ddiv:7").n == 7
    assert make("tspeed:100").n == 100
    with pytest.raises(ValueError):
        make("ddiv:0")
    with pytest.raises(ValueError):
        make("tspeed:5000")
    with pytest.raises(ValueError):
        make("ddiv:5:6")
    assert warm_bars("ddiv:5") == 22 and warm_bars("tspeed:200") == 201
```

Append to `tests/test_charts_bars_flow.py` (and add `from homebase.charts.studies import Profile` to its imports):

```python
def test_profile_keeps_the_prior_session_for_the_ghost_and_the_lines():
    from homebase.charts.bars import Bar
    def b(session, px, v):
        x = Bar.open_at(0, session, px)
        x.fp = {int(px / TS): [0, v]}
        return x
    p = Profile(TS)
    p.push(b("2026-10-08", 100.0, 5))
    assert "prev" not in p.value()
    p.push(b("2026-10-09", 101.0, 7))
    v = p.value()
    assert v["poc"] == 101.0 and v["prev"]["poc"] == 100.0
    live = b("2026-10-10", 102.0, 1)                 # the developing bar opens a new session
    v = p.value(live)
    assert v["poc"] == 102.0 and v["prev"]["poc"] == 101.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_studies_flow.py tests/test_charts_bars_flow.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'homebase.charts.studies_flow'`, and `KeyError: 'prev'` on the profile test).

- [ ] **Step 3: Implement**

Create `homebase/charts/studies_flow.py`:

```python
"""Order-flow studies built on the tick fields a Bar carries (buy / sell / n / te / span). Pure; the Study contract of
studies_ta.py (push / preview, immutable state, None while warming up).

Wire keys (every part after the name is a number; a missing one takes its default):
  ddiv:5       delta divergence: a swing high / low of the price (n bars each side, known n bars later) against the
               session's cumulative delta at that bar. Higher price high on a LOWER cumulative-delta high = bearish
               (dir -1); lower price low on a HIGHER cumulative-delta low = bullish (dir +1). One value on the bar
               that CONFIRMS the swing, none on any other bar, and none from the developing bar (never repaints)
                                                                                  -> {dir, ago, px}
  tspeed:200   prints per second of the bar and a burst line = 3 x the median rate of the last n bars before it
                                                                                  -> {rate, burst, hot}
"""
from __future__ import annotations

import math

from .studies_ta import _Study, make_ta_num

BURST_MULT = 3.0


class DeltaDiv(_Study):
    def __init__(self, n: int = 5):
        self.n = int(n)
        super().__init__()

    def initial(self):
        # session, cumulative delta, window of (high, low, cum) for the last 2n+1 bars, previous swing high / low (price, cum)
        return (None, 0, (), None, None)

    def step(self, st, bar):
        sess, cum, win, ph, pl = st
        if bar.session != sess:
            sess, cum, win, ph, pl = bar.session, 0, (), None, None
        cum += bar.buy - bar.sell
        n = self.n
        win = (win + ((bar.h, bar.l, cum),))[-(2 * n + 1):]
        out = None
        if len(win) == 2 * n + 1:
            h, l, c = win[n]
            if h > max(w[0] for w in win[:n]) and h > max(w[0] for w in win[n + 1:]):
                if ph is not None and h > ph[0] and c < ph[1]:
                    out = {"dir": -1, "ago": n, "px": h}
                ph = (h, c)
            if l < min(w[1] for w in win[:n]) and l < min(w[1] for w in win[n + 1:]):
                if pl is not None and l < pl[0] and c > pl[1]:
                    out = {"dir": 1, "ago": n, "px": l}
                pl = (l, c)
        return (sess, cum, win, ph, pl), out

    def preview(self, bar):
        return None     # a swing is only confirmed by CLOSED bars: the developing one never draws a marker


class TapeSpeed(_Study):
    def __init__(self, n: int = 200):
        self.n = int(n)
        super().__init__()

    def initial(self):
        return ()       # the rates of the closed bars, newest last

    @staticmethod
    def _rate(bar):
        if bar.n <= 0:
            return None
        ms = bar.span if bar.closed and bar.span else bar.te - bar.t
        return bar.n / max(1.0, ms / 1000.0)

    def step(self, st, bar):
        r = self._rate(bar)
        if r is None:
            return st, None
        burst = None
        if len(st) >= 10:
            s = sorted(st)
            burst = BURST_MULT * (s[len(s) // 2] + s[(len(s) - 1) // 2]) / 2.0
        out = {"rate": r, "burst": burst, "hot": r if burst is not None and r >= burst else None}
        return (st + (r,))[-self.n:], out


# name -> (class, parameters): each parameter is (default, minimum, maximum); a wire key may give them in order
PARAMS = {
    "ddiv": (DeltaDiv, ((5, 1, 50),)),
    "tspeed": (TapeSpeed, ((200, 20, 2000),)),
}
NAMES = tuple(PARAMS)


def make_flow(name: str, args: list):
    """The flow study `name` with its wire-key `args` (strings), or ValueError: too many parameters, one not a number
    or outside its range."""
    cls, spec = PARAMS[name]
    if len(args) > len(spec):
        raise ValueError(f"bad study {name!r}: at most {len(spec)} parameter(s)")
    vals = []
    for i, (default, lo, hi) in enumerate(spec):
        vals.append(int(make_ta_num(name, args, i, default, lo, hi)))
    return cls(*vals)


def warm_flow(name: str, rest: list) -> int:
    """Bars after a join that a flow study's value still depends on (hub.warm_bars)."""
    try:
        n = int(float(rest[0]))
    except (IndexError, ValueError):
        n = PARAMS[name][1][0][0]
    return 4 * n + 2 if name == "ddiv" else n + 1
```

`homebase/charts/studies.py` (three hunks: the import, `make()`, `Profile`; other sessions have uncommitted edits in this file, so apply by hand):

```diff
--- a/homebase/charts/studies.py
+++ b/homebase/charts/studies.py
@@ -15,6 +15,7 @@
 import re
 
 from .session import custom_anchor_key, is_rth, month_key, week_key
+from .studies_flow import NAMES as FLOW_NAMES, make_flow
 from .studies_ta import NAMES as TA_NAMES, make_ta
 
 SOURCES = ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")
@@ -253,9 +254,11 @@
     name, *args = str(key).split(":")
     if name in TA_NAMES:
         return make_ta(name, args, tick_size)
+    if name in FLOW_NAMES:
+        return make_flow(name, args)
     cls = REGISTRY.get(name)
     if cls is None:
-        raise ValueError(f"unknown study {key!r} (have {', '.join(sorted([*REGISTRY, *TA_NAMES]))}, profile)")
+        raise ValueError(f"unknown study {key!r} (have {', '.join(sorted([*REGISTRY, *TA_NAMES, *FLOW_NAMES]))}, profile)")
     if cls in (SMA, EMA):
         if len(args) > 2 or (args and not (args[0].isdecimal() and int(args[0]) in LENGTHS)):
             raise ValueError(f"bad study {key!r}: {name} takes a length and optional source "
@@ -307,17 +310,25 @@
         self.tick_size = tick_size
         self.session: str | None = None
         self.vol: dict = {}
+        self.prev_vol: dict = {}    # the session before: the prior-day ghost and lines
 
     def push(self, bar) -> None:
         if bar.session != self.session:
+            self.prev_vol = self.vol if self.session is not None else {}
             self.session, self.vol = bar.session, {}
         for k, (s, b) in bar.fp.items():
             self.vol[k] = self.vol.get(k, 0) + s + b
 
     def value(self, live=None) -> dict | None:
-        vol = self.vol
+        vol, prev = self.vol, self.prev_vol
         if live is not None:
-            vol = dict(vol) if live.session == self.session else {}
+            if live.session == self.session:
+                vol = dict(vol)
+            else:                       # the developing bar opens a new session: the finished one is the prior
+                vol, prev = {}, self.vol
             for k, (s, b) in live.fp.items():
                 vol[k] = vol.get(k, 0) + s + b
-        return profile_from(vol, self.tick_size)
+        out = profile_from(vol, self.tick_size)
+        if out is not None and prev:
+            out["prev"] = profile_from(prev, self.tick_size)
+        return out
```

`homebase/charts/hub.py` (`warm_bars`):

```diff
--- a/homebase/charts/hub.py
+++ b/homebase/charts/hub.py
@@ -34,6 +34,7 @@
 from .history import M1, History
 from .session import session_date
 from .studies import Profile, make
+from .studies_flow import NAMES as FLOW_NAMES, warm_flow
 from .studies_ta import NAMES as TA_NAMES, prime_ta, warm_ta
 from .tick import BUY, SideClassifier, Tick, from_row
 
@@ -67,6 +68,8 @@
     n = int(rest[0]) if rest and rest[0].isdecimal() else 0
     if name in TA_NAMES:
         return warm_ta(name, rest)
+    if name in FLOW_NAMES:
+        return warm_flow(name, rest)
     return {"sma": n, "vwma": n, "ema": 5 * n, "adx": 10 * n}.get(name, 0)
```

- [ ] **Step 4: Run the tests**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_studies_flow.py tests/test_charts_bars_flow.py tests/test_charts_studies.py tests/test_charts_hub.py`
Expected: PASS (6 + 7 new tests; the older study and hub tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/studies_flow.py homebase/charts/studies.py homebase/charts/hub.py tests/test_charts_studies_flow.py tests/test_charts_bars_flow.py
git commit -m "feat(charts): ddiv + tspeed studies, prior-session profile" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 3: `BookTracker`, the pure order-book episode tracker

**Files:**
- Create: `homebase/charts/bookflow.py`, `tests/test_bookflow.py`

**Interfaces:**
- Produces: `BookTracker(tick_size: float, tuning: dict | None = None)` with
  - `on_book(ts_ms, bids, offers) -> list[dict]` (`bids` / `offers` = `[[price, size], ...]` best first, at most 10),
  - `on_print(ts_ms, price, size, side) -> list[dict]` (`side` +1 = buyer lifted the ask, -1 = seller hit the bid),
  - `flush(ts_ms)` (close the seconds a quiet book never closed) and `finish(ts_ms=None)` (close every open level `faded`); each returns a list of events;
  - events: `{"k": "sample", "t": ms, "row": [t, b10, a10, imb1, imb5, imb10, micro, spread_ticks]}` once per second, and `{"k": "ep", "id", "s": "b"|"a", "p": price, "t0": ms, "t1": ms | None, "pk": peak size, "r": ratio to the median when it opened, "tr": contracts traded at the level, "end": "open"|"traded"|"pulled"|"faded", "ab": ms it was flagged absorbing | None, "d0": ticks from the touch when it opened}` when an episode is first worth showing (>= 3 s old), when it is flagged as absorbing and when it ends (the same `id` each time: a consumer merges by id);
  - module constants `LEVELS = 10`, `OPEN_RATIO = 3.0`, `CLOSE_RATIO = 2.0`, `MIN_MEDIAN_SAMPLES = 10`, and `TUNING` (the first-guess numbers: `min_episode_ms 3000`, `pull_frac 0.8`, `pull_ms 2000`, `pull_traded_frac 0.2`, `pull_ticks 4`, `traded_frac 0.6`, `abs_mult 2.0`, `abs_median_mult 8.0`, `abs_min_ratio 4.0`, `abs_hold_frac 0.5`, `abs_through_ticks 1`).

Definitions (spec 4.1, each a first guess the owner reviews on real days): an episode is a price level whose size is >= 3x the trailing 60 s median level (both sides pooled, top 10 each) and stays one until it is under 2x; it ends `traded` if prints at its price reached >= 60% of its peak (or price traded through it), `pulled` if >= 80% of its size vanished within 2 s while prints at it were < 20% of what was removed and the touch was within 4 ticks, otherwise `faded`. It is flagged `absorbing` (once) when the contracts traded into it are >= max(2x the size it opened with, 8x the median level), it opened at >= 4x the median, it still shows >= 50% of its opening size and price has not traded through it by more than 1 tick. One Hz samples carry the imbalance at 1 / 5 / 10 levels and the microprice, so the same tracker feeds the imbalance-over-time and depth-pane series.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bookflow.py`:

```python
from homebase.charts.bookflow import BookTracker, BUY, SELL, TUNING

TICK = 0.25

def lv(px0, sizes, step):
    return [[px0 + i * step, s] for i, s in enumerate(sizes)]

def book(bid=100.0, size=10, big=None):
    """10 bids below `bid`, 10 offers above bid+0.25; every level `size`; big = {('b'|'a', n_ticks_from_touch): size}"""
    big = big or {}
    b = [[bid - i * TICK, big.get(('b', i), size)] for i in range(10)]
    a = [[bid + TICK + i * TICK, big.get(('a', i), size)] for i in range(10)]
    return b, a

def warm(tr, secs=12, t0=0):
    out = []
    for s in range(secs):
        out += tr.on_book(t0 + s * 1000, *book())
    return out

def eps(events): return [e for e in events if e["k"] == "ep"]
def samples(events): return [e for e in events if e["k"] == "sample"]

def test_samples_once_per_second_last_book_wins():
    tr = BookTracker(TICK)
    ev = tr.on_book(1000, *book(size=10)) + tr.on_book(1500, *book(size=30))
    assert ev == []
    ev = tr.on_book(2100, *book(size=10))
    s = samples(ev)
    assert len(s) == 1 and s[0]["t"] == 1000
    t, b10, a10, i1, i5, i10, micro, spread = s[0]["row"]
    assert (t, b10, a10) == (1000, 300.0, 300.0)
    assert i1 == i5 == i10 == 0.0 and spread == 1 and micro == 100.125

def test_imbalance_signs_and_micro_leans_to_the_thin_side():
    tr = BookTracker(TICK)
    b, a = book()
    b[0][1] = 50                       # bid heavy at the touch
    tr.on_book(1000, b, a)
    row = samples(tr.flush(2000))[0]["row"]
    assert row[3] > 0 and row[4] > 0 and row[5] > 0
    assert row[6] > 100.125            # microprice sits nearer the thin offer

def test_no_episode_before_a_median_exists():
    tr = BookTracker(TICK)
    ev = []
    for s in range(5):
        ev += tr.on_book(s * 1000, *book(big={('b', 3): 200}))
    assert eps(ev) == []

def test_big_level_opens_after_two_seconds_and_traded_when_consumed():
    tr = BookTracker(TICK)
    ev = warm(tr, 12)
    t = 12_000
    big_px = 100.0 - 3 * TICK
    ev += tr.on_book(t, *book(big={('b', 3): 200}))             # level appears
    assert eps(ev) == []
    ev += tr.on_book(t + 3500, *book(big={('b', 3): 200}))      # old enough: shown
    e = eps(ev)
    assert len(e) == 1 and e[0]["end"] == "open" and e[0]["p"] == big_px and e[0]["s"] == "b"
    ev = tr.on_print(t + 4000, big_px, 150, SELL)               # sellers hit it
    ev += tr.on_book(t + 4250, *book(big={('b', 3): 40}))
    ev += tr.on_book(t + 4500, *book())                          # gone
    e = eps(ev)
    assert e and e[-1]["end"] == "traded" and e[-1]["tr"] == 150 and e[-1]["t1"] == t + 4500

def test_pulled_when_it_vanishes_with_price_close_and_no_trades():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    tr.on_book(t, *book(big={('b', 1): 300}))                    # one tick under the touch
    tr.on_book(t + 3500, *book(big={('b', 1): 300}))
    ev = tr.on_book(t + 4000, *book())
    e = eps(ev)
    assert e and e[-1]["end"] == "pulled"

def test_far_level_that_drifts_off_is_faded_not_pulled():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    tr.on_book(t, *book(big={('b', 8): 300}))                    # 8 ticks away
    tr.on_book(t + 3500, *book(big={('b', 8): 300}))
    ev = tr.on_book(t + 4000, *book())
    assert eps(ev)[-1]["end"] == "faded"

def test_short_lived_level_is_never_emitted():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev = tr.on_book(12_000, *book(big={('b', 2): 300}))
    ev += tr.on_book(13_000, *book())
    assert eps(ev) == []

def test_absorption_flag_when_volume_is_eaten_but_the_level_holds():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    big_px = 100.0 - 1 * TICK
    tr.on_book(t, *book(big={('b', 1): 100}))
    ev = tr.on_book(t + 3500, *book(big={('b', 1): 100}))
    assert eps(ev)[-1]["ab"] is None
    ev = tr.on_print(t + 4000, big_px, 150, SELL)                # 1.5x shown, not yet 2x
    assert [e for e in eps(ev) if e["ab"]] == []
    ev = tr.on_print(t + 4100, big_px, 100, SELL)                # 250 traded >= 2 x 100 and >= 8 x median; still shows size
    flagged = [e for e in eps(ev) if e["ab"] is not None]
    assert flagged and flagged[0]["ab"] == t + 4100 and flagged[0]["end"] == "open"

def test_no_absorption_when_price_trades_through():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    tr.on_book(t, *book(big={('b', 1): 100}))
    tr.on_book(t + 3500, *book(big={('b', 1): 100}))
    tr.on_print(t + 3600, 100.0 - 3 * TICK, 5, SELL)             # printed 2 ticks beyond
    ev = tr.on_print(t + 4000, 100.0 - TICK, 300, SELL)
    assert [e for e in eps(ev) if e["ab"]] == []

def test_finish_closes_open_levels_and_commits_the_last_second():
    tr = BookTracker(TICK)
    warm(tr, 12)
    tr.on_book(12_000, *book(big={('b', 1): 300}))
    tr.on_book(15_000, *book(big={('b', 1): 300}))
    ev = tr.finish()
    assert samples(ev) and eps(ev)[-1]["end"] == "faded"

def test_deterministic_same_input_same_output():
    def run():
        tr = BookTracker(TICK); out = warm(tr, 12)
        out += tr.on_book(12_000, *book(big={('a', 2): 250}))
        out += tr.on_print(14_000, 100.0 + TICK + 2 * TICK, 90, BUY)
        out += tr.on_book(16_000, *book(big={('a', 2): 250}))
        out += tr.finish()
        return out
    assert run() == run()


def test_an_empty_or_one_sided_book_line_never_breaks_the_tracker():
    tr = BookTracker(TICK)
    out = warm(tr, 12)
    out += tr.on_book(12_000, [], [])                                  # nothing resting at all
    out += tr.on_book(13_000, [[100.0, 10]], [])                       # one side only
    out += tr.on_book(14_000, *book())
    out += tr.on_print(14_100, 100.0, 5, SELL)
    out += tr.flush(20_000)
    rows = {e["t"]: e["row"] for e in out if e["k"] == "sample"}
    assert rows[12_000][6] is None and rows[12_000][7] is None         # microprice and spread: none
    assert rows[13_000][6] is None
    assert rows[14_000][6] is not None


def test_a_print_before_any_book_is_harmless():
    tr = BookTracker(TICK)
    assert tr.on_print(1000, 100.0, 5, BUY) == []
    out = tr.on_book(2000, *book()) + tr.flush(4000)
    ts = [e["row"][0] for e in out if e["k"] == "sample"]
    assert ts and ts == sorted(set(ts))                                # ascending, one row a second
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_bookflow.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'homebase.charts.bookflow'`).

- [ ] **Step 3: Implement**

Create `homebase/charts/bookflow.py`:

```python
"""Level 2 book tracker for the charts: one resting order level's life, and a once-a-second sample of the book.

Pure and deterministic: no clock, no I/O. Input is the same stream in every place it runs (the live feed's
recorded lines, the recorded depth files replayed, a test): `on_book(ts_ms, bids, offers)` for each recorded
book line (top 10 levels each side, best first) and `on_print(ts_ms, price, size, side)` for each trade
(side +1 = the buyer lifted the ask, -1 = the seller hit the bid). Feed them in time order, a book before a
print that carries the same stamp.

Output is a list of plain dicts (JSON-ready), from every call:
  {"k": "sample", "t": ms, "row": [t, b10, a10, imb1, imb5, imb10, micro, spread_ticks]}   once per second
  {"k": "ep", ...episode...}   an order level's life: when it is first worth showing (>= MIN_EPISODE_MS old),
                               when it is flagged as absorbing, and when it ends
An episode is "big" when its level shows >= OPEN_RATIO x the median level size of the last MEDIAN_WINDOW_S
seconds of books (both sides pooled, top 10 each), and stays one until it falls under CLOSE_RATIO x.

Every number that decides a verdict is in TUNING: first-guess definitions the owner reviews on real days.
"""
from __future__ import annotations

from collections import deque

LEVELS = 10
OPEN_RATIO = 3.0
CLOSE_RATIO = 2.0
MEDIAN_WINDOW_S = 60
MIN_MEDIAN_SAMPLES = 10          # no episode opens before this many seconds of books
SAMPLE_MS = 1000
BUY, SELL = 1, -1

TUNING = {
    "min_episode_ms": 3000,        # an order level younger than this when it ends is noise, never emitted
    "pull_frac": 0.80,             # pulled: the size fell by >= this fraction ...
    "pull_ms": 2000,               # ... within this long ...
    "pull_traded_frac": 0.20,      # ... while prints at the level were < this fraction of what was removed ...
    "pull_ticks": 4,               # ... and the touch was within this many ticks of the level
    "traded_frac": 0.60,           # traded: prints at the level reached >= this fraction of the peak size
    "abs_mult": 2.0,               # absorbing: traded >= this x the size shown when it opened ...
    "abs_median_mult": 8.0,        # ... and >= this x the median level size ...
    "abs_min_ratio": 4.0,          # ... and the level was at least this x the median to begin with ...
    "abs_hold_frac": 0.50,         # ... and the level still shows >= this fraction of that size ...
    "abs_through_ticks": 1,        # ... and price never printed beyond it by more than this many ticks
}


def _sum(rows, n) -> float:
    return float(sum(r[1] for r in rows[:n]))


def _imb(bids, offers, n) -> float:
    b, a = _sum(bids, n), _sum(offers, n)
    return round((b - a) / (b + a), 4) if b + a > 0 else 0.0


def _median(xs: list) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return float(s[m]) if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


class _Ep:
    __slots__ = ("side", "px", "idx", "t0", "start", "size", "peak", "ratio", "traded", "beyond", "dist0",
                 "dist", "sizes", "prints", "abs_t", "sent", "t1", "end")

    def __init__(self, side, px, idx, t0, size, ratio, dist):
        self.side, self.px, self.idx, self.t0 = side, px, idx, t0
        self.start = self.size = self.peak = size
        self.ratio = ratio
        self.traded = 0
        self.beyond = 0
        self.dist0 = self.dist = dist
        self.sizes = deque([(t0, size)])      # (ts, size) of the last pull window
        self.prints = deque()                 # (ts, size) traded at the level within the last pull window
        self.abs_t = None
        self.sent = False
        self.t1 = None
        self.end = "open"

    @property
    def id(self) -> str:
        return f"{self.side}{self.idx}_{self.t0}"

    def wire(self) -> dict:
        return {"k": "ep", "id": self.id, "s": self.side, "p": self.px, "t0": self.t0, "t1": self.t1,
                "pk": self.peak, "r": round(self.ratio, 2), "tr": self.traded, "end": self.end,
                "ab": self.abs_t, "d0": self.dist0}


class BookTracker:
    def __init__(self, tick_size: float, tuning: dict | None = None):
        self.tick = float(tick_size)
        self.tune = {**TUNING, **(tuning or {})}
        self._sec = None              # the second (ms) of the pending sample
        self._last = None             # the last (bids, offers) of that second
        self._win: deque = deque()    # (second, [sizes]) of committed samples
        self._med = 0.0
        self._eps: dict = {}          # (side, tick index) -> _Ep
        self._ts = None               # the newest stamp seen

    # ---- the stream

    def on_book(self, ts: int, bids: list, offers: list) -> list:
        bids, offers = [list(r) for r in bids[:LEVELS]], [list(r) for r in offers[:LEVELS]]
        out = self._roll(ts)
        self._sec, self._last, self._ts = ts - ts % SAMPLE_MS, (bids, offers), ts
        out += self._update(ts, bids, offers)
        return out

    def on_print(self, ts: int, price: float, size: int, side: int) -> list:
        out = self._roll(ts)
        self._ts = ts if self._ts is None else max(self._ts, ts)
        i = self._idx(price)
        for (s, k), ep in list(self._eps.items()):
            if k == i and ((s == "b" and side == SELL) or (s == "a" and side == BUY)):
                ep.traded += size
                ep.prints.append((ts, size))
            elif (s == "b" and side == SELL and i < k) or (s == "a" and side == BUY and i > k):
                ep.beyond = max(ep.beyond, abs(i - k))
            else:
                continue
            out += self._after(ep, ts)
        return out

    def flush(self, ts: int) -> list:
        """Commit the samples of every second that ended before ts (the live loop calls it once a second)."""
        return self._roll(ts)

    def finish(self, ts: int | None = None) -> list:
        """The recording ended (a finished day): commit the pending sample and end every open level as faded."""
        out = self._roll((self._sec or 0) + SAMPLE_MS) if self._sec is not None else []
        t = self._ts if ts is None else ts
        for key, ep in list(self._eps.items()):
            out += self._close(ep, t, "faded")
            del self._eps[key]
        return out

    # ---- the samples

    def _idx(self, px: float) -> int:
        return round(px / self.tick)

    def _roll(self, ts: int) -> list:
        if self._sec is None or ts < self._sec + SAMPLE_MS:
            return []
        bids, offers = self._last
        sec = self._sec
        self._sec = self._last = None
        micro = None
        crossed = bool(bids and offers and bids[0][0] >= offers[0][0])
        if bids and offers and not crossed:
            bs, as_ = bids[0][1], offers[0][1]
            if bs + as_ > 0:
                micro = round((bids[0][0] * as_ + offers[0][0] * bs) / (bs + as_), 6)
        spread = round((offers[0][0] - bids[0][0]) / self.tick) if bids and offers and not crossed else None
        row = [sec, _sum(bids, LEVELS), _sum(offers, LEVELS), _imb(bids, offers, 1), _imb(bids, offers, 5),
               _imb(bids, offers, LEVELS), micro, spread]
        self._win.append((sec, [r[1] for r in bids] + [r[1] for r in offers]))
        while self._win and self._win[0][0] <= sec - MEDIAN_WINDOW_S * SAMPLE_MS:
            self._win.popleft()
        self._med = _median([x for _, v in self._win for x in v]) if len(self._win) >= MIN_MEDIAN_SAMPLES else 0.0
        return [{"k": "sample", "t": sec, "row": row}]

    # ---- the order levels

    def _update(self, ts: int, bids: list, offers: list) -> list:
        out, med, tick = [], self._med, self.tick
        present = {}
        for side, rows in (("b", bids), ("a", offers)):
            for px, sz in rows:
                present[(side, self._idx(px))] = (px, sz)
        best_bid = bids[0][0] if bids else None
        best_ask = offers[0][0] if offers else None
        for key, ep in list(self._eps.items()):
            cur = present.get(key)
            size = cur[1] if cur else 0
            ratio = size / med if med > 0 else 0.0
            if size > 0 and ratio >= CLOSE_RATIO:
                ep.size = size
                if size > ep.peak:
                    ep.peak = size
                ep.ratio = max(ep.ratio, ratio)
                ep.sizes.append((ts, size))
                touch = best_bid if ep.side == "b" else best_ask
                if touch is not None:
                    d = (touch - ep.px) / tick if ep.side == "b" else (ep.px - touch) / tick
                    ep.dist = max(0.0, round(d, 2))
                self._trim(ep, ts)
                out += self._after(ep, ts)
            else:
                ep.size = size
                end = self._classify(ep, ts, size)
                out += self._close(ep, ts, end)
                del self._eps[key]
        if med > 0:
            for key, (px, sz) in present.items():
                if key in self._eps or sz < OPEN_RATIO * med:
                    continue
                side = key[0]
                touch = best_bid if side == "b" else best_ask
                d = 0.0 if touch is None else max(0.0, round(((touch - px) if side == "b" else (px - touch)) / tick, 2))
                ep = self._eps[key] = _Ep(side, px, key[1], ts, sz, sz / med, d)
        return out

    def _trim(self, ep: _Ep, ts: int) -> None:
        cut = ts - self.tune["pull_ms"]
        while len(ep.sizes) > 1 and ep.sizes[0][0] < cut:
            ep.sizes.popleft()
        while ep.prints and ep.prints[0][0] < cut:
            ep.prints.popleft()

    def _classify(self, ep: _Ep, ts: int, size_now: float) -> str:
        t = self.tune
        if ep.traded >= t["traded_frac"] * ep.peak or ep.beyond >= 1:
            return "traded"
        self._trim(ep, ts)
        ref = max(s for _, s in ep.sizes)
        removed = ref - size_now
        recent = sum(s for _, s in ep.prints)
        if (ref > 0 and removed >= t["pull_frac"] * ref and recent < t["pull_traded_frac"] * removed
                and ep.dist <= t["pull_ticks"]):
            return "pulled"
        return "faded"

    def _flag(self, ep: _Ep, ts: int) -> bool:
        """True the first time the level qualifies as absorbing (and never again)."""
        t = self.tune
        if ep.abs_t is not None or ep.beyond > t["abs_through_ticks"]:
            return False
        need = max(t["abs_mult"] * ep.start, t["abs_median_mult"] * self._med)
        if ep.ratio >= t["abs_min_ratio"] and ep.traded >= need and ep.size >= t["abs_hold_frac"] * ep.start:
            ep.abs_t = ts
            return True
        return False

    def _after(self, ep: _Ep, ts: int) -> list:
        """An open level changed: it is sent the first time it is old enough to show, and again when flagged."""
        flagged = self._flag(ep, ts)
        if ts - ep.t0 >= self.tune["min_episode_ms"] and (not ep.sent or flagged):
            ep.sent = True
            return [ep.wire()]
        return []

    def _close(self, ep: _Ep, ts: int, end: str) -> list:
        ep.t1, ep.end = ts, end
        if ts - ep.t0 < self.tune["min_episode_ms"] and not ep.sent:
            return []
        ep.sent = True
        return [ep.wire()]
```

- [ ] **Step 4: Run the tests**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_bookflow.py`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/bookflow.py tests/test_bookflow.py
git commit -m "feat(charts): BookTracker - order-level episodes and 1 Hz book samples (pure)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 4: `BookHistory` and `BookPool`, the recorded days replayed

**Files:**
- Create: `homebase/charts/bookhist.py`, `tests/test_bookhist.py`
- Modify: `homebase/charts/depthgrid.py` (`HistoryPool._run`, so `BookPool` shares the busy / pause / respawn handling)

**Interfaces:**
- Consumes: Task 3's `BookTracker`; `depthgrid.HistoryPool`, `Busy`, `Paused`, `BUSY`, `_members`, `_parse_member`, `_worker_reason`, `_OFFSET_MS`; `store.TickStore(base).load(root, date).ticks`; `session.session_range_ms`.
- Produces: `bookhist.MAX_SPAN_MS = 48 * 3_600_000`; `BookHistory(depth_base, tick_base, quiet=..., tick_of=..., now=...)` with `window(root, frm_ms, to_ms, now_ms) -> bytes` (JSON `{"tick": float, "step": ms, "t0", "t1", "samples": [[t, b10, a10, imb1, imb5, imb10, micro, spread], ...], "episodes": [ep dict as in Task 3]}`; `to` is clamped to now; samples are averaged to at most 20,000 points; a root or day with no recorded depth gives empty lists, never an error; raises `Paused` inside the pause windows); `child_book(...)` (the worker entry point) and `BookPool(depth_base, tick_base, executor_factory=None)` with `async window(root, frm, to, now_ms, offset_ms=0.0) -> bytes` (raises `Busy` while one runs).

A day's recorded lines are replayed through a `BookTracker` together with that day's tick archive, with the book before a print of the same stamp. A finished day is cached in memory (4 days); today is re-read at most every 20 s.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bookhist.py`:

```python
import gzip, json, datetime as dt
from pathlib import Path
from homebase.charts import bookhist as bh

TICK = 0.25
D = dt.date(2026, 10, 7)
T0 = int(dt.datetime(2026, 10, 7, 14, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)   # 10:00 ET

def levels(bid, big=None):
    big = big or {}
    b = [[bid - i * TICK, big.get(('b', i), 10)] for i in range(10)]
    a = [[bid + TICK + i * TICK, big.get(('a', i), 10)] for i in range(10)]
    return b, a

def write_depth(base: Path, lines):
    p = base / "NQ" / "2026" / f"{D.isoformat()}_NQZ6.depth.jsonl.gz"
    p.parent.mkdir(parents=True)
    body = "".join(json.dumps({"t": t, "b": b, "a": a}) + "\n" for t, b, a in lines)
    p.write_bytes(gzip.compress(body.encode()))
    return p

def write_ticks(base: Path, rows):
    p = base / "NQ" / "2026" / f"{D.isoformat()}_NQZ6.csv.gz"
    p.parent.mkdir(parents=True)
    body = "ts_ms,price,size,bid,ask,id\n" + "".join(f"{t},{px},{sz},{bid},{ask},{i}\n" for i, (t, px, sz, bid, ask) in enumerate(rows, 1))
    p.write_bytes(gzip.compress(body.encode()))

def scenario(tmp_path):
    lines = []
    for s in range(60):
        big = {('b', 2): 300} if 20 <= s < 30 else None
        lines.append((T0 + s * 1000, *levels(100.0, big)))
    write_depth(tmp_path / "depth", lines)
    # sellers hit the 99.50 bid (the big level, 300 shown) at 25 s: 640 contracts over 4 prints
    ticks = [(T0 + 25_000 + k * 100, 99.5, 160, 99.5, 99.75) for k in range(4)]
    write_ticks(tmp_path / "ticks", ticks)
    return tmp_path / "depth", tmp_path / "ticks"

def test_window_has_samples_and_the_episode_with_its_trades(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    out = json.loads(h.window("NQ", T0, T0 + 60_000, T0 + 3_600_000))
    assert len(out["samples"]) == 60 and out["step"] == 1000
    ep = [e for e in out["episodes"] if e["p"] == 99.5]
    assert len(ep) == 1 and ep[0]["s"] == "b" and ep[0]["tr"] == 640 and ep[0]["end"] == "traded"
    assert ep[0]["ab"] is not None            # 640 traded >= 2 x the 300 shown, level still stands at flag time

def test_window_cuts_samples_and_keeps_overlapping_episodes(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    out = json.loads(h.window("NQ", T0 + 40_000, T0 + 50_000, T0 + 3_600_000))
    assert len(out["samples"]) == 10
    assert out["episodes"] == []              # the episode ended at 30 s, before this window

def test_far_future_is_clamped_to_now(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, tick_of=lambda r: TICK)
    out = json.loads(h.window("NQ", T0, T0 + 10 * 3_600_000, T0 + 30_000))
    assert out["t1"] == T0 + 30_000 and len(out["samples"]) == 30

def test_paused_window_refuses_to_decode(tmp_path):
    d, t = scenario(tmp_path)
    h = bh.BookHistory(d, t, quiet=lambda: "paused for the 9:30 window", tick_of=lambda r: TICK)
    try:
        h.window("NQ", T0, T0 + 60_000, T0 + 3_600_000)
    except bh.Paused as e:
        assert "9:30" in str(e)
    else:
        raise AssertionError("expected Paused")

def test_average_buckets():
    rows = [[0, 10, 20, .1, .1, .1, 100.0, 1], [1000, 30, 40, .3, .3, .3, 102.0, 3], [2000, 50, 60, 0, 0, 0, None, None]]
    out = bh._average(rows, 2000)
    assert out[0] == [0, 20.0, 30.0, 0.2, 0.2, 0.2, 101.0, 2.0]
    assert out[1] == [2000, 50.0, 60.0, 0.0, 0.0, 0.0, None, None]
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_bookhist.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'homebase.charts.bookhist'`).

- [ ] **Step 3: Implement**

`homebase/charts/depthgrid.py` (extract `_run`; `grid()` calls it):

```diff
--- a/homebase/charts/depthgrid.py
+++ b/homebase/charts/depthgrid.py
@@ -301,6 +301,9 @@
         self._busy = False
 
     async def grid(self, root: str, frm: int, to: int, cols: int, now_ms: int, offset_ms: float = 0.0) -> bytes:
+        return await self._run(child_grid, self.base, root, frm, to, cols, now_ms, offset_ms)
+
+    async def _run(self, fn, *args) -> bytes:
         if self._busy:
             raise Busy(BUSY)
         self._busy = True
@@ -309,7 +312,7 @@
                 self._ex = self._factory()
             ex = self._ex
             try:
-                fut = ex.submit(child_grid, self.base, root, frm, to, cols, now_ms, offset_ms)
+                fut = ex.submit(fn, *args)
                 return await asyncio.wrap_future(fut)
             except BrokenProcessPool:
                 if self._ex is ex:
```

Create `homebase/charts/bookhist.py`:

```python
"""Book history for the charts: the recorded depth files + the tick archive, replayed through BookTracker.

GET /api/book/history answers from here. Like depthgrid.py it never runs in the chart service's process:
BookPool hands every request to ONE spawned worker (child_book), one request at a time (a second one while it
is busy is Busy, 503, never queued). Read-only: nothing here writes anywhere.

A session is replayed whole (the tracker needs the day's start for its trailing median), then cached by the
depth file's (inode, size, mtime). A file still growing (today's) is replayed again at most every
TODAY_TTL_S. The answer is the window cut out of that: samples averaged to `step`, and the episodes that
overlap it.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from ..contracts import tick_size as contract_tick_size
from .bookflow import BookTracker
from .depthgrid import (BUSY, Busy, DepthHistory, HistoryPool, Paused, _members, _parse_member,  # noqa: F401
                        _worker_reason, _OFFSET_MS)
from .session import session_range_ms
from .store import TickStore

MAX_SPAN_MS = 48 * 3_600_000       # a window is at most two sessions
MAX_POINTS = 20_000                # samples per response, after averaging
MAX_EPISODES = 6_000
TODAY_TTL_S = 20.0
CACHE_DAYS = 4


def depth_lines(path: Path):
    """(ts_ms, bids, offers) of each complete line of a depth file, in time order."""
    out = []
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return out
    for text, _end in _members(raw):
        for v in _parse_member(text):
            t, b, a = v.get("t"), v.get("b"), v.get("a")
            if isinstance(t, (int, float)) and not isinstance(t, bool) and isinstance(b, list) and isinstance(a, list):
                out.append((int(t), b, a))
    out.sort(key=lambda x: x[0])
    return out


def replay_day(lines: list, ticks: list, tick_size: float, finished: bool) -> tuple[list, dict]:
    """(sample rows, {episode id: episode}) of one session: the lines and the prints in time order, a book
    before a print with the same stamp."""
    tr = BookTracker(tick_size)
    samples: list = []
    eps: dict = {}

    def take(evs):
        for e in evs:
            if e["k"] == "sample":
                samples.append(e["row"])
            else:
                eps[e["id"]] = {k: v for k, v in e.items() if k != "k"}

    i = j = 0
    n, m = len(lines), len(ticks)
    while i < n or j < m:
        if j >= m or (i < n and lines[i][0] <= ticks[j].ts_ms):
            t, b, a = lines[i]
            i += 1
            take(tr.on_book(t, b, a))
        else:
            tk = ticks[j]
            j += 1
            take(tr.on_print(tk.ts_ms, tk.price, tk.size, tk.side))
    take(tr.finish() if finished else tr.flush(10 ** 18))
    return samples, eps


def _average(rows: list, step: int) -> list:
    """Rows [t, b10, a10, i1, i5, i10, micro, spread] averaged inside `step` ms buckets (the bucket's start
    as t); micro and spread are averaged over the rows that have them."""
    if step <= 1000:
        return rows
    out, cur, acc = [], None, []

    def put():
        if not acc:
            return
        cols = list(zip(*acc))
        mean = lambda xs: (lambda v: round(sum(v) / len(v), 4) if v else None)([x for x in xs if x is not None])
        out.append([cur, *[mean(c) for c in cols[1:]]])

    for r in rows:
        b = r[0] - r[0] % step
        if b != cur:
            put()
            cur, acc = b, []
        acc.append(r)
    put()
    return out


class BookHistory:
    def __init__(self, depth_base: Path, tick_base: Path, quiet=lambda: None, tick_of=contract_tick_size,
                 now=time.time):
        self.depth = DepthHistory(depth_base, tick_of)
        self.ticks = TickStore(tick_base)
        self.tick_of = tick_of
        self.quiet = quiet
        self._now = now
        self._cache: OrderedDict = OrderedDict()   # path -> (stamp, computed_at, samples, episodes)

    def _day(self, root: str, path: Path, d: dt.date, tick: float, now_ms: int):
        st = path.stat()
        stamp = (st.st_ino, st.st_size, st.st_mtime_ns)
        hit = self._cache.get(path)
        now_s = self._now()
        if hit is not None and (hit[0] == stamp or now_s - hit[1] < TODAY_TTL_S):
            self._cache.move_to_end(path)
            return hit[2], hit[3]
        why = self.quiet()
        if why:
            raise Paused(why)
        s = self.ticks.load(root, d)
        ticks = s.ticks if s is not None else []
        finished = session_range_ms(d, root)[1] <= now_ms
        samples, eps = replay_day(depth_lines(path), ticks, tick, finished)
        self._cache[path] = (stamp, now_s, samples, eps)
        while len(self._cache) > CACHE_DAYS:
            self._cache.popitem(last=False)
        return samples, eps

    def window(self, root: str, frm: int, to: int, now_ms: int) -> bytes:
        if not root.isalnum():
            raise ValueError(f"bad root {root!r}")
        frm, to = int(frm), int(to)
        if to <= frm:
            raise ValueError("to_ms must be after from_ms")
        if to - frm > MAX_SPAN_MS:
            raise ValueError(f"at most {MAX_SPAN_MS // 3_600_000} h per request")
        to = min(to, int(now_ms))
        tick = float(self.tick_of(root))
        rows: list = []
        eps: dict = {}
        if to > frm:
            for path in self.depth.files(root, frm, to):
                d = dt.date.fromisoformat(path.name[:10])
                s, e = self._day(root, path, d, tick, now_ms)
                rows.extend(r for r in s if frm <= r[0] < to)
                for k, v in e.items():
                    if v["t0"] < to and (v["t1"] is None or v["t1"] >= frm):
                        eps[k] = v
        raw = -(-(to - frm) // MAX_POINTS)
        step = max(1000, -(-raw // 1000) * 1000)           # whole seconds, at most MAX_POINTS samples
        rows = _average(rows, step)
        out = sorted(eps.values(), key=lambda v: v["t0"])
        if len(out) > MAX_EPISODES:
            out = sorted(sorted(out, key=lambda v: -v["r"])[:MAX_EPISODES], key=lambda v: v["t0"])
        return json.dumps({"tick": tick, "step": step, "t0": frm, "t1": to, "samples": rows, "episodes": out},
                          separators=(",", ":")).encode()


# ------------------------------------------------------------------ the worker process

_BOOKS: dict[tuple, BookHistory] = {}    # (in the worker) (depth base, tick base) -> its BookHistory and cache


def child_book(depth_base: str, tick_base: str, root: str, frm: int, to: int, now_ms: int, offset_ms: float) -> bytes:
    """(the worker) BookHistory.window with the worker's own cache; the paused windows by the service's clock."""
    _OFFSET_MS[0] = offset_ms
    key = (depth_base, tick_base)
    h = _BOOKS.get(key)
    if h is None:
        h = _BOOKS[key] = BookHistory(Path(depth_base), Path(tick_base), quiet=_worker_reason)
    return h.window(root, frm, to, now_ms)


class BookPool(HistoryPool):
    """(the service) HistoryPool's one worker, one request at a time, Busy while it is on another, for the book."""

    def __init__(self, depth_base: Path, tick_base: Path, executor_factory=None):
        super().__init__(depth_base, *([executor_factory] if executor_factory else []))
        self.tick_base = str(tick_base)

    async def window(self, root: str, frm: int, to: int, now_ms: int, offset_ms: float = 0.0) -> bytes:
        return await self._run(child_book, self.base, self.tick_base, root, frm, to, now_ms, offset_ms)
```

- [ ] **Step 4: Run the tests**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_bookhist.py tests/test_charts_depthgrid.py`
Expected: PASS (5 new tests; the depth history tests unchanged). If `tests/test_charts_depthgrid.py` is named differently, run `ls tests | grep depth` and use the file that tests `HistoryPool`.

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/bookhist.py homebase/charts/depthgrid.py tests/test_bookhist.py
git commit -m "feat(charts): BookHistory / BookPool - recorded depth + ticks replayed through the BookTracker" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 5: `BookLive` and the depth tap

**Files:**
- Create: `homebase/charts/booklive.py`, `tests/test_booklive.py`, `tests/test_charts_depth_tap.py`
- Modify: `homebase/charts/depth.py` (`Depth.tap`)

**Interfaces:**
- Consumes: Task 3's `BookTracker`, Task 4's `replay_day` (the equality test), `tick.Tick`.
- Produces: `Depth.tap: Callable[[str, int, list, list], None] | None`, called with `(root, ts_ms, bids, offers)` for the exact lines the recorder would write (top `REC_LEVELS`, on change, at most 4 a second), for a recorded root and for any root a page is showing; `BookLive(tick_of=contract_tick_size, log=None)` with `message(root, reset=True) -> {"type": "bookflow", "root", "reset", "samples", "episodes"}`, `view(key, root, send, room)` (greets the page with the recent 900 samples / 400 episodes and `reset: true`), `unview(key)`, `drop_conn(conn)`, `on_book(root, ts, bids, offers)`, `on_tick(root, tk)`, `flush(now_ms)`. It never raises (a failure is logged and the feed goes on). A page that has no room is resynced to the latest state (`PAGE_QUEUE_MAX = 8` messages), the same way the depth ladder is.

**Equality (the point of the tap):** live and history see the same lines, so the live state after a day equals the history replay of that day's recorded file line for line (first test in `test_booklive.py`). The 18:00 ET session roll closes the old tracker's open levels `faded` and starts a new one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_booklive.py`:

```python
"""BookLive: the live feeds' tracker. Synthetic books and prints only; nothing reads ~/futures_depth."""
from __future__ import annotations

import datetime as dt

from homebase.charts.bookhist import replay_day
from homebase.charts.booklive import RECENT_SAMPLES, BookLive
from homebase.charts.tick import Tick

TICK = 0.25
T0 = int(dt.datetime(2026, 10, 7, 14, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)   # 10:00 ET


def levels(bid, big=None):
    big = big or {}
    return ([[bid - i * TICK, big.get(("b", i), 10)] for i in range(10)],
            [[bid + TICK + i * TICK, big.get(("a", i), 10)] for i in range(10)])


def scenario():
    lines = []
    for s in range(60):
        big = {("b", 2): 300} if 20 <= s < 30 else None
        lines.append((T0 + s * 1000, *levels(100.0, big)))
    ticks = [Tick(T0 + 25_000 + k * 100, 99.5, 160, -1) for k in range(4)]
    return lines, ticks


class Page:
    def __init__(self):
        self.got, self.open = [], True

    def send(self, m):
        self.got.append(m)

    def room(self):
        return self.open


def feed(live, lines, ticks, root="NQ"):
    """Books and prints in time order, a book before a print with the same stamp: the order replay_day uses."""
    i = j = 0
    while i < len(lines) or j < len(ticks):
        if j >= len(ticks) or (i < len(lines) and lines[i][0] <= ticks[j].ts_ms):
            t, b, a = lines[i]
            i += 1
            live.on_book(root, t, b, a)
        else:
            live.on_tick(root, ticks[j])
            j += 1


def collect(page):
    rows, eps = [], {}
    for m in page.got:
        if m["type"] != "bookflow":
            continue
        rows += m["samples"]
        for e in m["episodes"]:
            eps[e["id"]] = e
    return rows, eps


def test_live_equals_the_history_replay_line_for_line():
    lines, ticks = scenario()
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    feed(live, lines, ticks)
    live.flush(T0 + 10 ** 9)                       # the pump's flush after the last second
    rows, eps = collect(page)
    want_rows, want_eps = replay_day(lines, ticks, TICK, finished=False)
    assert rows == want_rows
    assert eps == want_eps
    assert any(e["end"] == "traded" and e["ab"] is not None for e in eps.values())


def test_a_page_is_greeted_with_the_recent_state_and_reset():
    lines, ticks = scenario()
    live = BookLive(lambda r: TICK)
    feed(live, lines, ticks)                       # nobody watching yet
    page = Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    hello = page.got[0]
    assert hello["type"] == "bookflow" and hello["reset"] is True and hello["root"] == "NQ"
    assert len(hello["samples"]) >= 50 and len(hello["samples"]) <= RECENT_SAMPLES
    assert any(e["s"] == "b" and e["p"] == 99.5 for e in hello["episodes"])


def test_two_charts_of_one_page_share_one_stream_and_unview_detaches():
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    live.view((page, "c2"), "NQ", page.send, page.room)
    lines, ticks = scenario()
    feed(live, lines[:15], [])
    n = len([m for m in page.got if m["samples"]])
    live.unview((page, "c1"))
    feed(live, lines[15:20], [])
    assert len([m for m in page.got if m["samples"]]) > n          # c2 still attached: still receiving
    live.drop_conn(page)
    before = len(page.got)
    feed(live, lines[20:25], [])
    assert len(page.got) == before


def test_session_roll_finishes_the_old_trackers_open_levels():
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    for s in range(20):
        live.on_book("NQ", T0 + s * 1000, *levels(100.0, {("b", 2): 300} if s >= 11 else None))
    (ep_id, ep), = [(k, v) for k, v in collect(page)[1].items() if v["p"] == 99.5]
    assert ep["end"] == "open" and ep["t1"] is None            # shown once 3 s old, still standing
    live.on_book("NQ", T0 + 8 * 3_600_000, *levels(101.0))     # 18:00 ET: the next session
    done = collect(page)[1][ep_id]
    assert done["end"] == "faded" and done["t1"] is not None


def test_a_broken_feed_never_raises():
    logs = []
    live = BookLive(lambda r: TICK, log=logs.append)
    live.on_book("NQ", T0, None, None)             # not lists
    live.on_tick("NQ", object())                   # not a Tick
    assert logs and "book flow (NQ)" in logs[0]


def test_a_print_before_the_first_book_is_harmless_and_the_feed_goes_on():
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    live.on_tick("NQ", Tick(T0 - 500, 100.0, 3, 1))              # no book yet
    lines, ticks = scenario()
    feed(live, lines, ticks)
    live.flush(T0 + 10 ** 9)
    rows, eps = collect(page)
    assert len(rows) == 60 and any(e["end"] == "traded" for e in eps.values())
```

Create `tests/test_charts_depth_tap.py`:

```python
"""Depth.tap: the book lines the recorder would write, handed to a listener (booklive.py) -- the SAME lines, so a
recorded day replayed through bookhist.py and the live tracker see one input."""
from __future__ import annotations

from homebase import symbols
from homebase.charts.depth import Depth, DepthRecorder, read_depth
from tests.charts_util import D
from tests.test_charts_depth import FakeFeed, FakeWS, Page, T0, Clock, connect, ladder, run


def test_the_tap_gets_exactly_the_lines_the_recorder_writes(tmp_path):
    async def go():
        rec = DepthRecorder(tmp_path / "depth")
        feed, clock = FakeFeed(FakeWS()), Clock()
        d = Depth(feed, ("NQ",), recorder=rec, now=clock, wall_ms=lambda: T0)
        got = []
        d.tap = lambda root, ts, bids, offers: got.append({"t": ts, "b": bids, "a": offers, "root": root})
        await connect(d)
        for i in range(6):
            clock.t += 1
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False))
            d.step()
        await d.aflush()
        return rec, got
    rec, got = run(go())
    nq = symbols.resolve_contract("NQ")
    written = read_depth(rec.path("NQ", D, nq))
    assert len(got) == len(written) == 6
    assert [{k: g[k] for k in ("t", "b", "a")} for g in got] == written
    assert all(g["root"] == "NQ" for g in got)


def test_a_viewed_root_that_is_not_recorded_is_tapped_and_an_unviewed_one_is_not(tmp_path):
    async def go():
        ym = symbols.resolve_contract("YM")
        feed = FakeFeed(FakeWS({symbols.resolve_contract("NQ"): 111, ym: 333}))
        clock = Clock()
        d = Depth(feed, ("NQ",), recorder=DepthRecorder(tmp_path / "depth"), now=clock, wall_ms=lambda: T0)
        got = []
        d.tap = lambda root, ts, bids, offers: got.append(root)
        page = Page()
        d.view((page, "c1"), "YM", page.send, page.room)
        await connect(d)
        for i in range(3):
            clock.t += 1
            feed.ws.push(333, ladder(40000.0 + i, 12, step=1.0), ladder(40001.0 + i, 12, step=1.0, down=False))
            d.step()
        assert got == ["YM", "YM", "YM"]
        d.unview((page, "c1"))
        clock.t += 1
        feed.ws.push(333, ladder(41000.0, 12, step=1.0), ladder(41001.0, 12, step=1.0, down=False))
        d.step()
        return got
    assert run(go()) == ["YM", "YM", "YM"]


def test_without_a_tap_nothing_changes(tmp_path):
    async def go():
        rec = DepthRecorder(tmp_path / "depth")
        feed, clock = FakeFeed(FakeWS()), Clock()
        d = Depth(feed, ("NQ",), recorder=rec, now=clock, wall_ms=lambda: T0)
        assert d.tap is None
        await connect(d)
        for i in range(3):
            clock.t += 1
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False))
            d.step()
        await d.aflush()
        return rec
    rec = run(go())
    assert len(read_depth(rec.path("NQ", D, symbols.resolve_contract("NQ")))) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_booklive.py tests/test_charts_depth_tap.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'homebase.charts.booklive'`; the depth tap test: `AttributeError: ... 'tap'`).

- [ ] **Step 3: Implement**

`homebase/charts/depth.py`:

```diff
--- a/homebase/charts/depth.py
+++ b/homebase/charts/depth.py
@@ -357,6 +357,9 @@
         self._flush_lock: Optional[asyncio.Lock] = None
         self._stop = False
         self.error: Optional[str] = None
+        self.tap: Optional[Callable[[str, int, list, list], None]] = None
+        # tap(root, ts_ms, bids, offers): called with each book line the recorder would write (top REC_LEVELS, on
+        # change, <= 4 a second), for the recorded roots and for any root a page is showing. Must not raise.
 
     # ---- pages
 
@@ -446,7 +449,7 @@
                 self._log(f"depth {root}: the feed's stamp is {book.skew_ms / 1000:+.0f} s from the clock, using arrival time"
                           if book.skew_ms else f"depth {root}: the feed's stamps are back in line with the clock")
             self._wire_due.add(root)
-            if self.recorder is not None and root in self.record:
+            if (self.recorder is not None and root in self.record) or (self.tap is not None and self._count.get(root)):
                 self._rec_due.add(root)
             self._drain(root, now)
 
@@ -462,13 +465,17 @@
         if root in self._rec_due and now - self._last_rec.get(root, -math.inf) >= REC_MIN_S - _EPS:
             self._rec_due.discard(root)
             book, contract = self.books.get(root), self._contract.get(root)
-            if book is None or contract is None or book.ts is None:
+            rec = self.recorder is not None and root in self.record
+            if book is None or book.ts is None or (rec and contract is None):
                 return
             top = book.top(REC_LEVELS)
             if top != self._last_top.get(root):
                 self._last_top[root] = top
                 self._last_rec[root] = now
-                self.recorder.add(root, contract, book.ts, *top)
+                if rec:
+                    self.recorder.add(root, contract, book.ts, *top)
+                if self.tap is not None:
+                    self.tap(root, book.ts, *top)
 
     def _watch_socket(self) -> None:
         ws = getattr(self.feed, "ws", None)
```

Create `homebase/charts/booklive.py`:

```python
"""The live side of the book indicators: one BookTracker per root, fed by the SAME two streams the history replay reads.

  books:  Depth's recording tap (depth.Depth.tap) -- top 10 levels, <= 4 a second, only when the book changed: the
          lines the recorder writes to disk, so a recorded day replayed through bookhist.py is this, line for line
  prints: the hub's classified ticks (hub.Hub.taps), side from the same SideClassifier the tick archive uses

Its output goes to every page that charts the root as {"type": "bookflow", root, reset?, samples, episodes}
(bookstore.js applyLive). A page that attaches is greeted with the last RECENT_SAMPLES samples and the recent
episodes (reset: true), so it never waits for the next second. Never blocks: desk.Fanout's bounded outbox.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from typing import Callable, Hashable, Optional

from ..contracts import tick_size as contract_tick_size
from .bookflow import BookTracker
from .desk import Fanout
from .session import session_date

RECENT_SAMPLES = 900          # 15 minutes of 1 s samples
RECENT_EPISODES = 400
PAGE_QUEUE_MAX = 8            # messages held per page per root before it is resynced to the latest


class _Live:
    def __init__(self, root: str, tick: float):
        self.root, self.tick = root, tick
        self.tracker = BookTracker(tick)
        self.session = None
        self.samples: deque = deque(maxlen=RECENT_SAMPLES)
        self.eps: OrderedDict = OrderedDict()


class BookLive:
    def __init__(self, tick_of: Callable[[str], float] = contract_tick_size, log: Optional[Callable[[str], None]] = None):
        self.tick_of = tick_of
        self._log = log or (lambda _m: None)
        self._live: dict[str, _Live] = {}
        self._fans: dict[str, Fanout] = {}
        self._viewers: dict[Hashable, str] = {}

    # ---- pages

    def message(self, root: str, reset: bool = True) -> dict:
        lv = self._live.get(root)
        return {"type": "bookflow", "root": root, "reset": reset,
                "samples": list(lv.samples) if lv else [], "episodes": list(lv.eps.values()) if lv else []}

    def view(self, key: tuple, root: str, send: Callable[[dict], None], room: Callable[[], bool]) -> None:
        root = root.upper()
        old = self._viewers.get(key)
        if old == root:
            return
        if old is not None:
            self.unview(key)
        conn = key[0]
        attach = not any(k[0] is conn and r == root for k, r in self._viewers.items())
        self._viewers[key] = root
        if attach:
            fan = self._fans.get(root)
            if fan is None:
                fan = self._fans[root] = Fanout(hello=lambda r=root: self.message(r), maxlen=PAGE_QUEUE_MAX)
            fan.attach(conn, send, room)

    def unview(self, key: tuple) -> None:
        root = self._viewers.pop(key, None)
        if root is None:
            return
        if not any(k[0] is key[0] and r == root for k, r in self._viewers.items()):
            self._fans[root].detach(key[0])

    def drop_conn(self, conn) -> None:
        for key in [k for k in self._viewers if k[0] is conn]:
            self.unview(key)

    # ---- the feeds (never raise: a tracker fault must not touch the tick or depth path)

    def on_book(self, root: str, ts: int, bids: list, offers: list) -> None:
        try:
            lv = self._at(root, ts)
            self._take(lv, lv.tracker.on_book(ts, bids, offers))
        except Exception as e:  # noqa: BLE001
            self._log(f"book flow ({root}): {type(e).__name__}: {e}")

    def on_tick(self, root: str, tk) -> None:
        try:
            lv = self._at(root, tk.ts_ms)
            self._take(lv, lv.tracker.on_print(tk.ts_ms, tk.price, tk.size, tk.side))
        except Exception as e:  # noqa: BLE001
            self._log(f"book flow ({root}): {type(e).__name__}: {e}")

    def flush(self, now_ms: int) -> None:
        """Commit the seconds that ended while no book line came (the pump calls this about once a second)."""
        for root, lv in list(self._live.items()):
            try:
                self._take(lv, lv.tracker.flush(now_ms))
            except Exception as e:  # noqa: BLE001
                self._log(f"book flow ({root}): {type(e).__name__}: {e}")

    # ---- inside

    def _at(self, root: str, ts: int) -> _Live:
        lv = self._live.get(root)
        if lv is None:
            lv = self._live[root] = _Live(root, float(self.tick_of(root)))
        d = session_date(ts, root)
        if lv.session is not None and d != lv.session:        # the 18:00 roll: the old session ends, a new one starts
            self._take(lv, lv.tracker.finish())
            lv.tracker = BookTracker(lv.tick)
        lv.session = d
        return lv

    def _take(self, lv: _Live, events: list) -> None:
        rows, eps = [], []
        for e in events:
            if e["k"] == "sample":
                rows.append(e["row"])
                lv.samples.append(e["row"])
            else:
                ep = {k: v for k, v in e.items() if k != "k"}
                eps.append(ep)
                lv.eps[ep["id"]] = ep
                lv.eps.move_to_end(ep["id"])
        while len(lv.eps) > RECENT_EPISODES:
            lv.eps.popitem(last=False)
        if (rows or eps) and self._fans.get(lv.root) is not None:
            self._fans[lv.root].publish({"type": "bookflow", "root": lv.root, "samples": rows, "episodes": eps})
```

- [ ] **Step 4: Run the tests**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_booklive.py tests/test_charts_depth_tap.py tests/test_charts_depth.py`
Expected: PASS (6 + 3 new tests; the existing depth tests unchanged: the recorder still writes exactly the same lines). If the depth tests have another file name, `ls tests | grep depth`.

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/booklive.py homebase/charts/depth.py tests/test_booklive.py tests/test_charts_depth_tap.py
git commit -m "feat(charts): BookLive + Depth.tap - live episodes and samples from the recorder's own lines" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Wire it into the service: `/api/book/history`, the live fan-out, the whole suite

**Files:**
- Modify: `homebase/charts/hub.py` (`Hub.taps`), `homebase/charts/server.py` (imports, `BookLive`, `BookPool`, the route, view / unview / drop, pump flush, shutdown)
- Create: `tests/test_charts_book_server.py`

**Interfaces:**
- Consumes: Tasks 3-5 (`BookLive`, `BookPool`, `MAX_SPAN_MS`, `Depth.tap`).
- Produces: `Hub.taps: list[Callable[[str, Tick], None]]` (each called for every live print after its side is known); `GET /api/book/history?root=NQ&from_ms=&to_ms=` -> the `BookHistory.window` JSON (400 on a bad root / range or a span over 48 h, 404 on an unknown root, 503 `busy` while one runs and 503 with the reason inside the paused windows; same host guard as `/api/depth/history`); every page that subscribes to a chart gets `{"type": "bookflow", ...}` right after its `history` message (live service only; Bar Replay charts get none).

- [ ] **Step 1: Write the failing test**

Create `tests/test_charts_book_server.py`:

```python
"""GET /api/book/history: the recorded depth files + the tick archive replayed through BookTracker (bookhist.py),
behind the same host guard, paused windows and 503-while-busy as /api/depth/history. Synthetic files in tmp dirs."""
from __future__ import annotations

import gzip
import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from homebase.charts import bookhist
from homebase.charts.bookhist import MAX_SPAN_MS
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms, write_archive
from tests.test_charts_desk_server import QuietFeed

T0 = session_ms(D, 10, 0)
TICK = 0.25
BASE_URL = "http://127.0.0.1:8852"


def levels(bid, big=None):
    big = big or {}
    return ([[bid - i * TICK, big.get(("b", i), 10)] for i in range(10)],
            [[bid + TICK + i * TICK, big.get(("a", i), 10)] for i in range(10)])


def write_day(tmp_path):
    lines = []
    for s in range(60):
        b, a = levels(100.0, {("b", 2): 300} if 20 <= s < 30 else None)
        lines.append({"t": T0 + s * 1000, "b": b, "a": a})
    p = tmp_path / "depth" / "NQ" / str(D.year) / f"{D.isoformat()}_NQZ6.depth.jsonl.gz"
    p.parent.mkdir(parents=True)
    p.write_bytes(gzip.compress("".join(json.dumps(x) + "\n" for x in lines).encode()))
    prints = rows(T0 + 25_000, [99.5] * 4, step_ms=100, size=160, spread=0.25, first_id=1, sides=[-1] * 4)
    write_archive(tmp_path / "ticks", "NQ", D, "NQZ6", prints)


def app_at(tmp_path, now_ms):
    return create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=QuietFeed, now_ms=lambda: now_ms,
                      state=tmp_path / "state", depth_base=tmp_path / "depth",
                      depth_executor=lambda: ThreadPoolExecutor(max_workers=1))


def test_the_route_serves_samples_and_the_traded_episode(tmp_path):
    write_day(tmp_path)
    bookhist._BOOKS.clear()
    app = app_at(tmp_path, T0 + 3_600_000)
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/book/history", params={"root": "nq", "from_ms": T0, "to_ms": T0 + 60_000})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
        body = r.json()
        assert body["tick"] == TICK and body["step"] == 1000 and len(body["samples"]) == 60
        ep = [e for e in body["episodes"] if e["p"] == 99.5]
        assert len(ep) == 1 and ep[0]["s"] == "b" and ep[0]["tr"] == 640 and ep[0]["end"] == "traded"


def test_the_route_refuses_bad_hosts_roots_and_ranges(tmp_path):
    write_day(tmp_path)
    app = app_at(tmp_path, T0 + 3_600_000)
    with TestClient(app, base_url=BASE_URL) as c:
        ok = {"root": "NQ", "from_ms": T0, "to_ms": T0 + 1000}
        assert c.get("/api/book/history", params=ok, headers={"host": "evil.example"}).status_code == 403
        assert c.get("/api/book/history", params={**ok, "root": "ZZ"}).status_code == 404
        for bad in ({"root": "NQ"}, {"root": "NQ", "from_ms": "x", "to_ms": T0}, {"root": "NQ", "from_ms": -1, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0 - MAX_SPAN_MS - 1, "to_ms": T0},
                    {"root": "NQ", "from_ms": T0, "to_ms": T0 + 3_600_000 + 86_400_001}):
            assert c.get("/api/book/history", params=bad).status_code == 400, bad


def test_the_route_answers_503_in_the_paused_windows(tmp_path):
    write_day(tmp_path)
    for now, why in ((session_ms(D, 8, 30, 10), "paused for the 8:30 data release"),
                     (session_ms(D, 9, 25), "paused for the 9:30 window")):
        app = app_at(tmp_path, now)
        with TestClient(app, base_url=BASE_URL) as c:
            r = c.get("/api/book/history", params={"root": "NQ", "from_ms": T0 - 3_600_000, "to_ms": T0})
            assert r.status_code == 503 and r.json()["detail"] == why


def test_a_root_with_no_recorded_depth_is_an_empty_window_not_an_error(tmp_path):
    app = app_at(tmp_path, T0 + 3_600_000)
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/book/history", params={"root": "NQ", "from_ms": T0, "to_ms": T0 + 60_000})
        assert r.status_code == 200 and r.json()["samples"] == [] and r.json()["episodes"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_book_server.py`
Expected: FAIL (404 on `/api/book/history`).

- [ ] **Step 3: Implement**

`homebase/charts/hub.py` (`Hub.taps`, the tap call in `on_ticks`):

```diff
--- a/homebase/charts/hub.py
+++ b/homebase/charts/hub.py
@@ -192,6 +192,7 @@
         self.streams: dict[tuple[str, str], Stream] = {}
         self.minutes: dict[str, Minutes] = {}
         self._minutes_lock = threading.Lock()
+        self.taps: list = []                # each (root, Tick) -> None, called for every live print, after its side is known
 
     # ------------------------------------------------------------ today's tape
     def start_today(self, root: str, d: dt.date, ticks: list[Tick], info: dict | None = None) -> None:
@@ -236,6 +237,8 @@
                     s.sessions.append(info)
             tk = from_row(r, self.clf[root])
             self.today[root].append(tk)
+            for tap in self.taps:
+                tap(root, tk)
             for s in streams:
                 for b in s.builder.add(tk):
                     s.commit(b)
```

`homebase/charts/server.py` (eight small hunks; the file carries other sessions' uncommitted edits, so apply by hand, anchored by the names in the hunk headers; `known_root`, `depth_wall_ms`, `paused_reason`, `Busy`, `Paused`, `depth_executor`, `depth_base`, `DEPTH_ARCHIVE` are already defined in that file for the depth history route this mirrors):

```diff
--- a/homebase/charts/server.py
+++ b/homebase/charts/server.py
@@ -32,6 +32,8 @@
 from . import DEFAULT_ROOTS, DEPTH_RECORD_ROOTS, QUIET      # QUIET: never refill across the 9:30 fire
 from .bars import BarSpec
 from .barreplay import BarReplay
+from .bookhist import MAX_SPAN_MS as BOOK_MAX_SPAN_MS, BookPool
+from .booklive import BookLive
 from .bursts import REACTION_ROOTS, BurstBook, ReactionBook, configured_roots
 from .calendar import Calendar
 from .depth import DEPTH_ARCHIVE, Depth, DepthRecorder
@@ -1014,6 +1016,12 @@
         depth = Depth(feed, rec_roots, log=log, wall_ms=lambda: int(clock()),    # the service's clock, like the tick hub
                       recorder=DepthRecorder(depth_base or DEPTH_ARCHIVE) if rec_roots else None)
     hub = Hub(history, clock)
+    # the book indicators' live side (booklive.py): the same book lines the recorder writes and the hub's classified
+    # prints, through one BookTracker per root; live service only (a replay has no book)
+    booklive = BookLive(log=log)
+    if depth is not None:
+        depth.tap = booklive.on_book
+        hub.taps.append(booklive.on_tick)
     # per-chart Bar Replay: its own hubs over its own History memo; never the live hub, recorder, desk or quotes
     replays = BarReplay(store, sd / "cache", roots, lambda: clock(), min_bar=MIN_BAR,
                         max_studies=MAX_STUDIES, log=log, known=known)
@@ -1124,6 +1132,7 @@
                 for m in quotes.drain():
                     fan(m)
                 desk_fan.flush()                # only a page that had no room: a desk event goes out as it arrives
+                booklive.flush(clock())         # the seconds a quiet book never closed itself
                 if book is not None and book.dirty:
                     paper_push.kick()           # the backstop: a PAPER change nothing announced still reaches every page
                 replays.pump()
@@ -1243,6 +1252,7 @@
             if depth is not None:
                 await depth.aclose()    # cancels its requests in flight; the recording's last member
             depth_pool.shutdown()       # the depth history worker (depthgrid.HistoryPool), if it ever started
+            book_pool.shutdown()        # ... and the book history worker (bookhist.BookPool)
             tester.manager.shutdown()   # never leave a runner child orphaned
             tester.grids.shutdown()     # ... nor a heat-map cell's
             tester.wfs.shutdown()       # ... nor a walk-forward cell's
@@ -1776,6 +1786,35 @@
             raise HTTPException(400, str(e)) from None
         return Response(body, media_type="application/json")
 
+    # the book indicators' history (bookhist.py): the recorded depth files + the tick archive replayed through the
+    # same BookTracker the live feed runs; one spawned worker, one request at a time (busy -> 503), the same
+    # paused windows as the depth history, never past now
+    book_pool = BookPool(depth_base or DEPTH_ARCHIVE, base, depth_executor)
+
+    @app.get("/api/book/history")
+    async def api_book_history(request: Request):
+        q = request.query_params
+        root = known_root(q.get("root", ""))
+        now = clock()
+        try:
+            frm, to = int(q["from_ms"]), int(q["to_ms"])
+        except (KeyError, ValueError):
+            raise HTTPException(400, "from_ms / to_ms: epoch ms") from None
+        if frm < 0 or to > now + 86_400_000 or to <= frm or to - frm > BOOK_MAX_SPAN_MS:
+            raise HTTPException(400, f"0 <= from_ms < to_ms <= now + 1 day, "
+                                     f"at most {BOOK_MAX_SPAN_MS // 3_600_000} h apart")
+        wall = depth_wall_ms()
+        why = paused_reason(wall / 1000)
+        if why:
+            raise HTTPException(503, why)
+        try:
+            body = await book_pool.window(root, frm, to, now, wall - time.time() * 1000)
+        except (Busy, Paused) as e:
+            raise HTTPException(503, str(e)) from None
+        except ValueError as e:
+            raise HTTPException(400, str(e)) from None
+        return Response(body, media_type="application/json")
+
     @app.websocket("/ws")
     async def ws_endpoint(sock: WebSocket):
         if not origin_ok(sock.headers.get("origin"), sock.headers.get("host")):
@@ -1832,6 +1871,7 @@
                     hub.unsubscribe((conn, cid))
                     if depth is not None:
                         depth.unview((conn, cid))
+                        booklive.unview((conn, cid))
                     continue
                 if op == "older":
                     if not replays.ask_older(conn, cid, msg.get("before")):
@@ -1887,6 +1927,7 @@
                                            bool(msg.get("flow", True)))})
                     if depth is not None:
                         depth.view((conn, cid), root, conn.send, room)   # after `history`: depth follows it
+                        booklive.view((conn, cid), root, conn.send, room)   # and the book flow's recent state
                 except Exception as e:  # noqa: BLE001 — an unexpected failure building the
                                         # stream must not drop every chart on the page either
                     log(f"sub {cid} ({root} {spec.key}): {type(e).__name__}: {e}\n{traceback.format_exc()}")
@@ -1898,6 +1939,7 @@
                     hub.unsubscribe((conn, cid))
                     if depth is not None:
                         depth.unview((conn, cid))
+                        booklive.unview((conn, cid))
                     if s is not None and not s.subs and hub.streams.get(s.key) is s:
                         del hub.streams[s.key]
                     continue
@@ -1911,6 +1953,7 @@
             desk_fan.detach(conn)
             if depth is not None:
                 depth.drop_conn(conn)
+                booklive.drop_conn(conn)
             hub.drop_conn(conn)
             replays.drop_conn(conn)
             conn.task.cancel()
```

- [ ] **Step 4: Run the new test and the service tests**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q tests/test_charts_book_server.py tests/test_charts_server.py tests/test_charts_hub.py tests/test_charts_depth_server.py`
Expected: PASS. (`ls tests | grep depth` for the depth route test file's real name.)

- [ ] **Step 5: Run the whole suite**

Run: `/Users/ramoscapital/ramos-quant-homebase/.venv/bin/python -m pytest -q -p no:cacheprovider tests --ignore=tests/test_charts_paper.py --ignore=tests/test_charts_paperbook.py`
Expected: the same failures as on `main` and nothing new. Run the same command on `main` first if unsure which those are; in the prototype copy the only failures were environment ones (a missing `static/` tree, the deploy plist, the fixture gate, ports).

- [ ] **Step 6: Commit**

```bash
git add homebase/charts/hub.py homebase/charts/server.py tests/test_charts_book_server.py
git commit -m "feat(charts): /api/book/history + live bookflow fan-out" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Note for the restart (do not run it here)**

Python changes go live only after the branch is merged to `main` and the chart service is restarted. A restart cancels running tester jobs: check `desk_status` and restart in the same gated command (vault note `chart-service-restart-gate`). Plan B's page changes load without a restart (`?v=` bump), but the book series show nothing until this server side is live (a page asks `/api/book/history` and gets a 404 until then). One order matters: `ddiv` and `tspeed` are server studies, and an old service refuses a subscribe that names an unknown study, so nobody adds them to a chart before the restart. Both are off by default, so a fresh page is safe.

---
