"""The strategy contract and the runner options added after the verifier pass: validated inputs (tester's
resolve_inputs), session_independent as the tester, Template.ROLLS under run_session, strategy errors drop the
session (skipped_by_error), strict_limit + unrealistic_winners, slip_ticks / latency_ms sensitivity.
In-sample days only."""
import datetime as dt
import json
import random
import shutil
from array import array

import numpy as np
import pytest

import l2ref
import l2sim as S
import sim_validate as V

NEW = ("f_depth", "f_book", "x_book", "f_thin", "hold_to")      # Template inputs that are not tester inputs (default off / the tester rule)

D = dt.date(2024, 3, 5)
T0 = S.et_ns(D, "09:30")


def tape(prints, d=D, contract="NQH4"):
    ts = [S.et_ns(d, "09:30") + int(round(p[0] * 1e9)) for p in prints]
    return S.Tape("NQ", d, contract, ts, [p[1] for p in prints], [1] * len(prints))


class Script(S.Strategy):
    session_window = ("09:30", "10:00")

    def __init__(self, fn, times=()):
        super().__init__({})
        self.fn, self._times = fn, list(times)

    def times(self):
        return self._times

    def on_session(self, ctx):
        self.fn(ctx, "session", None)

    def on_bar(self, ctx, bar):
        self.fn(ctx, "bar", bar)

    def on_time(self, ctx, t):
        self.fn(ctx, "time", t)


def at_session(action):
    def fn(ctx, kind, arg):
        if kind == "session":
            action(ctx)
    return fn


# ---- inputs ------------------------------------------------------------------------------------------------------
BAD = [(l2ref.Donchian, {"tf": 15}), (l2ref.Donchian, {"tf": "2"}), (l2ref.Donchian, {"n": 20.7}),
       (l2ref.Donchian, {"n": 1}), (l2ref.Donchian, {"n": "20"}), (l2ref.Donchian, {"stop_val": -3.0}),
       (l2ref.Donchian, {"stop_val": float("nan")}), (l2ref.Donchian, {"dir": "sideways"}),
       (l2ref.Donchian, {"max_tr": 0}), (l2ref.Donchian, {"max_tr": True}), (l2ref.Donchian, {"sess": "ny"}),
       (l2ref.Donchian, {"stop_mode": "ATR"}), (l2ref.Donchian, {"exit_bars": 1.5}), (l2ref.Donchian, {"tgt_r": 21}),
       (l2ref.Donchian, {"f_trend": True}), (l2ref.Donchian, {"nope": 1}),
       (l2ref.Straddle, {"news_only": 1}), (l2ref.Straddle, {"off_atr": 0.0}), (l2ref.Straddle, {"delay_min": 121}),
       (l2ref.Orb, {"or_min": 15}), (l2ref.Orb, {"or_min": "10"})]


@pytest.mark.parametrize("cls,params", BAD, ids=[f"{c.__name__}-{p}" for c, p in BAD])
def test_a_bad_input_is_an_error_not_a_quiet_run(cls, params):
    """Verifier: Donchian accepted tf=15, n=20.7, stop_val=-3, dir='sideways' (a run with zero trades), max_tr=0."""
    with pytest.raises(ValueError) as e:
        cls(params)
    assert next(iter(params)) in str(e.value)
    with pytest.raises(ValueError):                                   # the runner refuses before any tape is read
        S.run(cls, params, "2024-12-02", "2024-12-03", workers=1)


def test_inputs_are_coerced_like_the_tester_and_defaults_equal_the_tester_resolved_inputs():
    p = l2ref.Donchian({"n": 20.0, "stop_val": 30, "exit_bars": 6.0, "tgt_r": 1}).p
    assert p["n"] == 20 and type(p["n"]) is int and type(p["exit_bars"]) is int
    assert p["stop_val"] == 30.0 and type(p["stop_val"]) is float and type(p["tgt_r"]) is float
    assert type(l2ref.Donchian({"n": np.int64(12)}).p["n"]) is int
    for cid, fam, src, sess, role in V.GATE + V.EXTRA:                # run.json inputs = the tester's resolved inputs
        inputs = V.load_bundle(src)[0]
        cls = l2ref.FAMILIES[fam]
        got = cls(inputs).p
        for k in NEW:                                                 # the inputs l2sim adds to the tester's (SPEC B6, EDGE_SPEC D2-D4)
            assert got.pop(k) == ("session" if k == "hold_to" else "off")     # ... all default off (hold_to: the tester's rule)
        assert got == inputs and {k: type(v) for k, v in got.items()} == {k: type(v) for k, v in inputs.items()}
        assert cls({k: inputs[k] for k in ("tf", "sess")}).p.keys() - set(NEW) == inputs.keys()
        assert set(cls.schema()) == set(cls.defaults())               # the reference families declare every input


