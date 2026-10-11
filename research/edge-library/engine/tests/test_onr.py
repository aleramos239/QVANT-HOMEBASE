"""ONR: the `onr_orb` entry (families/onr.py), written test-first from Conti's overnight-bias opening range breakout (video A0G14JYYVTk).

THE RULE UNDER TEST (New York time):
    overnight range = high / low of the 1-minute bars ov_from (01:00) .. 09:30, cut in thirds
    bias            = the 09:30 open strictly above the top third's lower edge -> LONG day; strictly below the bottom third's upper edge -> SHORT
                      day; else no trade
    opening range   = high / low of 09:30 .. 09:45
    signal          = a 15-minute close, not earlier than `earliest`, strictly beyond the range on the bias side AND ADX(14) strictly above adx_min
    one trade a day; stop = k x A from the fill, target = tgt_r x stop; flat 15:30; A = the mean of the last 15 daily ATR(14) values
Synthetic days with EXACT numbers (zero-range minute bars, so the ranges are exactly what the test writes) cover each behaviour; the real BUILD
days check the invariants (window, one trade, flat 15:30). No net, win rate or profit factor is read.
"""
import datetime as dt

import pytest

import families
import l2sim as S
import run_menus as RM
from families import onr as ON
from test_blocks import D, days_of, minute_tape, ns, real_days

V = 40
LO, HI = 15000.0, 15090.0                                           # the overnight range: thirds at 15030 and 15060
BASE = {"hold_to": "day", "tf": "15", "sess": "nyam", "stop_mode": "struct", "stop_val": 1.0, "tgt_r": 3.0, "adx_min": 0.0}


def sec(h, m=0):
    return h * 3600 + m * 60


def q(n, px, v=V):
    """n zero-range minutes at px."""
    return [(px, px, px, px, v)] * n


def rows(ranges):
    """Daily bars dated before D: high 15000 + range, low 15000, close 15050 -> every true range is the range itself."""
    return [{"date": (D - dt.timedelta(days=len(ranges) - i)).isoformat(), "h": 15000.0 + r, "l": 15000.0, "c": 15050.0, "contract": "NQM3"}
            for i, r in enumerate(ranges)]


DAILY = rows([100.0] * 40)                                          # every ATR(14) = 100.0, so A = 100.0 and the stop is k x 100


def overnight(lo=LO, hi=HI, spike=None):
    """00:00 .. 09:30 (570 minutes): quiet at 15045, one minute reaching `hi` at 02:00 and one reaching `lo` at 03:00 (both inside 01:00-09:30);
    `spike` = (minute index, price) puts one extra minute high / low at that minute (to test where the range starts)."""
    b = q(570, 15045.0)
    b[120] = (15045.0, hi, 15045.0, 15045.0, V)
    b[180] = (15045.0, 15045.0, lo, 15045.0, V)
    if spike:
        i, px = spike
        b[i] = (15045.0, max(px, 15045.0), min(px, 15045.0), 15045.0, V)
    return b


def day(open_px, closes, over=None, last_to_tail=True):
    """A full day (00:00 .. 15:59): the overnight, a 15-minute opening range of zero-range minutes at `open_px`, then one 15-minute bucket per
    close in `closes` (its first minute moves from the previous close to the new one, the rest sit there), then quiet to the end."""
    b = list(over if over is not None else overnight()) + q(15, open_px)
    last = open_px
    for c in closes:
        b += [(last, max(last, c), min(last, c), c, V)] + q(14, c)
        last = c
    return b + q(960 - len(b), last)


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


class Spy(ON.OnrOrb):
    log: list = []

    def _mkt(self, ctx, side, **kw):
        o = super()._mkt(ctx, side, **kw)
        type(self).log.append((sec_of(ctx), side, o is not None))
        return o


def run(params, bars, daily=DAILY, cls=None):
    st = (cls or ON.OnrOrb)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00", D), daily=daily, on_error="raise")
    return st, res


