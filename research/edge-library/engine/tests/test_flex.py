"""The open layer (families/_flex.py: an entry window, a day rule and an indicator gate on every wrapped family) and the three families it adds
(families/flex.py: ind_signal, win_break, win_bracket, win_candle).

THE RULES UNDER TEST (the module docstrings hold them in full)
  layer        w_start / w_end clip the DECISION time of an entry (a market order at a tf close, a bracket or a limit at its placement);
               days = a day rule of flexind.DAY_RULES (a day outside it is not run); gate = an indicator read on the closed tf bars since the
               restart, `with` / `against`, no value yet = both sides blocked. Every setting is OFF by default.
  ind_signal   an indicator crosses centre +/- lvl at a tf close -> a market entry with the crossing (follow) or against it (fade).
  win_break    the range of the 1-minute bars in [r_start, r_end), the FIRST tf close after r_end beyond it -> a market entry (follow / fade)
               or a limit at the broken edge; the pass that holds that close.
  win_bracket  OCO stop entries one tick beyond the range, placed at r_end.
  win_candle   the tf candle that opens at `start`, green long / red short (follow) or the other way (fade), at its close.
Checks: (i) the layer is on every wrapped family and OFF = trade for trade a fresh wrap; (ii) the three settings of the layer on exact
synthetic days; (iii) the families against independent restatements on seeded random days at every bar size; (iv) NO LOOK-AHEAD: rewriting
every bar after a decision changes nothing decided up to it; (v) the refusals. No net or win rate is read."""
import csv
import datetime as dt

import numpy as np
import pytest

import families
import flexind as FI
import l2sim as S
from families import _flat as FL
from families import _flex as FM
from families import blocks as B
from families import flex as FX
from test_blocks import DAILY, TICK, days_of, minute_tape, ns, rand_bars, real_days
from test_orb830 import BASE, FILL, HI, LO, PX, breaks_up, day, got, hold, run, sec

MS0 = ns("00:00") // 1_000_000
ORB = B.WRAPPED["orb_close"]
IND, WBRK, WBRA, WCAN = (B.WRAPPED[n] for n in ("ind_signal", "win_break", "win_bracket", "win_candle"))
DISP = B.WRAPPED["displace"]
BIG = {"hold_to": "day", "stop_mode": "pts", "stop_val": 400.0, "tgt_r": 0.0}        # a stop and no target that a test day never reaches