def test_resolve_inputs_agrees_with_the_tester_resolve_inputs():
    B = pytest.importorskip("homebase.strategies.base")
    cls = l2ref.Straddle
    dflt, sch = cls.defaults(), cls.schema()
    schema = []
    for k, d in dflt.items():
        spec = sch[k]
        if spec[0] == "choice":
            schema.append(B.Input(k, k, "choice", d, choices=tuple(spec[1])))
        elif spec[0] == "bool":
            schema.append(B.Input(k, k, "bool", d))
        else:
            schema.append(B.Input(k, k, spec[0], d, spec[1], spec[2]))
    values = {"tf": ["5", "30", 5, "7", None, True], "dir": ["long", "both", "up", 1],
              "stop_val": [0.1, 0.09, 1000, 1000.5, 3, "3", True, float("nan"), float("inf"), -1],
              "tgt_r": [0, 0.0, 20, 20.01, -0.5], "exit_bars": [0, 6, 6.0, 6.5, 500, 501, -1, "6", False],
              "max_tr": [1, 20, 21, 0, 2.0, 2.2], "news_only": [True, False, 0, 1, "true", None],
              "delay_min": [0, 120, 121, -1, 5.0, 5.5], "off_atr": [0.1, 5, 5.01, 0.05, 1, "1"],
              "f_vwap": ["off", "with", "against", "on", False], "bogus": [1]}
    n_ok = n_bad = 0
    for k, vs in values.items():
        for v in vs:
            try:
                want = B.resolve_inputs(schema, {k: v})
            except ValueError:
                want = None
            try:
                got = S.resolve_inputs(dflt, sch, {k: v})
            except ValueError:
                got = None
            assert (got is None) == (want is None), (k, v, got, want)
            if want is not None:
                assert got == want and type(got[k]) is type(want[k]), (k, v)
                n_ok += 1
            else:
                n_bad += 1
    assert n_ok >= 25 and n_bad >= 25
    assert S.resolve_inputs(dflt, sch, None) == B.resolve_inputs(schema, None)


def test_inputs_without_a_schema_are_typed_by_their_default():
    class X(S.Strategy):
        DEFAULTS = {"k": 2.0, "n": 3, "flag": False, "mode": "a", "obj": None}
    assert X({"k": 1}).p == {"k": 1.0, "n": 3, "flag": False, "mode": "a", "obj": None}
    assert X({"n": 4.0, "obj": [1]}).p["n"] == 4
    for bad in ({"n": 2.5}, {"flag": 1}, {"mode": 3}, {"k": float("nan")}, {"k": True}, {"k": "2"}, {"z": 1}):
        with pytest.raises(ValueError):
            X(bad)

    class Y(X):
        SCHEMA = {"mode": ("choice", ("a", "b")), "k": ("float", 0.5, 4)}
    assert Y({"mode": "b", "k": 4}).p["k"] == 4.0
    for bad in ({"mode": "c"}, {"k": 0.4}, {"k": 4.5}):
        with pytest.raises(ValueError):
            Y(bad)

    class Z(S.Strategy):
        DEFAULTS = {"a": 1}
        SCHEMA = {"b": ("int", 0, 1)}
    with pytest.raises(ValueError):                                   # a schema entry for an input that does not exist
        Z({})


# ---- session_independent --------------------------------------------------------------------------------------------
class CrossDay(S.Strategy):
    """Carries state across days (the verifier's probe): trades only on its odd-numbered sessions."""
    session_window = ("09:30", "09:40")

    def __init__(self, p=None):
        super().__init__(p)
        self.n = 0

    def times(self):
        return ["09:31", "09:35"]

    def on_session(self, ctx):
        self.n += 1

    def on_time(self, ctx, t):
        if t == "09:31" and self.n % 2:
            ctx.market("long")
        elif t == "09:35":
            ctx.flatten("time")


