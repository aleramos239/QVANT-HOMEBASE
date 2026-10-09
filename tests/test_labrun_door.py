"""The door: pure checks that say in one sentence why an order would be refused."""
from __future__ import annotations

import glob
import os

import pytest

from homebase.labrun import door
from homebase.labrun.door import check, check_event, read_source

STATE = {"flat": True, "working_entries": 0, "entries_today": 0, "last_price": 100.0, "now_hhmm": "09:30",
         "prices_late": False}
LIMITS = {"max_trades_day": 1, "max_qty": 4, "max_risk_usd": 0.0, "last_entry_et": "15:30",
          "session_from_et": "09:00", "point_value": 20.0, "tick": 0.25}


def entry(**kw) -> dict:
    d = {"op": "entry", "id": 1, "kind": "stop", "side": "long", "price": 101.0, "qty": 1, "own_qty": False,
         "sl": 100.0, "tp": 103.0, "tp_rr": None, "ref": 101.0, "move": False}
    d.update(kw)
    return d


def ask(intent, **kw):
    state = {**STATE, **{k: v for k, v in kw.items() if k in STATE}}
    limits = {**LIMITS, **{k: v for k, v in kw.items() if k in LIMITS}}
    return check(intent, state, limits)


def test_a_good_entry_is_allowed():
    assert ask(entry()) is None
    assert ask(entry(kind="market", price=None, ref=None, side="short", sl=101.0, tp=99.0)) is None


@pytest.mark.parametrize("op", [{"op": "cancel", "id": 3}, {"op": "flatten", "reason": "time"},
                                {"op": "plot", "name": "a", "t_ms": 1, "value": 2.0},
                                {"op": "hline", "name": "a", "price": 1.0, "role": "level", "t_ms": 1},
                                {"op": "skip", "reason": "x"}])
def test_other_ops_are_always_allowed(op):
    assert ask(op, flat=False, entries_today=9, prices_late=True, now_hhmm="23:59") is None


def test_a_lone_oco_intent_is_judged_with_its_entries_in_check_event():
    assert ask({"op": "oco", "ids": [1, 2]}) is None


def test_no_stop():
    assert ask(entry(sl=None)) == "Every entry needs a stop held at the broker."


@pytest.mark.parametrize("kw", [
    dict(sl=102.0),                                  # long: stop above the entry
    dict(sl=101.0),                                  # on the entry is not on the losing side
    dict(tp=100.5),                                  # long: target below the entry
    dict(side="short", sl=100.0, tp=99.0),           # short: stop below
    dict(side="short", sl=102.0, tp=104.0),          # short: target above
])
def test_stop_on_the_wrong_side(kw):
    assert ask(entry(**kw)) == "The stop must sit on the losing side of the entry."


def test_a_market_entry_is_judged_from_ref_else_last_price_else_refused():
    m = dict(kind="market", price=None)
    assert ask(entry(**m, ref=105.0, sl=104.0, tp=106.0), last_price=100.0) is None      # ref wins over last_price
    assert ask(entry(**m, ref=105.0, sl=102.0, tp=None), last_price=100.0) is None
    assert ask(entry(**m, ref=105.0, sl=106.0, tp=None), last_price=100.0) == "The stop must sit on the losing side of the entry."
    assert ask(entry(**m, ref=None, sl=99.0, tp=101.0), last_price=100.0) is None        # last_price when no ref
    assert ask(entry(**m, ref=None, sl=101.0), last_price=100.0) == "The stop must sit on the losing side of the entry."
    assert ask(entry(**m, ref=None, sl=99.0), last_price=None) == "The stop must sit on the losing side of the entry."


def test_no_target_is_fine():
    assert ask(entry(tp=None)) is None


def test_limit_entries_are_not_built():
    assert ask(entry(kind="limit", price=100.5, sl=99.0)) == "Limit entries are not built yet."


@pytest.mark.parametrize("kw", [dict(flat=False), dict(working_entries=1)])
def test_one_position_at_a_time(kw):
    assert ask(entry(), **kw) == "One position at a time."


def test_daily_limit_and_its_plural():
    assert ask(entry(), entries_today=1, max_trades_day=1) == "Daily limit reached (1 trade)."
    assert ask(entry(), entries_today=3, max_trades_day=3) == "Daily limit reached (3 trades)."
    assert ask(entry(), entries_today=2, max_trades_day=3) is None


def test_own_size():
    assert ask(entry(own_qty=True)) == "Size is set on the Desk, per account."


def test_stop_too_far():
    far = entry(sl=50.0, qty=2, tp=None)             # 51 pts * $20 * 2 = $2,040
    assert ask(far, max_risk_usd=1000.0) == "Stop too far: $2,040 at risk, limit $1,000."
    assert ask(far, max_risk_usd=0.0) is None        # 0 = not set
    assert ask(far, max_risk_usd=2040.0) is None     # equal is within the limit
    assert ask(entry(sl=101.0 - 62.5, qty=1, tp=None), max_risk_usd=1000.0) == \
        "Stop too far: $1,250 at risk, limit $1,000."
    assert ask(entry(sl=50.98, qty=1, tp=None), max_risk_usd=1000.0) == \
        "Stop too far: $1,001 at risk, limit $1,000."          # $1,000.40 never reads as equal to the limit


