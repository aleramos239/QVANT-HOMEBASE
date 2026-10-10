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
    Runner        the store's strategies on the session's prints: start / catch up / stop, the journal, the heartbeat,
                  and the daily match (labrun/match.py) of each finished day, in a worker thread
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
from bisect import bisect_left
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from ..backtest import sandbox, slots
from ..backtest.engine import Costs, build_bars
from ..backtest.runner import DAILY_LOOKBACK
from ..backtest.tape import ARCHIVE, CACHE, ET, TapeStore, effective_session_window, et_ns
from ..charts.session import session_date, session_range_ms
from ..contracts import point_value, tick_size
from . import door, match, store
from .deskclient import DeskClient
from .deskside import DeskSide, booked, desk_id
from .intents import ORDER_OPS, well_formed   # (the desk checks a runner's event with the same rule: labrun/intents.py)
from .shadowfills import ShadowFills
from .tickclient import TickClient

CHILD = ("-m", "homebase.labrun.child")
DEADLINE_S = 1.0                 # a child's answer to one event
START_S = 5.0                    # ... and to its first line (the interpreter starts, the draft loads)
MAX_REPLY = 64 * 1024            # one reply line, bytes
MAX_ORDERS = 20                  # order intents in one event
CLOCK_GRACE_NS = 1_000_000_000   # an event this far behind the clock fires without a print
END_GRACE_NS = 2_000_000_000     # the clock this far past the window's end ends the day (prints still on their way)
LATE_NS = 2_000_000_000          # a print that arrives this far behind the clock ...
LATE_FOR_NS = 5_000_000_000      # ... for this long: prices are late
SILENT_S = 5.0                   # no clock from the stream for this long (our own time): no prices
SAVE_S = 1.0                     # the day summary is written at most this often between state changes
BATCH = 200                      # run_day feeds this many prints at a time
POLL_S = 5.0                     # the store is read, and the heartbeat written, this often
MATCH_AFTER_NS = 600_000_000_000     # the daily match starts this long after the day's end (by the stream's clock),
MATCH_NOT_BEFORE = "17:35"           # never before this ET time of the session date (the archive must hold the day) ...
MATCH_RETRY_NS = 1_800_000_000_000   # ... and "not checked yet" is tried again this often,
MATCH_RETRIES = 6                    # at most this many times
ACTIVE = ("waiting", "running")
SHADOW = {"max_trades_day": 99, "max_qty": 99, "max_risk_usd": 0}
# desk mode (Step B: a day whose strategy has accounts on the Desk; see "DESK MODE" in StrategyDay)
TOO_LATE_NS = 3_000_000_000      # an event this far behind the stream's clock sends no entry
BLIND_S = 20.0                   # no clock from the stream for this long with an order working: its entries are cancelled
RETRY_S, RETRY_FOR_S = 1.0, 10.0     # a cancel, a flatten or a stop the Desk did not take is asked again: how often, how long
REFUSED_RUN = 3                  # this many events in a row whose entries were all refused: stopped for today
EXITS = ("cancel", "flatten")    # the orders that may be asked again (and the runner's own `stop`); an entry never is

# Every sentence a day's `why` can read (owner-facing: plain words, no Python names). While a day is still going:
#   door.PRICES_LATE ("Prices are late.") and NO_STREAM. A stopped day: one of the others.
NO_SANDBOX = "The sandbox is not working."
GONE = "The strategy stopped by itself."
TOO_MANY = "Too many orders at once."
BAD_SETTINGS = "The strategy's settings cannot be read."
NO_DAILY = "The daily bars could not be read."
NO_YESTERDAY = "Yesterday's prices are not stored yet."
TOO_LATE = "Started too late to follow today."
NOT_CHECKED = "Not checked yet: the check failed."
PROBLEM = "Stopped: the runner had a problem."
NO_STREAM = "No prices: the chart service is not answering."
#   "Too slow: no answer in N s." (_Child.ask) and "Strategy error: <its message>" / "Strategy error." (strategy_error)
# Desk mode only. On an order's row: NOT_ANSWERING (not sent: the Desk's stream is down or silent for 15 s, its key file
# does not read, or it refused the request whole), NO_ANSWER (sent, and no answer came: never sent again), TOO_LATE_ONE
# (not sent: the event is more than 3 s behind the stream's clock), door.PRICES_LATE (not sent), TOO_MANY (the Desk's
# 429) and whatever sentence the Desk answered. As a day's `why`: NOT_ANSWERING while it lasts; stopped: NO_RESUME,
# STOPPED_TODAY (the Desk says so, or the runner went away cleanly), KILLED, or the sentence of the third refused event.
NOT_ANSWERING = "The Desk is not answering."
NO_ANSWER = "The Desk did not answer."
TOO_LATE_ONE = "Too late for this one."
NO_RESUME = "Could not pick up where it left off."
STOPPED_TODAY = "Stopped for today."
KILLED = "Killed today."
NO_FILLS = "Not checked: a trade's fills are not known."     # the daily match of a desk day (a round with no price)


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
        return "Link the pair: one cancels the other"
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


def costs_of(record: dict) -> Costs:
    """The costs the promoted backtest ran with (frozen in the record by store.snapshot), so a shadow day's net is the
    same sum as its backtest's; the tester's own defaults for a record that does not carry them."""
    base = Costs()
    c, s = record.get("commission"), record.get("slippage_ticks")
    return Costs(c if _num(c) else base.commission_rt, s if _num(s) else base.slippage_ticks)


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


def gets_out(why: str) -> bool:
    """Desk mode, ruling Q2: a strategy that raised, was too slow, went away or flooded gets out of its trade at once
    (the tester's own law); every other stop keeps the position on its broker stop and the Desk's flat time."""
    return why in (GONE, TOO_MANY) or why.startswith(("Strategy error", "Too slow:"))


def desk_sentence(row: dict) -> str | None:
    """The Desk's one sentence for an entry it answered: none when at least one account took it; else its own
    `refused` (the first account's sentence when the accounts differ)."""
    if row.get("status") != "cancelled":
        return None
    text = row.get("refused")
    if isinstance(text, str) and text:
        return text
    accounts = row.get("accounts")
    first = next(iter(accounts.values()), None) if isinstance(accounts, dict) else None
    reason = first.get("reason") if isinstance(first, dict) else None
    return reason if isinstance(reason, str) and reason else door.CANNOT_CHECK


def exit_trouble(row: dict) -> str | None:
    """A cancel, a flatten or a stop the Desk answered: None when every account carried it out, else the Desk's
    sentence for the first account that did not (its `reason`, else the last step it names)."""
    accounts = row.get("accounts")
    for a in accounts.values() if isinstance(accounts, dict) else ():
        if isinstance(a, dict) and a.get("ok") is not False:
            continue
        if isinstance(a, dict):
            steps = a.get("actions")
            for text in (a.get("reason"), steps[-1] if isinstance(steps, list) and steps else None):
                if isinstance(text, str) and text:
                    return text[:200]
        return door.CANNOT_CHECK
    return None


