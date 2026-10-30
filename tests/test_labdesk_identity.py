"""The owner renames a promoted Lab strategy, switches the contract its orders go to (mini <-> micro) and duplicates it
(2026-10-28). A rename touches the label only; a switch moves the record, its size, its limits and its book together, at the
same exposure (10 micros = 1 mini), and refuses a size that would not come out whole; a duplicate is a copy that is off, on
no account, with no history."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.desk import labcfg
from homebase.labrun import store
from tests.test_server_lab import (ET, LAB, LIMITS, book, client, journal, open_round, paths, rec, set_limits,  # noqa: F401
                                   status)

AFTER_CLOSE = dt.datetime(2026, 9, 30, 17, 0, tzinfo=ET)
IN_SESSION = dt.datetime(2026, 9, 30, 10, 0, tzinfo=ET)


def ident(c, name=LAB, **kw):
    return c.post("/api/lab-identity", json={"strategy": name, **kw})


def make(paths, **kw):
    from fastapi.testclient import TestClient
    from tests.test_server_lab import make_client
    store.put(rec(**kw))
    app = make_client()
    app.state.engine.now_et = lambda: AFTER_CLOSE
    c = TestClient(app, base_url="http://127.0.0.1:8850")
    c.__enter__()
    c.app, c.cfg, c.engine, c.labdesk, c.tmp = app, app.state.cfg, app.state.engine, app.state.labdesk, paths
    return c


@pytest.fixture()
def mini(paths):
    c = make(paths, qty=1)
    yield c
    c.labdesk.close()


@pytest.fixture()
def micro(paths):
    c = make(paths, qty=10, exec_root="MNQ", commission=1.0)
    yield c
    c.labdesk.close()


def test_a_rename_changes_only_the_label(mini):
    r = ident(mini, label="  My   ORB  ")
    assert r.status_code == 200 and r.json()["label"] == "My ORB" and r.json()["changed"] is True
    assert store.get("pp_orb")["label"] == "My ORB" and store.get("pp_orb")["source"] == "class X: pass\n"
    assert mini.cfg.strategies[LAB].label == "My ORB"
    assert journal(mini, "lab_identity_set")[-1]["label"] == "My ORB"


@pytest.mark.parametrize("bad", ["", "   ", "x" * 61, 5, None, "a\x00b"])
def test_a_bad_name_is_a_400(mini, bad):
    assert ident(mini, label=bad).status_code == 400
    assert store.get("pp_orb")["label"] == "PP ORB"


def test_an_empty_request_is_a_400(mini):
    assert ident(mini).status_code == 400
    assert ident(mini, instrument="maxi").status_code == 400


def test_a_strategy_that_is_not_on_the_desk_is_a_404(mini):
    assert ident(mini, name="lab_nope", label="x").status_code == 404


def test_mini_to_micro_moves_every_size_at_the_same_exposure(mini):
    assert set_limits(mini, max_qty=1).status_code == 200
    assert book(mini, [("main", 1)]).status_code == 200
    r = ident(mini, instrument="micro")
    assert r.status_code == 200 and r.json()["instrument"] == "micro"
    got = store.get("pp_orb")
    assert got["exec_root"] == "MNQ" and got["exec_pick"] is True and got["qty"] == 10 and got["commission"] == 1.0
    assert mini.cfg.strategies[LAB].symbol == "MNQ"
    assert mini.cfg.book[LAB] == [{"account": "main", "qty": 10}]
    assert labcfg.limits_of(mini.cfg, LAB).max_qty == 10
    side = store.get_desk("pp_orb")
    assert side["book"] == [{"account": "main", "qty": 10}] and side["limits"]["max_qty"] == 10


def test_micro_to_mini_takes_the_exec_root_off(micro):
    assert set_limits(micro, max_qty=10).status_code == 200
    assert book(micro, [("main", 10)]).status_code == 200
    r = ident(micro, instrument="mini")
    assert r.status_code == 200 and r.json()["instrument"] == "mini"
    got = store.get("pp_orb")
    assert "exec_root" not in got and got["exec_pick"] is True and got["qty"] == 1 and got["commission"] == 4.0
    assert micro.cfg.strategies[LAB].symbol == "NQ"
    assert micro.cfg.book[LAB] == [{"account": "main", "qty": 1}]


def test_a_size_that_is_not_whole_is_refused_and_nothing_changes(micro):
    assert set_limits(micro, max_qty=10).status_code == 200
    assert book(micro, [("main", 4)]).status_code == 200
    r = ident(micro, instrument="mini")
    assert r.status_code == 409 and "not a whole number of minis" in r.json()["detail"]
    got = store.get("pp_orb")
    assert got["exec_root"] == "MNQ" and got["qty"] == 10 and "exec_pick" not in got
    assert micro.cfg.book[LAB] == [{"account": "main", "qty": 4}]


def test_two_minis_cannot_become_twenty_micros(mini):
    assert set_limits(mini, max_qty=2).status_code == 200
    r = ident(mini, instrument="micro")
    assert r.status_code == 409 and "Its most" in r.json()["detail"]
    assert "exec_root" not in store.get("pp_orb")


def test_the_same_contract_is_no_change(mini):
    r = ident(mini, instrument="mini")
    assert r.status_code == 200 and r.json()["changed"] is False
    assert "exec_pick" not in store.get("pp_orb")


def test_a_strategy_that_sizes_itself_cannot_be_switched(paths):
    c = make(paths, qty=1, exec_root="MNQ", own_size=True)
    try:
        r = ident(c, instrument="mini")
        assert r.status_code == 409 and "sizes its own orders" in r.json()["detail"]
        assert ident(c, label="Renamed").status_code == 200            # a rename is still fine
    finally:
        c.labdesk.close()


def test_a_market_with_no_micro_cannot_be_switched(paths):
    c = make(paths, root="RTY")
    try:
        r = ident(c, instrument="micro")
        assert r.status_code == 409 and "no micro" in r.json()["detail"]
    finally:
        c.labdesk.close()


def test_a_switch_is_refused_in_session_and_with_a_round_open(mini):
    mini.engine.now_et = lambda: IN_SESSION
    assert ident(mini, instrument="micro").status_code == 409
    assert ident(mini, label="Fine in session").status_code == 200       # only the contract waits for the window to close
    mini.engine.now_et = lambda: AFTER_CLOSE
    open_round(mini)
    r = ident(mini, instrument="micro")
    assert r.status_code == 409 and "Flatten" in r.json()["detail"]
    assert "exec_root" not in store.get("pp_orb")


def test_a_failed_sidecar_write_puts_the_record_back(mini, monkeypatch):
    assert set_limits(mini, max_qty=1).status_code == 200
    assert book(mini, [("main", 1)]).status_code == 200

    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(store, "put_desk", boom)
    r = ident(mini, instrument="micro")
    assert r.status_code == 409
    got = store.get("pp_orb")
    assert "exec_root" not in got and got["qty"] == 1


def test_a_duplicate_is_a_copy_that_is_off_with_no_account(mini):
    assert book(mini, [("main", 1)]).status_code in (200, 409)
    r = mini.post("/api/lab-duplicate", json={"strategy": LAB})
    assert r.status_code == 200 and r.json()["copy"] == "pp_orb_copy"
    cp = store.get("pp_orb_copy")
    assert cp["enabled"] is False and cp["id"] == "draft_pp_orb_copy" and cp["label"] == "PP ORB (copy)"
    assert cp["source"] == "class X: pass\n" and cp["sha256"] == "ab"
    assert store.get_desk("pp_orb_copy") is None
    assert store.get("pp_orb")["name"] == "pp_orb"                   # the original is untouched
    assert mini.post("/api/lab-duplicate", json={"strategy": LAB}).json()["copy"] == "pp_orb_copy2"
    assert journal(mini, "lab_duplicated")[-1]["copy"] == "pp_orb_copy2"


def test_a_duplicate_of_a_long_name_keeps_the_name_valid(paths):
    name = "a" * 40
    c = make(paths, name=name, id=f"draft_{name}")
    try:
        r = c.post("/api/lab-duplicate", json={"strategy": f"lab_{name}"})
        assert r.status_code == 200 and len(r.json()["copy"]) == 40 and r.json()["copy"].endswith("_copy")
    finally:
        c.labdesk.close()


def test_a_duplicate_of_something_that_is_not_there_is_a_404(mini):
    assert mini.post("/api/lab-duplicate", json={"strategy": "lab_nope"}).status_code == 404


def test_a_set_row_is_not_held_to_the_cap_and_keeps_its_settings_on_the_switch(mini):
    assert set_limits(mini, max_qty=1).status_code == 200
    row = {"account": "main", "qty": 4, "size": "contracts", "stop_after": "win", "most": 5}
    assert mini.post("/api/book", json={"strategy": LAB, "assignments": [row]}).status_code == 200
    assert set_limits(mini, max_qty=1).status_code == 200           # lowering the cap does not refuse a set row
    r = ident(mini, instrument="micro")
    assert r.status_code == 200
    assert mini.cfg.book[LAB] == [{**row, "qty": 40, "most": 50}]


def test_a_most_over_1000_micros_after_the_switch_is_held_at_1000(mini):
    assert set_limits(mini, max_qty=1).status_code == 200
    row = {"account": "main", "qty": 4, "size": "contracts", "most": 200}       # 200 minis = 2,000 micros: over the box's 1,000
    assert mini.post("/api/book", json={"strategy": LAB, "assignments": [row]}).status_code == 200
    assert ident(mini, instrument="micro").status_code == 200
    assert mini.cfg.book[LAB] == [{**row, "qty": 40, "most": 1000}]
