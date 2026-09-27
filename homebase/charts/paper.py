"""Forward PAPER test of the OOS-passed GC NFP + CPI 08:30 straddle, inside the chart service.

It never sends an order. On an event day it buffers the GC prints the chart service
already receives, and from 08:30:00 re-runs the BACKTESTER'S OWN
`run_session(GCNfpCpi(), tape_so_far, Costs())` on them (at most once a second, in a
worker thread), so paper fills follow the house tick law exactly: parity by construction.

  * Strategy: homebase/strategies/gc_nfpcpi.py with its saved spec (offset 2 / SL 3 /
    TP 6, 1 contract; anchor = last print before 08:30:00.000 ET, live 85 ms later,
    unfilled entries cancelled 08:45, flat 09:55).
  * Event day: the ForexFactory calendar the service already polls shows a USD,
    High-impact event at 08:30 ET titled "Non-Farm Employment Change" (NFP) or
    "CPI m/m" / "CPI y/y" / "Core CPI m/m" (CPI). When the calendar holds no week for
    the date, the strategy's static CSV decides for the dates it contains. The rule
    that decided ("ff" | "csv" | "forced") is logged and stored with the run.
  * Window: prints are buffered only from 08:29:50 to the flat time + 1 minute (09:56),
    plus ONE carried print -- the last one in [08:20, 08:29:50) -- so the anchor is
    the same as the full tape's even when nothing trades in the last 10 s before
    08:30. Nothing runs outside that window, nothing runs on other days.
  * Feed gaps never become trades (fix round 1): a gap -- marked in the recording, a
    reconnect not yet resolved by its refill, or >= 5 s with no print on ANY root between
    08:29:50 and 08:31:00 -- overlapping the part of the window the trade depends on makes
    the day `no_data` with the reason. The final run waits for a running GC refill (up
    to 10:30 ET). A weekday whose ForexFactory week is missing and has no CSV row is
    recorded as `calendar_missing`, not silently skipped.
  * A run on a PARTIAL tape ends in the engine's end-of-tape flatten ("eod"); before
    the window ends that close is not real, so the position is reported as open
    (state "in_trade", `open_pnl_usd` = the provisional mark).
  * Storage (<state>/charts/paper/): runs.jsonl, one line per finished run (append;
    rewritten when a day's run is re-finalised), and backtest.json, the research-window
    comparison computed ONCE with the tester runner (2021-01-01..2024-12-31 only; never
    a 2025+ run) by `python -m homebase.charts.paper backtest`, launched by BacktestJob
    never between 08:00 and 10:00 ET, killed after 15 min, a failure blocking it 24 h.
  * Replay: off, unless the chart service's --paper-day flag forces the replayed date to
    count as an event day; a replay never reads or writes runs.jsonl, and its runs are
    tagged `replay: true` and kept out of the forward stats.

No broker, desk or trading module is imported here (a test pins it), and no market
data is requested: only the ticks the service already streams.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import subprocess
import sys
import threading
import time
from array import array
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import Callable, Iterable

from ..backtest.engine import Costs, run_session, to_tick
from ..backtest.tape import ARCHIVE, CACHE, ET, Tape, et_ns, stable_sorted
from ..contracts import tick_size
from ..paths import repo_root, state_dir
from ..strategies.gc_nfpcpi import GCNfpCpi, calendar as csv_calendar
from . import QUIET, _jsonl
from .calendar import week_start

STRATEGY_ID = GCNfpCpi.id                   # "gc_nfpcpi"
NAME = "GC NFP/CPI (paper)"
ROOT = GCNfpCpi.root                        # "GC"
QTY = 1
COSTS = Costs()                             # the tester's defaults: $4.00 RT, 1 tick slip per side
BUFFER_FROM = "08:29:50"                    # the tick buffer (and the "waiting" state) starts here
RUN_EVERY_S = 1.0                           # at most one run_session a second
FINAL_GRACE_MS = 2000                       # the last prints before 09:56 may reach us a moment late
EVENT_RECHECK_S = 60.0                      # a non-event day re-reads the calendar at most this often
SILENCE_TO = "08:31:00"                     # >= SILENCE_S with no print on any root in [08:29:50, this) = a gap
SILENCE_S = 5
SILENCE_NS = SILENCE_S * 1_000_000_000
STALL_S = 60                                # >= this with no GC print, anchor -> min(now, 09:55): a GC stall
STALL_NS = STALL_S * 1_000_000_000          # (the worst real GC lull 08:31-09:55, 2021-2024: 12.5 s)
HOLD_UNTIL = "10:30"                        # the final run waits for a GC refill up to this ET time
BACKTEST_BLOCK = (dt.time(8, 0), dt.time(10, 0))   # the comparison child never starts in here (ET) ...
BACKTEST_AT = dt.time(10, 5)                # ... a start that lands inside waits until this
BACKTEST_TIMEOUT_S = 15 * 60                # killed after this
BACKTEST_POLL_S = 5.0
BACKTEST_RETRY_S = 24 * 3600                # backtest.failed blocks a respawn this long
FF_TITLES = {"Non-Farm Employment Change": "NFP", "CPI m/m": "CPI", "CPI y/y": "CPI", "Core CPI m/m": "CPI"}
EVENT_TIME = "08:30"
BACKTEST_WINDOW = "2021-2024"
PAPER_LABEL = "paper (forward)"
FORBIDDEN_IMPORTS = ("homebase.broker", "homebase.trading", "homebase.desk_api", "homebase.engine",
                     "homebase.timer", "homebase.charts.desk", "homebase.server", "homebase.risk")


def params() -> dict:
    s = GCNfpCpi()
    return {"offset_pts": s.p["offset_pts"], "sl_pts": s.p["sl_pts"], "tp_pts": s.p["tp_pts"], "qty": QTY}


def describe() -> dict:
    return {"id": STRATEGY_ID, "name": NAME, "root": ROOT, "params": params()}


def _add_min(hhmm: str, minutes: int) -> str:
    t = dt.datetime.combine(dt.date(2000, 1, 3), dt.time.fromisoformat(hhmm)) + dt.timedelta(minutes=minutes)
    return t.strftime("%H:%M:%S")


def label(tags) -> str | None:
    t = set(tags) & {"NFP", "CPI"}
    return "NFP+CPI" if t == {"NFP", "CPI"} else (next(iter(t)) if t else None)


def ff_tags(cal, d: dt.date) -> frozenset | None:
    """{"NFP", "CPI"} ∩ the USD High-impact 08:30 ET events ForexFactory lists for d, or
    None when the calendar holds no week for d (it was never fetched)."""
    t830 = et_ns(d, EVENT_TIME) // 1_000_000
    if cal is None or week_start(t830).isoformat() not in getattr(cal, "weeks", {}):
        return None
    return frozenset(FF_TITLES[e["title"]] for e in cal.events(t830, t830 + 1, ["USD"])
                     if e.get("impact") == "High" and e.get("title") in FF_TITLES)


def detect_event(d: dt.date, cal, force_day: dt.date | None = None) -> tuple[frozenset, str]:
    """(tags ⊆ {"NFP", "CPI"}, rule). The ForexFactory calendar decides; the static CSV
    only for a date it contains when the calendar has no week for it."""
    tags, rule = ff_tags(cal, d), "ff"
    if tags is None:
        if d in csv_calendar():
            tags, rule = csv_calendar()[d] & {"NFP", "CPI"}, "csv"
        else:
            tags, rule = frozenset(), "none"
    if force_day is not None and d == force_day:
        return (tags or frozenset({"NFP", "CPI"})), "forced"
    return frozenset(tags), rule


def stats(nets: list[float]) -> dict:
    """{n, wr (% winners), avg, net} over per-trade net P&L in USD."""
    n = len(nets)
    if not n:
        return {"n": 0, "wr": None, "avg": None, "net": 0.0}
    net = sum(nets)
    return {"n": n, "wr": round(100.0 * sum(1 for x in nets if x > 0) / n, 1),
            "avg": round(net / n, 2), "net": round(net, 2)}


def _row_ns(r: dict) -> int:
    t = r.get("ts_ns")
    return int(t) if t not in (None, "") else int(r["ts_ms"]) * 1_000_000


def _exit_kind(reason: str) -> str:
    return reason if reason in ("tp", "sl") else "flat"


class PaperRunner:
    """One strategy's forward paper run. `on_ticks`/`seed` feed it, `due(now_ms)` says
    whether a run is due (cheap; call it on the loop), `step(now_ms)` runs it (call it in a
    worker thread) and returns the /ws message when the state changed.

    Feed gaps (fix round 1, C1): the recording's marked gaps (`seed(..., gaps=)`), a
    reconnect (`note_gap`, until the refill that follows it calls `clear_pending` and its
    reseed carries whatever it could not fill as a marked gap), and >= 5 s with no print on
    ANY root between 08:29:50 and 08:31:00 while this process was watching (`note_alive`
    records the other roots' prints: a quiet GC alone on a live socket is the market, not a
    gap). A gap overlapping [08:29:50, exit] -- or [08:29:50, 08:45] with no fill -- makes
    the day `no_data` with the reason: no legs, no entry, no P&L. The final run waits while
    `busy()` (a GC refill running or pending), up to 10:30 ET; after that a refill still
    running is itself a gap."""

    def __init__(self, folder: Path | None, cal=None, *, enabled: bool = True,
                 force_day: dt.date | None = None, persist: bool = True, replay: bool = False,
                 backtest_file: Path | None = None, busy: Callable[[], bool] = lambda: False,
                 log: Callable[[str], None] = print, wall: Callable[[], float] = time.monotonic,
                 run: Callable = run_session):
        self.replay = bool(replay)
        # a replay never reads or writes the forward record (I3)
        self.folder = Path(folder) if folder is not None and not self.replay else None
        self.persist = persist and not self.replay
        self.backtest_file = Path(backtest_file) if backtest_file is not None else (
            self.folder / "backtest.json" if self.folder is not None else None)
        self.cal, self.enabled, self.force_day, self.busy = cal, enabled, force_day, busy
        self.log, self.wall, self._run = log, wall, run
        self.strategy = GCNfpCpi()
        self.tick = tick_size(ROOT)
        self.runs: list[dict] = []
        if self.folder is not None:
            self.runs = [r for r in _jsonl.read_all(self.folder / "runs.jsonl")
                         if r.get("strategy") == STRATEGY_ID and isinstance(r.get("date"), str)]
        self.runs_done = 0                  # run_session calls (tests)
        self.last_result = None             # the last run's SessionResult (tests: parity)
        self.current: dict | None = None    # the last /ws message (sent to new connections)
        self._lock = threading.Lock()
        self.day: dt.date | None = None
        self._reset(None, 0)

    # ---- day state
    def _reset(self, d: dt.date | None, now_ns: int) -> None:
        with self._lock:
            self._ts, self._px, self._sz = array("q"), array("d"), array("i")
            self._carry: tuple[int, float, int] | None = None
            self._alive = array("q")        # ns of other roots' prints, 08:29:50-08:31:00
            self.dirty = False
        self._rec_gaps: list[tuple[int, int, str]] = []     # the recording's marked gaps (seed)
        self._pending: list[tuple[int, int, str]] = []      # reconnects not yet resolved by a refill
        self.day, self.tags, self.rule = d, frozenset(), "none"
        self.phase, self.last_run = 0, float("-inf")
        self.final, self.seen, self._checked = False, False, float("-inf")
        self._rechecked, self._missing = False, False
        self._live_from = now_ns            # this process watches the live feed from here on
        self.current = None
        if d is None:
            return
        s = self.strategy
        self.t_sess0 = et_ns(d, s.session_window[0])
        self.t_buf0 = et_ns(d, BUFFER_FROM)
        self.t_fire = et_ns(d, s.fire)
        self.t_silence_end = et_ns(d, SILENCE_TO)
        self.t_cancel = et_ns(d, s.cancel_et)
        self.t_flat = et_ns(d, s.flat_et)
        self.t_end = et_ns(d, _add_min(s.flat_et, 1))
        self.t_hold = et_ns(d, HOLD_UNTIL)
        stored = self._stored(d)
        if stored is not None:              # finished before a restart: nothing left to do today
            self.final = True
            self.tags = frozenset((stored.get("event") or "").split("+")) & {"NFP", "CPI"}
            self.rule = stored.get("rule", "")
            self.current = self._msg({**stored, "state": "done"})
        else:
            self._detect()

    def _detect(self) -> None:
        self._checked = self.wall()
        tags, rule = detect_event(self.day, self.cal, self.force_day)
        if tags and not self.tags:
            self.log(f"paper {STRATEGY_ID}: {self.day} is an event day ({label(tags)}, rule {rule})")
        elif self.tags and not tags:
            self.log(f"paper {STRATEGY_ID}: {self.day} is no longer an event day (rule {rule}): skipped")
        self.tags, self.rule = tags, rule

    def _roll(self, now_ms: int) -> None:
        d = dt.datetime.fromtimestamp(now_ms / 1000, ET).date()
        if d != self.day:
            self._reset(d, now_ms * 1_000_000)
        elif not self.tags and not self.final and self.wall() - self._checked >= EVENT_RECHECK_S:
            self._detect()                  # the calendar may have been fetched since

    def _stored(self, d: dt.date) -> dict | None:
        return next((r for r in self.runs if r.get("date") == d.isoformat()), None)

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.tags) and not self.final and self.day is not None

    def window_ms(self, now_ms: int) -> tuple[int, int] | None:
        """[08:20, 09:56) ET of today in epoch ms while the runner wants ticks, else None
        (the service slices the session's tick list to it before `seed`)."""
        self._roll(now_ms)
        return (self.t_sess0 // 1_000_000, self.t_end // 1_000_000) if self.active else None

    def _phase(self, now_ns: int) -> int:
        """0 before 08:29:50 · 1 waiting · 2 fired · 3 past the cancel · 4 final (window over)."""
        if now_ns < self.t_buf0:
            return 0
        if now_ns < self.t_fire:
            return 1
        if now_ns < self.t_cancel:
            return 2
        if now_ns < self.t_end + FINAL_GRACE_MS * 1_000_000:
            return 3
        return 4

    # ---- ticks
    def _add(self, t: int, p: float, s: int) -> None:
        """Caller holds the lock. Only the window is kept (+ the one carried print)."""
        if t >= self.t_buf0:
            if t < self.t_end:
                self._ts.append(t)
                self._px.append(p)
                self._sz.append(s)
                self.dirty = True
        elif t >= self.t_sess0 and (self._carry is None or t >= self._carry[0]):
            self._carry = (t, p, s)
            self.dirty = True

    def on_ticks(self, rows: list[dict]) -> None:
        """The live tick path (rows as the feed/replay deliver them). O(1) off the window."""
        if not rows or not self.active:
            return
        if _row_ns(rows[-1]) < self.t_sess0 or _row_ns(rows[0]) >= self.t_end:
            return
        with self._lock:
            for r in rows:
                self._add(_row_ns(r), float(r["price"]), int(r.get("size") or 0))

    def note_alive(self, ts_ms: int) -> None:
        """A print on ANY root reached us (the md socket is alive): kept for the silence
        check, only between 08:29:50 and 08:31:00, at most one per 100 ms."""
        if not self.active:
            return
        t = int(ts_ms) * 1_000_000
        if self.t_buf0 <= t < self.t_silence_end and (not self._alive or t - self._alive[-1] >= 100_000_000):
            with self._lock:
                self._alive.append(t)

    def note_gap(self, start_ms: int, end_ms: int, reason: str = "reconnect") -> None:
        """The feed reconnected: [start, end) is a hole until the refill resolves it."""
        if self.day is not None and end_ms > start_ms:
            self._pending.append((int(start_ms) * 1_000_000, int(end_ms) * 1_000_000, reason))
            self.dirty = True

    def clear_pending(self) -> None:
        """The refill after a reconnect is over: its reseed carried what it could not fill."""
        if self._pending:
            self._pending = []
            self.dirty = True

    def seed(self, now_ms: int, ticks: Iterable[tuple[int, float, int]], gaps: Iterable = ()) -> None:
        """Rebuild today's buffer from the recorded ticks ((ts_ns, price, size), in tape
        order) and the recording's marked gaps ([start_ms, end_ms]): at startup (a restart
        mid-window) and after a gap refill."""
        self._roll(now_ms)
        if not self.active:
            return
        rec = []
        for g in gaps or ():
            try:
                a, b = int(g[0]) * 1_000_000, int(g[1]) * 1_000_000
            except (TypeError, ValueError, IndexError):
                continue
            if b > a:
                rec.append((a, b, "recorded"))
        with self._lock:
            self._ts, self._px, self._sz = array("q"), array("d"), array("i")
            self._carry = None
            for t, p, s in ticks:
                if self.t_sess0 <= t < self.t_end:
                    self._add(int(t), float(p), int(s))
            self._rec_gaps = rec
            self.dirty = True
            if self._ts or rec:
                self.seen = True            # a restart after the window can still finalise from these

    def snapshot(self) -> Tape:
        with self._lock:
            ts, px, sz = array("q", self._ts), array("d", self._px), array("i", self._sz)
            if self._carry is not None:
                ts.insert(0, self._carry[0])
                px.insert(0, self._carry[1])
                sz.insert(0, self._carry[2])
            alive = array("q", self._alive)
            self.dirty = False
        ts, px, sz = stable_sorted(ts, px, sz)
        self._snap_alive = alive
        return Tape(ROOT, self.day, "", ts, px, sz, {})

    # ---- gaps
    def _silences(self, tape: Tape, alive, now_ns: int) -> list[tuple[int, int, str]]:
        lo, hi = max(self.t_buf0, self._live_from), min(self.t_silence_end, now_ns)
        if hi - lo < SILENCE_NS:
            return []
        i, j = bisect_left(tape.ts, lo), bisect_left(tape.ts, hi)
        pts = [lo, *tape.ts[i:j], hi]
        out = []
        for x, y in zip(pts, pts[1:]):
            if y - x < SILENCE_NS:
                continue
            a, b = bisect_right(alive, x), bisect_left(alive, y)
            seen = [x, *alive[a:b], y]
            if any(q - p >= SILENCE_NS for p, q in zip(seen, seen[1:])):
                out.append((x, y, "silence"))
        return out

    def _anchor_ns(self, tape: Tape) -> int | None:
        """The anchor print's time: the last tape print before 08:30:00 (maybe the carry)."""
        i = bisect_left(tape.ts, self.t_fire)
        return tape.ts[i - 1] if i > 0 else None

    def stalls(self, tape: Tape, now_ns: int) -> list[tuple[int, int, str]]:
        """Fix round 2: every stretch of >= 60 s with no GC print between the anchor and
        min(now, 09:55), the tail after the last print included. Catches a GC-only stall
        (a dead or refused GC subscription while the other roots keep printing)."""
        a = self._anchor_ns(tape)
        end = min(now_ns, self.t_flat)
        if a is None or end - a < STALL_NS:
            return []
        i, j = bisect_left(tape.ts, a), bisect_left(tape.ts, end)
        pts = [*tape.ts[i:j], end]
        return [(x, y, "GC stall") for x, y in zip(pts, pts[1:]) if y - x >= STALL_NS]

    def gaps(self, tape: Tape, now_ns: int, final: bool) -> list[tuple[int, int, str]]:
        out = list(self._rec_gaps) + list(self._pending)
        out += self._silences(tape, getattr(self, "_snap_alive", array("q")), now_ns)
        if final and self.busy():
            out.append((self.t_buf0, now_ns, "refill still running at " + HOLD_UNTIL))
        return out

    # ---- runs
    def due(self, now_ms: int) -> bool:
        self._roll(now_ms)
        if not self.enabled or self.final or self.day is None:
            return False
        now_ns = now_ms * 1_000_000
        ph = self._phase(now_ns)
        if ph >= 1 and not self._rechecked:            # M5: the calendar may have moved the event
            self._rechecked = True
            self._detect()
            self._missing = (not self.tags and self.rule == "none" and not self.replay
                             and self.day.weekday() < 5)
        if self._missing:
            return self.wall() - self.last_run >= RUN_EVERY_S
        if not self.tags or ph == 0:
            return False
        if ph < 4:
            self.seen = True
        elif not self.seen:
            return False                    # never saw this window: nothing to finalise from
        elif self.busy() and now_ns < self.t_hold:
            return False                    # C1: GC's refill may still fill the tape
        if ph == self.phase and not (self.dirty and ph in (2, 3)):
            return False
        return self.wall() - self.last_run >= RUN_EVERY_S

    def step(self, now_ms: int) -> dict | None:
        """One run on the ticks so far. Returns the /ws message when it changed. Nothing is
        marked done (phase, final) unless the snapshot and the write succeeded (M6/M7)."""
        now_ns = now_ms * 1_000_000
        ph = self._phase(now_ns)
        self.last_run = self.wall()
        base = {"date": self.day.isoformat(), "event": label(self.tags), "rule": self.rule}
        try:
            if self._missing:
                summary = {**base, "state": "done", "status": "calendar_missing", "anchor": None, "legs": [],
                           "error": "no ForexFactory week for this date and no CSV row"}
                self._finish(summary)
                self._missing, self.final = False, True
            else:
                summary = self._compute(ph, now_ns, base)
                if ph == 4:
                    self._finish(summary)
                    self.final = True
        except Exception as e:  # noqa: BLE001 — retried at the next poll; never takes the service down
            self.log(f"paper {STRATEGY_ID}: {type(e).__name__}: {e} (will retry)")
            return None
        self.phase = ph
        msg = self._msg(summary)
        if msg == self.current:
            return None
        self.current = msg
        return msg

    def _compute(self, ph: int, now_ns: int, base: dict) -> dict:
        if ph <= 1:
            return {**base, "state": "waiting", "status": None, "anchor": None, "legs": []}
        tape = self.snapshot()              # may raise: the caller retries
        final = ph == 4
        try:
            self.runs_done += 1
            res = self.last_result = self._run(GCNfpCpi(), tape, COSTS, qty=QTY)
        except Exception as e:  # noqa: BLE001 — a paper run must never take the service down
            self.log(f"paper {STRATEGY_ID}: {type(e).__name__}: {e}")
            return {**base, "state": "done" if final else "waiting", "status": "error",
                    "error": f"{type(e).__name__}: {e}"[:200], "anchor": None, "legs": []}
        s = self.summarize(res, now_ns, final)
        hit = self._gap_hit(s, tape, now_ns, final)
        if hit:
            s = {"state": "done" if final else "waiting", "status": "no_data", "anchor": None, "legs": [],
                 "error": "feed gap " + "; ".join(f"{_et(a)}–{_et(b)} ET ({why})" for a, b, why in hit)}
        return {**base, **s}

    def _gap_hit(self, s: dict, tape: Tape, now_ns: int, final: bool) -> list:
        """The gaps overlapping [start, exit] (a trade), [start, now] (an open one) or
        [start, 08:45] (no fill), start = min(08:29:50, the anchor print) -- so a hole just
        before a stale carried anchor counts (fix round 2) -- plus any GC stall, which
        voids the day whatever it overlaps: a dead GC feed is never a trade."""
        if s.get("exit"):
            end = s["exit"]["ts"] * 1_000_000
        elif s.get("entry"):
            end = now_ns
        else:
            end = self.t_cancel if final else min(self.t_cancel, now_ns)
        a = self._anchor_ns(tape)
        start = self.t_buf0 if a is None else min(self.t_buf0, a)
        hit = [g for g in self.gaps(tape, now_ns, final) if g[0] <= end and g[1] > start]
        return hit + self.stalls(tape, now_ns)

    def summarize(self, res, now_ns: int, final: bool) -> dict:
        anchor = next((h["price"] for h in res.hlines if h.get("name") == "anchor"), None)
        legs = [] if anchor is None else [
            {"side": g.side, "price": to_tick(g.trigger, self.tick), "sl": to_tick(g.sl, self.tick),
             "tp": to_tick(g.tp, self.tick)} for g in self.strategy.legs(anchor)]
        out: dict = {"anchor": anchor, "legs": legs}
        if res.skip and res.skip.startswith("strategy error"):
            return {**out, "state": "done", "status": "error", "error": res.skip}
        if res.trades:
            t = res.trades[0]
            out["entry"] = {"side": t.side, "price": t.entry_price, "ts": t.entry_ns // 1_000_000,
                            "sl": t.sl, "tp": t.tp}
            if not final and t.exit_reason == "eod":            # the end of a partial tape, not an exit
                return {**out, "state": "in_trade", "status": None, "open_pnl_usd": t.net}
            out["exit"] = {"price": t.exit_price, "ts": t.exit_ns // 1_000_000,
                           "kind": _exit_kind(t.exit_reason)}
            out["pnl_usd"] = round(sum(x.net for x in res.trades), 2)
            return {**out, "state": "done", "status": "traded"}
        if anchor is None:
            return {**out, "state": "done" if final else "waiting", "status": "no_data"}
        if now_ns < self.t_cancel and not final:
            return {**out, "state": "armed", "status": None}
        return {**out, "state": "done", "status": "no_fill"}

    def _msg(self, s: dict) -> dict:
        msg = {"type": "paper", "strategy": STRATEGY_ID, "name": NAME, "root": ROOT,
               "date": s.get("date"), "event": s.get("event"), "rule": s.get("rule"),
               "state": s.get("state"), "status": s.get("status"), "anchor": s.get("anchor"),
               "legs": s.get("legs") or [], "entry": s.get("entry"), "exit": s.get("exit"),
               "pnl_usd": s.get("pnl_usd")}
        if s.get("open_pnl_usd") is not None:
            msg["open_pnl_usd"] = s["open_pnl_usd"]
        if s.get("error"):
            msg["error"] = s["error"]
        if self.replay or s.get("replay"):
            msg["replay"] = True
        return msg

    def _finish(self, s: dict) -> None:
        """Write the day's record FIRST; only then does it join self.runs (M7)."""
        rec = {"date": s["date"], "strategy": STRATEGY_ID, "event": s.get("event"), "rule": s.get("rule"),
               "status": s.get("status") or "no_data", "anchor": s.get("anchor"), "legs": s.get("legs") or []}
        for k in ("entry", "exit", "pnl_usd", "error"):
            if s.get(k) is not None:
                rec[k] = s[k]
        if self.replay:
            rec["replay"] = True
        rec["finalized_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        again = any(r.get("date") == rec["date"] for r in self.runs)
        if self.persist and self.folder is not None:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / "runs.jsonl"
            if again:                       # re-finalised: the day keeps ONE line
                others = [r for r in _jsonl.read_all(path) if r.get("date") != rec["date"]]
                _jsonl.write_all(path, sorted(others + [rec], key=lambda r: str(r.get("date"))))
            else:
                _jsonl.append(path, rec)
        self.runs = sorted([r for r in self.runs if r.get("date") != rec["date"]] + [rec],
                           key=lambda r: r["date"])
        self.log(f"paper {STRATEGY_ID}: {rec['date']} {rec['event']} ({rec['rule']}) -> {rec['status']}"
                 + (f" {rec['pnl_usd']:+.2f} USD" if "pnl_usd" in rec else "")
                 + (f" [{rec['error']}]" if "error" in rec else "") + (" [replay]" if self.replay else ""))

    # ---- the page
    def backtest(self) -> dict | None:
        if self.backtest_file is None:
            return None
        bt = _jsonl.read_json(self.backtest_file)
        if not bt:
            return None
        return {"window": bt.get("window"), "n": bt.get("n"), "wr": bt.get("wr"),
                "avg": bt.get("avg"), "net": bt.get("net")}

    def history(self) -> dict:
        runs = [dict(r) for r in self.runs]
        nets = [r["pnl_usd"] for r in runs if r.get("status") == "traded" and r.get("pnl_usd") is not None
                and not r.get("replay")]
        return {"runs": runs,
                "stats": {"paper": {"label": PAPER_LABEL, **stats(nets)}, "backtest": self.backtest()},
                "current": self.current}


def _et(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, ET).strftime("%H:%M:%S")


# ---- the one-time comparison job (I2)

def backtest_delay_s(now_ms: int) -> float:
    """Seconds to wait before the comparison may start: never 08:00-10:00 ET (the event
    window, which holds QUIET 09:20-09:35); a start inside it is moved to 10:05 ET."""
    t = dt.datetime.fromtimestamp(now_ms / 1000, ET)
    blocked = BACKTEST_BLOCK[0] <= t.time() < BACKTEST_BLOCK[1] or QUIET[0] <= t.time() < QUIET[1]
    if not blocked:
        return 0.0
    target = dt.datetime.combine(t.date(), BACKTEST_AT, ET)
    return max(0.0, (target - t).total_seconds())


class BacktestJob:
    """Launch the comparison child once, outside the blocked hours, kill it after 15
    minutes, reap it, and leave `backtest.failed` (which blocks a respawn for 24 h) when it
    fails. `spawn(folder)` returns a Popen-like object (poll/wait/kill/terminate)."""

    def __init__(self, folder: Path, spawn: Callable, clock_ms: Callable[[], int],
                 log: Callable[[str], None], sleep: Callable = asyncio.sleep,
                 wall: Callable[[], float] = time.time):
        self.folder, self.spawn, self.clock, self.log = Path(folder), spawn, clock_ms, log
        self.sleep, self.wall = sleep, wall
        self.proc = None

    def blocked(self) -> str | None:
        if (self.folder / "backtest.json").exists():
            return "done"
        failed = _jsonl.read_json(self.folder / "backtest.failed")
        ts = failed.get("ts")
        if isinstance(ts, (int, float)) and self.wall() - ts < BACKTEST_RETRY_S:
            return f"failed {failed.get('reason')!r} under 24 h ago"
        return None

    def _fail(self, reason: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        _jsonl.write_json(self.folder / "backtest.failed", {"ts": self.wall(), "reason": reason})
        self.log(f"paper backtest: {reason}")

    async def run(self) -> None:
        if self.blocked():
            return
        delay = backtest_delay_s(self.clock())
        if delay > 0:
            self.log(f"paper backtest: waiting {delay / 60:.0f} min (never 08:00-10:00 ET)")
            await self.sleep(delay)
            if self.blocked():
                return
        self.proc = proc = self.spawn(self.folder)
        t0 = self.wall()
        while proc.poll() is None:
            if self.wall() - t0 >= BACKTEST_TIMEOUT_S:
                proc.kill()
                proc.wait()
                self._fail(f"timeout after {BACKTEST_TIMEOUT_S // 60} min (killed)")
                return
            await self.sleep(BACKTEST_POLL_S)
        code = proc.wait()                  # reap
        if code != 0 or not (self.folder / "backtest.json").exists():
            self._fail(f"exit {code}")

    def stop(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 — TimeoutExpired: it must not outlive the service
            proc.kill()
            proc.wait()


# ---- the research-window comparison (computed once, cached in backtest.json)

def compute_backtest(folder: Path, archive: Path = ARCHIVE, cache: Path = CACHE) -> dict:
    """Run the strategy over the RESEARCH WINDOW ONLY (2021-01-01..2024-12-31) with the
    tester's own runner, into a private runs dir, and cache {window, n, wr, avg, net}."""
    from ..backtest import runner
    from ..backtest.tape import TapeStore

    p = params()
    body = {"strategy": STRATEGY_ID, "range": {"kind": "research"}, "qty": p["qty"],
            "inputs": {"offset_pts": p["offset_pts"], "sl_pts": p["sl_pts"], "tp_pts": p["tp_pts"],
                       "events": "NFP+CPI"},
            "commission": COSTS.commission_rt, "slippage_ticks": COSTS.slippage_ticks}
    req = runner.validate(body)
    if req["holdout"] is not None or req["range"]["holdout"] or req["range"]["end"] != "2024-12-31":
        raise RuntimeError("the paper comparison may only read the research window")
    base = Path(folder) / "tester"
    rid = runner.prepare(body, base)
    runner.exec_run(base / "runs" / rid, TapeStore(archive, cache))
    trades = runner.read_json(base / "runs" / rid / "trades.json", []) or []
    meta = runner.read_json(base / "runs" / rid / "run.json", {}) or {}
    cov = meta.get("coverage") or {}
    out = {"window": BACKTEST_WINDOW, "start": req["range"]["start"], "end": req["range"]["end"],
           **stats([float(t["net"]) for t in trades]),
           "params": p, "costs": {"commission_rt": COSTS.commission_rt, "slippage_ticks": COSTS.slippage_ticks},
           "sessions": cov.get("sessions"), "skipped": cov.get("skipped") or [],
           "run_id": rid, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    Path(folder).mkdir(parents=True, exist_ok=True)
    _jsonl.write_json(Path(folder) / "backtest.json", out)
    return out


def spawn_backtest(folder: Path) -> subprocess.Popen:
    """The chart service's one-time launch of the comparison, in its own (niced) process."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    log = open(folder / "backtest.log", "ab")
    try:
        return subprocess.Popen([sys.executable, "-m", "homebase.charts.paper", "backtest",
                                 "--folder", str(folder)], cwd=repo_root(), stdout=log,
                                stderr=subprocess.STDOUT)
    finally:
        log.close()                          # the child holds its own descriptor


def main(argv: list[str] | None = None) -> int:
    """python -m homebase.charts.paper backtest [--folder DIR]"""
    import os
    ap = argparse.ArgumentParser(prog="python -m homebase.charts.paper")
    ap.add_argument("cmd", choices=["backtest"])
    ap.add_argument("--folder", type=Path, default=None)
    ap.add_argument("--archive", type=Path, default=ARCHIVE)
    ap.add_argument("--cache", type=Path, default=CACHE)
    a = ap.parse_args(argv)
    os.nice(10)                              # never competes with the charts or the desk
    out = compute_backtest(a.folder or state_dir() / "charts" / "paper", a.archive, a.cache)
    print(f"{STRATEGY_ID} {out['window']}: n {out['n']}, WR {out['wr']}%, avg ${out['avg']}, "
          f"net ${out['net']:,.2f}, skipped {len(out['skipped'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
