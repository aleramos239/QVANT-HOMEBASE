"""Engine: signal -> bracketed straddles across the book -> clock-guarded
flat. No broker, no IO outside tmp_path."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from types import SimpleNamespace

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
        self.order_status: dict[str, str] = {}
        self.modified: list[tuple] = []
        self.fail_modify = False
        self.fail_market = False
        self.net_error = False
        self.fail_cancel_ids: set = set()        # each fails once, then works
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
        if self.fail_market and req.order_type == "Market":
            return OrderResult(ok=False, error="market rejected by test")
        return OrderResult(ok=True, order_id="plain")

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        if self.fail_leg and req.side == self.fail_leg:
            return OrderResult(ok=False, error="rejected by test")
        self.brackets.append(req)
        self._next_id += 1
        oid = f"{self.account_id}-{self._next_id}"
        return OrderResult(ok=True, order_id=oid,
                           raw={"sl_order_id": f"{oid}-sl", "tp_order_id": f"{oid}-tp"})

    async def modify_order(self, order_id, order_type, *, price=None,
                           stop_price=None, qty=None):
        self.modified.append((str(order_id), order_type,
                              stop_price if stop_price is not None else price))
        if self.fail_modify:
            return OrderResult(ok=False, error="modify rejected by test")
        return OrderResult(ok=True, order_id=str(order_id))

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        self.cancelled.append(str(order_id))
        if str(order_id) in self.fail_cancel_ids:
            self.fail_cancel_ids.discard(str(order_id))
            return OrderResult(ok=False, error="cancel rejected by test")
        return OrderResult(ok=True)

    async def cancel_all(self):
        self.cancel_all_calls += 1
        return OrderResult(ok=True)

    async def flatten_all(self):
        self.flatten_calls += 1
        return OrderResult(ok=True)

    async def get_net_position(self, symbol):
        if self.net_error:
            raise RuntimeError("position read failed")
        return self.net

    async def get_order_status(self, order_id):
        return self.order_status.get(str(order_id))


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
        armed=armed,
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


def test_both_legs_go_out_together(tmp_path):
    """The second leg no longer waits a round trip for the first."""
    eng, ad, _ = mkengine(tmp_path)
    orig, seen = ad.place_bracket, {"now": 0, "max": 0}

    async def slow(req):
        seen["now"] += 1
        seen["max"] = max(seen["max"], seen["now"])
        await asyncio.sleep(0.01)                  # a broker round trip
        seen["now"] -= 1
        return await orig(req)

    ad.place_bracket = slow
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    assert seen["max"] == 2                        # both in flight at once
    assert st_of(eng).status == "placed"


def test_lone_survivor_cancelled_when_first_leg_fails(tmp_path):
    """Both legs are in flight together now, so the SELL can already be
    working when the BUY is rejected — it must be cancelled, never left."""
    eng, ad, _ = mkengine(tmp_path)
    ad.fail_leg = "Buy"
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"]
    assert [b.side for b in ad.brackets] == ["Sell"]
    assert ad.cancelled == ["main-101"]
    assert st_of(eng).status == "error"


def test_a_leg_that_raises_counts_as_rejected(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    orig = ad.place_bracket

    async def boom(req):
        if req.side == "Buy":
            raise RuntimeError("socket died")
        return await orig(req)

    ad.place_bracket = boom
    out = run(eng.handle_alert(dict(ALERT)))
    assert not out["ok"] and "socket died" in out["accounts"]["main"]["reason"]
    assert ad.cancelled == ["main-101"]            # the sell that went in
    assert st_of(eng).status == "error"


def test_entry_fill_cancels_sibling(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    assert st.status == "live" and st.entry_side == "Buy"
    assert st.lower_id in ad.cancelled
    assert "entry_fill" in journal_events(tmp_path)


def test_entry_fill_without_order_id_still_cancels_sibling(tmp_path):
    """Tradovate fill pushes are sometimes partial. A fill with no usable
    order id must NOT leave the opposite entry resting."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25, raw={})))   # no orderId
    assert st.status == "live" and st.entry_side == "Buy"
    assert st.lower_id in ad.cancelled
    assert "fill_matched_by_side" in journal_events(tmp_path)