def test_session_independent_defaults_as_the_tester_and_cross_day_state_never_meets_several_workers():
    assert S.Strategy.session_independent is False and S.Template.session_independent is True
    assert all(c.session_independent for c in l2ref.FAMILIES.values()) and l2ref.FeatureProbe.session_independent
    assert CrossDay.session_independent is False
    try:
        from homebase.strategies.base import Strategy as HB
        assert HB.session_independent is S.Strategy.session_independent
    except ImportError:
        pass
    a = S.run(CrossDay, {}, "2024-10-01", "2024-10-31", workers=1)
    b = S.run(CrossDay, {}, "2024-10-01", "2024-10-31", workers=4)     # verifier: 22 vs 24 trades before the fix
    assert a["trades"] == b["trades"] and a["meta"]["workers"] == b["meta"]["workers"] == 1
    days = sorted({t["date"] for t in a["trades"]})
    assert a["sessions"] == 23 and days == [d.isoformat() for d in S.sessions("2024-10-01", "2024-10-31")][0::2]
    assert S.run(l2ref.Donchian, {"tf": "15"}, "2024-10-01", "2024-10-04", workers=4)["meta"]["workers"] == min(4, S.MAX_WORKERS)


# ---- Template.ROLLS -------------------------------------------------------------------------------------------------
def test_template_rolls_are_filled_for_run_session_too():
    daily = S.load_daily()
    dates = [r["date"] for r in daily]
    roll = S.rolls(daily)
    st = l2ref.Donchian({"tf": "15"})
    assert st.ROLLS == roll == S.default_rolls() and len(roll) == 13       # no runner involved
    for iso, is_roll in (("2022-06-13", True), ("2022-06-14", False), ("2023-03-13", True), ("2024-08-05", False)):
        st = l2ref.Donchian({"tf": "15"})
        t = S.load_tape(iso)
        S.run_session(st, t, daily=daily[:dates.index(iso)], window=S.effective_session_window(t.date, st.session_window))
        prev = daily[dates.index(iso) - 1]
        assert (st.pdh, st.pdl, st.pdc) == ((None, None, None) if is_roll else (prev["h"], prev["l"], prev["c"])), iso
        assert (iso in roll) is is_roll
    st = l2ref.Donchian({"tf": "15"})                                 # the runner's own list still wins
    st.ROLLS = {"2024-08-05"}
    assert st.ROLLS == frozenset({"2024-08-05"})
    t = S.load_tape("2024-08-05")
    S.run_session(st, t, daily=daily[:dates.index("2024-08-05")])
    assert st.pdh is None


def test_run_session_detects_a_roll_day_from_the_daily_bars():
    """A date the cached list does not know: the prior daily bar is another contract -> prior-day levels dropped."""
    pr = [(1, 100.0), (61, 100.5), (1700, 100.0)]
    prior = [{"date": "2024-03-04", "h": 110.0, "l": 90.0, "c": 100.0, "contract": "NQH4"}]
    st = l2ref.Donchian({"tf": "1"})
    S.run_session(st, tape(pr, contract="NQH4"), daily=prior)
    assert (st.pdh, st.pdl, st.pdc) == (110.0, 90.0, 100.0) and D.isoformat() not in st.ROLLS
    st = l2ref.Donchian({"tf": "1"})
    S.run_session(st, tape(pr, contract="NQM4"), daily=prior)
    assert st.pdh is None and D.isoformat() in st.ROLLS and st.ROLLS >= S.default_rolls()
    st = l2ref.Donchian({"tf": "1"})                                 # no contract on the daily bar: nothing to detect
    S.run_session(st, tape(pr, contract="NQM4"), daily=[{"date": "2024-03-04", "h": 110.0, "l": 90.0, "c": 100.0}])
    assert st.pdh == 110.0


# ---- strategy errors ---------------------------------------------------------------------------------------------------
class Crashy(S.Strategy):
    """Trades at 09:31, is flat at 09:33, trades again at 09:34 and crashes at 09:36 on `bad` dates."""
    session_window = ("09:30", "09:45")
    session_independent = True
    DEFAULTS = {"bad": "2024-12-03"}

    def times(self):
        return ["09:31", "09:33", "09:34", "09:36", "09:40"]

    def on_time(self, ctx, t):
        if t in ("09:31", "09:34"):
            ctx.market("long")
            ctx.stop_entry("long", ctx.last_price + 500.0)
        elif t == "09:36" and ctx.date.isoformat() in self.p["bad"].split(","):
            raise KeyError("imb10")
        else:
            ctx.flatten("time")


