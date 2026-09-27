"""The per-strategy kill (POST /api/trade/bot-kill) and the bot-history route.
Fake adapters only: no broker, no network."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

from homebase.broker.base import OrderResult
from homebase.config import AccountCfg, AppCfg, ChartTradingCfg, StrategyCfg
from homebase.engine import Engine
from homebase.timer import SelfTimer
from homebase.trading import ChartDesk
from tests.test_desk_api import desk_client  # noqa: F401 — the fixture
from tests.test_engine import Clock
from tests.test_timer import FakeMD
from tests.trading_util import Mono, TradeAdapter, journal, run

NQ_IDS = ("u1", "l1", "us", "ut", "ds", "dt")
ES_IDS = ("eu", "el", "eus", "eut", "eds", "edt")


def mk(tmp_path, et=(10, 0), armed=True):
    """nq930 (NQ) and es930 (ES) are both booked on a1; a2 is booked to nothing."""
    clock = Clock()
    clock.set_et(*et)
    cfg = AppCfg(
        armed=armed, webhook_secret="s",
        accounts={a: AccountCfg(keyring_key="k", account_name=a.upper(), label=a.upper())
                  for a in ("a1", "a2")},
        book={"nq930": [{"account": "a1", "qty": 2}], "es930": [{"account": "a1", "qty": 1}]},
        strategies={"nq930": StrategyCfg(symbol="NQ", qty=2, offset_pts=10.0, sl_pts=5.0,
                                         tp_pts=15.0, enabled=True, self_fire=True, gated=True),
                    "es930": StrategyCfg(symbol="ES", qty=1, offset_pts=2.0, sl_pts=1.0,
                                         tp_pts=3.0, enabled=True)},
        chart_trading=ChartTradingCfg(enabled=True))
    ads = {a: TradeAdapter(a) for a in cfg.accounts}
    eng = Engine(cfg, ads, now_fn=clock, root=tmp_path)
    desk = ChartDesk(cfg, eng, ads, {}, save=lambda c: None, mono=Mono())
    return desk, eng, ads, clock, cfg


def with_legs(st, ids, status, side="Buy"):
    st.status, st.qty, st.entry_side = status, 2, side if status == "live" else None
    st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id = ids
    st.upper_px, st.lower_px = 110.0, 90.0
    return st


def kill(desk, cid="k1", strategy="nq930"):
    return run(desk.bot_kill({"client_id": cid, "strategy": strategy}))


def logged(ad):
    """Record the adapter's broker calls in order: ("cancel", id) / ("market", side, qty)."""
    calls = []
    cancel, place = ad.cancel_order_by_id, ad.place_order

    async def c(i):
        calls.append(("cancel", str(i)))
        return await cancel(i)

    async def p(req):
        calls.append(("market", req.side, req.qty))
        return await place(req)

    ad.cancel_order_by_id, ad.place_order = c, p
    return calls


def test_kill_sells_only_the_bots_own_quantity_and_cancels_only_its_legs(tmp_path):
    """Fix round 1 (review Critical 1): the bot is long 2, the user also holds 3 NQ opened
    elsewhere -> the kill sells 2, never the account's 5."""
    desk, eng, ads, clock, cfg = mk(tmp_path)
    nq = with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    es = with_legs(eng._state("es930", "a1"), ES_IDS, "placed")
    ads["a1"].net = 5                                     # bot 2 + manual 3
    ads["a1"].order_status = {"u1": "Filled", "l1": "Canceled"}
    ads["a2"].net = 1                                     # a2: a manual NQ position, not booked
    calls = logged(ads["a1"])
    out = kill(desk)
    assert out["ok"] is True and list(out["results"]) == ["a1"]
    r = out["results"]["a1"]
    assert r["ok"] is True and r["acted"] is True and "market Sell 2: ok" in r["actions"]
    (o,) = ads["a1"].orders                               # ONE market order: the bot's 2 only
    assert (o.symbol, o.side, o.qty, o.order_type, o.text) == ("NQ", "Sell", 2, "Market", "homebase:kill")
    # entries cancelled first, then the market order, then the stop/target
    assert calls == [("cancel", "u1"), ("cancel", "l1"), ("market", "Sell", 2),
                     ("cancel", "us"), ("cancel", "ut"), ("cancel", "ds"), ("cancel", "dt")]
    assert not set(ES_IDS) & set(ads["a1"].cancelled)     # the other strategy is untouched
    assert es.status == "placed"
    assert ads["a2"].orders == [] and ads["a2"].cancelled == []      # outside the book: untouched
    for ad in ads.values():                               # never the account-wide calls
        assert ad.cancel_all_calls == 0 and ad.flatten_calls == 0
    assert (nq.status, nq.exit_reason) == ("done", "killed")
    assert eng.killed_today("nq930") and not eng.killed_today("es930")
    # not a global kill: the desk stays armed, chart trading stays on, the strategy stays enabled
    assert cfg.armed is True and cfg.chart_trading.enabled is True
    assert cfg.strategies["nq930"].enabled is True
    ev = [e["event"] for e in journal(tmp_path) if e["event"].startswith("strategy_kill")]
    assert ev == ["strategy_kill_requested", "strategy_killed"]
    killed = [e for e in journal(tmp_path) if e["event"] == "strategy_killed"][0]
    assert killed["strategy"] == "nq930" and killed["client_id"] == "k1"
    assert desk.bot_view()["strategies"]["nq930"]["killed"] is True
    assert desk.bot_view()["strategies"]["es930"]["killed"] is False


