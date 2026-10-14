"""Run controls (backtest/controls.py): the trade rules set on the run, enforced by the engine for any strategy."""
from __future__ import annotations

import datetime as dt
from array import array

import pytest

from homebase.backtest.controls import Controls, parse
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import Tape, et_ns
from homebase.strategies.base import Strategy

D = dt.date(2024, 3, 5)


def tape(rows, root="NQ") -> Tape:
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(D, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape(root, D, "NQH4", ts, px, array("i", [1] * len(ts)), {})


class Script(Strategy):
    id, root = "script", "NQ"
    session_window = ("09:25", "16:00")

    def __init__(self, plan):
        super().__init__({})
        self.plan = plan

    def times(self):
        return list(self.plan)

    def on_time(self, ctx, t):
        self.plan[t](ctx, self)


def go(rows, plan, ctl=None):
    return run_session(Script(plan), tape(rows), Costs(0.0, 0.0), qty=1, controls=Controls.from_dict(ctl))


def long_at(sl=None, tp=None, ref=None):
    return lambda ctx, s: ctx.market("long", sl=sl, tp=tp, ref=ref)


def short_at(sl=None, tp=None, ref=None):
    return lambda ctx, s: ctx.market("short", sl=sl, tp=tp, ref=ref)


# ---- the parse
def test_nothing_set_is_nothing():
    assert parse(None) == {} and parse({}) == {}
    assert parse({"direction": "both", "max_trades": 0, "stop_mode": "own", "entry_from": ""}) == {}
    assert Controls.from_dict({}) is None


def test_parse_drops_what_a_mode_does_not_read_and_refuses_what_is_missing():
    assert parse({"stop_mode": "own", "stop_pts": 10}) == {}
    assert parse({"stop_mode": "fixed", "stop_pts": 10, "stop_atr": 3}) == {"stop_mode": "fixed", "stop_pts": 10.0}
    with pytest.raises(ValueError, match="stop_pts"):
        parse({"stop_mode": "fixed"})
    with pytest.raises(ValueError, match="unknown"):
        parse({"nope": 1})
    with pytest.raises(ValueError, match="HH:MM"):
        parse({"entry_from": "9:30am"})
    with pytest.raises(ValueError, match="ends before"):
        parse({"entry_from": "10:00", "entry_to": "09:30"})
    with pytest.raises(ValueError, match="whole"):
        parse({"max_trades": 1.5})
    assert parse({"stop_mode": "atr", "stop_atr": 2, "atr_minutes": "15"})["atr_minutes"] == 15


def test_parse_is_idempotent():
    a = parse({"max_trades": 3, "target_mode": "rr", "target_rr": 2, "direction": "long"})
    assert parse(a) == a


# ---- the engine
ROWS = [("09:29:59", 100.0), ("09:30:05", 100.0), ("09:31", 101.0), ("09:40", 102.0), ("09:50", 103.0),
        ("10:10", 104.0), ("11:00", 105.0), ("15:00", 106.0)]


def test_without_controls_the_run_is_the_old_run():
    a = run_session(Script({"09:30:00": long_at()}), tape(ROWS), Costs(0.0, 0.0), qty=1)
    b = go(ROWS, {"09:30:00": long_at()}, None)
    assert [t.to_dict() for t in a.trades] == [t.to_dict() for t in b.trades] and a.blocked == {} == b.blocked


def test_entry_window_refuses_before_and_after():
    plan = {"09:30:00": long_at(), "10:30:00": long_at()}
    res = go(sorted(ROWS + [("10:31", 105.0)]), plan, {"entry_from": "10:00", "entry_to": "11:00"})
    assert len(res.trades) == 1 and res.trades[0].entry_ns >= et_ns(D, "10:30:00")
    assert res.blocked == {"outside the entry window": 1}


def test_entry_to_cancels_a_working_entry_order_and_leaves_an_open_position():
    plan = {"09:30:00": lambda ctx, s: ctx.stop_entry("long", 110.0), "09:31:00": long_at()}
    res = go(sorted(ROWS + [("11:30", 111.0)]), plan, {"entry_to": "11:00"})
    assert len(res.trades) == 1                                # the market entry rode on to the close
    assert res.trades[0].exit_reason == "eod"                  # entry_to does not flatten (flat_at does)


def test_flat_at_closes_the_position_and_stops_entries():
    plan = {"09:30:00": long_at(), "12:00:00": long_at()}
    res = go(ROWS, plan, {"flat_at": "10:00"})
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.exit_reason == "time" and t.exit_ns >= et_ns(D, "10:00:00")
    assert res.blocked == {"outside the entry window": 1}


def test_direction_long_only():
    res = go(ROWS, {"09:30:00": short_at(), "09:45:00": long_at()}, {"direction": "long"})
    assert [t.side for t in res.trades] == ["long"] and res.blocked == {"direction": 1}


def ramp(sign=-1):
    """A print a minute from 09:25 to 15:00: flat at 100 to 09:30, then one point every 10 minutes (down: sign -1)."""
    rows = []
    for m in range(9 * 60 + 25, 15 * 60 + 1):
        k = max(0, m - (9 * 60 + 30)) // 10
        rows.append((f"{m // 60:02d}:{m % 60:02d}:00", 100.0 + sign * k))
    return rows


def with_stop(ctx, s):
    ctx.market("long", sl=ctx.last_price - 0.5)


def with_target(ctx, s):
    ctx.market("long", tp=ctx.last_price + 0.5)


def _losses():
    return ramp(-1), {"09:30:00": with_stop, "09:45:00": with_stop, "10:00:00": with_stop, "10:15:00": with_stop}


def test_max_trades_counts_fills():
    rows, plan = _losses()
    res = go(rows, plan, {"max_trades": 2})
    assert len(res.trades) == 2 and res.blocked == {"max trades a day": 2}
    assert len(go(rows, plan, None).trades) == 4


def test_stop_after_losses():
    rows, plan = _losses()
    res = go(rows, plan, {"stop_losses": 2})
    assert len(res.trades) == 2 and res.blocked == {"stopped after losses": 2}


def test_stop_after_wins():
    rows = ramp(+1)
    plan = {"09:30:00": with_target, "09:45:00": with_target, "10:00:00": with_target}
    res = go(rows, plan, {"stop_wins": 2})
    assert len(res.trades) == 2 and all(t.net > 0 for t in res.trades)
    assert res.blocked == {"stopped after wins": 1}


def test_day_loss_in_dollars_and_cooldown():
    rows, plan = _losses()
    res = go(rows, plan, {"day_loss": 15.0})                   # one -1pt NQ loss is -$20
    assert len(res.trades) == 1 and res.blocked["daily loss reached"] == 3
    res = go(rows, plan, {"cooldown_min": 20})                 # the first loss prints at 09:40; 09:45 is inside
    assert res.blocked == {"cooling off": 1} and len(res.trades) == 3
    res = go(rows, plan, {"max_consec_losses": 2})
    assert len(res.trades) == 2 and res.blocked == {"losses in a row": 2}


def test_fixed_bracket_is_measured_from_the_fill_and_replaces_the_strategy_own():
    rows = [("09:29:59", 100.0), ("09:30:05", 100.0), ("09:31", 112.0), ("09:32", 100.0)]
    res = go(rows, {"09:30:00": long_at(sl=50.0, tp=500.0)},
             {"stop_mode": "fixed", "stop_pts": 5, "target_mode": "fixed", "target_pts": 10})
    t = res.trades[0]
    assert (t.entry_price, t.sl, t.tp) == (100.0, 95.0, 110.0)
    assert t.exit_reason == "tp" and t.exit_price == 110.0


def test_rr_target_and_no_target():
    rows = [("09:29:59", 100.0), ("09:30:05", 100.0), ("09:31", 108.0), ("09:32", 100.0)]
    t, = go(rows, {"09:30:00": long_at(sl=90.0)}, {"stop_mode": "fixed", "stop_pts": 4, "target_mode": "rr",
                                                     "target_rr": 2}).trades
    assert (t.sl, t.tp) == (96.0, 108.0)
    t, = go(rows, {"09:30:00": long_at(sl=90.0, tp=101.0)}, {"target_mode": "none"}).trades
    assert t.tp is None and t.sl == 90.0


def test_atr_bracket_uses_closed_bars_only_and_refuses_while_warming_up():
    # 5-minute bars, true range 4 each: 09:00 .. 09:30 closed bars before the entry at 09:30
    rows, p = [], 100.0
    for k in range(0, 40):
        m = 9 * 60 + k
        rows += [(f"{m // 60:02d}:{m % 60:02d}:00", p), (f"{m // 60:02d}:{m % 60:02d}:30", p + 4.0)]
        p += 0.0
    plan = {"09:36:00": long_at()}
    cfg = {"stop_mode": "atr", "stop_atr": 1.5, "target_mode": "atr", "target_atr": 3, "atr_period": 3}
    t, = go(rows, plan, cfg).trades
    assert t.entry_price == 104.0                              # the print at 09:36:30
    assert round(t.entry_price - t.sl, 2) == 6.0 and round(t.tp - t.entry_price, 2) == 12.0   # 1.5 x 4, 3 x 4
    res = go(rows, plan, {**cfg, "atr_period": 50})
    assert res.trades == [] and res.blocked == {"atr warming up": 1}


def test_max_hold_closes_an_old_position():
    res = go(ROWS, {"09:30:00": long_at()}, {"max_hold_min": 20})
    t, = res.trades
    assert t.exit_reason == "hold" and et_ns(D, "09:50:00") <= t.exit_ns <= et_ns(D, "10:10:00")


# ---- the signal bar size
class Barred(Strategy):
    id, root = "barred", "NQ"
    session_window = ("09:30", "10:30")
    bar_minutes = 1
    bar_sizes = (1, 5)

    def __init__(self, sizes=None):
        super().__init__({})
        if sizes is not None:
            self.bar_sizes = sizes
        self.seen = []

    def on_bar(self, ctx, bar):
        self.seen.append((bar.end_ns - bar.start_ns) // 60_000_000_000)


def _bars(ctl, sizes=None):
    s = Barred(sizes)
    res = run_session(s, tape([(f"09:{m:02d}:30", 100.0 + m) for m in range(30, 60)]), Costs(0.0, 0.0), qty=1,
                      controls=Controls.from_dict(ctl))
    return s, res


def test_signal_bar_size_swaps_the_bars_a_strategy_lists():
    s, res = _bars(None)
    assert set(s.seen) == {1} and len(s.seen) == 30 and s.bar_min_eff == 1 and res.blocked == {}
    s, res = _bars({"bar_minutes": 5})
    assert set(s.seen) == {5} and len(s.seen) == 6 and s.bar_min_eff == 5 and res.blocked == {}


def test_signal_bar_size_a_strategy_does_not_list_is_ignored_and_said_so():
    s, res = _bars({"bar_minutes": 15})
    assert set(s.seen) == {1} and s.bar_min_eff == 1
    assert list(res.blocked) == ["signal bar size not offered by this strategy (its own bars used)"]
    s, res = _bars({"bar_minutes": 5}, sizes=())
    assert set(s.seen) == {1}


def test_signal_bar_size_parse():
    assert parse({"bar_minutes": 0}) == {} and parse({"bar_minutes": "5"}) == {"bar_minutes": 5}
    with pytest.raises(ValueError, match="bar_minutes"):
        parse({"bar_minutes": 3})
