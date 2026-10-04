import numpy as np, pandas as pd
from v2 import *
r = run(2.0, 3.7, 7.6, 4.6, e_slip=1, s_slip=1, cancel_ms=1000)
print(r[r.dbl][["date","out","net","side","t_e_ms","hold_s","mae_usd"]])
r0 = run(2.0, 3.7, 7.6, 4.6, e_slip=1, s_slip=1, cancel_ms=50)
print(r0[r0.dbl][["date","out","net","side","t_e_ms","hold_s"]])
# entry time distribution
print((r.t_e_ms).describe())
print("entry within 300ms of release:", int((r.t_e_ms < 300).sum()), "of", len(r))
print("entry gap vs trigger (pts beyond anchor+-2):")
r["gap"] = np.abs(r.fill - r.anchor) - 2.0 - 0.1
print(r.gap.describe())
