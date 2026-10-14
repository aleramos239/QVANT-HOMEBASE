"""LOCK of the payout pipeline's set builder and its accounts (blueprint/pay_build.py, blueprint/pay_accounts.py).
HAND-MADE TRADES ONLY: the pool is handed over (pay_pool.members is put in its place), no store is read, no engine run is made.

1. THE DAY of an account: the slots in the day's order at one size; the day rule stops the later slots after a gain or a loss.
2. An Apex funded account takes no strategy that rests orders on both sides and none without a target of 0.2 R.
3. The accounts: a new account of the Desk gets its size from its first balance and the rule file of its firm; the owner's `rules` and
   `on` are never changed by a look at the Desk; an account is walked from its balance.
4. THE SET: a strategy that pays is taken for its slot, one that loses is not; the set is saved, its score is added to the history, a
   notice says a new set was built; nothing is built again while nothing changed.
5. SURVIVAL: the size chosen keeps the account alive often enough, though a bigger one would pay more.
6. THE UNSEEN DAYS: the set is PROVEN when every member has its read and the set still pays there; a member without a read is named.
7. The stopped ideas go round again only while the payout pipeline is the one that is on.

  pytest tests/test_pay_build.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import blueprint_synth as SY  # noqa: E402
import judge as J  # noqa: E402
import library as LB  # noqa: E402
from blueprint import pay_accounts as PA  # noqa: E402
from blueprint import pay_build as PB  # noqa: E402
from blueprint import pay_rotate as RO  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import pipe_switch as SW  # noqa: E402

CAL = SY.weekdays("2023-01-02", "2024-12-31")
DAYS = np.array([dt.date.fromisoformat(d).toordinal() for d in CAL])
UNSEEN = SY.weekdays("2025-07-01", "2025-12-31")
UDAYS = np.array([dt.date.fromisoformat(d).toordinal() for d in UNSEEN])
PRO, APEX = "lucid-pro-50k-no-dll@2026-10-11", "apex-legacy-50k@2026-10-11b"
AT = {"evening": "20:30", "night": "03:00", "day": "09:45"}


def trades(fn, slot: str = "day", cal=CAL) -> dict:
    """One trade a day in `slot`: fn(i) -> (the net at one micro, its worst open point at one micro)."""
    return LB.pack([SY.trade(d, *fn(i), at=AT[slot]) for i, d in enumerate(cal)])


steady = lambda i: ((12.0, 3.0) if i % 3 else (-10.0, 11.0))  # noqa: E731  two wins of $12 and a loss of $10: about +$4.7 a micro a day
loser = lambda i: ((-12.0, 13.0) if i % 3 else (10.0, 3.0))  # noqa: E731
wild = lambda i: ((150.0, 20.0) if i % 5 else (-400.0, 410.0))  # noqa: E731  +$40 a micro a day, and a $400 loss every fifth day


def member(name: str, fn, slot: str = "day", family=None, read=True, both=False, target_r: float = 1.0) -> dict:
    x = trades(fn, slot)
    return {"name": name, "family": family or name, "market": "NQ", "session": "nyam", "slot": slot, "both_sides": both, "read": read, "fn": fn,
            "options": [{"cell": "c", "kind": "even", "geometry": {"stop": "20 pts", "target_r": target_r, "kind": "even"}, "trades": len(x["net"]),
                         "win_rate": float((x["net"] > 0).mean()), "kept": 1.0, "net": float(x["net"].sum()), "x": x, "slot": slot, "sub": f"{name}_a5", "bar": "5"}]}


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setenv(PS.ENV, str(tmp_path / "env_root"))
    monkeypatch.delenv("HB_PIPELINE")
    root = tmp_path / "pipeline"
    root.mkdir()
    pool: list = []
    monkeypatch.setattr(PB.PP, "members", lambda r=None: ([{**m, "options": [dict(o) for o in m["options"]]} for m in pool], []))
    monkeypatch.setattr(PB.PP, "calendar", lambda markets: DAYS)
    monkeypatch.setattr(PB.PP, "unseen", lambda m, o, r=None: (trades(m["fn"], m["slot"], UNSEEN), UDAYS) if m["read"] else None)
    return root, pool


def desk(*labels, balance: float = 50_000.0) -> tuple:
    return list(labels), {k: {"2024-12-30": balance, "2024-12-31": balance} for k in labels}


# ================================================================ 1. the day

def test_the_day_is_the_slots_in_order_at_one_size_and_the_day_rule_stops_the_later_slots():
    a = {"net": np.array([100.0, -100.0, 50.0]), "open": np.array([10.0, 120.0, 0.0]), "up": np.array([100.0, 0.0, 50.0]), "n": np.ones(3)}
    b = {"net": np.array([-30.0, 40.0, 20.0]), "open": np.array([40.0, 0.0, 5.0]), "up": np.array([0.0, 40.0, 20.0]), "n": np.array([1.0, 1.0, 0.0])}
    day = PB.combine([None, a, b], 2)
    assert day["net"].tolist() == [140.0, -120.0, 140.0] and day["traded"].tolist() == [True, True, True]
    assert day["open"].tolist() == [20.0, 240.0, 0.0]      # the second slot's $80 under water came with $200 in hand: the day was never under by it
    assert day["up"].tolist() == [200.0, 0.0, 140.0]
    assert PB.combine([None, a, b], 2, gain=150.0)["net"].tolist() == [200.0, -120.0, 140.0]         # up $200 after the first slot: the day is over
    assert PB.combine([None, a, b], 2, loss=150.0)["net"].tolist() == [140.0, -200.0, 140.0]
    assert PB.combine([None, None, b], 1)["traded"].tolist() == [True, True, False]


# ================================================================ 2. what an Apex funded account may trade

def test_an_apex_funded_account_takes_no_both_sided_rule_and_none_without_a_target():
    ok, both, flat = member("ok", steady), member("both", steady, both=True), member("flat", steady, target_r=0.0)
    opt = lambda m: m["options"][0]  # noqa: E731
    assert PB.eligible(ok, opt(ok), APEX) is None and "both sides" in PB.eligible(both, opt(both), APEX) and "0.2 R" in PB.eligible(flat, opt(flat), APEX)
    assert PB.eligible(both, opt(both), PRO) is None and PB.eligible(flat, opt(flat), PRO) is None
    unknown = {**ok, "both_sides": None}
    assert "does not say" in PB.eligible(unknown, opt(unknown), APEX)


# ================================================================ 3. the accounts

def test_a_new_account_gets_its_size_and_its_firms_rule_file_and_the_owners_words_are_kept(world):
    root, _ = world
    labels, by = desk("LTF0001", "PAAPEX0002")
    by["PAAPEX0002"] = {"2024-12-01": 300_000.0, "2024-12-31": 303_000.0}
    got = {a["id"]: a for a in PA.sync(root, (labels, by))}
    assert got["LTF0001"]["size"] == 50_000 and got["LTF0001"]["rules"] == PRO and got["LTF0001"]["assumed"] is True and got["LTF0001"]["on"] is True
    assert got["PAAPEX0002"]["size"] == 300_000 and got["PAAPEX0002"]["rules"].startswith("apex-legacy-300k@") and got["PAAPEX0002"]["balance"] == 303_000.0
    assert PA.start(got["PAAPEX0002"]) == {"profit": 3000.0, "peak": 3000.0} and PA.start(got["LTF0001"]) == {"profit": 0.0, "peak": 0.0}
    file = root / "payout" / "accounts.json"
    mine = json.loads(file.read_text())
    mine["accounts"][0].update(rules="lucid-flex-50k@2026-10-11", on=False, assumed=False)
    file.write_text(json.dumps(mine))
    by["LTF0001"]["2025-01-02"] = 51_000.0
    again = {a["id"]: a for a in PA.sync(root, (labels, by))}
    assert (again["LTF0001"]["rules"], again["LTF0001"]["on"], again["LTF0001"]["assumed"], again["LTF0001"]["balance"]) == ("lucid-flex-50k@2026-10-11", False, False, 51_000.0)
    assert PA.sync(root, (None, None)) == PA.load(root)                    # a Desk that cannot be read changes nothing


# ================================================================ 4. the set

def test_a_strategy_that_pays_takes_its_slot_and_one_that_loses_does_not(world):
    root, pool = world
    pool[:] = [member("steady_day", steady), member("loser_day", loser), member("loser_night", loser, slot="night")]
    out = PB.build(root, paths=300, desk=desk("LTF0001"))
    s = out["sets"][PRO]
    assert s["slots"]["day"]["name"] == "steady_day" and s["slots"]["night"] is None and s["slots"]["evening"] is None
    assert s["size"] and s["per_week"] > 0 and s["slots"]["day"]["adds"] > 0 and out["group"]["per_week"] == pytest.approx(s["per_week"])
    assert out["group"]["accounts"][0]["id"] == "LTF0001" and out["short"]["days"] == 20 and out["worse"] <= out["group"]["per_week"]
    assert out["text"].startswith("Expected payout: $") and "day: steady_day" in out["text"] and "Evening" in out["text"]
    assert out["pool"] == {"members": 3, "by_slot": {"evening": 0, "night": 1, "day": 2}, "read": 3, "left_out": []}
    assert PB.show(root)["sets"][PRO]["slots"]["day"]["name"] == "steady_day"
    assert [n["kind"] for n in RO.notices(root)] == ["built"]
    rows = (root / "payout" / "score.jsonl").read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["per_week"] == pytest.approx(out["group"]["per_week"])


def test_nothing_in_the_pool_that_pays_is_no_set_and_says_so(world):
    root, pool = world
    pool[:] = [member("loser_day", loser)]
    out = PB.build(root, paths=200, desk=desk("LTF0001"))
    assert out["sets"][PRO]["size"] is None and out["group"]["per_week"] == 0.0 and out["text"].startswith("No set:")
    assert PB.build(root, paths=200, desk=desk())["text"].startswith("No account is on")


def test_the_runner_builds_again_only_when_something_changed_and_reads_the_evening_once_a_day(world, monkeypatch):
    root, pool = world
    pool[:] = [member("steady_day", steady)]
    monkeypatch.setattr(PB.PA, "_desk", lambda: desk("LTF0001"))
    monkeypatch.setattr(PB, "series", lambda r=None: (lambda name: (np.ones(10), "2024-12-31")))
    builds = []
    real = PB.build
    monkeypatch.setattr(PB, "build", lambda r=None, **k: builds.append(1) or real(r, paths=200))
    noon, late = dt.datetime(2026, 10, 14, 12, 0), dt.datetime(2026, 10, 14, 17, 30)
    assert PB.idle(root, noon) == {"built": True, "evening": None} and PB.idle(root, noon) == {"built": False, "evening": None}
    first = PB.idle(root, late)
    assert first["built"] is False and first["evening"]["kind"] == "set"
    assert PB.idle(root, late) == {"built": False, "evening": None}        # once a day
    pool.append(member("steady_night", steady, slot="night"))
    assert PB.idle(root, late)["built"] is True and len(builds) == 2


# ================================================================ 5. survival

def test_the_size_chosen_keeps_the_account_alive_though_a_bigger_one_would_pay_more(world):
    root, pool = world
    pool[:] = [member("wild_day", wild)]
    out = PB.build(root, paths=400, desk=desk("LTF0001"))
    s, acct = out["sets"][PRO], out["group"]["accounts"][0]
    assert s["size"] is not None and s["size"] < 5                          # $400 a micro on a losing day: 5 micros lose the $2,000 account in one
    assert acct["p_bust"] <= PB.PY.need("score", "max_bust")


# ================================================================ 6. the unseen days

def test_the_set_is_proven_when_every_member_has_its_read_and_it_still_pays_there(world):
    root, pool = world
    pool[:] = [member("steady_day", steady)]
    out = PB.build(root, paths=300, desk=desk("LTF0001"))
    assert out["proven"] is True and out["unseen"]["per_week"] > 0 and out["unseen"]["span"] == ["2025-07-01", "2025-12-31"] and out["waiting"] == []
    assert "PROVEN on the unseen days" in out["text"]


def test_a_member_without_its_read_is_named_and_the_set_is_not_proven(world):
    root, pool = world
    pool[:] = [member("steady_day", steady, read=None)]
    out = PB.build(root, paths=300, desk=desk("LTF0001"))
    assert out["proven"] is False and out["unseen"] is None and out["waiting"] == [{"name": "steady_day", "why": "it has not read the unseen days yet"}]
    assert "NOT PROVEN yet: steady_day" in out["text"]


def test_a_set_that_does_not_pay_on_the_unseen_days_is_not_proven(world, monkeypatch):
    root, pool = world
    pool[:] = [member("steady_day", steady)]
    monkeypatch.setattr(PB.PP, "unseen", lambda m, o, r=None: (trades(loser, m["slot"], UNSEEN), UDAYS))
    out = PB.build(root, paths=300, desk=desk("LTF0001"))
    assert out["proven"] is False and out["unseen"]["per_week"] == 0.0 and "NOT PROVEN: on the unseen days" in out["text"]


# ================================================================ 7. the stopped ideas

def test_the_stopped_ideas_go_round_again_only_while_the_payout_pipeline_is_on(world, monkeypatch):
    root, _ = world
    with pytest.raises(J.Refuse, match="not the one that is on"):
        PB.requeue(root)
    SW.enable("payout", True, root)
    SW.choose("payout", root)
    ideas = [{"name": "stopped_early", "status": "stopped"}, {"name": "has_a_pick", "status": "stopped", "picked": {"cell": "c"}},
             {"name": "was_read", "status": "stopped"}, {"name": "in_book", "status": "book"}]
    monkeypatch.setattr(PB.PS, "ideas", lambda r=None: ideas)
    monkeypatch.setattr(PB.PS, "stages", lambda n, r=None: {6: {}} if n == "was_read" else {1: {}})
    again = []
    from blueprint import pipe_runner as PRN
    monkeypatch.setattr(PRN, "rerun", lambda n, r=None: again.append(n))
    got = PB.requeue(root)
    assert again == ["stopped_early"] and got["requeued"] == ["stopped_early"] and "1 stopped idea go" in got["text"]
