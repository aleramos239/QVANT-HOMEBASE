"""Timing instrumentation for the 9:30 fire, no behaviour change: each OSO leg's own round
trip in the `placed` journal (leg_ms), and the broker round trips of the prestage's existing
position read (prestage_rtt_ms) as the baseline -- network vs broker queueing at the open.
Also the entry fill's own path (entry_fill: fill_seen_ts, fill_ms) and a chart action's request
-> broker answer (manual_*: ack_ms).  No network: fake sockets, injected clocks."""
from __future__ import annotations

import json
import time

from homebase.broker.base import FillEvent, OrderResult
from homebase.broker.tradovate_ws import TradovateWS
from tests import trading_util as TU
from tests.test_engine import ALERT, FakeAdapter, journal_events, mkengine, run, st_of
from tests.test_prestage import CountingAdapter, mk2
from tests.test_timer import _drive_to_fire, events
from tests.test_tradovate import (BUY_STOP, FakeSocket, collect_fills, every_lookup_404s,
                                  fill_push, mkadapter, tradovate_like)


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


# --- entry_fill: push seen -> enriched -> sibling cancel sent -> acknowledged --------------------
def _placed_with_slow_cancel(tmp_path, cancel_s=0.030):
    eng, ad, _ = mkengine(tmp_path)
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    perf = eng._perf = Perf()
    orig = ad.cancel_order_by_id

    async def slow(oid):                      # the broker answers the cancel in 30 ms
        perf.t += cancel_s
        return await orig(oid)

    ad.cancel_order_by_id = slow
    return eng, ad, perf, st_of(eng)


def test_entry_fill_journals_seen_enriched_cancel_sent_and_acknowledged(tmp_path):
    eng, ad, perf, st = _placed_with_slow_cancel(tmp_path)
    # the push was seen 20 ms before the engine got it; a broker read filled it in after 12 ms
    ev = FillEvent(account_id="main", symbol="NQZ6", side="Buy", qty=3, price=24510.25,
                   raw={"orderId": st.upper_id}, seen=perf.t - 0.020, enriched=perf.t - 0.008)
    before = time.time()
    run(eng.on_fill(ev))
    rec = records(tmp_path, "entry_fill")[0]
    assert rec["fill_ms"] == {"enriched": 12.0, "cancel_sent": 20.0, "cancel_ack": 50.0}
    assert before - 0.050 - 0.01 <= rec["fill_seen_ts"] <= time.time() - 0.050 + 0.01
    assert rec["fill_seen_ts"] < rec["ts"]                   # the line itself is written after the ack
    # nothing else moved: the same sibling cancel, the same fields as before
    assert ad.cancelled == [st.lower_id] and st.status == "live"
    assert rec["sibling_cancelled"] is True and rec["sibling_error"] is None and rec["qty_filled"] == 3


def test_a_fill_with_no_push_stamp_is_timed_from_the_engine(tmp_path):
    """An adapter that stamps nothing (paper, a test fake): on_fill is where the fill is first seen."""
    eng, ad, perf, st = _placed_with_slow_cancel(tmp_path)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell", qty=3, price=24489.75,
                              raw={"orderId": st.lower_id})))
    assert records(tmp_path, "entry_fill")[0]["fill_ms"] == \
        {"enriched": None, "cancel_sent": 0.0, "cancel_ack": 30.0}
    assert ad.cancelled == [st.upper_id]


def test_a_raising_sibling_cancel_is_timed_and_handled_as_before(tmp_path):
    eng, ad, perf, st = _placed_with_slow_cancel(tmp_path)

    async def boom(oid):
        perf.t += 0.015
        raise RuntimeError("cancel failed: timeout")

    ad.cancel_order_by_id = boom
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy", qty=3, price=24510.0,
                              raw={"orderId": st.upper_id})))
    rec = records(tmp_path, "entry_fill")[0]
    assert rec["fill_ms"] == {"enriched": None, "cancel_sent": 0.0, "cancel_ack": 15.0}
    assert rec["sibling_cancelled"] is False and "timeout" in rec["sibling_error"]
    assert st.status == "live"


def test_the_rest_of_a_split_entry_carries_its_own_fill_timing_and_no_cancel(tmp_path):
    eng, ad, perf, st = _placed_with_slow_cancel(tmp_path)
    for qty in (1, 2):
        run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy", qty=qty,
                                  price=24510.0, raw={"orderId": st.upper_id}, seen=perf.t - 0.004)))
    first, rest = records(tmp_path, "entry_fill")
    assert first["fill_ms"] == {"enriched": None, "cancel_sent": 4.0, "cancel_ack": 34.0}
    assert rest["fill_ms"] == {"enriched": None, "cancel_sent": None, "cancel_ack": None}
    assert rest["qty_filled"] == 3 and ad.cancelled == [st.lower_id]      # one cancel, as before


def _asked(ad):
    return [f.split("\n", 1)[0] for f in ad._ws.ws.sent]


