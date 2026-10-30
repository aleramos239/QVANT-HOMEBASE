"""In-sample + test months combined, the 8 highlighted fixed-stop boxes (2026-10-29). Saved trades only, no new month read."""
import numpy as np, pandas as pd
from pathlib import Path
W = Path(__file__).resolve().parents[3]
B = [("nq_b018_pd_bracket_on", "off_min15_pts25-r1p5"), ("nq_b018_pd_bracket_on", "off_min15_pts40-r0p75"), ("nq_b018_pd_bracket_on", "off_min15_pts60-r0p5"), ("nq_b018_pd_bracket_on", "off_min15_pts60-r0p75"),
     ("nq_b089_ib_break", "ib_min30_pts15-r0p5"), ("nq_b089_ib_break", "ib_min30_pts40-r0p5"), ("nq_b089_ib_break", "ib_min30_pts60-r0p5"), ("nq_b089_ib_break", "ib_min30_pts60-r1")]
WEEKS = (947 + 309) / 5
def load(D, cell):
    z = np.load(D / "cells.npz"); t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
    i = int(t.index[t.cell == cell][0]); s = slice(z["off"][i], z["off"][i + 1])
    return pd.DataFrame({"day": pd.to_datetime(z["entry_ms"][s], unit="ms", utc=True).tz_convert("America/New_York").tz_localize(None).normalize(), "net": z["net"][s]})
rows = []
for st, cell in B:
    a = pd.concat([load(W / f"runs_wf/{st}-NQ-tf5/is", cell), load(W / f"runs_wf/{st}-NQ-tf5__{cell}/oos", cell)]).sort_values("day")
    n = a.net; w, l = n[n > 0], n[n <= 0]; ds = a.groupby("day").net.sum(); eq = ds.cumsum(); yr = a.groupby(a.day.dt.year).net.sum()
    m = re = None
    rows.append({"Box": f'{st.split("_", 2)[2]} {cell.split("_pts")[0]} {cell.split("_pts")[1].split("-r")[0]} pts / {cell.split("-r")[1].replace("p", ".")} R', "Trades": len(n), "Win": f"{(n > 0).mean() * 100:.0f}%", "RR": round(w.mean() / abs(l.mean()), 2),
        "Avg $": round(n.mean()), "Net $": round(n.sum()), "$/wk": round(n.sum() / WEEKS), "PF": round(w.sum() / abs(l.sum()), 2), "Sharpe": round(ds.mean() / ds.std() * np.sqrt(252), 2),
        "t": round(n.mean() / (n.std(ddof=1) / np.sqrt(len(n))), 2), "Max DD $": round((eq - eq.cummax()).min()), "Yrs green": f"{(yr > 0).sum()}/{len(yr)}", "Best yr share": f"{yr.max() / n.sum() * 100:.0f}%"})
d = pd.DataFrame(rows); d.to_csv(Path(__file__).with_name("combined8.csv"), index=False)
print(d.to_string(index=False))
