import sys, collections
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S, score as SC
from bimb930 import Flow930
cols = list(Flow930.FEATURES)
if __name__ == "__main__":
    for mode, feat in (("flow", S.L2Features(cols)), ("long", S.L2Features(cols)), ("flow", SC.C2Features(cols, seed=1))):
        r = S.run(Flow930, {"mode": mode}, "2023-05-01", "2023-05-12", features=feat, workers=2)
        print(mode, type(feat).__name__, "sessions", r["sessions"], "used", r["used"], "err", r.get("skipped_by_error"), "trades", len(r["trades"]), dict(collections.Counter(t["side"] for t in r["trades"])), "both_sides", r.get("both_sides_sessions"))
