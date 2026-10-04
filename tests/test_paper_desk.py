"""Algos on paper accounts: the desk's pool picks up the chart service's paper accounts, the engine runs a
straddle's whole life on one through the real paper book, and the chart-trading path never sees it.
No network: the chart service is a mock transport over a real PaperBooks."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.broker.paper import PaperAdapter
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.server import build_adapter, create_app
from tests.test_broker_paper import Service, adapter, run
from tests.test_engine import Clock, FakeAdapter

STRAT = StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True)


def paper_cfg(**kw) -> AppCfg:
    return AppCfg(armed=True, accounts={"paper": AccountCfg(paper=True, label="PAPER")},
                  book={"nq930": [{"account": "paper", "qty": 3}]}, strategies={"nq930": STRAT}, **kw)


def test_a_paper_account_builds_a_paper_adapter_and_nothing_else_does():
    assert isinstance(build_adapter("paper-3", AccountCfg(paper=True, label="x")), PaperAdapter)
    assert AccountCfg().paper is False                                # an old config entry is a broker account


def test_a_straddle_runs_its_whole_life_on_a_paper_account(tmp_path):
    """The real engine, the real adapter, the real book's fill law: placed -> entry fill (sibling cancelled,
    brackets re-priced from the fill) -> take-profit exit, graded and journaled like a broker account's."""
    svc = Service()
    ad = adapter(svc)
    eng = Engine(paper_cfg(), {"paper": ad}, now_fn=Clock(), root=tmp_path)

    async def deliver():
        await ad._deliver(await ad._read())

    run(ad.connect())
    run(ad.observe_fills(eng.on_fill))
    ad._task.cancel()                                                 # fills are pulled by hand: no timing
    svc.feed([("09:29:59", 100.0)])
    out = run(eng.handle_alert({"strategy": "nq930", "upper": 110.0, "lower": 90.0}))
    assert out["ok"] and out["accounts"]["paper"]["ok"]
    st = eng._state("nq930", "paper")
    assert st.status == "placed" and st.upper_id and st.lower_id and st.up_sl_id and st.up_tp_id

    svc.feed([("09:30:02", 110.0)])                                   # the buy stop touches: 110 + 1 tick
    run(deliver())
    assert (st.status, st.entry_side, st.entry_fill, st.entry_qty) == ("live", "Buy", 110.25, 3)
    book = {o["order_id"]: o for o in run(ad._read())["orders"]}
    assert st.lower_id not in book                                    # the sibling leg was cancelled
    assert book[st.up_sl_id]["stop_price"] == 105.25 and book[st.up_tp_id]["price"] == 125.25   # from the fill

    svc.feed([("09:30:05", 125.5)])                                   # 1-tick penetration of the limit target
    run(deliver())
    assert st.status == "done" and st.exit_reason == "tp" and st.exit_fill == 125.25
    assert st.pnl == round((125.25 - 110.25) * 20 * 3, 2)
    assert run(ad.get_net_position("NQ")) == 0
    events = [json.loads(l)["event"] for l in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert events[:4] == ["placed", "placed", "entry_fill", "exit_fill"] or \
        {"placed", "entry_fill", "exit_fill"} <= set(events)


def test_the_kill_path_flattens_a_paper_account(tmp_path):
    svc = Service()
    ad = adapter(svc)
    eng = Engine(paper_cfg(), {"paper": ad}, now_fn=Clock(), root=tmp_path)
    run(ad.connect())
    run(ad.observe_fills(eng.on_fill))
    ad._task.cancel()
    svc.feed([("09:29:59", 100.0)])
    run(eng.handle_alert({"strategy": "nq930", "upper": 110.0, "lower": 90.0}))
    svc.feed([("09:30:02", 110.0)])
    run(ad._deliver(run(ad._read())))
    assert run(ad.get_net_position("NQ")) == 3
    run(eng.flatten_today())
    svc.feed([("09:30:03", 109.75), ("09:30:04", 109.75)])
    assert run(ad.get_net_position("NQ")) == 0
    assert not run(ad._read())["orders"]


# ---- the desk server ----------------------------------------------------------------------------------------
@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    svc = Service(accounts=2)

    def listing(request):
        assert request.url.path == "/api/paper/accounts"
        return httpx.Response(200, json={"accounts": svc.books.listing(), "broken": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(listing), base_url="http://paper.test")
    cfg = AppCfg(armed=False, accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
                 book={"nq930": []}, strategies={"nq930": STRAT})
    adapters = {"main": FakeAdapter("main")}

    def factory(aid, a):
        if a.paper:
            return adapter(svc, aid)
        return FakeAdapter(aid)

    app = create_app(cfg, adapters, background=False, adapter_factory=factory, paper_client=client)
    app.state.engine.now_et = lambda: dt.datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app, c.svc, c.cfg = app, svc, cfg
        yield c


def test_the_pool_picks_up_every_chart_service_paper_account(desk):
    run(desk.app.state.sync_paper())
    assert {aid: (a.paper, a.label) for aid, a in desk.cfg.accounts.items() if a.paper} == {
        "paper": (True, "PAPER (paper)"), "paper-2": (True, "t0 (paper)")}
    run(desk.app.state.sync_paper())                                  # idempotent
    assert len(desk.cfg.accounts) == 3
    saved = json.loads(config_mod.config_path().read_text())["accounts"]
    assert saved["paper-2"]["paper"] is True and saved["main"].get("paper") in (None, False)


def test_a_paper_account_shows_as_paper_and_books_to_an_algo(desk):
    run(desk.app.state.sync_paper())
    r = desk.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "paper", "qty": 3}]})
    assert r.status_code == 200, r.text
    st = desk.get("/api/status").json()
    assert st["accounts"]["paper"]["env"] == "paper" and st["accounts"]["main"]["env"] == "demo"
    assert st["book"]["nq930"] == [{"account": "paper", "qty": 3}]


