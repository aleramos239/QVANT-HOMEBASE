"""Timestamp-law evidence: is a depth.bin row stamped minute M the book at the START or the END of M?

For random in-sample minutes (seeded; roll-block sessions excluded) compare the row's best bid/ask with the
ofb_tick tape: distance (points) of the last print before / first print at-or-after ``M + tau`` to the quoted
interval [bid, ask] (0 when the print is inside it). The tau that minimises the distance is the snapshot instant.
Also: hist.bin best == depth.bin best, and ofb_tick's ``prev_best_*`` (its lag convention) == the row stamped
``flow_t``. In-sample only (sessions < 2025-01-01). Single process, ~1 min. Writes out/ts_law.json.

    python ts_law.py
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

import l2data as D

OFB_TICK = D.OFB_TICK_DIR
SEED = 20261001
DAYS_PER_YEAR, RTH_PER_DAY, OVN_PER_DAY = 40, 60, 30
COARSE = np.arange(-60, 121, 5).astype(float)
FINE = np.round(np.arange(58.0, 61.0001, 0.05), 2)


def _dist(p, bid, ask):
    return np.maximum(np.maximum(bid - p, p - ask), 0.0)


def main():
    rng = np.random.default_rng(SEED)
    rolls, sessions = D.roll_days()
    block = D.roll_block_dates(rolls, sessions)
    depth = D.BinFile(D.ofb_files("depth")[0], "depth")
    hist = D.BinFile(D.ofb_files("hist")[0], "hist")
    offs = np.concatenate([COARSE, FINE])
    offs_ns = (offs * 1e9).astype(np.int64)
    acc = {}                                              # (year, group) -> sums
    table, h2h = [], []
    hist_eq = [0, 0]
    prev_eq = [0, 0]
    for year in (2021, 2022, 2023, 2024):
        days = sorted(d for d in sessions if d.year == year and D.IS_START <= d <= D.IS_END and d not in block)
        days = [d for d in days if (OFB_TICK / f"{d:%Y}" / f"{d:%m}" / f"{d:%Y-%m-%d}.parquet").exists()]
        for d in sorted(rng.choice(np.array(days, dtype=object), DAYS_PER_YEAR, replace=False)):
            tk = pd.read_parquet(OFB_TICK / f"{d:%Y}" / f"{d:%m}" / f"{d:%Y-%m-%d}.parquet",
                                 columns=["ts_ns", "price", "flow_t", "prev_best_bid", "prev_best_ask"])
            ts, px = tk["ts_ns"].to_numpy(), tk["price"].to_numpy()
            for grp, m0, m1, n in (("rth", 9 * 60 + 31, 15 * 60 + 58, RTH_PER_DAY), ("ovn", 120, 480, OVN_PER_DAY)):
                for mod in sorted(rng.choice(np.arange(m0, m1), n, replace=False)):
                    key = (d.year * 10000 + d.month * 100 + d.day) * 10**6 + (mod // 60) * 10000 + (mod % 60) * 100
                    i = depth._bisect(key)
                    row = depth.row(i)                    # guarded accessor: sealed rows raise
                    assert int(row["key"]) == key
                    bid, ask = float(row["bid"][0, 0]), float(row["ask"][0, 0])
                    if not (0 < bid < ask):
                        continue
                    hrow = hist.row(i)
                    assert int(hrow["key"]) == key
                    hist_eq[0] += int(abs(hrow["s"][0] - bid) < 1e-6 and abs(hrow["s"][1] - ask) < 1e-6)
                    hist_eq[1] += 1
                    m_utc = int(D.key_to_utc([key])[0])
                    j = np.searchsorted(ts, m_utc * 10**9 + offs_ns, side="left")
                    ok = (j > 0) & (j < len(ts))
                    if not ok.all():
                        continue
                    before, after = _dist(px[j - 1], bid, ask), _dist(px[j], bid, ask)
                    a = acc.setdefault((year, grp), [0, np.zeros(len(offs)), np.zeros(len(offs)),
                                                    np.zeros(len(offs)), np.zeros(len(offs))])
                    a[0] += 1
                    a[1] += before
                    a[2] += after
                    a[3] += before == 0
                    a[4] += after == 0
                    k0, k60 = int(np.flatnonzero(offs == 0.0)[0]), int(np.flatnonzero(offs == 60.0)[0])
                    h2h.append((year, grp, before[k0], before[k60]))
                    # ofb_tick lag convention: ticks of minute M+1 carry flow_t == M with this row's best bid/ask
                    sel = tk["flow_t"].to_numpy() == m_utc
                    if sel.any():
                        pb, pa = tk["prev_best_bid"].to_numpy()[sel][0], tk["prev_best_ask"].to_numpy()[sel][0]
                        if pb == pb:
                            prev_eq[0] += int(abs(pb - bid) < 1e-6 and abs(pa - ask) < 1e-6)
                            prev_eq[1] += 1
                    if grp == "rth" and len([r for r in table if r["key"] // 10**10 == year]) < 6 and rng.random() < 0.02:
                        table.append({"key": int(key), "bid": bid, "ask": ask,
                                      "last_before_M": float(px[j[k0] - 1]), "first_after_M": float(px[j[k0]]),
                                      "last_before_M+60": float(px[j[k60] - 1]), "first_after_M+60": float(px[j[k60]]),
                                      "d_start": float(before[k0]), "d_end": float(before[k60])})
    nc = len(COARSE)

    def curves(keys):
        n = sum(acc[k][0] for k in keys)
        s = [sum(acc[k][i] for k in keys) / n for i in (1, 2, 3, 4)]
        fb, fa = s[0][nc:], s[1][nc:]
        return {
            "n_minutes": int(n),
            "coarse_last_before": {f"{int(o):+d}s": round(float(v), 4) for o, v in zip(COARSE, s[0][:nc])},
            "fine_last_before": {f"{o:.2f}": round(float(v), 4) for o, v in zip(FINE, fb)},
            "fine_first_after": {f"{o:.2f}": round(float(v), 4) for o, v in zip(FINE, fa)},
            "argmin_last_before_s": float(FINE[fb.argmin()]), "argmin_first_after_s": float(FINE[fa.argmin()]),
            "min_last_before_pts": round(float(fb.min()), 4), "min_first_after_pts": round(float(fa.min()), 4),
            "share_inside_last_before": {"M+0": round(float(s[2][np.flatnonzero(offs == 0.0)[0]]), 4),
                                         "M+59.3": round(float(s[2][nc + int(np.flatnonzero(FINE == 59.3)[0])]), 4),
                                         "M+60": round(float(s[2][np.flatnonzero(offs == 60.0)[0]]), 4)},
            "share_inside_first_after": {"M+0": round(float(s[3][np.flatnonzero(offs == 0.0)[0]]), 4),
                                         "M+59.3": round(float(s[3][nc + int(np.flatnonzero(FINE == 59.3)[0])]), 4),
                                         "M+60": round(float(s[3][np.flatnonzero(offs == 60.0)[0]]), 4)},
        }

    h = pd.DataFrame(h2h, columns=["year", "grp", "d_start", "d_end"])
    res = {
        "seed": SEED, "design": f"{DAYS_PER_YEAR} sessions/year x ({RTH_PER_DAY} RTH + {OVN_PER_DAY} overnight) minutes, "
                                "roll-block sessions excluded, in-sample only",
        "all": curves(list(acc)),
        "rth": curves([k for k in acc if k[1] == "rth"]),
        "ovn": curves([k for k in acc if k[1] == "ovn"]),
        "by_year_rth": {str(y): {k: v for k, v in curves([(y, "rth")]).items()
                                 if k.startswith(("n_", "argmin", "min_"))} for y in (2021, 2022, 2023, 2024)},
        "head_to_head": {"n": int(len(h)), "end_closer": int((h.d_end < h.d_start).sum()),
                         "start_closer": int((h.d_start < h.d_end).sum()), "tie": int((h.d_start == h.d_end).sum()),
                         "mean_d_start_pts": round(float(h.d_start.mean()), 4),
                         "mean_d_end_pts": round(float(h.d_end.mean()), 4)},
        "hist_best_equals_depth_best": {"equal": hist_eq[0], "n": hist_eq[1]},
        "ofb_tick_prev_best_equals_row_flow_t": {"equal": prev_eq[0], "n": prev_eq[1]},
        "examples": table,
    }
    D.OUT.mkdir(exist_ok=True)
    (D.OUT / "ts_law.json").write_text(json.dumps(res, indent=1))
    a = res["all"]
    print(f"n={a['n_minutes']}  argmin last-before {a['argmin_last_before_s']}s  first-after {a['argmin_first_after_s']}s")
    print("coarse:", {k: a["coarse_last_before"][k] for k in ("-60s", "-30s", "+0s", "+30s", "+55s", "+60s", "+65s", "+90s", "+120s")})
    print("head to head:", res["head_to_head"])
    print("hist==depth:", res["hist_best_equals_depth_best"], " ofb_tick prev==row:", res["ofb_tick_prev_best_equals_row_flow_t"])
    for y, v in res["by_year_rth"].items():
        print(y, v)
    for r in table:
        print(r)


if __name__ == "__main__":
    main()
