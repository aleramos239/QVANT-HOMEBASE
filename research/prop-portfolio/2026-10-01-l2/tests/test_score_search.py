"""score.py searches vs R's own: search_rules == a3p3.search3 / wf_offline.search_ps (pass-3 grids, stable pick), search_funded ==
funded.search, the control modes of lift_vs_control, and the L/apex300.py backend (Apex Legacy 300K PA)."""
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402

pytestmark = pytest.mark.usefixtures("trades_tmp")      # exports go to a directory of this module's own, never to L/trades

E, F, P = S.E, S.F, S.P
KEY, SRC, SESS = "hm2-straddle-tf30#10", S.BASELINE["flex_eval"]["src"], "nyam"
KEY2, SRC2, SESS2 = "fp-donchian-tf15#10", S.BASELINE["pro_dll_funded"]["src"], "pm"       # several trades a day: every rule axis bites


@pytest.fixture(scope="module")
def files():
    for k, s in ((KEY, SRC), (KEY2, SRC2)):
        S.export_bundle(s, S.export_name(k))
    return {KEY: "file:" + S.export_name(KEY), KEY2: "file:" + S.export_name(KEY2)}


@pytest.fixture(scope="module")
def rmods():
    """R's pass-2/3 search modules. Importing them registers lucidpro* in evalcore.FIRMS (R's own side effect; restored at the end)."""
    firms0 = dict(E.FIRMS)
    import a3_pass2 as A2
    import a3_rules as A1
    import a3p3 as P3
    import screen_analyze as SA
    import wf_offline as WF
    yield A1, A2, P3, SA, WF
    E.FIRMS.clear()
    E.FIRMS.update(firms0)


def _native_port(A2, SA, src, sess):
    t = A2.load_src(src)
    cal = SA.cal_for(t)
    return A2.port_of(t, np.flatnonzero(t.sess == E.SESS_CODE[sess]), cal), len(cal)


def test_grids_are_Rs(rmods):
    A1, A2, P3, SA, WF = rmods
    assert list(S.AX) == list(A2.AX)
    for f in S.EVAL_FIRMS:
        assert S.EVAL_GRIDS[f] == A2.GR[f], f
        assert S.P.firm(f).prim == E.primary_model(f)
    v = np.random.default_rng(0).random((4, 3, 4, 3, 2, 2))
    nr = np.random.default_rng(1).integers(0, 5, v.shape).astype(float)
    assert np.array_equal(S.stable(v), A1.stable(v)) and S.pick(v, nr) == tuple(int(i) for i in A2.pick(v, nr))
    assert S.pick(A1.stable(v), nr) == tuple(int(i) for i in A2.pick(A1.stable(v), nr))


