"""Step B (B1): the desk knows a promoted Lab strategy -- the status block, the switch, limits, the book's refusals (both
ways), Remove, the readiness lines and the 2 s refresh. No network, no broker: fake adapters, a temp state folder, a temp
config.json and the conftest's temp store (HOMEBASE_DESKLAB_ROOT). With this task alone a Lab strategy can never place an
order: nothing here sends one."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import subprocess
import sys
import threading
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase import labcfg, labdesk
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.labdesk import LabDesk, Refused
from homebase.labrun import store
from homebase.server import compute_readiness, create_app
from tests.test_engine import FakeAdapter
from tests.test_server import SeededFakeAdapter

ET = ZoneInfo("America/New_York")
WED_10 = dt.datetime(2026, 9, 30, 10, 0, tzinfo=ET)
LAB = "lab_pp_orb"
MARK = ["ab", "2026-10-09T12:00:00+00:00"]
LIMITS = {"max_trades_day": 2, "max_qty": 1, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}
SET_FIRST = "Set the limits first."
FLATTEN_FIRST = "Flatten it first."
NOT_ON_DESK = "That strategy is not on the Desk."


def rec(name="pp_orb", promoted=MARK[1], **kw):
    return {"name": name, "id": f"draft_{name}", "label": "PP ORB", "root": "NQ", "source": "class X: pass\n", "sha256": "ab",
            "params": {}, "qty": 1, "run": {"id": "r1"}, "notes": [], "promoted_utc": promoted, "enabled": False,
            "commission": 2.5, "slippage_ticks": 1.0, "session_window": ["09:25", "16:00"], "bar_minutes": 5, **kw}


def desk_cfg():
    return AppCfg(armed=False,
                  accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN", label="Main"),
                            "eval1": AccountCfg(keyring_key="k", account_name="E1", label="Eval 1"),
                            "eval2": AccountCfg(keyring_key="k", account_name="E2", label="Eval 2")},
                  book={"nq930": [{"account": "main", "qty": 3}]},
                  strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True)})


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    return tmp_path


def plain_rounds(engine):
    """These tests drive the desk's CONFIG half with plain day states (status placing / placed / live / done). The
    engine's own bookkeeping of Lab rounds (task B2: engine.lab_open, engine.lab_rounds) has its own tests; here the
    desk falls back to the day states, as it does on an engine that has neither."""
    engine.lab_open = lambda name: []
    engine.lab_rounds = None
    return engine


def make_client(cfg=None, lab=True, own=True):
    """The desk with its Lab side ON (it is opt-in per desk: fix round 3, R1). own: one refresh has run, so it holds the
    store -- only a refresh takes it, and re-reads every sidecar in the same pass."""
    cfg = cfg or desk_cfg()
    adapters = {aid: SeededFakeAdapter(aid) for aid in cfg.accounts}
    app = create_app(cfg, adapters, background=False, adapter_factory=lambda aid, a: FakeAdapter(aid), lab=lab)
    app.state.engine.now_et = lambda: WED_10
    plain_rounds(app.state.engine)
    if lab and own:
        asyncio.run(app.state.labdesk.refresh())
    return app


@pytest.fixture()
def client(paths):
    """The desk with one promoted strategy (pp_orb, NQ, off, no limits, no account) and nq930 booked on main."""
    store.put(rec())
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app, c.cfg, c.engine, c.labdesk, c.tmp = app, app.state.cfg, app.state.engine, app.state.labdesk, paths
        yield c
        app.state.labdesk.close()                                                # the store's desk lock goes back


def status(c, name=LAB):
    return c.get("/api/status").json()["strategies"][name]


def journal(c, event):
    p = c.tmp / "journal.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["event"] == event] if p.exists() else []


def set_limits(c, name=LAB, **kw):
    return c.post("/api/lab-limits", json={"strategy": name, "limits": {**LIMITS, **kw}})


def book(c, rows, name=LAB):
    return c.post("/api/book", json={"strategy": name, "assignments": [{"account": a, "qty": q} for a, q in rows]})


def open_round(c, account="main", status_="live", name=LAB):
    st = c.engine._state(name, account)
    st.status, st.qty = status_, 1
    return st


def no_lab_in_config(c):
    p = c.tmp / "config.json"
    return not p.exists() or "lab_" not in p.read_text()


# ---------------------------------------------------------------- the status block
def test_a_promoted_strategy_is_a_desk_strategy_off_with_no_account(client):
    d = client.get("/api/status").json()
    s = d["strategies"][LAB]
    assert s["cfg"]["kind"] == "lab" and s["cfg"]["symbol"] == "NQ" and s["cfg"]["label"] == "PP ORB"
    assert s["cfg"]["enabled"] is False and s["cfg"]["shadow"] is False and s["cfg"]["self_fire"] is True
    assert s["day_status"] == "idle" and s["killed"] is False and s["accounts"] == []
    assert s["lab"] == {"name": "pp_orb", "mark": MARK, "limits": None, "state": "off", "why": None, "trades_today": 0,
                        "mode_today": None, "runner": {"alive": False, "age_s": None}, "rounds": [], "refused": [],
                        "read_only": False}
    assert d["strategies"]["nq930"]["lab"] is None                               # every other strategy: no block
    assert d["book"] == {"nq930": [{"account": "main", "qty": 3}]}               # no account on it yet


def test_the_status_states_the_desk_can_tell_without_the_runner(client):
    assert status(client)["lab"]["state"] == "off"
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    assert status(client)["lab"]["state"] == "shadow"                            # on, no account
    set_limits(client)
    assert book(client, [("eval1", 1)]).status_code == 200
    assert status(client)["lab"]["state"] == "disarmed"                          # on, an account, the desk disarmed
    client.cfg.armed = True
    assert status(client)["lab"]["state"] == "waiting"
    st = open_round(client, "eval1", "placed")
    assert status(client)["lab"]["state"] == "working"
    st.status, st.entry_side, st.entry_fill = "live", "Buy", 21450.25
    s = status(client)
    assert s["lab"]["state"] == "in_position"
    assert s["lab"]["rounds"] == [{"account": "eval1", "round": 1, "status": "live", "side": "Buy", "qty": 1, "entry_fill": 21450.25,
                                   "exit_fill": None, "exit_reason": None, "pnl": None, "why": None}]
    st.status = "error"
    assert status(client)["lab"]["state"] == "check"
    st.status = "done"
    client.engine.kill_today(LAB)
    s = status(client)
    assert (s["lab"]["state"], s["lab"]["why"]) == ("stopped", "Killed today.")


def test_the_runner_line_comes_from_its_heartbeat_file(client):
    now = dt.datetime.now(dt.timezone.utc)
    store.put_runner({"pid": 1, "seen_utc": (now - dt.timedelta(seconds=3)).isoformat()})
    asyncio.run(client.labdesk.refresh())
    r = status(client)["lab"]["runner"]
    assert r["alive"] is True and 2.5 <= r["age_s"] <= 10
    store.put_runner({"pid": 1, "seen_utc": (now - dt.timedelta(seconds=90)).isoformat()})
    asyncio.run(client.labdesk.refresh())
    r = status(client)["lab"]["runner"]
    assert r["alive"] is False and r["age_s"] >= 89
    store.put_runner({"pid": 1, "seen_utc": "not a time"})
    asyncio.run(client.labdesk.refresh())
    assert status(client)["lab"]["runner"] == {"alive": False, "age_s": None}


def test_a_status_block_that_cannot_be_built_never_breaks_the_status_route(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(client.labdesk, "_state", boom)
    d = client.get("/api/status")
    assert d.status_code == 200
    s = d.json()["strategies"]
    assert s[LAB]["lab"]["state"] == "check" and s[LAB]["lab"]["name"] == "pp_orb"
    assert s["nq930"]["lab"] is None and s["nq930"]["day_status"] == "idle"


# ---------------------------------------------------------------- the switch
def test_the_switch_writes_the_stores_record_and_never_config_json(client):
    r = client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    assert r.status_code == 200 and r.json() == {"ok": True, "strategy": LAB, "enabled": True}
    assert store.get("pp_orb")["enabled"] is True                               # ONE switch: the record's
    assert client.cfg.strategies[LAB].enabled is True and status(client)["cfg"]["enabled"] is True
    assert no_lab_in_config(client)
    assert journal(client, "strategy_toggled")[-1] == {**journal(client, "strategy_toggled")[-1], "strategy": LAB, "enabled": True}
    asyncio.run(client.labdesk.refresh())                                        # the next read agrees
    assert client.cfg.strategies[LAB].enabled is True
    r = client.post("/api/strategy", json={"strategy": LAB, "enabled": False})
    assert r.json()["enabled"] is False and store.get("pp_orb")["enabled"] is False
    assert client.cfg.strategies[LAB].enabled is False


def test_switching_on_a_record_promoted_again_is_refused(client):
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", sha256="cd"))            # promoted again behind the desk's back
    r = client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    assert r.status_code == 409 and r.json()["detail"] == "The Lab record changed. Try again."
    assert store.get("pp_orb")["enabled"] is False and client.cfg.strategies[LAB].enabled is False
    asyncio.run(client.labdesk.refresh())                                        # the desk reads the new promotion
    assert client.post("/api/strategy", json={"strategy": LAB, "enabled": True}).status_code == 200
    assert store.get("pp_orb")["enabled"] is True


def test_switching_off_is_never_refused_for_a_changed_record(client):
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", sha256="cd", enabled=True))
    r = client.post("/api/strategy", json={"strategy": LAB, "enabled": False})
    assert r.status_code == 200 and store.get("pp_orb")["enabled"] is False
    assert client.cfg.strategies[LAB].enabled is False


def test_the_other_strategies_switch_is_what_it_was(client):
    r = client.post("/api/strategy", json={"strategy": "nq930", "enabled": False}).json()
    assert r == {"ok": True, "strategy": "nq930", "enabled": False}
    saved = json.loads((client.tmp / "config.json").read_text())
    assert saved["strategies"]["nq930"]["enabled"] is False and set(saved["strategies"]) == {"nq930"}
    assert store.get("pp_orb")["enabled"] is False
    assert client.post("/api/strategy", json={"strategy": "lab_nope", "enabled": True}).status_code == 404


def test_flatten_and_turn_off_switches_the_record_off(client):
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    r = client.post("/api/strategy-flatten", json={"strategy": LAB})
    assert r.status_code == 200 and r.json() == {"ok": True, "enabled": False, "results": {}}
    assert store.get("pp_orb")["enabled"] is False and client.cfg.strategies[LAB].enabled is False
    assert no_lab_in_config(client)
    t = journal(client, "strategy_toggled")[-1]
    assert (t["strategy"], t["enabled"], t["cause"]) == (LAB, False, "manual_flatten")
    for ad in client.app.state.adapters.values():                               # with this task alone: no order, ever
        assert ad.orders == [] and ad.brackets == [] and ad.cancelled == []


# ---------------------------------------------------------------- limits
def test_limits_are_set_shown_and_kept_in_the_sidecar(client):
    r = set_limits(client)
    assert r.status_code == 200 and r.json() == {"ok": True, "strategy": LAB, "limits": {**LIMITS, "max_risk_usd": 300.0}}
    assert status(client)["lab"]["limits"] == {**LIMITS, "max_risk_usd": 300.0}
    assert status(client)["cfg"]["flat_et"] == "15:55" and client.cfg.strategies[LAB].accept_until_et == "11:00"
    side = store.get_desk("pp_orb")
    assert side["mark"] == MARK and side["limits"] == {**LIMITS, "max_risk_usd": 300.0} and side["book"] == []
    assert journal(client, "lab_limits_set")[-1]["strategy"] == LAB and no_lab_in_config(client)
    set_limits(client, flat_et="15:00", max_qty=3)
    assert store.get_desk("pp_orb")["limits"]["flat_et"] == "15:00" and client.cfg.strategies[LAB].flat_et == "15:00"


@pytest.mark.parametrize("change, sentence", [
    ({"max_trades_day": 0}, "Trades a day: a whole number from 1 to 20."),
    ({"max_qty": 11}, "Contracts: a whole number from 1 to 10."),
    ({"max_risk_usd": 0}, "At risk per trade: a dollar amount above 0."),
    ({"last_entry_et": "15:55"}, "No new trade after: a time like 11:00, before the flat time."),
    ({"flat_et": "16:00"}, "Flat by: a time like 15:55, no later than 15:55.")])
def test_bad_limits_are_refused_with_their_sentence_and_nothing_is_kept(client, change, sentence):
    r = set_limits(client, **change)
    assert r.status_code == 400 and r.json()["detail"] == sentence
    assert status(client)["lab"]["limits"] is None and store.get_desk("pp_orb") is None


def test_limits_bodies_that_are_not_limits(client):
    assert client.post("/api/lab-limits", json={"strategy": LAB}).status_code == 400
    assert client.post("/api/lab-limits", json={"strategy": LAB, "limits": "x"}).status_code == 400
    assert client.post("/api/lab-limits", json=["x"]).status_code == 400
    for name in ("nq930", "lab_nope", ""):
        r = set_limits(client, name)
        assert r.status_code == 404 and r.json()["detail"] == NOT_ON_DESK
    assert client.cfg.strategies["nq930"].flat_et == "15:55" and store.get_desk("pp_orb") is None


def test_limits_are_not_changed_in_the_930_window(client):
    client.engine.now_et = lambda: dt.datetime(2026, 9, 30, 9, 25, tzinfo=ET)   # a Wednesday
    r = set_limits(client)
    assert r.status_code == 409 and r.json()["detail"] == "Not 09:20-09:35 ET. Try again after 09:35."
    assert status(client)["lab"]["limits"] is None
    for ok in (dt.datetime(2026, 9, 30, 9, 19, 59, tzinfo=ET), dt.datetime(2026, 9, 30, 9, 35, tzinfo=ET),
               dt.datetime(2026, 10, 3, 9, 25, tzinfo=ET)):                      # before, after, a Saturday
        client.engine.now_et = lambda ok=ok: ok
        assert set_limits(client).status_code == 200


@pytest.mark.parametrize("st", ["placing", "placed", "live"])
def test_limits_are_not_changed_while_a_round_is_open(client, st):
    assert set_limits(client).status_code == 200
    open_round(client, "eval1", st)
    r = set_limits(client, max_trades_day=5)
    assert r.status_code == 409 and r.json()["detail"] == FLATTEN_FIRST
    assert status(client)["lab"]["limits"]["max_trades_day"] == 2
    client.engine._state(LAB, "eval1").status = "done"
    assert set_limits(client, max_trades_day=5).status_code == 200


def test_a_round_the_engine_calls_open_blocks_limits_too(client):
    """B2 adds engine.lab_open (a round placing / placed / live, or not clean): the desk asks it when it is there."""
    set_limits(client)
    client.engine.lab_open = lambda name: ["eval1"] if name == LAB else []
    assert set_limits(client, max_trades_day=5).json()["detail"] == FLATTEN_FIRST


def test_limits_that_could_not_be_saved_are_not_kept(client, monkeypatch):
    def busy(*a, **k):
        raise TimeoutError("busy")
    monkeypatch.setattr(store, "put_desk", busy)
    r = set_limits(client)
    assert r.status_code == 409 and r.json()["detail"] == "Could not save it. Try again."
    assert status(client)["lab"]["limits"] is None and labcfg.pending(client.cfg) == []


# ---------------------------------------------------------------- the book
def test_no_account_can_be_assigned_before_the_limits_are_set(client):
    r = book(client, [("eval1", 1)])
    assert r.status_code == 409 and r.json()["detail"] == SET_FIRST
    assert LAB not in client.cfg.book and store.get_desk("pp_orb") is None
    assert book(client, []).status_code == 200                                   # taking every account off needs no limits


def test_an_account_is_assigned_and_the_book_lives_in_the_sidecar(client):
    set_limits(client)
    r = book(client, [("eval1", 1)])
    assert r.status_code == 200 and r.json()["book"][LAB] == [{"account": "eval1", "qty": 1}]
    assert client.get("/api/status").json()["book"][LAB] == [{"account": "eval1", "qty": 1}]
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}] and store.get_desk("pp_orb")["mark"] == MARK
    assert not (client.tmp / "config.json").exists()                             # a Lab book write is not a config write
    config_mod.save(client.cfg)
    saved = json.loads((client.tmp / "config.json").read_text())
    assert set(saved["book"]) == {"nq930"} and set(saved["strategies"]) == {"nq930"} and no_lab_in_config(client)
    assert journal(client, "book_updated")[-1]["strategy"] == LAB
    assert book(client, []).status_code == 200
    assert store.get_desk("pp_orb")["book"] == [] and client.cfg.book[LAB] == []


def test_a_size_above_the_cap_is_refused(client):
    set_limits(client)
    r = book(client, [("eval1", 2)])
    assert r.status_code == 409 and r.json()["detail"] == "Size is capped at 1 here."
    set_limits(client, max_qty=3)
    assert book(client, [("eval1", 3)]).status_code == 200
    assert book(client, [("eval1", 4)]).json()["detail"] == "Size is capped at 3 here."


def test_one_strategy_per_market_per_account_for_the_lab_strategys_book(client):
    set_limits(client)
    r = book(client, [("main", 1)])                                              # nq930 trades NQ on main
    assert r.status_code == 409 and r.json()["detail"] == "Another strategy trades NQ on this account."
    assert LAB not in client.cfg.book
    assert book(client, [("eval1", 1), ("main", 1)]).status_code == 409         # any row of the write
    assert book(client, [("eval1", 1)]).status_code == 200


def test_one_strategy_per_market_per_account_for_every_other_strategys_book_too(client):
    set_limits(client)
    assert book(client, [("eval1", 1)]).status_code == 200
    r = book(client, [("main", 3), ("eval1", 1)], "nq930")                       # nq930 onto the Lab strategy's account
    assert r.status_code == 409 and r.json()["detail"] == "Another strategy trades NQ on this account."
    assert client.cfg.book["nq930"] == [{"account": "main", "qty": 3}]
    assert book(client, [("main", 2), ("eval2", 1)], "nq930").status_code == 200   # other accounts: as ever
    assert book(client, [], LAB).status_code == 200                              # the Lab strategy leaves eval1
    assert book(client, [("main", 3), ("eval1", 1)], "nq930").status_code == 200


def test_the_market_rule_is_the_engines_substring_rule_and_other_markets_share_an_account(paths):
    store.put(rec("micro_one", root="MNQ"))
    store.put(rec("gold_one", root="GC"))
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        for n in ("lab_micro_one", "lab_gold_one"):
            assert set_limits(c, n).status_code == 200
        r = book(c, [("main", 1)], "lab_micro_one")                              # NQ is inside MNQ: one market
        assert r.status_code == 409 and r.json()["detail"] == "Another strategy trades NQ on this account."
        assert book(c, [("main", 1)], "lab_gold_one").status_code == 200         # gold beside nq930: fine
        assert book(c, [("eval1", 1)], "lab_micro_one").status_code == 200
        r = book(c, [("main", 3), ("eval1", 1)], "nq930")
        assert r.status_code == 409 and r.json()["detail"] == "Another strategy trades MNQ on this account."


def test_two_strategies_that_are_not_from_the_lab_are_never_judged(paths):
    """The rule needs a Lab strategy on one side: the desk's own strategies book as they always did."""
    cfg = desk_cfg()
    cfg.strategies["nq_two"] = StrategyCfg(symbol="NQ", qty=1, offset_pts=5.0, sl_pts=5.0, tp_pts=15.0)
    store.put(rec())
    app = make_client(cfg)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        assert book(c, [("main", 1)], "nq_two").status_code == 200               # beside nq930 on main, as before


