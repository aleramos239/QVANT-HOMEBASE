"""MANDATORY equivalence gate of the scoring adapter (SPEC stage 0).

R in-sample tester bundles (the approved picks' sources + one control pool) are exported to L/trades/R__*.json and scored
through the FILE path of score.py and through R's NATIVE path (R's own loader on the tester bundle + R's own machinery).
Every number must be IDENTICAL (==, not approx): P1..P5 / bust for every eval firm and breach model, the funded metrics
(E$40 ...) for every funded variant and model, the day-matched lift, and R's frozen in-sample numbers (holdout_manifest.json,
`insample` blocks: selection-time values, no 2025+ data) must be reproduced.

Native paths used (all R code, read-only):
  N1  portfolio.py:      evalcore.load(bundle) -> Ctx.calendar -> Base.from_tr -> PV -> norm_key -> make_A -> evalcore.race
  N2  a3_pass2.py:       load_src -> screen_analyze.cal_for -> port_of -> make_A -> evalcore.race      (pass-2/3 + funded search path)
  N3  evalcore.evaluate: R/evaluate.py's CLI path, member {'src': bundle} vs member {'src': 'file:<config>'}
  N4  holdout_score.py:  the frozen scorer in 'insample' mode (score_eval / score_funded incl. control lift)
  N5  funded.py:         holdout_score.Port2 -> DaySrc -> lifecycle -> metrics
"""
import json
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402

pytestmark = pytest.mark.usefixtures("trades_tmp")      # exports go to a directory of this module's own, never to L/trades

E, F, P = S.E, S.F, S.P
RLOAD = S._R_LOAD            # R's own evalcore.load (the adapter's wrapper is bypassed on the native side)
_R_CODE_AT_IMPORT = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in S.R.glob("*.py")}
_R_OUT_AT_IMPORT = {p.name for p in (S.R / "out").iterdir()}
MAN_PATH = S.R / "out" / "holdout_manifest.json"

# key -> approved session. The first three are the mandatory trio (straddle-tf30#10 nyam is the approved Flex / Pro eval source).
BUNDLES = {b["key"]: b for b in {**S.BASELINE, **S.BASELINE_ALT}.values()}       # the approved picks + straddle #9 (the pre-override Pro noDLL name)
SESS = {"hm2-straddle-tf30#10": "nyam", "hm2-straddle-tf30#9": "nyam", "hm2-straddle-tf30#32": "pm", "hm-orb-tf5#10": "mid",
        "fp-donchian-tf15#10": "pm", "fp-donchian-tf15#1": "nyam"}
RULE_CELLS = {      # per eval firm: no rules, the approved cell(s) of the firm, a stop / take / max-trades mix
    "lucid": [(40, {}), (40, {"day_lock": 750, "day_take": 1500, "target_take": 1}), (20, {"day_stop": 1000, "day_take": 1000, "max_day_tr": 1})],
    "lucidpro": [(30, {}), (30, {"day_lock": 1000, "target_take": 1}), (40, {"day_take": 2000, "day_stop": 1000, "max_day_tr": 1, "target_take": 1})],
    "lucidpro_nodll": [(40, {}), (40, {"day_lock": 1000, "target_take": 1}), (40, {"day_lock": 1000, "day_take": 3000, "target_take": 1})],
    "apex": [(40, {}), (40, {"day_stop": 2000, "target_take": 1}), (100, {"day_lock": 1000, "day_take": 1500, "day_stop": 1000, "max_day_tr": 1})],
    "apex_eod": [(20, {}), (20, {"day_lock": 1000, "target_take": 1}), (60, {"day_take": 1500, "day_stop": 500})],
}
FUNDED_CELLS = {    # per funded variant: (micros, rules, policy)
    "flex": [(40, {"day_take": 600, "day_lock": 300}, 1500), (20, {"day_stop": 600, "max_day_tr": 1}, 500)],
    "flex_dll": [(20, {"day_lock": 600}, 1500), (40, {"day_take": 400}, "max")],
    "pro_dll": [(30, {"day_lock": 600}, 1500), (40, {"day_take": 1000, "day_stop": 600}, 500)],
    "pro_nodll": [(40, {"day_take": 1000, "day_lock": 300}, 1000), (20, {}, "max")],
    "apex": [(30, {"day_take": 1000, "day_lock": 1000}, 1000), (50, {"day_stop": 600, "max_day_tr": 1}, 500)],
}


