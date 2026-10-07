"""LIQUIDITY LEVELS: engine/levels.py, the `liq` trigger (families/liq.py) and the `level` / `swept` filter blocks (families/blocks.py).

A synthetic Globex day with EXACT ranges, from 19:58 ET of the evening before to 11:00, so every level has a known value:
    evening  20:00-24:00   (15040, 14960)  (a 19:59 outlier bar and the 00:00 bar must not count: they lie outside the window)
    asia     00:00-03:00   (15060, 14990)  (the 00:00 bar spikes to 15060)
    lon0205  02:00-05:00   (15025, 14985)
    london   03:00-08:25   (15030, 14980)
    on       00:00-09:30   (15060, 14975)  (the NY sessions' overnight range)
    pd / d5  from the daily bars: pd = (15110, 15000), d5 = (15150, 15000)
(i) each level at the decisions where it is known, and not before; (ii) the sweep and break rules decision by decision; (iii) the blocks;
(iv) NO LOOK-AHEAD; (v) identical trades at 1 and 8 workers on real BUILD days. No net, win rate or profit factor is read.
"""
import datetime as dt

import numpy as np
import pytest

import families
import l2sim as S
import levels as LV
import run_menus as RM
from families import blocks as B
from families import liq as LQ
from test_blocks import D, QUIET, W, days_of, garble, minute_tape, ns, real_days
from test_blocks_l2 import Probe

PREV = D - dt.timedelta(days=1)
TICK = 0.25
DAY_LEVELS = tuple(n for n in LV.NAMES if n not in ("sw", "eq"))        # the levels of these synthetic days; the swing level has its own tests (test_swing.py)


@pytest.fixture(autouse=True)
def no_swing_history(monkeypatch, request):
    """The synthetic days carry real calendar dates: the swing level must not read the real sessions of those dates (the real-day tests,
    whose worker processes would not see this stub, read them on purpose)."""
    if "real" in request.node.name or "identical" in request.node.name:
        return
    monkeypatch.setattr(LV, "session_bars", lambda root, iso, tf=LV.SW_TF: None)


def seg(n, lo, hi):
    """n minute bars inside [lo, hi] that touch both ends (the 1st reaches hi, the 2nd lo), then rest at the middle."""
    mid = round((lo + hi) / 2 / TICK) * TICK
    out = [(mid, hi, mid, mid, 40), (mid, mid, lo, mid, 40)]
    return out + [(mid, mid + TICK, mid - TICK, mid, 40)] * (n - 2)


def day_bars(g=()):
    """19:58 .. 11:00 ET: the outlier minute pair, then the segments in the module docstring, then G = `g` (09:30 on, one bar a minute)."""
    b = [(15000.0, 15500.0, 14500.0, 15000.0, 40)] * 2                      # 19:58, 19:59: outside every window
    b += seg(240, 14960, 15040)                                             # 20:00 - 24:00
    b += seg(120, 14995, 15005) + seg(60, 14990, 15010)                     # 00:00 - 03:00 (asia)
    b[2 + 240] = (15000.0, 15060.0, 15000.0, 15000.0, 40)                   # the 00:00 bar: a spike up to 15060 (not part of the evening)
    b += seg(120, 14985, 15025)                                             # 03:00 - 05:00
    b += seg(205, 14980, 15030)                                             # 05:00 - 08:25
    b += seg(65, 14975, 15035)                                              # 08:25 - 09:30
    assert len(b) == 2 + 240 + 180 + 120 + 205 + 65 == 812
    return b + list(g)


def tape_of(bars):
    t = minute_tape(bars, "19:58", PREV)
    return S.Tape("NQ", D, "NQM3", t.ts, t.px, t.size)                      # a Globex day: the tape of the trade date D starts the evening before


def daily():
    rows = [100.0] * 20 + [100.0, 120.0, 90.0, 150.0, 110.0]
    return [{"date": (D - dt.timedelta(days=len(rows) - i)).isoformat(), "h": 15000.0 + r, "l": 15000.0, "c": 15050.0, "contract": "NQM3"} for i, r in enumerate(rows)]