def test_too_late_and_too_early():
    assert ask(entry(), now_hhmm="15:30") is None
    assert ask(entry(), now_hhmm="15:31") == "Too late for a new trade today."
    assert ask(entry(), now_hhmm="09:00") is None
    assert ask(entry(), now_hhmm="08:59") == "Too late for a new trade today."


def test_prices_late():
    assert ask(entry(), prices_late=True) == "Prices are late."


def test_the_first_failing_check_wins_in_this_order():
    bad = dict(flat=False, entries_today=5, now_hhmm="20:00", prices_late=True, max_risk_usd=1.0)
    e = entry(kind="limit", sl=None, own_qty=True)
    assert ask(e, **bad) == "Limit entries are not built yet."
    e["kind"] = "stop"
    assert ask(e, **bad) == "Every entry needs a stop held at the broker."
    e["sl"] = 105.0
    assert ask(e, **bad) == "The stop must sit on the losing side of the entry."
    e["sl"] = 99.0
    assert ask(e, **bad) == "Size is set on the Desk, per account."
    e["own_qty"] = False
    assert ask(e, **bad) == "One position at a time."
    bad["flat"] = True
    assert ask(e, **bad) == "Daily limit reached (1 trade)."
    assert ask(e, **{**bad, "max_trades_day": 5}) == "Daily limit reached (5 trades)."
    assert ask(e, **{**bad, "max_trades_day": 9}) == "Too late for a new trade today."
    assert ask(e, **{**bad, "max_trades_day": 9, "now_hhmm": "10:00"}) == \
        "Stop too far: $40 at risk, limit $1."
    assert ask(e, **{**bad, "max_trades_day": 9, "now_hhmm": "10:00", "max_risk_usd": 0.0}) == "Prices are late."


# ---------------------------------------------------------------- check_event

def straddle(**kw):
    up = entry(id=1, side="long", price=101.0, sl=100.0, tp=103.0, **kw)
    dn = entry(id=2, side="short", price=99.0, sl=100.0, tp=97.0, **kw)
    return [up, dn, {"op": "oco", "ids": [1, 2]}]


def test_an_oco_pair_is_one_trade_and_the_legs_do_not_refuse_each_other():
    assert check_event(straddle(), STATE, LIMITS) == [None, None, None]


def test_a_pair_counts_once_against_the_daily_limit():
    assert check_event(straddle(), {**STATE, "entries_today": 2}, {**LIMITS, "max_trades_day": 3}) == [None] * 3
    assert check_event(straddle(), {**STATE, "entries_today": 3}, {**LIMITS, "max_trades_day": 3}) == \
        ["Daily limit reached (3 trades)."] * 2 + [None]


def test_the_oco_intent_may_come_before_its_entries():
    a, b, o = straddle()
    assert check_event([o, a, b], STATE, LIMITS) == [None, None, None]


def test_pair_legs_still_get_their_own_sentences():
    a, b, o = straddle()
    b["sl"] = None
    assert check_event([a, b, o], STATE, LIMITS) == [None, "Every entry needs a stop held at the broker.", None]


def test_a_lone_entry_makes_the_next_one_in_the_same_event_refuse():
    a = entry(id=1)
    b = entry(id=2, side="short", price=99.0, sl=100.0, tp=97.0)
    assert check_event([a, b], STATE, {**LIMITS, "max_trades_day": 5}) == [None, "One position at a time."]


def test_a_refused_entry_does_not_use_up_the_slot():
    a = entry(id=1, sl=None)
    b = entry(id=2)
    assert check_event([a, b], STATE, LIMITS) == ["Every entry needs a stop held at the broker.", None]


def test_the_callers_state_is_not_changed():
    state = dict(STATE)
    check_event(straddle(), state, LIMITS)
    assert state == STATE


NOT_A_PAIR = "Only a buy-stop and sell-stop pair can be linked."
LONE = "One position at a time."


@pytest.mark.parametrize("fix, want", [
    (lambda a, b: b.update(side="long", price=102.0, sl=101.0, tp=104.0), [None, LONE, NOT_A_PAIR]),   # two buys
    (lambda a, b: b.update(qty=2), [None, LONE, NOT_A_PAIR]),                                          # sizes differ
    (lambda a, b: b.update(kind="market", price=None, ref=99.0), [None, LONE, NOT_A_PAIR]),            # a market leg
    (lambda a, b: a.update(kind="limit"), ["Limit entries are not built yet.", None, NOT_A_PAIR]),     # a limit leg
])
def test_an_oco_that_is_not_a_buy_stop_and_sell_stop_pair_is_refused(fix, want):
    a, b, o = straddle()
    fix(a, b)
    assert check_event([a, b, o], STATE, {**LIMITS, "max_trades_day": 5}) == want


