"""BookLive: the live feeds' tracker. Synthetic books and prints only; nothing reads ~/futures_depth."""
from __future__ import annotations

import datetime as dt

from homebase.charts.bookhist import replay_day
from homebase.charts.booklive import RECENT_SAMPLES, BookLive
from homebase.charts.tick import Tick

TICK = 0.25
T0 = int(dt.datetime(2026, 10, 7, 14, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)   # 10:00 ET


def levels(bid, big=None):
    big = big or {}
    return ([[bid - i * TICK, big.get(("b", i), 10)] for i in range(10)],
            [[bid + TICK + i * TICK, big.get(("a", i), 10)] for i in range(10)])


def scenario():
    lines = []
    for s in range(60):
        big = {("b", 2): 300} if 20 <= s < 30 else None
        lines.append((T0 + s * 1000, *levels(100.0, big)))
    ticks = [Tick(T0 + 25_000 + k * 100, 99.5, 160, -1) for k in range(4)]
    return lines, ticks


class Page:
    def __init__(self):
        self.got, self.open = [], True

    def send(self, m):
        self.got.append(m)

    def room(self):
        return self.open


def feed(live, lines, ticks, root="NQ"):
    """Books and prints in time order, a book before a print with the same stamp: the order replay_day uses."""
    i = j = 0
    while i < len(lines) or j < len(ticks):
        if j >= len(ticks) or (i < len(lines) and lines[i][0] <= ticks[j].ts_ms):
            t, b, a = lines[i]
            i += 1
            live.on_book(root, t, b, a)
        else:
            live.on_tick(root, ticks[j])
            j += 1


def collect(page):
    rows, eps = [], {}
    for m in page.got:
        if m["type"] != "bookflow":
            continue
        rows += m["samples"]
        for e in m["episodes"]:
            eps[e["id"]] = e
    return rows, eps


def test_live_equals_the_history_replay_line_for_line():
    lines, ticks = scenario()
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    feed(live, lines, ticks)
    live.flush(T0 + 10 ** 9)                       # the pump's flush after the last second
    rows, eps = collect(page)
    want_rows, want_eps = replay_day(lines, ticks, TICK, finished=False)
    assert rows == want_rows
    assert eps == want_eps
    assert any(e["end"] == "traded" and e["ab"] is not None for e in eps.values())


def test_a_page_is_greeted_with_the_recent_state_and_reset():
    lines, ticks = scenario()
    live = BookLive(lambda r: TICK)
    feed(live, lines, ticks)                       # nobody watching yet
    page = Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    hello = page.got[0]
    assert hello["type"] == "bookflow" and hello["reset"] is True and hello["root"] == "NQ"
    assert len(hello["samples"]) >= 50 and len(hello["samples"]) <= RECENT_SAMPLES
    assert any(e["s"] == "b" and e["p"] == 99.5 for e in hello["episodes"])


def test_two_charts_of_one_page_share_one_stream_and_unview_detaches():
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    live.view((page, "c2"), "NQ", page.send, page.room)
    lines, ticks = scenario()
    feed(live, lines[:15], [])
    n = len([m for m in page.got if m["samples"]])
    live.unview((page, "c1"))
    feed(live, lines[15:20], [])
    assert len([m for m in page.got if m["samples"]]) > n          # c2 still attached: still receiving
    live.drop_conn(page)
    before = len(page.got)
    feed(live, lines[20:25], [])
    assert len(page.got) == before


def test_session_roll_finishes_the_old_trackers_open_levels():
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    for s in range(20):
        live.on_book("NQ", T0 + s * 1000, *levels(100.0, {("b", 2): 300} if s >= 11 else None))
    (ep_id, ep), = [(k, v) for k, v in collect(page)[1].items() if v["p"] == 99.5]
    assert ep["end"] == "open" and ep["t1"] is None            # shown once 3 s old, still standing
    live.on_book("NQ", T0 + 8 * 3_600_000, *levels(101.0))     # 18:00 ET: the next session
    done = collect(page)[1][ep_id]
    assert done["end"] == "faded" and done["t1"] is not None


def test_a_broken_feed_never_raises():
    logs = []
    live = BookLive(lambda r: TICK, log=logs.append)
    live.on_book("NQ", T0, None, None)             # not lists
    live.on_tick("NQ", object())                   # not a Tick
    assert logs and "book flow (NQ)" in logs[0]


def test_a_print_before_the_first_book_is_harmless_and_the_feed_goes_on():
    live, page = BookLive(lambda r: TICK), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    live.on_tick("NQ", Tick(T0 - 500, 100.0, 3, 1))              # no book yet
    lines, ticks = scenario()
    feed(live, lines, ticks)
    live.flush(T0 + 10 ** 9)
    rows, eps = collect(page)
    assert len(rows) == 60 and any(e["end"] == "traded" for e in eps.values())


def test_an_empty_or_crossed_book_line_is_not_a_fault_and_the_feed_goes_on():
    logs = []
    live, page = BookLive(lambda r: TICK, log=logs.append), Page()
    live.view((page, "c1"), "NQ", page.send, page.room)
    lines, ticks = scenario()
    feed(live, lines[:10], [])
    live.on_book("NQ", T0 + 10_000, [], [])                                    # an empty book
    live.on_book("NQ", T0 + 11_000, [[100.5, 10]], [[100.0, 10]])              # crossed
    feed(live, lines[12:], ticks)
    live.flush(T0 + 10 ** 9)
    assert logs == []
    rows, eps = collect(page)
    assert len(rows) == 60 and any(e["end"] == "traded" for e in eps.values())


def test_a_failing_feed_logs_once_per_root_and_kind_a_minute():
    logs, now = [], [1000.0]
    live = BookLive(lambda r: TICK, log=logs.append, clock=lambda: now[0])
    for i in range(50):                                   # a broken book line every 250 ms
        now[0] += 0.25
        live.on_book("NQ", T0 + i, None, None)
    assert len(logs) == 1
    live.on_tick("NQ", object())                          # another kind of failure of the same root: its own line
    live.on_book("ES", T0, None, None)                    # another root: its own line
    assert len(logs) == 3
    now[0] += 61
    live.on_book("NQ", T0 + 99, None, None)               # a minute later: logged again
    assert len(logs) == 4 and "book flow (NQ)" in logs[-1]
