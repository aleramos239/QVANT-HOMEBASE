import sys, collections
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import Combo930
from widefeat import WideFeatures
if __name__ == "__main__":
    modes = Combo930.MODES
    runs = S.run_many([(Combo930, {"mode": m}) for m in modes], "2023-03-01", "2023-04-28", features=WideFeatures(list(Combo930.FEATURES)), workers=2)
    sides = {m: {t["date"]: t["side"] for t in r["trades"]} for m, r in zip(modes, runs)}
    for m, r in zip(modes, runs): print(m, "trades", len(r["trades"]), dict(collections.Counter(sides[m].values())), "err", r.get("skipped_by_error"), "both_sides", r.get("both_sides_sessions"))
    A, D, ALL = set(sides["long_agree"]), set(sides["long_dis"]), set(sides["long_all"])
    print("agree days + dis days == all days:", A | D == ALL and not (A & D), "| agree rule days == agree days:", set(sides["agree"]) == A, "| dis rule days == dis days:", set(sides["dis"]) == D)
    print("inverse flips every side (agree/dis):", all(sides["agree"][d] != sides["agree_inv"][d] for d in A), all(sides["dis"][d] != sides["dis_inv"][d] for d in D))
