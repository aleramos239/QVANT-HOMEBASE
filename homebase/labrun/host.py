"""The runner: every promoted Lab strategy on live prices, in SHADOW (2026-10-09).

    python -m homebase.labrun          (its own process; reads the chart service's tick stream, writes the store)

Each promoted, enabled strategy (labrun/store.py) gets one sandboxed child (labrun/child.py) and one StrategyDay. The
day builds the tester's own events from the prints -- the session start, each bar's close, each time -- sends them to
the child, and fills the orders that come back with the tester's own fill law (labrun/shadowfills.py), so a shadow day
equals a backtest of that day. The door (labrun/door.py) says whether the Desk would refuse an order; in SHADOW the
order is still filled on paper and the sentence is only written down. NOTHING here places an order, and nothing here
talks to the desk: the only connection this process opens is the chart service's read-only tick stream.

Strategy code is never trusted: it runs in the child only, the child's replies are read with a deadline and a size
limit, and a child that breaks either is killed and its strategy is stopped for the day. One stuck child costs the
others at most one deadline.

    StrategyDay   one strategy, one date: the child, the schedule, the would-be fills, the day summary
    run_day       a whole list of prints through one StrategyDay (the tests, the replay check)
    Runner        the store's strategies on today's prints: start / catch up / stop, the journal, the heartbeat
    TickClient    the chart service's stream: reconnect, since_ms, no print twice
    run           the process: the client's thread reads, this thread works
"""
from __future__ import annotations

import datetime as dt
import json
import os
import queue
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from array import array
from bisect import bisect_left
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from ..backtest import sandbox
from ..backtest.engine import Costs, build_bars
from ..backtest.runner import DAILY_LOOKBACK
from ..backtest.tape import ET, TapeStore, effective_session_window, et_ns
from ..contracts import point_value, tick_size
from . import door, store
from .shadowfills import ShadowFills

CHILD = ("-m", "homebase.labrun.child")
DEADLINE_S = 1.0                 # a child's answer to one event
START_S = 5.0                    # ... and to its first line (the interpreter starts, the draft loads)
MAX_REPLY = 64 * 1024            # one reply line, bytes
MAX_ORDERS = 20                  # order intents in one event
ORDER_OPS = ("entry", "oco", "cancel", "flatten")
CLOCK_GRACE_NS = 1_000_000_000   # an event this far behind the clock fires without a print
LATE_NS = 2_000_000_000          # the newest print this much older than the clock ...
LATE_FOR_NS = 5_000_000_000      # ... for this long: prices are late
SAVE_S = 1.0                     # the day summary is written at most this often between state changes
BATCH = 200                      # run_day feeds this many prints at a time
POLL_S = 5.0                     # the store is read, and the heartbeat written, this often
STREAM = "/api/labrun/ticks"
BACKOFF_S = (1.0, 30.0)
ACTIVE = ("waiting", "running")
SHADOW = {"max_trades_day": 99, "max_qty": 99, "max_risk_usd": 0}

NO_SANDBOX = "The sandbox is not working."
GONE = "The strategy stopped by itself."
TOO_MANY = "Too many orders at once."


