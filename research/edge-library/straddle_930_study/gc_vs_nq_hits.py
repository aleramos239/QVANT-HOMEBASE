"""GC vs NQ at 9:30, two accounts (one long, one short, market), $1,000 stop per contract, 1:2, in-sample. Hit rates only.
NQ: 1 NQ, 50/100 pts (bcc2 / 4b5a). GC: 2 GC, 10/20 pts = $2,000 stop total (6ea8 / 8c3d)."""
import json, glob
import pandas as pd
R = "/Users/ramoscapital/ramos-quant-homebase/homebase/.state/tester/runs/"

def load(strat, k):
    m = glob.glob(f"{R}20261101-*-{strat}-{k}"); assert len(m) == 1
    return pd.DataFrame({x["date"]: (x["net"], x["exit_reason"] == "tp") for x in json.load(open(m[0] + "/trades.json"))},
                        index=["net", "tp"]).T

def pair(strat, lk, sk):
    L, S = load(strat, lk), load(strat, sk)
    q = pd.DataFrame({"l": L.net, "s": S.net, "a": L.tp, "b": S.tp}).dropna()
    return q

def pct(q):
    return (q.a.astype(bool) | q.b.astype(bool)).mean() * 100, ((q.l > 0) | (q.s > 0)).mean() * 100

if __name__ == "__main__":
    M = {"NQ": pair("draft_nq_930_side", "bcc2", "4b5a"), "GC": pair("draft_gc_930_side", "6ea8", "8c3d")}
    print("| Market | Days | ≥1 hits full TP | ≥1 wins |\n|---|---|---|---|")
    for k, q in M.items():
        t, w = pct(q); print(f"| {k} | {len(q)} | {t:.1f}% | {w:.1f}% |")
    print("\n| Year | NQ ≥1 TP | NQ ≥1 wins | GC ≥1 TP | GC ≥1 wins |\n|---|---|---|---|---|")
    for y in sorted(set(M["NQ"].index.str[:4]) | set(M["GC"].index.str[:4])):
        cells = []
        for k in ("NQ", "GC"):
            q = M[k][M[k].index.str[:4] == y]
            cells += [f"{v:.1f}%" for v in pct(q)] if len(q) else ["-", "-"]
        print(f"| {y} | " + " | ".join(cells) + " |")
    g = M["GC"]; print("\nGC exits:", pd.concat([load('draft_gc_930_side','6ea8'), load('draft_gc_930_side','8c3d')]).shape)