@pytest.mark.parametrize("key,src,sess,firms", [(KEY, SRC, SESS, S.EVAL_FIRMS), (KEY2, SRC2, SESS2, ("lucid", "apex"))])
def test_search_rules_identical_to_a3p3(files, rmods, key, src, sess, firms):
    A1, A2, P3, SA, WF = rmods
    port, D = _native_port(A2, SA, src, sess)
    for firm in firms:
        prim = E.primary_model(firm)
        ref = P3.search3(port, D, firm, prim)
        mine = S.search_rules(files[key], firm, sess=sess, boots=0, keep_arrays=True)
        assert tuple(mine["shape"]) == ref["shape"] and mine["walks"] == ref["walks"]
        assert np.array_equal(mine["P5"], ref["P5"]) and np.array_equal(mine["B5"], ref["B5"]), firm
        assert np.array_equal(mine["P1"], ref["P1"]) and np.array_equal(mine["P3"], ref["P3"]) and np.array_equal(mine["nr"], ref["nr"])
        for k, mod in enumerate(P3.M3):                             # R's picks: stable P5 per model, ties fewer rules / smaller size
            ci = A2.pick(A1.stable(ref["P5"][k]), ref["nr"])
            pk = mine["picks"][f"p5_{mod}"]
            assert tuple(pk["index"]) == tuple(int(i) for i in ci) and pk["rules"] == dict(zip(A2.AX, P3.cell_of(firm, ci)))
            assert pk["stab"] == float(A1.stable(ref["P5"][k])[ci]) and pk["models"][mod]["p5"] == float(ref["P5"][k][ci])
            own, A = P3.eval_cell3(port, D, firm, P3.cell_of(firm, ci))
            for m2 in P3.M3:
                assert pk["models"][m2] == S._detail(*own[m2], 0)
            assert pk["net_rules"] == float(A.tot.sum())
        for nm, arr in (("speed_p1", "P1"), ("speed_p3", "P3")):
            ci = A2.pick(A1.stable(ref[arr]), ref["nr"])
            assert tuple(mine["picks"][nm]["index"]) == tuple(int(i) for i in ci)
        assert mine["picks"]["primary"] is mine["picks"][f"p5_{prim}"]
        assert len(mine["rows"]) == mine["cells"] == int(np.prod(ref["shape"]))
        row = mine["rows"][137]
        ci = tuple(S.EVAL_GRIDS[firm][a].index(row[a]) for a in S.AX)
        assert row["p5_realized"] == float(ref["P5"][1][ci]) and row["stab_eod"] == float(A1.stable(ref["P5"][0])[ci])


def test_search_rules_reproduces_the_approved_flex_rules(files):
    r = S.search_rules(files[KEY], "lucid", sess=SESS, boots=0)
    assert r["picks"]["primary"]["rules"] == {"micros": 40, "day_lock": 750, "day_take": 1500, "day_stop": 0, "max_day_tr": 0, "target_take": 1}
    best = r["picks"]["primary"]
    one = S.score_eval(files[KEY], "lucid", best["rules"], sess=SESS, boots=0)
    assert one["p5"] == best["models"]["realized"]["p5"] == pytest.approx(0.6918392204628502, abs=1e-12)
    assert one["models"]["intraday"]["p5"] == best["models"]["intraday"]["p5"]       # the intraday bound is always carried along


def test_search_ps_layout_matches_wf_offline(files, rmods):
    """keep_arrays=True returns the per-start pass flags in wf_offline.search_ps's layout, so R's walk-forward reducers
    (windows / reduce_cfg / pick_across) run on it unchanged."""
    A1, A2, P3, SA, WF = rmods
    port, D = _native_port(A2, SA, SRC2, SESS2)
    models0 = A2.MODELS
    try:
        PS, nr, shape, walks = WF.search_ps(port, D, "lucidpro_nodll", S.MODELS)
    finally:
        A2.MODELS = models0
    mine = S.search_rules(files[KEY2], "lucidpro_nodll", sess=SESS2, boots=0, keep_arrays=True)
    assert mine["PS"].shape == PS.shape and np.array_equal(mine["PS"], PS) and np.array_equal(mine["nr"], nr) and tuple(mine["shape"]) == shape
    W, tests, oos = WF.windows(mine["cal"])
    a, b = WF.reduce_cfg(mine["PS"], mine["nr"], shape, W, tests, oos, S.MODELS), WF.reduce_cfg(PS, nr, shape, W, tests, oos, S.MODELS)
    assert a == b and len(a["realized"]["q"]) == len(WF.QUARTERS) == 10
    assert a["realized"]["full"]["cell"] == int(np.ravel_multi_index(mine["picks"]["p5_realized"]["index"], shape))


