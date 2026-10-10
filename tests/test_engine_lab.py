"""Engine rounds for kind "lab" (Step B, task B2): several trades a day, one position at a time, the capped
flatten, the clock, restarts -- and the proof that the eight hooks are no-ops for every other kind.

Fake adapters only: no broker, no network, no IO outside tmp_path."""
from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from homebase import engine as engine_mod
from homebase import labcfg
from homebase.broker.base import FillEvent, OrderRequest, OrderResult
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import PLACING_UNKNOWN, Engine, LabLeg
from tests import test_engine as te
from tests import test_engine_levels as tl
from tests import test_feed_rules as tf
from tests.test_engine import Clock, FakeAdapter, run

LAB = "lab_pp"
LIMITS = labcfg.LabLimits(max_trades_day=3, max_qty=2, max_risk_usd=300.0, last_entry_et="11:00", flat_et="15:55")
REC = {"name": "pp", "root": "NQ", "label": "PP", "enabled": True, "qty": 1, "commission": 4.0,
       "session_window": ["09:25", "16:00"]}


# ------------------------------------------------------------------------------------------------ fixtures
class LabAdapter(FakeAdapter):
    """FakeAdapter with a broker's order book: every order has a status, a cancel that is accepted ends a
    working order (unless the id is in `stuck`), and get_order_state says how much of an order filled."""

    def __init__(self, aid):
        super().__init__(aid)
        self.filled: dict[str, int] = {}
        self.stuck: set = set()                  # a cancel is accepted and the order keeps working
        self.reject: str | None = None           # the broker's words for the next bracket
        self.net_reads = 0

    async def place_bracket(self, req):
        if self.reject is not None:
            return OrderResult(ok=False, error=self.reject)
        r = await super().place_bracket(req)
        if r.ok:
            self.order_status[r.order_id] = "Working"
            self.order_status[f"{r.order_id}-sl"] = "Suspended"
            if req.tp_price is None:             # a stop with no target: the broker returns no target id
                r.raw["tp_order_id"] = None
            else:
                self.order_status[f"{r.order_id}-tp"] = "Suspended"
        return r

    async def cancel_order_by_id(self, order_id):
        r = await super().cancel_order_by_id(order_id)
        oid = str(order_id)
        if r.ok and oid not in self.stuck and self.order_status.get(oid) in ("Working", "Suspended"):
            self.order_status[oid] = "Canceled"
            for k in ("sl", "tp"):               # an unfilled entry takes its held stop / target with it
                if self.order_status.get(f"{oid}-{k}") == "Suspended":
                    self.order_status[f"{oid}-{k}"] = "Canceled"
        return r

    async def get_order_state(self, order_id):
        return {"status": self.order_status.get(str(order_id)), "filled_qty": self.filled.get(str(order_id))}

    async def get_net_position(self, symbol):
        self.net_reads += 1
        return await super().get_net_position(symbol)


def lab_cfg(**over) -> StrategyCfg:
    """The StrategyCfg task B1 builds for a promoted strategy (labcfg.strategy_cfg), nothing hand-made."""
    limits = over.pop("limits", LIMITS)
    return labcfg.strategy_cfg({**REC, **over}, limits)


def mk(tmp_path, accounts=("a1",), qty=1, armed=True, at=(9, 31), extra=None, book=None):
    """A desk whose one Lab strategy is booked on `accounts`. `extra`: {name: StrategyCfg} of other strategies,
    `book`: their rows."""
    clock = Clock()
    clock.set_et(*at)
    cfg = AppCfg(armed=armed,
                 accounts={a: AccountCfg(keyring_key="k", account_name=a.upper()) for a in accounts},
                 book={LAB: [{"account": a, "qty": qty} for a in accounts], **(book or {})},
                 strategies={LAB: lab_cfg(), **(extra or {})})
    ads = {a: LabAdapter(a) for a in accounts}
    eng = Engine(cfg, ads, now_fn=clock, root=tmp_path)
    quick(eng)
    return eng, ads, clock


def quick(eng):
    async def fast_sleep(s):                     # the 250 ms polls, without the wait
        await asyncio.sleep(0)

    eng._kill_sleep = fast_sleep
    return eng


def events(tmp_path, name=None):
    p = tmp_path / "journal.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    return [r for r in rows if name is None or r["event"] == name]


# ------------------------------------------------------------------------------------------------ the hooks
LAB_NAMES = [n for n in vars(Engine) if n.startswith(("_lab", "lab_"))]


def tripwire(eng) -> dict:
    """Every Lab method of this engine raises and is counted; _archived is watched: what it answered, per call."""
    seen = {"lab": [], "archived": []}
    for n in LAB_NAMES:
        def trip(*a, _n=n, **kw):
            seen["lab"].append(_n)
            raise AssertionError(f"Lab code reached: {_n}")
        setattr(eng, n, trip)
    real = eng._archived

    def archived(st):
        seen["archived"].append(real(st))
        return seen["archived"][-1]

    eng._archived = archived
    return seen


def other_kinds(tmp_path):
    """One engine per existing kind, each with its day placed: [(kind, eng, adapter, strategy, account)]."""
    out = []
    eng, ad, _ = te.mkengine(tmp_path / "straddle")
    seen = tripwire(eng)
    assert run(eng.handle_alert(dict(te.ALERT)))["ok"]
    out.append(("straddle", eng, ad, "nq930", "main", seen))
    eng, ad, _ = tf.mkengine(tmp_path / "bars")
    seen = tripwire(eng)
    assert run(eng.handle_signal("bar_test", tf.SIG))["ok"]
    out.append(("bars", eng, ad, "bar_test", "main", seen))
    eng, ads, _ = tl.desk(tmp_path / "levels", {"lv_atr_take": tl.strat()}, {"a": tl.paper()},
                          {"lv_atr_take": [("a", 4)]})
    seen = tripwire(eng)
    assert run(eng.handle_levels("lv_atr_take", tl.GEO))["ok"]
    out.append(("levels", eng, ads["a"], "lv_atr_take", "a", seen))
    return out


@pytest.fixture
def kinds(tmp_path):
    for k in ("straddle", "bars", "levels"):
        (tmp_path / k).mkdir()
    return other_kinds(tmp_path)


def enter(eng, name, account, px, side="Buy"):
    st = eng._state(name, account)
    oid = st.upper_id if side == "Buy" else st.lower_id
    run(eng.on_fill(FillEvent(account_id=account, symbol="NQZ6", side=side, qty=st.qty, price=px,
                              raw={"orderId": oid})))
    return st


def clean_journal(eng):
    """No run of the clock raised, and no bracket move failed in Lab code."""
    rows = [json.loads(line) for line in eng.journal_path.read_text().splitlines()]
    assert not [r for r in rows if r["event"] == "clock_error"]
    assert not [r for r in rows if "Lab code reached" in json.dumps(r)]


def test_the_lab_methods_are_the_ones_the_tripwire_arms():
    assert {"_lab_move", "_lab_grade", "_lab_flatten_strategy", "_lab_tick"} <= set(LAB_NAMES)


def test_hook_day_status_is_unchanged_for_every_other_kind(kinds):
    for kind, eng, ad, name, account, seen in kinds:
        assert eng.day_status(name) == "placed", kind
        assert seen["archived"] and not any(seen["archived"]), kind      # asked, and never "archived"
        assert seen["lab"] == []


def test_hook_place_sends_the_configs_own_legs_when_no_reqs_are_given(kinds):
    assert inspect.signature(Engine._place).parameters["reqs"].default is None
    _, eng, ad, _, _, seen = kinds[0]
    cfg = eng.cfg.strategies["nq930"]
    assert ad.brackets == Engine._legs(cfg, te.ALERT["upper"], te.ALERT["lower"], 3)
    _, eng, ad, _, _, seen = kinds[2]
    st = eng._state("lv_atr_take", "a")
    assert ad.brackets == Engine._legs(eng.cfg.strategies["lv_atr_take"], tl.GEO.upper, tl.GEO.lower, 4,
                                       st.sl_pts, st.tp_pts, st.sl_sell_pts)
    assert seen["lab"] == []


def test_hook_move_brackets_never_reaches_the_lab_for_another_kind(kinds):
    want = {"straddle": [("main-101-sl", "Stop", 24505.25), ("main-101-tp", "Limit", 24525.25)],
            "bars": [("main-101-tp", "Limit", 30069.5)],                 # 30035.5 + 0.75 x 45.5, on the tick
            "levels": [("a-101-sl", "Stop", 24380.25), ("a-101-tp", "Limit", 24529.25)]}
    px = {"straddle": 24510.25, "bars": 30035.5, "levels": 24510.25}
    for kind, eng, ad, name, account, seen in kinds:
        st = enter(eng, name, account, px[kind])
        assert st.status == "live" and st.brackets_moved, kind
        assert ad.modified == want[kind], kind
        assert seen["lab"] == []
        clean_journal(eng)


def test_hook_grade_exit_never_reaches_the_lab_for_another_kind(kinds):
    px = {"straddle": (24510.0, 24525.0), "bars": (30035.0, 30068.75), "levels": (24510.0, 24529.0)}
    for kind, eng, ad, name, account, seen in kinds:
        st = enter(eng, name, account, px[kind][0])
        run(eng.on_fill(FillEvent(account_id=account, symbol="NQZ6", side="Sell", qty=st.qty, price=px[kind][1],
                                  raw={"orderId": "x"})))
        assert (st.status, st.exit_reason) == ("done", "tp"), kind
        assert seen["lab"] == []


def test_hook_flatten_strategy_is_the_old_flatten_for_another_kind(kinds):
    for kind, eng, ad, name, account, seen in kinds:
        st = enter(eng, name, account, 24510.0 if kind != "bars" else 30035.0)
        ad.net = st.qty
        out = run(eng.flatten_strategy(name))
        assert out[account][0] == f"market Sell {st.qty}: ok", kind
        assert [(o.side, o.qty, o.text) for o in ad.orders] == [("Sell", st.qty, "homebase:flat")]
        assert (st.status, st.exit_reason) == ("done", "manual_flat")
        assert seen["lab"] == []


def test_hook_flatten_today_skips_nothing_of_another_kind(kinds):
    for kind, eng, ad, name, account, seen in kinds:
        st = enter(eng, name, account, 24510.0 if kind != "bars" else 30035.0)
        ad.net = st.qty
        seen["archived"].clear()
        out = run(eng.flatten_today())
        assert list(out) == [f"{name}@{account}"], kind
        assert [(o.side, o.qty) for o in ad.orders] == [("Sell", st.qty)]
        assert (st.status, st.exit_reason) == ("done", "killed")
        assert seen["archived"] == [False] and seen["lab"] == []


def test_hook_clock_tick_runs_the_old_clock_for_another_kind(kinds):
    for kind, eng, ad, name, account, seen in kinds:
        st = enter(eng, name, account, 24510.0 if kind != "bars" else 30035.0)
        ad.net = st.qty
        eng._now.set_et(15, 56)
        run(eng.clock_tick())
        assert (st.status, st.exit_reason) == ("done", "flat"), kind
        assert [e["event"] for e in map(json.loads, eng.journal_path.read_text().splitlines())].count("clock_flat") == 1
        assert seen["lab"] == []
        clean_journal(eng)


def test_the_hooks_do_reach_the_lab_for_kind_lab(tmp_path):
    """The other half of the proof: the same five calls, on a Lab state, land in the Lab section."""
    eng, ads, clock = mk(tmp_path)
    st = eng._state(LAB, "a1")
    st.status, st.qty, st.entry_side, st.upper_id, st.entry_fill = "live", 1, "Buy", "e1", 100.0
    calls = []

    async def move(s, cfg, ad):
        calls.append("move")
        return {"sl": None, "tp": None, "moved": False}

    async def tick(s, cfg, ad, now):
        calls.append("tick")

    async def flat(name):
        calls.append("flatten")
        return {}

    eng._lab_move, eng._lab_tick, eng._lab_flatten_strategy = move, tick, flat
    eng._lab_grade = lambda s, px: calls.append("grade") or "sl"
    cfg = eng.cfg.strategies[LAB]
    run(eng._move_brackets(st, cfg, ads["a1"]))
    assert eng._grade_exit(st, 99.0) == "sl"
    run(eng.flatten_strategy(LAB))
    run(eng.clock_tick())
    assert calls == ["move", "grade", "flatten", "tick"]


def test_archived_is_false_at_the_plain_key_and_true_under_a_round_key(tmp_path):
    eng, ads, _ = mk(tmp_path)
    st = eng._state(LAB, "a1")
    assert eng._archived(st) is False
    old = eng.states.pop(f"{LAB}@a1")
    eng.states[f"{LAB}@a1#1"] = old
    new = eng._state(LAB, "a1")
    assert eng._archived(old) is True and eng._archived(new) is False


# ------------------------------------------------------------------------------------------------ driving a round
def leg(iid=1, side="Buy", entry="Stop", px=100.0, sl=95.0, tp=110.0, rr=None, ref="px", move=False) -> LabLeg:
    return LabLeg(iid=iid, side=side, entry=entry, entry_price=px if entry == "Stop" else None, sl_px=sl,
                  tp_px=tp, tp_rr=rr, ref_px=px if ref == "px" else ref, move=move)


def pair(buy=110.0, sell=90.0, dist=5.0, tp=10.0):
    return [leg(3, "Buy", px=buy, sl=buy - dist, tp=buy + tp), leg(4, "Sell", px=sell, sl=sell + dist, tp=sell - tp)]


def go(eng, legs, sizes=None, max_rounds=3):
    legs = legs if isinstance(legs, list) else [legs]
    return run(eng.lab_enter(LAB, legs, sizes or {a: 1 for a in eng.adapters}, max_rounds=max_rounds))


def rnd(eng, a="a1"):
    return eng.states[f"{LAB}@{a}"]


def fill_entry(eng, ad, st, px, side="Buy", qty=None):
    """The broker fills (part of) an entry: its order book says so, then the push arrives."""
    oid = st.upper_id if side == "Buy" else st.lower_id
    q = qty or st.qty
    ad.filled[oid] = ad.filled.get(oid, 0) + q
    if ad.filled[oid] >= st.qty:
        ad.order_status[oid] = "Filled"
    for k in ("sl", "tp"):
        if ad.order_status.get(f"{oid}-{k}") == "Suspended":
            ad.order_status[f"{oid}-{k}"] = "Working"
    ad.net += q if side == "Buy" else -q
    run(eng.on_fill(FillEvent(account_id=ad.account_id, symbol="NQZ6", side=side, qty=q, price=px,
                              raw={"orderId": oid})))


def fill_exit(eng, ad, st, px, by="tp", push=True):
    """The stop or the target fills (the other is cancelled by the broker), or a market order closes it."""
    eid = st.upper_id if st.entry_side == "Buy" else st.lower_id
    q = st.entry_qty - st.exit_qty
    if by in ("sl", "tp"):
        ad.order_status[f"{eid}-{by}"] = "Filled"
        other = f"{eid}-{'tp' if by == 'sl' else 'sl'}"
        if other in ad.order_status:
            ad.order_status[other] = "Canceled"
    ad.net -= q if st.entry_side == "Buy" else -q
    if push:
        run(eng.on_fill(FillEvent(account_id=ad.account_id, symbol="NQZ6",
                                  side="Sell" if st.entry_side == "Buy" else "Buy", qty=q, price=px,
                                  raw={"orderId": f"{eid}-{by}" if by in ("sl", "tp") else "plain"})))


def tick(eng):
    eng._retry_at.clear()                        # the throttles use the wall clock
    run(eng.clock_tick())


def trade(eng, ad, a="a1", entry=100.0, exit_px=110.0, by="tp", legs=None, max_rounds=3):
    """One whole round on one account: enter, fill, exit, and the clock checks its orders."""
    out = go(eng, legs or leg(), {a: 1}, max_rounds=max_rounds)
    assert out["accounts"][a]["ok"], out
    st = rnd(eng, a)
    fill_entry(eng, ad, st, entry)
    fill_exit(eng, ad, st, exit_px, by)
    tick(eng)
    return st


def rows(eng, **want):
    return [r for r in eng.lab_rounds(LAB) if all(r[k] == v for k, v in want.items())]


# ------------------------------------------------------------------------------------------------ lab_enter
def test_the_engine_says_the_doors_own_sentences():
    from homebase.labrun import door
    assert (engine_mod.LAB_ONE_AT_A_TIME, engine_mod.LAB_NO_STOP, engine_mod.LAB_WRONG_SIDE, engine_mod.LAB_NOT_A_PAIR,
            engine_mod.LAB_BAD_ORDER, engine_mod.LAB_TOO_LATE) == \
        (door.ONE_AT_A_TIME, door.NO_STOP, door.WRONG_SIDE, door.NOT_A_PAIR, door.CANNOT_CHECK, door.TOO_LATE)


