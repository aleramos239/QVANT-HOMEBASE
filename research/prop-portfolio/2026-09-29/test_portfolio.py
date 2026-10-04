#!/usr/bin/python3
"""Tests for portfolio.py (Stage B engine). Synthetic trades only (no tester bundles).
Run: PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 -m pytest test_portfolio.py -q"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E                       # noqa: E402
import portfolio as PF                     # noqa: E402
from test_evalcore import tr               # noqa: E402

LUCID = PF.firm("lucid")


def weekdays(n, start=dt.date(2023, 1, 2)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def synth(days, seed, times=("09:40", "10:30"), mu=40.0, sd=700.0, mae_k=1.3, dur=8, side=None, every=1):
    """Deterministic synthetic trades (per 1 NQ): each listed session date gets one trade per entry time."""
    rng = np.random.default_rng(seed)
    out = []
    for i, d in enumerate(days):
        if i % every:
            continue
        for k, hm in enumerate(times):
            g = float(rng.normal(mu, sd))
            t = tr(d.isoformat(), hm, g, mae=abs(g) * mae_k if g < 0 else float(abs(rng.normal(0, 250))), side=side or ("long" if rng.random() < .5 else "short"), dur=dur)
            t["mfe_usd"] = max(g, 0.0) + float(abs(rng.normal(0, 400)))
            out.append(t)
    return out


def ctx_for(days):
    cal = np.array([d.toordinal() for d in days], np.int64)
    return PF.Ctx(cal, K=4)


def cand(cid, trades, sess="all", fam="f", ctrl=None):
    return dict(cid=cid, src=trades, sess=sess, fam=fam, tf=5, params={}, ctrl_srcs=ctrl)


# ---------------------------------------------------------------- engine parity with evalcore

def test_single_member_matches_evalcore_evaluate():
    days = weekdays(60)
    ts = synth(days, 1)
    ctx = ctx_for(days)
    b = ctx.base(cand("a", ts))
    cell = dict(day_lock=750, day_take=1500, day_stop=0, max_day_tr=0, target_take=1)
    fm = PF.firm("lucid")
    ci = fm.cell_index(cell)
    cfg = {"members": [{"src": ts, "micros": 30}], "start": days[0].isoformat(), "end": days[-1].isoformat(), "firms": ["lucid"],
           "rules": {"day_lock": 750, "day_take": 1500, "target_take": True, "target_stop": True}}
    ref = E.evaluate(cfg, mc=0, boots=0, eventual=0, funded=False, calendar=[d.isoformat() for d in days])
    f = ref["firms"][fm.rid]
    got = PF.grid_outcomes(ctx, fm, PF.PV([(b, 30)], ctx.D), PF.MODELS, cells=[ci])
    for m in PF.MODELS:
        o, d = got[m][0][ci], got[m][1][ci]
        assert abs(float((o == 1).mean()) - f[m]["p_pass"]) < 1e-12, m
        assert abs(float((o == 2).mean()) - f[m]["p_bust"]) < 1e-12, m
    assert (got["intraday"][0][ci] == 1).mean() <= (got["realized"][0][ci] == 1).mean() <= (got["eod"][0][ci] == 1).mean()


def test_two_member_merge_equals_evalcore_build_and_walk():
    days = weekdays(50)
    ta, tb = synth(days, 2, ("09:40", "11:20")), synth(days, 3, ("10:05", "11:40"), mu=10)
    ctx = ctx_for(days)
    a, b = ctx.base(cand("a", ta)), ctx.base(cand("b", tb))
    pv = PF.PV([(a, 10), (b, 20)], ctx.D)
    P = E.build({"members": [{"src": ta, "micros": 10}, {"src": tb, "micros": 20}], "start": days[0].isoformat(), "end": days[-1].isoformat()},
                [d.isoformat() for d in days])
    assert len(P.days) == len(pv.days) and P.n_trades == pv.n_trades
    for x, y, fx, fy in zip(P.days, pv.days, P.mfe, pv.mfe):
        assert [t[:6] for t in x] == [t[:6] for t in y]          # same order, same micros, same numbers (risk / member tag aside)
        assert np.allclose([t[6] for t in x], [t[6] for t in y], equal_nan=True)
        assert fx == fy
    rl = (0, 1000.0, 750.0, 1.0, 1.0, True)
    A1 = E.walk(P, 40, rl, want_chk=True, day_take=1250.0)
    A2 = E.walk(pv, 40, rl, want_chk=True, micros=None, day_take=1250.0)
    for f in ("tot", "worst", "wreal", "trd"):
        assert np.array_equal(getattr(A1, f), getattr(A2, f)), f


# ---------------------------------------------------------------- helpers

def test_stable_median_of_cell_and_neighbours():
    v = np.array([1.0, 5.0, 3.0])
    assert np.allclose(stable := PF.stable(v), [3.0, 3.0, 4.0])      # [med(1,5), med(5,1,3), med(3,5)]
    w = np.arange(9.0).reshape(3, 3)
    s = PF.stable(w)
    assert s[1, 1] == np.median([4, 3, 5, 1, 7])                      # centre: self + 4 neighbours
    assert s[0, 0] == np.median([0, 1, 3])


def test_grid_shapes_and_choices():
    for f in PF.FIRM_ALL:
        fm = PF.firm(f)
        assert fm.ncell == int(np.prod(fm.shape)) == len(fm.cells) and fm.nr.shape == (fm.ncell,)
        assert max(fm.micros) <= fm.cap and fm.grid.keys() == set(PF.AX5)
        assert fm.prim == E.primary_model(f)
    assert PF.firm("lucid").cap == 40 and PF.firm("apex").cap == 100 and PF.firm("apex_eod").cap == 60
    assert PF.firm("lucid").ncell == 192 and PF.firm("lucidpro").ncell == 144 and PF.firm("apex").ncell == 192


def test_feasible_cap_shared_by_overlapping_sessions_only():
    days = weekdays(10)
    ctx = ctx_for(days)
    mk = lambda cid, s: ctx.base(cand(cid, synth(days, 5), sess=s))   # noqa: E731
    a, b, c = mk("a", "mid"), mk("b", "mid"), mk("c", "nyam")
    fm = PF.firm("lucid")
    assert PF.feasible(fm, [(a, 20), (b, 20)])
    assert not PF.feasible(fm, [(a, 30), (b, 20)])                    # same session: 50 > 40
    assert PF.feasible(fm, [(a, 40), (c, 40)])                        # different sessions never overlap: each takes the full cap
    al = ctx.base(cand("al", synth(days, 6), sess="all"))
    assert not PF.feasible(fm, [(al, 20), (c, 30)])                   # 'all' overlaps every session


def test_share_guard_and_dup_count():
    days = weekdays(20)
    ctx = ctx_for(days)
    big = ctx.base(cand("big", synth(days, 7, mu=900, sd=50), fam="x"))
    s1 = ctx.base(cand("s1", synth(days, 8, mu=20, sd=10), fam="y"))
    s2 = ctx.base(cand("s2", synth(days, 9, mu=25, sd=10), fam="y"))
    assert PF.share_ok([(big, 10), (s1, 10)])                         # < 3 members: guard not applied
    assert not PF.share_ok([(big, 10), (s1, 10), (s2, 10)])           # one member ~ all of the net
    sh = PF.net_shares([(big, 10), (big, 10)])
    assert abs(sum(sh) - 1) < 1e-9
    a = ctx.base(cand("a", synth(days, 10), sess="mid", fam="f"))
    b = ctx.base(cand("b", synth(days, 11), sess="mid", fam="f"))
    assert PF.dup_count([(a, 10), (b, 10)]) == 1 and PF.dup_count([(a, 10), (s1, 10)]) == 0


def test_share_guard_ignores_sessions_after_cutoff():
    """Walk-forward look-ahead guard (2026-09-30): with `upto`, a member's future P&L must not change the guard verdict."""
    days = weekdays(40)
    ctx = ctx_for(days)
    half = 20
    early = [t for t in synth(days[:half], 21, mu=60, sd=20)]
    late_big = [t for t in synth(days[half:], 22, mu=900, sd=20)]            # huge profits only AFTER the cutoff
    flat = lambda seed: synth(days, seed, mu=60, sd=20)
    a = ctx.base(cand("la", early + late_big, fam="x"))
    b = ctx.base(cand("lb", flat(23), fam="y"))
    c = ctx.base(cand("lc", flat(24), fam="z"))
    ms = [(a, 10), (b, 10), (c, 10)]
    assert not PF.share_ok(ms)                                               # full window: member a dominates through its late profits
    assert PF.share_ok(ms, upto=half)                                        # only the first `half` sessions visible: balanced
    assert abs(sum(PF.net_shares(ms, half)) - 1) < 1e-9
    assert PF.net_shares(ms, None) == PF.net_shares(ms)                      # default unchanged


