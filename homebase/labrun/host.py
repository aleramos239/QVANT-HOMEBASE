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
    Runner        the store's strategies on the session's prints: start / catch up / stop, the journal, the heartbeat
    run           the process: the tick client's thread (labrun/tickclient.py) reads, this thread works
"""
from __future__ import annotations

import datetime as dt
import json
import os
import queue
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from array import array
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from ..backtest import sandbox
from ..backtest.engine import Costs, build_bars
from ..backtest.runner import DAILY_LOOKBACK
from ..backtest.tape import ET, TapeStore, effective_session_window, et_ns
from ..charts.session import session_date, session_range_ms
from ..contracts import point_value, tick_size
from . import door, store
from .shadowfills import ShadowFills
from .tickclient import TickClient

CHILD = ("-m", "homebase.labrun.child")
DEADLINE_S = 1.0                 # a child's answer to one event
START_S = 5.0                    # ... and to its first line (the interpreter starts, the draft loads)
MAX_REPLY = 64 * 1024            # one reply line, bytes
MAX_ORDERS = 20                  # order intents in one event
ORDER_OPS = ("entry", "oco", "cancel", "flatten")
CLOCK_GRACE_NS = 1_000_000_000   # an event this far behind the clock fires without a print
END_GRACE_NS = 2_000_000_000     # the clock this far past the window's end ends the day (prints still on their way)
LATE_NS = 2_000_000_000          # a print that arrives this far behind the clock ...
LATE_FOR_NS = 5_000_000_000      # ... for this long: prices are late
SILENT_S = 5.0                   # no clock from the stream for this long (our own time): no prices
SAVE_S = 1.0                     # the day summary is written at most this often between state changes
BATCH = 200                      # run_day feeds this many prints at a time
POLL_S = 5.0                     # the store is read, and the heartbeat written, this often
ACTIVE = ("waiting", "running")
SHADOW = {"max_trades_day": 99, "max_qty": 99, "max_risk_usd": 0}

# Every sentence a day's `why` can read (owner-facing: plain words, no Python names). While a day is still going:
#   door.PRICES_LATE ("Prices are late.") and NO_STREAM. A stopped day: one of the others.
NO_SANDBOX = "The sandbox is not working."
GONE = "The strategy stopped by itself."
TOO_MANY = "Too many orders at once."
BAD_SETTINGS = "The strategy's settings cannot be read."
NO_DAILY = "The daily bars could not be read."
TOO_LATE = "Started too late to follow today."
PROBLEM = "Stopped: the runner had a problem."
NO_STREAM = "No prices: the chart service is not answering."
#   "Too slow: no answer in N s." (_Child.ask) and "Strategy error: <its message>" / "Strategy error." (strategy_error)


def log(msg: str) -> None:
    print(f"[labrun] {dt.datetime.now(ET).strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


class _Stop(Exception):
    """The strategy is stopped for today; str(e) is the sentence for the owner, `detail` what broke (the journal's)."""

    def __init__(self, why: str, detail: str | None = None):
        super().__init__(why)
        self.detail = detail


_TYPED = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*: ?")          # the child's event error: "<Type>: <message>"
_NAMED = re.compile(r"^[A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning|Exit|Interrupt)(?: while loading the draft)?: ?")
_BARE = re.compile(r"^[A-Z][A-Za-z0-9_]*(?:Error|Exception|Warning|Exit|Interrupt)$")


def strategy_error(msg, typed: bool) -> str:
    """"Strategy error: <message>" for the owner: the message text only, never a Python type name."""
    text = (_TYPED if typed else _NAMED).sub("", str(msg or "").strip(), count=1).strip()
    text = "" if _BARE.match(text) else (text.splitlines() or [""])[0][:200]
    return f"Strategy error: {text}" if text else "Strategy error."


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


_HHMM = re.compile(r"\d{2}:\d{2}")
_HMS = re.compile(r"\d{2}:\d{2}(?::\d{2})?")


def _at(v, shape) -> bool:
    """A wall time written exactly as `shape` and that exists (no 25:00)."""
    if not isinstance(v, str) or not shape.fullmatch(v):
        return False
    try:
        dt.time.fromisoformat(v)
    except ValueError:
        return False
    return True


def _window(w) -> bool:
    return isinstance(w, list) and len(w) == 2 and _at(w[0], _HHMM) and _at(w[1], _HHMM) and w[0] < w[1]


def well_set(meta, root) -> bool:
    """The child's answer to `init`, checked like an intent before anything is built from it (a negative bar_minutes
    kept the tester's build_bars going for ever): the record's own market, windows of two "HH:MM" with start < end,
    whole numbers in range, at most 500 times, true/false where true/false belongs."""
    if not isinstance(meta, dict):
        return False
    bars, place, times = meta.get("bar_minutes"), meta.get("placement_ms"), meta.get("times")
    return (isinstance(root, str) and meta.get("root") == root and _window(meta.get("session_window"))
            and (meta.get("bar_window") is None or _window(meta["bar_window"]))
            and _int(bars) and 0 <= bars <= 1440 and _int(place) and 0 <= place <= 60_000
            and isinstance(times, list) and len(times) <= 500 and all(_at(t, _HMS) for t in times)
            and isinstance(meta.get("needs_daily"), bool) and isinstance(meta.get("trades_on"), bool))


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
    """Prices are late: prints that ARRIVE more than 2 s behind the stream's clock, for 5 s running; it clears on
    the first print that arrives within 2 s of the clock. Judged only when a print arrives: a market with no prints
    is quiet, not late."""

    def __init__(self):
        self.since: int | None = None
        self.late = False

    def see(self, clock_ns: int, print_ns: int) -> bool:
        if clock_ns - print_ns <= LATE_NS:
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

    def ask(self, msg: dict, deadline_s: float, typed: bool = True) -> dict:
        """The child's one reply to one line, or the sentence that stops the strategy. typed: its error reads
        "<Type>: <message>" (an event's; the first line's is the message alone)."""
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
            raise _Stop(strategy_error(reply.get("error"), typed), str(reply.get("error")))
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
    ends `done` when a print at or after its window's end arrives (or the clock is 2 s past it), or `stopped` with
    the reason (`why`, a sentence for the owner; `detail`, what broke, for the journal).

    spawn(argv, run_dir) -> Popen with stdin and stdout pipes (default: the sandbox). daily: the completed daily bars
    before the date, or a function (root, date) that reads them, asked only if the strategy needs them (default: the
    tape store). save(summary): called at every state change and else at most once a second. late(t0_ns) -> True
    when a day whose window starts at t0 can no longer be followed in full: it is stopped before anything runs."""

    def __init__(self, record: dict, date: dt.date, *, spawn=None, daily=None, deadline_s: float = DEADLINE_S,
                 start_s: float = START_S, save=None, wall=time.monotonic, late=None):
        self.name, self.date, self.sha256 = record.get("name"), date, record.get("sha256")
        self.state, self.why, self.detail = "waiting", None, None
        self.fills: ShadowFills | None = None
        self.orders: list[dict] = []                 # the summary's rows, as they happened
        self._child: _Child | None = None
        self._deadline, self._save, self._wall = deadline_s, save, wall
        self._late = _Late()
        self._silent = False                         # the runner hears no clock from the stream
        self._clock: int | None = None               # ns, as on_clock last heard it
        self._newest: int | None = None              # ns, the newest print seen (inside the window or not)
        self._entries = 0                            # entries the door let through today
        self._saved_key = None
        self._saved_at = float("-inf")
        self._updated = _utc()
        try:
            self._start(record, spawn or sandboxed, daily if daily is not None else daily_bars, start_s, late)
        except _Stop as e:
            self._stopped(str(e), e.detail)
        except Exception as e:  # noqa: BLE001 -- whatever broke, its child must not outlive the attempt
            self._problem(e)
        self._changed()

    # ---- the start
    def _start(self, record: dict, spawn, daily, start_s: float, late) -> None:
        run_dir = proc = None
        try:
            run_dir = Path(tempfile.mkdtemp(prefix="hb-labrun-"))
            proc = spawn([sys.executable, *CHILD], run_dir)
            self._child = _Child(proc, run_dir)
        except BaseException as e:                   # whatever broke: no process and no folder is left behind
            if proc is not None:
                proc.kill()
                proc.wait(timeout=5)
            if run_dir is not None:
                shutil.rmtree(run_dir, ignore_errors=True)
            if isinstance(e, (sandbox.SandboxUnavailable, OSError)):     # fail closed: no sandbox, no strategy
                raise _Stop(NO_SANDBOX) from None
            raise
        meta = self._child.ask({"op": "init", "name": record.get("name"), "source": record.get("source"),
                                "params": record.get("params"), "qty": record.get("qty"),
                                "date": self.date.isoformat()}, start_s, typed=False).get("meta")
        root = record.get("root")
        if not well_set(meta, root):                 # checked like an intent, before anything is built from it
            raise _Stop(BAD_SETTINGS, f"meta: {str(meta)[:300]}")
        if not meta["trades_on"]:
            self.state = "not_today"
            self._end_child()
            return
        w0, w1 = effective_session_window(root, self.date, tuple(meta["session_window"]))
        self._t0, self._t1 = et_ns(self.date, w0), et_ns(self.date, w1)
        if late is not None and late(self._t0):
            raise _Stop(TOO_LATE)
        self._tick = tick_size(root)
        self._limits = {**SHADOW, "last_entry_et": w1[:5], "session_from_et": w0[:5],
                        "point_value": point_value(root) or 0.0, "tick": self._tick}
        # the schedule, run_session's: by time, then session < bar < time, then index
        self._events = deque(sorted([(self._t0, 0, 0, "session", None)]
                                    + [(et_ns(self.date, t), 2, n, "time", t) for n, t in enumerate(meta["times"])]))
        self._bars: deque = deque()                  # bar events found so far and not yet fired
        self._bar_min = meta["bar_minutes"]
        b0, b1 = meta["bar_window"] or (w0, w1)
        self._bar_next, self._bar_end = et_ns(self.date, b0), et_ns(self.date, b1)
        self._daily = []
        if meta["needs_daily"]:
            try:
                self._daily = daily(root, self.date) if callable(daily) else list(daily)
            except OSError as e:
                raise _Stop(NO_DAILY, f"{type(e).__name__}: {e}") from None
        self.fills = ShadowFills(root, self.date, Costs(), meta["placement_ms"])

    # ---- the prints and the clock
    def on_ticks(self, rows) -> None:
        """Prints (ts_ns, price, size) in time order. Every event that is due (its time <= the newest print's) runs
        first, each after the prints before it; then the rest of the prints are processed. A print at or after the
        window's end ends the day."""
        if self.state not in ACTIVE:
            return
        keep, newest, arrived = [], self._newest or 0, 0
        for r in rows:
            ts = r[0]
            arrived = max(arrived, ts)
            if ts >= newest:
                newest = ts
                if self._t0 <= ts < self._t1:
                    keep.append(r)
        if not arrived:
            return
        self._newest = newest
        self.fills.add_ticks(keep)
        if self._clock is not None and self._t0 <= self._clock < self._t1:
            self._late.see(self._clock, arrived)     # judged as the print arrives, against the clock as last heard
        self._run(newest)
        if newest >= self._t1:
            self._finish()
        self._changed()

    def on_clock(self, now_ms: int) -> None:
        """An event more than 1 s behind the clock runs even though no print has reached it. When the clock is 2 s
        past the window's end (time for the prints still on their way), the day ends."""
        now = self._clock = now_ms * 1_000_000
        if self.state in ACTIVE:
            if not self._t0 <= now < self._t1:
                self._late.clear()
            self._run(now - CLOCK_GRACE_NS - 1)
            if now > self._t1 + END_GRACE_NS:
                self._finish()
        self._changed()

    def end(self) -> None:
        """The session is over (it rolled): what is left runs and the day ends, as run_session ends a day."""
        self._finish()
        self._changed()

    def no_prices(self, silent: bool) -> None:
        """The runner hears no clock from the stream (or hears it again)."""
        self._silent = bool(silent)
        self._changed()

    def _finish(self) -> None:
        if self.state in ACTIVE:
            self._run(self._t1 - 1)
        if self.state in ACTIVE:
            self.fills.finish(self._t1)
            self.state = "done"
            self._end_child()

    def _run(self, horizon: int) -> None:
        """Every event at or before `horizon` (and before the window's end), in order; then the prints held."""
        if self.state not in ACTIVE:
            return
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
            self._stopped(str(e), e.detail)
        except Exception as e:  # noqa: BLE001 -- an event that broke half way: the day cannot be trusted any more
            self._problem(e)

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
                "last_price": last, "now_hhmm": _hms(t)[:5], "prices_late": self._late.late or self._silent}
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

    def _stopped(self, why: str, detail: str | None = None) -> None:
        self.state, self.why, self.detail = "stopped", why, detail
        self._end_child()
        if self.fills is not None:
            self.fills.crash()

    def _problem(self, e: Exception) -> None:
        """Not the strategy's doing: stop the day, say so in plain words, keep what broke for the journal."""
        log(f"{self.name}: {type(e).__name__}: {e}")
        self._stopped(PROBLEM, f"{type(e).__name__}: {e}")

    def off(self) -> None:
        """Switched off or removed: the child is stopped; a day that was still going reads `off`."""
        if self.state in ACTIVE:
            self.state = "off"
            if self.fills is not None:
                self.fills.crash("off")
        self._end_child()
        self._changed(now=True)

    def kill(self) -> None:
        """The runner is going away, or a fresh day takes this one's place: write what is known, stop the child."""
        self._changed(now=True)
        self._end_child()

    def drop(self) -> None:
        """Let go and write nothing: this day's prices were another timeline's (a replay took the stream's place)."""
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
        why = self.why
        if why is None and self.state in ACTIVE:
            why = NO_STREAM if self._silent else door.PRICES_LATE if self._late.late else None
        return {"date": self.date.isoformat(), "sha256": self.sha256, "state": self.state, "why": why,
                "orders": list(self.orders), "trades": trades, "net": round(sum((t["net"] for t in trades), 0.0), 2),
                "match": None, "updated_utc": self._updated}

    def _changed(self, now: bool = False) -> None:
        """Hand the summary to save() when it changed: at once on a new state (or `now`), else at most once every
        SAVE_S."""
        key = (self.state, self.why, self._late.late, self._silent, len(self.orders), self.trade_count)
        if key == self._saved_key:
            return
        fresh = now or self._saved_key is None or key[0] != self._saved_key[0]
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
        day.end()                                    # a tape that stops before the window does
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


def _session_ns(d: dt.date, root: str) -> tuple[int, int]:
    """[start, end) of the prints that belong to session d: from its open (18:00 ET the evening before; a weekend's
    prints of a classic market file into Monday) to 18:00 ET on d, where the next session's prints begin."""
    end = int(dt.datetime.combine(d, dt.time(18, 0), ET).timestamp())
    return session_range_ms(d, root)[0] * 1_000_000, end * 1_000_000_000


class Runner:
    """The strategies of the store on the current session's prints. One thread calls everything here: take() with
    what the tick client hands over, sync(), beat() and idle() every few seconds. `at`: the store's root (default
    ~/.homebase/desklab).

    A market's day is the SESSION date of the stream's clock (charts.session.session_date: it rolls at 18:00 ET, as
    the chart service's tape and the tester's archive do), and the prints held are that session's. While a
    connection is still sending its backlog (`connect` seen, `live` not yet) nothing is hosted, finished or clocked:
    the days only take the prints, in order."""

    def __init__(self, *, at=None, source: str = "", spawn=None, deadline_s: float = DEADLINE_S, daily=None,
                 wall=time.monotonic):
        self.at, self.source = at, source
        self._spawn, self._deadline, self._daily, self._wall = spawn, deadline_s, daily, wall
        self._live = False                           # the current connection has sent its whole backlog
        self._clock_ms: int | None = None            # the stream's clock (heard while live)
        self._clock_wall = wall()                    # when (wall) it was last heard
        self._silent = False                         # ... more than SILENT_S ago
        self._dates: dict[str, dt.date] = {}         # root -> its session date
        self._tapes: dict[str, tuple] = {}           # root -> that session's prints: (ts_ns, price, size) arrays
        self._late: dict[str, _Late] = {}
        self._days: dict[str, _Hosted] = {}
        self._final: dict[str, tuple] = {}           # name -> (date, sha256) of a day file found final: never hosted again
        self._roots: list[str] = []                  # the markets the enabled strategies trade

    # ---- what the tests and the status read
    def roots(self) -> list:
        return list(self._roots)

    def hosting(self) -> list:
        return sorted(n for n, h in self._days.items() if h.day.state in ACTIVE)

    def day(self, name: str) -> StrategyDay | None:
        h = self._days.get(name)
        return h.day if h is not None else None

    def date(self, root: str) -> dt.date | None:
        return self._dates.get(root)

    def prints(self, root: str) -> int:
        return len(self._tapes[root][0]) if root in self._tapes else 0

    # ---- the stream
    def take(self, item: tuple) -> None:
        if item[0] == "connect":
            self._live = False                       # a backlog follows: no clock counts until it is complete
        elif item[0] == "live":
            self._live = True
        elif item[0] == "clock":
            self.on_clock(item[1])
        elif item[0] == "ticks":
            self.on_rows(item[1], item[2])

    def on_clock(self, now_ms: int) -> None:
        if not self._live:                           # a clock ahead of its backlog would fire events "with no print"
            return                                   # whose prints are still on their way
        self._clock_ms, self._clock_wall = now_ms, self._wall()
        self._quiet(False)
        rolled = [self._roll(root, d) for root in sorted({*self._roots, *self._tapes})
                  if (d := session_date(now_ms, root)) != self._dates.get(root)]
        if rolled:
            self.sync()
        for h in list(self._days.values()):
            h.day.on_clock(now_ms)
            self._note(h)

    def on_rows(self, root: str, rows) -> None:
        """Fresh prints [[ts_ms, price, size], ...] of one market, in time order."""
        ts, px, size = self._tapes.setdefault(root, (array("q"), array("d"), array("q")))
        for r in rows:
            ns, price, n = int(r[0]) * 1_000_000, float(r[1]), int(r[2])   # ns: the tester's rule for ms recordings
            ts.append(ns)
            px.append(price)
            size.append(n)
        if rows and self._live and self._clock_ms is not None:             # as the print arrives (a backlog is not judged)
            self._late.setdefault(root, _Late()).see(self._clock_ms * 1_000_000, ts[-1])
        for h in list(self._days.values()):
            if h.root == root:
                self._feed(h)

    def idle(self) -> None:
        """No clock from the stream for SILENT_S of our own time: there are no prices, and every day says so."""
        self._quiet(self._wall() - self._clock_wall > SILENT_S)

    def _quiet(self, silent: bool) -> None:
        if silent != self._silent:
            self._silent = silent
            for h in self._days.values():
                h.day.no_prices(silent)

    def _roll(self, root: str, d: dt.date) -> str:
        """The market's session date changed: its days are finished and dropped, and of its prints only the new
        session's are kept (none of an older session, and none of a later one when the clock went back). A roll to
        an EARLIER session is a replay taking the stream's place: the later date's days are let go as they are --
        no event is fired at them, nothing is written, their day files and the journal stay as they were."""
        back = root in self._dates and d < self._dates[root]
        for name, h in list(self._days.items()):
            if h.root == root:
                if back:
                    h.day.drop()
                else:
                    h.day.end()
                    self._note(h)
                    h.day.kill()
                del self._days[name]
        self._dates[root] = d
        self._late.pop(root, None)
        if root in self._tapes:
            ts, px, size = self._tapes[root]
            lo, hi = _session_ns(d, root)
            if len(ts) and not (lo <= min(ts) and max(ts) < hi):
                keep = [i for i, t in enumerate(ts) if lo <= t < hi]
                self._tapes[root] = (array("q", (ts[i] for i in keep)), array("d", (px[i] for i in keep)),
                                     array("q", (size[i] for i in keep)))
        return root

    def _feed(self, h: _Hosted) -> None:
        ts, px, size = self._tapes[h.root]
        n = len(ts)
        if h.fed < n:
            h.day.on_ticks(zip(ts[h.fed:n], px[h.fed:n], size[h.fed:n]))
            h.fed = n
        self._note(h)

    def _note(self, h: _Hosted, quiet: bool = False) -> None:
        """One journal line per new order, stop and trade. quiet (catch-up): nothing is written, but a stop that was
        the runner's own problem, whose detail has no other home."""
        day = h.day
        stopped = day.state == "stopped"
        head = {"utc": _utc(), "date": day.date.isoformat()}
        lines = []
        if not quiet:
            lines += [{**head, "kind": "order", **o} for o in day.orders[h.orders:]]
        if stopped and not h.stop and (not quiet or day.why == PROBLEM):
            lines.append({**head, "kind": "stop", "why": day.why, "detail": day.detail})
        if not quiet and day.trade_count > h.trades:
            lines += [{**head, "kind": "trade", **t} for t in day.summary()["trades"][h.trades:]]
        for line in lines:
            self._write(store.journal, day.name, line)
        h.orders, h.trades, h.stop = len(day.orders), day.trade_count, stopped

    def _write(self, fn, *args) -> None:
        """A write to the store must never take the runner down: say so and go on."""
        try:
            fn(*args, self.at)
        except (OSError, ValueError, TypeError) as e:
            log(f"store: {type(e).__name__}: {e}")

    # ---- the store
    def sync(self) -> None:
        """Read the store: host each enabled strategy whose market has prints this session (never a Saturday's or a
        Sunday's session); a strategy that appears, is switched on or was promoted again gets a fresh day, fed from
        the session's prints first (catch-up) -- unless its day file for the date is final (_is_final). While a
        backlog is in flight nothing is hosted or stopped: the tape is not whole yet."""
        try:
            recs = [r for r in store.listing(self.at) if r.get("enabled") and isinstance(r.get("root"), str)]
        except OSError as e:
            log(f"store: {type(e).__name__}: {e}")
            return
        self._roots = sorted({r["root"] for r in recs})
        if not self._live or self._clock_ms is None:
            return
        for root in self._roots:                     # a market nobody traded until now
            if root not in self._dates:
                self._roll(root, session_date(self._clock_ms, root))
        want = {r["name"]: r for r in recs if self._dates[r["root"]].weekday() < 5 and self.prints(r["root"])}
        for name, h in list(self._days.items()):
            rec = want.get(name)
            if rec is None:
                h.day.off()
                del self._days[name]
            elif _key(rec) != h.key:
                h.day.kill()                         # (its last word is written first)
                del self._days[name]
        for name, rec in want.items():
            if name not in self._days and not self._is_final(rec):
                self._host(rec)

    def _is_final(self, rec: dict) -> bool:
        """A day file for the date with the SAME sha256 and state `done` or `stopped` is final: that strategy is not
        hosted again for that date and the file is never rewritten -- not after a restart, a failure or a late
        start. Promoted again (another sha256), it starts a fresh day."""
        name, mark = rec["name"], (self._dates[rec["root"]], rec.get("sha256"))
        if self._final.get(name) == mark:
            return True
        try:
            was = store.get_day(name, mark[0].isoformat(), self.at)
        except (OSError, ValueError):
            was = None
        if was is None or was.get("sha256") != mark[1] or was.get("state") not in ("done", "stopped"):
            return False
        self._final[name] = mark
        log(f"{name}: {mark[0]} is {was.get('state')} already: left as it is")
        return True

    def _host(self, rec: dict) -> None:
        name, root = rec["name"], rec["root"]
        date = self._dates[root]
        ts, px, size = self._tapes[root]
        now, oldest = self._clock_ms * 1_000_000, ts[0]
        try:
            there = store.day_path(name, date.isoformat(), self.at).exists()
        except (OSError, ValueError):
            there = True                             # cannot tell: fail closed, as if a day file were there

        def save(summary: dict) -> None:
            if summary["why"] == TOO_LATE and there:     # never over a day file that exists: it may be a finished day
                return
            self._write(store.put_day, name, summary)

        # Fail closed: the clock is past the window's start and the prints held begin after it (the stream's backlog
        # is the session from its open; a tape that starts later cannot rebuild the day in full).
        day = StrategyDay(rec, date, spawn=self._spawn, daily=self._daily, deadline_s=self._deadline, save=save,
                          wall=self._wall, late=lambda t0: now > t0 and oldest > t0)
        h = self._days[name] = _Hosted(day, root, _key(rec), fed=len(ts))
        if self._silent:
            day.no_prices(True)
        day.on_ticks(zip(ts, px, size))              # catch-up: the session so far
        day.on_clock(self._clock_ms)
        self._note(h, quiet=True)
        log(f"{name}: {date} {day.state}{' (' + day.why + ')' if day.why else ''}, {h.fed} prints to catch up")

    def beat(self) -> None:
        """The heartbeat (contracts.md runner status). No clock from the stream: every market reads late, no age.
        A market with no prints is quiet, not late."""
        heard = self._clock_ms is not None and self._wall() - self._clock_wall <= SILENT_S
        prices = {}
        for root in self._roots:
            ts = self._tapes[root][0] if root in self._tapes else ()
            if not heard:
                prices[root] = {"age_s": None, "late": True}
            elif not len(ts):
                prices[root] = {"age_s": None, "late": False}
            else:
                prices[root] = {"age_s": round((self._clock_ms - ts[-1] // 1_000_000) / 1000, 1),
                                "late": self._late[root].late if root in self._late else False}
        self._write(store.put_runner, {"pid": os.getpid(), "seen_utc": _utc(), "source": self.source, "prices": prices,
                                       "hosting": self.hosting()})

    def close(self) -> None:
        for h in self._days.values():
            h.day.kill()


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
                runner.idle()
                if time.monotonic() - polled >= POLL_S:
                    polled = time.monotonic()
                    runner.sync()
                    runner.beat()
            except Exception as e:  # noqa: BLE001 -- one bad item must not take every strategy down
                log(f"runner: {type(e).__name__}: {e}")
    finally:
        runner.close()
