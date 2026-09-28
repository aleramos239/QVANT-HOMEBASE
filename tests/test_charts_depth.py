"""Level 2 (spec 2026-09-27 charts-depth, Part A): the book, the DOM
subscriptions on the tick feed's md socket, the fan-out to pages, the
recorder. The chart service side is in test_charts_depth_server.py. Fakes
only: no broker, no tokens, nothing written under ~/futures_ticks."""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import threading
from pathlib import Path

import pytest

from homebase import symbols
from homebase.charts import depth as depth_mod
from homebase.charts.depth import (BOOK_LEVELS, DEPTH_ARCHIVE, Book, Depth, DepthRecorder, parse_roots,
                                   read_depth)
from homebase.charts.store import ARCHIVE
from homebase.charts.tickfeed import TickFeed
from tests.charts_util import D, ET, session_ms

NQ, ES = symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")
T0 = session_ms(D, 9, 45)


# ------------------------------------------------------------------ fakes

class FakeWS:
    """The md socket: answers md/subscribeDOM with a subscriptionId (the
    contractId every DOM push carries), unless told to refuse."""

    def __init__(self, ids=None):
        self.connected = True
        self.event_handlers = []
        self.sent = []
        self.ids = dict(ids or {NQ: 111, ES: 222})
        self.refuse: dict[str, Exception | dict] = {}

    async def request(self, ep, body=""):
        self.sent.append((ep, body))
        sym = body.get("symbol") if isinstance(body, dict) else None
        why = self.refuse.get(sym)
        if isinstance(why, Exception):
            raise why
        if isinstance(why, dict):
            return why
        if ep == "md/subscribeDOM":
            return {"mode": "RealTime", "subscriptionId": self.ids.get(sym, 999)}
        return {}

    async def close(self):
        self.connected = False

    def push(self, cid, bids, offers, ts="2026-09-24T13:45:00.000Z"):
        for h in list(self.event_handlers):
            h({"e": "md", "d": {"doms": [{"contractId": cid, "timestamp": ts,
                                           "bids": [{"price": p, "size": s} for p, s in bids],
                                           "offers": [{"price": p, "size": s} for p, s in offers]}]}})


class FakeFeed:
    def __init__(self, ws=None):
        self.ws = ws
        self.contracts = {}
        self.counted = 0

    def count_request(self):
        self.counted += 1


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Page:
    """One browser connection: what the depth fan-out sent it."""

    def __init__(self):
        self.got = []

    def send(self, msg):
        self.got.append(msg)

    @staticmethod
    def room():
        return True

    def depth(self, root=None):
        return [m for m in self.got if m.get("type") == "depth" and m.get("ts") is not None
                and (root is None or m["root"] == root)]


def ladder(best, n, step=0.25, down=True, size=5):
    return [(best - i * step if down else best + i * step, size + i) for i in range(n)]


def make(record=("NQ", "ES"), ws=None, recorder=None, clock=None, wall=None):
    feed = FakeFeed(FakeWS() if ws is None else ws)
    clock = clock or Clock()
    d = Depth(feed, record, recorder=recorder, now=clock, wall_ms=wall or (lambda: T0))
    return feed, d, clock


def run(coro):
    return asyncio.run(coro)


async def connect(d):
    """One step: sees the socket, sends the subscriptions, waits for their answers."""
    d.step()
    await d.settle()


def subs(ws, ep="md/subscribeDOM"):
    return [b["symbol"] for e, b in ws.sent if e == ep]


# ------------------------------------------------------------------ Book

def test_book_replaces_on_every_snapshot_best_first_and_capped():
    b = Book("NQ")
    b.apply({"timestamp": "2026-09-24T13:45:00.250Z",
             "bids": [{"price": 99.5, "size": 3}, {"price": 100.0, "size": 7}, {"price": 99.75, "size": 1}],
             "offers": [{"price": 100.5, "size": 2}, {"price": 100.25, "size": 4}]}, now=1.0, wall_ms=0)
    assert b.bids == [[100.0, 7], [99.75, 1], [99.5, 3]]            # best (highest) bid first
    assert b.offers == [[100.25, 4], [100.5, 2]]                     # best (lowest) offer first
    assert b.ts == int(dt.datetime(2026, 9, 24, 13, 45, 0, 250000, dt.timezone.utc).timestamp() * 1000)
    b.apply({"timestamp": "2026-09-24T13:45:01Z", "bids": [{"price": 101.0, "size": 1}], "offers": []},
            now=2.0, wall_ms=0)
    assert b.bids == [[101.0, 1]] and b.offers == []                 # replaced, not merged
    big = {"bids": [{"price": 1000 - i, "size": 1} for i in range(45)],
           "offers": [{"price": 2000 + i, "size": 1} for i in range(45)]}
    b.apply(big, now=3.0, wall_ms=12345)
    assert len(b.bids) == len(b.offers) == BOOK_LEVELS == 30
    assert b.ts == 12345                                             # no timestamp: the wall clock
    assert b.bids[0] == [1000, 1] and b.offers[0] == [2000, 1]


