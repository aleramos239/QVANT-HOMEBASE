"""CHECKER (stage 2b) -- 2024 gates and the seals, from the stores, own code (reuses only my check_gates helpers).
Reads ONLY 2024 stores the analyst already opened (runs_admit_r1/) -- logged in checker_pick_reads.csv. EXAM never."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_gates as G  # noqa: E402

W = G.W
R1DIR = W / "runs_admit_r1"
D2025 = dt.date(2025, 1, 1).toordinal()
D2024 = dt.date(2024, 1, 1).toordinal()


def load(d):
    m = json.loads((d / "run.json").read_text())
    z = np.load(d / "cells.npz")
    u = {k: z[k] for k in z.files}
    u["meta"] = m
    u["idx"] = {c["id"]: i for i, c in enumerate(m["cells"])}
    return u


def main():
    rep = {"seals": {}, "pick": {}}
    # ---- seals over every store directory of the project
    worst = {}
    for base in ("runs", "runs_admit", "runs_admit_r1", "runs_deepen", "runs_void"):
        mx, n, bad, per = 0, 0, [], {}
        for p in sorted((W / base).glob("*/cells.npz")):
            z = np.load(p)
            m = json.loads((p.parent / "run.json").read_text())
            n += 1
            dmax = int(z["date"].max()) if len(z["date"]) else 0
            dmin = int(z["date"].min()) if len(z["date"]) else 0
            mx = max(mx, dmax)
            per[m.get("period")] = per.get(m.get("period"), 0) + 1
            if dmax >= D2025 or m["range"]["end"] > "2024-12-31" or m["range"].get("holdout"):
                bad.append(p.parent.name)
            if base == "runs" and (dmax >= D2024 or m.get("period") != "build" or m["range"]["end"] != "2023-12-31"):
                bad.append("BUILD store reaches 2024: " + p.parent.name)
            if m.get("period") == "pick" and dmin and dmin < D2024:
                bad.append("pick store with pre-2024 trades: " + p.parent.name)
        worst[base] = {"stores": n, "last_trade_date": dt.date.fromordinal(mx).isoformat() if mx else None, "periods": per, "bad": bad}
    rep["seals"]["stores"] = worst
    r1 = [k for k in sorted(p.parent.name for p in (W / "runs").glob("*/run.json"))
          if json.loads((W / "runs" / k / "run.json").read_text())["family"] in G.R1]
    last = max(int(np.load(W / "runs" / k / "cells.npz")["date"].max()) for k in r1 if len(np.load(W / "runs" / k / "cells.npz")["date"]))
    rep["seals"]["round1_build_stores"] = len(r1)
    rep["seals"]["round1_last_trade_date"] = dt.date.fromordinal(last).isoformat()
    # ---- which 2024 stores exist, their session, and pick_reads.csv
    reads = list(csv.DictReader((W / "out" / "admit_r1" / "pick_reads.csv").open()))
    listed = {r["key"] for r in reads}
    on_disk = {}
    for p in sorted(R1DIR.glob("*/run.json")):
        m = json.loads(p.read_text())
        z = np.load(p.parent / "cells.npz")
        codes = sorted({G.SESS7[int(c)] for c in np.unique(z["sess"]) if c >= 0}) if len(z["sess"]) else []
        on_disk[p.parent.name] = {"period": m.get("period"), "family": m["family"], "root": m["root"], "sessions_traded": codes,
                                  "cells": len(m["cells"]), "stress": m.get("stress") or m.get("run_kw")}
    pick_disk = {k for k, v in on_disk.items() if v["period"] == "pick"}
    rep["seals"]["r1_admit_stores"] = on_disk
    rep["seals"]["pick_stores_not_in_pick_reads"] = sorted(pick_disk - listed)
    rep["seals"]["pick_reads_without_store"] = sorted(listed - pick_disk)
    led = list(csv.DictReader((W / "ledger.csv").open()))
    rep["seals"]["ledger_pick_rows_round1"] = [(r["stage"], r["key"]) for r in led if r["period"] == "pick" and
                                               (r["stage"].startswith(("r1_", "null_r1")) or "straddle_tight" in r["key"])]
    rep["seals"]["ledger_exam_rows"] = [r["key"] for r in led if r["period"] not in ("build", "pick", "insample", "")]
    # ---- 2024 heat maps of the four BUILD passers
    units = {"vwap_trend_pull-NQ-tf5": ("pm", "x0p1_pts30-r2", "c1"), "vol_spike_break-NQ-tf30": ("pm", "m4_pct0p2-r2", "c1"),
             "straddle_tight_0830-NQ-tf30": ("pre", "offB_pts5-r3", "shift"), "straddle_tight_0830-GC-tf30": ("pre", "offC_pts2-r1", "shift")}
    for key, (sess, cen, ctl) in units.items():
        ub = G.load(key)
        hb = G.heat(ub, sess)[""]
        assert hb["central"]["id"] == cen, (key, hb["central"]["id"])
        up = load(R1DIR / f"{key}-{sess}-pick")
        assert up["meta"]["period"] == "pick" and up["meta"]["range"]["end"] == "2024-12-31"
        hp = G.heat(up, sess)[""]
        cp = G.cell(up, up["idx"][cen], sess)
        r = {"build_share": hb["share"], "build_cells": hb["cells"], "build_central": cen, "build_central_net": hb["central"]["net"],
             "pick_cells": hp["cells"], "pick_share": hp["share"], "pick_median": hp["median"], "pick_pass": hp["pass"],
             "pick_central_net": round(float(cp["net"].sum()), 2), "pick_central_trades": int(len(cp["net"])),
             "pick_central_t": G.tstat(cp["net"])}
        nb = {x["id"]: x["net"] for x in hb["rows"]}
        npk = {x["id"]: x["net"] for x in hp["rows"]}
        both = sorted(c for c in nb if nb[c] > 0 and npk.get(c, 0) > 0)
        r["both_positive"] = len(both)
        if ctl == "shift":
            su = load(R1DIR / f"{key}-{sess}-pick-shift")
            nets = [float(G.cell(su, su["idx"][f"s{sd}_{cen}"])["net"].sum()) for sd in (1, 2)]
            r["pick_ctrl"], r["pick_lift"] = float(np.mean(nets)), r["pick_central_net"] - float(np.mean(nets))
        else:
            tf = key.rsplit("tf", 1)[1]
            pu = load(R1DIR / f"c1-NQ-tf{tf}-{sess}-pick")
            xid = cen.rsplit("_", 1)[-1]
            parts = [G.cell(pu, pu["idx"][f"s{sd}_{xid}"]) for sd in (1, 2)]
            pool = {q: np.concatenate([p[q] for p in parts]) for q in ("date", "sess", "net")}
            e, short = G.c1_expected(cp, pool)
            r["pick_ctrl"], r["pick_lift"], r["pick_short"] = e, r["pick_central_net"] - e, short
        # stress stores: surviving set = positive in BUILD, 2024, BUILD stress and 2024 stress
        sb, sp = R1DIR / f"{key}-{sess}-build-stress", R1DIR / f"{key}-{sess}-pick-stress"
        if sb.exists() and sp.exists():
            usb, usp = load(sb), load(sp)
            assert usb["meta"]["period"] == "build" and usp["meta"]["period"] == "pick"
            r["stress_kw"] = [usb["meta"].get("run_kw"), usp["meta"].get("run_kw")]
            snb = {c["id"]: float(G.cell(usb, i, sess)["net"].sum()) for i, c in enumerate(usb["meta"]["cells"])}
            snp = {c["id"]: float(G.cell(usp, i, sess)["net"].sum()) for i, c in enumerate(usp["meta"]["cells"])}
            surv = [c for c in both if snb.get(c, -1) > 0 and snp.get(c, -1) > 0]
            r["stress_cells"] = len(snb)
            r["both_positive_not_stressed"] = [c for c in both if c not in snb or c not in snp]
            r["surviving"] = len(surv)
            r["central_stress"] = [snb.get(cen), snp.get(cen)]
            r["central_survives"] = cen in surv
        rep["pick"][f"{key}|{sess}"] = r
        print(key, sess, json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}, default=str), flush=True)
    print(json.dumps(rep["seals"], indent=1, default=str))
    (G.OUT / "check_pick.json").write_text(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
