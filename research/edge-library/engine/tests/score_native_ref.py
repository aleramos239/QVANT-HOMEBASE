#!/usr/bin/env python3
"""NATIVE-R reference for the score.py equivalence check (tests/test_score_verify.py). NOT a test module.

Runs in its OWN process and never imports score.py: only R's code (evalcore / portfolio / funded / a3_pass2 / a3p3 /
holdout_score, read-only, no bytecode) on R's own tester bundles (run ids / grid cells, R's loader). `apex300` (L's Apex 300K
rules module, which itself imports only R) is used for the apex300_pa / apex50_pa references.

    python -B tests/score_native_ref.py cases.json out.json

cases.json: {"bundles": {name: R source}, "eval": [...], "funded": [...], "lift": [...], "search": [...], "fsearch": [...]}
(case layouts: see test_score_verify.py). Every float goes out through json (repr: exact round trip); per-start outcome arrays
go out as sha1 digests of their int64 bytes.
"""
import hashlib
import json
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
import numpy as np                                      # noqa: E402

L = Path(__file__).resolve().parent.parent
REPO = L.parents[2]
R = REPO / "research" / "prop-portfolio" / "2026-09-29"
sys.path.insert(0, str(R))
sys.path.append(str(REPO))
import evalcore as E                                    # noqa: E402
import funded as F                                      # noqa: E402
import portfolio as P                                   # noqa: E402

assert "score" not in sys.modules
VARIANTS = {"flex": ("flex", None), "flex_dll": ("flex", 1200), "pro_dll": ("pro", 1200), "pro_nodll": ("pro", 0), "apex": ("apex", None)}
RK = ("day_take", "day_lock", "day_stop", "max_day_tr")


def sha(a) -> str:
    return hashlib.sha1(np.ascontiguousarray(np.asarray(a, np.int64)).tobytes()).hexdigest()


def fsha(a) -> str:
    return hashlib.sha1(np.ascontiguousarray(np.asarray(a, np.float64)).tobytes()).hexdigest()


def guard(src) -> None:
    """In-sample bundles only: the run range is read from run.json BEFORE any trade row."""
    d = E._src_dir(src)
    r = json.loads(((d if d.is_dir() else d.parent) / "run.json").read_text())
    rg = r.get("range") or {}
    if str(rg.get("end") or "9999") >= E.HOLDOUT or r.get("holdout") or rg.get("holdout"):
        raise RuntimeError(f"{src}: not an in-sample bundle ({rg})")


def summ(o, d, boots: int) -> dict:
    """P(pass <= k), bust, by-day, median day, block-bootstrap CIs: written out here, not taken from score.py / portfolio._detail."""
    ps, bs = o == 1, o == 2
    x = {f"p{k}": float((ps & (d <= k)).mean()) for k in range(1, 6)}
    x["bust5"] = float(bs.mean())
    x["bust_by"] = [float((bs & (d <= k)).mean()) for k in range(1, 6)]
    x["neither5"] = float((o == 0).mean())
    x["med_days"] = float(np.median(d[ps])) if ps.any() else None
    x["sha_o"], x["sha_d"] = sha(o), sha(d)
    if boots:
        for k in range(1, 6):
            x[f"ci_p{k}"] = E.block_ci([ps & (d <= k)], boots=boots)[0]
        x["ci_bust5"] = E.block_ci([bs], boots=boots)[0]
    return x


def full_rules(rules: dict) -> dict:
    return {"day_lock": 0, "day_take": 0, "day_stop": 0, "max_day_tr": 0, "target_take": 0, **rules}


# ------------------------------------------------------------------ eval

