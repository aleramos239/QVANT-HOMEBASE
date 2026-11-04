"""CPI/NFP days, two accounts: buy stop 15 pts above / sell stop 15 pts below the 08:29:59 print (vs market at 08:29:59).
2 NQ, 50-pt stop, in-sample. '≥1 hits TP' = either account closed at its full target that day."""
import json, sys, warnings; warnings.filterwarnings("ignore")
import pandas as pd
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P
import news_pair as N

OFFS = {15: {"1:1.5": ("170103", "0b2c", "00be"), "1:2": ("170103", "c45a", "caed"), "1:3": ("170103", "5d2f", "b2b9"), "1:4": ("170103", "f6b1", "85a1")},
        10: {"1:1.5": ("172210", "f070", "1465"), "1:2": ("172210", "89b7", "ea26"), "1:3": ("172212", "76ef", "deb7"), "1:4": ("172212", "4b03", "c892")},
        20: {"1:1.5": ("", "04de", "9382"), "1:2": ("", "5acf", "469d"), "1:3": ("", "1eb5", "b593"), "1:4": ("", "012a", "33fe")},
        25: {"1:1.5": ("", "fe8c", "ed84"), "1:2": ("", "902a", "58d1"), "1:3": ("", "6724", "499f"), "1:4": ("", "8b35", "c836")},
        5: {"1:1.5": ("172210", "9a0d", "a174"), "1:2": ("172210", "a34a", "ddcb"), "1:3": ("172210", "238d", "1157"), "1:4": ("172210", "6824", "36ca")}}
days = N.news_pairs()["1:1.5"].index          # all 86 in-sample CPI/NFP days

def side(k, t):
    m = list(P.RUNS.glob(f"20261101-*-draft_nq_news_side-{k}"))
    assert len(m) == 1, (k, m)
    tr = json.load(open(m[0] / "trades.json"))
    return pd.DataFrame({x["date"]: (x["net"], x["exit_reason"] == "tp") for x in tr}, index=["net", "tp"]).T

def stats(L, S):
    df = pd.DataFrame({"l": L.net, "s": S.net, "ltp": L.tp, "stp": S.tp}).reindex(days)
    traded = df.l.notna() | df.s.notna()
    q = df[traded].fillna({"l": 0, "s": 0, "ltp": False, "stp": False})
    c = q.l + q.s; eq = c.cumsum()
    return dict(days=int(traded.sum()), tp=(q.ltp.astype(bool) | q.stp.astype(bool)).mean() * 100, both_tp=(q.ltp.astype(bool) & q.stp.astype(bool)).mean() * 100,
                one=((q.l > 0) | (q.s > 0)).mean() * 100, net=c.sum(), dd=(eq - eq.cummax()).min(),
                sh=_sharpe(list(c)), yrs=f"{int((c.groupby(c.index.str[:4]).sum() > 0).sum())}/{c.index.str[:4].nunique()}", lf=int(df.l.notna().sum()), sf=int(df.s.notna().sum()))

print(f"{len(days)} CPI/NFP days in-sample. Stop ±N = buy stop N pts above / sell stop N pts below the 08:29:59 print.")
for rr in N.NEWS:
    print(f"\n### {rr}\n| Entry | ≥1 hits full TP | Both hit TP | ≥1 wins | Net | Max DD | Sharpe | Green years |\n|---|---|---|---|---|---|---|")
    t, lk, sk = N.NEWS[rr]
    rows = [("Market", side(lk, t), side(sk, t))] + [(f"Stop ±{o}", side(OFFS[o][rr][1], OFFS[o][rr][0]), side(OFFS[o][rr][2], OFFS[o][rr][0])) for o in (5, 10, 15, 20, 25)]
    for lab, L, S in rows:
        r = stats(L, S)
        print(f"| {lab} | {r['tp']:.1f}% | {r['both_tp']:.1f}% | {r['one']:.1f}% | {P.money(r['net'])} | {P.money(r['dd'])} | {r['sh']:.2f} | {r['yrs']} |")
