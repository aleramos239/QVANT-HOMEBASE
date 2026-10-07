"""SWING LEVEL: engine/levels.py `sw` -- the owner's swing high / low (2026-10-06): a 5-minute bar whose high is above the 50 bars before it
AND the 50 bars after it (strict; a low mirrors it), the most recent one that no later bar traded beyond, over the last 5 sessions of one
contract, read once at the session's first decision.

(i) the pivot rule against a brute-force loop (random walks, ties, edges); (ii) the confirmation lag (a swing exists only n bars later) and
"untouched"; (iii) the level on synthetic sessions with an exact answer: history from prior sessions + today, fixed for the session, a roll
cuts the history, one-sided levels, no level; (iv) NO LOOK-AHEAD: the first decision does not change when prints after it change;
(v) the bar builder against a loop, and the cache file round trip; (vi) the `liq` trigger on the swing level. No net, win rate or profit factor is read.
"""
import datetime as dt
import math

import numpy as np
import pytest

import l2sim as S
import levels as LV
from test_blocks import D, QUIET, minute_tape, ns
from test_blocks_l2 import Probe
from test_liq import daily, flatg, go, run_liq, tape_of


# ---- (i) the pivot rule ----------------------------------------------------------------------------------------------------------------

def brute(h, l, n):
    hi = [i for i in range(n, len(h) - n) if all(h[i] > h[j] for j in range(i - n, i)) and all(h[i] > h[j] for j in range(i + 1, i + n + 1))]
    lo = [i for i in range(n, len(l) - n) if all(l[i] < l[j] for j in range(i - n, i)) and all(l[i] < l[j] for j in range(i + 1, i + n + 1))]
    return hi, lo


@pytest.mark.parametrize("n", [1, 3, 8, 50])
def test_pivots_are_the_strict_n_bar_extremes_of_a_brute_force_loop(n):
    rng = np.random.default_rng(n)
    for _ in range(6):
        c = np.cumsum(rng.integers(-3, 4, 400)).astype(float)                  # whole-number walks: many ties
        h, l = c + rng.integers(0, 3, 400), c - rng.integers(0, 3, 400)
        ih, il = LV.pivots(h, l, n)
        bh, bl = brute(h.tolist(), l.tolist(), n)
        assert ih.tolist() == bh and il.tolist() == bl
    assert len(brute(c.tolist(), c.tolist(), n)[0]) >= 0                         # (the loop itself runs on every n)


def test_a_tie_on_either_side_is_no_swing_and_the_edges_have_none():
    h = [1, 2, 3, 9, 3, 2, 1.0]
    l = [x - 1 for x in h]
    assert LV.pivots(h, l, 3)[0].tolist() == [3]
    assert LV.pivots([1, 2, 3, 9, 9, 2, 1.0], l, 3)[0].tolist() == []            # the same high twice: neither is above the other
    assert LV.pivots([9, 2, 3, 4, 3, 2, 1.0], l, 3)[0].tolist() == []            # a high at the very start has no bars before it
    assert LV.pivots(h[:6], l[:6], 3)[0].tolist() == []                           # fewer than 2n + 1 bars
    assert LV.pivots([5, 4, 3, 1, 3, 4, 5.0], [5, 4, 3, 1, 3, 4, 5.0], 3)[1].tolist() == [3]    # a low mirrors it


# ---- (ii) confirmation lag and "untouched" ---------------------------------------------------------------------------------------------

def test_a_swing_is_known_only_when_its_n_th_bar_after_has_closed():
    n = 4
    h = np.array([1, 2, 3, 4, 20, 4, 3, 2, 1, 0.5, 0.4], float)
    l = h - 1
    assert LV.untouched_swings(h[:4 + n], l[:4 + n], n) == (None, None)         # bars up to the 3rd after it: not yet
    assert LV.untouched_swings(h[:4 + n + 1], l[:4 + n + 1], n)[0] == 20.0       # the 4th bar after it has closed
    assert LV.untouched_swings(h, l, n)[0] == 20.0


