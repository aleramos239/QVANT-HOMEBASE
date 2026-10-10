"""engine/families/blocks.py (exit and filter blocks, ib_n, the extended menu) and run_idea.py (ideas as settings).

  (i)   every block on synthetic bars: it does what it says;
  (ii)  NO LOOK-AHEAD for every block: rewriting every print (and every feature row) from a decision on changes nothing
        decided up to it; a daily label does not move when the day's own bar changes; the volume block reads volume up to
        the decision only (and prior dates only); the RSI reads closed bars only;
  (iii) PARITY: a family run through blocks.WRAPPED with every block off is trade for trade the original family, on 10 BUILD
        days per market, 5 families + ib_n(60) = ib;
  (iv)  identical trades at 1 and 8 workers with the blocks ON;
  (v)   run_idea: the spec format, the plan arithmetic, a restartable build into a scratch store, the cap.
Real-day tests compare trades by equality and assert counts only: no net, win rate or profit factor is printed or read."""
import datetime as dt
import json
import os
import pickle
import sys

import numpy as np
import pytest

import families
import l2ref
import l2sim as S
import library as LB
import run_idea as RI
import run_menus as RM
from families import blocks as B
from families import port1, port2, round1

D = dt.date(2023, 3, 14)                            # a BUILD weekday (EDT), not a roll day
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
TICK = 0.25
CAND = list(RM.SMOKE_DAYS) + ["2022-05-10", "2023-02-14", "2023-05-16"]       # BUILD days; the first 10 a market has


def real_days():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def days_of(root, n=10):
    have = {d.isoformat() for d in S.sessions(*S.period("build"), root)}
    out = [d for d in CAND if d in have][:n]
    assert len(out) == n and all("2021-09-22" <= d <= "2023-12-31" for d in out)
    return out


def ns(hms, d=D):
    return S.et_ns(d, hms)


def sec(t_ns, d=D):
    return (t_ns - S.et_ns(d, "00:00")) // S.NS


def prior_dates(n, d=D):
    out, x = [], d
    while len(out) < n:
        x -= dt.timedelta(days=1)
        if x.weekday() < 5:
            out.append(x.isoformat())
    return out[::-1]


def daily_rows(ranges, d=D):
    """One daily bar per range, the last one dated the weekday before d."""
    return [{"date": iso, "h": 15000.0 + r, "l": 15000.0, "c": 15000.0 + r / 2, "contract": "NQM3"}
            for iso, r in zip(prior_dates(len(ranges), d), ranges)]


DAILY = daily_rows([100.0] * 25)


