"""Read-only: how taught-lane strategies combine on ONE account (build days only; reads stored trades, runs nothing).

usage: combo.py NAME[:CELL] NAME[:CELL] ...   (CELL defaults to the sheet's centre cell)
Prints each strategy alone, the daily-P&L correlation matrix, and the stack (all trades added, 1 contract each):
trades a day, avg trade, net, PF, Sharpe (daily incl. $0 days, sqrt 252), months won, worst drawdown (closed daily), per year.
shortcut: drawdown here is on closed daily P&L, not open losses; the taught lane's own 'DD open' column is the stricter number.
"""
import sys, json, os, datetime as dt
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import library as L

T = os.path.expanduser("~/.homebase/taught")


def load(spec):
    name, _, cell = spec.partition(":")
    res = json.load(open(f"{T}/{name}/result.json"))
    market = res["plan"]["market"]
    tf = res["plan"]["bars"][0]
    if not cell:
        cell = next(c["id"] for c in res["plan"]["cells"] if c["centre"])
    u = L.load_unit(f"{name}-{market}-tf{tf}", f"{T}/{name}/runs")
    x = L.unit_cell(u, cell)
    return name + ":" + cell, x


def daily(x, days):
    d = np.zeros(len(days))
    idx = {v: i for i, v in enumerate(days)}
    for dd, n in zip(x["date"], x["net"]):
        d[idx[int(dd)]] += n
    return d


def stats(net, d, days):
    net = np.asarray(net, float)
    cum = np.cumsum(d)
    dd = float((np.maximum.accumulate(np.concatenate(([0.0], cum))) - np.concatenate(([0.0], cum))).max())
    w, l = net[net > 0].sum(), -net[net < 0].sum()
    ym = np.array([dt.date.fromordinal(int(v)).year * 100 + dt.date.fromordinal(int(v)).month for v in days])
    mu = np.unique(ym)
    mon = np.array([d[ym == m].sum() for m in mu])
    yrs = {}
    for y in sorted({m // 100 for m in mu}):
        yrs[y] = round(float(d[(ym // 100) == y].sum()))
    sh = float(d.mean() / d.std() * np.sqrt(252)) if d.std() > 0 else 0.0
    return dict(trades=len(net), per_day=round(len(net) / len(days), 2), avg=round(float(net.mean()), 1) if len(net) else 0,
                net=round(float(net.sum())), pf=round(float(w / l), 3) if l else None, win=round(float((net > 0).mean()), 3),
                sharpe=round(sh, 2), months_won=round(float((mon > 0).mean()), 3), dd=round(dd), net_dd=round(float(net.sum()) / dd, 2) if dd else None,
                years=yrs)


def main(specs):
    xs = [load(s) for s in specs]
    days = sorted({int(v) for _, x in xs for v in x["date"]})
    # the session calendar: every build-day session any of them could trade (union of trade dates is a floor; use the engine's calendar)
    try:
        import l2sim as S
        cal = [d.toordinal() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)]
        days = sorted(set(cal) | set(days))
    except Exception as e:
        print("calendar fallback (trade dates only):", e)
    D = {}
    for name, x in xs:
        D[name] = daily(x, days)
        print(f"{name:55s}", stats(x["net"], D[name], days))
    names = list(D)
    if len(names) > 1:
        M = np.corrcoef(np.vstack([D[n] for n in names]))
        print("\ndaily P&L correlation")
        for i, n in enumerate(names):
            print(f"  {n[:45]:45s}", " ".join(f"{M[i, j]:+.2f}" for j in range(len(names))))
        allnet = np.concatenate([x["net"] for _, x in xs])
        tot = sum(D.values())
        print("\nSTACK (all, 1 contract each):", stats(allnet, tot, days))


if __name__ == "__main__":
    main(sys.argv[1:])
