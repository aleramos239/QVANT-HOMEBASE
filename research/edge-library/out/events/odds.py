"""STAGE 3 ODDS (information; EDGE_SPEC "STAGE 3" last paragraph): each admitted member and orb_NQ_tf1_pre ALONE on Lucid Flex /
Pro / Pro noDLL and Apex 50K, intraday rule (open losses count; Apex funded: 'pess'). BUILD + 2024 trades (2025+ never read).
  eval     P(pass <= 10 trading days): (i) every rolling start; (ii) only starts on the trading day BEFORE a tier-1 08:30 release
           (the next session is a group-B day). engine/score.py's own day walk and race on a 10-session window (the helper of
           out/admit_r1/member_odds.py; at 5 sessions it reproduces score_eval's p5, asserted).
  funded   P(max payout <= 20 trading days) = score_funded(policy 'max')['p_pay_20'].
  size     MAX = the largest micro count whose worst single-trade open loss (BUILD + 2024, + $1 commission) stays inside the
           account's drawdown ($2,000), cut to the contract limit (Lucid 40 micros, Apex 100);  R1000 = round($1,000 / (median
           stop distance x $ per point per micro)), cut to the same limit. One fixed size per run, no day rules.
  fills    BASE = the engine's fill on the trigger print (+ 1 tick);  5MS = the entry filled at the first print >= 5 ms after
           the trigger print, never better than the stop price (out/events/fill_probe.py re-priced trade records).
score.py is an NQ engine ($20 a point): a GC trade's prices are multiplied by 5 ($100 a point = 5 x $20), dollars unchanged;
GC runs use GC's own session calendar. Writes out/events/odds.json."""
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(HERE))
import ev as E  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import score as SC  # noqa: E402

EVALS = [("Lucid Flex 50K", "lucid", "flex"), ("Lucid Pro 50K (DLL)", "lucidpro", "pro_dll"),
         ("Lucid Pro 50K noDLL", "lucidpro_nodll", "pro_nodll"), ("Apex 50K", "apex", "apex")]
PRICE_KEYS = ("entry_price", "exit_price", "order_price", "sl", "tp", "mae_pts", "mfe_pts")


def nq_units(trades: list, root: str) -> list:
    k = S.SPECS[root][0] / 20.0
    if k == 1.0:
        return trades
    return [{**t, **{a: (None if t.get(a) is None else float(t[a]) * k) for a in PRICE_KEYS if a in t}} for t in trades]


def eval_h(trades, firm, micros, cal, H=10, before=None):
    fm = SC._firm(firm)
    rl = SC.norm_rules(None, micros)
    mem, c = SC._prep(trades, "all", rl["micros"], "all", cal, False, "raise")
    pv = SC.P.PV([(SC._base(m, c), m["micros"]) for m in mem], c.D)
    A = SC._make_A(pv, fm, rl)
    n = c.D - H + 1
    idx = np.arange(n)[:, None] + np.arange(H)
    o, d = SC.E.race(idx, A, fm.r, "intraday", rl["target_stop"], rl["target_take"])
    ps = o == 1
    out = {"starts": int(n), "p_pass": float(ps.mean()), "p5": float((ps & (d <= 5)).mean()), "bust": float((o == 2).mean()),
           "med_days": float(np.median(d[ps])) if ps.any() else None, "cap_ok": bool(A.st["cap_viol"] == 0 and A.st["clipped"] == 0)}
    if before is not None:
        iso = list(c.iso)
        sel = np.array([s + 1 < len(iso) and iso[s + 1] in before for s in range(n)], bool)
        out.update(starts_before=int(sel.sum()), p_pass_before=float(ps[sel].mean()) if sel.any() else None,
                   bust_before=float((o[sel] == 2).mean()) if sel.any() else None)
    return out


def main():
    adm = json.loads((HERE / "admission.json").read_text())
    names = [(o["name"], uid) for uid, o in adm.items() if o.get("admit") and o.get("dir")] + [("orb_NQ_tf1_pre", None)]
    tier1 = E.days("B")
    res = {}
    for name, uid in names:
        d = W / "members" / name
        spec = json.loads((d / "spec.json").read_text())
        root = spec["root"]
        cal = None if root == "NQ" else LB.calendar("build", root) + LB.calendar("pick", root)
        fills = {"BASE": json.loads((d / "trades_build.json").read_text()) + json.loads((d / "trades_pick.json").read_text()),
                 "5MS": json.loads((HERE / "member_runs" / f"fill5-{name}-build.json").read_text())
                        + json.loads((HERE / "member_runs" / f"fill5-{name}-pick.json").read_text())}
        res[name] = {"uid": uid, "root": root, "rows": []}
        for fill, raw in fills.items():
            assert max(t["date"] for t in raw) < "2025-01-01"
            pvm = S.SPECS[root][0] / 10.0
            stop = float(np.median([abs(t["entry_price"] - t["sl"]) for t in raw if t.get("sl") is not None]))
            worst = max(abs(t["mae_usd"]) for t in raw) / 10.0 + 1.0
            tr = nq_units(raw, root)
            for label, ef, ff in EVALS:
                fm = SC._firm(ef)
                dd = float(fm.r["trailing_mll"])
                sizes = {"MAX": max(1, min(fm.cap, int(dd // worst))), "R1000": max(1, min(fm.cap, int(round(1000.0 / (stop * pvm)))))}
                for sz, m in sizes.items():
                    if ef != "apex":
                        chk = eval_h(tr, ef, m, cal, 5)["p5"]
                        ref = SC.score_eval(tr, ef, micros=m, model="intraday", boots=0, calendar=cal)["p5"]
                        assert abs(chk - ref) < 1e-12, (name, ef, chk, ref)
                    e = eval_h(tr, ef, m, cal, 10, tier1)
                    f = SC.score_funded(tr, ff, "max", micros=m, model="intraday" if ff != "apex" else None, boots=0, both_sides=True,
                                        calendar=cal)
                    fmo = f["models"]["intraday" if ff != "apex" else "pess"]
                    row = {"fill": fill, "account": label, "size": sz, "micros": m, "risk_usd": round(m * stop * pvm),
                           "worst_open_loss": round(m * worst), "eval_p10": e["p_pass"], "eval_bust10": e["bust"],
                           "eval_p10_before_tier1": e["p_pass_before"], "eval_bust10_before_tier1": e["bust_before"],
                           "starts": e["starts"], "starts_before": e["starts_before"], "eval_med_days": e["med_days"],
                           "funded_p20": fmo["p_pay_20"], "funded_bust_pre_first": fmo.get("p_bust_pre_first"),
                           "noncompliant": f.get("noncompliant"), "trades": len(raw), "net_1c": round(sum(t["net"] for t in raw), 2)}
                    res[name]["rows"].append(row)
                    print(name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
    (HERE / "odds.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