def _full(rules):
    return {"day_lock": 0, "day_take": 0, "day_stop": 0, "max_day_tr": 0, "target_take": 0, **rules}


@pytest.fixture(scope="module")
def files():
    """Export the bundles (rows verbatim) -> {key: 'file:<name>'}."""
    out = {}
    for key, b in BUNDLES.items():
        S.export_bundle(b["src"], S.export_name(key))
        out[key] = "file:" + S.export_name(key)
    return out


@pytest.fixture(scope="module")
def man():
    if not MAN_PATH.exists():
        pytest.skip("R/out/holdout_manifest.json not found")
    return json.loads(MAN_PATH.read_text())


# ------------------------------------------------------------------ the export itself

def test_three_plus_bundles_exported_verbatim(files):
    assert len(files) >= 3
    for key, b in BUNDLES.items():
        d = S._R_SRC_DIR(b["src"])
        native_rows = json.loads((d / "trades.json").read_text())
        file_rows = json.loads(S.trade_file(files[key]).read_text())
        assert file_rows == native_rows and len(file_rows) > 300
        assert max(r["date"] for r in file_rows) < S.HOLDOUT
        assert S.validate_trades(file_rows) == []                    # R's bundles satisfy the sim contract the loader enforces


def test_loaded_arrays_identical(files):
    for key, b in BUNDLES.items():
        a, n = S.load_trades(files[key]), RLOAD(b["src"])
        assert a.n == n.n and a.iso == n.iso
        for f in ("date", "te", "tx", "side", "g", "mae", "mfe", "sess"):
            assert np.array_equal(getattr(a, f), getattr(n, f)), (key, f)
        assert np.array_equal(a.risk, n.risk, equal_nan=True)


def test_calendar_identical_to_R(files):
    cal = S.make_calendar()
    assert cal.D == 825 and cal.iso[0] == "2021-09-22" and cal.iso[-1] == "2024-12-31" and cal.S == 821
    assert cal.iso == E.tape_sessions("2021-01-01", "2024-12-31")
    tr = RLOAD(BUNDLES["hm2-straddle-tf30#10"]["src"])
    assert np.array_equal(cal.cal, P.Ctx.calendar(tr.date))                 # R's calendar with the bundle's trade dates added
    import screen_analyze as SA
    assert np.array_equal(cal.cal, SA.cal_for(tr))


# ------------------------------------------------------------------ eval: every firm x model

def _native_eval(src, sess, micros, firm, rules):
    """N1: portfolio.py path on R's bundle."""
    tr = RLOAD(src)
    ctx = P.Ctx(P.Ctx.calendar(tr.date))
    b = P.Base.from_tr(f"native|{sess}", ctx.cal, tr, sess)
    pv = P.PV([(b, micros)], ctx.D)
    fm = P.firm(firm)
    r = _full(rules)
    A = P.make_A(pv, fm, P.norm_key(pv, r["day_lock"], r["day_take"], r["day_stop"], r["max_day_tr"]))
    return {m: E.race(ctx.idx5, A, fm.r, m, True, bool(r["target_take"])) for m in E.MODELS}, A


def _native_eval_a2(src, sess, micros, firm, rules):
    """N2: a3_pass2 path (10-micro port, micros passed to the walk)."""
    import a3_pass2 as A2
    import screen_analyze as SA
    t = RLOAD(src)
    cal = SA.cal_for(t)
    port = A2.port_of(t, np.flatnonzero(E._sess_mask(t, sess)), cal)
    rid, r, dll = SA.firm(firm)
    x = _full(rules)
    A = A2.make_A(port, r, dll, *A2.norm_walk(port, micros, x["day_lock"], x["day_take"], x["day_stop"], x["max_day_tr"]))
    return {m: E.race(A2.idx5_of(len(cal)), A, r, m, True, bool(x["target_take"])) for m in E.MODELS}


