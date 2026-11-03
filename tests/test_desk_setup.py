"""One Set-up save (routes/setup.py, owner 2026-11-02): a team or a solo strategy in one call, checked whole, written in a safe
order. Through the practice Desk (the real LabDesk, the real routes) and the pure book planner."""
from __future__ import annotations

from types import SimpleNamespace

from homebase.desk import labcfg
from homebase.routes.setup import team_books
from tests.labdesk_util import LAB, LIMITS
from tests.test_fake_desk_lab import A1, A2, LIVE, desk  # noqa: F401  (the fixture)


def st(c):
    return c.get("/api/status").json()


def limits(c):
    assert c.post("/api/lab-limits", json={"strategy": LAB, "limits": LIMITS}).status_code == 200


def solo(c, **kw):
    return c.post("/api/setup", json={"strategy": LAB, "accounts": [A1, A2], "qty": 1, "turns": True, "on": True, **kw})


def team(c, **kw):
    return c.post("/api/setup", json={"team": "g1", "name": "Apex", "members": [LAB], "accounts": [A1, A2], "mode": "cycle",
                                      "risk_usd": 1000, "max_minis": 17, "on": True, **kw})


def test_solo_books_takes_turns_and_switches_on_in_one_save(desk):
    limits(desk)
    assert solo(desk).status_code == 200
    s = st(desk)
    assert s["book"][LAB] == [{"account": A1, "qty": 1}, {"account": A2, "qty": 1}]
    assert s["strategies"][LAB]["rotation"]["on"] is True and s["strategies"][LAB]["cfg"]["enabled"] is True
    assert solo(desk, accounts=[A2], turns=False, on=False).status_code == 200      # A1 out, off
    s = st(desk)
    assert s["book"][LAB] == [{"account": A2, "qty": 1}] and s["strategies"][LAB]["cfg"]["enabled"] is False
    assert s["strategies"][LAB]["rotation"]["on"] is False
    assert any(j["event"] == "setup_saved" for j in s["journal"])


def test_a_refused_solo_save_writes_nothing(desk):
    before = st(desk)["strategies"][LAB]
    r = solo(desk)                                    # no limits yet: the book is refused, so nothing else is written
    assert r.status_code == 409 and "Set the limits first." in r.json()["detail"]
    after = st(desk)["strategies"][LAB]
    assert after["rotation"] == before["rotation"] and after["cfg"]["enabled"] == before["cfg"]["enabled"]
    assert solo(desk, qty=0).status_code == 400 and solo(desk, accounts=[A1, A1]).status_code == 400


def test_a_team_routes_books_only_its_accounts_and_switches_its_strategies(desk):
    limits(desk)
    assert solo(desk, accounts=[LIVE], turns=False).status_code == 200          # booked outside the team first
    r = team(desk)
    assert r.status_code == 200 and r.json()["group"]["on"] is True
    s = st(desk)
    assert s["book"][LAB] == [{"account": A1, "qty": 1}, {"account": A2, "qty": 1}]   # LIVE dropped: only the team's
    assert s["groups"]["g1"]["outside"] == {} and s["strategies"][LAB]["cfg"]["enabled"] is True
    r = solo(desk)
    assert r.status_code == 409 and "Apex" in r.json()["detail"]                # set up on the team's page
    assert team(desk, on=False).status_code == 200                              # team OFF: its strategies off,
    s = st(desk)                                                                # its accounts and group stay
    assert s["strategies"][LAB]["cfg"]["enabled"] is False and s["groups"]["g1"]["on"] is True
    assert s["book"][LAB] == [{"account": A1, "qty": 1}, {"account": A2, "qty": 1}]
    assert team(desk, accounts=[]).status_code == 200 and st(desk)["groups"]["g1"]["on"] is False


def test_a_bad_team_is_refused_before_anything_is_written(desk):
    limits(desk)
    r = team(desk, mode="nope")
    assert r.status_code == 400 and st(desk)["groups"] == {} and LAB not in st(desk)["book"]


def test_team_off_switches_take_turns_off_for_its_strategies(desk):
    limits(desk)
    assert team(desk).status_code == 200
    assert st(desk)["strategies"][LAB]["rotation"]["on"] is True
    assert team(desk, on=False).status_code == 200
    assert st(desk)["strategies"][LAB]["rotation"]["on"] is False


def test_team_on_in_take_turns_mode_switches_it_back_on(desk):
    limits(desk)
    team(desk, on=False)
    assert st(desk)["strategies"][LAB]["rotation"]["on"] is False
    assert team(desk).status_code == 200
    assert st(desk)["strategies"][LAB]["rotation"]["on"] is True
    assert team(desk, mode="share").status_code == 200                          # ON, not Take turns: off
    assert st(desk)["strategies"][LAB]["rotation"]["on"] is False


