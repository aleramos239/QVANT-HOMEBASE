"""Audit 2026-10-27 (feed group): LevelTimer keeps its subscriptions through a failed rebuild, revives the take watcher
after the fire, and fires each strategy apart from the others' history reads."""
from __future__ import annotations

import asyncio

from homebase.broker.base import FillEvent
from tests.test_leveltimer import Rig, run, strat as leveltimer_strat


def test_a_failed_md_rebuild_keeps_the_subscription_and_closes_the_half_built_socket(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    closed = []

    async def close():
        closed.append(1)
    r.md.close = close
    r.tick(8, 55, 5)
    assert r.lt.status()["strategies"]["lv_atr_take"]["stage"] == "live" and r.lt._subs == {"NQ": "NQZ6"}
    r.md.connected = False                                       # the socket died after the stage
    real = r.md.subscribe_quote

    async def refused(symbol):
        raise RuntimeError("subscribeQuote timeout")
    r.md.subscribe_quote = refused
    r.tick(8, 56, 0)
    assert closed == [1] and r.lt._md is None and r.lt._subs == {"NQ": "NQZ6"}      # nothing forgotten, nothing leaked
    r.md.subscribe_quote = real
    n = len(r.md.subs)
    r.tick(8, 56, 20)                                            # MD_RETRY_S later
    assert r.md.connected and len(r.md.subs) == n + 1 and r.lt._subs == {"NQ": "NQZ6"}


def test_a_live_strategy_whose_symbol_lost_its_subscription_subscribes_again(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.tick(8, 55, 5)
    r.lt._subs.clear()
    r.tick(8, 55, 6)
    assert r.lt._subs == {"NQ": "NQZ6"}


def test_a_socket_that_dies_after_the_fire_with_a_trade_open_is_rebuilt(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.day_to_the_fire()
    st = r.eng._state("lv_atr_take", "a")
    run(r.eng.on_fill(FillEvent(account_id="a", symbol="NQZ6", side="Buy", qty=4, price=st.upper_px + 0.25,
                                raw={"orderId": st.upper_id})))
    n = len(r.md.connects)
    r.md.connected = False                                       # token expiry / a kick, position open
    r.tick(9, 45, 0)
    assert len(r.md.connects) == n + 1 and r.md.connected and r.lt._subs == {"NQ": "NQZ6"}


def test_one_strategys_slow_history_read_does_not_hold_the_others(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.eng.cfg.strategies["lv_atr_target"] = leveltimer_strat("lv_atr_target")
    order = []

    async def slow(*a, **k):
        order.append("history-start")
        await asyncio.sleep(0.05)
        order.append("history-end")

    async def fire(*a, **k):
        order.append("fire")
    r.lt._history, r.lt._fire = slow, fire
    r.tick(8, 55, 5)
    r.clock.at(9, 30, 0.1)
    run(r.lt.tick())
    assert order[:2] == ["history-start", "history-start"] and order.count("fire") == 2   # run apart, not one after the other
