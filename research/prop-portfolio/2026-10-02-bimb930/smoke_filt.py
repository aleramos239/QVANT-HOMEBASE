import sys, collections
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import Combo930, Flow930, rsi14
from widefeat import WideFeatures
if __name__ == "__main__":
    print("rsi14 rising closes:", rsi14([float(i) for i in range(1, 60)]), "| falling:", rsi14([float(100 - i) for i in range(60)]), "| flat+noise ~50:", round(rsi14([100 + (i % 2) for i in range(80)]), 1))
    for lo, hi in (("2021-09-22", "2021-12-15"), ("2023-03-01", "2023-06-30")):
        specs = [(Flow930, {"mode": "long", "filt": f}) for f in ("off", "adx", "rsi")] + [(Flow930, {"mode": "flow", "filt": f}) for f in ("off", "adx", "rsi")]
        runs = S.run_many(specs, lo, hi, features=S.L2Features(list(Flow930.FEATURES)), workers=2)
        print(lo, hi)
        for (c, p), r in zip(specs, runs):
            print("  ", p["mode"], p["filt"], "| used", r["used"], "err", r.get("skipped_by_error"), "trades", len(r["trades"]), dict(collections.Counter(t["side"] for t in r["trades"])))
