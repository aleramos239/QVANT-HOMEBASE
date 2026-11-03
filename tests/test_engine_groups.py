"""Account cycle groups (the owner, 2026-10-25): Lab strategies share ONE take-turns pointer over a set of accounts,
never a long on one account while a short is open on another, every order sized to the group's dollars at risk.
Fake adapters only: no broker, no IO outside tmp_path."""
from __future__ import annotations

import pytest

from homebase.desk.engine import Engine
from homebase.desk.engine_groups import GroupError
from homebase.desk.engine_lab import GROUP_HEDGE
from homebase.desk import labdesk
from tests import test_engine_lab as tlab

TWO = "lab_two"
ACCTS = ("a1", "a2", "a3")


def mk(tmp_path, accounts=ACCTS):
    """Two Lab strategies (tlab.LAB and TWO), both booked on every account."""
    eng, ads, clock = tlab.mk(tmp_path, accounts=accounts, extra={TWO: tlab.lab_cfg()},
                              book={TWO: [{"account": a, "qty": 1} for a in accounts]})
    return eng, ads, clock


def enter(eng, name, legs, max_rounds=5):
    legs = legs if isinstance(legs, list) else [legs]
    return tlab.run(eng.lab_enter(name, legs, {a: 1 for a in eng.adapters}, max_rounds=max_rounds))


def took(out) -> list:
    return [a for a, r in out["accounts"].items() if r["ok"]]


def group(eng, on=True, **kw):
    return eng.set_group("g", {"name": "Apex", "members": [tlab.LAB, TWO], "accounts": list(ACCTS), "on": on, **kw})


def test_off_group_changes_nothing(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng, on=False)
    assert took(enter(eng, tlab.LAB, tlab.leg())) == list(ACCTS)       # every booked account, as always


def test_members_share_one_turn(tmp_path):
    eng, ads, _ = mk(tmp_path)
    assert group(eng)["next"] == "a1"
    assert took(enter(eng, tlab.LAB, tlab.leg(iid=1))) == ["a1"]
    assert took(enter(eng, TWO, tlab.leg(iid=2))) == ["a2"]          # the other member: the NEXT account
    assert took(enter(eng, TWO, tlab.leg(iid=3))) == ["a3"]          # (one at a time per strategy is the door's)
    assert took(enter(eng, tlab.LAB, tlab.leg(iid=4))) == []         # every account holds a trade: skipped
    assert len(tlab.events(tmp_path, "group_skipped")) == 1
    assert eng.groups_view()["g"]["next"] == "a1"


