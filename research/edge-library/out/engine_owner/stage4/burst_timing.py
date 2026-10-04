#!/usr/bin/env python3
"""COUNTS ONLY (no price, no P&L): where the release burst sits on the TAPE clock. For every BUILD calendar day at 08:30
(tier-1: NFP, CPI, PPI, RETAIL, GDP, PCE) and 10:00 ET: the number of prints per bucket after the release second, and the
offset of the busiest 250 ms bucket in [-5 s, +10 s]. -> burst_timing.json + a few lines."""
import csv, json, sys, datetime as dt
from pathlib import Path
import numpy as np
W = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(W / "engine"))
import l2sim as S
rows = list(csv.DictReader(open(W / "engine" / "cache" / "events.csv")))
out = {}
edges = [0, 0.25, 0.5, 1, 2, 5, 15, 60]
for root in ("NQ", "GC", "ES"):
    for at, types in (("08:30", {"NFP", "CPI", "PPI", "RETAIL", "GDP", "PCE"}), ("10:00", None)):
        days = sorted({r["date"] for r in rows if r.get("time_et", r.get("time", ""))[:5] == at
                       and (types is None or r.get("type") in types) and "2021-09-22" <= r["date"] <= "2023-12-31"})
        peak, counts, first1 = [], [], []
        for iso in days:
            d = dt.date.fromisoformat(iso)
            tp = S.load_tape(d, root)
            if tp is None:
                continue
            t0 = S.et_ns(d, at)
            ts = tp.ts
            b = np.arange(-20, 41) * 250_000_000 + t0                 # 250 ms buckets, -5 s .. +10 s
            c = np.diff(np.searchsorted(ts, b))
            peak.append(float((int(np.argmax(c)) - 20) * 0.25))
            e = np.searchsorted(ts, [t0 + int(x * 1e9) for x in edges])
            counts.append([int(v) for v in np.diff(e)])
            first1.append(int(e[3] - e[0]))                           # prints in the first second
        pk = np.array(peak); cn = np.array(counts)
        out[f"{root}_{at}"] = {"days": len(pk), "peak_bucket_start_s": {"p10": float(np.percentile(pk, 10)), "median": float(np.median(pk)),
                               "p90": float(np.percentile(pk, 90))},
                               "share_peak_before_0s": float((pk < 0).mean()), "share_peak_in_0_to_0p5s": float(((pk >= 0) & (pk < 0.5)).mean()),
                               "share_peak_in_0p5_to_1s": float(((pk >= 0.5) & (pk < 1)).mean()), "share_peak_in_1_to_2s": float(((pk >= 1) & (pk < 2)).mean()),
                               "share_peak_at_2s_or_later": float((pk >= 2).mean()),
                               "median_prints_per_bucket": dict(zip(["0-0.25", "0.25-0.5", "0.5-1", "1-2", "2-5", "5-15", "15-60"], [float(v) for v in np.median(cn, axis=0)])),
                               "share_days_no_print_first_0p25s": float((cn[:, 0] == 0).mean()), "share_days_no_print_first_1s": float((cn[:, :3].sum(axis=1) == 0).mean())}
        print(root, at, json.dumps(out[f"{root}_{at}"]), flush=True)
(Path(__file__).parent / "burst_timing.json").write_text(json.dumps(out, indent=1))
