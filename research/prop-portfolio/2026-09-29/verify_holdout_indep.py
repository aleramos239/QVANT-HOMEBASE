#!/usr/bin/python3
"""Adversarial verification of the NQ holdout scoring (part 3): re-derive the holdout numbers from the RAW holdout trades with the
independent walks of verify_indep.py (eval) and verify_funded_indep.py (funded lifecycle), then compare with out/holdout_results.json.

Shares with the scorer ONLY: E.load (trade loader), the rule JSON (E.firm_rules), the manifest (WHAT to score) and
daymatched_controls (control construction, for the lift check). The holdout calendar is rebuilt here from the tick-archive file names.
Run:  PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 verify_holdout_indep.py [--lift]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
import evalcore as E            # noqa: E402
import verify_indep as V        # noqa: E402
import verify_funded_indep as VF  # noqa: E402

man = json.loads((E.D / "out/holdout_manifest.json").read_text())
res = json.loads((E.D / "out/holdout_results.json").read_text())
H0, H1 = man["holdout"]["start"], man["holdout"]["end"]

# ---- calendar: weekday archive sessions straight from the tick archive file names
from homebase.backtest.tape import TapeStore  # noqa: E402
arch = TapeStore().archive / E.ROOT
cal_set = set()
for y in (2025, 2026):
    for f in (arch / str(y)).glob("*.json"):
        try:
            d = dt.date.fromisoformat(f.name[:10])
        except ValueError:
            continue
        if H0 <= d.isoformat() <= H1 and d.weekday() < 5:
            cal_set.add(d.toordinal())

runs = {}
for ln in (E.D / "jobs.jsonl").read_text().splitlines():
    if ln.strip():
        j = json.loads(ln)
        if j.get("stage") == "holdout" and j.get("status") == "done":
            runs[j["key"]] = j["id"]


def trades_of(cfg_or_ctrl: str, ctrl=False):
    spec = (man["controls"] if ctrl else man["configs"])[cfg_or_ctrl]
    t = E.load(runs[spec["job_key"]], holdout=True)
    return t


_L: dict = {}


def member_list(cfg: str, sess: str):
    k = (cfg, sess)
    if k not in _L:
        t = trades_of(cfg)
        out = []
        for i in range(t.n):
            s = V.sess_of(int(t.te[i]))
            if sess == "all" or s == sess:
                out.append((int(t.date[i]), int(t.te[i]), int(t.tx[i]), int(t.side[i]), float(t.g[i]), float(t.mae[i]), float(t.mfe[i])))
        _L[k] = out
    return _L[k]


def all_dates():
    s = set()
    for c in man["configs"]:
        s |= {int(x) for x in trades_of(c).date}
    return s


tr_dates = all_dates()
off = sorted(tr_dates - cal_set)
CAL = sorted(cal_set | tr_dates)
print(f"calendar: archive weekday sessions {len(cal_set)} (scorer {res['calendar']['sessions']}), trade dates off-calendar {len(off)} "
      f"{[dt.date.fromordinal(x).isoformat() for x in off[:5]]}, union {len(CAL)}")
print(f"first {dt.date.fromordinal(CAL[0])} last {dt.date.fromordinal(CAL[-1])}; weekday gaps (no archive):",
      [dt.date.fromordinal(o).isoformat() for o in range(CAL[0], CAL[-1] + 1) if dt.date.fromordinal(o).weekday() < 5 and o not in set(CAL)])

bad = []


def cmp(tag, a, b, tol=1e-9):
    if a is None or b is None:
        ok = a is None and b is None
    else:
        ok = abs(a - b) <= tol * max(1.0, abs(b))
    if not ok:
        bad.append((tag, a, b))
    return ok


# ------------------------------------------------------------------ eval finalists
EV = {}


def spec_of(fid, members=None):
    fin = man["finalists"][fid]
    mem = members or [(member_list(m["cfg"], m["sess"]), m["sess"], int(m["micros"])) for m in fin["members"]]
    return V.Spec(fin["firm"], mem, fin["rules"], cal=CAL)


worst = 0.0
for fid, fin in man["finalists"].items():
    sp = spec_of(fid)
    arr = sp.arrays()
    EV[fid] = (sp, arr)
    r = res["eval"][fid]
    row = []
    for m in V.MODELS:
        o, d = arr[m]
        mt = V.metrics(o, d)
        for k in ("p1", "p2", "p3", "p5", "bust5"):
            ok = cmp(f"{fid}/{m}/{k}", mt[k], r[m][k])
            worst = max(worst, abs(mt[k] - r[m][k]))
        row.append(f"{m[:3]} {mt['p5']:.4f}")
    print(f"eval {fid:42s} n_starts {sp.S} (scorer {r['n_starts']}) " + " | ".join(row))
print("eval max abs diff vs scorer:", worst)

# ---- 60% criterion recomputed (primary model, compliant finalists only)
crit = {}
for f in sorted({v["firm"] for v in man["finalists"].values()}):
    best = max(((V.metrics(*EV[k][1][E.primary_model(f)])["p5"], k) for k, v in man["finalists"].items() if v["firm"] == f and not v["apex_flags"]), default=None)
    scorer = res["criterion_by_firm"][f]
    if best is None:                                  # no rule-compliant finalist (ES Apex: every finalist fails the PA MAE rule)
        anyb = max(((V.metrics(*EV[k][1][E.primary_model(f)])["p5"], k) for k, v in man["finalists"].items() if v["firm"] == f))
        crit[f] = anyb
        print(f"criterion {f:15s} NO compliant finalist (scorer best_primary={scorer['best_primary']}); best non-compliant {anyb[0]:.4f} {anyb[1]}")
        if scorer["best_primary"] is not None or scorer["pass_primary"]:
            bad.append(("criterion-none", f, scorer["best_primary"]))
        continue
    crit[f] = best
    ok = best[0] >= 0.60
    print(f"criterion {f:15s} best compliant {best[0]:.4f} {best[1]:40s} pass={ok}  scorer pass={scorer['pass_primary']} best={scorer['best_primary'][1]}")
    if ok != scorer["pass_primary"] or best[1] != scorer["best_primary"][1]:
        bad.append(("criterion", f, best, scorer["best_primary"]))

# ---- walk stats (executed trades, net) of the top finalists
for f, (p5, fid) in crit.items():
    sp = EV[fid][0]
    nets = [sp.day(i).tot for i in range(sp.D)]
    ex = sum(len(sp.day(i).execd) for i in range(sp.D))
    cmp(f"{fid}/exec", ex, res["eval"][fid]["walk"]["executed"])
    cmp(f"{fid}/net", float(sum(nets)), res["eval"][fid]["series"]["net"])
    print(f"walk {fid}: executed {ex} (scorer {res['eval'][fid]['walk']['executed']}) net {sum(nets):.0f} (scorer {res['eval'][fid]['series']['net']:.0f})")

# ---- multi-account mixes
for n, mix in man["multi_account"].items():
    row = {}
    for model in ("primary",) + V.MODELS:
        anyp = np.zeros(EV[mix["accounts"][0]][0].S, bool)
        for a in mix["accounts"]:
            fm = man["finalists"][a]["firm"]
            mm = E.primary_model(fm) if model == "primary" else model
            o, d = EV[a][1][mm]
            anyp |= (o == 1) & (d <= 5)
        row[model] = float(anyp.mean())
        sc = res["multi"][n]["primary" if model == "primary" else model]["p_any5"]
        cmp(f"mix{n}/{model}", row[model], sc)
    print(f"mix N={n} {mix['accounts']}: " + " ".join(f"{k} {v:.4f}" for k, v in row.items()) + f" | scorer primary {res['multi'][n]['primary']['p_any5']:.4f}")

# ------------------------------------------------------------------ funded
KIND = {"flex": ("flex", 0.0), "flex_dll": ("flex", 1200.0), "pro_dll": ("pro", 1200.0), "pro_nodll": ("pro", 0.0), "apex": ("apex", 0.0)}
FKEYS = ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_net_40", "e_net_60", "p_bust_pre_first", "p_bust_any", "e_npay_60")
fworst = 0.0
for fid, fin in man["funded"].items():
    kind, dll = KIND[fin["variant"]]
    t = trades_of(fin["cfg"])
    days, miss = VF.day_trades_from(t, fin["sess"], CAL) if hasattr(VF, "day_trades_from") else (None, None)
    if days is None:                                  # build per-session trade dicts here (session assigned from the entry minute)
        pos = {o: i for i, o in enumerate(CAL)}
        days = [[] for _ in CAL]
        for (d, te, tx, sd, g, mae, mfe) in member_list(fin["cfg"], fin["sess"]):
            days[pos[d]].append(dict(te=te, tx=tx, side=sd, g=g, mae=mae, mfe=mfe, m=10, mem=0))
        for d in days:
            d.sort(key=lambda x: x["te"])
    rl = {k: fin["rules"][k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}
    W = VF.RefWalk(days, int(fin["micros"]), rl, E.PL.TICK_USD)
    models = ("pess", "nat", "opt") if kind == "apex" else ("realized", "eod", "intraday")
    out = {}
    for model in models:
        out[model] = VF.ref_metrics(kind, W, fin["policy"], model, dll=dll)
        for k in FKEYS:
            a, b = out[model][k], res["funded"][fid][model][k]
            if a is None or b is None:
                if (a is None) != (b is None):
                    bad.append((f"{fid}/{model}/{k}", a, b))
                continue
            fworst = max(fworst, abs(a - b))
            cmp(f"{fid}/{model}/{k}", a, b, 1e-7)
    prim = models[0]
    o = out[prim]
    print(f"funded {fid:12s} {fin['cell']:22s} n={o['n']} P20 {o['p_pay_20']:.4f} P40 {o['p_pay_40']:.4f} med {o['med_days_first']} "
          f"E40 {o['e_net_40']:.1f} (scorer {res['funded'][fid]['headline']['e_net_40']:.1f}) | " + " ".join(f"{m} E40 {out[m]['e_net_40']:.0f}" for m in models[1:]))
print("funded max abs diff vs scorer:", fworst)

# ------------------------------------------------------------------ lift vs day-matched controls (top eval finalist per firm + mix accounts)
if "--lift" in sys.argv:
    need = sorted({fid for _, fid in crit.values()} | {a for mix in man["multi_account"].values() for a in mix["accounts"] if mix and a in ("lucid:best2", "lucidpro:pf", "apex:best2", "lucid:single", "lucidpro:best2", "lucid:fx_single", "lucid:fxfast_best2", "lucidpro_nodll:single")})
    for fid in need:
        fin = man["finalists"][fid]
        per = []
        for m in fin["members"]:
            c = man["configs"][m["cfg"]]
            cand = {"cid": f"{m['cfg']}|{m['sess']}"}
            pool = E.concat_tr([trades_of(i, ctrl=True) for i in c["ctrl_eval"]["ids"]])
            tr = trades_of(m["cfg"])
            mk = E._sess_mask(tr, m["sess"])
            sub = SimpleNamespace(date=tr.date[mk], sess=tr.sess[mk], n=int(mk.sum()))
            cs = E.daymatched_controls(sub, pool, K=man["scoring"]["K_controls"], seed=zlib.crc32(cand["cid"].encode()) % 100000, mask=None,
                                       carry=("side", "g", "mae", "mfe", "risk", "sess"))
            lists = []
            for k_, cc in enumerate(cs):
                # property checks: same (date, session) counts as the real member; same micros / rules applied below
                cnt_c, cnt_r = {}, {}
                for d_, s_ in zip(cc["date"].tolist(), cc["sess"].tolist()):
                    cnt_c[(d_, s_)] = cnt_c.get((d_, s_), 0) + 1
                for d_, s_ in zip(sub.date.tolist(), sub.sess.tolist()):
                    cnt_r[(d_, s_)] = cnt_r.get((d_, s_), 0) + 1
                if cnt_c != cnt_r and k_ == 0:
                    print(f"   note {fid} {m['cfg']}: control0 per-(date,sess) counts differ from the real member in {sum(1 for k in set(cnt_c)|set(cnt_r) if cnt_c.get(k,0)!=cnt_r.get(k,0))} cells (shortfall {cc['short']}, fb_share {cc['fb_share']:.3f})")
                lists.append([(int(d), int(te), int(tx), int(sd), float(g), float(ma), float(mf))
                              for d, te, tx, sd, g, ma, mf in zip(cc["date"], cc["te"], cc["tx"], cc["side"], cc["g"], cc["mae"], cc["mfe"])])
            per.append(lists)
        K = min(len(x) for x in per)
        cp = {m: [] for m in V.MODELS}
        for k_ in range(K):
            mem = [(per[i][k_], fin["members"][i]["sess"], int(fin["members"][i]["micros"])) for i in range(len(fin["members"]))]
            sp = V.Spec(fin["firm"], mem, fin["rules"], cal=CAL)
            arr = sp.arrays()
            for m_ in V.MODELS:
                cp[m_].append(arr[m_][0] == 1)
        sp, arr = EV[fid]
        r = res["eval"][fid]["lift"]
        line = []
        for m_ in V.MODELS:
            real = (arr[m_][0] == 1).astype(float)
            lf = float((real - np.mean(np.stack(cp[m_]), 0)).mean())
            cmp(f"{fid}/lift/{m_}", lf, r[m_]["lift"], 1e-9)
            line.append(f"{m_[:3]} lift {lf:+.4f} (scorer {r[m_]['lift']:+.4f}) ctrl {float(np.mean(np.stack(cp[m_]))):.4f}")
        print(f"lift {fid:30s} K={K} " + " | ".join(line))

print("\nMISMATCHES:", len(bad))
for b in bad[:40]:
    print("  ", b)
