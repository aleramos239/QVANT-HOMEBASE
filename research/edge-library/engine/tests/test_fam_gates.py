"""Gates G1 / G2 / G3 on the approved picks (gates.py; definitions: FAMILIES.md "Gates G1 / G2 / G3").
Synthetic feature tables + synthetic trade rows prove that every gate fires exactly when defined and never reads a row that
is not usable strictly before the trade's entry (the timeline of tests/test_l2sim_lookahead.py is reused). Gates are not a
Template family and not in the registry: instead of the 1-vs-8-worker comparison the tests prove what that comparison
protects (a verdict of G1 / G2 depends on that trade's own day only; G3's cross-session state is causal and independent
of the row order). Only counts and equality are asserted on real data: no P&L is looked at. All files go to tmp_path."""
import datetime as dt
import inspect
import json
import shutil

import numpy as np
import pytest

import gates as G
import l2sim as S
import screen
import test_l2sim_lookahead as LA

NS, MIN = S.NS, S.MIN_NS
D = dt.date(2024, 3, 5)


# ------------------------------------------------------------------ synthetic helpers

def table(day, start="09:00", imb=None, depth=None, drop=()):
    """Row i is stamped `start` + i min and usable at `start` + (i + 1) min; `drop` removes rows (a gap in the table)."""
    n = len(imb if imb is not None else depth)
    keep = [i for i in range(n) if i not in set(drop)]
    usable = np.array([S.et_ns(day, start) + (i + 1) * MIN for i in keep], np.int64)
    nan = [np.nan] * n
    return S.Features(usable, {"t_utc": usable // NS - 60,
                               "imb10": np.asarray(imb if imb is not None else nan, np.float32)[keep],
                               "depth10_rel20d": np.asarray(depth if depth is not None else nan, np.float32)[keep]})


def loader(tabs):
    return lambda d: tabs.get(d)


def ms_at(day, hms, ms=0):
    return S.et_ns(day, hms) // 10 ** 6 + ms


def trade(day, hms="09:40:10", side="long", ms=0, **kw):
    sgn, px, e = S.SIDE[side], 15000.0, ms_at(day, hms, ms)
    r = {"date": day.isoformat(), "side": side, "qty": 1, "entry_price": px, "exit_price": px + sgn * 10.0, "exit_reason": "tp",
         "order_price": None, "sl": px - sgn * 20.0, "tp": px + sgn * 10.0, "gross": 200.0, "commission": 4.0, "net": 196.0,
         "mae_pts": 2.0, "mfe_pts": 10.0, "mae_usd": 40.0, "mfe_usd": 200.0, "bars": 2, "seconds": 600.0, "entry_ms": e,
         "exit_ms": e + 600_000}
    r.update(kw)
    return r


def one(gate, tab, hms="09:40:10", side="long", ms=0, params=None, day=D):
    """-> (signal, verdict) of ONE trade."""
    rows = [trade(day, hms, side, ms)]
    sig = G.signals(rows, gate, loader({day: tab}), params)
    return sig[0], G.categories(rows, gate, sig, calendar=[day.isoformat()], params=params)[0]


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------ the timestamp law

def test_features_are_reached_only_through_the_guarded_ctx_accessor():
    src = inspect.getsource(G)
    for banned in ("l2data", ".cols", "usable_ns", "._feat", "load_features", "read_parquet"):
        assert banned not in src, banned
    assert "ctx.feat(" in src and "ctx.feat_window(" in src and "l2sim.Ctx(" in src
    with pytest.raises(TypeError, match="l2sim.Features"):           # a raw table (a way around the guard) is refused
        G.signals([trade(D)], "G1", lambda d: {"imb10": [0.1]})


def test_a_row_usable_exactly_at_the_entry_is_not_seen_and_one_usable_before_it_is():
    """Row 30 (stamped 09:30) is the only thin one; it is usable from 09:31:00.000."""
    tab = table(D, depth=[0.0] * 30 + [-0.5] + [0.0] * 10)
    assert one("G2", tab, "09:31:00", ms=0) == ("mid", "skip")       # entry_ms == usable_at: strictly before fails
    assert one("G2", tab, "09:31:00", ms=1) == ("thin", "keep")
    assert one("G2", tab, "09:31:59", ms=999) == ("thin", "keep")
    assert one("G2", tab, "09:32:00", ms=0) == ("thin", "keep")      # row 31 is usable AT 09:32:00.000: not yet
    assert one("G2", tab, "09:32:00", ms=1) == ("mid", "skip")
    assert one("G2", tab, "09:30:59", ms=999) == ("mid", "skip")     # the minute still forming is never the row


