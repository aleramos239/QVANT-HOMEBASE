"""Read-only summary of the stop study: structure stop vs the 8 fixed stops, same entries, same target multiple."""
import sys, json, glob, os, collections
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import library as L
D = sys.argv[1]
MIN = 100
rows, chk = [], []
for jf in sorted(glob.glob(f"{D}/*.json")):
    key = os.path.basename(jf)[:-5]
    family, root, tf = key.rsplit("-", 2)
    meta = json.load(open(jf)); z = np.load(f"{D}/{key}.npz")
    u = L.load_unit(key); cal = L.calendar("build", root)
    old = u["meta"]["cells"]
    def fresh(cid): return {k: z[f"{cid}|{k}"] for k in L.FIELDS}
    def stat(x, sess):
        m = np.asarray(x["sess"]) == L.SESS_CODE[sess]
        x = {k: np.asarray(x[k])[m] for k in L.FIELDS}
        if len(x["net"]) < MIN: return None
        a = L.metrics(x, cal); s = L.sized(x, root); b = L.metrics(s, cal, s["cost"])
        return dict(n=a["trades"], avg=a["avg_trade"], pf=a["pf"], net=a["net"], dd=a["max_dd"], risk=float(np.nanmedian(x["risk"])),
                    snet=b["net"], sdd=b["max_dd"], stop=float((np.asarray(x["reason"]) == 0).mean()), win=a["win"])
    for m in meta:
        if m["old"]:
            o = L.unit_cell(u, m["old"])
            chk.append((key, m["id"], m["trades"], len(o["net"]), round(m["net"]), round(float(np.sum(o["net"])))))
            continue
        r = m["exit"]["tgt_r"]
        fx = [c for c in old if c["vi"] == m["vi"] and c["exit"]["tgt_r"] == r and not c.get("info")]
        xs = fresh(m["id"])
        for sess in L.SESS7:
            s = stat(xs, sess)
            if s is None: continue
            f = {}
            for c in fx:
                t = stat(L.unit_cell(u, c["id"]), sess)
                if t: f[f'{c["exit"]["stop_mode"]}{c["exit"]["stop_val"]:g}'] = t
            if len(f) == 8:
                rows.append(dict(family=family, root=root, tf=tf, vi=m["vi"], tgt=r, sess=sess, struct=s, fixed=f))
json.dump(rows, open(f"{D}/../struct_sum.json", "w"))
bad = [c for c in chk if c[2] != c[3] or c[4] != c[5]]
print(f"repeat check: {len(chk)} cells, {len(bad)} differ", bad[:5])
q = lambda c: c["snet"] / c["sdd"] if c["sdd"] > 0 else 0.0
def line(tag, rs):
    if not rs: return
    n = len(rs)
    rank = np.mean([1 + sum(q(c) > q(r["struct"]) for c in r["fixed"].values()) for r in rs])
    bm = sum(q(r["struct"]) > np.median([q(c) for c in r["fixed"].values()]) for r in rs)
    bb = sum(q(r["struct"]) > max(q(c) for c in r["fixed"].values()) for r in rs)
    sp = np.mean([r["struct"]["snet"] > 0 for r in rs]); fp = np.mean([np.mean([c["snet"] > 0 for c in r["fixed"].values()]) for r in rs])
    sa = np.median([r["struct"]["avg"] for r in rs]); fa = np.median([np.median([c["avg"] for c in r["fixed"].values()]) for r in rs])
    so = np.mean([r["struct"]["stop"] for r in rs]); rk = np.median([r["struct"]["risk"] for r in rs])
    print(f"{tag:26s} n={n:4d} rank {rank:.1f}/9 beats-middle {100*bm/n:3.0f}% beats-all {100*bb/n:3.0f}% | profitable S {100*sp:3.0f}% F {100*fp:3.0f}% | avg trade S ${sa:6.1f} F ${fa:6.1f} | S stop-outs {100*so:2.0f}% dist {rk:.1f} pts")
line("ALL", rows)
for f in dict.fromkeys(r["family"] for r in rows): line(f, [r for r in rows if r["family"] == f])
for g in ("NQ", "ES", "GC"): line(g, [r for r in rows if r["root"] == g])
for t in (0.0, 1.0, 2.0, 3.0): line(f"target {t:g}R", [r for r in rows if r["tgt"] == t])
for s in L.SESS7: line(s, [r for r in rows if r["sess"] == s])
print()
for f in dict.fromkeys(r["family"] for r in rows):
    for g in ("NQ",): 
        for s in ("nyam", "mid", "pm"): line(f"{f} {g} {s}", [r for r in rows if r["family"] == f and r["root"] == g and r["sess"] == s])