def test_a_strategy_error_drops_the_session_like_the_tester_engine():
    E = pytest.importorskip("homebase.backtest.engine")
    from homebase.backtest.tape import Tape as HBTape
    t = S.load_tape("2024-12-03")
    hb = HBTape(t.root, t.date, t.contract, array("q", t.ts.tolist()), array("d", t.px.tolist()),
                array("i", t.size.tolist()), dict(t.daily))
    ra = E.run_session(Crashy(), hb, E.Costs(), qty=1, daily=[])
    rb = S.run_session(Crashy(), t)
    assert ra.trades == [] and rb.trades == []                       # incl. the trade CLOSED before the crash
    assert ra.skip == "strategy error: 'imb10'" and rb.skip == "strategy error: KeyError: 'imb10'"
    ok = S.run_session(Crashy({"bad": ""}), t)
    assert ok.skip is None and len(ok.trades) == 2
    with pytest.raises(KeyError):
        S.run_session(Crashy(), t, on_error="raise")


def test_the_runner_counts_and_reports_sessions_dropped_by_error(capsys, l_tmp):
    days = ("2024-12-02", "2024-12-06")
    clean = S.run(Crashy, {"bad": ""}, *days, workers=1)
    assert clean["skipped_by_error"] == 0 and clean["no_trade"] == [] and len(clean["trades"]) == 10
    assert capsys.readouterr().err == ""
    for workers in (1, 2):
        r = S.run(Crashy, {"bad": "2024-12-03,2024-12-05"}, *days, workers=workers)
        assert r["skipped_by_error"] == 2 and r["sessions"] == 5 and r["used"] == 5 and r["skipped"] == []
        assert r["no_trade"] == [{"date": d, "reason": "strategy error: KeyError: 'imb10'"} for d in ("2024-12-03", "2024-12-05")]
        assert r["trades"] == [t for t in clean["trades"] if t["date"] not in ("2024-12-03", "2024-12-05")]
        err = capsys.readouterr().err
        assert "2 of 5 sessions DROPPED by a strategy error" in err and "2024-12-03" in err
    out = l_tmp / "err_bundle"
    S.write_bundle(r, out)
    cov = json.loads((out / "run.json").read_text())["coverage"]
    assert cov["skipped_by_error"] == 2 and cov["used"] == 5 and len(cov["no_trade"]) == 2
    with pytest.raises(KeyError):
        S.run(Crashy, {}, *days, workers=1, on_error="raise")
    with pytest.raises(ValueError):
        S.run(Crashy, {}, *days, workers=1, on_error="ignore")


@pytest.mark.parametrize("exc", [S.HoldoutSealed("sealed"), PermissionError("l2data: sealed"), S.LookAheadError("x"),
                                 MemoryError()])
def test_seal_and_look_ahead_errors_are_never_swallowed_as_a_skipped_session(exc):
    def fn(ctx, kind, arg):
        if kind == "bar":
            raise exc
    with pytest.raises(type(exc)):
        S.run_session(Script(fn), tape([(1, 100.0), (61, 100.0), (1700, 100.0)]))

    def sealed(ctx, kind, arg):                                       # a strategy reaching for a sealed tape
        S.load_tape("2025-01-02")
    with pytest.raises(S.HoldoutSealed):
        S.run_session(Script(sealed), tape([(1, 100.0), (1700, 100.0)]))
    try:
        import l2data
    except ImportError:
        return
    assert S._fatal(l2data.HoldoutSealed("x"))                        # the data layer's own seal error


# ---- strict_limit / unrealistic winners ----------------------------------------------------------------------------------
THRU = [(1, 100.0), (2, 98.25), (3, 99.0), (4, 99.75), (1700, 99.75)]      # print 2 trades through the limit AND the stop


def lim_long(c):
    c.limit_entry("long", 99.0, sl=98.5, tp=99.5)