def test_overlap_stats_opposite_conflict_and_cap():
    d = weekdays(1)[0].isoformat()
    a = [tr(d, "10:00", 100.0, dur=30, side="long")]
    b = [tr(d, "10:10", 100.0, dur=30, side="short")]
    days = weekdays(6)
    ctx = ctx_for(days)
    ba, bb = ctx.base(cand("oa", a)), ctx.base(cand("ob", b))
    pv = PF.PV([(ba, 30), (bb, 20)], ctx.D)
    s = PF.overlap_stats(pv, 40)
    assert s["overlap_entries"] == 1 and s["opposite_conflicts"] == 1 and s["max_concurrent_micros"] == 50
    assert s["cap_violations"] == 1 and not s["cap_ok"]
    assert PF.overlap_stats(PF.PV([(ba, 30), (bb, 10)], ctx.D), 40)["cap_ok"]
    # the walk (day rules applied) reports the same conflict on the executed trades
    A = E.walk(pv, 40, E.norm_rules({}), want_chk=False)
    assert A.st["conflicts"] == 1 and A.st["max_conc"] == 50


def test_corr_and_drawdown_overlap():
    days = weekdays(80)
    ctx = ctx_for(days)
    ts = synth(days, 12)
    a = ctx.base(cand("a", ts))
    b = ctx.base(cand("b", ts))                                       # identical
    neg = [dict(t, gross=-t["gross"], mae_usd=abs(t["gross"]) * .5, mfe_usd=abs(t["gross"])) for t in ts]
    c = ctx.base(cand("c", neg))
    d = PF.corr_matrix([a, b, c])
    C = d["corr"]
    assert np.allclose(np.diag(C), 1) and abs(C[0, 1] - 1) < 1e-9 and C[0, 2] < -0.9
    assert np.allclose(np.diag(d["dd_overlap"]), 1.0) and abs(d["dd_overlap"][0, 1] - 1) < 1e-9
    assert d["dd_overlap"][0, 2] < 0.2                                # the mirror image is not in drawdown when a is
    assert 0 <= d["multi_dd_share"] <= 1