def test_book_of_is_every_level_best_first_as_copies_or_none():
    """fast-paper: the paper book's read of the DOM -- all BOOK_LEVELS, never the wire's 20, and nothing it can change."""
    _, d, _ = make()
    assert d.book_of("NQ") is None                                   # no book (not subscribed, or the socket went)
    b = d.books["NQ"] = Book("NQ")
    assert d.book_of("NQ") is None                                   # a book that never had a snapshot
    b.apply({"timestamp": "2026-09-24T13:45:00.250Z",
             "bids": [{"price": 1000 - i * 0.25, "size": 2} for i in range(25)],
             "offers": [{"price": 1000.25 + i * 0.25, "size": 3} for i in range(25)]}, now=1.0, wall_ms=0)
    got = d.book_of("NQ")
    assert got["ts_ms"] == b.ts and len(got["bids"]) == len(got["offers"]) == 25
    assert got["bids"][0] == [1000.0, 2] and got["offers"][0] == [1000.25, 3]
    got["bids"][0][1] = 99
    got["offers"].clear()
    assert b.bids[0] == [1000.0, 2] and len(b.offers) == 25


def test_book_skips_malformed_levels():
    b = Book("NQ")
    b.apply({"bids": [{"price": "x", "size": 1}, {"price": 10.0, "size": 0}, {"price": 9.75},
                      {"price": float("nan"), "size": 2}, {"price": 9.5, "size": 4}, "junk"],
             "offers": None}, now=1.0, wall_ms=5)
    assert b.bids == [[9.5, 4]] and b.offers == []


def test_the_spec_values():
    m = depth_mod
    assert (m.BOOK_LEVELS, m.WIRE_LEVELS, m.REC_LEVELS) == (30, 20, 10)
    assert (m.WIRE_MIN_S, m.REC_MIN_S) == (0.1, 0.25)               # <= 10 msgs/s, <= 4 lines/s per root
    assert (m.LINGER_S, m.RETRY_S, m.FLUSH_S) == (60, 600, 30)
    assert m.GZIP_LEVEL == 6


def test_parse_roots_from_the_env_value():
    assert parse_roots(None) == ("NQ", "ES")
    assert parse_roots("nq, gc ,,") == ("NQ", "GC")
    assert parse_roots("") == ()


# ------------------------------------------------------------------ contractId -> root

def test_dom_events_route_to_a_root_by_the_subscription_contract_id():
    async def go():
        feed, d, _ = make()
        await connect(d)
        ws = feed.ws
        assert ws.event_handlers == [d.on_event]
        ws.push(111, ladder(100.0, 3), ladder(100.25, 3, down=False))
        ws.push(222, ladder(50.0, 2), ladder(50.25, 2, down=False))
        ws.push(999, ladder(1.0, 2), ladder(1.25, 2, down=False))       # not ours
        return d
    d = run(go())
    assert d.books["NQ"].bids[0] == [100.0, 5] and d.books["ES"].bids[0] == [50.0, 5]
    assert set(d.books) == {"NQ", "ES"}


def test_a_reply_without_a_subscription_id_is_a_refusal_retried_in_10_minutes():
    async def go():
        feed, d, clock = make(record=("NQ",))
        feed.ws.refuse[NQ] = {"mode": "RealTime"}              # no subscriptionId: nothing to bind
        await connect(d)
        st = d.status()["NQ"]
        assert not st["subscribed"] and "subscriptionId" in st["error"]
        feed.ws.push(4242, ladder(100.0, 2), ladder(100.25, 2, down=False))
        assert "NQ" not in d.books                              # never bound by guesswork
        feed.ws.refuse.clear()
        clock.t += 599
        await connect(d)
        assert subs(feed.ws) == [NQ]
        clock.t += 1
        await connect(d)
        assert subs(feed.ws) == [NQ, NQ] and d.status()["NQ"]["subscribed"]
    run(go())