def test_a_swing_that_a_later_bar_traded_beyond_is_dropped_and_an_equal_touch_is_not_beyond():
    n = 3
    h = np.array([1, 2, 3, 10, 3, 2, 1, 1, 1, 1, 6, 1, 1, 1, 1, 1, 1, 1, 1, 1.0])      # a swing high at 3 (10) and a lower one at 10 (6)
    l = h - 1
    assert LV.untouched_swings(h, l, n)[0] == 6.0                                       # the most recent one
    h2 = h.copy()
    h2[16] = 7.0                                                                      # a bar after the 3 that confirm it, above 6 (under 10): 6 is gone, the 7 is a swing itself
    assert LV.untouched_swings(h2, h2 - 1, n)[0] == 7.0
    h3 = h2.copy()
    h3[17] = 10.5                                                                     # above 10 as well: nothing is left
    assert LV.untouched_swings(h3, h3 - 1, n)[0] is None
    h4 = h.copy()
    h4[16] = 6.0                                                                      # exactly the swing price: not traded beyond it
    assert LV.untouched_swings(h4, h4 - 1, n)[0] == 6.0
    h5 = h.copy()
    h5[12] = 6.0                                                                      # a tie INSIDE its 3 bars after: it was never a swing at all
    assert LV.untouched_swings(h5, h5 - 1, n)[0] == 10.0


def test_untouched_swings_agree_with_a_loop_on_random_series():
    rng = np.random.default_rng(7)
    for n in (2, 5, 20):
        for _ in range(8):
            c = np.cumsum(rng.normal(0, 1, 300))
            h, l = c + rng.random(300), c - rng.random(300)
            bh, bl = brute(h.tolist(), l.tolist(), n)
            eh = [h[i] for i in bh if all(h[j] <= h[i] for j in range(i + 1, 300))]
            el = [l[i] for i in bl if all(l[j] >= l[i] for j in range(i + 1, 300))]
            assert LV.untouched_swings(h, l, n) == (eh[-1] if eh else None, el[-1] if el else None)


# ---- (iii) the level on synthetic sessions ---------------------------------------------------------------------------------------------

NB = 120                                                       # bars in each synthetic prior session
DATES = [r["date"] for r in daily()[-5:]]


def history(peaks=(), troughs=()):
    """5 prior sessions of NB 5-minute bars each (no swings of their own: a ripple that ties itself), with the given (global bar, price) peaks and troughs."""
    n = 5 * NB
    h = 15000.0 + (np.arange(n) % 7) * 3.0
    l = h - 10.0
    for i, px in peaks:
        h[i], l[i] = px, px - 10.0
    for i, px in troughs:
        l[i], h[i] = px, px + 10.0
    base = S.et_ns(D - dt.timedelta(days=30), "18:00")
    end = base + (np.arange(n) + 1) * 300 * S.NS
    return {d: (end[k * NB:(k + 1) * NB], h[k * NB:(k + 1) * NB], l[k * NB:(k + 1) * NB]) for k, d in enumerate(DATES)}


def stub(monkeypatch, hist):
    monkeypatch.setattr(LV, "session_bars", lambda root, iso, tf=LV.SW_TF: hist.get(iso))


