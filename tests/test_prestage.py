"""The 9:30 bot skips, for the day, any booked account already holding a
position in its symbol at 09:28:30 (user-approved, spec 2026-09-26) — or a
working order resting in it (controller ruling P1). The read is capped so it
can never delay the 09:30:00 fire (ruling P6)."""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.server import compute_readiness
from homebase.timer import SelfTimer
from tests.test_engine import Clock, FakeAdapter
from tests.test_timer import FakeMD, _drive_to_fire, events, run

UTC = dt.timezone.utc


class HangingAdapter(FakeAdapter):
    async def get_net_position(self, symbol):
        await asyncio.sleep(10)
        return 0


class CountingAdapter(FakeAdapter):
    reads = 0

    async def get_net_position(self, symbol):
        CountingAdapter.reads += 1
        return await super().get_net_position(symbol)


class OrderAdapter(FakeAdapter):
    """A fake with Task 2's cached order view (trade_view)."""
    view_orders: dict = {}          # account -> working orders, set per test
    view_positions: dict = {}       # account -> cached positions, set per test

    def trade_view(self):
        return {"orders": list(self.view_orders.get(self.account_id, [])),
                "seeded": True,
                "positions": list(self.view_positions.get(self.account_id, []))}


def _order(oid, symbol):
    return {"order_id": oid, "symbol": symbol, "side": "Buy", "type": "Limit", "qty": 1,
            "price": 24400.0, "stop_price": None, "status": "Working"}


def _position(cid, symbol, net):
    return {"contract_id": cid, "symbol": symbol, "net": net, "avg_price": 24400.0}


def mk2(tmp_path, nets, adapter_cls=FakeAdapter):
    """Two-or-more booked accounts; nets: {account: net | "error"}."""
    clock = Clock()
    cfg = AppCfg(armed=False, webhook_secret="s",
                 accounts={a: AccountCfg(keyring_key="k", account_name=a.upper(), label=a.upper())
                           for a in nets},
                 book={"nq930": [{"account": a, "qty": 1} for a in nets]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0,
                                                  tp_pts=15.0, enabled=True, gated=True,
                                                  self_fire=True)})
    adapters = {}
    for a, net in nets.items():
        ad = adapter_cls(a)
        if net == "error":
            ad.net_error = True
        else:
            ad.net = net
        adapters[a] = ad
    engine = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    md = FakeMD(last_trade=24500.0)
    return SelfTimer(cfg, engine, md_factory=lambda: md, now_fn=clock), engine, clock


def test_prestage_skips_an_account_holding_the_bots_symbol(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2})
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["skipped_accounts"] == {"a2": 2}
    ev = events(tmp_path)
    skips = [e for e in ev if e["event"] == "timer_skipped"]
    assert len(skips) == 1
    assert {k: skips[0][k] for k in ("strategy", "reason", "account", "net")} == \
        {"strategy": "nq930", "reason": "manual_position", "account": "a2", "net": 2}
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a1"]
    assert ev.index(skips[0]) < next(i for i, e in enumerate(ev) if e["event"] == "dry_run")


def test_the_check_runs_at_0928_30_not_before(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 1})
    clock.set_et(9, 21)
    run(timer.tick())
    clock.dt = dt.datetime(2026, 9, 14, 13, 28, 29, tzinfo=UTC)
    run(timer.tick())
    assert not any(e["event"] == "timer_skipped" for e in events(tmp_path))
    clock.dt = dt.datetime(2026, 9, 14, 13, 28, 30, tzinfo=UTC)
    run(timer.tick())
    assert [e["account"] for e in events(tmp_path) if e["event"] == "timer_skipped"] == ["a1"]
    assert engine.skipped_today("nq930") == {"a1"}