def test_two_rows_on_one_broker_account_are_refused(client):
    set_limits(client)
    client.app.state.adapters["eval1"].__class__ = type("SameBroker", (SeededFakeAdapter,), {"broker_key": ("demo", 77)})
    client.app.state.adapters["eval2"].__class__ = client.app.state.adapters["eval1"].__class__
    r = book(client, [("eval1", 1), ("eval2", 1)])
    assert r.status_code == 409 and r.json()["detail"] == "That is the same broker account as Eval 1."
    assert book(client, [("eval1", 1)]).status_code == 200
    r = book(client, [("eval1", 1), ("eval1", 1)])                               # the same desk entry twice
    assert r.status_code == 409 and r.json()["detail"] == "That is the same broker account as Eval 1."


def test_an_account_with_an_open_round_cannot_be_taken_off(client):
    set_limits(client)
    book(client, [("eval1", 1), ("eval2", 1)])
    open_round(client, "eval1", "live")
    r = book(client, [("eval2", 1)])
    assert r.status_code == 409 and r.json()["detail"] == FLATTEN_FIRST
    assert client.cfg.book[LAB] == [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 1}]
    assert book(client, [("eval1", 1)]).status_code == 200                       # the flat one may go
    client.engine._state(LAB, "eval1").status = "done"
    assert book(client, []).status_code == 200


def test_a_book_that_could_not_be_saved_is_put_back(client, monkeypatch):
    set_limits(client)
    assert book(client, [("eval1", 1)]).status_code == 200

    def busy(*a, **k):
        raise TimeoutError("busy")
    monkeypatch.setattr(store, "put_desk", busy)
    r = book(client, [])                                                         # taking the account off cannot be written
    assert r.status_code == 409 and r.json()["detail"] == "Could not save it. Try again."
    assert client.cfg.book[LAB] == [{"account": "eval1", "qty": 1}]              # so it is still on, and the page says so
    assert labcfg.pending(client.cfg) == []


def test_an_account_removed_from_the_desk_leaves_the_lab_strategys_sidecar(client):
    set_limits(client)
    book(client, [("eval1", 1), ("eval2", 1)])
    assert client.post("/api/accounts/remove", json={"account": "eval2"}).status_code == 200
    assert client.cfg.book[LAB] == [{"account": "eval1", "qty": 1}]
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}] and no_lab_in_config(client)


def test_with_no_lab_strategy_the_book_route_is_what_it_was(paths):
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        r = c.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "main", "qty": 2}, {"account": "eval1", "qty": 1}]})
        assert r.status_code == 200 and r.json() == {"ok": True, "book": {"nq930": [{"account": "main", "qty": 2}, {"account": "eval1", "qty": 1}]}}
        assert c.get("/api/status").json()["strategies"]["nq930"]["lab"] is None
        assert c.post("/api/lab-limits", json={"strategy": "nq930", "limits": LIMITS}).status_code == 404
        assert c.post("/api/lab-remove", json={"strategy": "nq930"}).status_code == 404
        assert set(app.state.cfg.strategies) == {"nq930"}


# ---------------------------------------------------------------- remove
def test_remove_takes_it_off_the_desk_and_keeps_the_history(client):
    set_limits(client)
    book(client, [("eval1", 1)])
    store.put_day("pp_orb", {"date": "2026-09-29", "sha256": "ab", "state": "done"})
    r = client.post("/api/lab-remove", json={"strategy": LAB})
    assert r.status_code == 200 and r.json() == {"ok": True, "removed": LAB}
    assert store.get("pp_orb") is None and store.get_desk("pp_orb") is None
    assert store.get_day("pp_orb", "2026-09-29") is not None                     # the days stay
    assert LAB not in client.cfg.strategies and LAB not in client.cfg.book
    d = client.get("/api/status").json()
    assert LAB not in d["strategies"] and LAB not in d["book"] and "nq930" in d["strategies"]
    assert journal(client, "lab_removed")[-1]["strategy"] == LAB and no_lab_in_config(client)
    assert client.post("/api/lab-remove", json={"strategy": LAB}).status_code == 404


def test_remove_is_refused_while_a_round_is_open(client):
    set_limits(client)
    book(client, [("eval1", 1)])
    open_round(client, "eval1", "placed")
    r = client.post("/api/lab-remove", json={"strategy": LAB})
    assert r.status_code == 409 and r.json()["detail"] == FLATTEN_FIRST
    assert store.get("pp_orb") is not None and client.cfg.book[LAB] == [{"account": "eval1", "qty": 1}]


def test_remove_never_touches_a_strategy_that_is_not_from_the_lab(client):
    for name in ("nq930", "lab_nope", ""):
        r = client.post("/api/lab-remove", json={"strategy": name})
        assert r.status_code == 404 and r.json()["detail"] == NOT_ON_DESK
    assert "nq930" in client.cfg.strategies and client.cfg.book["nq930"] == [{"account": "main", "qty": 3}]
    assert client.post("/api/lab-remove", json=["x"]).status_code == 400


# ---------------------------------------------------------------- readiness
def lab_checks(c, now=WED_10):
    r = compute_readiness(now, c.cfg, c.engine, {}, {"connected": False, "watching": {}}, {"strategies": {}}, None)
    return [x for x in r["checks"] if x["label"] == "PP ORB"]


def test_readiness_an_enabled_lab_strategy_with_no_account_is_info_not_a_warning(client):
    assert lab_checks(client) == []                                              # off: not part of the day
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    assert lab_checks(client) == [{"level": "info", "label": "PP ORB", "detail": "no account: runs in shadow"}]


def test_readiness_an_idle_lab_strategy_past_its_last_entry_is_not_a_missing_signal(client):
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    set_limits(client)
    book(client, [("eval1", 1)])
    late = dt.datetime(2026, 9, 30, 13, 0, tzinfo=ET)                            # after "no new trade after" 11:00
    assert lab_checks(client, late) == []                                        # no "no signal arrived" line
    st = open_round(client, "eval1", "live")
    assert lab_checks(client, late) == [{"level": "ok", "label": "PP ORB", "detail": "live"}]
    st.status = "done"
    assert lab_checks(client, late) == [{"level": "ok", "label": "PP ORB", "detail": "done"}]


