"""2025 (CHECK) tape coverage per market: sessions, missing weekdays, print counts, gaps. Reads 2025 tapes only (allow_check)."""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402

out = {}
for root in ("NQ", "ES", "GC"):
    days = S.sessions(*S.CHECK, root, allow_check=True)
    wk = [S.CHECK[0] + dt.timedelta(n) for n in range(365) if (S.CHECK[0] + dt.timedelta(n)).weekday() < 5]
    missing = [d.isoformat() for d in wk if d not in set(days)]
    n, no_tape, late_start, early_end, rth_gap, contracts = [], [], [], [], [], []
    for d in days:
        t = S.load_tape(d, root, allow_check=True)
        if t is None or not len(t.ts):
            no_tape.append(d.isoformat())
            continue
        n.append(len(t.ts))
        contracts.append(t.contract)
        first = dt.datetime.fromtimestamp(int(t.ts[0]) / 1e9, S.ET)
        last = dt.datetime.fromtimestamp(int(t.ts[-1]) / 1e9, S.ET)
        eve = dt.datetime.combine(d - dt.timedelta(days=1), dt.time(18, 0), S.ET)
        if (first - eve).total_seconds() > 600 and (d - dt.timedelta(days=1)).weekday() != 5:      # Monday's file starts Sunday 18:00
            late_start.append((d.isoformat(), first.strftime("%m-%d %H:%M")))
        if last.date() == d and last.hour < 16:
            early_end.append((d.isoformat(), last.strftime("%H:%M")))
        a, b = S.et_ns(d, "09:30"), S.et_ns(d, "16:00")
        lo, hi = np.searchsorted(t.ts, a), np.searchsorted(t.ts, b)
        if hi - lo < 2:
            rth_gap.append((d.isoformat(), "no RTH prints"))
        else:
            g = float(np.diff(t.ts[lo:hi]).max()) / 1e9
            if g > 300 and not (last.date() == d and last.hour < 16):
                rth_gap.append((d.isoformat(), f"{g:.0f} s"))
    assert all(d.year == 2025 for d in days)
    out[root] = {"sessions": len(days), "with_tape": len(n), "no_tape": no_tape, "weekdays_without_session": missing,
                 "prints_min": int(min(n)), "prints_median": int(np.median(n)), "prints_max": int(max(n)),
                 "thin_sessions(<25% of median)": int(sum(x < 0.25 * np.median(n) for x in n)), "late_start": late_start,
                 "early_end(before 16:00 ET)": early_end, "rth_gap_over_5min": rth_gap, "front_contracts": sorted(set(contracts)),
                 "first": days[0].isoformat(), "last": days[-1].isoformat()}
    print(root, json.dumps(out[root]), flush=True)
(W / "out" / "check2025" / "coverage_2025.json").write_text(json.dumps(out, indent=1))
