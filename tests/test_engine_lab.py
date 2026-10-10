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
