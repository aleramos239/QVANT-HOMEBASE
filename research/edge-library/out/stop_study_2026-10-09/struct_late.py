"""Read-only: part 2 (2024-01..2025-06, later build days), NQ 5-minute: structure stop vs the fixed stops, same entries; average of all variants."""
import sys, json
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import library as L
D = sys.argv[1]
for key in ("donchian-NQ-tf5", "orb-NQ-tf5", "supertrend-NQ-tf5"):
    j = json.load(open(f"{D}/{key}.json")); z = np.load(f"{D}/{key}.npz"); meta = j["cells"]
    print(f"\n{key}  days {j['days']}  (average of {len({m['vi'] for m in meta})} setting values, both sides, 1 contract)")
    print(f"{'session':6s} {'stop':8s} | trades  avg$    PF  win  maxDD  net/DD  stop pts | share of 4 targets x values profitable")
    for sess in ("nyam", "mid", "pm"):
        for label in ("struct", "atr3", "atr1.5", "pts45", "pts30", "pts20", "pts10"):
            A = []
            for m in meta:
                e = m["exit"]; lab = "struct" if e["stop_mode"] == "struct" else f'{e["stop_mode"]}{e["stop_val"]:g}'
                if lab != label: continue
                x = {k: z[f"{m['id']}|{k}"] for k in L.FIELDS}
                mk = np.asarray(x["sess"]) == L.SESS_CODE[sess]
                x = {k: np.asarray(x[k])[mk] for k in L.FIELDS}
                if not len(x["net"]): continue
                a = L.metrics(x)
                A.append([a["trades"], a["avg_trade"], a["pf"] or 0, a["win"], a["max_dd"], a["net"] / a["max_dd"] if a["max_dd"] else 0, float(np.nanmedian(x["risk"])), a["net"] > 0])
            if not A: continue
            v = np.array(A, float).mean(axis=0)
            print(f"{sess:6s} {label:8s} | {v[0]:5.0f} {v[1]:6.1f} {v[2]:5.2f} {100*v[3]:3.0f}% {v[4]:6.0f} {v[5]:6.2f} {v[6]:8.0f} | {100*v[7]:3.0f}%")