@pytest.mark.parametrize("key", list(BUNDLES))
def test_eval_identical_every_firm_and_model(files, key):
    src, n = BUNDLES[key]["src"], 0
    for sess in (SESS[key], "all"):
        for firm in S.EVAL_FIRMS:
            for micros, rules in RULE_CELLS[firm]:
                if sess == "all" and rules:                       # the all-session run: the no-rules cell only (speed)
                    continue
                mine = S.score_eval(files[key], firm, rules, micros=micros, sess=sess, boots=0, arrays=True)
                nat, A = _native_eval(src, sess, micros, firm, rules)
                nat2 = _native_eval_a2(src, sess, micros, firm, rules)
                assert np.array_equal(mine["daily"].tot, A.tot) and np.array_equal(mine["daily"].worst, A.worst)
                assert np.array_equal(mine["daily"].wreal, A.wreal)
                for m in E.MODELS:
                    o, d = nat[m]
                    assert np.array_equal(mine["arrays"][m][0], o) and np.array_equal(mine["arrays"][m][1], d), (key, sess, firm, rules, m)
                    assert np.array_equal(nat2[m][0], o) and np.array_equal(nat2[m][1], d)
                    mm = mine["models"][m]
                    assert mm["p5"] == float((o == 1).mean()) and mm["bust5"] == float((o == 2).mean())
                    for k in range(1, 6):
                        assert mm[f"p{k}"] == float(((o == 1) & (d <= k)).mean())
                    assert mm == {k: v for k, v in P._detail(o, d, 0).items()} | {kk: mm[kk] for kk in ("p4", "bust_by", "neither5")}
                    n += 1
                assert mine["p5"] == mine["models"][E.primary_model(firm)]["p5"] and mine["model"] == E.primary_model(firm)
    assert n >= 5 * 3 * 3 + 5 * 3                                  # every firm x model, >= 3 rule cells + the all-session cell


def test_eval_ci_identical_to_R_detail(files):
    key = "hm2-straddle-tf30#10"
    for firm, (micros, rules) in (("lucid", RULE_CELLS["lucid"][1]), ("apex", RULE_CELLS["apex"][1])):
        mine = S.score_eval(files[key], firm, rules, micros=micros, sess="nyam", boots=2000)
        nat, _ = _native_eval(BUNDLES[key]["src"], "nyam", micros, firm, rules)
        for m in E.MODELS:
            ref = P._detail(*nat[m], 2000)
            for k in ("p1", "p2", "p3", "p5", "bust5", "med_days", "ci_p1", "ci_p2", "ci_p3", "ci_p5"):
                assert mine["models"][m][k] == ref[k], (firm, m, k)


@pytest.mark.parametrize("key", ["hm2-straddle-tf30#10", "hm-orb-tf5#10", "fp-donchian-tf15#1"])
def test_evalcore_evaluate_accepts_file_members(files, key):
    """N3: R's own evaluate() (evaluate.py CLI path) with a 'file:' member == with the native bundle member, every firm:
    eval races (3 models), block CI, i.i.d. MC, eventual pass (propsim.run) and evalcore's funded race."""
    rules = {"day_lock": 600, "day_stop": 800, "max_day_tr": 2, "target_stop": True, "day_take": 1200, "target_take": False}
    base = {"rules": rules, "firms": list(S.EVAL_FIRMS)}
    kw = dict(mc=2000, boots=300, eventual=200)
    nat = E.evaluate({**base, "members": [{"src": BUNDLES[key]["src"], "sess": SESS[key], "micros": 20}]}, **kw)
    fil = E.evaluate({**base, "members": [{"src": files[key], "sess": SESS[key], "micros": 20}]}, **kw)
    assert nat["window"] == fil["window"] and nat["window"]["sessions"] == 825
    assert len(nat["firms"]) == 5
    for rid in nat["firms"]:
        assert nat["firms"][rid] == fil["firms"][rid], rid
    # ... and the adapter's score_eval gives the same P(pass<=5d) / bust under evaluate.py's rule semantics
    for firm in S.EVAL_FIRMS:
        f = nat["firms"][E.firm_rules(firm)[0]]
        mine = S.score_eval(files[key], firm, rules, micros=20, sess=SESS[key], boots=300)
        for m in E.MODELS:
            assert mine["models"][m]["p5"] == f[m]["p_pass"] and mine["models"][m]["bust5"] == f[m]["p_bust"]
            assert [mine["models"][m][f"p{k}"] for k in range(1, 6)] == f[m]["pass_by"]
            assert mine["models"][m]["bust_by"] == f[m]["bust_by"]
        assert mine["models"]["eod"]["ci_p5"] == f["eod"]["ci95_pass"] and mine["models"]["eod"]["ci_bust5"] == f["eod"]["ci95_bust"]