class Sw(Probe):
    asked: list = []

    def fam_signal(self, ctx):
        type(self).asked.append(((ctx.now_ns - ns("00:00")) // S.NS, LV.levels(self, "sw")))


def quiet_day(g=()):
    """19:58 .. 11:00: one flat price (no swing of its own: every bar ties), then G from 09:30 on. (day_bars has outlier bars and spikes of its own.)"""
    return flatg(812) + list(g or flatg(90))


def sw_at(bars=None, rolls=(), sess="nyam"):
    cls = type("W", (Sw,), {"asked": []})
    go(cls, {"hold_to": "day", **QUIET, "tf": "5", "sess": sess}, tape_of(bars or quiet_day()), rolls)
    return cls.asked


def test_the_level_is_the_latest_untouched_swing_of_the_last_five_sessions_and_stays_fixed_for_the_session(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0), (450, 15120.0), (520, 15130.0), (560, 15150.0)], troughs=[(400, 14700.0)]))
    got = sw_at()
    assert got and {x[1]["sw"] for x in got} == {(15150.0, 14700.0)}          # 15120 was passed by the 15130 bar, 15300 is older than 15150
    assert len({x[1]["sw"] for x in got}) == 1                                  # the same price at every decision of the session


def test_a_peak_the_session_has_already_traded_beyond_is_not_a_level(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)], troughs=[(400, 14700.0)]))
    assert sw_at()[0][1]["sw"] == (15300.0, 14700.0)
    over = quiet_day()
    over[100] = over[110] = (15000.0, 15400.0, 15000.0, 15000.0, 40)      # two 5-minute bars at 15400 (a tie: no swing of their own) above the 15300 peak
    assert sw_at(over)[0][1]["sw"] == (math.inf, 14700.0)                       # no swing high left: one-sided


def test_one_sided_levels_use_an_unreachable_side_and_no_swing_means_no_level(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)]))
    assert sw_at()[0][1]["sw"] == (15300.0, -math.inf)
    stub(monkeypatch, history(troughs=[(300, 14700.0)]))
    assert sw_at()[0][1]["sw"] == (math.inf, 14700.0)
    stub(monkeypatch, history())
    assert all("sw" not in x[1] for x in sw_at())
    stub(monkeypatch, {})                                                      # no history: today alone has far fewer than 101 bars
    assert all("sw" not in x[1] for x in sw_at())


def test_a_contract_roll_cuts_the_history(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)], troughs=[(400, 14700.0), (580, 14800.0)]))   # the 14800 trough is in the newest session
    assert sw_at()[0][1]["sw"] == (15300.0, 14800.0)
    assert sw_at(rolls={DATES[3]})[0][1]["sw"] == (math.inf, 14800.0)           # the roll day is the first session of the new contract: older ones are out
    assert all("sw" not in x[1] for x in sw_at(rolls={D.isoformat()}))          # today is a roll day: only today's own (too few) bars


def test_the_swing_level_is_known_in_every_session_of_the_day(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)], troughs=[(400, 14700.0)]))
    for sess in ("asia", "london", "pre", "nyam"):
        assert all(x[1]["sw"] == (15300.0, 14700.0) for x in sw_at(sess=sess)), sess


# ---- (iv) no look-ahead ------------------------------------------------------------------------------------------------------------------

def test_the_first_decision_does_not_change_when_the_prints_after_it_change(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)], troughs=[(400, 14700.0)]))
    a = quiet_day()
    first = sw_at(a)[0]
    b = list(a)
    for k in range(812 + 12, len(b)):                                          # everything from 09:42 on: a huge spike and a collapse
        b[k] = (15005.0, 16500.0, 13000.0, 15005.0, 40) if k % 2 else (15005.0, 15010.0, 12000.0, 12500.0, 40)
    got = sw_at(b)
    assert got[0] == first and {x[1]["sw"] for x in got} == {first[1]["sw"]}


def test_a_peak_made_of_today_is_not_a_swing_until_its_bars_after_it_have_closed(monkeypatch):
    stub(monkeypatch, history(troughs=[(400, 14700.0)]))
    bars = quiet_day()
    bars[812 - 5] = (15005.0, 15500.0, 15005.0, 15005.0, 40)                    # 09:25: a peak 5 bars before the session's first decision
    assert sw_at(bars)[0][1]["sw"] == (math.inf, 14700.0)                         # 50 bars (250 min) have not passed: it is not known


