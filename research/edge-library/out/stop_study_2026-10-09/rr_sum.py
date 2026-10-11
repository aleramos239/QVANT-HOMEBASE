import json, sys, numpy as np
rows = [r for r in json.load(open(sys.argv[1])) if "__" not in r["key"]]
root = sys.argv[2]; rows = [r for r in rows if r["root"] == root]
print(root, len(rows), "boxes with 200+ trades from", len({r["key"] for r in rows}), "heat maps,", len({r["fam"] for r in rows}), "entry rules")
def line(tag, rs):
    if len(rs) < 30: return
    P = [r for r in rs if r["net"] > 0]
    ev = np.array([r.get("ev", 0.0) for r in rs]); evp = np.array([r["ev"] for r in P if "ev" in r] or [0.0]); pay = np.array([r["pay"] for r in P if "pay" in r] or [0.0])
    print(f"{tag:22s} {len(rs):6d} | win {100*np.median([r['win'] for r in rs]):3.0f}% | profitable {100*len(P)/len(rs):3.0f}% | avg trade ${np.median([r['avg'] for r in rs]):6.1f} | at $70 {100*np.mean([r['avg']>=70 for r in rs]):3.0f}% | "
          f"months won>=70% {100*np.mean([r['months']>=0.7 for r in rs]):3.0f}% | lose-run<=8 {100*np.mean([r['lose_run']<=8 for r in rs]):3.0f}% | eval odds: all {100*ev.mean():4.1f}%  profitable {100*np.median(evp):4.1f}%  top-10% {100*np.quantile(ev,0.9):4.1f}% | payout (profitable) {100*np.median(pay):4.1f}%")
print("\nBY TARGET (reward : risk)")
for t in (0.5, 0.75, 1.0, 2.0, 3.0, 0.0): line(("none" if t == 0 else f"{t:g}R"), [r for r in rows if r["tgt"] == t])
print("\nBY STOP")
for s in sorted({r["stop"] for r in rows}, key=lambda s: (s[:3], float(s[3:]))): line(s, [r for r in rows if r["stop"] == s])
print("\nBY WIN RATE")
for a, b in ((0, .35), (.35, .45), (.45, .55), (.55, .65), (.65, 1.01)): line(f"win {100*a:.0f}-{100*b:.0f}%", [r for r in rows if a <= r["win"] < b])
print("\nSMALL STOP x SMALL TARGET vs WIDE STOP x SMALL TARGET vs WIDE STOP x BIG TARGET")
small, wide = ("pts10", "pts20", "pct0.1"), ("pts45", "atr3", "pct0.2")
line("small stop, <=1R", [r for r in rows if r["stop"] in small and r["tgt"] in (0.5, 0.75, 1.0)])
line("small stop, >=2R/none", [r for r in rows if r["stop"] in small and r["tgt"] in (2.0, 3.0, 0.0)])
line("wide stop, <=1R", [r for r in rows if r["stop"] in wide and r["tgt"] in (0.5, 0.75, 1.0)])
line("wide stop, >=2R/none", [r for r in rows if r["stop"] in wide and r["tgt"] in (2.0, 3.0, 0.0)])
top = sorted([r for r in rows if "ev" in r], key=lambda r: -r["ev"])[:400]
print("\nTHE 400 BOXES WITH THE BEST EVAL ODDS: what are they?  eval odds", f"{100*top[-1]['ev']:.0f}%..{100*top[0]['ev']:.0f}%")
import collections
print(" target:", dict(collections.Counter("none" if r["tgt"] == 0 else f"{r['tgt']:g}R" for r in top).most_common()))
print(" stop:  ", dict(collections.Counter(r["stop"] for r in top).most_common()))
print(" win rate median", f"{100*np.median([r['win'] for r in top]):.0f}%", "| rules:", dict(collections.Counter(r["fam"] for r in top).most_common(6)))
