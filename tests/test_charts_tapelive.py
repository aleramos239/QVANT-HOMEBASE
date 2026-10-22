"""TapeLive: the session tape to the pages that opened the Time & Sales panel, from a fake hub.today list."""
from __future__ import annotations

import datetime as dt
import json

from homebase.charts.tapelive import RESET_ROWS, TapeLive
from homebase.charts.tick import Tick

D = dt.date(2026, 10, 21)
T0 = 1_792_000_000_000


def tk(i):
    return Tick(T0 + i * 10, 25000.0 + i * 0.25, 1 + i % 3, 1 if i % 2 else -1, i)


class Page:
    def __init__(self):
        self.got, self.open = [], True

    def send(self, m):
        self.got.append(m)

    def room(self):
        return self.open


def setup(n=10, recent=3):
    today = {"NQ": [tk(i) for i in range(n)]}
    live = TapeLive(lambda r: today.get(r), lambda r: D if r in today else None, recent=recent)
    page = Page()
    live.view((page, "tape"), "nq", page.send, page.room)
    return today, live, page


def test_first_view_greets_with_the_recent_rows():
    today, live, page = setup()
    assert page.got == [{"type": "tape", "root": "NQ", "s": "2026-10-21", "i0": 7, "rows": today["NQ"][7:],
                         "reset": True}]
    # a Tick is a tuple: the socket's json writes the row as [ts_ms, price, size, side, id]
    assert json.loads(json.dumps(page.got[0]))["rows"][0] == [tk(7).ts_ms, 25001.75, 2, 1, 7]
    live.flush()
    assert len(page.got) == 1                   # nothing new: nothing sent


def test_growth_sends_only_the_new_rows():
    today, live, page = setup()
    today["NQ"] += [tk(10), tk(11)]
    live.flush()
    assert page.got[1] == {"type": "tape", "root": "NQ", "s": "2026-10-21", "i0": 10, "rows": [tk(10), tk(11)]}
    today["NQ"].append(tk(12))
    live.flush()
    assert page.got[2]["i0"] == 12 and page.got[2]["rows"] == [tk(12)]
    assert len(page.got) == 3


def test_a_swapped_list_resets():
    today, live, page = setup()
    today["NQ"] = [tk(i) for i in range(100, 105)]     # a refill's reseed / the 18:00 roll
    live.flush()
    assert page.got[1] == {"type": "tape", "root": "NQ", "s": "2026-10-21", "i0": 2, "rows": today["NQ"][2:],
                           "reset": True}
    today["NQ"].append(tk(105))
    live.flush()
    assert page.got[2]["i0"] == 5 and page.got[2]["rows"] == [tk(105)]


def test_a_backlog_past_reset_rows_resets():
    today, live, page = setup()
    today["NQ"] += [tk(i) for i in range(10, 10 + RESET_ROWS)]
    live.flush()
    assert page.got[1]["i0"] == 10 and len(page.got[1]["rows"]) == RESET_ROWS and "reset" not in page.got[1]
    n = len(today["NQ"])
    today["NQ"] += [tk(i) for i in range(n, n + RESET_ROWS + 1)]
    live.flush()
    assert page.got[2]["reset"] is True
    assert page.got[2]["i0"] == n + RESET_ROWS + 1 - 3 and page.got[2]["rows"] == today["NQ"][-3:]


def test_no_tape_yet_then_one():
    today = {}
    live = TapeLive(lambda r: today.get(r), lambda r: D if r in today else None, recent=3)
    page = Page()
    live.view((page, "tape"), "NQ", page.send, page.room)
    assert page.got == [{"type": "tape", "root": "NQ", "s": None, "i0": 0, "rows": [], "reset": True}]
    live.flush()
    assert len(page.got) == 1
    today["NQ"] = [tk(0), tk(1)]
    live.flush()
    assert page.got[1] == {"type": "tape", "root": "NQ", "s": "2026-10-21", "i0": 0, "rows": [tk(0), tk(1)],
                           "reset": True}