def eval_pf(B, c) -> dict:
    """portfolio.py path: evalcore.load(bundle) -> Ctx.calendar -> Base.from_tr -> PV -> norm_key -> make_A -> evalcore.race."""
    trs = [E.load(B[m["b"]]) for m in c["members"]]
    cal = P.Ctx.calendar(np.concatenate([t.date for t in trs]))
    ctx = P.Ctx(cal)
    pv = P.PV([(P.Base.from_tr(f"{m['b']}|{m['sess']}", ctx.cal, t, m["sess"]), int(m["micros"])) for m, t in zip(c["members"], trs)], ctx.D)
    fm = P.firm(c["firm"])
    r = full_rules(c["rules"])
    A = P.make_A(pv, fm, P.norm_key(pv, r["day_lock"], r["day_take"], r["day_stop"], r["max_day_tr"]))
    out = {"models": {m: summ(*E.race(ctx.idx5, A, fm.r, m, True, bool(r["target_take"])), c.get("boots", 0)) for m in E.MODELS},
           "primary": fm.prim, "D": int(ctx.D), "n_trades": int(pv.n_trades), "sha_tot": fsha(A.tot), "sha_worst": fsha(A.worst),
           "sha_wreal": fsha(A.wreal), "net": float(A.tot.sum()),
           "walk": {k: int(A.st[k]) for k in ("executed", "skipped", "clipped", "overlap", "conflicts", "max_conc", "cap_viol")}}
    return out


def eval_ev(B, c) -> dict:
    """evalcore.evaluate (R/evaluate.py's CLI path): evalcore.build on the tape calendar -> walk -> race, any rule dims."""
    cfg = {"members": [{"src": B[m["b"]], "sess": m["sess"], "micros": int(m["micros"]), "news": m.get("news", "all")} for m in c["members"]],
           "rules": dict(c["rules"]), "firms": [c["firm"]]}
    res = E.evaluate(cfg, mc=0, boots=c.get("boots", 0), eventual=0, funded=False)
    (f,) = res["firms"].values()
    out = {"window": res["window"], "walk": f["walk"], "cost": f["cost"], "series": f["series"], "primary": f["primary"], "models": {}}
    for m in E.MODELS:
        out["models"][m] = {k: f[m][k] for k in ("p_pass", "p_bust", "pass_by", "bust_by", "med_days_pass")}
        if "ci95_pass" in f[m]:
            out["models"][m]["ci95_pass"], out["models"][m]["ci95_bust"] = f[m]["ci95_pass"], f[m]["ci95_bust"]
    return out


# ------------------------------------------------------------------ funded

def _port(B, c):
    return E.build({"members": [{"src": B[m["b"]], "sess": m["sess"], "micros": int(m.get("micros") or 10), "news": m.get("news", "all")}
                                for m in c["members"]]})


def funded_ev(B, c) -> dict:
    """funded.evaluate_funded on an evalcore.build portfolio (R's documented call); apex300_pa / apex50_pa: apex300.evaluate_funded
    on the same R portfolio. micros=None: every member trades its own micros."""
    Pn = _port(B, c)
    rl = {k: c["rules"].get(k, 0) for k in RK}
    if c["variant"] in VARIANTS:
        f, dll = VARIANTS[c["variant"]]
        ref = F.evaluate_funded(Pn, f, micros=c["micros"], rules=rl, policy=c["policy"], dll=dll, strategy=c.get("strategy"), inputs=c.get("inputs"))
        models = F.ORDERS if f == "apex" else E.MODELS
    else:
        if str(L) not in sys.path:
            sys.path.insert(0, str(L))
        import apex300 as AX
        raw = [{"src": str(E._src_dir(B[m["b"]]) / "trades.json"), "sess": m["sess"]} for m in c["members"]]      # per-trade sl / tp checks
        ref = AX.evaluate_funded(Pn, c["variant"], micros=c["micros"], rules=rl, policy=c["policy"], start=c.get("start", "fresh"),
                                 strategy=c.get("strategy"), inputs=c.get("inputs"), both_sides=c.get("both_sides"), trades=raw,
                                 **c.get("spec", {}))
        models = AX.ORDERS
    out = {"models": {m: ref[m] for m in models}, "primary": ref["primary"], "n_days": len(Pn.days), "n_trades": int(Pn.n_trades)}
    for k in ("flags", "mae_over_limit_share", "noncompliant", "mae_limit_at_start", "stop_ge_80pct_threshold_share", "no_stop_share", "start",
              "compliance", "trade_checks", "cons_base", "commission", "stop_5x_target_basis"):
        if k in ref:
            out[k] = ref[k]
    if "cons_alt" in ref:
        out["cons_alt"] = {"cons_base": ref["cons_alt"]["cons_base"], **{m: ref["cons_alt"][m] for m in models}}
    return out