def log(msg: str) -> None:
    print(f"[labrun] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


class _Stop(Exception):
    """The strategy is stopped for today; str(e) is the sentence for the owner."""


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _hms(t_ns: int) -> str:
    return dt.datetime.fromtimestamp(t_ns // 1_000_000_000, ET).strftime("%H:%M:%S")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _opt(v) -> bool:
    return v is None or _num(v)


def well_formed(it) -> bool:
    """An intent as contracts.md writes it. The child is our code, but what it prints is not trusted."""
    if not isinstance(it, dict):
        return False
    op = it.get("op")
    if op == "entry":
        return (_int(it.get("id")) and it.get("kind") in ("market", "stop", "limit") and it.get("side") in ("long", "short")
                and (_num(it.get("price")) if it["kind"] != "market" else it.get("price") is None)
                and _int(it.get("qty")) and 1 <= it["qty"] <= 10_000 and isinstance(it.get("move"), bool)
                and all(_opt(it.get(k)) for k in ("sl", "tp", "tp_rr", "ref")))
    if op == "oco":
        return isinstance(it.get("ids"), list) and bool(it["ids"]) and all(_int(i) for i in it["ids"])
    if op == "cancel":
        return _int(it.get("id"))
    if op in ("flatten", "skip"):
        return isinstance(it.get("reason"), str)
    if op == "plot":
        return isinstance(it.get("name"), str) and _int(it.get("t_ms")) and _num(it.get("value"))
    if op == "hline":
        return (isinstance(it.get("name"), str) and _num(it.get("price")) and isinstance(it.get("role"), str)
                and _int(it.get("t_ms")))
    return False


def words(it: dict, tick: float) -> str:
    """One order, in plain words: "Buy stop 21,450.25, stop 21,400.25, target 21,550.25"."""
    digits = max(2, len(f"{tick:.10f}".rstrip("0").split(".")[1]))

    def px(v) -> str:
        return f"{v:,.{digits}f}"

    op = it["op"]
    if op == "oco":
        return "One cancels the other"
    if op == "cancel":
        return "Cancel"
    if op == "flatten":
        return f"Flatten ({it['reason']})"
    side = "Buy" if it["side"] == "long" else "Sell"
    out = f"{side} at market" if it["kind"] == "market" else f"{side} {it['kind']} {px(it['price'])}"
    if it.get("sl") is not None:
        out += f", stop {px(it['sl'])}"
    if it.get("tp_rr") is not None:             # the engine's rule: with an RR the target comes from the fill
        out += f", target {it['tp_rr']:g} x the stop"
    elif it.get("tp") is not None:
        out += f", target {px(it['tp'])}"
    return out


def daily_bars(root: str, d: dt.date, tapes: TapeStore | None = None) -> list:
    """The completed daily bars before d, read as the tester reads them (runner.execute)."""
    tapes = tapes or TapeStore()
    out = []
    for x in tapes.sessions(root, d - DAILY_LOOKBACK, d):
        bar = tapes.daily(root, x) if x < d else None
        if bar is not None:
            out.append(bar)
    return out


def sandboxed(argv: list, run_dir: Path) -> subprocess.Popen:
    """The child inside the macOS sandbox a draft's backtest runs in (backtest/sandbox.py + draft.sb): no network, no
    fork, nothing to write but its own temp folder, none of the desk's files to read. No sandbox, no child."""
    sandbox.require()
    prm = sandbox.params(run_dir=run_dir, archive=run_dir, cache=run_dir, tmp=run_dir)
    return subprocess.Popen(sandbox.command(argv, prm), cwd=run_dir, env=sandbox.env(run_dir), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)


class _Late:
    """Prices are late: the newest print more than 2 s older than the clock for 5 s running, until a fresh print."""

    def __init__(self):
        self.since: int | None = None
        self.late = False

    def see(self, clock_ns: int, newest_ns: int | None) -> bool:
        if newest_ns is not None and clock_ns - newest_ns <= LATE_NS:
            self.since, self.late = None, False
        else:
            if self.since is None:
                self.since = clock_ns
            self.late = self.late or clock_ns - self.since >= LATE_FOR_NS
        return self.late

    def clear(self) -> None:
        self.since, self.late = None, False


class _Child:
    """One child process: a line in, a line out, never a wait without an end. Its stdout is read by a thread that
    holds at most one reply's bytes; its stdin is written without blocking."""

    _BIG = object()

    def __init__(self, proc: subprocess.Popen, run_dir: Path):
        self.proc, self.run_dir = proc, run_dir
        self._q: queue.Queue = queue.Queue()
        self._in = proc.stdin.fileno()
        os.set_blocking(self._in, False)
        threading.Thread(target=self._read, name="labrun-child", daemon=True).start()

    def _read(self) -> None:
        out = self.proc.stdout
        try:
            while True:
                line = out.readline(MAX_REPLY + 1)
                if not line.endswith(b"\n"):          # the end, or a line with no end in sight: stop reading
                    self._q.put(self._BIG if len(line) > MAX_REPLY else None)
                    return
                self._q.put(line)
        except (OSError, ValueError):
            self._q.put(None)

    def _send(self, data: bytes, end: float, slow: str) -> None:
        view = memoryview(data)
        while view:
            try:
                view = view[os.write(self._in, view):]
            except BlockingIOError:
                left = end - time.monotonic()
                if left <= 0:
                    raise _Stop(slow) from None
                select.select([], [self._in], [], left)
            except OSError:
                raise _Stop(GONE) from None

    def ask(self, msg: dict, deadline_s: float) -> dict:
        """The child's one reply to one line, or the sentence that stops the strategy."""
        slow = f"Too slow: no answer in {deadline_s:g} s."
        if not self._q.empty():                       # it spoke out of turn, or it is gone
            raise _Stop(GONE)
        end = time.monotonic() + deadline_s
        self._send((json.dumps(msg) + "\n").encode(), end, slow)
        try:
            line = self._q.get(timeout=max(0.0, end - time.monotonic()))
        except queue.Empty:
            raise _Stop(slow) from None
        if line is self._BIG:
            raise _Stop(TOO_MANY)
        try:
            reply = json.loads(line) if line is not None else None
        except ValueError:
            reply = None
        if not isinstance(reply, dict):
            raise _Stop(GONE)
        if reply.get("ok") is not True:
            raise _Stop(f"Strategy error: {reply.get('error')}")
        return reply

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        try:
            self.proc.kill()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for f in (self.proc.stdin, self.proc.stdout):
            try:
                f.close()
            except OSError:
                pass
        shutil.rmtree(self.run_dir, ignore_errors=True)


class StrategyDay:
    """One promoted strategy on one date. on_ticks() takes the prints as they come, on_clock() the clock; the day
    ends `done` when the clock passes its window, or `stopped` with the reason.

    spawn(argv, run_dir) -> Popen with stdin and stdout pipes (default: the sandbox). daily: the completed daily bars
    before the date, or a function (root, date) that reads them, asked only if the strategy needs them (default: the
    tape store). save(summary): called at every state change and else at most once a second."""

    def __init__(self, record: dict, date: dt.date, *, spawn=None, daily=None, deadline_s: float = DEADLINE_S,
                 start_s: float = START_S, save=None, wall=time.monotonic):
        self.name, self.date, self.sha256 = record.get("name"), date, record.get("sha256")
        self.state, self.why = "waiting", None
        self.fills: ShadowFills | None = None
        self.orders: list[dict] = []                 # the summary's rows, as they happened
        self._child: _Child | None = None
        self._deadline, self._save, self._wall = deadline_s, save, wall
        self._late = _Late()
        self._clock: int | None = None               # ns, as on_clock last heard it
        self._newest: int | None = None              # ns, the newest print seen (inside the window or not)
        self._entries = 0                            # entries the door let through today
        self._saved_key = None
        self._saved_at = float("-inf")
        self._updated = _utc()
        try:
            self._start(record, spawn or sandboxed, daily if daily is not None else daily_bars, start_s)
        except _Stop as e:
            self._stopped(str(e))
        self._changed()

    # ---- the start
    def _start(self, record: dict, spawn, daily, start_s: float) -> None:
        run_dir = None
        try:
            run_dir = Path(tempfile.mkdtemp(prefix="hb-labrun-"))
            proc = spawn([sys.executable, *CHILD], run_dir)
        except (sandbox.SandboxUnavailable, OSError):    # fail closed: no sandbox, no strategy
            if run_dir is not None:
                shutil.rmtree(run_dir, ignore_errors=True)
            raise _Stop(NO_SANDBOX) from None
        self._child = _Child(proc, run_dir)
        meta = self._child.ask({"op": "init", "name": record.get("name"), "source": record.get("source"),
                                "params": record.get("params"), "qty": record.get("qty"),
                                "date": self.date.isoformat()}, start_s).get("meta")
        try:
            root = meta["root"]
            if not meta["trades_on"]:
                self.state = "not_today"
                self._end_child()
                return
            w0, w1 = effective_session_window(root, self.date, tuple(meta["session_window"]))
            self._t0, self._t1 = et_ns(self.date, w0), et_ns(self.date, w1)
            self._tick = tick_size(root)
            self._limits = {**SHADOW, "last_entry_et": w1[:5], "session_from_et": w0[:5],
                            "point_value": point_value(root) or 0.0, "tick": self._tick}
            # the schedule, run_session's: by time, then session < bar < time, then index
            self._events = deque(sorted([(self._t0, 0, 0, "session", None)]
                                        + [(et_ns(self.date, t), 2, n, "time", t) for n, t in enumerate(meta["times"])]))
            self._bars: deque = deque()              # bar events found so far and not yet fired
            self._bar_min = int(meta["bar_minutes"])
            b0, b1 = meta["bar_window"] or (w0, w1)
            self._bar_next, self._bar_end = et_ns(self.date, b0), et_ns(self.date, b1)
            placement = int(meta["placement_ms"])
            needs_daily = bool(meta["needs_daily"])
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise _Stop(f"Strategy error: {e}") from None
        try:
            self._daily = (daily(root, self.date) if callable(daily) else list(daily)) if needs_daily else []
        except (OSError, ValueError) as e:
            raise _Stop(f"The daily bars could not be read: {e}") from None
        self.fills = ShadowFills(root, self.date, Costs(), placement)

    # ---- the prints and the clock
    def on_ticks(self, rows) -> None:
        """Prints (ts_ns, price, size) in time order. Every event that is due (its time <= the newest print's) runs
        first, each after the prints before it; then the rest of the prints are processed."""
        if self.state not in ACTIVE:
            return
        keep, newest = [], self._newest or 0
        for r in rows:
            ts = r[0]
            if ts >= newest:
                newest = ts
                if self._t0 <= ts < self._t1:
                    keep.append(r)
        if not newest:
            return
        self._newest = newest
        self.fills.add_ticks(keep)
        self._judge_late()
        self._run(newest)
        self._changed()

    def on_clock(self, now_ms: int) -> None:
        """An event more than 1 s behind the clock runs even though no print has reached it. When the clock passes
        the window's end: what is left runs, the day is finished and the child is stopped."""
        now = self._clock = now_ms * 1_000_000
        if self.state in ACTIVE:
            self._judge_late()
            if now < self._t1:
                self._run(now - CLOCK_GRACE_NS - 1)
            else:
                self._run(self._t1 - 1)
                if self.state in ACTIVE:
                    self.fills.finish(self._t1)
                    self.state = "done"
                    self._end_child()
        self._changed()

    @property
    def end_ms(self) -> int:
        """When the window ends (0: the day never got one)."""
        return self._t1 // 1_000_000 if self.fills is not None else 0

    def _judge_late(self) -> None:
        if self._clock is None or not self._t0 <= self._clock < self._t1:
            self._late.clear()
        else:
            self._late.see(self._clock, self._newest)

    def _run(self, horizon: int) -> None:
        try:
            self._find_bars(horizon)
            while True:
                ev = min(self._events[0] if self._events else (horizon + 1,), self._bars[0] if self._bars else (horizon + 1,))
                if ev[0] > horizon or ev[0] >= self._t1:
                    break
                (self._bars if ev[1] == 1 else self._events).popleft()
                self._event(*ev)
            self.fills.advance_all()
        except _Stop as e:
            self._stopped(str(e))
        except Exception as e:  # noqa: BLE001 -- an event that broke half way: the day cannot be trusted any more
            log(f"{self.name}: {type(e).__name__}: {e}")
            self._stopped(f"The runner could not go on: {type(e).__name__}: {e}")

    def _find_bars(self, horizon: int) -> None:
        """The bars that closed by `horizon`, built by the tester's own build_bars from the prints held: aligned to
        multiples of bar_minutes in epoch time, an empty bucket makes no bar."""
        if not self._bar_min or self._bar_next >= self._bar_end:
            return
        step = self._bar_min * 60_000_000_000
        upto = min(horizon - horizon % step, self._bar_end)
        if upto <= self._bar_next - self._bar_next % step:
            return
        f = self.fills
        for b in build_bars(f.ts, f.px, f.size, 0, len(f.ts), self._bar_next, upto, self._bar_min):
            self._bars.append((b.end_ns, 1, 0, "bar", asdict(b)))
        self._bar_next = -(-upto // step) * step

    def _event(self, t: int, _prio, _n, kind: str, arg) -> None:
        f = self.fills
        f.advance_to(t)
        f.now(t)
        if kind == "session":
            self.state = "running"
        last = f.last_price()
        msg = {"op": "event", "kind": kind, "t_ns": t, "arg": arg, "last_price": last, "flat": f.flat,
               "updates": f.updates()}
        if kind == "session":
            msg["daily"] = self._daily
        seen = {"flat": f.flat, "working_entries": f.working_entries, "entries_today": self._entries,
                "last_price": last, "now_hhmm": _hms(t)[:5], "prices_late": self._late.late}
        intents = self._child.ask(msg, self._deadline).get("intents")
        if not isinstance(intents, list) or not all(well_formed(i) for i in intents):
            raise _Stop(GONE)
        if sum(1 for i in intents if i["op"] in ORDER_OPS) > MAX_ORDERS:
            raise _Stop(TOO_MANY)
        verdicts = door.check_event(intents, seen, self._limits)
        # SHADOW: every order is filled on paper whatever the door said (the backtest has no door, and the day must
        # stay comparable with it); the sentence is only written down
        f.apply(intents)
        ok = set()
        for it, no in zip(intents, verdicts):
            if it["op"] not in ORDER_OPS:
                continue
            self.orders.append({"t": _hms(t), "text": words(it, self._tick), "refused": no})
            if no is None and it["op"] == "entry":
                ok.add(it["id"])
                self._entries += 1
            elif no is None and it["op"] == "oco" and len(it["ids"]) == 2 and ok.issuperset(it["ids"]):
                self._entries -= 1                   # a linked pair is one trade

    # ---- the end
    def _end_child(self) -> None:
        if self._child is not None:
            self._child.kill()

    def _stopped(self, why: str) -> None:
        self.state, self.why = "stopped", why
        self._end_child()
        if self.fills is not None:
            self.fills.crash()

    def off(self) -> None:
        """Switched off or removed: the child is stopped; a day that was still going reads `off`."""
        if self.state in ACTIVE:
            self.state = "off"
            if self.fills is not None:
                self.fills.crash("off")
        self._end_child()
        self._changed()

    def kill(self) -> None:
        """Stop the child and say nothing (the runner is going away, or a fresh day takes this one's place)."""
        self._end_child()

    def child_alive(self) -> bool:
        return self._child is not None and self._child.alive()

    # ---- what is written down
    def trades(self) -> list[dict]:
        return self.fills.trades() if self.fills is not None else []

    @property
    def trade_count(self) -> int:
        return len(self.fills.result.trades) if self.fills is not None else 0

    def summary(self) -> dict:
        """The day summary (contracts.md). `match` is filled by the daily match, not here."""
        trades = [{"side": t["side"], "qty": t["qty"], "entry_t": _hms(t["entry_ns"]), "entry_px": t["entry_price"],
                   "exit_t": _hms(t["exit_ns"]), "exit_px": t["exit_price"], "reason": t["exit_reason"], "net": t["net"]}
                  for t in self.trades()]
        why = self.why or (door.PRICES_LATE if self.state in ACTIVE and self._late.late else None)
        return {"date": self.date.isoformat(), "sha256": self.sha256, "state": self.state, "why": why,
                "orders": list(self.orders), "trades": trades, "net": round(sum((t["net"] for t in trades), 0.0), 2),
                "match": None, "updated_utc": self._updated}

    def _changed(self) -> None:
        """Hand the summary to save() when it changed: at once on a new state, else at most once every SAVE_S."""
        key = (self.state, self.why, self._late.late, len(self.orders), self.trade_count)
        if key == self._saved_key:
            return
        fresh = self._saved_key is None or key[0] != self._saved_key[0]
        if not fresh and self._wall() - self._saved_at < SAVE_S:
            return
        self._saved_key, self._saved_at, self._updated = key, self._wall(), _utc()
        if self._save is not None:
            self._save(self.summary())


def run_day(record: dict, rows, date: dt.date, *, spawn=None, daily=None, deadline_s: float = DEADLINE_S,
            batch: int = BATCH) -> dict:
    """A whole list of prints (ts_ns, price, size) through one StrategyDay, `batch` at a time, the prints' own times
    as the clock. No network, no files. Returns {"summary": the day summary, "trades": the engine's trade dicts}."""
    day = StrategyDay(record, date, spawn=spawn, daily=daily or [], deadline_s=deadline_s)
    try:
        for i in range(0, len(rows), batch):
            part = rows[i:i + batch]
            day.on_ticks(part)
            day.on_clock(part[-1][0] // 1_000_000)
        day.on_clock(day.end_ms)
        return {"summary": day.summary(), "trades": day.trades()}
    finally:
        day.kill()


# ---------------------------------------------------------------- the runner

@dataclass
class _Hosted:
    day: StrategyDay
    root: str
    key: tuple                  # the record this day was started from: its code, settings and size
    fed: int = 0                # how many of the market's prints it has had
    orders: int = 0             # how many of its orders, trades and stops are in the journal (or were catch-up)
    trades: int = 0
    stop: bool = False


def _key(rec: dict) -> tuple:
    return (rec.get("sha256"), json.dumps(rec.get("params"), sort_keys=True, default=str), rec.get("qty"))


def _midnight_ms(now_ms: int) -> int:
    d = dt.datetime.fromtimestamp(now_ms / 1000, ET).date()
    return int(dt.datetime.combine(d, dt.time(0), ET).timestamp() * 1000)


class Runner:
    """The strategies of the store on today's prints. One thread calls everything here: on_clock() and on_rows() with
    what the stream sent, sync() and beat() every few seconds. `at`: the store's root (default ~/.homebase/desklab)."""

    def __init__(self, *, at=None, source: str = "", spawn=None, deadline_s: float = DEADLINE_S, daily=None,
                 wall=time.monotonic):
        self.at, self.source = at, source
        self._spawn, self._deadline, self._daily, self._wall = spawn, deadline_s, daily, wall
        self._date: dt.date | None = None            # today, ET: the date of the stream's clock
        self._midnight = 0                           # ns
        self._clock_ms: int | None = None
        self._clock_wall = float("-inf")             # when (wall) the stream's clock was last heard
        self._tapes: dict[str, tuple] = {}           # root -> today's prints from 00:00 ET: (ts_ns, price, size) arrays
        self._late: dict[str, _Late] = {}
        self._days: dict[str, _Hosted] = {}
        self._roots: list[str] = []                  # the markets the enabled strategies trade

    # ---- what the tests and the status read
    def roots(self) -> list:
        return list(self._roots)

    def hosting(self) -> list:
        return sorted(n for n, h in self._days.items() if h.day.state in ACTIVE)

    def day(self, name: str) -> StrategyDay | None:
        h = self._days.get(name)
        return h.day if h is not None else None

    def prints(self, root: str) -> int:
        return len(self._tapes[root][0]) if root in self._tapes else 0

    # ---- the stream
    def take(self, item: tuple) -> None:
        if item[0] == "clock":
            self.on_clock(item[1])
        elif item[0] == "ticks":
            self.on_rows(item[1], item[2])

    def on_clock(self, now_ms: int) -> None:
        self._clock_ms, self._clock_wall = now_ms, self._wall()
        d = dt.datetime.fromtimestamp(now_ms / 1000, ET).date()
        if d != self._date:
            self._roll(d, now_ms)
        for root in self._roots:
            ts = self._tapes[root][0] if root in self._tapes else ()
            self._late.setdefault(root, _Late()).see(now_ms * 1_000_000, ts[-1] if len(ts) else None)
        for h in list(self._days.values()):
            h.day.on_clock(now_ms)
            self._note(h)

    def on_rows(self, root: str, rows) -> None:
        """Fresh prints [[ts_ms, price, size], ...] of one market, in time order."""
        ts, px, size = self._tapes.setdefault(root, (array("q"), array("d"), array("q")))
        for r in rows:
            ns, price, n = int(r[0]) * 1_000_000, float(r[1]), int(r[2])   # ns: the tester's rule for ms recordings
            if ns >= self._midnight:
                ts.append(ns)
                px.append(price)
                size.append(n)
        for h in list(self._days.values()):
            if h.root == root:
                self._feed(h)

    def _roll(self, d: dt.date, now_ms: int) -> None:
        """The ET date changed: every day is finished and dropped, yesterday's prints are dropped, new days start."""
        for h in self._days.values():
            h.day.on_clock(now_ms)                   # past its window: what is left runs, the day ends `done`
            self._note(h)
            h.day.kill()
        self._days.clear()
        self._date = d
        self._midnight = _midnight_ms(now_ms) * 1_000_000
        for root, (ts, px, size) in list(self._tapes.items()):
            i = bisect_left(ts, self._midnight)
            self._tapes[root] = (ts[i:], px[i:], size[i:])
        self.sync()

    def _feed(self, h: _Hosted) -> None:
        ts, px, size = self._tapes[h.root]
        n = len(ts)
        if h.fed < n:
            h.day.on_ticks(zip(ts[h.fed:n], px[h.fed:n], size[h.fed:n]))
            h.fed = n
        self._note(h)

    def _note(self, h: _Hosted, quiet: bool = False) -> None:
        """One journal line per new order, stop and trade (quiet: catch-up, nothing is written)."""
        day = h.day
        if not quiet and (len(day.orders) > h.orders or day.trade_count > h.trades or (day.state == "stopped") > h.stop):
            head = {"utc": _utc(), "date": day.date.isoformat()}
            lines = [{**head, "kind": "order", **o} for o in day.orders[h.orders:]]
            if day.state == "stopped" and not h.stop:
                lines.append({**head, "kind": "stop", "why": day.why})
            if day.trade_count > h.trades:
                lines += [{**head, "kind": "trade", **t} for t in day.summary()["trades"][h.trades:]]
            for line in lines:
                self._write(store.journal, day.name, line)
        h.orders, h.trades, h.stop = len(day.orders), day.trade_count, day.state == "stopped"

    def _write(self, fn, *args) -> None:
        """A write to the store must never take the runner down: say so and go on."""
        try:
            fn(*args, self.at)
        except (OSError, ValueError, TypeError) as e:
            log(f"store: {type(e).__name__}: {e}")

    # ---- the store
    def sync(self) -> None:
        """Read the store: host each enabled strategy whose market has prints today (weekdays only); a strategy that
        appears, is switched on or was promoted again gets a fresh day, fed from today's prints first (catch-up)."""
        try:
            recs = [r for r in store.listing(self.at) if r.get("enabled") and isinstance(r.get("root"), str)]
        except OSError as e:
            log(f"store: {type(e).__name__}: {e}")
            return
        self._roots = sorted({r["root"] for r in recs})
        if self._date is None:
            return
        want = {r["name"]: r for r in recs if self.prints(r["root"])} if self._date.weekday() < 5 else {}
        for name, h in list(self._days.items()):
            rec = want.get(name)
            if rec is None:
                h.day.off()
                del self._days[name]
            elif _key(rec) != h.key:
                h.day.kill()
                del self._days[name]
        for name, rec in want.items():
            if name not in self._days:
                self._host(rec)

    def _host(self, rec: dict) -> None:
        name = rec["name"]
        day = StrategyDay(rec, self._date, spawn=self._spawn, daily=self._daily, deadline_s=self._deadline,
                          save=lambda s: self._write(store.put_day, name, s), wall=self._wall)
        h = self._days[name] = _Hosted(day, rec["root"], _key(rec))
        ts, px, size = self._tapes[h.root]
        h.fed = len(ts)
        day.on_ticks(zip(ts, px, size))              # catch-up: today so far
        if self._clock_ms is not None:
            day.on_clock(self._clock_ms)
        self._note(h, quiet=True)
        log(f"{name}: hosted ({day.state}{', ' + day.why if day.why else ''}), {h.fed} prints to catch up")

    def beat(self) -> None:
        """The heartbeat (contracts.md runner status)."""
        heard = self._clock_ms is not None and self._wall() - self._clock_wall <= POLL_S
        prices = {}
        for root in self._roots:
            ts = self._tapes[root][0] if root in self._tapes else ()
            if heard and len(ts):
                prices[root] = {"age_s": round((self._clock_ms - ts[-1] // 1_000_000) / 1000, 1),
                                "late": self._late[root].late if root in self._late else False}
            else:
                prices[root] = {"age_s": None, "late": True}
        self._write(store.put_runner, {"pid": os.getpid(), "seen_utc": _utc(), "source": self.source, "prices": prices,
                                       "hosting": self.hosting()})

    def close(self) -> None:
        for h in self._days.values():
            h.day.kill()


# ---------------------------------------------------------------- the chart service's tick stream

class _Again(Exception):
    """Ask the stream again, at once."""


class TickClient:
    """Reads GET /api/labrun/ticks (Server-Sent Events) and hands put() what it carries: ("clock", now_ms) and
    ("ticks", root, [[ts_ms, price, size], ...]). It reconnects with back-off (1 s to 30 s), asks for since_ms = 00:00
    ET today on the first connect and the oldest of its newest-print times after that, and never takes a print twice:
    per market, a row older than its newest time is dropped, and of the rows AT its newest time the first k are
    dropped, k being how many it already holds at that millisecond. The only connection this process opens."""

    def __init__(self, url: str, roots, put, *, transport=None, sleep=time.sleep, wall_ms=lambda: int(time.time() * 1000)):
        self.url, self._roots, self._put, self._sleep = url, roots, put, sleep
        self._http = httpx.Client(base_url=url, transport=transport, trust_env=False, follow_redirects=False,
                                  timeout=httpx.Timeout(10.0, read=15.0))   # the stream's clock ticks every second
        self._day = _midnight_ms(wall_ms())          # 00:00 ET of the day it asks for
        self._newest: dict[str, list] = {}           # root -> [its newest print's ms, how many it holds at that ms]
        self._skip: dict[str, int] = {}              # root -> rows at that ms still to drop on this connection

    def reconnected(self) -> None:
        self._skip = {r: n for r, (_, n) in self._newest.items()}

    def fresh(self, root: str, rows) -> list:
        """The rows not held yet."""
        ms, n = self._newest.get(root, (-1, 0))
        skip = self._skip.get(root, 0)
        out = []
        for r in rows:
            t = r[0]
            if t < ms:
                continue
            if t > ms:
                ms, n, skip = t, 0, 0
            elif skip:
                skip -= 1
                continue
            n += 1
            out.append(r)
        self._newest[root], self._skip[root] = [ms, n], skip
        return out

    def since_ms(self, roots) -> int:
        return min([self._newest[r][0] if r in self._newest else self._day for r in roots], default=self._day)

    def _once(self, stop: threading.Event) -> bool:
        """One connection. True when it carried anything."""
        roots = self._roots()
        self.reconnected()
        got = False
        with self._http.stream("GET", STREAM, params={"roots": ",".join(roots), "since_ms": self.since_ms(roots)}) as r:
            if r.status_code != 200:
                raise ValueError(f"the chart service answered {r.status_code}")
            event = ""
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    if stop.is_set():
                        return got
                    if self._roots() != roots:
                        raise _Again()
                    self._on(event, json.loads(line[5:]))
                    got = True
                elif not line:
                    event = ""
        return got

    def _on(self, event: str, data: dict) -> None:
        if event == "clock":
            day = _midnight_ms(data["now_ms"])
            earlier, self._day = day < self._day, day
            if earlier:                              # a replayed session: ask again from ITS midnight
                raise _Again()
            self._put(("clock", data["now_ms"]))
        elif not event:
            rows = self.fresh(data["root"], data["rows"])
            if rows:
                self._put(("ticks", data["root"], rows))

    def run(self, stop: threading.Event) -> None:
        wait = BACKOFF_S[0]
        while not stop.is_set():
            try:
                ok = self._once(stop)
            except _Again:
                continue
            except (httpx.HTTPError, OSError, ValueError, LookupError, TypeError) as e:
                ok = False
                log(f"stream: {type(e).__name__}: {e}")
            if stop.is_set():
                break
            if ok:                                   # a stream that worked: try again soon
                wait = BACKOFF_S[0]
                self._sleep(wait)
            else:                                    # each failure in a row waits twice as long
                self._sleep(wait)
                wait = min(wait * 2, BACKOFF_S[1])


def run(charts: str, at=None) -> None:
    """The process. The client's thread only reads the stream into a queue, so nothing here can make the chart
    service wait for us; this thread does the work, one item at a time."""
    inbox: queue.Queue = queue.Queue()
    runner = Runner(at=at, source=charts)
    runner.sync()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    client = TickClient(charts, runner.roots, inbox.put)
    threading.Thread(target=client.run, args=(stop,), name="labrun-stream", daemon=True).start()
    log(f"up -- {charts}, store {store.root(at)}")
    polled = float("-inf")
    try:
        while not stop.is_set():
            try:
                item = inbox.get(timeout=1.0)
            except queue.Empty:
                item = None
            try:
                if item is not None:
                    runner.take(item)
                if time.monotonic() - polled >= POLL_S:
                    polled = time.monotonic()
                    runner.sync()
                    runner.beat()
            except Exception as e:  # noqa: BLE001 -- one bad item must not take every strategy down
                log(f"runner: {type(e).__name__}: {e}")
    finally:
        runner.close()