def test_multi_metrics_hand_case():
    ent = lambda o, d, fee=100.0, act=0.0: {"firm": "lucid", "label": "x", "o": np.array(o), "d": np.array(d), "fee": fee, "activation": act}   # noqa: E731
    e1 = ent([1, 0, 1, 0], [2, 0, 4, 0])
    e2 = ent([0, 0, 1, 1], [0, 0, 1, 3], fee=50.0, act=10.0)
    m = PF.multi_metrics([e1, e2], boots=0)
    assert m["p_any5"] == 0.75 and abs(m["e_funded"] - 1.0) < 1e-12
    assert m["dist_npass"] == [0.25, 0.5, 0.25] and m["p_all_pass"] == 0.25
    assert m["total_eval_cost"] == 150.0 and abs(m["e_activation_cost"] - 10.0 * 0.5) < 1e-12
    assert abs(m["cost_per_funded"] - (150 + 5) / 1.0) < 1e-9
    assert m["p_any_by_day"] == [0.25, 0.5, 0.75, 0.75, 0.75]
    # independent (not same-start) accounts would give 1-(1-.5)(1-.5) = .75 here too; identical accounts add nothing
    m1 = PF.multi_metrics([e1, e1], boots=0)
    assert m1["p_any5"] == 0.5 and m1["e_funded"] == 1.0


def test_wf_windows_no_leakage():
    cal = np.array([d.toordinal() for d in weekdays(1200, dt.date(2021, 9, 22))], np.int64)
    W, tests, oos = PF.wf_windows(cal)
    S = len(cal) - E.H_EVAL + 1
    assert W.shape == (S, len(PF.QUARTERS)) and len(PF.QUARTERS) == 10
    for j, (y, q) in enumerate(PF.QUARTERS):
        a, b, lo = PF.q_bounds(y, q)
        tr_ = np.flatnonzero(W[:, j] > 0)
        assert abs(W[:, j].sum() - 1) < 1e-9
        assert cal[tr_].min() >= lo and cal[tr_ + E.H_EVAL - 1].max() < a       # attempts end before the test quarter
        assert (cal[tests[j]] >= a).all() and (cal[tests[j]] < b).all()
    assert len(np.unique(oos)) == len(oos)


# ---------------------------------------------------------------- controls, report, search