def test_a_penalty_reply_is_a_refusal_that_waits_at_least_its_p_time():
    async def go():
        feed, d, clock = make(record=("NQ", "ES"))
        feed.ws.refuse[NQ] = {"p-ticket": "tk", "p-time": 900}     # longer than the 10-min retry
        feed.ws.refuse[ES] = {"p-ticket": "tk2", "p-time": 5}      # shorter: the 10-min retry rules
        await connect(d)
        st = d.status()
        assert not st["NQ"]["subscribed"] and "p-ticket" in st["NQ"]["error"]
        assert not st["ES"]["subscribed"] and "p-ticket" in st["ES"]["error"]
        feed.ws.refuse.clear()
        clock.t += 600
        await connect(d)
        assert subs(feed.ws) == [NQ, ES, ES]
        clock.t += 299
        await connect(d)
        assert subs(feed.ws) == [NQ, ES, ES]
        clock.t += 1
        await connect(d)
        assert subs(feed.ws) == [NQ, ES, ES, NQ] and d.status()["NQ"]["subscribed"]
    run(go())


# ------------------------------------------------------------------ subscriptions

def test_record_roots_are_subscribed_on_the_feeds_socket_without_spending_chart_budget():
    async def go():
        feed, d, _ = make()
        await connect(d)
        await connect(d)                                  # a second step asks nothing twice
        return feed, d
    feed, d = run(go())
    assert subs(feed.ws) == [NQ, ES]
    assert feed.counted == 0                              # subscribeDOM is not a getChart
    st = d.status()
    assert st["NQ"]["subscribed"] and st["ES"]["subscribed"] and st["NQ"]["error"] is None


def test_the_real_tick_feeds_budget_is_untouched():
    async def go():
        tf = TickFeed(["NQ"], lambda *a: None)
        tf.ws = FakeWS()
        d = Depth(tf, ("NQ", "ES"), now=Clock(), wall_ms=lambda: T0)
        await connect(d)
        return tf
    tf = run(go())
    assert subs(tf.ws) == [NQ, ES] and tf.budget_used() == 0


def test_demand_subscribes_and_the_last_viewer_leaving_unsubscribes_after_60s():
    async def go():
        clock = Clock()
        feed, d, _ = make(record=("NQ",), ws=FakeWS({NQ: 111, symbols.resolve_contract("GC"): 333}),
                          clock=clock)
        await connect(d)
        p = Page()
        d.view((p, "a"), "GC", p.send, p.room)
        await connect(d)
        gc = symbols.resolve_contract("GC")
        assert subs(feed.ws) == [NQ, gc]
        d.unview((p, "a"))
        clock.t += 59
        await connect(d)
        assert subs(feed.ws, "md/unsubscribeDOM") == []            # still lingering
        d.view((p, "b"), "GC", p.send, p.room)                     # back within the linger
        d.unview((p, "b"))
        clock.t += 59
        await connect(d)
        assert subs(feed.ws, "md/unsubscribeDOM") == []            # the linger restarted
        clock.t += 1
        await connect(d)
        assert subs(feed.ws, "md/unsubscribeDOM") == [gc]
        assert subs(feed.ws) == [NQ, gc]                           # never subscribed twice
        # a recorded root stays subscribed with nobody watching it
        d.view((p, "c"), "NQ", p.send, p.room)
        d.drop_conn(p)
        clock.t += 600
        await connect(d)
        assert subs(feed.ws, "md/unsubscribeDOM") == [gc]
        st = d.status()
        assert st["NQ"]["subscribed"] and ("GC" not in st or not st["GC"]["subscribed"])
    run(go())


def test_everything_is_resubscribed_after_the_md_socket_reconnects():
    async def go():
        feed, d, clock = make(record=("NQ",))
        p = Page()
        d.view((p, "a"), "ES", p.send, p.room)
        await connect(d)
        old = feed.ws
        assert sorted(subs(old)) == sorted([NQ, ES])
        old.connected = False                          # the socket died...
        await connect(d)
        assert not d.status()["NQ"]["subscribed"]
        feed.ws = FakeWS()                              # ...and the feed reconnected
        await connect(d)
        assert sorted(subs(feed.ws)) == sorted([NQ, ES])
        assert feed.ws.event_handlers == [d.on_event]
        feed.ws.push(111, ladder(100.0, 2), ladder(100.25, 2, down=False))
        assert d.status()["NQ"]["subscribed"] and d.books["NQ"].bids
        assert len(subs(old)) == 2                      # nothing more went to the dead socket
    run(go())