def minute_tape(bars, start="09:00", d=D, root="NQ", contract="NQM3"):
    """One (o, h, l, c, v) per minute from `start` -> 4 prints per minute at :00 (o), :15, :30 (low then high for an up bar,
    high then low for a down bar) and :45 (c), each of size v / 4 (v a multiple of 4)."""
    ts, px, sz = [], [], []
    t0 = ns(start, d)
    for i, (o, h, l, c, v) in enumerate(bars):
        mid = (l, h) if c >= o else (h, l)
        for k, p in enumerate((o, mid[0], mid[1], c)):
            ts.append(t0 + i * 60 * S.NS + k * 15 * S.NS)
            px.append(p)
            sz.append(v // 4)
    return S.Tape(root, d, contract, np.array(ts, np.int64), np.array(px, float), np.array(sz, np.int64))


def rand_bars(n, seed, p0=15000.0, step=6.0):
    """A seeded random walk of n minute bars on the tick grid, volumes with a heavy tail (multiples of 4)."""
    g = np.random.default_rng(seed)
    out, o = [], p0
    for _ in range(n):
        c = o + round(float(g.normal(0, step)) / TICK) * TICK
        h = max(o, c) + int(g.integers(0, 8)) * TICK
        l = min(o, c) - int(g.integers(0, 8)) * TICK
        out.append((o, h, l, c, 4 * int(10 + g.lognormal(3.0, 1.0))))
        o = c
    return out


def flat_bars(n, vols=None, px=15000.0):
    """n quiet bars: one tick of range, no stop is ever near."""
    return [(px, px + TICK, px, px + (TICK if i % 2 else 0.0), 40 if vols is None else vols[i]) for i in range(n)]


def mins(bars, start="09:00"):
    """[(start second after 00:00 ET, o, h, l, c, v)] of a minute_tape's bars."""
    s0 = S._sec(start)
    return [(s0 + 60 * i, *b) for i, b in enumerate(bars)]


def hl(ms, a, b):
    xs = [m for m in ms if a <= m[0] and m[0] + 60 <= b]
    return max(m[2] for m in xs) - min(m[3] for m in xs)


def tf_bars(ms, tf, upto):
    """The tf bars (clock multiples) that have closed by second `upto`: [(end second, h, l, c)]."""
    step, out = tf * 60, {}
    for s, o, h, l, c, v in ms:
        k = s // step
        e = out.setdefault(k, [(k + 1) * step, h, l, c])
        e[1], e[2], e[3] = max(e[1], h), min(e[2], l), c
    return [tuple(e) for k, e in sorted(out.items()) if e[0] <= upto]


def garble(tape, cut_ns, seed=7):
    """The same tape with EVERY print stamped at / after cut_ns rewritten (price and size)."""
    g = np.random.default_rng(seed)
    px, sz = tape.px.copy(), tape.size.copy()
    m = tape.ts >= cut_ns
    px[m] = np.round((px[m] + g.normal(0, 400.0, int(m.sum()))) / TICK) * TICK
    sz[m] = g.integers(1, 5000, int(m.sum()))
    return S.Tape(tape.root, tape.date, tape.contract, tape.ts.copy(), px, sz)


def spy(cls):
    """A subclass that logs every entry decision: ('mkt', ns, side, ref, None | (sl, tp)) and ('arm', ns, the legs asked,
    the orders placed as (side, price, sl, tp))."""
    class Spy(cls):
        log: list = []

        def _mkt(self, ctx, side, **kw):
            ref = kw.get("ref") if kw.get("ref") is not None else self.C[-1]
            o = super()._mkt(ctx, side, **kw)
            type(self).log.append(("mkt", ctx.now_ns, side, ref, None if o is None else (o.sl, o.tp)))
            return o

        def _arm(self, ctx, legs, **kw):
            out = super()._arm(ctx, legs, **kw)
            type(self).log.append(("arm", ctx.now_ns, tuple((x[0], x[1]) for x in legs), tuple((o.side, o.price, o.sl, o.tp) for o in out)))
            return out
    Spy.log = []
    return Spy


def play(cls, params, tape, daily=DAILY, features=None):
    """One synthetic session through one instance (hold_to day) -> (trades, the Spy log, the instance)."""
    sp = spy(cls)
    st = sp({"hold_to": "day", **params})
    res = S.run_session(st, tape, daily=list(daily), features=features, on_error="raise")
    return res.trades, list(sp.log), st


def placed(log):
    """Every order placed in a log: [(decision ns, side +1 / -1, reference price, sl, tp)]."""
    out = []
    for e in log:
        if e[0] == "mkt" and e[4] is not None:
            out.append((e[1], 1 if e[2] == "long" else -1, e[3], *e[4]))
        elif e[0] == "arm":
            out += [(e[1], 1 if o[0] in (1, "long") else -1, o[1], o[2], o[3]) for o in e[3]]
    return out


class Always(S.Template):
    """Enters `go` at market at every tf-bar close the Template allows (the filters are the family-free part of Blocks)."""
    DEFAULTS = {"go": "long"}
    SCHEMA = {"go": ("choice", ("long", "short"))}
    SCREEN_TFS = ("1", "5")
    FEATURES = ()

    def fam_signal(self, ctx):
        self._mkt(ctx, self.p["go"])


class AlwaysB(B.Blocks, Always):
    pass


QUIET = {"tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20, "exit_bars": 3}


def attempts(log):
    """[(decision second after 00:00 ET, an order was placed)] of an Always log."""
    return [(sec(e[1]), e[4] is not None) for e in log]


# ---- the registry, the wrapped classes, the menu -----------------------------------------------------------------------------

def test_blocks_registers_ib_n_and_wraps_every_bar_based_library_family():
    assert families.ERRORS == {} and families.MODULE_OF["ib_n"] == "blocks" and RM.group_families("blocks") == ["ib_n"]
    lib = families.library("ib_n")
    assert [v["ib_min"] for v in lib["variants"]] == ["5", "15", "30", "60"] and lib["roots"] == ("NQ", "ES", "GC")
    assert B.IbN.SCREEN_TFS == ("5", "15", "30") and B.IbN.defaults()["mode"] == "break" and B.IbN.defaults()["ib_min"] == "60"
    want = {n for n, e in families.REGISTRY.items() if n in families.LIBRARY and not e[0].FEATURES
            and not RM.is_time_fired(e[0]) and families.MODULE_OF[n] in ("port1", "port2", "port3", "round1", "timed", "blocks", "fvg", "liq", "noise", "ifvg", "sfp", "open_fvg")}
    assert set(B.WRAPPED) == want and {"orb", "ib", "ib_n", "donchian", "first_bar_mom", "vwap_trend_pull", "vol_spike_break"} <= want
    for name, cls in B.WRAPPED.items():
        base = families.REGISTRY[name][0]
        assert cls.__mro__[1] is B.Blocks and cls.__mro__[2] is base and cls.BASE == name
        assert pickle.loads(pickle.dumps(cls)) is cls and cls.__module__ == "families.blocks"     # workers import it by name
        d = cls.defaults()
        assert {k: d[k] for k in base.defaults()} == base.defaults()                              # nothing of the family changes
        assert all(d[k] == "off" for k in ("f_dvol", "f_rsi", "f_cvol", "f_news", "f_bookopp", "f_book"))
        assert (cls.STRUCT is not None) == (name in B.HEIGHTS)
    assert set(B.CONTROLS) == set(B.HEIGHTS) and all(issubclass(c, l2ref.Random) and pickle.loads(pickle.dumps(c)) is c
                                                     for c in B.CONTROLS.values())


def test_the_extended_menu_is_the_standard_32_cells_plus_the_new_stops_and_targets():
    for root in ("NQ", "ES", "GC"):
        std, ext, flat = S.menu(root), B.menu_extended(root), B.menu_extended(root, rng=False)
        assert ext[:32] == std and flat == [x for x in ext if x["stop_mode"] != "rng"] and flat == ext[:60]
        assert len(ext) == 78 == len({S.cell_id(x) for x in ext}) and len(flat) == 60
        stops = {(x["stop_mode"], x["stop_val"]) for x in ext}
        assert stops - {(x["stop_mode"], x["stop_val"]) for x in std} == {("atr", 1.0), ("atr", 2.0), ("rng", 0.25), ("rng", 0.5), ("rng", 1.0)}
        assert {x["tgt_r"] for x in ext} == {0.0, 1.0, 1.5, 2.0, 3.0, 4.0}
        assert all(sum(1 for x in ext if (x["stop_mode"], x["stop_val"]) == s) == 6 for s in stops)      # every stop x 6 targets
        assert B.exits("standard", root, "orb") == std and B.exits("extended", root, "orb") == ext
        assert B.exits("extended", root, "vwap_trend_pull") == flat
    assert {S.cell_id(x) for x in B.menu_extended("NQ")[32:]} >= {"atr1p5-r1p5", "pts10-r4", "atr1-r0", "atr2-r4", "rng0p25-r1p5", "rng1-r4"}


def test_a_family_without_a_structure_refuses_the_range_stop_with_a_clear_error():
    for name in ("vwap_trend_pull", "rsi2", "vwap_z", "squeeze"):
        with pytest.raises(ValueError, match="needs a structure"):
            B.WRAPPED[name]({"tf": "5", "stop_mode": "rng", "stop_val": 0.5})
    with pytest.raises(ValueError, match="rng"):
        families.REGISTRY["orb"][0]({"tf": "5", "stop_mode": "rng"})        # the original family does not know the mode at all
    for name in B.HEIGHTS:
        B.WRAPPED[name]({"tf": "5", "stop_mode": "rng", "stop_val": 0.25})
    with pytest.raises(ValueError, match="two sides of ONE block"):
        B.WRAPPED["orb"]({"tf": "5", "f_book": "on", "f_bookopp": "on"})


# ---- the range stop: stop_val x the family's own structure -------------------------------------------------------------------

BARS = rand_bars(600, seed=11)                      # 03:00 .. 13:00 ET
MS = mins(BARS, "03:00")


def _channel(n):
    def fn(now_s):
        tb = tf_bars(MS, 5, now_s)
        assert tb[-1][0] == now_s
        return max(b[1] for b in tb[-n - 1:-1]) - min(b[2] for b in tb[-n - 1:-1])
    return fn


def _signal_bar(now_s):
    tb = tf_bars(MS, 5, now_s)
    return tb[-1][1] - tb[-1][2]


# family, inputs, the height expected at a decision (a function of its second), the only second an order may be placed at
RNG_CASES = [
    ("orb", {"or_min": "15"}, lambda s: hl(MS, 34200, 35100), 35100),
    ("orb", {"or_min": "5", "sess": "mid"}, lambda s: hl(MS, 39600, 39900), 39900),
    ("ib_n", {"ib_min": "5"}, lambda s: hl(MS, 34200, 34500), 34500),
    ("ib_n", {"ib_min": "15"}, lambda s: hl(MS, 34200, 35100), 35100),
    ("ib_n", {"ib_min": "30"}, lambda s: hl(MS, 34200, 36000), 36000),
    ("ib_n", {"ib_min": "60"}, lambda s: hl(MS, 34200, 37800), 37800),
    ("ib_n", {"ib_min": "15", "sess": "mid"}, lambda s: hl(MS, 34200, 35100), 39600),
    ("ib", {}, lambda s: hl(MS, 34200, 37800), 37800),
    ("lon_break", {}, lambda s: hl(MS, 10800, 30300), 34200),
    ("orb_confirm", {"or_min": "15", "dir": "long"}, lambda s: hl(MS, 34200, 35100), None),
    ("orb_confirm", {"or_min": "15", "dir": "short"}, lambda s: hl(MS, 34200, 35100), None),
    ("donchian", {"n": 10, "max_tr": 6}, _channel(10), None),
    ("vol_spike_break", {"m": 1.0, "max_tr": 6}, _channel(20), None),
    ("first_bar_mom", {"k": 0.2}, _signal_bar, 34500),
]


def _rng_params(inputs, sv=0.5, r=2.0):
    return {"tf": "5", "sess": "nyam", "stop_mode": "rng", "stop_val": sv, "tgt_r": r, **inputs}


def test_the_range_stop_is_stop_val_times_the_structure_height_for_every_family_with_one():
    tape = minute_tape(BARS, "03:00")
    seen = set()
    for name, inputs, height, at in RNG_CASES:
        for sv in (0.25, 0.5, 1.0):
            _, log, _ = play(B.WRAPPED[name], _rng_params(inputs, sv), tape)
            for t, sd, ref, sl, tp in placed(log):
                h = height(sec(t))
                d = max(sv * h, 2 * TICK)            # the engine prices every order on the tick grid
                assert h > 0 and sl == S.to_tick(ref - sd * d, TICK) and tp == S.to_tick(ref + sd * 2.0 * d, TICK), (name, inputs, sv)
                assert (ref - sl) * sd > 0 and abs(abs(ref - sl) - d) <= TICK / 2
                assert at is None or sec(t) == at
                seen.add(name)
    assert seen == set(B.HEIGHTS)                    # every family with a structure placed at least one range-stop order


def test_the_range_stop_is_floored_at_two_ticks_and_there_is_no_entry_without_a_structure():
    tape = minute_tape(flat_bars(180), "08:00")       # every range is ONE tick high
    _, log, _ = play(B.WRAPPED["orb"], _rng_params({"or_min": "5"}, 0.25, 0.0), tape)
    assert placed(log) and all(abs(ref - sl) == 2 * TICK for _, _, ref, sl, _ in placed(log))
    dead = minute_tape([(15000.0, 15000.0, 15000.0, 15000.0, 40)] * 180, "08:00")       # a range of height 0: no structure
    _, log, _ = play(B.WRAPPED["orb"], _rng_params({"or_min": "5"}), dead)
    assert log and not placed(log)
    # the control enters at random, but never before its structure exists (the opening range ends 10:00, the IB 10:30)
    tape = minute_tape(BARS, "03:00")
    for name, inputs, first in (("orb", {"or_min": "30"}, 36000), ("ib_n", {"ib_min": "60"}, 37800), ("ib", {}, 37800)):
        p = {"tf": "1", "sess": "nyam", "p_entry": 1.0, "seed": 1, "max_tr": 20, "exit_bars": 1, "stop_mode": "rng", "stop_val": 1.0,
             "tgt_r": 0.0, **inputs}
        _, log, _ = play(B.CONTROLS[name], p, tape)
        got = [s for s, ok in attempts(log) if ok]
        assert got and min(got) == first and any(s < first and not ok for s, ok in attempts(log))
        h = hl(MS, 34200, first)
        assert all(sl == S.to_tick(ref - sd * h, TICK) for _, sd, ref, sl, _ in placed(log))
    # the same control with another stop is plain l2ref.Random: same draws, same entries
    p = {"tf": "5", "sess": "nyam", "p_entry": 0.5, "seed": 2, "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "hold_to": "day"}
    a = S.run_session(l2ref.Random(p), tape, daily=list(DAILY), on_error="raise").trades
    b = S.run_session(B.CONTROLS["orb"](p), tape, daily=list(DAILY), on_error="raise").trades
    assert a and a == b


@pytest.mark.parametrize("case", range(len(RNG_CASES)))
def test_no_look_ahead_in_the_range_stop_rewriting_every_print_from_a_decision_on_changes_nothing_before_it(case):
    name, inputs, _, _ = RNG_CASES[case]
    tape = minute_tape(BARS, "03:00")
    _, clean, _ = play(B.WRAPPED[name], _rng_params(inputs), tape)
    cuts = sorted({e[1] for e in clean})
    assert cuts
    for cut in cuts[:6] + [ns("09:47:10"), ns("11:02:20")]:
        _, dirty, _ = play(B.WRAPPED[name], _rng_params(inputs), garble(tape, cut))
        assert [e for e in dirty if e[1] <= cut] == [e for e in clean if e[1] <= cut], (name, cut)


# ---- ib_n -------------------------------------------------------------------------------------------------------------------

def test_ib_n_places_the_bracket_one_tick_beyond_its_own_range_at_the_range_end():
    tape = minute_tape(BARS, "03:00")
    for m, end in (("5", 34500), ("15", 35100), ("30", 36000), ("60", 37800)):
        xs = [x for x in MS if 34200 <= x[0] and x[0] + 60 <= end]
        hi, lo = max(x[2] for x in xs), min(x[3] for x in xs)
        for sess, at in (("nyam", end), ("mid", 39600), ("pm", 48600)):
            _, log, st = play(B.IbN, {"tf": "5", "sess": sess, "ib_min": m, "stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}, tape)
            arms = [e for e in log if e[0] == "arm"]
            assert len(arms) == 1 and sec(arms[0][1]) == at and (st.ibh, st.ibl) == (hi, lo)
            assert arms[0][2] == (("long", hi + TICK), ("short", lo - TICK))
            lp = [x for x in MS if x[0] < at][-1][4]                      # the last print before the decision
            assert {o[1] for o in arms[0][3]} == {p for p, sd in ((hi + TICK, 1), (lo - TICK, -1)) if (p - lp) * sd > 0}
    assert B.IbN({"tf": "5", "sess": "all"}).sessions() == ["nyam", "mid", "pm"] and B.IbN({"tf": "5", "sess": "asia"}).sessions() == []
    with pytest.raises(ValueError, match="ib_min"):
        B.IbN({"tf": "5", "ib_min": "45"})


def test_ib_n_at_60_minutes_is_ib_on_synthetic_bars_in_both_modes():
    tape = minute_tape(BARS, "03:00")
    n = 0
    for mode in ("break", "fade"):
        for sess in ("nyam", "mid", "pm"):
            p = {"tf": "5", "sess": sess, "mode": mode, "hold_to": "day"}
            a = S.run_session(port1.Ib(p), tape, daily=list(DAILY), on_error="raise").trades
            b = S.run_session(B.IbN({**p, "ib_min": "60"}), tape, daily=list(DAILY), on_error="raise").trades
            assert a == b
            n += len(a)
    assert n > 0


# ---- volatility: the prior day's range against its own 20-day median ----------------------------------------------------------

def test_the_volatility_block_reads_the_prior_days_range_against_the_20_day_median():
    assert B.day_vol(daily_rows([10.0] * 19 + [30.0]), D.isoformat()) == "hi"
    assert B.day_vol(daily_rows([10.0] * 19 + [5.0]), D.isoformat()) == "lo"
    assert B.day_vol(daily_rows([10.0] * 20), D.isoformat()) == "lo"              # not above its median = the low side
    assert B.day_vol(daily_rows([10.0] * 18 + [30.0]), D.isoformat()) is None     # 19 bars: no label, neither side
    assert B.day_vol(daily_rows([50.0] * 30 + [10.0] * 19 + [11.0]), D.isoformat()) == "hi"      # only the last 20 count
    tape = minute_tape(flat_bars(120), "09:00")
    for ranges, side in (([10.0] * 19 + [30.0], "hi"), ([10.0] * 19 + [5.0], "lo")):
        for f in ("hi", "lo"):
            tr, log, _ = play(AlwaysB, {**QUIET, "f_dvol": f}, tape, daily=daily_rows(ranges))
            assert log and all(ok == (f == side) for _, ok in attempts(log)) and bool(tr) == (f == side)
    for f in ("hi", "lo"):                           # no label: BOTH sides stay out
        tr, log, _ = play(AlwaysB, {**QUIET, "f_dvol": f}, tape, daily=daily_rows([10.0] * 18 + [30.0]))
        assert log and not tr


def test_no_look_ahead_in_the_volatility_label_the_days_own_bar_and_later_bars_do_not_move_it():
    for ranges in ([10.0] * 19 + [30.0], [10.0] * 19 + [5.0], [7.0, 9.0, 11.0] * 8):
        rows = daily_rows(ranges)
        want = B.day_vol(rows, D.isoformat())
        for own in (0.25, 5.0, 5000.0):
            later = [{"date": (D + dt.timedelta(days=k)).isoformat(), "h": 15000.0 + own * (k + 1), "l": 15000.0, "c": 15001.0,
                      "contract": "NQM3"} for k in range(3)]                       # the day's own bar, then two later ones
            assert B.day_vol(rows + later, D.isoformat()) == want
        moved = [dict(r) for r in rows]
        moved[-1]["h"] += 1000.0                     # the PRIOR day's bar is what the label reads
        assert B.day_vol(moved, D.isoformat()) == "hi"


def test_the_volatility_label_is_the_tested_label_builder_of_the_deepen_stage_on_every_build_date():
    path = LB.W / "out" / "deepen"
    if not (path / "labels.py").exists():
        pytest.skip("out/deepen/labels.py is not here")
    sys.path.insert(0, str(path))
    try:
        import labels
    finally:
        sys.path.remove(str(path))
    n = 0
    for root in ("NQ", "ES", "GC"):
        rows = [r for r in S.load_daily(root) if r["date"] <= "2023-12-31"]         # BUILD rows only
        dates = [d for d in LB.calendar("build", root)]
        ref = labels.day_labels(rows, dates)
        mine = {d: B.day_vol(rows, d) for d in dates}
        assert all(mine[d] == {True: "hi", False: "lo", None: None}[ref[d]["vol_hi"]] for d in dates)
        assert sum(v is None for v in mine.values()) == 20 and {"hi", "lo"} <= set(mine.values())
        n += len(dates)
    assert n > 1500


# ---- momentum: RSI(14) on the family's bars, closed bars only -----------------------------------------------------------------

def rsi_ref(c, n=14):
    """Wilder RSI by the textbook formula 100 - 100 / (1 + RS) (numpy; written apart from blocks.rsi)."""
    d = np.diff(np.asarray(c, float))
    if len(d) < n:
        return None
    up, dn = np.clip(d, 0, None), np.clip(-d, 0, None)
    g, l = up[:n].mean(), dn[:n].mean()
    for k in range(n, len(d)):
        g, l = (g * (n - 1) + up[k]) / n, (l * (n - 1) + dn[k]) / n
    if g + l == 0:
        return 50.0
    return 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)


def test_rsi_is_wilders_rsi_14():
    g = np.random.default_rng(3)
    c = (15000 + np.cumsum(g.normal(0, 5, 400))).tolist()
    for n in (15, 16, 40, 400):
        assert B.rsi(c[:n]) == pytest.approx(rsi_ref(c[:n]), abs=1e-9)
    assert B.rsi(c[:14]) is None and B.rsi([]) is None
    assert B.rsi(list(range(30))) == 100.0 and B.rsi(list(range(30, 0, -1))) == 0.0 and B.rsi([5.0] * 30) == 50.0


@pytest.mark.parametrize("tf", ["1", "5"])
def test_the_momentum_block_allows_a_side_by_the_rsi_of_the_closed_bars_at_the_signal_bar(tf):
    bars = rand_bars(480, seed=5)                     # 01:00 .. 09:00 ET; the london session (03:00-08:25) is traded
    tape, ms = minute_tape(bars, "01:00"), mins(bars, "01:00")
    seen = set()
    for go, sd in (("long", 1), ("short", -1)):
        for f in ("with", "against"):
            _, log, _ = play(AlwaysB, {**QUIET, "tf": tf, "sess": "london", "exit_bars": 1, "go": go, "f_rsi": f}, tape)
            assert len(log) >= 12
            for s, ok in attempts(log):
                r = rsi_ref([b[3] for b in tf_bars(ms, int(tf), s)])               # bars CLOSED by the decision, no other
                assert ok == ((r - 50.0) * sd * (1 if f == "with" else -1) > 0)
                seen.add((go, f, ok))
    assert len(seen) == 8                            # every side of the block both allowed and blocked something
    # fewer than 15 closes since the restart: no signal, BOTH sides stay out (tf 5 from 09:00: the 15th close is 10:15)
    tape = minute_tape(bars, "09:00")
    for f in ("with", "against"):
        for go in ("long", "short"):
            _, log, _ = play(AlwaysB, {**QUIET, "tf": "5", "go": go, "f_rsi": f}, tape)
            assert any(s < 36900 for s, _ in attempts(log)) and all(not ok for s, ok in attempts(log) if s < 36900)


# ---- volume: the session's volume so far against the 20-day median of the same clock window ---------------------------------

def _profiles(monkeypatch, per_minute, root="NQ"):
    """20 prior trade dates, date k trading per_minute[k] contracts in every minute: the block's memo is filled with them."""
    dates = prior_dates(20)
    memo = {(root, iso): np.concatenate(([0], np.cumsum(np.full(B.NMIN, v, np.int64)))) for iso, v in zip(dates, per_minute)}
    monkeypatch.setattr(B, "_CUM", memo)
    return daily_rows([100.0] * 20)


def test_the_volume_block_compares_the_session_volume_so_far_with_the_20_day_median(monkeypatch):
    vols = [20] * 60 + [200] * 60 + [4] * 60          # 09:00-10:00 thin, 10:00-11:00 heavy, then nothing much
    bars = flat_bars(180, vols)
    tape, ms = minute_tape(bars, "09:00"), mins(bars, "09:00")
    daily = _profiles(monkeypatch, [40 + 4 * k for k in range(20)])                # median per minute = 78
    seen = set()
    for f in ("hi", "lo"):
        _, log, _ = play(AlwaysB, {**QUIET, "f_cvol": f}, tape, daily=daily)
        assert len(log) > 30
        for s, ok in attempts(log):
            today = sum(m[5] for m in ms if 34200 <= m[0] and m[0] + 60 <= s)       # from the 09:30 session start
            ref = 78.0 * (s - 34200) // 60
            assert today != ref and ok == ((today > ref) == (f == "hi"))
            seen.add((f, ok))
    assert len(seen) == 4
    # equality, fewer than 20 prior dates, a prior date without a tape: no signal -> BOTH sides stay out
    even = _profiles(monkeypatch, [20] * 20)
    for f in ("hi", "lo"):
        _, log, _ = play(AlwaysB, {**QUIET, "f_cvol": f}, minute_tape(flat_bars(60, [20] * 60), "09:00"), daily=even)
        assert log and not any(ok for _, ok in attempts(log))
        _, log, _ = play(AlwaysB, {**QUIET, "f_cvol": f}, tape, daily=daily[1:])
        assert log and not any(ok for _, ok in attempts(log))
    B._CUM[("NQ", daily[5]["date"])] = None
    for f in ("hi", "lo"):
        _, log, _ = play(AlwaysB, {**QUIET, "f_cvol": f}, tape, daily=daily)
        assert log and not any(ok for _, ok in attempts(log))
    assert B.cum_ref("NQ", [r["date"] for r in even], 34200, 34200) is None and B.cum_ref("NQ", [], 34200, 34500) is None


def test_no_look_ahead_in_the_volume_block_only_volume_up_to_the_signal_bar_and_only_prior_dates(monkeypatch):
    vols = [20] * 60 + [200] * 60 + [4] * 60
    bars = flat_bars(180, vols)
    tape = minute_tape(bars, "09:00")
    daily = _profiles(monkeypatch, [40 + 4 * k for k in range(20)])
    _, clean, _ = play(AlwaysB, {**QUIET, "f_cvol": "hi"}, tape, daily=daily)
    flips = [e[1] for a, e in zip(clean, clean[1:]) if (a[4] is None) != (e[4] is None)]
    assert flips
    for cut in flips + [ns("09:44"), ns("10:20:30"), ns("10:51")]:
        _, dirty, _ = play(AlwaysB, {**QUIET, "f_cvol": "hi"}, garble(tape, cut), daily=daily)
        assert [e for e in dirty if e[1] <= cut] == [e for e in clean if e[1] <= cut]
    # the day's own row and every later date in the store are never read: poison them
    B._CUM[("NQ", D.isoformat())] = np.zeros(B.NMIN + 1, np.int64) + 10 ** 12
    B._CUM[("NQ", (D + dt.timedelta(days=1)).isoformat())] = np.zeros(B.NMIN + 1, np.int64) + 10 ** 12
    _, again, _ = play(AlwaysB, {**QUIET, "f_cvol": "hi"}, tape, daily=daily)
    assert again == clean
    # ... and a bar BEFORE the signal is read: more volume in the first session minute flips the first decisions
    loud = minute_tape(flat_bars(180, [20] * 30 + [40000] + vols[31:]), "09:00")
    _, moved, _ = play(AlwaysB, {**QUIET, "f_cvol": "hi"}, loud, daily=daily)
    assert attempts(clean)[0] == (34260, False) and attempts(moved)[0] == (34260, True)


def test_the_minute_volume_of_a_tape_is_the_volume_of_the_engines_one_minute_bars(tmp_path, monkeypatch):
    bars = rand_bars(240, seed=9)
    tape = minute_tape(bars, "08:00")
    mv = B.minute_volume(tape)
    assert mv.shape == (B.NMIN,) and mv.sum() == tape.size.sum()
    for i, b in enumerate(bars):
        assert mv[(8 * 60 + i) - B.MIN0] == b[4]
    # an evening print (18:00 the day before) is minute 0; a print at / after 17:00 is outside the Globex day
    eve = S.Tape("NQ", D, "NQM3", np.array([S.et_ns(D - dt.timedelta(days=1), "18:00"), ns("16:59:59"), ns("17:00")], np.int64),
                 np.array([1.0, 1.0, 1.0]), np.array([3, 5, 7], np.int64))
    mv = B.minute_volume(eve)
    assert mv[0] == 3 and mv[-1] == 5 and mv.sum() == 8
    # what the block sums for today = the same minutes of the same tape
    class Probe(AlwaysB):
        seen: list = []

        def blk_session_volume(self):
            out = super().blk_session_volume()
            type(self).seen.append(out)
            return out
    monkeypatch.setattr(B, "_CUM", {})
    S.run_session(Probe({**QUIET, "f_cvol": "hi", "hold_to": "day"}), tape, daily=[], on_error="raise")
    full = B.minute_volume(tape)
    assert len(Probe.seen) > 50
    for a, b, v in Probe.seen:
        assert a == 34200 and v == full[a // 60 - B.MIN0:b // 60 - B.MIN0].sum()
    # "the session so far" starts at the session's anchor: a midday signal reads the volume since the 09:30 cash open
    assert B.VOL_ANCHOR == {"asia": 0, "london": 10800, "pre": 30300, "nyam": 34200, "mid": 34200, "pm": 34200, "eve": -21600}
    Probe.seen = []
    late = minute_tape(rand_bars(300, seed=9), "08:00")                             # 08:00 .. 13:00 ET
    S.run_session(Probe({**QUIET, "sess": "mid", "f_cvol": "hi", "hold_to": "day"}), late, daily=[], on_error="raise")
    full = B.minute_volume(late)
    assert len(Probe.seen) > 50 and all(a == 34200 and b > 39600 and v == full[a // 60 - B.MIN0:b // 60 - B.MIN0].sum()
                                        for a, b, v in Probe.seen)
    # the cache file: built per trade date, read back, a missing date falls back to the tape
    monkeypatch.setattr(B, "_mv_path", lambda root: tmp_path / f"minvol_{root}.npz")
    monkeypatch.setattr(B, "_MV_FILE", {})
    np.savez_compressed(tmp_path / "minvol_NQ.npz", dates=np.array(["2023-03-13"]), vol=full[None, :])
    c = B.cum_volume("NQ", "2023-03-13")
    assert c.shape == (B.NMIN + 1,) and c[0] == 0 and c[-1] == full.sum() and (np.diff(c) == full).all()


def test_the_volume_reference_on_real_days_is_the_median_of_the_prior_20_dates_same_clock_window():
    real_days()
    root, iso = "GC", "2023-03-14"
    rows = [r for r in S.load_daily(root) if r["date"] < iso]
    dates = [r["date"] for r in rows[-20:]]
    assert len(dates) == 20 and dates[-1] < iso
    tapes = [S.load_tape(d, root) for d in dates]
    for a, b in ((34200, 35100), (30300, 34200), (-21600, -18000), (48600, 50400)):
        vals = []
        for t in tapes:
            t0 = S.et_ns(t.date, "00:00")
            m = (t.ts >= t0 + a * S.NS) & (t.ts < t0 + b * S.NS)
            vals.append(int(t.size[m].sum()))
        assert B.cum_ref(root, dates, a, b) == float(np.median(vals)) and min(vals) >= 0


# ---- news: release days -------------------------------------------------------------------------------------------------------

def test_the_news_block_allows_or_blocks_whole_release_days(monkeypatch):
    days = B.release_days()
    assert "2021-09-03" in days and "2021-09-02" in days                      # NFP + ISM services; weekly claims (08:30)
    import csv
    with (S.CACHE / "events.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    by: dict = {}
    for r in rows:
        by.setdefault(r["date"], set()).add(r["time_et"])
    assert days == {d for d, ts in by.items() if ts & {"08:30", "10:00"}}
    only_fomc = [d for d, ts in by.items() if ts == {"14:00"}]
    assert only_fomc and not set(only_fomc) & days                            # a 14:00 FOMC row alone is not a release day
    tape = minute_tape(flat_bars(120), "09:00")
    for cal, is_day in ((frozenset({D.isoformat()}), True), (frozenset({"2023-03-15"}), False)):
        monkeypatch.setattr(B, "_NEWS", [cal])
        for f in ("yes", "no"):
            tr, log, _ = play(AlwaysB, {**QUIET, "f_news": f}, tape)
            assert log and all(ok == ((f == "yes") == is_day) for _, ok in attempts(log)) and bool(tr) == ((f == "yes") == is_day)


# ---- book: the top-10 imbalance agrees / disagrees with the side (NQ) ---------------------------------------------------------

def feats(fn, start="08:55", end="11:05"):
    """One row per minute stamped [start, end): usable 60 s after its stamp. imb10 = fn('HH:MM')."""
    m0 = np.arange(ns(start), ns(end), S.MIN_NS, dtype=np.int64)
    hhmm = [dt.datetime.fromtimestamp(t / 1e9, S.ET).strftime("%H:%M") for t in m0]
    return S.Features(m0 + S.MIN_NS, {"t_utc": (m0 // S.NS).astype(np.int64), "imb10": np.array([fn(h) for h in hhmm], np.float32)})


def imb(h):
    return float("nan") if h == "10:15" else 0.2 if h < "09:50" or "10:10" <= h < "10:40" else -0.2


def mean5(f, t_ns):
    """The 5-minute mean at a decision, from the rows directly: the 5 newest usable rows, all finite, the newest fresh."""
    n = int(np.searchsorted(f.usable_ns, t_ns, side="right"))
    w = f.cols["imb10"][max(0, n - 5):n]
    if len(w) < 5 or not np.isfinite(w).all() or not 0 <= t_ns - f.usable_ns[n - 1] < S.MIN_NS:
        return None
    return float(np.mean(w.astype(np.float64)))


def test_the_book_block_agree_is_the_templates_own_filter_and_disagree_is_its_mirror():
    tape, f = minute_tape(flat_bars(120), "09:00"), feats(imb)
    seen = set()
    for go, sd in (("long", 1), ("short", -1)):
        a = S.run_session(Always({**QUIET, "go": go, "f_book": "on", "hold_to": "day"}), tape, daily=[], features=f, on_error="raise").trades
        b, log, _ = play(AlwaysB, {**QUIET, "go": go, "f_book": "on"}, tape, daily=[], features=f)
        assert a and a == b                          # agree = l2sim.Template's f_book, not a second filter
        for e in log:
            m = mean5(f, e[1])
            assert (e[4] is not None) == (m is not None and m * sd >= 0)
        _, log, _ = play(AlwaysB, {**QUIET, "go": go, "f_bookopp": "on"}, tape, daily=[], features=f)
        for e in log:
            m = mean5(f, e[1])
            assert (e[4] is not None) == (m is not None and m * sd < 0)
            seen.add((go, e[4] is not None, m is None))
    assert {(g, True, False) for g in ("long", "short")} <= seen and {(g, False, True) for g in ("long", "short")} <= seen
    for opt in ("f_book", "f_bookopp"):              # no table / a stale table: no signal, nothing passes on either side
        for ft in (None, feats(lambda h: -0.2, end="09:20")):
            tr, log, _ = play(AlwaysB, {**QUIET, opt: "on"}, tape, daily=[], features=ft)
            assert log and not tr


def test_no_look_ahead_in_the_filters_rewriting_prints_and_book_rows_from_a_decision_on_changes_nothing_before_it(monkeypatch):
    bars = rand_bars(300, seed=5)
    tape, f = minute_tape(bars, "08:00"), feats(imb, "07:55", "13:05")
    daily = _profiles(monkeypatch, [40 + 4 * k for k in range(20)])
    monkeypatch.setattr(B, "_NEWS", [frozenset({D.isoformat()})])
    wide = {**QUIET, "tf": "5"}
    for extra in ({"f_rsi": "with"}, {"f_rsi": "against", "go": "short"}, {"f_cvol": "hi"}, {"f_cvol": "lo"}, {"f_dvol": "lo"},
                  {"f_news": "yes"}, {"f_book": "on"}, {"f_bookopp": "on"}, {"f_bookopp": "on", "f_rsi": "with", "f_cvol": "hi"}):
        _, clean, _ = play(AlwaysB, {**wide, **extra}, tape, daily=daily, features=f)
        assert clean
        cuts = sorted({e[1] for e in clean})[::3] + [ns("09:47:10"), ns("10:33:40")]
        for cut in cuts:
            g = np.random.default_rng(1)
            late = f.usable_ns > cut                 # a row is usable 60 s after its stamp: rows not yet usable are rewritten
            cols = {k: v.copy() for k, v in f.cols.items()}
            cols["imb10"][late] = g.uniform(-1, 1, int(late.sum())).astype(np.float32)
            _, dirty, _ = play(AlwaysB, {**wide, **extra}, garble(tape, cut), daily=daily, features=S.Features(f.usable_ns, cols))
            assert [e for e in dirty if e[1] <= cut] == [e for e in clean if e[1] <= cut], (extra, cut)


# ---- parity on real BUILD days: blocks off = the original family ---------------------------------------------------------------

PARITY = ["orb", "donchian", "first_bar_mom", "vwap_trend_pull", "vol_spike_break"]


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_parity_a_wrapped_family_with_every_block_off_is_trade_for_trade_the_original(root):
    real_days()
    days = days_of(root)
    exits = [S.menu(root)[k] for k in (2, 9, 28)]     # an ATR stop with a target, a points stop, a percent stop without one
    specs, pairs = [], []
    for name in PARITY + ["ib"]:
        cls = families.REGISTRY[name][0]
        for v in families.library(name)["variants"]:
            for x in exits:
                for sess, hold in [(s, "day") for s in RM.DAY_PASSES] + [("all", "session")]:
                    p = {**v, **x, "tf": "5", "sess": sess, "hold_to": hold}
                    if not cls(p).sessions():
                        continue
                    q = {**p, "ib_min": "60"} if name == "ib" else p         # ib_n at 60 minutes against ib
                    pairs.append((name, len(specs)))
                    specs += [(cls, p), (B.WRAPPED["ib_n" if name == "ib" else name], q)]
    res = S.run_many(specs, days=days, root=root, workers=W)
    assert all(r["skipped_by_error"] == 0 for r in res) and res[0]["sessions"] == 10
    count = {n: 0 for n in PARITY + ["ib"]}
    for name, k in pairs:
        a, b = res[k], res[k + 1]
        assert a["trades"] == b["trades"], (name, specs[k][1])               # every field of every trade, in order
        assert (a["used"], a["both_sides_sessions"], len(a["no_trade"])) == (b["used"], b["both_sides_sessions"], len(b["no_trade"]))
        count[name] += len(a["trades"])
    assert all(n > 0 for n in count.values()), count                         # counts only: every family traded


# ---- identical trades at 1 and 8 workers, blocks ON ----------------------------------------------------------------------------

def _on_specs(root):
    x = {"stop_mode": "rng", "stop_val": 0.5, "tgt_r": 1.5}
    y = {"stop_mode": "atr", "stop_val": 2.0, "tgt_r": 4.0}
    hd = {"tf": "5", "hold_to": "day"}
    out = [(B.WRAPPED["orb"], {**hd, **x, "sess": "nyam", "or_min": "15"}),
           (B.WRAPPED["orb"], {**hd, **x, "sess": "london", "or_min": "30", "f_cvol": "hi"}),
           (B.WRAPPED["ib_n"], {**hd, **x, "sess": "nyam", "ib_min": "15", "f_rsi": "with"}),
           (B.WRAPPED["ib_n"], {**hd, **y, "sess": "mid", "ib_min": "5", "f_news": "yes"}),
           (B.WRAPPED["donchian"], {**hd, **x, "sess": "nyam", "n": 20, "f_dvol": "hi"}),
           (B.WRAPPED["donchian"], {**hd, **y, "sess": "pm", "n": 10, "f_rsi": "against"}),
           (B.WRAPPED["first_bar_mom"], {**hd, **x, "sess": "nyam", "k": 1.0, "f_cvol": "lo"}),
           (B.WRAPPED["vol_spike_break"], {**hd, **x, "sess": "london", "m": 2.0, "f_news": "no"}),
           (B.WRAPPED["vwap_trend_pull"], {**hd, **y, "sess": "mid", "f_dvol": "lo"}),
           (B.CONTROLS["ib_n"], {**hd, **x, "sess": "nyam", "ib_min": "15", "p_entry": 0.5, "seed": 1}),
           (B.CONTROLS["donchian"], {**hd, **x, "sess": "pm", "n": 20, "p_entry": 0.5, "seed": 2})]
    if root == "NQ":
        out += [(B.WRAPPED["donchian"], {**hd, **y, "sess": "nyam", "n": 10, "f_book": "on"}),
                (B.WRAPPED["donchian"], {**hd, **y, "sess": "nyam", "n": 10, "f_bookopp": "on"}),
                (B.WRAPPED["orb"], {**hd, **x, "sess": "nyam", "or_min": "5", "f_bookopp": "on"})]
    return out


@pytest.mark.parametrize("root", ["NQ", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_blocks_on(root):
    real_days()
    days = days_of(root)
    specs = _on_specs(root)
    try:
        feats_ = S.L2Features(B.BOOK_COLS) if root == "NQ" else None
        a = S.run_many(specs, days=days, root=root, workers=1, features=feats_)
        b = S.run_many(specs, days=days, root=root, workers=W, features=feats_)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    assert a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == W
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (cls.__name__, x["no_trade"][:2])
        assert x["trades"] == y["trades"], (cls.__name__, p)
    assert sum(len(x["trades"]) for x in a) > 0
    if root == "NQ":                                 # the two sides of the book block never allow the same signal
        agree, opp = ({(t["entry_ms"], t["side"]) for t in a[k]["trades"]} for k in (11, 12))
        assert not agree & opp


# ---- run_idea: the spec, the plan, the build -----------------------------------------------------------------------------------

SPEC = {"name": "t_orb", "reason": "The first minutes of a session set a range and a break of it traps the other side.",
        "family": "orb", "markets": ["GC"], "bar_sizes": ["15"], "sessions": ["nyam"], "params": {"or_min": ["5", "15"]},
        "filters": [{"block": "news", "side": "yes"}, {"block": "volume", "side": "high"}, {"block": "book", "side": "agree"}],
        "exits": "extended", "filter_exits": "standard", "limits": {"max_tr": 1}}


def test_an_idea_spec_is_checked_field_by_field():
    sp = RI.check_spec(dict(SPEC))
    assert sp["variants"] == [{"or_min": "5"}, {"or_min": "15"}] and sp["fixed"] == {} and sp["filter_exits"] == "standard"
    for bad, word in (({"reason": "it works"}, "reason is REQUIRED"), ({"family": "nope"}, "family"), ({"markets": ["CL"]}, "markets"),
                      ({"bar_sizes": ["7"]}, "bar_sizes"), ({"sessions": ["lunch"]}, "sessions"), ({"params": {"n": [10]}}, "params"),
                      ({"params": {"stop_val": [1.0]}}, "params"), ({"fixed": {"f_rsi": "with"}}, "fixed"),
                      ({"filters": [{"block": "news", "side": "maybe"}]}, "filter"), ({"exits": "wide"}, "exits"),
                      ({"limits": {"tgt_r": 2.0}}, "limits"), ({"name": "T-orb"}, "name"), ({"extra": 1}, "unknown fields"),
                      ({"limits": {"max_tr": 0}}, "max_tr"), ({"filters": [{"block": "news", "side": "yes"}] * 2}, "twice")):
        with pytest.raises(RI.SpecError, match=word):
            RI.check_spec({**SPEC, **bad})
    with pytest.raises(RI.SpecError, match="missing fields"):
        RI.check_spec({k: v for k, v in SPEC.items() if k != "reason"})
    with pytest.raises(RI.SpecError, match="never trades there"):
        RI.check_spec({**SPEC, "family": "ib_n", "params": {"ib_min": ["5"]}, "sessions": ["asia", "nyam"]})
    with pytest.raises(RI.SpecError, match="file name"):
        RI.check_spec(dict(SPEC), "other")
    for name in ("orb", "c1x", "c1_mine"):               # a store key of the idea must never be a family's or a control's
        with pytest.raises(RI.SpecError, match="collide"):
            RI.check_spec({**SPEC, "name": name})
    assert RI.RUNS == LB.RUNS                            # idea stores are the library's BUILD stores (what judge.py reads)
    # a family without a structure: the extended menu has no range stop, and no range control
    flat = RI.check_spec({**SPEC, "family": "vwap_trend_pull", "params": {"x": [0.1]}})
    assert [u["cells"] for u in RI.spec_units(flat)] == [60, 32, 32] and {c["kind"] for c in RI.spec_controls(flat)} == {"c1", "c1x"}


def test_the_units_and_controls_of_a_spec():
    sp = RI.check_spec({**SPEC, "markets": ["NQ", "GC"]})
    us = RI.spec_units(sp)
    assert [u["key"] for u in us] == ["t_orb-NQ-tf15", "t_orb__news_yes-NQ-tf15", "t_orb__volume_high-NQ-tf15", "t_orb__book_agree-NQ-tf15",
                                      "t_orb-GC-tf15", "t_orb__news_yes-GC-tf15", "t_orb__volume_high-GC-tf15"]     # Level 2: NQ only
    assert [u["cells"] for u in us] == [156, 64, 64, 64, 156, 64, 64] and [u["book"] for u in us] == [False, False, False, True] + [False] * 3
    base, news = us[0]["grid"], us[1]["grid"]
    assert [c["id"] for c in base[:2]] == ["or_min5_atr1p5-r0", "or_min5_atr1p5-r1"] and base[77]["id"] == "or_min5_rng1-r4"
    assert all(c["spec"][0] is B.WRAPPED["orb"] and c["spec"][1]["max_tr"] == 1 for c in base + news)
    assert all(c["spec"][1]["f_news"] == "yes" for c in news) and all("f_news" not in c["spec"][1] for c in base)
    assert us[3]["grid"][0]["spec"][1]["f_book"] == "on" and RI._features(us[3]).columns == B.BOOK_COLS and RI._features(us[0]) is None
    assert RI.cell_specs(base[0], sp["sessions"]) == [(B.WRAPPED["orb"], {**base[0]["spec"][1], "sess": "nyam", "hold_to": "day"})]
    cs = {c["key"]: c for c in RI.spec_controls(sp)}
    assert set(cs) == {"c1-NQ-tf15", "c1x-NQ-tf15", "t_orb__c1r-NQ-tf15", "c1-GC-tf15", "c1x-GC-tf15", "t_orb__c1r-GC-tf15",
                       "t_orb__book_agree-NQ-tf15-c2s1", "t_orb__book_agree-NQ-tf15-c2s2"}       # the book unit: + a shuffled book
    c2 = cs["t_orb__book_agree-NQ-tf15-c2s2"]
    assert (c2["kind"], c2["seed"], c2["cells"]) == ("c2", 2, 64) and c2["grid"] == us[3]["grid"]
    assert RI.catalog([sp]) == [(u["key"], "nyam") for u in us]
    x, r = cs["c1x-GC-tf15"], cs["t_orb__c1r-GC-tf15"]
    assert x["cells"] == 56 and all(c["spec"][0] is l2ref.Random and c["exit"]["stop_mode"] != "rng" for c in x["grid"])
    assert r["cells"] == 2 * 2 * 18 and all(c["spec"][0] is B.CONTROLS["orb"] and c["exit"]["stop_mode"] == "rng" for c in r["grid"])
    ext = B.menu_extended("GC")
    assert all(ext[c["xi"]] == c["exit"] for c in x["grid"] + r["grid"])           # a control cell carries its exit's menu index
    assert {c["spec"][1]["or_min"] for c in r["grid"]} == {"5", "15"} and len({c["id"] for c in r["grid"]}) == 72
    # the structure inputs only: three values of a non-structure input share ONE range control
    fb = RI.check_spec({**SPEC, "family": "first_bar_mom", "params": {"k": [1.0, 1.5, 2.0]}})
    assert RI.struct_variants(fb) == [{}] and [c["cells"] for c in RI.spec_controls(fb) if c["kind"] == "c1r"] == [36]


def test_the_plan_counts_units_cells_and_null_cells_and_checks_the_80000_cap(tmp_path):
    sp = RI.check_spec({**SPEC, "markets": ["NQ", "GC"]})
    led = tmp_path / "ledger.csv"
    p = RI.plan([sp], ledger=led, runs_dir=tmp_path)
    assert (p["units"], p["base_units"], p["filter_units"], p["candidate_cells"], p["pending_cells"]) == (7, 2, 5, 632, 632)
    assert p["null_cells"] == 2 * (64 + 56 + 72) + 2 * 64 == p["null_cells_to_run"] and p["instances"] == 632
    assert RI.CAPS["cells"] == 80000 == p["cap"] and p["used"] == RM.PAPER_CELLS and p["fits"] and p["cap_left_after"] == 80000 - RM.PAPER_CELLS - 632
    LB.ledger_add("build", "filler", "grid", cells=80000 - RM.PAPER_CELLS - 631, path=led, caps=RI.CAPS)
    p = RI.plan([sp], ledger=led, runs_dir=tmp_path)
    assert not p["fits"] and p["cap_left_after"] == -1
    with pytest.raises(LB.CapExceeded):              # a spec that does not fit is refused as a whole, before anything runs
        RI.build(sp, workers=1, runs_dir=tmp_path, ledger=led, log=tmp_path / "log", days=["2023-03-14"])
    assert not any(tmp_path.glob("t_orb*")) and len(LB.read_ledger(led)) == 1


def test_the_r3_spec_files_load_and_ask_for_the_extended_menu_and_every_filter_on_both_sides():
    paths = RI.spec_paths(["r3_*"])
    specs = [RI.load_spec(p) for p in paths]
    assert {s["family"] for s in specs} == {"ib_n", "orb", "donchian", "first_bar_mom", "vwap_trend_pull", "vol_spike_break"}
    every = [(b, s) for b, sides in B.FILTERS.items() for s in sides if b in ("volatility", "momentum", "volume", "news", "book") and s in ("high", "low", "with", "against", "yes", "no", "agree", "disagree")]    # the r3 files predate the newer blocks and sides
    for s in specs:
        assert s["name"].startswith("r3_") and s["markets"] == ["NQ", "ES", "GC"] and s["exits"] == s["filter_exits"] == "extended"
        assert sorted(s["filters"]) == sorted(every) and {"5", "15"} <= set(s["bar_sizes"]) and len(s["reason"].split()) >= 8
    ib = next(s for s in specs if s["family"] == "ib_n")
    assert ib["params"] == {"ib_min": ["5", "15", "30", "60"]} and ib["fixed"] == {"mode": "break"} and ib["sessions"] == ["nyam", "mid", "pm"]


def test_build_writes_restartable_stores_and_books_them_and_the_base_cells_are_the_original_family(tmp_path):
    real_days()
    sp = RI.check_spec({**SPEC, "filters": SPEC["filters"][:2]})
    days = days_of("GC", 4)
    led, log = tmp_path / "ledger.csv", tmp_path / "log"
    out = RI.build(sp, workers=2, runs_dir=tmp_path, ledger=led, log=log, days=days)
    keys = ["c1-GC-tf15", "c1x-GC-tf15", "t_orb__c1r-GC-tf15", "t_orb-GC-tf15", "t_orb__news_yes-GC-tf15", "t_orb__volume_high-GC-tf15"]
    assert [o["key"] for o in out] == keys and all(o["ok"] for o in out)
    rows = {r["key"]: r for r in LB.read_ledger(led)}
    assert [(rows[k]["stage"], rows[k]["kind"]) for k in keys] == [("null", "null")] * 3 + [("build", "grid")] * 3
    assert [int(rows[k]["cells"] or 0) for k in keys] == [0, 0, 0, 156, 64, 64]
    assert [int(rows[k]["null_cells"] or 0) for k in keys] == [64, 56, 72, 0, 0, 0] and LB.ledger_used(path=led)["cells"] == 284
    u = LB.load_unit("t_orb-GC-tf15", tmp_path)
    m = u["meta"]
    assert (m["idea"], m["family"], m["exits"], m["sessions"], m["hold_to"], m["period"], m["filter"]) == ("t_orb", "orb", "extended", ["nyam"], "day", "build", None)
    assert m["rationale"] == sp["reason"] and len(m["cells"]) == 156 and m["coverage"]["sessions"] == len(days)
    f = LB.load_unit("t_orb__news_yes-GC-tf15", tmp_path)["meta"]
    assert f["filter"]["block"] == "news" and f["filter"]["side"] == "yes" and f["complexity"] == m["complexity"] + 1
    # the base unit's standard cells = the ORIGINAL orb on the same days (trade counts per cell and entry times)
    orb = families.REGISTRY["orb"][0]
    ref = S.run_many([(orb, {"tf": "15", "sess": "nyam", "hold_to": "day", "max_tr": 1, "or_min": v["or_min"], **x})
                      for v in sp["variants"] for x in S.menu("GC")], days=days, root="GC", workers=2)
    ids = [f"or_min{v['or_min']}_{S.cell_id(x)}" for v in sp["variants"] for x in S.menu("GC")]
    for cid, r in zip(ids, ref):
        mine = LB.unit_cell(u, cid)
        assert sorted(mine["entry_ms"].tolist()) == sorted(t["entry_ms"] for t in r["trades"])
    assert sum(len(r["trades"]) for r in ref) > 0
    # a news-day unit trades on release days only; restart: everything is skipped, nothing is booked twice
    nd = LB.load_unit("t_orb__news_yes-GC-tf15", tmp_path)
    rel = {dt.date.fromisoformat(d).toordinal() for d in B.release_days()}
    assert set(nd["date"].tolist()) <= rel
    again = RI.build(sp, workers=2, runs_dir=tmp_path, ledger=led, log=log, days=days)
    assert all(o.get("skipped") for o in again) and len(LB.read_ledger(led)) == 6
    assert RI.status([sp], runs_dir=tmp_path, ledger=led) == {"units": 3, "done": 3, "pending": [], "controls": 3, "controls_pending": []}