def test_busy_account_passes_the_turn(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    eng.groups["g"]["last"] = "a3"                                   # a1 is next ...
    ads["a1"].net = 1                                                # ... but holds NQ already: a2 takes it
    assert took(enter(eng, tlab.LAB, tlab.leg())) == ["a2"]


def test_opposite_entry_is_skipped_and_the_turn_stays(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    enter(eng, tlab.LAB, tlab.leg(iid=1, side="Buy"))                # a1: a buy entry working
    out = enter(eng, TWO, tlab.leg(iid=2, side="Sell", px=90.0, sl=95.0, tp=80.0))
    assert out["reason"] == GROUP_HEDGE and took(out) == []
    assert [len(ads[a].brackets) for a in ACCTS] == [1, 0, 0]
    assert eng.groups_view()["g"]["next"] == "a2"                    # the turn did not move
    lines = tlab.events(tmp_path, "group_hedge_skipped")
    assert len(lines) == 1 and lines[0]["open"] == ["Buy"] and lines[0]["sides"] == ["Sell"]
    assert took(enter(eng, TWO, tlab.leg(iid=3, side="Buy"))) == ["a2"]     # the same direction: the next account


def test_a_pair_meets_anything_open(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    enter(eng, tlab.LAB, tlab.leg(iid=1, side="Buy"))
    assert enter(eng, TWO, tlab.pair())["reason"] == GROUP_HEDGE


def test_broker_position_on_another_account_counts(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    ads["a3"].trade_view = lambda: {"positions": [{"symbol": "NQZ6", "net": -2}], "orders": []}
    assert enter(eng, tlab.LAB, tlab.leg(side="Buy"))["reason"] == GROUP_HEDGE
    assert took(enter(eng, tlab.LAB, tlab.leg(iid=2, side="Sell", px=90.0, sl=95.0, tp=80.0))) == ["a1"]


def test_other_market_is_not_a_hedge(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    ads["a3"].trade_view = lambda: {"positions": [{"symbol": "GCZ6", "net": -1}], "orders": []}
    assert took(enter(eng, tlab.LAB, tlab.leg(side="Buy"))) == ["a1"]


def test_the_check_is_asked_again_when_the_round_opens(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    calls = []
    real = eng.group_hedged

    def later(g, symbol, legs, name=""):             # clear at the first ask, a short opened while the order waited
        calls.append(1)
        return len(calls) > 1 or real(g, symbol, legs, name)

    eng.group_hedged = later
    out = enter(eng, tlab.LAB, tlab.leg())
    assert out["reason"] == GROUP_HEDGE and ads["a1"].brackets == []


def test_pointer_and_switch_survive_a_restart(tmp_path):
    eng, ads, clock = mk(tmp_path)
    group(eng, risk_usd=1000.0)
    enter(eng, tlab.LAB, tlab.leg())                                 # a1
    eng2 = Engine(eng.cfg, ads, now_fn=clock, root=tmp_path)
    v = eng2.groups_view()["g"]
    assert v["on"] and v["next"] == "a2" and v["risk_usd"] == 1000.0 and v["members"] == [tlab.LAB, TWO]


@pytest.mark.parametrize("body, words", [
    ({"members": ["nope"]}, "not a Lab strategy"),
    ({"accounts": ["zz"]}, "not an account"),
    ({"risk_usd": -1}, "Risk per trade"),
    ({"max_minis": 0}, "Most per trade"),
    ({"members": [], "on": True}, "needs a strategy"),
    ({"on": "yes"}, "on must be"),
])
def test_bad_settings_are_refused(tmp_path, body, words):
    eng, _, _ = mk(tmp_path)
    with pytest.raises(GroupError, match=words):
        eng.set_group("g", {"name": "x", "members": [tlab.LAB], "accounts": ["a1"], **body})
    assert eng.groups == {}


def test_one_group_per_strategy_and_delete(tmp_path):
    eng, _, _ = mk(tmp_path)
    group(eng)
    with pytest.raises(GroupError, match="already in the group"):
        eng.set_group("h", {"name": "h", "members": [TWO], "accounts": ["a1"]})
    eng.delete_group("g")
    assert eng.groups_view() == {} and eng.group_of(tlab.LAB) is None


# ------------------------------------------------------------------------------------------------ through the Lab door
def desk(tmp_path, **kw):
    from tests import labdesk_util as lu
    d = lu.mkdesk(tmp_path, accounts=("a1", "a2"))
    d.eng.set_group("g", {"name": "Apex", "members": [lu.LAB], "accounts": ["a1", "a2"], "on": True, **kw})
    return lu, d


def test_risk_sizes_the_order(tmp_path):
    lu, d = desk(tmp_path, risk_usd=1000.0, max_minis=17)
    # buy stop 110, stop 105: 5 points x $20 an NQ = $100 a contract -> $1,000 = 10 NQ ($300 limit: 3)
    row = lu.send(d, [lu.entry()])["results"][0]
    assert row["status"] == "working" and [a for a, r in row["accounts"].items() if r["ok"]] == ["a1"]
    assert d.ads["a1"].brackets[0].qty == 3          # the strategy's own "at risk per trade" ($300) still caps it


@pytest.mark.parametrize("risk, qty", [(1000.0, 10), (5000.0, 17)])    # $100 a contract; at most 17 NQ
def test_risk_sizes_up_to_the_cap(tmp_path, risk, qty):
    from tests import labdesk_util as lu
    d = lu.mkdesk(tmp_path, accounts=("a1", "a2"), limits=dict(lu.LIMITS, max_risk_usd=100_000))
    d.eng.set_group("g", {"name": "A", "members": [lu.LAB], "accounts": ["a1", "a2"], "on": True,
                          "risk_usd": risk, "max_minis": 17})
    assert lu.send(d, [lu.entry()])["results"][0]["status"] == "working"
    assert d.ads["a1"].brackets[0].qty == qty and d.ads["a2"].brackets == []


def test_no_size_fits_is_refused_and_not_counted(tmp_path):
    lu, d = desk(tmp_path, risk_usd=40.0)            # $40 at a $100-a-contract stop: not one contract
    row = lu.send(d, [lu.entry()])["results"][0]
    assert row["status"] == "cancelled" and row["refused"] == labdesk.GROUP_NO_SIZE
    assert d.ads["a1"].brackets == [] and d.ld._rec(lu.LAB)["untaken"] == 0


def test_hedge_skip_is_not_an_untaken_entry(tmp_path):
    lu, d = desk(tmp_path)
    d.ads["a2"].trade_view = lambda: {"positions": [{"symbol": "NQZ6", "net": -1}], "orders": []}
    for i in (1, 2, 3):
        row = lu.send(d, [lu.entry(iid=i)], seq=i)["results"][0]
        assert row["status"] == "cancelled" and row["refused"] == GROUP_HEDGE
    assert d.ld._rec(lu.LAB)["untaken"] == 0 and d.ld._rec(lu.LAB)["stopped"] is None



@pytest.mark.parametrize("risk, qty", [(1000.0, 10), (1060.0, 11), (160.0, 1), (140.0, 1), (60.0, None)])
def test_rounding_never_goes_more_than_ten_percent_over(tmp_path, risk, qty):
    """$100 a contract. $1,060 -> 11 ($1,100, under 10 % over); $160 -> 2 would be $200 (25 % over): 1; $140 -> 1;
    $60 -> 1 would be $100 (67 % over): none fits, refused."""
    from tests import labdesk_util as lu
    d = lu.mkdesk(tmp_path, accounts=("a1",), limits=dict(lu.LIMITS, max_risk_usd=100_000))
    d.eng.set_group("g", {"name": "A", "members": [lu.LAB], "accounts": ["a1"], "on": True, "risk_usd": risk})
    lu.send(d, [lu.entry()])
    assert [b.qty for b in d.ads["a1"].brackets] == ([qty] if qty else [])


@pytest.mark.parametrize("cycle, own, qty", [(500.0, {}, 5), (500.0, None, 5), (0.0, 1000.0, 10), (500.0, 1000.0, 10),
                                              (5000.0, 300.0, 3)])
def test_a_strategy_s_own_risk_sizes_its_trades(tmp_path, cycle, own, qty):
    """$100 a contract: a member with its own risk in the cycle (risk_by) is sized to it; one without keeps the cycle's."""
    from tests import labdesk_util as lu
    d = lu.mkdesk(tmp_path, accounts=("a1",), limits=dict(lu.LIMITS, max_risk_usd=100_000))
    body = {"name": "A", "members": [lu.LAB], "accounts": ["a1"], "on": True, "risk_usd": cycle}
    if own is not None:
        body["risk_by"] = own if isinstance(own, dict) else {lu.LAB: own}
    d.eng.set_group("g", body)
    lu.send(d, [lu.entry()])
    assert [b.qty for b in d.ads["a1"].brackets] == [qty]


def test_risk_by_is_kept_checked_and_follows_the_members(tmp_path):
    eng, ads, clock = mk(tmp_path)
    group(eng, risk_usd=2000.0, risk_by={tlab.LAB: 1500, TWO: 0})
    assert eng.groups["g"]["risk_by"] == {tlab.LAB: 1500.0}                  # 0 = the cycle's risk: not kept
    eng.set_group("g", {"max_minis": 10})                                     # left out: kept
    assert Engine(eng.cfg, ads, now_fn=clock, root=tmp_path).groups["g"]["risk_by"] == {tlab.LAB: 1500.0}
    for bad in ({tlab.LAB: -1}, {tlab.LAB: "1500"}, {tlab.LAB: True}, {tlab.LAB: float("nan")}, {tlab.LAB: 1e9}, [1500]):
        with pytest.raises(GroupError, match="Risk per strategy"):
            eng.set_group("g", {"risk_by": bad})
    assert eng.groups["g"]["risk_by"] == {tlab.LAB: 1500.0}
    eng.set_group("g", {"members": [TWO]})                                    # a strategy that leaves takes its amount along
    assert eng.groups["g"]["risk_by"] == {}


def test_a_bad_risk_by_in_the_file_keeps_the_group(tmp_path):
    import json
    eng, ads, clock = mk(tmp_path)
    group(eng, risk_usd=2000.0)
    raw = json.loads((tmp_path / "groups.json").read_text())
    raw["g"]["risk_by"] = {tlab.LAB: "x", TWO: 900, "lab_gone": 500}
    (tmp_path / "groups.json").write_text(json.dumps(raw))
    g = Engine(eng.cfg, ads, now_fn=clock, root=tmp_path).groups["g"]
    assert g["on"] and g["risk_by"] == {TWO: 900.0}


def test_cycle_on_switches_on_each_members_take_turns(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng, on=False)
    assert not eng.rotating(tlab.LAB) and not eng.rotating(TWO)          # off: nothing of theirs changes
    group(eng)
    assert eng.rotating(tlab.LAB) and eng.rotating(TWO)
    eng.set_group("g", {"on": False})                                    # off again: each keeps taking turns on its own
    assert eng.rotating(tlab.LAB) and eng.rotating(TWO)
    assert took(enter(eng, tlab.LAB, tlab.leg())) == ["a1"]              # one account, not all three


# ------------------------------------------------------------------------------------------------ review fixes 2026-10-26
def test_a_full_size_nq_position_counts_for_micro_members(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    eng.cfg.strategies[tlab.LAB] = __import__("dataclasses").replace(eng.cfg.strategies[tlab.LAB], symbol="MNQ")
    ads["a2"].trade_view = lambda: {"positions": [{"symbol": "NQZ6", "net": -1}], "orders": []}   # NQ short, by hand
    assert enter(eng, tlab.LAB, tlab.leg(side="Buy"))["reason"] == GROUP_HEDGE


def test_an_order_of_unknown_fate_counts_as_open(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    enter(eng, tlab.LAB, tlab.leg(iid=1, side="Buy"))                   # a1
    st = eng.states[f"{tlab.LAB}@a1"]
    st.status = "error"                                                 # the broker timed out: it may rest there
    eng._lab_x(st)["clean"] = False
    assert enter(eng, TWO, tlab.leg(iid=2, side="Sell", px=90.0, sl=95.0, tp=80.0))["reason"] == GROUP_HEDGE


def test_a_strategy_outside_the_cycle_may_not_hedge_its_accounts(tmp_path):
    three = "lab_three"
    eng, ads, clock = tlab.mk(tmp_path, accounts=ACCTS, extra={TWO: tlab.lab_cfg(), three: tlab.lab_cfg()},
                              book={TWO: [{"account": a, "qty": 1} for a in ACCTS], three: [{"account": "a2", "qty": 1}]})
    eng.set_group("g", {"name": "Apex", "members": [tlab.LAB, TWO], "accounts": ["a1", "a2"], "on": True})
    enter(eng, tlab.LAB, tlab.leg(iid=1, side="Buy"))                   # a1: long
    out = tlab.run(eng.lab_enter(three, [tlab.leg(iid=9, side="Sell", px=90.0, sl=95.0, tp=80.0)], {"a2": 1}, max_rounds=5))
    assert out["accounts"]["a2"]["reason"] == GROUP_HEDGE and ads["a2"].brackets == []
    out = tlab.run(eng.lab_enter(three, [tlab.leg(iid=10, side="Buy")], {"a2": 1}, max_rounds=5))
    assert out["accounts"]["a2"]["ok"]                                  # the same way is fine


def test_an_account_is_in_one_group_at_most(tmp_path):
    three = "lab_three"
    eng, ads, _ = tlab.mk(tmp_path, accounts=ACCTS, extra={TWO: tlab.lab_cfg(), three: tlab.lab_cfg()})
    group(eng)
    with pytest.raises(GroupError, match="already in the group"):
        eng.set_group("h", {"name": "h", "members": [three], "accounts": ["a3"]})


def test_booked_only_outside_the_cycle_is_said_not_silent(tmp_path):
    eng, ads, _ = mk(tmp_path)
    eng.set_group("g", {"name": "Apex", "members": [tlab.LAB, TWO], "accounts": ["a1"], "on": True})
    out = tlab.run(eng.lab_enter(tlab.LAB, [tlab.leg()], {"a2": 1, "a3": 1}, max_rounds=5))
    assert out["reason"] == "It is not booked on any account of its group." and all(not ad.brackets for ad in ads.values())
    assert eng.groups_view()["g"]["outside"] == {tlab.LAB: ["a2", "a3"], TWO: ["a2", "a3"]}
    assert len(tlab.events(tmp_path, "group_skipped")) == 1


def test_saving_an_on_cycle_leaves_a_take_turns_switched_off_by_hand(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    eng.set_rotation(TWO, False)                                        # the owner, on TWO's page
    eng.set_group("g", {"risk_usd": 900.0})
    assert not eng.rotating(TWO) and eng.rotating(tlab.LAB)


def test_a_new_team_gets_the_first_free_id(tmp_path):
    eng, ads, _ = mk(tmp_path)
    assert eng.new_team_id() == "g1"
    eng.set_group("g1", {"name": "A"})
    eng.set_group("g3", {"name": "C"})
    assert eng.new_team_id() == "g2"


def _leftover(tmp_path, groups):
    import json
    p = tmp_path / "deskgroups.json"
    p.write_text(json.dumps({"groups": groups, "next": 9}))
    return p


def test_leftover_team_is_adopted_off_with_no_accounts(tmp_path):
    eng, ads, _ = mk(tmp_path)
    p = _leftover(tmp_path, [{"id": "g2", "name": "Eval", "kind": "eval", "members": [TWO, "nq930_not_lab"]}])
    assert eng.adopt_teams(p) == ["g2"]
    g = eng.groups["g2"]
    assert (g["name"], g["members"], g["accounts"], g["mode"], g["on"]) == ("Eval", [TWO], [], "cycle", False)
    assert not eng.rotating(TWO), "an OFF team switches no Take turns on"
    assert len(tlab.events(tmp_path, "group_set")) == 1


def test_adopted_file_is_renamed_retired_once(tmp_path):
    from homebase.desk.engine_groups import retire
    eng, ads, _ = mk(tmp_path)
    p = _leftover(tmp_path, [{"id": "g2", "name": "Eval", "members": [TWO]}])
    assert eng.adopt_teams(p) == ["g2"] and retire(p) is True
    retired = tmp_path / "deskgroups.json.retired"
    assert not p.exists() and retired.exists()
    kept = retired.read_text()
    assert eng.adopt_teams(p) == [] and retire(p) is False             # a second start: nothing there, nothing changes
    assert retired.read_text() == kept and eng.groups["g2"]["members"] == [TWO]
    p.write_text("{}")                                                  # a new leftover never overwrites the first
    assert retire(p) is False and p.exists() and retired.read_text() == kept


def test_a_leftover_team_id_clash_never_overwrites_the_desk_team(tmp_path):
    eng, ads, _ = mk(tmp_path)
    eng.set_group("g1", {"name": "Apex", "members": [tlab.LAB], "accounts": ["a1"], "on": True})
    before = dict(eng.groups["g1"])
    p = _leftover(tmp_path, [{"id": "g1", "name": "Old", "members": [TWO]},
                             {"id": "g2", "name": "Clash", "members": [tlab.LAB]},     # already in g1: a GroupError
                             {"id": "g3", "name": "Fine", "members": [TWO]}])
    assert eng.adopt_teams(p) == ["g3"]
    assert eng.groups["g1"] == before and "g2" not in eng.groups


def test_an_account_done_for_the_day_passes_the_cycle_turn_on(tmp_path):
    """stop_after is the account's own rule: the group's turn skips it (as it skips a busy account) and moves on."""
    eng, ads, _ = mk(tmp_path)
    group(eng)
    for r in eng.cfg.book[tlab.LAB]:
        if r["account"] == "a1":
            r["stop_after"] = "win"
    st = tlab.run(eng.lab_enter(tlab.LAB, [tlab.leg(iid=1)], {"a1": 1}, max_rounds=5))["accounts"]["a1"] and tlab.rnd(eng)
    tlab.fill_entry(eng, ads["a1"], st, 100.0)
    tlab.fill_exit(eng, ads["a1"], st, 110.0, "tp")                   # a1 won
    tlab.tick(eng)
    eng.groups["g"]["last"] = "a3"                                    # a1 is next ...
    assert took(enter(eng, tlab.LAB, tlab.leg(iid=2))) == ["a2"]      # ... but it is done: the turn moves on
    assert len(ads["a1"].brackets) == 1


# ------------------------------------------------------------------------------------------------ modes (owner, 2026-10-30)
def test_share_mode_every_account_takes_every_trade(tmp_path):
    eng, ads, _ = mk(tmp_path)
    v = group(eng, mode="share")
    assert v["mode"] == "share" and v["next"] is None
    assert not eng.rotating(tlab.LAB)                                    # no take-turns switched on for it
    assert took(enter(eng, tlab.LAB, tlab.leg(iid=1))) == list(ACCTS)
    out = enter(eng, TWO, tlab.leg(iid=3, side="Sell", px=90.0, sl=95.0, tp=80.0))
    assert out["reason"] == GROUP_HEDGE and took(out) == []              # the hedge block still covers them all


def test_share_mode_a_pair_goes_to_every_account(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng, mode="share")
    assert took(enter(eng, tlab.LAB, tlab.pair())) == list(ACCTS)       # one signal is not a hedge of itself
    assert enter(eng, TWO, tlab.pair())["reason"] == GROUP_HEDGE        # another strategy's pair still is


def test_split_mode_each_strategy_trades_its_own_account(tmp_path):
    eng, ads, _ = mk(tmp_path)
    v = group(eng, mode="split", assign={tlab.LAB: "a2", TWO: "a3"})
    assert v["assign"] == {tlab.LAB: "a2", TWO: "a3"} and v["next"] is None
    assert v["outside"] == {tlab.LAB: ["a1", "a3"], TWO: ["a1", "a2"]}   # booked there, never traded there
    assert took(enter(eng, tlab.LAB, tlab.leg(iid=1))) == ["a2"]
    assert took(enter(eng, TWO, tlab.leg(iid=2))) == ["a3"]
    assert [len(ads[a].brackets) for a in ACCTS] == [0, 1, 1]


def test_split_mode_blocks_a_hedge_across_its_accounts(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng, mode="split", assign={tlab.LAB: "a1", TWO: "a2"})
    enter(eng, tlab.LAB, tlab.leg(iid=1, side="Buy"))                    # a1 long
    out = enter(eng, TWO, tlab.leg(iid=2, side="Sell", px=90.0, sl=95.0, tp=80.0))
    assert out["reason"] == GROUP_HEDGE and ads["a2"].brackets == []


def test_split_mode_without_an_account_never_trades(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng, mode="split", assign={tlab.LAB: "a1"})
    out = enter(eng, TWO, tlab.leg())
    assert out["reason"].startswith("Its own account in its group cannot") and all(not ad.brackets for ad in ads.values())


def test_modes_are_checked_kept_and_survive_a_restart(tmp_path):
    eng, ads, clock = mk(tmp_path)
    with pytest.raises(GroupError, match="Mode"):
        group(eng, mode="all")
    with pytest.raises(GroupError, match="ticked accounts"):
        group(eng, mode="split", assign={tlab.LAB: "zz"})
    group(eng, mode="split", assign={tlab.LAB: "a1", "gone": "a2"})
    assert eng.groups["g"]["assign"] == {tlab.LAB: "a1"}                 # a non-member's account is dropped
    v = Engine(eng.cfg, ads, now_fn=clock, root=tmp_path).groups_view()["g"]
    assert v["mode"] == "split" and v["assign"] == {tlab.LAB: "a1"}
    eng.set_group("g", {"accounts": ["a1", "a2"], "assign": {tlab.LAB: "a1", TWO: "a2"}})
    assert eng.groups["g"]["mode"] == "split"                            # a save without the mode keeps it
    eng.set_group("g", {"accounts": ["a1"]})
    assert eng.groups["g"]["assign"] == {tlab.LAB: "a1"}                 # an account taken out takes its strategy's with it


def test_an_old_file_reads_as_a_cycle(tmp_path):
    eng, ads, clock = mk(tmp_path)
    group(eng)
    import json
    p = tmp_path / "groups.json"
    d = json.loads(p.read_text())
    d["g"].pop("mode"), d["g"].pop("assign")
    p.write_text(json.dumps(d))
    v = Engine(eng.cfg, ads, now_fn=clock, root=tmp_path).groups_view()["g"]
    assert v["mode"] == "cycle" and v["assign"] == {} and v["next"] == "a1"
