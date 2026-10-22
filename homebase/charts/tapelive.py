"""Time & Sales: the session tape to every page that opened the panel, straight from the hub's today list.

The tick path does no extra work: hub.on_ticks appends to hub.today[root] as before, and the pump calls flush() after
hub.drain(), which sends each watched root's new rows (<= 4 messages a second). A refill's reseed and the 18:00 roll
replace that list (hub.start_today / on_ticks), so the next flush sends a fresh hello with the recent rows (reset);
so does a backlog past RESET_ROWS. Opt-in: a page that never sends {"op": "tape"} gets nothing, and a root nobody
watches costs nothing. Never blocks: desk.Fanout's bounded outbox.

Message: {"type": "tape", "root", "s": the session date, "i0": the session index of rows[0], "rows": [[ts_ms, price,
size, side, id], ...], "reset"?: true}. A row is the hub's Tick itself (a tuple: send_json writes it as that list).
"""
from __future__ import annotations

from typing import Callable, Hashable, Optional

from .desk import Fanout

RECENT = 2000          # rows a page is greeted with
RESET_ROWS = 4000      # a backlog past this goes out as a fresh hello instead (peak ES is ~1,500 rows a flush)
PAGE_QUEUE_MAX = 16    # messages held per page per root before it is resynced to a hello


class _Seen:
    """What flush last saw of one root's tape: the list object, and how many of its rows every page has."""
    def __init__(self, tape: Optional[list]):
        self.tape = tape
        self.sent = len(tape) if tape is not None else 0


class TapeLive:
    def __init__(self, tape_of: Callable[[str], Optional[list]], session_of: Callable[[str], object],
                 recent: int = RECENT, maxlen: int = PAGE_QUEUE_MAX):
        self.tape_of, self.session_of = tape_of, session_of
        self.recent, self.maxlen = recent, maxlen
        self._fans: dict[str, Fanout] = {}
        self._seen: dict[str, _Seen] = {}
        self._viewers: dict[Hashable, str] = {}

    # ---- pages

    def message(self, root: str, i0: int, rows: list, reset: bool = False) -> dict:
        d = self.session_of(root)
        m = {"type": "tape", "root": root, "s": d.isoformat() if d is not None else None, "i0": i0, "rows": rows}
        if reset:
            m["reset"] = True
        return m

    def hello(self, root: str) -> dict:
        """The recent rows up to what every page has (the shared cursor), so a greeting never skips a row."""
        seen = self._seen[root]
        i0 = max(0, seen.sent - self.recent)
        return self.message(root, i0, (seen.tape or [])[i0:seen.sent], reset=True)

    def view(self, key: Hashable, root: str, send: Callable[[dict], None], room: Callable[[], bool]) -> None:
        root = root.upper()
        if self._viewers.get(key) == root:
            return
        self.unview(key)
        self._viewers[key] = root
        fan = self._fans.get(root)
        if fan is None:
            self._seen[root] = _Seen(self.tape_of(root))
            fan = self._fans[root] = Fanout(hello=lambda r=root: self.hello(r), maxlen=self.maxlen)
        fan.attach(key, send, room)

    def unview(self, key: Hashable) -> None:
        root = self._viewers.pop(key, None)
        if root is None:
            return
        self._fans[root].detach(key)
        if root not in self._viewers.values():      # the last page left: flush() stops reading this tape
            del self._fans[root], self._seen[root]

    def drop_conn(self, conn) -> None:
        for key in [k for k in self._viewers if k[0] is conn]:
            self.unview(key)

    # ---- the pump

    def flush(self) -> None:
        for root, fan in list(self._fans.items()):
            t = self.tape_of(root)
            seen = self._seen[root]
            n = len(t) if t is not None else 0
            if t is not seen.tape or n - seen.sent > RESET_ROWS:
                self._seen[root] = _Seen(t)
                fan.publish(self.hello(root))
            elif n > seen.sent:
                i0, seen.sent = seen.sent, n
                fan.publish(self.message(root, i0, t[i0:n]))
            else:
                fan.flush()                      # a page that had no room earlier gets what waited
