import numpy as np, pandas as pd
from pathlib import Path
W = Path(__file__).resolve().parents[3]
B = [("nq_b089_ib_break", "ib_min30_pts15-r0p5"), ("nq_b089_ib_break", "ib_min30_pts60-r2"), ("nq_b089_ib_break", "ib_min30_pts60-r1p5"),
     ("nq_b041_london_kz_bracket", "r_end0400_pts25-r0p75"), ("nq_b041_london_kz_bracket", "r_end0400_pts40-r0p5")]
DAYS = {"IS": 947, "OOS": 309}
def load(D, cell):
    z = np.load(D / "cells.npz"); t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    i = int(t.index[t.cell == cell][0]); s = slice(z["off"][i], z["off"][i + 1])
    return pd.DataFrame({"day": pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize(), "net": z["net"][s], "side": z["side"][s]})
def m(df, d):
    n = df.net; w, l = n[n > 0], n[n <= 0]; ds = df.groupby("day").net.sum(); eq = ds.cumsum()
    yrs = df.groupby(df.day.dt.year).net.sum()
    return dict(trades=len(n), per_wk=len(n) / (d / 5), win=f"{(n > 0).mean() * 100:.0f}%", rr=w.mean() / abs(l.mean()), avg=n.mean(), net=n.sum(), perwk=n.sum() / (d / 5),
                pf=w.sum() / abs(l.sum()), sharpe=ds.mean() / ds.std() * np.sqrt(252), t=n.mean() / (n.std(ddof=1) / np.sqrt(len(n))), maxdd=(eq - eq.cummax()).min(),
                yrs=" ".join(f"{y % 100}:{v / 1000:+.1f}k" for y, v in yrs.items()))
for st, cell in B:
    a = load(W / f"runs_wf/{st}-NQ-tf5/is", cell); o = load(W / f"runs_wf/{st}-NQ-tf5__{cell}/oos", cell)
    print(f"\n{st} {cell}")
    r = {"in-sample": m(a, 947), "test months": m(o, 309)}
    print(pd.DataFrame(r).to_string(float_format=lambda x: f"{x:,.2f}"))
