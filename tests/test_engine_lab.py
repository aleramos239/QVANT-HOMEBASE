"""Engine rounds for kind "lab" (Step B, task B2): several trades a day, one position at a time, the capped
flatten, the clock, restarts -- and the proof that the seven hooks are no-ops for every other kind.

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
    assert not (tmp_path / f"labday-{eng._today()}.json").exists()


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
    ad.reject = "margin"
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
    ads["a1"].reject = "Order rejected: not enough margin"
    out = go(eng, leg())
    assert out["accounts"]["a1"] == {"ok": False, "round": 1,
                                     "reason": "The broker refused it: Order rejected: not enough margin"}
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
    assert rows(eng)[0]["clean"] is True and rows(eng)[0]["why"] is None
    assert go(eng, leg(iid=2))["accounts"]["a1"]["ok"] is True


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
    assert rows(eng)[0]["clean"] is True


def test_the_flat_time_retry_waits_five_seconds_and_sells_once_it_can_read(tmp_path):
    eng, ads, clock = mk(tmp_path)
    ad = ads["a1"]
    st = live_round(eng, ad)
    ad.net_error = True
    clock.set_et(15, 55)
    run(eng.clock_tick())
    run(eng.clock_tick())                                             # inside the 5 s: no second read
    assert ad.net_reads == 1 and ad.orders == []
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
    tick(eng2)                                                        # the flat time still closes the other one
    assert [(o.side, o.qty, o.text) for o in ads["a2"].orders] == [("Sell", 1, "homebase:lab-flat")]
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
