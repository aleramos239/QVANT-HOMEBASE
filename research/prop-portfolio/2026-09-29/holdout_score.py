#!/usr/bin/python3
"""FROZEN holdout scorer (2025-01-01 -> latest data), shared by the NQ and ES pilots (`PP_PILOT=es` / `--pilot es`).

Scores every finalist of out/holdout_manifest.json with the in-sample code (evalcore / portfolio / funded) UNCHANGED:
  eval finalists   P1/P2/P3/P5 (+ block-bootstrap CI), bust5, by-day, eod / realized / intraday, lift vs day-matched random
                   controls (same days, same rules, controls = the same random runs re-run on the holdout days), news split,
                   executed shares, by-half-year P5, the 60% criterion (P(pass<=5d) >= 0.60, primary model and each bound);
  funded finalists P(first payout by 20/40/60d), median days, E[first cheque], E$40 / E$60, bust-before-payout, rolling 2025+ starts,
                   alt breach models, lift vs the controls;
  multi-account    P(>=1 pass <= 5d) of the frozen mixes (primary / eod / realized / intraday);
  side by side     in-sample (frozen numbers) vs walk-forward OOS vs holdout, and the holdout 'decay'.
NO re-tuning: nothing here chooses or ranks anything after seeing 2025+ numbers; every choice is the manifest's.

  holdout_score.py validate [manifest.json]   run the SAME code on the 2021-24 window (in-sample sources) and compare with the frozen in-sample numbers
                                   (reads no 2025+ data); writes out/holdout_validate_insample.json
  holdout_score.py selftest [manifest.json]   the holdout code path on in-sample data (job keys -> in-sample sources) must equal the in-sample path
  holdout_score.py score           score the holdout (refuses unless the manifest + code hashes match and every holdout job is done)
  holdout_score.py hashes          print the sha256 of the manifest and of the scoring code

Run with /usr/bin/python3 and PYTHONPATH=~/ramos-quant-homebase (numpy). Single process (desk window gate 09:18-09:36 ET honoured).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E          # noqa: E402
import funded as F            # noqa: E402
import portfolio as P         # noqa: E402

D = E.D
OUT = D / "out"
MANIFEST, SHA_FILE = OUT / "holdout_manifest.json", OUT / "holdout_manifest.sha256"
CODE_DIR = Path(__file__).resolve().parent
CODE_FILES = ("evalcore.py", "funded.py", "portfolio.py", "holdout_score.py")
MODELS = E.MODELS
H5, HL = E.H_EVAL, F.H_LIFE
CRITERION = 0.60


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def run_counts(man: dict) -> dict:
    """Holdout runs of the manifest and how many finished (jobs.jsonl); they count against hb.py's screening-run cap (400 per pilot)."""
    done = set()
    for ln in (D / "jobs.jsonl").read_text().splitlines():
        if ln.strip():
            j = json.loads(ln)
            if j.get("stage") == "holdout" and j.get("status") == "done":
                done.add(j["key"])
    fin = [j for j in man["jobs"] if j["role"] == "finalist"]
    ctl = [j for j in man["jobs"] if j["role"] == "control"]
    return {"finalist_runs": len(fin), "control_runs": len(ctl), "total": len(man["jobs"]), "done": sum(1 for j in man["jobs"] if j["key"] in done),
            "cap_screening_runs": 400}


def sha256_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def code_hashes() -> dict:
    return {f: sha256_file(CODE_DIR / f) for f in CODE_FILES}


def load_manifest(path=MANIFEST) -> dict:
    return json.loads(Path(path).read_text())


def verify_frozen(man: dict) -> list:
    """Problems that forbid scoring the holdout (empty list = frozen and unchanged)."""
    bad = []
    if not SHA_FILE.exists():
        return ["no holdout_manifest.sha256"]
    if sha256_file(MANIFEST) != SHA_FILE.read_text().split()[0]:
        bad.append("manifest sha256 differs from holdout_manifest.sha256")
    for f, h in code_hashes().items():
        if man["code_sha256"].get(f) != h:
            bad.append(f"{f} changed since the freeze")
    for f, h in man.get("inputs_sha256", {}).items():
        p = Path(f) if Path(f).is_absolute() else (CODE_DIR / f)
        if not p.exists() or sha256_file(p) != h:
            bad.append(f"input {f} changed since the freeze")
    return bad


# ------------------------------------------------------------------ source resolution (holdout runs | in-sample cells)

