"""Stage-1 grid replay. usage: grid.py IS|HO [cells.json]  -> grid_<part>.csv.gz (long: one row per cell x model x event).
IS = 2021-10 -> 2024-12 (selection). HO = 2025-01 -> 2026-09 (only called by score_holdout.py on frozen cells)."""
import itertools, pickle, sys, json
import numpy as np
from nfp_lib import *

MODELS = {"M0": (0, 0, False), "M1": (1, 1, False), "P1": (1, 1, True), "P2": (2, 2, True), "P4": (4, 4, True)}
SL_ONE = (1200, 1500, 2000)                     # stop $ for the one-shot ($3,000 net target)
TWO = ((750, 1500), (1200, 1500))               # (stop $, target $net) for the 2-event alternative
SKIP_FIRST = 4                                  # warm-up events for the volatility estimate (all arms)
VN = 8                                          # prior events in the vol estimate


def units(root):
    s = SPEC[root]
    ns_ = {"GC": (10, 15, 20, 30, 40), "NQ": (10, 20, 30, 40), "ES": (10, 20, 30, 40), "SI": (10, 20, 30, 40)}[root]
    u = [(f"4x{root}", 4 * s["pv"], 4 * COMM_MINI)] + [(f"{n}xM{root if root != 'SI' else 'SIL'}"[:12], n * s["mpv"], n * COMM_MICRO) for n in ns_]
    return [(n if not n.startswith(f"{ns_[0]}") else n, pv, c) for n, pv, c in u]


def cells_for(root):
    out = []
    pts_offs = {"GC": (1.0, 2.0, 3.0, 5.0, 8.0)}.get(root, ())
    vol_offs = (0.05, 0.10, 0.20, 0.30)
    brs = [(s, 3000) for s in SL_ONE] + (list(TWO) if root == "GC" else [])
    for (un, pv, c), (sl, tp) in itertools.product(units(root), brs):
        for o in pts_offs:
            out.append(dict(root=root, arm="const", unit=un, pv=pv, comm=c, offmode="pts", off=o, sl_usd=sl, tp_usd=tp))
        for a in vol_offs:
            out.append(dict(root=root, arm="const", unit=un, pv=pv, comm=c, offmode="vol", off=a, sl_usd=sl, tp_usd=tp))
    if root == "GC":                              # size scales with volatility: TP pts = b x V
        for b, a, sl in itertools.product((0.3, 0.5, 0.8, 1.2), vol_offs, SL_ONE):
            out.append(dict(root=root, arm="volsize", unit=f"b{b}", pv=None, comm=None, offmode="vol", off=a, sl_usd=sl, tp_usd=3000, b=b))
    return out


def vprev(root, evs, tapes):
    """V_prev per event: median first-minute range of the previous <=8 events (None until SKIP_FIRST priors)."""
    fm, out = [], {}
    for d, _ in evs:
        k = (root, d)
        P = prep(d, *tapes[k]) if k in tapes else None
        if len(fm) >= SKIP_FIRST:
            out[d] = float(np.median(fm[-VN:]))
        if P is not None:
            fm.append(first_minute_range(P))
    return out


def run(part, only=None):
    D = pickle.load(open(CACHE / f"tapes_{part}.pkl", "rb"))
    evs, tapes = D["events"], D["tapes"]
    rows = []
    Vs = {}
    for root in SPEC:
        # V_prev needs the preceding events; HO runs carry the IS tail in via tapes_IS
        full_ev, full_tp = evs, tapes
        if part == "HO":
            I = pickle.load(open(CACHE / "tapes_IS.pkl", "rb"))
            full_ev, full_tp = I["events"] + evs, {**I["tapes"], **tapes}
        Vs[root] = vprev(root, full_ev, full_tp)
    prepped = {k: prep(k[1], *v) for k, v in tapes.items()}
    cells = only if only is not None else [c for r in SPEC for c in cells_for(r)]
    for ci, c in enumerate(cells):
        root, s = c["root"], SPEC[c["root"]]
        tick = s["tick"]
        for d, tag in evs:
            V = Vs[root].get(d)
            P = prepped.get((root, d))
            if V is None or P is None:
                continue
            if c["arm"] == "volsize":
                T = c["b"] * V
                N = int(min(40, max(1, round(c["tp_usd"] / (s["mpv"] * T)))))
                pv, comm = s["mpv"] * N, COMM_MICRO * N
            else:
                pv, comm = c["pv"], c["comm"]
            off = c["off"] if c["offmode"] == "pts" else max(tick, round(c["off"] * V / tick) * tick)
            sl, tp = bracket(pv, comm, tick, c["sl_usd"], c["tp_usd"])
            for mn, (es, ss, cas) in MODELS.items():
                net, why = replay(P, off, sl, tp, tick, pv, comm, es, ss, cas)
                rows.append((ci, mn, d.isoformat(), tag, round(net, 2), why, round(off, 3), round(sl, 4), round(tp, 4), pv))
    import pandas as pd
    df = pd.DataFrame(rows, columns="cell model date event net why off_pts sl_pts tp_pts pv".split())
    meta = pd.DataFrame(cells); meta.index.name = "cell"
    return df, meta, Vs


if __name__ == "__main__":
    part = sys.argv[1]
    only = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
    df, meta, Vs = run(part, only)
    tag = sys.argv[3] if len(sys.argv) > 3 else ""
    df.to_csv(CACHE / f"grid_{part}{tag}.csv.gz", index=False)
    meta.to_csv(CACHE / f"cells_{part}{tag}.csv")
    json.dump({r: {d.isoformat(): v for d, v in Vs[r].items()} for r in Vs}, open(CACHE / f"vprev_{part}{tag}.json", "w"))
    print(part, "cells", len(meta), "rows", len(df))