def test_walk_forward_identical_to_wf_offline_task(files, rmods):
    """score.walk_forward == R's wf_offline.task + agg_task on a native family grid (2 cells of hm2-straddle-tf30, nyam, with
    kc = 2 day-matched control replicates drawn from R's own control pool)."""
    A1, A2, P3, SA, WF = rmods
    man = json.loads((S.R / "out" / "holdout_manifest.json").read_text())
    keys = ["hm2-straddle-tf30#10", "hm2-straddle-tf30#9"]
    members = [(man["configs"][k]["in_sample_src"], "straddle", 30, k, dict(man["configs"][k]["params"])) for k in keys]
    firm, mods, kc = "lucidpro_nodll", ("eod", "realized"), 2
    models0 = A2.MODELS
    try:
        (ref,) = WF.task(("hm2-straddle-tf30", SESS, firm, members, kc, mods))
    finally:
        A2.MODELS = models0
    pool = A2.resolve(E.profile_from("straddle", dict(members[0][4], tf=30)))["srcs"]      # R's control pool for this exit profile
    S.export_bundle(members[1][0], S.export_name(keys[1]))
    mine = S.walk_forward([files[KEY], "file:" + S.export_name(keys[1])], firm, sess=SESS, control_pool=pool, kc=kc, models=mods,
                          label="hm2-straddle-tf30", names=keys)
    t = mine["task"]
    assert t["D"] == ref["D"] == 825 and t["n_starts"] == ref["n_starts"] and t["test_dates"] == ref["test_dates"] and t["members"] == ref["members"]
    assert len(t["reps"]) == len(ref["reps"]) == kc + 1
    for a, b in zip(t["reps"], ref["reps"]):
        assert a == b                                                # full-window pick, the 10 quarterly picks, test pass flags, rules
    assert mine["rows"] == WF.agg_task(ref) and len(mine["rows"]) == 2
    row = [r for r in mine["rows"] if r["model"] == "realized"][0]
    assert row["n_ctrl"] == kc and 0.0 <= row["oos_p5"] <= 1.0 and row["n_oos"] == sum(len(x) for x in ref["test_dates"])
    assert abs(row["oos_lift"] - (row["oos_p5"] - row["ctrl_oos_p5"])) < 1e-12


def test_search_rules_custom_grid_and_cap(files):
    g = {"micros": [20, 40, 60], "day_lock": [0], "day_take": [0, 1500], "day_stop": [0], "max_day_tr": [0], "target_take": [0, 1]}
    r = S.search_rules(files[KEY], "lucid", sess=SESS, grid=g, boots=0, out_csv=None)
    assert r["cells"] == 12 and len(r["rows"]) == 8                  # 60 micros > the 40-micro cap: not scored, never picked
    assert all(x["micros"] <= 40 for x in r["rows"]) and r["picks"]["primary"]["rules"]["micros"] <= 40
    one = S.score_eval(files[KEY], "lucid", {"day_take": 1500, "target_take": 1}, micros=40, sess=SESS, boots=0)
    row = [x for x in r["rows"] if x["micros"] == 40 and x["day_take"] == 1500 and x["target_take"] == 1][0]
    assert row["p5_realized"] == one["models"]["realized"]["p5"] and row["p1"] == one["p1"] and row["p3"] == one["p3"]


def test_search_csv_goes_to_L_out_only(files, tmp_path):
    g = {"micros": [40], "day_lock": [0], "day_take": [0], "day_stop": [0], "max_day_tr": [0], "target_take": [0, 1]}
    r = S.search_rules(files[KEY], "lucid", sess=SESS, grid=g, boots=0, out_csv=str(tmp_path / "s.csv"))
    assert (tmp_path / "s.csv").read_text().splitlines()[0].startswith("firm,micros,day_lock,day_take,day_stop,max_day_tr,target_take")
    with pytest.raises(ValueError, match="refusing to write into R"):
        S._write_csv(r["rows"], S.R / "out" / "zz_never.csv")
    assert not (S.R / "out" / "zz_never.csv").exists()


# ------------------------------------------------------------------ funded search