def test_a_refused_subscription_is_an_error_retried_every_10_minutes():
    async def go():
        feed, d, clock = make(record=("NQ", "ES"))
        feed.ws.refuse[ES] = RuntimeError("md/subscribeDOM failed: status=403 data=Access is denied")
        feed.ws.refuse[NQ] = {"errorText": "no depth entitlement"}
        await connect(d)
        st = d.status()
        assert "Access is denied" in st["ES"]["error"] and not st["ES"]["subscribed"]
        assert "no depth entitlement" in st["NQ"]["error"]
        clock.t += 599
        await connect(d)
        assert subs(feed.ws) == [NQ, ES]                 # not asked again yet
        feed.ws.refuse.clear()
        clock.t += 1
        await connect(d)
        assert subs(feed.ws) == [NQ, ES, NQ, ES]
        st = d.status()
        assert st["ES"]["subscribed"] and st["ES"]["error"] is None
    run(go())


def test_a_refused_root_is_asked_again_at_once_on_a_reconnect():
    async def go():
        feed, d, clock = make(record=("ES",))
        feed.ws.refuse[ES] = RuntimeError("md/subscribeDOM failed: status=403")
        await connect(d)
        assert d.status()["ES"]["error"]
        feed.ws = FakeWS()                                  # the feed reconnected 1 s later
        clock.t += 1
        await connect(d)
        assert subs(feed.ws) == [ES]
        assert d.status()["ES"]["subscribed"] and d.status()["ES"]["error"] is None
    run(go())


def et_ms(h, m):
    return int(dt.datetime.combine(D, dt.time(h, m), ET).timestamp() * 1000)


def test_no_retry_or_new_demand_subscription_inside_the_0920_0935_quiet_window():
    async def go():
        wall = [et_ms(9, 19)]
        gc = symbols.resolve_contract("GC")
        feed, d, clock = make(record=("NQ", "ES"), ws=FakeWS({NQ: 111, ES: 222, gc: 333}),
                              wall=lambda: wall[0])
        feed.ws.refuse[ES] = RuntimeError("md/subscribeDOM failed: status=403")
        await connect(d)                                     # 09:19: both asked, ES refused
        assert subs(feed.ws) == [NQ, ES]
        feed.ws.refuse.clear()
        wall[0] = et_ms(9, 20)
        p = Page()
        d.view((p, "a"), "GC", p.send, p.room)               # new demand in the window
        clock.t += 600                                        # ES's retry falls due in the window
        await connect(d)
        assert subs(feed.ws) == [NQ, ES]
        # a reconnect inside the window re-subscribes what was subscribed, and nothing else
        feed.ws = FakeWS({NQ: 111, ES: 222, gc: 333})
        wall[0] = et_ms(9, 30)
        await connect(d)
        assert subs(feed.ws) == [NQ]
        wall[0] = et_ms(9, 34) + 59_000
        await connect(d)
        assert subs(feed.ws) == [NQ]
        wall[0] = et_ms(9, 35)                               # deferred to 09:35
        await connect(d)
        assert sorted(subs(feed.ws)) == sorted([NQ, ES, gc])
    run(go())


def test_a_reconnect_sends_viewers_an_empty_book():
    async def go():
        feed, d, clock = make(record=("NQ",))
        p = Page()
        d.view((p, "a"), "NQ", p.send, p.room)
        await connect(d)
        feed.ws.push(111, ladder(100.0, 3), ladder(100.25, 3, down=False))
        assert p.got[-1]["bids"]
        feed.ws.connected = False                             # the socket dropped: the book is stale
        clock.t += 1
        await connect(d)
        return p
    p = run(go())
    assert p.got[-1] == {"type": "depth", "root": "NQ", "ts": None, "bids": [], "offers": []}