def test_evalcore_evaluate_after_loss_and_no_target_stop(files):
    """The non-default rule dims (after_loss / after_win / target_stop off) go through evalcore.walk unchanged."""
    key = "fp-donchian-tf15#10"
    rules = {"day_stop": 600, "after_loss": 0.5, "after_win": 1.5, "target_stop": False, "day_take": 900, "target_take": True}
    nat = E.evaluate({"rules": rules, "firms": ["lucid", "apex"], "members": [{"src": BUNDLES[key]["src"], "sess": "all", "micros": 20}]},
                     mc=0, boots=0, eventual=0, funded=False)
    for firm in ("lucid", "apex"):
        f = nat["firms"][E.firm_rules(firm)[0]]
        mine = S.score_eval(files[key], firm, rules, micros=20, sess="all", boots=0)
        for m in E.MODELS:
            assert mine["models"][m]["p5"] == f[m]["p_pass"] and mine["models"][m]["bust5"] == f[m]["p_bust"]
        assert mine["walk"]["executed"] == f["walk"]["executed"]


# ------------------------------------------------------------------ funded: every variant x model

def _native_funded(src, sess, micros, variant, rules, policy):
    """N5: R's funded path on R's bundle (holdout_score.Port2 + funded.DaySrc / lifecycle / metrics)."""
    import holdout_score as HS
    t = RLOAD(src)
    cal = P.Ctx.calendar(t.date)
    idx = np.flatnonzero(E._sess_mask(t, sess))
    port = HS.Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], cal)
    f, dll = HS.VARIANTS[variant]
    Sp = F.make_spec(f, dll)
    rl = {k: rules.get(k, 0) for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}
    src_ = F.DaySrc(port, rl, micros, events=Sp.kind == "apex")
    return {m: F.metrics(F.lifecycle(Sp, src_, policy, F.H_LIFE, m), F.H_LIFE) for m in HS.MODELS_ALT["apex" if Sp.kind == "apex" else "lucid"]}, Sp


@pytest.mark.parametrize("key", list(BUNDLES))
def test_funded_identical_every_variant_and_model(files, key):
    n = 0
    for variant, cells in FUNDED_CELLS.items():
        for micros, rules, policy in cells:
            mine = S.score_funded(files[key], variant, policy, micros=micros, rules=rules, sess=SESS[key], boots=0)
            nat, Sp = _native_funded(BUNDLES[key]["src"], SESS[key], micros, variant, rules, policy)
            assert set(mine["models"]) == set(nat) and len(nat) == 3 and mine["primary"] == Sp.primary
            for m, ref in nat.items():
                assert mine["models"][m] == ref, (key, variant, micros, rules, policy, m)        # E$40 and every other metric
                assert mine["models"][m]["e_net_40"] == ref["e_net_40"]
                n += 1
            assert mine["e_net_40"] == nat[Sp.primary]["e_net_40"] and mine["p_bust_pre_first"] == nat[Sp.primary]["p_bust_pre_first"]
    assert n == 5 * 2 * 3