def test_every_entry_time_reads_the_newest_row_usable_strictly_before_it_on_the_lookahead_timeline():
    """The timeline of tests/test_l2sim_lookahead.synth (row i usable at 09:30 + (i + 1) min, value i) against an
    independent brute-force clock."""
    f, _ = LA.synth()
    usable = np.asarray(f.usable_ns)
    tab = S.Features(usable, {"imb10": np.asarray(f.cols["x"], np.float32), "t_utc": usable // NS - 60})
    t0 = LA.T0 // 10 ** 6
    times = sorted(set(list(range(t0, t0 + 13 * 60_000, 1_700)) + [int(u // 10 ** 6) + k for u in usable for k in (-1, 0, 1)]))
    rows = [trade(LA.D, "09:30:00", "long", ms=int(t - t0)) for t in times]
    sig = G.signals(rows, "G1", loader({LA.D: tab}), {"g1_rows": 1})
    seen = 0
    for t, s in zip(times, sig):
        ok = np.flatnonzero(usable < t * 10 ** 6)                    # strictly before entry_ms
        want = None
        if len(ok) and t * 10 ** 6 - 1 - usable[ok[-1]] < MIN:       # ... and the minute that just ended
            want = float(ok[-1])
        assert s == want, (t, s, want)
        if s is not None:
            seen += 1
            assert usable[int(s)] < t * 10 ** 6
    assert seen > 300 and sig[0] is None                             # nothing is usable at 09:30:00


@pytest.mark.parametrize("gate", G.GATES)
def test_rows_that_are_not_usable_yet_cannot_change_a_verdict(gate):
    rng = np.random.default_rng(7)
    n = 240
    imb = rng.normal(0, 0.15, n).astype(np.float32)
    dep = rng.normal(-0.1, 0.25, n).astype(np.float32)
    base = table(D, "09:00", imb=imb, depth=dep)
    for k in range(40):
        r = [trade(D, "09:00:00", "long" if k % 2 else "short", ms=int(rng.integers(62 * 60_000, 235 * 60_000)))]
        e_ns = r[0]["entry_ms"] * 10 ** 6
        fut = np.asarray(base.usable_ns) >= e_ns                      # every row not usable strictly before the entry
        assert fut.any()
        for poison in (np.nan, 9.0, -9.0):
            p = S.Features(base.usable_ns, {"t_utc": base.cols["t_utc"],
                                            "imb10": np.where(fut, poison, base.cols["imb10"]).astype(np.float32),
                                            "depth10_rel20d": np.where(fut, poison, base.cols["depth10_rel20d"]).astype(np.float32)})
            assert G.signals(r, gate, loader({D: p})) == G.signals(r, gate, loader({D: base}))
        cut = int((~fut).sum())                                       # the table simply ending there gives the same signal
        short = S.Features(base.usable_ns[:cut], {c: v[:cut] for c, v in base.cols.items()})
        assert G.signals(r, gate, loader({D: short})) == G.signals(r, gate, loader({D: base}))


def test_the_execution_guard_only_moves_the_clock_back_and_a_negative_one_is_refused():
    tab = table(D, depth=[0.0] * 30 + [-0.5] + [0.0] * 10)
    assert one("G2", tab, "09:31:00", ms=500)[0] == "thin"
    assert one("G2", tab, "09:31:00", ms=500, params={"guard_ms": 1000})[0] == "mid"     # 0.5 s after the boundary: previous row
    assert one("G2", tab, "09:31:01", ms=500, params={"guard_ms": 1000})[0] == "thin"
    for bad in (-1, -1000, 0.5, True):
        with pytest.raises(S.LookAheadError):
            G.signals([trade(D)], "G2", loader({D: tab}), {"guard_ms": bad})
    with pytest.raises(ValueError, match="unknown gate parameters"):
        G.signals([trade(D)], "G2", loader({D: tab}), {"thin": 0.9})


def test_holdout_rows_are_refused_before_any_feature_is_read():
    calls = []
    bad = trade(dt.date(2025, 1, 2))
    for gate in G.GATES:
        with pytest.raises(S.HoldoutSealed):
            G.signals([trade(D), bad], gate, lambda d: calls.append(d))
    assert calls == []
    with pytest.raises(ValueError, match="ET date"):
        G.signals([trade(D, date="2024-03-06")], "G1", lambda d: calls.append(d))
    with pytest.raises(ValueError, match="qty"):
        G.signals([trade(D, qty=2)], "G1", lambda d: calls.append(d))


# ------------------------------------------------------------------ G1

def g1_table(vals, start="09:00", pad=0.5, **kw):
    """imb10 = `pad` everywhere except rows 35..39 (stamped 09:35..09:39: the 5 newest usable rows at 09:40:10)."""
    imb = [pad] * 60
    imb[35:40] = vals
    return table(D, start, imb=imb, **kw)


def test_g1_skips_exactly_when_the_five_minute_mean_opposes_the_side():
    neg = [-0.1, -0.2, 0.05, -0.3, -0.05]
    tab = g1_table(neg, pad=0.9)                                     # rows 34 and 40 (+0.9) must not enter the mean
    want = float(np.mean(np.asarray(neg, np.float32).astype(np.float64)))
    s, v = one("G1", tab, side="long")
    assert s == want and s < 0 and v == "skip"
    assert one("G1", tab, side="short") == (want, "keep")
    pos = g1_table([0.1, 0.2, -0.05, 0.3, 0.05], pad=-0.9)
    assert one("G1", pos, side="long")[1] == "keep" and one("G1", pos, side="short")[1] == "skip"
    zero = g1_table([0.25, -0.25, 0.0, 0.5, -0.5])
    assert one("G1", zero, side="long") == (0.0, "keep") and one("G1", zero, side="short") == (0.0, "keep")
    # the newest row decides nothing alone: 4 positive minutes and one large negative one
    mixed = g1_table([0.1, 0.1, 0.1, 0.1, -0.9])
    assert one("G1", mixed, side="long")[1] == "skip" and one("G1", mixed, side="short")[1] == "keep"


def test_g1_no_signal_keeps_the_trade():
    neg = [-0.3] * 5
    assert one("G1", g1_table(neg), side="long")[1] == "skip"                              # the control: a clean veto
    for k in range(5):                                                                     # any NaN in the 5 rows
        v = list(neg)
        v[k] = np.nan
        assert one("G1", g1_table(v), side="long") == (None, "keep")
    stale = table(D, imb=[-0.3] * 39)                                                      # last row usable 09:39: 70 s old
    assert one("G1", stale, side="long") == (None, "keep")
    short = table(D, "09:36", imb=[-0.3] * 30)                                             # 4 usable rows at 09:40:10
    assert one("G1", short, side="long") == (None, "keep")
    assert one("G1", table(D, "09:35", imb=[-0.3] * 30), side="long")[1] == "skip"         # exactly 5
    gap = g1_table(neg, pad=-0.3, drop=(37,))                                              # 5 rows, not consecutive minutes
    assert one("G1", gap, side="long") == (None, "keep")
    assert G.signals([trade(D)], "G1", loader({})) == [None]                               # no table for the day
    empty = S.Features(np.empty(0, np.int64), {"imb10": np.empty(0, np.float32), "t_utc": np.empty(0, np.int64)})
    assert G.signals([trade(D)], "G1", loader({D: empty})) == [None]


# ------------------------------------------------------------------ G2

@pytest.mark.parametrize("v,regime,verdict", [(-0.5, "thin", "keep"), (-0.2, "thin", "keep"), (-0.19, "mid", "skip"), (0.0, "mid", "skip"),
                                              (0.2, "thick", "skip"), (0.7, "thick", "skip"), (np.nan, None, "skip")])
def test_g2_keeps_only_a_thin_book_at_the_entry(v, regime, verdict):
    dep = [0.5] * 60                                                 # thick before and after: only row 39 counts at 09:40:10
    dep[39] = v
    assert one("G2", table(D, depth=dep)) == (regime, verdict)
    assert regime == S.depth_regime(np.float32(v))


def test_g2_uses_the_one_shared_b6_definition_and_blocks_without_a_signal(monkeypatch):
    dep = [-0.5] * 60
    assert one("G2", table(D, depth=dep))[1] == "keep"
    assert one("G2", table(D, depth=dep[:39])) == (None, "skip")                           # stale
    assert G.categories([trade(D)], "G2", [None]) == ["skip"]
    seen = []
    monkeypatch.setattr(S, "depth_regime", lambda v: seen.append(v) or "mid")
    assert one("G2", table(D, depth=dep)) == ("mid", "skip") and len(seen) == 1 and seen[0] == pytest.approx(-0.5)


# ------------------------------------------------------------------ G3

def test_g3_z_score_is_b1s_definition():
    rng = np.random.default_rng(3)
    imb = rng.normal(0, 0.2, 100).astype(np.float32)
    x = imb.astype(np.float64)

    def z(vals, hms="10:20:30"):
        return G.signals([trade(D, hms)], "G3", loader({D: table(D, imb=vals)}))[0]

    h = x[19:79]                                                     # 10:20:30 -> newest row 79 (stamped 10:19), the 60 before it
    assert z(imb) == pytest.approx((x[79] - h.mean()) / h.std(), abs=1e-12)
    assert z(imb, "09:25:30") is None                                # 24 rows before the newest one: fewer than 30
    assert z(imb, "09:31:30") == pytest.approx((x[30] - x[:30].mean()) / x[:30].std(), abs=1e-12)     # exactly 30
    v = imb.copy()
    v[19:50] = np.nan                                                # 29 finite values left
    assert z(v) is None
    v = imb.copy()
    v[19:49] = np.nan                                                # 30 finite values left
    hh = x[49:79]
    assert z(v) == pytest.approx((x[79] - hh.mean()) / hh.std(), abs=1e-12)
    v = imb.copy()
    v[79] = np.nan                                                   # the newest row itself
    assert z(v) is None
    v = imb.copy()
    v[19:79] = 0.25                                                  # no dispersion
    assert z(v) is None
    v = imb.copy()
    v[80:] = 50.0                                                    # the minute still forming and later: irrelevant
    assert z(v) == z(imb)
    v = imb.copy()
    v[:19] = 50.0                                                    # older than 60 minutes: irrelevant
    assert z(v) == z(imb)
    assert z(imb[:79]) is None                                       # stale newest row
    gap = table(D, imb=imb, drop=range(25, 70))                      # a hole: rows older than 60 clock minutes do not refill it
    assert G.signals([trade(D, "10:20:30")], "G3", loader({D: gap}))[0] is None


def g3_case(n_days=330, seed=5):
    rng = np.random.default_rng(seed)
    cal = weekdays(dt.date(2022, 1, 3), n_days)
    rows, sig = [], []
    for k, d in enumerate(cal):
        if k % 7 == 3:
            continue                                                 # a calendar session without a trade still counts
        rows.append(trade(d, "09:45:00", "long" if k % 2 else "short"))
        sig.append(None if k % 11 == 5 else float(rng.normal()))
        if k % 5 == 0:                                               # a second nyam trade the same day
            rows.append(trade(d, "10:15:00", "short"))
            sig.append(float(rng.normal()))
        rows.append(trade(d, "14:00:00", "long"))                    # pm: its own population (shifted)
        sig.append(float(rng.normal() + 3.0))
    return [c.isoformat() for c in cal], rows, sig


def g3_brute(cal, rows, sig, sessions=250, min_pop=60):
    """Independent O(n^2) re-statement of the registered rule."""
    pos = [cal.index(r["date"]) for r in rows]
    ses = [S.session_of(r["entry_ms"]) for r in rows]
    al = [None if s is None else S.SIDE[r["side"]] * s for r, s in zip(rows, sig)]
    out = []
    for i in range(len(rows)):
        pop = [al[j] for j in range(len(rows)) if al[j] is not None and pos[j] < pos[i] and pos[j] >= pos[i] - sessions and ses[j] == ses[i]]
        if al[i] is None or len(pop) < min_pop:
            out.append(1.0)
            continue
        q1, q2 = np.quantile(pop, [1 / 3, 2 / 3])
        out.append(1.5 if al[i] > q2 else 0.5 if al[i] < q1 else 1.0)
    return out


def test_g3_terciles_come_from_the_trailing_250_sessions_of_the_same_session_of_day_only():
    cal, rows, sig = g3_case()
    got = G.categories(rows, "G3", sig, calendar=cal)
    assert got == g3_brute(cal, rows, sig)
    n = {m: got.count(m) for m in (0.5, 1.0, 1.5)}
    assert n[0.5] > 100 and n[1.5] > 100 and n[1.0] > 100            # all three tiers are exercised
    first = [m for r, m in zip(rows, got) if r["date"] < cal[55]]
    assert set(first) == {1.0}                                       # fewer than 60 earlier values: no resize
    assert all(m == 1.0 for m, s in zip(got, sig) if s is None)      # no signal: x1
    # the window really is 250 sessions: a shorter one gives other tiers late in the sample
    assert G.categories(rows, "G3", sig, calendar=cal, params={"g3_sessions": 80}) == g3_brute(cal, rows, sig, sessions=80)
    assert G.categories(rows, "G3", sig, calendar=cal, params={"g3_sessions": 80}) != got


def test_g3_is_causal_and_independent_of_the_row_order():
    cal, rows, sig = g3_case()
    base = G.categories(rows, "G3", sig, calendar=cal)
    for cut in (cal[100], cal[200], cal[300]):
        later = [None if r["date"] >= cut and s is not None and i % 2 else (s if r["date"] < cut else (s or 0.0) * -5.0 + 1.0)
                 for i, (r, s) in enumerate(zip(rows, sig))]
        got = G.categories(rows, "G3", later, calendar=cal)
        assert [m for r, m in zip(rows, got) if r["date"] < cut] == [m for r, m in zip(rows, base) if r["date"] < cut]
        # a trade of the cut day itself may change (its own signal changed), but the day's trades never see each other:
        same_day = [i for i, r in enumerate(rows) if r["date"] == cut]
        solo = [None if i in same_day[1:] else s for i, s in enumerate(sig)]
        assert G.categories(rows, "G3", solo, calendar=cal)[same_day[0]] == base[same_day[0]]
    perm = np.random.default_rng(1).permutation(len(rows)).tolist()
    shuffled = G.categories([rows[i] for i in perm], "G3", [sig[i] for i in perm], calendar=cal)
    assert shuffled == [base[i] for i in perm]


# ------------------------------------------------------------------ apply / null

def test_a_gate_never_creates_moves_or_reprices_a_trade():
    rows = [trade(D, f"09:{40 + i}:10", "long" if i % 2 else "short") for i in range(9)]
    keep = ["keep", "skip", "keep"] * 3
    out = G.apply(rows, "G1", keep)
    assert out == [r for r, c in zip(rows, keep) if c == "keep"] and all(o is not r for o in out for r in rows)
    assert G.apply(rows, "G2", ["skip"] * 9) == []
    mult = [0.5, 1.0, 1.5] * 3
    out = G.apply(rows, "G3", mult)
    assert len(out) == 3 * (1 + 2 + 3)
    strip = [{k: v for k, v in o.items() if not k.startswith("gate_")} for o in out]
    assert all(s in rows for s in strip)
    k = 0
    for r, m in zip(rows, mult):                                     # each trade: 2 x multiplier identical half-unit rows, in place
        n = int(2 * m)
        assert strip[k:k + n] == [r] * n and [o["gate_unit"] for o in out[k:k + n]] == list(range(1, n + 1))
        assert {o["gate_mult"] for o in out[k:k + n]} == {m} and {o["gate_units"] for o in out[k:k + n]} == {n}
        k += n


def test_match_counts_gives_the_real_counts_per_stratum_with_the_fewest_moves():
    rng = np.random.default_rng(11)
    n = 400
    strat = [("nyam", "pm", None)[i % 3] for i in range(n)]
    for order in (("keep", "skip"), (0.5, 1.0, 1.5)):
        real = [order[int(x)] for x in rng.integers(0, len(order), n)]
        null = [order[int(x)] for x in rng.integers(0, len(order), n)]
        out = G.match_counts(null, real, strat, np.random.default_rng(5), order)
        moves = 0
        for s in set(strat):
            ix = [i for i in range(n) if strat[i] == s]
            for c in order:
                assert sum(out[i] == c for i in ix) == sum(real[i] == c for i in ix)
            moves += sum(max(0, sum(null[i] == c for i in ix) - sum(real[i] == c for i in ix)) for c in order)
        assert sum(a != b for a, b in zip(out, null)) == moves > 0    # minimal: only the surplus moved
        assert out == G.match_counts(null, real, strat, np.random.default_rng(5), order)          # seeded
        assert out != G.match_counts(null, real, strat, np.random.default_rng(6), order)
        assert G.match_counts(real, real, strat, np.random.default_rng(5), order) == real         # nothing to move
    with pytest.raises(ValueError):
        G.match_counts(["keep", "maybe"], ["keep", "skip"], [None, None], rng, ("keep", "skip"))
    a, b = G.null_rng("gate_x_G1", 1).integers(0, 10 ** 9, 4), G.null_rng("gate_x_G1", 2).integers(0, 10 ** 9, 4)
    c = G.null_rng("gate_y_G1", 1).integers(0, 10 ** 9, 4)
    assert a.tolist() == G.null_rng("gate_x_G1", 1).integers(0, 10 ** 9, 4).tolist() and a.tolist() != b.tolist() != c.tolist()


def outcome(r, pts):
    """The row with a result of `pts` points (a consistent R row: gross, net, exit, MAE / MFE)."""
    sgn, px = S.SIDE[r["side"]], r["entry_price"]
    r.update(exit_price=px + sgn * pts, gross=pts * 20.0, net=pts * 20.0 - 4.0, exit_reason="tp" if pts > 0 else "sl", sl=px - sgn * 45.0,
             tp=px + sgn * 65.0, mae_pts=max(2.0, -pts), mfe_pts=max(2.0, pts), mae_usd=max(2.0, -pts) * 20.0, mfe_usd=max(2.0, pts) * 20.0)
    return r


def toy_world(n_days=90, seed=2, start=120, mask_every=0, mask_null_only=0, mask_real_only=0):
    """Trades (nyam + pm, both sides, mixed synthetic results) on n in-sample calendar sessions + a real and two null feature
    tables per day. mask_every=k: every k-th day has no book in ANY world (a roll / masked day: NaN stays NaN under the null).
    mask_null_only=k: days k // 2 mod k have no book in the NULL worlds only (the donor had no row). mask_real_only=k: days
    1 mod k have no book in the REAL world only."""
    import score
    days = [dt.date.fromisoformat(d) for d in score.in_sample_sessions()[start:start + n_days]]
    rng = np.random.default_rng(seed)
    rows = []
    for k, d in enumerate(days):
        rows.append(trade(d, "09:47:13", "long" if k % 2 else "short", ms=250))
        if k % 3 == 0:
            rows.append(trade(d, "10:31:00", "long", ms=40))
        rows.append(trade(d, "14:05:30", "short" if k % 4 else "long"))
    for r in rows:
        outcome(r, float(rng.choice([60.0, 25.0, -30.0, -40.0])))
    rows.sort(key=lambda r: (r["exit_ms"], r["entry_ms"]))

    def tabs(s):
        r = np.random.default_rng([seed, s])
        out = {}
        for k, d in enumerate(days):
            imb, dep = r.normal(0, 0.2, 480), r.normal(-0.15, 0.2, 480)
            dead = (mask_every and k % mask_every == 0) or (s and mask_null_only and k % mask_null_only == mask_null_only // 2) \
                or (not s and mask_real_only and k % mask_real_only == 1)
            out[d] = table(d, "08:00", imb=imb, depth=dep) if not dead else table(d, "08:00", imb=[np.nan] * 480, depth=[np.nan] * 480)
        return out

    worlds = {None: tabs(0), 1: tabs(1), 2: tabs(2)}
    return [d.isoformat() for d in days], rows, (lambda gate, seed: loader(worlds[seed]))


@pytest.mark.parametrize("gate", G.GATES)
def test_the_permutation_null_has_the_real_gates_row_count_in_every_session(gate):
    cal, rows, feats = toy_world()
    prm = {"g3_min_pop": 20}
    real = G.run_gate(rows, gate, feats(gate, None), calendar=cal, params=prm)
    assert real["trades"] == G.run_gate(rows, gate, feats(gate, None), calendar=cal, params=prm)["trades"]     # deterministic
    assert len(set(real["cats"])) == len(G.ORDER[gate])               # every category occurs
    nulls = {}
    for seed in G.NULL_SEEDS:
        nl = G.run_null(rows, gate, feats(gate, seed), real, key="gate_toy_" + gate, seed=seed, calendar=cal, params=prm)
        assert nl["counts"]["cats_by_session"] == real["counts"]["cats_by_session"]
        assert nl["counts"]["rows_by_session"] == real["counts"]["rows_by_session"] and len(nl["trades"]) == len(real["trades"])
        assert nl["cats"] != real["cats"] and nl["counts"]["moved_to_match"] > 0
        strip = [{k: v for k, v in o.items() if not k.startswith("gate_")} for o in nl["trades"]]
        assert all(s in rows for s in strip)
        again = G.run_null(rows, gate, feats(gate, seed), real, key="gate_toy_" + gate, seed=seed, calendar=cal, params=prm)
        assert again["trades"] == nl["trades"]
        nulls[seed] = nl["cats"]
    assert nulls[1] != nulls[2]
    # the null of the real features with nothing to move is the real gate itself
    same = G.run_null(rows, gate, feats(gate, None), real, key="k", seed=1, calendar=cal, params=prm)
    assert same["trades"] == real["trades"] and same["counts"]["moved_to_match"] == 0


@pytest.mark.parametrize("gate", ("G1", "G2"))
def test_a_g1_g2_verdict_depends_on_the_trades_own_day_only(gate):
    """What the 1-vs-8-worker test protects for a Template family: no state crosses a session."""
    cal, rows, feats = toy_world(n_days=30)
    full = G.run_gate(rows, gate, feats(gate, None), calendar=cal)["cats"]
    for d in cal[::7]:
        ix = [i for i, r in enumerate(rows) if r["date"] == d]
        solo = G.run_gate([rows[i] for i in ix], gate, feats(gate, None), calendar=cal)["cats"]
        assert solo == [full[i] for i in ix]
    perm = np.random.default_rng(4).permutation(len(rows)).tolist()
    assert G.run_gate([rows[i] for i in perm], gate, feats(gate, None), calendar=cal)["cats"] == [full[i] for i in perm]


# ------------------------------------------------------------------ bundles, ledger, cap

def toy_kw(tmp_path, monkeypatch, **world):
    cal, rows, feats = toy_world(**world)
    (tmp_path / "trades").mkdir()
    (tmp_path / "trades" / "toy.json").write_text(json.dumps(rows))
    monkeypatch.setattr(G, "PICKS", {"toy-tf15_c1": {"file": "toy", "key": "toy-tf15#1", "tf": "15", "sess": "nyam"}})
    monkeypatch.setattr(S, "wait_compute_window", lambda *a, **k: 0.0)
    kw = dict(runs_dir=tmp_path / "runs", ledger=tmp_path / "ledger.csv", log=tmp_path / "gate.log", trades_dir=tmp_path / "trades",
              features=feats, calendar=cal)
    return tmp_path, rows, kw


@pytest.fixture
def toy(tmp_path, monkeypatch):
    return toy_kw(tmp_path, monkeypatch)


def test_run_all_writes_one_bundle_and_one_gate_ledger_row_per_job_and_is_idempotent(toy):
    import score
    tmp, rows, kw = toy
    out = G.run_all(**kw)
    keys = [j["key"] for j in G.jobs()]
    assert out == {"ran": keys, "skipped": [], "restored": []} and len(keys) == 9
    assert keys[:3] == ["gate_toy-tf15_c1_G1", "gate_toy-tf15_c1_G1-perms1", "gate_toy-tf15_c1_G1-perms2"]
    led = screen.read_ledger(kw["ledger"])
    assert [r["key"] for r in led] == keys and {r["stage"] for r in led} == {"gate"} and screen.cap_used(led) == 9
    for r in led:
        d = kw["runs_dir"] / r["key"]
        run = json.loads((d / "run.json").read_text())
        gate = run["gate"]["gate"]
        tr = json.loads((d / ("half_units.json" if gate == "G3" else "trades.json")).read_text())
        assert r["family"] == "gate_" + gate and r["tf"] == "15" and int(r["trades"]) == len(tr) == run["trades"]
        assert (r["control"], r["seed"]) == (("perm", str(run["gate"]["seed"])) if "-perms" in r["key"] else ("", ""))
        assert run["engine"] == G.ENGINE and run["range"] == {"start": "2021-09-22", "end": "2024-12-31", "holdout": False}
        assert json.loads(r["inputs_json"]) == run["inputs"] and run["inputs"]["pick"] == "toy-tf15_c1" and run["inputs"]["guard_ms"] == 0
        assert run["gate"]["counts"]["source_trades"] == len(rows) and run["gate"]["half_unit_rows"] == (gate == "G3")
        assert run["gate"]["stage"] == "gate" and run["gate"]["control_only"] == ("-perms" in r["key"])
        assert score.validate_trades(tr) == []
        if gate != "G3":
            assert score.load_trades(str(d)).n == len(tr)            # the scorer reads the directory
            continue
        assert not (d / "trades.json").exists()                      # the half-unit rows are not a scorer input ...
        with pytest.raises(FileNotFoundError):
            score.load_trades(str(d))                                # ... and the scorer cannot take them by accident
        assert sum(run["tiers"].values()) == len(rows) and run["tiers"] == {n: run["gate"]["counts"]["cats"][str(m)] for m, n in G.TIERS}
        for m, n in G.TIERS:                                         # one scorer bundle per non-empty size tier
            assert (d / n).exists() == (run["tiers"][n] > 0)
            if run["tiers"][n]:
                t = score.load_trades(str(d / n))
                assert t.n == run["tiers"][n] and {x["gate_mult"] for x in t.rows} == {m}
    by = {r["key"]: int(r["trades"]) for r in led}
    for g in G.GATES:                                                # each null has exactly its gate's row count
        assert by[f"gate_toy-tf15_c1_{g}"] == by[f"gate_toy-tf15_c1_{g}-perms1"] == by[f"gate_toy-tf15_c1_{g}-perms2"]
    assert 0 < by["gate_toy-tf15_c1_G1"] < len(rows) and 0 < by["gate_toy-tf15_c1_G2"] < len(rows)
    assert by["gate_toy-tf15_c1_G3"] >= len(rows)                    # G3 (registered minimum 60 values) never drops a trade
    mem = G._members(kw["runs_dir"] / "gate_toy-tf15_c1_G3", "gate_toy-tf15_c1_G3", "nyam", 5)
    res = score.score_eval(mem, "lucid", {}, boots=0)                # the sized position: every source trade ONCE, in its tier
    assert res["n_trades"] == sum(1 for r in rows if S.session_of(r["entry_ms"]) == "nyam")
    assert [(m["micros"], m["trades"] > 0) for m in res["members"]] == [(5, True), (10, True), (15, True)]
    before = {p: p.read_bytes() for p in kw["runs_dir"].rglob("*.json")}
    again = G.run_all(**kw)
    assert again == {"ran": [], "skipped": keys, "restored": []} and len(screen.read_ledger(kw["ledger"])) == 9
    assert {p: p.read_bytes() for p in kw["runs_dir"].rglob("*.json")} == before
    assert sorted(p.name for p in kw["runs_dir"].iterdir()) == sorted(keys)        # no temporary directory is left


def test_run_all_resumes_refuses_past_the_cap_and_detects_a_drifted_definition(toy):
    tmp, rows, kw = toy
    with pytest.raises(screen.CapExceeded, match="0 used \\+ 9 pending > cap 8"):
        G.run_all(cap=8, **kw)
    assert not kw["runs_dir"].exists() and screen.read_ledger(kw["ledger"]) == [] and "REFUSED" in kw["log"].read_text()
    first = G.run_all(gates=["G2"], **kw)
    assert first["ran"] == ["gate_toy-tf15_c1_G2", "gate_toy-tf15_c1_G2-perms1", "gate_toy-tf15_c1_G2-perms2"]
    rest = G.run_all(**kw)
    assert len(rest["ran"]) == 6 and rest["skipped"] == first["ran"]
    # a null is pending while its real gate is recorded with another row count: the definition drifted -> refuse
    led = screen.read_ledger(kw["ledger"])
    with open(kw["ledger"], "w", newline="") as fh:
        import csv
        w = csv.DictWriter(fh, screen.COLS)
        w.writeheader()
        for r in led:
            if r["key"] == "gate_toy-tf15_c1_G1":
                r = {**r, "trades": "1"}
            if r["key"] != "gate_toy-tf15_c1_G1-perms2":
                w.writerow(r)
    with pytest.raises(RuntimeError, match="changed after the first run"):
        G.run_all(**kw)
    with pytest.raises(KeyError):
        G.jobs(gates=["G4"])
    with pytest.raises(KeyError):
        G.jobs(only=["nope"])


# ------------------------------------------------------------------ the registered plan (real picks; no P&L)

def test_the_plan_is_six_picks_three_gates_and_two_nulls_each():
    import score
    plan = G.jobs()
    assert len(plan) == 54 and len({j["key"] for j in plan}) == 54
    assert sum(j["control"] == "" for j in plan) == 18 and sum(j["control"] == "perm" for j in plan) == 36
    assert plan[0]["key"] == "gate_straddle-tf30_c10_G1" and plan[2]["key"] == "gate_straddle-tf30_c10_G1-perms2"
    assert G.gate_key("orb-tf5_c10", "G3", 2) == "gate_orb-tf5_c10_G3-perms2"
    assert G.NULL_SEED_BASE == score.C2_SEED and G.NULL_SEEDS == screen.C2_SEEDS
    known = {b["key"] for b in {**score.BASELINE, **score.BASELINE_ALT}.values()}
    assert {p["key"] for p in G.PICKS.values()} == known and len(G.PICKS) == 6
    for pick, p in G.PICKS.items():
        assert p["file"] == score.export_name(p["key"]) and (G.TRADES / (p["file"] + ".json")).exists()
        assert p["sess"] in {b["sess"] for b in G.slots(pick).values()} and len(G.slots(pick)) >= 1
    assert G.DEFAULTS == {"g1_rows": 5, "z_win": 60, "z_min": 30, "g3_sessions": 250, "g3_min_pop": 60, "guard_ms": 0}
    for g in G.GATES:                                                # the null shuffles the gate's feature column, never the clock
        c2 = score.C2Features(G.COLS[g], seed=1)
        assert c2.shuffle_cols == tuple(c for c in G.COLS[g] if c != "t_utc") and len(c2.shuffle_cols) == 1


def test_cell_hands_the_scorer_the_bundle_for_g1_g2_and_a_tier_portfolio_for_g3(tmp_path):
    import score
    c1, c3 = G.cell("straddle-tf30_c10", "G1", "flex_eval"), G.cell("straddle-tf30_c10", "G3", "flex_eval")
    b = score.BASELINE["flex_eval"]
    assert c1["gate_kw"] == c1["base_kw"] == {"firm": "lucid", "rules": b["rules"], "sess": "nyam", "micros": 40}
    assert c1["real"].endswith("runs/gate_straddle-tf30_c10_G1") and c1["base"] == "file:R__hm2-straddle-tf30_c10" and not c1["warnings"]
    assert [n.rsplit("/", 1)[-1] for n in c1["nulls"]] == ["gate_straddle-tf30_c10_G1-perms1", "gate_straddle-tf30_c10_G1-perms2"]
    # G3: one member per size tier at u / 2u / 3u micros (u = half the pick's), never the half-unit rows at half micros
    assert c3["gate_kw"] == {"firm": "lucid", "rules": b["rules"], "sess": "nyam"} and c3["base_kw"] == c1["base_kw"]
    assert [(m["src"].split("runs/")[-1], m["micros"], m["sess"], m["label"]) for m in c3["real"]] == [
        ("gate_straddle-tf30_c10_G3/x0.5", 20, "nyam", "gate_straddle-tf30_c10_G3|x0.5"),
        ("gate_straddle-tf30_c10_G3/x1", 40, "nyam", "gate_straddle-tf30_c10_G3|x1"),
        ("gate_straddle-tf30_c10_G3/x1.5", 60, "nyam", "gate_straddle-tf30_c10_G3|x1.5")]
    assert [[m["src"].split("runs/")[-1] for m in n] for n in c3["nulls"]] == [
        [f"gate_straddle-tf30_c10_G3-perms{s}/{t}" for t in ("x0.5", "x1", "x1.5")] for s in (1, 2)]
    assert (c3["unit"], c3["tier_micros"], c3["cap"], c3["cap_ok"], c3["unit_cap"]) == (20, {"x0.5": 20, "x1": 40, "x1.5": 60}, 40, False, 13)
    assert "base_same_size_kw" not in c3 and any("over the lucid limit of 40" in w for w in c3["warnings"])
    cc = G.cell("straddle-tf30_c10", "G3", "flex_eval", unit=13)                    # the cap-compliant cell
    assert [m["micros"] for m in cc["real"]] == [13, 26, 39] and cc["cap_ok"] and cc["base_same_size_kw"]["micros"] == 26
    assert cc["base_kw"]["micros"] == 40
    with pytest.raises(ValueError, match="unit=13"):                                # over the cap: refused before a file is read
        G.score_cell("straddle-tf30_c10", "G3", "flex_eval", runs_dir=tmp_path)
    with pytest.raises(ValueError, match="unit=13"):
        G.lift_cell("straddle-tf30_c10", "G3", "flex_eval", runs_dir=tmp_path)
    with pytest.raises(ValueError, match=">= 1"):
        G.cell("straddle-tf30_c10", "G3", "flex_eval", unit=0)
    assert set(G.slots("straddle-tf30_c10")) == {"flex_eval", "pro_nodll_eval"}
    # the pick whose only approved cell has max_day_tr = 1: one row per trade, so the cell is valid for G3 too
    s9 = G.cell("straddle-tf30_c9", "G3")
    assert s9["slot"] == "pro_nodll_eval_s9" and s9["gate_kw"]["rules"]["max_day_tr"] == 1 and len(s9["real"]) == 3
    # funded cells; the first slot of a pick is its approved cell, the Apex 300K PA bar comes after it
    assert list(G.slots("donchian-tf15_c1")) == ["apex_pa_funded", "apex300_pa"]
    f = G.cell("donchian-tf15_c1", "G3")
    assert f["slot"] == "apex_pa_funded" and f["kind"] == "funded" and [m["micros"] for m in f["real"]] == [15, 30, 45]
    assert f["cap"] == 50 and f["cap_ok"] and f["gate_kw"]["policy"] == 1000 and "micros" not in f["gate_kw"]       # the PA half size
    assert f["gate_kw"]["both_sides"] is False and f["gate_kw"]["strategy"] == "donchian" and f["gate_kw"]["inputs"]["tgt_r"] == 0.4
    a = G.cell("donchian-tf15_c1", "G3", "apex300_pa")
    assert a["gate_kw"]["firm"] == "apex300_pa" and a["gate_kw"]["policy"] == "max" and a["base_kw"]["micros"] == 100
    assert [m["micros"] for m in a["real"]] == [50, 100, 150] and a["cap"] == 170 and a["cap_ok"] and a["unit_cap"] == 56
    d = G.cell("donchian-tf15_c10", "G3")                                            # Pro DLL funded, m30: 45 micros > the Lucid 40
    assert (d["slot"], d["tier_micros"]["x1.5"], d["cap"], d["cap_ok"], d["unit_cap"]) == ("pro_dll_funded", 45, 40, False, 13)
    assert a["gate_kw"]["rules"] == {"day_take": 3000, "day_lock": 3000, "day_stop": 0, "max_day_tr": 0}
    assert G.cell("donchian-tf15_c1", "G1", "apex300_pa")["gate_kw"]["micros"] == 100
    bar = G.L / "out" / "baseline_insample.json"                                     # the published 300K PA bar (SCORING.md)
    if bar.exists():
        fresh = json.loads(bar.read_text())["apex300_pa"]["bar"]["fresh"]
        x = G.EXTRA_SLOTS["apex300_pa"]
        assert fresh["from"].startswith(x["key"] + "|" + x["sess"]) and (fresh["micros"], fresh["policy"]) == (x["micros"], x["policy"])
        assert {k: float(v) for k, v in fresh["rules"].items()} == {k: float(v) for k, v in x["rules"].items()}
    # the execution-guard robustness bundles have their own keys
    g = G.cell("straddle-tf30_c10", "G1", "flex_eval", guard_ms=1000)
    assert g["real"].endswith("runs/gate_straddle-tf30_c10_G1-guard1000") and g["nulls"][1].endswith("G1-guard1000-perms2")


def test_smoke_on_real_in_sample_days_counts_only():
    """Four fixed in-sample days of one pick through the real feature table and the real C2 null: counts and equality only."""
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    try:
        out = G.smoke(4, only=["donchian-tf15_c1"])
    except FileNotFoundError as e:
        pytest.skip(f"feature cache / trade list not available: {e}")
    o = out["picks"]["donchian-tf15_c1"]
    assert out["ok"] and out["days"] == 4 and o["source_trades"] > 0 and o["entry_kind"]["resting"] == 0
    for g in G.GATES:
        assert o[g]["deterministic"] and all(p["counts_match"] and p["rows"] == o[g]["rows"] for p in o[g]["perm"].values())
    assert o["G1"]["rows"] <= o["source_trades"] and o["G2"]["rows"] <= o["source_trades"] <= o["G3"]["rows"] <= 3 * o["source_trades"]
    flat = json.dumps(out)
    for word in ("net", "gross", "pnl", "exit_reason", "win"):
        assert word not in flat


def test_the_source_lists_are_in_sample_one_nq_rows_with_no_entry_in_the_last_five_minutes_of_a_session():
    """A gate only drops / repeats rows, so the pick's own 'no entry in the last 5 minutes' property carries over."""
    for pick in G.PICKS:
        rows, sha = G.pick_rows(pick)
        assert len(rows) > 3000 and len(sha) == 64 and max(r["date"] for r in rows) <= "2024-12-31"
        G.check_rows(rows)                                           # in-sample, 1 NQ, date = ET date of entry_ms
        for r in rows:
            a = dt.datetime.fromtimestamp(r["entry_ms"] / 1000, S.ET)
            k = S.session_of(r["entry_ms"])
            assert k is not None                                     # every trade has a session of the day (the null's strata)
            end = S.SESS[k][1] if not (a.date() in S.EARLY_CLOSES and k in ("mid", "pm")) else min(S.SESS[k][1], 13 * 3600 + 15 * 60)
            assert a.hour * 3600 + a.minute * 60 + a.second < end - 300


# ------------------------------------------------------------------ added after verification (2026-10-02): G3 boundary + ties

def test_g3_needs_exactly_sixty_earlier_values_and_a_tie_with_a_tercile_stays_x1():
    cal = [d.isoformat() for d in weekdays(dt.date(2022, 1, 3), 70)]
    rows = [trade(dt.date.fromisoformat(d), "09:45:00", "long") for d in cal[:62]]
    sig = [float(k) for k in range(62)]                              # long: a = z = 0, 1, 2, ...
    cats, basis = G.verdicts(rows, "G3", sig, calendar=cal)
    assert basis == [False] * 60 + [True, True]                      # day 59 has 59 earlier values (no tercile), day 60 has 60
    assert cats[:60] == [1.0] * 60 and cats[60] == 1.5 and G.categories(rows, "G3", sig, calendar=cal) == cats
    assert G.verdicts(rows, "G3", sig, calendar=cal, params={"g3_min_pop": 61})[1] == [False] * 61 + [True]
    # ties: day 61 holds five trades judged against the SAME population (days 0..60: the day's trades never see each other)
    pop = np.arange(61, dtype=np.float64)
    q1, q2 = (float(x) for x in np.quantile(pop, [1.0 / 3.0, 2.0 / 3.0]))
    d61 = dt.date.fromisoformat(cal[61])
    vals = [q2, float(np.nextafter(q2, np.inf)), q1, float(np.nextafter(q1, -np.inf)), (q1 + q2) / 2]
    rows = rows[:61] + [trade(d61, f"09:{45 + i}:00", "long") for i in range(5)]
    got = G.categories(rows, "G3", sig[:61] + vals, calendar=cal)[61:]
    assert got == [1.0, 1.5, 1.0, 0.5, 1.0]                          # a == q2 and a == q1 are x1: only strictly beyond resizes
    # the side aligns the z: the same values on short trades are the mirror image
    short = rows[:61] + [trade(d61, f"09:{45 + i}:00", "short") for i in range(5)]
    assert G.categories(short, "G3", sig[:61] + [-v for v in vals], calendar=cal)[61:] == got


# ------------------------------------------------------------------ the permutation null: wiring, basis

def test_the_plan_reads_the_real_table_for_a_gate_and_c2_features_of_its_own_seed_for_each_null(toy, monkeypatch):
    import score
    for g in G.GATES:
        real = G._features(g)
        assert type(real) is S.L2Features and real.columns == G.COLS[g] and real.allow_holdout is False and real.mask is True
        nulls = [G._features(g, s) for s in G.NULL_SEEDS]
        assert all(type(n) is score.C2Features and n.columns == G.COLS[g] and n.allow_holdout is False for n in nulls)
        assert [n.seed for n in nulls] == [1, 2] and all(n.min_gap == 5 and n.strata is None and not n.partial for n in nulls)
    tmp, rows, kw = toy
    feats = kw.pop("features")
    calls = []
    monkeypatch.setattr(G, "_features", lambda gate, seed=None: calls.append((gate, seed)) or feats(gate, seed))
    G.run_all(**kw)                                                  # features=None: the default loader
    assert set(calls) == {(g, s) for g in G.GATES for s in (None, 1, 2)}
    pick = "toy-tf15_c1"

    def on_disk(key, gate):
        return json.loads((kw["runs_dir"] / key / ("half_units.json" if gate == "G3" else "trades.json")).read_text())

    for g in G.GATES:                                                # every bundle = the direct computation on ITS OWN world
        real = G.run_gate(rows, g, feats(g, None), calendar=kw["calendar"])
        assert on_disk(G.gate_key(pick, g), g) == real["trades"]
        seen = [real["cats"]]
        for s in G.NULL_SEEDS:
            nl = G.run_null(rows, g, feats(g, s), real, key=G.gate_key(pick, g), seed=s, calendar=kw["calendar"])
            assert on_disk(G.gate_key(pick, g, s), g) == nl["trades"]
            assert nl["cats"] not in seen                            # not the real gate, not the other seed
            seen.append(nl["cats"])
            # fed the REAL table, or the other seed's stream, the result would be another one:
            assert G.run_null(rows, g, feats(g, None), real, key=G.gate_key(pick, g), seed=s, calendar=kw["calendar"])["trades"] != nl["trades"]
            assert G.run_null(rows, g, feats(g, s), real, key=G.gate_key(pick, g), seed=3 - s, calendar=kw["calendar"])["trades"] != nl["trades"]


def test_match_counts_moves_judged_trades_first():
    order, n = ("keep", "skip"), 60
    strat, null = ["nyam"] * n, ["keep"] * n
    movable = [i % 3 == 0 for i in range(n)]                         # 20 judged trades
    real = ["skip"] * 10 + ["keep"] * 50
    out = G.match_counts(null, real, strat, np.random.default_rng(5), order, movable=movable)
    moved = [i for i in range(n) if out[i] != null[i]]
    assert len(moved) == 10 and all(movable[i] for i in moved) and out.count("skip") == 10
    assert out != G.match_counts(null, real, strat, np.random.default_rng(6), order, movable=movable)
    real = ["skip"] * 25 + ["keep"] * 35                             # more than the judged trades can give: all 20, then 5 others
    out = G.match_counts(null, real, strat, np.random.default_rng(5), order, movable=movable)
    moved = [i for i in range(n) if out[i] != null[i]]
    assert len(moved) == 25 and sum(movable[i] for i in moved) == 20
    full = G.match_counts(null, real, strat, np.random.default_rng(5), order)
    assert full == G.match_counts(null, real, strat, np.random.default_rng(5), order, movable=[True] * n)     # None = every trade
    with pytest.raises(ValueError):
        G.match_counts(null, real, strat, np.random.default_rng(5), order, movable=[True] * 3)


@pytest.mark.parametrize("gate", G.GATES)
def test_the_null_never_judges_a_trade_the_real_gate_cannot_judge(gate):
    """Masked days (no book in any world): the real gate gives them its no-signal verdict; the count matching must not hand
    them another one while judged trades are left."""
    cal, rows, feats = toy_world(mask_every=4)
    prm = {"g3_min_pop": 20}
    real = G.run_gate(rows, gate, feats(gate, None), calendar=cal, params=prm)
    blind = [i for i, b in enumerate(real["basis"]) if not b]
    none = {"G1": "keep", "G2": "skip", "G3": 1.0}[gate]
    assert len(blind) > 40 and all(real["cats"][i] == none for i in blind) and real["counts"]["basis"] == len(rows) - len(blind)
    assert real["counts"]["no_signal"] == sum(s is None for s in real["sig"]) > 40
    for seed in G.NULL_SEEDS:
        nl = G.run_null(rows, gate, feats(gate, seed), real, key="gate_toy_" + gate, seed=seed, calendar=cal, params=prm)
        assert nl["counts"]["moved_to_match"] > 0 and nl["counts"]["moved_without_basis"] == 0
        assert all(nl["cats"][i] == none for i in blind)             # untouched
        assert nl["counts"]["cats_by_session"] == real["counts"]["cats_by_session"]
    # a trade is judged only with evidence on BOTH sides: days dead in the null only (the donor had no row) are left alone
    # too, and so are days the real gate cannot judge even where the null has a verdict of its own
    cal, rows, feats = toy_world(mask_every=7, mask_null_only=4, mask_real_only=5)
    real = G.run_gate(rows, gate, feats(gate, None), calendar=cal, params=prm)
    for seed in G.NULL_SEEDS:
        raw, basis = G.verdicts(rows, gate, G.signals(rows, gate, feats(gate, seed), prm), cal, prm)
        nl = G.run_null(rows, gate, feats(gate, seed), real, key="gate_toy_" + gate, seed=seed, calendar=cal, params=prm)
        fixed = [i for i in range(len(rows)) if not (real["basis"][i] and basis[i])]
        assert sum(real["basis"][i] and not basis[i] for i in fixed) > 15 and sum(basis[i] and not real["basis"][i] for i in fixed) > 15
        assert nl["basis"] == basis and nl["counts"]["moved_to_match"] > 0
        touched = [i for i in fixed if nl["cats"][i] != raw[i]]
        assert len(touched) == nl["counts"]["moved_without_basis"] and (gate == "G3" or not touched)
        st, free = G.strata(rows), set(range(len(rows))) - set(fixed)
        for i in touched:                                            # the fall-back: only once EVERY judged trade of that category
            assert all(nl["cats"][j] != raw[j] for j in free if st[j] == st[i] and raw[j] == raw[i])     # and session had been moved
        assert nl["counts"]["cats_by_session"] == real["counts"]["cats_by_session"]


# ------------------------------------------------------------------ the snapshot-phase guard (as l2sim.run applies it)

def test_a_month_that_failed_the_phase_check_is_judged_one_second_earlier_and_an_unchecked_holdout_month_raises(tmp_path, monkeypatch):
    pg = tmp_path / "phase_guard.json"
    monkeypatch.setattr(S, "PHASE_GUARD", pg)
    tab = table(D, depth=[0.0] * 30 + [-0.5] + [0.0] * 10)            # row 30 (thin) is usable from 09:31:00.000
    assert one("G2", tab, "09:31:00", ms=500)[0] == "thin"           # no persisted check at all: nothing failed
    pg.write_text(json.dumps({"months": {"2024-03": {"ok": False}}, "failed": ["2024-03"]}))
    assert one("G2", tab, "09:31:00", ms=500)[0] == "mid"            # 0.5 s after the boundary: under the 1 s guard, the row before
    assert one("G2", tab, "09:31:01", ms=1)[0] == "thin" and one("G2", tab, "09:31:01", ms=0)[0] == "mid"
    assert one("G2", tab, "09:31:01", ms=500, params={"guard_ms": 1000})[0] == "mid"       # it ADDS to guard_ms
    r = G.run_gate([trade(D, "09:31:00", ms=500), trade(D, "09:31:02")], "G2", loader({D: tab}), calendar=[D.isoformat()])
    assert r["cats"] == ["skip", "keep"] and r["counts"]["exec_guard"] == {"ms": 1000, "months": ["2024-03"], "trades": 2}
    assert G.exec_guard_months(loader({D: tab}), [D.isoformat()]) == {"2024-03"}
    D2 = dt.date(2024, 4, 9)                                         # a month that passed, in the same list: its clock is not moved
    two = [trade(D, "09:31:00", ms=500), trade(D2, "09:31:00", ms=500)]
    both = loader({D: tab, D2: table(D2, depth=[0.0] * 30 + [-0.5] + [0.0] * 10)})
    assert G.signals(two, "G2", both) == ["mid", "thin"] and G.exec_guard_months(both, [D.isoformat(), D2.isoformat()]) == {"2024-03"}
    assert G.run_gate(two, "G2", both, calendar=[D.isoformat(), D2.isoformat()])["counts"]["exec_guard"]["trades"] == 1
    for bad in (-1, 0.5, True):                                      # a bad guard is refused in a guarded month too
        with pytest.raises(S.LookAheadError):
            G.signals([trade(D)], "G2", loader({D: tab}), {"guard_ms": bad})
    pg.write_text(json.dumps({"months": {"2024-02": {}, "2024-03": {}}, "failed": ["2024-02"]}))
    assert one("G2", tab, "09:31:00", ms=500)[0] == "thin"           # another month failed: no guard here
    assert G.run_gate([trade(D)], "G2", loader({D: tab}), calendar=[D.isoformat()])["counts"]["exec_guard"] is None

    class FlowOnly:                                                  # a loader that names only flow / clock columns: not a book reader
        columns = ("f_delta", "t_utc")

        def __call__(self, d):
            return tab
    pg.write_text(json.dumps({"months": {"2024-03": {}}, "failed": ["2024-03"]}))
    assert G.exec_guard_months(FlowOnly(), [D.isoformat()]) == frozenset()
    for g in G.GATES:                                                # every gate's own loader reads the book
        assert S.needs_exec_guard(G._features(g)) and S.needs_exec_guard(G._features(g, 1))
    # holdout (synthetic rows and tables; no sealed row is read): sealed by default, then the phase check must exist
    H = dt.date(2025, 3, 4)
    rows, feats = [trade(H, "09:31:00", ms=500)], loader({H: table(H, depth=[0.0] * 30 + [-0.5] + [0.0] * 10)})
    with pytest.raises(S.HoldoutSealed):
        G.signals(rows, "G2", feats)
    with pytest.raises(S.PhaseGuardMissing, match="2025-03"):
        G.signals(rows, "G2", feats, allow_holdout=True)
    pg.write_text(json.dumps({"months": {"2025-03": {}}, "failed": []}))
    assert G.signals(rows, "G2", feats, allow_holdout=True) == ["thin"]
    pg.write_text(json.dumps({"months": {"2025-03": {}}, "failed": ["2025-03"]}))
    assert G.signals(rows, "G2", feats, allow_holdout=True) == ["mid"]


# ------------------------------------------------------------------ diagnostics (counts only)

def test_entry_timing_counts_fills_just_after_a_minute_and_late_market_fills():
    rows = [trade(D, "09:45:00", ms=97),                             # 97 ms after the minute, market
            trade(D, "09:45:00", ms=999),
            trade(D, "09:45:01"),                                    # exactly 1 s: a clock 1 s earlier is 1 ns short of the row
            trade(D, "09:45:01", ms=1),                              # 1.001 s: the guarded clock sees the same row
            trade(D, "09:46:00"),                                    # ON a boundary: reads the row before it, guarded or not;
            #                                                          exactly 60 s after the bar: still the bar-close row
            trade(D, "09:46:00", ms=5),                              # 5 ms after ITS minute, 60.005 s after the 15-min bar
            trade(D, "09:59:33"),                                    # 14 min 33 s after the bar
            trade(D, "10:00:59", ms=999),                            # 59.999 s after the bar: not late
            trade(D, "09:50:00", ms=3, order_price=15001.0)]         # a resting entry is never a late MARKET fill
    assert G.entry_timing(rows, "15") == {"under_1s_after_minute": 5, "market_entries": 8, "market_over_60s_after_bar": 2}
    assert G.entry_timing(rows) == {"under_1s_after_minute": 5, "market_entries": 8}
    assert G.entry_timing(rows, "1")["market_over_60s_after_bar"] == 0
    # the count IS the set of trades whose row changes under the 1 s guard (a table whose value is its own row number)
    tab = table(D, imb=[float(i) for i in range(70)])
    now = G.signals(rows, "G1", loader({D: tab}), {"g1_rows": 1})
    late = G.signals(rows, "G1", loader({D: tab}), {"g1_rows": 1, "guard_ms": 1000})
    assert sum(a != b for a, b in zip(now, late)) == 5 and [a != b for a, b in zip(now, late)] == [True, True, True, False, False, True,
                                                                                               False, False, True]


def test_guard_check_counts_the_verdicts_that_need_the_first_second():
    dep = [0.0] * 60
    dep[30], dep[40] = -0.5, -0.5                                    # thin rows usable from 09:31:00 and 09:41:00
    tab = table(D, depth=dep)
    rows = [trade(D, "09:31:00", ms=200), trade(D, "09:31:30"), trade(D, "09:41:00", ms=999), trade(D, "09:41:01", ms=1), trade(D, "09:50:00", ms=10)]
    real = G.run_gate(rows, "G2", loader({D: tab}), calendar=[D.isoformat()])
    assert real["cats"] == ["keep", "keep", "keep", "keep", "skip"]
    chk = G.guard_check(rows, "G2", loader({D: tab}), real["cats"], calendar=[D.isoformat()])
    assert chk == {"guard_ms": 1000, "verdicts_changed": 2, "no_signal": 0}                # the two fills under 1 s after the boundary
    assert G.guard_check(rows, "G2", loader({D: tab}), real["cats"], calendar=[D.isoformat()], guard_ms=100)["verdicts_changed"] == 0
    assert G.guard_check(rows, "G2", loader({D: tab}), real["cats"], calendar=[D.isoformat()], guard_ms=250)["verdicts_changed"] == 1


# ------------------------------------------------------------------ G3 bundles: tiers

def test_a_g3_bundle_is_half_unit_rows_for_the_ledger_and_one_scorer_bundle_per_size_tier(tmp_path):
    import score
    rows = [trade(D, f"09:{40 + i}:10", "long" if i % 2 else "short") for i in range(9)]
    mult = [0.5, 1.0, 1.5] * 3
    half = G.apply(rows, "G3", mult)
    tr = G.tier_rows(half)
    assert {n: len(v) for n, v in tr.items()} == {"x0.5": 3, "x1": 3, "x1.5": 3}
    for m, n in G.TIERS:                                             # every source trade ONCE, in the tier of its multiplier
        assert [{k: v for k, v in t.items() if k != "gate_mult"} for t in tr[n]] == [r for r, x in zip(rows, mult) if x == m]
        assert {t["gate_mult"] for t in tr[n]} == {m} and all("gate_unit" not in t and "gate_units" not in t for t in tr[n])
    d = G.write_bundle(tmp_path / "gate_x_G3", "gate_x_G3", half, {"strategy": "gates.G3"})
    assert sorted(p.name for p in d.iterdir()) == ["half_units.json", "run.json", "x0.5", "x1", "x1.5"]
    run = json.loads((d / "run.json").read_text())
    assert json.loads((d / "half_units.json").read_text()) == half and run["trades"] == 18 and run["tiers"] == {"x0.5": 3, "x1": 3, "x1.5": 3}
    for m, n in G.TIERS:
        sub = json.loads((d / n / "run.json").read_text())
        assert json.loads((d / n / "trades.json").read_text()) == tr[n] and score.load_trades(str(d / n)).n == 3
        assert (sub["tier"], sub["gate_mult"], sub["parent"], sub["trades"], sub["range"]) == (n, m, "gate_x_G3", 3, run["range"])
    assert [(m["src"], m["micros"], m["label"]) for m in G._members(d, "gate_x_G3", "nyam", 20)] == [
        (str(d / "x0.5"), 20, "gate_x_G3|x0.5"), (str(d / "x1"), 40, "gate_x_G3|x1"), (str(d / "x1.5"), 60, "gate_x_G3|x1.5")]
    # an empty tier has no bundle and is no member; a bundle that is not written yet lists all three
    d2 = G.write_bundle(tmp_path / "gate_y_G3", "gate_y_G3", G.apply(rows, "G3", [1.0] * 9), {})
    assert sorted(p.name for p in d2.iterdir()) == ["half_units.json", "run.json", "x1"]
    assert G._members(d2, "gate_y_G3", "pm", 15) == [{"src": str(d2 / "x1"), "sess": "pm", "micros": 30, "label": "gate_y_G3|x1"}]
    assert [m["micros"] for m in G._members(tmp_path / "nope", "k", "pm", 15)] == [15, 30, 45]
    assert [m["micros"] for m in G._members(tmp_path / "nope", "k", "pm", 15, tiers=["x1", "x1.5"])] == [30, 45]
    # a G1 / G2 list: trades.json, read by the scorer as before
    d3 = G.write_bundle(tmp_path / "gate_z_G1", "gate_z_G1", G.apply(rows, "G1", ["keep", "skip", "keep"] * 3), {})
    assert sorted(p.name for p in d3.iterdir()) == ["run.json", "trades.json"] and score.load_trades(str(d3)).n == 6


def _models(res: dict, kind: str) -> dict:
    keys = ([f"p{k}" for k in range(1, 6)] + ["bust5"]) if kind == "eval" else ["e_net_40", "p_pay_20", "p_pay_40", "p_pay_60", "p_bust_pre_first",
                                                                              "med_days_first"]
    return {m: {k: v[k] for k in keys} for m, v in res["models"].items()}


def test_g3_scoring_is_neutral_an_all_x1_gate_and_any_tier_split_at_equal_micros_score_exactly_like_the_pick(tmp_path):
    """The verifier's finding (half-unit rows at half micros do NOT score like the position) as a regression test, on the real
    in-sample trade lists at every cell: EQUALITY with the ungated pick only, no level is printed or asserted."""
    import score
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    rng = np.random.default_rng(9)
    cells = 0
    for pick in G.PICKS:
        try:
            rows, _ = G.pick_rows(pick)
        except FileNotFoundError as e:
            pytest.skip(f"trade list not available: {e}")
        runs = tmp_path / pick
        k1, k2 = G.gate_key(pick, "G3"), G.gate_key(pick, "G3", 1)
        G.write_bundle(runs / k1, k1, G.apply(rows, "G3", [1.0] * len(rows)), {})                # the ungated pick as a G3 bundle
        G.write_bundle(runs / k2, k2, G.apply(rows, "G3", [float(m) for m in rng.choice([0.5, 1.0, 1.5], len(rows))]), {})
        for slot in G.slots(pick):
            c = G.cell(pick, "G3", slot, runs)
            fn = score.score_eval if c["kind"] == "eval" else score.score_funded
            m0 = c["base_kw"]["micros"]
            base = fn(c["base"], **c["base_kw"], boots=0)
            assert [m["micros"] for m in c["real"]] == [m0] and len(c["nulls"][0]) == 3
            flat = fn(c["real"], **c["gate_kw"], boots=0)                                       # all x1 = one member at the pick's micros
            split = fn([{**m, "micros": m0} for m in c["nulls"][0]], **c["gate_kw"], boots=0)   # three tier members, equal micros
            for other in (flat, split):
                assert _models(other, c["kind"]) == _models(base, c["kind"]), (pick, slot)
                if c["kind"] == "eval":
                    assert other["walk"] == base["walk"] and other["n_trades"] == base["n_trades"]
                else:
                    assert other["trades"] == base["trades"] and other.get("compliance") == base.get("compliance")
            assert [m["trades"] > 0 for m in split["members"]] == [True, True, True]
            cells += 1
    assert cells == 8                                                # 6 approved cells + straddle #9 (max_day_tr = 1) + the 300K PA bar


TOY_SLOTS = {"toy_eval": dict(kind="eval", firm="lucid", key="toy-tf15#1", sess="nyam", micros=10,
                              rules={"day_lock": 0, "day_take": 0, "day_stop": 0, "max_day_tr": 0, "target_take": 1}),
             "toy_funded": dict(kind="funded", firm="flex", key="toy-tf15#1", sess="nyam", micros=10,
                                rules={"day_take": 0, "day_lock": 0, "day_stop": 0, "max_day_tr": 0}, policy=500)}


def test_lift_cell_is_lift_vs_control_for_g1_g2_and_the_same_paired_difference_on_the_tier_portfolios_for_g3(toy, monkeypatch):
    import score
    tmp, rows, kw = toy
    monkeypatch.setattr(G, "EXTRA_SLOTS", TOY_SLOTS)
    G.run_all(**kw)
    pick, ckw = "toy-tf15_c1", dict(runs_dir=kw["runs_dir"], trades_dir=kw["trades_dir"])
    n_nyam = sum(1 for r in rows if S.session_of(r["entry_ms"]) == "nyam")
    run = json.loads((kw["runs_dir"] / "gate_toy-tf15_c1_G3" / "run.json").read_text())
    assert set(run["gate"]["cells"]) == {"toy_eval", "toy_funded"}   # the cells written with the bundle = cell() afterwards
    for slot in TOY_SLOTS:
        assert run["gate"]["cells"][slot] == G.cell(pick, "G3", slot, **ckw)
        c = G.cell(pick, "G1", slot, **ckw)
        a = G.lift_cell(pick, "G1", slot, boots=200, **ckw)
        want = score.lift_vs_control(c["real"], c["nulls"], c["gate_kw"]["firm"], c["gate_kw"]["rules"], micros=10, sess="nyam", mode="direct",
                                     kind=c["kind"], boots=200, **({"policy": 500} if c["kind"] == "funded" else {}))
        assert a == want and a["K"] == 2 and "lift" in a
        b = G._lift_direct(c["kind"], c["real"], c["nulls"], c["gate_kw"], boots=200)          # the G3 path on single sources
        assert b["models"] == a["models"] and (b["lift"], b["lift_gt0"], b["K"]) == (a["lift"], a["lift_gt0"], a["K"])
        assert b["ctrl_trades"] == a["ctrl_trades"]
        assert any(m["lift" if c["kind"] == "eval" else "lift_e40"] != 0 for m in a["models"].values())      # something to compare
        g3 = G.lift_cell(pick, "G3", slot, boots=200, **ckw)
        assert g3["K"] == 2 and g3["real_trades"] == n_nyam and g3["ctrl_trades"] == [n_nyam, n_nyam]       # G3 never drops a trade
        assert set(g3["models"]) == set(a["models"])
        sc = {w: G.score_cell(pick, "G3", slot, w, boots=0, **ckw) for w in ("real", 1, 2, "base", "base_same_size")}
        for w, r in sc.items():
            assert (r["n_trades"] if c["kind"] == "eval" else r["trades"]) == n_nyam
            tag = {"real": "_G3|x", 1: "_G3-perms1|x", 2: "_G3-perms2|x"}.get(w)
            assert [m["micros"] for m in r["members"]] == ([5, 10, 15] if tag else [10]) and all(tag is None or tag in m["label"] for m in r["members"])
        one_metric, each = ("p5", "ctrl_p5_each") if c["kind"] == "eval" else ("e_net_40", "ctrl_e40_each")
        for b, m in g3["models"].items():                            # the G3 lift = real - mean of ITS OWN two nulls, model by model
            ctrl = [sc[w]["models"][b][one_metric] for w in (1, 2)]
            assert m[each] == ctrl and m["real_p5" if c["kind"] == "eval" else "real_e40"] == sc["real"]["models"][b][one_metric]
            assert m["lift" if c["kind"] == "eval" else "lift_e40"] == pytest.approx(sc["real"]["models"][b][one_metric] - np.mean(ctrl), abs=1e-12)
        assert any(sc[w]["models"][b][one_metric] != sc["real"]["models"][b][one_metric] for w in (1, 2) for b in g3["models"])
        g1 = {w: G.score_cell(pick, "G1", slot, w, boots=0, **ckw)["members"][0] for w in ("real", 1, 2)}
        assert [m["micros"] for m in g1.values()] == [10, 10, 10]
        assert [m["label"] for m in g1.values()] == ["gate_toy-tf15_c1_G1", "gate_toy-tf15_c1_G1-perms1", "gate_toy-tf15_c1_G1-perms2"]


# ------------------------------------------------------------------ run_all: ledger row before bundle, robustness stage

def test_a_refused_ledger_row_leaves_no_bundle_and_a_recorded_key_without_bundle_is_rebuilt(toy, monkeypatch):
    tmp, rows, kw = toy
    keys = [j["key"] for j in G.jobs()]
    record = screen.record_gate

    def refuse(key, *a, **k):
        if key == "gate_toy-tf15_c1_G2-perms1":
            raise screen.CapExceeded("screening-run cap reached (test)")
        return record(key, *a, **k)

    monkeypatch.setattr(screen, "record_gate", refuse)
    with pytest.raises(screen.CapExceeded):
        G.run_all(**kw)
    assert [r["key"] for r in screen.read_ledger(kw["ledger"])] == keys[:4]
    assert sorted(p.name for p in kw["runs_dir"].iterdir()) == sorted(keys[:4])      # no uncounted bundle, no temporary directory
    monkeypatch.setattr(screen, "record_gate", record)
    shutil.rmtree(kw["runs_dir"] / keys[2])                          # a recorded key whose bundle is gone / half written
    (kw["runs_dir"] / keys[0] / "trades.json").unlink()
    want = (kw["runs_dir"] / keys[1] / "run.json").read_bytes()
    out = G.run_all(**kw)
    assert out == {"ran": keys[4:], "skipped": keys[:4], "restored": [keys[0], keys[2]]}
    led = screen.read_ledger(kw["ledger"])
    assert [r["key"] for r in led] == keys and screen.cap_used(led) == 9             # no second row for a rebuilt bundle
    assert all(G._complete(kw["runs_dir"] / k) for k in keys) and sorted(p.name for p in kw["runs_dir"].iterdir()) == sorted(keys)
    assert (kw["runs_dir"] / keys[1] / "run.json").read_bytes() == want              # an intact bundle is not rewritten
    real = G.run_gate(rows, "G1", kw["features"]("G1", None), calendar=kw["calendar"])
    assert json.loads((kw["runs_dir"] / keys[0] / "trades.json").read_text()) == real["trades"]


def test_the_execution_guard_stage_reruns_screened_gates_only_and_is_not_counted(toy):
    tmp, rows, kw = toy
    with pytest.raises(RuntimeError, match="SCREENED gates only"):
        G.run_all(guard_ms=1000, **kw)
    assert not kw["runs_dir"].exists()
    for bad in (-5, 0.5):
        with pytest.raises((S.LookAheadError, ValueError)):
            G.run_all(guard_ms=bad, **kw)
    G.run_all(**kw)
    out = G.run_all(guard_ms=1000, **kw)
    keys = [j["key"] for j in G.jobs(guard_ms=1000)]
    assert out == {"ran": keys, "skipped": [], "restored": []} and len(keys) == 9
    assert keys[:3] == ["gate_toy-tf15_c1_G1-guard1000", "gate_toy-tf15_c1_G1-guard1000-perms1", "gate_toy-tf15_c1_G1-guard1000-perms2"]
    led = screen.read_ledger(kw["ledger"])
    assert len(led) == 18 and screen.cap_used(led) == 9 and {r["stage"] for r in led[9:]} == {"gate_guard"}      # not counted in the cap
    st = G.status(kw["ledger"])
    assert (st["guard_runs"], st["done"], st["planned"], st["cap_used"], st["cap_after_pending"]) == (9, 9, 9, 9, 9)
    cal = kw["calendar"]
    for g in G.GATES:
        f = "half_units.json" if g == "G3" else "trades.json"
        base = G.run_gate(rows, g, kw["features"](g, None), calendar=cal)
        late = G.run_gate(rows, g, kw["features"](g, None), calendar=cal, params={"guard_ms": 1000})
        k = G.gate_key("toy-tf15_c1", g, None, 1000)
        run = json.loads((kw["runs_dir"] / k / "run.json").read_text())
        assert json.loads((kw["runs_dir"] / k / f).read_text()) == late["trades"]          # the gate with its clock 1 s earlier
        assert run["inputs"]["guard_ms"] == 1000 and run["gate"]["stage"] == "gate_guard" and "guard_check" not in run["gate"]["counts"]
        nl = G.run_null(rows, g, kw["features"](g, 2), late, key=k, seed=2, calendar=cal, params={"guard_ms": 1000})
        assert json.loads((kw["runs_dir"] / G.gate_key("toy-tf15_c1", g, 2, 1000) / f).read_text()) == nl["trades"]
        # the screen bundle already says how many verdicts need the first second (a count, no trade list)
        chk = json.loads((kw["runs_dir"] / G.gate_key("toy-tf15_c1", g) / "run.json").read_text())["gate"]["counts"]
        assert chk["guard_check"] == {"guard_ms": 1000, "verdicts_changed": sum(x != y for x, y in zip(base["cats"], late["cats"])),
                                      "no_signal": late["counts"]["no_signal"]}
        assert chk["entry_timing"] == G.entry_timing(rows, "15")
        if g != "G3":
            assert chk["guard_check"]["verdicts_changed"] > 0        # the toy list has fills 40 ms after a minute boundary
    assert G.run_all(guard_ms=1000, **kw) == {"ran": [], "skipped": keys, "restored": []}
    assert G.main(["plan"]) == 0


# ------------------------------------------------------------------ the REAL feature table and the REAL C2 loader

def _real_case(n_days=6, picks=("donchian-tf15_c1", "straddle-tf30_c10")):
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    days = set(screen.SMOKE_DAYS[:n_days])
    try:
        rows = [r for p in picks for r in G.pick_rows(p)[0] if r["date"] in days]
        G._features("G1")(dt.date.fromisoformat(min(days)))
    except FileNotFoundError as e:
        pytest.skip(f"feature cache / trade list not available: {e}")
    return rows


def _poisoned(load, cut_ns, value=None):
    """`load` with every row that is NOT usable strictly before `cut_ns` replaced by `value` (None: the table ends there)."""
    def f(d):
        t = load(d)
        if t is None:
            return None
        fut = np.asarray(t.usable_ns) >= cut_ns
        if value is None:
            n = int((~fut).sum())
            return S.Features(t.usable_ns[:n], {c: v[:n] for c, v in t.cols.items()})
        return S.Features(t.usable_ns, {c: (v if c == "t_utc" else np.where(fut, value, v).astype(v.dtype)) for c, v in t.cols.items()})
    return f


def _leak(load):
    """A one-minute LOOK-AHEAD: every row claims to be usable (and stamped) one minute before it really is."""
    def f(d):
        t = load(d)
        return None if t is None else S.Features(np.asarray(t.usable_ns) - MIN, {c: (v - 60 if c == "t_utc" else v) for c, v in t.cols.items()})
    return f


@pytest.mark.parametrize("seed", [None, 1])
def test_on_the_real_table_and_the_real_c2_null_no_row_that_is_not_usable_yet_can_change_a_signal(seed):
    rows = _real_case()
    assert len(rows) > 30
    for gate in G.GATES:
        load = G._features(gate, seed)
        base = G.signals(rows, gate, load)
        assert sum(s is not None for s in base) >= len(rows) // 3    # the check has something to protect
        leaked, caught = G.signals(rows, gate, _leak(load)), 0
        for r, b, lk in zip(rows, base, leaked):
            cut = int(r["entry_ms"]) * 10 ** 6
            assert G.signals([r], gate, load) == [b]                 # a signal depends on the trade's own day only
            for value in (None, np.nan, 9.0, -9.0):
                assert G.signals([r], gate, _poisoned(load, cut, value)) == [b], (gate, r["date"], r["entry_ms"], value)
            # POWER: under the one-minute look-ahead the same garbage DOES reach the signal
            caught += G.signals([r], gate, _leak(_poisoned(load, cut, 9.0))) != [lk]
        n_leak = sum(s is not None for s in leaked)
        assert n_leak >= len(rows) // 3 and caught >= 0.6 * n_leak, (gate, caught, n_leak)
        if gate != "G2":                                             # (a regime label often survives one minute; a float does not)
            both = [(a, b) for a, b in zip(base, leaked) if a is not None and b is not None]
            assert sum(a != b for a, b in both) >= 0.9 * len(both)
        # usable one minute early WITHOUT the stamp moving: the freshness law refuses every row
        early = lambda d, load=load: (lambda t: None if t is None else S.Features(np.asarray(t.usable_ns) - MIN, t.cols))(load(d))
        assert G.signals(rows, gate, early) == [None] * len(rows)


def test_the_real_c2_null_is_another_sessions_book_and_each_seed_is_another_donor():
    rows = _real_case()
    for gate in ("G1", "G3"):
        real, n1, n2 = (G.signals(rows, gate, G._features(gate, s)) for s in (None, 1, 2))
        for a, b in ((real, n1), (real, n2), (n1, n2)):
            both = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
            assert len(both) >= len(rows) // 4 and sum(x != y for x, y in both) >= 0.95 * len(both)
        # NaN stays NaN: the null has no signal where the real table has none (masked book, roll days)
        assert all(n is None for r, n in zip(real, n1) if r is None) and all(n is None for r, n in zip(real, n2) if r is None)
    real, n1 = (G.signals(rows, "G2", G._features("G2", s)) for s in (None, 1))
    assert all(n is None for r, n in zip(real, n1) if r is None)


def test_the_cells_written_with_a_g3_bundle_name_only_the_tiers_that_exist(tmp_path, monkeypatch):
    """30 sessions never reach the registered 60 values: every trade is x1, so the scorer gets ONE member (no empty tier)."""
    tmp, rows, kw = toy_kw(tmp_path, monkeypatch, n_days=30)
    monkeypatch.setattr(G, "EXTRA_SLOTS", TOY_SLOTS)
    G.run_all(gates=["G3"], **kw)
    for s in (None, 1, 2):
        d = kw["runs_dir"] / G.gate_key("toy-tf15_c1", "G3", s)
        run = json.loads((d / "run.json").read_text())
        assert run["tiers"] == {"x0.5": 0, "x1": len(rows), "x1.5": 0} and sorted(p.name for p in d.iterdir()) == ["half_units.json", "run.json", "x1"]
        c = run["gate"]["cells"]["toy_eval"]
        assert [m["src"].rsplit("/", 2)[-2:] for m in c["real"]] == [["gate_toy-tf15_c1_G3", "x1"]] and [len(n) for n in c["nulls"]] == [1, 1]
        assert c == G.cell("toy-tf15_c1", "G3", "toy_eval", kw["runs_dir"], trades_dir=kw["trades_dir"])
    import score
    r = G.score_cell("toy-tf15_c1", "G3", "toy_eval", "real", boots=0, runs_dir=kw["runs_dir"], trades_dir=kw["trades_dir"])
    b = G.score_cell("toy-tf15_c1", "G3", "toy_eval", "base", boots=0, runs_dir=kw["runs_dir"], trades_dir=kw["trades_dir"])
    assert _models(r, "eval") == _models(b, "eval") and r["walk"] == b["walk"]         # an all-x1 G3 IS the pick