def test_unview_stops_sends():
    today, live, page = setup()
    live.unview((page, "tape"))
    today["NQ"].append(tk(10))
    live.flush()
    assert len(page.got) == 1
    live.unview((page, "tape"))                 # twice is fine
    live.view((page, "tape"), "NQ", page.send, page.room)
    assert page.got[1]["reset"] is True and page.got[1]["i0"] == 8


def test_a_page_switching_root_leaves_the_old_one():
    today, live, page = setup()
    today["ES"] = [tk(50)]
    live.view((page, "tape"), "ES", page.send, page.room)
    assert page.got[1] == {"type": "tape", "root": "ES", "s": "2026-10-21", "i0": 0, "rows": [tk(50)], "reset": True}
    live.view((page, "tape"), "es", page.send, page.room)   # the same root again: nothing
    today["NQ"].append(tk(10))
    today["ES"].append(tk(51))
    live.flush()
    assert [m["root"] for m in page.got[2:]] == ["ES"]


def test_drop_conn_cleans_up():
    today, live, page = setup()
    other = Page()
    live.view((other, "tape"), "NQ", other.send, other.room)
    live.drop_conn(page)
    today["NQ"].append(tk(10))
    live.flush()
    assert len(page.got) == 1
    assert other.got[1]["rows"] == [tk(10)]     # the other page still gets the tape
    live.drop_conn(other)
    assert live._viewers == {} and live._fans == {} and live._seen == {}
    live.drop_conn(other)                       # a conn never seen is fine


def test_a_page_with_no_room_is_resynced_with_a_hello():
    today, live, page = setup(recent=3)
    page.open = False
    for i in range(10, 40):                     # past PAGE_QUEUE_MAX flushes while the socket is full
        today["NQ"].append(tk(i))
        live.flush()
    assert len(page.got) == 1
    page.open = True
    live.flush()
    assert page.got[1]["reset"] is True and page.got[1]["rows"] == today["NQ"][-3:]
    assert page.got[-1]["rows"][-1] == tk(39)


def test_the_ws_op_through_the_service(tmp_path):
    """{"op": "tape"} on the real /ws: the hello, then a live tick's row from the pump; a page that never sends
    the op sees no tape; null closes it."""
    from fastapi.testclient import TestClient

    from tests.charts_util import D as DAY, rows, session_ms, write_archive
    from tests.test_charts_desk_server import BASE_URL, WS_HOST, QuietFeed, live_app
    from tests.test_charts_server import next_of

    write_archive(tmp_path / "ticks", "NQ", DAY, "NQZ6", rows(session_ms(DAY, 9, 29), [100.0, 100.25, 100.5]))
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c, \
            c.websocket_connect("/ws", headers=WS_HOST) as ws, c.websocket_connect("/ws", headers=WS_HOST) as quiet:
        ws.send_json({"op": "tape", "root": "nq"})
        m = next_of(ws, "tape")
        assert m["root"] == "NQ" and m["s"] == DAY.isoformat() and m["reset"] is True
        assert m["i0"] == 0 and [r[1] for r in m["rows"]] == [100.0, 100.25, 100.5]
        quiet.send_json({"op": "sub", "id": "a", "root": "NQ", "spec": "time:60"})
        next_of(quiet, "history")
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(DAY, 9, 40), [101.0, 101.25], first_id=9)))
        m = next_of(ws, "tape")
        assert "reset" not in m and m["i0"] == 3
        assert m["rows"] == [[session_ms(DAY, 9, 40), 101.0, 1, 1, 9], [session_ms(DAY, 9, 40) + 1000, 101.25, 1, 1, 10]]
        seen = []
        while not any(x.get("type") == "update" for x in seen):
            seen.append(quiet.receive_json())
        assert not any(x.get("type") == "tape" for x in seen)
        ws.send_json({"op": "tape", "root": None})
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(DAY, 9, 41), [102.0], first_id=11)))
        # the pump sends tape before quotes: the closed view's first frame after the tick is its quote
        assert ws.receive_json()["type"] == "quote"
