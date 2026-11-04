"""Test-month check for one disp-follow box: t, by year, worse fills, and the MFF Builder 50K $1,500 funded replay
(no 50 % consistency rule; one account at a time, the day's first trade only). Usage: funded_check.py trades.json [...]"""
import json, math, sys
from collections import defaultdict

def load(paths):
    out = []
    for p in paths:
        t = json.load(open(p)); out += t if isinstance(t, list) else t.get("trades", [])
    return sorted(out, key=lambda x: x["entry_ms"])

def stats(t):
    n = [x["net"] for x in t]; m = sum(n) / len(n); sd = (sum((v - m) ** 2 for v in n) / (len(n) - 1)) ** .5
    yrs = defaultdict(float)
    for x in t: yrs[x["date"][:4]] += x["net"]
    return dict(trades=len(n), net=round(sum(n)), t=round(m / sd * len(n) ** .5, 2),
                worse_fills=round(sum(n) - 10 * len(n) * t[0]["qty"]),   # 1 more tick each side
                years={k: round(v) for k, v in sorted(yrs.items())})

def funded(t, DD=1500, LOCK=100, DLL=1000, BUF=1600, STEP=500, CAP=2000):
    days = {}
    for x in t: days.setdefault(x["date"], x)          # first trade of the day
    accts, cur = [], None
    for d, x in sorted(days.items()):
        if cur is None:
            cur = dict(bal=0.0, peak=0.0, pays=0, paid=0.0, days=0, cyc=0, base=BUF)
        a = cur; floor = min(a["peak"] - DD, LOCK); room = a["bal"] - floor
        worst = max(x["mae_usd"], -x["net"])
        a["days"] += 1; a["cyc"] += 1
        if worst >= room:                               # breach on the worst open loss
            accts.append(a); cur = None; continue
        net = -DLL - x["commission"] if worst >= DLL else x["net"]   # soft daily pause flattens at -$1,000 open
        a["bal"] += net; a["peak"] = max(a["peak"], a["bal"])
        if a["bal"] >= a["base"] + STEP and a["cyc"] >= 2:
            amt = min(CAP, a["bal"] - BUF); a["bal"] -= amt; a["paid"] += .8 * amt; a["pays"] += 1
            a["base"] = a["bal"]; a["cyc"] = 0
            if a["pays"] >= 5: accts.append(a); cur = None
    if cur: accts.append(cur)
    k = len(accts)
    return dict(accounts=k, first_payout=round(100 * sum(a["pays"] >= 1 for a in accts) / k, 1),
                two_plus=round(100 * sum(a["pays"] >= 2 for a in accts) / k, 1),
                per_account=round(sum(a["paid"] for a in accts) / k), days_per_account=round(sum(a["days"] for a in accts) / k, 1))

if __name__ == "__main__":
    t = load(sys.argv[1:]); print(stats(t)); print(funded(t))