def funded_p2(B, c) -> dict:
    """funded_search / holdout_score path: 10-micro Port2 of ONE member on screen_analyze.cal_for -> DaySrc -> lifecycle -> metrics."""
    import holdout_score as HS
    import screen_analyze as SA
    (m,) = c["members"]
    t = E.load(B[m["b"]])
    idx = np.flatnonzero(E._sess_mask(t, m["sess"]))
    port = HS.Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], SA.cal_for(t))
    f, dll = VARIANTS[c["variant"]]
    S = F.make_spec(f, dll)
    rl = {k: c["rules"].get(k, 0) for k in RK}
    src = F.DaySrc(port, rl, c["micros"], events=S.kind == "apex")
    out = {"models": {}, "primary": S.primary}
    for mod in HS.MODELS_ALT["apex" if S.kind == "apex" else "lucid"]:
        res = F.lifecycle(S, src, c["policy"], F.H_LIFE, mod)
        mm = F.metrics(res, F.H_LIFE)
        if c.get("boots"):
            a = HS._start_arrays(res)
            mm["e_net_40_ci"] = E.block_ci([a["n40"]], block=60, boots=c["boots"])[0]
            mm["p_pay_20_ci"] = E.block_ci([((a["first"] > 0) & (a["first"] <= 20)).astype(float)], block=60, boots=c["boots"])[0]
        out["models"][mod] = mm
    return out


# ------------------------------------------------------------------ C1 lift

def lift_eval(B, c) -> dict:
    """portfolio.py: Ctx.controls (K day-matched draws from the given pool, seed crc32(cid) % 100000) + control_lift."""
    (m,) = c["members"]
    tr = E.load(B[m["b"]])
    ctx = P.Ctx(P.Ctx.calendar(tr.date), K=c["K"])
    cid = c["cid"]
    b = ctx.base({"cid": cid, "src": B[m["b"]], "sess": m["sess"], "ctrl_srcs": [B[x] for x in c["pool"]]})
    fm = P.firm(c["firm"])
    r = full_rules(c["rules"])
    ci = fm.cell_index(r)
    members = [(b, int(m["micros"]))]
    res = P.grid_outcomes(ctx, fm, P.PV(members, ctx.D), E.MODELS, cells=[ci])
    ps_all = {mod: (res[mod][0][ci] == 1, res[mod][1][ci]) for mod in E.MODELS}
    lf = P.control_lift(ctx, fm, members, ci, ps_all, c.get("boots", 0))
    return {"K": lf["K"], "seed": zlib.crc32(cid.encode()) % 100000, "models": {mod: lf[mod] for mod in E.MODELS}}


def lift_funded(B, c) -> dict:
    """holdout_score.score_funded's control block, written out: daymatched_controls (seed crc32('fund|cid')) -> Port2 -> metrics."""
    import holdout_score as HS
    (m,) = c["members"]
    t = E.load(B[m["b"]])
    idx = np.flatnonzero(E._sess_mask(t, m["sess"]))
    cal = P.Ctx.calendar(t.date)
    f, dll = VARIANTS[c["variant"]]
    S = F.make_spec(f, dll)
    rl = {k: c["rules"].get(k, 0) for k in RK}
    pool = E.concat_tr([E.load(B[x]) for x in c["pool"]])
    sub = SimpleNamespace(date=t.date[idx], sess=t.sess[idx], n=len(idx))
    seed = zlib.crc32(f"fund|{c['cid']}".encode())
    cs = E.daymatched_controls(sub, pool, K=c["K"], seed=seed, mask=None, carry=("side", "g", "mae", "mfe", "risk", "sess"))
    port = HS.Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], cal)
    real = F.metrics(F.lifecycle(S, F.DaySrc(port, rl, c["micros"], events=S.kind == "apex"), c["policy"], F.H_LIFE, S.primary), F.H_LIFE)
    ce = []
    for x in cs:
        cp = HS.Port2(x["date"], x["te"], x["tx"], x["side"], x["g"], x["mae"], x["mfe"], x["risk"], cal)
        mm = F.metrics(F.lifecycle(S, F.DaySrc(cp, rl, c["micros"], events=S.kind == "apex"), c["policy"], F.H_LIFE, S.primary), F.H_LIFE)
        ce.append((mm["e_net_40"], mm["p_pay_40"], mm["p_pay_20"]))
    ce = np.array(ce)
    return {"K": len(ce), "seed": seed, "real_e40": real["e_net_40"], "ctrl_e40": float(ce[:, 0].mean()),
            "ctrl_e40_sd": float(ce[:, 0].std(ddof=1)) if len(ce) > 1 else None, "ctrl_p40": float(ce[:, 1].mean()),
            "ctrl_p20": float(ce[:, 2].mean()), "lift_e40": float(real["e_net_40"] - ce[:, 0].mean()), "ctrl_e40_each": ce[:, 0].tolist()}


