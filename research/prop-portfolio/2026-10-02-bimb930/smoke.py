import sys, collections
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S, score as SC
from bimb930 import Imb930
cols = list(Imb930.FEATURES)
if __name__ == "__main__":
    for mode in ("imb", "long"):
        r = S.run(Imb930, {"mode": mode}, "2023-05-01", "2023-05-12", features=S.L2Features(cols), workers=2)
        sides = collections.Counter(t["side"] for t in r["trades"])
        import datetime as dt, zoneinfo
        ny = zoneinfo.ZoneInfo("America/New_York")
        late = sum(1 for t in r["trades"] if dt.datetime.fromtimestamp(t["exit_ms"]/1000, ny).time() >= dt.time(11, 0))
        print(mode, "exits_after_11:00", late, "reasons", dict(collections.Counter(t["exit_reason"] for t in r["trades"])), "| sessions", r["sessions"], "used", r["used"], "skipped_by_error", r.get("skipped_by_error"),
              "trades", len(r["trades"]), dict(sides), "both_sides_sessions", r.get("both_sides_sessions"))
    n = S.run(Imb930, {"mode": "imb"}, "2023-05-01", "2023-05-12", features=SC.C2Features(cols, seed=1), workers=2)
    print("c2 null seed1 trades", len(n["trades"]), dict(collections.Counter(t["side"] for t in n["trades"])))