def test_readiness_of_the_other_strategies_is_what_it_was(client):
    client.post("/api/book", json={"strategy": "nq930", "assignments": []})
    r = client.get("/api/status").json()["readiness"]
    assert {"level": "warn", "label": "nq930", "detail": "enabled but no accounts assigned"} in r["checks"]
    late = dt.datetime(2026, 9, 30, 13, 0, tzinfo=ET)
    client.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "main", "qty": 3}]})
    got = compute_readiness(late, client.cfg, client.engine, {}, None, None, None)["checks"]
    assert {"level": "bad", "label": "nq930", "detail": "no signal arrived — this strategy trades every day"} in got


# ---------------------------------------------------------------- the refresh (LabDesk on a real engine, no HTTP)
def make_desk(tmp_path, cfg=None, paused=lambda: False, own=True):
    """own: its first refresh has run (as run() does at the start), so it holds the store if no other desk does."""
    cfg = cfg or desk_cfg()
    adapters = {aid: FakeAdapter(aid) for aid in cfg.accounts}
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = plain_rounds(Engine(cfg, adapters, now_fn=lambda: WED_10.astimezone(dt.timezone.utc), root=tmp_path))
    labdesk.attach(cfg)
    ld = LabDesk(cfg, engine, adapters, paused=paused)
    if own:
        asyncio.run(ld.refresh())
    return ld, cfg, engine


def jl(tmp_path, event):
    p = tmp_path / "journal.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["event"] == event] if p.exists() else []


def test_refresh_finds_a_strategy_promoted_after_the_start_and_one_that_left(tmp_path):
    ld, cfg, _ = make_desk(tmp_path)
    assert labcfg.lab_ids(cfg) == []
    store.put(rec())
    assert asyncio.run(ld.refresh()) == {"added": [LAB], "removed": [], "changed": []}
    assert cfg.strategies[LAB].kind == "lab" and jl(tmp_path, "lab_added")[-1]["strategy"] == LAB
    store.remove("pp_orb")
    assert asyncio.run(ld.refresh()) == {"added": [], "removed": [LAB], "changed": []}
    assert LAB not in cfg.strategies and jl(tmp_path, "lab_removed")[-1]["strategy"] == LAB


def test_refresh_never_removes_a_strategy_while_the_engine_holds_an_open_round(tmp_path):
    store.put(rec(enabled=True))
    ld, cfg, engine = make_desk(tmp_path)
    st = engine._state(LAB, "eval1")
    st.status = "live"
    store.remove("pp_orb")
    asyncio.run(ld.refresh())
    assert LAB in cfg.strategies and cfg.strategies[LAB].enabled is False        # kept for the round, switched off
    st.status = "done"
    asyncio.run(ld.refresh())
    assert LAB not in cfg.strategies


def test_refresh_reads_the_disk_in_a_thread_and_changes_the_config_on_the_loop(tmp_path, monkeypatch):
    ld, cfg, _ = make_desk(tmp_path)
    store.put(rec())
    main, seen = threading.get_ident(), {}
    real_read, real_apply = labcfg.read_store, labcfg.apply
    monkeypatch.setattr(labcfg, "read_store", lambda *a, **k: (seen.__setitem__("read", threading.get_ident()), real_read(*a, **k))[1])
    monkeypatch.setattr(labcfg, "apply", lambda *a, **k: (seen.__setitem__("apply", threading.get_ident()), real_apply(*a, **k))[1])

    async def go():
        seen["loop"] = threading.get_ident()
        return await ld.refresh()
    assert asyncio.run(go())["added"] == [LAB]
    assert seen["read"] != seen["loop"] and seen["apply"] == seen["loop"] and seen["loop"] == main


def test_refresh_is_skipped_while_the_views_are_paused(tmp_path, monkeypatch):
    paused = {"on": True}
    ld, cfg, _ = make_desk(tmp_path, paused=lambda: paused["on"])
    store.put(rec())
    reads = []
    real = labcfg.read_store
    monkeypatch.setattr(labcfg, "read_store", lambda *a, **k: (reads.append(1), real(*a, **k))[1])
    assert asyncio.run(ld.refresh()) is None and reads == [] and LAB not in cfg.strategies      # not even a disk read
    paused["on"] = False
    assert asyncio.run(ld.refresh())["added"] == [LAB]


def test_a_fire_that_begins_during_the_read_puts_the_change_off(tmp_path, monkeypatch):
    paused = {"on": False}
    ld, cfg, _ = make_desk(tmp_path, paused=lambda: paused["on"])
    store.put(rec())
    real = labcfg.read_store
    monkeypatch.setattr(labcfg, "read_store", lambda *a, **k: (paused.__setitem__("on", True), real(*a, **k))[1])
    assert asyncio.run(ld.refresh()) is None and LAB not in cfg.strategies
    monkeypatch.setattr(labcfg, "read_store", real)
    paused["on"] = False
    assert asyncio.run(ld.refresh())["added"] == [LAB]


def test_a_read_that_began_before_the_owner_switched_it_off_is_thrown_away(tmp_path, monkeypatch):
    """The store read runs in a thread. If the owner turns the strategy OFF while it runs, what it read (still ON) must
    never be put over the desk's memory: for two seconds the desk would believe an off strategy is on."""
    store.put(rec(enabled=True))
    ld, cfg, _ = make_desk(tmp_path)
    assert cfg.strategies[LAB].enabled is True
    real = labcfg.read_store
    reading, go_on = threading.Event(), threading.Event()

    def slow(*a, **k):
        got = real(*a, **k)                                                      # read: still on
        reading.set()
        go_on.wait(5)
        return got
    monkeypatch.setattr(labcfg, "read_store", slow)

    async def both():
        t = asyncio.create_task(ld.refresh())
        await asyncio.to_thread(reading.wait, 5)
        assert await ld.set_enabled(LAB, False) is True                          # the owner's switch, during the read
        go_on.set()
        return await t
    assert asyncio.run(both()) is None                                           # thrown away
    assert cfg.strategies[LAB].enabled is False and store.get("pp_orb")["enabled"] is False
    monkeypatch.setattr(labcfg, "read_store", real)
    asyncio.run(ld.refresh())
    assert cfg.strategies[LAB].enabled is False


def test_refresh_writes_what_the_overlay_cleaned_out_of_a_sidecar(tmp_path):
    store.put(rec(promoted="2026-10-10T08:00:00+00:00"))                         # promoted again since the sidecar
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    ld, cfg, _ = make_desk(tmp_path)
    assert LAB not in cfg.book
    asyncio.run(ld.refresh())
    side = store.get_desk("pp_orb")
    assert side["book"] == [] and side["mark"] == ["ab", "2026-10-10T08:00:00+00:00"] and side["limits"]["max_trades_day"] == 2


def test_the_refresh_task_journals_an_error_and_keeps_going(tmp_path, monkeypatch):
    ld, cfg, _ = make_desk(tmp_path)
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) <= 3:
            raise RuntimeError("the store is on fire")
        return None
    monkeypatch.setattr(ld, "refresh", flaky)

    async def go():
        t = asyncio.create_task(ld.run(interval_s=0.001))
        while len(calls) < 6:
            await asyncio.sleep(0.001)
        assert not t.done()                                                      # three errors did not kill it
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
    asyncio.run(go())
    errs = jl(tmp_path, "lab_refresh_error")
    assert len(errs) == 1 and "on fire" in errs[0]["error"]                      # the same error is said once, not every 2 s


def test_the_refresh_task_survives_a_journal_that_cannot_be_written(tmp_path, monkeypatch):
    ld, cfg, engine = make_desk(tmp_path)
    calls = []

    async def boom():
        calls.append(1)
        raise RuntimeError("x")
    monkeypatch.setattr(ld, "refresh", boom)
    monkeypatch.setattr(engine, "journal", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    async def go():
        t = asyncio.create_task(ld.run(interval_s=0.001))
        while len(calls) < 4:
            await asyncio.sleep(0.001)
        assert not t.done()
        t.cancel()
    asyncio.run(go())


def test_the_desk_runs_the_refresh_task_only_in_the_background(paths, monkeypatch):
    ran = []

    async def fake_run(self, interval_s=2.0):
        ran.append(interval_s)
    monkeypatch.setattr(LabDesk, "run", fake_run)
    with TestClient(make_client(), base_url="http://127.0.0.1:8850"):
        pass
    assert ran == []                                                             # background=False: no task
    assert labdesk.REFRESH_S == 2.0


# ---------------------------------------------------------------- the desk's start
def test_the_desk_starts_with_a_store_it_cannot_read(paths, monkeypatch):
    """A Lab problem never stops the desk: nq930 must trade whatever the store looks like."""
    def boom(*a, **k):
        raise OSError("the store folder is gone")
    monkeypatch.setattr(labcfg, "read_store", boom)
    app = make_client(own=False)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        d = c.get("/api/status").json()
        assert set(d["strategies"]) == {"nq930"} and d["strategies"]["nq930"]["lab"] is None
        assert c.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "main", "qty": 1}]}).status_code == 200


def test_the_after_save_hook_is_registered_once_however_many_desks_are_built(paths):
    for _ in range(3):
        make_client()
    assert config_mod._after_save.count(labcfg.persist_all) == 1


def test_a_desk_started_on_a_booked_strategy_reads_its_limits_and_book_and_writes_nothing(paths):
    store.put(rec(enabled=True))
    side = {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"}
    store.put_desk("pp_orb", side)
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        d = c.get("/api/status").json()
        assert d["book"][LAB] == [{"account": "eval1", "qty": 1}] and d["strategies"][LAB]["lab"]["limits"] == side["limits"]
        assert d["strategies"][LAB]["cfg"]["enabled"] is True
    assert store.get_desk("pp_orb") == side and not (paths / "config.json").exists()


def test_nothing_in_this_task_can_send_an_order(client):
    """Every route of this task, on a booked, enabled, armed Lab strategy: the adapters never hear of it."""
    client.cfg.armed = True
    set_limits(client)
    book(client, [("eval1", 1), ("eval2", 1)])
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    asyncio.run(client.labdesk.refresh())
    client.get("/api/status")
    client.post("/api/strategy", json={"strategy": LAB, "enabled": False})
    client.post("/api/strategy-flatten", json={"strategy": LAB})
    book(client, [])
    client.post("/api/lab-remove", json={"strategy": LAB})
    for ad in client.app.state.adapters.values():
        assert ad.orders == [] and ad.brackets == [] and ad.cancelled == [] and ad.modified == []
        assert ad.cancel_all_calls == 0 and ad.flatten_calls == 0


# ---------------------------------------------------------------- LabDesk said directly
def test_check_book_and_refused_carry_the_sentence(tmp_path):
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    with pytest.raises(Refused) as e:
        ld.check_book(LAB, [{"account": "eval1", "qty": 1}])
    assert str(e.value) == SET_FIRST and e.value.status == 409
    ld.check_book("nq930", [{"account": "main", "qty": 3}, {"account": "eval1", "qty": 1}])    # nothing to say
    assert ld.status_view("nq930") is None and ld.status_view("nope") is None


def test_strategy_code_never_runs_in_the_desk_process():
    code = ("import sys; import homebase.labdesk, homebase.labcfg\n"
            "bad = sorted(m for m in sys.modules if m.startswith('homebase.backtest'))\n"
            "print(bad); sys.exit(1 if bad else 0)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_a_test_alert_on_a_lab_strategy_places_nothing_and_leaves_no_state(client):
    """The desk's other ways in (alerts, the 9:30 timer, the levels timer, the bar feed) all filter on the kind."""
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    set_limits(client)
    book(client, [("eval1", 1)])
    r = client.post("/api/test-alert", json={"strategy": LAB})
    assert r.status_code == 200 and r.json()["result"]["ok"] is False
    assert client.engine.day_states(LAB) == [] and status(client)["day_status"] == "idle"
    for ad in client.app.state.adapters.values():
        assert ad.orders == [] and ad.brackets == []
    client.app.state.inactive_sweep(dt.datetime(2026, 9, 30, 13, 0, tzinfo=ET))  # the "will not trade today" sweep: nothing to say
    assert [r for r in journal(client, "inactive_today") if r["strategy"] == LAB] == []


# =====================================================================================================================
# Fix round 1 (review of B1)
# =====================================================================================================================
import time

L3 = {**LIMITS, "max_qty": 3}
BOOKED_FOR_MORE = "An account is booked for more. Lower its size first."
NOT_SAVED = "Could not save it. Try again."
OTHER_DESK = "Another Desk is running on this store."
CANNOT_READ = "The Desk cannot read it."
CANNOT_READ_LIMITS = "The Desk cannot read its limits."


def hold_the_store():
    """Another writer (the chart service promoting, say) holds the store's write lock. Returns release()."""
    inside, release = threading.Event(), threading.Event()

    def holder():
        with store.write_lock():
            inside.set()
            release.wait(10)
    t = threading.Thread(target=holder)
    t.start()
    assert inside.wait(5)

    def done():
        release.set()
        t.join(5)
    return done


def refused(coro):
    with pytest.raises(Refused) as e:
        asyncio.run(coro)
    return str(e.value), e.value.status


# ---- item 1
def test_lowering_most_contracts_below_a_booked_size_is_refused_and_nothing_changes(client):
    assert set_limits(client, max_qty=3).status_code == 200
    assert book(client, [("eval1", 3), ("eval2", 1)]).status_code == 200
    before = store.get_desk("pp_orb")
    r = set_limits(client, max_qty=2)
    assert r.status_code == 409 and r.json()["detail"] == BOOKED_FOR_MORE
    assert status(client)["lab"]["limits"]["max_qty"] == 3 and client.cfg.book[LAB][0] == {"account": "eval1", "qty": 3}
    assert store.get_desk("pp_orb") == before
    assert set_limits(client, max_qty=3, max_trades_day=5).status_code == 200    # the same cap, another field: fine
    assert book(client, [("eval1", 2), ("eval2", 1)]).status_code == 200         # he lowers the size first
    assert set_limits(client, max_qty=2).status_code == 200


# ---- item 2 (the reviewer's probe 1)
def test_a_sidecar_whose_limits_no_longer_read_shows_check_has_no_book_and_is_left_on_disk(paths):
    store.put(rec(enabled=True))
    disk = {"mark": MARK, "limits": {**L3, "flat_et": "16:30"}, "book": [{"account": "eval1", "qty": 5}], "written_utc": "x"}
    store.put_desk("pp_orb", disk)
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp, c.cfg = paths, app.state.cfg
        d = c.get("/api/status").json()
        s = d["strategies"][LAB]
        assert (s["lab"]["state"], s["lab"]["why"], s["lab"]["limits"]) == ("check", CANNOT_READ_LIMITS, None)
        assert LAB not in d["book"]
        for _ in range(2):
            asyncio.run(app.state.labdesk.refresh())
        assert store.get_desk("pp_orb") == disk                                  # never `limits: null` over what he typed
        assert journal(c, "lab_unbooked") == [{**journal(c, "lab_unbooked")[0], "strategy": LAB, "accounts": ["eval1"],
                                               "why": "limits unreadable"}]      # said once
        r = book(c, [("eval1", 1)])
        assert r.status_code == 409 and r.json()["detail"] == SET_FIRST
        assert book(c, []).status_code == 200 and store.get_desk("pp_orb") == disk    # nothing to take off, nothing written
        assert set_limits(c).status_code == 200                                  # he saves limits again
        assert status(c)["lab"]["state"] == "shadow" and status(c)["lab"]["limits"]["flat_et"] == "15:55"
        got = store.get_desk("pp_orb")
        assert got["limits"]["flat_et"] == "15:55" and got["book"] == []
        assert book(c, [("eval1", 1)]).status_code == 200
        app.state.labdesk.close()


def test_a_row_above_the_cap_on_disk_is_dropped_at_the_start_and_said(paths):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 5}, {"account": "eval2", "qty": 1}],
                              "written_utc": "x"})
    ld, cfg, _ = make_desk(paths)
    assert cfg.book[LAB] == [{"account": "eval2", "qty": 1}]
    asyncio.run(ld.refresh())
    said = jl(paths, "lab_unbooked")
    assert [(r["strategy"], r["accounts"], r["why"]) for r in said] == [(LAB, ["eval1"], "above the size cap")]
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 1}]