def read_tells(lines, mark) -> dict | None:
    """A day's tell-log (store.tells), read to pick the day up again. None when it is not this promotion's day in desk
    mode: no head line, or another mark's. Else:
      replay   the child's events that were answered by it, oldest first: {"line": what it was told, "intents": what
               it answered, "results": the results line or None}
      last     the highest `seq` any line carries (the next event is last + 1: a `seq` is never used twice)
      must     the events the Desk answered: it must still know every one of them
      maybe    the events that carried an order and have no results line (the runner went away in the middle)
      never    the events of which nothing left for the Desk
      flat     the last `flat` a child was told
    An event line with no intents line after it (the child was never heard) is as if it had not been written."""
    head = lines[0] if isinstance(lines, list) and lines else None
    if not isinstance(head, dict) or not head.get("head") or head.get("mark") != list(mark):
        return None
    evs: dict[int, dict] = {}
    last = 0
    for line in lines[1:]:
        seq = line.get("seq")
        if not _int(seq) or seq < 1:
            continue
        last = max(last, seq)
        if "kind" in line or "own" in line:
            own = "own" in line
            evs[seq] = {"line": line, "own": own, "intents": line.get("intents") if own else None, "results": None}
        elif seq in evs and "results" in line:
            evs[seq]["results"] = line               # (a later one, after an exit was asked again, replaces it)
        elif seq in evs and "intents" in line:
            evs[seq]["intents"] = line["intents"]
    must, maybe, either = set(), set(), set()
    replay, flat = [], True
    for seq in sorted(evs):
        e = evs[seq]
        if not isinstance(e["intents"], list):
            continue
        if not e["own"]:
            replay.append(e)
            flat = e["line"].get("flat") is not False
        carried = e["own"] or any(isinstance(i, dict) and i.get("op") in ORDER_OPS for i in e["intents"])
        res = e["results"]
        if res is None:
            if carried:
                maybe.add(seq)
        elif res.get("sent") and res.get("ok"):
            must.add(seq)
        elif res.get("sent"):
            either.add(seq)                          # it left, and no answer came: the Desk may know it or not
    return {"replay": deque(replay), "last": last, "must": must, "maybe": maybe,
            "never": set(range(1, last + 1)) - must - maybe - either, "flat": flat}


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
    before the date, or a function (root, date) that reads them, asked only if the strategy needs them and only when
    its session event fires (default: the tape store). save(summary): called at every state change and else at most
    once a second. late(t0_ns) -> True when a day whose window starts at t0 can no longer be followed in full: it is
    stopped before anything runs. now_ns: the stream's clock as the day is made (the runner's); a day made after its
    window began is `rebuilt` -- made from prints already held, not followed live from its start.

    desk / send / tell / resume: DESK MODE (see that section below). With no `desk` none of it is reached: the day is
    hosted in shadow, as it always was."""

    def __init__(self, record: dict, date: dt.date, *, spawn=None, daily=None, deadline_s: float = DEADLINE_S,
                 start_s: float = START_S, save=None, wall=time.monotonic, late=None, now_ns: int | None = None,
                 desk: DeskSide | None = None, send=None, tell=None, resume=None):
        self.name, self.date, self.sha256 = record.get("name"), date, record.get("sha256")
        self.promoted = record.get("promoted_utc")
        self.state, self.why, self.detail = "waiting", None, None
        self.rebuilt = False                         # made by catch-up (the summary says so)
        self.match: dict | None = None               # the daily match's verdict, once the runner has it
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
        self._desk_init(desk, send, tell, resume, now_ns)     # (desk mode's own fields; nothing is read or sent)
        try:
            self._start(record, spawn or sandboxed, daily if daily is not None else daily_bars, start_s, late, now_ns)
        except _Stop as e:
            self._stopped(str(e), e.detail)
        except Exception as e:  # noqa: BLE001 -- whatever broke, its child must not outlive the attempt
            self._problem(e)
        self._changed()

    # ---- the start
    def _start(self, record: dict, spawn, daily, start_s: float, late, now_ns) -> None:
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
        self.rebuilt = now_ns is not None and now_ns > self._t0
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
        self._root = root
        self._daily = daily if meta["needs_daily"] else None     # read when the session event fires (_session_daily)
        self.fills = ShadowFills(root, self.date, costs_of(record), meta["placement_ms"])
        if self._desk is not None:
            self._desk_start()

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

    def _session_daily(self) -> list:
        """The completed daily bars before the date, for a strategy that needs them: read when its session event
        fires, not when the day was hosted (often 18:00 ET the evening before, before the tick job has stored that
        day). Fail closed: bars that cannot be read, or whose newest is older than the session day before, stop the
        day before the strategy sees anything."""
        if self._daily is None:
            return []
        try:
            bars = self._daily(self._root, self.date) if callable(self._daily) else list(self._daily)
        except OSError as e:
            raise _Stop(NO_DAILY, f"{type(e).__name__}: {e}") from None
        newest = bars[-1].get("date") if bars and isinstance(bars[-1], dict) else None
        if not isinstance(newest, str) or newest < _before(self.date).isoformat():
            raise _Stop(NO_YESTERDAY, f"the newest daily bar is {newest if isinstance(newest, str) else 'none'}")
        return bars

    def _event(self, t: int, _prio, _n, kind: str, arg) -> None:
        if self._desk is not None:                   # desk mode: the orders go to the Desk, nothing is filled here
            return self._desk_event(t, kind, arg)
        daily = self._session_daily() if kind == "session" else None     # (it may stop the day: before anything runs)
        f = self.fills
        f.advance_to(t)
        f.now(t)
        if kind == "session":
            self.state = "running"
        last = f.last_price()
        msg = {"op": "event", "kind": kind, "t_ns": t, "arg": arg, "last_price": last, "flat": f.flat,
               "updates": f.updates()}
        if kind == "session":
            msg["daily"] = daily
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
        if self._desk is not None:
            self._desk_stop(why)

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
            if self._desk is not None:
                self._desk_stop("off")
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
        if self._desk is not None:                   # desk mode: the lead account's real trades, never a model's
            return self._desk.trades()
        return self.fills.trades() if self.fills is not None else []

    @property
    def trade_count(self) -> int:
        if self._desk is not None:
            return len(self._desk.trades())
        return len(self.fills.result.trades) if self.fills is not None else 0

    @property
    def end_ns(self) -> int:
        """The end of the day's window (known once the day has started)."""
        return self._t1

    def summary(self) -> dict:
        """The day summary (contracts.md). `match` is the daily match's verdict, set by the runner; a stopped day
        says it was not checked. `rebuilt` is there (true) only for a day made by catch-up."""
        trades = [{"side": t["side"], "qty": t["qty"], "entry_t": _hms(t["entry_ns"]), "entry_px": t["entry_price"],
                   "exit_t": _hms(t["exit_ns"]), "exit_px": t["exit_price"], "reason": t["exit_reason"], "net": t["net"]}
                  for t in self.trades()]
        why = self.why
        if why is None and self.state in ACTIVE:
            why = NO_STREAM if self._silent else door.PRICES_LATE if self._late.late else None
        verdict = {"ok": None, "text": "Not checked: it was stopped."} if self.state == "stopped" else self.match
        return {"date": self.date.isoformat(), "sha256": self.sha256, "promoted_utc": self.promoted, "state": self.state,
                "why": why, "orders": list(self.orders), "trades": trades,
                "net": round(sum((t["net"] for t in trades), 0.0), 2), "match": verdict, "updated_utc": self._updated,
                **({"rebuilt": True} if self.rebuilt else {}), **(self._desk_summary(why) if self._desk is not None else {})}

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

    # ==================================================================================================================
    # DESK MODE (Step B, task B4). A day whose strategy has accounts on the Desk: the child's orders are SENT to the
    # Desk's guarded intake (labrun/deskclient.py) and the child is told what the Desk says happened (labrun/deskside.py).
    # The Desk is armed. What this section must never do is send an entry twice, or use a `seq` for two events:
    #
    #   * an event's entries leave in ONE request, once. No answer (a timeout, a dropped connection, an error answer)
    #     is written down ("The Desk did not answer.") and the child is told nothing new until the Desk's stream says
    #     what happened. A request is only ever sent again when it carries NO entry -- a cancel, a flatten, the
    #     runner's own stop -- and then with the same `seq` and the same intents, byte for byte: the Desk applies an
    #     identical event at most once (_attempt).
    #   * the exits of an event that also carried an entry, when no answer came, are asked again as a NEW event with a
    #     new `seq` and only those exits (and not at all once the stream shows the first request did arrive). So is an
    #     exit the Desk answered but could not carry out on an account. All of it for RETRY_FOR_S at most.
    #   * a new `seq` is always above every one this day has used AND every one the Desk says it answered (_next_seq),
    #     also for a runner that starts again.
    #   * a runner that starts again feeds a fresh child the tell-log's own inputs and sends NOTHING while it does, and
    #     nothing at all before the Desk's first snapshot of the day is in; what the child answers must equal the log,
    #     and the Desk must know exactly the events the log says it answered -- else "Could not pick up where it left
    #     off." and the day is over.
    #   * once the Desk says the strategy is killed or stopped for today, nothing more is sent for it.
    #
    # ShadowFills still takes the prints, the plots and the lines (the bars are built from its tape) but never an
    # order: no model fill exists in desk mode. `flat`, every fill and every trade come from the Desk (DeskSide).
    # Entries are refused HERE, without a request, when prices are late or the tick stream is silent, when the event is
    # more than 3 s behind the stream's clock, and when the Desk's stream is down or silent; exits still go.
    #
    # The tell-log (store.tell; one JSON line each, appended):
    #   {"head": 1, "strategy", "mark", "date"}                           the day began in desk mode, for this promotion
    #   {"seq", "t_ns", "kind", "arg", "last_price", "flat", "updates"[, "daily"]}    BEFORE the child is asked
    #   {"seq", "intents": [...]}                                         what it answered
    #   {"seq", "sent", "ok", "results": [{"op"[, "id"], "refused", "dead"}]}     only for an event with orders
    #   {"seq", "own": "stop" | "blind" | "again", "intents": [...]}      the runner's own request, then its results line
    # ==================================================================================================================
    def _desk_init(self, desk, send, tell, resume, now_ns) -> None:
        self._desk: DeskSide | None = desk
        self._send = send                            # one event to the Desk, once (DeskClient.send)
        self._tell = tell or (lambda line: None)     # one line to the day's tell-log
        self._born = now_ns or 0                     # the stream's clock as the day was made
        self._seq = 0                                # the last `seq` this day used (every event of the child has one)
        # the day's own tell-log, when the runner is starting again (read before the child is: a day that cannot
        # even start still knows it had begun, and says so to the Desk)
        self._log = read_tells(resume, desk.mark) if desk is not None and resume is not None else None
        self._logged = self._log["last"] if self._log else 0     # the highest `seq` the log held
        self._replay: deque = self._log["replay"] if self._log else deque()   # its events a fresh child is still to be fed
        self._check: dict | None = None              # what the Desk's first snapshot must agree with (read_tells)
        self._mine: set[int] = set()                 # the events THIS process sent
        self._refused_run = 0                        # events in a row whose entries were all refused
        self._retry: list[dict] = []                 # exits the Desk has not taken yet (_again)
        self._keep = False                           # the stop being raised keeps the position (flatten: false)
        self._hush = False                           # the Desk ended the day itself: nothing is sent back
        self._stop_sent = False
        self._blinded = False                        # the entries were cancelled for this spell without prices

    @property
    def mode(self) -> str:
        return "desk" if self._desk is not None else "shadow"

    @property
    def desk(self) -> DeskSide | None:
        return self._desk

    @property
    def begun(self) -> bool:
        """Its child has been asked something today, in this process or the one before."""
        return max(self._seq, self._logged) > 0

    @property
    def start_ns(self) -> int:
        return self._t0

    def _desk_start(self) -> None:
        """The mode, decided once (design D2): desk mode only for a day made before its window began, or picked up
        from its own tell-log. A day made later with nothing to pick up is shadow today: the account starts with the
        next session."""
        side = self._desk
        if self._log is None:
            if self.rebuilt:
                self._desk = None
                return
            self._tell({"head": 1, "strategy": side.desk_id, "mark": list(side.mark), "date": side.date})
            self._log = read_tells([{"head": 1, "mark": list(side.mark)}], side.mark)
        self._check = self._log
        if not side.silent():                        # the Desk's snapshot of this day is in already
            if side.killed or side.stopped is not None:
                return self.desk_says(KILLED if side.killed else STOPPED_TODAY)
            self._desk_verify()

    def _held(self) -> bool:
        """A day picked up from its log sends nothing before the Desk's first snapshot of the day has been checked
        against that log: until then no `seq` is known to be free."""
        return self._check is not None and self._logged > 0

    def _next_seq(self) -> int:
        """A number no event of this day has had: above this day's own, the tell-log's, and the Desk's `answered`."""
        self._seq = max(self._seq, self._logged, max(self._desk.answered, default=0)) + 1
        return self._seq

    def _desk_verify(self) -> None:
        """Once, at the first snapshot of this day: the Desk knows exactly the events the tell-log says it answered.
        One it does not know, or one it knows that the log never sent (the log is behind the Desk): the child here
        and the Desk are not looking at the same day, and nothing more is sent but the stop -- under a `seq` above
        every one the Desk has answered."""
        c = self._check
        if c is None:
            return
        self._check = None
        answered = set(self._desk.answered)
        odd = sorted((c["must"] | c["maybe"]) - answered) or sorted(
            a for a in answered if a not in self._mine and (a in c["never"] or a > c["last"]))
        if odd:
            self._retry = [r for r in self._retry if r["body"] is None]      # (a `seq` picked before this is not safe)
            if self.state in ACTIVE:
                self._keep = True
                self._stopped(NO_RESUME, f"the Desk and the tell-log differ at event {odd[0]}")

    def _halt(self, why: str, detail: str | None = None):
        """Stop for today on the runner's own account: the position keeps its stop (a `stop` with flatten: false)."""
        self._keep = True
        raise _Stop(why, detail)

    def _ask(self, line: dict) -> list:
        """The child's intents for one event, checked as the shadow path checks them."""
        msg = {"op": "event", "kind": line["kind"], "t_ns": line["t_ns"], "arg": line.get("arg"),
               "last_price": line.get("last_price"), "flat": line.get("flat") is not False,
               "updates": line.get("updates") or []}
        if line["kind"] == "session":
            msg["daily"] = line.get("daily")
        intents = self._child.ask(msg, self._deadline).get("intents")
        if not isinstance(intents, list) or not all(well_formed(i) for i in intents):
            raise _Stop(GONE)
        if sum(1 for i in intents if i["op"] in ORDER_OPS) > MAX_ORDERS:
            raise _Stop(TOO_MANY)
        return intents

    def _desk_event(self, t: int, kind: str, arg) -> None:
        if self._replay:
            return self._desk_replay(t, kind)
        side, f = self._desk, self.fills
        daily = self._session_daily() if kind == "session" else None     # (it may stop the day: before anything runs)
        f.advance_to(t)
        f.now(t)
        if kind == "session":
            self.state = "running"
        last = f.last_price()
        seq = self._next_seq()
        line = {"seq": seq, "t_ns": t, "kind": kind, "arg": arg, "last_price": last, "flat": side.flat,
                "updates": side.updates()}
        if kind == "session":
            line["daily"] = daily
        self._tell(line)                             # BEFORE the child is asked
        intents = self._ask(line)
        self._tell({"seq": seq, "intents": intents})
        f.apply([i for i in intents if i["op"] not in ORDER_OPS])        # plots, lines, a skip: never an order
        orders = [i for i in intents if i["op"] in ORDER_OPS]
        if orders:
            side.sent(seq, orders)
            self._desk_orders(seq, t, last, orders)

    def _desk_replay(self, t: int, kind: str) -> None:
        """The runner started again: the next event of the tell-log, fed to the fresh child exactly as it was fed
        before. NOTHING is sent. The day's own schedule must reach the same event, and the child must answer the same
        intents; anything else and the day cannot be picked up."""
        side, f = self._desk, self.fills
        old = self._replay[0]
        line = old["line"]
        if (line.get("t_ns"), line.get("kind")) != (t, kind):
            self._halt(NO_RESUME, f"the log's event {line.get('seq')} is {line.get('kind')} at {line.get('t_ns')}, "
                                  f"the day's is {kind} at {t}")
        self._replay.popleft()
        f.advance_to(t)
        f.now(t)
        if kind == "session":
            self.state = "running"
        seq = self._seq = line["seq"]
        side.told(line.get("updates"))
        try:
            intents = self._ask(line)
        except _Stop as e:
            self._halt(NO_RESUME, f"event {seq}: {e.detail or e}")
        if intents != old["intents"]:
            self._halt(NO_RESUME, f"event {seq}: the strategy asked for something else this time")
        f.apply([i for i in intents if i["op"] not in ORDER_OPS])
        orders = [i for i in intents if i["op"] in ORDER_OPS]
        if not orders:
            return
        side.sent(seq, orders)
        res = old["results"]
        rows = res.get("results") if isinstance(res, dict) else None
        if not isinstance(rows, list) or len(rows) != len(orders):
            rows = [None] * len(orders)
        entries = []
        for it, r in zip(orders, rows):
            if isinstance(r, dict):
                said = r.get("refused") if isinstance(r.get("refused"), str) else None
                if it["op"] == "entry" and r.get("dead") is True:
                    side.dead([it["id"]])
            else:                                    # the runner went away before the answer was written down
                said = NO_ANSWER if it["op"] == "entry" else None
            self.orders.append({"t": _hms(t), "text": words(it, self._tick), "refused": said})
            if it["op"] == "entry":
                entries.append(said)
        self._count(entries)

    def _post(self, body: dict) -> dict:
        """One request, once (DeskClient.send). A line that breaks instead of answering is "no answer": it never
        raises into an event or a stop."""
        try:
            got = self._send(body)
        except Exception as e:  # noqa: BLE001
            log(f"{self.name}: desk: {type(e).__name__}")
            got = None
        return got if isinstance(got, dict) else {"ok": False, "left": True, "status": None, "detail": None}

    def _now_ref(self) -> int:
        """The stream's clock as far as this day knows it: the newest of the clock as last heard, the newest print,
        and the clock as the day was made."""
        return max(self._clock or 0, self._newest or 0, self._born)

    def _body(self, seq: int, t: int, last, intents: list) -> dict:
        """One event as the Desk reads it (homebase/labdesk.py, parse_event). `last_ms`: the time of the print
        `last_price` is."""
        f, side = self.fills, self._desk
        i = bisect_left(f.ts, t) if f is not None and last is not None else 0
        return {"strategy": side.desk_id, "date": side.date, "mark": list(side.mark), "seq": seq, "t_ns": t,
                "state": {"last_price": last, "last_ms": f.ts[i - 1] // 1_000_000 if i else None,
                          "prices_late": bool(last is None or self._late.late or self._silent)},
                "intents": intents}

    def _desk_orders(self, seq: int, t: int, last, orders: list) -> None:
        """The order intents of one event: refuse the entries here when they must not go, send the rest in ONE
        request, write down what the Desk said about each."""
        side, held = self._desk, self._held()
        no = (door.PRICES_LATE if self._late.late or self._silent else TOO_LATE_ONE if self._now_ref() - t > TOO_LATE_NS
              else NOT_ANSWERING if held or side.silent() else None)
        idx = [n for n, it in enumerate(orders) if no is None or it["op"] in EXITS]      # what leaves, by position
        said: list = [no if it["op"] not in EXITS else None for it in orders]            # one sentence an order
        dead = [it["id"] for it in orders if it["op"] == "entry"] if no else []
        rows = [{"t": _hms(t), "text": words(it, self._tick), "refused": None} for it in orders]
        left = ok = False
        again = None                                 # what is to be asked again: (positions, the request or None)
        if idx:
            out = [orders[n] for n in idx]
            body = self._body(seq, t, last, out)
            whole = all(it["op"] in EXITS for it in out)             # no entry in it: it may be sent again as it is
            if held:
                texts, gone, bad = [NO_ANSWER] * len(out), [], list(range(len(out)))
                again = (bad, body)
            else:
                got = self._post(body)
                self._mine.add(seq)
                left, ok = got.get("left") is not False, got.get("ok") is True
                texts, gone, bad = self._desk_answer(out, got)
                if bad:
                    again = (bad, body if whole and not ok else None)
            for n, text in zip(idx, texts):
                said[n] = text
            dead += gone
        side.dead(dead)
        for r, text in zip(rows, said):
            r["refused"] = text
        self.orders += rows

        def write(sent: bool, done: bool) -> None:
            self._tell({"seq": seq, "sent": sent, "ok": done,
                        "results": [{"op": it["op"], **({"id": it["id"]} if "id" in it else {}), "refused": r["refused"],
                                     "dead": it["op"] == "entry" and it["id"] in dead} for it, r in zip(orders, rows)]})
        write(left, ok)
        if again is not None:
            bad, body = again
            self._again([out[n] for n in bad], [rows[idx[n]] for n in bad], body=body, write=write if body else None,
                        first=None if ok or held else seq, left=left, text=None if not ok else texts[bad[0]])
        self._count([text for it, text in zip(orders, said) if it["op"] == "entry"])

    def _desk_answer(self, out: list, got: dict) -> tuple[list, list, list]:
        """What one request's answer means for the intents it carried: (a sentence each, the entries that are dead,
        the positions of the exits that are to be asked again). An entry is dead when the Desk says no account took
        it, or refused the request whole, or no request left at all; with no answer its fate is unknown and nobody
        is told. An exit is asked again when no answer came, or when the Desk could not carry it out on an account."""
        rows = got.get("results")
        exits = [n for n, it in enumerate(out) if it["op"] != "entry" and it["op"] != "oco"]
        if got.get("ok") is True:
            if not (isinstance(rows, list) and len(rows) == len(out) and all(isinstance(r, dict) for r in rows)):
                return [NO_ANSWER if it["op"] == "entry" else None for it in out], [], []
            texts = [desk_sentence(r) if it["op"] == "entry"
                     else (r.get("refused") if isinstance(r.get("refused"), str) else None) if it["op"] == "oco"
                     else exit_trouble(r) for it, r in zip(out, rows)]
            return (texts, [it["id"] for it, r in zip(out, rows) if it["op"] == "entry" and r.get("status") == "cancelled"],
                    [n for n in exits if texts[n] is not None])
        status = got.get("status")
        if got.get("left") is False:
            no, final = NOT_ANSWERING, True          # the key file does not read: nothing left this process
        elif isinstance(status, int) and 400 <= status < 500:
            detail = got.get("detail")               # the Desk refused the request whole: nothing of it was applied
            no = TOO_MANY if status == 429 else detail if status == 409 and isinstance(detail, str) and detail else NOT_ANSWERING
            final = True
        else:
            no, final = NO_ANSWER, False             # sent, no answer: it may be at the Desk or not
        return ([NO_ANSWER if n in exits else no for n in range(len(out))],
                [it["id"] for it in out if it["op"] == "entry"] if final else [], exits)

    def _count(self, entries: list) -> None:
        """Three events in a row whose entries were all refused (here or by the Desk): stopped for today."""
        if not entries:
            return
        if any(text is None for text in entries):
            self._refused_run = 0
            return
        self._refused_run += 1
        if self._refused_run >= REFUSED_RUN:
            self._halt(entries[-1])

    # ---- asking again: only ever a request with no entry in it
    def _again(self, intents: list, rows: list, *, body=None, write=None, first=None, left=False, text=None, what="again",
               then=None, now=False) -> None:
        """Something the Desk has not taken yet: exits (or the runner's own stop), to be asked RETRY_S apart for
        RETRY_FOR_S. `body`: the very request to send again, same `seq`, same intents (it carried no entry and no
        answer came). None: the next try is a NEW event with a new `seq` -- the first request also carried an entry
        (`first`: its `seq`; if the stream shows the Desk answered it, its exits were applied and nothing is sent),
        or the Desk answered and could not carry the exit out on an account (`text`: its sentence).
        rows: the day's order rows of those intents ([] for the runner's own), kept true to the latest word."""
        t = self._wall()
        r = {"intents": intents, "rows": rows, "body": body, "write": write, "first": first, "left": left, "text": text,
             "what": what, "then": then, "until": None if now or self._held() else t + RETRY_FOR_S, "next": t + RETRY_S}
        if not now or self._attempt(r) is not True:
            self._retry.append(r)

    def _attempt(self, r: dict) -> bool | None:
        """One try. True: taken (or no longer needed); False: not yet; None: nothing may be sent just now (_held)."""
        if self._held():
            return None
        if r["until"] is None:
            r["until"] = self._wall() + RETRY_FOR_S
        if r["body"] is None:                        # a new event
            if r["first"] is not None and r["first"] in self._desk.answered:
                self._word(r, None)                  # the first request did reach the Desk: its exits were applied
                return True
            seq = self._next_seq()
            self._tell({"seq": seq, "own": r["what"], "intents": r["intents"]})
            r["body"], r["left"], r["write"] = self._body(seq, self._now_ref(), None, r["intents"]), False, None
        seq = r["body"]["seq"]
        got = self._post(r["body"])                  # the same `seq` and the same intents as the last try of it
        self._mine.add(seq)
        r["left"] = r["left"] or got.get("left") is not False
        texts, _, bad = self._desk_answer(r["intents"], got)
        ok = got.get("ok") is True
        if ok:
            self._word(r, None)
            for n in bad:
                if n < len(r["rows"]):
                    r["rows"][n]["refused"] = texts[n]
            if r["then"] is not None:
                r["then"], then = None, r["then"]
                then()
        self._log_try(r, seq, ok, texts)
        if not ok:
            return False
        if not bad:
            return True
        # answered, and an account could not carry it out: only a NEW event may ask for it again
        r.update(intents=[r["intents"][n] for n in bad], rows=[r["rows"][n] for n in bad if n < len(r["rows"])],
                 body=None, first=None, text=texts[bad[0]], what="again")
        return False

    def _log_try(self, r: dict, seq: int, ok: bool, texts: list) -> None:
        if r["write"] is not None:                   # the event's own results line, written again with the latest word
            r["write"](r["left"], ok)
        else:
            self._tell({"seq": seq, "sent": r["left"], "ok": ok,
                        "results": [{"op": it["op"], **({"id": it["id"]} if "id" in it else {}),
                                     "refused": text if ok else NO_ANSWER, "dead": False}
                                    for it, text in zip(r["intents"], texts)]})

    def _word(self, r: dict, text) -> None:
        for row in r["rows"]:
            row["refused"] = text

    def tend(self) -> None:
        """The runner's idle step: ask again what the Desk has not taken -- a cancel, a flatten, the stop -- once a
        second, for ten seconds. Never an entry. What is still not taken then keeps the last sentence on its row:
        "The Desk did not answer.", or the Desk's own."""
        tried = False
        for r in list(self._retry):
            now = self._wall()
            if now < r["next"]:
                continue
            done = self._attempt(r)
            if done is None:
                continue
            tried = True
            if done or now >= r["until"]:
                self._retry.remove(r)
            else:
                r["next"] = now + RETRY_S
        if tried:
            self._resave()

    def pending(self) -> bool:
        return bool(self._retry)

    def _desk_stop(self, why: str) -> None:
        """This strategy is stopped for today: tell the Desk (it cancels the unfilled entries; with flatten it closes
        the strategy's own position at once). Not when the Desk ended the day itself, and not for a day that never
        began: nothing of it is at the Desk."""
        if self._hush or self._stop_sent or not self.begun or self._send is None:
            return
        self._stop_sent = True
        # (a day still being picked up from its log -- its child did not start, or broke in the replay -- keeps the
        # position whatever the sentence: that is "could not pick up", not the strategy's own doing)
        out = gets_out(why) and not self._keep and not self._replay
        self._again([{"op": "stop", "why": why[:200], "flatten": out}], [], what="stop", now=True)

    def blind(self, seconds: float) -> None:
        """No clock from the tick stream for `seconds`: after BLIND_S with an entry working, every unfilled entry is
        cancelled at the Desk, once for the spell. An open position keeps its broker stop."""
        if self._desk is None or self.state not in ACTIVE:
            return
        if seconds < BLIND_S:
            self._blinded = False
            return
        ids = self._desk.working()
        if self._blinded or not ids:
            return
        self._blinded = True
        self._again([{"op": "cancel", "id": i} for i in ids[:MAX_ORDERS]], [], what="blind", now=True)

    # ---- what the Desk says
    def on_desk(self, snap) -> None:
        """One whole snapshot of this strategy from the Desk's stream."""
        side = self._desk
        if side is None or not side.take(snap):
            return
        if side.killed or side.stopped is not None:
            return self.desk_says(KILLED if side.killed else STOPPED_TODAY)
        self._desk_verify()
        self._changed()

    def desk_says(self, why: str) -> None:
        """The Desk ended this strategy's day itself (killed there; stopped for today: switched off, "Flatten & turn
        off", both entries of a pair filled, ...), in any mode: the child is stopped for today and nothing more is
        sent for it -- no stop, and nothing that was still to be asked again."""
        self._hush = True
        self._retry.clear()
        if self.state in ACTIVE:
            self._stopped(why)
        self._changed(now=True)

    def unbooked(self) -> None:
        """Every account was taken off this strategy on the Desk mid-day (the Desk allows it only when the strategy
        is flat): the desk day is over, and no shadow day takes its place."""
        if self.state in ACTIVE:
            self.state = "done"
            self._end_child()
        self._changed(now=True)

    def leave(self) -> None:
        """The runner is going away on purpose (not a crash): a day that has begun in desk mode is ended at the Desk
        with a stop that keeps the position. The day reads stopped once the Desk has answered it; if it never does,
        the day is left as it is and the next runner picks it up from the tell-log."""
        if self._desk is None or self.state != "running" or self._stop_sent or self._send is None:
            return
        self._stop_sent = True
        self._again([{"op": "stop", "why": STOPPED_TODAY, "flatten": False}], [], what="stop", then=self._left, now=True)

    def _left(self) -> None:
        if self.state in ACTIVE:
            self.state, self.why = "stopped", STOPPED_TODAY
            self._end_child()

    def _desk_summary(self, why) -> dict:
        """What a desk day's summary adds: its mode, the Desk's silence while it lasts, and how many of the lead
        account's trades have no price (the daily match cannot compare those)."""
        out: dict = {"mode": "desk"}
        if why is None and self.state == "running" and self._desk.silent():
            out["why"] = NOT_ANSWERING
        n = self._desk.unpriced()
        if n:
            out["unpriced"] = n
        return out

    def _resave(self) -> None:
        """Write the summary again although its key did not change (a row's sentence did)."""
        self._saved_key = None
        self._changed()

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
    key: tuple                  # the record this day was started from: its code, promotion, settings and size
    fed: int = 0                # how many of the market's prints it has had
    orders: int = 0             # how many of its orders, trades and stops are in the journal (or were catch-up)
    trades: int = 0
    stop: bool = False
    rec: dict | None = None     # ... and the record itself (the daily match runs its code)