class Resolver:
    """config id -> TR, control id -> TR. mode 'holdout': the finished holdout runs (jobs.jsonl key -> run id); 'insample': the
    in-sample heat-map cells / runs of the manifest (the SAME code on the 2021-24 window; evalcore drops 2025+ there)."""

    def __init__(self, man: dict, mode: str, runs: dict | None = None):
        self.man, self.mode = man, mode
        self.runs: dict = dict(runs or {})              # runs override = selftest only (job key -> in-sample source standing in for a holdout run)
        if mode == "holdout" and runs is None:
            for ln in (D / "jobs.jsonl").read_text().splitlines():
                if ln.strip():
                    j = json.loads(ln)
                    if j.get("stage") == "holdout" and j.get("status") == "done":
                        self.runs[j["key"]] = j["id"]

    def _tr(self, spec: dict):
        if self.mode == "insample":
            return E.load(spec["in_sample_src"])
        run = self.runs.get(spec["job_key"])
        if run is None:
            raise RuntimeError(f"holdout job {spec['job_key']} is not done")
        t = E.load(run, holdout=True)
        h0, h1 = self.man["holdout"]["start"], self.man["holdout"]["end"]
        if t.n and (min(t.iso) < h0 or max(t.iso) > h1):
            raise RuntimeError(f"{spec['job_key']}: trades outside {h0}..{h1}")
        return t

    def tr(self, cfg: str):
        return self._tr(self.man["configs"][cfg])

    def ctrl_pool(self, ids: list):
        return E.concat_tr([self._tr(self.man["controls"][i]) for i in ids])


def calendar(man: dict, mode: str, extra=()) -> np.ndarray:
    if mode == "insample":
        return P.Ctx.calendar(extra)
    from homebase.backtest.tape import TapeStore
    h = man["holdout"]
    ds = TapeStore().sessions(E.ROOT, dt.date.fromisoformat(h["start"]), dt.date.fromisoformat(h["end"]))
    return np.array(sorted({d.toordinal() for d in ds} | {int(x) for x in extra}), np.int64)


class Ctx2(P.Ctx):
    """portfolio.Ctx on the manifest's sources (same Base / controls construction and seeds as the in-sample code)."""

    def __init__(self, cal, res: Resolver, K: int = 10):
        super().__init__(cal, None, None, K)
        self.res = res

    def base(self, cand: dict):
        cid = cand["cid"]
        if cid not in self.bases:
            self.bases[cid] = P.Base.from_tr(cid, self.cal, self.res.tr(cand["cfg"]), cand.get("sess", "all"), meta=cand)
            self.cands[cid] = cand
        return self.bases[cid]

    def pool_tr(self, cand: dict):
        ids = tuple(cand["ctrl"])
        if ids not in self._pools:
            self._pools[ids] = self.res.ctrl_pool(list(ids))
        return self._pools[ids], cand.get("pool_flag", "exact")

    def controls(self, b):
        if b.bid not in self._ctl:
            cand = self.cands[b.name]
            pool, flag = self.pool_tr(cand)
            tr = self.res.tr(cand["cfg"])
            m = E._sess_mask(tr, cand.get("sess", "all"))
            sub = SimpleNamespace(date=tr.date[m], sess=tr.sess[m], n=int(m.sum()))
            cs = E.daymatched_controls(sub, pool, K=self.K, seed=zlib.crc32(b.name.encode()) % 100000, mask=None,
                                       carry=("side", "g", "mae", "mfe", "risk", "sess"))
            self._ctl[b.bid] = [P.Base(f"{b.name}~c{k}", self.cal, c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["mfe"], c["risk"],
                                       dict(b.meta, control=k, pool_flag=flag)) for k, c in enumerate(cs)]
        return self._ctl[b.bid]


def make_ctx(man: dict, mode: str, K: int | None = None, runs: dict | None = None) -> Ctx2:
    res = Resolver(man, mode, runs)
    ids = sorted({c for f in man["finalists"].values() for c in (m["cfg"] for m in f["members"])}
                 | {f["cfg"] for f in man["funded"].values()})
    trs = [res.tr(c) for c in ids]
    extra = np.concatenate([t.date for t in trs]) if trs else ()
    return Ctx2(calendar(man, mode, extra), res, K or man["scoring"]["K_controls"])


def cand_of(man: dict, cfg: str, sess: str, pool: str = "ctrl_eval") -> dict:
    c = man["configs"][cfg]
    return {"cid": f"{cfg}|{sess}", "cfg": cfg, "sess": sess, "fam": c["fam"], "tf": c["tf"], "params": c.get("params", {}),
            "ctrl": c[pool]["ids"], "pool_flag": c[pool].get("flag", "exact")}


# ------------------------------------------------------------------ eval finalists

def _detail(o, d, boots: int) -> dict:
    return P._detail(o, d, boots)