def test_all_accounts_skipped_refuses_the_fire(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": -1})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "alert_refused" and e["reason"] == "all_accounts_skipped" for e in ev)
    assert next(e for e in ev if e["event"] == "timer_fired")["result"] is False
    assert not any(e["event"] == "dry_run" for e in ev)


def test_an_unreadable_position_fires_as_before(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": "error", "a2": 0})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and e.get("account") == "a1" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]
    assert "skipped_accounts" not in timer.status()["strategies"]["nq930"]


def test_a_hung_position_read_times_out_and_fires_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.timer.PRESTAGE_READ_S", 0.05)
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=HangingAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and "account" not in e for e in ev)
    assert timer.status()["strategies"]["nq930"]["stage"] == "fired"
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_a_skip_turns_readiness_red_for_that_account(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2})
    clock.set_et(9, 21)
    run(timer.tick())
    clock.set_et(9, 29)
    run(timer.tick())
    r = compute_readiness(engine.now_et(), engine.cfg, engine,
                          {"a1": {"connected": True}, "a2": {"connected": True}},
                          timer_status=timer.status())
    assert r["ready"] is False
    assert {"level": "bad", "label": "A2",
            "detail": "nq930 skipped today — holds +2 NQ (manual position at 09:29:00)"} in r["checks"]


def test_skips_are_for_today_only(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0})
    engine.skip_today("nq930", "a1")
    assert engine.skipped_today("nq930") == {"a1"}
    clock.dt += dt.timedelta(days=1)
    assert engine.skipped_today("nq930") == set()


# --- ruling P1: a resting manual working order skips too -------------------------------
def _orders_case(tmp_path, monkeypatch, orders):
    monkeypatch.setattr(OrderAdapter, "view_orders", orders)
    return mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=OrderAdapter)


def test_a_resting_manual_order_in_the_symbol_skips_a_flat_account(tmp_path, monkeypatch):
    timer, engine, clock = _orders_case(tmp_path, monkeypatch,
                                        {"a2": [_order("7", "NQZ6"), _order("9", "NQZ6")]})
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired"
    assert st["skipped_accounts"] == {"a2": 0} and st["skipped_orders"] == {"a2": ["7", "9"]}
    ev = events(tmp_path)
    skips = [e for e in ev if e["event"] == "timer_skipped"]
    assert [{k: e[k] for k in ("strategy", "reason", "account", "net", "orders")}
            for e in skips] == [{"strategy": "nq930", "reason": "manual_order", "account": "a2",
                                 "net": 0, "orders": ["7", "9"]}]
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a1"]
    assert engine.skipped_today("nq930") == {"a2"}


def test_a_micro_order_counts_by_the_engines_substring_rule(tmp_path, monkeypatch):
    timer, engine, clock = _orders_case(tmp_path, monkeypatch, {"a1": [_order("5", "MNQZ6")]})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert [(e["account"], e["reason"]) for e in ev if e["event"] == "timer_skipped"] == \
        [("a1", "manual_order")]
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a2"]


def test_an_order_in_another_symbol_does_not_skip(tmp_path, monkeypatch):
    timer, engine, clock = _orders_case(tmp_path, monkeypatch,
                                        {"a1": [_order("5", "ESZ6")], "a2": [_order("6", "CLX6")]})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert not any(e["event"] in ("timer_skipped", "prestage_check_failed") for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]
    assert "skipped_orders" not in timer.status()["strategies"]["nq930"]


