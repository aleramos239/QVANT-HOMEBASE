"""Aggregate a grid_<part>.csv.gz into per-cell x model x set metrics (P pass / bust / survive, multi-event passes)."""
import sys
import numpy as np, pandas as pd
from nfp_lib import *

def summarize(part="IS", tag="", horizon=4):
    g = pd.read_csv(CACHE / f"grid_{part}{tag}.csv.gz")
    meta = pd.read_csv(CACHE / f"cells_{part}{tag}.csv", index_col="cell")
    rows = []
    for (ci, mn), h in g.groupby(["cell", "model"]):
        h = h.sort_values("date").reset_index(drop=True)
        tpu = meta.loc[ci, "tp_usd"]
        nets = h.net.to_numpy()
        for setname, mask in (("NFP", h.event == "NFP"), ("CPI", h.event == "CPI"), ("ALL", h.event.notna())):
            m = mask.to_numpy()
            n = int(m.sum())
            if n == 0:
                continue
            x = nets[m]
            win = int((x >= tpu - 0.01).sum()); bust = int((x <= -2000).sum())
            # one-event pass (what tomorrow is): a one-shot target needs 1 win, the 2-event alternative needs 2
            p1 = win / n if tpu >= 3000 else 0.0
            # consecutive-event eval: start an eval at every event of the set, run through the next `horizon` events
            idx = np.flatnonzero(m)
            res = [eval_run(nets[i:i + horizon]) [0] for i in idx]
            lo, hi = wilson(win, n)
            rows.append(dict(cell=ci, model=mn, set=setname, n=n, filled=int((h.why[m] != "NOFILL").sum()),
                             win=win, p_win=win / n, p_win_lo=lo, p_win_hi=hi, p_bust1=bust / n,
                             p_pass1=p1, p_pass_h=np.mean([r == "pass" for r in res]),
                             p_bust_h=np.mean([r == "bust" for r in res]),
                             mean_net=float(x.mean()), sum_net=float(x.sum()), worst=float(x.min())))
    s = pd.DataFrame(rows).merge(meta.reset_index(), on="cell")
    return s

if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "IS"
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    s = summarize(part, tag); s.to_csv(CACHE / f"summary_{part}{tag}.csv", index=False); print(len(s))
