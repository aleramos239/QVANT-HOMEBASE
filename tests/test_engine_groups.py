"""Account cycle groups (the owner, 2026-10-25): Lab strategies share ONE take-turns pointer over a set of accounts,
never a long on one account while a short is open on another, every order sized to the group's dollars at risk.
Fake adapters only: no broker, no IO outside tmp_path."""
from __future__ import annotations

import pytest

from homebase.engine import Engine
from homebase.engine_groups import GroupError
from homebase.engine_lab import GROUP_HEDGE
from homebase import labdesk
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

    def later(g, symbol, legs):                      # clear at the first ask, a short opened while the order waited
        calls.append(1)
        return len(calls) > 1 or real(g, symbol, legs)

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


def test_follow_group_keeps_name_and_members_in_step(tmp_path):
    from homebase.engine_groups import GroupMissing
    eng, ads, _ = mk(tmp_path)
    group(eng)
    v = eng.follow_group("g", "Apex 300k", [TWO, "nq930_not_lab"])
    assert (v["name"], v["members"], v["on"]) == ("Apex 300k", [TWO], True)
    assert eng.follow_group("g", None, [])["on"] is False                # no strategy left: off
    with pytest.raises(GroupMissing):
        eng.follow_group("zz", "x", [])