def test_a_position_and_an_order_journal_manual_position(tmp_path, monkeypatch):
    monkeypatch.setattr(OrderAdapter, "view_orders", {"a1": [_order("5", "NQZ6")]})
    timer, engine, clock = mk2(tmp_path, {"a1": -3, "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    skips = [e for e in events(tmp_path) if e["event"] == "timer_skipped"]
    assert [(e["reason"], e["net"], e["orders"]) for e in skips] == [("manual_position", -3, ["5"])]
    st = timer.status()["strategies"]["nq930"]
    assert st["skipped_accounts"] == {"a1": -3} and st["skipped_orders"] == {"a1": ["5"]}


def test_an_unresolved_order_fires_and_journals_the_failed_check(tmp_path, monkeypatch):
    timer, engine, clock = _orders_case(tmp_path, monkeypatch, {"a1": [_order("5", None)]})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    failed = [e for e in ev if e["event"] == "prestage_check_failed"]
    assert [e["account"] for e in failed] == ["a1"] and "5" in failed[0]["error"]
    assert "unresolved" in failed[0]["error"]
    assert not any(e["event"] == "timer_skipped" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_an_unresolved_order_does_not_hide_a_resolved_one(tmp_path, monkeypatch):
    timer, engine, clock = _orders_case(tmp_path, monkeypatch,
                                        {"a1": [_order("5", None), _order("6", "NQZ6")]})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and e["account"] == "a1" for e in ev)
    assert [(e["account"], e["orders"]) for e in ev if e["event"] == "timer_skipped"] == \
        [("a1", ["6"])]


def test_a_broken_order_view_still_skips_on_the_position(tmp_path, monkeypatch):
    class Broken(FakeAdapter):
        def trade_view(self):
            raise RuntimeError("cache torn")
    timer, engine, clock = mk2(tmp_path, {"a1": 2, "a2": 0}, adapter_cls=Broken)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert [e["account"] for e in ev if e["event"] == "prestage_check_failed"] == ["a1", "a2"]
    assert [(e["account"], e["reason"]) for e in ev if e["event"] == "timer_skipped"] == \
        [("a1", "manual_position")]
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a2"]


def test_a_naked_micro_position_skips_by_the_engines_substring_rule(tmp_path, monkeypatch):
    """Task 6 review minor 2: a cached position in a related symbol (MNQ for
    an NQ bot) skips the account even though the pinned contract's own
    broker-read net is flat."""
    monkeypatch.setattr(OrderAdapter, "view_positions",
                        {"a1": [_position("1", "MNQZ6", 2)]})
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    skips = [e for e in ev if e["event"] == "timer_skipped"]
    assert [(e["account"], e["reason"], e["net"]) for e in skips] == \
        [("a1", "manual_position", 2)]
    assert engine.skipped_today("nq930") == {"a1"}
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a2"]


def test_a_different_expiry_position_skips_too(tmp_path, monkeypatch):
    """A position in a different expiry of the SAME root (NQH6 vs the
    pinned NQZ6) is caught the same way."""
    monkeypatch.setattr(OrderAdapter, "view_positions",
                        {"a2": [_position("2", "NQH6", -1)]})
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert [(e["account"], e["reason"], e["net"])
            for e in ev if e["event"] == "timer_skipped"] == [("a2", "manual_position", -1)]
    assert engine.skipped_today("nq930") == {"a2"}


def test_a_flat_cached_position_does_not_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(OrderAdapter, "view_positions", {"a1": [_position("1", "MNQZ6", 0)]})
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert not any(e["event"] == "timer_skipped" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_a_position_in_another_symbol_does_not_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(OrderAdapter, "view_positions", {"a1": [_position("1", "ESZ6", 3)]})
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert not any(e["event"] == "timer_skipped" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_an_unresolved_cached_position_fires_and_journals_the_failed_check(tmp_path, monkeypatch):
    monkeypatch.setattr(OrderAdapter, "view_positions", {"a1": [_position("1", None, 2)]})
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    failed = [e for e in ev if e["event"] == "prestage_check_failed"]
    assert [e["account"] for e in failed] == ["a1"] and "unresolved" in failed[0]["error"]
    assert not any(e["event"] == "timer_skipped" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_a_broken_view_journals_once_not_twice_per_account(tmp_path, monkeypatch):
    """trade_view() is now shared between the order and position checks: a
    broken cache must journal exactly ONE prestage_check_failed per account,
    not one per check."""
    class Broken(FakeAdapter):
        def trade_view(self):
            raise RuntimeError("cache torn")
    timer, engine, clock = mk2(tmp_path, {"a1": 2, "a2": 0}, adapter_cls=Broken)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    failed = [e for e in ev if e["event"] == "prestage_check_failed"]
    assert [e["account"] for e in failed] == ["a1", "a2"]      # exactly one each


def test_no_order_view_fires_as_before(tmp_path):
    """The base adapter's trade_view() is None (every test fake): positions only."""
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0})
    assert FakeAdapter("x").trade_view() is None
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert not any(e["event"] in ("timer_skipped", "prestage_check_failed") for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_an_order_only_skip_turns_readiness_red(tmp_path, monkeypatch):
    timer, engine, clock = _orders_case(tmp_path, monkeypatch,
                                        {"a2": [_order("7", "NQZ6"), _order("9", "MNQZ6")]})
    clock.set_et(9, 21)
    run(timer.tick())
    clock.set_et(9, 29)
    run(timer.tick())
    r = compute_readiness(engine.now_et(), engine.cfg, engine,
                          {"a1": {"connected": True}, "a2": {"connected": True}},
                          timer_status=timer.status())
    assert r["ready"] is False
    assert {"level": "bad", "label": "A2",
            "detail": "nq930 skipped today — 2 working NQ order(s) (manual, at 09:29:00)"} \
        in r["checks"]


# --- ruling P6: the read never delays the 09:30:00 fire -------------------------------
def test_the_read_is_capped_by_the_time_left_before_the_fire(tmp_path):
    """At 09:29:59.550 only 0.05 s is left once the 0.5 s margin is kept:
    the read gives up then, not after PRESTAGE_READ_S (2 s)."""
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=HangingAdapter)
    clock.set_et(9, 21)
    run(timer.tick())
    clock.dt = dt.datetime(2026, 9, 14, 13, 29, 59, 550000, tzinfo=UTC)
    t0 = time.monotonic()
    run(timer.tick())
    assert time.monotonic() - t0 < 1.0
    assert timer.status()["strategies"]["nq930"]["stage"] == "staged"
    assert any(e["event"] == "prestage_check_failed" and "account" not in e
               for e in events(tmp_path))
    clock.set_et(9, 30)
    run(timer.tick())
    assert sorted(e["account"] for e in events(tmp_path) if e["event"] == "dry_run") == \
        ["a1", "a2"]


def test_no_time_left_skips_the_read_and_fires_as_before(tmp_path):
    """A late (re)start that stages inside the last 0.5 s, or at the fire
    itself, reads nothing: the account with a position fires as before."""
    for when in (dt.datetime(2026, 9, 14, 13, 29, 59, 600000, tzinfo=UTC),
                 dt.datetime(2026, 9, 14, 13, 30, 0, tzinfo=UTC)):
        root = tmp_path / when.strftime("%H%M%S%f")
        root.mkdir()
        CountingAdapter.reads = 0
        timer, engine, clock = mk2(root, {"a1": 2}, adapter_cls=CountingAdapter)
        clock.set_et(9, 21)
        run(timer.tick())
        clock.dt = when
        run(timer.tick())
        clock.set_et(9, 30)
        run(timer.tick())
        ev = events(root)
        assert CountingAdapter.reads == 0
        assert [e["error"] for e in ev if e["event"] == "prestage_check_failed"] == \
            ["too close to the fire"]
        assert not any(e["event"] == "timer_skipped" for e in ev)
        assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a1"]


# --- controller rulings on the Task 6 concerns ---------------------------------------------
def test_a_failing_journal_never_changes_the_decision(tmp_path, monkeypatch, capsys):
    """Ruling 1: every journal write inside the check fails -> the skipped
    account is still skipped, the others still fire; the failure goes to stderr."""
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2, "a3": "error"})
    real = Engine.journal

    def flaky(self, event, **data):
        if event in ("timer_skipped", "prestage_check_failed"):
            raise OSError("disk full")
        return real(self, event, **data)
    monkeypatch.setattr(Engine, "journal", flaky)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["skipped_accounts"] == {"a2": 2}
    assert engine.skipped_today("nq930") == {"a2"}
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a3"]
    err = capsys.readouterr().err
    assert "timer_skipped" in err and "prestage_check_failed" in err and "disk full" in err


def test_a_broken_stderr_print_never_raises_into_the_stage(tmp_path, monkeypatch):
    """Task 6 review minor 3: jnl's own stderr fallback is wrapped too — if
    even THAT raises (e.g. a closed/broken stream), the stage still
    completes and the skip decision still stands."""
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2})
    real = Engine.journal

    def flaky_journal(self, event, **data):
        if event in ("timer_skipped", "prestage_check_failed"):
            raise OSError("disk full")
        return real(self, event, **data)
    monkeypatch.setattr(Engine, "journal", flaky_journal)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: (_ for _ in ()).throw(OSError("broken pipe")))
    _drive_to_fire(timer, clock)          # must not raise
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["skipped_accounts"] == {"a2": 2}
    assert engine.skipped_today("nq930") == {"a2"}


