"""Step B (B3): the two small modules the desk and the runner both import -- labrun.intents (an intent's shape) and
labrun.fanout (the one strategy brain over every account's rounds). Pure: no engine, no files."""
from __future__ import annotations

import subprocess
import sys

from homebase.labrun import fanout, host, intents


# ---------------------------------------------------------------- intents
def entry(**kw):
    return {"op": "entry", "id": 3, "kind": "stop", "side": "long", "price": 110.0, "qty": 1, "own_qty": False,
            "sl": 105.0, "tp": None, "tp_rr": 2.0, "ref": 110.0, "move": True, **kw}


def test_well_formed_moved_out_of_the_host_and_the_host_still_uses_it():
    assert host.well_formed is intents.well_formed
    assert intents.ORDER_OPS == host.ORDER_OPS == ("entry", "oco", "cancel", "flatten")


def test_well_formed_takes_every_intent_of_the_contract_and_nothing_else():
    good = [entry(), entry(kind="market", price=None), {"op": "oco", "ids": [3, 4]}, {"op": "cancel", "id": 2},
            {"op": "flatten", "reason": "time"}, {"op": "skip", "reason": "x"},
            {"op": "plot", "name": "vwap", "t_ms": 1, "value": 2.5},
            {"op": "hline", "name": "hi", "price": 1.0, "role": "level", "t_ms": 1}]
    assert all(intents.well_formed(i) for i in good)
    bad = [None, 5, {}, {"op": "nope"}, entry(id="3"), entry(id=True), entry(kind="iceberg"), entry(side="up"),
           entry(price=None), entry(kind="market"), entry(qty=0), entry(qty=1.0), entry(qty=10_001), entry(move=1),
           entry(sl=float("nan")), entry(tp=float("inf")), entry(tp_rr="2"), {"op": "oco", "ids": []},
           {"op": "oco", "ids": [1, "2"]}, {"op": "cancel", "id": None}, {"op": "flatten"},
           {"op": "stop", "why": "x", "flatten": True}]              # `stop` is the runner's, never a child's
    assert not any(intents.well_formed(i) for i in bad)


def test_a_stop_is_the_only_op_the_runner_adds():
    assert intents.well_formed_stop({"op": "stop", "why": "Strategy error: boom", "flatten": True})
    assert intents.well_formed_stop({"op": "stop", "why": "", "flatten": False})
    for bad in (None, {}, {"op": "stop"}, {"op": "stop", "why": 5, "flatten": True}, {"op": "stop", "why": "x", "flatten": 1},
                {"op": "flatten", "reason": "x"}):
        assert not intents.well_formed_stop(bad)


