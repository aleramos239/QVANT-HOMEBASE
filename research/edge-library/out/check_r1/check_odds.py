"""CHECKER (stage 2b) -- member odds recomputed for the Lucid accounts (and Apex 50K eval).
  sizing   about $1,000 of risk = round(1000 / (median stop distance in points x $2 per point per micro)), cut to the account's
           contract limit (Lucid 50K: 40 micros). The same rule the analyst states; recomputed here from the trade files.
  eval     MY OWN day walk (one trade a day; open losses count): start at 0, floor -2,000 trailing the END-OF-DAY peak, locked
           at +100 once the peak reaches +2,100; bust when profit + the day's worst open point <= floor or the day's close <=
           floor; pass at +3,000 (Flex: at least 2 traded days and no day above 50 % of the profit; Pro: daily loss limit
           1,200 stops the day). Every possible start day, 10 trading days. Costs: $4 per 10 micros round turn.
           The same walk on 5 days is compared with engine/score.py score_eval(...)['p5'] (must be equal).
  funded   engine/score.py score_funded(policy 'max')['p_pay_20'] and the bust figure, read directly.
BUILD + 2024 trades of the two members (files already read by the analyst). 2025+ never."""
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402
import score as SC  # noqa: E402

RULES = {"lucid": dict(target=3000, mll=2000, lock_at=2100, lock_floor=100, min_days=2, cons=0.5, dll=0.0),
         "lucidpro": dict(target=3000, mll=2000, lock_at=2100, lock_floor=100, min_days=1, cons=None, dll=1200.0),
         "lucidpro_nodll": dict(target=3000, mll=2000, lock_at=2100, lock_floor=100, min_days=1, cons=None, dll=0.0),
         "apex": dict(target=3000, mll=2000, lock_at=2100, lock_floor=100, min_days=1, cons=None, dll=0.0)}
CAP = {"lucid": 40, "lucidpro": 40, "lucidpro_nodll": 40, "apex": 100}
TICK_USD = 0.5                                             # one NQ tick per micro


def cost(n):
    return (n // 10) * 4.0 + (n % 10) * 1.0


def day_arrays(trades, cal, n, dll):
    idx = {d: i for i, d in enumerate(cal)}
    pnl, wst, trd = np.zeros(len(cal)), np.zeros(len(cal)), np.zeros(len(cal), bool)
    per_day = {}
    for t in trades:
        per_day.setdefault(t["date"], []).append(t)
    assert max(len(v) for v in per_day.values()) == 1, "more than one trade a day: my simple walk does not apply"
    for d, (t,) in per_day.items():
        c = cost(n)
        p = n * t["gross"] / 10.0 - c
        w = min(p, -t["mae_usd"] * n / 10.0 - c)
        if dll and w <= -dll:                              # the daily loss limit closes the day at -dll (+ 1 tick per micro)
            p = -dll - TICK_USD * n
            w = p
        i = idx[d]
        pnl[i], wst[i], trd[i] = p, w, True
    return pnl, wst, trd


def my_eval(trades, cal, firm, n, H):
    r = RULES[firm]
    pnl, wst, trd = day_arrays(trades, cal, n, r["dll"])
    if r["dll"]:
        pnl = np.maximum(pnl, -r["dll"])
    P = len(cal) - H + 1
    res = np.zeros(P, np.int8)
    for s in range(P):
        profit = peak = largest = 0.0
        floor, td = -float(r["mll"]), 0
        for k in range(s, s + H):
            new = profit + pnl[k]
            if new <= floor or profit + wst[k] <= floor:
                res[s] = 2
                break
            profit = new
            td += int(trd[k])
            largest = max(largest, pnl[k])
            peak = max(peak, new)
            floor = float(r["lock_floor"]) if peak >= r["lock_at"] else peak - r["mll"]
            if new >= r["target"] and td >= r["min_days"] and (r["cons"] is None or largest <= r["cons"] * new):
                res[s] = 1
                break
    return float((res == 1).mean()), float((res == 2).mean())


def main():
    cal = [d.isoformat() for d in S.sessions(S.BUILD[0], S.PICK[1], "NQ")]
    assert len(cal) == 825 and cal[-1] <= "2024-12-31"
    theirs = json.loads((W / "out" / "admit_r1" / "member_odds.json").read_text())
    out = {}
    for name in ("straddle_tight_0830_NQ_tf30_pre", "orb_NQ_tf1_pre"):
        d = W / "members" / name
        tr = json.loads((d / "trades_build.json").read_text()) + json.loads((d / "trades_pick.json").read_text())
        assert max(t["date"] for t in tr) < "2025-01-01"
        stop = float(np.median([abs(t["entry_price"] - t["sl"]) for t in tr if t.get("sl") is not None]))
        m1000 = int(round(1000.0 / (stop * 2.0)))
        worst = max(t["mae_usd"] for t in tr)
        print(f"{name}: trades {len(tr)}, median stop {stop} pts -> {m1000} micros for $1,000; worst open loss 1 contract ${worst:.0f}")
        out[name] = {"median_stop_pts": stop, "micros_1000": m1000, "rows": []}
        for firm, fv in (("lucid", "flex"), ("lucidpro", "pro_dll"), ("lucidpro_nodll", "pro_nodll"), ("apex", None)):
            n = min(CAP[firm], m1000)
            p5_mine, _ = my_eval(tr, cal, firm, n, 5)
            ref = SC.score_eval(tr, firm, micros=n, model="intraday", boots=0)
            p10, b10 = my_eval(tr, cal, firm, n, 10)
            row = {"firm": firm, "micros": n, "risk_usd": n * stop * 2.0, "my_p5": p5_mine, "engine_p5": ref["p5"],
                   "my_p10": p10, "my_bust10": b10}
            if fv:
                f = SC.score_funded(tr, fv, "max", micros=n, model="intraday", boots=0, both_sides=True)
                fm = f["models"]["intraday"]
                row.update(funded_p20=fm["p_pay_20"], funded_bust_pre_first=fm.get("p_bust_pre_first"))
            t = next((x for x in theirs[name]["rows"] if x["micros"] == n and (
                (firm == "lucid" and "Flex" in x["account"]) or (firm == "lucidpro" and "(daily loss limit)" in x["account"]) or
                (firm == "lucidpro_nodll" and "no daily" in x["account"]) or (firm == "apex" and x["account"] == "Apex 50K"))), None)
            if t:
                row.update(their_p10=t["eval_p10"], their_bust10=t["eval_bust10"], their_funded_p20=t["funded_p20"],
                           their_funded_bust=t["funded_bust_pre_first"])
            out[name]["rows"].append(row)
            print("  ", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
    Path(__file__).with_name("check_odds.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