def go(cls, params, tape, rolls=()):
    """One instance through one session with an explicit roll list (the synthetic day lies right after a real roll: pin it to none)."""
    st = cls(params)
    st.ROLLS = frozenset(rolls)
    return S.run_session(st, tape, daily=daily(), on_error="raise")


def flatg(n, px=15005.0):
    return [(px, px + TICK, px - TICK, px, 40)] * n


def sec(h, m, s=0):
    return h * 3600 + m * 60 + s


class Spy(LQ.Liq):
    log: list = []

    def _mkt(self, ctx, side, **kw):
        o = super()._mkt(ctx, side, **kw)
        type(self).log.append(((ctx.now_ns - ns("00:00")) // S.NS, side, kw.get("struct"), o is not None))
        return o


def run_liq(params, bars, rolls=()):
    cls = type("L", (Spy,), {"log": []})
    go(cls, {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20, **params}, tape_of(bars), rolls)
    return list(cls.log)


class Lv(Probe):
    """Records the levels known at every decision."""
    asked: list = []

    def fam_signal(self, ctx):
        type(self).asked.append(((ctx.now_ns - ns("00:00")) // S.NS, LV.levels(self, "all")))


def levels_at(sess, tf="5", rolls=(), bars=None):
    cls = type("V", (Lv,), {"asked": []})
    go(cls, {"hold_to": "day", **QUIET, "tf": tf, "sess": sess}, tape_of(bars or day_bars(flatg(90))), rolls)
    return dict(cls.asked)


# ---- (i) the levels, known when their windows have ended ---------------------------------------------------------------------------------

def test_every_level_has_its_value_and_is_known_only_after_its_window():
    ny = levels_at("nyam")
    assert ny and all(set(v) == set(DAY_LEVELS) for v in ny.values())
    v = ny[min(ny)]
    assert v == {"pd": (15110.0, 15000.0), "on": (15060.0, 14975.0), "asia": (15060.0, 14990.0), "lon0205": (15025.0, 14985.0),
                 "ldn": (15030.0, 14980.0), "asia2000": (15040.0, 14960.0), "d5": (15150.0, 15000.0)}, v
    asia = levels_at("asia")                                  # 00:00-03:00: no Asia range yet, no overnight range yet, the evening and the days are there
    assert asia and all(set(x) == {"pd", "asia2000", "d5"} for x in asia.values())
    lon = levels_at("london")
    for s, x in lon.items():
        assert set(x) == {"pd", "on", "asia", "asia2000", "d5"} | ({"lon0205"} if s >= sec(5, 0) else set()), (s, sorted(x))
        assert "ldn" not in x                                                  # London itself is not known until 08:25
        assert x["on"] == x["asia"] == (15060.0, 14990.0)                      # the overnight range of London = the Asia range
    assert any(s >= sec(5, 0) for s in lon) and any(s < sec(5, 0) for s in lon)
    pre = levels_at("pre")
    assert pre and all(set(x) == {"pd", "on", "asia", "lon0205", "ldn", "asia2000", "d5"} for x in pre.values())
    assert all(x["on"] == (15060.0, 14980.0) for x in pre.values())                  # the overnight range of the pre-market: 00:00-08:25


def test_the_evening_level_reads_the_prints_of_2000_to_2400_and_needs_30_of_them():
    v = levels_at("asia")[min(levels_at("asia"))]
    assert v["asia2000"] == (15040.0, 14960.0)                                 # the 19:59 outlier and the 00:00 spike are outside the window
    sparse = tape_of(day_bars(flatg(90)))
    keep = np.ones(len(sparse.ts), bool)
    a, b = S.et_ns(PREV, "20:00"), S.et_ns(D, "00:00")
    idx = np.flatnonzero((sparse.ts >= a) & (sparse.ts < b))
    keep[idx[10:]] = False                                                     # only 10 prints left in the evening
    sparse = S.Tape("NQ", D, "NQM3", sparse.ts[keep], sparse.px[keep], sparse.size[keep])
    cls = type("V", (Lv,), {"asked": []})
    go(cls, {"hold_to": "day", **QUIET, "tf": "5", "sess": "nyam"}, sparse)
    assert cls.asked and all("asia2000" not in x for _, x in cls.asked)


def test_rolls_remove_the_levels_of_the_prior_days():
    day = D.isoformat()
    for rolls, gone in (({day}, {"pd", "d5"}), ({daily()[-3]["date"]}, {"d5"}), ({daily()[-6]["date"]}, set())):
        got = levels_at("nyam", rolls=rolls)
        v = got[min(got)]
        assert set(DAY_LEVELS) - set(v) == gone, (rolls, sorted(v))


# ---- (ii) the trigger ------------------------------------------------------------------------------------------------------------------------

def g_sweep_up():
    """09:30 on: flat, then a bar that trades beyond the London high 15030 and closes OUTSIDE (15040), then a bar that closes back inside."""
    return flatg(10) + [(15005.0, 15042.0, 15005.0, 15040.0, 40), (15040.0, 15041.0, 15025.0, 15026.0, 40)] + flatg(30, 15026.0)


def test_sweep_fades_a_level_high_once_the_close_is_back_inside_and_uses_the_extreme_as_the_structure():
    log = run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(g_sweep_up()))
    assert log == [(sec(9, 42), "short", 15042.0, True)]                         # the 12th bar of the session closes at 09:42:00, the extreme was 15042
    # the same bar that closes back inside at once is the signal at ITS close
    one = flatg(10) + [(15005.0, 15042.0, 15005.0, 15028.0, 40)] + flatg(30, 15028.0)
    assert run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(one)) == [(sec(9, 41), "short", 15042.0, True)]
    # a level LOW swept and reclaimed: a long, the extreme is the low
    low = flatg(10) + [(15005.0, 15005.0, 14970.0, 14972.0, 40), (14972.0, 14990.0, 14971.0, 14988.0, 40)] + flatg(30, 14988.0)
    assert run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(low)) == [(sec(9, 42), "long", 14970.0, True)]
    # no close back inside, no signal; a touch that does not trade beyond is no sweep
    out = flatg(10) + [(15005.0, 15042.0, 15005.0, 15040.0, 40)] + flatg(30, 15040.0)
    assert run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(out)) == []
    touch = flatg(10) + [(15005.0, 15030.0, 15005.0, 15028.0, 40)] + flatg(30, 15028.0)
    assert run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(touch)) == []


