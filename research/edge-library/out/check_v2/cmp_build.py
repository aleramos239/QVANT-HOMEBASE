import json, csv, sys
from pathlib import Path
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
M = {r["uid"]: r for r in json.loads((W/"out/check_v2/chk_build.json").read_text())}
A = {r["uid"]: r for r in json.loads((W/"out/v2/build_units.json").read_text())}
assert set(M) == set(A)
d1 = [u for u in M if M[u]["t1"] != A[u]["t1"]]
d3 = [u for u in M if M[u]["t3"] != A[u]["t3"]]
dc = [u for u in M if M[u]["cells"] != A[u]["cells"]]
dn = [u for u in M if M[u]["cells"] and (abs(M[u]["avg"] - A[u]["avg_net"]) > 0.01 or abs(M[u]["share"] - A[u]["share_pos"]) > 1e-9 or abs(M[u]["avg_trades"] - A[u]["avg_trades"]) > 1e-6)]
d2 = [u for u in M if (M[u]["t2"] is None) != (A[u]["t2"] is None) or (M[u]["t2"] is not None and bool(M[u]["t2"]) != bool(A[u]["t2"]))]
dp = [u for u in M if M[u]["build_pass"] != A[u]["build_pass"]]
print("t1 differ", d1, "| t3 differ", d3, "| cells differ", dc, "| net/share/trades differ", dn)
print("t2 differ", len(d2)); 
for u in d2:
    ad = json.loads(A[u]["detail"])
    print("  ", u, "mine", M[u]["t2"], {c: (v.get("p_beat"), v.get("lift"), v.get("pass")) for c, v in M[u]["det"].items()}, "| analyst", A[u]["t2"], {c: (v.get("p_beat"), v.get("lift"), v.get("pass")) for c, v in ad.items()})
print("build_pass differ", dp)
# exact-60 passers and strict
print("pass t1 at exactly 60%:", [u for u in M if M[u]["t1"] and not M[u]["t1_strict"]])
print("build passers at exactly 60%:", [u for u in M if M[u]["build_pass"] and not M[u]["t1_strict"]])
# p_beat / lift comparison for controls
import numpy as np
dl, dpb = [], []
for u in M:
    if M[u]["t2"] is None: continue
    ad = json.loads(A[u]["detail"])
    for c, v in M[u]["det"].items():
        a = ad.get(c, {})
        if "lift" in v and "lift" in a:
            dl.append((abs(v["lift"] - a["lift"]), u, c, v["lift"], a["lift"], v.get("ctl_sd"), a.get("ctl_sd")))
            dpb.append((abs(v["p_beat"] - a["p_beat"]), u, c, v["p_beat"], a["p_beat"]))
        elif "per_trade" in v:
            if abs(v["per_trade"] - a.get("per_trade", 1e9)) > 0.011: print("per_trade differs", u, c, v, a)
            if "p_beat" in v and abs(v["p_beat"] - a.get("p_beat", 9)) > 0.02: print("days p differs", u, c, v["p_beat"], a.get("p_beat"))
        if v.get("pass") != a.get("pass"): print("control verdict differs", u, c, {k: v.get(k) for k in ("pass","lift","p_beat","ctl_mean","ctl_sd","short","why")}, {k: a.get(k) for k in ("pass","lift","p_beat","ctl_mean","ctl_sd","short","why")})
dl.sort(reverse=True); dpb.sort(reverse=True)
print("largest lift differences:"); [print("  ", x) for x in dl[:6]]
print("largest p_beat differences:"); [print("  ", x) for x in dpb[:8]]
sr = [v["ctl_sd"]/json.loads(A[u]["detail"])[c]["ctl_sd"] for u in M if M[u]["t2"] is not None for c, v in M[u]["det"].items() if c == "c1" and v.get("ctl_sd") and json.loads(A[u]["detail"]).get(c, {}).get("ctl_sd")]
print("c1 sd ratio mine/analyst: median", np.median(sr), "min", min(sr), "max", max(sr), "n", len(sr))
by = {}
for u in M:
    s = M[u]["src"]; b = by.setdefault(s, [0,0,0,0,0]); b[0]+=1; b[1]+=M[u]["t1"]; b[2]+=M[u]["t1"] and M[u]["t3"]; b[3]+=M[u]["build_pass"]; b[4]+=bool(A[u]["build_pass"])
print("per stage [units,(1),(1)+(3),mine pass, analyst pass]", by)
# thin controls: units judged with < 20 real replicates among those drawn
thin = sum(1 for u in M if M[u]["t2"] is not None and any(v.get("real", 99) < 20 for v in M[u]["det"].values()))
print("drawn units with a control of < 20 real replicates:", thin, "of", sum(M[u]["t2"] is not None for u in M))
print("BUILD passers with a control of < 20 real replicates:", sum(1 for u in M if M[u]["build_pass"] and any(v.get("real", 99) < 20 for v in M[u]["det"].values())), "of", sum(M[u]["build_pass"] for u in M))