def test_shutdown_cancels_the_subscribe_requests_in_flight(tmp_path):
    async def go():
        rec = DepthRecorder(tmp_path / "depth")
        feed, d, _ = make(record=("NQ",), recorder=rec)
        hung = asyncio.Event()

        async def never(ep, body=""):
            hung.set()
            await asyncio.Event().wait()                     # a request with no answer
        feed.ws.request = never
        d.step()
        await hung.wait()
        await asyncio.wait_for(d.aclose(), 2)
        return d
    d = run(go())
    assert not d._tasks


def test_a_dead_socket_during_subscribe_is_not_a_refusal():
    async def go():
        feed, d, _ = make(record=("NQ",))

        async def dying(ep, body=""):
            feed.ws.connected = False
            raise RuntimeError("websocket not connected")
        feed.ws.request = dying
        await connect(d)
        return d
    d = run(go())
    assert d.status()["NQ"]["error"] is None and not d.status()["NQ"]["subscribed"]


def test_no_socket_no_requests():
    async def go():
        feed = FakeFeed(None)
        d = Depth(feed, ("NQ",), now=Clock(), wall_ms=lambda: T0)
        await connect(d)
        return d
    d = run(go())
    assert d.status()["NQ"]["subscribed"] is False


# ------------------------------------------------------------------ fan-out

def test_fanout_is_coalesced_to_10_per_second_per_root_latest_book_wins():
    async def go():
        feed, d, clock = make(record=())
        p = Page()
        d.view((p, "a"), "NQ", p.send, p.room)
        await connect(d)
        start = clock.t
        for i in range(100):                             # 100 snapshots in one second
            clock.t = start + i * 0.01
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False))
            d.step()
        clock.t = start + 1.0
        d.step()
        return p
    p = run(go())
    msgs = p.depth("NQ")
    assert 10 <= len(msgs) <= 11                        # [start, start+1] inclusive of both ends
    assert msgs[-1]["bids"][0][0] == 199.0               # the last book was delivered, not dropped
    assert all(len(m["bids"]) == len(m["offers"]) == 20 for m in msgs)
    assert set(msgs[0]) == {"type", "root", "ts", "bids", "offers"}


def test_a_coalesced_book_goes_out_when_its_window_opens():
    async def go():
        feed, d, clock = make(record=())
        p = Page()
        d.view((p, "a"), "NQ", p.send, p.room)
        await connect(d)
        start = clock.t
        feed.ws.push(111, ladder(100.0, 2), ladder(100.25, 2, down=False))
        clock.t = start + 0.03
        feed.ws.push(111, ladder(101.0, 2), ladder(101.25, 2, down=False))
        clock.t = start + 0.06
        feed.ws.push(111, ladder(102.0, 2), ladder(102.25, 2, down=False))
        clock.t = start + 0.08
        d.step()
        n_early = len(p.depth())
        clock.t = start + 0.1
        d.step()
        return n_early, p
    n_early, p = run(go())
    assert n_early == 1
    assert [m["bids"][0][0] for m in p.depth()] == [100.0, 102.0]


def test_depth_only_reaches_pages_with_a_chart_on_that_root():
    async def go():
        feed, d, clock = make(record=())
        nq, es, both = Page(), Page(), Page()
        d.view((nq, "a"), "NQ", nq.send, nq.room)
        d.view((es, "a"), "ES", es.send, es.room)
        d.view((both, "a"), "NQ", both.send, both.room)
        d.view((both, "b"), "ES", both.send, both.room)
        await connect(d)
        feed.ws.push(111, ladder(100.0, 2), ladder(100.25, 2, down=False))
        feed.ws.push(222, ladder(50.0, 2), ladder(50.25, 2, down=False))
        d.unview((both, "b"))                             # its ES chart closed
        clock.t += 1
        feed.ws.push(222, ladder(51.0, 2), ladder(51.25, 2, down=False))
        return nq, es, both
    nq, es, both = run(go())
    assert {m["root"] for m in nq.depth()} == {"NQ"}
    assert {m["root"] for m in es.depth()} == {"ES"} and len(es.depth()) == 2
    assert [m["root"] for m in both.depth()] == ["NQ", "ES"]