def test_one_signal_per_price_and_session_and_the_extreme_grows_while_the_close_stays_outside():
    twice = g_sweep_up() + [(15026.0, 15050.0, 15026.0, 15049.0, 40), (15049.0, 15049.0, 15020.0, 15021.0, 40)] + flatg(10, 15021.0)
    log = run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(twice))
    assert [(s, side) for s, side, _, _ in log] == [(sec(9, 42), "short")]                  # the second sweep of the same price is ignored
    grow = flatg(10) + [(15005.0, 15042.0, 15005.0, 15040.0, 40), (15040.0, 15060.0, 15040.0, 15058.0, 40), (15058.0, 15058.0, 15020.0, 15021.0, 40)] + flatg(30, 15021.0)
    assert run_liq({"mode": "sweep", "levels": "ldn"}, day_bars(grow)) == [(sec(9, 43), "short", 15060.0, True)]


def test_break_follows_the_first_close_beyond_a_price_and_never_one_that_was_already_beaten():
    brk = flatg(10) + [(15005.0, 15036.0, 15005.0, 15034.0, 40), (15034.0, 15045.0, 15034.0, 15044.0, 40)] + flatg(30, 15044.0)
    assert run_liq({"mode": "break", "levels": "ldn"}, day_bars(brk)) == [(sec(9, 41), "long", 15030.0, True)]       # only the first close beyond signals
    down = flatg(10) + [(15005.0, 15005.0, 14970.0, 14976.0, 40)] + flatg(30, 14976.0)
    assert run_liq({"mode": "break", "levels": "ldn"}, day_bars(down)) == [(sec(9, 41), "short", 14980.0, True)]
    gap = flatg(10, 15040.0) + flatg(30, 15041.0)                           # the session opens above the London high: the 09:30 bar is the first close beyond it
    assert run_liq({"mode": "break", "levels": "ldn"}, day_bars(gap)) == [(sec(9, 31), "long", 15030.0, True)]       # ... and the closes after it do not repeat it


