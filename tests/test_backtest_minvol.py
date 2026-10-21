"""backtest/minvol.py: the earlier trade dates' volume per ET minute (ctx.minute_volume, Strategy.needs_minute_volume)."""
from __future__ import annotations

import datetime as dt
from array import array

import pytest

from homebase import strategies
from homebase.backtest import minvol
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.runner import execute, prepare, read_json
from homebase.backtest.tape import Tape, TapeStore, et_ns
from homebase.strategies.base import Strategy
from tests.test_backtest_hourly import days_before
from tests.test_backtest_runner import _winning_day

D = dt.date(2024, 3, 5)                      # a Tuesday
EVE = D - dt.timedelta(days=1)
AT_10 = 360 + 600                            # the index of 10:00 ET of the date (18:00 the evening before = 0)


def tape_of(d, rows, contract="NQH4") -> Tape:
    """rows: [(ns, size)]."""
    return Tape("NQ", d, contract, array("q", [r[0] for r in rows]), array("d", [1.0] * len(rows)),
                array("i", [r[1] for r in rows]), {"h": 1.0, "l": 1.0, "c": 1.0})


def test_minutes_index_0_is_18_00_the_evening_before_and_the_last_is_16_59_of_the_date():
    t = tape_of(D, [(et_ns(EVE, "17:59:59"), 100), (et_ns(EVE, "18:00"), 2), (et_ns(EVE, "18:00:59"), 3),
                    (et_ns(EVE, "18:01"), 4), (et_ns(D, "09:30:10"), 5), (et_ns(D, "09:30:50"), 5),
                    (et_ns(D, "16:59:59"), 6), (et_ns(D, "17:00"), 100)])
    v = minvol.minutes(t)
    assert len(v) == minvol.NMIN == 1380
    assert (v[0], v[1], v[360 + 570], v[1379]) == (5, 4, 10, 6)          # 18:00 + 18:00:59; 18:01; 09:30; 16:59
    assert sum(v) == 25                                                  # before 18:00 and from 17:00 on: not counted
    assert sum(minvol.minutes(tape_of(D, []))) == 0


class Store:
    """A tape store of trade dates {date: (tape or None, has a daily bar)}; load counts its reads."""

    def __init__(self, days):
        self.days, self.loads = days, []

    def sessions(self, root, start, end):
        return sorted(d for d in self.days if start <= d <= end)

    def daily(self, root, d):
        return {"date": d.isoformat()} if self.days[d][1] else None

    def load(self, root, d):
        self.loads.append(d)
        return self.days[d][0]


def day(d, size, contract="NQH4"):
    return tape_of(d, [(et_ns(d, "10:00:30"), size)], contract), True


def test_prior_gives_the_n_dates_before_the_date_oldest_first_whatever_the_contract_and_never_the_date_or_later():
    a, b, c = days_before(3)
    store = Store({a: day(a, 10, "NQH4"), b: day(b, 20, "NQM4"), c: day(c, 30, "NQM4"), D: day(D, 99, "NQM4"),
                   D + dt.timedelta(days=1): day(D + dt.timedelta(days=1), 99)})
    got = minvol.prior(store, "NQ", D, 2)
    assert [g["date"] for g in got] == [b.isoformat(), c.isoformat()]
    assert [g["vol"][AT_10] for g in got] == [20, 30] and all(len(g["vol"]) == 1380 and sum(g["vol"]) == g["vol"][AT_10]
                                                               for g in got)
    assert [g["date"] for g in minvol.prior(store, "NQ", D, 3)] == [a.isoformat(), b.isoformat(), c.isoformat()]  # no roll stop
    assert D not in store.loads and all(x < D for x in store.loads)
    assert len(minvol.prior(store, "NQ", D, 99)) == 3                                                # at most what is there


def test_a_date_without_a_tape_gives_none_and_a_date_without_a_daily_bar_is_not_one_of_the_dates():
    a, b, stub, c = days_before(4)
    store = Store({a: day(a, 10), b: (None, True), stub: (None, False), c: day(c, 30)})
    got = minvol.prior(store, "NQ", D, 3)
    assert [(g["date"], g["vol"] is None) for g in got] == [(a.isoformat(), False), (b.isoformat(), True),
                                                            (c.isoformat(), False)]


def test_n_zero_reads_nothing_and_a_cache_reads_each_date_once():
    a, b, c = days_before(3)
    store, cache = Store({a: day(a, 10), b: day(b, 20), c: day(c, 30)}), {}
    assert minvol.prior(store, "NQ", D, 0) == [] and store.loads == []
    first = minvol.prior(store, "NQ", D, 3, cache)
    assert minvol.prior(store, "NQ", D, 3, cache) == first and sorted(store.loads) == [a, b, c]


