"""families/book.py -- B1 bimb_follow, B2 bimb_fade, B3 thin_side (definitions: FAMILIES.md "Book families").

What is proven here, on synthetic tapes + synthetic feature tables (and two real in-sample days, signals only):
  * the trigger fires EXACTLY when defined: every decision instant of a session is compared with an oracle that recomputes
    the definition from the raw table by row STAMP, without ctx (SPY classes record the signal instead of trading, so the
    strategy stays flat and every tf close of the session is a decision);
  * never on data that is not usable yet: a row is acted on one minute after its stamp and not before, rewriting every row and
    print after a cut time changes no earlier decision, no row beyond the newest usable one is ever touched, and a table that
    leaks the forming minute (or lags) gives no signal at all (helpers of tests/test_l2sim_lookahead.py);
  * roll / NaN / book_ok False rows, a short or flat history, a stale row: no signal;
  * no entry in the last 5 minutes of a session, none before the first close of a session, at most max_tr per session;
  * the real classes trade what the spy signals: market entry on the first print after the decision, stop and target on,
    one direction (the simulator's own stamps), stop <= 5 x target from the fill;
  * the pre-registered defaults are the SPEC's, and the registry's 1-vs-8-worker test covers every name.
No P&L is asserted, printed or looked at anywhere."""
import datetime as dt
import inspect

import numpy as np
import pytest

import apex300
import families
import l2sim as S
import test_l2sim_lookahead as LA
from families import book as B

D = dt.date(2024, 3, 5)                 # a plain in-sample Tuesday (the tapes and tables below are synthetic)
MID = S.et_ns(D, "00:00")
TICK = 0.25


def ns(hhmm: str) -> int:
    return S.et_ns(D, hhmm)