# ------------------------------------------------------------------ searches

def search_eval(B, c) -> dict:
    """a3p3.search3 on a3_pass2.port_of + the pass-3 picks (a3_pass2.pick of a3_rules.stable)."""
    import a3_pass2 as A2
    import a3_rules as A1
    import a3p3 as P3
    import screen_analyze as SA
    (m,) = c["members"]
    t = A2.load_src(B[m["b"]])
    cal = SA.cal_for(t)
    port = A2.port_of(t, np.flatnonzero(E._sess_mask(t, m["sess"])), cal)
    prim = E.primary_model(c["firm"])
    ref = P3.search3(port, len(cal), c["firm"], prim)
    out = {"shape": list(ref["shape"]), "walks": ref["walks"], "primary": prim,
           **{k: fsha(ref[k]) for k in ("P5", "B5", "P1", "P3", "nr")}, "max_p5": [float(np.nanmax(ref["P5"][k])) for k in range(3)], "picks": {}}
    for k, mod in enumerate(P3.M3):
        ci = A2.pick(A1.stable(ref["P5"][k]), ref["nr"])
        own, A = P3.eval_cell3(port, len(cal), c["firm"], P3.cell_of(c["firm"], ci))
        out["picks"][f"p5_{mod}"] = {"index": [int(i) for i in ci], "rules": dict(zip(A2.AX, P3.cell_of(c["firm"], ci))),
                                     "stab": float(A1.stable(ref["P5"][k])[ci]), "net_rules": float(A.tot.sum()),
                                     "models": {m2: summ(*own[m2], 0) for m2 in P3.M3}}
    for nm, arr in (("speed_p1", "P1"), ("speed_p3", "P3")):
        ci = A2.pick(A1.stable(ref[arr]), ref["nr"])
        out["picks"][nm] = {"index": [int(i) for i in ci], "stab": float(A1.stable(ref[arr])[ci])}
    return out


def search_funded(B, c) -> dict:
    """funded.search on a 10-micro Port2 (funded_search's port) + funded.pick_cells over the eligible rows."""
    import holdout_score as HS
    (m,) = c["members"]
    t = E.load(B[m["b"]])
    idx = np.flatnonzero(E._sess_mask(t, m["sess"]))
    port = HS.Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], P.Ctx.calendar(t.date))
    f, dll = VARIANTS[c["variant"]]
    S = F.make_spec(f, dll)
    rows = F.search(port, S, c["grid"])
    ok = [r for r in rows if not (S.kind == "apex" and r.get("cut_share", 0.0) > 0.02)]
    return {"rows": rows, "eligible": len(ok), "picks": F.pick_cells(ok)}


FN = {"eval": {"pf": eval_pf, "ev": eval_ev}, "funded": {"ev": funded_ev, "p2": funded_p2}, "lift": {"eval": lift_eval, "funded": lift_funded},
      "search": {"a3p3": search_eval}, "fsearch": {"funded": search_funded}}


def _js(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def main(argv) -> int:
    cases = json.loads(Path(argv[1]).read_text())
    B = cases["bundles"]
    for s in B.values():
        guard(s)
    F.desk_window_wait()
    out = {}
    for kind, fns in FN.items():
        for c in cases.get(kind, []):
            out[c["id"]] = fns[c["path"]](B, c)
    Path(argv[2]).write_text(json.dumps(out, default=_js))
    assert "score" not in sys.modules
    assert not list(R.glob("__pycache__"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
