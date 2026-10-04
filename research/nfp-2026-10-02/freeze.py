"""Freeze <=5 finalists chosen on 2021-24 ONLY, write frozen_finalists.json + .sha256 BEFORE any 2025+ P&L is replayed."""
import hashlib, json, datetime as dt
import pandas as pd
from nfp_lib import *
meta = pd.read_csv(CACHE / "cells_IS.csv", index_col="cell")
sel = pd.read_csv(CACHE / "select_is.csv").set_index("cell")
PICK = {"A_IS_pick_4GC_off2pt_SL1500": 10, "B_plain_4GC_off2pt_SL2000": 19, "C_4GC_off2pt_SL1200": 1,
        "D_4GC_off0.1V_SL1500": 15, "E_volsize_b0.3_off0.1V_SL1500": 274}
out = {"frozen_at_et": dt.datetime.now(ET).isoformat(timespec="seconds"),
       "selection_rule": "IS 2021-10..2024-12 only; score = mean P(win) over slip models M1,P2,P4 pooled NFP+CPI, smoothed over offset neighbours (interior offsets only); cells within 1 SE (0.055) of the top: lowest P2 bust, then highest smoothed score. A = winner of that rule.",
       "holdout_decision_rule": "Recommend A unless another finalist has holdout P(win) under model P2 (NFP+CPI pooled) higher by >= 0.15, in which case report it as a post-holdout choice. Holdout = 2025-01..2026-09, ONE scoring run of these 5 cells, no re-tune.",
       "finalists": []}
for name, ci in PICK.items():
    c = {k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)) for k, v in meta.loc[ci].to_dict().items()}
    c["name"] = name; c["is_cell"] = ci
    c["is_smooth"] = float(sel.loc[ci, "smooth"]) if ci in sel.index else None
    out["finalists"].append(c)
txt = json.dumps(out, indent=1, sort_keys=True)
(HERE / "frozen_finalists.json").write_text(txt)
h = hashlib.sha256(txt.encode()).hexdigest()
(HERE / "frozen_finalists.sha256").write_text(h + "  frozen_finalists.json\n")
print(h); print(txt[:1500])