def test_a_new_team_gets_the_next_free_id(desk):
    body = {"team": "", "members": [], "accounts": [], "mode": "cycle", "on": False}
    r = desk.post("/api/setup", json={**body, "name": "A"})
    assert r.status_code == 200 and r.json()["team"] == "g1"
    assert desk.post("/api/setup", json={**body, "name": "B"}).json()["team"] == "g2"
    assert sorted(st(desk)["groups"]) == ["g1", "g2"]


def test_team_save_moves_a_member_from_another_team_in_one_book_write(desk):
    limits(desk)
    team(desk)
    r = desk.post("/api/setup", json={"team": "g2", "name": "B", "members": [LAB], "accounts": [LIVE], "mode": "cycle",
                                      "risk_usd": 500, "max_minis": 5, "on": True})
    assert r.status_code == 200, r.text
    s = st(desk)
    assert s["groups"]["g2"]["members"] == [LAB] and s["groups"]["g2"]["on"] is True
    assert s["groups"]["g1"]["members"] == [] and s["groups"]["g1"]["on"] is False      # the old team's record is written
    assert s["book"][LAB] == [{"account": LIVE, "qty": 1}]
    books = [j for j in s["journal"] if j["event"] == "book_updated" and j.get("strategy") == LAB]
    assert len(books) == 2 and books[0]["assignments"] == [{"account": LIVE, "qty": 1}]   # the team's, then the move: one write


def test_a_move_whose_new_team_cannot_be_written_puts_the_old_team_back(desk, monkeypatch):
    limits(desk)
    team(desk)
    eng, real, calls = desk.d.eng, desk.d.eng._save_groups, []

    def save():
        calls.append(1)
        if len(calls) == 2:                                                     # the new team's write
            raise OSError("disk full")
        real()
    monkeypatch.setattr(eng, "_save_groups", save)
    try:
        desk.post("/api/setup", json={"team": "g2", "name": "B", "members": [LAB], "accounts": [LIVE], "mode": "cycle", "on": True})
    except OSError:
        pass                                                                    # the test client re-raises the server's error
    monkeypatch.setattr(eng, "_save_groups", real)
    eng._load_groups()                                                          # what the file holds
    assert eng.groups["g1"]["members"] == [LAB] and "g2" not in eng.groups
    assert st(desk)["book"][LAB] == [{"account": A1, "qty": 1}, {"account": A2, "qty": 1}]


def test_dead_team_routes_are_gone(desk):
    assert desk.post("/api/groups", json={"id": "g1", "name": "A"}).status_code in (404, 405)
    assert desk.post("/api/groups/follow", json={"id": "g1", "members": []}).status_code in (404, 405)


def cfg_of(book):
    return SimpleNamespace(book=book, accounts={"a1": 1, "a2": 1, "a3": 1, "x": 1})


def test_team_books_plans_every_mode_and_leaver():
    cfg = cfg_of({"s1": [{"account": "a1", "qty": 3, "size": "risk", "risk_usd": 500, "hold": True}, {"account": "x", "qty": 1}],
                  "s2": [], "s3": [{"account": "a2", "qty": 1}, {"account": "x", "qty": 1}]})
    old = {"members": ["s1", "s3"], "accounts": ["a1", "a2"]}
    new = {"members": ["s1", "s2"], "accounts": ["a1", "a2"], "mode": "cycle", "assign": {}}
    out = team_books(cfg, old, new)
    assert out["s1"] == [{"account": "a1", "qty": 3, "hold": True}, {"account": "a2", "qty": 1, "hold": True}]   # extras dropped
    assert out["s2"] == [{"account": "a1", "qty": 1}, {"account": "a2", "qty": 1}]
    assert out["s3"] == [{"account": "x", "qty": 1}]                            # left: keeps only what is not the team's
    split = {**new, "mode": "split", "assign": {"s1": "a2"}}
    out = team_books(cfg, old, split, hold={"s1": False})
    assert out["s1"] == [{"account": "a2", "qty": 1}] and "s2" not in out       # s2: no account, no change
    same = cfg_of({"s1": [{"account": "a1", "qty": 1}, {"account": "a2", "qty": 1}]})
    assert team_books(same, {}, {"members": ["s1"], "accounts": ["a1", "a2"], "mode": "share", "assign": {}}) == {}


def book_a1(c, **row):
    r = c.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 1, **row}]})
    assert r.status_code == 200, r.text


A1_ROW = {"size": "risk", "risk_usd": 500, "most": 2, "contract": "NQ"}


def test_a_solo_save_keeps_every_rows_settings_and_takes_new_ones(desk):
    limits(desk)
    book_a1(desk, **A1_ROW)
    assert solo(desk, turns=False).status_code == 200                      # a2 ticks in, no settings touched
    book = st(desk)["book"][LAB]
    assert book[0] == {"account": A1, "qty": 1, **A1_ROW}
    assert book[1] == {"account": A2, "qty": 1}
    mine = {A2: {"qty": 3, "size": "contracts", "most": 20, "contract": "MNQ"}, "nobody": {"qty": 9}}
    assert solo(desk, turns=False, settings=mine).status_code == 200       # a setting for an unticked account is ignored
    book = st(desk)["book"][LAB]
    assert book[0] == {"account": A1, "qty": 1, **A1_ROW}
    assert book[1] == {"account": A2, "qty": 3, "size": "contracts", "most": 20, "contract": "MNQ"}
    assert len(book) == 2


