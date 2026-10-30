"""Box nq_b018_pd_bracket_on off_min15 pts40-r0p75: engine trades split into the day's FIRST trade (= the Desk port, parity 605/605, $20,360) and the EXTRA trades
(re-entries and stacked entries the engine allowed). Saved trades only, IS + test months. Run: .venv-research/bin/python first_only.py"""
src = open("mc8.py").read(); exec(src[:src.index("rows = []")])
import numpy as np, pandas as pd
def load2(D, cell):
    z = np.load(D / "cells.npz"); t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    i = int(t.index[t.cell == cell][0]); s = slice(z["off"][i], z["off"][i + 1])
    e = pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None)
    return pd.DataFrame({"t": e, "day": e.normalize(), "net": z["net"][s]}).sort_values("t")
cell = "off_min15_pts40-r0p75"; st = "nq_b018_pd_bracket_on"
I = load2(W / f"runs_wf/{st}-NQ-tf5/is", cell); O = load2(W / f"runs_wf/{st}-NQ-tf5__{cell}/oos", cell)
for nm, df in (("in-sample", I), ("test months", O), ("all months", pd.concat([I, O]))):
    f = df.drop_duplicates("day"); x = df[df.duplicated("day")]
    print(f"{nm:12s} first-trade: n {len(f)} net {f.net.sum():9.0f}   extras: n {len(x)} net {x.net.sum():8.0f}")
A = pd.concat([I, O]).drop_duplicates("day"); Ofirst = O.drop_duplicates("day"); Ifirst = I.drop_duplicates("day")
A["yr"] = A.day.dt.year; A["mo"] = A.day.dt.to_period("M")
for nm, d in (("ALL first-trade", A), ("in-sample", Ifirst), ("test months", Ofirst)):
    r = read(d); print(nm, {k: round(v, 3) for k, v in r.items()})
yrs = A.groupby("yr").net.sum(); mos = A.groupby("mo").net.sum().sort_values(ascending=False)
print("years", {int(k): round(float(v)) for k, v in yrs.items()}, "top-year share", round(float(yrs.max() / A.net.sum()), 2))
print("w/o 3 best months", float(A.net.sum() - mos.head(3).sum()), "| $10 worse fills", float((A.net - 10).sum()))
