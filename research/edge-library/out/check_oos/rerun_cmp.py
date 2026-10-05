"""Compare the from-scratch default re-runs (rerun/*.json) with the analyst's stores, trade for trade."""
import json, glob, datetime as dt
from pathlib import Path
import numpy as np
import chk as C
tot = bad = 0
for f in sorted(glob.glob("rerun/*.json")):
    r = json.load(open(f))
    key = Path(f).stem
    d = "runs_check2025" if r["period"] == "check" else "runs_exam2026"
    rec = [x for x in C.IDX if x["dir"] == d and x["key"] == key]
    assert len(rec) == 1, key
    st = C.load(rec[0])
    for cid, tr in r["trades"].items():
        x = C.cell(st, cid, None if r["timed"] else r["sess"])
        mine = sorted((dt.date.fromisoformat(t["date"]).toordinal(), int(t["entry_ms"]), max(0, (int(t["exit_ms"]) - int(t["entry_ms"])) // 1000), round(float(t["net"]), 2), 1 if t["side"] == "long" else -1) for t in tr)
        theirs = sorted(zip(x["date"].astype(int).tolist(), x["entry_ms"].astype(int).tolist(), x["dur_s"].astype(int).tolist(), np.round(x["net"].astype(float), 2).tolist(), x["side"].astype(int).tolist()))
        same = mine == theirs
        tot += 1; bad += not same
        nm, nt = sum(t[3] for t in mine), sum(t[3] for t in theirs)
        print(("SAME " if same else "DIFF "), key, cid, "trades", len(mine), len(theirs), "net", round(nm, 2), round(nt, 2), "sessions", r["sessions"], "used", r["used"],
              "skipped", r["skipped"] if len(str(r["skipped"])) < 150 else len(r["skipped"]), "store range", rec[0]["start"], rec[0]["end"], "store stress/oco", rec[0]["stress"], rec[0]["oco"])
print("cells compared", tot, "different", bad)