def test_a_paper_account_cannot_be_removed_from_the_desk(desk):
    run(desk.app.state.sync_paper())
    r = desk.post("/api/accounts/remove", json={"account": "paper"})
    assert r.status_code == 409 and "Charts page" in r.json()["detail"]
    assert "paper" in desk.cfg.accounts


def test_a_paper_account_gone_from_the_charts_page_can_be_removed_from_the_desk(desk):
    run(desk.app.state.sync_paper())
    desk.cfg.accounts["paper-4"] = AccountCfg(paper=True, label="3 (paper)", account_name="3")  # deleted on Charts
    desk.cfg.book["nq930"] = [{"account": "paper-4", "qty": 1}]
    r = desk.post("/api/accounts/remove", json={"account": "paper-4"})
    assert r.status_code == 200, r.text
    assert "paper-4" not in desk.cfg.accounts and desk.cfg.book["nq930"] == []
    assert "paper-4" not in json.loads(config_mod.config_path().read_text())["accounts"]
    run(desk.app.state.sync_paper())                                  # and it does not come back
    assert "paper-4" not in desk.cfg.accounts


def test_a_gone_paper_account_stays_when_the_charts_page_cannot_be_asked(desk, monkeypatch):
    desk.cfg.accounts["paper-4"] = AccountCfg(paper=True, label="3 (paper)", account_name="3")

    def down():
        raise httpx.ConnectError("chart service down")
    monkeypatch.setattr(desk.svc.books, "listing", down)
    r = desk.post("/api/accounts/remove", json={"account": "paper-4"})
    assert r.status_code == 409 and "reach" in r.json()["detail"]
    assert "paper-4" in desk.cfg.accounts


def test_the_chart_trading_path_never_lists_a_paper_account(tmp_path):
    from tests.trading_util import mkdesk
    chart_desk, _, adapters, _, _, _ = mkdesk(tmp_path)
    chart_desk.cfg.accounts["paper"] = AccountCfg(paper=True, label="PAPER (paper)")
    adapters["paper"] = PaperAdapter("paper", client=httpx.AsyncClient(base_url="http://paper.test"))
    snap = chart_desk.snapshot()
    assert [a["id"] for a in snap["accounts"]] == ["a1", "a2"]        # the pool's broker accounts only
    assert chart_desk._accts().keys() == {"a1", "a2"}