def test_a_row_that_reaches_the_desks_memory_without_a_route_is_dropped_by_the_next_refresh(client):
    set_limits(client)
    book(client, [("eval1", 1)])
    client.cfg.book[LAB].append({"account": "eval2", "qty": 4})                  # as the "account is back" re-booking would
    asyncio.run(client.labdesk.refresh())
    assert client.cfg.book[LAB] == [{"account": "eval1", "qty": 1}]
    assert journal(client, "lab_unbooked")[-1]["accounts"] == ["eval2"]
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}]


# ---- item 3 (the reviewer's probe 7)
def test_a_save_never_stands_still_for_a_store_another_process_holds(client):
    set_limits(client)
    book(client, [("eval1", 1)])
    done = hold_the_store()
    try:
        client.cfg.book[LAB] = []                                                # memory changed; any config.save follows
        t0 = time.perf_counter()
        config_mod.save(client.cfg)                                              # /api/kill, an account removed, ...
        assert time.perf_counter() - t0 < 0.05
        assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}]     # missed: still pending
        t0 = time.perf_counter()
        assert asyncio.run(client.labdesk.refresh()) is not None                 # the refresh does not wait either ...
        assert time.perf_counter() - t0 < 0.5
        assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}] and labcfg.pending(client.cfg) != []

        async def a_few_rounds():
            t = asyncio.create_task(client.labdesk.run(interval_s=0.001))
            await asyncio.sleep(0.05)
            t.cancel()
        asyncio.run(a_few_rounds())
        assert journal(client, "lab_refresh_error") == []                        # ... and a miss is not an error (fix round 2, H)
    finally:
        done()
    asyncio.run(client.labdesk.refresh())                                        # the next refresh writes it
    assert store.get_desk("pp_orb")["book"] == []


# ---- item 4
@pytest.mark.parametrize("when, allowed", [
    ((2026, 9, 30, 9, 19, 59), True), ((2026, 9, 30, 9, 20, 0), False), ((2026, 9, 30, 9, 34, 59), False),
    ((2026, 9, 30, 9, 35, 0), True), ((2026, 10, 3, 9, 30, 0), True)])           # a Wednesday; the last one a Saturday
def test_the_quiet_windows_edges_for_limits(client, when, allowed):
    client.engine.now_et = lambda: dt.datetime(*when, tzinfo=ET)
    r = set_limits(client)
    if allowed:
        assert r.status_code == 200
    else:
        assert r.status_code == 409 and r.json()["detail"] == "Not 09:20-09:35 ET. Try again after 09:35."
        assert status(client)["lab"]["limits"] is None


# ---- item 5 (the reviewer's probe 2)
def test_a_second_desk_on_the_store_reads_only(tmp_path):
    store.put(rec(enabled=True))
    disk = {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"}
    store.put_desk("pp_orb", disk)
    first, cfg1, _ = make_desk(tmp_path / "one")
    assert first.owner() is True
    other = AppCfg(accounts={"demo": AccountCfg(keyring_key="k", account_name="D", label="Demo")},
                   strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0)})
    second, cfg2, _ = make_desk(tmp_path / "two", other)
    for _ in range(3):
        asyncio.run(second.refresh())
    assert LAB in cfg2.strategies and config_mod.assignments(cfg2, LAB) == []    # it sees the strategy; the account is not its own
    assert store.get_desk("pp_orb") == disk and store.booked("pp_orb")           # the first desk's sidecar is untouched
    assert len(jl(tmp_path / "two", "lab_store_busy")) == 1 and jl(tmp_path / "two", "lab_unbooked") == []
    v = second.status_view(LAB)
    assert v["state"] == "shadow" and v["read_only"] is True and first.status_view(LAB)["read_only"] is False
    assert refused(second.set_limits(LAB, LIMITS)) == (OTHER_DESK, 409)
    assert refused(second.set_book(LAB, [{"account": "demo", "qty": 1}])) == (OTHER_DESK, 409)
    assert refused(second.set_book(LAB, [])) == (OTHER_DESK, 409)
    assert refused(second.set_enabled(LAB, True)) == (OTHER_DESK, 409)
    assert refused(second.remove(LAB)) == (OTHER_DESK, 409)
    assert store.get("pp_orb")["enabled"] is True and store.get_desk("pp_orb") == disk
    store.remove("pp_orb")                                                       # the record goes by hand
    asyncio.run(second.refresh())
    assert store.get_desk("pp_orb") == disk                                      # a reader never removes a sidecar
    assert len(jl(tmp_path / "two", "lab_store_busy")) == 1                      # said once
    assert "unbooked" not in jl(tmp_path / "two", "lab_removed")[-1]             # it un-booked nothing


def test_the_first_desk_still_works_while_a_second_one_reads(tmp_path):
    store.put(rec())
    first, cfg1, _ = make_desk(tmp_path / "one")
    second, cfg2, _ = make_desk(tmp_path / "two")
    asyncio.run(first.set_limits(LAB, LIMITS))
    asyncio.run(second.refresh())
    asyncio.run(first.set_book(LAB, [{"account": "eval1", "qty": 1}]))
    assert asyncio.run(first.set_enabled(LAB, True)) is True
    for _ in range(2):
        asyncio.run(second.refresh())
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}] and store.get("pp_orb")["enabled"] is True
    assert cfg2.strategies[LAB].enabled is True                                  # the reader follows the record


def test_the_routes_of_a_second_desk_answer_another_desk_is_running(paths):
    store.put(rec())
    one = make_client()
    two = make_client()
    with TestClient(one, base_url="http://127.0.0.1:8850") as c1, TestClient(two, base_url="http://127.0.0.1:8850") as c2:
        c1.tmp = c2.tmp = paths
        assert set_limits(c1).status_code == 200                                 # the first to act owns the store
        for r in (set_limits(c2), book(c2, []), c2.post("/api/strategy", json={"strategy": LAB, "enabled": True}),
                  c2.post("/api/lab-remove", json={"strategy": LAB})):
            assert r.status_code == 409 and r.json()["detail"] == OTHER_DESK
        store.set_enabled("pp_orb", True)
        r = c2.post("/api/strategy", json={"strategy": LAB, "enabled": False})   # OFF is never refused (fix round 2, B)
        assert r.status_code == 200 and store.get("pp_orb")["enabled"] is False
        store.set_enabled("pp_orb", True)
        r = c2.post("/api/strategy-flatten", json={"strategy": LAB})             # so "Flatten & turn off" works here too
        assert r.status_code == 200 and r.json() == {"ok": True, "enabled": False, "results": {}}
        assert store.get("pp_orb")["enabled"] is False
        d = c2.get("/api/status").json()
        assert d["strategies"][LAB]["lab"]["read_only"] is True
        assert {"level": "warn", "label": "Lab strategies",
                "detail": "Another Desk is running on this store: Lab strategies are read-only here."} in d["readiness"]["checks"]
        d1 = c1.get("/api/status").json()
        assert d1["strategies"][LAB]["lab"]["read_only"] is False
        assert not [x for x in d1["readiness"]["checks"] if x["label"] == "Lab strategies"]
        assert c2.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "eval2", "qty": 1}]}).status_code == 200
        assert c2.get("/api/status").json()["strategies"][LAB]["lab"]["state"] == "off"
        one.state.labdesk.close()
        two.state.labdesk.close()


def test_a_desk_that_is_only_built_never_takes_the_store(paths, desklab_root):
    """Importing homebase.server builds a desk (and so does every test that builds one and never starts it): none of
    them may take the real desk's lock, or leave a file in the store."""
    store.put(rec())
    app = make_client(own=False)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.get("/api/status")
        for r in (set_limits(c), book(c, []), c.post("/api/strategy", json={"strategy": LAB, "enabled": True}),
                  c.post("/api/lab-remove", json={"strategy": LAB})):           # a change never takes it either (N1)
            assert r.status_code == 409
    assert not (desklab_root / "desk.lock").exists() and not labcfg.owns(app.state.cfg)


# ---- item 6 (the reviewer's probe 3)
def test_a_record_that_goes_by_hand_takes_the_strategy_and_its_sidecar_off(tmp_path):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    ld, cfg, _ = make_desk(tmp_path)
    (store.root() / "pp_orb.json").unlink()
    assert asyncio.run(ld.refresh())["removed"] == [LAB]
    assert LAB not in cfg.strategies and store.get_desk("pp_orb") is None and store.booked("pp_orb") is False
    gone = jl(tmp_path, "lab_removed")
    assert len(gone) == 1 and (gone[0]["strategy"], gone[0]["why"], gone[0]["sidecar_removed"]) == (LAB, "record gone", True)
    assert gone[0]["unbooked"] == ["eval1"]                                      # fix round 2, F: the accounts that went with it
    asyncio.run(ld.refresh())
    assert len(jl(tmp_path, "lab_removed")) == 1