def test_a_second_strategy_in_the_same_contract_and_account_is_untouched(tmp_path):
    desk, eng, ads, clock, cfg = mk(tmp_path)
    cfg.strategies["nq10am"] = StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0,
                                           tp_pts=15.0, enabled=True)
    cfg.book["nq10am"] = [{"account": "a1", "qty": 1}]
    with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    other = with_legs(eng._state("nq10am", "a1"), ("x1", "x2", "xs", "xt", "ys", "yt"), "live")
    other.qty = 1
    ads["a1"].net = 3                                     # nq930 long 2 + nq10am long 1
    ads["a1"].order_status = {"u1": "Filled", "l1": "Canceled"}
    kill(desk)
    assert [(o.side, o.qty) for o in ads["a1"].orders] == [("Sell", 2)]   # nq10am's 1 stays
    assert not {"x1", "x2", "xs", "xt", "ys", "yt"} & set(ads["a1"].cancelled)
    assert other.status == "live" and not eng.killed_today("nq10am")


def test_a_net_on_the_other_side_sells_nothing_and_leaves_the_stops(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    ads["a1"].net = -3                                    # the bot is long 2; the account reads short
    ads["a1"].order_status = {"u1": "Filled", "l1": "Canceled"}
    out = kill(desk)
    r = out["results"]["a1"]
    assert r["ok"] is False and "check it" in r["actions"][-1]
    assert ads["a1"].orders == []
    assert not {"us", "ut", "ds", "dt"} & set(ads["a1"].cancelled)       # stop/target left working


def test_placed_not_filled_cancels_the_entries_first_and_sells_nothing(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "placed")
    ads["a1"].net = 1                                     # a manual position, not the bot's
    ads["a1"].order_status = {"u1": "Canceled", "l1": "Canceled"}
    calls = logged(ads["a1"])
    out = kill(desk)
    assert out["results"]["a1"]["ok"] is True and ads["a1"].orders == []
    assert calls[:2] == [("cancel", "u1"), ("cancel", "l1")]
    assert (st.status, st.exit_reason) == ("done", "killed")


def test_an_entry_that_fills_at_the_kill_is_sold_capped_before_its_brackets_go(tmp_path):
    """Fix round 1 (review Important 3): the old order read the position (0), then the entry
    filled, then the brackets were cancelled -> a naked position. Now the entries are cancelled
    first: this one filled just before (its cancel fails, it reads Filled) -> its qty is sold,
    then its stop/target are cancelled."""
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "placed")
    ad = ads["a1"]
    ad.fail_cancel_ids = {"u1"}
    ad.order_status = {"u1": "Filled", "l1": "Canceled"}
    ad.net = 3                                            # 2 of the bot's + 1 manual
    calls = logged(ad)
    out = kill(desk)
    assert out["results"]["a1"]["ok"] is True
    assert calls == [("cancel", "u1"), ("cancel", "l1"), ("market", "Sell", 2),
                     ("cancel", "us"), ("cancel", "ut"), ("cancel", "ds"), ("cancel", "dt")]
    assert (st.status, st.exit_reason) == ("done", "killed")


def test_an_entry_neither_cancelled_nor_filled_stops_the_kill(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "placed")
    ads["a1"].fail_cancel_ids = {"u1"}
    ads["a1"].order_status = {"u1": "Working", "l1": "Canceled"}
    ads["a1"].net = 2
    out = kill(desk)
    assert out["results"]["a1"]["ok"] is False and "check it" in out["results"]["a1"]["actions"][-1]
    assert ads["a1"].orders == [] and st.status == "placed"
    assert not {"us", "ut", "ds", "dt"} & set(ads["a1"].cancelled)