def test_levels_all_takes_the_first_price_in_the_order_of_names_and_one_trade_at_a_time():
    # one bar closes beyond pd (15110), on / asia (15060), lon0205, ldn, asia2000 at once; the next beyond d5 (15150)
    both = flatg(10) + [(15005.0, 15115.0, 15005.0, 15112.0, 40), (15112.0, 15155.0, 15112.0, 15152.0, 40)] + flatg(30, 15152.0)
    log = run_liq({"mode": "break", "levels": "all"}, day_bars(both))
    assert log == [(sec(9, 41), "long", 15110.0, True)]                         # pd comes first in levels.NAMES; the trade is still open at the d5 break


# ---- the registry --------------------------------------------------------------------------------------------------------------------------------

def test_the_registry_holds_liq_with_mode_as_its_mirror_axis():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["liq"]
    lib = families.library("liq")
    assert cls is LQ.Liq and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15") and lib["roots"] == ("NQ", "ES", "GC")
    assert lib["mirror"] == "mode" and {v["mode"] for v in lib["variants"]} == {"sweep", "break"}
    assert cls.schema()["levels"] == ("choice", LV.NAMES + ("all",)) and issubclass(B.WRAPPED["liq"], LQ.Liq)
    for s in RM.DAY_PASSES:
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == [s]


# ---- (iii) the blocks ----------------------------------------------------------------------------------------------------------------------------

def probe_blocks(params, bars, tf="1"):
    cls = type("P", (Probe,), {"asked": []})
    go(cls, {"hold_to": "day", **QUIET, "tf": tf, **params}, tape_of(bars))
    return dict(cls.asked)


def all_prices():
    return sorted({15110.0, 15000.0, 15060.0, 14975.0, 15060.0, 14990.0, 15025.0, 14985.0, 15030.0, 14980.0, 15040.0, 14960.0, 15150.0})


