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
import time
from dataclasses import dataclass, field

from ..contracts import point_value, tick_size
from .bars import Bar, BarBuilder, BarSpec
from .history import History
from .session import session_date
from .studies import Profile, make
from .tick import BUY, SideClassifier, Tick, from_row

HISTORY_MAX = 20_000    # a history message carries at most this many bars: the most recent
BUILD_BUDGET_S = 2.0    # a subscribe or scroll-back chunk spends at most this long BUILDING sessions that
                        # are not already cached (a cold 1-minute cache, from raw ticks, is slow -- see
                        # warm.py). Past the budget it stops asking for more and answers with what it has:
                        # a subscribe (sessions_back can be 250, for a daily chart) or a scroll-back chunk
                        # must never block the connection until every session is built, only until it can
                        # answer. Checked between sessions, never mid-build, so one still-building session
                        # is always finished and included.


def sessions_back(spec: BarSpec) -> int:
    """Completed sessions loaded behind today, per bar type; also the size of one scroll-back chunk."""
    if spec.kind != "time" or spec.size < 60:
        return 1
    if spec.size <= 300:
        return 5
    if spec.size <= 3600:
        return 20
    return 250


def warm_bars(key: str) -> int:
    """How many bars after a join a study's value still depends on the bars before it: a window's length, or
    long enough for an EMA's (5n) / a Wilder ADX's (10n) memory to fade below e^-10. 0: the study restarts
    every session (VWAP, cumulative delta, levels)."""
    name, _, n = str(key).partition(":")
    n = int(n) if n.isdecimal() else 0
    return {"sma": n, "vwma": n, "ema": 5 * n, "adx": 10 * n}.get(name, 0)


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
    partial: bool = False   # prepare() hit BUILD_BUDGET_S before loading every completed session it wanted;
                            # the page should ask `older` right away rather than wait for the user to scroll

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
        return {"root": self.root, "spec": self.spec.key, "tick_size": ts, "point_value": point_value(self.root),
                "bars": bars, "live": live is not None, "studies": studies,
                "profile": self.profile.value(live) if self.profile is not None else None,
                "sessions": self.sessions, "partial": self.partial}

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
            self.start_today(root, session_date(int(rows[0]["ts_ms"]), root), [])
        streams = [s for s in self.streams.values() if s.root == root]
        for r in rows:
            d = session_date(int(r["ts_ms"]), root)
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
        """Worker thread: past sessions + today's bars from a snapshot of the tape. sessions_back(spec) can
        be 250 (a daily chart); building a session that is not already cached reads and parses its raw
        ticks, which is slow. BUILD_BUDGET_S bounds how long this spends on sessions still to be built, so
        a cold subscribe answers with what it managed rather than blocking the connection until every
        session is built. It walks NEWEST first, so a budget cutoff always drops sessions off the OLD end,
        never the new one -- the result is always a contiguous block ending at the latest completed session
        (built oldest-to-newest into the stream once decided). The sessions left out are exactly what
        scroll-back (`older`) is for; s.partial says so, so the page can ask for them right away instead of
        waiting for the user to scroll."""
        ts = tick_size(root)
        today_date = self.today_date.get(root)
        today = today_date or session_date(self.now_ms(), root)
        s = Stream(root, spec, ts, BarBuilder(spec, ts, root))
        dates = [d for d in self.store.sessions(root) if d < today][-sessions_back(spec):]
        newest_first = list(reversed(dates))
        t0 = time.monotonic()
        chunks = []
        for i, d in enumerate(newest_first):
            chunks.append((self.history.bars(root, spec, d), self.history.info(root, d)))
            if i + 1 < len(newest_first) and time.monotonic() - t0 > BUILD_BUDGET_S:
                break        # the OLDER remainder stays unloaded: at least one session is always built
        for bars_d, info_d in reversed(chunks):     # oldest first again, for the stream's own order
            s.bars.extend(bars_d)
            s.sessions.append(info_d)
        s.partial = len(chunks) < len(newest_first)
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

    def stream_of(self, sub: tuple) -> Stream | None:
        """The stream a chart (conn, chart id) is subscribed to."""
        return next((s for s in self.streams.values() if sub in s.subs), None)

    def older(self, s: Stream, before_ms: int) -> dict:
        """Worker thread: scroll-back. The next chunk of COMPLETED sessions strictly before before_ms (the
        page's first bar), newest first, until sessions_back(spec) sessions or HISTORY_MAX bars (a session
        that does not fit gives its newest bars; the next request continues before them), or BUILD_BUDGET_S
        of building sessions that are not already cached -- past it, this stops and answers with the chunk
        so far (done can still be False: the page just asks again for the rest, instead of this call
        blocking the connection on a cold chunk). Built as a history message's bars are, but never
        memoized. Its studies run over it from a fresh start, as a history message's do, then on across the
        join through the page's first bars for as long as a study remembers what came before ("repair": the
        page overwrites those values). done: nothing older is left. Never today's session."""
        root, spec = s.root, s.spec
        keys = list(s.studies)
        today = self.today_date.get(root) or session_date(self.now_ms(), root)
        cut = session_date(before_ms, root)
        dates = [d for d in self.store.sessions(root) if d < today]
        back = [d for d in dates if d <= cut]
        chunk: list[Bar] = []
        infos: list[dict] = []
        taken, trimmed, i = 0, False, len(back)
        t0 = time.monotonic()
        while i > 0 and taken < sessions_back(spec) and len(chunk) < HISTORY_MAX:
            if taken and time.monotonic() - t0 > BUILD_BUDGET_S:
                break        # at least one session is always built; the rest is the next `older` request's
            i -= 1
            bs = [b for b in self.history.bars(root, spec, back[i], memo=False) if b.t < before_ms]
            if not bs:
                continue
            room = HISTORY_MAX - len(chunk)
            if len(bs) > room:
                bs, trimmed = bs[-room:], True
            chunk[:0] = bs
            infos.insert(0, self.history.info(root, back[i]))
            taken += 1
        # across the join: the page's first bars, as far as a study still remembers the chunk, and all of a
        # session the chunk ends inside (VWAP and cumulative delta restart only at a session's open)
        ahead: list[Bar] = []
        if chunk:
            mid = chunk[-1].session == cut.isoformat()
            rest = [b for b in self.history.bars(root, spec, cut, memo=False) if b.t >= before_ms] if mid else []
            span = min(max(len(rest), max((warm_bars(k) for k in keys), default=0)), HISTORY_MAX)
            for d in (x for x in dates if x >= cut):
                if len(ahead) >= span:
                    break
                ahead.extend(b for b in self.history.bars(root, spec, d, memo=False) if b.t >= before_ms)
            ahead = ahead[:span]
        studies, repair = {}, {}
        for k in keys:
            st = make(k)
            studies[k] = [st.push(b) for b in chunk]
            repair[k] = [st.push(b) for b in ahead]
        return {"bars": [b.wire(s.tick_size) for b in chunk], "studies": studies, "repair": repair,
                "sessions": infos, "done": i == 0 and not trimmed}

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