def test_a_slow_page_is_never_waited_on_and_resyncs_to_the_latest_book():
    async def go():
        feed, d, clock = make(record=())
        slow, fast = Page(), Page()
        open_ = [False]
        d.view((slow, "a"), "NQ", slow.send, lambda: open_[0])
        d.view((fast, "a"), "NQ", fast.send, fast.room)
        await connect(d)
        for i in range(30):
            clock.t += 0.2
            feed.ws.push(111, ladder(100.0 + i, 2), ladder(100.25 + i, 2, down=False))
        assert len(fast.depth()) == 30 and slow.depth() == []
        open_[0] = True
        d.step()
        return slow
    slow = run(go())
    got = slow.depth()
    assert 1 <= len(got) <= 4 and got[-1]["bids"][0][0] == 129.0


# ------------------------------------------------------------------ recorder

def rec_setup(tmp_path, record=("NQ",)):
    rec = DepthRecorder(tmp_path / "depth")
    feed, d, clock = make(record=record, recorder=rec)
    return rec, feed, d, clock


def test_recording_is_capped_at_4_lines_a_second_top10_only(tmp_path):
    async def go():
        rec, feed, d, clock = rec_setup(tmp_path)
        await connect(d)
        start = clock.t
        for i in range(20):                                # every 50 ms, every book different
            clock.t = start + i * 0.05
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False),
                         ts=f"2026-09-24T13:45:{i // 20:02d}.{(i * 50) % 1000:03d}Z")
            d.step()
        clock.t = start + 0.99
        d.step()
        await d.aflush()
        return rec
    rec = run(go())
    p = rec.path("NQ", D, NQ)
    lines = read_depth(p)
    assert len(lines) == 4
    assert all(len(ln["b"]) == len(ln["a"]) == 10 and set(ln) == {"t", "b", "a"} for ln in lines)
    assert lines[0]["b"][0] == [100.0, 5] and isinstance(lines[0]["t"], int)


def test_only_a_changed_top10_is_recorded(tmp_path):
    async def go():
        rec, feed, d, clock = rec_setup(tmp_path)
        await connect(d)
        for i in range(8):
            clock.t += 1
            deep = ladder(100.0, 10) + [(90.0, 100 + i)]  # only level 11 changes
            feed.ws.push(111, deep, ladder(100.25, 10, down=False))
            d.step()
        clock.t += 1
        feed.ws.push(111, ladder(100.0, 10, size=9), ladder(100.25, 10, down=False))
        d.step()
        await d.aflush()
        return rec
    rec = run(go())
    lines = read_depth(rec.path("NQ", D, NQ))
    assert len(lines) == 2 and lines[1]["b"][0] == [100.0, 9]


def test_recording_files_by_session_date_with_the_crypto_rule(tmp_path):
    rec = DepthRecorder(tmp_path / "depth")
    fri_eve = int(dt.datetime(2026, 9, 25, 18, 30, tzinfo=ET).timestamp() * 1000)   # Friday 18:30 ET
    rec.add("NQ", "NQZ6", fri_eve, [[1.0, 1]], [[1.25, 1]])
    rec.add("BTC", "BTCV6", fri_eve, [[1.0, 1]], [[5.0, 1]])
    assert rec.flush() == 2
    base = tmp_path / "depth"
    assert (base / "NQ" / "2026" / "2026-09-28_NQZ6.depth.jsonl.gz").exists()     # Monday's session
    assert (base / "BTC" / "2026" / "2026-09-26_BTCV6.depth.jsonl.gz").exists()   # 24/7: Saturday's


def test_one_gzip_member_per_flush_and_a_torn_tail_loses_only_the_last(tmp_path):
    rec = DepthRecorder(tmp_path / "depth")
    for i in range(3):
        rec.add("NQ", "NQZ6", T0 + i, [[100.0 + i, 1]], [[101.0, 1]])
        rec.flush()
    p = rec.path("NQ", D, "NQZ6")
    raw = p.read_bytes()
    assert raw.count(b"\x1f\x8b\x08") == 3
    p.write_bytes(raw[:-7])                               # a crash mid-write of the third member
    assert [ln["b"][0][0] for ln in read_depth(p)] == [100.0, 101.0]
    # a new process appending after the tear repairs the file first: nothing after it is hidden
    rec2 = DepthRecorder(tmp_path / "depth")
    rec2.add("NQ", "NQZ6", T0 + 9, [[109.0, 1]], [[110.0, 1]])
    rec2.flush()
    assert [ln["b"][0][0] for ln in read_depth(p)] == [100.0, 101.0, 109.0]
    with gzip.open(p, "rt") as fh:                       # and the whole file inflates cleanly again
        assert len(fh.read().splitlines()) == 3


