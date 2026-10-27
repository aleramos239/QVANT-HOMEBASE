"""Account rotation (the owner, 2026-10-19): "one trade one account, next trade new account, same strategy but take
turns for the execution". Off by default. Fake adapters only: no broker, no IO outside tmp_path."""
from __future__ import annotations

import datetime as dt

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.desk.engine import Engine
from tests import test_engine_lab as tlab
from tests.test_engine import ALERT, Clock, FakeAdapter, run

ACCTS = ("a", "b", "c")


def mk(tmp_path, accounts=ACCTS, clock=None):
    clock = clock or Clock()
    cfg = AppCfg(armed=True,
                 accounts={a: AccountCfg(keyring_key="k", account_name=a.upper()) for a in accounts},
                 book={"nq930": [{"account": a, "qty": 1} for a in accounts]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0,
                                                  tp_pts=15.0, enabled=True)})
    ads = {a: FakeAdapter(a) for a in accounts}
    return Engine(cfg, ads, now_fn=clock, root=tmp_path), ads, clock


def placed(ads) -> list[str]:
    return [a for a, ad in ads.items() if ad.brackets]


def next_day(eng, ads, clock):
    clock.dt += dt.timedelta(days=1)
    for ad in ads.values():
        ad.brackets.clear()


def test_off_by_default_every_account_trades(tmp_path):
    eng, ads, _ = mk(tmp_path)
    assert eng.rotation_view("nq930") == {"on": False, "next": None}
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    assert placed(ads) == ["a", "b", "c"]


def test_round_robin_in_book_order_and_wraps(tmp_path):
    eng, ads, clock = mk(tmp_path)
    eng.set_rotation("nq930", True)
    assert eng.rotation_view("nq930") == {"on": True, "next": "a"}
    got = []
    for _ in range(4):                               # one straddle a day: a, b, c, then a again
        out = run(eng.handle_alert(dict(ALERT)))
        assert out["ok"] and list(out["accounts"]) == placed(ads)
        got += placed(ads)
        next_day(eng, ads, clock)
    assert got == ["a", "b", "c", "a"]
    assert eng.rotation_view("nq930")["next"] == "b"


def test_blocked_account_is_skipped_turn_moves_on(tmp_path):
    eng, ads, clock = mk(tmp_path)
    eng.set_rotation("nq930", True)
    run(eng.handle_alert(dict(ALERT)))               # a
    next_day(eng, ads, clock)
    eng.book("b").locked = "day_lock"                # b: stopped for the day
    run(eng.handle_alert(dict(ALERT)))
    assert placed(ads) == ["c"]
    next_day(eng, ads, clock)
    ads["a"]._connected = False                      # a: disconnected
    run(eng.handle_alert(dict(ALERT)))
    assert placed(ads) == ["b"]                      # (a new day: b's lock was yesterday's)


def test_all_blocked_skips_the_trade_with_one_journal_line(tmp_path):
    eng, ads, _ = mk(tmp_path)
    eng.set_rotation("nq930", True)
    for ad in ads.values():
        ad._connected = False
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"] and placed(ads) == []
    lines = tlab.events(tmp_path, "rotation_skipped")
    assert len(lines) == 1 and lines[0]["strategy"] == "nq930"
    assert lines[0]["reason"] == "No booked account could take this trade."
    assert eng.day_status("nq930") == "idle"         # nothing acted: no error state left on any account
    assert eng.rotation_view("nq930")["next"] == "a"  # the turn did not move


def test_pointer_and_switch_survive_a_restart(tmp_path):
    eng, ads, clock = mk(tmp_path)
    eng.set_rotation("nq930", True)
    run(eng.handle_alert(dict(ALERT)))               # a
    eng2 = Engine(eng.cfg, ads, now_fn=clock, root=tmp_path)
    assert eng2.rotation_view("nq930") == {"on": True, "next": "b"}
    next_day(eng2, ads, clock)
    run(eng2.handle_alert(dict(ALERT)))
    assert placed(ads) == ["b"]


def test_switch_is_journaled_and_off_restores_all(tmp_path):
    eng, ads, clock = mk(tmp_path)
    eng.set_rotation("nq930", True)
    eng.set_rotation("nq930", False)
    assert [r["on"] for r in tlab.events(tmp_path, "rotation_set")] == [True, False]
    run(eng.handle_alert(dict(ALERT)))
    assert placed(ads) == ["a", "b", "c"]


def test_unbooked_last_account_starts_from_the_first(tmp_path):
    eng, ads, clock = mk(tmp_path)
    eng.set_rotation("nq930", True)
    run(eng.handle_alert(dict(ALERT)))               # a
    eng.cfg.book["nq930"] = [{"account": "c", "qty": 1}, {"account": "b", "qty": 1}]
    assert eng.rotation_view("nq930")["next"] == "c"


