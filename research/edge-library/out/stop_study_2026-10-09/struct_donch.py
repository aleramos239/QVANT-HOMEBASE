"""Read-only: the channel-break rule (donchian) with the stop at the other side of the channel, NQ, build days 2021-09-22..2023-12-31."""
import sys, json, datetime as dt
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import library as L
D, key = sys.argv[1], sys.argv[2]
root = key.split("-")[1]
meta = json.load(open(f"{D}/{key}.json")); z = np.load(f"{D}/{key}.npz"); u = L.load_unit(key); cal = L.calendar("build", root)
def cut(x, sess, side=None):
    m = np.asarray(x["sess"]) == L.SESS_CODE[sess]
    if side: m &= np.asarray(x["side"]) == side
    return {k: np.asarray(x[k])[m] for k in L.FIELDS}
print("variants:", [m["variant"] for m in meta if m["old"]])
print(f"{'session':6s} {'target':7s} {'stop':8s} | trades  avg$   PF   win  maxDD   net/DD | long avg  short avg | micro: DD at 1 micro | years 2021* 2022 2023 (avg $)")
for sess in ("nyam", "mid", "pm"):
    for r in (0.0, 1.0, 2.0, 3.0):
        for label in ("struct", "atr3", "pts45"):
            A = []
            for m in meta:
                if m["old"]: continue
                if m["exit"]["tgt_r"] != r: continue
                if label == "struct":
                    x = {k: z[f"{m['id']}|{k}"] for k in L.FIELDS}
                else:
                    sm, sv = ("atr", 3.0) if label == "atr3" else ("pts", 45.0)
                    c = [c for c in u["meta"]["cells"] if c["vi"] == m["vi"] and c["exit"] == {"stop_mode": sm, "stop_val": sv, "tgt_r": r}][0]
                    x = L.unit_cell(u, c["id"])
                x = cut(x, sess)
                a = L.metrics(x, cal)
                yrs = [dt.date.fromordinal(int(d)).year for d in x["date"]]
                py = [float(np.mean(x["net"][np.array(yrs) == y])) if (np.array(yrs) == y).any() else float("nan") for y in (2021, 2022, 2023)]
                lo, sh = x["net"][x["side"] > 0], x["net"][x["side"] < 0]
                A.append([a["trades"], a["avg_trade"], a["pf"], a["win"], a["max_dd"], a["net"] / a["max_dd"] if a["max_dd"] else 0, lo.mean() if len(lo) else 0, sh.mean() if len(sh) else 0, a["max_dd"] / 10, float(np.nanmedian(x["risk"])), *py])
            A = np.array(A, float); v = A.mean(axis=0)
            print(f"{sess:6s} {('none' if r == 0 else f'{r:g}R'):7s} {label:8s} | {v[0]:5.0f} {v[1]:6.1f} {v[2]:5.2f} {100*v[3]:4.0f}% {v[4]:7.0f} {v[5]:6.2f} | {v[6]:7.1f} {v[7]:8.1f} | {v[8]:6.0f} (stop {v[9]:.0f} pts) | {v[10]:6.1f} {v[11]:6.1f} {v[12]:6.1f}")
