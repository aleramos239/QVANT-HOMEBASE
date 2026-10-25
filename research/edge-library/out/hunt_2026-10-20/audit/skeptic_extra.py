"""Extra skeptic checks (stored data only): R-multiples build vs test days, the sibling fvg_odir unseen read's overlap with this leg's
test-day entries (same gap, same price), and the recent months.
Run: .venv-research/bin/python research/edge-library/out/hunt_2026-10-20/audit/skeptic_extra.py"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

import skeptic_oside_r1 as K

build, test, wf = K.load(K.NAME)
D = K.desk_trades()
risk = {int(t["entry_ms"]): abs(t["entry_price"] - t["sl"]) for t in D}
out = {}

b = build["struct-r1"]
rb = b["net"] / (b["risk"] * 20)
L = test["struct-r1"]
rk = np.array([risk.get(int(e), np.nan) for e in L["entry_ms"]])
rt = L["net"] / (rk * 20)
out["R_per_trade"] = {"build_r1": round(float(np.nanmean(rb)), 3), "test_days_r1": round(float(np.nanmean(rt)), 3),
                      "build_median_stop_usd": round(float(np.median(b["risk"]) * 20)), "test_median_stop_usd": round(float(np.nanmedian(rk) * 20))}

# months of the whole test period, r1 cell, with the R mean
mo = np.array([K.month(d) for d in L["date"]])
out["test_months_r1"] = {m: {"n": int((mo == m).sum()), "net": round(float(L["net"][mo == m].sum())), "R": round(float(np.nanmean(rt[mo == m])), 3)}
                         for m in sorted(set(mo))}
last4 = np.isin(mo, ["2026-05", "2026-06", "2026-07", "2026-08"])
out["last4_whole_months_r1"] = K.stats(L["net"][last4])
oct_nov = np.isin(mo, ["2025-10", "2025-11"])
out["oct_nov_2025_share_of_test_period"] = round(float(L["net"][oct_nov].sum() / L["net"].sum()), 3)

# overlap with the fvg_odir unseen read of 2026-10-19 (19:30 ET), same 1R cell: same fill price within 5 minutes
od = json.loads((K.HOME / "owner_fvg_odir_15_nl_new" / "unseen" / "trades.json").read_text())["struct-r1"]
oside = [(int(e), t) for e, t in ((int(t["entry_ms"]), t) for t in D) if "2025-07-01" <= t["date"] <= "2026-09-22"]
key = {(t["date"], t["side"], t["entry_price"]) for _, t in oside}
same = [t for t in od if (t["date"], t["side"], t["entry_price"]) in key]
out["odir_unseen_overlap"] = {"odir_trades": len(od), "oside_test_trades": len(oside), "same_day_side_price": len(same),
                              "share_of_odir": round(len(same) / len(od), 3), "share_of_oside": round(len(same) / len(oside), 3),
                              "odir_net_r1": round(sum(t["net"] for t in od))}
# what the odir read showed about stop size on 2025-07+ (the finding that came before the 2.5x / 3x sheets)
st = np.array([abs(t["entry_price"] - t["sl"]) for t in od])
nn = np.array([t["net"] for t in od])
out["odir_unseen_by_stop"] = {"stop_lt20": K.stats(nn[st < 20]), "stop_ge20": K.stats(nn[st >= 20]), "stop_ge30": K.stats(nn[st >= 30])}

# store creation times vs the unseen read (local ET mtimes of the sheet stores)
ts = {}
for n in ["owner_fvg_odir_15_nl_new/unseen/claim.json", "owner_fvg_oside_15_a1m2_r1/sheet.json", "owner_fvg_oside_15_a1m2p5_r1/sheet.json",
          "owner_fvg_oside_15_a1m3_r05/sheet.json", "owner_fvg_oside_15_a1m3_r1/sheet.json", "owner_fvg_oside_15_a1m3_nl_r1/sheet.json"]:
    p = K.HOME / n
    ts[n] = dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes") if p.exists() else None
out["timeline_local_mtime"] = ts
print(json.dumps(out, indent=1))
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1))