def test_two_kills_at_once_sell_once(tmp_path):
    """Fix round 1 (review Critical 2): two client_ids (two charts, a re-click) at once."""
    desk, eng, ads, *_ = mk(tmp_path)
    with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    ad = ads["a1"]
    ad.net = 2
    ad.order_status = {"u1": "Filled", "l1": "Canceled"}
    place = ad.place_order

    async def slow(req):
        await asyncio.sleep(0.01)                         # the other kill runs meanwhile
        return await place(req)

    ad.place_order = slow

    async def both():
        return await asyncio.gather(desk.bot_kill({"client_id": "a", "strategy": "nq930"}),
                                    desk.bot_kill({"client_id": "b", "strategy": "nq930"}))

    first, second = run(both())
    assert [(o.side, o.qty) for o in ad.orders] == [("Sell", 2)]
    assert first["results"]["a1"].get("acted") is True
    assert second["results"]["a1"] == {"ok": True, "note": "already killed — nothing to do"}


def test_an_idle_booked_account_is_left_alone(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    ads["a1"].net = 1                                     # the user's own NQ position
    out = kill(desk)
    assert out["ok"] is True and "actions" not in out["results"]["a1"]
    assert ads["a1"].orders == [] and ads["a1"].cancelled == []
    assert eng.killed_today("nq930")


def test_a_done_run_cancels_only_its_leftover_working_orders_and_never_flattens(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "done")
    ads["a1"].net = 1                                     # a manual position after the bot finished
    ads["a1"].order_status = {**{i: "Canceled" for i in NQ_IDS}, "u1": "Filled", "ut": "Working"}
    out = kill(desk)
    assert out["results"]["a1"]["ok"] is True
    assert ads["a1"].cancelled == ["ut"] and ads["a1"].orders == []
    assert st.status == "done"


def test_a_failed_flatten_is_reported_and_leaves_the_stops_working(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    ads["a1"].net, ads["a1"].fail_market = 2, True
    ads["a1"].order_status = {"u1": "Filled", "l1": "Canceled"}
    out = kill(desk)
    assert out["ok"] is False and out["results"]["a1"]["ok"] is False
    assert not {"us", "ut", "ds", "dt"} & set(ads["a1"].cancelled)   # stop/target left working
    assert eng.killed_today("nq930")                       # still killed for the day


def test_the_client_id_is_deduplicated(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    ads["a1"].net = 2
    first = kill(desk)
    ads["a1"].net = 2                                      # a second kill WOULD sell again
    assert kill(desk) == first
    assert len(ads["a1"].orders) == 1
    assert len([e for e in journal(tmp_path) if e["event"] == "strategy_killed"]) == 1


def test_bot_kill_validates_its_body(tmp_path):
    desk, *_ = mk(tmp_path)
    with pytest.raises(ValueError, match="unknown strategy 'nope'"):
        run(desk.bot_kill({"client_id": "c", "strategy": "nope"}))
    with pytest.raises(ValueError, match="client_id"):
        run(desk.bot_kill({"strategy": "nq930"}))
    with pytest.raises(ValueError, match="the body is a JSON object"):
        run(desk.bot_kill([1]))


def test_an_alert_after_the_kill_is_refused_and_places_nothing(tmp_path):
    desk, eng, ads, clock, cfg = mk(tmp_path, et=(9, 30))
    kill(desk)
    out = run(eng.handle_alert({"strategy": "nq930", "upper": 110.0, "lower": 90.0}))
    assert out["ok"] is False and "killed" in out["reason"]
    assert ads["a1"].brackets == []
    assert [e["reason"] for e in journal(tmp_path) if e["event"] == "alert_refused"] == ["killed"]
    # the other strategy still trades
    assert run(eng.handle_alert({"strategy": "es930", "upper": 102.0, "lower": 98.0}))["ok"] is True


@pytest.mark.parametrize("kill_at", [(9, 25), (9, 29)])       # before staging, and once staged
def test_the_timer_never_fires_a_killed_strategy(tmp_path, kill_at):
    desk, eng, ads, clock, cfg = mk(tmp_path, et=(9, 21), armed=False)
    md = FakeMD(last_trade=24500.0)
    timer = SelfTimer(cfg, eng, md_factory=lambda: md, now_fn=clock)
    run(timer.tick())                                          # gate
    if kill_at == (9, 29):
        clock.set_et(9, 29)
        run(timer.tick())                                      # staged
        assert timer.status()["strategies"]["nq930"]["stage"] == "staged"
    clock.set_et(*kill_at)
    kill(desk)
    for hm in ((9, 29), (9, 30), (9, 31)):
        clock.set_et(*hm)
        run(timer.tick())
    assert timer.status()["strategies"]["nq930"]["stage"] == "skipped"
    ev = journal(tmp_path)
    assert not any(e["event"] in ("dry_run", "timer_fired") for e in ev)
    assert [e.get("reason") for e in ev if e["event"] == "timer_skipped"] == ["killed"]


def test_the_kill_survives_a_restart_and_ends_with_the_day(tmp_path):
    desk, eng, ads, clock, cfg = mk(tmp_path)
    kill(desk)
    again = Engine(cfg, ads, now_fn=clock, root=tmp_path)
    assert again.killed_today("nq930") and not again.killed_today("es930")
    clock.dt = clock.dt + dt.timedelta(days=1)                # the next day
    assert not again.killed_today("nq930")


def test_a_kill_requested_but_never_finished_still_holds_after_a_restart(tmp_path):
    """Fix round 1 (review Minor 7): the desk died mid-kill -- only the request line is there."""
    desk, eng, ads, clock, cfg = mk(tmp_path, et=(9, 20))
    eng.journal("strategy_kill_requested", strategy="nq930", source="chart", client_id="k")
    again = Engine(cfg, ads, now_fn=clock, root=tmp_path)
    assert again.killed_today("nq930")
    clock.set_et(9, 30)
    out = run(again.handle_alert({"strategy": "nq930", "upper": 110.0, "lower": 90.0}))
    assert out["ok"] is False and ads["a1"].brackets == []


def test_a_kill_after_the_acks_that_raises_never_fails_the_placement(tmp_path):
    """Fix round 1 (review Minor 6)."""
    desk, eng, ads, clock, cfg = mk(tmp_path, et=(9, 30))
    ad = ads["a1"]
    gate = asyncio.Event()
    orig = ad.place_bracket

    async def slow(req):
        await gate.wait()
        return await orig(req)

    async def broken(symbol):
        raise RuntimeError("socket gone")

    ad.place_bracket, ad.get_net_position = slow, broken

    async def go():
        fire = asyncio.ensure_future(eng.handle_alert({"strategy": "nq930", "upper": 110.0,
                                                        "lower": 90.0}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await desk.bot_kill({"client_id": "k", "strategy": "nq930"})
        gate.set()
        return await fire

    out = run(go())
    assert out["ok"] is True and out["accounts"]["a1"]["ok"] is True     # the placement stands
    ev = [e for e in journal(tmp_path) if e["event"] in ("strategy_killed_after_ack", "strategy_kill_failed")]
    assert len(ev) == 1 and ev[0]["event"] == "strategy_killed_after_ack" and ev[0]["ok"] is False
    assert "position unreadable" in ev[0]["actions"][-1]
    assert eng._state("nq930", "a1").status == "placed"                 # its brackets keep working

    # an exception outside the kill's own handling -> strategy_kill_failed, still never raised
    async def boom(*a, **k):
        raise RuntimeError("boom")

    eng._kill_state = boom
    run(eng._kill_after_ack(eng._state("nq930", "a1"), cfg.strategies["nq930"], ad))
    assert journal(tmp_path)[-1]["event"] == "strategy_kill_failed"


def test_a_kill_that_lands_while_the_bot_is_placing_finishes_after_the_acks(tmp_path):
    desk, eng, ads, clock, cfg = mk(tmp_path, et=(9, 30))
    ad = ads["a1"]
    gate = asyncio.Event()
    orig = ad.place_bracket

    async def slow(req):
        await gate.wait()
        return await orig(req)

    ad.place_bracket = slow

    async def go():
        fire = asyncio.ensure_future(eng.handle_alert({"strategy": "nq930", "upper": 110.0,
                                                        "lower": 90.0}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert eng._state("nq930", "a1").status == "placing"
        k = await desk.bot_kill({"client_id": "k", "strategy": "nq930"})
        gate.set()
        await fire
        return k

    k = run(go())
    assert k["results"]["a1"]["ok"] is True and k["results"]["a1"]["pending"] is True
    st = eng._state("nq930", "a1")
    assert (st.status, st.exit_reason) == ("done", "killed")
    ids = [i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id) if i]
    assert len(ids) == 6 and sorted(ad.cancelled) == sorted(ids)
    assert any(e["event"] == "strategy_killed_after_ack" for e in journal(tmp_path))


# --- the routes (key-guarded like every /api/trade/* route) -------------------------------
def test_the_bot_routes_need_the_key_and_refuse_browsers(desk_client):
    c = desk_client
    assert c.post("/api/trade/bot-kill", json={"client_id": "c", "strategy": "nq930"}).status_code == 401
    assert c.get("/api/trade/bot-history?strategy=nq930").status_code == 401
    assert c.get("/api/trade/bot-history?strategy=nq930",
                 headers={**c.H, "origin": "http://127.0.0.1:8850"}).status_code == 403
    r = c.post("/api/trade/bot-kill", json={"client_id": "c", "strategy": "nq930"}, headers=c.H)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert c.post("/api/trade/bot-kill", json={"client_id": "c", "strategy": "x"},
                  headers=c.H).status_code == 400


def test_the_history_route_reads_the_journal(desk_client, monkeypatch):
    c = desk_client
    monkeypatch.setattr(c.app.state.desk, "history_paused", lambda: False)   # never flake near 9:30
    eng = c.app.state.engine
    today = eng.now_et().date().isoformat()
    lines = [{"ts": 1.0, "et": f"{today}T09:28:31-04:00", "event": "timer_skipped",
              "strategy": "nq930", "reason": "manual_order", "account": "a1"}]
    with open(c.tmp / "journal.jsonl", "a") as f:
        f.write("garbage\n" + "".join(json.dumps(x) + "\n" for x in lines))
    r = c.get("/api/trade/bot-history?strategy=nq930&days=5", headers=c.H)
    assert r.status_code == 200
    body = r.json()
    assert (body["strategy"], body["symbol"]) == ("nq930", "NQ")
    assert body["runs"] == [{"date": today, "account": "a1", "status": "skipped",
                             "reason": "manual_order", "legs": []}]
    assert c.get("/api/trade/bot-history?strategy=nq930&days=0", headers=c.H).status_code == 400
    assert c.get("/api/trade/bot-history?strategy=nope", headers=c.H).status_code == 400
    assert c.get("/api/trade/bot-history", headers=c.H).status_code == 400
    monkeypatch.setattr(c.app.state.desk, "history_paused", lambda: True)
    assert c.get("/api/trade/bot-history?strategy=nq930", headers=c.H).status_code == 503


@pytest.mark.parametrize("hms,paused", [((9, 28, 59), False), ((9, 29, 0), True), ((9, 30, 29), True),
                                        ((9, 30, 30), False)])
def test_history_pauses_from_0929_to_093030(tmp_path, hms, paused):
    desk, eng, ads, clock, cfg = mk(tmp_path)
    clock.dt = dt.datetime(2026, 9, 14, hms[0] + 4, hms[1], hms[2], tzinfo=dt.timezone.utc)
    assert desk.history_paused() is paused
    clock.dt = clock.dt + dt.timedelta(days=5)                    # Saturday: never paused by the clock
    assert desk.history_paused() is False


def test_a_failed_placement_is_never_flattened(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = eng._state("nq930", "a1")
    st.status, st.exit_reason, st.note = "error", "error", "account not connected"
    ads["a1"].net = 1                                      # not the bot's
    out = kill(desk)
    assert out["results"]["a1"] == {"ok": True, "actions": []}
    assert ads["a1"].orders == [] and ads["a1"].cancelled == []


def test_a_both_filled_error_nets_to_zero_so_only_its_brackets_go(tmp_path):
    """Both entries filled: the bot is +2 and -2 -> its own net is 0; the account's -1 is
    not the bot's by its own fills and is left alone (never more than the bot's quantity)."""
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    st.status, st.exit_reason = "error", "both_filled"
    ads["a1"].net = -1
    ads["a1"].order_status = {"u1": "Filled", "l1": "Filled"}
    out = kill(desk)
    assert out["results"]["a1"]["ok"] is True
    assert ads["a1"].orders == []
    assert {"us", "ut", "ds", "dt"} <= set(ads["a1"].cancelled)


def test_a_both_filled_error_with_the_bots_net_left_sells_that(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    st.status, st.exit_reason = "error", "both_filled"
    ads["a1"].net = 4                                     # bot +2 (sell side cancelled) + manual 2
    ads["a1"].order_status = {"u1": "Filled", "l1": "Canceled"}
    kill(desk)
    assert [(o.side, o.qty) for o in ads["a1"].orders] == [("Sell", 2)]