def test_disarmed_journals_only_and_creates_no_state(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"), armed=False)
    out = go(eng, leg())
    assert out["armed"] is False
    assert out["accounts"] == {a: {"ok": False, "round": None, "reason": "The desk is disarmed: written down only."}
                               for a in ("a1", "a2")}
    assert eng.states == {} and all(ad.brackets == [] for ad in ads.values())
    dry = events(tmp_path, "dry_run")
    assert [(e["strategy"], e["account"], e["qty"]) for e in dry] == [(LAB, "a1", 1), (LAB, "a2", 1)]
    assert dry[0]["legs"][0]["sl_px"] == 95.0 and eng.lab_rounds(LAB) == [] and eng.lab_open(LAB) == []
    assert json.loads((tmp_path / f"labday-{eng._today()}.json").read_text()) == {}     # the day was rolled; no round


@pytest.mark.parametrize("how,reason", [("unknown", "That strategy is not on the Desk."),
                                        ("not_lab", "That strategy is not on the Desk."),
                                        ("off", "It is off."), ("killed", "Killed today."),
                                        ("late", "Too late for a new trade today.")])
def test_a_strategy_that_may_not_trade_is_refused_whole(tmp_path, how, reason):
    eng, ads, clock = mk(tmp_path, extra={"nq930": StrategyCfg(symbol="ES", qty=1, offset_pts=1.0, sl_pts=1.0,
                                                              tp_pts=1.0, enabled=True)})
    name = LAB
    if how == "unknown":
        name = "lab_nope"
    elif how == "not_lab":
        name = "nq930"
    elif how == "off":
        eng.cfg.strategies[LAB] = lab_cfg(enabled=False)
    elif how == "killed":
        eng.kill_today(LAB)
    else:
        clock.set_et(15, 55)
    out = run(eng.lab_enter(name, [leg()], {"a1": 1}, max_rounds=3))
    assert out["accounts"] == {"a1": {"ok": False, "round": None, "reason": reason}} and out["reason"] == reason
    assert ads["a1"].brackets == [] and eng.states == {}


@pytest.mark.parametrize("legs,reason", [
    ([leg(sl=None)], "Every entry needs a stop held at the broker."),
    ([leg(sl=float("nan"))], "Every entry needs a stop held at the broker."),
    ([leg(sl=101.0)], "The stop must sit on the losing side of the entry."),
    ([leg(side="Sell", sl=99.0, tp=90.0)], "The stop must sit on the losing side of the entry."),
    ([leg(tp=99.0)], "The Desk cannot check this order."),                       # a target behind the entry
    ([leg(tp=None, rr=2.0)], "The Desk cannot check this order."),               # an RR target with no first price
    ([leg(entry="Limit")], "The Desk cannot check this order."),
    ([leg(side="long")], "The Desk cannot check this order."),
    ([leg(entry="Stop", px=None)], "The Desk cannot check this order."),
    ([], "The Desk cannot check this order."),
    ([leg(1), leg(2), leg(3)], "The Desk cannot check this order."),
    ([leg(3, "Buy", px=110.0, sl=105.0, tp=120.0), leg(4, "Buy", px=111.0, sl=105.0, tp=120.0)],
     "Only a buy-stop and sell-stop pair can be linked."),
    ([leg(3, "Buy", px=110.0, sl=105.0, tp=120.0), leg(4, "Sell", entry="Market", sl=120.0, tp=None, ref=None)],
     "Only a buy-stop and sell-stop pair can be linked."),
    ([leg(3, "Buy", px=90.0, sl=85.0, tp=95.0), leg(4, "Sell", px=110.0, sl=115.0, tp=105.0)],
     "The Desk cannot check this order."),                                       # the buy stop under the sell stop
])
def test_a_leg_the_engine_cannot_place_safely_is_refused_before_anything_exists(tmp_path, legs, reason):
    eng, ads, _ = mk(tmp_path)
    out = run(eng.lab_enter(LAB, legs, {"a1": 1}, max_rounds=3))
    assert out["accounts"]["a1"] == {"ok": False, "round": None, "reason": reason}
    assert ads["a1"].brackets == [] and eng.states == {}


def test_a_round_is_on_disk_before_its_order_leaves(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    seen = {}
    real = ad.place_bracket

    async def spy(req):
        day = json.loads((tmp_path / f"day-{eng._today()}.json").read_text())
        lab = json.loads((tmp_path / f"labday-{eng._today()}.json").read_text())
        seen.update(status=day[f"{LAB}@a1"]["status"], qty=day[f"{LAB}@a1"]["qty"], extras=lab[f"{LAB}@a1"],
                    journal=[e["event"] for e in events(tmp_path)])
        return await real(req)

    ad.place_bracket = spy
    out = go(eng, leg(iid=7, move=True))
    assert out == {"armed": True, "accounts": {"a1": {"ok": True, "round": 1, "reason": None}}}
    assert (seen["status"], seen["qty"]) == ("placing", 1)
    assert seen["extras"]["round"] == 1 and seen["extras"]["iid"] == {"Buy": 7} and seen["extras"]["clean"] is False
    assert seen["extras"]["legs"]["Buy"]["sl_px"] == 95.0 and seen["extras"]["move"] is True
    assert seen["journal"] == ["lab_round"]
    st = rnd(eng)
    assert (st.status, st.upper_id, st.up_sl_id, st.up_tp_id) == ("placed", "a1-101", "a1-101-sl", "a1-101-tp")
    placed = events(tmp_path, "placed")[0]
    assert (placed["kind"], placed["side"], placed["entry"], placed["sl"], placed["tp"]) == \
        ("bars", "Buy", "Stop", 95.0, 110.0)                       # ruling Q17: the line keeps kind "bars"
    assert eng.day_status(LAB) == "placed" and eng.lab_open(LAB) == ["a1"]


def test_the_requests_a_single_entry_and_a_pair_send(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"), qty=2)
    go(eng, leg(entry="Market", sl=95.0, tp=None, ref=100.0), {"a1": 2})
    assert ads["a1"].brackets == [OrderRequest(symbol="NQ", side="Buy", qty=2, order_type="Market", price=None,
                                               stop_price=95.0, tp_price=None, text="homebase:entry")]
    assert rnd(eng, "a1").up_tp_id is None and rnd(eng, "a1").up_sl_id == "a1-101-sl"
    go(eng, pair(), {"a2": 2})
    assert ads["a2"].brackets == [
        OrderRequest(symbol="NQ", side="Buy", qty=2, order_type="Stop", price=110.0, stop_price=105.0,
                     tp_price=120.0, text="homebase:entry"),
        OrderRequest(symbol="NQ", side="Sell", qty=2, order_type="Stop", price=90.0, stop_price=95.0,
                     tp_price=80.0, text="homebase:entry")]
    st = rnd(eng, "a2")
    assert (st.status, st.upper_id, st.lower_id, st.upper_px, st.lower_px) == ("placed", "a2-101", "a2-102", 110.0, 90.0)
    assert rows(eng, account="a2")[0]["iid"] == {"Buy": 3, "Sell": 4}


def test_a_trade_from_entry_to_target_books_its_price_and_pnl(tmp_path):
    eng, ads, _ = mk(tmp_path)
    st = trade(eng, ads["a1"], entry=100.0, exit_px=110.0, by="tp")
    assert (st.status, st.exit_reason, st.entry_fill, st.exit_fill, st.pnl) == ("done", "tp", 100.0, 110.0, 200.0)
    assert [e["event"] for e in events(tmp_path)][:6] == \
        ["lab_round", "placed", "entry_fill", "brackets_moved", "exit_fill", "day_booked"]
    assert events(tmp_path, "lab_settled")[0]["round"] == 1
    (r,) = eng.lab_rounds(LAB)
    assert (r["account"], r["round"], r["status"], r["entry_side"], r["entry_fill"], r["exit_fill"], r["exit_reason"],
            r["pnl"], r["sl"], r["tp"], r["clean"], r["why"]) == \
        ("a1", 1, "done", "Buy", 100.0, 110.0, "tp", 200.0, 95.0, 110.0, True, None)
    assert r["entry_ms"] and r["exit_ms"] and eng.lab_open(LAB) == []
    assert eng.book("a1").closed_net == 196.0                          # the account's day: gross less the $4 fee


def test_a_stop_with_no_target_is_graded_a_stop_out_not_a_target(tmp_path):
    eng, ads, _ = mk(tmp_path)
    st = trade(eng, ads["a1"], entry=100.0, exit_px=95.0, by="sl", legs=leg(tp=None))
    assert (st.status, st.exit_reason, st.tp_px, st.up_tp_id, st.pnl) == ("done", "sl", None, None, -100.0)
    moved = events(tmp_path, "brackets_moved")[0]
    assert (moved["sl"], moved["tp"]) == (95.0, None)                  # both keys, always (metrics reads them together)
    assert rows(eng)[0]["clean"] is True                               # three ids, all terminal


def oracle_levels(side, entry, sl, tp, rr, move, fill):
    """What the Strategy Tester's own fill law makes of the same order (backtest/engine.py _fill)."""
    import datetime as dt
    from homebase.backtest.engine import Costs, Ctx, _Sim
    sim = _Sim("NQ", dt.date(2026, 9, 14), [0, 1, 2], [fill, fill, fill], 0, 3, Costs(slippage_ticks=0.0), 0)
    ctx = sim._ctx = Ctx(sim, 1, [])
    ctx.move_brackets_to_fill = move
    o = ctx.stop_entry("long" if side == "Buy" else "short", entry, sl=sl, tp=tp, tp_rr=rr)
    sim._fill(o, 1)
    return o.fill_px, o.fill_sl, o.fill_tp


@pytest.mark.parametrize("side,entry,sl,tp,fill", [("Buy", 100.0, 95.0, 110.0, 101.5), ("Sell", 100.0, 105.0, 90.0, 98.75)])
@pytest.mark.parametrize("move", [False, True])
@pytest.mark.parametrize("rr", [None, 2.0])
def test_the_brackets_after_the_fill_are_the_testers(tmp_path, side, entry, sl, tp, fill, move, rr):
    """Move to the fill x target by RR, all four, long and short: the levels that rest at the broker, and the
    orders that were modified to get there, are what the tester computes."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(side=side, px=entry, sl=sl, tp=tp, rr=rr, move=move))
    st = rnd(eng)
    fill_entry(eng, ad, st, fill, side=side)
    want_fill, want_sl, want_tp = oracle_levels(side, entry, sl, tp, rr, move, fill)
    assert (st.entry_fill, st.sl_px, st.tp_px) == (want_fill, want_sl, want_tp)
    oid = st.upper_id if side == "Buy" else st.lower_id
    assert ad.modified == ([(f"{oid}-sl", "Stop", want_sl)] if want_sl != sl else []) + \
                          ([(f"{oid}-tp", "Limit", want_tp)] if want_tp != tp else [])
    moved = events(tmp_path, "brackets_moved")[0]
    assert (moved["fill"], moved["sl"], moved["tp"]) == (want_fill, want_sl, want_tp)
    assert bool(ad.modified) == (move or rr is not None)               # absolute levels: nothing to move


def test_a_modify_the_broker_refuses_leaves_the_levels_that_rest_there(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ads["a1"].fail_modify = True
    go(eng, leg(move=True))
    st = rnd(eng)
    fill_entry(eng, ads["a1"], st, 101.0)
    assert (st.status, st.sl_px, st.tp_px) == ("live", 95.0, 110.0)
    moved = events(tmp_path, "brackets_moved")[0]
    assert moved["moved"] is False and "modify rejected by test" in moved["error"] and moved["sl"] == 95.0


def test_three_rounds_in_a_day_then_the_limit(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    first = trade(eng, ad, exit_px=110.0, by="tp")
    second = trade(eng, ad, exit_px=95.0, by="sl")
    third = trade(eng, ad, exit_px=110.0, by="tp")
    assert list(eng.states) == [f"{LAB}@a1#1", f"{LAB}@a1#2", f"{LAB}@a1"]       # I-3: the open round is last
    assert [eng.states[k] for k in eng.states] == [first, second, third]
    # what kill_strategy (engine.py) and the chart's bot view (trading.py) build: the open round wins
    assert {st.account: st for st in eng.day_states(LAB)} == {"a1": third}
    assert [(r["round"], r["exit_reason"], r["pnl"]) for r in eng.lab_rounds(LAB)] == \
        [(1, "tp", 200.0), (2, "sl", -100.0), (3, "tp", 200.0)]
    assert [e["round"] for e in events(tmp_path, "lab_round")] == [1, 2, 3]
    assert len(ad.brackets) == 3 and eng.book("a1").closes == 3
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": None, "reason": "Daily limit reached (3 trades)."}
    assert len(ad.brackets) == 3 and list(eng.states)[-1] == f"{LAB}@a1" and rnd(eng) is third
    assert eng.day_status(LAB) == "done"


def test_day_status_ignores_archived_rounds(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    ad.reject = "OSO rejected (no orderId returned)"
    go(eng, leg())
    assert rnd(eng).status == "error" and eng.day_status(LAB) == "error"
    ad.reject = None
    go(eng, leg())                                                    # round 1 (error, clean) is archived
    assert [s.status for s in eng.day_states(LAB)] == ["error", "placed"]
    assert eng.day_status(LAB) == "placed"                            # the open round, not the archived error


def test_two_accounts_fill_at_their_own_prices(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"), qty=2)
    out = go(eng, leg(rr=2.0, tp=110.0), {"a1": 1, "a2": 2})
    assert {a: r["round"] for a, r in out["accounts"].items()} == {"a1": 1, "a2": 1}
    fill_entry(eng, ads["a1"], rnd(eng, "a1"), 100.25)
    fill_entry(eng, ads["a2"], rnd(eng, "a2"), 101.0)
    assert (rnd(eng, "a1").qty, rnd(eng, "a1").entry_fill, rnd(eng, "a1").tp_px) == (1, 100.25, 110.75)
    assert (rnd(eng, "a2").qty, rnd(eng, "a2").entry_fill, rnd(eng, "a2").tp_px) == (2, 101.0, 113.0)
    fill_exit(eng, ads["a1"], rnd(eng, "a1"), 110.75, "tp")
    assert (rnd(eng, "a1").status, rnd(eng, "a1").pnl, rnd(eng, "a2").status) == ("done", 210.0, "live")
    assert eng.day_status(LAB) == "live" and eng.lab_open(LAB) == ["a1", "a2"]   # a1: not checked yet
    tick(eng)
    assert eng.lab_open(LAB) == ["a2"]


def test_one_position_at_a_time(tmp_path):
    eng, ads, _ = mk(tmp_path)
    go(eng, leg())
    for _ in range(2):                                                # placed, then live
        out = go(eng, leg(iid=2))
        assert out["accounts"]["a1"] == {"ok": False, "round": None, "reason": "One position at a time."}
        if rnd(eng).status == "placed":
            fill_entry(eng, ads["a1"], rnd(eng), 100.0)
    assert len(ads["a1"].brackets) == 1 and list(eng.states) == [f"{LAB}@a1"]


def test_a_finished_round_whose_orders_are_not_checked_yet_blocks_the_next(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0)
    fill_exit(eng, ad, st, 110.0, "tp")                               # done, and no clock tick yet
    out = go(eng, leg(iid=2))
    assert out["accounts"]["a1"]["reason"] == "The Desk cannot check the last trade's orders."
    assert len(ad.brackets) == 1 and rnd(eng) is st
    tick(eng)
    assert go(eng, leg(iid=2))["accounts"]["a1"] == {"ok": True, "round": 2, "reason": None}


def test_a_rejected_entry_sits_the_trade_out_and_the_next_one_goes(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"))
    ads["a1"].reject = "OSO rejected (no orderId returned)"
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": 1,
                                     "reason": "The broker refused it: OSO rejected (no orderId returned)"}
    assert out["accounts"]["a2"]["ok"] is True
    st = rnd(eng, "a1")
    assert (st.status, st.upper_id) == ("error", None) and rows(eng, account="a1")[0]["clean"] is True
    assert eng.lab_open(LAB) == ["a2"]
    ads["a1"].reject = None
    assert go(eng, leg(iid=2), {"a1": 1})["accounts"]["a1"] == {"ok": True, "round": 2, "reason": None}


@pytest.mark.parametrize("words", ["OSO failed: timeout", "paper book unreachable: ReadTimeout"])
def test_a_refusal_whose_outcome_is_unknown_blocks_the_account(tmp_path, words):
    """The broker's answer never came: the order may be working under an id nobody has."""
    eng, ads, _ = mk(tmp_path)
    ads["a1"].reject = words
    assert go(eng, leg())["accounts"]["a1"]["ok"] is False
    ads["a1"].reject = None
    tick(eng)
    assert go(eng, leg(iid=2))["accounts"]["a1"]["reason"] == "The Desk cannot check the last trade's orders."
    assert rows(eng)[0]["clean"] is False and eng.lab_open(LAB) == ["a1"]
    assert events(tmp_path, "lab_check")[0]["strategy"] == LAB


def test_a_pair_with_one_leg_rejected_is_never_clean(tmp_path):
    """Ruling Q-A: the survivor is cancelled, but its id is not kept: its end cannot be checked."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    ad.fail_leg = "Sell"
    out = go(eng, pair())
    assert out["accounts"]["a1"] == {"ok": False, "round": 1, "reason": "The broker refused it: rejected by test"}
    st = rnd(eng)
    assert (st.status, st.upper_id, st.lower_id) == ("error", None, None) and ad.cancelled == ["a1-101"]
    ad.fail_leg = None
    for _ in range(3):
        tick(eng)
    assert go(eng, leg(iid=9))["accounts"]["a1"] == \
        {"ok": False, "round": None, "reason": "The Desk cannot check the last trade's orders."}
    assert len(ad.brackets) == 1
    (r,) = eng.lab_rounds(LAB)
    assert (r["status"], r["clean"], r["why"]) == ("error", False, "The Desk cannot check the last trade's orders.")
    (chk,) = events(tmp_path, "lab_check")
    assert (chk["strategy"], chk["account"], chk["round"]) == (LAB, "a1", 1) and "leg" in chk["reason"]
    assert eng.lab_open(LAB) == ["a1"]


def test_a_fill_that_beats_the_ack_is_held_and_replayed(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    real = ad.place_bracket

    async def filled_first(req):
        r = await real(req)
        ad.order_status[r.order_id], ad.net = "Filled", 1
        await eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Buy", qty=1, price=100.5,
                                    raw={"orderId": r.order_id}))
        return r

    ad.place_bracket = filled_first
    assert go(eng, leg())["accounts"]["a1"]["ok"] is True
    assert (rnd(eng).status, rnd(eng).entry_fill) == ("live", 100.5)


def test_a_partial_fill_cancels_the_sibling_at_once_and_moves_the_brackets_when_whole(tmp_path):
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, [leg(3, "Buy", px=110.0, sl=105.0, tp=120.0, move=True), leg(4, "Sell", px=90.0, sl=95.0, tp=80.0)],
       {"a1": 2})
    st = rnd(eng)
    fill_entry(eng, ad, st, 110.0, qty=1)
    assert (st.status, st.entry_qty) == ("live", 1) and ad.cancelled == [st.lower_id] and ad.modified == []
    fill_entry(eng, ad, st, 111.0, qty=1)                             # the average fill is 110.5
    assert (st.entry_qty, st.entry_fill, st.sl_px, st.tp_px) == (2, 110.5, 105.5, 120.5)
    assert ad.modified == [("a1-101-sl", "Stop", 105.5), ("a1-101-tp", "Limit", 120.5)]
    run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=120.5, raw={"orderId": "a1-101-tp"})))
    assert st.status == "live" and events(tmp_path, "exit_part")
    ad.net = 1
    fill_exit(eng, ad, st, 120.5, "tp")
    assert (st.status, st.exit_qty, st.exit_reason, st.pnl) == ("done", 2, "tp", 400.0)
    tick(eng)
    assert rows(eng)[0]["clean"] is True and rows(eng)[0]["cancelled"] == ["Sell"]


def test_both_legs_filled_is_the_emergency_and_never_clean(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    st = rnd(eng)
    fill_entry(eng, ad, st, 110.0, side="Buy")
    ad.stuck.add(st.lower_id)                                         # the sibling's cancel did not take
    ad.order_status[st.lower_id] = "Working"
    fill_entry(eng, ad, st, 90.0, side="Sell")
    assert (st.status, st.exit_reason) == ("error", "both_filled")
    assert events(tmp_path, "both_filled_emergency")
    for _ in range(3):
        tick(eng)
    assert go(eng, leg(iid=9))["accounts"]["a1"]["reason"] == "The Desk cannot check the last trade's orders."
    assert rows(eng)[0]["clean"] is False and eng.day_status(LAB) == "error"


# ------------------------------------------------------------------------------------------------ who sits out
def test_a_stopped_or_unconnected_account_sits_out_and_uses_no_round(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2", "a3"))
    eng.book("a1").locked = "day_lock"
    ads["a2"]._connected = False
    out = go(eng, leg())
    assert out["accounts"] == {"a1": {"ok": False, "round": None, "reason": "This account is stopped for the day."},
                               "a2": {"ok": False, "round": None, "reason": "The account is not connected."},
                               "a3": {"ok": True, "round": 1, "reason": None}}
    assert list(eng.states) == [f"{LAB}@a3"]
    assert [(e["account"], e["reason"]) for e in events(tmp_path, "place_skipped")] == \
        [("a1", "This account is stopped for the day."), ("a2", "The account is not connected.")]
    eng.book("a1").locked = None
    assert go(eng, leg(), {"a1": 1})["accounts"]["a1"] == {"ok": True, "round": 1, "reason": None}


def test_an_account_the_strategy_is_not_booked_on_is_never_traded(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"))
    eng.cfg.book[LAB] = [{"account": "a1", "qty": 1}]
    out = go(eng, leg(), {"a1": 1, "a2": 1, "a1#1": 1, "zz": 1})
    assert [a for a, r in out["accounts"].items() if r["ok"]] == ["a1"]
    assert ads["a2"].brackets == [] and list(eng.states) == [f"{LAB}@a1"]
    assert go(eng, leg(), {"a1": 0})["accounts"]["a1"]["reason"] == "The Desk cannot check this order."


def test_one_strategy_per_market_per_account(tmp_path):
    """Design A5, at placement: another strategy booked in this market on the account -> it sits the trade out."""
    other = StrategyCfg(symbol="MNQ", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0, enabled=True)
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"), extra={"mnq930": other},
                     book={"mnq930": [{"account": "a1", "qty": 1}]})
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": None, "reason": "Another strategy trades MNQ on this account."}
    assert out["accounts"]["a2"]["ok"] is True and ads["a1"].brackets == []
    eng.cfg.strategies["mnq930"].symbol = "ES"                        # another market: no conflict
    assert go(eng, leg(), {"a1": 1})["accounts"]["a1"]["ok"] is True


def test_an_account_with_a_daily_take_rule_sits_out(tmp_path):
    """Ruling Q-B: a live Lab round would switch the take watcher off for that account (check_takes needs a price
    for every live state). So the two never share an account."""
    take = tl.strat(day_take=1500.0, symbol="ES")                    # another market: only the take rule is in the way
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"), extra={"lv_atr_take": take},
                     book={"lv_atr_take": [{"account": "a1", "qty": 4}]})
    assert eng.rules_for("a1").day_take == 1500.0 and not eng.rules_for("a2").day_take
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": None,
                                     "reason": "This account has a daily take rule. A Lab strategy cannot share it."}
    assert out["accounts"]["a2"] == {"ok": True, "round": 1, "reason": None}
    assert ads["a1"].brackets == [] and list(eng.states) == [f"{LAB}@a2"]
    eng.cfg.strategies["lv_atr_take"] = tl.strat(day_take=0.0, target_take=True, symbol="ES")
    assert go(eng, leg(), {"a1": 1})["accounts"]["a1"]["ok"] is False
    eng.cfg.strategies["lv_atr_take"] = tl.strat(day_take=0.0, target_take=False, symbol="ES")     # no take rule: it trades
    assert go(eng, leg(), {"a1": 1})["accounts"]["a1"] == {"ok": True, "round": 1, "reason": None}


# ------------------------------------------------------------------------------------------------ lab_cancel
def test_cancel_ends_an_unfilled_round_and_the_next_one_may_start(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(iid=7))
    st = rnd(eng)
    out = run(eng.lab_cancel(LAB, 7))
    assert out == {"a1": {"ok": True, "state": "cancelled",
                          "actions": ["cancel entry a1-101: ok", "cancel a1-101-sl: ok", "cancel a1-101-tp: ok"]}}
    assert ad.cancelled == ["a1-101", "a1-101-sl", "a1-101-tp"] and ad.orders == []      # no market order, ever
    assert (st.status, st.exit_reason) == ("done", "cancelled")
    (ev,) = events(tmp_path, "lab_cancelled")
    assert (ev["strategy"], ev["account"], ev["round"], ev["sides"], ev["why"], ev["ended"]) == \
        (LAB, "a1", 1, ["Buy"], "cancel", True)
    assert rows(eng)[0]["cancelled"] == ["Buy"] and rows(eng)[0]["clean"] is False
    tick(eng)
    assert rows(eng)[0]["clean"] is True
    assert go(eng, leg(iid=8))["accounts"]["a1"] == {"ok": True, "round": 2, "reason": None}


def test_cancel_of_an_order_the_round_does_not_hold_does_nothing(tmp_path):
    eng, ads, _ = mk(tmp_path)
    assert run(eng.lab_cancel(LAB, 7)) == {}                              # no round today
    go(eng, leg(iid=7))
    assert run(eng.lab_cancel(LAB, 99)) == {"a1": {"ok": True, "state": "none", "actions": []}}
    assert run(eng.lab_cancel("nq930")) == {} and run(eng.lab_cancel("lab_nope")) == {}
    assert rnd(eng).status == "placed" and ads["a1"].cancelled == []


def test_cancel_of_one_leg_of_a_pair_leaves_the_other_working(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    st = rnd(eng)
    out = run(eng.lab_cancel(LAB, 4))                                     # the sell stop
    assert out["a1"]["state"] == "cancelled" and ad.cancelled == [st.lower_id]
    assert st.status == "placed" and rows(eng)[0]["cancelled"] == ["Sell"]
    assert events(tmp_path, "lab_cancelled")[0]["ended"] is False
    fill_entry(eng, ad, st, 110.0, side="Buy")                            # the buy stop still fills
    assert (st.status, st.entry_side) == ("live", "Buy")
    assert run(eng.lab_cancel(LAB)) == {"a1": {"ok": True, "state": "filled", "actions": []}}
    assert st.status == "live" and ad.orders == []                        # a cancel never closes a position


def test_cancel_of_both_legs_ends_the_round(tmp_path):
    eng, ads, _ = mk(tmp_path)
    go(eng, pair())
    out = run(eng.lab_cancel(LAB, why="runner_down"))
    assert out["a1"]["state"] == "cancelled" and (rnd(eng).status, rnd(eng).exit_reason) == ("done", "cancelled")
    assert set(ads["a1"].cancelled[:2]) == {"a1-101", "a1-102"}
    assert events(tmp_path, "lab_cancelled")[0]["why"] == "runner_down"


def test_a_fill_that_beat_the_cancel_leaves_the_round_and_its_stop_alone(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(iid=7))
    st = rnd(eng)
    ad.order_status[st.upper_id], ad.filled[st.upper_id], ad.net = "Filled", 1, 1     # filled; its push is on the way
    out = run(eng.lab_cancel(LAB, 7))
    assert out["a1"]["ok"] is True and out["a1"]["state"] == "filled"
    assert ad.cancelled == ["a1-101"] and st.status == "placed"           # the stop and target were never touched
    (ev,) = events(tmp_path, "lab_cancel_raced_fill")
    assert (ev["account"], ev["iid"], ev["order_id"]) == ("a1", 7, "a1-101")
    assert not events(tmp_path, "lab_cancelled")
    run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Buy", qty=1, price=100.25,
                              raw={"orderId": st.upper_id})))
    assert (st.status, st.entry_fill) == ("live", 100.25)                 # the position is live with its broker stop


def test_a_cancel_the_broker_does_not_confirm_blocks_the_next_round(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(iid=7))
    ad.stuck.add("a1-101")                                                # accepted, and still working 3 s later
    out = run(eng.lab_cancel(LAB, 7))
    assert out["a1"]["ok"] is False and out["a1"]["state"] == "working"
    assert rnd(eng).status == "placed" and ad.cancelled == ["a1-101"]
    (chk,) = events(tmp_path, "lab_check")
    assert chk["round"] == 1 and "a1-101" in chk["reason"]
    assert go(eng, leg(iid=8))["accounts"]["a1"]["reason"] == "One position at a time."
    assert len(ad.brackets) == 1 and eng.lab_open(LAB) == ["a1"]
    ad.stuck.clear()                                                      # the runner asks again: now it ends
    assert run(eng.lab_cancel(LAB, 7))["a1"]["state"] == "cancelled"


@pytest.mark.parametrize("net,error", [(2, False), (0, True)])
def test_cancel_never_takes_a_stop_from_an_account_that_may_hold_a_position(tmp_path, net, error):
    """A fill push can be missed: with a position in that market on the account (or one that cannot be read) the
    cancelled entry's stop and target are left alone, as the kill does."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(iid=7))
    ad.net, ad.net_error = net, error
    out = run(eng.lab_cancel(LAB, 7))
    assert out["a1"]["state"] == "cancelled" and ad.cancelled == ["a1-101"]
    assert "left alone" in out["a1"]["actions"][-1] and rnd(eng).status == "done"


def test_cancel_waits_for_an_entry_whose_ack_is_still_out(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    real = ad.place_bracket

    async def slow(req):
        await asyncio.sleep(0.01)
        return await real(req)

    ad.place_bracket = slow

    async def poll(s):
        await asyncio.sleep(0.002)

    eng._kill_sleep = poll

    async def cancel_soon():
        await asyncio.sleep(0.001)                                        # the round exists, its ack does not
        assert rnd(eng).status == "placing"
        return await eng.lab_cancel(LAB)

    async def both():
        return await asyncio.gather(eng.lab_enter(LAB, [leg(iid=7)], {"a1": 1}, max_rounds=3), cancel_soon())

    entered, cancelled = run(both())
    assert entered["accounts"]["a1"]["ok"] is True
    assert cancelled["a1"]["state"] == "cancelled" and rnd(eng).status == "done"


# ------------------------------------------------------------------------------------------------ the capped flatten
def calls_of(ad):
    """The adapter's broker calls in order: ("cancel", id) / ("market", side, qty, text)."""
    calls = []
    cancel, place = ad.cancel_order_by_id, ad.place_order

    async def c(i):
        calls.append(("cancel", str(i)))
        return await cancel(i)

    async def p(req):
        calls.append(("market", req.side, req.qty, req.text))
        return await place(req)

    ad.cancel_order_by_id, ad.place_order = c, p
    return calls


def live_round(eng, ad, a="a1", legs=None, fill=100.0, qty=1):
    go(eng, legs or leg(), {a: qty})
    st = rnd(eng, a)
    fill_entry(eng, ad, st, fill)
    assert st.status == "live"
    return st


def later(clock, seconds):
    import datetime as dt
    clock.dt += dt.timedelta(seconds=seconds)


def never_account_wide(*ads):
    assert all(ad.cancel_all_calls == 0 and ad.flatten_calls == 0 for ad in ads)


def test_the_flatten_sells_its_own_position_only_with_a_manual_one_in_the_same_market(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.net = 3                                                        # its 1, and 2 the owner bought by hand
    calls = calls_of(ad)
    out = run(eng.lab_flatten(LAB, reason="time"))
    assert out == {"a1": {"ok": True, "sold": 1,
                          "actions": ["market Sell 1: ok", "cancel a1-101-sl: ok", "cancel a1-101-tp: ok"]}}
    assert calls == [("market", "Sell", 1, "homebase:lab-flat"), ("cancel", "a1-101-sl"), ("cancel", "a1-101-tp")]
    assert st.status == "live" and rows(eng)[0]["closing"] == "time"    # live until its exit fill arrives
    fill_exit(eng, ad, st, 104.0, by="market")
    assert (st.status, st.exit_reason, st.exit_fill, st.pnl, ad.net) == ("done", "time", 104.0, 80.0, 2)
    (ev,) = events(tmp_path, "lab_flatten")
    assert ev["strategy"] == LAB and ev["reason"] == "time" and ev["results"]["a1"]["sold"] == 1
    assert events(tmp_path, "exit_fill")[0]["reason"] == "time"
    never_account_wide(ad)


@pytest.mark.parametrize("how", ["other_side", "unreadable"])
def test_a_net_it_cannot_use_sells_nothing_and_leaves_the_stops(tmp_path, how):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    if how == "other_side":
        ad.net = -2
    else:
        ad.net_error = True
    calls = calls_of(ad)
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is False and out["sold"] == 0 and "check it" in out["actions"][-1]
    assert calls == [] and st.status == "live" and rows(eng)[0]["closing"] is None
    ad.net, ad.net_error = 1, False                                   # a later try, now readable: it closes
    assert run(eng.lab_flatten(LAB))["a1"]["sold"] == 1


def test_an_entry_that_is_neither_cancelled_nor_filled_stops_the_flatten(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    st = rnd(eng)
    ad.stuck.add(st.upper_id)
    ad.net = 1                                                        # someone holds 1: it is not attributed
    calls = calls_of(ad)
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is False and "check it" in out["actions"][-1]
    assert calls == [("cancel", "a1-101")] and st.status == "placed"


def test_the_flatten_of_an_unfilled_round_cancels_it_and_sells_nothing(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    st = rnd(eng)
    calls = calls_of(ad)
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is True and out["sold"] == 0
    assert calls[:2] == [("cancel", "a1-101"), ("cancel", "a1-102")] and not [c for c in calls if c[0] == "market"]
    assert (st.status, st.exit_reason) == ("done", "cancelled") and events(tmp_path, "lab_cancelled")[0]["ended"]


def test_an_entry_that_filled_unseen_is_sold_capped(tmp_path):
    """Placed, the fill push never came: the entry reads Filled at the flatten -> its quantity, and only that."""
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 2})
    st = rnd(eng)
    ad.order_status[st.upper_id], ad.filled[st.upper_id], ad.net = "Filled", 2, 5
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["sold"] == 2 and "market Sell 2: ok" in out["actions"]
    assert (st.status, st.entry_side) == ("live", "Buy")
    assert [(o.side, o.qty) for o in ad.orders] == [("Sell", 2)]


def test_a_part_filled_entry_is_cancelled_and_only_what_filled_is_sold(tmp_path):
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 2})
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0, qty=1)                             # 1 of 2 in, the rest still working
    assert (st.status, st.entry_qty, ad.order_status[st.upper_id]) == ("live", 1, "Working")
    calls = calls_of(ad)
    out = run(eng.lab_flatten(LAB))["a1"]
    assert calls[:2] == [("cancel", "a1-101"), ("market", "Sell", 1, "homebase:lab-flat")] and out["sold"] == 1
    fill_exit(eng, ad, st, 101.0, by="market")
    assert (st.status, st.exit_qty, st.pnl) == ("done", 1, 20.0)


def test_a_refused_close_is_never_sent_again(tmp_path):
    """Ruling Q-C: one market order per round, ever."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.fail_market = True
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is False and out["sold"] == 0
    assert out["actions"] == ["market Sell 1: market rejected by test",
                              "check it — the close order was not confirmed; its stop is still working"]
    assert st.status == "live" and ad.cancelled == []                 # its stop and target still work
    (r,) = eng.lab_rounds(LAB)
    assert r["why"] == "Check it: the close order was not confirmed. Its stop is still working." and not r["clean"]
    assert len(events(tmp_path, "lab_check")) == 1
    ad.fail_market = False
    for _ in range(3):                                                # a second "Flatten & turn off", and a third
        later(clock, 10)
        again = run(eng.lab_flatten(LAB))["a1"]
        assert again["ok"] is False and "check it" in again["actions"][-1]
    assert len(ad.orders) == 1 and ad.cancelled == [] and st.status == "live"
    assert len(events(tmp_path, "lab_check")) == 1                    # said once
    assert eng.lab_open(LAB) == ["a1"]


def test_a_net_that_reads_zero_on_a_retry_finishes_the_round(tmp_path):
    """Ruling Q-C: the refused close did go out after all (or the stop was hit): the retry reads flat and ends it."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.fail_market = True
    run(eng.lab_flatten(LAB, reason="time"))
    ad.net = 0
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is True and len(ad.orders) == 1
    assert (st.status, st.exit_reason) == ("done", "time")
    assert ad.cancelled == ["a1-101-sl", "a1-101-tp"]                 # flat: nothing left to protect
    assert events(tmp_path, "lab_exit_unconfirmed")[0]["round"] == 1
    tick(eng)
    assert rows(eng)[0]["clean"] is False                             # fix round 1, S6: no exit fill, never clean
    assert go(eng, leg(iid=2))["accounts"]["a1"]["ok"] is False


def test_an_accepted_close_whose_fill_never_arrives_is_ended_after_five_seconds(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    assert run(eng.lab_flatten(LAB))["a1"]["sold"] == 1
    ad.net = 0                                                        # it filled; the push is lost
    later(clock, 2)
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is True and st.status == "live" and len(ad.orders) == 1      # still waiting, nothing re-sent
    later(clock, 4)
    assert run(eng.lab_flatten(LAB))["a1"]["ok"] is True
    assert (st.status, st.exit_reason, st.pnl) == ("done", "flat", None) and len(ad.orders) == 1
    assert events(tmp_path, "lab_exit_unconfirmed")


def test_an_accepted_close_that_does_not_fill_goes_to_check_it_and_is_not_sent_again(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    run(eng.lab_flatten(LAB))                                         # accepted, and the market is halted
    later(clock, 6)
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is False and "check it" in out["actions"][-1] and len(ad.orders) == 1
    assert rows(eng)[0]["why"] == "Check it: the close order was not confirmed. Its stop is still working."
    fill_exit(eng, ad, st, 103.0, by="market")                        # it fills after all: the fills confirm it
    assert (st.status, st.exit_reason, st.pnl) == ("done", "flat", 60.0)
    tick(eng)
    assert rows(eng)[0]["clean"] is True and rows(eng)[0]["why"] is None


def test_a_position_that_is_already_gone_is_not_sold(tmp_path):
    """The stop was hit and its push never came: the account reads flat -> no order, and the round ends."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.net = 0
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out == {"ok": True, "sold": 0,
                   "actions": ["the account is already flat", "cancel a1-101-sl: ok", "cancel a1-101-tp: ok"]}
    assert st.status == "live" and ad.orders == []
    ad.net = 2                                                        # the owner buys by hand afterwards
    later(clock, 6)
    assert run(eng.lab_flatten(LAB))["a1"]["ok"] is True
    assert (st.status, st.exit_reason) == ("done", "exit") and ad.orders == []     # never sold: not its position


def test_flatten_strategy_closes_a_lab_strategy_with_the_capped_flatten(tmp_path):
    """Hook 5: the Desk's "Flatten & turn off" -> its own position on every account, never the account's net."""
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"))
    go(eng, leg())
    for a in ("a1", "a2"):
        fill_entry(eng, ads[a], rnd(eng, a), 100.0)
    ads["a1"].net = 4
    out = run(eng.flatten_strategy(LAB))
    assert out == {a: ["market Sell 1: ok", f"cancel {a}-101-sl: ok", f"cancel {a}-101-tp: ok"] for a in ("a1", "a2")}
    assert [(o.side, o.qty, o.text) for o in ads["a1"].orders] == [("Sell", 1, "homebase:lab-flat")]
    (ev,) = events(tmp_path, "manual_flatten")
    assert ev["strategy"] == LAB and set(ev["results"]) == {"a1", "a2"}
    fill_exit(eng, ads["a2"], rnd(eng, "a2"), 99.0, by="market")
    assert rnd(eng, "a2").exit_reason == "manual_flat"
    never_account_wide(*ads.values())


def test_two_flattens_at_once_sell_once(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    place = ad.place_order

    async def slow(req):
        await asyncio.sleep(0.01)
        return await place(req)

    ad.place_order = slow

    async def both():
        return await asyncio.gather(eng.lab_flatten(LAB), eng.lab_flatten(LAB), eng.flatten_strategy(LAB))

    run(both())
    assert [(o.side, o.qty) for o in ad.orders] == [("Sell", 1)]


def test_a_flatten_with_no_round_or_a_finished_one_does_nothing(tmp_path):
    eng, ads, _ = mk(tmp_path)
    assert run(eng.lab_flatten(LAB)) == {} and run(eng.lab_flatten("nq930")) == {}
    st = trade(eng, ads["a1"])
    n = len(ads["a1"].cancelled)
    assert run(eng.lab_flatten(LAB)) == {"a1": {"ok": True, "sold": 0, "actions": []}}
    assert ads["a1"].orders == [] and len(ads["a1"].cancelled) == n and st.status == "done"


# ------------------------------------------------------------------------------------------------ the two Kills
def three_rounds(eng, ad):
    """Two closed, archived rounds and an open third (live)."""
    trade(eng, ad, exit_px=110.0)
    trade(eng, ad, exit_px=95.0, by="sl")
    return live_round(eng, ad)


def test_the_strategy_kill_mid_round_acts_on_the_open_round_only(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = three_rounds(eng, ad)
    assert list(eng.states) == [f"{LAB}@a1#1", f"{LAB}@a1#2", f"{LAB}@a1"]
    ad.net = 3                                                        # its 1 and 2 by hand
    calls = calls_of(ad)
    out = run(eng.kill_strategy(LAB))
    assert out["a1"]["ok"] is True and out["a1"]["acted"] is True
    assert calls == [("cancel", "a1-103"), ("market", "Sell", 1, "homebase:kill"),
                     ("cancel", "a1-103-sl"), ("cancel", "a1-103-tp")]
    assert (st.status, st.exit_reason) == ("done", "killed")
    assert [s.exit_reason for s in list(eng.states.values())[:2]] == ["tp", "sl"]     # the archive is untouched
    assert go(eng, leg(iid=9))["accounts"]["a1"]["reason"] == "Killed today."
    never_account_wide(ad)


def test_the_global_kill_sends_one_market_out_with_three_closed_rounds(tmp_path):
    """Hook 6. Without it every closed round would read the net and sell it again. Ruling Q18: the global Kill
    stays account-wide (the account's whole net in the market), also for a Lab round."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    for px in (110.0, 110.0, 110.0):
        trade(eng, ad, exit_px=px)
    assert [s.status for s in eng.states.values()] == ["done", "done", "done"] and len(eng.states) == 3
    ad.net = 2                                                        # a position in NQ on the account
    out = run(eng.flatten_today())
    assert list(out) == [f"{LAB}@a1"]
    assert [(o.side, o.qty, o.text) for o in ad.orders] == [("Sell", 2, "homebase:flat")]


# ------------------------------------------------------------------------------------------------ the clock
def test_the_clock_finds_an_entry_whose_fill_push_was_missed(tmp_path):
    """Also the fill that beat a cancel: the position goes live with its broker stop at the next tick."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    st = rnd(eng)
    ad.order_status[st.upper_id], ad.filled[st.upper_id], ad.net = "Filled", 1, 1
    assert run(eng.lab_cancel(LAB, 3))["a1"]["state"] == "filled" and st.status == "placed"
    tick(eng)
    assert (st.status, st.entry_side) == ("live", "Buy") and st.lower_id in ad.cancelled
    assert events(tmp_path, "entry_found_by_check")[0]["strategy"] == LAB
    assert not [c for c in ad.cancelled if c.endswith(("-sl", "-tp")) and c.startswith(st.upper_id)]


def test_the_flat_time_closes_a_live_round_with_no_runner(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.net = 3                                                        # 2 of them are the owner's
    clock.set_et(15, 54)
    tick(eng)
    assert ad.orders == [] and st.status == "live"                    # not yet
    clock.set_et(15, 55)
    tick(eng)
    assert [(o.side, o.qty, o.text) for o in ad.orders] == [("Sell", 1, "homebase:lab-flat")]
    (ev,) = events(tmp_path, "clock_flat")
    assert (ev["strategy"], ev["account"], ev["actions"][0]) == (LAB, "a1", "market Sell 1: ok")
    fill_exit(eng, ad, st, 102.0, by="market")
    assert (st.status, st.exit_reason, st.pnl) == ("done", "flat", 40.0)
    for _ in range(3):
        later(clock, 6)
        tick(eng)
    assert len(ad.orders) == 1 and len(events(tmp_path, "clock_flat")) == 1 and rows(eng)[0]["clean"] is True
    never_account_wide(ad)


def test_the_flat_time_cancels_an_unfilled_round(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    clock.set_et(15, 55)
    tick(eng)
    assert (rnd(eng).status, rnd(eng).exit_reason) == ("done", "cancelled") and ad.orders == []
    assert events(tmp_path, "clock_flat") and events(tmp_path, "lab_cancelled")[0]["why"] == "flat"
    tick(eng)
    assert rows(eng)[0]["clean"] is True


def test_a_close_refused_at_the_flat_time_is_not_sent_again_on_the_next_ticks(tmp_path):
    """Ruling Q-C, on the clock."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.fail_market = True
    clock.set_et(15, 55)
    tick(eng)
    ad.fail_market = False
    for _ in range(5):
        later(clock, 31)
        tick(eng)
    assert len(ad.orders) == 1 and ad.cancelled == [] and st.status == "live"      # its stop still works
    failed = events(tmp_path, "clock_flat_failed")
    assert failed[0]["actions"] == ["market Sell 1: market rejected by test",
                                    "check it — the close order was not confirmed; its stop is still working"]
    assert len(failed) == 2 and not events(tmp_path, "clock_flat")    # the refusal, then one "still check it"
    assert rows(eng)[0]["why"] == "Check it: the close order was not confirmed. Its stop is still working."
    ad.net = 0                                                        # the stop is hit; nobody tells the engine
    later(clock, 31)
    tick(eng)
    assert (st.status, st.exit_reason) == ("done", "flat") and len(ad.orders) == 1
    tick(eng)
    assert rows(eng)[0]["clean"] is False                             # fix round 1, S6


def test_the_flat_time_retry_waits_five_seconds_and_sells_once_it_can_read(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.net_error = True
    clock.set_et(15, 55)
    before = ad.net_reads                                             # the entry's own position read (C2)
    run(eng.clock_tick())
    run(eng.clock_tick())                                             # inside the 5 s: no second read
    assert ad.net_reads == before + 1 and ad.orders == []
    assert len(events(tmp_path, "clock_flat_failed")) == 1
    ad.net_error = False
    tick(eng)
    assert [(o.side, o.qty) for o in ad.orders] == [("Sell", 1)] and len(events(tmp_path, "clock_flat")) == 1


def test_the_clock_never_stands_three_seconds_on_an_entry_the_broker_does_not_end(tmp_path):
    """A flatten asked for by hand polls the entries for 3 s (12 reads apart). The clock is its own retry loop
    (every 5 s) and every strategy's tick waits on it: there the wait is half a second at most."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    ad.stuck.add(rnd(eng).upper_id)
    slept = []

    async def counted(s):
        slept.append(s)
        await asyncio.sleep(0)

    eng._kill_sleep = counted
    clock.set_et(15, 55)
    tick(eng)
    assert len(slept) == engine_mod.LAB_CLOCK_POLLS == 2 and rnd(eng).status == "placed" and ad.orders == []
    assert "check it" in events(tmp_path, "clock_flat_failed")[0]["actions"][-1]
    slept.clear()
    assert run(eng.lab_flatten(LAB))["a1"]["ok"] is False and len(slept) == engine_mod.KILL_POLL_N
    ad.stuck.clear()
    slept.clear()
    tick(eng)                                                         # the next retry: it is cancelled now
    assert (rnd(eng).status, rnd(eng).exit_reason, slept) == ("done", "cancelled", [])


def test_a_manual_flatten_whose_fill_is_lost_is_ended_by_the_clock_before_the_flat_time(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    run(eng.flatten_strategy(LAB))
    ad.net = 0
    later(clock, 6)
    tick(eng)
    assert (st.status, st.exit_reason) == ("done", "manual_flat") and len(ad.orders) == 1
    assert events(tmp_path, "lab_exit_unconfirmed")


def test_the_clock_never_waits_for_the_kill_lock(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    clock.set_et(15, 55)

    async def held():
        async with eng._kill_lock(LAB):                               # a kill or a flatten is running
            await asyncio.wait_for(eng.clock_tick(), 1.0)
            assert ad.orders == []
        eng._retry_at.clear()
        await eng.clock_tick()

    run(held())
    assert [(o.side, o.qty) for o in ad.orders] == [("Sell", 1)]


def test_a_killed_check_it_round_is_not_flattened_and_its_entries_are_cancelled_once(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    st = rnd(eng)
    ad.stuck.add(st.upper_id)
    out = run(eng.kill_strategy(LAB))
    assert out["a1"]["ok"] is False and st.status == "placed" and eng.needs_check(st)
    n = len(ad.cancelled)
    clock.set_et(15, 55)
    tick(eng)
    tick(eng)
    assert ad.orders == [] and st.status == "placed"
    assert ad.cancelled[n:] == [st.upper_id] and len(events(tmp_path, "killed_run_entries_cancelled")) == 1
    assert events(tmp_path, "killed_run_needs_check")


def test_a_lab_tick_that_raises_never_stops_another_strategys_clock(tmp_path):
    es = StrategyCfg(symbol="ES", qty=1, offset_pts=2.0, sl_pts=1.0, tp_pts=3.0, enabled=True)
    eng, ads, clock = mk(tmp_path, extra={"es930": es}, book={"es930": [{"account": "a1", "qty": 1}]})
    ad = ads["a1"]
    live_round(eng, ad)
    assert run(eng.handle_alert({"strategy": "es930", "upper": 5002.0, "lower": 4998.0}))["ok"]
    other = eng._state("es930", "a1")
    run(eng.on_fill(FillEvent(account_id="a1", symbol="ESZ6", side="Buy", qty=1, price=5002.0,
                              raw={"orderId": other.upper_id})))
    assert other.status == "live"

    async def boom(*a, **kw):
        raise RuntimeError("lab broke")

    eng._lab_flatten_one = boom
    clock.set_et(15, 56)
    tick(eng)
    assert (other.status, other.exit_reason) == ("done", "flat")      # es930's own 15:55 flat still ran
    (err,) = events(tmp_path, "clock_error")
    assert (err["strategy"], err["error"]) == (LAB, "lab broke")


def test_the_clock_runs_the_both_filled_emergency_for_a_sibling_that_filled_unseen(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    st = rnd(eng)
    ad.stuck.add(st.lower_id)
    fill_entry(eng, ad, st, 110.0, side="Buy")
    ad.order_status[st.lower_id] = "Filled"                           # the sell stop filled; no push
    ad.net = 0
    tick(eng)
    assert (st.status, st.exit_reason) == ("error", "both_filled")
    assert events(tmp_path, "both_filled_emergency")[0]["found_by"] == "sibling_check"
    assert rows(eng)[0]["clean"] is False


def test_a_closed_rounds_working_entry_is_cancelled_again_until_it_ends(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    st = rnd(eng)
    run(eng.lab_cancel(LAB))
    assert st.status == "done"
    ad.order_status[st.upper_id] = "Working"                          # the broker shows it working after all
    ad.stuck.add(st.upper_id)
    n = len(ad.cancelled)
    tick(eng)
    assert ad.cancelled[n:] == [st.upper_id] and rows(eng)[0]["clean"] is False
    assert rows(eng)[0]["why"] == "The Desk cannot check the last trade's orders."
    assert go(eng, leg(iid=2))["accounts"]["a1"]["reason"] == "The Desk cannot check the last trade's orders."
    ad.stuck.clear()
    tick(eng)                                                         # cancelled again: now it takes
    tick(eng)
    assert rows(eng)[0]["clean"] is True and len(events(tmp_path, "lab_check")) == 1
    assert go(eng, leg(iid=2))["accounts"]["a1"]["ok"] is True


def test_a_closed_rounds_stop_is_never_cancelled_while_the_account_holds_a_position(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    st.status, st.exit_reason = "done", "killed"                      # ended with its stop still at the broker
    ad.net = 1
    n = len(ad.cancelled)
    for _ in range(3):
        tick(eng)
    assert ad.cancelled[n:] == [] and rows(eng)[0]["clean"] is False
    assert "left working" in events(tmp_path, "lab_check")[0]["actions"][0]
    ad.net = 0                                                        # flat: the leftovers may go
    tick(eng)
    assert ad.cancelled[n:] == ["a1-101-sl", "a1-101-tp"]
    tick(eng)
    assert rows(eng)[0]["clean"] is True


def test_an_archived_round_is_never_acted_on_again_whatever_its_orders_read(tmp_path):
    """I-4. Round 1 is closed, clean and archived; its sell stop then reads Filled (it cannot: it was read ended).
    The clock must not run the both-filled emergency -- an account-wide flatten -- on a round that is over."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    first = trade(eng, ad, entry=110.0, exit_px=120.0, legs=pair())
    live = live_round(eng, ad, legs=leg(iid=9))
    assert eng._archived(first) and not eng._archived(live)
    ad.order_status[first.lower_id] = "Filled"
    eng._lab_x(first)["cancelled"] = []
    ad.net = 1
    n = len(ad.cancelled)
    clock.set_et(15, 54)
    tick(eng)
    assert (first.status, first.exit_reason) == ("done", "tp") and ad.orders == [] and len(ad.cancelled) == n
    assert not events(tmp_path, "both_filled_emergency") and live.status == "live"


def test_an_entry_that_filled_after_its_round_was_ended_is_never_clean(tmp_path):
    """The account's day lock ends a placed round at once (engine._lock_account); the entry fills anyway."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    st = rnd(eng)
    run(eng._lock_account("a1", "day_lock", why="test"))
    assert (st.status, st.exit_reason) == ("done", "day_lock")
    ad.order_status[st.upper_id], ad.filled[st.upper_id] = "Filled", 1
    for _ in range(3):
        tick(eng)
    assert rows(eng)[0]["clean"] is False and "never held" in events(tmp_path, "lab_check")[0]["reason"]
    assert eng.lab_open(LAB) == ["a1"]


# ------------------------------------------------------------------------------------------------ disk and restarts
def restart(eng, tmp_path):
    """A new engine on the same folder, the same config, clock and adapters: what a desk restart keeps."""
    return quick(Engine(eng.cfg, eng.adapters, now_fn=eng._now, root=tmp_path))


def test_construction_never_reads_the_lab_file(tmp_path):
    clock = Clock()
    (tmp_path / f"labday-{clock().astimezone(engine_mod.ET).date().isoformat()}.json").mkdir()   # not even a file
    eng, ads, _ = mk(tmp_path)
    assert "_lab" not in eng.__dict__                                 # read at the first Lab call, never before
    assert eng.lab_rounds(LAB) == [] and eng.lab_open(LAB) == []      # ... and that call does not raise either


def test_a_restart_between_rounds_keeps_every_round_and_goes_on(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    trade(eng, ad, exit_px=110.0)
    live_round(eng, ad, legs=leg(iid=5, rr=2.0, move=True), fill=100.5)
    before = eng.lab_rounds(LAB)
    eng2 = restart(eng, tmp_path)
    assert list(eng2.states) == [f"{LAB}@a1#1", f"{LAB}@a1"]          # I-3 survives the day file
    assert eng2.lab_rounds(LAB) == before
    assert [(r["round"], r["status"], r["clean"], r["iid"]) for r in before] == \
        [(1, "done", True, {"Buy": 1}), (2, "live", False, {"Buy": 5})]
    st = rnd(eng2)
    assert (st.sl_px, st.tp_px) == (95.5, 110.5) and eng2.day_status(LAB) == "live" and eng2.lab_open(LAB) == ["a1"]
    fill_exit(eng2, ad, st, 110.5, "tp")
    tick(eng2)
    assert (st.status, st.exit_reason, st.pnl) == ("done", "tp", 200.0)
    assert go(eng2, leg(iid=6))["accounts"]["a1"] == {"ok": True, "round": 3, "reason": None}
    assert list(eng2.states) == [f"{LAB}@a1#1", f"{LAB}@a1#2", f"{LAB}@a1"]


def test_a_round_caught_placing_by_a_restart_is_never_clean(tmp_path):
    """Ruling Q-A, second half: the order was in flight; it may be working under an id nobody recorded."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]

    async def never(req):
        await asyncio.sleep(3600)

    ad.place_bracket = never

    async def cut_off():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(eng.lab_enter(LAB, [leg()], {"a1": 1}, max_rounds=3), 0.02)

    run(cut_off())
    assert json.loads((tmp_path / f"day-{eng._today()}.json").read_text())[f"{LAB}@a1"]["status"] == "placing"
    del ad.place_bracket
    eng2 = restart(eng, tmp_path)
    st = rnd(eng2)
    assert (st.status, st.note) == ("error", PLACING_UNKNOWN)
    for _ in range(3):
        tick(eng2)
    out = go(eng2, leg(iid=2))
    assert out["accounts"]["a1"] == {"ok": False, "round": None,
                                     "reason": "The Desk cannot check the last trade's orders."}
    assert ad.brackets == [] and eng2.lab_open(LAB) == ["a1"]
    (r,) = eng2.lab_rounds(LAB)
    assert (r["status"], r["clean"], r["why"]) == ("error", False, "The Desk cannot check the last trade's orders.")
    (chk,) = events(tmp_path, "lab_check")
    assert (chk["account"], chk["round"], chk["reason"]) == ("a1", 1, PLACING_UNKNOWN)


@pytest.mark.parametrize("damage", ["missing", "garbage", "not_a_dict", "rows_not_dicts"])
def test_rounds_whose_extras_are_lost_are_not_clean(tmp_path, damage):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    trade(eng, ad, exit_px=110.0)
    assert rows(eng)[0]["clean"] is True
    p = tmp_path / f"labday-{eng._today()}.json"
    if damage == "missing":
        p.unlink()
    else:
        p.write_text({"garbage": "{not json", "not_a_dict": "[1, 2]", "rows_not_dicts": json.dumps(
            {f"{LAB}@a1": 7})}[damage])
    eng2 = restart(eng, tmp_path)                                     # the desk starts all the same
    (r,) = eng2.lab_rounds(LAB)
    assert (r["status"], r["round"], r["clean"], r["pnl"]) == ("done", 1, False, 200.0)
    assert eng2.lab_open(LAB) == ["a1"]
    for _ in range(3):
        tick(eng2)
    assert go(eng2, leg(iid=2))["accounts"]["a1"]["reason"] == "The Desk cannot check the last trade's orders."
    assert len(ad.brackets) == 1


def test_a_live_round_whose_extras_are_lost_still_exits_and_still_flattens(tmp_path):
    eng, ads, clock = mk(tmp_path, accounts=("a1", "a2"))
    go(eng, leg())
    for a in ("a1", "a2"):
        fill_entry(eng, ads[a], rnd(eng, a), 100.0)
    (tmp_path / f"labday-{eng._today()}.json").write_text("{")
    eng2 = restart(eng, tmp_path)
    fill_exit(eng2, ads["a1"], rnd(eng2, "a1"), 95.0, "sl")           # the broker stop: booked and graded
    assert (rnd(eng2, "a1").status, rnd(eng2, "a1").exit_reason, rnd(eng2, "a1").pnl) == ("done", "sl", -100.0)
    clock.set_et(15, 55)
    tick(eng2)             # fix round 3, R-B: a round whose record was lost is hands off -- nothing is sent
    assert ads["a2"].orders == [] and rnd(eng2, "a2").status == "live"
    assert not events(tmp_path, "clock_flat_failed") and not events(tmp_path, "clock_flat")
    assert all(not r["clean"] for r in eng2.lab_rounds(LAB))


def test_a_close_that_left_before_a_restart_is_not_sent_again_after_it(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    assert run(eng.lab_flatten(LAB, reason="time"))["a1"]["sold"] == 1
    eng2 = restart(eng, tmp_path)
    later(clock, 1)
    assert run(eng2.lab_flatten(LAB))["a1"] == {"ok": True, "sold": 0,
                                                "actions": ["the close order is out: waiting for its fill"]}
    clock.set_et(15, 55)
    tick(eng2)
    assert len(ad.orders) == 1 and rnd(eng2).status == "live"         # "check it" now; still one order
    fill_exit(eng2, ad, rnd(eng2), 101.0, by="market")
    assert (rnd(eng2).status, rnd(eng2).exit_reason) == ("done", "time")


def test_a_round_that_cannot_be_written_is_refused_and_nothing_is_sent(tmp_path):
    eng, ads, _ = mk(tmp_path)

    def full(strict=False):
        if strict:
            raise OSError("disk full")

    eng._lab_save = full
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": 1,
                                     "reason": "The Desk could not write this trade down. Nothing was sent."}
    assert ads["a1"].brackets == [] and rnd(eng).status == "error"
    del eng._lab_save
    assert go(eng, leg())["accounts"]["a1"] == {"ok": True, "round": 2, "reason": None}


def test_the_first_lab_action_of_a_new_day_drops_yesterdays_rounds(tmp_path):
    import datetime as dt
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    trade(eng, ad)
    trade(eng, ad)
    old = eng._state("nq930", "a1")                                   # another strategy's state of that day
    assert len(eng.states) == 3 and len(eng._lab_mem()) == 2
    clock.dt += dt.timedelta(days=1)
    assert eng.lab_rounds(LAB) == [] and eng.lab_open(LAB) == [] and eng.day_status(LAB) == "idle"
    assert go(eng, leg(iid=9))["accounts"]["a1"] == {"ok": True, "round": 1, "reason": None}
    assert list(eng.states) == ["nq930@a1", f"{LAB}@a1"] and eng.states["nq930@a1"] is old
    assert list(eng._lab_mem()) == [f"{LAB}@a1"] and eng._lab_mem()[f"{LAB}@a1"]["round"] == 1
    assert list(json.loads((tmp_path / f"labday-{eng._today()}.json").read_text())) == [f"{LAB}@a1"]


def test_broken_extras_never_raise_into_a_fill(tmp_path):
    """_lab_move and _lab_grade run inside on_fill: whatever the extras hold, the fill is booked."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(move=True))
    st = rnd(eng)
    eng._lab_mem()[f"{LAB}@a1"]["legs"] = {"Buy": {"ref_px": "x", "move": True, "sl_px": 95.0, "tp_px": 110.0}}
    fill_entry(eng, ad, st, 101.0)
    assert st.status == "live" and "error" in events(tmp_path, "brackets_moved")[0]
    assert events(tmp_path, "brackets_moved")[0]["sl"] == 95.0
    eng._lab_mem()[f"{LAB}@a1"] = None
    eng._lab_x = lambda s: (_ for _ in ()).throw(RuntimeError("extras gone"))
    fill_exit(eng, ad, st, 110.0, "tp")
    assert (st.status, st.exit_reason, st.pnl) == ("done", "exit", 180.0)


# ================================================================================================ fix round 1
def markets(ad):
    return [(o.side, o.qty, o.text) for o in ad.orders if o.order_type == "Market"]


# ------------------------------------------------------------------------------------------------ C1
@pytest.mark.parametrize("refused", [False, True])
def test_c1_an_empty_reason_never_switches_the_one_close_guard_off(tmp_path, refused):
    """The guard is a fact of its own (close_sent_ms), written when the order is sent -- never the reason text."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.fail_market = refused
    run(eng.lab_flatten(LAB, reason=""))
    ad.fail_market = False
    run(eng.lab_flatten(LAB, reason=""))
    run(eng.lab_flatten(LAB, reason=None))
    clock.set_et(15, 56)
    tick(eng)
    later(clock, 31)
    tick(eng)
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]
    x = eng._lab_x(st)
    assert x["close_sent_ms"] and x["closing"] == "flat"            # an empty reason is "flat"
    if not refused:
        fill_exit(eng, ad, st, 101.0, by="market")
        assert (st.status, st.exit_reason) == ("done", "flat")


# ------------------------------------------------------------------------------------------------ C3
def test_c3_a_stop_and_a_close_that_both_filled_is_never_clean(tmp_path):
    """The stop fills between the net read and the close's arrival: the account is left short with no stop. The
    round must say so, and no new trade may follow."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    real = ad.place_order

    async def race(req):
        r = await real(req)
        ad.order_status[f"{st.upper_id}-sl"], ad.order_status[f"{st.upper_id}-tp"] = "Filled", "Canceled"
        ad.net -= 2                                                 # the stop's 1 and the close's 1: short 1
        return r

    ad.place_order = race
    assert run(eng.lab_flatten(LAB, reason="time"))["a1"]["sold"] == 1
    ad.place_order = real
    assert eng._lab_x(st)["close_id"] == "plain" and eng._lab_x(st)["close_ok"] is True
    for px, oid in ((95.0, f"{st.upper_id}-sl"), (95.25, "plain")):
        run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=px, raw={"orderId": oid})))
    assert st.status == "done" and ad.net == -1
    for _ in range(3):
        tick(eng)
    (r,) = eng.lab_rounds(LAB)
    assert (r["clean"], r["why"]) == (False, "Check it: this trade's exit may have filled twice.")
    (chk,) = events(tmp_path, "lab_check")
    assert chk["round"] == 1 and "filled" in chk["reason"]
    assert go(eng, leg(iid=2))["accounts"]["a1"]["ok"] is False and len(ad.brackets) == 1
    assert eng.lab_open(LAB) == ["a1"]


def test_c3_a_stop_and_a_target_that_both_filled_is_never_clean(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    fill_exit(eng, ad, st, 110.0, "tp")
    ad.order_status[f"{st.upper_id}-sl"] = "Filled"                 # the broker's one-cancels-other did not hold
    for _ in range(2):
        tick(eng)
    assert rows(eng)[0]["why"] == "Check it: this trade's exit may have filled twice." and not rows(eng)[0]["clean"]


def test_c3_a_round_that_ended_while_its_close_was_sent_keeps_its_orders_alone(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    real = ad.place_order

    async def stopped_out_meanwhile(req):
        r = await real(req)
        fill_exit(None, ad, st, 95.0, "sl", push=False)             # the broker's book: the stop filled
        await eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=95.0,
                                    raw={"orderId": f"{st.upper_id}-sl"}))
        return r

    ad.place_order = stopped_out_meanwhile
    out = run(eng.lab_flatten(LAB))["a1"]
    assert st.status == "done" and ad.cancelled == []               # no cancel after the round ended
    assert "ended" in out["actions"][-1]


# ------------------------------------------------------------------------------------------------ C4
def test_c4_a_kill_after_an_accepted_close_sends_nothing_more(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    run(eng.lab_flatten(LAB, reason="time"))                        # accepted; not filled yet: the net is still +1
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]
    out = run(eng.kill_strategy(LAB))["a1"]
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]        # never a second market order
    assert out["ok"] is False and "check it" in out["actions"][-1] and st.status == "live"
    assert eng.killed_today(LAB)
    fill_exit(eng, ad, st, 101.0, by="market")                      # the close fills: booked as usual
    assert (st.status, st.exit_reason, st.pnl) == ("done", "time", 20.0)


def test_c4_a_kill_after_a_refused_close_sends_nothing(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.fail_market = True
    run(eng.lab_flatten(LAB))
    ad.fail_market = False
    n = len(ad.cancelled)
    out = run(eng.kill_strategy(LAB))["a1"]
    assert len(ad.orders) == 1 and out["ok"] is False and "check it" in out["actions"][-1]
    assert ad.cancelled[n:] == [] and st.status == "live"           # its stop still works
    clock.set_et(15, 56)
    later(clock, 31)
    tick(eng)
    assert len(ad.orders) == 1


def test_c4_a_kill_of_a_round_that_read_flat_never_sells_a_manual_position(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.net = 0
    run(eng.lab_flatten(LAB))                                       # read flat: its position is gone; nothing sent
    ad.net = 1                                                      # the owner buys 1 by hand
    run(eng.kill_strategy(LAB))
    assert ad.orders == []


def test_c4_a_kill_with_no_close_sent_closes_the_round_as_before(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    out = run(eng.kill_strategy(LAB))["a1"]
    assert out["ok"] is True and markets(ad) == [("Sell", 1, "homebase:kill")]
    assert (st.status, st.exit_reason) == ("done", "killed")


def test_c4_the_global_kill_sends_no_second_market_order_for_a_close_in_flight(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    run(eng.lab_flatten(LAB))                                       # accepted, the net still reads +1
    out = run(eng.flatten_today())
    assert out == {} and markets(ad) == [("Sell", 1, "homebase:lab-flat")]
    assert st.status == "live"                                      # the Kill's own account sweep is the backstop


def test_hook_kill_one_never_reaches_the_lab_for_another_kind(kinds):
    """The eighth hook (fix round 1, C4)."""
    for kind, eng, ad, name, account, seen in kinds:
        st = enter(eng, name, account, 24510.0 if kind != "bars" else 30035.0)
        ad.net = st.qty
        ad.order_status = {st.upper_id: "Filled", **({st.lower_id: "Canceled"} if st.lower_id else {})}
        out = run(eng.kill_strategy(name))
        assert out[account]["ok"] is True and out[account]["acted"] is True, kind
        assert [(o.side, o.qty, o.text) for o in ad.orders] == [("Sell", st.qty, "homebase:kill")]
        assert (st.status, st.exit_reason) == ("done", "killed") and seen["lab"] == []


# ------------------------------------------------------------------------------------------------ S5, S8
def test_s8_the_flatten_closes_only_what_is_still_in(tmp_path):
    """2 in, 1 out again by its stop, and 1 the owner holds by hand: the flatten sells 1, not 2."""
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 2})
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0, qty=2)
    run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=95.0,
                              raw={"orderId": f"{st.upper_id}-sl"})))
    assert (st.status, st.exit_qty) == ("live", 1)
    ad.net = 2                                                      # its last 1, and 1 by hand
    assert run(eng.lab_flatten(LAB))["a1"]["sold"] == 1
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]


def test_s5_a_filled_count_that_may_lag_is_not_trusted_against_the_net(tmp_path):
    """3 asked, 2 in, 1 fill seen. The broker's count for a cancelled entry is a lower bound: the flatten must not
    sell 1, call it closed and cancel the stop of the contract that is left."""
    eng, ads, _ = mk(tmp_path, qty=3)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 3})
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0, qty=1)
    ad.net = 2                                                      # a second fill's push carried no order id
    out = run(eng.lab_flatten(LAB))["a1"]
    assert out["ok"] is False and out["sold"] == 0 and "check it" in out["actions"][-1]
    assert markets(ad) == [] and ad.order_status[f"{st.upper_id}-sl"] == "Working"
    ad.net = 1                                                      # the count and the net agree: it closes
    eng2_out = run(eng.lab_flatten(LAB))["a1"]
    assert eng2_out["sold"] == 1


# ------------------------------------------------------------------------------------------------ C2 (i)
def test_c2_an_account_that_already_holds_the_market_sits_out_every_round(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1", "a2"))
    ads["a1"].net = 1
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": None, "reason": "The account already holds NQ. Check it."}
    assert out["accounts"]["a2"] == {"ok": True, "round": 1, "reason": None}
    assert ads["a1"].brackets == [] and list(eng.states) == [f"{LAB}@a2"]         # no round, nothing on disk
    assert f"{LAB}@a1" not in json.loads((tmp_path / f"labday-{eng._today()}.json").read_text())
    assert ("a1", "The account already holds NQ. Check it.") in \
        [(e["account"], e["reason"]) for e in events(tmp_path, "place_skipped")]
    ads["a1"].net = 0
    trade(eng, ads["a1"])                                           # round 1 on a1, closed and clean
    ads["a1"].net = -2                                              # not only the day's first entry: every round
    assert go(eng, leg(iid=2), {"a1": 1})["accounts"]["a1"]["reason"] == "The account already holds NQ. Check it."
    assert len(ads["a1"].brackets) == 1 and rnd(eng, "a1").status == "done"
    ads["a1"].net = 0
    assert go(eng, leg(iid=2), {"a1": 1})["accounts"]["a1"] == {"ok": True, "round": 2, "reason": None}


@pytest.mark.parametrize("how", ["raises", "none"])
def test_c2_an_account_whose_position_cannot_be_read_sits_out(tmp_path, how):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    if how == "raises":
        ad.net_error = True
    else:
        async def nothing(symbol):
            return None

        ad.get_net_position = nothing
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": None,
                                     "reason": "The Desk cannot read this account's position."}
    assert ad.brackets == [] and eng.states == {}


def test_c2_the_position_is_read_before_the_round_exists(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    seen = []
    real = ad.get_net_position

    async def read(symbol):
        seen.append((symbol, dict(eng.states), [e["event"] for e in events(tmp_path)], list(ad.brackets)))
        return await real(symbol)

    ad.get_net_position = read
    assert go(eng, leg())["accounts"]["a1"]["ok"] is True
    assert seen == [("NQ", {}, [], [])]                             # one read, before anything was made or sent


# ------------------------------------------------------------------------------------------------ C2 (ii)
def next_day(clock, days=1):
    import datetime as dt
    clock.dt = dt.datetime(2026, 9, 14, 13, 31, tzinfo=dt.timezone.utc) + dt.timedelta(days=days)


def unresolved_day_one(tmp_path):
    """Day 1: a live round whose close was refused at the flat time. Its stop still works at the broker."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.fail_market = True
    clock.set_et(15, 56)
    tick(eng)
    ad.fail_market = False
    assert st.status == "live" and eng.lab_open(LAB) == ["a1"] and ad.net == 1
    return eng, ad, clock, st


def assert_carried(eng, ad, tmp_path, n_orders=1, n_brackets=1):
    assert eng.lab_open(LAB) == ["a1"]
    (r,) = eng.lab_rounds(LAB)
    assert (r["account"], r["round"], r["date"], r["carried"], r["clean"], r["why"]) == \
        ("a1", 1, "2026-09-14", True, False, "The Desk cannot check the last trade's orders.")
    out = go(eng, leg(iid=7))["accounts"]["a1"]
    assert out == {"ok": False, "round": None, "reason": "The Desk cannot check the last trade's orders."}
    assert len(ad.orders) == n_orders and len(ad.brackets) == n_brackets          # nothing sent
    assert eng.day_status(LAB) == "idle"                            # a block, not a trade of today


def test_c2_a_round_still_open_at_midnight_blocks_the_next_day(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    assert_carried(eng, ad, tmp_path)
    (c,) = events(tmp_path, "lab_carry")
    assert (c["strategy"], c["account"], c["round"], c["date"], c["status"]) == (LAB, "a1", 1, "2026-09-14", "live")
    assert set(c["orders"]) == {"a1-101", "a1-101-sl", "a1-101-tp"}
    assert list(eng.states) == [f"{LAB}@a1#c2026-09-14"]            # yesterday's live state is gone from the day


def test_c2_a_carried_block_clears_by_itself_and_never_sends_anything(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    cancelled = list(ad.cancelled)
    for _ in range(3):                                              # the stop still works: it stays
        tick(eng)
    assert eng.lab_open(LAB) == ["a1"]
    ad.net = 0                                                      # the account reads flat (closed by hand) ...
    tick(eng)
    assert eng.lab_open(LAB) == ["a1"]                              # ... but its stop is still working: it stays
    ad.net = 1
    ad.order_status.update({"a1-101-sl": "Filled", "a1-101-tp": "Canceled"})      # every order ended ...
    tick(eng)
    assert eng.lab_open(LAB) == ["a1"]                              # ... but the account does not read flat
    ad.net = 0
    run(eng.clock_tick())                                           # inside the 5 s: not asked again
    assert eng.lab_open(LAB) == ["a1"]
    tick(eng)
    assert eng.lab_open(LAB) == [] and eng.lab_rounds(LAB) == []
    (c,) = events(tmp_path, "lab_carry_cleared")
    assert (c["strategy"], c["account"], c["round"], c["date"]) == (LAB, "a1", 1, "2026-09-14")
    assert ad.cancelled == cancelled and len(ad.orders) == 1        # read only, from the first day's close on
    assert go(eng, leg(iid=7))["accounts"]["a1"] == {"ok": True, "round": 1, "reason": None}


def test_c2_what_the_engine_still_holds_is_carried_even_when_yesterdays_files_are_gone(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    (tmp_path / "labday-2026-09-14.json").unlink()
    (tmp_path / "day-2026-09-14.json").unlink()
    next_day(clock)                                                 # the same engine, over midnight
    assert_carried(eng, ad, tmp_path)


def test_c2_a_carried_block_survives_a_restart_and_is_carried_once(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng2 = restart(eng, tmp_path)                                   # the desk starts on day 2: only the files
    assert eng2.states == {}
    assert_carried(eng2, ad, tmp_path)
    eng3 = restart(eng2, tmp_path)                                  # and again, the same day
    assert_carried(eng3, ad, tmp_path)
    assert list(eng3.states) == [f"{LAB}@a1#c2026-09-14"] and len(events(tmp_path, "lab_carry")) == 1
    next_day(clock, 2)                                              # a third day: still not resolved
    eng4 = restart(eng3, tmp_path)
    assert_carried(eng4, ad, tmp_path)
    assert events(tmp_path, "lab_carry")[-1]["date"] == "2026-09-14"


def test_c2_a_block_that_cleared_is_not_carried_again_by_a_restart(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    ad.order_status.update({"a1-101-sl": "Filled", "a1-101-tp": "Canceled"})
    ad.net = 0
    tick(eng)
    assert eng.lab_open(LAB) == []
    eng2 = restart(eng, tmp_path)
    assert eng2.lab_open(LAB) == [] and eng2.lab_rounds(LAB) == [] and len(events(tmp_path, "lab_carry")) == 1


def test_c2_every_kill_and_flatten_leaves_a_carried_block_alone(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    cancelled, orders = list(ad.cancelled), len(ad.orders)
    ad.net = 3
    out = run(eng.kill_strategy(LAB))
    assert out["a1"]["ok"] is False and "check it" in out["a1"]["actions"][0]
    assert run(eng.flatten_today()) == {} and run(eng.flatten_strategy(LAB)) == {}
    assert run(eng.lab_cancel(LAB)) == {} and run(eng.lab_flatten(LAB)) == {}
    later(clock, 7 * 3600)                                          # past the flat time, still the second day
    assert eng.now_et().date().isoformat() == "2026-09-15"
    tick(eng)
    assert ad.cancelled == cancelled and len(ad.orders) == orders   # yesterday's stop is never touched


def test_c2_a_clean_yesterday_carries_nothing(tmp_path):
    eng, ads, clock = mk(tmp_path)
    trade(eng, ads["a1"])
    next_day(clock)
    eng2 = restart(eng, tmp_path)
    assert eng2.lab_open(LAB) == [] and not events(tmp_path, "lab_carry")
    assert go(eng2, leg())["accounts"]["a1"] == {"ok": True, "round": 1, "reason": None}


@pytest.mark.parametrize("damage", ["lab_garbage", "day_missing", "eight_days"])
def test_c2_an_older_file_that_does_not_read_carries_nothing(tmp_path, damage):
    """... and rule (i) still stands in front of the entry: the account holds the market."""
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    if damage == "lab_garbage":
        (tmp_path / "labday-2026-09-14.json").write_text("{nope")
    elif damage == "day_missing":
        (tmp_path / "day-2026-09-14.json").unlink()
    next_day(clock, 8 if damage == "eight_days" else 1)
    eng2 = restart(eng, tmp_path)                                   # the desk starts all the same
    assert eng2.lab_open(LAB) == [] and eng2.lab_rounds(LAB) == []
    assert go(eng2, leg())["accounts"]["a1"]["reason"] == "The account already holds NQ. Check it."
    assert len(ad.brackets) == 1


# ------------------------------------------------------------------------------------------------ I1
@pytest.mark.parametrize("missing", ["both", "target"])
def test_i1_a_trade_whose_stop_order_the_desk_does_not_know_is_check_it(tmp_path, missing):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    real = ad.place_bracket

    async def no_ids(req):
        r = await real(req)
        r.raw["tp_order_id"] = None
        if missing == "both":
            r.raw["sl_order_id"] = None
        return r

    ad.place_bracket = no_ids
    out = go(eng, leg())["accounts"]["a1"]
    ad.place_bracket = real
    assert out["ok"] is True and out["round"] == 1
    assert out["warning"] == "Check it: the Desk does not know this trade's stop order."
    st = rnd(eng)
    (r,) = eng.lab_rounds(LAB)
    assert (r["clean"], r["why"]) == (False, "Check it: the Desk does not know this trade's stop order.")
    assert events(tmp_path, "lab_check")[0]["round"] == 1
    fill_entry(eng, ad, st, 100.0)
    n = len(ad.cancelled)
    f = run(eng.lab_flatten(LAB, reason="time"))["a1"]
    assert f["ok"] is False and f["sold"] == 0 and "check it" in f["actions"][-1]
    assert ad.orders == [] and ad.cancelled[n:] == [] and st.status == "live"     # its stop at the broker stays
    fill_exit(eng, ad, st, 95.0, "sl")                              # the broker's stop ends it: booked as usual
    for _ in range(3):
        tick(eng)
    assert st.status == "done" and eng.lab_rounds(LAB)[0]["clean"] is False
    assert go(eng, leg(iid=2))["accounts"]["a1"]["ok"] is False


def test_i1_a_stop_with_no_target_needs_no_target_id(tmp_path):
    eng, ads, _ = mk(tmp_path)
    out = go(eng, leg(tp=None))["accounts"]["a1"]
    assert out == {"ok": True, "round": 1, "reason": None} and not events(tmp_path, "lab_check")


# ------------------------------------------------------------------------------------------------ I2
CLEAR_REJECTS = ["adapter not connected", "OSO rejected (no orderId returned)", "order rejected (no orderId returned)",
                 "a Stop Limit order needs both a limit price and a trigger", "bracketed stop entries need a broker OSO"]


def test_i2_the_clear_refusals_are_the_adapters_own_fixed_phrases():
    """Each phrase is in homebase/broker/ as the answer of a path that sends nothing, or of an answered reject."""
    import pathlib
    src = "".join((pathlib.Path(engine_mod.__file__).parent / "broker" / f).read_text()
                  for f in ("tradovate.py", "base.py"))
    assert sorted(engine_mod.LAB_CLEAR_REJECTS) == sorted(CLEAR_REJECTS)
    assert all(f'"{phrase}"' in src for phrase in CLEAR_REJECTS)


@pytest.mark.parametrize("words", CLEAR_REJECTS)
def test_i2_a_clear_refusal_is_clean_and_the_next_entry_goes(tmp_path, words):
    eng, ads, _ = mk(tmp_path)
    ads["a1"].reject = words
    assert go(eng, leg())["accounts"]["a1"] == {"ok": False, "round": 1, "reason": f"The broker refused it: {words}"}
    ads["a1"].reject = None
    assert rows(eng)[0]["clean"] is True and eng.lab_open(LAB) == []
    assert go(eng, leg(iid=2))["accounts"]["a1"] == {"ok": True, "round": 2, "reason": None}


@pytest.mark.parametrize("fail", ["", None, "OSO failed: ", "Insufficient funds", "rejected", "paper book 500: oops",
                                  asyncio.TimeoutError(), RuntimeError("")])
def test_i2_anything_that_is_not_a_clear_refusal_is_outcome_unknown(tmp_path, fail):
    """The order may be at the broker under an id nobody has: a phrase is unknown until it is proven a reject."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    real = ad.place_bracket

    async def ghost(req):
        await real(req)                                             # the order IS at the broker
        if isinstance(fail, Exception):
            raise fail
        return OrderResult(ok=False, error=fail)

    ad.place_bracket = ghost
    first = go(eng, leg())["accounts"]["a1"]
    ad.place_bracket = real
    assert (first["ok"], first["round"], first["reason"]) == (False, 1, "The Desk cannot check this order.")
    (r,) = eng.lab_rounds(LAB)
    assert (r["status"], r["clean"], r["why"]) == ("error", False, "The Desk cannot check the last trade's orders.")
    assert events(tmp_path, "lab_check")[0]["round"] == 1
    for _ in range(3):
        tick(eng)
    nxt = go(eng, leg(iid=2))["accounts"]["a1"]
    assert nxt == {"ok": False, "round": None, "reason": "The Desk cannot check the last trade's orders."}
    assert len(ad.brackets) == 1 and eng.lab_open(LAB) == ["a1"]


# ------------------------------------------------------------------------------------------------ I3
def test_i3_cancel_of_a_part_filled_entry_cancels_the_rest(tmp_path):
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 2})
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0, qty=1)                           # 1 of 2 in; the other still works
    n = len(ad.cancelled)
    out = run(eng.lab_cancel(LAB, None, why="runner_down"))["a1"]
    assert ad.cancelled[n:] == [st.upper_id] and ad.order_status[st.upper_id] == "Canceled"
    assert (out["ok"], out["state"], out["filled"]) == (True, "part", 1)
    assert st.status == "live" and ad.orders == []                  # the 1 that is in keeps its stop
    assert "Buy" not in rows(eng)[0]["cancelled"]                   # not "ended with no fill"
    assert run(eng.lab_flatten(LAB))["a1"]["sold"] == 1             # and the flatten closes exactly that 1


def test_i3_a_wholly_filled_entry_is_still_filled(tmp_path):
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 2})
    fill_entry(eng, ad, rnd(eng), 100.0, qty=2)
    n = len(ad.cancelled)
    assert run(eng.lab_cancel(LAB))["a1"] == {"ok": True, "state": "filled", "actions": []}
    assert ad.cancelled[n:] == []


def test_i3_a_remainder_the_broker_does_not_end_is_working(tmp_path):
    eng, ads, _ = mk(tmp_path, qty=2)
    ad = ads["a1"]
    go(eng, leg(), {"a1": 2})
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0, qty=1)
    ad.stuck.add(st.upper_id)
    out = run(eng.lab_cancel(LAB))["a1"]
    assert (out["ok"], out["state"]) == (False, "working") and events(tmp_path, "lab_check")


# ------------------------------------------------------------------------------------------------ S1
@pytest.mark.parametrize("key,value", [("cancelled", None), ("cancelled", "Buy"), ("cancelled", [7]), ("legs", []),
                                       ("legs", {"Buy": 3}), ("iid", "x"), ("round", "one"), ("clean", "yes"),
                                       ("close_sent_ms", "soon"), ("carry", 5), ("entry_ms", "x")])
def test_s1_extras_of_a_wrong_type_make_the_round_not_clean_and_never_break_the_clock(tmp_path, key, value):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    p = tmp_path / f"labday-{eng._today()}.json"
    d = json.loads(p.read_text())
    d[f"{LAB}@a1"][key] = value
    p.write_text(json.dumps(d))
    eng2 = restart(eng, tmp_path)
    clock.set_et(15, 56)
    tick(eng2)
    tick(eng2)
    assert not events(tmp_path, "clock_error")
    x = eng2._lab_mem()[f"{LAB}@a1"]
    assert x["check"] is True and isinstance(x["cancelled"], list) and isinstance(x["legs"], dict)
    assert eng2.lab_rounds(LAB)[0]["clean"] is False and eng2.lab_open(LAB) == ["a1"]
    # a close mark that does not read is still "sent": never a second order. Every other damage leaves the round
    # what it is, a trade of today that the flat time closes (its own position, capped)
    assert markets(ad) == ([] if key == "close_sent_ms" else [("Sell", 1, "homebase:lab-flat")])


def test_s1_a_carried_block_whose_mark_is_damaged_is_still_a_block(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    assert eng.lab_open(LAB) == ["a1"]
    p = tmp_path / f"labday-{eng._today()}.json"
    d = json.loads(p.read_text())
    d[f"{LAB}@a1#c2026-09-14"]["carry"] = "yes"
    p.write_text(json.dumps(d))
    eng2 = restart(eng, tmp_path)
    assert eng2.lab_open(LAB) == ["a1"]
    assert go(eng2, leg(iid=7))["accounts"]["a1"]["reason"] == "The Desk cannot check the last trade's orders."
    assert len(ad.brackets) == 1


# ------------------------------------------------------------------------------------------------ S2, S3
def test_s2_a_leg_that_is_not_a_labLeg_is_refused_and_no_state_is_left_placing(tmp_path):
    class Duck:                                                     # every attribute, and not a LabLeg
        iid, side, entry, entry_price, sl_px, tp_px, tp_rr, ref_px, move = 1, "Buy", "Stop", 100.0, 95.0, 110.0, None, 100.0, False

    eng, ads, _ = mk(tmp_path)
    whole = run(eng.lab_enter(LAB, [Duck()], {"a1": 1}, max_rounds=3))
    out = whole["accounts"]["a1"]
    assert whole["reason"] == "The Desk cannot check this order."   # refused whole, before any account is looked at
    assert out == {"ok": False, "round": None, "reason": "The Desk cannot check this order."}
    assert eng.states == {} and ads["a1"].brackets == []


def test_s2_nothing_is_left_placing_when_the_round_cannot_be_built(tmp_path, monkeypatch):
    eng, ads, _ = mk(tmp_path)

    def broken(obj):
        raise TypeError("cannot build")

    monkeypatch.setattr(engine_mod, "asdict", broken)
    out = run(eng.lab_enter(LAB, [leg()], {"a1": 1}, max_rounds=3))["accounts"]["a1"]
    assert out["ok"] is False and ads["a1"].brackets == []
    assert not [s for s in eng.states.values() if s.status == "placing"]


def test_s3_a_failure_after_the_brokers_ack_is_still_a_placed_trade(tmp_path):
    eng, ads, _ = mk(tmp_path)
    real = eng.journal

    def journal(event, **kw):
        if event == "placed":
            raise OSError("disk full")
        return real(event, **kw)

    eng.journal = journal
    out = go(eng, leg())["accounts"]["a1"]
    assert (out["ok"], out["round"], out["reason"]) == (True, 1, None) and "disk full" in out["warning"]
    assert rnd(eng).status == "placed" and len(ads["a1"].brackets) == 1


# ------------------------------------------------------------------------------------------------ S4
def test_s4_the_flat_time_close_waits_for_the_adapter_and_is_not_used_up(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad._connected = False
    clock.set_et(15, 56)
    for _ in range(3):
        tick(eng)
    assert ad.orders == [] and eng._lab_x(st)["close_sent_ms"] is None and st.status == "live"
    (w,) = events(tmp_path, "clock_flat_waiting")
    assert (w["strategy"], w["account"]) == (LAB, "a1")
    ad._connected = True
    run(eng.clock_tick())                                           # the first tick after it is back: no 5 s wait
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]


# ------------------------------------------------------------------------------------------------ S6, S7
def test_s6_a_round_ended_with_no_exit_fill_is_never_clean(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    run(eng.lab_flatten(LAB))
    ad.net = 0                                                      # it filled; the push is lost
    later(clock, 6)
    tick(eng)
    assert st.status == "done" and events(tmp_path, "lab_exit_unconfirmed")
    for _ in range(3):
        tick(eng)
    (r,) = eng.lab_rounds(LAB)
    assert (r["clean"], r["why"]) == (False, "The Desk cannot check the last trade's orders.")
    assert go(eng, leg(iid=2))["accounts"]["a1"]["ok"] is False and eng.lab_open(LAB) == ["a1"]


# ================================================================================================ fix round 2
def during_the_position_read(eng, ad, what, legs=None):
    """lab_enter on a1; while its position read is out, `what()` happens (a plain call or a coroutine); then the
    read answers 0 and the entry goes on. -> lab_enter's answer for a1."""
    gate = asyncio.Event()

    async def slow(symbol):
        await gate.wait()
        return 0

    ad.get_net_position = slow

    async def go_():
        t = asyncio.ensure_future(eng.lab_enter(LAB, [legs or leg()], {"a1": 1}, max_rounds=3))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        r = what()
        if asyncio.iscoroutine(r):
            await r
        gate.set()
        return await t

    return run(go_())["accounts"]["a1"]


# ------------------------------------------------------------------------------------------------ N1
def test_n1_a_global_kill_during_the_position_read_stops_the_entry(tmp_path):
    """The reviewer's probe: /api/kill = disarm, then every kill lock and flatten_today, while the read is out."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]

    async def kill():
        eng.cfg.armed = False
        async with eng.all_kill_locks():
            await eng.flatten_today()

    out = during_the_position_read(eng, ad, kill, legs=leg(entry="Market", ref=100.0))
    assert out == {"ok": False, "round": None, "reason": "The desk is disarmed: written down only."}
    assert ad.brackets == [] and eng.states == {}                    # nothing sent, no state, no round used
    (dry,) = events(tmp_path, "dry_run")
    assert (dry["strategy"], dry["account"], dry["qty"]) == (LAB, "a1", 1) and not events(tmp_path, "lab_round")


@pytest.mark.parametrize("how,reason", [("disarm", "The desk is disarmed: written down only."),
                                        ("kill", "Killed today."), ("off", "It is off."),
                                        ("flat_time", "Too late for a new trade today."),
                                        ("last_entry", "Too late for a new trade today."),
                                        ("removed", "That strategy is not on the Desk.")])
def test_n1_every_precondition_is_asked_again_after_the_position_read(tmp_path, how, reason):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]

    def change():
        if how == "disarm":
            eng.cfg.armed = False
        elif how == "kill":
            return eng.kill_strategy(LAB)                           # a per-strategy Kill: no round yet, nothing to do
        elif how == "off":
            eng.cfg.strategies[LAB] = lab_cfg(enabled=False)        # the switch replaces the cfg object
        elif how == "flat_time":
            clock.set_et(15, 55)
        elif how == "last_entry":
            clock.set_et(11, 1)
        else:
            del eng.cfg.strategies[LAB]

    out = during_the_position_read(eng, ad, change)
    assert out == {"ok": False, "round": None, "reason": reason}
    assert ad.brackets == [] and eng.states == {} and not events(tmp_path, "lab_round")
    assert not events(tmp_path, "strategy_killed_after_ack")
    if how != "removed":
        assert eng.lab_rounds(LAB) == [] and eng.lab_open(LAB) == []


def test_n1_the_accept_window_is_the_doors(tmp_path):
    """No new trade before the session's start or after the last-entry minute (the door's own rule, by HH:MM)."""
    eng, ads, clock = mk(tmp_path)
    clock.set_et(9, 24)
    assert go(eng, leg())["reason"] == "Too late for a new trade today."
    clock.set_et(11, 0)
    later(clock, 30)                                                # 11:00:30 is still the last-entry minute
    assert go(eng, leg())["accounts"]["a1"]["ok"] is True
    (tmp_path / "b").mkdir()
    eng2, ads2, clock2 = mk(tmp_path / "b")
    clock2.set_et(11, 1)
    assert go(eng2, leg())["reason"] == "Too late for a new trade today." and ads2["a1"].brackets == []


# ------------------------------------------------------------------------------------------------ N2
def ghost_close(eng, ad):
    """The close reaches the broker and its answer is a failure (a timeout)."""
    real = ad.place_order

    async def ghost(req):
        await real(req)
        raise asyncio.TimeoutError("request timed out")

    ad.place_order = ghost
    out = run(eng.lab_flatten(LAB, reason="time"))["a1"]
    ad.place_order = real
    assert out["ok"] is False and len(ad.orders) == 1
    return out


def test_n2_an_unconfirmed_close_and_the_stop_that_both_filled_is_never_clean(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ghost_close(eng, ad)
    assert rows(eng)[0]["why"] == "Check it: the close order was not confirmed. Its stop is still working."
    ad.order_status[f"{st.upper_id}-sl"], ad.order_status[f"{st.upper_id}-tp"] = "Filled", "Canceled"
    ad.net -= 2                                                     # the stop AND the close filled: +1 -> -1
    for px, oid in ((95.0, f"{st.upper_id}-sl"), (95.25, "plain")):
        run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=px, raw={"orderId": oid})))
    assert st.status == "done"
    for _ in range(3):
        tick(eng)
    (r,) = eng.lab_rounds(LAB)
    assert (r["clean"], r["why"]) == (False, "Check it: this trade's exit may have filled twice.")
    assert eng.lab_open(LAB) == ["a1"] and not events(tmp_path, "lab_settled")
    assert "filled" in events(tmp_path, "lab_check")[-1]["reason"]


def test_n2_an_exit_fill_never_wipes_an_unconfirmed_close(tmp_path):
    """The stop ends the round; every order reads ended; the account still holds the market: not clean."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ghost_close(eng, ad)
    fill_exit(eng, ad, st, 95.0, "sl")
    ad.order_status[f"{st.upper_id}-sl"] = "Canceled"               # no stop reads Filled: only the net can tell
    ad.net = -1
    assert st.status == "done" and eng._lab_x(st)["unconfirmed"] is True
    for _ in range(4):
        tick(eng)                                                   # four reads in the same second: one count
    assert rows(eng)[0]["clean"] is False
    assert rows(eng)[0]["why"] != "Check it: this trade's exit may have filled twice."
    for _ in range(2):
        later(clock, 2)
        tick(eng)
    assert rows(eng)[0]["clean"] is False
    assert rows(eng)[0]["why"] == "Check it: this trade's exit may have filled twice."


def test_n2_an_unconfirmed_close_is_clean_once_the_orders_and_the_net_are_both_read(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ghost_close(eng, ad)
    fill_exit(eng, ad, st, 101.0, by="market")                      # the close did fill, alone; net 0
    for k in ("sl", "tp"):
        ad.order_status[f"{st.upper_id}-{k}"] = "Canceled"          # every order of the round reads ended ...
    ad.net_error = True                                             # ... and the position cannot be read
    for _ in range(3):
        tick(eng)
    assert rows(eng)[0]["clean"] is False                           # the net was not read yet
    ad.net_error = False
    for _ in range(4):
        tick(eng)
    assert (rows(eng)[0]["clean"], rows(eng)[0]["why"]) == (True, None)


# ------------------------------------------------------------------------------------------------ N3
@pytest.mark.parametrize("damage", ["zero", "negative", "infinite", "nan", "none", "key_gone", "extras_gone",
                                    "old_key", "not_a_dict"])
def test_n3_the_fact_that_a_close_was_sent_survives_any_file(tmp_path, damage):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    assert run(eng.lab_flatten(LAB, reason="time"))["a1"]["sold"] == 1
    p = tmp_path / f"labday-{eng._today()}.json"
    d = json.loads(p.read_text())
    x = d[f"{LAB}@a1"]
    if damage == "extras_gone":
        d.pop(f"{LAB}@a1")
    elif damage == "not_a_dict":
        d[f"{LAB}@a1"] = [1]
    elif damage == "key_gone":
        x.pop("close_sent_ms")
    elif damage == "old_key":                                       # a file written before fix round 1
        x["closing_ms"] = x.pop("close_sent_ms")
        for k in ("close_ok", "close_id", "blind", "carry"):
            x.pop(k, None)
    else:
        x["close_sent_ms"] = {"zero": 0, "negative": -5, "infinite": float("inf"), "nan": float("nan"),
                              "none": None}[damage]
    p.write_text(json.dumps(d))
    eng2 = restart(eng, tmp_path)
    clock.set_et(15, 56)
    for _ in range(3):
        later(clock, 31)
        tick(eng2)
    run(eng2.lab_flatten(LAB))
    run(eng2.kill_strategy(LAB))
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]        # the one of before the restart, never a second
    assert not events(tmp_path, "clock_error") and eng2.lab_open(LAB) == ["a1"]




@pytest.mark.parametrize("key,value", [("gone_ms", float("inf")), ("placed_ms", float("-inf")), ("entry_ms", float("nan")),
                                       ("round", float("inf")), ("legs", {"Buy": {"sl_px": float("inf"), "move": True,
                                                                                 "ref_px": float("nan"), "tp_px": 110.0}})])
def test_n3_a_number_that_is_not_finite_makes_the_round_not_clean_and_never_breaks_the_clock(tmp_path, key, value):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(move=True))
    p = tmp_path / f"labday-{eng._today()}.json"
    d = json.loads(p.read_text())
    d[f"{LAB}@a1"][key] = value
    p.write_text(json.dumps(d))
    eng2 = restart(eng, tmp_path)
    fill_entry(eng2, ad, rnd(eng2), 101.0)
    clock.set_et(15, 56)
    for _ in range(3):
        later(clock, 6)
        tick(eng2)
    assert not events(tmp_path, "clock_error") and len(markets(ad)) <= 1
    assert eng2._lab_mem()[f"{LAB}@a1"]["check"] is True and eng2.lab_rounds(LAB)[0]["clean"] is False


# ------------------------------------------------------------------------------------------------ N4
def test_n4a_a_block_is_cleared_by_hand_only_on_a_flat_account(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    ad.order_status = {}                                            # the venue no longer answers for those ids
    for _ in range(3):
        tick(eng)
    assert eng.lab_open(LAB) == ["a1"]                              # it can never clear by itself
    cancelled, orders = list(ad.cancelled), len(ad.orders)
    assert run(eng.lab_clear_block(LAB, "a1")) == {"ok": False, "reason": "The account already holds NQ. Check it."}
    ad.net_error = True
    assert run(eng.lab_clear_block(LAB, "a1")) == {"ok": False,
                                                    "reason": "The Desk cannot read this account's position."}
    assert eng.lab_open(LAB) == ["a1"] and not events(tmp_path, "lab_carry_cleared")
    ad.net_error, ad.net = False, 0
    out = run(eng.lab_clear_block(LAB, "a1"))
    assert out["ok"] is True and out["cleared"] == ["2026-09-14"]
    (c,) = events(tmp_path, "lab_carry_cleared")
    assert (c["account"], c["date"], c["why"]) == ("a1", "2026-09-14", "by hand")
    assert eng.lab_open(LAB) == [] and ad.cancelled == cancelled and len(ad.orders) == orders   # it sent nothing
    assert run(eng.lab_clear_block(LAB, "a1"))["ok"] is False       # nothing left to clear
    assert run(eng.lab_clear_block("nq930", "a1"))["ok"] is False
    assert go(eng, leg(iid=7))["accounts"]["a1"]["ok"] is True


def test_n4b_one_bad_field_in_yesterdays_file_does_not_lose_the_other_accounts(tmp_path):
    eng, ads, clock = mk(tmp_path, accounts=("a1", "a2", "a3"))
    go(eng, leg())
    fill_entry(eng, ads["a1"], rnd(eng, "a1"), 100.0)               # a1 live, a2 and a3 placed
    p = tmp_path / f"day-{eng._today()}.json"
    d = json.loads(p.read_text())
    d[f"{LAB}@a1"]["qty"] = "x"
    d[f"{LAB}@a3"] = "garbage"
    p.write_text(json.dumps(d))
    next_day(clock)
    eng2 = restart(eng, tmp_path)
    assert eng2.lab_open(LAB) == ["a1", "a2", "a3"]
    why = {r["account"]: r["why"] for r in eng2.lab_rounds(LAB)}
    assert why == {"a1": "The Desk cannot read yesterday's record for this account.",
                   "a2": "The Desk cannot check the last trade's orders.",
                   "a3": "The Desk cannot read yesterday's record for this account."}
    assert sorted(e["account"] for e in events(tmp_path, "lab_carry")) == ["a1", "a2", "a3"]
    assert go(eng2, leg(iid=9))["accounts"]["a2"]["reason"] == "The Desk cannot check the last trade's orders."
    for a in ("a1", "a2", "a3"):
        ads[a].order_status = {k: "Canceled" for k in ads[a].order_status}
        ads[a].net = 0
    for _ in range(2):
        tick(eng2)
    assert eng2.lab_open(LAB) == ["a1", "a3"]                       # a record that does not read clears by hand only
    eng3 = restart(eng2, tmp_path)
    assert len(events(tmp_path, "lab_carry")) == 3                  # journaled once
    assert run(eng3.lab_clear_block(LAB, "a1"))["ok"] is True






# ------------------------------------------------------------------------------------------------ N6
def test_n6_a_kill_of_a_round_whose_stop_is_unknown_closes_it_and_says_check_it(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    real = ad.place_bracket

    async def no_ids(req):
        r = await real(req)
        r.raw["sl_order_id"] = r.raw["tp_order_id"] = None
        return r

    ad.place_bracket = no_ids
    go(eng, leg())
    ad.place_bracket = real
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0)
    out = run(eng.kill_strategy(LAB))["a1"]
    assert markets(ad) == [("Sell", 1, "homebase:kill")]             # the Kill still closes the position
    assert out["ok"] is False and out["acted"] is True
    assert out["actions"][-1] == "check it — this trade's stop order is unknown to the Desk and may still be working"
    assert ad.order_status[f"{st.upper_id}-sl"] == "Working"        # ... and that is why it says so
    assert "kill" in events(tmp_path, "lab_check")[-1]["reason"] and rows(eng)[0]["clean"] is False


# ------------------------------------------------------------------------------------------------ T1, W1
def test_t1_two_entries_racing_on_one_account_place_one_bracket(tmp_path):
    """Both pass the checks, both read the position; the run that opens the round asks again."""
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    gate = asyncio.Event()

    async def slow(symbol):
        await gate.wait()
        return 0

    ad.get_net_position = slow

    async def both():
        a = asyncio.ensure_future(eng.lab_enter(LAB, [leg(iid=1)], {"a1": 1}, max_rounds=3))
        b = asyncio.ensure_future(eng.lab_enter(LAB, [leg(iid=2)], {"a1": 1}, max_rounds=3))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gate.set()
        return await a, await b

    first, second = (o["accounts"]["a1"] for o in run(both()))
    assert first == {"ok": True, "round": 1, "reason": None}
    assert second == {"ok": False, "round": None, "reason": "One position at a time."}
    assert len(ad.brackets) == 1 and list(eng.states) == [f"{LAB}@a1"]


def test_t1_a_block_whose_position_cannot_be_read_stays(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    ad.order_status = {k: "Canceled" for k in ad.order_status}
    ad.net, ad.net_error = 0, True                                  # every order ended; the position read raises
    for _ in range(3):
        tick(eng)
    assert eng.lab_open(LAB) == ["a1"] and not events(tmp_path, "lab_carry_cleared")


def damaged_restart(eng, tmp_path, change):
    p = tmp_path / f"labday-{eng._today()}.json"
    d = json.loads(p.read_text())
    change(d)
    p.write_text(json.dumps(d))
    return restart(eng, tmp_path)


def test_n3_extras_that_are_not_a_rounds_extras_count_as_lost(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    run(eng.lab_flatten(LAB, reason="time"))
    eng2 = damaged_restart(eng, tmp_path, lambda d: d.update({f"{LAB}@a1": {"orders": "x"}}))
    clock.set_et(15, 56)
    tick(eng2)
    run(eng2.lab_flatten(LAB))
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")] and eng2.lab_open(LAB) == ["a1"]




def test_n3_marks_in_the_file_that_the_round_itself_contradicts_are_not_believed(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)

    def lie(d):
        d[f"{LAB}@a1"].update(clean=True, cancelled=["Buy"])        # "clean" while live; "no fill" on the filled side

    eng2 = damaged_restart(eng, tmp_path, lie)
    assert eng2.lab_rounds(LAB)[0]["clean"] is False and eng2.lab_open(LAB) == ["a1"]
    assert go(eng2, leg(iid=2))["accounts"]["a1"]["ok"] is False
    clock.set_et(15, 56)
    tick(eng2)
    assert markets(ad) == [("Sell", 1, "homebase:lab-flat")]        # its position is still closed at the flat time


def test_n3_a_round_marked_blind_in_the_file_is_never_clean(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    eng2 = damaged_restart(eng, tmp_path, lambda d: d[f"{LAB}@a1"].update(blind=True))
    fill_exit(eng2, ad, rnd(eng2), 110.0, "tp")
    for _ in range(3):
        tick(eng2)
    (r,) = eng2.lab_rounds(LAB)
    assert (r["status"], r["clean"], r["why"]) == ("done", False, "Check it: the Desk does not know this trade's stop order.")




def test_w1_a_failed_entry_keeps_the_venues_own_words(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ads["a1"].reject = "Insufficient funds for this order"
    out = go(eng, leg())["accounts"]["a1"]
    assert out == {"ok": False, "round": 1, "reason": "The Desk cannot check this order.",
                   "detail": "Insufficient funds for this order"}
    assert events(tmp_path, "lab_check")[0]["detail"] == "Insufficient funds for this order"


def test_s7_the_lab_calls_refuse_a_strategy_of_another_kind_and_make_no_extras_for_it(tmp_path):
    es = StrategyCfg(symbol="ES", qty=1, offset_pts=2.0, sl_pts=1.0, tp_pts=3.0, enabled=True)
    eng, ads, _ = mk(tmp_path, extra={"es930": es}, book={"es930": [{"account": "a1", "qty": 1}]})
    assert run(eng.handle_alert({"strategy": "es930", "upper": 5002.0, "lower": 4998.0}))["ok"]
    assert eng.lab_rounds("es930") == [] and eng.lab_open("es930") == [] and eng.lab_rounds("nope") == []
    assert run(eng.lab_cancel("es930")) == {} and run(eng.lab_flatten("es930")) == {}
    assert "es930@a1" not in eng.__dict__.get("_lab", {}) and eng._state("es930", "a1").status == "placed"
    assert ads["a1"].cancelled == [] and ads["a1"].orders == []


# ================================================================================================ fix round 3
LOST = "check it — this trade's record was lost: nothing is sent or cancelled for it"


def sent(ad):
    """Everything the adapter was asked to do, as counts: nothing of it may move for a block or a lost round."""
    return len(ad.orders), len(ad.brackets), len(ad.cancelled), len(ad.modified)


# ------------------------------------------------------------------------------------------------ R-A
def test_ra_a_carried_block_is_never_a_busy_state_and_keeps_what_was_known(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    (r,) = eng.lab_rounds(LAB)
    assert (r["carried"], r["date"], r["status"], r["exit_reason"]) == (True, "2026-09-14", "error", "carried")
    assert (r["entry_side"], r["qty"], r["entry_qty"], r["entry_fill"], r["sl"], r["tp"]) == ("Buy", 1, 1, 100.0, 95.0, 110.0)
    assert sorted(r["orders"]) == ["a1-101", "a1-101-sl", "a1-101-tp"] and r["iid"] == {"Buy": 1}
    block = eng.states[f"{LAB}@a1#c2026-09-14"]
    assert block.status == "error"                                  # never live, placed or placing
    assert [getattr(block, k) for k in ("upper_id", "lower_id", "up_sl_id", "up_tp_id", "dn_sl_id", "dn_tp_id")] == [None] * 6
    assert (block.entry_side, block.entry_fill, block.entry_qty) == (None, None, 0)
    moved = run(eng._move_brackets(block, eng.cfg.strategies[LAB], ad))             # and nothing of it is ever moved
    assert "carried" in moved["error"] and ad.modified == []


def test_ra_the_chart_is_free_on_an_account_with_a_block_and_nothing_of_the_desk_acts_on_it(tmp_path):
    """The reviewer's X3: the owner can place, flatten and cancel the old stop from the chart."""
    from types import SimpleNamespace

    from homebase import trading
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    desk = SimpleNamespace(cfg=eng.cfg, engine=eng, _is_chart_order=lambda aid, oid: False)
    desk._day_state = lambda aid, name: trading.ChartDesk._day_state(desk, aid, name)
    desk._not_the_bots = lambda *a: trading.ChartDesk._not_the_bots(desk, *a)
    later(clock, 30 * 60)                                           # 10:01, past the 09:20-09:35 lock of every booked bot
    trading.ChartDesk._lock(desk, "a1", "NQZ6", "A1")                                # an order, a flatten: allowed
    trading.ChartDesk._lock(desk, "a1", "NQZ6", "A1", cancel_oid=f"{st.upper_id}-sl")   # a cancel of the old stop
    assert not [s for s in eng.day_states_for_account("a1") if s.status in trading.BOT_BUSY]
    before = sent(ad)
    assert run(eng.kill_strategy(LAB))["a1"]["ok"] is False
    assert run(eng.flatten_strategy(LAB)) == {} and run(eng.lab_flatten(LAB)) == {} and run(eng.lab_cancel(LAB)) == {}
    assert run(eng.flatten_today()) == {} and run(eng.reconcile_account("a1")) == {}
    later(clock, 6 * 3600)                                          # past the flat time, the same day
    tick(eng)
    assert sent(ad) == before and eng.lab_open(LAB) == ["a1"] and eng.day_status(LAB) == "idle"


def test_ra_a_fill_on_the_account_is_never_booked_to_a_block(tmp_path):
    """The reviewer's M1: the owner closes the old position by hand and opens a NEW short. Not the block's exit."""
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    ad.net, ad.order_status = -1, {}
    run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=130.0,
                              raw={"orderId": "by-hand-at-the-broker"})))
    run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=95.0,
                              raw={"orderId": f"{st.upper_id}-sl"})))          # and a push for its own old stop
    block = eng.states[f"{LAB}@a1#c2026-09-14"]
    assert (block.status, block.exit_fill, block.pnl, block.exit_qty) == ("error", None, None, 0)
    assert eng.book("a1").closes == 0 and eng.book("a1").closed_net == 0
    assert not [e for e in events(tmp_path, "exit_fill") if e["et"].startswith("2026-09-15")]
    assert eng.lab_open(LAB) == ["a1"]


def test_ra_an_order_of_a_block_that_fills_is_written_down_and_changes_nothing(tmp_path):
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    tick(eng)                                                       # the first read: what was filled already
    assert not events(tmp_path, "lab_carry_fill")                   # (its entry, yesterday) is not news
    ad.order_status[f"{st.upper_id}-sl"], ad.filled[f"{st.upper_id}-sl"] = "Filled", 1
    before = sent(ad)
    tick(eng)
    tick(eng)
    (f,) = events(tmp_path, "lab_carry_fill")
    assert (f["strategy"], f["account"], f["date"], f["order_id"], f["side"], f["qty"]) == \
        (LAB, "a1", "2026-09-14", "a1-101-sl", "Sell", 1)
    assert sent(ad) == before and eng.lab_open(LAB) == ["a1"]       # the account still holds the market (net 1)
    assert eng.states[f"{LAB}@a1#c2026-09-14"].status == "error"


def test_ra_check_takes_and_reconcile_neither_act_on_nor_because_of_a_block(tmp_path):
    es = StrategyCfg(symbol="ES", qty=1, offset_pts=2.0, sl_pts=1.0, tp_pts=3.0, enabled=True)
    eng, ads, clock = mk(tmp_path, extra={"es930": es}, book={"es930": [{"account": "a1", "qty": 1}]})
    ad = ads["a1"]
    live_round(eng, ad)
    next_day(clock)
    assert eng.lab_open(LAB) == ["a1"]
    assert run(eng.handle_alert({"strategy": "es930", "upper": 5002.0, "lower": 4998.0}))["ok"]
    other = eng._state("es930", "a1")
    run(eng.on_fill(FillEvent(account_id="a1", symbol="ESZ6", side="Buy", qty=1, price=5002.0,
                              raw={"orderId": other.upper_id})))
    eng.cfg.strategies["es930"].day_take = 50.0                     # a take rule on the account, after the block
    block = eng.states[f"{LAB}@a1#c2026-09-14"]
    eng._mono = lambda: 1000.0
    assert run(eng.check_takes({"ES": 5010.0})) == []               # the touch is seen (no NQ price is asked for) ...
    eng._mono = lambda: 1010.0
    (hit,) = run(eng.check_takes({"ES": 5010.0}))                   # ... and after the grace the take flattens es930
    assert list(hit["actions"]) == ["es930"] and (other.status, other.exit_reason) == ("done", "day_take")
    assert (block.status, block.exit_reason) == ("error", "carried")
    assert run(eng.reconcile_account("a1")) == {} and (block.status, block.exit_reason) == ("error", "carried")


# ------------------------------------------------------------------------------------------------ R-B, R-C
def test_rb_a_placed_round_whose_record_was_lost_is_hands_off_and_keeps_its_stop(tmp_path):
    """The reviewer's X1. The cancel would be accepted and the entry would keep working; the stop must be there
    when it fills."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg(move=True, rr=2.0))
    eid = rnd(eng).upper_id
    eng2 = damaged_restart(eng, tmp_path, lambda d: d.pop(f"{LAB}@a1"))
    ad.stuck = {eid}
    clock.set_et(10, 0)
    before = sent(ad)
    tick(eng2)
    tick(eng2)
    st = rnd(eng2)
    assert sent(ad) == before and st.status == "placed" and ad.order_status[f"{eid}-sl"] == "Suspended"
    (chk,) = events(tmp_path, "lab_check")
    assert chk["reason"] == "this trade's record was lost: nothing is sent or cancelled for it" and chk["account"] == "a1"
    (r,) = eng2.lab_rounds(LAB)
    assert (r["clean"], r["why"]) == (False, "The Desk cannot check the last trade's orders.")
    assert eng2.lab_open(LAB) == ["a1"]
    fill_entry(eng2, ad, st, 100.75)                                # the entry fills later, off its trigger: its stop
                                                                    # is still there, and nothing is re-priced
    assert st.status == "live" and ad.order_status[f"{eid}-sl"] == "Working" and ad.modified == []
    clock.set_et(15, 56)
    for _ in range(3):
        later(clock, 31)
        tick(eng2)
    assert run(eng2.lab_flatten(LAB))["a1"] == {"ok": False, "sold": 0, "actions": [LOST]}
    assert run(eng2.lab_cancel(LAB))["a1"] == {"ok": False, "state": "working", "actions": [LOST]}
    assert run(eng2.kill_strategy(LAB))["a1"] == {"ok": False, "actions": [LOST]}
    assert run(eng2.flatten_today()) == {}                          # the Kill's own account sweep is the backstop
    assert ad.orders == [] and ad.cancelled == [] and ad.order_status[f"{eid}-sl"] == "Working"
    assert not [e for e in events(tmp_path) if e["event"].startswith("clock_flat")]
    assert len(events(tmp_path, "lab_check")) == 1 and st.status == "live"
    eng3 = restart(eng2, tmp_path)                                  # said once, also over another restart
    eng3.lab_rounds(LAB)
    assert len(events(tmp_path, "lab_check")) == 1


def test_rb_a_lost_round_is_carried_as_a_block_at_the_day_roll(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    eng2 = damaged_restart(eng, tmp_path, lambda d: d.update({f"{LAB}@a1": [1]}))
    assert eng2.lab_open(LAB) == ["a1"]
    next_day(clock)
    (r,) = eng2.lab_rounds(LAB)
    assert (r["carried"], r["status"], r["date"]) == (True, "error", "2026-09-14")
    assert sorted(r["orders"]) == ["a1-101", "a1-101-sl", "a1-101-tp"]


@pytest.mark.parametrize("mark", [{"closing": "time", "close_sent_ms": 0}, {"gone_ms": -1}])
def test_rc_a_round_is_never_ended_on_a_position_read_while_an_entry_still_works(tmp_path, mark):
    """Extras there, the close fact damaged (a close MAY be out, or the round "read flat"), the round only placed:
    the retry may cancel the entry, but while it still reads working nothing is ended and its stop is not cancelled."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    eid = rnd(eng).upper_id
    eng2 = damaged_restart(eng, tmp_path, lambda d: d[f"{LAB}@a1"].update(mark))
    ad.stuck = {eid}
    clock.set_et(15, 56)
    for _ in range(3):
        later(clock, 31)
        tick(eng2)
    st = rnd(eng2)
    assert st.status == "placed" and ad.orders == []
    assert eid in ad.cancelled                                      # the entry's cancel is asked for (always safe) ...
    assert ad.order_status[f"{eid}-sl"] == "Suspended" and f"{eid}-sl" not in ad.cancelled    # ... its stop never
    assert "check it" in events(tmp_path, "clock_flat_failed")[0]["actions"][-1]
    assert "is not ended at the broker" in events(tmp_path, "clock_flat_failed")[0]["actions"][-1]
    out = run(eng2.kill_strategy(LAB))["a1"]                        # the Kill's Lab path: the same rule
    assert out["ok"] is False and st.status == "placed" and f"{eid}-sl" not in ad.cancelled


def test_rc_the_settle_never_cancels_a_stop_while_an_entry_of_the_round_still_works(tmp_path):
    eng, ads, _ = mk(tmp_path)
    ad = ads["a1"]
    go(eng, leg())
    st = rnd(eng)
    run(eng._lock_account("a1", "day_lock", why="test"))            # ends the round at once; the cancel is refused
    for k in ("", "-sl", "-tp"):
        ad.order_status[f"{st.upper_id}{k}"] = "Working" if not k else "Suspended"
    ad.stuck = {st.upper_id}
    n = len(ad.cancelled)
    for _ in range(3):
        tick(eng)
    assert set(ad.cancelled[n:]) == {st.upper_id}                   # the entry is asked again; its stop is left
    assert ad.order_status[f"{st.upper_id}-sl"] == "Suspended" and rows(eng)[0]["clean"] is False


# ------------------------------------------------------------------------------------------------ R-D
def test_rd_a_block_is_not_cleared_while_one_of_its_orders_still_works(tmp_path):
    """The reviewer's X2: flat by hand, the old stop left working. Clearing would let it fill into a new trade."""
    eng, ad, clock, st = unresolved_day_one(tmp_path)
    next_day(clock)
    eng.lab_open(LAB)
    ad.net = 0
    before = sent(ad)
    out = run(eng.lab_clear_block(LAB, "a1"))
    assert out == {"ok": False, "reason": "An old order of this trade is still working. Cancel it first.",
                   "orders": ["a1-101-sl", "a1-101-tp"]}
    assert eng.lab_open(LAB) == ["a1"] and sent(ad) == before and not events(tmp_path, "lab_carry_cleared")
    ad.order_status["a1-101-sl"] = "Canceled"
    ad.order_status.pop("a1-101-tp")                                # one that no longer reads does not stop it
    assert run(eng.lab_clear_block(LAB, "a1"))["ok"] is True and sent(ad) == before


# ------------------------------------------------------------------------------------------------ M2, M3
def test_m2_one_lagging_position_read_does_not_cost_the_account_the_day(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ghost_close(eng, ad)
    fill_exit(eng, ad, st, 101.0, by="market")                      # the close did fill, alone
    for k in ("sl", "tp"):
        ad.order_status[f"{st.upper_id}-{k}"] = "Canceled"
    lag, real = [1], ad.get_net_position

    async def late(symbol):
        return lag.pop() if lag else await real(symbol)

    ad.get_net_position = late
    for _ in range(4):
        later(clock, 3)
        tick(eng)
    assert (rows(eng)[0]["clean"], rows(eng)[0]["why"]) == (True, None)
    assert not events(tmp_path, "lab_check")[1:]                    # only the unconfirmed close itself was said


@pytest.mark.parametrize("damage", [("date", None), ("date", 5), ("date", "not a day"), ("status", "idle"),
                                    ("status", "weird"), ("entry_qty", -1), ("qty", -3), ("entry_fill", "x"),
                                    ("account", "zz"), ("upper_id", 7)])
def test_m3_a_damaged_row_of_yesterday_is_carried_unread_never_dropped(tmp_path, damage):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    live_round(eng, ad)
    p = tmp_path / f"day-{eng._today()}.json"
    d = json.loads(p.read_text())
    d[f"{LAB}@a1"][damage[0]] = damage[1]
    p.write_text(json.dumps(d))
    next_day(clock)
    eng2 = restart(eng, tmp_path)
    before = sent(ad)
    assert eng2.lab_open(LAB) == ["a1"]
    (r,) = eng2.lab_rounds(LAB)
    assert (r["carried"], r["why"]) == (True, "The Desk cannot read yesterday's record for this account.")
    (c,) = events(tmp_path, "lab_carry")
    assert c["unread"] is True and c["account"] == "a1"
    run(eng2.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=95.0, raw={"orderId": "a1-101-sl"})))
    tick(eng2)
    assert go(eng2, leg(iid=9))["accounts"]["a1"]["ok"] is False and sent(ad) == before


# ------------------------------------------------------------------------------------------------ G1, G2
@pytest.mark.parametrize("field,value", [("entry_qty", -1), ("exit_qty", -2), ("qty", "x"), ("entry_fill", float("inf")),
                                         ("exit_fill", "x"), ("sl_px", float("nan"))])
def test_g1_a_damaged_number_in_todays_day_file_makes_a_block_and_never_raises(tmp_path, field, value):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    p = tmp_path / f"day-{eng._today()}.json"
    d = json.loads(p.read_text())
    d[f"{LAB}@a1"][field] = value
    p.write_text(json.dumps(d))
    eng2 = restart(eng, tmp_path)
    before = sent(ad)
    assert eng2.lab_open(LAB) == ["a1"]                             # the first Lab call takes the state out of play
    for side, oid in (("Buy", st.upper_id), ("Sell", f"{st.upper_id}-sl"), ("Sell", "plain")):
        run(eng2.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side=side, qty=1, price=99.0, raw={"orderId": oid})))
    clock.set_et(15, 56)
    tick(eng2)
    run(eng2.lab_flatten(LAB))
    run(eng2.kill_strategy(LAB))
    assert not events(tmp_path, "clock_error") and sent(ad) == before
    (r,) = eng2.lab_rounds(LAB)
    assert (r["carried"], r["clean"]) == (True, False)
    assert r["why"] == "The Desk cannot read yesterday's record for this account."


def test_g2_a_new_round_settles_on_the_fast_schedule_again(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    key = f"{LAB}@a1"
    trade(eng, ad)
    eng.__dict__.setdefault("_lab_tries", {})[key] = 9              # what a round that never got clean leaves behind
    eng.__dict__.setdefault("_lab_tries", {})[f"carry:{key}#c2026-09-13"] = 20
    go(eng, leg(iid=2))
    assert key not in eng._lab_tries
    st = rnd(eng)
    fill_entry(eng, ad, st, 100.0)
    fill_exit(eng, ad, st, 110.0, "tp")
    ad.order_status[f"{st.upper_id}-sl"] = "Working"                # the broker's cancel of the stop lags one read
    run(eng.clock_tick())
    assert rows(eng)[-1]["clean"] is False
    eng._retry_at[f"settle:{key}"] -= 2.5                           # 2.5 s later: the fast schedule reads again
    run(eng.clock_tick())
    assert rows(eng)[-1]["clean"] is True


# ------------------------------------------------------------------------------------------------ T1
def test_t1_the_older_close_key_carries_its_time_over_and_the_round_stays_a_round(tmp_path):
    """A file of the first build: `closing` + `closing_ms`. The time moves to close_sent_ms as it is; the round is
    not marked for it, and its close is simply out (waiting for its fill), never sent again."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    run(eng.lab_flatten(LAB, reason="time"))
    t_sent = eng._lab_x(st)["close_sent_ms"]

    def old_build(d):
        x = d[f"{LAB}@a1"]
        x["closing_ms"] = x.pop("close_sent_ms")
        for k in ("close_ok", "close_id", "blind", "carry", "lost", "lost_said", "net_bad", "net_bad_ms"):
            x.pop(k, None)

    eng2 = damaged_restart(eng, tmp_path, old_build)
    x = eng2._lab_x(rnd(eng2))
    assert x["close_sent_ms"] == t_sent and "closing_ms" not in x and x["check"] is False and x["unconfirmed"] is False
    later(clock, 1)
    assert run(eng2.lab_flatten(LAB))["a1"] == {"ok": True, "sold": 0,
                                                "actions": ["the close order is out: waiting for its fill"]}
    fill_exit(eng2, ad, rnd(eng2), 101.0, by="market")
    tick(eng2)
    assert (rnd(eng2).exit_reason, eng2.lab_rounds(LAB)[0]["clean"]) == ("time", True) and len(ad.orders) == 1


def test_t1_no_order_id_of_a_carried_pair_is_on_the_blocks_state(tmp_path):
    """After R-A a block holds no order id at all, so neither entry of yesterday's pair can ever be matched by
    on_fill as a fill of the Desk's; both ids are in the block's list, where they are read."""
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    go(eng, pair())
    st = rnd(eng)
    fill_entry(eng, ad, st, 110.0, side="Buy")                      # live long; the sell stop was cancelled
    next_day(clock)
    (r,) = eng.lab_rounds(LAB)
    assert {"a1-101", "a1-102"} <= set(r["orders"])
    block = eng.states[f"{LAB}@a1#c2026-09-14"]
    assert block.upper_id is None and block.lower_id is None
    before = sent(ad)
    run(eng.on_fill(FillEvent(account_id="a1", symbol="NQZ6", side="Sell", qty=1, price=90.0, raw={"orderId": "a1-102"})))
    assert (block.status, block.exit_reason) == ("error", "carried") and sent(ad) == before
    assert not events(tmp_path, "both_filled_emergency")
