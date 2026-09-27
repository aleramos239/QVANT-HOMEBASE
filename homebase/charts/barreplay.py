"""Bar Replay, per chart, inside the LIVE chart service (spec 2026-09-27, Part A).

A chart switches into replay: it streams one archived past session on its own, next to live charts that
are unaffected. Over /ws (page -> server):

    {"op": "replay_start", "id", "date": "YYYY-MM-DD", "start_et": "HH:MM", "speed": 1|2|5|10|30|60|"bar",
     "root"?, "spec"?, "studies"?, "fp"?}      # root/spec/studies default to the chart's live subscription
    {"op": "replay_ctl", "id", "action": "play"|"pause"|"step"|"speed"|"jump", "speed"?, "to_et"?: "HH:MM"}
    {"op": "replay_stop", "id"}                 # answers {"type": "reset", "id"}: the page resubscribes live

Server -> page: the normal `history` (cut at the cursor) and `update` messages, flagged "replay": true;
`older` answers too (sessions before the replay day only); {"type": "replay_state", "id", "date",
"cursor_ms", "speed", "playing", "done"} once a second and on every change; a refused op answers
{"type": "replay_error", "id", "op", "error"} (not "error": the page reads that as a refused `sub`).

Isolation: each replay stream belongs to one (connection, chart id) and has its OWN Hub (over its own
History memo): it never touches the live hub, the recorder, the desk link or the quotes -- this module
imports none of them. The cursor is the replay clock: every trade with ts <= cursor has been applied.
`speed` multiplies wall time over tick time; "bar" moves only on `step` (and one bar a second on `play`).
A step advances exactly one bar of the chart's own type. Loading and rebuilding (start, jump, scroll-back)
run off the event loop; playing and stepping only feed ticks already in memory.
"""
from __future__ import annotations

import asyncio
import bisect
import datetime as dt
import re
import time
from dataclasses import dataclass, field

from .bars import BarSpec
from .history import History
from .hub import Hub, Stream
from .session import ET, session_date, session_range_ms
from .store import TickStore
from .studies import make

FIRST_DATE = dt.date(2021, 9, 22)       # the archive's first session
SPEEDS = (1, 2, 5, 10, 30, 60, "bar")
MAX_PER_CONN = 2
MAX_PER_SERVER = 4
MEMO_MAX = 16                           # the replays' own History memo (sessions of bars); cleared when idle
FEED_MAX = 20_000                       # ticks fed per stream per call (pump / op): a big step on a big bar
                                        # (time:86400, tick:1000000) goes on over several pumps, never one freeze
STATE_S = 1.0                           # a replay_state at least this often while a replay exists
BAR_PLAY_S = 1.0                        # speed "bar" + play: one bar per this many wall seconds
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_HHMM = re.compile(r"\d{2}:\d{2}")


def wall_s() -> float:                  # one seam for the service tests (unit tests inject `wall`)
    return time.monotonic()


class Refused(ValueError):
    """A replay op the page asked for that cannot be done; the text is for the page."""


@dataclass
class Replay:
    conn: object
    cid: str
    root: str
    spec: BarSpec
    keys: list
    fp: bool
    date: dt.date
    s0: int
    s1: int
    ticks: list                         # the whole session (one session's buffer), oldest first
    ts: list                            # ticks' ts_ms, for bisect
    info: dict
    hub: Hub = None
    stream: Stream = None
    idx: int = 0                        # ticks[:idx] are applied
    cursor: int = 0
    speed: object = 1
    playing: bool = False
    done: bool = False
    anchor_wall: float = 0.0
    anchor_cursor: int = 0
    last_state: float = 0.0
    last_bar: float = 0.0
    gen: int = 0                        # bumped by every (re)build and by the end: stale scroll-back is dropped
    step_to: int | None = None          # a time step under way: its target cursor
    step_n0: int | None = None          # a tick/volume/range step under way: the closed-bar count it started at
    older_busy: set = field(default_factory=set)

    @property
    def stepping(self) -> bool:
        return self.step_to is not None or self.step_n0 is not None


def _studies_of(live) -> list:
    """A live stream's study keys (read only), in the order a `sub` gives them."""
    keys = list(live.studies)
    if getattr(live, "profile", None) is not None:
        keys.append("profile")
    return keys


