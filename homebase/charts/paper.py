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
  * A run on a PARTIAL tape ends in the engine's end-of-tape flatten ("eod"); before
    the window ends that close is not real, so the position is reported as open
    (state "in_trade", `open_pnl_usd` = the provisional mark).
  * Storage (<state>/charts/paper/): runs.jsonl, one line per finished run (append;
    rewritten when a day's run is re-finalised), and backtest.json, the research-window
    comparison computed ONCE with the tester runner (2021-01-01..2024-12-31 only; never
    a 2025+ run) by `python -m homebase.charts.paper backtest`.
  * Replay: off, unless the chart service's --paper-day flag forces the replayed date to
    count as an event day; a replay stores nothing.

No broker, desk or trading module is imported here (a test pins it), and no market
data is requested: only the ticks the service already streams.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import threading
import time
from array import array
from pathlib import Path
from typing import Callable, Iterable

from ..backtest.engine import Costs, run_session, to_tick
from ..backtest.tape import ARCHIVE, CACHE, ET, Tape, et_ns, stable_sorted
from ..contracts import tick_size
from ..paths import repo_root, state_dir
from ..strategies.gc_nfpcpi import GCNfpCpi, calendar as csv_calendar
from . import _jsonl
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
    worker thread) and returns the /ws message when the state changed."""

    def __init__(self, folder: Path | None, cal=None, *, enabled: bool = True,
                 force_day: dt.date | None = None, persist: bool = True,
                 log: Callable[[str], None] = print, wall: Callable[[], float] = time.monotonic,
                 run: Callable = run_session):
        self.folder = Path(folder) if folder is not None else None
        self.cal, self.enabled, self.force_day, self.persist = cal, enabled, force_day, persist
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
        self._reset(None)

    # ---- day state
    def _reset(self, d: dt.date | None) -> None:
        with self._lock:
            self._ts, self._px, self._sz = array("q"), array("d"), array("i")
            self._carry: tuple[int, float, int] | None = None
            self.dirty = False
        self.day, self.tags, self.rule = d, frozenset(), "none"
        self.phase, self.last_run = 0, float("-inf")
        self.final, self.seen, self._checked = False, False, float("-inf")
        self.current = None
        if d is None:
            return
        s = self.strategy
        self.t_sess0 = et_ns(d, s.session_window[0])
        self.t_buf0 = et_ns(d, BUFFER_FROM)
        self.t_fire = et_ns(d, s.fire)
        self.t_cancel = et_ns(d, s.cancel_et)
        self.t_end = et_ns(d, _add_min(s.flat_et, 1))
        stored = self._stored(d)
        if stored is not None:              # finished before a restart: nothing left to do today
            self.final = True
            self.tags = frozenset(stored.get("event", "").split("+")) & {"NFP", "CPI"}
            self.rule = stored.get("rule", "")
            self.current = self._msg({**stored, "state": "done"})
        else:
            self._detect()

    def _detect(self) -> None:
        self._checked = self.wall()
        tags, rule = detect_event(self.day, self.cal, self.force_day)
        if tags and not self.tags:
            self.log(f"paper {STRATEGY_ID}: {self.day} is an event day ({label(tags)}, rule {rule})")
        self.tags, self.rule = tags, rule

    def _roll(self, now_ms: int) -> None:
        d = dt.datetime.fromtimestamp(now_ms / 1000, ET).date()
        if d != self.day:
            self._reset(d)
        elif not self.tags and not self.final and self.wall() - self._checked >= EVENT_RECHECK_S:
            self._detect()                  # the calendar may have been fetched since

    def _stored(self, d: dt.date) -> dict | None:
        return next((r for r in self.runs if r.get("date") == d.isoformat()), None)

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.tags) and not self.final and self.day is not None

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

    def seed(self, now_ms: int, ticks: Iterable[tuple[int, float, int]]) -> None:
        """Rebuild today's buffer from the recorded ticks ((ts_ns, price, size), in tape
        order): at startup (a restart mid-window) and after a gap refill."""
        self._roll(now_ms)
        if not self.active:
            return
        with self._lock:
            self._ts, self._px, self._sz = array("q"), array("d"), array("i")
            self._carry = None
            for t, p, s in ticks:
                if self.t_sess0 <= t < self.t_end:
                    self._add(int(t), float(p), int(s))
            self.dirty = True
            if self._ts:
                self.seen = True            # a restart after the window can still finalise from these

    def snapshot(self) -> Tape:
        with self._lock:
            ts, px, sz = array("q", self._ts), array("d", self._px), array("i", self._sz)
            if self._carry is not None:
                ts.insert(0, self._carry[0])
                px.insert(0, self._carry[1])
                sz.insert(0, self._carry[2])
            self.dirty = False
        ts, px, sz = stable_sorted(ts, px, sz)
        return Tape(ROOT, self.day, "", ts, px, sz, {})

    # ---- runs
    def due(self, now_ms: int) -> bool:
        self._roll(now_ms)
        if not self.active:
            return False
        ph = self._phase(now_ms * 1_000_000)
        if ph == 0:
            return False
        if ph < 4:
            self.seen = True
        elif not self.seen:
            return False                    # never saw this window: nothing to finalise from
        if ph == self.phase and not (self.dirty and ph in (2, 3)):
            return False
        return self.wall() - self.last_run >= RUN_EVERY_S

    def step(self, now_ms: int) -> dict | None:
        """One run on the ticks so far. Returns the /ws message when it changed."""
        now_ns = now_ms * 1_000_000
        ph = self._phase(now_ns)
        self.phase, self.last_run = ph, self.wall()
        base = {"date": self.day.isoformat(), "event": label(self.tags), "rule": self.rule}
        if ph <= 1:
            summary = {**base, "state": "waiting", "status": None, "anchor": None, "legs": []}
        else:
            tape = self.snapshot()
            try:
                self.runs_done += 1
                res = self.last_result = self._run(GCNfpCpi(), tape, COSTS, qty=QTY)
                summary = {**base, **self.summarize(res, now_ns, final=ph == 4)}
            except Exception as e:  # noqa: BLE001 — a paper run must never take the service down
                self.log(f"paper {STRATEGY_ID}: {type(e).__name__}: {e}")
                summary = {**base, "state": "done" if ph == 4 else "waiting", "status": "error",
                           "error": f"{type(e).__name__}: {e}"[:200], "anchor": None, "legs": []}
        if ph == 4:
            self.final = True
            self._finish(summary)
        msg = self._msg(summary)
        if msg == self.current:
            return None
        self.current = msg
        return msg

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
        return msg

    def _finish(self, s: dict) -> None:
        rec = {"date": s["date"], "strategy": STRATEGY_ID, "event": s.get("event"), "rule": s.get("rule"),
               "status": s.get("status") or "no_data", "anchor": s.get("anchor"), "legs": s.get("legs") or []}
        for k in ("entry", "exit", "pnl_usd", "error"):
            if s.get(k) is not None:
                rec[k] = s[k]
        rec["finalized_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        again = any(r.get("date") == rec["date"] for r in self.runs)
        self.runs = [r for r in self.runs if r.get("date") != rec["date"]] + [rec]
        self.runs.sort(key=lambda r: r["date"])
        self.log(f"paper {STRATEGY_ID}: {rec['date']} {rec['event']} ({rec['rule']}) -> {rec['status']}"
                 + (f" {rec['pnl_usd']:+.2f} USD" if "pnl_usd" in rec else ""))
        if not self.persist or self.folder is None:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / "runs.jsonl"
        if again:                           # re-finalised: the day keeps ONE line
            others = [r for r in _jsonl.read_all(path) if r.get("date") != rec["date"]]
            _jsonl.write_all(path, sorted(others + [rec], key=lambda r: str(r.get("date"))))
        else:
            _jsonl.append(path, rec)

    # ---- the page
    def backtest(self) -> dict | None:
        if self.folder is None:
            return None
        bt = _jsonl.read_json(self.folder / "backtest.json")
        if not bt:
            return None
        return {"window": bt.get("window"), "n": bt.get("n"), "wr": bt.get("wr"),
                "avg": bt.get("avg"), "net": bt.get("net")}

    def history(self) -> dict:
        runs = [dict(r) for r in self.runs]
        nets = [r["pnl_usd"] for r in runs if r.get("status") == "traded" and r.get("pnl_usd") is not None]
        return {"runs": runs,
                "stats": {"paper": {"label": PAPER_LABEL, **stats(nets)}, "backtest": self.backtest()},
                "current": self.current}


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
