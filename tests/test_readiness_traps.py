"""The readiness check names each line's strategy, account and fix, and says the nine traps that used to be silent
(Desk makeover task 2, spec 4.8)."""
from __future__ import annotations

import datetime as dt

from homebase.desk import labcfg
from homebase.desk.labdesk import SET_LIMITS_FIRST
from homebase.labrun import store
from homebase.server import compute_readiness
from tests.labdesk_util import LAB, LIMITS, mkdesk, rec
from tests.test_engine import run

NOLABEL = {"label": None}                # the label is then the record's name: "pp"
UP = {"a1": {"connected": True}}


def checks(d, acct=UP, lab="ld"):
    return compute_readiness(d.eng.now_et(), d.cfg, d.eng, acct, None, None, None,
                             lab=d.ld if lab == "ld" else lab)["checks"]


def mine(d, key="strategy", val=LAB, **kw):
    return [c for c in checks(d, **kw) if c.get(key) == val]


def add_pp2(d, accounts=("a1",)):
    store.put(rec(name="pp2", label=None))
    run(d.ld.refresh())
    run(d.ld.set_limits("lab_pp2", LIMITS))
    run(d.ld.set_book("lab_pp2", [{"account": a, "qty": 1} for a in accounts]))


def test_taken_off_its_accounts_says_so_with_turn_on(tmp_path):
    d = mkdesk(tmp_path, qty=0, rec_kw=NOLABEL)
    labcfg._note(d.cfg, "lab_unbooked", strategy=LAB, accounts=["a1"], why="a new version")
    d.ld._say_notes({})
    got = [c for c in mine(d) if c["detail"].startswith("Taken off its accounts (")]
    assert len(got) == 1
    c = got[0]
    assert (c["level"], c["label"], c["fix"]) == ("warn", "pp", "turn_on")
    assert c["detail"].endswith("). It is OFF: set it up and turn it on to trade again.")
    assert "a new version" in c["detail"]
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    assert not [c for c in mine(d) if c["detail"].startswith("Taken off")]


def test_two_strategies_on_one_market_and_account_warn_each(tmp_path):
    d = mkdesk(tmp_path, rec_kw=NOLABEL)
    add_pp2(d)
    shared = [c for c in checks(d) if c.get("fix") == "open"]
    assert sorted((c["strategy"], c["level"], c["account"], c["detail"]) for c in shared) == [
        ("lab_pp", "warn", "a1", "Shares NQ on ..a1 with pp2: one waits while the other holds a trade."),
        ("lab_pp2", "warn", "a1", "Shares NQ on ..a1 with pp: one waits while the other holds a trade.")]


