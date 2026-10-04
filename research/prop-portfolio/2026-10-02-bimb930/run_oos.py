import sys, os, time, gzip, pickle, json
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import l2sim as S
from bimb930 import Combo930, WImb930
from widefeat import WideFeatures
OUT = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_oos/"
START, END = "2025-01-02", "2026-05-29"
GRID = [(sm, v, rr) for sm, vals in (("pts", (10.0, 15.0, 20.0, 25.0, 30.0)), ("atr", (1.0, 1.5, 2.0, 2.5, 3.0))) for v in vals for rr in (1.0, 2.0, 3.0)]
def pack(r):
    return {"trades": [(t["date"], t["side"], t["gross"], abs(t["entry_price"] - t["sl"]), t["exit_reason"]) for t in r["trades"]], "used": r["used"], "sessions": r["sessions"],
            "errors": r.get("skipped_by_error"), "both_sides": r.get("both_sides_sessions"), "exec_guard": (r.get("meta") or {}).get("exec_guard")}
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True); t0 = time.time(); res = {}
    specs = [(Combo930, {"mode": m, "filt": "rsi", "stop_mode": sm, "stop_val": v, "tgt_r": rr}) for m in ("agree", "agree_inv") for sm, v, rr in GRID]
    keys = [(m, sm, v, rr) for m in ("agree", "agree_inv") for sm, v, rr in GRID]
    runs = S.run_many(specs, START, END, allow_holdout=True, features=WideFeatures(list(Combo930.FEATURES), allow_holdout=True))
    for (m, sm, v, rr), r in zip(keys, runs): res[f"combo|{m}|rsi|{sm}|{v}|{rr}"] = pack(r)
    print("combo done", round(time.time() - t0), "s", flush=True)
    sp2 = [(WImb930, {"mode": "wimb_inv", "filt": "adx", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": rr}) for rr in (2.0, 3.0)]
    runs2 = S.run_many(sp2, START, END, allow_holdout=True, features=WideFeatures(list(WImb930.FEATURES), allow_holdout=True))
    for rr, r in zip((2.0, 3.0), runs2): res[f"wide|wimb_inv|adx|pts|30.0|{rr}"] = pack(r)
    with gzip.open(OUT + "trades_oos.pkl.gz", "wb") as f: pickle.dump(res, f)
    r0 = res["combo|agree|rsi|pts|25.0|2.0"]; print("sessions", r0["sessions"], "used", r0["used"], "errors", {k: v["errors"] for k, v in res.items() if v["errors"]}, "exec_guard", r0["exec_guard"])
    print("ALL DONE", round(time.time() - t0), "s", flush=True)