def test_a_record_file_that_no_longer_reads_is_not_a_record_that_is_gone(tmp_path):
    """Fix round 2, C (the reviewer's probe D): a read that fails -- here a file without permissions, which stands for
    any OSError on the read -- must never cost him the limits he typed and his bookings."""
    store.put(rec(enabled=True))
    disk = {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"}
    store.put_desk("pp_orb", disk)
    ld, cfg, _ = make_desk(tmp_path)
    asyncio.run(ld.refresh())
    f = store.root() / "pp_orb.json"
    f.chmod(0o000)
    try:
        for _ in range(2):
            asyncio.run(ld.refresh())
        v = ld.status_view(LAB)
        assert (v["state"], v["why"]) == ("check", CANNOT_READ) and cfg.strategies[LAB].enabled is False
        assert store.get_desk("pp_orb") == disk and f.is_file()                  # the sidecar is exactly as it was
        assert cfg.book[LAB] == [{"account": "eval1", "qty": 1}] and labcfg.limits_of(cfg, LAB) is not None
    finally:
        f.chmod(0o600)
    asyncio.run(ld.refresh())
    assert ld.status_view(LAB)["state"] == "disarmed" and cfg.strategies[LAB].enabled is True
    assert store.get_desk("pp_orb") == disk and jl(tmp_path, "lab_removed") == [] and jl(tmp_path, "lab_unbooked") == []
    assert len(jl(tmp_path, "lab_unreadable")) == 1
    f.write_text("{not json")                                                    # garbage is the same: the file is there
    asyncio.run(ld.refresh())
    assert LAB in cfg.strategies and store.get_desk("pp_orb") == disk and ld.status_view(LAB)["why"] == CANNOT_READ


def test_a_record_that_goes_while_a_round_is_open_keeps_the_strategy_and_the_sidecar(tmp_path):
    store.put(rec(enabled=True))
    side = {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"}
    store.put_desk("pp_orb", side)
    ld, cfg, engine = make_desk(tmp_path)
    st = engine._state(LAB, "eval1")
    st.status = "live"
    store.remove("pp_orb")
    for _ in range(2):
        asyncio.run(ld.refresh())
    assert LAB in cfg.strategies and store.get_desk("pp_orb") == side and jl(tmp_path, "lab_removed") == []
    st.status = "done"                                                           # the round is over
    asyncio.run(ld.refresh())
    assert LAB not in cfg.strategies and store.get_desk("pp_orb") is None


def test_a_sidecar_left_from_before_the_desk_started_is_removed_and_one_just_promoted_is_not(tmp_path):
    ld, cfg, _ = make_desk(tmp_path)
    assert ld.owner() is True
    store.put_desk("old_one", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    assert store.booked("old_one") is True                                       # the Lab page would refuse Promote
    snap = labcfg.read_store()                                                   # a read from before ...
    store.put(rec("old_one"))                                                    # ... he promotes it again
    assert ld._drop_orphan("old_one") is False and store.get_desk("old_one") is not None
    (store.root() / "old_one.json").write_text("{not json")                      # a record file that does not read is there too
    assert ld._drop_orphan("old_one") is False and store.get_desk("old_one") is not None
    store.remove("old_one")
    assert labcfg.orphans(cfg, snap) == ["old_one"]
    asyncio.run(ld.refresh())
    assert store.get_desk("old_one") is None
    said = jl(tmp_path, "lab_removed")
    assert [(r["strategy"], r["why"]) for r in said] == [("lab_old_one", "record gone")]


# ---- item 7 (the reviewer's probe 4)
def test_broken_records_never_stop_the_refresh_or_the_others(tmp_path):
    root = store.root()
    store.put(rec("good_one"))
    (root / "garbage.json").write_text("{not json")
    (root / "a_list.json").write_text("[1, 2]")
    (root / "wrong_name.json").write_text(json.dumps(rec("other")))
    (root / "int_root.json").write_text(json.dumps(rec("int_root", root=5)))
    (root / "odd_fields.json").write_text(json.dumps(rec("odd_fields", session_window="x", qty="2", label=7, enabled="yes", sha256=None)))
    (root / "good_one.desk.json").write_text("[]")
    ld, cfg, _ = make_desk(tmp_path)
    assert sorted(labcfg.lab_ids(cfg)) == ["lab_good_one", "lab_odd_fields"]
    assert cfg.strategies["lab_odd_fields"].enabled is False and cfg.strategies["lab_odd_fields"].label == "odd_fields"
    (root / "huge_fee.json").write_text('{"name": "huge_fee", "root": "NQ", "commission": 1' + "0" * 400 + '}')
    assert asyncio.run(ld.refresh())["added"] == ["lab_huge_fee"]                # it used to raise, on every refresh
    store.put(rec("late_one"))
    assert asyncio.run(ld.refresh())["added"] == ["lab_late_one"]
    said = {r["strategy"]: r["error"] for r in jl(tmp_path, "lab_unreadable")}     # once each, with the detail
    assert sorted(said) == ["lab_a_list", "lab_garbage", "lab_int_root", "lab_wrong_name"] and len(jl(tmp_path, "lab_unreadable")) == 4
    assert "no market" in said["lab_int_root"] and "does not read" in said["lab_garbage"]
    v = ld.status_view("lab_good_one")                                           # M7: its sidecar file is there and does not read
    assert (v["state"], v["why"]) == ("check", CANNOT_READ_LIMITS)
    assert (root / "good_one.desk.json").read_text() == "[]"


def test_a_strategy_whose_record_stops_reading_shows_check_and_cannot_be_switched_on(client, monkeypatch):
    real = labcfg.strategy_cfg

    def boom(r, limits):
        raise OverflowError("int too large to convert to float: " + "9" * 300)
    monkeypatch.setattr(labcfg, "strategy_cfg", boom)
    asyncio.run(client.labdesk.refresh())
    s = status(client)
    assert (s["lab"]["state"], s["lab"]["why"]) == ("check", CANNOT_READ) and s["cfg"]["enabled"] is False
    r = client.post("/api/strategy", json={"strategy": LAB, "enabled": True})
    assert r.status_code == 409 and r.json()["detail"] == CANNOT_READ and store.get("pp_orb")["enabled"] is False
    assert len(journal(client, "lab_unreadable")) == 1 and "int too large" in journal(client, "lab_unreadable")[0]["error"]
    monkeypatch.setattr(labcfg, "strategy_cfg", real)
    asyncio.run(client.labdesk.refresh())
    assert status(client)["lab"]["state"] == "off"


@pytest.mark.parametrize("raw, sentence", [
    ('"max_risk_usd": 1' + "0" * 400, "At risk per trade: a dollar amount above 0."),
    ('"max_risk_usd": 1e999', "At risk per trade: a dollar amount above 0."),
    ('"max_risk_usd": NaN', "At risk per trade: a dollar amount above 0."),
    ('"max_trades_day": 1' + "0" * 400, "Trades a day: a whole number from 1 to 20.")])
def test_an_absurd_number_in_a_limits_body_is_a_400_never_a_500(client, raw, sentence):
    rest = {k: v for k, v in LIMITS.items() if f'"{k}"' not in raw}
    body = '{"strategy": "lab_pp_orb", "limits": {' + raw + ", " + json.dumps(rest)[1:] + "}"
    r = client.post("/api/lab-limits", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["detail"] == sentence
    assert status(client)["lab"]["limits"] is None


# ---- item 8
def test_a_book_dropped_for_a_new_promotion_is_journaled(client):
    set_limits(client)
    book(client, [("eval1", 1), ("eval2", 1)])
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", sha256="cd"))            # by hand: the Lab page would have refused
    asyncio.run(client.labdesk.refresh())
    assert LAB not in client.cfg.book
    u = journal(client, "lab_unbooked")
    assert [(r["strategy"], r["accounts"], r["why"]) for r in u] == [(LAB, ["eval1", "eval2"], "promoted again")]
    assert store.get_desk("pp_orb")["book"] == [] and store.get_desk("pp_orb")["mark"] == ["cd", "2026-10-10T08:00:00+00:00"]


# ---- item 9
@pytest.fixture()
def short_wait(monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 0.05)


def test_the_request_wait_for_the_store_is_two_seconds():
    assert labdesk.REQ_WAIT_S == 2.0


def test_every_lab_route_gives_up_on_a_held_store_with_its_sentence_and_changes_nothing(client, short_wait):
    assert set_limits(client).status_code == 200
    assert book(client, [("eval1", 1)]).status_code == 200
    before = (store.get("pp_orb"), store.get_desk("pp_orb"), dict(client.cfg.book), status(client)["lab"]["limits"])
    done = hold_the_store()
    try:
        answers = [set_limits(client, max_trades_day=7), book(client, []), book(client, [("eval1", 1), ("eval2", 1)]),
                   client.post("/api/strategy", json={"strategy": LAB, "enabled": True}),
                   client.post("/api/strategy", json={"strategy": LAB, "enabled": False}),
                   client.post("/api/lab-remove", json={"strategy": LAB})]
    finally:
        done()
    for r in answers:
        assert r.status_code == 409 and r.json()["detail"] == NOT_SAVED
    assert (store.get("pp_orb"), store.get_desk("pp_orb"), dict(client.cfg.book), status(client)["lab"]["limits"]) == before
    assert LAB in client.cfg.strategies and client.cfg.strategies[LAB].enabled is False
    assert labcfg.pending(client.cfg) == [] and not labcfg.any_busy(client.cfg)
    assert set_limits(client, max_trades_day=7).status_code == 200               # the store is free again: it works
    assert client.post("/api/lab-remove", json={"strategy": LAB}).status_code == 200


def test_the_wait_for_the_store_is_off_the_event_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 0.3)
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    done = hold_the_store()

    async def go():
        ticks = 0
        t = asyncio.create_task(ld.set_limits(LAB, LIMITS))
        while not t.done():
            await asyncio.sleep(0.01)
            ticks += 1
        with pytest.raises(Refused, match="Could not save it"):
            t.result()
        return ticks
    try:
        assert asyncio.run(go()) >= 10                                           # the loop kept turning for the 0.3 s
    finally:
        done()
    assert labcfg.limits_of(cfg, LAB) is None


def test_flatten_and_turn_off_reports_the_flatten_when_the_switch_cannot_be_written(client, short_wait, monkeypatch):
    client.post("/api/strategy", json={"strategy": LAB, "enabled": True})

    async def flattened(name):
        return {"eval1": ["cancel entry 1: ok", "market Sell 1: ok"]}
    monkeypatch.setattr(client.engine, "flatten_strategy", flattened)
    done = hold_the_store()
    try:
        r = client.post("/api/strategy-flatten", json={"strategy": LAB})
    finally:
        done()
    assert r.status_code == 200
    assert r.json() == {"ok": True, "enabled": True, "results": {"eval1": ["cancel entry 1: ok", "market Sell 1: ok"]},
                        "detail": "Flattened. Could not switch it off: try the switch again."}
    assert store.get("pp_orb")["enabled"] is True and client.cfg.strategies[LAB].enabled is True
    assert journal(client, "lab_save_error")
    r = client.post("/api/strategy-flatten", json={"strategy": LAB})             # the store is free: flattened and off
    assert r.json() == {"ok": True, "enabled": False, "results": {"eval1": ["cancel entry 1: ok", "market Sell 1: ok"]}}


def test_a_second_change_to_a_strategy_while_one_is_being_written_is_refused_not_interleaved(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 1.0)
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    done = hold_the_store()
    reads = []
    real = labcfg.read_store
    monkeypatch.setattr(labcfg, "read_store", lambda *a, **k: (reads.append(1), real(*a, **k))[1])

    async def go():
        first = asyncio.create_task(ld.set_limits(LAB, LIMITS))
        await asyncio.sleep(0.05)                                                # the first is waiting for the store
        for other in (ld.set_limits(LAB, {**LIMITS, "max_trades_day": 9}), ld.set_enabled(LAB, True),
                      ld.set_enabled(LAB, False), ld.remove(LAB)):
            with pytest.raises(Refused, match="Could not save it"):
                await other
        assert await ld.refresh() is None and reads == []                        # the refresh does not even read meanwhile
        done()
        return await first
    try:
        assert asyncio.run(go())["limits"]["max_trades_day"] == 2
    finally:
        done()
    assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2 and labcfg.limits_of(cfg, LAB).max_trades_day == 2
    assert store.get("pp_orb")["enabled"] is False and LAB in cfg.strategies     # the refused ones changed nothing


def test_a_request_that_is_cancelled_while_it_writes_still_ends_with_memory_and_disk_agreeing(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 2.0)
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    done = hold_the_store()

    async def go():
        t = asyncio.create_task(ld.set_limits(LAB, LIMITS))
        await asyncio.sleep(0.05)
        t.cancel()                                                               # the page went away
        with pytest.raises(asyncio.CancelledError):
            await t
        done()                                                                   # the store is free: the write lands
        for _ in range(200):
            if not labcfg.any_busy(cfg):
                break
            await asyncio.sleep(0.01)
    try:
        asyncio.run(go())
    finally:
        done()
    assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2             # on disk ...
    assert labcfg.limits_of(cfg, LAB).max_trades_day == 2 and labcfg.pending(cfg) == []    # ... and in memory


# ---- item 10
def test_a_sidecar_that_cannot_be_written_for_one_strategy_does_not_block_another(paths, monkeypatch):
    store.put(rec("one_a"))
    store.put(rec("two_b"))
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        assert set_limits(c, "lab_one_a").status_code == 200
        real = store.put_desk

        def picky(name, *a, **k):
            if name == "one_a":
                raise OSError("this one file cannot be written")
            return real(name, *a, **k)
        monkeypatch.setattr(store, "put_desk", picky)
        app.state.cfg.book["lab_one_a"] = [{"account": "eval1", "qty": 1}]       # a change of one_a that stays pending
        config_mod.save(app.state.cfg)
        assert [n for n, _ in labcfg.pending(app.state.cfg)] == ["one_a"]
        assert set_limits(c, "lab_two_b").status_code == 200                     # two_b is not held up by it
        assert book(c, [("eval2", 1)], "lab_two_b").status_code == 200
        assert store.get_desk("two_b")["book"] == [{"account": "eval2", "qty": 1}]
        r = set_limits(c, "lab_one_a", max_trades_day=5)
        assert r.status_code == 409 and r.json()["detail"] == NOT_SAVED          # one_a itself still cannot be written
        app.state.labdesk.close()


# ---- item 11
def test_the_status_blocks_why_carries_no_error_text(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("a long internal detail nobody should read on the page")
    monkeypatch.setattr(client.labdesk, "_state", boom)
    for _ in range(3):
        s = status(client)
    assert (s["lab"]["state"], s["lab"]["why"]) == ("check", CANNOT_READ)
    said = journal(client, "lab_view_error")
    assert len(said) == 1 and "internal detail" in said[0]["error"]              # the detail: the journal, once


# =====================================================================================================================
# Fix round 2
# =====================================================================================================================
READ_ONLY_LINE = {"level": "warn", "label": "Lab strategies",
                  "detail": "Another Desk is running on this store: Lab strategies are read-only here."}


def no_accounts_cfg():
    """A worktree has no config.json: its desk has the shipped strategies and no account."""
    return AppCfg(strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True)})


def lab_checks_of(cfg, engine):
    return [x for x in compute_readiness(WED_10, cfg, engine, {}, None, None, None)["checks"] if x["label"] == "Lab strategies"]


# ---- A, B, D (the reviewer's probe A)
def test_a_desk_with_another_pool_started_first_un_books_nothing_and_the_real_desk_takes_the_store_back(tmp_path):
    store.put(rec(enabled=True))
    disk = {"mark": MARK, "limits": {**L3, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"}
    store.put_desk("pp_orb", disk)
    # 1. a dev desk with no accounts starts while the real desk is down: it is the owner, and it leaves the book alone
    dev, dev_cfg, _ = make_desk(tmp_path / "dev", no_accounts_cfg())
    for _ in range(2):
        asyncio.run(dev.refresh())
    assert dev.owner() is True and store.get_desk("pp_orb") == disk and store.booked("pp_orb") is True
    assert dev_cfg.book[LAB] == disk["book"] and config_mod.assignments(dev_cfg, LAB) == []
    assert jl(tmp_path / "dev", "lab_unbooked") == [] and dev.status_view(LAB)["state"] == "shadow"
    # 2. the real desk comes back while the dev desk is still up: it reads, with its account on the strategy
    real, real_cfg, real_engine = make_desk(tmp_path / "real")
    asyncio.run(real.refresh())
    assert real.owner() is False and config_mod.assignments(real_cfg, LAB) == [{"account": "eval1", "qty": 1}]
    v = real.status_view(LAB)
    assert v["read_only"] is True and v["state"] == "disarmed" and v["limits"]["max_qty"] == 3
    assert lab_checks_of(real_cfg, real_engine) == [READ_ONLY_LINE] and lab_checks_of(dev_cfg, dev.engine) == []
    assert refused(real.set_limits(LAB, LIMITS)) == (OTHER_DESK, 409)
    assert refused(real.set_book(LAB, [{"account": "eval1", "qty": 2}])) == (OTHER_DESK, 409)
    assert refused(real.set_enabled(LAB, True)) == (OTHER_DESK, 409)
    assert asyncio.run(real.set_enabled(LAB, False)) is True                     # B: OFF is never refused
    assert store.get("pp_orb")["enabled"] is False and real_cfg.strategies[LAB].enabled is False
    # 3. the dev desk goes away. A change is still refused until the next refresh has taken the store and re-read it ...
    dev.close()
    assert refused(real.set_limits(LAB, LIMITS)) == (OTHER_DESK, 409)
    asyncio.run(real.refresh())
    assert real.owner() is True and len(jl(tmp_path / "real", "lab_store_owned")) == 1
    v = real.status_view(LAB)
    assert v["read_only"] is False and lab_checks_of(real_cfg, real_engine) == []
    # ... and then the real desk is the Desk again
    assert asyncio.run(real.set_limits(LAB, {**L3, "max_trades_day": 4}))["ok"] is True
    asyncio.run(real.set_book(LAB, [{"account": "eval1", "qty": 2}]))
    assert asyncio.run(real.set_enabled(LAB, True)) is True
    got = store.get_desk("pp_orb")
    assert got["book"] == [{"account": "eval1", "qty": 2}] and got["limits"]["max_trades_day"] == 4
    asyncio.run(real.refresh())
    assert len(jl(tmp_path / "real", "lab_store_owned")) == 1 and len(jl(tmp_path / "real", "lab_store_busy")) == 1


def test_a_desk_that_takes_the_store_over_starts_from_what_the_owner_last_wrote(tmp_path):
    store.put(rec())
    first, cfg1, _ = make_desk(tmp_path / "one")
    asyncio.run(first.set_limits(LAB, L3))
    second, cfg2, _ = make_desk(tmp_path / "two")                                # reads: limits 3, no account
    asyncio.run(second.refresh())
    asyncio.run(first.set_book(LAB, [{"account": "eval1", "qty": 2}]))           # the owner books an account afterwards
    asyncio.run(first.set_limits(LAB, {**L3, "max_trades_day": 7}))
    asyncio.run(second.refresh())                                                # the reader follows the owner's sidecar
    assert cfg2.book[LAB] == [{"account": "eval1", "qty": 2}] and labcfg.limits_of(cfg2, LAB).max_trades_day == 7
    asyncio.run(first.set_book(LAB, [{"account": "eval2", "qty": 1}]))           # the owner's LAST change, then it ends,
    first.close()                                                                # with no read by the other in between
    asyncio.run(second.refresh())                                                # the refresh that takes the store re-reads
    assert second.owner() is True and cfg2.book[LAB] == [{"account": "eval2", "qty": 1}]
    asyncio.run(second.set_limits(LAB, {**L3, "max_trades_day": 9}))             # its first write keeps the owner's booking
    got = store.get_desk("pp_orb")
    assert got["book"] == [{"account": "eval2", "qty": 1}] and got["limits"]["max_trades_day"] == 9


def test_the_owners_book_write_keeps_the_rows_of_accounts_it_does_not_have(tmp_path):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": L3, "book": [{"account": "other_pool", "qty": 9}, {"account": "eval1", "qty": 3}],
                              "written_utc": "x"})
    ld, cfg, _ = make_desk(tmp_path)
    assert asyncio.run(ld.set_limits(LAB, {**L3, "max_qty": 3}))["ok"]           # other_pool's 9 is not ours to judge
    assert refused(ld.set_limits(LAB, {**L3, "max_qty": 2})) == (BOOKED_FOR_MORE, 409)     # eval1's 3 is
    asyncio.run(ld.set_book(LAB, [{"account": "eval2", "qty": 1}]))              # eval1 off, eval2 on
    assert cfg.book[LAB] == [{"account": "eval2", "qty": 1}, {"account": "other_pool", "qty": 9}]
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 1}, {"account": "other_pool", "qty": 9}]
    asyncio.run(ld.set_book(LAB, []))
    assert store.get_desk("pp_orb")["book"] == [{"account": "other_pool", "qty": 9}] and store.booked("pp_orb")
    assert ld.status_view(LAB)["state"] == "off" and config_mod.assignments(cfg, LAB) == []
    asyncio.run(ld.refresh())
    assert store.get_desk("pp_orb")["book"] == [{"account": "other_pool", "qty": 9}] and jl(tmp_path, "lab_unbooked") == []
    assert asyncio.run(ld.remove(LAB)) == {"ok": True, "removed": LAB}           # Remove from Desk is the way out
    assert store.get_desk("pp_orb") is None