def test_a_solo_save_with_a_contract_the_strategy_cannot_trade_writes_nothing(desk):
    limits(desk)
    book_a1(desk)
    before = st(desk)["book"][LAB]
    r = solo(desk, turns=False, settings={A2: {"contract": "ES"}})
    assert r.status_code == 409 and "ES" in r.json()["detail"]
    assert st(desk)["book"][LAB] == before
    r = desk.post("/api/book", json={"strategy": LAB, "assignments": [{"account": A1, "qty": 1, "contract": "ES"}]})
    assert r.status_code == 409 and st(desk)["book"][LAB] == before        # the book route says no too


def test_a_team_save_keeps_a_rows_contract():
    cur = [{"account": "a1", "qty": 2, "contract": "NQ"}]
    cfg = SimpleNamespace(book={"s": cur}, accounts={"a1": 1, "a2": 1})
    new = {"members": ["s"], "assign": {}, "mode": "cycle", "accounts": ["a1", "a2"]}
    out = team_books(cfg, {}, new)["s"]
    assert out[0] == {"account": "a1", "qty": 2, "contract": "NQ"} and out[1] == {"account": "a2", "qty": 1}


def test_a_solo_save_with_a_row_the_cap_cannot_fill_writes_nothing(desk):
    labcfg.record_of(desk.d.ld.cfg, LAB)["exec_root"] = "MNQ"       # its orders go to MNQ (the practice Desk has no switch route)
    assert desk.post("/api/lab-limits", json={"strategy": LAB, "limits": {**LIMITS, "max_qty": 5}}).status_code == 200
    r = solo(desk, turns=False, settings={A2: {"contract": "NQ"}})
    assert r.status_code == 409 and "NQ is over this strategy's Most contracts (5 MNQ). Raise Limits first." in r.json()["detail"]
    assert not st(desk)["book"].get(LAB)
    assert solo(desk, turns=False, settings={A2: {"contract": "NQ", "size": "risk", "risk_usd": 500}}).status_code == 200   # a set row: no cap


def test_a_save_that_changes_a_contract_with_a_trade_open_on_it_is_refused_whole(desk):
    limits(desk)
    assert solo(desk, turns=False).status_code == 200
    st_ = desk.d.eng._state(LAB, A2)
    st_.status, st_.qty = "live", 1                                         # a2 holds a trade, in the strategy's own NQ
    before = st(desk)["book"][LAB]
    r = solo(desk, turns=False, qty=2, settings={A1: {"qty": 2}, A2: {"contract": "MNQ"}})
    assert r.status_code == 409 and "has an open trade on NQ; change it once it is flat." in r.json()["detail"]
    assert st(desk)["book"][LAB] == before                                  # a1's size went nowhere either
    assert solo(desk, turns=False, settings={A2: {"contract": "NQ"}}).status_code == 200   # the contract it already trades in
    assert solo(desk, turns=False, settings={A2: {"qty": 2, "size": "contracts"}}).status_code == 200   # size only: next round
    st_.symbol = "MNQ"                                                      # a round in MNQ now: NQ is the change
    r = solo(desk, turns=False, settings={A2: {"contract": "NQ"}})
    assert r.status_code == 409 and "has an open trade on MNQ; change it once it is flat." in r.json()["detail"]
    del desk.d.eng.states[f"{LAB}@{A2}"]                                    # the trade is over
    assert solo(desk, turns=False, settings={A2: {"contract": "NQ"}}).status_code == 200   # flat: allowed


def test_the_open_rounds_contract_is_read_when_an_earlier_round_of_the_day_is_archived(desk):
    limits(desk)
    assert solo(desk, turns=False).status_code == 200
    eng, key = desk.d.eng, f"{LAB}@{A2}"
    first = eng._state(LAB, A2)
    first.status, first.symbol = "done", "NQ"                               # round 1: over, clean, in NQ
    eng._lab_mem()[key] = {**eng._lab_blank(1), "clean": True}
    eng._lab_archive(key, first)
    second = eng._state(LAB, A2)                                            # round 2: live, in MNQ (inserted after the archive)
    second.status, second.qty, second.symbol = "live", 1, "MNQ"
    assert [s.symbol for s in eng.day_states(LAB) if s.account == A2][0] == "NQ" and eng.lab_open_symbol(LAB, A2) == "MNQ"
    assert solo(desk, turns=False, settings={A2: {"contract": "MNQ", "qty": 2, "size": "contracts"}}).status_code == 200   # size only
    r = solo(desk, turns=False, settings={A2: {"contract": "NQ"}})
    assert r.status_code == 409 and "has an open trade on MNQ; change it once it is flat." in r.json()["detail"]
    assert eng.lab_open_symbol(LAB, A1) is None