def test_a_limit_fill_print_through_the_stop_is_a_winner_by_default_and_a_stop_out_under_strict_limit():
    t = S.run_session(Script(at_session(lim_long)), tape(THRU)).trades
    assert len(t) == 1 and t[0]["exit_reason"] == "tp" and t[0]["entry_price"] == 99.0 and t[0]["exit_price"] == 99.5
    assert t[0]["mae_pts"] == 0.75 and t[0]["net"] == 0.5 * 20 - 4          # the tester's law: a booked +$6
    assert S.unrealistic_winners(t) == t                                   # ... which the helper lists
    s = S.run_session(Script(at_session(lim_long)), tape(THRU), costs=S.Costs(strict_limit=True)).trades
    assert len(s) == 1 and s[0]["exit_reason"] == "sl" and s[0]["entry_price"] == 99.0
    assert s[0]["exit_price"] == 98.0 and s[0]["exit_ms"] == s[0]["entry_ms"]   # stopped ON the fill print: gap + 1 tick
    assert s[0]["net"] == -1.0 * 20 - 4 and S.unrealistic_winners(s) == []
    # short side, mirrored
    up = [(1, 100.0), (2, 101.75), (3, 101.0), (4, 100.25), (1700, 100.25)]

    def lim_short(c):
        c.limit_entry("short", 101.0, sl=101.5, tp=100.5)
    t = S.run_session(Script(at_session(lim_short)), tape(up)).trades
    assert t[0]["exit_reason"] == "tp" and S.unrealistic_winners(t) == t
    s = S.run_session(Script(at_session(lim_short)), tape(up), costs=S.Costs(strict_limit=True)).trades
    assert s[0]["exit_reason"] == "sl" and s[0]["exit_price"] == 102.0


def test_strict_limit_changes_nothing_else():
    cases = [
        ([(1, 100.0), (2, 98.75), (3, 99.0), (4, 99.75), (1700, 99.75)], lim_long, "tp"),      # through the limit, NOT the stop
        ([(1, 100.0), (2, 98.75), (3, 98.5), (1700, 98.5)], lim_long, "sl"),                    # stopped by a LATER print
        ([(1, 100.0), (2, 100.0), (1700, 100.0)], lambda c: c.market("long", sl=100.5), "sl"),  # market: still next print
        ([(1, 100.0), (2, 103.0), (3, 102.0), (1700, 102.0)], lambda c: c.stop_entry("long", 101.0, sl=103.5), "sl"),
    ]
    for prints, act, reason in cases:
        a = S.run_session(Script(at_session(act)), tape(prints)).trades
        b = S.run_session(Script(at_session(act)), tape(prints), costs=S.Costs(strict_limit=True)).trades
        assert a == b and len(a) == 1 and a[0]["exit_reason"] == reason
        assert S.unrealistic_winners(a) == []
    # the helper's rule: 'tp', a stop, MAE >= stop distance, filled at the order price (a limit entry)
    base = {"exit_reason": "tp", "entry_price": 99.0, "order_price": 99.0, "sl": 98.5, "mae_pts": 0.5}
    assert S.unrealistic_winners([base]) == [base]
    for change in ({"mae_pts": 0.25}, {"exit_reason": "sl"}, {"sl": None}, {"order_price": 98.75}, {"order_price": None}):
        assert S.unrealistic_winners([{**base, **change}]) == []
    assert S.unrealistic_winners([{**base, "order_price": None}], limit_only=False) == [{**base, "order_price": None}]


class TightLimit(S.Strategy):
    """Every minute 09:30-15:55: a limit 1 tick on the passive side of the last print, stop 2 ticks beyond it,
    target 1R; an unfilled order is replaced each minute; one position at a time (the verifier's probe)."""
    session_window = ("09:30", "16:00")
    session_independent = True
    DEFAULTS = {"stop": 2}

    def on_session(self, ctx):
        self.o, self.n = None, 0

    def on_bar(self, ctx, bar):
        if self.o is not None and self.o.status == "working":
            ctx.cancel(self.o)
        if not ctx.flat or ctx.now_ns >= S.et_ns(ctx.date, "15:55"):
            return
        self.n += 1
        sd = 1 if self.n % 2 else -1
        px = ctx.last_price - sd * ctx.tick
        d = self.p["stop"] * ctx.tick
        self.o = ctx.limit_entry("long" if sd > 0 else "short", px, sl=px - sd * d, tp=px + sd * d)


