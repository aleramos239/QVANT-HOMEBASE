"""INDEPENDENT equivalence check of score.py (verifier's lens, 2026-10-01): file path vs R's NATIVE path, cross-process.

The native side runs in a separate interpreter that never imports score.py (tests/score_native_ref.py: R's own loader on R's
tester bundles + R's own machinery), so score.py's in-process wrappers of evalcore.load cannot leak into the reference. The file
side exports the same bundles to L/trades/R__*.json and scores them through score.py. Every number must be IDENTICAL (==).

Bundles: NONE of the builder's (straddle #9/#10/#32, orb #10, donchian #1/#10): a heat-map cell with up to 11 trades a day
(squeeze-tf5#21), a heat-map cell with 12k trades (rsi2-tf1#21), a short-only time-exit cell (tod_drift-tf30#19) and a plain
screen RUN (supertrend-tf5, a run id, not a grid cell). Members: multi-session ('nyam+pm', ['asia', 'london']), single session,
all sessions, and a 3-member portfolio whose members are multi-session. All 5 eval firms x 3 breach models, all 5 funded
variants x 3 models (+ apex300_pa / apex50_pa x 3 start states), C1 lift (eval + funded), rule search and funded search.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
L = Path(__file__).resolve().parent.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))
import score as S          # noqa: E402

pytestmark = pytest.mark.usefixtures("trades_tmp")      # exports go to a directory of this module's own, never to L/trades

BUNDLES = {
    "sq21": "20260930-002323-draft_pp_squeeze-b809#21",
    "rsi21": "20260930-095544-draft_pp_rsi2-2f5b#21",
    "tod19": "20260930-104356-draft_pp_tod_drift-63a7#19",
    "st5": "20260929-214838-draft_pp_supertrend-3660",
    "rnd_a": "20260929-222957-draft_pp_random-73ab#9", "rnd_b": "20260929-235517-draft_pp_random-5d13#9",
    "rnd_c": "20260930-000439-draft_pp_random-8171#9",
}
FILE = {"sq21": "R__hm2-squeeze-tf5_c21", "rsi21": "R__hm2-rsi2-tf1_c21", "tod19": "R__hm2-tod_drift-tf30_c19",
        "st5": "R__screen-supertrend-tf5", "rnd_a": "R__hmctrl-random-tf5-s11_c9", "rnd_b": "R__hmctrl-random-tf5-s12_c9",
        "rnd_c": "R__hmctrl-random-tf5-s13_c9"}
POOL = ["rnd_a", "rnd_b", "rnd_c"]
MEMBERS = {
    "M1": [{"b": "sq21", "sess": "nyam+pm"}],                                  # heat-map cell, multi-session member
    "M2": [{"b": "st5", "sess": ["asia", "london"]}],                          # run id, multi-session member (list form)
    "M3": [{"b": "tod19", "sess": "mid"}],
    "M4": [{"b": "sq21", "sess": "nyam+mid", "micros": 20}, {"b": "tod19", "sess": "pm", "micros": 10},
           {"b": "rsi21", "sess": "asia+london", "micros": 10}],              # portfolio of multi-session members
    "M5": [{"b": "rsi21", "sess": "all"}],
}
EVAL_CELLS = {
    "lucid": [(30, {}), (40, {"day_lock": 1500, "day_take": 1250, "max_day_tr": 1, "target_take": 1}), (10, {"day_stop": 2000, "day_take": 1000})],
    "lucidpro": [(20, {}), (40, {"day_lock": 2000, "day_take": 3000, "target_take": 1}), (30, {"day_stop": 2000, "max_day_tr": 1})],
    "lucidpro_nodll": [(30, {}), (20, {"day_take": 1500, "day_stop": 1000, "target_take": 1}), (40, {"day_lock": 2000, "max_day_tr": 1})],
    "apex": [(60, {}), (80, {"day_lock": 2000, "day_take": 3000, "day_stop": 3000, "target_take": 1}), (20, {"day_take": 2000, "max_day_tr": 1})],
    "apex_eod": [(30, {}), (50, {"day_lock": 2000, "day_take": 3000, "target_take": 1}), (40, {"day_stop": 750, "max_day_tr": 1})],
}
ODD_RULES = [{"day_stop": 700, "after_loss": 0.5, "after_win": 1.5, "target_stop": False, "day_take": 900, "target_take": True},
             {"day_lock": 400, "max_day_tr": 2, "target_stop": True, "after_loss": 2.0}]
FUNDED_CELLS = {
    "flex": [(30, {"day_take": 400, "day_stop": 300}, 500), (40, {"day_lock": 600, "max_day_tr": 1}, "max")],
    "flex_dll": [(40, {"day_take": 250, "day_lock": 300}, 1000), (20, {}, 500)],
    "pro_dll": [(20, {"day_take": 600, "max_day_tr": 1}, 1000), (40, {"day_stop": 300}, "max")],
    "pro_nodll": [(30, {"day_lock": 1000, "day_stop": 600}, 1500), (10, {"day_take": 150}, 500)],
    "apex": [(100, {"day_take": 400}, 500), (20, {"day_lock": 600, "day_stop": 1000, "max_day_tr": 1}, "max")],
}
APEX_GATE = {       # what the Apex compliance gate is told about each member set
    "M2": {"strategy": "supertrend", "inputs": {"tgt_r": 2.0}, "both_sides": False},       # market entries, one direction
    "M3": {"strategy": "tod_drift", "inputs": {"tgt_r": 0.0}, "both_sides": False},        # time exit: no target -> 5:1 FAIL
    "M4": {"strategy": "squeeze", "inputs": {"tgt_r": 1.0, "sq_type": "nr7"}, "both_sides": True},     # OCO -> one direction FAIL
}
APEX300_CELLS = [(20, {"day_take": 1500, "day_stop": 750}, 500), (30, {"day_lock": 2000, "max_day_tr": 1}, 2500)]


def _with_micros(mem, micros):
    return [dict(m, micros=m.get("micros", micros)) for m in mem]


def build_cases() -> dict:
    ev, fu, lf, se, fs = [], [], [], [], []
    for mk, mem in MEMBERS.items():
        for firm, cells in EVAL_CELLS.items():
            for i, (mic, rules) in enumerate(cells):
                if mk == "M5" and i:                                  # the 12k-trade all-session run: the no-rules cell only (speed)
                    continue
                ev.append({"id": f"pf|{mk}|{firm}|{i}", "path": "pf", "members": _with_micros(mem, mic), "firm": firm, "rules": rules,
                           "boots": 300 if i == 1 else 0})
    for mk in ("M1", "M4"):
        for firm in EVAL_CELLS:
            for i, rules in enumerate(ODD_RULES):
                mem = [dict(m, news=("skip" if i else "only")) for m in _with_micros(MEMBERS[mk], 20)]
                ev.append({"id": f"ev|{mk}|{firm}|{i}", "path": "ev", "members": mem, "firm": firm, "rules": rules, "boots": 200})
    for mk in ("M1", "M2", "M3", "M4"):
        for var, cells in FUNDED_CELLS.items():
            for i, (mic, rules, pol) in enumerate(cells):
                multi = mk == "M4"                                   # portfolio: every member keeps its own micros
                fu.append({"id": f"fev|{mk}|{var}|{i}", "path": "ev", "members": MEMBERS[mk], "variant": var, "micros": None if multi else mic,
                           "rules": rules, "policy": pol, "strategy": "squeeze" if mk in ("M1", "M4") else "supertrend",
                           "inputs": {"tgt_r": 1.0, "sq_type": "nr7"} if mk in ("M1", "M4") else {"tgt_r": 2.0}})
    for var, cells in FUNDED_CELLS.items():
        mic, rules, pol = cells[0]
        fu.append({"id": f"fp2|M2|{var}", "path": "p2", "members": MEMBERS["M2"], "variant": var, "micros": mic, "rules": rules, "policy": pol,
                   "boots": 300})
    for var in ("apex300_pa", "apex50_pa"):
        for mk in ("M2", "M3", "M4"):
            for start in ("fresh", "plus3000", "plus7600"):
                for i, (mic, rules, pol) in enumerate(APEX300_CELLS):
                    st = start
                    if var == "apex50_pa":
                        mic, pol = min(mic, 50), (500 if pol == 2500 else pol)
                        st = {"fresh": "fresh", "plus3000": 1000.0, "plus7600": 2600.0}[start]      # the 50K's cushion states, as profit $
                    fu.append({"id": f"fev|{mk}|{var}|{start}|{i}", "path": "ev", "members": MEMBERS[mk], "variant": var,
                               "micros": None if mk == "M4" else mic, "rules": rules, "policy": pol, "start": st, **APEX_GATE[mk],
                               "spec": {"cons_base": "balance"} if (mk == "M3" and i == 1) else {}})
    for firm, mic, rules in (("lucid", 40, {"day_lock": 750, "day_take": 1500, "target_take": 1}), ("apex", 60, {"day_take": 2000, "max_day_tr": 1})):
        lf.append({"id": f"lift|eval|{firm}", "path": "eval", "members": _with_micros(MEMBERS["M1"], mic), "firm": firm, "rules": rules,
                   "pool": POOL, "K": 4, "cid": "hm2-squeeze-tf5#21|nyam+pm", "boots": 300})
    for var, mic, rules, pol in (("pro_nodll", 30, {"day_take": 600}, 1000), ("apex", 30, {"day_lock": 600}, 500)):
        lf.append({"id": f"lift|funded|{var}", "path": "funded", "members": [{"b": "sq21", "sess": "pm"}], "variant": var, "micros": mic,
                   "rules": rules, "policy": pol, "pool": POOL, "K": 3, "cid": "hm2-squeeze-tf5#21|pm"})
    for firm in ("lucidpro_nodll", "apex_eod"):
        se.append({"id": f"search|{firm}", "path": "a3p3", "members": MEMBERS["M1"], "firm": firm})
    g = {"micros": [20, 40], "day_take": [0, 400], "day_lock": [0, 600], "day_stop": [0, 300], "max_day_tr": [0, 1], "policy": [500, 1500]}
    for var in ("flex_dll", "pro_nodll", "apex"):
        fs.append({"id": f"fsearch|{var}", "path": "funded", "members": MEMBERS["M2"], "variant": var, "grid": g})
    return {"bundles": BUNDLES, "eval": ev, "funded": fu, "lift": lf, "search": se, "fsearch": fs}


@pytest.fixture(scope="module")
def cases():
    return build_cases()


@pytest.fixture(scope="module")
def native(cases, tmp_path_factory):
    """R's numbers from a separate interpreter that never imports score.py. Scratch files in a directory of this run's own
    (pytest's tmp_path_factory): two suite runs at the same time cannot delete each other's files."""
    d = tmp_path_factory.mktemp("score_verify")
    (d / "cases.json").write_text(json.dumps(cases))
    S.desk_window_wait()
    r = subprocess.run([sys.executable, "-B", str(L / "tests" / "score_native_ref.py"), str(d / "cases.json"), str(d / "out.json")],
                       capture_output=True, text=True, cwd=str(d))
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads((d / "out.json").read_text())


@pytest.fixture(scope="module")
def files(trades_tmp):
    for k, src in BUNDLES.items():
        S.export_bundle(src, FILE[k])
    assert all((trades_tmp / f"{v}.json").exists() for v in FILE.values()) and not list(trades_tmp.glob("*.tmp"))
    return {k: "file:" + v for k, v in FILE.items()}


def _mem(files, mem):
    return [{**{k: v for k, v in m.items() if k != "b"}, "src": files[m["b"]]} for m in mem]


def _js(x):
    """What json would give back (tuples -> lists, numpy scalars -> python) so == compares like with like."""
    return json.loads(json.dumps(x, default=lambda o: o.tolist() if isinstance(o, np.ndarray) else (o.item() if hasattr(o, "item") else str(o))))


def test_exports_are_verbatim_and_new(files):
    used_by_builder = {b["src"] for b in S.BASELINE.values()}
    for k, src in BUNDLES.items():
        assert src not in used_by_builder
        d = S._R_SRC_DIR(src)
        assert json.loads(S.trade_file(files[k]).read_text()) == json.loads((d / "trades.json").read_text())
    assert "#" not in BUNDLES["st5"] and "#" in BUNDLES["sq21"]                # a run id and heat-map cells


def test_eval_every_firm_and_model_identical_to_native_R(cases, native, files):
    import hashlib
    n = 0
    for c in cases["eval"]:
        if c["path"] != "pf":
            continue
        ref = native[c["id"]]
        mine = S.score_eval(_mem(files, c["members"]), c["firm"], c["rules"], boots=c["boots"], arrays=True)
        assert mine["window"]["sessions"] == ref["D"] == 825 and mine["n_trades"] == ref["n_trades"] and mine["primary"] == ref["primary"], c["id"]
        for k, a in (("sha_tot", mine["daily"].tot), ("sha_worst", mine["daily"].worst), ("sha_wreal", mine["daily"].wreal)):
            assert hashlib.sha1(np.ascontiguousarray(np.asarray(a, np.float64)).tobytes()).hexdigest() == ref[k], (c["id"], k)
        w = mine["walk"]
        assert [w["executed"], w["skipped"], w["clipped"], w["overlap_entries"], w["opposite_conflicts"], w["max_concurrent_micros"],
                w["cap_violations"]] == [ref["walk"][k] for k in ("executed", "skipped", "clipped", "overlap", "conflicts", "max_conc", "cap_viol")]
        assert mine["series"]["net"] == ref["net"]
        for m in S.MODELS:
            o, d = mine["arrays"][m]
            rm = ref["models"][m]
            assert hashlib.sha1(np.asarray(o, np.int64).tobytes()).hexdigest() == rm["sha_o"], (c["id"], m)
            assert hashlib.sha1(np.asarray(d, np.int64).tobytes()).hexdigest() == rm["sha_d"], (c["id"], m)
            for k, v in rm.items():
                if not k.startswith("sha_"):
                    assert mine["models"][m][k] == v, (c["id"], m, k, mine["models"][m][k], v)
            n += 1
        assert mine["p5"] == ref["models"][ref["primary"]]["p5"]
    assert n == (4 * 3 + 1) * 5 * 3                                    # 4 member sets x 3 cells + the 12k run, x 5 firms x 3 models


def test_evaluate_path_odd_rules_and_news_identical_to_native_R(cases, native, files):
    n = 0
    for c in cases["eval"]:
        if c["path"] != "ev":
            continue
        ref = native[c["id"]]
        mine = S.score_eval(_mem(files, c["members"]), c["firm"], c["rules"], boots=c["boots"])
        assert mine["window"]["sessions"] == ref["window"]["sessions"] and mine["n_trades"] == ref["window"]["trades"] > 0, c["id"]
        assert _js(mine["walk"]) == ref["walk"] and _js(mine["cost"]) == ref["cost"] and _js(mine["series"]) == ref["series"], c["id"]
        for m in S.MODELS:
            a, r = mine["models"][m], ref["models"][m]
            assert a["p5"] == r["p_pass"] and a["bust5"] == r["p_bust"] and [a[f"p{k}"] for k in range(1, 6)] == r["pass_by"], (c["id"], m)
            assert a["bust_by"] == r["bust_by"] and a["med_days"] == r["med_days_pass"], (c["id"], m)
            if "ci95_pass" in r:
                assert a["ci_p5"] == r["ci95_pass"] and a["ci_bust5"] == r["ci95_bust"], (c["id"], m)
            n += 1
    assert n == 2 * 5 * 2 * 3


def test_funded_every_variant_and_model_identical_to_native_R(cases, native, files):
    n, seen, verdicts = 0, set(), set()
    for c in cases["funded"]:
        ref = native[c["id"]]
        kw = dict(micros=c["micros"], rules=c["rules"], boots=c.get("boots", 0), strategy=c.get("strategy"), inputs=c.get("inputs"),
                  both_sides=c.get("both_sides"))
        if c["variant"] in S._ext_firms():
            kw["start"] = c["start"]
        mine = S.score_funded(_mem(files, c["members"]), c["variant"], c["policy"], **kw, **c.get("spec", {}))
        assert set(mine["models"]) == set(ref["models"]) and len(ref["models"]) == 3 and mine["primary"] == ref["primary"], c["id"]
        for m, r in ref["models"].items():
            assert _js(mine["models"][m]) == r, (c["id"], m, {k: (mine["models"][m].get(k), v) for k, v in r.items() if mine["models"][m].get(k) != v})
            n += 1
        assert mine["e_net_40"] == ref["models"][ref["primary"]]["e_net_40"]
        if "n_days" in ref:
            assert mine["window"]["sessions"] == ref["n_days"] and mine["trades"] == ref["n_trades"], c["id"]
        if "flags" in ref:
            assert mine["apex_flags"] == ref["flags"] and mine["mae_over_limit_share"] == ref["mae_over_limit_share"], c["id"]
        for k in ("noncompliant", "mae_limit_at_start", "stop_ge_80pct_threshold_share", "no_stop_share", "start", "compliance",
                  "trade_checks", "cons_base", "commission", "stop_5x_target_basis"):
            if k in ref:
                assert _js(mine[k]) == ref[k], (c["id"], k, mine[k], ref[k])
        if "cons_alt" in ref:                                          # the other reading of the consistency base, every model
            assert _js(mine["cons_alt"]) == ref["cons_alt"], c["id"]
            assert mine["cons_alt"]["cons_base"] != mine["cons_base"]
            verdicts.add((c["variant"], mine["compliant"], tuple(sorted(mine["compliance"].items()))))
        seen.add(c["variant"])
    assert seen == set(S.FUNDED_VARIANTS) | {"apex300_pa", "apex50_pa"}
    assert n == (4 * 5 * 2 + 5 + 2 * 3 * 3 * 2) * 3
    assert {v[1] for v in verdicts} == {True, False}                   # the gate passes some configs and fails others
    assert any(dict(v[2])["one_direction"] == "FAIL" for v in verdicts) and any(dict(v[2])["stop_5x_target"] == "FAIL" for v in verdicts)


def test_apex50_pa_with_R_readings_equals_Rs_apex(cases, native, files):
    """L/apex300's 50K spec under R's readings (r_compat) is R's `apex`: the file path through apex300 == R's funded.evaluate_funded."""
    n = 0
    for c in cases["funded"]:
        if c["variant"] != "apex" or c["path"] != "ev":
            continue
        ref = native[c["id"]]
        mine = S.score_funded(_mem(files, c["members"]), "apex50_pa", c["policy"], micros=c["micros"], rules=c["rules"], boots=0,
                              **S._ext().r_compat("apex50_pa"))
        for m, r in ref["models"].items():
            assert _js(mine["models"][m]) == r, (c["id"], m)
            n += 1
    assert n == 4 * 2 * 3


def test_c1_lift_identical_to_native_R(cases, native, files):
    for c in cases["lift"]:
        ref = native[c["id"]]
        (m,) = c["members"]
        pool = [files[x] for x in c["pool"]]
        if c["path"] == "eval":
            mine = S.lift_vs_control(files[m["b"]], pool, c["firm"], c["rules"], micros=m["micros"], sess=m["sess"], K=c["K"],
                                     seed=ref["seed"], boots=c["boots"])
            assert mine["K"] == ref["K"] == c["K"]
            for mod in S.MODELS:
                for k in ("real_p5", "ctrl_p5", "ctrl_p5_sd", "lift", "ci"):
                    assert mine["models"][mod][k] == ref["models"][mod][k], (c["id"], mod, k)
        else:
            mine = S.lift_vs_control(files[m["b"]], pool, c["variant"], c["rules"], micros=c["micros"], sess=m["sess"], K=c["K"],
                                     seed=ref["seed"], kind="funded", policy=c["policy"])
            for k in ("real_e40", "ctrl_e40", "ctrl_e40_sd", "ctrl_p40", "ctrl_p20", "lift_e40", "ctrl_e40_each"):
                assert mine[k] == ref[k], (c["id"], k, mine[k], ref[k])
        # the file path's default seed is R's when the label is R's config id
        assert S.default_seed("hm2-squeeze-tf5#21", m["sess"], "eval" if c["path"] == "eval" else "funded") == ref["seed"]


def test_rule_search_identical_to_native_R(cases, native, files):
    import hashlib
    for c in cases["search"]:
        ref = native[c["id"]]
        (m,) = c["members"]
        mine = S.search_rules(files[m["b"]], c["firm"], sess=m["sess"], boots=0, keep_arrays=True)
        assert list(mine["shape"]) == ref["shape"] and mine["walks"] == ref["walks"] and mine["primary"] == ref["primary"]
        for k in ("P5", "B5", "P1", "P3", "nr"):
            assert hashlib.sha1(np.ascontiguousarray(np.asarray(mine[k], np.float64)).tobytes()).hexdigest() == ref[k], (c["id"], k)
        for nm, rp in ref["picks"].items():
            mp = mine["picks"][nm]
            assert mp["index"] == rp["index"] and mp["stab"] == rp["stab"], (c["id"], nm)
            if "rules" in rp:
                assert mp["rules"] == rp["rules"] and mp["net_rules"] == rp["net_rules"]
                for m2, r2 in rp["models"].items():
                    for k, v in r2.items():
                        if not k.startswith("sha_"):
                            assert mp["models"][m2][k] == v, (c["id"], nm, m2, k)
        assert [mine["picks"][f"p5_{mod}"]["raw_max"] for mod in S.MODELS] == ref["max_p5"]


def test_funded_search_identical_to_native_R(cases, native, files):
    for c in cases["fsearch"]:
        ref = native[c["id"]]
        (m,) = c["members"]
        mine = S.search_funded(files[m["b"]], c["variant"], sess=m["sess"], grid=c["grid"])
        assert _js(mine["rows"]) == ref["rows"] and len(ref["rows"]) == 64, c["id"]
        assert mine["eligible"] == ref["eligible"] and _js(mine["picks"]) == ref["picks"], c["id"]