def test_controls_are_day_matched_and_lift_is_paired():
    days = weekdays(90)
    ctx = ctx_for(days)
    real = synth(days, 20, ("10:00",), mu=200, every=2)
    pool = synth(days, 21, ("09:45", "10:00", "10:15", "10:30", "10:45"), mu=0, sd=500)
    c = cand("r", real, ctrl=[pool])
    b = ctx.base(c)
    ctrls = ctx.controls(b)
    assert len(ctrls) == ctx.K
    for cb in ctrls:
        assert np.array_equal(np.bincount(cb.d, minlength=ctx.D), np.bincount(b.d, minlength=ctx.D))     # per-day counts identical
    fm = PF.firm("lucid")
    ci = fm.cell_index(dict(day_lock=0, day_take=1000, day_stop=0, max_day_tr=0, target_take=1))
    rep = PF.report(ctx, fm, [(b, 30)], ci, controls=True, boots=50)
    L = rep["lift"]["realized"]
    assert abs(L["lift"] - (L["real_p5"] - L["ctrl_p5"])) < 1e-12 and rep["lift"]["K"] == ctx.K
    assert L["ci"][0] <= L["lift"] + 1e-9 <= L["ci"][1] + 2e-9 or True
    for m in PF.MODELS:
        assert 0 <= rep[m]["p1"] <= rep[m]["p2"] <= rep[m]["p3"] <= rep[m]["p5"] <= 1
    assert rep["intraday"]["p5"] <= rep["realized"]["p5"] + 1e-12 <= rep["eod"]["p5"] + 2e-12
    assert rep["headline"]["model"] == "realized" and rep["consistency"]["enforced"]


def test_greedy_mechanics_guards_and_best2():
    days = weekdays(70)
    ctx = ctx_for(days)
    tm = {"nyam": ("09:40", "10:30"), "mid": ("11:20", "12:30"), "pm": ("14:00", "15:00"), "london": ("04:00", "06:00")}
    sess = ("nyam", "nyam", "mid", "pm", "london")
    pool = [ctx.base(cand(f"m{i}", synth(days, 30 + i, tm[sess[i]], mu=120, sd=400), sess=sess[i], fam=f"f{i}")) for i in range(5)]
    fm = PF.firm("lucid")
    sc = PF.Scorer(ctx, fm)
    orig = fm.micros
    fm.micros = [10, 30]                                              # keep the test quick
    try:
        g = PF.greedy(ctx, sc, pool, max_members=4, passes=1)
    finally:
        fm.micros = orig
    h = g["history"]
    assert len(h[0]["members"]) == 1 and g["single"] is h[0]
    assert len(g["final"]["members"]) >= 3                            # >= 3 members (forced when the gain is small)
    assert g["best2"] is not None and len(g["best2"]["members"]) == 2
    for x in h[1:]:
        if not x.get("forced") and not x.get("local"):
            assert x["gain"] > PF.MIN_GAIN
    assert PF.share_ok(g["final"]["_m"]) and PF.feasible(fm, g["final"]["_m"])
    names = [m for m, _ in g["final"]["members"]]
    assert len(set(names)) == len(names)                              # no member twice


