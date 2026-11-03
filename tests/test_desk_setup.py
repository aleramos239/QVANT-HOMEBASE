"""One Set-up save (routes/setup.py, owner 2026-11-02): a team or a solo strategy in one call, checked whole, written in a safe
order. Through the practice Desk (the real LabDesk, the real routes) and the pure book planner."""
from __future__ import annotations

from types import SimpleNamespace

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


def test_follow_books_a_strategy_that_joins_and_unbooks_one_that_leaves(desk):
    limits(desk)
    team(desk)
    r = desk.post("/api/groups/follow", json={"id": "g1", "members": []})
    assert r.status_code == 200 and r.json()["on"] is False
    assert st(desk)["book"].get(LAB, []) == []                                  # left: the team's accounts go with it
    r = desk.post("/api/groups/follow", json={"id": "g1", "members": [LAB]})
    assert r.status_code == 200 and r.json()["on"] is True                      # back in an emptied team: it routes again
    assert st(desk)["book"][LAB] == [{"account": A1, "qty": 1}, {"account": A2, "qty": 1}]
    assert desk.post("/api/groups/follow", json={"id": "nope", "members": []}).status_code == 404


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


def test_a_move_between_teams_is_one_book_write_never_empty(desk):
    limits(desk)
    team(desk)
    assert desk.post("/api/setup", json={"team": "g2", "name": "B", "members": [], "accounts": [LIVE], "mode": "cycle",
                                          "risk_usd": 500, "max_minis": 5, "on": False}).status_code == 200
    r = desk.post("/api/groups/follow", json={"groups": [{"id": "g2", "members": [LAB]}, {"id": "g1", "members": []},
                                                         {"id": "nope", "members": []}]})
    assert r.status_code == 200, r.text                         # g2 first: checked with the leaver out of g1 already
    s = st(desk)
    assert s["groups"]["g2"]["members"] == [LAB] and s["groups"]["g2"]["on"] is True and s["groups"]["g1"]["members"] == []
    assert s["book"][LAB] == [{"account": LIVE, "qty": 1}]
    books = [j for j in s["journal"] if j["event"] == "book_updated" and j.get("cause") == "setup"]
    assert len(books) == 2 and books[0]["assignments"] == [{"account": LIVE, "qty": 1}]   # the move: one write (newest first)


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
