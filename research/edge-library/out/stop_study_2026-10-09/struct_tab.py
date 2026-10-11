import json, sys, numpy as np
rows = json.load(open(sys.argv[1])); roots = sys.argv[2].split(",")
rows = [r for r in rows if r["root"] in roots]
q = lambda c: c["snet"] / c["sdd"] if c["sdd"] > 0 else 0.0
def line(tag, rs):
    if not rs: return
    n = len(rs)
    rank = np.mean([1 + sum(q(c) > q(r["struct"]) for c in r["fixed"].values()) for r in rs])
    bm = sum(q(r["struct"]) > np.median([q(c) for c in r["fixed"].values()]) for r in rs)
    sp = np.mean([r["struct"]["snet"] > 0 for r in rs]); fp = np.mean([np.mean([c["snet"] > 0 for c in r["fixed"].values()]) for r in rs])
    sa = np.median([r["struct"]["avg"] for r in rs]); fa = np.median([np.median([c["avg"] for c in r["fixed"].values()]) for r in rs])
    fb = np.median([max(c["avg"] for c in r["fixed"].values()) for r in rs])
    so = np.mean([r["struct"]["stop"] for r in rs]); rk = np.median([r["struct"]["risk"] for r in rs])
    near = []
    for r in rs:
        k = min(r["fixed"], key=lambda k: abs(np.log(r["fixed"][k]["risk"] / r["struct"]["risk"])))
        near.append(q(r["struct"]) > q(r["fixed"][k]))
    print(f"{tag:30s} n={n:4d} rank {rank:.1f}/9 beats-middle {100*bm/n:3.0f}% beats-same-size {100*np.mean(near):3.0f}% | profitable S {100*sp:3.0f}% F {100*fp:3.0f}% | avg S {sa:6.1f} F-mid {fa:6.1f} F-best {fb:6.1f} | stop-outs {100*so:2.0f}% dist {rk:.1f}")
DAY = ("nyam", "mid", "pm")
line("ALL", rows); line("ALL NY day", [r for r in rows if r["sess"] in DAY])
for f in dict.fromkeys(r["family"] for r in rows):
    for tf in ("tf1", "tf5"):
        line(f"{f} {tf}", [r for r in rows if r["family"] == f and r["tf"] == tf])
        line(f"  NY day", [r for r in rows if r["family"] == f and r["tf"] == tf and r["sess"] in DAY])
for t in (0.0, 1.0, 2.0, 3.0): line(f"target {t:g}R NY day", [r for r in rows if r["tgt"] == t and r["sess"] in DAY])
tight = ("pinbar", "sweep_rev", "ema_pullback", "vol_spike_break"); wide = ("donchian", "orb", "supertrend")
line("WICK-type rules, NY day", [r for r in rows if r["family"] in tight and r["sess"] in DAY])
line("RANGE-type rules, NY day", [r for r in rows if r["family"] in wide and r["sess"] in DAY])