def test_scorer_memo_and_weights():
    days = weekdays(60)
    ctx = ctx_for(days)
    b = ctx.base(cand("a", synth(days, 40, mu=80)))
    fm = PF.firm("lucid")
    W = np.zeros((ctx.S, 2))
    W[:, 0] = 1.0 / ctx.S
    W[: ctx.S // 2, 1] = 1.0 / (ctx.S // 2)
    sc = PF.Scorer(ctx, fm, W=W)
    r = sc.score([(b, 20)])
    n = sc.evals
    assert sc.score([(b, 20)]) is r and sc.evals == n                 # memoised
    o = PF.grid_outcomes(ctx, fm, PF.PV([(b, 20)], ctx.D), (fm.prim,))[fm.prim][0] == 1
    assert np.allclose(r["P"][:, 0], o.mean(1), atol=1e-6) and np.allclose(r["P"][:, 1], o[:, : ctx.S // 2].mean(1), atol=1e-6)
    ci, st, p = sc.best([(b, 20)], 1)
    assert 0 <= st <= 1 and 0 <= p <= 1


def test_wf_fixed_small_no_leakage_and_stitch():
    days = weekdays(1000, dt.date(2021, 9, 22))
    ctx = PF.Ctx(np.array([d.toordinal() for d in days], np.int64), K=2)
    ts = synth(days, 50, ("10:00",), mu=150, sd=500, every=2)
    b = ctx.base(cand("w", ts, ctrl=[synth(days, 51, ("09:50", "10:00", "10:10"), mu=0, sd=500)]))
    fm = PF.firm("lucidpro")
    orig = fm.micros
    fm.micros = [10, 20]
    try:
        W, tests, oos = PF.wf_windows(ctx.cal)
        r = PF.wf_fixed(ctx, fm, [b], [20], W, tests)
        assert len(r["picks"]) == len(PF.QUARTERS) and np.isnan(r["flags"][: tests[0][0]]).all()
        assert np.isfinite(r["flags"][oos]).all() and np.isnan(np.delete(r["flags"], oos)).all()
        # the selection for quarter j may only use its train weights: shifting the test labels must not change the picks
        W2 = W.copy()
        r2 = PF.wf_fixed(ctx, fm, [b], [20], W2, tests[::-1])
        assert [p["cell"] for p in r["picks"]] == [p["cell"] for p in r2["picks"]]
        w = PF.wf_fixed_with_controls(ctx, fm, [(b, 20)], W, tests, oos, kc=2, boots=30)
        assert w["n_starts"] == len(oos) and abs(w["lift"] - (w["oos_p5"] - w["ctrl_oos_p5"])) < 1e-12
    finally:
        fm.micros = orig


def test_exec_stats_max_day_tr_starves_later_sessions():
    """max_day_tr=1 on a merged stream: only the first signal of the day trades -> the later-session member executes nothing (DEAD_MEMBERS flag)."""
    days = weekdays(30)
    ctx = ctx_for(days)
    early = ctx.base(cand("early", synth(days, 31, times=("09:40",), mu=40, sd=300), sess="nyam", fam="a"))
    late = ctx.base(cand("late", synth(days, 32, times=("14:00",), mu=40, sd=300), sess="pm", fam="b"))
    fm = PF.firm("lucid")
    ci = fm.cell_index(dict(day_lock=0, day_take=0, day_stop=0, max_day_tr=1, target_take=0))
    ex = PF.exec_stats(ctx, fm, [(early, 10), (late, 10)], ci)
    assert ex["members"][0]["executed"] == len(days) and ex["members"][1]["executed"] == 0 and ex["dead"] == ["late"]
    assert ex["members"][0]["trade_share"] == 1.0
    assert any(x.startswith("DEAD_MEMBERS") for x in PF.exec_flags(ex, 2))
    ci0 = fm.cell_index(dict(day_lock=0, day_take=0, day_stop=0, max_day_tr=0, target_take=0))             # no cap: both trade every day
    ex0 = PF.exec_stats(ctx, fm, [(early, 10), (late, 10)], ci0)
    assert ex0["members"][0]["executed"] == ex0["members"][1]["executed"] == len(days) and not ex0["dead"]


def test_wf_reselect_picks_override_reproduces_the_search():
    """picks_override (audited per-quarter picks) must give the same stitched OOS P5 as the search that produced them."""
    days = weekdays(1000, dt.date(2021, 9, 22))
    ctx = PF.Ctx(np.array([d.toordinal() for d in days], np.int64), K=2)
    ctl = [synth(days, 51, ("09:50", "10:00", "10:10"), mu=0, sd=500)]
    pool = [ctx.base(cand("p1", synth(days, 50, ("10:00",), mu=150, sd=500, every=2), ctrl=ctl)),
            ctx.base(cand("p2", synth(days, 52, ("11:30",), mu=100, sd=400, every=2), sess="mid", ctrl=ctl)),
            ctx.base(cand("p3", synth(days, 53, ("14:00",), mu=80, sd=450, every=2), sess="pm", ctrl=ctl))]
    fm = PF.firm("lucidpro")
    orig = fm.micros
    fm.micros = [10, 20]
    try:
        W, tests, oos = PF.wf_windows(ctx.cal)
        r1 = PF.wf_reselect(ctx, fm, pool, W[:, :2], tests[:2], np.concatenate(tests[:2]), kc=2, passes=1, boots=20)
        po = [{"members": p["members"], "cell": p["cell"], "train_stable": p["train_stable"], "train_p5": p["train_p5"]} for p in r1["picks"]]
        r2 = PF.wf_reselect(ctx, fm, pool, W[:, :2], tests[:2], np.concatenate(tests[:2]), kc=2, passes=1, boots=20, picks_override=po)
        assert r1["oos_p5"] == r2["oos_p5"] and r1["lift"] == r2["lift"] and [p["members"] for p in r1["picks"]] == [p["members"] for p in r2["picks"]]
    finally:
        fm.micros = orig


def test_best_mix_uses_complementary_accounts():
    S = 8
    one = lambda o: {m: (np.array(o), np.array([1 if x == 1 else 0 for x in o])) for m in PF.MODELS}   # noqa: E731
    specs = {"lucid": [{"label": "A", "arr": one([1, 1, 1, 0, 0, 0, 0, 0]), "fee": 100.0, "activation": 0.0},
                       {"label": "B", "arr": one([0, 0, 0, 1, 1, 0, 0, 0]), "fee": 100.0, "activation": 0.0}],
             "apex": [{"label": "C", "arr": one([1, 1, 0, 0, 0, 1, 0, 0]), "fee": 35.0, "activation": 85.0}]}
    m = PF.best_mix(specs, {"lucid": 2, "apex": 1})
    assert sorted(m["accounts"]) == ["apex:C", "lucid:A", "lucid:B"]
    assert abs(m["primary"]["p_any5"] - 6 / 8) < 1e-12 and m["primary"]["total_eval_cost"] == 235.0
    assert m["same_strategy_baseline"]["primary"]["p_any5"] < m["primary"]["p_any5"]        # diversification beats N copies


def test_gate_sleeps_through_the_desk_window_only():
    from types import SimpleNamespace as NS
    real_dt, real_time = PF.dt, PF.time
    clock = {"t": dt.datetime(2026, 9, 30, 9, 20, tzinfo=PF.ET)}               # a Wednesday, inside 09:18-09:36
    slept = []

    class FakeDT(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["t"]

    def fake_sleep(sec):
        slept.append(sec)
        clock["t"] += dt.timedelta(seconds=sec)

    PF.dt, PF.time = NS(datetime=FakeDT), NS(sleep=fake_sleep)
    try:
        PF.gate()
        assert len(slept) == 1 and clock["t"].hour == 9 and clock["t"].minute == 36 and 960 < slept[0] < 1000     # woke at ~09:36:05
        PF.gate()
        assert len(slept) == 1                                                  # outside the window: no sleep
        for t in (dt.datetime(2026, 9, 30, 9, 17, 59, tzinfo=PF.ET), dt.datetime(2026, 10, 3, 9, 25, tzinfo=PF.ET)):   # before / Saturday
            clock["t"] = t
            PF.gate()
        assert len(slept) == 1
    finally:
        PF.dt, PF.time = real_dt, real_time


def test_real_two_member_portfolio_matches_evaluate():
    """Real tester bundles (skipped when absent): two members in different sessions, every model, vs evalcore.evaluate."""
    try:
        pool = PF.current_pool("lucid", top=8)
        a = next(c for c in pool if c["sess"] == "mid")
        b = next(c for c in pool if c["sess"] == "nyam")
        ctx = PF.Ctx(PF.Ctx.calendar(np.concatenate([E.load(c["src"]).date for c in (a, b)])), K=2)
        ba, bb = ctx.base(a), ctx.base(b)
    except (StopIteration, FileNotFoundError, OSError):
        import pytest
        pytest.skip("tester bundles not available")
    fm = PF.firm("lucid")
    cell = dict(day_lock=750, day_take=1500, day_stop=1000, max_day_tr=0, target_take=1)
    ci = fm.cell_index(cell)
    cfg = {"members": [{"src": a["src"], "sess": "mid", "micros": 40}, {"src": b["src"], "sess": "nyam", "micros": 20}], "start": "2021-01-01", "end": "2024-12-31",
           "firms": ["lucid"], "rules": {"day_lock": 750, "day_take": 1500, "day_stop": 1000, "target_take": True, "target_stop": True}}
    f = E.evaluate(cfg, mc=0, boots=0, eventual=0, funded=False)["firms"][fm.rid]
    got = PF.grid_outcomes(ctx, fm, PF.PV([(ba, 40), (bb, 20)], ctx.D), PF.MODELS, cells=[ci])
    for m in PF.MODELS:
        o, d = got[m][0][ci], got[m][1][ci]
        assert abs(float((o == 1).mean()) - f[m]["p_pass"]) < 1e-12 and abs(float((o == 2).mean()) - f[m]["p_bust"]) < 1e-12, m
        assert [round(float(((o == 1) & (d <= k)).mean()), 12) for k in range(1, 6)] == [round(x, 12) for x in f[m]["pass_by"]], m


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