def test_an_account_removed_from_the_desk_is_the_one_path_that_strips_its_row(client):
    set_limits(client)
    book(client, [("eval1", 1), ("eval2", 1)])
    assert client.post("/api/accounts/remove", json={"account": "eval2"}).status_code == 200
    assert client.cfg.book[LAB] == [{"account": "eval1", "qty": 1}]
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}]  # written by the hook
    assert journal(client, "lab_unbooked") == []                                 # (account_removed is the line for it)


def test_a_lock_that_could_not_be_tried_is_not_another_desk(tmp_path, monkeypatch):
    store.put(rec())
    real = store.desk_lock

    def broken(at=None):
        raise OSError(24, "Too many open files")
    monkeypatch.setattr(store, "desk_lock", broken)
    ld, cfg, engine = make_desk(tmp_path)
    for _ in range(2):
        asyncio.run(ld.refresh())
    assert ld.owner() is False and labcfg.store_state(cfg) == "unknown"
    assert refused(ld.set_limits(LAB, LIMITS)) == (NOT_SAVED, 409)               # not "Another Desk is running"
    assert ld.status_view(LAB)["read_only"] is True and lab_checks_of(cfg, engine) == []
    assert jl(tmp_path, "lab_store_busy") == [] and len(jl(tmp_path, "lab_store_error")) == 1
    assert "Too many open files" in jl(tmp_path, "lab_store_error")[0]["error"]
    monkeypatch.setattr(store, "desk_lock", real)
    asyncio.run(ld.refresh())                                                    # tried again on the next refresh
    assert ld.owner() is True and len(jl(tmp_path, "lab_store_owned")) == 1
    assert asyncio.run(ld.set_limits(LAB, LIMITS))["ok"] is True


# ---- B
def test_switching_off_is_never_refused_also_when_nothing_else_is_allowed(tmp_path, monkeypatch):
    store.put(rec(enabled=True))
    first, cfg1, _ = make_desk(tmp_path / "one")
    assert first.owner()
    reader, cfg, _ = make_desk(tmp_path / "two")
    asyncio.run(reader.refresh())
    store.put(rec(enabled=True, promoted="2026-10-10T08:00:00+00:00", sha256="cd"))      # promoted again behind its back
    assert asyncio.run(reader.set_enabled(LAB, False)) is True                   # a reader, a changed mark: still off
    assert store.get("pp_orb")["enabled"] is False and cfg.strategies[LAB].enabled is False
    monkeypatch.setattr(labcfg, "strategy_cfg", lambda r, l: (_ for _ in ()).throw(ValueError("x")))
    store.set_enabled("pp_orb", True)
    asyncio.run(first.refresh())                                                 # the owner cannot read the record any more
    assert first.status_view(LAB)["why"] == CANNOT_READ
    assert asyncio.run(first.set_enabled(LAB, False)) is True and store.get("pp_orb")["enabled"] is False


# ---- D
def test_the_read_only_line_shows_only_on_a_reader_with_a_lab_strategy(tmp_path):
    first, cfg1, e1 = make_desk(tmp_path / "one")                                # no Lab strategy yet
    assert first.owner()
    second, cfg2, e2 = make_desk(tmp_path / "two")
    asyncio.run(second.refresh())
    assert second.owner() is False and lab_checks_of(cfg2, e2) == []             # a reader, nothing promoted: no line
    store.put(rec())
    asyncio.run(first.refresh())
    asyncio.run(second.refresh())
    assert lab_checks_of(cfg2, e2) == [READ_ONLY_LINE] and lab_checks_of(cfg1, e1) == []
    assert compute_readiness(WED_10, cfg2, e2, {}, None, None, None)["checks"].count(READ_ONLY_LINE) == 1
    built, cfg3, e3 = make_desk(tmp_path / "three", own=False)                   # a desk that never asked: no line
    assert lab_checks_of(cfg3, e3) == [] and built.status_view(LAB)["read_only"] is False