# ---- (v) the bar builder and the cache file -------------------------------------------------------------------------------------------

def test_hl_bars_match_a_loop_and_leave_out_the_open_bucket():
    rng = np.random.default_rng(3)
    t0 = S.et_ns(D, "09:00")
    ts = np.sort(t0 + rng.integers(0, 3 * 3600 * S.NS, 4000)).astype(np.int64)
    px = 15000 + np.cumsum(rng.integers(-2, 3, 4000)).astype(float)
    now = t0 + 100 * 60 * S.NS + 17 * S.NS                                     # 10:40:17: the 10:40 bucket is still open
    hi = int(np.searchsorted(ts, now))
    end, h, l = LV.hl_bars(ts, px, hi, t0, now, 5)
    step = 300 * S.NS
    want = {}
    for t, p in zip(ts[:hi].tolist(), px[:hi].tolist()):
        k = t // step
        if t0 - t0 % step <= k * step and (k + 1) * step <= now:
            a = want.setdefault(k, [p, p])
            a[0], a[1] = max(a[0], p), min(a[1], p)
    ks = sorted(want)
    assert end.tolist() == [(k + 1) * step for k in ks] and h.tolist() == [want[k][0] for k in ks] and l.tolist() == [want[k][1] for k in ks]
    assert end.max() <= now


def test_the_cache_file_round_trips_and_session_bars_prefer_it(tmp_path, monkeypatch):
    dates = [dt.date(2023, 3, 13), dt.date(2023, 3, 14)]
    tapes = {}
    for d in dates:
        t = minute_tape([(15000.0 + k, 15003.0 + k, 14997.0 + k, 15001.0 + k, 40) for k in range(600)], "18:00", d - dt.timedelta(days=1))
        tapes[d.isoformat()] = S.Tape("NQ", d, "NQH3", t.ts, t.px, t.size)
    monkeypatch.setattr(S, "CACHE", tmp_path)
    monkeypatch.setattr(S, "sessions", lambda a, b, root, **kw: dates)
    monkeypatch.setattr(S, "load_tape", lambda iso, root, **kw: tapes.get(str(iso)))
    monkeypatch.setattr(LV, "_FM", {})
    monkeypatch.setattr(LV, "_BARS", {})
    r = LV.build_bars_cache("NQ", ("2023-03-13", "2023-03-14"))
    assert r["added"] == 2 and r["dates"] == 2 and (tmp_path / "bars5m_NQ.npz").exists()
    for iso, t in tapes.items():
        want = LV.session_arrays(t)
        got = LV.session_bars("NQ", iso)
        assert all(np.array_equal(x, y) for x, y in zip(got, want)) and len(want[0]) > 100
    assert LV.build_bars_cache("NQ", ("2023-03-13", "2023-03-14"))["added"] == 0           # nothing new: nothing recomputed
    monkeypatch.setattr(S, "load_tape", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the file has the date: no tape is read")))
    LV._BARS.clear()
    assert LV.session_bars("NQ", "2023-03-14") is not None


# ---- (vi) the trigger on the swing level -------------------------------------------------------------------------------------------------

def test_liq_sweeps_the_swing_high_with_the_extreme_as_the_structure(monkeypatch):
    stub(monkeypatch, history(peaks=[(150, 15300.0)], troughs=[(400, 14700.0)]))
    g = flatg(10) + [(15005.0, 15330.0, 15005.0, 15320.0, 40), (15320.0, 15325.0, 15290.0, 15295.0, 40)] + flatg(30, 15295.0)
    got = run_liq({"mode": "sweep", "levels": "sw"}, quiet_day(g))
    assert [(side, struct) for _, side, struct, ok in got] == [("short", 15330.0)] and got[0][3]
    got = run_liq({"mode": "break", "levels": "sw"}, quiet_day(g))
    assert [(side, struct) for _, side, struct, ok in got] == [("long", 15300.0)]
