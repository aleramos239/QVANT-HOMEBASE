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


def make_client(cfg=None):
    cfg = cfg or desk_cfg()
    adapters = {aid: SeededFakeAdapter(aid) for aid in cfg.accounts}
    app = create_app(cfg, adapters, background=False, adapter_factory=lambda aid, a: FakeAdapter(aid))
    app.state.engine.now_et = lambda: WED_10
    plain_rounds(app.state.engine)
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
                        "mode_today": None, "runner": {"alive": False, "age_s": None}, "rounds": [], "refused": []}
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
def make_desk(tmp_path, cfg=None, paused=lambda: False):
    cfg = cfg or desk_cfg()
    adapters = {aid: FakeAdapter(aid) for aid in cfg.accounts}
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = plain_rounds(Engine(cfg, adapters, now_fn=lambda: WED_10.astimezone(dt.timezone.utc), root=tmp_path))
    labdesk.attach(cfg)
    return LabDesk(cfg, engine, adapters, paused=paused), cfg, engine


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
    app = make_client()
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
        with pytest.raises(TimeoutError):
            asyncio.run(client.labdesk.refresh())                                # the refresh does not wait either
        assert time.perf_counter() - t0 < 0.5
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
    assert LAB in cfg2.strategies and LAB not in cfg2.book                       # it sees the strategy; the account is not its own
    assert store.get_desk("pp_orb") == disk and store.booked("pp_orb")           # the first desk's sidecar is untouched
    assert len(jl(tmp_path / "two", "lab_store_busy")) == 1 and jl(tmp_path / "two", "lab_unbooked") == []
    assert second.status_view(LAB)["state"] == "shadow"
    assert refused(second.set_limits(LAB, LIMITS)) == (OTHER_DESK, 409)
    assert refused(second.set_book(LAB, [{"account": "demo", "qty": 1}])) == (OTHER_DESK, 409)
    assert refused(second.set_book(LAB, [])) == (OTHER_DESK, 409)
    assert refused(second.set_enabled(LAB, False)) == (OTHER_DESK, 409)
    assert refused(second.set_enabled(LAB, True)) == (OTHER_DESK, 409)
    assert refused(second.remove(LAB)) == (OTHER_DESK, 409)
    assert store.get("pp_orb")["enabled"] is True and store.get_desk("pp_orb") == disk
    store.remove("pp_orb")                                                       # the record goes by hand
    asyncio.run(second.refresh())
    assert store.get_desk("pp_orb") == disk                                      # a reader never removes a sidecar
    assert len(jl(tmp_path / "two", "lab_store_busy")) == 1                      # said once
    first.close()                                                                # the first desk ends
    assert second.owner() is False                                               # the reader never takes over
    asyncio.run(second.refresh())
    assert store.get_desk("pp_orb") == disk


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
                  c2.post("/api/strategy", json={"strategy": LAB, "enabled": False}), c2.post("/api/lab-remove", json={"strategy": LAB})):
            assert r.status_code == 409 and r.json()["detail"] == OTHER_DESK
        r = c2.post("/api/strategy-flatten", json={"strategy": LAB})             # its flatten still runs and answers
        assert r.status_code == 200 and r.json()["results"] == {} and "Could not switch it off" in r.json()["detail"]
        assert c2.post("/api/book", json={"strategy": "nq930", "assignments": [{"account": "eval2", "qty": 1}]}).status_code == 200
        assert c2.get("/api/status").json()["strategies"][LAB]["lab"]["state"] == "off"
        one.state.labdesk.close()
        two.state.labdesk.close()


def test_a_desk_that_is_only_built_never_takes_the_store(paths, desklab_root):
    """Importing homebase.server builds a desk (and so does every test that builds one and never starts it): none of
    them may take the real desk's lock, or leave a file in the store."""
    store.put(rec())
    app = make_client()
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.get("/api/status")
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
    asyncio.run(ld.refresh())
    assert len(jl(tmp_path, "lab_removed")) == 1


def test_a_record_file_that_no_longer_reads_is_a_record_that_is_gone(tmp_path):
    store.put(rec())
    store.put_desk("pp_orb", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    ld, cfg, _ = make_desk(tmp_path)
    (store.root() / "pp_orb.json").write_text("{not json")
    asyncio.run(ld.refresh())
    assert LAB not in cfg.strategies and store.get_desk("pp_orb") is None


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
    store.put_desk("old_one", {"mark": MARK, "limits": LIMITS, "book": [{"account": "eval1", "qty": 1}], "written_utc": "x"})
    ld, cfg, _ = make_desk(tmp_path)
    assert ld.owner() is True
    assert store.booked("old_one") is True                                       # the Lab page would refuse Promote
    snap = labcfg.read_store()                                                   # a read from before ...
    store.put(rec("old_one"))                                                    # ... he promotes it again
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
    assert [r["strategy"] for r in jl(tmp_path, "lab_unreadable")] == ["lab_int_root"]     # once, with the detail
    assert "no market" in jl(tmp_path, "lab_unreadable")[0]["error"]


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

    async def go():
        first = asyncio.create_task(ld.set_limits(LAB, LIMITS))
        await asyncio.sleep(0.05)                                                # the first is waiting for the store
        with pytest.raises(Refused, match="Could not save it"):
            await ld.set_limits(LAB, {**LIMITS, "max_trades_day": 9})
        assert await ld.refresh() is None                                        # and the refresh changes nothing meanwhile
        done()
        return await first
    try:
        assert asyncio.run(go())["limits"]["max_trades_day"] == 2
    finally:
        done()
    assert store.get_desk("pp_orb")["limits"]["max_trades_day"] == 2 and labcfg.limits_of(cfg, LAB).max_trades_day == 2


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