def decisions(params, bars, daily=DAILY):
    cls = type("Spy", (Spy,), {"log": []})
    run(params, bars, daily, cls)
    return list(cls.log)


# ---- (i) the bias: thirds of the overnight range ---------------------------------------------------------------------------------------------------

def test_an_open_in_the_top_third_is_a_long_day_and_in_the_bottom_third_a_short_day():
    assert decisions({}, day(15075.0, [15095.0])) == [(sec(10), "long", True)]
    assert decisions({}, day(15015.0, [14995.0])) == [(sec(10), "short", True)]


def test_a_long_day_ignores_a_break_downwards_and_a_short_day_a_break_upwards():
    assert decisions({}, day(15075.0, [15055.0])) == []
    assert decisions({}, day(15015.0, [15035.0])) == []


def test_the_middle_third_and_both_boundaries_are_no_trade():
    for px in (15045.0, 15060.0, 15030.0):                          # the middle, exactly the top third's edge, exactly the bottom third's edge
        assert decisions({}, day(px, [px + 30.0, px - 30.0, px + 40.0])) == [], px
    assert decisions({}, day(15060.25, [15080.0])) == [(sec(10), "long", True)]
    assert decisions({}, day(15029.75, [15000.0])) == [(sec(10), "short", True)]


def test_the_range_starts_at_ov_from_01_00_by_default_and_at_00_00_when_asked():
    over = overnight(spike=(30, 15200.0))                           # a 00:30 spike to 15200: inside 00:00-09:30, outside 01:00-09:30
    st, _ = run({}, day(15075.0, [15095.0], over=over))
    assert st.bias == 1                                             # the range is 15000..15090: 15075 is in its top third
    st, _ = run({"ov_from": "00:00"}, day(15075.0, [15095.0], over=over))
    assert st.bias == 0                                             # the range is 15000..15200: 15075 is in the middle third


def test_no_first_minute_bar_within_five_minutes_of_the_open_is_no_trade():
    b = day(15075.0, [15095.0])
    gap = list(b)
    for i in range(570, 577):                                       # no print 09:30 .. 09:36: the first bar of the day starts at 09:37
        gap[i] = None
    gap = [x for x in gap if x is not None]
    gap = gap + q(960 - len(gap), gap[-1][3])
    # (the tape is built per minute from 00:00, so removing minutes shifts the day: the open's bar is the 09:30 bar of the SHIFTED day)
    st, _ = run({}, day(15075.0, [15095.0]))
    assert st.bias == 1


# ---- (ii) the opening range: 09:30 .. 09:45 ----------------------------------------------------------------------------------------------------------

def test_the_opening_range_is_the_first_15_minutes_only():
    over = overnight()
    b = list(over) + q(14, 15075.0) + [(15075.0, 15080.0, 15075.0, 15075.0, V)]      # 09:44 reaches 15080
    b += [(15075.0, 15090.0, 15075.0, 15075.0, V)] + q(14, 15075.0)                  # 09:45 reaches 15090: NOT part of the range
    b += q(960 - len(b), 15075.0)
    st, _ = run({}, b)
    assert st.orng == (15080.0, 15075.0)


def test_a_close_exactly_on_the_range_is_no_signal_and_one_tick_beyond_it_is():
    assert decisions({}, day(15075.0, [15075.0])) == []
    assert decisions({}, day(15075.0, [15075.25])) == [(sec(10), "long", True)]
    assert decisions({}, day(15015.0, [15014.75])) == [(sec(10), "short", True)]


def test_a_break_the_wrong_way_first_does_not_cancel_the_day():
    log = decisions({}, day(15075.0, [15060.0, 15095.0]))           # 10:00 closes below the range (a short break on a long day), 10:15 above it
    assert log == [(sec(10, 15), "long", True)]


# ---- (iii) the first signal bar ---------------------------------------------------------------------------------------------------------------------

