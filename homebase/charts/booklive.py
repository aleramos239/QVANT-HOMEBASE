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
