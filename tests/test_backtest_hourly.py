"""backtest/hourly.py: the 1-hour closes of the sessions before a date (ctx.hourly, Strategy.needs_hourly)."""
from __future__ import annotations

import datetime as dt
from array import array

from homebase.backtest import hourly
from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import Tape, et_ns
from homebase.strategies.base import Strategy

D = dt.date(2024, 3, 5)                      # a Tuesday
EVE = D - dt.timedelta(days=1)


def tape_of(d, rows, contract="NQH4") -> Tape:
    """rows: [(ns, price)]."""
    return Tape("NQ", d, contract, array("q", [r[0] for r in rows]), array("d", [r[1] for r in rows]),
                array("q", [1] * len(rows)), {"h": 0.0, "l": 0.0, "c": 0.0})


def test_session_hours_are_the_last_print_of_each_whole_hour_from_18_00_the_evening_before_to_17_00():
    t = tape_of(D, [(et_ns(EVE, "18:10"), 1.0), (et_ns(EVE, "18:50"), 2.0), (et_ns(EVE, "19:30"), 3.0),
                    (et_ns(EVE, "21:59:59"), 4.0), (et_ns(D, "16:59:59"), 5.0), (et_ns(D, "17:00:30"), 6.0),
                    (et_ns(D, "18:30"), 7.0)])
    assert hourly.session_hours(t) == [[et_ns(EVE, "19:00"), 2.0], [et_ns(EVE, "20:00"), 3.0],
                                       [et_ns(EVE, "22:00"), 4.0], [et_ns(D, "17:00"), 5.0]]   # 20:00-21:00 had no print
    assert hourly.session_hours(tape_of(D, [])) == []


class Store:
    """A tape store of sessions {date: (contract, tape or None)}; pick says the contract, load counts its reads."""

    def __init__(self, days):
        self.days, self.loads = days, []

    def sessions(self, root, start, end):
        return sorted(d for d in self.days if start <= d <= end)

    def pick(self, root, d):
        got = self.days.get(d)
        return None if got is None or got[1] is None else ("path", got[0])

    def load(self, root, d):
        self.loads.append(d)
        return self.days[d][1]


def session(d, close, contract="NQH4"):
    return contract, tape_of(d, [(et_ns(d, "10:15"), close), (et_ns(d, "11:20"), close + 1)], contract)


def days_before(n, start=D):
    out, d = [], start
    while len(out) < n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out[::-1]


def test_prior_gives_the_n_sessions_before_the_date_oldest_first_and_never_the_date_or_later():
    a, b, c = days_before(3)
    store = Store({a: session(a, 10.0), b: session(b, 20.0), c: session(c, 30.0), D: session(D, 99.0),
                   D + dt.timedelta(days=1): session(D + dt.timedelta(days=1), 99.0)})
    got = hourly.prior(store, "NQ", D, 2)
    assert got == [[et_ns(b, "11:00"), 20.0], [et_ns(b, "12:00"), 21.0], [et_ns(c, "11:00"), 30.0], [et_ns(c, "12:00"), 31.0]]
    assert D not in store.loads and all(x < D for x in store.loads)
    assert hourly.prior(store, "NQ", D, 0) == [] and len(hourly.prior(store, "NQ", D, 99)) == 6      # at most what is there


def test_prior_stops_at_the_roll_and_a_roll_day_gets_none():
    a, b, c = days_before(3)
    store = Store({a: session(a, 10.0, "NQH4"), b: session(b, 20.0, "NQM4"), c: session(c, 30.0, "NQM4"),
                   D: session(D, 99.0, "NQM4")})
    assert [h[1] for h in hourly.prior(store, "NQ", D, 5)] == [20.0, 21.0, 30.0, 31.0]             # b is the roll day: in
    store.days[D] = session(D, 99.0, "NQU4")
    assert hourly.prior(store, "NQ", D, 5) == []                                                   # D rolled: nothing


def test_prior_passes_over_a_day_without_a_tape_and_takes_the_newest_contract_when_the_date_is_not_stored_yet():
    a, b, c = days_before(3)
    store = Store({a: session(a, 10.0), b: ("NQH4", None), c: session(c, 30.0)})
    assert [h[1] for h in hourly.prior(store, "NQ", D, 2)] == [10.0, 11.0, 30.0, 31.0]             # D not stored: c's contract


def test_prior_reads_a_session_once_with_a_cache():
    a, b, c = days_before(3)
    store, cache = Store({a: session(a, 10.0), b: session(b, 20.0), c: session(c, 30.0)}), {}
    hourly.prior(store, "NQ", D, 3, cache)
    hourly.prior(store, "NQ", D, 3, cache)
    assert sorted(store.loads) == [a, b, c]


class Reads(Strategy):
    id, name, root = "r", "Reads", "NQ"
    session_window = ("09:30", "10:00")

    def needs_hourly(self):
        return 2

    def on_session(self, ctx):
        ctx.plot("n", ctx.now_ns, float(len(ctx.hourly)))


def test_run_session_hands_the_hours_to_ctx_hourly_and_the_default_is_none():
    t = tape_of(D, [(et_ns(D, "09:30:05"), 1.0), (et_ns(D, "09:59"), 1.0)])
    res = run_session(Reads(), t, Costs(), hourly=[[1, 2.0], [3, 4.0]])
    assert [p[1] for p in res.plots["n"]] == [2.0]
    assert [p[1] for p in run_session(Reads(), t, Costs()).plots["n"]] == [0.0]
    assert Strategy().needs_hourly() == 0
