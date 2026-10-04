"""STAGE 2b: every library member ALONE on each account type (EDGE_SPEC "STAGE 2b", last paragraph). 2021-09-22..2024-12-31
(BUILD + PICK; 2025+ never read), engine/score.py (+ engine/apex300.py for the Apex PA accounts), breach model = intraday (open
losses count; Apex PA: 'pess' = the worst intraday order).
  size     "about $1,000 of risk" = ONE fixed size per member: round($1,000 / (median stop distance x $2 per point per micro)),
           cut to the account's contract limit (Lucid 50K: 40 micros; Apex 50K: 100; Apex 300K: 350). The engine sizes a member
           with one number of micros; no day rules (no daily take / stop), stop trading once the target is hit (the engine default).
  eval     P(pass <= 10 trading days): score.py's own day walk and race (evalcore.race) on a 10-session rolling window instead of
           its built-in 5 (checked: the same helper at 5 sessions reproduces score_eval's p5 exactly).
  funded   P(max payout <= 20 trading days) = score_funded(policy='max')['p_pay_20'] (request only when the cheque reaches the
           per-payout cap; first payout within 20 sessions of a rolling start).
Writes out/admit_r1/member_odds.json and out/member_odds.md."""
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import score as SC  # noqa: E402

OUT = W / "out"
MEMBERS = [("orb_NQ_tf1_pre", "clean member"), ("straddle_tight_0830_NQ_tf30_pre", "FLAGGED member (stage 2b; thin random bar; same idea as orb_NQ_tf1_pre)")]
EVALS = [("Lucid Flex 50K", "lucid", "flex"), ("Lucid Pro 50K (daily loss limit)", "lucidpro", "pro_dll"),
         ("Lucid Pro 50K, no daily loss limit", "lucidpro_nodll", "pro_nodll"), ("Apex 50K", "apex", "apex")]
PV_MICRO = 2.0


def load(name):
    d = W / "members" / name
    rows = json.loads((d / "trades_build.json").read_text()) + json.loads((d / "trades_pick.json").read_text())
    assert max(r["date"] for r in rows) < "2025-01-01"
    return rows


def eval_h(trades, firm, micros, H=10):
    fm = SC._firm(firm)
    rl = SC.norm_rules(None, micros)
    mem, cal = SC._prep(trades, "all", rl["micros"], "all", None, False, "raise")
    pv = SC.P.PV([(SC._base(m, cal), m["micros"]) for m in mem], cal.D)
    A = SC._make_A(pv, fm, rl)
    S = cal.D - H + 1
    idx = np.arange(S)[:, None] + np.arange(H)
    out = {"starts": int(S), "cap_ok": bool(A.st["cap_viol"] == 0 and A.st["clipped"] == 0)}
    for b in SC.MODELS:
        o, d = SC.E.race(idx, A, fm.r, b, rl["target_stop"], rl["target_take"])
        ps = o == 1
        out[b] = {"p_pass": float(ps.mean()), "p5": float((ps & (d <= 5)).mean()), "bust": float((o == 2).mean()),
                  "neither": float((o == 0).mean()), "med_days": float(np.median(d[ps])) if ps.any() else None}
    return out


def main():
    res, L = {}, []
    for name, tag in MEMBERS:
        tr = load(name)
        risk = np.array([abs(t["entry_price"] - t["sl"]) for t in tr if t.get("sl") is not None])
        m1000 = int(round(1000.0 / (float(np.median(risk)) * PV_MICRO)))
        worst = max(abs(t["mae_usd"]) for t in tr) / 10.0 + 1.0
        res[name] = {"tag": tag, "trades": len(tr), "median_stop_pts": float(np.median(risk)), "micros_1000": m1000,
                     "worst_open_loss_per_micro": round(worst, 2), "rows": []}
        for label, ef, ff in EVALS:
            cap = SC._firm(ef).cap
            m = min(cap, m1000)
            chk = eval_h(tr, ef, m, 5)["intraday"]["p5"]
            ref = SC.score_eval(tr, ef, micros=m, model="intraday", boots=0)["p5"]
            assert abs(chk - ref) < 1e-12, (name, ef, chk, ref)
            e = eval_h(tr, ef, m, 10)
            f = SC.score_funded(tr, ff, "max", micros=m, model="intraday" if ff != "apex" else None, boots=0, both_sides=True)
            fm = f["models"]["intraday" if ff != "apex" else "pess"]
            res[name]["rows"].append({"account": label, "micros": m, "capped": m < m1000, "risk_usd": round(m * float(np.median(risk)) * PV_MICRO),
                                      "worst_open_loss": round(m * worst), "eval_p10": e["intraday"]["p_pass"], "eval_bust10": e["intraday"]["bust"],
                                      "eval_p5": e["intraday"]["p5"], "eval_med_days": e["intraday"]["med_days"],
                                      "eval_p10_eod": e["eod"]["p_pass"], "funded_p20": fm["p_pay_20"], "funded_p40": fm.get("p_pay_40"),
                                      "funded_bust_pre_first": fm.get("p_bust_pre_first"), "funded_model": "intraday" if ff != "apex" else "pess",
                                      "apex_flags": f.get("apex_flags") or f.get("gate_flags"), "noncompliant": f.get("noncompliant")})
        m = min(350, m1000)
        e3 = SC.score_eval(tr, "apex300_eval", micros=m, boots=0, both_sides=True)
        f3 = SC.score_funded(tr, "apex300_pa", "max", micros=m, boots=0, both_sides=True)
        fm = f3["models"]["pess"]
        res[name]["rows"].append({"account": "Apex 300K PA", "micros": m, "capped": False, "risk_usd": round(m * float(np.median(risk)) * PV_MICRO),
                                  "worst_open_loss": round(m * worst), "eval_p10": e3.get("p10"), "eval_bust10": e3.get("bust10"), "eval_p5": None,
                                  "eval_med_days": e3.get("med_days"), "eval_p10_eod": None, "funded_p20": fm["p_pay_20"], "funded_p40": fm.get("p_pay_40"),
                                  "funded_bust_pre_first": fm.get("p_bust_pre_first"), "funded_model": "pess",
                                  "apex_flags": f3.get("apex_flags"), "noncompliant": f3.get("noncompliant"),
                                  "compliance": f3.get("compliance")})
        for r in res[name]["rows"]:
            print(name, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    (OUT / "admit_r1" / "member_odds.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
