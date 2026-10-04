import gzip, pickle, json, math, statistics as st
import numpy as np
import analyze_heat2 as A
D = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_filt/"
FILTS = ("off", "adx", "rsi"); SIDES = ("all", "long", "short")
def cellm(rows, side):
    r = rows if side == "all" else [x for x in rows if x[1] == side]
    m = A.metr(r)
    if m is None: return None
    if side == "all": m["yr"] = {y: A.metr([x for x in rows if x[0][:4] == y]) for y in sorted({x[0][:4] for x in rows})}
    return m
def load():
    out, err = {}, 0
    for fam in ("book", "wide", "flow", "combo"):
        d = pickle.load(gzip.open(D + f"trades_{fam}.pkl.gz", "rb"))
        for k, v in d.items():
            mode, f, sm, sv, rr = k.split("|"); err += bool(v["errors"])
            rows = A.size(v["trades"])
            out[(fam, mode, f, sm, sv, rr)] = {s: cellm(rows, s) for s in SIDES}
    return out, err
if __name__ == "__main__":
    res, err = load(); print("cells", len(res), "specs with errors", err)
    # regression: filter off == heat map v2
    v2 = {tuple(k.split("|")): m for k, m in json.load(open(A.D + "cells_v2.json")).items() if m}
    bad = 0; chk = 0
    for (fam, mode, f, sm, sv, rr), x in res.items():
        if f != "off": continue
        o = v2.get((fam, mode, sm, sv, rr))
        if o is None: continue
        chk += 1; n = x["all"]
        if n is None or n["n"] != o["n"] or abs(n["net"] - o["net"]) > 1.0: bad += 1
    print("regression (filter off vs heat map v2):", chk, "cells compared,", bad, "mismatches")
    def cj(m, yr=True):
        if m is None: return None
        d = {"n": m["n"], "wr": round(m["wr"], 4), "net": round(m["net"]), "pf": None if m["pf"] is None else round(m["pf"], 3), "sh": None if m["sharpe"] is None else round(m["sharpe"], 2),
             "dd": round(m["dd"]), "ex": round(m["exp"], 1), "mc": round(m["micros"], 1)}
        if yr and "yr" in m: d["yr"] = {y: ([round(v["net"]), round(v["wr"], 3), None if v["sharpe"] is None else round(v["sharpe"], 2), v["n"]] if v else None) for y, v in m["yr"].items()}
        return d
    store = {"|".join(k): {s: cj(x[s], s == "all") for s in SIDES} for k, x in res.items()}
    json.dump(store, open(D + "cells_filt.json", "w"))
    print("saved cells_filt.json")
