import sys, collections
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import WImb930
from widefeat import WideFeatures, WideC2
cols = list(WImb930.FEATURES)
if __name__ == "__main__":
    out = {}
    for mode in ("wimb", "wimb_inv", "long"):
        r = S.run(WImb930, {"mode": mode}, "2023-05-01", "2023-05-12", features=WideFeatures(cols), workers=2)
        out[mode] = {t["date"]: t["side"] for t in r["trades"]}
        print(mode, "sessions", r["sessions"], "used", r["used"], "err", r.get("skipped_by_error"), "trades", len(r["trades"]), dict(collections.Counter(out[mode].values())), "both_sides", r.get("both_sides_sessions"))
    print("inverse flips every side:", all(out["wimb"][d] != out["wimb_inv"][d] for d in out["wimb"] if d in out["wimb_inv"]), "| same days:", set(out["wimb"]) == set(out["wimb_inv"]))
    n = S.run(WImb930, {"mode": "wimb"}, "2023-05-01", "2023-05-12", features=WideC2(cols, seed=1), workers=2)
    print("C2 null seed1: trades", len(n["trades"]), dict(collections.Counter(t["side"] for t in n["trades"])), "err", n.get("skipped_by_error"))
