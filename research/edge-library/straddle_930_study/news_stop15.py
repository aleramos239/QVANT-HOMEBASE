"""CPI/NFP days, two accounts: buy stop 15 pts above / sell stop 15 pts below the 08:29:59 print (vs market at 08:29:59).
2 NQ, 50-pt stop, in-sample. '≥1 hits TP' = either account closed at its full target that day."""
import json, sys, warnings; warnings.filterwarnings("ignore")
import pandas as pd
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P
import news_pair as N

STOP = {"1:1.5": ("0b2c", "00be"), "1:2": ("c45a", "caed"), "1:3": ("5d2f", "b2b9"), "1:4": ("f6b1", "85a1")}
days = N.news_pairs()["1:1.5"].index          # all 86 in-sample CPI/NFP days

def side(k, t):
    tr = json.load(open(P.RUNS / f"20261101-{t}-draft_nq_news_side-{k}/trades.json"))
    return pd.DataFrame({x["date"]: (x["net"], x["exit_reason"] == "tp") for x in tr}, index=["net", "tp"]).T

def stats(L, S):
    df = pd.DataFrame({"l": L.net, "s": S.net, "ltp": L.tp, "stp": S.tp}).reindex(days)
    traded = df.l.notna() | df.s.notna()
    q = df[traded].fillna({"l": 0, "s": 0, "ltp": False, "stp": False})
    c = q.l + q.s; eq = c.cumsum()
    return dict(days=int(traded.sum()), tp=(q.ltp.astype(bool) | q.stp.astype(bool)).mean() * 100, both_tp=(q.ltp.astype(bool) & q.stp.astype(bool)).mean() * 100,
                one=((q.l > 0) | (q.s > 0)).mean() * 100, net=c.sum(), dd=(eq - eq.cummax()).min(),
                sh=_sharpe(list(c)), lf=int(df.l.notna().sum()), sf=int(df.s.notna().sum()))

print(f"{len(days)} CPI/NFP days in-sample\n")
print("| Entry | RR | Days traded | ≥1 hits full TP | Both hit TP | ≥1 wins | Net | Max DD | Sharpe |\n|---|---|---|---|---|---|---|---|---|")
for rr in STOP:
    t, lk, sk = N.NEWS[rr]
    for lab, L, S in [("Stop ±15", side(STOP[rr][0], "170103"), side(STOP[rr][1], "170103")),
                      ("Market", side(lk, t), side(sk, t))]:
        r = stats(L, S)
        print(f"| {lab} | {rr} | {r['days']} | {r['tp']:.1f}% | {r['both_tp']:.1f}% | {r['one']:.1f}% | {P.money(r['net'])} | "
              f"{P.money(r['dd'])} | {r['sh']:.2f} |")
L, S = side("0b2c", "170103"), side("00be", "170103")
print(f"\nStop ±15 fills: buy stop filled {len(L)} days, sell stop {len(S)} days, both {len(L.index.intersection(S.index))}, "
      f"neither {len(days) - len(L.index.union(S.index))}")
