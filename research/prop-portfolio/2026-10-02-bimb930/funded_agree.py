import sys, json, copy, datetime as dt
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2")
import numpy as np
import l2sim as S
import score as SC
from bimb930 import Combo930
from widefeat import WideFeatures
RISK, COMM = 1000.0, 1.04
CELLS = {"agree_inv_atr1.5_1to3": ("agree_inv", "atr", 1.5, 3.0), "long_agree_atr1.5_1to3": ("long_agree", "atr", 1.5, 3.0), "agree_inv_25pt_1to3": ("agree_inv", "pts", 25.0, 3.0)}

def sized(trades):
    """Original 1-NQ sim rows (unchanged, they pass the scorer's row checks) + each trade's micro count and its own net."""
    out = []
    for t in trades:
        d = abs(t["entry_price"] - t["sl"]); n = int(max(1, min(170, round(RISK / (d * 2.0)))))
        r = dict(t); r["_micros"] = n; r["_net"] = t["gross"] * n / 10.0 - n * COMM; out.append(r)
    return out

def members(rows):
    """One portfolio member per micro size: every trade is then scored at ITS OWN micros (apex300 sizes per member)."""
    by = {}
    for r in rows: by.setdefault(r["_micros"], []).append({k: v for k, v in r.items() if not k.startswith("_")})
    return [{"src": v, "sess": "all", "micros": n, "label": f"m{n}"} for n, v in sorted(by.items())]

if __name__ == "__main__":
    keys = list(CELLS)
    runs = S.run_many([(Combo930, {"mode": m, "stop_mode": sm, "stop_val": v, "tgt_r": r}) for m, sm, v, r in CELLS.values()], features=WideFeatures(list(Combo930.FEATURES)))
    res, eq = {}, {}
    for k, r in zip(keys, runs):
        assert not r.get("skipped_by_error")
        rows = sized(r["trades"]); res[k] = (r, rows)
        eq[k] = [(t["date"], t["_net"]) for t in rows]
        print(k, "trades", len(rows), "net %.0f" % sum(t["_net"] for t in rows), "avg micros %.1f" % np.mean([t["_micros"] for t in rows]), "min/max micros", min(t["_micros"] for t in rows), max(t["_micros"] for t in rows))
    json.dump(eq, open("out_heat2/equity_agree.json", "w"))
    PAGE = dict(net_pay=7000.0, post_req_min=7500.0, post_net_min=7500.0, post_cap_net=7500.0)
    USER = dict(net_pay=4000.0, post_req_min=7500.0, post_net_min=4000.0, post_cap_net=4000.0)
    F = ["p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_net", "e_cheque_if_paid", "e_net_40", "e_net_60", "p_bust_pre_first", "p_bust_any", "e_npay_40", "e_npay_60", "cut_share", "cuts"]
    out = {}
    for k in ("agree_inv_atr1.5_1to3", "agree_inv_25pt_1to3", "long_agree_atr1.5_1to3"):
        r, rows = res[k]; m, sm, v, rr = CELLS[k]
        for label, over, pol in (("user_rule_3500_at_7500", USER, "max"), ("page_reading_T500", PAGE, 500), ("page_reading_Tmax", PAGE, "max")):
            fr = SC.score_funded(members(rows), "apex300_pa", pol, sess="all", strategy="bimb930_combo", inputs={"tgt_r": rr}, both_sides=False, start="fresh", comm_nq=10.4, comm_mnq=1.04, **over)
            x = {q: (None if fr.get(q) is None else round(float(fr[q]), 3)) for q in F}
            x["ci_e40"] = [round(c) for c in fr["e_net_40_ci"]]; x["compliance"] = fr.get("compliance"); x["n_starts"] = fr.get("n_starts"); x["trades"] = fr.get("trades")
            alt = (fr.get("cons_alt") or {}).get(fr.get("model")) or {}; x["e_net_40_cons_balance"] = None if not alt else round(float(alt.get("e_net_40", 0)))
            out[f"{k}|{label}"] = x; print(k, label, x, flush=True)
    json.dump(out, open("out_heat2/funded_agree.json", "w"), indent=1, default=str)