# ---- E (the reviewer's probe F, 2)
def test_a_record_the_desk_cannot_use_can_still_be_removed_on_the_desk(paths):
    store.put(rec(root=None))                                                    # a record that names no market
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    store.put_day("pp_orb", {"date": "2026-09-29", "sha256": "ab", "state": "done"})
    (store.root() / "garbage.json").write_text("{not json")
    store.put_desk("garbage", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        assert LAB not in c.get("/api/status").json()["strategies"]              # not a strategy on the Desk ...
        assert store.booked("pp_orb") and store.booked("garbage")                # ... and the Lab page refuses Promote / Remove
        st = app.state.engine._state(LAB, "eval1")
        st.status = "live"                                                       # the engine still holds a round for it
        r = c.post("/api/lab-remove", json={"strategy": LAB})
        assert r.status_code == 409 and r.json()["detail"] == FLATTEN_FIRST and store.get_desk("pp_orb") is not None
        st.status = "done"
        r = c.post("/api/lab-remove", json={"strategy": LAB})
        assert r.status_code == 200 and r.json() == {"ok": True, "removed": LAB}
        assert not store.has_record_file("pp_orb") and store.get_desk("pp_orb") is None and not store.booked("pp_orb")
        assert store.get_day("pp_orb", "2026-09-29") is not None                 # the history stays
        r = c.post("/api/lab-remove", json={"strategy": "lab_garbage"})          # a file that does not read: the same
        assert r.status_code == 200 and not store.has_record_file("garbage") and store.get_desk("garbage") is None
        last = journal(c, "lab_removed")[-1]
        assert (last["strategy"], last["why"]) == ("lab_garbage", "removed")
        for name in (LAB, "lab_never_was", "nq930", "lab_", "lab_Bad Name", "lab_runner", ""):   # nothing there: not on the Desk
            r = c.post("/api/lab-remove", json={"strategy": name})
            assert r.status_code == 404 and r.json()["detail"] == NOT_ON_DESK, name
        assert "nq930" in app.state.cfg.strategies and (store.root() / "desk.lock").is_file()


def test_a_reader_cannot_remove_an_unusable_record_either(tmp_path):
    store.put(rec(root=None))
    first, _, _ = make_desk(tmp_path / "one")
    assert first.owner()
    second, _, _ = make_desk(tmp_path / "two")
    asyncio.run(second.refresh())
    assert refused(second.remove(LAB)) == (OTHER_DESK, 409) and store.has_record_file("pp_orb")


def test_removing_an_unusable_record_gives_up_on_a_held_store(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 0.05)
    store.put(rec(root=None))
    ld, _, _ = make_desk(tmp_path)
    done = hold_the_store()
    try:
        assert refused(ld.remove(LAB)) == (NOT_SAVED, 409)
    finally:
        done()
    assert store.has_record_file("pp_orb")
    assert asyncio.run(ld.remove(LAB)) == {"ok": True, "removed": LAB}


# ---- G
def test_after_a_restart_a_round_the_engine_restored_keeps_the_sidecar_of_a_record_that_went(tmp_path):
    side = {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"}
    store.put_desk("pp_orb", side)                                               # the record went; then the desk restarted
    ld, cfg, engine = make_desk(tmp_path, own=False)
    st = engine._state(LAB, "eval1")                                             # the day file gave the engine its round back
    st.status = "live"
    for _ in range(2):
        asyncio.run(ld.refresh())
    assert store.get_desk("pp_orb") == side and LAB not in cfg.strategies and jl(tmp_path, "lab_removed") == []
    st.status = "done"
    asyncio.run(ld.refresh())
    assert store.get_desk("pp_orb") is None and jl(tmp_path, "lab_removed")[-1]["strategy"] == LAB


# ---- H
def test_a_real_failure_in_the_refresh_is_still_journaled(tmp_path, monkeypatch):
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    asyncio.run(ld.set_limits(LAB, LIMITS))
    cfg.book[LAB] = [{"account": "eval1", "qty": 1}]

    def full(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(store, "put_desk", full)

    async def a_few_rounds():
        t = asyncio.create_task(ld.run(interval_s=0.001))
        await asyncio.sleep(0.05)
        t.cancel()
    asyncio.run(a_few_rounds())
    errs = jl(tmp_path, "lab_refresh_error")
    assert len(errs) == 1 and "No space left" in errs[0]["error"]


# ---- I
def test_the_desks_shutdown_gives_the_store_back(paths):
    store.put(rec())
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        assert set_limits(c).status_code == 200 and labcfg.owns(app.state.cfg)
    assert not labcfg.owns(app.state.cfg) and labcfg.store_state(app.state.cfg) == "released"
    nxt = make_client()
    with TestClient(nxt, base_url="http://127.0.0.1:8850") as c:                 # the desk that starts next owns it
        c.tmp = paths
        assert set_limits(c, max_trades_day=4).status_code == 200
    assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 4


# =====================================================================================================================
# Fix round 3
# =====================================================================================================================
SWITCHED_OFF = "Lab strategies are switched off on this Desk."


def tree(root):
    """Every file under a folder with its bytes and its stamps: nothing read is fine, nothing written is the claim."""
    return {str(f.relative_to(root)): (f.read_bytes(), f.stat().st_mtime_ns) for f in sorted(root.rglob("*")) if f.is_file()}


# ---- R1: the Lab side is opt-in per desk
def test_with_the_lab_side_off_the_desk_is_what_it_was_before_this_task(paths, desklab_root, monkeypatch):
    store.put(rec(enabled=True))
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    before = tree(desklab_root)
    touched = []
    for fn in ("listing", "names", "get", "get_desk", "get_runner", "desk_lock", "put_desk", "set_enabled", "remove", "remove_desk"):
        real = getattr(store, fn)
        monkeypatch.setattr(store, fn, lambda *a, _fn=fn, _real=real, **k: (touched.append(_fn), _real(*a, **k))[1])
    hooks = list(config_mod._after_save)
    app = make_client(lab=False)
    assert config_mod._after_save == hooks                                       # no after-save work registered by it
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        d = c.get("/api/status").json()
        assert set(d["strategies"]) == {"nq930"} and "lab" not in d["strategies"]["nq930"]
        assert "lab" not in json.dumps(d).lower().replace("label", "")           # no Lab key or id anywhere in the status
        assert d["book"] == {"nq930": [{"account": "main", "qty": 3}]}
        asyncio.run(app.state.labdesk.refresh())                                 # even asked to: nothing
        assert asyncio.run(asyncio.wait_for(app.state.labdesk.run(), 1)) is None  # its task ends at once
        for r in (set_limits(c), c.post("/api/lab-remove", json={"strategy": LAB}), c.post("/api/lab-limits", json={"strategy": "nq930", "limits": LIMITS})):
            assert r.status_code == 409 and r.json()["detail"] == SWITCHED_OFF
        r = c.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "main", "qty": 2}, {"account": "eval1", "qty": 1}]})
        assert r.status_code == 200 and r.json() == {"ok": True, "book": {"nq930": [{"account": "main", "qty": 2}, {"account": "eval1", "qty": 1}]}}
        assert c.post("/api/book", json={"strategy": LAB, "assignments": []}).status_code == 404        # not a strategy here
        assert c.post("/api/strategy", json={"strategy": LAB, "enabled": True}).status_code == 404
        assert c.post("/api/strategy-flatten", json={"strategy": LAB}).status_code == 404
        r = c.post("/api/strategy", json={"strategy": "nq930", "enabled": False})
        assert r.json() == {"ok": True, "strategy": "nq930", "enabled": False}
        assert c.post("/api/strategy-flatten", json={"strategy": "nq930"}).json() == {"ok": True, "enabled": False, "results": {}}
        assert c.post("/api/accounts/remove", json={"account": "eval2"}).status_code == 200
        assert not [x for x in c.get("/api/status").json()["readiness"]["checks"] if "Lab" in x["label"]]
    assert touched == [] and tree(desklab_root) == before                        # the store was never read, never written
    assert not (desklab_root / "desk.lock").exists() and labcfg.store_state(app.state.cfg) is None
    assert "_lab" not in vars(app.state.cfg) and set(app.state.cfg.strategies) == {"nq930"}
    assert "lab_" not in (paths / "config.json").read_text()


def test_the_flag_is_a_file_in_this_checkouts_state_folder(paths):
    """lab=None (as the real desk is started): on only when <state_dir>/lab_desk.on exists. state_dir is per checkout,
    so a desk run from another worktree or copy never has it."""
    store.put(rec())
    assert labdesk.FLAG_FILE == "lab_desk.on" and labdesk.flagged(paths) is False
    adapters = {aid: SeededFakeAdapter(aid) for aid in desk_cfg().accounts}
    off = create_app(desk_cfg(), adapters, background=False)                     # no file: off
    assert off.state.labdesk.on is False and LAB not in off.state.cfg.strategies
    (paths / "lab_desk.on").write_text("")
    assert labdesk.flagged(paths) is True
    on = create_app(desk_cfg(), adapters, background=False)                      # the file is there: on
    assert on.state.labdesk.on is True and LAB in on.state.cfg.strategies
    assert create_app(desk_cfg(), adapters, background=False, lab=False).state.labdesk.on is False     # a test may say so
    (paths / "lab_desk.on").unlink()
    assert create_app(desk_cfg(), adapters, background=False, lab=True).state.labdesk.on is True


def test_a_desk_with_the_lab_side_off_built_directly_is_inert(tmp_path):
    store.put(rec())
    cfg = desk_cfg()
    engine = Engine(cfg, {}, now_fn=lambda: WED_10.astimezone(dt.timezone.utc), root=tmp_path)
    ld = LabDesk(cfg, engine, {}, on=False)
    assert asyncio.run(ld.refresh()) is None and ld.owner() is False and not ld.is_lab(LAB) and ld.status_view(LAB) is None
    ld.check_book("nq930", [{"account": "main", "qty": 1}])
    assert ld.book_view() is cfg.book                                            # the status's book: the very same object
    for coro in (ld.set_limits(LAB, LIMITS), ld.remove(LAB), ld.set_book(LAB, [])):
        assert refused(coro) == (SWITCHED_OFF, 409)
    assert asyncio.run(ld.set_enabled(LAB, False)) is False
    ld.close()
    assert "_lab" not in vars(cfg) and labcfg.store_state(cfg) is None


# ---- N1 (the reviewer's probe G)
def test_nothing_is_written_between_taking_the_store_and_re_reading_it(tmp_path):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": {**L3, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    old, _, _ = make_desk(tmp_path / "old")
    pause = [False]
    new, new_cfg, _ = make_desk(tmp_path / "new", paused=lambda: pause[0])
    assert new.owner() is False and new_cfg.book[LAB] == [{"account": "eval1", "qty": 1}]
    pause[0] = True                                                              # the chart views pause (a bot is placing)
    asyncio.run(old.set_book(LAB, [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 2}]))
    old.close()                                                                  # the old desk ends
    assert asyncio.run(new.refresh()) is None                                    # paused: no read ...
    assert not labcfg.owns(new_cfg) and labcfg.store_state(new_cfg) == "busy"    # ... so the lock is not taken either
    assert refused(new.set_limits(LAB, {**L3, "max_trades_day": 3})) == (OTHER_DESK, 409)
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 2}]
    pause[0] = False
    asyncio.run(new.refresh())                                                   # takes it and re-reads in the same pass
    assert new.owner() is True and new_cfg.book[LAB] == [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 2}]
    assert asyncio.run(new.set_limits(LAB, {**L3, "max_trades_day": 3}))["ok"] is True
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 2}]   # eval2 is still booked


def test_a_take_over_whose_re_read_was_thrown_away_still_owes_it(tmp_path, monkeypatch):
    """The lock is taken at the start of the refresh; if its read is then thrown away (the views paused meanwhile) the
    desk holds the store but may write nothing until a refresh has re-read every sidecar."""
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": {**L3, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    old, _, _ = make_desk(tmp_path / "old")
    pause = [False]
    new, new_cfg, _ = make_desk(tmp_path / "new", paused=lambda: pause[0])
    asyncio.run(old.set_book(LAB, [{"account": "eval2", "qty": 2}]))
    old.close()
    real = labcfg.read_store
    monkeypatch.setattr(labcfg, "read_store", lambda *a, **k: (pause.__setitem__(0, True), real(*a, **k))[1])
    assert asyncio.run(new.refresh()) is None                                    # the views paused during the read
    monkeypatch.setattr(labcfg, "read_store", real)
    assert labcfg.owns(new_cfg) and new.owner() is False                         # it holds the lock; it is not the owner yet
    assert refused(new.set_limits(LAB, L3)) == (OTHER_DESK, 409)
    assert refused(new.set_book(LAB, [])) == (OTHER_DESK, 409) and refused(new.remove(LAB)) == (OTHER_DESK, 409)
    new_cfg.book[LAB] = []                                                       # even a change of memory is not written:
    config_mod.save(new_cfg)                                                     # the hook writes nothing before the re-read
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 2}]
    assert new.status_view(LAB)["read_only"] is True
    pause[0] = False
    asyncio.run(new.refresh())
    assert new.owner() is True and new_cfg.book[LAB] == [{"account": "eval2", "qty": 2}]
    assert new.status_view(LAB)["read_only"] is False and len(jl(tmp_path / "new", "lab_store_owned")) == 1


def test_only_a_refresh_takes_the_store(tmp_path):
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path, own=False)
    assert ld.owner() is False
    for coro in (ld.set_limits(LAB, LIMITS), ld.set_book(LAB, []), ld.set_enabled(LAB, True), ld.remove(LAB)):
        assert refused(coro) == (NOT_SAVED, 409)                                 # nobody else has it: "try again", not "another desk"
    assert asyncio.run(ld.set_enabled(LAB, False)) is True                       # (OFF needs no store)
    config_mod.save(cfg)
    assert labcfg.store_state(cfg) is None and not (store.root() / "desk.lock").exists()
    asyncio.run(ld.refresh())
    assert ld.owner() is True and asyncio.run(ld.set_limits(LAB, LIMITS))["ok"] is True


