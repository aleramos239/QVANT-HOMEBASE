"""ChartDesk views, events and settings. No broker, no network."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from dataclasses import asdict

import pytest

import homebase.config as config_mod
from homebase.config import ChartTradingCfg
from homebase.trading import state_view
from tests.trading_util import NQC, drain, journal, mkdesk, run


def test_chart_trading_config_defaults_roundtrip_and_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = config_mod.load()
    assert asdict(cfg.chart_trading) == {"enabled": False, "max_order_qty": 10, "max_position_qty": 20}
    cfg.chart_trading = ChartTradingCfg(enabled=True, max_order_qty=3, max_position_qty=6)
    config_mod.save(cfg)
    assert asdict(config_mod.load().chart_trading) == {"enabled": True, "max_order_qty": 3,
                                                       "max_position_qty": 6}
    for junk in ({"enabled": "true"}, {"enabled": True, "max_order_qty": 0},
                 {"enabled": True, "max_position_qty": "x"}, "on"):
        (tmp_path / "config.json").write_text(json.dumps({"chart_trading": junk}))
        assert config_mod.load().chart_trading.enabled is False


def test_snapshot_shape(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 2, "avg_price": 100.5}]
    st = eng._state("nq930", "a1")
    st.status, st.upper_id = "done", "60"
    ads["a1"].view["orders"] = [{"order_id": "60", "symbol": NQC, "side": "Buy", "type": "Stop",
                                 "qty": 3, "price": None, "stop_price": 110.0, "status": "Working"}]
    s = desk.snapshot()
    assert s["enabled"] is True and s["limits"] == {"max_order_qty": 10, "max_position_qty": 20}
    a1, a2 = s["accounts"]
    assert (a1["id"], a1["label"], a1["pinned"], a1["env"]) == ("a1", "A1", "A1", "demo")
    assert a1["connected"] is True and a1["tradable"] is True and a1["error"] is None
    assert a1["positions"] == [{"contract_id": 1, "symbol": NQC, "net": 2, "avg_price": 100.5,
                                "root": "NQ", "point_value": 20.0}]
    assert a1["orders"][0]["owner"] == "nq930"                 # the bot's own order is marked
    assert a1["strategies"] == ["nq930"] and a2["strategies"] == []
    bot = s["bot"]["strategies"]["nq930"]
    assert bot["book"] == {"a1": 3} and bot["timer"]["adx"] == 23.4
    assert bot["day_status"] == "done" and bot["accounts"]["a1"]["status"] == "done"
    json.dumps(s)                                               # JSON-clean


def test_an_unpinned_or_unseeded_account_is_not_tradable(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].pinned_ok = False
    ads["a2"].view["seeded"] = False
    assert [a["tradable"] for a in desk.snapshot()["accounts"]] == [False, False]


def test_bot_levels_follow_the_engine(tmp_path):
    desk, eng, *_ = mkdesk(tmp_path)
    s = eng.cfg.strategies["nq930"]
    st = eng._state("nq930", "a1")
    st.status, st.upper_px, st.lower_px, st.qty = "placed", 110.0, 90.0, 3
    v = state_view(st, s)
    assert (v["upper"], v["lower"], v["sl"], v["tp"]) == (110.0, 90.0, None, None)
    st.status, st.entry_side, st.entry_anchor, st.entry_fill = "live", "Buy", 110.0, 110.5
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (105.0, 125.0)   # from the anchor
    st.brackets_moved = True
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (105.5, 125.5)   # moved to the fill
    st.entry_side, st.entry_anchor, st.entry_fill = "Sell", 90.0, 89.75
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (94.75, 74.75)
    st.sl_px, st.tp_px = 80.0, 70.0                                              # a bars rule
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (80.0, 70.0)


def test_listener_publishes_the_fill_then_the_changed_account(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    desk.attach("a1", ads["a1"])
    desk.attach("a1", ads["a1"])                                 # idempotent
    assert len(ads["a1"]._listeners) == 1

    async def go():
        q = desk.subscribe()
        desk.flush()                                             # first flush: the full state
        ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 1, "avg_price": 100.0}]
        ads["a1"]._notify("fill", {"id": 9, "orderId": 5, "contractId": 1, "action": "Buy",
                                   "qty": 1, "price": 100.0, "timestamp": "t"})
        await asyncio.sleep(0)                                   # the scheduled flush runs
        await asyncio.sleep(0)
        return drain(q)

    evs = run(go())
    assert [e for e, _ in evs] == ["state", "fill", "account"]
    assert evs[1][1] == {"account": "a1", "fill": {
        "id": 9, "order_id": "5", "symbol": NQC, "side": "Buy", "qty": 1, "price": 100.0,
        "time": "t", "owner": None}}
    assert evs[2][1]["positions"][0]["net"] == 1 and evs[2][1]["fills"][-1]["id"] == 9


def test_flush_publishes_only_what_changed(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    async def go():
        q = desk.subscribe()
        desk.flush()
        desk.flush()                                             # nothing changed
        eng._state("nq930", "a1").status = "placed"
        desk.flush()                                             # the bot changed
        ads["a2"]._connected = False
        desk.flush()                                             # one account changed
        return [e for e, _ in drain(q)]

    assert run(go()) == ["state", "bot", "account"]


def test_a_reader_that_falls_behind_is_dropped_with_an_end_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.trading.SUB_QUEUE_MAX", 3)
    desk, *_ = mkdesk(tmp_path)

    async def go():
        q = desk.subscribe()
        for i in range(5):
            desk.publish("fill", {"i": i})
        return drain(q), q in desk._subs

    items, still = run(go())
    assert items == [(None, None)] and still is False


def test_settings_validate_save_journal_and_publish(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, enabled=False)

    async def go():
        q = desk.subscribe()
        out = desk.set_settings({"enabled": True, "max_order_qty": 4})
        return out, [e for e, _ in drain(q)]

    out, evs = run(go())
    assert out == {"enabled": True, "max_order_qty": 4, "max_position_qty": 20}
    assert saved[-1].chart_trading.enabled is True and evs == ["state"]
    ev = [e for e in journal(tmp_path) if e["event"] == "chart_trading_set"][-1]
    assert ev["enabled"] is True and ev["max_order_qty"] == 4 and "strategy" not in ev
    for bad, msg in (({"enabled": "yes"}, "enabled: true or false"),
                     ({"max_order_qty": 0}, "max_order_qty: a whole number 1-50"),
                     ({"max_position_qty": 101}, "max_position_qty: a whole number 1-100"),
                     ({"max_order_qty": True}, "max_order_qty: a whole number 1-50"),
                     ([], "the body is a JSON object")):
        with pytest.raises(ValueError, match=re.escape(msg)):
            desk.set_settings(bad)
    assert desk.cfg.chart_trading.max_order_qty == 4             # a refused change changes nothing


def test_disable_switches_off_and_never_raises(tmp_path):
    desk, eng, *_ = mkdesk(tmp_path)

    def broken(cfg):
        raise OSError("disk full")

    desk._save = broken
    desk.disable(cause="kill")
    assert desk.cfg.chart_trading.enabled is False
    ev = [e for e in journal(tmp_path) if e["event"] == "chart_trading_set"][-1]
    assert ev == {**ev, "enabled": False, "cause": "kill"}


# --- controller ruling P2: the 09:30:00.000 bot fire is protected from view work ---


def test_nothing_is_rebuilt_or_serialized_at_093000(tmp_path):
    """09:29:50-09:30:30 ET on weekdays: flush() (periodic or push-triggered)
    must not rebuild or publish a view. Fill events still publish, cheaply."""
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, et=(9, 29))   # 09:29:00 ET: baseline
    desk.attach("a1", ads["a1"])

    async def go():
        q = desk.subscribe()
        desk.flush()                                      # baseline "state", before the pause
        clock.dt += dt.timedelta(seconds=60)               # now 09:30:00.000 ET: inside the pause
        ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 1,
                                        "avg_price": 100.0}]
        desk.flush()                                       # paused: no rebuild, nothing published
        ads["a1"]._notify("fill", {"id": 9, "orderId": 5, "contractId": 1, "action": "Buy",
                                   "qty": 1, "price": 100.0, "timestamp": "t"})
        await asyncio.sleep(0)                             # the push-scheduled flush runs, still paused
        await asyncio.sleep(0)
        return drain(q)

    evs = [e for e, _ in run(go())]
    assert evs == ["state", "fill"]                        # only the baseline + the (cheap) fill


def test_the_refresh_resumes_at_093030(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, et=(9, 29))

    async def go():
        q = desk.subscribe()
        desk.flush()                                       # baseline "state"
        clock.dt += dt.timedelta(seconds=60)               # 09:30:00: inside the pause
        ads["a2"]._connected = False
        desk.flush()                                       # still paused: nothing
        clock.dt += dt.timedelta(seconds=30)               # 09:30:30: the pause ends
        desk.flush()                                       # the held-up change now publishes
        return [e for e, _ in drain(q)]

    assert run(go()) == ["state", "account"]


def test_a_placing_bot_day_pauses_flush_outside_the_window_too(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)                  # 11:00 ET: well outside the window

    async def go():
        q = desk.subscribe()
        desk.flush()                                       # baseline
        eng._state("nq930", "a1").status = "placing"
        ads["a1"]._connected = False                       # would otherwise flush an account event
        desk.flush()
        return [e for e, _ in drain(q)]

    assert run(go()) == ["state"]                          # only the baseline; placing held the flush