def test_reconcile_recovers_entry_filled_while_disconnected(tmp_path):
    """Socket down during the entry fill: the fill is never dispatched, so the
    opposite stop would keep resting. Reconnect must find it from the
    broker's position and cancel the sibling."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)                       # placed, no fill event seen
    ad.net = -3                                # broker says: short 3
    out = run(eng.reconcile_account("main"))
    assert out == {"nq930": "entry_recovered"}
    assert st.status == "live" and st.entry_side == "Sell"
    assert st.upper_id in ad.cancelled         # the BUY stop is gone
    assert "fill_recovered_on_reconnect" in journal_events(tmp_path)


def test_reconcile_recovers_exit_while_disconnected(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.0,
                              raw={"orderId": st.upper_id})))
    ad.net = 0                                 # bracket closed it while away
    out = run(eng.reconcile_account("main"))
    assert out == {"nq930": "exit_recovered"}
    assert st.status == "done"
    assert st.exit_reason == "closed_while_disconnected"


def test_reconcile_catches_a_trade_that_opened_and_closed_while_away(tmp_path):
    """Entry AND exit both happened in the gap: the position is flat again,
    only the entry ORDER shows the fill. The sibling must still go."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.net = 0
    ad.order_status[st.lower_id] = "Filled"
    assert run(eng.reconcile_account("main")) == {"nq930": "entry_recovered"}
    assert st.entry_side == "Sell" and st.upper_id in ad.cancelled


def test_clock_check_cancels_sibling_when_the_fill_push_is_lost(tmp_path):
    """2026-09-21: the buy stop filled but on_fill never heard of it, and
    the sell stop kept resting. The clock's order-status check must find
    the fill and cancel the sell stop."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.order_status.update({st.upper_id: "Filled", st.lower_id: "Working"})
    run(eng.clock_tick())
    assert st.status == "live" and st.entry_side == "Buy"
    assert st.lower_id in ad.cancelled
    assert "entry_found_by_check" in journal_events(tmp_path)


def test_clock_check_catches_a_trade_that_already_went_flat(tmp_path):
    """Entry and target inside one tick: flat again, so a position check
    sees nothing — the order status still shows the fill."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.net = 0
    ad.order_status[st.lower_id] = "Filled"
    run(eng.clock_tick())
    assert st.status == "live" and st.entry_side == "Sell"
    assert st.upper_id in ad.cancelled


