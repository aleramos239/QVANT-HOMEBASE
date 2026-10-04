import gzip, pickle, json, math, csv
import numpy as np
D = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_heat2/"
RISK, MNQ_PT, COMM, CAP = 1000.0, 2.0, 1.04, 170

def size(trades):
    out = []
    for date, side, gross1, dist, reason in trades:
        n = int(max(1, min(CAP, round(RISK / (dist * MNQ_PT))))) if dist > 0 else 1
        out.append((date, side, gross1 * n / 10.0 - n * COMM, n, n * dist * MNQ_PT, n == CAP and RISK / (dist * MNQ_PT) > CAP))
    return out

def metr(rows):
    if not rows: return None
    nets = np.array([r[2] for r in rows]); n = len(nets); wins = int((nets > 0).sum())
    gw, gl = nets[nets > 0].sum(), -nets[nets <= 0].sum()
    sd = nets.std(ddof=1) if n > 1 else float("nan")
    eq = np.cumsum(nets); peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    return {"n": n, "wr": wins / n, "net": float(nets.sum()), "pf": float(gw / gl) if gl > 0 else None,
            "sharpe": float(nets.mean() / sd * math.sqrt(252)) if sd and sd == sd and sd > 0 else None,
            "dd": float((eq - peak).min()), "exp": float(nets.mean()), "micros": float(np.mean([r[3] for r in rows])),
            "risk": float(np.mean([r[4] for r in rows])), "capped": int(sum(r[5] for r in rows))}

def cell(trades):
    rows = size(trades); m = metr(rows)
    if m is None: return None
    m["yr"] = {y: metr([r for r in rows if r[0][:4] == y]) for y in sorted({r[0][:4] for r in rows})}
    return m

def load():
    res = {}
    for fam in ("book", "wide", "flow", "combo"):
        d = pickle.load(gzip.open(D + f"trades_{fam}.pkl.gz", "rb"))
        for k, v in d.items():
            mode, sm, sv, rr = k.split("|"); res[(fam, mode, sm, sv, rr)] = {"m": cell(v["trades"]), "err": v["errors"], "both": v["both_sides"]}
    return res

if __name__ == "__main__":
    res = load()
    assert all(not v["err"] for v in res.values()), "strategy errors"
    json.dump({"|".join(k): v["m"] for k, v in res.items()}, open(D + "cells_v2.json", "w"))
    with open(D + "cells_v2.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["fam", "mode", "stop_type", "stop_val", "rr", "n", "win_rate", "net", "pf", "sharpe", "max_dd", "expectancy", "avg_micros", "avg_risk", "capped"])
        for k, v in res.items():
            m = v["m"]
            if m: w.writerow(list(k) + [m["n"], round(m["wr"], 4), round(m["net"]), None if m["pf"] is None else round(m["pf"], 3), None if m["sharpe"] is None else round(m["sharpe"], 2), round(m["dd"]), round(m["exp"], 1), round(m["micros"], 1), round(m["risk"]), m["capped"]])
    print("cells", len(res), "written")
