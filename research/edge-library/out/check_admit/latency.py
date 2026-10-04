import sys, json
from pathlib import Path
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, str(W / "engine"))
if __name__ == "__main__":
    import l2sim as S, families as F
    p = {**F.REGISTRY["orb"][1], "tf": "1", "sess": "pre", "or_min": "5", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0, "hold_to": "day"}
    for kw in ({"slip_ticks": 2.0}, {"latency_ms": 250}, {"slip_ticks": 2.0, "latency_ms": 250}):
        r = S.run(F.REGISTRY["orb"][0], p, period="build", root="NQ", workers=4, **kw)
        tr = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == "pre"]
        print(kw, "trades", len(tr), "net", round(sum(t["net"] for t in tr)), "meta stress", r["meta"].get("stress"))
    print("placement_ms default", F.REGISTRY["orb"][0].placement_ms, "STRESS", S.STRESS)
