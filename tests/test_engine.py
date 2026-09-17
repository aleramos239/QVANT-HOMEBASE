"""Engine: signal -> bracketed straddles across the book -> clock-guarded
flat. No broker, no IO outside tmp_path."""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

from homebase.broker.base import BrokerAdapter, FillEvent, OrderRequest, OrderResult
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine

UTC = dt.timezone.utc


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeAdapter(BrokerAdapter):
    platform = "fake"

    def __init__(self, account_id="fake-acct"):
        super().__init__(account_id)
        self._connected = True
        self.orders: list[OrderRequest] = []
        self.brackets: list[OrderRequest] = []
        self.cancelled: list[str] = []
        self.cancel_all_calls = 0
        self.flatten_calls = 0
        self.fail_leg: str | None = None
        self.net = 0
        self._next_id = 100

    @property
    def connected(self):  # the base class gates on the socket; fakes are up
        return self._connected

    async def connect(self): ...
    async def close(self): ...
    async def observe_fills(self, on_fill): ...
    async def get_balance(self): return {}

    async def place_order(self, req):
        self.orders.append(req)
        return OrderResult(ok=True, order_id="plain")

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        if self.fail_leg and req.side == self.fail_leg:
            return OrderResult(ok=False, error="rejected by test")
        self.brackets.append(req)
        self._next_id += 1
        return OrderResult(ok=True, order_id=f"{self.account_id}-{self._next_id}")

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        self.cancelled.append(str(order_id))
        return OrderResult(ok=True)

    async def cancel_all(self):
        self.cancel_all_calls += 1
        return OrderResult(ok=True)

    async def flatten_all(self):
        self.flatten_calls += 1
        return OrderResult(ok=True)

    async def get_net_position(self, symbol):
        return self.net


class Clock:
    """Mutable injected clock. 13:31 UTC == 09:31 ET during EDT."""

    def __init__(self, hh=13, mm=31):
        self.dt = dt.datetime(2026, 9, 14, hh, mm, tzinfo=UTC)

    def set_et(self, hh, mm):
        self.dt = dt.datetime(2026, 9, 14, hh + 4, mm, tzinfo=UTC)

    def __call__(self):
        return self.dt


def mkcfg(armed=True, book=None) -> AppCfg:
    return AppCfg(
        armed=armed, webhook_secret="s",
        accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
        book=book if book is not None else {"nq930": [{"account": "main", "qty": 3}]},
        strategies={"nq930": StrategyCfg(
            symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0,
            tp_pts=15.0, enabled=True)})


def mkengine(tmp_path, armed=True, clock=None, cfg=None):
    clock = clock or Clock()
    cfg = cfg or mkcfg(armed)
    adapters = {aid: FakeAdapter(aid) for aid in cfg.accounts}
    eng = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    return eng, adapters["main"], clock


ALERT = {"strategy": "nq930", "upper": 24510.0, "lower": 24490.0}


def journal_events(tmp_path):
    p = tmp_path / "journal.jsonl"
    if not p.exists():
        return []
    return [json.loads(l)["event"] for l in p.read_text().splitlines()]


def st_of(eng, account="main"):
    return eng._state("nq930", account)


def test_disarmed_journals_only(tmp_path):
    eng, ad, _ = mkengine(tmp_path, armed=False)
    out = run(eng.handle_alert(dict(ALERT)))
    assert out["ok"] and out["armed"] is False
    assert ad.brackets == []
    assert "dry_run" in journal_events(tmp_path)


