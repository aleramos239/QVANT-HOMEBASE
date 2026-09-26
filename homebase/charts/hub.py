"""The live chart engine. One Stream per (root, bar type), shared by every
chart showing it. A Stream is built from past sessions (History) plus
today's tape, then advanced tick by tick. The server's pump calls
on_clock()/drain() every 250 ms, so a chart gets at most 4 updates a
second however fast the tape. Each subscriber keeps its own cursor (bars
already sent), so a chart that joins mid-stream never gets a bar twice.

Threading: prepare() does the heavy part (history + today's bars from a
snapshot of the tape) in a worker thread; attach() runs on the event loop,
catches up the ticks that arrived meanwhile, and registers the stream.
Everything else runs on the event loop only.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..contracts import tick_size
from .bars import Bar, BarBuilder, BarSpec
from .history import History
from .session import session_date
from .studies import Profile, make
from .tick import BUY, SideClassifier, Tick, from_row

HISTORY_MAX = 20_000    # a history message carries at most this many bars: the most recent


def sessions_back(spec: BarSpec) -> int:
    """Completed sessions loaded behind today, per bar type."""
    if spec.kind != "time" or spec.size < 60:
        return 1
    if spec.size <= 300:
        return 3
    if spec.size <= 3600:
        return 10
    return 60


@dataclass
class Stream:
    root: str
    spec: BarSpec
    tick_size: float
    builder: BarBuilder
    bars: list = field(default_factory=list)       # closed bars, oldest first
    studies: dict = field(default_factory=dict)    # key -> Study
    values: dict = field(default_factory=dict)     # key -> [value per closed bar]
    profile: Profile | None = None
    sessions: list = field(default_factory=list)   # [{date, contract, source, approx, gaps}]
    subs: dict = field(default_factory=dict)       # (conn, chart_id) -> bars already sent
    dirty: bool = False
    reset: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.root, self.spec.key)

    def commit(self, b: Bar) -> None:
        self.bars.append(b)
        for k, st in self.studies.items():
            self.values[k].append(st.push(b))
        if self.profile is not None:
            self.profile.push(b)

    def add_study(self, key: str) -> None:
        if key == "profile":
            if self.profile is None:
                self.profile = Profile(self.tick_size)
                for b in self.bars:
                    self.profile.push(b)
            return
        if key in self.studies:
            return
        st = make(key)
        self.studies[key] = st
        self.values[key] = [st.push(b) for b in self.bars]

    def payload(self, fp: bool = True) -> dict:
        """The history message: the most recent HISTORY_MAX bars, every
        study's values sliced to match. A subscriber's cursor is still
        len(self.bars), so its updates continue where this ends."""
        ts, live = self.tick_size, self.builder.cur
        first = max(0, len(self.bars) + (live is not None) - HISTORY_MAX)
        bars = [b.wire(ts, fp) for b in self.bars[first:]]
        if live is not None:
            bars.append(live.wire(ts, fp))
        studies = {k: self.values[k][first:] + ([st.preview(live)] if live is not None else [])
                   for k, st in self.studies.items()}
        return {"root": self.root, "spec": self.spec.key, "tick_size": ts, "bars": bars,
                "live": live is not None, "studies": studies,
                "profile": self.profile.value(live) if self.profile is not None else None,
                "sessions": self.sessions}

    def update_since(self, cursor: int) -> dict:
        ts, live = self.tick_size, self.builder.cur
        msg = {"type": "update", "closed": [b.wire(ts) for b in self.bars[cursor:]],
               "live": live.wire(ts) if live is not None else None,
               "studies": {k: {"closed": self.values[k][cursor:],
                               "live": st.preview(live) if live is not None else None}
                           for k, st in self.studies.items()}}
        if self.profile is not None:
            msg["profile"] = self.profile.value(live)
        return msg


@dataclass
class Prepared:
    root: str
    spec: BarSpec
    stream: Stream
    tape: list | None      # the today-list object the snapshot was taken from (None: no tape yet)
    upto: int               # how many of its ticks the snapshot covered
    today_date: dt.date | None   # self.today_date[root] read at the TOP of prepare() (torn-read guard)


class Hub:
    def __init__(self, history: History, now_ms):
        self.history = history
        self.store = history.store
        self.now_ms = now_ms
        self.today: dict[str, list[Tick]] = {}
        self.today_date: dict[str, dt.date] = {}
        self.today_info: dict[str, dict] = {}
        self.clf: dict[str, SideClassifier] = {}
        self.streams: dict[tuple[str, str], Stream] = {}

    # ------------------------------------------------------------ today's tape
    def start_today(self, root: str, d: dt.date, ticks: list[Tick], info: dict | None = None) -> None:
        """(Re)seed today's session for root: at startup, after a refill.
        Streams of root are reset (the page resubscribes and rebuilds)."""
        self.today[root] = list(ticks)
        self.today_date[root] = d
        self.today_info[root] = info or {"date": d.isoformat(), "contract": None,
                                         "source": "live", "approx": False, "gaps": []}
        last = ticks[-1] if ticks else None
        self.clf[root] = SideClassifier(last.price if last else None, last.side if last else BUY)
        for s in self.streams.values():
            if s.root == root:
                s.reset = True

    def on_ticks(self, root: str, rows: list[dict]) -> None:
        if not rows:
            return
        if root not in self.clf:
            self.start_today(root, session_date(int(rows[0]["ts_ms"])), [])
        streams = [s for s in self.streams.values() if s.root == root]
        for r in rows:
            d = session_date(int(r["ts_ms"]))
            if d < self.today_date[root]:
                continue        # an older session's straggler: charts only roll FORWARD
            if d > self.today_date[root]:               # 18:00 roll: the old session is on disk
                info = dict(self.today_info[root], date=d.isoformat(), gaps=[])
                self.today[root] = []
                self.today_date[root] = d
                self.today_info[root] = info
                self.clf[root] = SideClassifier()        # a reload starts each session fresh too
                self.history.clear()
                for s in streams:
                    s.sessions.append(info)
            tk = from_row(r, self.clf[root])
            self.today[root].append(tk)
            for s in streams:
                for b in s.builder.add(tk):
                    s.commit(b)
                s.dirty = True

    def on_clock(self, now_ms: int) -> None:
        for s in self.streams.values():
            for b in s.builder.on_clock(now_ms):
                s.commit(b)
                s.dirty = True

    # ------------------------------------------------------------ streams
    def prepare(self, root: str, spec: BarSpec, study_keys: list[str]) -> Prepared:
        """Worker thread: past sessions + today's bars from a snapshot of the tape."""
        ts = tick_size(root)
        today_date = self.today_date.get(root)
        today = today_date or session_date(self.now_ms())
        s = Stream(root, spec, ts, BarBuilder(spec, ts))
        for d in [d for d in self.store.sessions(root) if d < today][-sessions_back(spec):]:
            s.bars.extend(self.history.bars(root, spec, d))
            s.sessions.append(self.history.info(root, d))
        tape = self.today.get(root)              # None: root has no tape yet (not [] — see attach)
        upto = len(tape) if tape else 0
        if tape is not None:
            for tk in tape[:upto]:
                s.bars.extend(s.builder.add(tk))
        info = self.today_info.get(root)
        if info:
            s.sessions.append(info)
        for k in study_keys:
            s.add_study(k)
        return Prepared(root, spec, s, tape, upto, today_date)

    def attach(self, p: Prepared) -> Stream:
        """Event loop: register (or reuse) the stream, catching up the ticks
        that arrived while prepare() ran."""
        existing = self.streams.get((p.root, p.spec.key))
        if existing is not None:
            return existing
        s = p.stream
        tape = self.today.get(p.root)
        if tape is not p.tape or self.today_date.get(p.root) != p.today_date:
            s.reset = True                 # reseeded, rolled, or torn mid-prepare: resubscribe
        elif tape is not None:
            for tk in tape[p.upto:]:
                for b in s.builder.add(tk):
                    s.commit(b)
        self.streams[s.key] = s
        return s

    def subscribe(self, s: Stream, sub: tuple) -> None:
        s.subs[sub] = len(s.bars)

    def unsubscribe(self, sub: tuple) -> None:
        for k, s in list(self.streams.items()):
            if s.subs.pop(sub, None) is not None and not s.subs:
                del self.streams[k]

    def drop_conn(self, conn) -> None:
        for k, s in list(self.streams.items()):
            for sub in [x for x in s.subs if x[0] is conn]:
                del s.subs[sub]
            if not s.subs:
                del self.streams[k]

    def drain(self) -> list[tuple[tuple, dict]]:
        """(subscriber, message) for everything that changed since the last drain."""
        out: list[tuple[tuple, dict]] = []
        for k, s in list(self.streams.items()):
            if s.reset:
                del self.streams[k]
                out.extend((sub, {"type": "reset"}) for sub in s.subs)
                continue
            n = len(s.bars)
            if not s.dirty and all(c == n for c in s.subs.values()):
                continue
            built: dict[int, dict] = {}
            for sub, c in list(s.subs.items()):
                if c not in built:
                    built[c] = s.update_since(c)
                out.append((sub, built[c]))
                s.subs[sub] = n
            s.dirty = False
        return out
