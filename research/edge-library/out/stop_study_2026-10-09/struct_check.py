"""Read-only: stored old-library BUILD results (2021-09-22..2023-12-31) of orb_confirm, the one family that was run with a
structure stop (other side of the opening range, no target). Same entries, 9 stops: structure vs the 8 fixed, no target."""
import sys, json
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import library as L

rows = []
for root in ("NQ", "ES", "GC"):
    for tf in (1, 5, 15):
        u = L.load_unit(f"orb_confirm-{root}-tf{tf}")
        cells = u["meta"]["cells"]
        cal = L.calendar("build", root)
        nt = [c for c in cells if c["exit"]["tgt_r"] == 0.0]
        for vi in sorted({c["vi"] for c in cells}):
            grp = [c for c in nt if c["vi"] == vi]
            v = grp[0]["variant"]
            for sess in ("nyam", "mid", "pm"):
                out = {}
                for c in grp:
                    x = L.unit_cell(u, c["id"])
                    m = np.asarray(x["sess"]) == L.SESS_CODE[sess]
                    x = {k: np.asarray(x[k])[m] for k in L.FIELDS}
                    if len(x["net"]) < 100:
                        continue
                    a = L.metrics(x, cal)
                    z = L.sized(x, root)
                    b = L.metrics(z, cal, z["cost"])
                    lab = "struct" if c["exit"]["stop_mode"] == "struct" else f'{c["exit"]["stop_mode"]}{c["exit"]["stop_val"]:g}'
                    out[lab] = dict(n=a["trades"], avg=a["avg_trade"], pf=a["pf"], dd=a["max_dd"], net=a["net"],
                                    risk=float(np.nanmedian(x["risk"])), snet=b["net"], sdd=b["max_dd"], spf=b["pf"],
                                    sharpe=b["sharpe"], stop=float((np.asarray(x["reason"]) == 0).mean()))
                if "struct" in out and len(out) == 9:
                    rows.append(dict(root=root, tf=tf, v=v, sess=sess, cells=out))
json.dump(rows, open(sys.argv[1], "w"))
print(len(rows), "units")
