"""Depth.tap: the book lines the recorder would write, handed to a listener (booklive.py) -- the SAME lines, so a
recorded day replayed through bookhist.py and the live tracker see one input."""
from __future__ import annotations

from homebase import symbols
from homebase.charts.depth import Depth, DepthRecorder, read_depth
from tests.charts_util import D
from tests.test_charts_depth import FakeFeed, FakeWS, Page, T0, Clock, connect, ladder, run


def test_the_tap_gets_exactly_the_lines_the_recorder_writes(tmp_path):
    async def go():
        rec = DepthRecorder(tmp_path / "depth")
        feed, clock = FakeFeed(FakeWS()), Clock()
        d = Depth(feed, ("NQ",), recorder=rec, now=clock, wall_ms=lambda: T0)
        got = []
        d.tap = lambda root, ts, bids, offers: got.append({"t": ts, "b": bids, "a": offers, "root": root})
        await connect(d)
        for i in range(6):
            clock.t += 1
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False))
            d.step()
        await d.aflush()
        return rec, got
    rec, got = run(go())
    nq = symbols.resolve_contract("NQ")
    written = read_depth(rec.path("NQ", D, nq))
    assert len(got) == len(written) == 6
    assert [{k: g[k] for k in ("t", "b", "a")} for g in got] == written
    assert all(g["root"] == "NQ" for g in got)


def test_a_viewed_root_that_is_not_recorded_is_tapped_and_an_unviewed_one_is_not(tmp_path):
    async def go():
        ym = symbols.resolve_contract("YM")
        feed = FakeFeed(FakeWS({symbols.resolve_contract("NQ"): 111, ym: 333}))
        clock = Clock()
        d = Depth(feed, ("NQ",), recorder=DepthRecorder(tmp_path / "depth"), now=clock, wall_ms=lambda: T0)
        got = []
        d.tap = lambda root, ts, bids, offers: got.append(root)
        page = Page()
        d.view((page, "c1"), "YM", page.send, page.room)
        await connect(d)
        for i in range(3):
            clock.t += 1
            feed.ws.push(333, ladder(40000.0 + i, 12, step=1.0), ladder(40001.0 + i, 12, step=1.0, down=False))
            d.step()
        assert got == ["YM", "YM", "YM"]
        d.unview((page, "c1"))
        clock.t += 1
        feed.ws.push(333, ladder(41000.0, 12, step=1.0), ladder(41001.0, 12, step=1.0, down=False))
        d.step()
        return got
    assert run(go()) == ["YM", "YM", "YM"]


def test_without_a_tap_nothing_changes(tmp_path):
    async def go():
        rec = DepthRecorder(tmp_path / "depth")
        feed, clock = FakeFeed(FakeWS()), Clock()
        d = Depth(feed, ("NQ",), recorder=rec, now=clock, wall_ms=lambda: T0)
        assert d.tap is None
        await connect(d)
        for i in range(3):
            clock.t += 1
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False))
            d.step()
        await d.aflush()
        return rec
    rec = run(go())
    assert len(read_depth(rec.path("NQ", D, symbols.resolve_contract("NQ")))) == 3


def test_a_tap_that_raises_neither_stops_the_recorder_nor_the_feed(tmp_path):
    async def go():
        rec = DepthRecorder(tmp_path / "depth")
        logs = []
        feed, clock = FakeFeed(FakeWS()), Clock()
        d = Depth(feed, ("NQ",), recorder=rec, now=clock, wall_ms=lambda: T0, log=logs.append)

        def boom(*_a):
            raise RuntimeError("listener broke")
        d.tap = boom
        await connect(d)
        for i in range(3):
            clock.t += 1
            feed.ws.push(111, ladder(100.0 + i, 25), ladder(100.25 + i, 25, down=False))
            d.step()
        await d.aflush()
        return rec, logs
    rec, logs = run(go())
    assert len(read_depth(rec.path("NQ", D, symbols.resolve_contract("NQ")))) == 3
    assert logs and "listener broke" in logs[0]