def test_an_unreadable_position_with_a_cached_manual_order_skips(tmp_path, monkeypatch):
    """Ruling 2: the position read fails but the cache shows a resting NQ
    order -> skipped, manual_order, position_unreadable."""
    monkeypatch.setattr(OrderAdapter, "view_orders", {"a1": [_order("5", "MNQZ6")]})
    timer, engine, clock = mk2(tmp_path, {"a1": "error", "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and e.get("account") == "a1" for e in ev)
    skips = [e for e in ev if e["event"] == "timer_skipped"]
    assert [{k: e.get(k) for k in ("reason", "account", "net", "orders", "position_unreadable")}
            for e in skips] == [{"reason": "manual_order", "account": "a1", "net": 0,
                                 "orders": ["5"], "position_unreadable": True}]
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a2"]
    st = timer.status()["strategies"]["nq930"]
    assert st["skipped_orders"] == {"a1": ["5"]}
    assert st["skipped_unreadable"] == {"a1": True}


def test_an_unreadable_position_readiness_says_position_unknown(tmp_path, monkeypatch):
    """Task 6 review minor 5: a position_unreadable skip reads 'position
    unknown' on the readiness strip, not a claimed flat book."""
    monkeypatch.setattr(OrderAdapter, "view_orders", {"a1": [_order("5", "MNQZ6")]})
    timer, engine, clock = mk2(tmp_path, {"a1": "error", "a2": 0}, adapter_cls=OrderAdapter)
    clock.set_et(9, 21)
    run(timer.tick())
    clock.set_et(9, 29)
    run(timer.tick())
    r = compute_readiness(engine.now_et(), engine.cfg, engine,
                          {"a1": {"connected": True}, "a2": {"connected": True}},
                          timer_status=timer.status())
    assert {"level": "bad", "label": "A1",
            "detail": "nq930 skipped today — position unknown, 1 working NQ order(s) "
                      "(manual, at 09:29:00)"} in r["checks"]


def test_an_unreadable_position_without_a_manual_order_fires_as_before(tmp_path, monkeypatch):
    """Ruling 2, other half: only an ES order cached -> fire as before."""
    monkeypatch.setattr(OrderAdapter, "view_orders", {"a1": [_order("5", "ESZ6")]})
    timer, engine, clock = mk2(tmp_path, {"a1": "error", "a2": 0}, adapter_cls=OrderAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and e.get("account") == "a1" for e in ev)
    assert not any(e["event"] == "timer_skipped" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_a_timed_out_or_skipped_read_still_honours_a_cached_manual_order(tmp_path, monkeypatch):
    """A hung read (timeout) and a stage with no time left are unreadable
    positions too: a cached manual order still skips, the flat account fires."""
    class HangingOrders(HangingAdapter, OrderAdapter):
        pass
    monkeypatch.setattr(OrderAdapter, "view_orders", {"a1": [_order("5", "NQZ6")]})
    for when in (dt.datetime(2026, 9, 14, 13, 29, 59, 550000, tzinfo=UTC),   # 0.05 s budget
                 dt.datetime(2026, 9, 14, 13, 29, 59, 900000, tzinfo=UTC)):  # no time left
        root = tmp_path / when.strftime("%H%M%S%f")
        root.mkdir()
        timer, engine, clock = mk2(root, {"a1": 0, "a2": 0}, adapter_cls=HangingOrders)
        clock.set_et(9, 21)
        run(timer.tick())
        clock.dt = when
        run(timer.tick())
        clock.set_et(9, 30)
        run(timer.tick())
        ev = events(root)
        assert [(e["account"], e["reason"], e.get("position_unreadable")) for e in ev
                if e["event"] == "timer_skipped"] == [("a1", "manual_order", True)], when
        assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a2"], when
