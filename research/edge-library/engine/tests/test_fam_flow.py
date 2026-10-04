"""Flow families F1-F4 (families/flow.py) against their pre-registered definitions (FAMILIES.md "Flow families").

Synthetic tapes + synthetic feature tables only, except one equality-only check on two in-sample days. Nothing here
looks at P&L: the assertions are on WHEN a signal fires, its side, and on what a decision may have read.

* ORACLE: every definition is re-implemented below in plain Python from FAMILIES.md (own clock buckets, own bars, own
  ATR, own session table), independent of families/flow.py and of the Template. On randomised days (missing prints,
  NaN flow, book_ok False, missing rows) the families must signal at exactly the oracle's instants, with its side.
* TIMESTAMP LAW (helpers of tests/test_l2sim_lookahead.py): every value a decision reads belongs to a usable row;
  rows that are not usable yet cannot change a decision; a table shifted by a minute / an hour never signals.
"""
import copy
import datetime as dt

import numpy as np
import pytest

import apex300
import families
import l2sim as S
import score
import test_l2sim_lookahead as LA
from families import flow as F

D = dt.date(2024, 3, 5)                                   # a plain in-sample day (EST); nothing is read from disk for it
MID_NS = S.et_ns(D, "00:00")
MID = MID_NS // S.NS
TICK = 0.25
SESS = {"nyam": (34200, 39600), "mid": (39600, 48600), "pm": (48600, 57480)}        # written out: not l2sim.SESS
FAMS = {"delta_follow": F.DeltaFollow, "absorption": F.Absorption, "cvd_div": F.CvdDiv, "sweep_follow": F.SweepFollow}
SWEEP = ("f_sweep_buy_vol", "f_sweep_sell_vol")