class BarReplay:
    def __init__(self, store: TickStore, cache_dir, roots, now_ms, *, min_bar: dict, max_studies: int,
                 wall=None, log=None):
        self.store = store
        # its own memo (never evicts the live charts'), small, and emptied whenever no replay is left
        self.history = History(store, cache_dir=cache_dir, memo_max=MEMO_MAX)
        self.roots = [r.upper() for r in roots]
        self.now_ms = now_ms                                 # the LIVE clock: which sessions are completed
        self.min_bar, self.max_studies = min_bar, max_studies
        self._wall = wall or (lambda: wall_s())
        self._log = log or (lambda m: None)
        self.active: dict[tuple, Replay] = {}
        self.pending: set = set()                            # (conn, cid) being built: counted by the limits
        self.tasks: set = set()

    # ------------------------------------------------------------ queries
    def owns(self, conn, cid: str) -> bool:
        return (conn, cid) in self.active

    def count(self, conn=None) -> int:
        keys = list(self.active) + list(self.pending)
        return len(keys) if conn is None else sum(1 for k in keys if k[0] is conn)

    def cursor(self, conn, cid: str) -> int | None:
        r = self.active.get((conn, cid))
        return None if r is None else r.cursor

    def tick_count(self, conn, cid: str) -> int:
        r = self.active.get((conn, cid))
        return 0 if r is None else len(r.ticks)

    # ------------------------------------------------------------ messages
    def _error(self, conn, cid: str, op: str, text: str) -> None:
        conn.send({"type": "replay_error", "id": cid, "op": op, "error": text})

    def _state(self, r: Replay, **extra) -> None:
        r.last_state = self._wall()
        r.conn.send({"type": "replay_state", "id": r.cid, "date": r.date.isoformat(), "cursor_ms": r.cursor,
                     "speed": r.speed, "playing": r.playing, "done": r.done, **extra})

    def _history(self, r: Replay) -> None:
        r.conn.send({"type": "history", "id": r.cid, **r.stream.payload(r.fp), "replay": True})

    def _flush(self, r: Replay) -> None:
        for (_conn, cid), msg in r.hub.drain():
            r.conn.send({**msg, "id": cid, "replay": True})

    # ------------------------------------------------------------ validation
    def _parse_start(self, msg: dict, live) -> tuple:
        root = msg.get("root") if msg.get("root") is not None else (live.root if live is not None else None)
        spec_key = msg.get("spec") if msg.get("spec") is not None else (live.spec.key if live is not None else None)
        if root is None or spec_key is None:
            raise Refused("replay_start: name a root and spec, or subscribe the chart first")
        root = str(root).upper()
        if root not in self.roots:
            raise Refused(f"{root!r} is not charted (have {', '.join(self.roots)})")
        try:
            spec = BarSpec.parse(spec_key)
        except ValueError as e:
            raise Refused(str(e)) from None
        if spec.size < self.min_bar[spec.kind]:
            raise Refused(f"{spec.key} is too fine for the charts (minimum {spec.kind}:{self.min_bar[spec.kind]})")
        studies = msg.get("studies") if msg.get("studies") is not None else (
            _studies_of(live) if live is not None else [])
        if not isinstance(studies, list) or len(studies) > self.max_studies:
            raise Refused(f"studies: a list of at most {self.max_studies}")
        keys = [str(k) for k in studies]
        for k in keys:
            if k != "profile":
                try:
                    make(k)
                except ValueError as e:
                    raise Refused(str(e)) from None
        date = msg.get("date")
        if not isinstance(date, str) or not _DATE.fullmatch(date):
            raise Refused("date: YYYY-MM-DD")
        try:
            d = dt.date.fromisoformat(date)
        except ValueError:
            raise Refused("date: YYYY-MM-DD") from None
        if d < FIRST_DATE:
            raise Refused(f"the archive starts at {FIRST_DATE.isoformat()}")
        if d >= session_date(self.now_ms(), root):
            raise Refused(f"{d.isoformat()} is not a completed session "
                          f"(replay any archived session from {FIRST_DATE.isoformat()} to yesterday)")
        speed = msg.get("speed", 1)
        self._check_speed(speed)
        start = msg.get("start_et", "09:30")
        cursor = self._at(root, d, start)
        return root, spec, keys, d, speed, cursor, bool(msg.get("fp", True))

    @staticmethod
    def _check_speed(speed) -> None:
        if isinstance(speed, bool) or speed not in SPEEDS:
            raise Refused("speed: 1, 2, 5, 10, 30, 60 or \"bar\"")

    @staticmethod
    def _at(root: str, d: dt.date, hhmm) -> int:
        """ET wall time HH:MM on session d (18:00 and later is the evening before) -> epoch ms."""
        if not isinstance(hhmm, str) or not _HHMM.fullmatch(hhmm):
            raise Refused("time: HH:MM (ET)")
        try:
            t = dt.time.fromisoformat(hhmm)
        except ValueError:
            raise Refused("time: HH:MM (ET)") from None
        day = d - dt.timedelta(days=1) if t >= dt.time(18, 0) else d
        ms = int(dt.datetime.combine(day, t, ET).timestamp() * 1000)
        s0, s1 = session_range_ms(d, root)
        if not s0 <= ms < s1:
            raise Refused(f"{hhmm} ET is outside the {root} session of {d.isoformat()}")
        return ms

    # ------------------------------------------------------------ building (worker thread)
    def _load(self, root: str, d: dt.date):
        sess = self.store.load(root, d)
        if sess is None or not sess.ticks:
            return None
        return sess.ticks, [t.ts_ms for t in sess.ticks], self.history.info(root, d)

    def _build(self, root: str, spec: BarSpec, keys: list, d: dt.date, ticks: list, ts: list, info: dict,
               cursor: int):
        """A private Hub whose today is the replay day, its tape cut at the cursor; the past sessions come
        through Hub.prepare (newest first within the history time budget, as a live subscribe)."""
        idx = bisect.bisect_right(ts, cursor)
        hub = Hub(self.history, lambda: cursor)
        hub.start_today(root, d, ticks[:idx], dict(info))
        return hub, hub.prepare(root, spec, keys), idx

    def _install(self, r: Replay, hub: Hub, prepared, idx: int, cursor: int) -> None:
        """Event loop: swap the replay onto a freshly built hub and send its history."""
        s = hub.attach(prepared)
        r.hub, r.stream, r.idx, r.cursor = hub, s, idx, cursor
        r.gen += 1
        r.step_to = r.step_n0 = None
        r.done = False
        hub.on_clock(cursor)                 # a time bar that ends exactly at the cursor is closed
        self._check_done(r)
        hub.subscribe(s, (r.conn, r.cid))
        s.dirty = False
        self._anchor(r)
        self._history(r)

    # ------------------------------------------------------------ ops
    async def start(self, conn, cid: str, msg: dict, live=None) -> bool:
        """replay_start. `live`: the chart's live Stream, if any (read only: its root/spec/studies are the
        defaults). True once the replay's history is sent -- the caller then takes the chart off the live
        hub (no await in between, so no live update can follow the replay's history)."""
        key = (conn, cid)
        try:
            root, spec, keys, d, speed, cursor, fp = self._parse_start(msg, live)
            others = [k for k in list(self.active) + list(self.pending) if k != key]
            if sum(1 for k in others if k[0] is conn) >= MAX_PER_CONN:
                raise Refused(f"at most {MAX_PER_CONN} replays per page")
            if len(others) >= MAX_PER_SERVER:
                raise Refused(f"at most {MAX_PER_SERVER} replays on the chart service")
        except Refused as e:
            self._error(conn, cid, "replay_start", str(e))
            return False
        replaced = self.active.pop(key, None) is not None   # free the old day BEFORE loading the new one
        self.pending.add(key)
        ok = False
        try:
            loaded = await asyncio.to_thread(self._load, root, d)
            if loaded is None:
                raise Refused(f"no archived {root} session on {d.isoformat()}")
            ticks, ts, info = loaded
            hub, prepared, idx = await asyncio.to_thread(self._build, root, spec, keys, d, ticks, ts, info, cursor)
            ok = True
        except Refused as e:
            self._error(conn, cid, "replay_start", str(e))
        except Exception as e:  # noqa: BLE001 — a failed build answers the page, never kills the socket
            self._log(f"replay_start {cid} ({root} {spec.key} {d}): {type(e).__name__}: {e}")
            self._error(conn, cid, "replay_start", str(e) or type(e).__name__)
        finally:
            self.pending.discard(key)
        if not ok or getattr(conn, "dead", False):
            if replaced:                     # it was replaying and now is not: back to live
                conn.send({"type": "reset", "id": cid})
            self._idle()
            return False
        s0, s1 = session_range_ms(d, root)
        r = Replay(conn, cid, root, spec, keys, fp, d, s0, s1, ticks, ts, info, speed=speed)
        self.active[key] = r
        self._install(r, hub, prepared, idx, cursor)
        self._state(r)
        return True

    async def control(self, conn, cid: str, msg: dict) -> None:
        r = self.active.get((conn, cid))
        if r is None:
            self._error(conn, cid, "replay_ctl", "this chart is not replaying")
            return
        act = msg.get("action")
        try:
            if act == "play":
                if not r.done:
                    self._catch_up(r)
                    r.step_to = r.step_n0 = None     # a step under way gives way to play
                    r.playing = True
                    self._anchor(r)
            elif act == "pause":
                self._catch_up(r)
                r.playing = False
                r.step_to = r.step_n0 = None
            elif act == "step":
                self._catch_up(r)
                r.playing = False
                self._step(r)
            elif act == "speed":
                speed = msg.get("speed")
                self._check_speed(speed)
                self._catch_up(r)
                r.speed = speed
                self._anchor(r)
            elif act == "jump":
                cursor = self._at(r.root, r.date, msg.get("to_et"))
                r.gen += 1                   # scroll-back answers from before the jump are dropped
                hub, prepared, idx = await asyncio.to_thread(
                    self._build, r.root, r.spec, r.keys, r.date, r.ticks, r.ts, r.info, cursor)
                if self.active.get((conn, cid)) is not r:
                    return                   # stopped meanwhile
                self._install(r, hub, prepared, idx, cursor)
            else:
                raise Refused("action: play, pause, step, speed or jump")
        except Refused as e:
            self._error(conn, cid, "replay_ctl", str(e))
            return
        self._flush(r)
        self._state(r)

    def stop(self, conn, cid: str, notify: bool = True) -> bool:
        """replay_stop (notify: tell the page, which resubscribes live on the reset). False: not replaying."""
        r = self.active.pop((conn, cid), None)
        if r is None:
            return False
        r.playing = False
        r.gen += 1                           # an in-flight scroll-back answer is dropped
        if notify:
            self._state(r, stopped=True)
            conn.send({"type": "reset", "id": cid})
        self._idle()
        return True

    def drop_conn(self, conn) -> None:
        for k in [k for k in self.active if k[0] is conn]:
            self.active.pop(k).gen += 1
        self._idle()

    def _idle(self) -> None:
        """No replay left (active or loading): drop the replays' memo of built sessions."""
        if not self.active and not self.pending:
            self.history.clear()

    def ask_older(self, conn, cid: str, before) -> bool:
        """Scroll-back on a replay chart: the live `older` answer, built by the replay's own hub (whose today
        is the replay day, so nothing at or after it). False: this chart is not replaying."""
        r = self.active.get((conn, cid))
        if r is None:
            return False
        if not isinstance(before, int) or isinstance(before, bool):
            conn.send({"type": "older", "id": cid, "before": before, "replay": True,
                       "error": "before: the first bar's time (epoch ms)"})
            return True
        busy = r.gen
        if busy in r.older_busy:
            conn.send({"type": "older", "id": cid, "before": before, "replay": True, "error": "busy"})
            return True
        r.older_busy.add(busy)
        task = asyncio.get_running_loop().create_task(self._older(r, busy, before))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return True

    async def _older(self, r: Replay, gen: int, before: int) -> None:
        hub, stream = r.hub, r.stream
        try:
            ans = await asyncio.to_thread(hub.older, stream, before)
        except Exception as e:  # noqa: BLE001 — the page retries a failed chunk
            ans = {"error": str(e) or type(e).__name__}
        finally:
            r.older_busy.discard(gen)
        if r.gen != gen or self.active.get((r.conn, r.cid)) is not r:
            return                           # stopped or jumped meanwhile: that chart is not there any more
        r.conn.send({"type": "older", "id": r.cid, "before": before, **ans, "replay": True})

    # ------------------------------------------------------------ the clock
    def pump(self) -> None:
        """Called by the service's pump (every 250 ms): advance playing replays, send their updates, and a
        replay_state once a second. One failing replay is paused and told; the others go on."""
        now = self._wall()
        for r in list(self.active.values()):
            try:
                was = (r.done, r.stepping)
                if r.stepping:
                    self._continue_step(r)       # one FEED_MAX slice per pump
                elif r.playing:
                    if r.speed == "bar":
                        if now - r.last_bar >= BAR_PLAY_S:
                            r.last_bar = now
                            self._step(r)
                    else:
                        self._catch_up(r)
                self._flush(r)
                if (r.done, r.stepping) != was or now - r.last_state >= STATE_S:
                    self._state(r)
            except Exception as e:  # noqa: BLE001 — never the live pump's problem
                self._log(f"replay {r.cid} ({r.root} {r.spec.key} {r.date}): {type(e).__name__}: {e}")
                self._error(r.conn, r.cid, "replay_ctl", f"replay stopped: {type(e).__name__}: {e}")
                self.stop(r.conn, r.cid)         # frees its buffer and its place in the limits; page -> live

    def _anchor(self, r: Replay) -> None:
        r.anchor_wall = r.last_bar = self._wall()
        r.anchor_cursor = r.cursor

    def _catch_up(self, r: Replay) -> None:
        """A playing replay at a numeric speed: move the cursor to where the wall clock says it is."""
        if not r.playing or r.speed == "bar":
            return
        self._advance(r, r.anchor_cursor + round((self._wall() - r.anchor_wall) * 1000 * r.speed))

    def _feed(self, r: Replay, upto_ms: int, n0: int | None = None) -> bool:
        """Apply the buffered ticks with ts <= upto_ms, at most FEED_MAX of them (n0: stop once the stream
        holds more than n0 closed bars). True: finished (reached upto_ms, or the bar closed); False: the
        slice ran out first -- the caller goes on at the next pump."""
        s, tape, ticks = r.stream, r.hub.today[r.root], r.ticks
        budget = FEED_MAX
        while r.idx < len(ticks) and ticks[r.idx].ts_ms <= upto_ms:
            if budget <= 0:
                return False
            budget -= 1
            tk = ticks[r.idx]
            r.idx += 1
            tape.append(tk)
            for b in s.builder.add(tk):
                s.commit(b)
            s.dirty = True
            r.cursor = max(r.cursor, tk.ts_ms)
            if n0 is not None and len(s.bars) > n0:
                return True
        return True

    def _advance(self, r: Replay, target_ms: int) -> bool:
        """Move the cursor to target_ms (capped at the session end). False: only part of the way this call."""
        target = min(target_ms, r.s1)
        if target > r.cursor:
            if not self._feed(r, target):
                return False
            r.cursor = target
            r.hub.on_clock(target)
        self._check_done(r)
        return True

    def _check_done(self, r: Replay) -> None:
        """Every trade applied: the cursor goes to the session end, which closes the last time bar."""
        if r.idx >= len(r.ticks) and not r.done:
            r.done, r.playing = True, False
            r.step_to = r.step_n0 = None
            r.cursor = max(r.cursor, r.s1)
            r.hub.on_clock(r.s1)

    def _step(self, r: Replay) -> None:
        """Begin a step: exactly one more closed bar of the chart's own type (fewer only at the session's
        end). It feeds at most FEED_MAX ticks now; a step still under way goes on at every pump."""
        if r.done or r.stepping:
            return
        s = r.stream
        if s.spec.kind == "time":
            n = s.spec.size * 1000
            cur = s.builder.cur
            if cur is None:
                nxt = r.ticks[r.idx].ts_ms
                t = r.s0 + (nxt - r.s0) // n * n
            else:
                t = cur.t
            r.step_to = min(t + n, r.s1)
        else:
            r.step_n0 = len(s.bars)
        self._continue_step(r)

    def _continue_step(self, r: Replay) -> None:
        if r.step_to is not None:
            if self._advance(r, r.step_to):
                r.step_to = None
        elif r.step_n0 is not None:
            if self._feed(r, r.s1, n0=r.step_n0):
                r.step_n0 = None
            self._check_done(r)