def test_the_level_block_is_the_distance_to_the_closest_level_price_in_atr():
    walk = [(p, p + TICK, p - TICK, p, 40) for p in np.arange(15005.0, 15200.0, 5.0)]       # price climbs 5 points a minute from 09:30
    bars = day_bars(walk)
    near, clear = probe_blocks({"f_level": "near"}, bars), probe_blocks({"f_level": "clear"}, bars)
    on_level, far = [], []
    for s in sorted(near):
        close = 15005.0 + 5.0 * ((s - sec(9, 30)) // 60 - 1)
        d = min(abs(close - px) for px in all_prices())
        assert not (near[s] and clear[s])                                           # never both
        if d == 0:
            on_level.append(s)
        if d >= 15:
            far.append(s)
    assert on_level and all(near[s] and not clear[s] for s in on_level)             # a close ON a level is near it
    assert far and all(clear[s] and not near[s] for s in far)                       # 15+ points from every level (ATR about 5) is clear
    assert any(near.values()) and any(clear.values())


def exp_swept(bars, upto_s):
    """(a level HIGH was traded beyond, a level LOW was) by the bars completed at second upto_s of the trade date, from the known-from rules."""
    hi = lo = False
    t0 = sec(19, 58) - 86400
    for i, (o, h, l, c, v) in enumerate(bars):
        end = t0 + 60 * (i + 1)
        if end <= 0 or end > upto_s:
            continue                                                         # (the instance's bars start at 00:00)
        known = {"pd": (15110.0, 15000.0), "d5": (15150.0, 15000.0), "asia2000": (15040.0, 14960.0)}
        if end > sec(3, 0):
            known["asia"] = (15060.0, 14990.0)
        if end > sec(5, 0):
            known["lon0205"] = (15025.0, 14985.0)
        if end > sec(8, 25):
            known["ldn"] = (15030.0, 14980.0)
        if end > sec(9, 30):
            known["on"] = (15060.0, 14975.0)                                 # onh / onl are set at the session's start
        hi = hi or any(h > a for a, _ in known.values())
        lo = lo or any(l < b for _, b in known.values())
    return hi, lo


def test_the_swept_block_remembers_which_side_of_the_levels_was_traded_beyond():
    for g, name in ((flatg(30), "nothing"), (g_sweep_up(), "high"), (flatg(10) + [(15005.0, 15005.0, 14970.0, 14972.0, 40)] + flatg(30, 14972.0), "low")):
        bars = day_bars(g)
        for go, sd in (("long", 1), ("short", -1)):
            for mode in ("with", "against"):
                got = probe_blocks({"go": go, "f_swept": mode}, bars)
                assert got
                for s, ok in got.items():
                    hi, lo = exp_swept(bars, s)
                    need = ("lo" if sd > 0 else "hi") if mode == "with" else ("hi" if sd > 0 else "lo")
                    assert ok is bool(lo if need == "lo" else hi), (name, go, mode, s, hi, lo)
    # (the pre-market bars already trade beyond the Asia and London lows, so "with" for a long is on from the first NY decision: exp_swept says so)
    first = probe_blocks({"go": "long", "f_swept": "with"}, day_bars(flatg(30)))
    assert first and all(first[s] is exp_swept(day_bars(flatg(30)), s)[1] for s in first)


# ---- (iv) no look-ahead --------------------------------------------------------------------------------------------------------------------------

def test_no_look_ahead_in_the_levels_the_trigger_and_the_blocks():
    bars = day_bars(g_sweep_up())
    tape = tape_of(bars)
    for cut_s in (sec(9, 35), sec(9, 41, 30), sec(9, 50)):
        dirty_tape = garble(tape, ns("00:00") + cut_s * S.NS)
        for mode in ("sweep", "break"):
            logs = []
            for t in (tape, dirty_tape):
                cls = type("A", (Spy,), {"log": []})
                go(cls, {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20,
                         "mode": mode, "levels": "all"}, t)
                logs.append([x for x in cls.log if x[0] <= cut_s])
            assert logs[0] == logs[1], (mode, cut_s)
        for extra in ({"f_level": "near"}, {"f_level": "clear"}, {"f_swept": "with"}, {"f_swept": "against", "go": "short"}):
            a = probe_blocks(extra, bars)
            cls = type("P", (Probe,), {"asked": []})
            go(cls, {"hold_to": "day", **QUIET, **extra}, dirty_tape)
            b = dict(cls.asked)
            assert {s: v for s, v in a.items() if s <= cut_s} == {s: v for s, v in b.items() if s <= cut_s}, (extra, cut_s)
    assert run_liq({"mode": "sweep", "levels": "all"}, bars)                       # (the clean run does trade)
    # the evening level reads nothing at or after 00:00: garbling every print from midnight on leaves it as it was
    garbled = garble(tape_of(day_bars(flatg(90))), S.et_ns(D, "00:00"))
    cls = type("V", (Lv,), {"asked": []})
    go(cls, {"hold_to": "day", **QUIET, "tf": "5", "sess": "asia"}, garbled)
    assert cls.asked and all(x["asia2000"] == (15040.0, 14960.0) for _, x in cls.asked)


# ---- (v) real BUILD days -----------------------------------------------------------------------------------------------------------------------------

def _specs():
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0}
    out = []
    for sess in ("asia", "london", "nyam"):
        for mode in ("sweep", "break"):
            for lv in ("pd", "on", "ldn", "lon0205", "asia", "asia2000", "d5", "sw", "eq", "all"):
                out.append((B.WRAPPED["liq"], {**hd, "sess": sess, "mode": mode, "levels": lv}))
    out += [(B.WRAPPED["donchian"], {**hd, "sess": "nyam", "n": 10, "f_level": "near"}), (B.WRAPPED["donchian"], {**hd, "sess": "nyam", "n": 10, "f_level": "clear"}),
            (B.WRAPPED["donchian"], {**hd, "sess": "nyam", "n": 10, "f_swept": "with"}), (B.WRAPPED["donchian"], {**hd, "sess": "london", "n": 10, "f_swept": "against"})]
    return out


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_liquidity_levels(root):
    real_days()
    days = days_of(root)
    specs = _specs()
    a = S.run_many(specs, days=days, root=root, workers=1)
    b = S.run_many(specs, days=days, root=root, workers=W)
    seen = {}
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        if "mode" in p:
            seen[p["mode"], p["sess"]] = seen.get((p["mode"], p["sess"]), 0) + len(x["trades"])
    assert all(v > 0 for v in seen.values()), seen                                    # both modes traded in the Asia, London and NY sessions
    assert RM.hold_checks(a, root) == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