def _by_day(o, d) -> dict:
    ps, bs = o == 1, o == 2
    return {"pass_by_day": [float((ps & (d <= k)).mean()) for k in range(1, 6)], "bust_by_day": [float((bs & (d <= k)).mean()) for k in range(1, 6)],
            "pass_on_day": [float((ps & (d == k)).mean()) for k in range(1, 6)], "bust_on_day": [float((bs & (d == k)).mean()) for k in range(1, 6)],
            "neither_5d": float((o == 0).mean())}


def eval_cell(ctx: Ctx2, fm: P.Firm, pv: P.PV, rules: dict):
    """-> ({model: (outcome[S], day[S])}, DayArr). Same path as portfolio.make_A / race_cell for one explicit rules cell."""
    dl, dtk, ds, mt, tt = (rules["day_lock"], rules["day_take"], rules["day_stop"], rules["max_day_tr"], rules["target_take"])
    key = P.norm_key(pv, dl, dtk, ds, mt)
    A = P.make_A(pv, fm, key)
    return {m: E.race(ctx.idx5, A, fm.r, m, True, bool(tt)) for m in MODELS}, A, key


def exec_of(ctx: Ctx2, fm: P.Firm, members, rules: dict) -> dict:
    pv = P.PV(members, ctx.D)
    dl, dtk, ds, mt = P.norm_key(pv, rules["day_lock"], rules["day_take"], rules["day_stop"], rules["max_day_tr"])
    A = E.walk(pv, fm.cap, (int(mt), float(ds), float(dl), 1.0, 1.0, False), want_chk=False, micros=None, dll=fm.dll, day_take=float(dtk), collect=True)
    ex = A.st["exec"]
    rows = [{"name": b.name, "micros": int(n), "executed": int(ex.get(b.bid, [0, 0.0])[0]), "net": float(ex.get(b.bid, [0, 0.0])[1])} for b, n in members]
    tc, pos = sum(r["executed"] for r in rows), sum(max(r["net"], 0.0) for r in rows)
    for r in rows:
        r["trade_share"] = r["executed"] / tc if tc else None
        r["net_share"] = max(r["net"], 0.0) / pos if pos > 0 else None
    return {"members": rows, "executed_total": tc, "net_total": float(sum(r["net"] for r in rows))}


def half_year(ctx: Ctx2, o, d, prim_model_arrays) -> dict:
    ds = [dt.date.fromordinal(int(x)) for x in ctx.cal[:ctx.S]]
    lab = np.array([f"{x.year}H{1 if x.month <= 6 else 2}" for x in ds])
    ps = o == 1
    return {k: {"n_starts": int((lab == k).sum()), "p5": float(ps[lab == k].mean())} for k in sorted(set(lab))}


