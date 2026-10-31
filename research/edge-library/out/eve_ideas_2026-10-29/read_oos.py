"""OOS grid for ideas 15-16 and 23: boxes green in-sample AND on the test months, with every touching box (8 neighbours, same entry offset and stop family) green in both too."""
import json, os, subprocess, sys
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
STOPS = {"atr": [0.5, 1, 1.5, 2], "pts": [15, 25, 40, 60]}; TG = [0.5, 0.75, 1, 1.5, 2]
def show(store):
    return json.loads(subprocess.run([PY, "bp.py", "wf", "show", store, "--json"], cwd=ED, capture_output=True, text=True).stdout)["wf"]
res = {}
for n in ["i15_16_close_loc_follow", "i23_new_high_long"]:
    parent = n + "-NQ-tf5"
    G = {}
    for b in show(parent)["is"]:
        s = b["settings"]
        if s["stop_mode"] == "own": continue
        key = (s["off_min"], s["stop_mode"], s["stop_val"], s["tgt_r"])
        d = {"box": b["box"], "is_net": b["net"], "is_n": b["trades"], "is_t": b["t_stat"], "is_yrs": b["years_green"], "wf": b["worse_fills_net"]}
        st = os.path.join(ED, "runs_wf", parent + "__" + b["box"])
        if os.path.exists(os.path.join(st, "oos")):
            r = show(parent + "__" + b["box"])["oos"]
            rec = r["record"]; bl = r["blocks"]
            d.update(o_net=rec["net"], o_n=rec["trades"], o_t=rec["t_stat"], o_avg=rec["avg_trade"], o_wr=rec["win_rate"], o_blk=sum(x["net"] > 0 for x in bl), o_blkn=len(bl))
        G[key] = d
    res[n] = G
json.dump({n: {"|".join(map(str, k)): v for k, v in g.items()} for n, g in res.items()}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oos_grid.json"), "w"))
def green(d): return d is not None and "o_net" in d and d["is_net"] > 0 and d["o_net"] > 0
for n, G in res.items():
    read = [d for d in G.values() if "o_net" in d]
    print("==", n, "boxes read", len(read), "of", len(G), "| OOS net>0:", sum(d["o_net"] > 0 for d in read), "| IS&OOS green:", sum(green(d) for d in read), "| OOS t>=2:", sum((d["o_t"] or 0) >= 2 for d in read))
    solid = []
    for (om, sm, sv, tg), d in G.items():
        if not green(d): continue
        si, ti = STOPS[sm].index(sv), TG.index(tg)
        nb = [G.get((om, sm, STOPS[sm][a], TG[c])) for a in range(max(0, si - 1), min(4, si + 2)) for c in range(max(0, ti - 1), min(5, ti + 2)) if (a, c) != (si, ti)]
        if all(green(x) for x in nb):
            solid.append((om, sm, sv, tg, d, len(nb)))
    print("  green in both with all touching boxes green in both:", len(solid))
    for om, sm, sv, tg, d, k in sorted(solid, key=lambda x: -x[4]["o_net"]):
        print("   %-26s nb=%d IS $%7.0f n%3d t%.2f yrs%s wf$%s | OOS $%7.0f n%3d avg$%4.0f wr%3.0f%% t%.2f blocks+ %d/%d" % (d["box"], k, d["is_net"], d["is_n"], d["is_t"] or 0, d["is_yrs"], d["wf"], d["o_net"], d["o_n"], d["o_avg"], 100 * d["o_wr"], d["o_t"] or 0, d["o_blk"], d["o_blkn"]))