def test_unrealistic_winners_on_real_days_and_strict_limit_removes_them():
    days = ["2022-06-14", "2023-05-03", "2024-08-05", "2024-12-02"]
    a = S.run(TightLimit, {}, days=days, workers=1, keep_ns=True)
    b = S.run(TightLimit, {}, days=days, workers=1, keep_ns=True, strict_limit=True)
    bad = S.unrealistic_winners(a["trades"])
    assert a["unrealistic_winners"] == len(bad) >= 5 and len(a["trades"]) > 500      # a 2-tick stop: several per day
    assert b["unrealistic_winners"] == 0 and S.unrealistic_winners(b["trades"], limit_only=False) == []
    assert a["meta"]["strict_limit"] is False and a["meta"]["stress"] is None
    assert b["meta"]["strict_limit"] is True and b["meta"]["stress"] == {"strict_limit": True}
    # the two runs are identical up to the first limit fill whose print is through its stop; there the strict run
    # stops out ON the fill print (strict_limit touches nothing else)
    for d in days:
        ta, tb = ([x for x in r["trades"] if x["date"] == d] for r in (a, b))
        k = next(i for i, (x, y) in enumerate(zip(ta, tb)) if x != y)
        x, y = ta[k], tb[k]
        sd = 1 if y["side"] == "long" else -1
        assert (x["entry_ns"], x["entry_price"], x["sl"]) == (y["entry_ns"], y["entry_price"], y["sl"])
        assert y["exit_reason"] == "sl" and y["exit_ns"] == y["entry_ns"] and y["entry_price"] == y["order_price"]
        assert (y["exit_price"] + sd * 0.25 - y["sl"]) * sd <= 0          # the fill print was at/through the stop
        assert x["exit_ns"] >= y["exit_ns"]                               # the tester law held it at least as long
    # ... and a booked winner whose fill also exists in the strict run is a stop-out there
    by_entry = {(t["date"], t["entry_ns"]): t for t in b["trades"]}
    both = [(t, by_entry[(t["date"], t["entry_ns"])]) for t in bad if (t["date"], t["entry_ns"]) in by_entry
            and by_entry[(t["date"], t["entry_ns"])]["order_price"] == t["order_price"]]
    assert len(both) >= 3
    for t, x in both:
        assert x["exit_reason"] == "sl" and x["exit_ns"] == x["entry_ns"] and x["net"] < 0 < t["net"]