def test_an_oco_with_the_wrong_ids_or_count_is_refused():
    a, b, _ = straddle()
    for ids in ([1], [1, 2, 3], [1, 9], [1, 1]):
        got = check_event([a, b, {"op": "oco", "ids": ids}], STATE, {**LIMITS, "max_trades_day": 5})
        assert got[2] == "Only a buy-stop and sell-stop pair can be linked."
        assert got[1] == "One position at a time."               # judged as lone entries


def test_an_invalid_oco_judges_its_entries_as_lone_ones():
    a, b, o = straddle()
    b["qty"] = 3
    got = check_event([a, b, o], STATE, {**LIMITS, "max_trades_day": 5})
    assert got == [None, "One position at a time.", "Only a buy-stop and sell-stop pair can be linked."]


def test_one_verdict_per_intent_in_order():
    intents = [{"op": "plot", "name": "a", "t_ms": 1, "value": 1.0}, entry(id=1), {"op": "skip", "reason": "x"},
               {"op": "cancel", "id": 1}, {"op": "flatten", "reason": "time"}]
    assert check_event(intents, STATE, LIMITS) == [None] * 5
    assert check_event([], STATE, LIMITS) == []


# ---------------------------------------------------------------- read_source

def calls(*lines: str) -> str:
    return "class S:\n    def on_time(self, ctx, t):\n" + "".join(f"        {ln}\n" for ln in lines)


def test_a_clean_source_has_no_notes():
    assert read_source(calls("ctx.market('long', sl=1.0)", "ctx.stop_entry('short', 5.0, sl=6.0)")) == []
    assert read_source("") == []


def test_no_stop_one_and_many():
    assert read_source(calls("ctx.market('long')")) == ["1 order can go out with no stop."]
    assert read_source(calls("ctx.market('long', sl=None)", "ctx.stop_entry('long', 5.0, sl=1.0)")) == \
        ["1 order can go out with no stop."]
    assert read_source(calls("ctx.market('long')", "ctx.stop_entry('short', 5.0)", "ctx.limit_entry('long', 4.0)")) == \
        ["3 orders can go out with no stop.", "It uses limit entries: not built yet."]


def test_a_conditional_stop_with_a_none_branch_counts():
    assert read_source(calls("ctx.market('long', sl=None if x else 5.0)")) == ["1 order can go out with no stop."]
    assert read_source(calls("ctx.market('long', sl=5.0 if x else None)")) == ["1 order can go out with no stop."]
    assert read_source(calls("ctx.market('long', sl=5.0 if x else 6.0)")) == []


def test_a_stop_given_by_position_counts_as_a_stop():
    assert read_source(calls("ctx.stop_entry('long', 5.0, None, 4.0)")) == []
    assert read_source(calls("ctx.market('long', None, 4.0)")) == []
    assert read_source(calls("ctx.market('long', None, None)")) == ["1 order can go out with no stop."]


def test_limit_entries():
    assert read_source(calls("ctx.limit_entry('long', 4.0, sl=3.0)")) == ["It uses limit entries: not built yet."]


def test_own_size():
    note = "It sets its own size: size is set on the Desk."
    assert read_source(calls("ctx.market('long', qty=3, sl=1.0)")) == [note]
    assert read_source(calls("ctx.stop_entry('long', 5.0, 3, sl=4.0)")) == [note]
    assert read_source(calls("ctx.market('long', qty=None, sl=1.0)")) == []


def test_all_three_notes_in_order():
    src = calls("ctx.limit_entry('long', 4.0, qty=2)")
    assert read_source(src) == ["1 order can go out with no stop.", "It uses limit entries: not built yet.",
                                "It sets its own size: size is set on the Desk."]


def test_other_calls_are_ignored():
    assert read_source(calls("ctx.plot('a', 1, 2)", "ctx.flatten()", "market('long')", "ctx.hline('x', 1.0, qty=3)",
                             "ctx.cancel(o)")) == []


def test_a_syntax_error_is_one_note():
    notes = read_source("def (:\n")
    assert len(notes) == 1 and notes[0].startswith("The code does not read: ") and notes[0].endswith(".")


def test_read_source_never_runs_the_text(tmp_path):
    marker = tmp_path / "ran"
    read_source(f"open({str(marker)!r}, 'w').write('x')\nimport os\nos._exit(3)\n")
    assert not marker.exists()


def test_every_real_draft_reads_without_raising():
    files = sorted(glob.glob(os.path.expanduser("~/.homebase/strategies/*.py")))
    if not files:
        pytest.skip("no drafts folder on this machine")
    for f in files:
        with open(f, encoding="utf-8") as fh:
            notes = read_source(fh.read())
        assert isinstance(notes, list) and all(isinstance(n, str) for n in notes), f


def test_the_module_imports_nothing_from_homebase():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(door))
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            assert n.level == 0 and not (n.module or "").startswith("homebase")
        if isinstance(n, ast.Import):
            assert not any(a.name.startswith("homebase") for a in n.names)
