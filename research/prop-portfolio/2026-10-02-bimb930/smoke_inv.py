import sys, collections
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import Imb930, Flow930
if __name__ == "__main__":
    for cls, m, base in ((Imb930, "imb_inv", "imb"), (Flow930, "flow_inv", "flow")):
        a = S.run(cls, {"mode": base}, "2023-05-01", "2023-05-12", features=S.L2Features(list(cls.FEATURES)), workers=2)
        b = S.run(cls, {"mode": m}, "2023-05-01", "2023-05-12", features=S.L2Features(list(cls.FEATURES)), workers=2)
        sa = {t["date"]: t["side"] for t in a["trades"]}; sb = {t["date"]: t["side"] for t in b["trades"]}
        flipped = all(sa[d] != sb[d] for d in sa if d in sb)
        print(m, "orig trades", len(sa), "inv trades", len(sb), "same days", set(sa) == set(sb), "every side flipped", flipped, "errors", b.get("skipped_by_error"))