# ---- N2 (the reviewer's probe H)
def reader_beside_a_desk_of_another_pool(tmp_path):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": {**L3, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 2}], "written_utc": "x"})
    dev, _, _ = make_desk(tmp_path / "dev", no_accounts_cfg())                   # another pool: it owns the store
    real, real_cfg, _ = make_desk(tmp_path / "real")                             # the real desk: a reader
    return dev, real, real_cfg


def test_h1_what_a_take_over_drops_is_dropped_from_the_disk_it_just_read_and_is_journaled(tmp_path):
    dev, real, cfg = reader_beside_a_desk_of_another_pool(tmp_path)
    asyncio.run(dev.set_limits(LAB, {**L3, "max_qty": 1}))                       # allowed: eval1 is not in the dev desk's pool
    asyncio.run(real.refresh())                                                  # the reader drops eval1 in its view
    assert config_mod.assignments(cfg, LAB) == [] and jl(tmp_path / "real", "lab_unbooked") == []
    assert store.get_desk("pp_orb")["book"] == [{"account": "eval1", "qty": 2}]
    dev.close()
    asyncio.run(real.refresh())                                                  # takes the store
    assert real.owner() is True
    u = jl(tmp_path / "real", "lab_unbooked")
    assert [(r["strategy"], r["accounts"], r["why"]) for r in u] == [(LAB, ["eval1"], "above the size cap")]   # said, once
    got = store.get_desk("pp_orb")
    assert got["book"] == [] and got["limits"]["max_qty"] == 1
    asyncio.run(real.refresh())
    assert len(jl(tmp_path / "real", "lab_unbooked")) == 1


def test_h2_the_previous_owners_last_save_wins_over_what_the_reader_last_read(tmp_path):
    dev, real, cfg = reader_beside_a_desk_of_another_pool(tmp_path)
    asyncio.run(dev.set_limits(LAB, {**L3, "max_qty": 1}))
    asyncio.run(real.refresh())                                                  # the reader: cap 1, eval1 dropped in its view
    asyncio.run(dev.set_limits(LAB, {**L3, "max_qty": 3}))                       # the owner's LAST save: the cap is 3 again
    dev.close()                                                                  # ... and it ends before the reader's next read
    asyncio.run(real.refresh())
    assert real.owner() is True
    got = store.get_desk("pp_orb")
    assert got["limits"]["max_qty"] == 3 and got["book"] == [{"account": "eval1", "qty": 2}]
    assert labcfg.limits_of(cfg, LAB).max_qty == 3 and config_mod.assignments(cfg, LAB) == [{"account": "eval1", "qty": 2}]
    assert jl(tmp_path / "real", "lab_unbooked") == []


# ---- N3 (the reviewer's page probe)
def test_the_page_never_sees_or_echoes_a_row_of_an_account_it_cannot_act_on(paths):
    store.put(rec())
    other = {"account": "eval9", "qty": 1}                                       # an account that is not in this desk's pool
    store.put_desk("pp_orb", {"mark": MARK, "limits": {**LIMITS, "max_qty": 2}, "book": [other, {"account": "eval1", "qty": 1}],
                              "written_utc": "x"})
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        d = c.get("/api/status").json()
        rows = d["book"][LAB]
        assert rows == [{"account": "eval1", "qty": 1}] and "eval9" not in d["accounts"]
        assert d["book"]["nq930"] == [{"account": "main", "qty": 3}]             # every other strategy: its rows as they are
        # resize, the way the page does it: every row it holds goes back
        r = c.post("/api/book", json={"strategy": LAB, "assignments": [{**x, "qty": 2} for x in rows]})
        assert r.status_code == 200 and r.json()["book"][LAB] == [{"account": "eval1", "qty": 2}]
        assert other in store.get_desk("pp_orb")["book"]
        # assign another account
        rows = c.get("/api/status").json()["book"][LAB]
        r = c.post("/api/book", json={"strategy": LAB, "assignments": rows + [{"account": "eval2", "qty": 1}]})
        assert r.status_code == 200 and r.json()["book"][LAB] == [{"account": "eval1", "qty": 2}, {"account": "eval2", "qty": 1}]
        assert other in store.get_desk("pp_orb")["book"]
        # the x on a row
        r = c.post("/api/book", json={"strategy": LAB, "assignments": [x for x in r.json()["book"][LAB] if x["account"] != "eval1"]})
        assert r.status_code == 200 and c.get("/api/status").json()["book"][LAB] == [{"account": "eval2", "qty": 1}]
        assert store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 1}, other]
        # a row the page could never have got from the status is still a 400, and changes nothing
        r = c.post("/api/book", json={"strategy": LAB, "assignments": [other]})
        assert r.status_code == 400 and store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 1}, other]
        assert c.post("/api/book", json={"strategy": LAB, "assignments": []}).status_code == 200
        assert c.get("/api/status").json()["book"][LAB] == [] and store.get_desk("pp_orb")["book"] == [other]
        assert app.state.cfg.book[LAB] == [other]                                # the desk keeps it; the page does not see it
        r = c.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "main", "qty": 2}]})
        assert r.status_code == 200 and r.json()["book"] == {"nq930": [{"account": "main", "qty": 2}], LAB: []}   # nor in this answer


# ---- M1
def test_an_account_removed_on_a_reader_is_stripped_when_it_takes_the_store(paths):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": {**LIMITS, "max_risk_usd": 300.0}, "book": [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 1}],
                              "written_utc": "x"})
    other = store.desk_lock()                                                    # another desk holds the store
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        assert app.state.labdesk.owner() is False
        assert c.post("/api/accounts/remove", json={"account": "eval1"}).status_code == 200
        assert len(store.get_desk("pp_orb")["book"]) == 2                        # a reader writes nothing
        asyncio.run(app.state.labdesk.refresh())
        assert config_mod.assignments(app.state.cfg, LAB) == [{"account": "eval2", "qty": 1}] and journal(c, "lab_unbooked") == []
        store.desk_unlock(other)                                                 # the other desk ends
        asyncio.run(app.state.labdesk.refresh())                                 # take-over: re-read, then the strip
        assert app.state.labdesk.owner() is True
        assert store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 1}]
        u = journal(c, "lab_unbooked")
        assert [(r["strategy"], r["accounts"], r["why"]) for r in u] == [(LAB, ["eval1"], "account removed")]
        asyncio.run(app.state.labdesk.refresh())
        assert len(journal(c, "lab_unbooked")) == 1 and app.state.cfg.book[LAB] == [{"account": "eval2", "qty": 1}]


def test_an_account_removed_while_a_lab_write_is_in_flight_does_not_come_back(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 2.0)
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    asyncio.run(ld.set_limits(LAB, LIMITS))
    asyncio.run(ld.set_book(LAB, [{"account": "eval1", "qty": 1}, {"account": "eval2", "qty": 1}]))
    done = hold_the_store()

    async def go():
        t = asyncio.create_task(ld.set_limits(LAB, {**LIMITS, "max_trades_day": 5}))    # its rows are read: eval1, eval2
        await asyncio.sleep(0.05)                                                # ... and it waits for the store
        for name in list(cfg.book):                                              # server._drop_account_locked, for eval2
            cfg.book[name] = [a for a in cfg.book[name] if a.get("account") != "eval2"]
        cfg.accounts.pop("eval2")
        config_mod.save(cfg)
        done()
        await t
        await ld.refresh()
    try:
        asyncio.run(go())
    finally:
        done()
    assert cfg.book[LAB] == [{"account": "eval1", "qty": 1}]                     # eval2 did not come back with the write
    got = store.get_desk("pp_orb")
    assert got["book"] == [{"account": "eval1", "qty": 1}] and got["limits"]["max_trades_day"] == 5
    assert [(r["accounts"], r["why"]) for r in jl(tmp_path, "lab_unbooked")] == [(["eval2"], "account removed")]


def test_an_account_that_comes_back_is_no_longer_stripped(tmp_path):
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    asyncio.run(ld.set_limits(LAB, LIMITS))
    gone = cfg.accounts.pop("eval2")
    config_mod.save(cfg)
    cfg.accounts["eval2"] = gone                                                 # "the account is back on your login"
    cfg.book[LAB] = [{"account": "eval2", "qty": 1}]                             # ... with its booking
    config_mod.save(cfg)
    asyncio.run(ld.refresh())
    assert cfg.book[LAB] == [{"account": "eval2", "qty": 1}] and store.get_desk("pp_orb")["book"] == [{"account": "eval2", "qty": 1}]


# ---- M2, M8
def test_removing_an_unusable_record_names_the_accounts_its_sidecar_held(paths):
    store.put(rec("bad_one", root=None))
    store.put_desk("bad_one", {"mark": MARK, "limits": LIMITS, "book": [{"account": "main", "qty": 1}, {"account": "eval9", "qty": 2}],
                               "written_utc": "x"})
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        assert c.post("/api/lab-remove", json={"strategy": "lab_bad_one"}).status_code == 200
        last = journal(c, "lab_removed")[-1]
        assert (last["strategy"], last["why"], last["unusable"], last["unbooked"]) == ("lab_bad_one", "removed", True, ["main", "eval9"])


def test_a_good_record_the_desk_has_not_read_yet_is_not_removed_as_unusable(tmp_path):
    ld, cfg, _ = make_desk(tmp_path)
    store.put(rec())                                                             # promoted under 2 s ago: not overlaid yet
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [], "written_utc": "x"})
    assert LAB not in cfg.strategies
    assert refused(ld.remove(LAB)) == (NOT_ON_DESK, 404)
    assert store.get("pp_orb") is not None and store.get_desk("pp_orb") is not None
    asyncio.run(ld.refresh())
    assert asyncio.run(ld.remove(LAB)) == {"ok": True, "removed": LAB}           # once it is on the Desk: the usual Remove


# ---- M5, M6
def test_a_close_that_raises_never_breaks_the_desks_shutdown(paths, monkeypatch):
    store.put(rec())
    app = make_client()

    def boom(self):
        raise RuntimeError("cannot close")
    monkeypatch.setattr(LabDesk, "close", boom)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        assert c.get("/api/status").status_code == 200                           # leaving the block must not raise


def test_a_write_that_reaches_its_thread_after_the_desk_let_go_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(labdesk, "REQ_WAIT_S", 2.0)
    store.put(rec())
    ld, cfg, _ = make_desk(tmp_path)
    done = hold_the_store()

    async def go():
        t = asyncio.create_task(ld.set_limits(LAB, LIMITS))
        await asyncio.sleep(0.05)                                                # it waits for the store ...
        ld.close()                                                               # ... the desk shuts down ...
        done()                                                                   # ... and only then does the write get its turn
        with pytest.raises(Refused, match="Could not save it"):
            await t
    try:
        asyncio.run(go())
    finally:
        done()
    assert store.get_desk("pp_orb") is None and labcfg.limits_of(cfg, LAB) is None


# ---- M7
def test_a_sidecar_file_that_is_there_and_does_not_read_is_never_written_over_unasked(paths):
    store.put(rec(enabled=True))
    f = store.root() / "pp_orb.desk.json"
    f.write_text("{this is not json")
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.tmp = paths
        s = status(c)
        assert (s["lab"]["state"], s["lab"]["why"], s["lab"]["limits"]) == ("check", CANNOT_READ_LIMITS, None)
        assert LAB not in c.get("/api/status").json()["book"]
        assert book(c, [("eval1", 1)]).json()["detail"] == SET_FIRST
        assert book(c, []).status_code == 200
        client_cfg = app.state.cfg
        client_cfg.book["nq930"] = [{"account": "main", "qty": 1}]
        config_mod.save(client_cfg)                                              # any save, any refresh ...
        for _ in range(2):
            asyncio.run(app.state.labdesk.refresh())
        assert f.read_text() == "{this is not json"                              # ... the file is as it was
        assert journal(c, "lab_sidecar_replaced") == []
        assert set_limits(c).status_code == 200                                  # he saves limits again: now it is replaced, and said
        assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2 and store.get_desk("pp_orb")["book"] == []
        said = journal(c, "lab_sidecar_replaced")
        assert len(said) == 1 and said[0]["strategy"] == LAB
        assert status(c)["lab"]["state"] == "shadow"
        set_limits(c, max_trades_day=3)
        assert len(journal(c, "lab_sidecar_replaced")) == 1                      # only that once


def test_a_sidecar_without_permissions_is_the_same(tmp_path):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    f = store.root() / "pp_orb.desk.json"
    before = f.read_bytes()
    f.chmod(0o000)
    try:
        ld, cfg, _ = make_desk(tmp_path)
        asyncio.run(ld.refresh())
        v = ld.status_view(LAB)
        assert (v["state"], v["why"]) == ("check", CANNOT_READ_LIMITS) and config_mod.assignments(cfg, LAB) == []
    finally:
        f.chmod(0o600)
    assert f.read_bytes() == before