# ------------------------------------------------------------------------------------------------ a Lab strategy
def test_lab_rounds_take_turns(tmp_path):
    eng, ads, _ = tlab.mk(tmp_path, accounts=("a1", "a2"))
    eng.set_rotation(tlab.LAB, True)
    first = tlab.go(eng, tlab.leg())
    assert [a for a, r in first["accounts"].items() if r["ok"]] == ["a1"]
    second = tlab.go(eng, tlab.leg(iid=2))
    assert [a for a, r in second["accounts"].items() if r["ok"]] == ["a2"]
    assert [len(ads[a].brackets) for a in ("a1", "a2")] == [1, 1]
    # both hold a working entry: neither can take a third -> skipped, one line
    third = tlab.go(eng, tlab.leg(iid=3))
    assert not any(r["ok"] for r in third["accounts"].values())
    assert len(tlab.events(tmp_path, "rotation_skipped")) == 1
    assert eng.rotation_view(tlab.LAB)["next"] == "a1"


def test_lab_account_not_flat_is_skipped(tmp_path):
    eng, ads, _ = tlab.mk(tmp_path, accounts=("a1", "a2"))
    eng.set_rotation(tlab.LAB, True)
    ads["a1"].net = 1                                # a1 holds NQ already: it sits out, a2 takes the trade
    out = tlab.go(eng, tlab.leg())
    assert out["accounts"]["a2"]["ok"] and not out["accounts"]["a1"]["ok"]
    assert ads["a1"].brackets == [] and len(ads["a2"].brackets) == 1
    assert eng.rotation_view(tlab.LAB)["next"] == "a1"


def test_lab_rotation_off_every_account(tmp_path):
    eng, ads, _ = tlab.mk(tmp_path, accounts=("a1", "a2"))
    out = tlab.go(eng, tlab.leg())
    assert all(r["ok"] for r in out["accounts"].values())


# ------------------------------------------------------------------------------------------------ bars, levels
def test_bar_rule_takes_turns(tmp_path):
    from tests import test_feed_rules as tf
    cfg = tf.mkcfg()
    cfg.accounts["b"] = AccountCfg(keyring_key="k", account_name="B")
    cfg.book["bar_test"].append({"account": "b", "qty": 2})
    ads = {a: FakeAdapter(a) for a in cfg.accounts}
    clock = Clock(14, 0)                             # 10:00 ET
    eng = Engine(cfg, ads, now_fn=clock, root=tmp_path)
    eng.set_rotation("bar_test", True)
    eng.book("main").locked = "day_lock"             # main's turn, but it is stopped for the day: b takes it
    out = run(eng.handle_signal("bar_test", tf.SIG))
    assert out["ok"] and list(out["accounts"]) == ["b"] and placed(ads) == ["b"]
    assert eng.rotation_view("bar_test")["next"] == "main"


def test_levels_takes_turns(tmp_path):
    from tests import test_engine_levels as tl
    eng, ads, clock = tl.desk(tmp_path, {"lv_atr_take": tl.strat()}, {"a": tl.paper(), "b": tl.paper()},
                              {"lv_atr_take": [("a", 4), ("b", 2)]})
    eng.set_rotation("lv_atr_take", True)
    out = run(eng.handle_levels("lv_atr_take", tl.GEO))
    assert out["ok"] and list(out["accounts"]) == ["a"] and placed(ads) == ["a"]
    assert list(tl.events(tmp_path, "levels_placed")[0]["accounts"]) == ["a"]


# ------------------------------------------------------------------------------------------------ through the Lab door
def test_lab_intake_sends_the_entry_to_one_account(tmp_path):
    from tests import labdesk_util as lu
    d = lu.mkdesk(tmp_path, accounts=("a1", "a2"))
    d.eng.set_rotation(lu.LAB, True)
    row = lu.send(d, [lu.entry()])["results"][0]
    assert row["status"] == "working" and row["refused"] is None
    assert [a for a, r in row["accounts"].items() if r["ok"]] == ["a1"] and "a2" not in row["accounts"]
    assert len(d.ads["a1"].brackets) == 1 and d.ads["a2"].brackets == []
    assert lu.journal(tmp_path, "lab_refused") == []         # the account that was not asked is not "refused"
    assert d.eng.rotation_view(lu.LAB)["next"] == "a2"


def test_lab_intake_skips_a_stopped_account(tmp_path):
    from tests import labdesk_util as lu
    d = lu.mkdesk(tmp_path, accounts=("a1", "a2"))
    d.eng.set_rotation(lu.LAB, True)
    d.eng.book("a1").locked = "day_lock"
    row = lu.send(d, [lu.entry()])["results"][0]
    assert row["status"] == "working"
    assert row["accounts"]["a2"]["ok"] and not row["accounts"]["a1"]["ok"]
    assert d.ads["a1"].brackets == [] and len(d.ads["a2"].brackets) == 1
