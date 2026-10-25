"""jj_plan_speed -- RISK AND SPEED FOR A 40 % / 1:1.5 COIN FLIP ON THE $1,000 PLAN (the owner, 2026-10-19: "increase the risk and speed,
base it off as if we had a 40 % win rate with 1:1.5 RR").

A synthetic trade stream: `k` trades a day on the real build-day calendar, each a 40 % coin flip at 1:1.5 after costs (a 25-point stop
on 1 NQ: loss -$509, win +$756, scaled by the micros), through jj_fifty_accounts' 50-account walk (eval -> funded -> every payout) under
each rule file. Swept: micros per trade (the risk) x trades a day (the speed), eval and funded sized apart. Scored by net per eval and by
net per eval per 30 trading days of calendar (the speed), with the median days to the first payout. Averaged over seeds.

Run: .venv-research/bin/python research/edge-library/taught/jj_plan_speed.py [--rules lucid-flex-25k-dll@2026-10-19 --fee 45]
     [--micros 2,4,6,8,10,12,16,20] [--per-day 1,2,4,8,12] [--seeds 3] [--p 0.40] [--funded 2,5,10]"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import jj_fifty_accounts as J                                  # noqa: E402
from homebase.backtest import propsim as P                     # noqa: E402
from homebase.backtest.propsim import propsim as E             # noqa: E402

WIN, LOSS = 756.0, -509.0                                      # 1 NQ at 25 / 38 after the engine's costs
MS_DAY = 86_400_000


def calendar() -> list[str]:
    import l2sim as S
    return [d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)]


def synthetic(dates: list[str], k: int, p: float, seed: int) -> list[dict]:
    """k coin flips a day at 1 NQ, spread 09:35 .. 15:00, wins at p."""
    rng = random.Random(seed)
    out = []
    for d in dates:
        day_ms = int(dt.datetime.fromisoformat(d + "T09:35:00").timestamp() * 1000)
        for i in range(k):
            w = rng.random() < p
            out.append({"date": d, "entry_ms": day_ms + i * (325 * 60_000 // max(k, 1)), "net": WIN if w else LOSS,
                        "mae_usd": 60.0 if w else 500.0, "side": 1})
    return out


def run(base, r, r_eval, em, fm, fee, split, n, runway, seeds_done) -> dict:
    ev = J.resize(base, em, 1.0)
    fu = J.resize(base, fm, 1.0)
    res = J.fifty(ev, r, n, runway, 5, funded_trades=fu, r_eval=r_eval)
    path, dates = J.days(ev, r_eval)
    fpath = J.days(fu, r)[0]
    span = len(path) - runway
    first = []
    for i in range(n):
        s = round(i * span / n)
        e = E.run_eval(path[s:], r_eval)
        if e["outcome"] != "pass":
            continue
        f = J.funded(fpath[s + e["day"]:], r, 5)
        if f["cheques"]:
            first.append(e["day"] + f["cheques"][0][0])
    net = (res["gross_payouts"] * split - fee * n) / n
    return {"net": net, "pass": res["passed"] / n, "paid": res["paid"] / n, "payouts": res["payouts"] / n,
            "first": st.median(first) if first else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", default="lucid-flex-25k-dll@2026-10-19")
    ap.add_argument("--fee", type=float, default=45.0)
    ap.add_argument("--micros", default="2,4,6,8,10,12,16,20")
    ap.add_argument("--per-day", default="1,2,4,8,12")
    ap.add_argument("--funded", default="2,5,10")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--p", type=float, default=0.40)
    ap.add_argument("--eval-dll", default=None)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--runway", type=int, default=120)
    ap.add_argument("--split", type=float, default=0.9)
    a = ap.parse_args(argv)
    r = P.load_rules(a.rules)
    r_eval = {**r, "daily_loss_limit": None if a.eval_dll and a.eval_dll.lower() == "none" else float(a.eval_dll)} if a.eval_dll else r
    dates = calendar()
    micros = [int(x) for x in a.micros.split(",")]
    per_day = [int(x) for x in a.per_day.split(",")]
    funded = [int(x) for x in a.funded.split(",")]
    print(f"{r['name']} ({a.rules}); fee ${a.fee:.0f}; a {100 * a.p:.0f} % coin flip at 1:1.5 (25 / 38 on 1 NQ after costs); {a.seeds} seeds; "
          f"50 accounts on real build days; eval micros (rows) x trades a day (columns); each cell = the best funded size of {funded}")
    print("cell: net per eval | net per eval per 30 trading days (speed) | pass % / paid % | median trading days to the first payout | funded micros")
    best = []
    for em in micros:
        row = []
        for k in per_day:
            cells = []
            for fm in funded:
                acc = []
                for seed in range(a.seeds):
                    base = synthetic(dates, k, a.p, seed * 1000 + k)
                    acc.append(run(base, r, r_eval, em, fm, a.fee, a.split, a.n, a.runway, None))
                net = st.mean(x["net"] for x in acc)
                firsts = [x["first"] for x in acc if x["first"] is not None]
                first = st.median(firsts) if firsts else None
                cells.append({"fm": fm, "net": net, "pass": st.mean(x["pass"] for x in acc), "paid": st.mean(x["paid"] for x in acc),
                              "first": first, "speed": net / (first / 30.0) if first else None})
            c = max(cells, key=lambda x: x["net"])
            row.append(c)
            best.append((em, k, c))
        def fmt(k, c):
            sp = "n/a" if c["speed"] is None else "$%s" % format(round(c["speed"]), ",")
            fd = "-" if c["first"] is None else "%dd" % round(c["first"])
            return "%2d/day $%5s (%s/mo) %3.0f/%3.0f%% %s f%d" % (k, format(round(c["net"]), ","), sp, 100 * c["pass"], 100 * c["paid"], fd, c["fm"])
        print("eval %2d micros ($%4s risk): " % (em, format(em * 50, ",")) + " | ".join(fmt(k, c) for k, c in zip(per_day, row)))
    top = sorted([b for b in best if b[2]["speed"] is not None], key=lambda b: -b[2]["speed"])[:5]
    print("\nFASTEST (net per eval per 30 trading days):")
    for em, k, c in top:
        print("  eval %d micros ($%s a trade), %d trades a day, funded %d micros: $%s per eval, $%s per eval per month, first payout after %d trading days, pass %.0f %%, paid %.0f %%"
              % (em, format(em * 50, ","), k, c["fm"], format(round(c["net"]), ","), format(round(c["speed"]), ","), round(c["first"]), 100 * c["pass"], 100 * c["paid"]))
    top2 = sorted(best, key=lambda b: -b[2]["net"])[:3]
    print("MOST PER EVAL (ignoring time):")
    for em, k, c in top2:
        print("  eval %d micros, %d trades a day, funded %d micros: $%s per eval, pass %.0f %%, paid %.0f %%, first payout %s"
              % (em, k, c["fm"], format(round(c["net"]), ","), 100 * c["pass"], 100 * c["paid"], "-" if c["first"] is None else "%dd" % round(c["first"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
