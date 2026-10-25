"""Live delta for Lab / Desk strategies (owner, 2026-10-24): Strategy.needs_delta -> bar.buy / bar.sell and ctx.minute_volume "delta".

  (i)   backtest/sides.py: the flow builder's aggressor rule, by hand and against ~/futures_derived/flow_tape on a real day;
  (ii)  the tester: run_session gives each bar buy / sell only when the strategy asks; minvol.deltas / prior(delta=True);
  (iii) the Desk side: the chart service's stream rows carry the hub's side, the runner keeps it with the prints, the child hands
        buy / sell to the strategy as plain bar attributes, and the init check refuses a needs_delta that is not true / false.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from array import array
from types import SimpleNamespace

import pytest

from homebase.backtest import minvol
from homebase.backtest.engine import Bar, Costs, run_session
from homebase.backtest.sides import order_sides, split_delta
from homebase.backtest.tape import Tape, et_ns
from homebase.charts import server
from homebase.charts.tick import Tick
from homebase.labrun import child, host
from homebase.labrun.livectx import LiveCtx
from homebase.labrun.shadowfills import ShadowFills
from homebase.strategies.base import Strategy

D = dt.date(2024, 3, 5)


# ---- (i) the rule ----------------------------------------------------------------------------------------------------------------

def test_one_stamp_is_one_order_a_walk_decides_else_the_tick_rule_carried_forward():
    ts = [1, 2, 2, 2, 3, 4, 5, 5, 6, 7]
    px = [10.0, 10.0, 10.25, 10.5, 10.5, 10.25, 10.25, 10.25, 10.25, 10.5]
    #       ?    order 2: walks up = buy   same=carry  down=sell  order 5 flat, same price = carry sell   carry   up
    assert list(order_sides(ts, px)) == [0, 1, 1, 1, 1, -1, -1, -1, -1, 1]
    assert list(order_sides([1, 1], [5.0, 4.75])) == [-1, -1]                   # a first order that walks down is a sell
    assert list(order_sides([], [])) == []


FLOW_DAY = os.path.expanduser("~/futures_derived/flow_tape/NQ/2025/2025-03-17.parquet")


@pytest.mark.skipif(not os.path.exists(FLOW_DAY), reason="no flow_tape on this machine")
def test_the_rule_is_the_flow_builders_print_for_print_on_a_real_day():
    pd = pytest.importorskip("pandas")
    df = pd.read_parquet(FLOW_DAY)
    got = order_sides(df.ts_ns.tolist(), df.price.tolist())
    assert list(got) == df.side.tolist()


def test_split_delta_counts_each_bars_prints_by_side_and_skips_unknown():
    bars = [Bar(0, 10, 1, 1, 1, 1, 0), Bar(10, 20, 1, 1, 1, 1, 0)]
    split_delta([0, 5, 9, 10, 15, 25], [3, 4, 5, 6, 7, 8], [0, 1, -1, 1, 1, -1], 0, 6, bars)
    assert [(b.buy, b.sell) for b in bars] == [(4, 5), (13, 0)]               # the 0-side print and the one after the bars: none


# ---- (ii) the tester -------------------------------------------------------------------------------------------------------------

def tape_of(rows, d=D) -> Tape:
    """rows: [(et 'HH:MM:SS', price, size)] -> a tape of that date, one print a row (distinct stamps)."""
    return Tape("NQ", d, "NQH4", array("q", [et_ns(d, t) for t, _, _ in rows]), array("d", [p for _, p, _ in rows]),
                array("i", [s for _, _, s in rows]), {"h": 1.0, "l": 1.0, "c": 1.0})


class Rec(Strategy):
    name, root, bar_minutes, session_window = "rec", "NQ", 1, ("09:30", "09:34")
    flag = True
    seen: list = []

    def needs_delta(self):
        return self.flag

    def on_bar(self, ctx, bar):
        type(self).seen.append(getattr(bar, "buy", None) if not self.flag else (bar.buy, bar.sell))


ROWS = [("09:30:00", 100.0, 1), ("09:30:10", 100.25, 2), ("09:30:20", 100.0, 3), ("09:31:05", 100.0, 4), ("09:31:30", 100.5, 5),
        ("09:32:10", 100.25, 6)]


def test_run_session_gives_each_bar_buy_and_sell_only_when_the_strategy_needs_delta():
    yes = type("Y", (Rec,), {"seen": []})
    run_session(yes(), tape_of(ROWS), Costs())
    assert yes.seen == [(2, 3), (5, 4), (0, 6)]      # 09:30 ? +2 -3; 09:31 carry -4, +5; 09:32 -6
    no = type("N", (Rec,), {"seen": [], "flag": False})
    run_session(no(), tape_of(ROWS), Costs())
    assert no.seen == [None, None, None]


def test_minvol_deltas_and_prior_with_delta():
    t = tape_of(ROWS)
    dl, v = minvol.deltas(t), minvol.minutes(t)
    at = 360 + 570                                    # 09:30 ET
    assert (dl[at], dl[at + 1], dl[at + 2], sum(dl)) == (-1, 1, -6, -6) and v[at] == 6
    store = SimpleNamespace(sessions=lambda root, a, b: [D], daily=lambda root, x: {"h": 1}, pick=lambda root, x: None,
                            load=lambda root, x: t)
    nxt = D + dt.timedelta(days=1)
    assert "delta" not in minvol.prior(store, "NQ", nxt, 1)[0]
    store.pick = lambda root, x: (SimpleNamespace(name="f", stat=lambda: SimpleNamespace(st_mtime_ns=1, st_size=1)),)
    row = minvol.prior(store, "NQ", nxt, 1, delta=True)[0]
    assert row["date"] == D.isoformat() and row["delta"][at + 2] == -6 and len(row["delta"]) == minvol.NMIN


# ---- (iii) the Desk side ---------------------------------------------------------------------------------------------------------

def test_the_stream_rows_carry_the_hubs_side():
    ticks = [Tick(1000, 100.0, 2, 1, 1), Tick(1001, 99.75, 3, -1, 2)]
    live = json.loads(server._live_rows("NQ", ticks).split("data:", 1)[1])
    back = json.loads(server._backlog_rows("NQ", ticks, 0, 2).split("data:", 1)[1])
    assert live["rows"] == back["rows"] == [[1000, 100.0, 2, 1], [1001, 99.75, 3, -1]]


def test_the_runner_keeps_each_prints_side_and_an_old_three_field_row_is_side_0():
    f = ShadowFills("NQ", D, Costs(), 85)
    f.add_ticks([(1, 100.0, 2, 1), (2, 100.0, 3, -1), (3, 100.0, 4), (4, 100.0, 5, 7)])
    assert list(f.side) == [1, -1, 0, 0] and list(f.size) == [2, 3, 4, 5]
    assert [host._side(r) for r in ([1, 1.0, 1, -1], [1, 1.0, 1], [1, 1.0, 1, "x"])] == [-1, 0, 0]


def test_the_child_hands_buy_and_sell_to_the_strategy_as_plain_bar_attributes():
    got = []
    strat = SimpleNamespace(on_bar=lambda ctx, bar: got.append((bar, getattr(bar, "buy", None), getattr(bar, "sell", None))))
    ctx = LiveCtx(root="NQ", date=D, tick=0.25, point_value=20.0, qty=1, daily=[])
    arg = {"start_ns": 0, "end_ns": 60, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 9}
    child._event(strat, ctx, {"kind": "bar", "flat": True, "t_ns": 60, "arg": {**arg, "buy": 5, "sell": 4}})
    child._event(strat, ctx, {"kind": "bar", "flat": True, "t_ns": 60, "arg": arg})
    assert got[0][0] == Bar(**arg) and got[0][1:] == (5, 4) and got[1][1:] == (None, None)


def test_the_init_check_refuses_a_needs_delta_that_is_not_true_or_false():
    meta = {"root": "NQ", "session_window": ["09:30", "11:00"], "bar_minutes": 5, "bar_window": None, "placement_ms": 85,
            "times": [], "needs_daily": True, "trades_on": True, "needs_minute_volume": 20}
    assert host.well_set(meta, "NQ") and host.well_set({**meta, "needs_delta": True}, "NQ")
    assert not host.well_set({**meta, "needs_delta": "yes"}, "NQ")


def _archive(path, rows, quotes=True):
    """A desk-style archive file: ts_ms, price, size, bid, ask, bid_size, ask_size, id, ts_ns."""
    import csv as _csv
    import gzip as _gzip
    with _gzip.open(path, "wt", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["ts_ms", "price", "size", "bid", "ask", "bid_size", "ask_size", "id", "ts_ns"])
        for i, (ts, p, q, b, a) in enumerate(rows):
            w.writerow([ts // 1_000_000, p, q, b if quotes else "", a if quotes else "", 1, 1, i, ts])


def test_a_file_recorded_with_quotes_is_classified_by_the_quotes_as_the_chart_service_does(tmp_path):
    from homebase.backtest.sides import quote_sides
    f = tmp_path / "x.csv.gz"
    rows = [(1, 100.0, 1, 99.75, 100.0), (2, 99.75, 2, 99.75, 100.0), (3, 99.75, 3, 99.5, 99.75), (4, 99.85, 4, 99.75, 100.0)]
    _archive(f, rows)
    assert list(quote_sides(f, 4)) == [1, -1, 1, 1]          # at the ask, at the bid, at the ask, inside -> tick rule (up)
    assert quote_sides(f, 5) is None                          # the file no longer lines up with the tape: not used
    g = tmp_path / "y.csv.gz"
    _archive(g, rows, quotes=False)
    assert quote_sides(g, 4) is None                          # the backfill (no quotes): the order rule instead
    t = Tape("NQ", D, "NQH4", array("q", [r[0] for r in rows]), array("d", [r[1] for r in rows]), array("i", [r[2] for r in rows]),
             {"h": 1.0, "l": 1.0, "c": 1.0}, src=f)
    assert list(t.sides()) == [1, -1, 1, 1]
    t2 = Tape("NQ", D, "NQH4", t.ts, t.px, t.size, t.daily, src=g)
    assert list(t2.sides()) == list(order_sides(t.ts, t.px))


def test_an_unsorted_file_gives_its_sides_in_the_tapes_order(tmp_path):
    from homebase.backtest.sides import quote_sides
    f = tmp_path / "z.csv.gz"
    _archive(f, [(5, 100.0, 1, 99.75, 100.0), (3, 99.75, 2, 99.75, 100.0)])     # written out of order; the tape sorts by ts
    assert list(quote_sides(f, 2)) == [-1, 1]
