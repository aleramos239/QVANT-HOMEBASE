"""Timing instrumentation for the 9:30 fire, no behaviour change: each OSO leg's own round
trip in the `placed` journal (leg_ms), and the broker round trips of the prestage's existing
position read (prestage_rtt_ms) as the baseline -- network vs broker queueing at the open.
No network: fake sockets, injected clocks."""
from __future__ import annotations

import datetime as dt
import json

from homebase.broker.base import OrderResult
from homebase.broker.tradovate_ws import TradovateWS
from tests.test_engine import ALERT, FakeAdapter, journal_events, mkengine, run, st_of
from tests.test_prestage import CountingAdapter, mk2
from tests.test_timer import _drive_to_fire, events
from tests.test_tradovate import FakeSocket, mkadapter, tradovate_like


class Perf:
    """An injected perf_counter the fake broker moves forward."""

    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


def records(tmp_path, event):
    p = tmp_path / "journal.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["event"] == event]


# --- leg_ms: each leg's own round trip ---------------------------------------------------
def test_placed_journals_each_legs_own_round_trip(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    perf = eng._perf = Perf()
    orig = ad.place_bracket

    async def slow(req):                      # the broker answers the BUY in 40 ms, the SELL in 90
        perf.t += 0.040 if req.side == "Buy" else 0.090
        return await orig(req)

    ad.place_bracket = slow
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    rec = records(tmp_path, "placed")[0]
    assert rec["leg_ms"] == {"upper": 40.0, "lower": 90.0}
    assert isinstance(rec["place_ms"], int)                  # unchanged beside it
    assert st_of(eng).status == "placed" and [b.side for b in ad.brackets] == ["Buy", "Sell"]


def test_a_rejected_or_raising_leg_is_timed_too(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    perf = eng._perf = Perf()
    orig = ad.place_bracket

    async def boom(req):
        perf.t += 0.015
        if req.side == "Sell":
            raise RuntimeError("OSO failed: timeout")
        return await orig(req)

    ad.place_bracket = boom
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"] and "timeout" in out["accounts"]["main"]["reason"]
    rec = records(tmp_path, "place_failed")[0]
    assert rec["leg_ms"] == {"upper": 15.0, "lower": 15.0} and rec["leg"] == "lower"
    assert ad.cancelled == ["main-101"]                      # the survivor, as before


def test_the_legs_still_go_out_together(tmp_path):
    """The timing wrapper must not serialize the legs."""
    import asyncio
    eng, ad, _ = mkengine(tmp_path)
    orig, seen = ad.place_bracket, {"now": 0, "max": 0}

    async def slow(req):
        seen["now"] += 1
        seen["max"] = max(seen["max"], seen["now"])
        await asyncio.sleep(0.01)
        seen["now"] -= 1
        return await orig(req)

    ad.place_bracket = slow
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    assert seen["max"] == 2
    leg_ms = records(tmp_path, "placed")[0]["leg_ms"]
    assert set(leg_ms) == {"upper", "lower"} and all(5.0 <= v < 5000 for v in leg_ms.values())


def test_a_dry_run_journals_no_timing(tmp_path):
    eng, ad, _ = mkengine(tmp_path, armed=False)
    run(eng.handle_alert(dict(ALERT)))
    assert "placed" not in journal_events(tmp_path) and ad.brackets == []


# --- the socket: every answered request's round trip ---------------------------------------
def test_the_socket_records_each_requests_round_trip():
    ws = TradovateWS(token="t")
    ws.ws = FakeSocket(ws, tradovate_like)
    clock = iter([10.0, 10.0321, 20.0, 20.0125])
    ws._perf = lambda: next(clock)
    assert run(ws.contract_find("NQZ6"))["id"] == 3267315
    try:
        run(ws.fill_item(1))                                  # a 404 still took a round trip
    except RuntimeError:
        pass
    assert list(ws.rtts) == [(10.0321, "contract/find", 32.1), (20.0125, "fill/item", 12.5)]


def test_the_adapter_reports_the_latest_round_trip_per_request_since_a_moment(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad._ws.rtts.extend([(5.0, "position/list", 99.0),         # before `since`: not this read
                        (11.0, "contract/find", 30.5),
                        (12.0, "position/list", 31.0),
                        (13.0, "position/list", 29.5)])
    assert ad.request_rtts_ms(10.0) == {"contract/find": 30.5, "position/list": 29.5}
    assert ad.request_rtts_ms(14.0) == {}
    ad._ws = None
    assert ad.request_rtts_ms(0.0) == {}


def test_a_real_position_read_leaves_both_of_its_round_trips(tmp_path):
    import time
    ad = mkadapter(tmp_path, tradovate_like)
    since = time.perf_counter()
    assert run(ad.get_net_position("NQ")) == 3
    got = ad.request_rtts_ms(since)
    assert set(got) == {"contract/find", "position/list"} and all(v >= 0 for v in got.values())


# --- prestage_rtt_ms: the baseline, from the prestage's existing read ------------------------
class TimedAdapter(CountingAdapter):
    rtts: dict = {}

    def request_rtts_ms(self, since):
        return dict(self.rtts.get(self.account_id, {}))


def test_the_prestage_journals_the_round_trips_of_its_own_read(tmp_path):
    TimedAdapter.rtts = {"a1": {"contract/find": 28.1, "position/list": 30.2},
                         "a2": {"contract/find": 41.0, "position/list": 39.9}}
    CountingAdapter.reads = 0
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=TimedAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    rtt = [e for e in ev if e["event"] == "prestage_rtt"]
    assert len(rtt) == 1 and rtt[0]["strategy"] == "nq930"
    assert rtt[0]["prestage_rtt_ms"] == TimedAdapter.rtts
    assert CountingAdapter.reads == 2                        # no broker call added: one read each
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_timing_that_fails_never_touches_the_check(tmp_path):
    class Broken(CountingAdapter):
        def request_rtts_ms(self, since):
            raise RuntimeError("no clock")

    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2}, adapter_cls=Broken)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert not any(e["event"] == "prestage_rtt" for e in ev)
    assert timer.status()["strategies"]["nq930"]["skipped_accounts"] == {"a2": 2}
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a1"]


def test_no_round_trips_measured_journals_nothing(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0}, adapter_cls=FakeAdapter)
    _drive_to_fire(timer, clock)
    assert not any(e["event"] == "prestage_rtt" for e in events(tmp_path))


def test_an_unreadable_position_still_reports_its_round_trips(tmp_path):
    class FailingRead(TimedAdapter):
        async def get_net_position(self, symbol):
            raise RuntimeError("position/list failed: status=404")

    TimedAdapter.rtts = {"a1": {"contract/find": 27.0, "position/list": 33.0}}
    timer, engine, clock = mk2(tmp_path, {"a1": 0}, adapter_cls=FailingRead)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert [e["prestage_rtt_ms"] for e in ev if e["event"] == "prestage_rtt"] == \
        [{"a1": {"contract/find": 27.0, "position/list": 33.0}}]
    assert any(e["event"] == "prestage_check_failed" and e.get("account") == "a1" for e in ev)