@dataclass
class _Match:
    """One day's daily match, from its scheduling to its last answer."""
    rec: dict
    date: dt.date
    trades: list                # the shadow day's trades, the engine's rows
    day: StrategyDay | None     # the day (it keeps the verdict on its later saves), None when read back from its file
    due_ns: int                 # the stream's clock at or after which it starts
    started: int = 0            # ... and the clock it last started at
    tries: int = 0              # answers so far that were "not checked yet" and will be asked again
    running: bool = False
    over: bool = False

    def end(self) -> None:
        """No more tries; the day (its whole session's prints) is let go."""
        self.over, self.day = True, None


def _mark(rec: dict) -> tuple:
    """A promotion: the code and the moment it was promoted (promoting again, even the same code, is a new one)."""
    return (rec.get("sha256"), rec.get("promoted_utc"))


def _key(rec: dict) -> tuple:
    return (*_mark(rec), json.dumps(rec.get("params"), sort_keys=True, default=str), rec.get("qty"))


def _before(d: dt.date) -> dt.date:
    """The weekday before d."""
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def session_today(now_ms: int, root: str | None) -> dt.date | None:
    """The session day the runner is on at that moment for that market, or None when there is none to host: the
    session date of the clock (charts.session.session_date: it rolls at 18:00 ET), never a Saturday's or a Sunday's
    session, and not before that session has begun (a weekend, until Sunday 18:00 ET). The Desk's list reads "today"
    with this same rule (charts/tester_api.py)."""
    d = session_date(now_ms, root)
    return d if d.weekday() < 5 and session_range_ms(d, root)[0] <= now_ms else None