def test_clock_check_quiet_while_both_entries_work(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.order_status.update({st.upper_id: "Working", st.lower_id: "Working"})
    run(eng.clock_tick())
    assert st.status == "placed" and ad.cancelled == []


def test_clock_check_both_filled_flattens(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.order_status.update({st.upper_id: "Filled", st.lower_id: "Filled"})
    run(eng.clock_tick())
    assert st.status == "error" and st.exit_reason == "both_filled"
    # long 3 + short 3 nets to 0 but leaves FOUR GTC brackets: all cancelled
    assert {f"{st.upper_id}-sl", f"{st.upper_id}-tp", f"{st.lower_id}-sl", f"{st.lower_id}-tp"} <= set(ad.cancelled)


def test_late_fill_push_after_the_check_keeps_the_real_prices(tmp_path):
    """The check adopted the entry first; the push that follows must still
    record the fill price so the exit grades and the P&L journals."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.order_status[st.upper_id] = "Filled"
    run(eng.clock_tick())
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Buy",
                              qty=3, price=24510.25,
                              raw={"orderId": st.upper_id})))
    assert st.entry_fill == 24510.25
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side="Sell",
                              qty=3, price=24525.0,
                              raw={"orderId": "tp-child"})))
    assert st.status == "done" and st.exit_reason == "tp"
    assert st.pnl == round((24525.0 - 24510.25) * 20 * 3, 2)
    assert ad.cancelled.count(st.lower_id) == 1      # once, not twice


def test_reconcile_leaves_quiet_state_alone(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.net = 0                                 # still waiting, nothing filled
    assert run(eng.reconcile_account("main")) == {}
    assert st.status == "placed" and ad.cancelled == []


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
    assert {f"{st.upper_id}-sl", f"{st.upper_id}-tp", f"{st.lower_id}-sl", f"{st.lower_id}-tp"} <= set(ad.cancelled)


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
    ad.net = 3                                     # still long 3 at 15:56
    clock.set_et(15, 56)
    run(eng.clock_tick())
    assert st.status == "done" and st.exit_reason == "flat"
    flat = [o for o in ad.orders if o.order_type == "Market"]
    assert len(flat) == 1 and flat[0].side == "Sell" and flat[0].qty == 3
    assert {f"{st.upper_id}-sl", f"{st.upper_id}-tp"} <= set(ad.cancelled)


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
    # the GTC stop/target must not outlive the position
    assert {f"{st.upper_id}-sl", f"{st.upper_id}-tp"} <= set(ad.cancelled)
    assert "main" in res


def test_flatten_leaves_the_brackets_if_the_market_order_fails(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.0)
    ad.net, ad.fail_market = 3, True
    run(eng.flatten_strategy("nq930"))
    assert f"{st.upper_id}-sl" not in ad.cancelled    # still protected


def test_flatten_leaves_the_brackets_if_the_position_cant_be_read(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.0)
    ad.net_error = True
    run(eng.flatten_strategy("nq930"))
    assert not any(o.order_type == "Market" for o in ad.orders)
    assert f"{st.upper_id}-sl" not in ad.cancelled


def test_failed_sibling_cancel_is_retried(tmp_path):
    """The sibling cancel is refused once: the clock sees the sell stop still
    working and cancels it again."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.fail_cancel_ids = {st.lower_id}
    _fill(eng, st, "Buy", 3, 24510.0)
    assert ad.cancelled.count(st.lower_id) == 1        # refused
    ad.order_status[st.lower_id] = "Working"
    run(eng.clock_tick())
    assert ad.cancelled.count(st.lower_id) == 2        # retried
    assert "sibling_cancel_retry" in journal_events(tmp_path)


def _later(monkeypatch, seconds):
    """`seconds` later on the engine's wall clock."""
    now = time.time() + seconds
    monkeypatch.setattr("homebase.engine.time", SimpleNamespace(
        time=lambda: now, perf_counter=time.perf_counter, monotonic=time.monotonic))


def test_an_accepted_cancel_that_did_not_take_is_sent_again_within_a_second(tmp_path, monkeypatch):
    """gc_nfp, 2026-10-02 08:30:00: the buy stop filled, the broker ACCEPTED the sell stop's cancel
    and the sell stop kept working until it was cancelled by hand a couple of seconds later. An
    accepted request is not a cancelled order: the fast check asks again and re-sends."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 1, 24510.0)                  # the first contract of three, as on the day
    assert ad.cancelled.count(st.lower_id) == 1        # sent, and accepted
    ad.order_status[st.lower_id] = "Working"           # ... but the order is still there
    run(eng.sibling_tick())
    assert ad.cancelled.count(st.lower_id) == 1        # too soon to call it refused
    _later(monkeypatch, 0.6)
    run(eng.sibling_tick())
    assert ad.cancelled.count(st.lower_id) == 2        # sent again, well inside the old 2 s wait
    assert "sibling_cancel_retry" in journal_events(tmp_path)
    ad.order_status[st.lower_id] = "Canceled"
    run(eng.sibling_tick())
    assert "sibling_cancel_confirmed" in journal_events(tmp_path)
    run(eng.sibling_tick())                            # confirmed: nothing left to watch
    assert journal_events(tmp_path).count("sibling_cancel_confirmed") == 1
    assert ad.cancelled.count(st.lower_id) == 2


def test_a_cancel_that_never_takes_is_reported_and_left_to_the_clock(tmp_path, monkeypatch):
    """Three seconds of re-sending and the sell stop still works: say so once, in the journal; the
    clock's own check (every 2 s) carries on from there."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.0)
    ad.order_status[st.lower_id] = "Working"
    _later(monkeypatch, 3.5)
    run(eng.sibling_tick())
    run(eng.sibling_tick())
    assert journal_events(tmp_path).count("sibling_cancel_unconfirmed") == 1
    _later(monkeypatch, 6.0)
    run(eng.clock_tick())                              # the slow backstop is still on it
    assert ad.cancelled.count(st.lower_id) >= 3


def test_the_fast_check_closes_a_sibling_that_filled(tmp_path):
    """The sell stop filled before its cancel landed: found at once, not at the next clock second."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.0)
    ad.order_status[st.lower_id] = "Filled"
    run(eng.sibling_tick())
    assert st.status == "error" and st.exit_reason == "both_filled"
    assert "both_filled_emergency" in journal_events(tmp_path)


def test_sibling_that_fills_after_the_exit_is_flattened(tmp_path):
    """The sell stop outlived the trade and filled later — a new, unmanaged
    short. The clock must close it and cancel its brackets."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    ad.fail_cancel_ids = {st.lower_id}
    _fill(eng, st, "Buy", 3, 24510.0)
    _fill(eng, st, "Sell", 3, 24525.0, oid="tp-child")   # target: done
    assert st.status == "done"
    ad.order_status[st.lower_id] = "Filled"
    ad.net = -3
    run(eng.clock_tick())
    assert st.status == "error" and st.exit_reason == "both_filled"
    flat = [o for o in ad.orders if o.order_type == "Market"]
    assert len(flat) == 1 and flat[0].side == "Buy" and flat[0].qty == 3
    assert {f"{st.lower_id}-sl", f"{st.lower_id}-tp"} <= set(ad.cancelled)


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


def test_restart_recovers_todays_skips(tmp_path):
    """A desk restart after the 09:28:30 prestage must keep today's skips —
    so an alert or retry never places onto a skipped account (Task 6 review
    minor 1)."""
    clock = Clock()
    eng, _, _ = mkengine(tmp_path, clock=clock)
    eng.skip_today("nq930", "main")
    eng.journal("timer_skipped", strategy="nq930", reason="manual_position",
                account="main", net=2, orders=[])
    cfg2 = mkcfg()
    eng2 = Engine(cfg2, {"main": FakeAdapter("main")}, now_fn=clock,
                  root=tmp_path)
    assert eng2.skipped_today("nq930") == {"main"}
    # a gate_chop skip (no account) never fabricates one
    eng2.journal("timer_skipped", strategy="nq930", reason="gate_chop", adx=14.0)
    eng3 = Engine(cfg2, {"main": FakeAdapter("main")}, now_fn=clock,
                  root=tmp_path)
    assert eng3.skipped_today("nq930") == {"main"}


def test_malformed_journal_lines_never_crash_construction(tmp_path):
    """Fix round 1 item 1: a malformed journal must never crash engine
    construction (the desk must still start). A JSON line that isn't an
    object (a bare int, null, a list) must not raise AttributeError on
    .get(); a non-UTF-8 byte must not raise UnicodeDecodeError past the
    OSError-only guard; a truncated last line just fails to parse. The good
    line among the garbage still counts."""
    good = json.dumps({"ts": 1, "et": "2026-09-14T09:28:30",
                       "event": "timer_skipped", "strategy": "nq930",
                       "reason": "manual_position", "account": "a1", "net": 2})
    p = tmp_path / "journal.jsonl"
    body = b"5\n" + b"null\n" + b"[1, 2]\n" + good.encode() + b"\n" \
        + b"\xff\xfe not valid utf-8\n" \
        + b'{"truncated": "no closing brace'          # no trailing newline
    p.write_bytes(body)
    clock = Clock()
    cfg = mkcfg()
    eng = Engine(cfg, {"main": FakeAdapter("main")}, now_fn=clock, root=tmp_path)
    assert eng.skipped_today("nq930") == {"a1"}


# --- SL/TP measured from the ACTUAL fill, like the research -------------------
def _fill(eng, st, side, qty, price, oid=None):
    run(eng.on_fill(FillEvent(account_id="main", symbol="NQZ6", side=side,
                              qty=qty, price=price,
                              raw={"orderId": oid or (st.upper_id if side == "Buy"
                                                      else st.lower_id)})))


def test_buy_fill_moves_brackets_to_the_fill(tmp_path):
    """Buy stop 24510 fills 1 tick worse at 24510.25: SL/TP move to
    24505.25 / 24525.25 — 5 and 15 points from where price actually filled."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.25)
    assert ad.modified == [(f"{st.upper_id}-sl", "Stop", 24505.25),
                           (f"{st.upper_id}-tp", "Limit", 24525.25)]
    assert st.lower_id in ad.cancelled
    assert "brackets_moved" in journal_events(tmp_path)


def test_sell_fill_moves_brackets_to_the_fill(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Sell", 3, 24489.75)             # sell stop 24490, 1 tick worse
    assert ad.modified == [(f"{st.lower_id}-sl", "Stop", 24494.75),
                           (f"{st.lower_id}-tp", "Limit", 24474.75)]


def test_fill_at_the_trigger_moves_nothing(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.0)
    assert ad.modified == []


def test_split_entry_moves_once_from_the_average_fill(tmp_path):
    """3 lots fill as 1 @ 24510.25 + 2 @ 24510.50: nothing moves on the first
    piece; once all 3 are in, SL/TP sit off the average (24510.4167), rounded
    to a real tick."""
    eng, ad, _ = mkengine(tmp_path)
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 1, 24510.25)
    assert ad.modified == []                        # entry not complete yet
    _fill(eng, st, "Buy", 2, 24510.50)
    assert ad.modified == [(f"{st.upper_id}-sl", "Stop", 24505.5),
                           (f"{st.upper_id}-tp", "Limit", 24525.5)]
    assert round(st.entry_fill, 4) == 24510.4167 and st.entry_qty == 3


def test_failed_move_keeps_the_trigger_brackets(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    ad.fail_modify = True
    st = _place(eng, ad)
    _fill(eng, st, "Buy", 3, 24510.25)
    assert st.status == "live" and st.lower_id in ad.cancelled
    moved = [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text().splitlines()
             if json.loads(l)["event"] == "brackets_moved"][0]
    assert moved["moved"] is False and "rejected" in moved["error"]


def test_entry_fill_that_beats_the_acks_is_kept(tmp_path):
    """The BUY fills while the SELL's ack is still in flight (9:30 open):
    the fill is held and replayed once both legs are placed — sibling
    cancelled, brackets moved."""
    eng, ad, _ = mkengine(tmp_path)
    orig = ad.place_bracket

    async def racing(req):
        r = await orig(req)
        if req.side == "Sell":                      # BUY already accepted
            await eng.on_fill(FillEvent(account_id="main", symbol="NQZ6",
                                        side="Buy", qty=3, price=24510.25,
                                        raw={"orderId": "main-101"}))
        return r

    ad.place_bracket = racing
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    st = st_of(eng)
    assert st.status == "live" and st.entry_side == "Buy"
    assert st.lower_id in ad.cancelled
    assert (f"{st.upper_id}-sl", "Stop", 24505.25) in ad.modified


def test_second_signal_during_placement_is_refused(tmp_path):
    eng, ad, _ = mkengine(tmp_path)
    orig, second = ad.place_bracket, {}

    async def racing(req):
        if req.side == "Buy" and not second:
            second["out"] = await eng.handle_alert(dict(ALERT))
        return await orig(req)

    ad.place_bracket = racing
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    assert second["out"]["ok"] is False and "already" in second["out"]["reason"]
    assert len(ad.brackets) == 2                    # one straddle, not two


def test_every_account_is_placed_at_the_same_time(tmp_path):
    """Apex x3 + live x1: the live account's orders must not wait behind the
    Apex's broker round trip."""
    cfg = mkcfg(book={"nq930": [{"account": "main", "qty": 3},
                                {"account": "live1", "qty": 1}]})
    cfg.accounts["live1"] = AccountCfg(keyring_key="k2", account_name="L1", live=True)
    adapters = {aid: FakeAdapter(aid) for aid in cfg.accounts}
    seen = {"now": 0, "max": 0}
    for ad in adapters.values():
        async def slow(req, orig=ad.place_bracket):
            seen["now"] += 1
            seen["max"] = max(seen["max"], seen["now"])
            await asyncio.sleep(0.01)
            seen["now"] -= 1
            return await orig(req)
        ad.place_bracket = slow
    eng = Engine(cfg, adapters, now_fn=Clock(), root=tmp_path)
    assert run(eng.handle_alert(dict(ALERT)))["ok"]
    assert seen["max"] == 4                         # 2 accounts x 2 legs at once
    assert [b.qty for b in adapters["live1"].brackets] == [1, 1]