def score_eval(ctx: Ctx2, man: dict, fid: str, boots: int = 2000) -> dict:
    fin = man["finalists"][fid]
    fm = P.firm(fin["firm"])
    members = [(ctx.base(cand_of(man, m["cfg"], m["sess"])), int(m["micros"])) for m in fin["members"]]
    pv = P.PV(members, ctx.D)
    P.gate()
    res, A, key = eval_cell(ctx, fm, pv, fin["rules"])
    out = {"id": fid, "firm": fin["firm"], "role": fin["role"], "primary": fm.prim, "n_starts": int(ctx.S), "n_sessions": int(ctx.D),
           "window": [dt.date.fromordinal(int(ctx.cal[0])).isoformat(), dt.date.fromordinal(int(ctx.cal[-1])).isoformat()]}
    for m in MODELS:
        out[m] = _detail(res[m][0], res[m][1], boots if m in (fm.prim, "eod", "intraday") else 0)
    P_ = out[fm.prim]
    out["headline"] = {k: P_[k] for k in ("p1", "p2", "p3", "p5", "bust5", "med_days")} | {"ci_p5": P_.get("ci_p5"), "model": fm.prim}
    out["by_day"] = {m: _by_day(*res[m]) for m in MODELS}
    st = A.st
    out["walk"] = {"executed": st["executed"], "skipped": st["skipped"], "clipped": st["clipped"], "opposite_conflicts": int(st["conflicts"]),
                   "overlap_entries": st["overlap"], "max_concurrent_micros": st["max_conc"], "cap_violations": int(st["cap_viol"])}
    out["series"] = E._series(A)
    out["exec"] = exec_of(ctx, fm, members, fin["rules"])
    out["by_half_year"] = {m: half_year(ctx, *res[m], None) for m in (fm.prim,)}
    out["trades_raw"] = [{"cfg": m["cfg"], "sess": m["sess"], "micros": m["micros"], "n": b.n} for m, (b, _) in zip(fin["members"], members)]
    nd = E.news_days()
    if man["holdout"].get("news_available", True):
        cn = np.array([int(x) in nd for x in ctx.cal])
        wn = cn[ctx.idx5].any(1)
        nws = {"n_starts_with_news": int(wn.sum()), "n_starts_without": int((~wn).sum())}
        for m in MODELS:
            ps, bs = res[m][0] == 1, res[m][0] == 2
            nws[m] = {"p5_news": float(ps[wn].mean()) if wn.any() else None, "p5_nonnews": float(ps[~wn].mean()) if (~wn).any() else None,
                      "bust5_news": float(bs[wn].mean()) if wn.any() else None, "bust5_nonnews": float(bs[~wn].mean()) if (~wn).any() else None}
        out["news"] = nws
    else:
        out["news"] = "N/A (no news-day source for the holdout)"
    # lift vs day-matched random controls (every member -> its own k-th control; same micros, same rules)
    ctrls = [ctx.controls(b) for b, _ in members]
    K = min(len(c) for c in ctrls)
    cp = {m: [] for m in MODELS}
    for k in range(K):
        cpv = P.PV([(c[k], n) for c, (_, n) in zip(ctrls, members)], ctx.D)
        r, _, _ = eval_cell(ctx, fm, cpv, fin["rules"])
        for m in MODELS:
            cp[m].append(r[m][0] == 1)
    lift = {"K": K, "pool_flag": [c[0].meta.get("pool_flag") for c in ctrls]}
    for m in MODELS:
        c = np.mean(np.stack(cp[m]), 0)
        real = (res[m][0] == 1).astype(float)
        diff = real - c
        lift[m] = {"real_p5": float(real.mean()), "ctrl_p5": float(c.mean()), "ctrl_p5_sd": float(np.std([x.mean() for x in cp[m]])),
                   "lift": float(diff.mean()), "ci": E.block_ci([diff], boots=boots)[0]}
    out["lift"] = lift
    p5 = {m: out[m]["p5"] for m in MODELS}
    ci_lo = (out[fm.prim].get("ci_p5") or [None, None])[0]
    out["criterion"] = {"threshold": CRITERION, "primary_p5": P_["p5"], "primary_pass": bool(P_["p5"] >= CRITERION),
                        "primary_ci_lo_pass": bool(ci_lo is not None and ci_lo >= CRITERION),
                        "bounds": {m: bool(p5[m] >= CRITERION) for m in MODELS}}
    out["arrays"] = {m: (res[m][0], res[m][1]) for m in MODELS}      # for the multi-account layer (dropped before writing)
    return out


# ------------------------------------------------------------------ funded finalists

class Port2:
    """Port-like (days of walk tuples + parallel mfe lists) at 10 micros; DaySrc rescales to the cell's micros (same as the funded search)."""

    def __init__(self, date, te, tx, side, g, mae, mfe, risk, cal):
        o = np.lexsort((te, date))
        pos = np.searchsorted(cal, date[o])
        self.days, self.mfe = [[] for _ in cal], [[] for _ in cal]
        for j, p in zip(o, pos):
            self.days[p].append((int(te[j]), int(tx[j]), int(side[j]), float(g[j]), float(mae[j]), 10, float(risk[j]), 0))
            self.mfe[p].append(float(mfe[j]))


VARIANTS = {"flex": ("flex", None), "flex_dll": ("flex", 1200), "pro_dll": ("pro", 1200), "pro_nodll": ("pro", 0), "apex": ("apex", None)}
MODELS_ALT = {"lucid": ("realized", "eod", "intraday"), "apex": ("pess", "nat", "opt")}


def _start_arrays(res) -> dict:
    n = len(res)
    a = {k: np.zeros(n) for k in ("first", "n40", "bust")}
    for i, (b, pays, cuts, ex) in enumerate(res):
        a["bust"][i] = b
        if pays:
            a["first"][i] = pays[0][0]
            a["n40"][i] = sum(p[2] for p in pays if p[0] <= 40)
    return a