# ---- slip_ticks / latency_ms sensitivity ------------------------------------------------------------------------------------
PARAMS = {"tf": "15", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": 0.6}
RANGE = ("2024-11-18", "2024-12-06")


def test_market_fill_under_latency_and_slip_overrides():
    pr = [(0.05, 100.0), (0.085, 101.0), (0.2, 102.0), (0.25, 103.0), (5, 104.0), (1700, 105.0)]
    mk = at_session(lambda c: c.market("long"))
    t = S.run_session(Script(mk), tape(pr)).trades[0]
    assert t["entry_price"] == 101.25 and t["exit_price"] == 104.75                 # tester law: 85 ms, 1 tick
    t = S.run_session(Script(mk), tape(pr), costs=S.Costs(4.0, 2.0, latency_ms=250)).trades[0]
    assert t["entry_price"] == 103.5 and t["entry_ms"] == (T0 + 250_000_000) // 1_000_000
    assert t["exit_price"] == 104.5                                                 # the flatten pays 2 ticks too
    t = S.run_session(Script(mk), tape(pr), costs=S.Costs(4.0, 0.0, latency_ms=0)).trades[0]
    assert t["entry_price"] == 100.0
    for bad in (dict(slippage_ticks=-1), dict(latency_ms=-5), dict(slippage_ticks=float("nan"))):
        with pytest.raises(ValueError):
            S.Costs(**bad)


def test_default_run_is_the_tester_law_and_the_options_are_recorded():
    base = S.run(l2ref.Donchian, PARAMS, *RANGE, workers=1)
    m = base["meta"]
    assert (m["slippage_ticks"], m["placement_ms"], m["strict_limit"], m["stress"]) == (1.0, 85, False, None)
    same = S.run(l2ref.Donchian, PARAMS, *RANGE, workers=1, slip_ticks=1, latency_ms=85, strict_limit=False)
    assert same["trades"] == base["trades"] and same["meta"]["stress"] is None
    hard = S.run(l2ref.Donchian, PARAMS, *RANGE, workers=2, **S.STRESS)
    assert S.STRESS == {"slip_ticks": 2.0, "latency_ms": 250}
    assert hard["meta"]["stress"] == S.STRESS and hard["meta"]["slippage_ticks"] == 2.0 and hard["meta"]["placement_ms"] == 250
    assert hard["trades"] != base["trades"] and len(hard["trades"]) > 20
    # the kwargs are the same thing as the two older routes: Costs(slippage) and a class-level placement_ms
    assert S.run(l2ref.Donchian, PARAMS, *RANGE, workers=1, slip_ticks=2)["trades"] == \
        S.run(l2ref.Donchian, PARAMS, *RANGE, workers=1, costs=S.Costs(4.0, 2.0))["trades"]
    assert S.run(l2ref.Donchian, PARAMS, *RANGE, workers=1, latency_ms=0)["trades"] == \
        S.run(V.DonchianNoLatency, PARAMS, *RANGE, workers=1)["trades"]
    # one more tick of slip per side costs a market-in / stop-or-flatten-out trade exactly $10 when the prints are the same
    s2 = S.run(l2ref.Donchian, PARAMS, *RANGE, workers=1, slip_ticks=2)
    assert sum(t["net"] for t in s2["trades"]) < sum(t["net"] for t in base["trades"])


class Fz(S.Strategy):
    """A small random order flow (market / stop / limit with brackets) for the stressed differential."""
    session_window = ("09:30", "11:00")
    DEFAULTS = {"seed": 0}

    def times(self):
        return ["10:55"]

    def on_session(self, ctx):
        self.r = random.Random(f"{self.p['seed']}|{ctx.date}")

    def on_time(self, ctx, t):
        ctx.flatten("time")

    def on_bar(self, ctx, bar):
        r, lp, t = self.r, ctx.last_price, ctx.tick
        side = r.choice(("long", "short"))
        sd = 1 if side == "long" else -1
        kw = {"sl": lp - sd * r.randint(2, 40) * t, "tp": lp + sd * r.randint(2, 60) * t}
        u = r.random()
        if u < 0.3:
            ctx.market(side, **kw)
        elif u < 0.6:
            ctx.stop_entry(side, lp + sd * r.randint(1, 12) * t, sl=lp - sd * 5.0, tp_rr=1.0)
        elif u < 0.9:
            ctx.limit_entry(side, lp - sd * r.randint(1, 12) * t, sl=lp - sd * 10.0, tp_rr=1.0)


KEYS = ("date", "side", "qty", "entry_ns", "entry_price", "exit_ns", "exit_price", "exit_reason", "order_price",
        "sl", "tp", "gross", "commission", "net", "mae_pts", "mfe_pts", "mae_usd", "mfe_usd", "bars", "seconds")


@pytest.mark.parametrize("slip,lat", [(2.0, 250), (2.0, 85), (1.0, 250), (3.0, 1000), (0.0, 0)])
def test_stressed_runs_match_the_tester_engine_with_the_same_slip_and_latency(slip, lat):
    """slip_ticks / latency_ms are the tester's own two knobs (Costs.slippage_ticks, Strategy.placement_ms): l2sim
    with the overrides equals the tester's engine configured the same way."""
    E = pytest.importorskip("homebase.backtest.engine")
    from homebase.backtest.tape import Tape as HBTape
    n = 0
    for iso in ("2022-06-13", "2024-08-05"):
        t = S.load_tape(iso)
        hb = HBTape(t.root, t.date, t.contract, array("q", t.ts.tolist()), array("d", t.px.tolist()),
                    array("i", t.size.tolist()), dict(t.daily))
        a = Fz({"seed": 3})
        a.placement_ms = lat                                           # the tester's route
        ra = E.run_session(a, hb, E.Costs(4.0, slip), qty=1, daily=[])
        assert ra.skip is None
        rb = S.run_session(Fz({"seed": 3}), t, S.Costs(4.0, slip, latency_ms=lat))      # the sensitivity route
        assert [x.to_dict() for x in ra.trades] == [{k: x[k] for k in KEYS} for x in rb.trades]
        n += len(rb.trades)
    assert n > 40


def test_cli_passes_the_sensitivity_flags(capsys):
    rc = S.main(["run", "l2ref:Donchian", "--inputs", json.dumps(PARAMS), "--start", "2024-12-02", "--end", "2024-12-04",
                 "--workers", "1", "--slip-ticks", "2", "--latency-ms", "250", "--strict-limit"])
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0 and line["stress"] == {"slip_ticks": 2.0, "latency_ms": 250, "strict_limit": True}
    assert line["skipped_by_error"] == 0 and line["unrealistic_winners"] == 0 and line["out"] is None
    rc = S.main(["run", "l2ref:Donchian", "--inputs", json.dumps(PARAMS), "--start", "2024-12-02", "--end", "2024-12-04",
                 "--workers", "1"])
    assert rc == 0 and json.loads(capsys.readouterr().out.strip().splitlines()[-1])["stress"] is None
