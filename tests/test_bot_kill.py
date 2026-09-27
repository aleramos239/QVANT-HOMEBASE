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


def test_kill_flattens_its_contract_and_cancels_its_legs_on_its_booked_account_only(tmp_path):
    desk, eng, ads, clock, cfg = mk(tmp_path)
    nq = with_legs(eng._state("nq930", "a1"), NQ_IDS, "live")
    es = with_legs(eng._state("es930", "a1"), ES_IDS, "placed")
    ads["a1"].net = 2
    ads["a2"].net = 1                                     # a2: a manual NQ position, not booked
    out = kill(desk)
    assert out["ok"] is True and list(out["results"]) == ["a1"]
    r = out["results"]["a1"]
    assert r["ok"] is True and r["actions"][0] == "market Sell 2: ok"
    (o,) = ads["a1"].orders                               # the one market order, NQ, symbol-scoped
    assert (o.symbol, o.side, o.qty, o.order_type) == ("NQ", "Sell", 2, "Market")
    assert sorted(ads["a1"].cancelled) == sorted(NQ_IDS)  # its own legs only
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
    ev = [e for e in journal(tmp_path) if e["event"] == "strategy_killed"]
    assert len(ev) == 1 and ev[0]["strategy"] == "nq930" and ev[0]["client_id"] == "k1"
    assert ev[0]["results"]["a1"]["ok"] is True
    assert desk.bot_view()["strategies"]["nq930"]["killed"] is True
    assert desk.bot_view()["strategies"]["es930"]["killed"] is False


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
    out = kill(desk)
    assert out["ok"] is False and out["results"]["a1"]["ok"] is False
    assert ads["a1"].cancelled == []                       # stop/target left working
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


def test_the_history_route_reads_the_journal(desk_client):
    c = desk_client
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


def test_a_failed_placement_is_never_flattened(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = eng._state("nq930", "a1")
    st.status, st.exit_reason, st.note = "error", "error", "account not connected"
    ads["a1"].net = 1                                      # not the bot's
    out = kill(desk)
    assert out["results"]["a1"] == {"ok": True, "actions": []}
    assert ads["a1"].orders == [] and ads["a1"].cancelled == []


def test_a_both_filled_error_is_flattened(tmp_path):
    desk, eng, ads, *_ = mk(tmp_path)
    st = with_legs(eng._state("nq930", "a1"), NQ_IDS, "placed")
    st.status, st.exit_reason = "error", "both_filled"
    ads["a1"].net = -1
    out = kill(desk)
    assert out["results"]["a1"]["ok"] is True
    assert [(o.side, o.qty) for o in ads["a1"].orders] == [("Buy", 1)]