def test_armed_places_two_bracketed_stop_legs(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    out = run(eng.handle_alert(dict(ALERT)))
    assert out["ok"] and out["armed"]
    assert [r.side for r in ad.brackets] == ["Buy", "Sell"]
    buy, sell = ad.brackets
    assert (buy.order_type, buy.price, buy.stop_price, buy.tp_price) == \
        ("Stop", 24510.0, 24505.0, 24525.0)
    assert (sell.order_type, sell.price, sell.stop_price, sell.tp_price) == \
        ("Stop", 24490.0, 24495.0, 24475.0)
    assert buy.qty == sell.qty == 3
    assert st_of(eng).status == "placed"


def test_fan_out_places_on_every_assigned_account(tmp_path):
    cfg = mkcfg(book={"nq930": [{"account": "main", "qty": 3},
                                {"account": "spare", "qty": 1}]})
    cfg.accounts["spare"] = AccountCfg(keyring_key="k2", account_name="SPARE")
    clock = Clock()
    adapters = {aid: FakeAdapter(aid) for aid in cfg.accounts}
    eng = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    out = run(eng.handle_alert(dict(ALERT)))
    assert out["ok"]
    assert [r.qty for r in adapters["main"].brackets] == [3, 3]
    assert [r.qty for r in adapters["spare"].brackets] == [1, 1]
    assert st_of(eng, "main").status == st_of(eng, "spare").status == "placed"
    # one-per-day is book-wide
    assert run(eng.handle_alert(dict(ALERT)))["ok"] is False


def test_no_assignments_refused(tmp_path):
    eng, ad, _ = mkengine(tmp_path, cfg=mkcfg(book={}))
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"] and "assigned" in out["reason"]
    assert ad.brackets == []


def test_one_trade_per_day(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    run(eng.handle_alert(dict(ALERT)))
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"] and "already" in out["reason"]
    assert len(ad.brackets) == 2


def test_bad_spread_refused(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    out = run(eng.handle_alert({"strategy": "nq930", "upper": 24515.0,
                                "lower": 24490.0}))
    assert not out["ok"] and "spread" in out["reason"]
    assert ad.brackets == []


def test_outside_window_refused(tmp_path):
    clock = Clock()
    clock.set_et(11, 0)
    eng, ad, _ = mkengine(tmp_path, clock=clock)
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"] and "window" in out["reason"]
    assert ad.brackets == []


def test_lone_survivor_cancelled_when_second_leg_fails(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    ad.fail_leg = "Sell"
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"]
    assert len(ad.brackets) == 1
    assert ad.cancelled == ["main-101"]
    assert st_of(eng).status == "error"


def _place(eng, ad):
    run(eng.handle_alert(dict(ALERT)))
    return st_of(eng)


def test_entry_fill_cancels_sibling(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    assert st.status == "live" and st.entry_side == "Buy"
    assert st.lower_id in ad.cancelled
    assert "entry_fill" in journal_events(tmp_path)


def test_both_filled_flattens_that_account(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell",
                              qty=3, price=24490.0,
                              raw={"orderId": st.lower_id})))
    assert st.status == "error" and st.exit_reason == "both_filled"
    assert ad.cancel_all_calls == 1 and ad.flatten_calls == 1


def test_exit_fill_graded_tp_with_pnl(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell",
                              qty=3, price=24525.0, raw={"orderId": "999"})))
    assert st.status == "done" and st.exit_reason == "tp"
    assert st.pnl == round((24525.0 - 24510.25) * 20 * 3, 2)   # NQ $20/pt
    rec = [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text().splitlines()]
    exit_ev = [r for r in rec if r["event"] == "exit_fill"][0]
    assert exit_ev["pnl"] == st.pnl


def test_clock_cancels_unfilled(tmp_path):
    clock = Clock()
    eng, ad, _ = mkengine(tmp_path, clock=clock)
    st = _place(eng, ad)
    clock.set_et(12, 56)
    run(eng.clock_tick())
    assert st.status == "done" and st.exit_reason == "no_fill"
    assert st.upper_id in ad.cancelled and st.lower_id in ad.cancelled


def test_clock_cancel_detects_raced_fill(tmp_path):
    clock = Clock()
    eng, ad, _ = mkengine(tmp_path, clock=clock)
    st = _place(eng, ad)
    ad.net = 3
    clock.set_et(12, 56)
    run(eng.clock_tick())
    assert st.status == "live"


def test_clock_flattens_after_1555(tmp_path):
    clock = Clock()
    eng, ad, _ = mkengine(tmp_path, clock=clock)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    clock.set_et(15, 56)
    run(eng.clock_tick())
    assert st.status == "done" and st.exit_reason == "flat"
    assert ad.flatten_calls == 1 and ad.cancel_all_calls == 1


def test_flatten_strategy_cancels_and_flattens(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    ad.net = 3                                     # live long 3
    res = run(eng.flatten_strategy("nq930"))
    assert st.status == "done" and st.exit_reason == "manual_flat"
    flat = [o for o in ad.orders if o.order_type == "Market"]
    assert len(flat) == 1 and flat[0].side == "Sell" and flat[0].qty == 3
    assert "main" in res


def test_flatten_strategy_cancels_unfilled(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)                           # placed, nothing filled
    res = run(eng.flatten_strategy("nq930"))
    assert st.upper_id in ad.cancelled and st.lower_id in ad.cancelled
    assert st.status == "done" and st.exit_reason == "manual_flat"
    assert not any(o.order_type == "Market" for o in ad.orders)


def test_restart_recovers_state(tmp_path):
    clock = Clock()
    eng, ad, _ = mkengine(tmp_path, clock=clock)
    st = _place(eng, ad)
    cfg2 = mkcfg()
    eng2 = Engine(cfg2, {"main": FakeAdapter("main")}, now_fn=clock,
                  root=tmp_path)
    assert eng2._state("nq930", "main").status == "placed"
    assert eng2._state("nq930", "main").upper_id == st.upper_id