def test_the_recorder_flushes_every_30s_and_on_shutdown(tmp_path):
    async def go():
        rec, feed, d, clock = rec_setup(tmp_path)
        await connect(d)
        feed.ws.push(111, ladder(100.0, 3), ladder(100.25, 3, down=False))
        p = rec.path("NQ", D, NQ)
        clock.t += 29
        d.step()
        await d.settle()
        assert not p.exists()
        clock.t += 1
        d.step()
        await d.settle()
        assert len(read_depth(p)) == 1
        clock.t += 1
        feed.ws.push(111, ladder(101.0, 3), ladder(101.25, 3, down=False))
        await d.aclose()                                   # what shutdown calls
        assert len(read_depth(p)) == 2
    run(go())


def test_disk_errors_are_reported_and_never_raise(tmp_path):
    blocker = tmp_path / "depth"
    blocker.write_text("a file where the directory should be")
    rec = DepthRecorder(blocker)
    rec.add("NQ", "NQZ6", T0, [[1.0, 1]], [[1.25, 1]])
    assert rec.flush() == 0
    assert rec.error and rec.buffered == 1                # kept for the next flush


def test_a_failed_file_is_rechecked_at_most_every_repair_retry(tmp_path, monkeypatch):
    clock = Clock(0.0)
    rec = DepthRecorder(tmp_path / "depth", now=clock)
    calls = []

    def repair(p):
        calls.append(clock.t)
        raise OSError("No space left on device")
    monkeypatch.setattr(rec, "_repair", repair)
    rec.add("NQ", "NQZ6", T0, [[1.0, 1]], [[1.25, 1]])
    assert rec.flush() == 0 and "No space" in rec.error
    for _ in range(9):                                      # every 30 s flush for 4.5 min: not re-read
        clock.t += 30
        assert rec.flush() == 0 and "No space" in rec.error and rec.buffered == 1
    assert calls == [0.0]
    clock.t = depth_mod.REPAIR_RETRY_S
    rec.flush()
    assert calls == [0.0, depth_mod.REPAIR_RETRY_S]
    monkeypatch.undo()
    clock.t += depth_mod.REPAIR_RETRY_S
    assert rec.flush() == 1 and rec.error is None
    assert len(read_depth(rec.path("NQ", D, "NQZ6"))) == 1


def test_the_file_scan_runs_off_the_event_loop(tmp_path, monkeypatch):
    threads = []
    real = depth_mod._scan

    def scan(raw):
        threads.append(threading.current_thread())
        return real(raw)
    monkeypatch.setattr(depth_mod, "_scan", scan)
    rec = DepthRecorder(tmp_path / "depth")
    rec.add("NQ", "NQZ6", T0, [[1.0, 1]], [[1.25, 1]])
    rec.flush()                                             # the file does not exist yet: no scan
    assert threads == []
    rec2 = DepthRecorder(tmp_path / "depth")                # a new process: its first touch scans it

    async def go():
        feed, d, _ = make(record=("NQ",), recorder=rec2)
        rec2.add("NQ", "NQZ6", T0 + 1, [[2.0, 1]], [[2.25, 1]])
        await d.aflush()
    run(go())
    assert len(threads) == 1 and threads[0] is not threading.main_thread()
    assert len(read_depth(rec.path("NQ", D, "NQZ6"))) == 2


def test_members_are_compressed_at_level_6(tmp_path):
    rec = DepthRecorder(tmp_path / "depth")
    rec.add("NQ", "NQZ6", T0, [[1.0, 1]], [[1.25, 1]])
    rec.flush()
    raw = rec.path("NQ", D, "NQZ6").read_bytes()
    assert raw[8] == 0          # gzip XFL: 2 = level 9, 4 = level 1, 0 = anything between


def test_the_recorder_never_writes_under_futures_ticks(tmp_path):
    assert DEPTH_ARCHIVE == Path.home() / "futures_depth"
    for bad in (ARCHIVE, ARCHIVE / "NQ", ARCHIVE / ".." / "futures_ticks" / "x"):
        with pytest.raises(ValueError):
            DepthRecorder(bad)
    rec = DepthRecorder(tmp_path / "depth")
    rec.add("NQ", "NQZ6", T0, [[1.0, 1]], [[1.25, 1]])
    rec.flush()
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()] == \
        [f"depth/NQ/2026/{D}_NQZ6.depth.jsonl.gz"]