def test_search_funded_identical_to_R(files):
    import holdout_score as HS
    g = {"micros": [20, 40], "day_take": [0, 600], "day_lock": [0, 300], "day_stop": [0], "max_day_tr": [0, 1], "policy": [500, "max"]}
    t = S._R_LOAD(SRC2)
    idx = np.flatnonzero(E._sess_mask(t, SESS2))
    port = HS.Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], P.Ctx.calendar())
    for variant in ("flex", "pro_dll", "apex"):
        f, dll = S.FUNDED_VARIANTS[variant]
        ref = F.search(port, F.make_spec(f, dll), g)
        mine = S.search_funded(files[KEY2], variant, sess=SESS2, grid=g)
        assert mine["rows"] == ref and len(ref) == 32
        elig = [r for r in ref if not (variant == "apex" and r["cut_share"] > 0.02)]
        assert mine["picks"] == F.pick_cells(elig) and mine["eligible"] == len(elig)
        best = mine["picks"]["e40_raw"]
        if best is None:                                              # Apex: every cell breaks the MAE rule at these sizes
            assert variant == "apex" and not elig
            continue
        one = S.score_funded(files[KEY2], variant, best["policy"], micros=best["micros"], sess=SESS2, boots=0,
                             rules={k: best[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")})
        assert one["e_net_40"] == best["e_net_40"] and one["p_pay_20"] == best["p_pay_20"]
    with pytest.raises(ValueError):
        S.search_funded(files[KEY2], "flex", grid=g, workers=9)


def test_search_funded_fork_pool_equals_inline(files):
    g = {"micros": [20, 40], "day_take": [0, 600], "day_lock": [0], "day_stop": [0], "max_day_tr": [0], "policy": [500]}
    if S.blackout_wait_s():
        pytest.skip("inside an offline compute window: no multiprocessing now")
    a = S.search_funded(files[KEY2], "pro_nodll", sess=SESS2, grid=g, workers=1)
    b = S.search_funded(files[KEY2], "pro_nodll", sess=SESS2, grid=g, workers=2)
    assert a["rows"] == b["rows"]


# ------------------------------------------------------------------ controls

def test_daymatched_draw_is_Rs_and_matches_counts(files):
    from types import SimpleNamespace
    man = json.loads((S.R / "out" / "holdout_manifest.json").read_text())
    ctl = [man["controls"][i]["in_sample_src"] for i in man["configs"][KEY]["ctrl_eval"]["ids"]]
    seed = zlib.crc32(f"{KEY}|{SESS}".encode()) % 100000
    cs = S.daymatched(files[KEY], ctl, sess=SESS, K=4, seed=seed)
    tr = S._R_LOAD(SRC)
    m = E._sess_mask(tr, SESS)
    ref = E.daymatched_controls(SimpleNamespace(date=tr.date[m], sess=tr.sess[m], n=int(m.sum())), E.concat_tr([S._R_LOAD(c) for c in ctl]),
                                K=4, seed=seed, mask=None, carry=("side", "g", "mae", "mfe", "risk", "sess"))
    assert len(cs) == 4
    for a, b in zip(cs, ref):
        for k in ("date", "te", "tx", "g", "mae", "mfe", "side", "pi", "fb"):
            assert np.array_equal(a[k], b[k])
        if a["short"] == 0:                                           # same (date, session) trade counts as the config
            assert np.array_equal(np.unique(a["date"], return_counts=True), np.unique(tr.date[m], return_counts=True))
        assert set(a["sess"].tolist()) == {E.SESS_CODE[SESS]}
    assert S.default_seed(KEY, SESS) == seed and S.default_seed(KEY, SESS, "funded") == zlib.crc32(f"fund|{KEY}|{SESS}".encode())


def test_lift_direct_mode_and_zero_lift_against_itself(files):
    rules = {"day_lock": 750, "day_take": 1500, "target_take": 1}
    same = S.lift_vs_control(files[KEY], [files[KEY], SRC], "lucid", rules, micros=40, sess=SESS, mode="direct", boots=200)
    assert same["K"] == 2 and same["lift"] == 0.0 and same["ci"] == [0.0, 0.0] and same["lift_gt0"] is False
    for m in S.MODELS:
        assert same["models"][m]["lift"] == 0.0 and same["models"][m]["real_p5"] == same["models"][m]["ctrl_p5"]
        assert all(same["models"][m][f"lift_p{k}"] == 0.0 for k in range(1, 6))
    # a different ledger as the 'null': lift = P5(real) - P5(null), per model, paired on the start days
    other = "file:" + S.export_name(KEY2)
    d = S.lift_vs_control(files[KEY], [other], "lucid", rules, micros=40, sess=SESS, mode="direct", boots=0)
    a = S.score_eval(files[KEY], "lucid", rules, micros=40, sess=SESS, boots=0)
    b = S.score_eval(other, "lucid", rules, micros=40, sess=SESS, boots=0)
    for m in S.MODELS:
        assert d["models"][m]["lift"] == pytest.approx(a["models"][m]["p5"] - b["models"][m]["p5"], abs=1e-12)
    assert d["model"] == "realized" and d["lift"] == d["models"]["realized"]["lift"]
    f = S.lift_vs_control(files[KEY2], [files[KEY2]], "pro_dll", {"day_lock": 600}, micros=30, sess=SESS2, mode="direct", kind="funded", policy=1500)
    assert f["lift_e40"] == 0.0 and f["real_e40"] == f["ctrl_e40"] and f["lift_gt0"] is False
    with pytest.raises(ValueError):
        S.lift_vs_control(files[KEY], json.loads(S.trade_file(files[KEY]).read_text()), "lucid", rules, mode="direct")      # rows, not a list of ledgers
    with pytest.raises(ValueError):
        S.lift_vs_control(files[KEY], [files[KEY]], "lucid", rules, mode="shuffled")


# ------------------------------------------------------------------ Apex Legacy 300K PA backend (L/apex300.py)

def test_apex300_backend(files):
    AX = pytest.importorskip("apex300")
    assert "apex300_pa" in S.funded_variants() and S.funded_spec("apex300_pa").mll == AX.make_spec("apex300_pa").mll
    rules = {"day_take": 1500, "day_lock": 1000}
    port = AX.port_from_trades(json.loads(S.trade_file(files[KEY2]).read_text()), sess=SESS2)
    for start in ("fresh", "plus3000", "plus7600"):
        ref = AX.evaluate_funded(port, "apex300_pa", micros=100, rules=rules, policy=1500, start=start, strategy="donchian", inputs={"tgt_r": 0.6})
        mine = S.score_funded(files[KEY2], "apex300_pa", 1500, micros=100, rules=rules, sess=SESS2, boots=0, start=start, strategy="donchian",
                              inputs={"tgt_r": 0.6})
        for m in ("pess", "nat", "opt"):
            assert mine["models"][m] == ref[m], (start, m)
        assert mine["model"] == "pess" and mine["e_net_40"] == ref["pess"]["e_net_40"] and mine["start"] == ref["start"]
        assert mine["apex_flags"] == ref["flags"] and mine["noncompliant"] == ref["noncompliant"]
        assert mine["mae_over_limit_share"] == ref["mae_over_limit_share"] and mine["mae_limit_at_start"] == ref["mae_limit_at_start"]
    with pytest.raises(ValueError):
        S.score_funded(files[KEY2], "apex300_pa", 1500, micros=400, sess=SESS2)        # above the 35-mini limit
    with pytest.raises(ValueError):
        S.score_funded(files[KEY2], "flex", 500, micros=20, sess=SESS2, start="plus3000")   # start states: apex300 specs only
    lift = S.lift_vs_control(files[KEY2], [files[KEY2]], "apex300_pa", rules, micros=100, sess=SESS2, mode="direct", kind="funded", policy=1500,
                             start="plus3000")
    assert lift["lift_e40"] == 0.0 and lift["start"] == "plus3000"