def match_due(date: dt.date, end_ns: int) -> int:
    """When a day's match may start (ns): ten minutes after its window's end, and not before 17:35 ET of the session
    date -- the tick job merges the day's recording into the archive after the close (17:05-17:30 ET), and a backtest
    of the day before that reads a fragment."""
    return max(end_ns + MATCH_AFTER_NS, et_ns(date, MATCH_NOT_BEFORE))


def sized(rec: dict, trades: list) -> dict:
    """The record for a desk day's match: the tester runs at the size the Desk traded (size is set on the Desk, per
    account: a backtest at the record's own size would differ on every trade, by size alone)."""
    qty = trades[0].get("qty") if trades and isinstance(trades[0], dict) else None
    return {**rec, "qty": qty} if _int(qty) and qty > 0 else rec


def _session_ns(d: dt.date, root: str) -> tuple[int, int]:
    """[start, end) of the prints that belong to session d: from its open (18:00 ET the evening before; a weekend's
    prints of a classic market file into Monday) to 18:00 ET on d, where the next session's prints begin."""
    end = int(dt.datetime.combine(d, dt.time(18, 0), ET).timestamp())
    return session_range_ms(d, root)[0] * 1_000_000, end * 1_000_000_000


class Runner:
    """The strategies of the store on the current session's prints. One thread calls everything here: take() with
    what the tick client hands over, sync(), beat() and idle() every few seconds. `at`: the store's root (default
    ~/.homebase/desklab).

    A finished day's match with the tester (labrun/match.py) starts when it is due (match_due: ten minutes after its
    end, never before 17:35 ET of its date), by the stream's clock, in a worker thread of its own (never in the
    09:20-09:35 ET window on a weekday; the worker waits in line for a backtest slot), and its answer is written
    into the day file and the journal by this thread. `matcher(record, date, trades) -> {"ok", "text"}` (default: the
    real tester, in the sandbox); a "not checked yet" is asked again every MATCH_RETRY_NS, MATCH_RETRIES times.

    A market's day is the SESSION date of the stream's clock (charts.session.session_date: it rolls at 18:00 ET, as
    the chart service's tape and the tester's archive do), and the prints held are that session's. While a
    connection is still sending its backlog (`connect` seen, `live` not yet) nothing is hosted, finished or clocked:
    the days only take the prints, in order.

    desk: the runner's line to the Desk (labrun/deskclient.py), only when the process was started with --desk; see
    "the Desk" below. With none -- the default -- no day is ever hosted in desk mode, nothing is sent anywhere and no
    key is read: everything here is what it was before Step B."""

    def __init__(self, *, at=None, source: str = "", spawn=None, deadline_s: float = DEADLINE_S, daily=None,
                 wall=time.monotonic, matcher=None, desk=None):
        self.at, self.source = at, source
        self._spawn, self._deadline, self._daily, self._wall = spawn, deadline_s, daily, wall
        self._matcher = matcher or self._tester
        self._matches: dict[tuple, _Match] = {}      # (name, date, promotion) -> its daily match
        self._results: queue.Queue = queue.Queue()   # the worker threads' answers, read on this thread
        self._swept: set[str] = set()                # the strategies whose past days were looked at for a match
        self._live = False                           # the current connection has sent its whole backlog
        self._clock_ms: int | None = None            # the stream's clock (heard while live)
        self._clock_wall = wall()                    # when (wall) it was last heard
        self._silent = False                         # ... more than SILENT_S ago
        self._dates: dict[str, dt.date] = {}         # root -> its session date
        self._tapes: dict[str, tuple] = {}           # root -> that session's prints: (ts_ns, price, size) arrays
        self._late: dict[str, _Late] = {}
        self._days: dict[str, _Hosted] = {}
        self._final: dict[str, tuple] = {}           # name -> (date, promotion) of a day file found final: never hosted again
        self._roots: list[str] = []                  # the markets the enabled strategies trade
        self._desk = desk                            # the line to the Desk, or None: shadow only
        self._desk_up = False                        # its stream is open
        self._desk_date: str | None = None           # the Desk's own day, as its stream last said
        self._snaps: dict[str, dict] = {}            # desk id -> the Desk's latest snapshot of that strategy
        self._ending: list[StrategyDay] = []         # days no longer hosted whose stop the Desk has not taken yet
        self._said: dict | None = None               # the heartbeat's body, as last built
        self._nap = time.sleep                       # close() waits between two tries of a stop (the tests replace it)

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

    def matching(self) -> int:
        """How many daily matches are out in a worker thread and not yet read."""
        return sum(m.running for m in self._matches.values())

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
        elif self._desk is not None and item[0] in ("desk", "desk_down", "desk_beat"):
            self._on_desk(*item)

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
        self._start_matches(now_ms)

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
        self._collect()
        if self._desk is not None:
            self._desk_idle()

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
        old = _before(_before(d))                    # the matches that are over and more than two sessions old go
        for key, m in list(self._matches.items()):
            if m.over and m.rec["root"] == root and m.date < old:
                del self._matches[key]
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
        if day.state == "done":
            self._plan(h.rec, day.date, match_due(day.date, day.end_ns), day=day)
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
        """Read the store: host each enabled strategy whose market has prints this session (session_today: never a
        Saturday's or a Sunday's session); a strategy that appears, is switched on or was promoted again gets a fresh
        day, fed from the session's prints first (catch-up) -- unless its day file for the date is final (_is_final).
        While a backlog is in flight nothing is hosted or stopped: the tape is not whole yet. The first time a
        strategy is seen, a finished day of today or the session before with no match (or "not checked yet") is
        matched again."""
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
        for rec in recs:
            if rec["name"] not in self._swept:
                self._swept.add(rec["name"])
                self._sweep(rec)
        want = {r["name"]: r for r in recs
                if session_today(self._clock_ms, r["root"]) == self._dates[r["root"]] and self.prints(r["root"])}
        for name, h in list(self._days.items()):
            rec = want.get(name)
            if rec is None:
                h.day.off()
                if h.day.pending():                  # (desk mode: its stop is asked again from idle())
                    self._ending.append(h.day)
                del self._days[name]
            elif _key(rec) != h.key:
                h.day.kill()                         # (its last word is written first)
                del self._days[name]
            elif self._desk is not None and self._rebook(h, rec):
                del self._days[name]                 # (it is hosted afresh just below, in its new mode)
        for name, rec in want.items():
            if name not in self._days and not self._is_final(rec):
                self._host(rec)

    def _day_file(self, rec: dict, date: dt.date) -> dict | None:
        """The date's day file, when it was written for this promotion (store.same_promotion)."""
        try:
            was = store.get_day(rec["name"], date.isoformat(), self.at)
        except (OSError, ValueError):
            return None
        return was if store.same_promotion(was, rec) else None

    def _is_final(self, rec: dict) -> bool:
        """A day file for the date with the SAME promotion (the code and the moment it was promoted) and state
        `done` or `stopped` is final: that strategy is not hosted again for that date and the file is never rewritten
        -- not after a restart, a failure or a late start. Promoted again (even the same code, with other settings or
        size), it starts a fresh day."""
        name, mark = rec["name"], (self._dates[rec["root"]], *_mark(rec))
        if self._final.get(name) == mark:
            return True
        was = self._day_file(rec, mark[0])
        if was is None or was.get("state") not in ("done", "stopped"):
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
                self._too_late(name, date)
                return
            self._write(store.put_day, name, summary)

        if self._desk is not None and self._desk_over(rec, date):
            return                                   # the Desk has ended its day already: no child, in any mode
        # Fail closed: the clock is past the window's start and the prints held begin after it (the stream's backlog
        # is the session from its open; a tape that starts later cannot rebuild the day in full).
        day = StrategyDay(rec, date, spawn=self._spawn, daily=self._daily, deadline_s=self._deadline, save=save,
                          wall=self._wall, late=lambda t0: now > t0 and oldest > t0, now_ns=now,
                          **(self._desk_day(rec, date) if self._desk is not None else {}))
        h = self._days[name] = _Hosted(day, root, _key(rec), fed=len(ts), rec=rec)
        if self._silent:
            day.no_prices(True)
        day.on_ticks(zip(ts, px, size))              # catch-up: the session so far
        day.on_clock(self._clock_ms)
        self._note(h, quiet=True)
        log(f"{name}: {date} {day.state}{' (' + day.why + ')' if day.why else ''}, {h.fed} prints to catch up")

    def _too_late(self, name: str, date: dt.date) -> None:
        """A day file that is not final (waiting, running) cannot be rebuilt: only its state, its `why` and its time
        change; its orders, trades and net stay as they were. A finished or stopped one is left as it is."""
        try:
            was = store.get_day(name, date.isoformat(), self.at)
        except (OSError, ValueError):
            return
        if was is not None and was.get("state") in ACTIVE:
            self._write(store.put_day, name, {**was, "state": "stopped", "why": TOO_LATE, "updated_utc": _utc()})

    # ---- the daily match
    def _plan(self, rec: dict, date: dt.date, due_ns: int, day: StrategyDay | None = None, trades=None) -> None:
        """Schedule the day's match once per promotion."""
        key = (rec["name"], date, *_mark(rec))
        if key not in self._matches:
            self._matches[key] = _Match(rec, date, day.trades() if trades is None else trades, day, due_ns)

    def _sweep(self, rec: dict) -> None:
        """A runner that starts again: a finished day of today or the session before, written for this promotion,
        with no match or "not checked yet", is matched again (from the trades its file holds) -- today's not before
        17:35 ET (match_due)."""
        today = self._dates[rec["root"]]
        match.clean(store.root(self.at) / rec["name"] / "match")
        for date in (today, _before(today)):
            was = self._day_file(rec, date)
            if was is not None and was.get("state") == "done" and (not was.get("match") or match.retry(was["match"])):
                try:
                    trades = match.from_summary(was.get("trades") or [], date)
                except (KeyError, TypeError, ValueError):
                    continue
                if was.get("mode") == "desk":        # a desk day: its trades are real, at the Desk's size
                    if was.get("unpriced"):
                        self._write(store.put_day, rec["name"], {**was, "match": {"ok": None, "text": NO_FILLS},
                                                                 "updated_utc": _utc()})
                        continue
                    self._plan(sized(rec, trades), date, match_due(date, 0), trades=trades)
                    continue
                self._plan(rec, date, match_due(date, 0), trades=trades)

    def _start_matches(self, now_ms: int) -> None:
        """Answers in; then each match that is due starts in a worker thread -- never 09:20-09:35 ET on a weekday,
        and never for a day that was promoted again meanwhile (its file is another promotion's)."""
        self._collect()
        now = now_ms * 1_000_000
        due = [m for m in self._matches.values() if not m.over and not m.running and m.due_ns <= now]
        if not due or slots.in_quiet(dt.datetime.fromtimestamp(now_ms / 1000, ET)):
            return
        for m in due:
            if self._day_file(m.rec, m.date) is None:
                m.end()
                continue
            m.running, m.started = True, now
            if m.day is not None and m.day.mode == "desk" and not self._real_trades(m):
                continue                             # (answered: its fills cannot be compared)
            threading.Thread(target=self._match_run, args=(m,), name="labrun-match", daemon=True).start()

    def _match_run(self, m: _Match) -> None:
        """The worker thread: ask, put the answer where this thread reads it. Nothing else. Whatever happens it puts
        one (a failure reads "not checked yet" and counts as a try), so `running` never stays set."""
        got = {"ok": None, "text": NOT_CHECKED}
        try:
            got = self._matcher(m.rec, m.date, m.trades)
        except BaseException as e:  # noqa: BLE001 -- a bug in the check must not end as a silent thread
            log(f"{m.rec['name']}: match: {type(e).__name__}: {e}")
        finally:
            self._results.put((m, got))

    def _collect(self) -> None:
        while True:
            try:
                m, got = self._results.get_nowait()
            except queue.Empty:
                return
            m.running, day = False, m.day
            if match.retry(got) and m.tries < MATCH_RETRIES:
                m.tries, m.due_ns = m.tries + 1, m.started + MATCH_RETRY_NS
            else:
                m.end()
            was = self._day_file(m.rec, m.date)
            if was is None:                          # promoted again meanwhile: this answer is for another day
                m.end()
                continue
            if day is not None:
                day.match = got                      # (the day's later saves carry it)
            self._write(store.put_day, m.rec["name"], {**was, "match": got, "updated_utc": _utc()})
            self._write(store.journal, m.rec["name"], {"utc": _utc(), "date": m.date.isoformat(), "kind": "match", **got})

    def _tester(self, rec: dict, date: dt.date, trades: list) -> dict:
        return match.match_day(rec, date, trades, base=store.root(self.at) / rec["name"] / "match", archive=ARCHIVE,
                               cache=CACHE, python=sys.executable)

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
        if self._desk is not None:
            self._desk_say()

    def close(self) -> None:
        if self._desk is not None:
            self._desk_leave()
        for h in self._days.values():
            h.day.kill()

    # ---- the Desk (Step B; every method below is reached only when the runner was given a line to it)
    def _book(self, rec: dict) -> list | None:
        """The accounts the Desk's sidecar books for this promotion, when a day may run in desk mode (deskside.booked:
        the sidecar reads, its mark is the record's, its limits read, its book is not empty); else None = shadow."""
        try:
            return booked(store.get_desk(rec["name"], self.at), rec)
        except (OSError, ValueError):
            return None

    def _desk_day(self, rec: dict, date: dt.date) -> dict:
        """What a new day is given to run in desk mode -- {} for shadow. The day itself still falls back to shadow
        when it was made after its window began and has no tell-log of its own to pick up (StrategyDay._desk_start)."""
        accounts = self._book(rec)
        if not accounts:
            return {}
        name, d, mark = rec["name"], date.isoformat(), store.mark_of(rec)
        try:
            lines = store.tells(name, d, self.at) or None
        except (OSError, ValueError):
            lines = None
        was = read_tells(lines, mark)
        side = DeskSide(desk_id(name), mark, d, accounts, wall=self._wall, flat=was["flat"] if was else True)
        snap = self._snaps.get(side.desk_id)
        if snap is not None:
            side.take(snap)
        if not self._desk_up:
            side.down()
        elif snap is None:
            side.heard()
        return {"desk": side, "send": self._desk.send, "resume": lines if was else None,
                "tell": lambda line: self._write(store.tell, name, d, line)}

    def _desk_word(self, rec: dict, date: dt.date) -> str | None:
        """KILLED / STOPPED_TODAY when the Desk's latest snapshot, of THIS day and THIS promotion, says so."""
        snap = self._snaps.get(desk_id(rec["name"])) if self._desk_up else None
        if snap is None or snap.get("date") != date.isoformat() or snap.get("mark") != store.mark_of(rec):
            return None
        return KILLED if snap.get("killed") is True else STOPPED_TODAY if isinstance(snap.get("stopped"), str) else None

    def _desk_over(self, rec: dict, date: dt.date) -> bool:
        """The Desk has ended this strategy's day (killed there, or stopped for today): it is not hosted, the day
        file says so (what an earlier runner wrote of the day stays) and is final."""
        why = self._desk_word(rec, date)
        if why is None:
            return False
        name = rec["name"]
        was = self._day_file(rec, date) or {}
        self._write(store.put_day, name, {
            "date": date.isoformat(), "sha256": rec.get("sha256"), "promoted_utc": rec.get("promoted_utc"),
            "orders": [], "trades": [], "net": 0.0, **was, "state": "stopped", "why": why,
            "match": {"ok": None, "text": "Not checked: it was stopped."}, "updated_utc": _utc()})
        self._write(store.journal, name, {"utc": _utc(), "date": date.isoformat(), "kind": "stop", "why": why, "detail": None})
        self._final[name] = (date, *_mark(rec))
        log(f"{name}: {date} {why} (the Desk): not hosted")
        return True

    def _rebook(self, h: _Hosted, rec: dict) -> bool:
        """The Desk's book for a hosted strategy, read again. True = the day is to be hosted afresh in its other mode,
        which only ever happens to a day that has not begun:
          desk day, accounts still booked        its book is kept up to date (it only decides the lead account)
          desk day, every account taken off      begun: it ends `done` and no shadow day is started for the date;
                                                 not begun: a fresh day, in shadow
          shadow day, an account was assigned    before its window began: a fresh day, in desk mode; after: it stays
                                                 shadow today (the heartbeat says so)"""
        day, accounts = h.day, self._book(rec)
        if day.mode == "desk":
            if accounts:
                day.desk.accounts = accounts
            elif day.state in ACTIVE and day.begun:
                day.unbooked()
                self._note(h)
            elif day.state in ACTIVE:
                day.kill()
                return True
            return False
        if accounts and day.state == "waiting" and self._clock_ms * 1_000_000 <= day.start_ns:
            day.kill()
            return True
        return False

    def _on_desk(self, kind: str, event=None, data=None) -> None:
        """What the Desk's reader and the heartbeat's timer put on the queue (DeskClient)."""
        days = list(self._days.values())
        if kind == "desk_down":
            self._desk_up = False
            for h in days:
                if h.day.desk is not None:
                    h.day.desk.down()
        elif kind == "desk_beat":
            self._desk_advice(event)
        elif isinstance(data, dict):
            self._desk_up = True
            if isinstance(data.get("date"), str):
                self._desk_date = data["date"]
            if event == "state":                     # every Lab strategy on the Desk, whole
                snaps = data.get("strategies")
                self._snaps = {k: v for k, v in snaps.items() if isinstance(v, dict)} if isinstance(snaps, dict) else {}
                for h in days:
                    self._desk_give(h, self._snaps.get(desk_id(h.day.name)))
            else:
                if event == "strategy" and isinstance(data.get("strategy"), str):
                    self._snaps[data["strategy"]] = data
                for h in days:
                    if event == "strategy" and desk_id(h.day.name) == data.get("strategy"):
                        self._desk_give(h, data)
                    elif h.day.desk is not None:
                        h.day.desk.heard()           # the stream is alive

    def _desk_give(self, h: _Hosted, snap) -> None:
        """One strategy's snapshot to its day. A day in desk mode reads all of it (StrategyDay.on_desk); a day in
        shadow only whether the Desk has ended the strategy's day."""
        day = h.day
        if day.desk is not None:
            if snap is None:                         # a whole state that does not list it
                day.desk.heard()
                day.desk.gone()
            else:
                day.on_desk(snap)
        elif day.state in ACTIVE and h.rec is not None:
            why = self._desk_word(h.rec, day.date)
            if why is not None:
                day.desk_says(why)
        self._note(h)

    def _desk_advice(self, answer) -> None:
        """The Desk's answer to a heartbeat: advice. Nothing is ever sent because of it; a child is stopped when it
        says the strategy is killed or stopped -- and only for a day that is the Desk's own day (its stream says
        which that is: a day hosted the evening before is not ended by yesterday's stop)."""
        named = answer.get("strategies") if isinstance(answer, dict) else None
        for h in list(self._days.values()) if isinstance(named, dict) else ():
            said = named.get(desk_id(h.day.name))
            if not isinstance(said, dict) or h.day.state not in ACTIVE or self._desk_date != h.day.date.isoformat():
                continue
            if said.get("killed") is True or isinstance(said.get("stopped"), str):
                h.day.desk_says(KILLED if said.get("killed") is True else STOPPED_TODAY)
                self._note(h)

    def _desk_idle(self) -> None:
        """Every turn of the loop: the cancel when prices are gone, what the Desk has not taken yet, and the
        heartbeat's body said again (the timer posts it only while the runner keeps saying it)."""
        blind = self._wall() - self._clock_wall
        for h in list(self._days.values()):
            if h.day.desk is not None:               # (a shadow day has nothing to ask the Desk)
                h.day.blind(blind)
                h.day.tend()
                self._note(h)
        for day in self._ending:
            day.tend()
        self._ending = [day for day in self._ending if day.pending()]
        if self._said is not None:
            self._desk.say(self._said)

    def _desk_say(self) -> None:
        """The heartbeat's body: every hosted strategy by its desk id, shadow ones too."""
        named = {desk_id(name): {"state": h.day.state, "why": h.day.summary()["why"], "mode": h.day.mode}
                 for name, h in self._days.items()}
        self._said = {"pid": os.getpid(), "strategies": named}
        self._desk.say(self._said)

    def _desk_leave(self) -> None:
        """The runner is going away on purpose: every day that has begun in desk mode is ended at the Desk (a stop
        that keeps the position), asked again for ten seconds at most."""
        days = [h.day for h in self._days.values()] + self._ending
        for day in days:
            day.leave()
        for _ in range(int(RETRY_FOR_S / RETRY_S)):
            if not any(day.pending() for day in days):
                break
            self._nap(RETRY_S)
            for day in days:
                day.tend()

    def _real_trades(self, m: _Match) -> bool:
        """A desk day's match compares the lead account's REAL trades, as they stand when the match starts, with the
        tester run at that account's size. False: a trade has no price -- answered here, the tester is not asked."""
        m.trades = m.day.trades()
        if m.day.desk.unpriced():
            self._results.put((m, {"ok": None, "text": NO_FILLS}))
            return False
        m.rec = sized(m.rec, m.trades)
        return True


def run(charts: str, at=None, desk: str | None = None, desk_key=None) -> None:
    """The process. The client's thread only reads the stream into a queue, so nothing here can make the chart
    service wait for us; this thread does the work, one item at a time.
    desk / desk_key (--desk, --desk-key): the Desk's address and its key file. Only then is a DeskClient made: its
    reader and its heartbeat timer are threads of their own that only ever put on the same queue."""
    inbox: queue.Queue = queue.Queue()
    line = DeskClient(desk, desk_key, inbox.put) if desk else None
    runner = Runner(at=at, source=charts, desk=line)
    runner.sync()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    client = TickClient(charts, runner.roots, inbox.put)
    threading.Thread(target=client.run, args=(stop,), name="labrun-stream", daemon=True).start()
    if line is not None:
        threading.Thread(target=line.run, args=(stop,), name="labrun-desk", daemon=True).start()
        threading.Thread(target=line.beats, args=(stop,), name="labrun-beat", daemon=True).start()
    log(f"up -- {charts}, store {store.root(at)}" + (f", desk {desk}" if desk else ""))
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