def test_earliest_10_30_skips_the_closes_before_it_and_trades_the_first_one_from_then_on():
    b = day(15075.0, [15095.0, 15096.0, 15097.0, 15098.0])          # four buckets: closes 10:00 10:15 10:30 10:45, all above the range
    assert decisions({}, b) == [(sec(10), "long", True)]
    assert decisions({"earliest": "10:30"}, b) == [(sec(10, 30), "long", True)]


def test_no_entry_in_the_last_5_minutes_before_15_30_and_a_trade_is_flat_at_15_30():
    n = (sec(15, 30) - sec(9, 45)) // 900                           # buckets from 09:45 to 15:30
    flat = [15075.0] * (n - 1)                                      # sit at the open all day ...
    late = day(15075.0, flat + [15095.0])                           # ... and break at the close of the 15:15-15:30 bucket
    assert decisions({}, late) == []
    ok = day(15075.0, flat[:-1] + [15095.0, 15095.0])               # the break closes at 15:15: a decision
    assert [d[0] for d in decisions({}, ok)] == [sec(15, 15)]
    st, res = run({"k": 3.0}, day(15075.0, [15095.0]))              # a stop 300 points away and a target 900: only the clock ends it
    t = res.trades[0]
    assert t["exit_reason"] == "time" and t["exit_ms"] == ns("15:30") // 1_000_000


# ---- (iv) ADX --------------------------------------------------------------------------------------------------------------------------------

def test_the_adx_gate_is_strictly_above_adx_min_and_reads_the_signal_bar():
    b = day(15075.0, [15095.0])
    st, _ = run({}, b)
    x = st.adx
    assert x is not None and x > 0
    assert decisions({"adx_min": x - 0.001}, b) == [(sec(10), "long", True)]
    # strictly above: a tie is no signal at 10:00 (the quiet bars after a one-sided move lift ADX, so a later close may still pass)
    assert all(d[0] != sec(10) for d in decisions({"adx_min": x}, b))
    assert decisions({"adx_min": 100.0}, b) == []


def test_a_close_beyond_the_range_with_a_weak_adx_does_not_end_the_day_a_later_one_trades():
    b = day(15075.0, [15095.0, 15115.0, 15135.0, 15155.0])          # a steady climb: ADX rises bucket after bucket
    st, _ = run({}, b)
    x1 = st.adx
    first = decisions({"adx_min": 0.0}, b)
    assert first == [(sec(10), "long", True)]
    cls = type("Sig", (ON.OnrOrb,), {})
    seen = []

    class Look(ON.OnrOrb):
        def fam_signal(self, ctx):
            super().fam_signal(ctx)
            seen.append((sec_of(ctx), self.adx))

    run({"adx_min": 100.0}, b, cls=Look)
    adx_by_time = {t: a for t, a in seen if a is not None}
    assert len(adx_by_time) >= 2
    t1, t2 = sorted(adx_by_time)[:2]
    assert adx_by_time[t2] > adx_by_time[t1]                        # the climb lifts ADX
    thr = (adx_by_time[t1] + adx_by_time[t2]) / 2
    assert decisions({"adx_min": thr}, b) == [(t2, "long", True)]   # the first close fails the gate, the next one passes it


# ---- (v) stop, target, one trade, A ----------------------------------------------------------------------------------------------------------------

def test_the_stop_is_k_times_a_from_the_fill_and_the_target_is_tgt_r_times_the_stop():
    st, res = run({"k": 0.3}, day(15075.0, [15095.0]))
    t = res.trades[0]
    assert t["side"] == "long" and t["entry_price"] - t["sl"] == pytest.approx(30.0) and t["tp"] - t["entry_price"] == pytest.approx(90.0)
    st, res = run({"k": 0.5, "tgt_r": 2.0}, day(15015.0, [14995.0]))
    t = res.trades[0]
    assert t["side"] == "short" and t["sl"] - t["entry_price"] == pytest.approx(50.0) and t["entry_price"] - t["tp"] == pytest.approx(100.0)