def test_evaluate_funded_of_R_matches(files):
    """funded.evaluate_funded on an evalcore.build portfolio (R's documented single-config call) == score_funded."""
    key = "hm2-straddle-tf30#32"
    Pn = E.build({"members": [{"src": BUNDLES[key]["src"], "sess": "pm", "micros": 10}]})
    for firm, dll, variant in (("flex", None, "flex"), ("pro", 0, "pro_nodll"), ("apex", None, "apex")):
        ref = F.evaluate_funded(Pn, firm, micros=40, rules={"day_take": 600, "day_lock": 300}, policy=1000, dll=dll)
        mine = S.score_funded(files[key], variant, 1000, micros=40, rules={"day_take": 600, "day_lock": 300}, sess="pm", boots=0)
        for m in mine["models"]:
            assert mine["models"][m] == ref[m], (firm, m)
        if firm == "apex":
            assert mine["mae_over_limit_share"] == ref["mae_over_limit_share"]


# ------------------------------------------------------------------ R's frozen in-sample numbers + the frozen scorer (N4)

EVAL_FINALISTS = ["lucid:single", "lucidpro_nodll:single", "lucidpro_nodll:speed_p3", "lucidpro_nodll:single:hm-orb-tf5#10|mid@40"]
FUNDED_FINALISTS = ["flex#1", "pro_nodll#1", "pro_nodll#2", "pro_dll#1", "flex_dll#2", "apex#1"]


def test_frozen_insample_eval_numbers_reproduced(files, man):
    for fid in EVAL_FINALISTS:
        fin = man["finalists"][fid]
        (mem,) = fin["members"]
        mine = S.score_eval(files[mem["cfg"]], fin["firm"], fin["rules"], micros=mem["micros"], sess=mem["sess"], boots=2000)
        ins = fin["insample"]
        tol = 1e-12 if "ci_p5" in ins else 1e-6                    # candidates.csv rows keep 6 digits
        assert mine["model"] == man["firms"][fin["firm"]]["primary"]
        for k in ("p1", "p2", "p3", "p5", "bust5"):
            if k in ins:
                assert abs(mine[k] - ins[k]) <= tol, (fid, k, mine[k], ins[k])
        for m in E.MODELS:                                        # candidates.csv rows carry the OTHER models at their own optimal cell
            if f"{m}_p5" in ins and "ci_p5" in ins:
                assert abs(mine["models"][m]["p5"] - ins[f"{m}_p5"]) <= tol, (fid, m)
        if "ci_p5" in ins:
            assert mine["ci_p5"] == pytest.approx(ins["ci_p5"], abs=1e-12)
    # the two approved eval picks, explicitly
    assert S.score_baseline("flex_eval", boots=0)["p5"] == pytest.approx(0.6918392204628502, abs=1e-12)
    assert S.score_baseline("pro_nodll_eval", boots=0)["p5"] == pytest.approx(0.7064555420219245, abs=1e-12)
    # SPEC override: the Pro noDLL eval bar is straddle-tf30#10 nyam (R's manifest single); #9 is kept as an alternative only
    assert S.BASELINE["pro_nodll_eval"]["key"] == "hm2-straddle-tf30#10" and S.BASELINE["pro_nodll_eval"]["sess"] == "nyam"
    assert "pro_nodll_eval_s9" not in S.BASELINE and S.BASELINE_ALT["pro_nodll_eval_s9"]["key"] == "hm2-straddle-tf30#9"
    fin = man["finalists"]["lucidpro_nodll:single"]
    assert fin["members"][0]["cfg"] == S.BASELINE["pro_nodll_eval"]["key"] and fin["rules"] == S.BASELINE["pro_nodll_eval"]["rules"]
    assert S.score_baseline("pro_nodll_eval_s9", boots=0)["p5"] == pytest.approx(0.7064555420219245, abs=1e-12)      # the tie


def test_frozen_insample_funded_numbers_reproduced(files, man):
    for fid in FUNDED_FINALISTS:
        fin = man["funded"][fid]
        mine = S.score_funded(files[fin["cfg"]], fin["variant"], fin["policy"], micros=fin["micros"], rules=fin["rules"], sess=fin["sess"], boots=0)
        ins = fin["insample"]
        assert mine["model"] == ins["model"]
        for k in ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_first_net", "e_cheque_if_paid", "e_net_40", "e_net_60",
                  "p_bust_pre_first", "p_bust_any"):
            assert mine[k] == pytest.approx(ins[k], abs=1e-9), (fid, k)
        for j in (1, 2):
            assert mine["models"][ins[f"alt{j}_model"]]["e_net_40"] == pytest.approx(ins[f"alt{j}_e40"], abs=1e-6), (fid, j)


