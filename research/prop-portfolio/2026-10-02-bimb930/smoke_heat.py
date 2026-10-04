import sys
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import Flow930
if __name__ == "__main__":
    specs = [(Flow930, {"mode": m, "stop_mode": sm, "stop_val": v, "tgt_r": r}) for m in ("flow", "long") for sm, v in (("pts", 10.0), ("atr", 2.0)) for r in (1.0, 3.0)]
    runs = S.run_many(specs, "2023-05-01", "2023-05-12", features=S.L2Features(list(Flow930.FEATURES)), workers=2)
    for (c, p), r in zip(specs, runs):
        risks = [abs(t["entry_price"] - t["sl"]) for t in r["trades"]]
        print(p, "| used", r["used"], "err", r.get("skipped_by_error"), "trades", len(r["trades"]), "stop pts min/max", (round(min(risks), 2), round(max(risks), 2)) if risks else None)