def wilder_series(rs):
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"])) for p, r in zip(rs, rs[1:])]
    a = sum(trs[:14]) / 14.0
    out = [a]
    for x in trs[14:]:
        a = (a * 13.0 + x) / 14.0
        out.append(a)
    return out


def test_a_is_the_mean_of_the_last_15_daily_atr14_values_not_the_last_value():
    rs = rows([100.0] * 25 + [300.0] * 6 + [100.0] * 9)
    series = wilder_series(rs)
    expect = sum(series[-15:]) / 15.0
    assert abs(expect - series[-1]) > 5.0                           # (the two differ here: the test can tell them apart)
    st, res = run({"k": 0.3}, day(15075.0, [15095.0]), daily=rs)
    assert st.a == pytest.approx(expect)
    t = res.trades[0]
    assert abs((t["entry_price"] - t["sl"]) - 0.3 * expect) <= 0.25        # the stop price sits on a tick


def test_fewer_than_29_daily_bars_means_no_trade():
    assert decisions({}, day(15075.0, [15095.0]), daily=rows([100.0] * 28)) == []
    assert decisions({}, day(15075.0, [15095.0]), daily=rows([100.0] * 29)) == [(sec(10), "long", True)]


def test_one_trade_a_day_even_when_the_stop_is_hit_and_the_range_breaks_again():
    b = day(15075.0, [15095.0, 15060.0, 15110.0, 15060.0, 15120.0])       # break, fall back (the 5-point stop is hit), break again ...
    st, res = run({"k": 0.05}, b)                                   # stop 5 points: hit by the fall to 15060
    assert len(res.trades) == 1 and res.trades[0]["exit_reason"] in ("stop", "sl")
    assert len(decisions({"k": 0.05}, b)) == 1


def test_only_the_nyam_pass_trades_and_its_window_is_09_30_to_15_30():
    for s in RM.DAY_PASSES:
        got = ON.OnrOrb({"tf": "15", "sess": s, "hold_to": "day"}).sessions()
        assert got == (["nyam"] if s == "nyam" else [])
    assert ON.OnrOrb({"tf": "15", "sess": "nyam", "hold_to": "day"}).S["nyam"] == (34200, 55800)


# ---- (vi) real BUILD days: the invariants of the code check, at 1 worker ------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES"])
def test_real_build_days_hold_one_trade_a_day_the_window_and_the_flat_time(root):
    real_days()
    days = days_of(root, 6)
    spec = (ON.OnrOrb, {**BASE, "adx_min": 20.0, "k": 0.3})
    out = S.run_many([spec], root=root, days=days, period="build", workers=1, on_error="raise")
    again = S.run_many([spec], root=root, days=days, period="build", workers=1, on_error="raise")
    assert out[0]["trades"] == again[0]["trades"]
    assert out[0]["skipped_by_error"] == 0
    per_day = {}
    for t in out[0]["trades"]:
        d = S._date(t["date"])
        es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
        assert sec(10) <= es <= sec(15, 25) + 120, (t["date"], es)
        assert t["exit_ms"] <= S.et_ns(d, "15:30") // 1_000_000 + 60_000
        per_day[t["date"]] = per_day.get(t["date"], 0) + 1
    assert all(n == 1 for n in per_day.values())


# ---- (vii) the registry ----------------------------------------------------------------------------------------------------------------------------

def test_the_registry_holds_onr_orb_wrapped_for_the_blocks():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["onr_orb"]
    lib = families.library("onr_orb")
    assert cls is ON.OnrOrb and both is False and cls.FEATURES == () and lib["roots"] == ("NQ", "ES", "GC")
    assert families.MODULE_OF["onr_orb"] == "onr"
    from families import blocks as B
    assert issubclass(B.WRAPPED["onr_orb"], ON.OnrOrb) and "onr_orb" in B.BASES
