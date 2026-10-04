"""Stage 2: IS-only ranking of the GC one-shot cells (declared rule, see results.md).
score = mean over slip models {M1,P2,P4} of P(win this event), pooled NFP+CPI 2021-10..2024-12 (first 4 events = vol warm-up dropped),
smoothed over the cell and its offset neighbours (same size/stop/offset-mode) so a lone spike cannot win."""
import numpy as np, pandas as pd
from nfp_lib import *
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200)
s = pd.read_csv(CACHE / "summary_IS.csv")
g = s[(s.root == "GC") & (s.tp_usd == 3000) & (s.set == "ALL")].copy()
key = ["arm", "unit", "offmode", "sl_usd"]
rows = []
for k, h in g.groupby(key):
    offs = sorted(h.off.unique())
    sc = h[h.model.isin(["M1", "P2", "P4"])].groupby("off").p_win.mean()
    bust = h[h.model == "P2"].set_index("off").p_bust1
    ph = h[h.model == "P2"].set_index("off").p_pass_h
    for i, o in enumerate(offs):
        if i in (0, len(offs) - 1):
            continue          # interior offsets only: a cell needs both neighbours to be smoothed
        nb = [offs[j] for j in (i - 1, i, i + 1) if 0 <= j < len(offs)]
        rows.append(dict(zip(key, k), off=o, score=sc[o], smooth=float(np.mean([sc[x] for x in nb])),
                         p2_bust1=bust[o], p2_pass4=ph[o], cell=int(h[(h.off == o)].cell.iloc[0])))
r = pd.DataFrame(rows).sort_values("smooth", ascending=False)
r.to_csv(CACHE / "select_is.csv", index=False)
print(r.head(25).round(3).to_string(index=False))
print(); print("best per arm/offmode/SL:")
print(r.groupby(["arm", "offmode", "sl_usd"]).head(1).sort_values("smooth", ascending=False).round(3).to_string(index=False))