@pytest.fixture(scope="module")
def frozen(man):
    """N4: holdout_score in 'insample' mode (the frozen scorer on the 2021-24 window; reads in-sample sources only)."""
    import holdout_score as HS
    ctx = HS.make_ctx(man, "insample")
    assert ctx.D == 825
    return HS, ctx


def _ctrl_srcs(man, cfg, pool):
    return [man["controls"][i]["in_sample_src"] for i in man["configs"][cfg][pool]["ids"]]


def test_frozen_scorer_eval_and_lift_identical(files, man, frozen):
    HS, ctx = frozen
    for fid in ("lucid:single", "lucidpro_nodll:single"):
        fin = man["finalists"][fid]
        (mem,) = fin["members"]
        ref = HS.score_eval(ctx, man, fid, boots=2000)
        mine = S.score_eval(files[mem["cfg"]], fin["firm"], fin["rules"], micros=mem["micros"], sess=mem["sess"], boots=2000)
        for m in E.MODELS:
            for k in ("p1", "p2", "p3", "p5", "bust5", "med_days"):
                assert mine["models"][m][k] == ref[m][k], (fid, m, k)
            assert mine["models"][m]["bust_by"] == ref["by_day"][m]["bust_by_day"]
        assert mine["ci_p5"] == ref["headline"]["ci_p5"] and mine["p5"] == ref["headline"]["p5"]
        assert mine["walk"]["executed"] == ref["walk"]["executed"] and mine["series"] == ref["series"]
        # C1 lift: controls exported to files too (file path on BOTH sides of the lift)
        cid = f"{mem['cfg']}|{mem['sess']}"
        ctl = []
        for i in man["configs"][mem["cfg"]]["ctrl_eval"]["ids"]:
            S.export_bundle(man["controls"][i]["in_sample_src"], S.export_name(i))
            ctl.append("file:" + S.export_name(i))
        lift = S.lift_vs_control(files[mem["cfg"]], ctl, fin["firm"], fin["rules"], micros=mem["micros"], sess=mem["sess"],
                                 K=ctx.K, seed=zlib.crc32(cid.encode()) % 100000, boots=2000)
        for m in E.MODELS:
            for k in ("real_p5", "ctrl_p5", "ctrl_p5_sd", "lift", "ci"):
                assert lift["models"][m][k] == ref["lift"][m][k], (fid, m, k)
        ins = fin["insample"]
        assert lift["lift"] == pytest.approx(ins["lift"], abs=1e-12) and lift["ci"] == pytest.approx(ins["lift_ci"], abs=1e-12)
        assert lift["K"] == 10 and lift["lift_gt0"] is True


def test_frozen_scorer_funded_and_lift_identical(files, man, frozen):
    HS, ctx = frozen
    for fid in ("flex#1", "pro_nodll#1", "apex#1"):
        fin = man["funded"][fid]
        ref = HS.score_funded(ctx, man, fid, boots=2000)
        kw = dict(micros=fin["micros"], rules=fin["rules"], sess=fin["sess"])
        mine = S.score_funded(files[fin["cfg"]], fin["variant"], fin["policy"], boots=2000, strategy=man["configs"][fin["cfg"]]["strategy"],
                              inputs=dict(man["configs"][fin["cfg"]]["inputs"]), **kw)
        for m in mine["models"]:
            for k, v in ref[m].items():
                assert mine["models"][m][k] == v, (fid, m, k)
        assert mine["e_net_40"] == ref["headline"]["e_net_40"] and mine["e_net_40_ci"] == ref["headline"]["e_net_40_ci"]
        assert mine["n_starts"] == ref["n_starts"] == 766 and mine["trades"] == ref["trades"]
        if fin["variant"] == "apex":
            assert mine["apex_flags"] == ref["apex_flags"]
        cid = f"{fin['cfg']}|{fin['sess']}"
        lift = S.lift_vs_control(files[fin["cfg"]], _ctrl_srcs(man, fin["cfg"], "ctrl_funded"), fin["variant"], kind="funded",
                                 policy=fin["policy"], K=ctx.K, seed=zlib.crc32(f"fund|{cid}".encode()), **kw)
        for k in ("ctrl_e40", "ctrl_e40_sd", "ctrl_p40", "ctrl_p20", "lift_e40"):
            assert lift[k] == ref["lift"][k], (fid, k)