def test_a_date_whose_tape_did_not_load_is_read_again_next_time():
    a, b = days_before(2)
    store, cache = Store({a: day(a, 10), b: (None, True)}), {}
    assert [g["vol"] is None for g in minvol.prior(store, "NQ", D, 2, cache)] == [False, True]
    store.days[b] = day(b, 20)                                    # the archive caught up
    assert minvol.prior(store, "NQ", D, 2, cache)[-1]["vol"][AT_10] == 20 and store.loads.count(b) == 2


class Reads(Strategy):
    id, name, root = "mv_reads", "Reads", "NQ"
    session_window = ("09:30", "10:00")
    session_independent = True

    def needs_minute_volume(self):
        return 2

    def on_session(self, ctx):
        mv = ctx.minute_volume
        ctx.plot("n", ctx.now_ns, float(len(mv)))
        ctx.plot("newest", ctx.now_ns, float(mv[-1]["date"].replace("-", "")) if mv else 0.0)
        ctx.plot("total", ctx.now_ns, float(sum(mv[-1]["vol"])) if mv else 0.0)


def test_run_session_hands_the_volume_to_ctx_minute_volume_and_the_default_is_none():
    t = tape_of(D, [(et_ns(D, "09:30:05"), 1), (et_ns(D, "09:59"), 1)])
    res = run_session(Reads(), t, Costs(), minute_volume=[{"date": "2024-03-04", "vol": [1] * 1380}])
    assert [p[1] for p in res.plots["n"]] == [1.0] and [p[1] for p in res.plots["total"]] == [1380.0]
    assert [p[1] for p in run_session(Reads(), t, Costs()).plots["n"]] == [0.0]
    assert Strategy().needs_minute_volume() == 0


def test_a_lab_run_feeds_each_day_the_dates_before_it_from_their_own_tapes(tmp_path, monkeypatch):
    for d in (dt.date(2024, 3, 4), dt.date(2024, 3, 5), dt.date(2024, 3, 6)):
        _winning_day(tmp_path / "ticks", d)                  # 1,793 prints of size 1, 09:25 -> 15:46
    monkeypatch.setitem(strategies.REGISTRY, Reads.id, Reads)
    rid = prepare({"strategy": Reads.id, "range": {"kind": "custom", "start": "2024-03-04", "end": "2024-03-06"}},
                  tmp_path / "t")
    execute(tmp_path / "t" / "runs" / rid, TapeStore(tmp_path / "ticks", tmp_path / "cache"))
    got = read_json(tmp_path / "t" / "runs" / rid / "plots.json")["plots"]
    assert [p[1] for p in got["n"]] == [0.0, 1.0, 2.0]                           # 03-04 has no date before it here
    assert [p[1] for p in got["newest"]] == [0.0, 20240304.0, 20240305.0]         # yesterday, never today
    assert [p[1] for p in got["total"]] == [0.0, 1793.0, 1793.0]


def test_a_strategy_that_does_not_ask_costs_nothing(tmp_path, monkeypatch):
    _winning_day(tmp_path / "ticks", D)

    def boom(*a, **kw):
        raise AssertionError("read for a strategy that did not ask")
    monkeypatch.setattr(minvol, "minutes", boom)
    monkeypatch.setattr(minvol, "prior", boom)
    rid = prepare({"strategy": "nq930", "inputs": {"adx_gate": False},
                   "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}, tmp_path / "t")
    meta = execute(tmp_path / "t" / "runs" / rid, TapeStore(tmp_path / "ticks", tmp_path / "cache"))
    assert meta["report"]["summary"]["all"]["trades"] == 1


def test_more_than_30_dates_is_refused(tmp_path, monkeypatch):
    class Many(Reads):
        id = "mv_many"

        def needs_minute_volume(self):
            return 31
    _winning_day(tmp_path / "ticks", D)
    monkeypatch.setitem(strategies.REGISTRY, Many.id, Many)
    rid = prepare({"strategy": Many.id, "range": {"kind": "custom", "start": "2024-03-05", "end": "2024-03-05"}},
                  tmp_path / "t")
    with pytest.raises(ValueError, match="needs_minute_volume: 0 .. 30 dates, not 31"):
        execute(tmp_path / "t" / "runs" / rid, TapeStore(tmp_path / "ticks", tmp_path / "cache"))