def hm(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 3600 + int(m) * 60


# ---- the synthetic day --------------------------------------------------------------------------------------------
class World:
    """One synthetic day. bars: minute start second (ET) -> (o, h, l, c), printed at +1 / +15 / +30 / +45 s.
    rows: minute start second -> {column: value} = the feature row STAMPED for that minute (usable 60 s later)."""

    def __init__(self, seed: int, start="08:30", end="13:45", feat_start="02:00", messy: bool = True, wick: int = 6):
        rng = np.random.default_rng(seed)
        self.bars, self.rows = {}, {}
        px = 72000                                        # ticks (18,000.00)
        for s in range(hm(start), hm(end), 60):
            o = px + int(rng.integers(-1, 2))
            c = o + int(rng.integers(-3, 4))
            h, l = max(o, c) + int(rng.integers(0, wick)), min(o, c) - int(rng.integers(0, wick))
            self.bars[s] = tuple(x * TICK for x in (o, h, l, c))
            px = c
        for s in range(hm(feat_start), hm(end), 60):
            dense = s >= hm("10:15")                      # sweeps are rare early (P95 = 0: the "> 0" guard) and common later
            hit = rng.random(2) < (0.5 if dense else 0.04)
            self.rows[s] = {"f_delta": float(rng.integers(-30, 31)), "book_ok": True,
                            "f_sweep_buy_vol": float(rng.integers(1, 7)) if hit[0] else 0.0,
                            "f_sweep_sell_vol": float(rng.integers(1, 7)) if hit[1] else 0.0}
        if not messy:
            return
        ks = sorted(self.rows)
        for s in rng.choice(ks, size=len(ks) // 25, replace=False):          # minutes without a print: flow is NaN
            self.rows[int(s)].update(f_delta=float("nan"), f_sweep_buy_vol=float("nan"), f_sweep_sell_vol=float("nan"))
        for s in range(hm("05:00"), hm("05:10"), 60):                         # two whole tf-5 buckets without flow
            self.rows[s].update(f_delta=float("nan"), f_sweep_buy_vol=float("nan"), f_sweep_sell_vol=float("nan"))
        live = [s for s in ks if s >= hm("09:30")]
        for s in rng.choice(live, size=12, replace=False):                    # masked rows (roll / crossed book)
            self.rows[int(s)]["book_ok"] = False
        for s in rng.choice(live, size=4, replace=False):                     # rows missing from the table
            del self.rows[int(s)]
        for s in rng.choice([s for s in self.bars if s >= hm("09:30")], size=14, replace=False):
            del self.bars[int(s)]                                             # minutes without a print on the tape
        for s in (hm("10:04"), hm("10:24"), hm("12:09"), hm("12:10"), hm("12:11"), hm("12:12"), hm("12:13"), hm("12:14")):
            self.bars.pop(s, None)                                            # late tf-5 closes and one empty tf-5 bucket

    def tape(self) -> S.Tape:
        ts, px = [], []
        for s in sorted(self.bars):
            for off, p in zip((1, 15, 30, 45), self.bars[s]):
                ts.append(MID_NS + (s + off) * S.NS)
                px.append(p)
        return S.Tape("NQ", D, "NQH4", ts, px, [1] * len(ts))

    def features(self, cols, shift_s: int = 0) -> S.Features:
        ks = sorted(self.rows)
        out = {"t_utc": np.array([MID + s for s in ks], np.int64)}
        for c in cols:
            if c == "book_ok":
                out[c] = np.array([self.rows[s][c] for s in ks], bool)
            elif c != "t_utc":
                out[c] = np.array([self.rows[s][c] for s in ks], np.float32)
        return S.Features(np.array([(MID + s + 60 + shift_s) * S.NS for s in ks], np.int64), out)


def world(name, seed, **kw) -> World:
    """The random day for a family. F3 gets short wicks: with long ones a CLOSE beyond the session extreme is too rare
    for the day to exercise the trigger."""
    return World(seed, wick=2 if name == "cvd_div" else 6, **kw)


def recorder(cls):
    """The family with its order replaced by a note: it stays flat, so EVERY decision instant is evaluated."""
    class Rec(cls):
        def on_session(self, ctx):
            super().on_session(ctx)
            self.sig = []

        def _mkt(self, ctx, side, **kw):
            self.sig.append((int((ctx.now_ns - self.t0) // S.NS), side))
    return Rec


def signals(cls, world, params, feats=None):
    st = recorder(cls)(params)
    res = S.run_session(st, world.tape(), features=world.features(cls.FEATURES) if feats is None else feats)
    assert res.skip is None, res.skip
    assert res.trades == []
    return st.sig


# ---- the oracle (FAMILIES.md, re-implemented) ---------------------------------------------------------------------
def tf_bars(world, tf):
    """clock bucket start -> [o, h, l, c, start of its last printed minute]"""
    out = {}
    for s in sorted(world.bars):
        k = s - s % (tf * 60)
        o, h, l, c = world.bars[s]
        if k not in out:
            out[k] = [o, h, l, c, s]
        else:
            b = out[k]
            b[1], b[2], b[3], b[4] = max(b[1], h), min(b[2], l), c, s
    return out


def atr_after(bars):
    """bucket start -> (Wilder ATR(14) including that bar, bars so far)"""
    out, trs, atr, prev = {}, [], None, None
    for k in sorted(bars):
        o, h, l, c, _ = bars[k]
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        trs.append(tr)
        atr = sum(trs) / len(trs) if len(trs) <= 14 else (atr * 13.0 + tr) / 14.0
        out[k], prev = (atr, len(trs)), c
    return out


def bucket(world, T, tf, j, names):
    """Sums of `names` over the j-th tf clock bucket before T (0 = the signal bar), None when no row counts."""
    lo, tot, n = T - (j + 1) * tf * 60, [0.0] * len(names), 0
    for s in range(lo, lo + tf * 60, 60):
        r = world.rows.get(s)
        if r is None or any(r[c] != r[c] for c in names):
            continue
        n += 1
        tot = [a + r[c] for a, c in zip(tot, names)]
    return tot if n else None


def decisions(world, tf, sessions):
    """(T, session, bucket start): the instants at which a family may signal -- an on-time tf close inside a session,
    >= 3 tf bars so far, more than 5 minutes before the session end, newest row = the minute that just ended, book_ok."""
    bars = tf_bars(world, tf)
    atr = atr_after(bars)
    for k in sorted(bars):
        T = k + tf * 60
        if bars[k][4] != T - 60 or atr[k][1] < 3:
            continue
        sid = next((n for n in sessions if SESS[n][0] < T <= SESS[n][1]), None)
        if sid is None or T >= SESS[sid][1] - 300:
            continue
        r = world.rows.get(T - 60)
        if r is None or not r["book_ok"]:
            continue
        yield T, sid, k


def top(world, T, tf, names, q, stats):
    """(signal-bar sums, True when sum(signal bar) > 0 and >= the q-th percentile of the trailing 60 buckets)"""
    cur = bucket(world, T, tf, 0, names)
    hist = [abs(sum(b)) for b in (bucket(world, T, tf, j, names) for j in range(1, 61)) if b is not None]
    if cur is None or len(hist) < 30:
        stats["thin"] += 1
        return cur, False
    a, p = abs(sum(cur)), float(np.percentile(np.array(hist, float), q))
    stats["eq"] += a == p
    stats["zero"] += a == 0 and p == 0
    return cur, a > 0 and a >= p


def oracle(name, world, tf, sessions=("nyam", "mid", "pm"), q=None, move_atr=0.25, warm_min=15):
    bars = tf_bars(world, tf)
    atr = atr_after(bars)
    out, stats = [], {"eq": 0, "zero": 0, "thin": 0, "n": 0}
    for T, sid, k in decisions(world, tf, sessions):
        stats["n"] += 1
        o, h, l, c, _ = bars[k]
        side = None
        if name in ("delta_follow", "absorption"):
            cur, hot = top(world, T, tf, ["f_delta"], 90.0 if q is None else q, stats)
            if hot:
                d = cur[0]
                if name == "delta_follow":
                    side = "long" if d > 0 and c > o else "short" if d < 0 and c < o else None
                elif abs(c - o) <= move_atr * atr[k][0]:
                    side = "short" if d > 0 else "long"
        elif name == "sweep_follow":
            cur, hot = top(world, T, tf, list(SWEEP), 95.0 if q is None else q, stats)
            if hot:
                side = "long" if cur[0] > cur[1] else "short" if cur[1] > cur[0] else None
        else:
            s0 = SESS[sid][0]
            prev = [bars[b] for b in bars if s0 < b + tf * 60 < T]
            rows = [world.rows.get(s) for s in range(s0, T, 60)]
            if (T - s0) // 60 >= max(warm_min, 1) and prev and None not in rows and rows[-1]["f_delta"] == rows[-1]["f_delta"]:
                cum, hi, lo = 0.0, 0.0, 0.0
                for r in rows:
                    cum += r["f_delta"] if r["f_delta"] == r["f_delta"] else 0.0
                    hi, lo = max(hi, cum), min(lo, cum)
                if c > max(b[1] for b in prev):
                    side = "short" if cum < hi else None
                elif c < min(b[2] for b in prev):
                    side = "long" if cum > lo else None
        if side:
            out.append((T, side))
    return out, stats


# ---- the registry entry = the SPEC's pre-registered defaults ------------------------------------------------------
def test_registry_entries_carry_the_pre_registered_defaults():
    assert families.ERRORS == {}, families.ERRORS
    common = {"sess": "all", "dir": "both", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0, "trail_atr": 0.0,
              "exit_bars": 0, "max_tr": 3, "f_trend": "off", "f_vwap": "off", "f_depth": "off", "f_book": "off", "x_book": "off",
              "f_thin": "off", "hold_to": "session"}
    own = {"delta_follow": {"q": 90.0}, "absorption": {"q": 90.0, "move_atr": 0.25}, "cvd_div": {"warm_min": 15},
           "sweep_follow": {"q": 95.0}}
    for name, cls in FAMS.items():
        e = families.REGISTRY[name]
        assert e[0] is cls and e[1] == {} and e[2] is False and families.MODULE_OF[name] == "flow"
        assert families.check_entry(name, e) == []
        assert cls.SCREEN_TFS == ("1", "5") and cls.session_independent is True and not hasattr(cls, "SCREEN_RUN")
        p = cls(families.screen_inputs(name, "5")).p
        assert {k: p[k] for k in common} == common and {k: p[k] for k in own[name]} == own[name]
        assert set(p) == set(common) | set(own[name]) | {"tf"}                 # <= 2 family parameters, nothing hidden
        assert set(cls.FEATURES) - {"t_utc", "book_ok"} == (set(SWEEP) if name == "sweep_follow" else {"f_delta"})
        null = score.C2Features(cls.FEATURES, seed=1)                          # the C2 null shuffles the flow columns only
        assert set(null.shuffle_cols) == set(cls.FEATURES) - {"t_utc", "book_ok"}
    assert (F.LOOK, F.MIN_VALID) == (60, 30)
    assert "REVISIT" not in families.REGISTRY["delta_follow"][3] and "refuted" in families.REGISTRY["absorption"][3]


# ---- the two building blocks ---------------------------------------------------------------------------------------
def test_bucket_sums_are_clock_buckets_counted_back_from_the_decision():
    now, nan = 10_000 * 300, float("nan")                                     # a multiple of 5 minutes
    t = np.array([now - 60 * k for k in range(14, 0, -1)], np.int64)          # the 14 minutes before the decision
    v = np.arange(1.0, 15.0)
    sums, valid = F.bucket_sums(t, [v], now, 5, look=3)
    assert sums.tolist() == [[10 + 11 + 12 + 13 + 14, 5 + 6 + 7 + 8 + 9, 1 + 2 + 3 + 4, 0]] and valid.tolist() == [True, True, True, False]
    sums, valid = F.bucket_sums(t, [v], now, 1, look=3)                       # tf 1: one row per bucket, older rows ignored
    assert sums.tolist() == [[14.0, 13.0, 12.0, 11.0]] and valid.all()
    w = v.copy()
    w[[5, 6, 7, 8]] = nan                                                     # bucket 1 keeps one finite minute (5)
    sums, valid = F.bucket_sums(t, [w], now, 5, look=3)
    assert sums.tolist() == [[60.0, 5.0, 10.0, 0.0]] and valid.tolist() == [True, True, True, False]
    w[4] = nan                                                                # ... and now none: MISSING, not zero
    sums, valid = F.bucket_sums(t, [w], now, 5, look=3)
    assert valid.tolist() == [True, False, True, False] and sums[0, 1] == 0.0
    a, b = v.copy(), v.copy()                                                 # two columns: a row counts only when both are finite
    a[13], b[12] = nan, nan
    sums, valid = F.bucket_sums(t, [a, b], now, 5, look=3)
    assert sums[:, 0].tolist() == [10 + 11 + 12, 10 + 11 + 12] and valid[0]
    keep = np.array([k not in (3, 9) for k in range(14)])                     # rows missing from the table: buckets by clock, not by count
    sums, valid = F.bucket_sums(t[keep], [v[keep]], now, 5, look=3)
    assert sums.tolist() == [[11 + 12 + 13 + 14, 5 + 6 + 7 + 8 + 9, 1 + 2 + 3, 0]]
    sums, valid = F.bucket_sums(np.array([now, now + 60, now - 60]), [np.array([100.0, 100.0, 1.0])], now, 1, look=3)
    assert sums.tolist() == [[1.0, 0, 0, 0]]                                  # a row stamped at / after the decision never counts


def test_top_quantile_is_inclusive_needs_30_values_and_a_positive_bar():
    h = [10.0] * 60
    assert F.top_quantile(10.0, h, 90.0) and not F.top_quantile(9.0, h, 90.0)             # >= : equality fires
    assert not F.top_quantile(0.0, [0.0] * 60, 95.0) and F.top_quantile(1.0, [0.0] * 60, 95.0)   # "and > 0"
    assert not F.top_quantile(1e9, [1.0] * 29, 90.0) and F.top_quantile(1e9, [1.0] * 30, 90.0)   # 30 valid buckets
    h = list(range(1, 61))                                                    # P90 = 54.1, P95 = 57.05 (linear interpolation)
    assert not F.top_quantile(54.0, h, 90.0) and F.top_quantile(55.0, h, 90.0)
    assert not F.top_quantile(57.0, h, 95.0) and F.top_quantile(58.0, h, 95.0)


# ---- the triggers fire exactly when defined ------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(FAMS))
@pytest.mark.parametrize("tf", ["1", "5"])
@pytest.mark.parametrize("seed", [11, 12, 13, 62])
def test_signals_equal_the_oracle_on_randomised_days(name, tf, seed):
    w = world(name, seed)
    want, stats = oracle(name, w, int(tf))
    got = signals(FAMS[name], w, {"tf": tf})
    assert got == want
    assert stats["n"] > (150 if tf == "1" else 25)                            # the day really offers that many decisions


@pytest.mark.parametrize("name", sorted(FAMS))
def test_the_randomised_days_exercise_both_sides_the_boundary_and_the_guards(name):
    """Power of the oracle test: over the seeds both directions occur and (percentile families) the bar sits exactly
    ON the percentile at some decisions; for sweeps the zero-percentile case (the '> 0' guard) occurs too."""
    sides, eq, zero, n = set(), 0, 0, 0
    for seed in (11, 12, 13, 62):
        for tf in (1, 5):
            want, stats = oracle(name, world(name, seed), tf)
            sides |= {s for _, s in want}
            eq, zero, n = eq + stats["eq"], zero + stats["zero"], n + len(want)
    assert sides == {"long", "short"} and n >= 20
    if name != "cvd_div":
        assert eq > 0
    if name == "sweep_follow":
        assert zero > 0


@pytest.mark.parametrize("name,params,kw", [
    ("delta_follow", {"q": 75.0}, {"q": 75.0}), ("absorption", {"q": 60.0, "move_atr": 0.6}, {"q": 60.0, "move_atr": 0.6}),
    ("sweep_follow", {"q": 80.0}, {"q": 80.0}), ("cvd_div", {"warm_min": 0}, {"warm_min": 0}),
    ("cvd_div", {"warm_min": 45}, {"warm_min": 45})])
def test_the_family_inputs_are_what_the_trigger_uses(name, params, kw):
    w, differs = world(name, 21), 0
    for tf in ("1", "5"):
        want, _ = oracle(name, w, int(tf), **kw)
        assert signals(FAMS[name], w, {"tf": tf, **params}) == want
        differs += want != oracle(name, w, int(tf))[0]
    assert differs > 0                                                        # the input matters on this day


def test_one_session_only_and_the_session_restart_of_the_cum_delta():
    for name, cls in FAMS.items():
        w = world(name, 31)
        for sess in ("nyam", "mid"):
            want, _ = oracle(name, w, 5, sessions=(sess,))
            assert signals(cls, w, {"tf": "5", "sess": sess}) == want
            assert all(SESS[sess][0] < T < SESS[sess][1] - 300 for T, _ in want)
    # F3: the mid session's cum-delta and price extremes start at 11:00, they do not inherit nyam's
    w = world("cvd_div", 31)
    both = signals(F.CvdDiv, w, {"tf": "1"})
    mid = signals(F.CvdDiv, w, {"tf": "1", "sess": "mid"})
    assert [x for x in both if SESS["mid"][0] < x[0] <= SESS["mid"][1]] == mid == oracle("cvd_div", w, 1, sessions=("mid",))[0]
    assert len(mid) > 0


def test_explicit_delta_bar_fires_at_its_own_close_and_not_before():
    """Hand-built: quiet flow (|delta| 1 .. 10 cycling), flat bars; ONE minute (10:00) with delta +50 and an up bar.
    F1 goes long at 10:01:00 -- the first instant the row is usable -- and nowhere else; with a down bar F1 is silent
    and F2 (bar inside 0.25 ATR) fades it."""
    w = World(1, messy=False)
    for i, s in enumerate(sorted(w.rows)):
        w.rows[s].update(f_delta=float((i % 10 + 1) * (1 if i % 2 else -1)), f_sweep_buy_vol=0.0, f_sweep_sell_vol=0.0)
    for s in w.bars:
        w.bars[s] = (18000.0, 18002.0, 17998.0, 18000.0)                      # close == open: F1 can never fire
    x = hm("10:00")
    w.rows[x]["f_delta"] = 50.0
    w.bars[x] = (18000.0, 18002.0, 17998.0, 18000.5)                          # up 2 ticks (ATR 4 -> 0.25 ATR = 1.0)
    assert signals(F.DeltaFollow, w, {"tf": "1", "sess": "nyam"}) == [(x + 60, "long")]
    assert (x + 60, "short") in signals(F.Absorption, w, {"tf": "1", "sess": "nyam"})
    w.bars[x] = (18000.0, 18002.0, 17998.0, 17999.5)                          # the bar closes AGAINST the delta
    assert signals(F.DeltaFollow, w, {"tf": "1", "sess": "nyam"}) == []
    w.rows[x]["f_delta"] = -50.0                                              # sell delta, down bar -> short
    assert signals(F.DeltaFollow, w, {"tf": "1", "sess": "nyam"}) == [(x + 60, "short")]
    assert (x + 60, "long") in signals(F.Absorption, w, {"tf": "1", "sess": "nyam"})
    w.bars[x] = (18000.0, 18002.0, 17994.0, 17995.0)                          # a 5-point bar is not absorbed
    assert (x + 60, "long") not in signals(F.Absorption, w, {"tf": "1", "sess": "nyam"})
    assert signals(F.DeltaFollow, w, {"tf": "1", "sess": "nyam"}) == [(x + 60, "short")]
    # tf 5: the same minute inside the 10:00-10:05 bar -> one signal at 10:05:00, the bar's own close
    w.bars[hm("10:04")] = (18000.0, 18002.0, 17994.0, 17994.0)
    assert signals(F.DeltaFollow, w, {"tf": "5", "sess": "nyam"}) == [(hm("10:05"), "short")]
    # sweeps: buy sweeps in 10:00 -> long at 10:01; equal buy and sell sweep volume -> no side, no signal
    w.rows[x].update(f_sweep_buy_vol=7.0, f_sweep_sell_vol=2.0)
    assert signals(F.SweepFollow, w, {"tf": "1", "sess": "nyam"}) == [(x + 60, "long")]
    w.rows[x].update(f_sweep_buy_vol=4.0, f_sweep_sell_vol=4.0)
    assert signals(F.SweepFollow, w, {"tf": "1", "sess": "nyam"}) == []
    w.rows[x].update(f_sweep_buy_vol=1.0, f_sweep_sell_vol=6.0)
    assert signals(F.SweepFollow, w, {"tf": "1", "sess": "nyam"}) == [(x + 60, "short")]


def test_explicit_cvd_divergence():
    """Hand-built nyam session at tf 5: price grinds to a new closing high at 10:00-10:05 while the session cum-delta,
    positive early, has fallen back -> short at 10:05:00. With the cum-delta AT its high: no signal. Mirror for lows."""
    def world(deltas_after, up=True):
        w = World(2, messy=False)
        for s in w.rows:
            w.rows[s]["f_delta"] = 0.0
        for s in w.bars:
            w.bars[s] = (18000.0, 18001.0, 17999.0, 18000.0)
        sgn = 1 if up else -1
        w.rows[hm("09:31")]["f_delta"] = 40.0 * sgn                          # the session cum-delta extreme, early
        for m, d in deltas_after.items():
            w.rows[hm(m)]["f_delta"] = d * sgn
        px = 18000.0 + sgn * 3.0
        w.bars[hm("10:04")] = (18000.0, max(18001.0, px), min(17999.0, px), px)    # the 10:00 bar CLOSES beyond 18001 / 17999
        return w
    T = hm("10:05")
    assert signals(F.CvdDiv, world({"09:50": -15.0}), {"tf": "5", "sess": "nyam"}) == [(T, "short")]       # cvd 25 < 40
    assert signals(F.CvdDiv, world({"10:03": 5.0}), {"tf": "5", "sess": "nyam"}) == []                    # cvd 45 = its high
    assert signals(F.CvdDiv, world({"10:02": 5.0, "10:04": -5.0}), {"tf": "5", "sess": "nyam"}) == [(T, "short")]   # 45 inside the bar, 40 at the close
    assert signals(F.CvdDiv, world({"09:50": -15.0}, up=False), {"tf": "5", "sess": "nyam"}) == [(T, "long")]
    assert signals(F.CvdDiv, world({"10:03": 5.0}, up=False), {"tf": "5", "sess": "nyam"}) == []
    w = world({})                                                              # cvd flat at +40 = its extreme: confirmed, no fade
    assert signals(F.CvdDiv, w, {"tf": "5", "sess": "nyam"}) == []
    w = world({"09:31": -40.0})                                                # never above the 0 start: cvd -40 < 0 = session high
    assert signals(F.CvdDiv, w, {"tf": "5", "sess": "nyam"}) == [(T, "short")]
    w = world({"09:50": -15.0})
    w.bars[hm("10:04")] = (18000.0, 18003.0, 17999.0, 18001.0)                 # a wick above the high, close AT it: not a new high
    assert signals(F.CvdDiv, w, {"tf": "5", "sess": "nyam"}) == []
    w = world({"09:36": -15.0})                                                # the same break inside the first 15 minutes: warm-up
    w.bars[hm("09:39")] = (18000.0, 18003.0, 17999.0, 18003.0)
    got = signals(F.CvdDiv, w, {"tf": "5", "sess": "nyam"})
    assert (hm("09:40"), "short") not in got and signals(F.CvdDiv, w, {"tf": "5", "sess": "nyam", "warm_min": 10})[0] == (hm("09:40"), "short")


# ---- guards: masked / NaN / stale rows, late closes, the last five minutes -----------------------------------------
@pytest.mark.parametrize("name", sorted(FAMS))
def test_masked_nan_and_missing_rows_give_no_signal(name):
    cls, base = FAMS[name], world(name, 41, messy=False)
    ref = signals(cls, base, {"tf": "1"})
    assert len(ref) >= 5
    T, side = ref[len(ref) // 2]
    w = copy.deepcopy(base)                                                   # book_ok False on the decision row
    w.rows[T - 60]["book_ok"] = False
    assert (T, side) not in signals(cls, w, {"tf": "1"})
    w = copy.deepcopy(base)                                                   # the row is missing: the newest row is stale
    del w.rows[T - 60]
    assert T not in [t for t, _ in signals(cls, w, {"tf": "1"})]
    w = copy.deepcopy(base)                                                   # NaN flow on the decision row
    w.rows[T - 60].update(f_delta=float("nan"), f_sweep_buy_vol=float("nan"), f_sweep_sell_vol=float("nan"))
    assert T not in [t for t, _ in signals(cls, w, {"tf": "1"})]
    w = copy.deepcopy(base)                                                   # every row masked: a roll day never trades
    for r in w.rows.values():
        r["book_ok"] = False
    assert signals(cls, w, {"tf": "1"}) == [] and signals(cls, w, {"tf": "5"}) == []
    w = copy.deepcopy(base)                                                   # no flow at all (a session without a flow tape)
    for r in w.rows.values():
        r.update(f_delta=float("nan"), f_sweep_buy_vol=float("nan"), f_sweep_sell_vol=float("nan"))
    assert signals(cls, w, {"tf": "1"}) == [] and signals(cls, w, {"tf": "5"}) == []
    assert S.run_session(recorder(cls)({"tf": "5"}), base.tape(), features=None).skip is None      # no table: silent, no crash


@pytest.mark.parametrize("name", sorted(FAMS))
def test_fewer_than_30_trailing_buckets_give_no_signal(name):
    if name == "cvd_div":
        pytest.skip("F3 has no trailing percentile")
    cls = FAMS[name]
    w = World(42, messy=False, feat_start="09:05")                            # the table starts 25 minutes before the session
    got = signals(cls, w, {"tf": "1", "sess": "nyam"})
    assert got == oracle(name, w, 1, sessions=("nyam",))[0] and len(got) > 0
    assert min(t for t, _ in got) >= hm("09:05") + 31 * 60                     # 30 trailing buckets + the signal bar
    w = World(42, messy=False, feat_start="08:30")                            # tf 5: 30 buckets = 150 minutes -> nothing before 11:05
    got = signals(cls, w, {"tf": "5"})
    assert got == oracle(name, w, 5)[0] and all(t >= hm("11:05") for t, _ in got)


@pytest.mark.parametrize("name", sorted(FAMS))
def test_a_late_close_is_not_a_signal_instant(name):
    """tf 5: the bar 10:00-10:05 whose last minute has no print is closed by the Template at 10:06:00 -- no signal there
    (and none at 10:05:00, where nothing fires); with the minute printed the same bar signals at 10:05:00."""
    cls = FAMS[name]
    for seed in range(50, 80):
        base = world(name, seed, messy=False)
        ref = signals(cls, base, {"tf": "5", "sess": "nyam"})
        if ref:
            break
    T, side = ref[0]
    w = copy.deepcopy(base)
    del w.bars[T - 60]
    got = signals(cls, w, {"tf": "5", "sess": "nyam"})
    assert all(t % 300 == 0 for t, _ in got) and T not in [t for t, _ in got]
    assert got == oracle(name, w, 5, sessions=("nyam",))[0]
    assert all(t % 300 == 0 for t, _ in ref)


@pytest.mark.parametrize("name", sorted(FAMS))
def test_no_signal_in_the_last_five_minutes_of_a_session(name):
    """Every bar of the day is made a trigger bar; the family still never signals at or after session end - 5 min."""
    w = World(43, messy=False)
    for s in w.rows:                                                          # all bars equal: each one sits ON its percentile
        w.rows[s].update(f_delta=500.0, f_sweep_buy_vol=50.0, f_sweep_sell_vol=0.0)
    for i, s in enumerate(sorted(w.bars)):                                    # rising closes (F1), a close above the prior high every bar (F3)
        p = 18000.0 + 0.5 * i
        w.bars[s] = (p, p + 0.5, p - 0.25, p + 0.25)
    params = {"tf": "1", "move_atr": 2.0} if name == "absorption" else {"tf": "1", "warm_min": 0} if name == "cvd_div" else {"tf": "1"}
    if name == "cvd_div":                                                     # falling cum-delta against rising closes
        for s in w.rows:
            w.rows[s]["f_delta"] = -5.0
    got = [t for t, _ in signals(FAMS[name], w, params)]
    for a, b in SESS.values():
        ins = [t for t in got if a < t <= b]
        if b <= max(w.bars):
            assert ins and max(ins) == b - 360, (name, a, b, max(ins, default=None))   # the last one: 6 minutes before the end
    assert not [t for t in got if any(b - 300 <= t <= b for _, b in SESS.values())]
    assert not [t for t in got if hm("08:25") < t <= hm("09:30")]              # between sessions: nothing


@pytest.mark.parametrize("name", sorted(FAMS))
def test_no_signal_in_the_last_five_minutes_of_a_half_day(name):
    """A CME half day ends at 13:15 ET for the engine (the mid session's own end is 13:30): with every bar a trigger bar
    the last signal is at 13:09, on the full day it runs on to 13:24."""
    half = dt.date(2023, 11, 24)
    assert half in S.EARLY_CLOSES and D not in S.EARLY_CLOSES
    out = {}
    for day in (D, half):
        mid_ns = S.et_ns(day, "00:00")
        ts, px, t_utc, usable = [], [], [], []
        for i, s in enumerate(range(hm("08:30"), hm("13:45"), 60)):           # rising closes, each above the prior high
            p = 18000.0 + 0.5 * i
            for off, q in zip((1, 15, 30, 45), (p, p + 0.5, p - 0.25, p + 0.25)):
                ts.append(mid_ns + (s + off) * S.NS)
                px.append(q)
        for s in range(hm("02:00"), hm("13:45"), 60):
            t_utc.append(mid_ns // S.NS + s)
            usable.append(mid_ns + (s + 60) * S.NS)
        n = len(t_utc)
        cols = {"t_utc": np.array(t_utc, np.int64), "book_ok": np.ones(n, bool),
                "f_delta": np.full(n, -5.0 if name == "cvd_div" else 500.0, np.float32),
                "f_sweep_buy_vol": np.full(n, 50.0, np.float32), "f_sweep_sell_vol": np.zeros(n, np.float32)}
        cls = FAMS[name]
        st = recorder(cls)({"tf": "1", "sess": "mid", **({"move_atr": 2.0} if name == "absorption" else {}),
                            **({"warm_min": 0} if name == "cvd_div" else {})})
        res = S.run_session(st, S.Tape("NQ", day, "NQZ3", ts, px, [1] * len(ts)),
                            features=S.Features(usable, {c: cols[c] for c in cls.FEATURES}),
                            window=S.effective_session_window(day, cls.session_window))
        assert res.skip is None
        out[day] = [t for t, _ in st.sig]
    assert max(out[D]) == hm("13:24") and max(out[half]) == hm("13:09")
    assert out[half] == [t for t in out[D] if t < hm("13:10")]


# ---- the timestamp law -----------------------------------------------------------------------------------------------
def test_the_synthetic_table_obeys_the_clock_the_engine_uses():
    """Harness check with the look-ahead helpers: at every one-minute bar close the newest visible row of a World table
    is the minute that just closed (t_utc + 60 == decision time), never the forming one."""
    w = World(5, messy=False)
    seen = []

    def fn(ctx, bar):
        seen.append((ctx.now_ns // S.NS, ctx.feat("t_utc"), ctx.feat_n()))
        with pytest.raises(S.LookAheadError):
            ctx.feat("f_delta", -1)
    st = LA.Call(fn)
    st.session_window = ("00:00", "16:10")
    assert S.run_session(st, w.tape(), features=w.features(("f_delta", "book_ok"))).skip is None
    assert len(seen) == len(w.bars) and all(t + 60 == now for now, t, _ in seen)
    assert [n for _, _, n in seen] == list(range(seen[0][2], seen[0][2] + len(seen)))        # one more row per minute


@pytest.mark.parametrize("name", sorted(FAMS))
@pytest.mark.parametrize("tf", ["1", "5"])
def test_every_value_a_decision_reads_is_usable(name, tf, monkeypatch):
    """Spy on ctx.feat / ctx.feat_window while the REAL family trades a messy day: every index is an integer >= 0, and
    every row handed back was usable at that decision (the spy re-derives it from the table's own usable_ns)."""
    cls, w = FAMS[name], world(name, 12)
    feats = w.features(cls.FEATURES)
    calls = []
    real_feat, real_win = S.Ctx.feat, S.Ctx.feat_window

    def feat(self, col, back=0, default=None):
        v = real_feat(self, col, back, default)
        calls.append(("feat", self.now_ns, col, back, v))
        return v

    def feat_window(self, col, n=None):
        v = real_win(self, col, n)
        calls.append(("win", self.now_ns, col, n, v))
        return v
    monkeypatch.setattr(S.Ctx, "feat", feat)
    monkeypatch.setattr(S.Ctx, "feat_window", feat_window)
    res = S.run_session(cls({"tf": tf}), w.tape(), features=feats)
    assert res.skip is None and len(res.trades) > 0 and len(calls) > 20
    assert {c[2] for c in calls} <= set(cls.FEATURES)
    for kind, now, col, arg, v in calls:
        assert isinstance(arg, int) and not isinstance(arg, bool) and arg >= 0
        n = int((feats.usable_ns <= now).sum())                               # rows usable at this decision
        if kind == "feat":
            assert arg == 0 and (v is None if n == 0 else v == feats.cols[col][n - 1].item())
        else:
            want = feats.cols[col][max(0, n - arg):n]
            assert len(v) == len(want) and np.array_equal(v, want, equal_nan=True)
            if col == "t_utc" and len(v):
                assert (v.max() + 60) * S.NS <= now


@pytest.mark.parametrize("name", sorted(FAMS))
@pytest.mark.parametrize("tf", ["1", "5"])
def test_rows_that_are_not_usable_yet_cannot_change_a_decision(name, tf):
    """Rewrite every row that is NOT usable at the cut (trigger-sized values, book_ok True): every signal up to the cut
    is unchanged. The rewrite does change later signals, so the comparison is able to fail."""
    cls, base = FAMS[name], world(name, 13)
    ref = signals(cls, base, {"tf": tf})
    moved = 0
    for cut in (hm("09:45"), hm("10:20"), hm("11:35"), hm("12:50")):
        w = copy.deepcopy(base)
        for i, s in enumerate(range(cut, max(base.rows) + 60, 60)):           # stamped >= cut  <=>  usable after the cut
            sg = 1.0 if i % 2 else -1.0
            w.rows[s] = {"f_delta": 5000.0 * sg, "f_sweep_buy_vol": 900.0 if sg > 0 else 0.0,
                         "f_sweep_sell_vol": 0.0 if sg > 0 else 900.0, "book_ok": True}
        got = signals(cls, w, {"tf": tf})
        assert [x for x in got if x[0] <= cut] == [x for x in ref if x[0] <= cut]
        moved += got != ref
    assert moved > 0


@pytest.mark.parametrize("name", sorted(FAMS))
@pytest.mark.parametrize("shift_s", [-3600, -120, -60, 60, 120, 3600])
def test_a_shifted_table_never_signals(name, shift_s):
    """A table usable a minute EARLY would show the forming minute at each close (look-ahead); a minute late, a stale
    one. The freshness guard (newest row = the minute that just ended) refuses both: not one signal."""
    cls, w = FAMS[name], world(name, 14, messy=False)
    assert len(signals(cls, w, {"tf": "1"})) > 0
    for tf in ("1", "5"):
        assert signals(cls, w, {"tf": tf}, feats=w.features(cls.FEATURES, shift_s=shift_s)) == []
    assert signals(cls, w, {"tf": "1"}, feats=w.features(cls.FEATURES, shift_s=-1)) == signals(cls, w, {"tf": "1"})


# ---- the real class: orders ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(FAMS))
@pytest.mark.parametrize("tf", ["1", "5"])
def test_trades_are_the_oracle_signals_one_position_at_a_time(name, tf):
    """The family as registered (market orders) on days where every minute prints: each trade enters on the first print
    after an oracle signal with its side; walking the oracle's signals with 'flat, < 3 entries this session' gives
    exactly the trades; market entries only, one direction, a stop and a target with stop <= 5 x target."""
    cls, n_tr = FAMS[name], 0
    for seed in (61, 62, 63):
        w = world(name, seed, messy=False)
        res = S.run_session(cls({"tf": tf}), w.tape(), features=w.features(cls.FEATURES))
        assert res.skip is None and res.both_sides is False
        want, _ = oracle(name, w, int(tf))
        took, per_sess, open_until = [], {}, -1
        exits = {t["entry_ns"]: t["exit_ns"] for t in res.trades}
        for T, side in want:
            sid = next(k for k, (a, b) in SESS.items() if a < T <= b)
            if MID_NS + T * S.NS <= open_until or per_sess.get(sid, 0) >= 3 or T not in w.bars:
                continue                                                      # (T not in bars: the tape ends, the order never fills)
            fill = MID_NS + (T + 1) * S.NS                                    # the first print after T + 85 ms
            took.append((fill, side))
            per_sess[sid] = per_sess.get(sid, 0) + 1
            open_until = exits.get(fill, -1)
        assert sorted((t["entry_ns"], t["side"]) for t in res.trades) == took
        for t in res.trades:
            assert t["order_price"] is None and t["oco"] is False and t["both_sides"] is False and t["qty"] == 1
            sd = 1 if t["side"] == "long" else -1
            stop, tgt = (t["entry_price"] - t["sl"]) * sd, (t["tp"] - t["entry_price"]) * sd
            assert stop >= 2 * TICK and tgt > 0 and stop <= 5 * tgt and abs(tgt - 2 * stop) <= 2 * TICK
        tc = apex300.trade_checks(res.trades)                                 # the Apex gate's own per-row evidence (counts only)
        assert tc["n"] == tc["stamped"] == len(res.trades)
        assert tc["max_stop_over_target"] is None or tc["max_stop_over_target"] <= 1.0      # stop = 0.5 x target (+ tick rounding)
        assert not any(tc[k] for k in ("no_stop", "no_target", "stop_gt_5x", "opposite_overlap", "both_side_orders",
                                       "resting_entries", "both_side_sessions"))
        n_tr += len(res.trades)
    assert n_tr > 0


@pytest.mark.parametrize("name", sorted(FAMS))
def test_dir_input_restricts_the_side(name):
    cls, w = FAMS[name], world(name, 61, messy=False)
    for d in ("long", "short"):
        res = S.run_session(cls({"tf": "1", "dir": d}), w.tape(), features=w.features(cls.FEATURES))
        assert res.skip is None and {t["side"] for t in res.trades} <= {d}


# ---- real in-sample rows: equality only ------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(FAMS))
def test_real_days_future_rows_do_not_change_earlier_trades(name):
    """Two in-sample days through the real loader: with every feature row that is not usable at 11:00 ET rewritten, the
    trades entered before 11:00 are identical field for field. Only equality is asserted; no P&L is looked at."""
    cls = FAMS[name]
    if not all((S.CACHE / f"l2feat_NQ_{y}.parquet").exists() for y in (2023, 2024)):
        pytest.skip("data-layer cache not built")
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    loader = S.L2Features(cls.FEATURES)
    n = 0
    for iso, tf in (("2023-08-09", "1"), ("2024-04-10", "5")):
        try:
            tape = S.load_tape(iso)
        except FileNotFoundError:
            pytest.skip("tape not available")
        if tape is None:
            pytest.skip("tape not available")
        f = loader(tape.date)
        cut = S.et_ns(tape.date, "11:00")
        late = f.usable_ns > cut
        cols = {k: v.copy() for k, v in f.cols.items()}
        for k in cols:
            if k.startswith("f_"):
                cols[k][late] = 50000.0 * np.where(np.arange(late.sum()) % 2, 1.0, -1.0) if k == "f_delta" else 9000.0
        cols["book_ok"][late] = True
        win = S.effective_session_window(tape.date, cls.session_window)
        a = S.run_session(cls({"tf": tf}), tape, features=f, window=win)
        b = S.run_session(cls({"tf": tf}), tape, features=S.Features(f.usable_ns, cols), window=win)
        assert a.skip is None and b.skip is None
        early = [t for t in a.trades if t["entry_ns"] <= cut]
        assert early == [t for t in b.trades if t["entry_ns"] <= cut]
        n += len(early)
        t = f.cols["t_utc"]
        assert np.array_equal((t + 60) * S.NS, f.usable_ns)                    # the family's freshness test is the table's law
    assert n >= 0