def hm(t: int) -> str:
    s = (t - MID) // S.NS
    return "%02d:%02d" % (s // 3600, s % 3600 // 60)


# ---- synthetic tape + feature table ------------------------------------------------------------------------------------
def make_tape(start="08:30", end="11:10", seed=3, skip=(), bump=None):
    """Four prints a minute (:05 :20 :35 :50) on a seeded walk of -2..+2 ticks; `skip` = minutes (HH:MM) without a print;
    bump=(t_ns, pts): every print at/after t moved by pts."""
    rng = np.random.default_rng(seed)
    mins = np.arange(ns(start), ns(end), S.MIN_NS)
    px = 18000.0 + TICK * np.cumsum(rng.integers(-2, 3, 4 * len(mins)))
    ts = (mins[:, None] + np.array([5, 20, 35, 50]) * S.NS).ravel()
    keep = ~np.isin(ts // S.MIN_NS * S.MIN_NS, [ns(s) for s in skip])
    ts, px = ts[keep], px[keep]
    if bump:
        px = np.where(ts >= bump[0], px + bump[1], px)
    return S.Tape("NQ", D, "NQH4", ts, px, np.ones(len(ts), np.int64))


def table(start="07:00", end="11:10", seed=1, quiet=False):
    """One row per minute stamped [start, end). quiet: imbalance alternating +-0.01 (|z| = 1 against itself: never a trigger)
    and both depth ratios at 1.00. Otherwise fat-tailed imbalances with NaN and book_ok False holes, depth ratios on a 0.05 grid
    (`rb100` / `ra100` = the ratios in hundredths, for a tie-exact oracle)."""
    stamp = np.arange(ns(start), ns(end), S.MIN_NS)
    n = len(stamp)
    rng = np.random.default_rng(seed)
    tb = {"stamp": stamp, "t_utc": stamp // S.NS, "book_ok": np.ones(n, bool)}
    if quiet:
        alt = np.where(np.arange(n) % 2 == 0, 0.01, -0.01)
        tb["imb10"], tb["imb3"] = alt.astype(np.float32), (2 * alt).astype(np.float32)
        tb["rb100"] = tb["ra100"] = np.full(n, 100)
    else:
        for c in ("imb10", "imb3"):
            v = np.clip(0.1 * rng.standard_t(3, n), -0.95, 0.95)
            v[rng.random(n) < 0.04] = np.nan
            tb[c] = v.astype(np.float32)
        tb["book_ok"] = rng.random(n) > 0.04                   # flag off on rows that still carry a finite value
        tb["rb100"] = rng.choice([40, 55, 60, 65, 85, 90, 95, 100, 110, 130], n)
        tb["ra100"] = rng.choice([40, 55, 60, 65, 85, 90, 95, 100, 110, 130], n)
    return rel(tb)


def rel(tb):
    """(Re)derive the stored columns from the hundredths: ratio - 1 in float32, as the data layer stores them."""
    for c, r in (("bid10_rel15", "rb100"), ("ask10_rel15", "ra100")):
        v = (np.asarray(tb[r], np.float64) / 100.0 - 1.0).astype(np.float32)
        tb[c] = np.where(np.asarray(tb[r]) < 0, np.float32("nan"), v)          # a negative entry = a missing value
    return tb


COLS = ("imb10", "imb3", "bid10_rel15", "ask10_rel15", "book_ok", "t_utc")


def feats(tb, shift_s=0, drop=()):
    """The table as the engine sees it: row stamped M usable at M + 60 s (+ shift_s: a broken adapter). drop = stamps removed."""
    keep = ~np.isin(tb["stamp"], [ns(s) for s in drop])
    return S.Features(tb["stamp"][keep] + (60 + shift_s) * S.NS, {c: tb[c][keep] for c in COLS})


# ---- the oracle: the definitions of FAMILIES.md recomputed from the table by STAMP, without ctx --------------------------
def z_oracle(tb, col, T):
    m = T - S.MIN_NS                                             # the minute that just ended at the decision T
    i = np.flatnonzero(tb["stamp"] == m)
    if len(i) == 0 or not tb["book_ok"][i[0]] or not np.isfinite(tb[col][i[0]]):
        return None
    hist = (tb["stamp"] >= m - 60 * S.MIN_NS) & (tb["stamp"] < m) & tb["book_ok"] & np.isfinite(tb[col])
    h = tb[col][hist].astype(np.float64)
    if len(h) < 30 or h.std() == 0:
        return None
    return (float(tb[col][i[0]]) - h.mean()) / h.std()


def bimb_oracle(tb, col, T, sign, k=2.0):
    z = z_oracle(tb, col, T)
    if z is None or abs(z) < k:
        return None
    return "long" if z * sign > 0 else "short"


def thin_oracle(tb, T, thin=60, hold=90):
    i = np.flatnonzero(tb["stamp"] == T - S.MIN_NS)
    if len(i) == 0 or not tb["book_ok"][i[0]]:
        return None
    rb, ra = int(tb["rb100"][i[0]]), int(tb["ra100"][i[0]])
    if rb < 0 or ra < 0:
        return None
    if rb <= thin and ra >= hold:
        return "short"                                           # bid side thin -> toward it = down
    if ra <= thin and rb >= hold:
        return "long"
    return None


def decisions(tf, sess=("nyam",), last="11:10"):
    """Every instant the Template lets a flat strategy decide: tf closes after the session start, before session end - 5 min."""
    out = []
    for s in sess:
        a, b = S.SESS[s]
        out += [MID + x * S.NS for x in range(a + tf * 60, b - 300, tf * 60)]
    return [t for t in out if t <= ns(last)]


# ---- spies: the family's own fam_signal, the entry recorded instead of sent (the strategy stays flat) --------------------
class Spy:
    def _mkt(self, ctx, side, **kw):
        self.sig.append((ctx.now_ns, side))

    def fam_signal(self, ctx):
        self.calls.append(ctx.now_ns)
        super().fam_signal(ctx)


class SpyFollow(Spy, B.BimbFollow):
    pass


class SpyFade(Spy, B.BimbFade):
    pass


class SpyThin(Spy, B.ThinSide):
    pass


def spy(cls, f, params, tape=None, window=None):
    st = cls(params)
    st.sig, st.calls = [], []
    res = S.run_session(st, tape or make_tape(), features=f, window=window)
    assert res.skip is None and res.trades == []
    return st


def at(tb, fn, drop=()):
    """fn(ctx) at every 1-minute bar close 09:31 .. 09:59 through the look-ahead tests' probe strategy -> {HH:MM: value}."""
    ts = [ns("09:30") + (60 * i + 1) * S.NS for i in range(30)]
    tape = S.Tape("NQ", D, "NQH4", ts, [100.0] * len(ts), [1] * len(ts))
    out = {}
    assert S.run_session(LA.Call(lambda ctx, bar: out.__setitem__(hm(ctx.now_ns), fn(ctx))), tape, features=feats(tb, drop=drop)).skip is None
    assert len(out) == 29
    return out


# ---- 1. the z-score is the definition ----------------------------------------------------------------------------------
@pytest.mark.parametrize("col", ["imb10", "imb3"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_z_equals_the_definition_at_every_decision(col, seed):
    tb = table(seed=seed)
    got = at(tb, lambda ctx: B.imb_z(ctx, col))
    some = 0
    for t, z in got.items():
        want = z_oracle(tb, col, ns(t))
        assert (z is None) == (want is None), (t, z, want)
        if z is not None:
            assert z == pytest.approx(want, rel=1e-12, abs=1e-12)
            some += 1
    assert some >= 20


def edit(tb, **cols):
    out = {k: v.copy() for k, v in tb.items()}
    for c, pairs in cols.items():
        for stamp, v in pairs:
            out[c][np.isin(out["stamp"], [ns(s) for s in ([stamp] if isinstance(stamp, str) else stamp)])] = v
    return rel(out)


def stamps(a, b):
    """HH:MM of every minute in [a, b)."""
    return [hm(t) for t in range(ns(a), ns(b), S.MIN_NS)]


def test_z_no_signal_cases():
    """Decision 09:50: the newest usable row is stamped 09:49, its history the rows stamped 08:49 .. 09:48."""
    q = table(quiet=True)
    z = lambda tb, **kw: at(tb, lambda ctx: B.imb_z(ctx, "imb10"), **kw)["09:50"]
    assert abs(z(q)) == pytest.approx(1.0, rel=1e-5)             # +-0.01 against a +-0.01 history: mean 0, std 0.01
    # the current minute is not part of its own mean / std: 0.025 against that history is z = 2.5 (2.44 if it were inside)
    assert z(edit(q, imb10=[("09:49", 0.025)])) == pytest.approx(2.5, rel=1e-5)
    assert z(edit(q, imb10=[("09:49", -0.025)])) == pytest.approx(-2.5, rel=1e-5)
    # a row older than the 60 minutes (08:48) and the rows not usable yet (09:50 on) carry no weight
    wild = edit(q, imb10=[("08:48", 0.9), (stamps("09:50", "10:30"), -0.9)])
    assert z(wild) == z(q)
    # NaN newest row / book_ok False newest row (value still finite): no signal
    assert z(edit(q, imb10=[("09:49", np.nan)])) is None
    assert z(edit(q, book_ok=[("09:49", False)])) is None
    # 30 valid history values are enough, 29 are not -- by NaN and by the flag alike
    assert z(edit(q, imb10=[(stamps("08:49", "09:19"), np.nan)])) is not None            # 30 left: 09:19 .. 09:48
    assert z(edit(q, imb10=[(stamps("08:49", "09:20"), np.nan)])) is None                # 29 left
    assert z(edit(q, book_ok=[(stamps("08:49", "09:19"), False)])) is not None
    assert z(edit(q, book_ok=[(stamps("08:49", "09:20"), False)])) is None
    # a flat history has no z
    assert z(edit(q, imb10=[(stamps("08:49", "09:49"), 0.05)])) is None
    # a stale newest row (the 09:49 row is missing: the newest usable one is 09:48) is never used
    assert z(q, drop=["09:49"]) is None
    # the window is 60 MINUTES, not 60 rows: with 09:05 .. 09:44 missing, 60 older rows exist but only 20 are inside the hour
    assert z(q, drop=stamps("09:05", "09:45")) is None
    assert z(q, drop=stamps("09:05", "09:35")) is not None                                # 30 inside the hour
    # no usable row at all / too few rows
    assert at(table(start="09:45", quiet=True), lambda ctx: B.imb_z(ctx, "imb10"))["09:50"] is None


# ---- 2. B1 / B2 fire exactly when defined --------------------------------------------------------------------------------
@pytest.mark.parametrize("tf", [1, 5])
@pytest.mark.parametrize("n_lv", ["10", "3"])
@pytest.mark.parametrize("cls,sign", [(SpyFollow, 1), (SpyFade, -1)])
def test_bimb_signals_are_exactly_the_definition(cls, sign, n_lv, tf):
    both = set()
    for seed in (1, 2, 3, 4):
        tb = table(seed=seed)
        st = spy(cls, feats(tb), {"tf": str(tf), "sess": "nyam", "n_lv": n_lv})
        dec = decisions(tf)
        assert st.calls == dec                                   # every tf close of the session, none in its last 5 minutes
        want = [(t, bimb_oracle(tb, "imb" + n_lv, t, sign)) for t in dec]
        assert st.sig == [(t, s) for t, s in want if s], (seed, [(hm(t), s) for t, s in st.sig])
        both |= {s for _, s in st.sig}
    assert both == {"long", "short"}


def test_follow_and_fade_take_opposite_sides_of_the_same_trigger():
    tb = table(seed=4)                                           # a synthetic table with triggers of both signs in nyam
    p = {"tf": "1", "sess": "nyam"}
    a, b = spy(SpyFollow, feats(tb), p).sig, spy(SpyFade, feats(tb), p).sig
    assert len(a) >= 3 and [t for t, _ in a] == [t for t, _ in b] and all(x[1] != y[1] for x, y in zip(a, b))
    # k is the threshold: a higher k keeps a subset, k = 0.5 a superset
    hi, lo = spy(SpyFollow, feats(tb), {**p, "k": 3.0}).sig, spy(SpyFollow, feats(tb), {**p, "k": 0.5}).sig
    assert set(hi) < set(a) < set(lo)
    # dir is honoured by the real class (Template.allowed)
    for d in ("long", "short"):
        tr = S.run_session(B.BimbFollow({**p, "dir": d, "max_tr": 20}), make_tape(), features=feats(tb)).trades
        assert tr and {t["side"] for t in tr} == {d}


# ---- 3. B3 definition ----------------------------------------------------------------------------------------------------
def test_thin_side_thresholds_are_on_the_ratio_and_ties_are_inside():
    q = table(quiet=True)

    def side(rb, ra, **kw):
        return at(edit(q, rb100=[("09:49", rb)], ra100=[("09:49", ra)], **kw), lambda ctx: B.thin_side(ctx, 0.60, 0.90))["09:50"]
    assert side(100, 100) is None
    assert side(60, 90) == "bid" and side(90, 60) == "ask"       # the float32 ties 0.60 / 0.90 are inside
    assert side(59, 130) == "bid" and side(130, 40) == "ask"
    assert side(61, 100) is None and side(100, 61) is None       # not thin enough
    assert side(60, 89) is None and side(89, 60) is None         # the other side did not hold
    assert side(40, 40) is None and side(60, 60) is None         # both sides thin: no direction
    assert side(-1, 100) is None and side(60, -1) is None        # a missing value (NaN)
    assert side(60, 90, book_ok=[("09:49", False)]) is None      # masked row
    assert at(edit(q, rb100=[("09:49", 60)]), lambda ctx: B.thin_side(ctx, 0.60, 0.90), drop=["09:49"])["09:50"] is None   # stale
    assert at(edit(q, rb100=[("09:49", 60)]), lambda ctx: B.thin_side(ctx, 0.60, 0.90))["09:51"] is None     # one minute only
    # the stored values really are the awkward float32 ones
    assert float(np.float32(0.9 - 1.0)) < -0.1 and float(np.float32(0.6 - 1.0)) < -0.4


@pytest.mark.parametrize("tf", [1, 5])
def test_thin_side_signals_are_exactly_the_definition(tf):
    both = set()
    for seed in (1, 2, 3, 4):
        tb = table(seed=seed)
        st = spy(SpyThin, feats(tb), {"tf": str(tf), "sess": "nyam"})
        dec = decisions(tf)
        assert st.calls == dec
        want = [(t, thin_oracle(tb, t)) for t in dec]
        assert st.sig == [(t, s) for t, s in want if s], seed
        both |= {s for _, s in st.sig}
    assert both == {"long", "short"}
    tb = table(seed=1)                                           # the two inputs are the two thresholds
    st = spy(SpyThin, feats(tb), {"tf": "1", "sess": "nyam", "thin": 0.55, "hold": 0.95})
    assert st.sig == [(t, s) for t in decisions(1) if (s := thin_oracle(tb, t, 55, 95))] and st.sig


# ---- 4. never on data that is not usable yet -----------------------------------------------------------------------------
def spike(col_edits, tf, cls, **p):
    return spy(cls, feats(edit(table(quiet=True), **col_edits)), {"tf": str(tf), "sess": "nyam", **p}).sig


def test_a_row_is_acted_on_one_minute_after_its_stamp_and_not_before():
    """A lone spike stamped 10:07 (the book 59 s into 10:07) is usable at 10:08:00: that is the one decision that fires."""
    up, thin = {"imb10": [("10:07", 0.9)]}, {"rb100": [("10:07", 50)]}
    assert spike(up, 1, SpyFollow) == [(ns("10:08"), "long")]
    assert spike(up, 1, SpyFade) == [(ns("10:08"), "short")]
    assert spike({"imb10": [("10:07", -0.9)]}, 1, SpyFollow) == [(ns("10:08"), "short")]
    assert spike(thin, 1, SpyThin) == [(ns("10:08"), "short")]
    assert spike({"ra100": [("10:07", 50)]}, 1, SpyThin) == [(ns("10:08"), "long")]
    assert spike({"imb3": [("10:07", 0.9)]}, 1, SpyFollow, n_lv="3") == [(ns("10:08"), "long")]
    assert spike({"imb3": [("10:07", 0.9)]}, 1, SpyFollow, n_lv="10") == []          # N = 10 reads imb10 only
    # tf 5 looks at the newest ONE-minute row at its own close: 10:09's row at 10:10, never 10:07's
    assert spike(up, 5, SpyFollow) == [] and spike(thin, 5, SpyThin) == []
    assert spike({"imb10": [("10:09", 0.9)]}, 5, SpyFollow) == [(ns("10:10"), "long")]
    assert spike({"rb100": [("10:09", 50)]}, 5, SpyThin) == [(ns("10:10"), "short")]


@pytest.mark.parametrize("cls", [SpyFollow, SpyFade, SpyThin])
@pytest.mark.parametrize("shift_s", [-3600, -60, -1, 1, 60, 3600])
def test_a_table_on_the_wrong_clock_gives_no_signal(cls, shift_s):
    """The look-ahead tests' constant shifts, applied to the adapter under the family: a table that shows the forming minute
    (a minute or more early) or lags (late) fails the freshness guard on every row -- the family cannot trade on such a leak.
    One second early changes nothing at a minute boundary (the forming minute's row is still not visible there): the family
    decides only at bar closes, so its signals are the unshifted ones."""
    tb = table(seed=2)
    base = spy(cls, feats(tb), {"tf": "1", "sess": "nyam"}).sig
    assert len(base) >= 3
    st = spy(cls, feats(tb, shift_s=shift_s), {"tf": "1", "sess": "nyam"})
    assert st.sig == (base if shift_s == -1 else []) and st.calls == decisions(1)


@pytest.mark.parametrize("cls", [SpyFollow, SpyFade, SpyThin])
@pytest.mark.parametrize("tf", [1, 5])
def test_rewriting_everything_after_a_cut_changes_no_earlier_decision(cls, tf):
    tb = table(seed=3)
    p = {"tf": str(tf), "sess": "nyam"}
    base = spy(cls, feats(tb), p).sig
    assert len(base) >= 2
    for cut in ("09:40", "10:00", "10:08", "10:25", "10:50"):
        c = ns(cut)
        fut = tb["stamp"] >= c                                   # rows usable only AFTER the decision at `cut`
        poison = {k: v.copy() for k, v in tb.items()}
        flip = np.where(np.arange(fut.sum()) % 2 == 0, 0.9, -0.9)
        poison["imb10"][fut], poison["imb3"][fut] = flip, -flip
        poison["rb100"][fut], poison["ra100"][fut], poison["book_ok"][fut] = 40, 130, True
        got = spy(cls, feats(rel(poison)), p, tape=make_tape(bump=(c, 50.0))).sig
        assert [x for x in got if x[0] <= c] == [x for x in base if x[0] <= c], cut
        assert got != base or cut == "10:50"                     # ... while the rewritten future does change the later ones


class Rec:
    """A feature column that remembers the highest row index anything read from it."""

    def __init__(self, a):
        self.a, self.top = a, -1

    def __len__(self):
        return len(self.a)

    def __getitem__(self, k):
        stop = (len(self.a) if k.stop is None else k.stop) if isinstance(k, slice) else int(k) + 1
        self.top = max(self.top, stop - 1)
        return self.a[k]


@pytest.mark.parametrize("cls", [SpyFollow, SpyThin])
def test_no_row_beyond_the_newest_usable_one_is_ever_read(cls):
    f = feats(table(seed=1))
    f.cols = {k: Rec(v) for k, v in f.cols.items()}
    tops = []

    class Watch(cls):
        def fam_signal(self, ctx):
            for r in f.cols.values():
                r.top = -1
            super().fam_signal(ctx)
            tops.append((ctx.now_ns, max(r.top for r in f.cols.values())))
    spy(Watch, f, {"tf": "1", "sess": "nyam"})
    assert len(tops) == len(decisions(1))
    for now, top in tops:
        assert top >= 0 and f.usable_ns[top] == now              # the newest row read = the minute that just ended, never later
    src = inspect.getsource(B)                                   # and there is no other way in: ctx.feat / ctx.feat_window only
    assert "l2data" not in src.split('"""', 2)[2] and "._feat" not in src and "import l2sim as S" in src
    assert S.Template.session_independent and all(c.session_independent for c in (B.BimbFollow, B.BimbFade, B.ThinSide))


# ---- 5. session rules: first close, last 5 minutes, max_tr ---------------------------------------------------------------
ALWAYS = lambda: edit(table(quiet=True), rb100=[(stamps("07:00", "11:10"), 50)])        # bid side thin on every row


@pytest.mark.parametrize("tf", [1, 5])
def test_no_signal_in_the_last_five_minutes_or_before_the_first_close_of_a_session(tf):
    st = spy(SpyThin, feats(ALWAYS()), {"tf": str(tf), "sess": "all"})
    want = decisions(tf, ("nyam", "mid"))                        # the tape runs 08:30 .. 11:10: nyam, then the start of mid
    assert st.sig == [(t, "short") for t in want] and st.calls == want
    got = [hm(t) for t, _ in st.sig]
    assert got[0] == ("09:31" if tf == 1 else "09:35")           # london ended 08:25; nothing before nyam's first close
    last_nyam = max(g for g in got if g < "11:00")
    assert last_nyam == ("10:54" if tf == 1 else "10:50")        # 10:55 .. 11:00 are the last five minutes
    assert min(g for g in got if g >= "11:00") == ("11:01" if tf == 1 else "11:05")


def test_a_minute_without_prints_delays_the_tf_close_but_never_reads_ahead():
    """tf 5, no print in 10:09: the Template closes the 10:05 bar at the next minute close that has prints (10:11); the row
    used there is 10:10's (the newest then), and the skipped instant fires nothing."""
    tb = edit(table(quiet=True), rb100=[("10:10", 50)])
    st = spy(SpyThin, feats(tb), {"tf": "5", "sess": "nyam"}, tape=make_tape(skip=["10:09"]))
    assert ns("10:10") not in st.calls and ns("10:11") in st.calls and st.sig == [(ns("10:11"), "short")]
    st = spy(SpyThin, feats(edit(table(quiet=True), rb100=[("10:08", 50), ("10:09", 50)])), {"tf": "5", "sess": "nyam"},
             tape=make_tape(skip=["10:09"]))
    assert st.sig == []                                          # 10:09's row is no longer the newest at 10:11


def test_real_class_respects_max_tr_one_position_and_the_last_five_minutes():
    p = {"tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 1.0}              # a 1-point stop: trades end fast
    f = feats(ALWAYS())
    three = S.run_session(B.ThinSide(p), make_tape(), features=f).trades
    assert len(three) == 3                                       # max_tr 3 per session (Template default = SPEC)
    many = S.run_session(B.ThinSide({**p, "max_tr": 20}), make_tape(), features=f).trades
    assert len(many) > 3 and {t["side"] for t in many} == {"short"}
    assert all(ns("09:31") < t["entry_ns"] < ns("10:55") for t in many)                # no entry in the last 5 minutes
    by_entry = sorted(many, key=lambda t: t["entry_ns"])
    assert all(a["exit_ns"] <= b["entry_ns"] for a, b in zip(by_entry, by_entry[1:]))  # one position at a time
    assert all(t["exit_ns"] <= ns("11:00") + 5 * S.NS for t in many)                   # flat at the session end (first print after)


# ---- 6. the real classes trade what the spies signal; Apex evidence ----------------------------------------------------
@pytest.mark.parametrize("cls,edits,side", [
    (B.BimbFollow, {"imb10": [("10:07", 0.9)]}, "long"), (B.BimbFade, {"imb10": [("10:07", 0.9)]}, "short"),
    (B.BimbFollow, {"imb10": [("10:07", -0.9)]}, "short"), (B.BimbFade, {"imb10": [("10:07", -0.9)]}, "long"),
    (B.ThinSide, {"rb100": [("10:07", 60)], "ra100": [("10:07", 90)]}, "short"),
    (B.ThinSide, {"ra100": [("10:07", 60)], "rb100": [("10:07", 90)]}, "long")])
def test_entry_is_a_market_order_on_the_first_print_after_the_decision_with_stop_and_target(cls, edits, side):
    tape = make_tape()
    res = S.run_session(cls({"tf": "1", "sess": "nyam"}), tape, features=feats(edit(table(quiet=True), **edits)))
    assert res.skip is None and len(res.trades) == 1 and res.both_sides is False
    t = res.trades[0]
    sd = 1 if side == "long" else -1
    k = int(np.searchsorted(tape.ts, ns("10:08") + 85 * 1_000_000))          # the first print once the order is live (85 ms)
    assert t["side"] == side and t["entry_ns"] == tape.ts[k] == ns("10:08") + 5 * S.NS
    assert t["entry_price"] == tape.px[k] + sd * TICK and t["order_price"] is None       # market + 1 tick slip
    stop, tgt = sd * (t["entry_price"] - t["sl"]), sd * (t["tp"] - t["entry_price"])
    assert stop >= 2 * TICK and abs(tgt - 2.0 * stop) <= 2 * TICK                       # stop 1.5 ATR, target 2 R, from the fill
    assert stop <= 5 * tgt and t["oco"] is False and t["both_sides"] is False


def test_apex_evidence_one_direction_and_stop_within_five_targets():
    rows = []
    for cls in (B.BimbFollow, B.BimbFade, B.ThinSide):
        for tf in ("1", "5"):
            for seed in (1, 2, 3):
                res = S.run_session(cls({"tf": tf, "sess": "all"}), make_tape(seed=seed), features=feats(table(seed=seed)))
                assert res.skip is None and res.both_sides is False
                rows += res.trades
    c = apex300.trade_checks(rows)
    assert c["n"] == len(rows) >= 20 and c["stamped"] == c["n"]
    assert c["no_stop"] == c["no_target"] == c["stop_gt_5x"] == c["both_side_orders"] == c["resting_entries"] == 0
    assert c["max_stop_over_target"] <= 0.75                     # stop d, target 2 d (tick rounding aside)
    for name in NAMES:
        assert families.REGISTRY[name][2] is False               # the declaration the simulator's stamps agree with


# ---- 7. pre-registration pins + registry ---------------------------------------------------------------------------------
NAMES = ("bimb_follow", "bimb_follow_n3", "bimb_fade", "bimb_fade_n3", "thin_side")


def test_registered_defaults_are_the_pre_registered_ones():
    assert not any(k == "book" or "book.py" in v for k, v in families.ERRORS.items()), families.ERRORS
    assert {n for n, m in families.MODULE_OF.items() if m == "book"} == set(NAMES)
    common = {"sess": "all", "dir": "both", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0, "trail_atr": 0.0, "exit_bars": 0,
              "max_tr": 3, "f_trend": "off", "f_vwap": "off", "f_depth": "off", "f_book": "off", "x_book": "off", "f_thin": "off", "hold_to": "session"}
    want = {"bimb_follow": (B.BimbFollow, {"k": 2.0, "n_lv": "10"}), "bimb_follow_n3": (B.BimbFollow, {"k": 2.0, "n_lv": "3"}),
            "bimb_fade": (B.BimbFade, {"k": 2.0, "n_lv": "10"}), "bimb_fade_n3": (B.BimbFade, {"k": 2.0, "n_lv": "3"}),
            "thin_side": (B.ThinSide, {"thin": 0.60, "hold": 0.90})}
    for name, (cls, own) in want.items():
        got_cls, inputs, both, notes = families.REGISTRY[name]
        assert got_cls is cls and both is False and families.check_entry(name, families.REGISTRY[name]) == []
        assert cls.SCREEN_TFS == ("1", "5") and getattr(cls, "SCREEN_RUN", {}) == {}
        for tf in cls.SCREEN_TFS:
            assert cls(families.screen_inputs(name, tf)).p == {**common, **own, "tf": tf}
    assert (B.Z_WIN, B.Z_MIN, B.EPS) == (60, 30, 1e-6) and B.BimbFollow.SIGN == 1 and B.BimbFade.SIGN == -1
    assert B.BimbFollow.FEATURES == ("imb10", "imb3", "book_ok", "t_utc")
    assert B.ThinSide.FEATURES == ("bid10_rel15", "ask10_rel15", "book_ok", "t_utc")
    with pytest.raises(ValueError):
        B.ThinSide({"thin": 0.9})                                # thin and hold cannot cross
    with pytest.raises(ValueError):
        B.BimbFollow({"n_lv": "5"})


def test_the_registry_worker_parity_test_covers_every_book_family():
    """The 1-vs-8-worker identity test is tests/test_families.py (every registered name x screen tf); it must list ours."""
    import test_families as TF
    assert {(n, tf) for n in NAMES for tf in ("1", "5")} <= set(TF.CASES)
    import score
    for cls in (B.BimbFollow, B.ThinSide):                       # the C2 null shuffles the book features, nothing else
        c2 = score.C2Features(cls.FEATURES, seed=1)
        assert set(c2.shuffle_cols) == set(cls.FEATURES) - {"book_ok", "t_utc"}


# ---- 8. two real in-sample days: signals only (the spy never trades) -------------------------------------------------------
def real_day(iso, cls, params):
    try:
        tape = S.load_tape(iso)
        f = S.L2Features(cls.FEATURES)(tape.date)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    if tape is None or f is None:
        pytest.skip("tape / feature cache not available")
    st = spy(cls, f, params, tape=tape, window=S.effective_session_window(tape.date, cls.session_window))
    tb = {c: f.cols[c] for c in f.cols}
    tb["stamp"] = f.cols["t_utc"] * S.NS
    assert (f.usable_ns == tb["stamp"] + S.MIN_NS).all()
    return st, tb, S.et_ns(tape.date, "00:00")


@pytest.mark.parametrize("tf", ["1", "5"])
def test_real_day_signals_match_the_definition_at_every_decision(tf):
    st, tb, mid = real_day("2024-03-05", SpyFollow, {"tf": tf, "sess": "all"})
    assert len(st.calls) > (800 if tf == "1" else 150)
    for t in st.calls:                                           # every decision sits inside a session, before its last 5 minutes
        s = S._sid_at((t - mid) // S.NS - 1)
        assert s is not None and (t - mid) // S.NS < S.SESS[s][1] - 300 and t % S.MIN_NS == 0
    want = [(t, bimb_oracle(tb, "imb10", t, 1)) for t in st.calls]
    assert st.sig == [(t, s) for t, s in want if s] and len(st.sig) >= 1
    st3, tb3, _ = real_day("2024-03-05", SpyThin, {"tf": tf, "sess": "all"})
    for c, r in (("bid10_rel15", "rb100"), ("ask10_rel15", "ra100")):        # the oracle's hundredths, to 1e-4 of a ratio
        v = tb3[c].astype(np.float64)
        tb3[r] = np.where(np.isfinite(v), np.round((1.0 + np.nan_to_num(v)) * 1e4), -1).astype(np.int64)
    want3 = [(t, thin_oracle(tb3, t, 6000, 9000)) for t in st3.calls]
    assert st3.calls == st.calls and st3.sig == [(t, s) for t, s in want3 if s]


@pytest.mark.parametrize("cls", [SpyFollow, SpyFade, SpyThin])
def test_real_roll_day_book_masked_no_signal(cls):
    st, tb, _ = real_day("2022-06-13", cls, {"tf": "1", "sess": "all"})      # roll day: book_ok False on every row
    assert len(st.calls) > 800 and st.sig == [] and not tb["book_ok"].any()