def test_the_adapter_stamps_the_push_and_an_enrichment_only_when_it_read_the_broker(tmp_path):
    # the order (its push came before its fill) and its contract (we placed it) are known: no broker read
    ad = mkadapter(tmp_path, tradovate_like)
    ad._orders[663695020149] = {"id": 663695020149, "accountId": 66121477, "contractId": 3267315}
    t0 = time.perf_counter()
    ev, = collect_fills(ad, [fill_push(663695020149, "Buy", 3, 30231.75, 1)], place=BUY_STOP)
    assert t0 <= ev.seen <= time.perf_counter() and ev.enriched is None and ad._fill_seen == {}
    assert "order/item" not in _asked(ad) and "fill/item" not in _asked(ad)
    # every lookup 404s (2026-09-21): the order was asked for -> an enrichment stamp after the push
    ad = mkadapter(tmp_path, every_lookup_404s)
    ev, = collect_fills(ad, [fill_push(663695020149, "Buy", 3, 30231.75, 2)])
    assert ev.seen <= ev.enriched <= time.perf_counter() and ad._fill_seen == {}
    assert "order/item" in _asked(ad)


# --- manual_*: the request coming in -> the broker's answer ---------------------------------------
def _slow(ad, mono, name, s):
    orig = getattr(ad, name)

    async def slow(*a, **k):
        mono.t += s
        return await orig(*a, **k)

    setattr(ad, name, slow)


def test_chart_actions_journal_request_to_broker_answer(tmp_path):
    desk, eng, ads, clock, mono, _ = TU.mkdesk(tmp_path)
    ad = ads["a1"]
    real_place = ad.place_order

    async def place(req):                                    # a broker-style numeric id
        r = await real_place(req)
        return OrderResult(ok=r.ok, order_id="77" if r.ok else None, error=r.error)

    ad.place_order = place
    for name, s in (("place_order", 0.040), ("cancel_order_by_id", 0.025), ("cancel_symbol", 0.010),
                    ("flatten_symbol", 0.060)):
        _slow(ad, mono, name, s)
    body = {"accounts": ["a1"], "root": "NQ"}
    out = TU.run(desk.order({**body, "client_id": "o1", "side": "Buy", "qty": 1, "type": "Limit",
                             "price": 99.0}))["results"]["a1"]
    assert out == {"ok": True, "order_id": "77", "error": None}          # the result is untouched
    ad.view["orders"] = [{"order_id": "77", "symbol": TU.NQC, "side": "Buy", "type": "Limit",
                          "qty": 1, "price": 99.0, "stop_price": None, "status": "Working"}]
    for call in (lambda: desk.cancel({"client_id": "c1", "account": "a1", "order_id": "77"}),
                 lambda: desk.cancel_symbol({**body, "client_id": "s1"}),
                 lambda: desk.flatten({**body, "client_id": "f1"})):
        mono.t += 11                                         # clear of the rate guard and the reservation
        assert TU.run(call())["results"]["a1"]["ok"]
    ad.net = 2
    mono.t += 1
    assert TU.run(desk.reverse({**body, "client_id": "r1"}))["results"]["a1"]["ok"]
    got = [(e["event"], e.get("scope") or e.get("step"), e["ack_ms"])
           for e in TU.journal(tmp_path) if e["event"].startswith("manual_")]
    assert got == [("manual_order", None, 40.0), ("manual_cancel", "order", 25.0),
                   ("manual_cancel", "symbol", 10.0), ("manual_flatten", None, 60.0),
                   ("manual_reverse", "flatten", 60.0), ("manual_reverse", "open", 100.0)]


def test_an_exits_action_journals_request_to_its_last_broker_answer(tmp_path):
    desk, eng, ads, clock, mono, _ = TU.mkdesk(tmp_path)
    ad = ads["a1"]
    ad.net = 3
    ad.view["positions"] = [{"contract_id": 1, "symbol": TU.NQC, "net": 3, "avg_price": 100.0}]
    _slow(ad, mono, "place_oco", 0.045)
    r = TU.run(desk.exits({"client_id": "x1", "accounts": ["a1"], "root": "NQ",
                           "quotes": TU.quote(clock), "expected_net": {"a1": 3},
                           "sl_price": 95.0, "tp_price": 110.0}))["results"]["a1"]
    assert r["ok"] and len(ad.ocos) == 1
    assert [e["ack_ms"] for e in TU.journal(tmp_path) if e["event"] == "manual_exits"] == [45.0]


def test_each_account_of_one_action_is_timed_from_the_same_request(tmp_path):
    """The accounts run side by side: a slow one's wait is its own, the request's start is shared."""
    desk, eng, ads, clock, mono, _ = TU.mkdesk(tmp_path)
    _slow(ads["a2"], mono, "flatten_symbol", 0.080)
    TU.run(desk.flatten({"client_id": "f1", "accounts": ["a1", "a2"], "root": "NQ"}))
    ms = {e["account"]: e["ack_ms"] for e in TU.journal(tmp_path) if e["event"] == "manual_flatten"}
    assert ms == {"a1": 0.0, "a2": 80.0}


def test_a_chart_action_run_outside_a_request_journals_no_duration(tmp_path):
    desk, eng, ads, clock, mono, _ = TU.mkdesk(tmp_path)
    assert desk._ack_ms() is None