def test_funded_lift_native_k8_matches_frozen_ctrl(files, man):
    """funded_search's own control draw (K = 8, seed crc32('fund|cid')) gives the manifest's frozen ctrl_e40 / lift_e40."""
    fin = man["funded"]["flex#1"]
    cid = f"{fin['cfg']}|{fin['sess']}"
    lift = S.lift_vs_control(files[fin["cfg"]], _ctrl_srcs(man, fin["cfg"], "ctrl_funded"), "flex", fin["rules"], kind="funded", policy=fin["policy"],
                             micros=fin["micros"], sess=fin["sess"], K=8, seed=zlib.crc32(f"fund|{cid}".encode()))
    assert lift["ctrl_e40"] == pytest.approx(fin["insample"]["ctrl_e40"], abs=1e-6)
    assert lift["lift_e40"] == pytest.approx(fin["insample"]["lift_e40"], abs=1e-6)


# ------------------------------------------------------------------ multi-member portfolios (R: lucid:best2, lucidpro_nodll:pf)

def test_portfolio_members_identical(files, man):
    fin = man["finalists"]["lucidpro_nodll:pf"]                    # #9 nyam + first_bar_mom mid + #10 pm, max_day_tr = 1
    srcs = {m["cfg"]: man["configs"][m["cfg"]]["in_sample_src"] for m in fin["members"]}
    members = [{"src": files.get(m["cfg"], srcs[m["cfg"]]), "sess": m["sess"], "micros": m["micros"]} for m in fin["members"]]
    assert sum(1 for m in members if str(m["src"]).startswith("file:")) == 2 and len(members) == 3      # file + native members mixed
    mine = S.score_eval(members, "lucidpro_nodll", fin["rules"], boots=0, arrays=True)
    ctx = P.Ctx(P.Ctx.calendar())
    fm = P.firm("lucidpro_nodll")
    bases = [(P.Base.from_tr(f"{m['cfg']}|{m['sess']}", ctx.cal, RLOAD(srcs[m["cfg"]]), m["sess"]), m["micros"]) for m in fin["members"]]
    pv = P.PV(bases, ctx.D)
    r = fin["rules"]
    A = P.make_A(pv, fm, P.norm_key(pv, r["day_lock"], r["day_take"], r["day_stop"], r["max_day_tr"]))
    for m in E.MODELS:
        o, d = E.race(ctx.idx5, A, fm.r, m, True, bool(r["target_take"]))
        assert np.array_equal(mine["arrays"][m][0], o) and np.array_equal(mine["arrays"][m][1], d)
    assert mine["p5"] == pytest.approx(fin["insample"]["p5"], abs=1e-12)
    assert mine["walk"]["executed"] == A.st["executed"] and mine["walk"]["skipped"] == A.st["skipped"] > 0


# ------------------------------------------------------------------ R stays untouched

def test_zz_R_untouched_and_no_bytecode():
    assert not list(S.R.glob("__pycache__")) and not list(S.R.glob("*.pyc"))
    assert sys.dont_write_bytecode
    assert E.load is S._load_wrapper and S._R_LOAD.__module__ == "evalcore" and S._R_LOAD is not S._load_wrapper
    assert not (S.R / "trades").exists()
    now = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in S.R.glob("*.py")}
    assert now == _R_CODE_AT_IMPORT                        # no R code file created, removed or modified by this test session
    assert {p.name for p in (S.R / "out").iterdir()} == _R_OUT_AT_IMPORT and {p.name for p in (S.R / "bundles_cache").iterdir()} == {"nq_sessions.json"}