def trades(res):
    return [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"], t["sl"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


def go(cls, params, bars):
    st = cls({**BIG, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(**getattr(cls, "SCREEN_RUN", {})), daily=list(DAILY), on_error="raise")
    return st, res


# ---- (i) the layer is on every wrapped family and off = a fresh wrap -----------------------------------------------------------------------------
def test_every_wrapped_family_carries_the_layer_and_it_is_off_by_default():
    assert B.WRAPPED
    for n, c in B.WRAPPED.items():
        assert FM.FlexMods in c.__mro__, n
        d = c.defaults()
        assert (d["w_start"], d["w_end"], d["days"], d["gate"], d["g_side"]) == ("", "", "all", "off", "with"), n
        assert set(FM.KEYS) <= set(d), n


def test_apply_is_idempotent_and_off_switch_exists(monkeypatch):
    before = [c.__bases__ for c in B.WRAPPED.values()]
    assert FM.apply() == 0
    assert [c.__bases__ for c in B.WRAPPED.values()] == before
    monkeypatch.setenv("HOMEBASE_FLEX", "0")
    assert FM.apply() == 0


NAMES = sorted(B.WRAPPED)


@pytest.mark.parametrize("name", NAMES)
def test_off_is_trade_for_trade_a_fresh_wrap(name):
    """A fresh B._wrap (no layer) and the patched class give the same inputs (old keys) and the same trades on a seeded day, per session."""
    cls = B.WRAPPED[name]
    fresh = B._wrap(name, B.BASES[name][0])
    assert FM.FlexMods not in fresh.__mro__
    assert (fresh.__module__, fresh.__qualname__) == (cls.__module__, cls.__qualname__)         # the fingerprint's class path
    tape = minute_tape(rand_bars(960, 11), "00:00")
    ran = 0
    for s in ("london", "pre", "nyam"):
        out = []
        for c in (cls, fresh):
            try:
                st = c({"hold_to": "day", "tf": "5", "sess": s})
                st.ROLLS = frozenset()
                r = S.run_session(st, tape, costs=S.Costs(**getattr(c, "SCREEN_RUN", {})), daily=list(DAILY), on_error="raise")
                out.append(({x: v for x, v in st.p.items() if x not in FM.KEYS + FL.KEYS}, r.trades))
            except Exception as e:                                                   # noqa: BLE001 - the same refusal from both is a match
                out.append((type(e).__name__, str(e)))
        assert out[0] == out[1], (name, s)
        ran += isinstance(out[0][0], dict)
    assert ran == 3


# ---- (ii) the layer's settings on exact days -----------------------------------------------------------------------------------------------------
def test_the_entry_window_clips_the_decision_time():
    bars = day(breaks_up("09:36"))                                                        # the break bar closes 09:37:00; the fill is :15 later
    assert got(run(ORB, BASE, {}, bars)[1]) == [(sec(9, 37, FILL), "long", HI + 4, LO, None)]
    assert got(run(ORB, BASE, {"w_end": "09:38"}, bars)[1])                              # decided before 09:38: kept
    assert got(run(ORB, BASE, {"w_end": "09:37"}, bars)[1]) == []                        # decided AT 09:37: w_end is exclusive
    assert got(run(ORB, BASE, {"w_start": "09:37"}, bars)[1])                            # decided at 09:37: w_start is inclusive
    late = got(run(ORB, BASE, {"w_start": "09:38"}, bars)[1])                           # the 09:37 bar also closes beyond the range: the NEXT break
    assert [x[0] for x in late] == [sec(9, 38, FILL)]                                    # (orb_close takes the next one itself)
    assert got(run(ORB, BASE, {"w_start": "09:39"}, bars)[1]) == []
    assert got(run(ORB, BASE, {"w_start": "09:30", "w_end": "09:40"}, bars)[1])


def test_a_window_that_ends_before_it_starts_or_is_not_a_time_is_refused():
    with pytest.raises(ValueError):
        ORB({**BASE, "w_start": "10:00", "w_end": "09:45"})
    with pytest.raises(ValueError):
        ORB({**BASE, "w_end": "25:00"})
    with pytest.raises(ValueError):
        ORB({**BASE, "w_start": "17:30"})                                                # the 17:00-18:00 break of the Globex day


def test_the_day_rule_skips_days_before_the_tape_is_read():
    mon, tue = dt.date(2025, 2, 3), dt.date(2025, 2, 4)
    st = ORB({**BASE, "days": "mon"})
    assert st.trades_on(mon) and not st.trades_on(tue)
    nfp = next(r["date"] for r in csv.DictReader(FI.EVENTS.open()) if r["type"] == "NFP")
    assert ORB({**BASE, "days": "nfp"}).trades_on(dt.date.fromisoformat(nfp))
    assert not ORB({**BASE, "days": "nonews"}).trades_on(dt.date.fromisoformat(nfp))
    assert ORB({**BASE, "days": "news"}).trades_on(dt.date.fromisoformat(nfp))
    with pytest.raises(ValueError):
        ORB({**BASE, "days": "payday"})                                                  # a typo must not trade every day


def test_the_indicator_gate_reads_closed_bars_and_blocks_both_sides_without_a_value():
    bars = day(breaks_up("09:36"))
    want = [(sec(9, 37, FILL), "long", HI + 4, LO, None)]
    assert got(run(ORB, BASE, {"gate": "rsi", "g_n": 14, "g_lvl": -49.0}, bars)[1]) == want        # bull = RSI > 1: always, once it has a value
    assert got(run(ORB, BASE, {"gate": "rsi", "g_n": 14, "g_lvl": 60.0}, bars)[1]) == []           # bull needs RSI > 110
    assert got(run(ORB, BASE, {"gate": "rsi", "g_n": 14, "g_lvl": 60.0, "g_side": "against"}, bars)[1]) == []   # bear needs RSI < -10
    assert got(run(ORB, BASE, {"gate": "rsi", "g_n": 14, "g_lvl": -49.0, "g_side": "against"}, bars)[1]) == []  # a long against a bull
    assert got(run(ORB, BASE, {"gate": "rsi", "g_n": 500, "g_lvl": -49.0}, bars)[1]) == want       # 576 bars by 09:36: a value
    assert got(run(ORB, BASE, {"gate": "adx", "g_n": 20, "g_lvl": 0.0}, bars)[1]) == want           # a regime gate: ADX >= 0 once it has a value
    assert got(run(ORB, BASE, {"gate": "adx", "g_n": 300, "g_lvl": 0.0}, bars)[1]) == []           # needs 600 bars, 576 exist: no value, no trade
    with pytest.raises(ValueError):
        ORB({**BASE, "gate": "rsi", "g_n": 0})


# ---- (iii) the families against independent restatements -----------------------------------------------------------------------------------------
def aggregate(bars, tf):
    """1-minute (o, h, l, c, v) from 00:00 -> [(close second, o, h, l, c)] of the tf bars on the clock grid."""
    out = []
    for k in range(len(bars) // tf):
        w = bars[k * tf:(k + 1) * tf]
        out.append(((k + 1) * tf * 60, w[0][0], max(x[1] for x in w), min(x[2] for x in w), w[-1][3]))
    return out


def rsi_series(closes, n):
    out, ag, al = [None] * len(closes), None, None
    g = l = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        if ag is None:
            g, l = g + up, l + dn
            if i < n:
                continue
            ag, al = g / n, l / n
        else:
            ag, al = (ag * (n - 1) + up) / n, (al * (n - 1) + dn) / n
        out[i] = 50.0 if al == 0 and ag == 0 else 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


NYAM = S.SESS["nyam"]


def in_pass(end, a=NYAM[0], b=NYAM[1]):
    """A decision at a tf close `end` can place an entry in the pass [a, b): after its start, before its last 5 minutes."""
    return a < end < b - 300


@pytest.mark.parametrize("tf", ["1", "5", "15", "30"])
@pytest.mark.parametrize("mode", ["follow", "fade"])
def test_ind_signal_is_the_first_crossing_of_the_line_in_the_pass(tf, mode):
    n, lvl, hit = 14, 15.0, 0
    for seed in range(24):
        bars = rand_bars(960, 100 + seed, step=9.0)
        tb = aggregate(bars, int(tf))
        r = rsi_series([x[4] for x in tb], n)
        want = None
        for i in range(1, len(tb)):
            v, p = r[i], r[i - 1]
            if v is None or p is None or not in_pass(tb[i][0]):
                continue
            ev = 1 if p <= 50 + lvl < v else -1 if p >= 50 - lvl > v else 0
            if ev:
                side = "long" if (ev > 0) == (mode == "follow") else "short"
                want = (tb[i][0] + FILL, side)
                break
        _, res = go(IND, {"tf": tf, "sess": "nyam", "ind": "rsi", "n": n, "lvl": lvl, "mode": mode}, bars)
        have = [(t[0], t[1]) for t in trades(res)]
        assert have == ([want] if want else []), (seed, tf, mode)
        hit += bool(want)
    assert hit >= 2                                                                    # the check is not vacuous


@pytest.mark.parametrize("tf", ["1", "5", "15"])
@pytest.mark.parametrize("mode", ["follow", "fade"])
def test_win_break_is_the_first_close_beyond_the_range_after_it_ends(tf, mode):
    hit = 0
    for seed in range(14):
        bars = rand_bars(960, 300 + seed, step=5.0)
        a, b = 34200, 34200 + 15 * 60                                                     # 09:30 - 09:45
        win = bars[a // 60:b // 60]
        hi, lo = max(x[1] for x in win), min(x[2] for x in win)
        want = None
        for end, o, h, l, c in aggregate(bars, int(tf)):
            if end <= b or not in_pass(end):
                continue
            brk = "long" if c > hi else "short" if c < lo else None
            if brk:
                side = brk if mode == "follow" else ("short" if brk == "long" else "long")
                want = (end + FILL, side)
                break
        _, res = go(WBRK, {"tf": tf, "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "mode": mode}, bars)
        assert [(t[0], t[1]) for t in trades(res)] == ([want] if want else []), (seed, tf, mode)
        hit += bool(want)
    assert hit >= 5


def test_win_break_stops_at_the_other_edge_and_a_limit_waits_for_the_retest():
    bars = day(breaks_up("09:50"))                                                         # the range = 09:30-09:45 of the quiet day: the minutes 09:31/32
    bars = list(bars)
    st, res = go(WBRK, {"tf": "1", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "stop_mode": "struct", "stop_val": 1.0}, bars)
    t = trades(res)
    assert [(x[1], x[3]) for x in t] == [("long", LO)]                                    # sl = the far edge
    st, res = go(WBRK, {"tf": "1", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "entry": "limit", "wait": "0",
                        "stop_mode": "struct", "stop_val": 1.0}, bars)
    assert [x[1:] for x in trades(res)] == [("long", HI, LO)]                             # the day falls back through the edge: the retest fills AT it
    wide = list(bars)
    wide[S._sec("09:52") // 60:] = [hold(HI + 20.0)] * (960 - S._sec("09:52") // 60)       # it never comes back
    st, res = go(WBRK, {"tf": "1", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "entry": "limit", "wait": "0",
                        "stop_mode": "struct", "stop_val": 1.0}, wide)
    assert trades(res) == []


def test_win_bracket_places_both_stops_at_r_end_and_the_first_through_fills():
    quiet_day = day()                                                                     # range 14980 / 15020 inside 09:30-09:45
    up_day = list(quiet_day)
    up_day[S._sec("09:50") // 60] = (PX, HI + 10, PX, HI + 8, 40)
    dn_day = list(quiet_day)
    dn_day[S._sec("09:50") // 60] = (PX, PX, LO - 10, LO - 8, 40)
    params = {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "stop_mode": "struct", "stop_val": 1.0}
    assert trades(go(WBRA, params, quiet_day)[1]) == []
    t = trades(go(WBRA, params, up_day)[1])                                                 # the bar gaps through the stop: the fill is the print
    assert [x[1] for x in t] == ["long"] and t[0][2] - t[0][3] == pytest.approx(HI + TICK - LO)   # the stop is the other edge's distance from the fill
    t = trades(go(WBRA, params, dn_day)[1])
    assert [x[1] for x in t] == ["short"] and t[0][3] - t[0][2] == pytest.approx(HI - (LO - TICK))


@pytest.mark.parametrize("tf,start", [("5", "09:30"), ("15", "09:30"), ("5", "08:30"), ("5", "10:00"), ("30", "09:30"), ("1", "09:30")])
@pytest.mark.parametrize("mode", ["follow", "fade"])
def test_win_candle_is_the_candle_at_start_followed_or_faded_at_its_close(tf, start, mode):
    step, a = int(tf) * 60, S._sec(start)
    sess = next(s for s in S.ORDER7 if S.SESS[s][0] < a + step < S.SESS[s][1] - 300)
    hit = 0
    for seed in range(10):
        bars = rand_bars(960, 500 + seed, step=7.0)
        w = bars[a // 60:(a + step) // 60]
        o, c = w[0][0], w[-1][3]
        want = None if c == o else ((a + step + FILL), ("long" if (c > o) == (mode == "follow") else "short"))
        _, res = go(WCAN, {"tf": tf, "sess": sess, "start": start, "mode": mode}, bars)
        assert [(t[0], t[1]) for t in trades(res)] == ([want] if want else []), (seed, tf, start, mode)
        hit += bool(want)
    assert hit >= 8


def test_win_candle_gates_all_must_hold():
    bars = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    base = list(bars)
    base[S._sec("09:30") // 60:S._sec("09:35") // 60] = [(PX, PX + TICK, PX - TICK, PX + 2 * TICK, 40), (PX + 2 * TICK, PX + 8.0, PX + 2 * TICK, PX + 6.0, 40),
                                                       hold(PX + 6.0), hold(PX + 6.0), hold(PX + 6.0)]
    p = {"tf": "5", "sess": "nyam", "start": "09:30"}
    assert [x[1] for x in trades(go(WCAN, p, base)[1])] == ["long"]                       # body 6, range 8.25
    assert [x[1] for x in trades(go(WCAN, {**p, "body_pts": 6.0}, base)[1])] == ["long"]
    assert trades(go(WCAN, {**p, "body_pts": 6.25}, base)[1]) == []
    assert [x[1] for x in trades(go(WCAN, {**p, "body_r": 0.7}, base)[1])] == ["long"]    # 6 / 8.25 = 0.727
    assert trades(go(WCAN, {**p, "body_r": 0.8}, base)[1]) == []


def test_displace_is_the_first_body_over_k_atr_of_the_bars_before_it():
    flat = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960
    a = S._sec("09:50") // 60
    big = (PX, PX + 6.5, PX - TICK, PX + 6.0, 40)                       # body 6.0, close 0.5 under the high (range 6.5 + tick)
    p = {"tf": "5", "sess": "nyam", "k": 2.0}
    bars = list(flat)
    bars[a:a + 5] = [big, hold(PX + 6.0), hold(PX + 6.0), hold(PX + 6.0), hold(PX + 6.0)]
    t = trades(go(DISP, p, bars)[1])
    assert [x[1] for x in t] == ["long"] and t[0][0] == S._sec("09:55") + FILL
    assert [x[1] for x in trades(go(DISP, {**p, "mode": "fade"}, bars)[1])] == ["short"]
    small = list(flat)
    small[a:a + 5] = [(PX, PX + 2.0, PX - TICK, PX + 1.0, 40)] + [hold(PX + 1.0)] * 4
    assert trades(go(DISP, {**p, "k": 10.0}, small)[1]) == []               # body 1.0 is under 10 x ATR
    assert [x[1] for x in trades(go(DISP, {**p, "close_r": 0.25}, bars)[1])] == ["long"]
    soft = list(flat)
    soft[a:a + 5] = [(PX, PX + 6.5, PX - TICK, PX + 3.0, 40)] + [hold(PX + 3.0)] * 4   # body 3.0, close mid-range
    assert trades(go(DISP, {**p, "k": 1.0, "close_r": 0.25}, soft)[1]) == []
    assert [x[1] for x in trades(go(DISP, {**p, "k": 1.0}, soft)[1])] == ["long"]
    twice = list(bars)
    b = S._sec("10:20") // 60
    twice[b:b + 5] = [(PX + 6.0, PX + 6.0 + TICK, PX - 1.0, PX - 0.5, 40)] + [hold(PX - 0.5)] * 4
    assert len(trades(go(DISP, p, twice)[1])) == 1                         # one trade a session


# ---- the layer on the new families ------------------------------------------------------------------------------------------------------------------
def test_the_layer_clips_and_gates_the_new_families_too():
    bars = rand_bars(960, 300, step=5.0)
    p = {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45"}
    free = trades(go(WBRK, p, bars)[1])
    assert free
    t0 = free[0][0]
    h, m = divmod((t0 - FILL) // 60, 60)
    close_txt = f"{h:02d}:{m:02d}"
    assert trades(go(WBRK, {**p, "w_end": close_txt}, bars)[1]) == []
    assert trades(go(WBRK, {**p, "w_start": close_txt}, bars)[1]) == free


# ---- (iv) no look-ahead ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cls,params", [
    (IND, {"tf": "5", "sess": "nyam", "ind": "rsi", "n": 14, "lvl": 15.0}),
    (IND, {"tf": "5", "sess": "nyam", "ind": "zscore", "n": 20, "lvl": 1.5, "mode": "fade"}),
    (IND, {"tf": "15", "sess": "london", "ind": "ema_x", "n": 9, "m": 21, "lvl": 0.3}),
    (WBRK, {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45"}),
    (WBRK, {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "entry": "limit", "wait": "30"}),
    (WBRA, {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45"}),
    (WCAN, {"tf": "5", "sess": "nyam", "start": "09:30", "k": 0.5}),
    (B.WRAPPED["open_candle"], {"tf": "5", "sess": "pre", "gate": "rsi", "g_n": 14, "g_lvl": -10.0, "w_end": "09:00"}),
])
def test_rewriting_every_bar_after_a_decision_changes_nothing_decided_up_to_it(cls, params):
    cut = S._sec("11:30") // 60
    seen = 0
    for seed in range(12):
        a = rand_bars(960, 700 + seed, step=6.0)
        b = a[:cut] + rand_bars(960 - cut, 9000 + seed, p0=a[cut - 1][3], step=14.0)
        ta = [t for t in trades(go(cls, params, a)[1]) if t[0] < cut * 60]
        tb = [t for t in trades(go(cls, params, b)[1]) if t[0] < cut * 60]
        assert ta == tb, (seed, params)
        seen += bool(ta)
    if cls is not B.WRAPPED["open_candle"]:
        assert seen >= 1


# ---- (v) refusals ------------------------------------------------------------------------------------------------------------------------------------
def test_windows_that_cannot_trade_are_refused_when_the_instance_is_built():
    ok = {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45"}
    WBRK(ok)
    with pytest.raises(ValueError):
        WBRK({**ok, "r_end": "09:30"})                                                    # not after r_start
    with pytest.raises(ValueError):
        WBRK({**ok, "r_end": "10:58"})                                                    # the first close after it is in the last 5 minutes
    with pytest.raises(ValueError):
        WBRK({**ok, "r_start": "20:00"})                                                  # an evening start needs an evening instance
    with pytest.raises(ValueError):
        WBRK({**ok, "mode": "fade", "entry": "limit"})
    with pytest.raises(ValueError):
        WCAN({"tf": "5", "sess": "nyam", "start": "09:32"})                               # not a whole 5-minute bar
    with pytest.raises(ValueError):
        IND({"tf": "5", "sess": "nyam", "ind": "adx"})                                     # a regime indicator has no side: it is a gate
    assert WBRK({**ok, "sess": "mid"}).sessions() == []                                   # the pass of the break is nyam, not mid
    assert WBRK(ok).sessions() == ["nyam"]


def test_the_families_are_in_the_library_and_the_run_menu_knows_their_settings():
    for n in ("ind_signal", "win_break", "win_bracket", "win_candle"):
        assert n in families.REGISTRY and n in B.WRAPPED and n in families.LIBRARY, n
        assert not families.ERRORS.get(n)
    assert families.ERRORS == {}


# ---- (vi) real build days ----------------------------------------------------------------------------------------------------------------------------
def _real(cls, params, root="NQ", n=6, workers=1):
    real_days()
    days = days_of(root, n)
    out = S.run_many([(cls, {**BIG, **params})], days=days, root=root, workers=workers, **dict(getattr(cls, "SCREEN_RUN", {})))
    return days, out[0]


def _key(r):
    return [(t["date"], t["entry_ms"], t["side"], t["entry_price"], t["exit_ms"], t["exit_price"]) for t in r["trades"]]


@pytest.mark.parametrize("name,params", [("orb_close", {"tf": "5", "sess": "nyam"}), ("open_candle", {"tf": "5", "sess": "pre"}),
                                         ("ib_n", {"tf": "5", "sess": "nyam"}), ("straddle", {"tf": "5", "sess": "pre"})])
def test_real_build_days_the_layer_off_is_the_fresh_wrap(name, params):
    cls = B.WRAPPED[name]
    fresh = B._wrap(name, B.BASES[name][0])
    _, a = _real(cls, params)
    _, b = _real(fresh, params)
    assert _key(a) == _key(b)


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_new_families_one_trade_a_day_inside_the_pass_and_the_same_at_1_and_4_workers(root):
    cases = [(WBRK, {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45"}),
             (IND, {"tf": "5", "sess": "nyam", "ind": "rsi", "n": 14, "lvl": 15.0}),
             (WCAN, {"tf": "5", "sess": "nyam", "start": "09:30"}),
             (WBRA, {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45"})]
    for cls, params in cases:
        days, a = _real(cls, params, root=root, workers=1)
        _, b = _real(cls, params, root=root, workers=4)
        assert _key(a) == _key(b), (root, cls.__name__)
        by_day = {}
        for t in a["trades"]:
            by_day.setdefault(t["date"], []).append(t)
            et = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, S.ET)
            s = et.hour * 3600 + et.minute * 60 + et.second
            assert sec(9, 30) < s < sec(10, 56), (root, cls.__name__, t["date"], s)
            assert t["exit_ms"] // 1000 <= int(dt.datetime.fromisoformat(t["date"]).replace(tzinfo=S.ET).timestamp()) + sec(15, 59)         # flat 15:58; a thin tape fills at its next print
        assert all(len(v) == 1 for v in by_day.values())
        assert by_day, (root, cls.__name__)


def test_real_build_days_the_day_rule_runs_only_its_days():
    days, r = _real(WBRK, {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "days": "mon"}, n=10)
    assert all(dt.date.fromisoformat(t["date"]).weekday() == 0 for t in r["trades"])