def test_one_strategy_alone_on_its_account_shares_nothing(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"), rec_kw=NOLABEL)
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    add_pp2(d, accounts=("a2",))
    assert not [c for c in checks(d, acct={"a1": {"connected": True}, "a2": {"connected": True}})
                if c.get("fix") == "open"]


def test_a_position_block_is_bad_with_its_account(tmp_path):
    d = mkdesk(tmp_path, rec_kw=NOLABEL)
    today = d.eng._today()
    d.eng.position_blocks[(LAB, "a1")] = (today, "The account already holds NQ. Check it.")
    want = {"level": "bad", "label": "pp", "detail": "The account already holds NQ. Check it.",
            "strategy": LAB, "account": "a1"}
    assert want in checks(d)
    d.eng.position_blocks[(LAB, "a1")] = ((dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat(),
                                          "The account already holds NQ. Check it.")
    assert not [c for c in checks(d) if c["detail"] == "The account already holds NQ. Check it."]


def test_the_engine_sets_and_clears_a_position_block(tmp_path):
    d = mkdesk(tmp_path, rec_kw=NOLABEL)
    d.ads["a1"].net = {"NQ": 1}

    async def net(sym):
        return d.ads["a1"].net.get(sym, 0)
    d.ads["a1"].get_net_position = net
    why = run(d.eng._lab_position(LAB, d.cfg.strategies[LAB], "a1"))
    assert why == "The account already holds NQ. Check it."
    assert d.eng.position_blocks[(LAB, "a1")] == (d.eng._today(), why)


def test_a_window_outside_the_desk_day_says_shadow_only(tmp_path):
    d = mkdesk(tmp_path, qty=0, limits=None, window=("09:25", "17:30"))
    assert labcfg.span(labcfg.record_of(d.cfg, LAB)) is None
    got = [c for c in mine(d) if c["detail"] == labcfg.SAY_EVENING]
    assert len(got) == 1 and got[0]["level"] == "info"


def test_lab_switch_file_missing_with_booked_records_is_bad(tmp_path):
    d = mkdesk(tmp_path)
    off = type(d.ld)(d.cfg, d.eng, d.ads, on=False)
    line = {"level": "bad", "label": "Lab strategies",
            "detail": "The Lab switch file (lab_desk.on) is missing: no Lab strategy can trade."}
    assert [c for c in checks(d, lab=off) if c["label"] == "Lab strategies"] == [line]
    e = mkdesk(tmp_path / "e", qty=0, own_store=True)
    off = type(e.ld)(e.cfg, e.eng, e.ads, on=False, at=tmp_path / "e" / "store")
    off._at = tmp_path / "e" / "store"
    assert not [c for c in checks(e, lab=off) if c["label"] == "Lab strategies"]


def test_runner_down_is_one_bad_line(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._runner = lambda: {"alive": False, "age_s": 95}
    assert [c for c in checks(d) if c["label"] == "Lab runner"] == [
        {"level": "bad", "label": "Lab runner",
         "detail": "The Lab runner has not answered for 95 s: no Lab strategy can trade."}]
    d.ld._runner = lambda: {"alive": False, "age_s": None}
    assert [c["detail"] for c in checks(d) if c["label"] == "Lab runner"] == [
        "The Lab runner is not running: no Lab strategy can trade."]
    d.ld._runner = lambda: {"alive": True, "age_s": 3}
    assert not [c for c in checks(d) if c["label"] == "Lab runner"]


def test_offline_account_names_each_booked_strategy_with_reconnect(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"), rec_kw=NOLABEL)
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    got = checks(d, acct={"a1": {"connected": False}, "a2": {"connected": False}})
    assert {"level": "bad", "label": "pp", "detail": "..a1 is offline.", "strategy": LAB, "account": "a1",
            "fix": "reconnect"} in got
    assert not [c for c in got if c.get("account") == "a1" and "strategy" not in c]
    a2 = [c for c in got if c.get("account") == "a2"]
    assert len(a2) == 1 and a2[0]["level"] == "bad" and a2[0]["fix"] == "reconnect" and "strategy" not in a2[0]


def test_desk_off_is_one_line(tmp_path):
    # passes as is: the Mode line was already one line for the whole Desk
    d = mkdesk(tmp_path, armed=False, rec_kw=NOLABEL)
    add_pp2(d)
    store.put(rec(name="pp3", label=None))
    run(d.ld.refresh())
    run(d.ld.set_limits("lab_pp3", LIMITS))
    run(d.ld.set_book("lab_pp3", [{"account": "a1", "qty": 1}]))
    mode = [c for c in checks(d) if c["label"] == "Mode"]
    assert len(mode) == 1 and "strategy" not in mode[0]


def test_limits_needed_first_says_so_with_set_limits(tmp_path):
    d = mkdesk(tmp_path, qty=0, limits=None)
    try:
        d.ld.check_book(LAB, [{"account": "a1", "qty": 1}])
        refused = None
    except Exception as e:  # noqa: BLE001
        refused = str(e)
    assert refused == SET_LIMITS_FIRST
    got = [c for c in mine(d) if c.get("fix") == "limits"]
    assert len(got) == 1
    assert (got[0]["level"], got[0]["detail"]) == ("warn", "Limits needed first: it runs in shadow until they are set.")


def test_split_team_member_without_account_has_fix_team(tmp_path):
    d = mkdesk(tmp_path, qty=0)
    d.eng.groups = {"g1": {"name": "T", "members": [LAB], "mode": "split"}}
    got = [c for c in mine(d) if c["detail"].startswith("in team T")]
    assert len(got) == 1 and got[0]["fix"] == "team" and got[0]["level"] == "warn"