def score_funded(ctx: Ctx2, man: dict, fid: str, boots: int = 2000) -> dict:
    fin = man["funded"][fid]
    f, dll = VARIANTS[fin["variant"]]
    S = F.make_spec(f, dll)
    apex = S.kind == "apex"
    cfg = man["configs"][fin["cfg"]]
    t = ctx.res.tr(fin["cfg"])
    idx = np.flatnonzero(E._sess_mask(t, fin["sess"]))
    port = Port2(t.date[idx], t.te[idx], t.tx[idx], t.side[idx], t.g[idx], t.mae[idx], t.mfe[idx], t.risk[idx], ctx.cal)
    rl = {k: fin["rules"][k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}
    micros, T = int(fin["micros"]), fin["policy"]
    src = F.DaySrc(port, rl, micros, events=apex)
    P.gate()
    out = {"id": fid, "variant": fin["variant"], "rank": fin.get("rank"), "primary": S.primary, "n_starts": port_starts(port),
           "window": [dt.date.fromordinal(int(ctx.cal[0])).isoformat(), dt.date.fromordinal(int(ctx.cal[-1])).isoformat()],
           "trades": int(len(idx))}
    models = MODELS_ALT["apex" if apex else "lucid"]
    for m in models:
        res = F.lifecycle(S, src, T, HL, m)
        mm = F.metrics(res, HL)
        if m == S.primary:
            a = _start_arrays(res)
            mm["e_net_40_ci"] = E.block_ci([a["n40"]], block=60, boots=boots)[0]
            mm["p_pay_20_ci"] = E.block_ci([((a["first"] > 0) & (a["first"] <= 20)).astype(float)], block=60, boots=boots)[0]
        out[m] = mm
    out["headline"] = out[S.primary]
    if apex:
        out["apex_flags"] = F.apex_flags(cfg["strategy"], dict(cfg["inputs"]), rl, out[S.primary]["cut_share"])
    # controls: day-matched random runs (same funded cell)
    cand = cand_of(man, fin["cfg"], fin["sess"], "ctrl_funded")
    pool, _ = ctx.pool_tr(cand)
    sub = SimpleNamespace(date=t.date[idx], sess=t.sess[idx], n=len(idx))
    cs = E.daymatched_controls(sub, pool, K=ctx.K, seed=zlib.crc32(f"fund|{cand['cid']}".encode()), mask=None, carry=("side", "g", "mae", "mfe", "risk", "sess"))
    ce = []
    for c in cs:
        cp = Port2(c["date"], c["te"], c["tx"], c["side"], c["g"], c["mae"], c["mfe"], c["risk"], ctx.cal)
        mm = F.metrics(F.lifecycle(S, F.DaySrc(cp, rl, micros, events=apex), T, HL, S.primary), HL)
        ce.append((mm["e_net_40"], mm["p_pay_40"], mm["p_pay_20"]))
    ce = np.array(ce)
    h = out[S.primary]
    out["lift"] = {"K": len(ce), "ctrl_e40": float(ce[:, 0].mean()), "ctrl_e40_sd": float(ce[:, 0].std(ddof=1)) if len(ce) > 1 else None,
                   "ctrl_p40": float(ce[:, 1].mean()), "ctrl_p20": float(ce[:, 2].mean()), "lift_e40": float(h["e_net_40"] - ce[:, 0].mean())}
    return out


def port_starts(port) -> int:
    return len(port.days) - HL + 1


# ------------------------------------------------------------------ multi-account

def score_multi(man: dict, evals: dict, boots: int = 2000) -> dict:
    out = {}
    for n, mix in man["multi_account"].items():
        accts = mix["accounts"]
        if not all(a in evals for a in accts):
            continue

        def ents(model):
            return [{"firm": evals[a]["firm"], "label": a, "o": evals[a]["arrays"][model if model else P.E.primary_model(evals[a]["firm"])][0],
                     "d": evals[a]["arrays"][model if model else P.E.primary_model(evals[a]["firm"])][1],
                     "fee": P.firm(evals[a]["firm"]).fee, "activation": P.firm(evals[a]["firm"]).activation} for a in accts]
        r = {"counts": mix.get("counts"), "accounts": accts, "primary": P.multi_metrics(ents(None), boots)}
        for m in MODELS:
            r[m] = P.multi_metrics(ents(m), 0)
        out[str(n)] = r
    return out


# ------------------------------------------------------------------ run everything

def run(man: dict, mode: str, boots: int = 2000, log=print, runs: dict | None = None) -> dict:
    t0 = time.time()
    ctx = make_ctx(man, mode, runs=runs)
    log(f"[{mode}] calendar {ctx.D} sessions, {ctx.S} rolling 5-day starts")
    evals = {}
    for fid in man["finalists"]:
        evals[fid] = score_eval(ctx, man, fid, boots)
        h = evals[fid]["headline"]
        log(f"  eval {fid}: P5 {h['p5']:.3f} (eod {evals[fid]['eod']['p5']:.3f} rlz {evals[fid]['realized']['p5']:.3f} intra {evals[fid]['intraday']['p5']:.3f})"
            f" lift {evals[fid]['lift'][evals[fid]['primary']]['lift']:+.3f}")
    fund = {}
    for fid in man["funded"]:
        fund[fid] = score_funded(ctx, man, fid, boots)
        h = fund[fid]["headline"]
        log(f"  funded {fid}: P20/40/60 {h['p_pay_20']:.2f}/{h['p_pay_40']:.2f}/{h['p_pay_60']:.2f} E40 {h['e_net_40']:.0f} E60 {h['e_net_60']:.0f}")
    multi = score_multi(man, evals, boots)
    res = {"mode": mode, "generated": dt.datetime.now().isoformat(timespec="seconds"), "secs": round(time.time() - t0, 1),
           "calendar": {"sessions": int(ctx.D), "starts5": int(ctx.S), "start": dt.date.fromordinal(int(ctx.cal[0])).isoformat(),
                        "end": dt.date.fromordinal(int(ctx.cal[-1])).isoformat()},
           "holdout_runs": run_counts(man) if mode == "holdout" else None,
           "eval": {k: {a: b for a, b in v.items() if a != "arrays"} for k, v in evals.items()}, "funded": fund, "multi": multi}
    res["criterion_by_firm"] = criterion_by_firm(man, res["eval"])
    return res


def criterion_by_firm(man: dict, ev: dict) -> dict:
    """Per firm: does ANY finalist reach P(pass<=5d) >= 60% under the primary model (and under each bound)? Apex firms: compliant finalists only."""
    out = {}
    for f in sorted({v["firm"] for v in ev.values()}):
        rows = [(k, v) for k, v in ev.items() if v["firm"] == f]
        elig = [(k, v) for k, v in rows if not man["finalists"][k].get("apex_flags")]
        out[f] = {"n_finalists": len(rows), "n_eligible": len(elig),
                  "best_primary": max(((v["headline"]["p5"], k) for k, v in elig), default=None),
                  "pass_primary": any(v["criterion"]["primary_pass"] for _, v in elig),
                  "pass_primary_ci_lo": any(v["criterion"]["primary_ci_lo_pass"] for _, v in elig),
                  "pass_by_bound": {m: any(v["criterion"]["bounds"][m] for _, v in elig) for m in MODELS},
                  "passing": [k for k, v in elig if v["criterion"]["primary_pass"]]}
    return out


# ------------------------------------------------------------------ in-sample validation + report

def compare_insample(man: dict, res: dict) -> dict:
    """Frozen in-sample numbers vs what this code gives on the 2021-24 window (plumbing check)."""
    rows, mx = [], 0.0
    for fid, f in man["finalists"].items():
        ins = f.get("insample") or {}
        if "p5" in ins and fid in res["eval"]:
            d = res["eval"][fid]["headline"]["p5"] - ins["p5"]
            rows.append({"id": fid, "frozen_p5": ins["p5"], "rescored_p5": res["eval"][fid]["headline"]["p5"], "diff": d,
                         "frozen_lift": ins.get("lift"), "rescored_lift": res["eval"][fid]["lift"][res["eval"][fid]["primary"]]["lift"]})
            mx = max(mx, abs(d))
    frows = []
    for fid, f in man["funded"].items():
        ins = f.get("insample") or {}
        if "e_net_40" in ins and fid in res["funded"]:
            h = res["funded"][fid]["headline"]
            frows.append({"id": fid, "frozen_e40": ins["e_net_40"], "rescored_e40": h["e_net_40"], "frozen_p20": ins.get("p_pay_20"), "rescored_p20": h["p_pay_20"]})
    return {"eval": rows, "funded": frows, "max_abs_p5_diff": mx}


# ------------------------------------------------------------------ markdown report (side by side + decay)

def _f(x, n=3):
    return "n/a" if x is None else f"{x:.{n}f}"


def _ci(c):
    return "" if not c or c[0] is None else f" [{c[0]:.2f},{c[1]:.2f}]"


def summary_md(man: dict, res: dict, title: str, mpath=None) -> str:
    ev, fu = res["eval"], res["funded"]
    cal = res["calendar"]
    L = [f"# {title}", f"Window {cal['start']}..{cal['end']} ({cal['sessions']} sessions, {cal['starts5']} rolling 5-day starts); mode {res['mode']}; "
         f"manifest sha256 {sha256_file(mpath or MANIFEST)[:16]}...; no re-tuning, every number is the frozen finalist scored by the frozen code.",
         (f"Holdout runs: {res['holdout_runs']['finalist_runs']} finalist + {res['holdout_runs']['control_runs']} control = {res['holdout_runs']['total']} "
          f"({res['holdout_runs']['done']} done), counted in the 400-run screening cap." if res.get("holdout_runs") else "In-sample validation: no 2025+ data read."),
         "Columns: IS = frozen in-sample (2021-09-22..2024-12-31, primary model) | WF = in-sample walk-forward OOS | HO = holdout. P1/P2/P3/P5 = P(pass <= k days), "
         "bust5 = P(bust within 5 days); bounds eod/realized/intraday; lift = P5 - day-matched random control (same days, same rules); decay = HO P5 - IS P5.", ""]
    L.append("## 60% criterion per firm (P(pass <= 5d) >= 0.60, primary model; Apex firms: rule-compliant finalists only)")
    for f, c in res["criterion_by_firm"].items():
        bp = c["best_primary"]
        L.append(f"- {f}: best eligible finalist {bp[1] if bp else 'n/a'} P5 {_f(bp[0] if bp else None)} -> primary {'PASS' if c['pass_primary'] else 'FAIL'}"
                 f" (CI lower bound >= 0.60: {'yes' if c['pass_primary_ci_lo'] else 'no'}); bounds eod/realized/intraday: "
                 + "/".join('Y' if c['pass_by_bound'][m] else 'n' for m in MODELS) + f"; passing: {c['passing'] or 'none'}")
    L.append("")
    for f in sorted({v["firm"] for v in ev.values()}, key=lambda x: list(man["firms"]).index(x)):
        fm = man["firms"][f]
        L.append(f"## {f} ({fm['rules_id']}; primary {fm['primary']}{'; UNCONFIRMED' if fm['unconfirmed'] else ''})")
        L.append("| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for fid, v in ev.items():
            if v["firm"] != f:
                continue
            fin = man["finalists"][fid]
            ins = fin.get("insample") or {}
            h = v["headline"]
            lf = v["lift"][v["primary"]]
            shr = {x["name"]: x["trade_share"] for x in v["exec"]["members"]}
            mem = "; ".join(f"{m['cfg']}/{m['sess']}/{m['micros']}" + (f" ({shr[m['cfg'] + '|' + m['sess']]:.0%} of executed)" if len(fin["members"]) > 1 and shr.get(m['cfg'] + '|' + m['sess']) is not None else "")
                            for m in fin["members"])
            rl = fin["rules"]
            rs = f"L{rl['day_lock'] or '-'} K{rl['day_take'] or '-'} S{rl['day_stop'] or '-'} T{rl['max_day_tr'] or '-'} {'TT' if rl['target_take'] else 'tt'}"
            dec = None if ins.get("p5") is None else h["p5"] - ins["p5"]
            flag = " APEX:" + ",".join(fin["apex_flags"]) if fin["apex_flags"] else ""
            L.append(f"| {fid}{flag} | {'+'.join(fin['roles'])} | {mem} | {rs} | {_f(ins.get('p5'), 2)} | {_f(ins.get('wf_oos_p5'), 2)} | "
                     f"{_f(h['p1'], 2)}/{_f(h['p2'], 2)}/{_f(h['p3'], 2)}/{_f(h['p5'], 2)}{_ci(h.get('ci_p5'))} | {_f(h['bust5'], 2)} | "
                     f"{_f(v['eod']['p5'], 2)}/{_f(v['realized']['p5'], 2)}/{_f(v['intraday']['p5'], 2)} | {lf['lift']:+.3f}{_ci(lf['ci'])} | "
                     f"{'n/a' if dec is None else f'{dec:+.3f}'} | {'PASS' if v['criterion']['primary_pass'] else 'fail'} |")
        L.append("")
    L.append("## Funded finalists (rolling 60-session lives, primary breach model; payout policy as frozen)")
    L.append("| finalist | config / cell | IS P20/40/60, med d, E[1st chq], E$40, E$60, bust-pre | WF E$40 | HO P20/40/60, med d, E[1st chq], E$40 [CI], E$60, bust-pre | lift E$40 | decay E$40 | alt models E$40 | flags |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for fid, v in fu.items():
        fin = man["funded"][fid]
        i, h = fin["insample"], v["headline"]
        alts = ", ".join(f"{m} {_f(v[m]['e_net_40'], 0)}" for m in MODELS_ALT["apex" if fin["variant"] == "apex" else "lucid"][1:])
        L.append(f"| {fid} | {fin['cid']} {fin['cell']} | {_f(i['p_pay_20'], 2)}/{_f(i['p_pay_40'], 2)}/{_f(i['p_pay_60'], 2)}, {_f(i['med_days_first'], 0)}d, "
                 f"${_f(i['e_first_gross'], 0)}, ${_f(i['e_net_40'], 0)}, ${_f(i['e_net_60'], 0)}, {_f(i['p_bust_pre_first'], 2)} | ${_f(i['wf_oos_e_net_40'], 0)} | "
                 f"{h['p_pay_20']:.2f}/{h['p_pay_40']:.2f}/{h['p_pay_60']:.2f}, {_f(h['med_days_first'], 0)}d, ${_f(h['e_first_gross'], 0)}, "
                 f"${h['e_net_40']:.0f}{_ci(h.get('e_net_40_ci'))}, ${h['e_net_60']:.0f}, {h['p_bust_pre_first']:.2f} | {v['lift']['lift_e40']:+.0f} | "
                 f"{h['e_net_40'] - (i['e_net_40'] or 0):+.0f} | {alts} | {','.join(v.get('apex_flags') or []) or '-'} |")
    L.append("")
    L.append("## Multi-account (one eval per account, same start day; P(>=1 pass within 5 days))")
    L.append("| N | accounts | IS primary [eod/intraday] | HO primary [CI] | HO eod/realized/intraday | HO by-day 1..5 | E[funded] | eval cost | decay |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for n, v in res["multi"].items():
        m = man["multi_account"][n]
        i, p = m["insample"], v["primary"]
        L.append(f"| {n} | {', '.join(v['accounts'])} | {_f(i['primary_p_any5'], 3)} [{_f(i['eod'], 2)}/{_f(i['intraday'], 2)}] | {_f(p['p_any5'], 3)}{_ci(p.get('ci_p_any5'))} | "
                 f"{_f(v['eod']['p_any5'], 2)}/{_f(v['realized']['p_any5'], 2)}/{_f(v['intraday']['p_any5'], 2)} | {', '.join(f'{x:.2f}' for x in p['p_any_by_day'])} | "
                 f"{p['e_funded']:.2f} | ${p['total_eval_cost']:.0f} | {p['p_any5'] - i['primary_p_any5']:+.3f} |")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "hashes"
    mpath = Path(argv[1]) if len(argv) > 1 else MANIFEST
    man = load_manifest(mpath)
    if cmd == "hashes":
        print(json.dumps({"manifest_sha256": sha256_file(MANIFEST), "code_sha256": code_hashes(), "frozen": verify_frozen(man)}, indent=1))
    elif cmd == "validate":
        res = run(man, "insample")
        res["compare"] = compare_insample(man, res)
        (OUT / "holdout_validate_insample.json").write_text(json.dumps(res, indent=1, default=_js))
        (OUT / "holdout_validate_insample.md").write_text(summary_md(man, res, "Scorer validation on the IN-SAMPLE window (same code; not holdout results)", mpath))
        print("max |P5 diff| vs frozen in-sample:", res["compare"]["max_abs_p5_diff"])
    elif cmd == "selftest":
        # holdout code path (Resolver 'holdout' branch, tape calendar, E.load(holdout=True)) on the IN-SAMPLE window: job keys -> in-sample sources
        m2 = json.loads(json.dumps(man))
        m2["holdout"]["start"], m2["holdout"]["end"] = "2021-01-01", "2024-12-31"
        runs = {c["job_key"]: c["in_sample_src"] for c in list(m2["configs"].values()) + list(m2["controls"].values())}
        a = run(m2, "holdout", boots=20, log=lambda *x: None, runs=runs)
        b = run(man, "insample", boots=20, log=lambda *x: None)
        bad = [k for k in a["eval"] if abs(a["eval"][k]["headline"]["p5"] - b["eval"][k]["headline"]["p5"]) > 1e-9
               or abs(a["eval"][k]["lift"][a["eval"][k]["primary"]]["lift"] - b["eval"][k]["lift"][b["eval"][k]["primary"]]["lift"]) > 1e-9]
        badf = [k for k in a["funded"] if abs(a["funded"][k]["headline"]["e_net_40"] - b["funded"][k]["headline"]["e_net_40"]) > 1e-6]
        badm = [n for n in a["multi"] if abs(a["multi"][n]["primary"]["p_any5"] - b["multi"][n]["primary"]["p_any5"]) > 1e-12]
        print("selftest: holdout path vs in-sample path, mismatches eval", bad, "funded", badf, "multi", badm, "OK" if not (bad or badf or badm) else "FAILED")
        sys.exit(1 if (bad or badf or badm) else 0)
    elif cmd == "score":
        bad = verify_frozen(man)
        if bad:
            sys.exit("REFUSED (not frozen / changed): " + "; ".join(bad))
        res = run(man, "holdout")
        (OUT / "holdout_results.json").write_text(json.dumps(res, indent=1, default=_js))
        (OUT / "holdout_summary.md").write_text(summary_md(man, res, f"{E.ROOT} holdout results (2025-01-01..latest), frozen finalists, frozen code"))
        print("wrote", OUT / "holdout_results.json", OUT / "holdout_summary.md")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