def test_the_two_modules_are_stdlib_only():
    code = ("import sys; import homebase.labrun.intents, homebase.labrun.fanout\n"
            "bad = sorted(m for m in sys.modules if m.startswith('homebase.') and m not in "
            "('homebase.labrun', 'homebase.labrun.intents', 'homebase.labrun.fanout'))\n"
            "print(bad); sys.exit(1 if bad else 0)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


# ---------------------------------------------------------------- the brain
def row(account="a1", n=1, status="placed", iid=None, qty=1, side=None, entry_qty=0, fill=None, exit_qty=0, sl=None,
        tp=None, cancelled=(), entry_ms=None, clean=False, carried=False, **kw):
    """One row of engine.lab_rounds."""
    return {"account": account, "round": n, "status": status, "date": "2026-09-14", "carried": carried,
            "iid": {"Buy": 3} if iid is None else iid, "qty": qty, "entry_side": side, "entry_qty": entry_qty,
            "entry_fill": fill, "exit_qty": exit_qty, "exit_fill": None, "exit_reason": None, "sl": sl, "tp": tp,
            "pnl": None, "clean": clean, "entry_ms": entry_ms, "exit_ms": None, "why": None,
            "cancelled": list(cancelled), "closing": None, "placed_ms": 1000 * n, "orders": [], **kw}


PAIR = {"Buy": 3, "Sell": 4}


def test_no_rounds_is_a_flat_brain_with_nothing_working():
    assert fanout.brain([], 0) == {"flat": True, "working": 0, "entries_today": 0, "orders": {}}
    assert fanout.brain(None, 2)["entries_today"] == 2


def test_a_resting_entry_is_working_and_the_brain_is_still_flat():
    b = fanout.brain([row()], 1)
    assert b == {"flat": True, "working": 1, "entries_today": 1, "orders": {"3": {"status": "working"}}}
    assert fanout.brain([row(status="placing")], 1)["orders"] == {"3": {"status": "working"}}


def test_a_filled_entry_reports_that_accounts_fill_and_levels():
    b = fanout.brain([row(status="live", side="Buy", entry_qty=1, fill=110.5, sl=105.5, tp=120.5, entry_ms=77)], 1)
    assert b["orders"] == {"3": {"status": "filled", "fill_px": 110.5, "fill_sl": 105.5, "fill_tp": 120.5, "fill_ms": 77}}
    assert b["flat"] is False and b["working"] == 0


def test_the_first_account_that_filled_is_the_one_reported():
    rows = [row("a1", status="live", side="Buy", entry_qty=1, fill=110.75, sl=105.75, entry_ms=90),
            row("a2", status="live", side="Buy", entry_qty=1, fill=110.25, sl=105.25, entry_ms=80)]
    assert fanout.brain(rows, 1)["orders"]["3"] == {"status": "filled", "fill_px": 110.25, "fill_sl": 105.25,
                                                    "fill_tp": None, "fill_ms": 80}
    # with no times the order of the rows decides (oldest first, as the engine gives them)
    rows = [dict(r, entry_ms=None) for r in rows]
    assert fanout.brain(rows, 1)["orders"]["3"]["fill_px"] == 110.75


def test_a_part_fill_is_working_until_the_rest_is_ended():
    part = row(status="live", qty=2, side="Buy", entry_qty=1, fill=110.5, sl=105.5, entry_ms=5)
    b = fanout.brain([part], 1)
    assert b["orders"]["3"] == {"status": "working"} and b["flat"] is False and b["working"] == 1
    done = dict(part, status="done", exit_qty=1)
    assert fanout.brain([done], 1)["orders"]["3"]["status"] == "filled"


def test_an_order_is_cancelled_only_when_every_account_ended_it_with_no_fill():
    one = [row("a1", status="done", cancelled=["Buy"]), row("a2", status="placed")]
    assert fanout.brain(one, 1)["orders"]["3"] == {"status": "working"}
    both = [row("a1", status="done", cancelled=["Buy"]), row("a2", status="error")]     # cancelled, and rejected
    b = fanout.brain(both, 1)
    assert b["orders"]["3"] == {"status": "cancelled"} and b["working"] == 0 and b["flat"] is True


def test_the_other_leg_of_a_pair_is_cancelled_once_one_leg_fills_on_any_account():
    rows = [row("a1", iid=PAIR, status="live", side="Buy", entry_qty=1, fill=110.5, sl=105.5, entry_ms=5),
            row("a2", iid=PAIR, status="placed")]
    b = fanout.brain(rows, 1)
    assert b["orders"]["3"]["status"] == "filled" and b["orders"]["4"] == {"status": "cancelled"}
    assert b["working"] == 0
    assert b["flat"] is False                       # a2 still rests a leg of an order already reported filled


def test_opposite_legs_filled_on_two_accounts_the_first_fill_is_the_brains(  # design I, question 15
):
    rows = [row("a1", iid=PAIR, status="live", side="Buy", entry_qty=1, fill=110.5, sl=105.5, entry_ms=50),
            row("a2", iid=PAIR, status="live", side="Sell", entry_qty=1, fill=89.5, sl=94.5, entry_ms=40)]
    b = fanout.brain(rows, 1)
    assert b["orders"]["4"]["status"] == "filled" and b["orders"]["4"]["fill_px"] == 89.5
    assert b["orders"]["3"] == {"status": "cancelled"}
    assert b["flat"] is False                       # not flat until both are out
    out = [dict(rows[0], status="done", exit_qty=1), dict(rows[1], status="done", exit_qty=1)]
    assert fanout.brain(out, 1)["flat"] is True


def test_flat_again_once_every_round_is_over():
    rows = [row("a1", status="done", side="Buy", entry_qty=1, fill=110.5, exit_qty=1, clean=True, entry_ms=5),
            row("a1", n=2, iid={"Sell": 7}, status="placed")]
    b = fanout.brain(rows, 2)
    assert b["flat"] is True and b["working"] == 1 and b["entries_today"] == 2
    assert b["orders"]["3"]["status"] == "filled" and b["orders"]["7"] == {"status": "working"}


def test_a_block_carried_from_an_earlier_day_is_not_one_of_todays_orders():
    rows = [row("a1", status="error", carried=True, side="Buy", entry_qty=1, fill=100.0, iid={"Buy": 3}),
            row("a1", n=1, iid={"Buy": 3}, status="placed")]
    b = fanout.brain(rows, 0)
    assert b["orders"] == {"3": {"status": "working"}} and b["flat"] is True
    assert fanout.brain(rows[:1], 0) == {"flat": True, "working": 0, "entries_today": 0, "orders": {}}


def test_the_latest_round_of_an_account_speaks_for_an_order_id_used_twice():
    rows = [row("a1", n=1, status="done", side="Buy", entry_qty=1, fill=100.0, exit_qty=1, entry_ms=1),
            row("a1", n=2, status="placed")]
    assert fanout.brain(rows, 2)["orders"]["3"] == {"status": "working"}


def test_rows_that_do_not_read_never_raise():
    junk = [None, 5, {}, {"iid": None, "status": "live"}, {"iid": {"Buy": "x"}, "status": "placed"},
            {"iid": {"Up": 3}, "status": "placed"}, row(qty=None, status="live", side="Buy", entry_qty=None)]
    b = fanout.brain(junk, 0)
    assert b["flat"] is False                       # a live row, whatever else it says, is a position
    assert set(b["orders"]) <= {"3"}
