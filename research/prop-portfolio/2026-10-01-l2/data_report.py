"""Sanity report of the L2 feature table (in-sample only): coverage per year, NaN share, distributions, hygiene
flags, minute alignment of the vendor and own delta, and the correlation of I3 / I10 with the next 1 / 5 minute
return. A DATA check, not a search: two features x two horizons, nothing is selected from it.

    python data_report.py            -> out/data_sanity.json, out/data_sanity.md
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import l2data as D

Q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
RTH = ("nyam", "mid", "pm")


def _corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 100:
        return None
    xs, ys = pd.Series(x[m]), pd.Series(y[m])
    return {"n": int(m.sum()), "pearson": round(float(xs.corr(ys)), 4),
            "spearman": round(float(xs.rank().corr(ys.rank())), 4)}


def _md_table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def desk_parity():
    """Live-parity DESIGN check only (no prices, no outcomes): desk DOM minute snapshots vs OFB late-2024, RTH."""
    res = {}
    files = sorted(D.DESK_DEPTH_DIR.glob("2026/*.depth.jsonl.gz"))
    rows = []
    for p in files:
        if p.stat().st_size < 100_000:
            continue
        st = D.LiveFeatureState()
        for m, b, a in D.desk_minute_books(p):
            f = st.update(m, b, a)
            f["bid_span"] = (b[0][0] - b[min(len(b), 10) - 1][0]) / D.TICK if b else np.nan
            f["file"] = p.name[:10]
            rows.append(f)
    if not rows:
        return res
    d = pd.DataFrame(rows)
    et = pd.to_datetime(d["usable_at"], unit="s", utc=True).dt.tz_convert(D.ET)
    d["et_min"] = et.dt.hour * 60 + et.dt.minute
    d["rth"] = (d["et_min"] >= 570) & (d["et_min"] < 958)
    # recording outages: gaps > 5 minutes between consecutive minute snapshots inside Globex hours, and the share
    # of each R session's decision minutes that has a snapshot (a live book strategy has NaN features in a gap)
    d["et_date"], d["sess"] = et.dt.date, D.session_of(d["et_min"].to_numpy())
    gaps = []
    t = d["t_utc"].to_numpy()
    for i in np.flatnonzero(np.diff(t) > 300):
        a, b = (pd.Timestamp(int(x), unit="s", tz="UTC").tz_convert(D.ET) for x in (t[i], t[i + 1]))
        if (a.hour == 17 or (a.hour == 16 and a.minute >= 55) or a.dayofweek == 5      # maintenance hour, weekend,
                or (a.dayofweek == 6 and a.hour < 18) or (a.dayofweek == 4 and a.hour >= 16)):   # Sunday pre-open
            continue
        gaps.append({"from_et": a.strftime("%Y-%m-%d %H:%M"), "to_et": b.strftime("%Y-%m-%d %H:%M"),
                     "minutes": int((t[i + 1] - t[i]) // 60)})
    res["desk_gaps_gt_5min"] = gaps
    want = {name: b - a for name, a, b in D.SESSIONS}
    cov = {}
    for day, g in d[d["sess"] != ""].groupby("et_date"):
        if day.weekday() < 5:
            cov[str(day)] = {k: f"{int((g['sess'] == k).sum())}/{want[k]}" for k in want}
    res["desk_minutes_per_r_session"] = cov
    res["desk_days"] = sorted(d["file"].unique().tolist())
    res["desk_minutes"] = int(len(d))
    cols = ["bid_top1", "bid_top10", "ask_top10", "depth10", "spread_ticks", "bid_wall_sz", "bid_wall_dist",
            "bid_med_sz", "bid_n", "bid_span"]
    res["desk_rth_median"] = {c: round(float(d.loc[d.rth, c].median()), 2) for c in cols}
    res["desk_ovn_median"] = {c: round(float(d.loc[~d.rth, c].median()), 2) for c in cols}
    res["desk_rth_minutes"] = int(d.rth.sum())
    res["desk_abs_imb10_median_rth"] = round(float(d.loc[d.rth, "imb10"].abs().median()), 3)
    return res


def main():
    raw = D.build_features(verbose=False, with_mid=True)          # unmasked, with the internal mid
    df = raw.copy()
    bad = ~df["book_ok"].to_numpy()
    for c in D.BOOK_COLS + D.RT_COLS:
        df[c] = df[c].where(~bad)
    res = {"rows": int(len(df)), "first_usable_at": str(df.index[0]), "last_usable_at": str(df.index[-1]),
           "index_unique_monotonic": bool(df.index.is_unique and df.index.is_monotonic_increasing)}
    year = pd.DatetimeIndex(pd.to_datetime(df["date"])).year.to_numpy()
    rth = df["session"].isin(RTH).to_numpy()
    in_r = (df["session"] != "").to_numpy()

    # ---- coverage per year
    cov = []
    for y in sorted(set(year)):
        g = df[year == y]
        cov.append({"year": int(y), "rows": int(len(g)), "sessions": int(g["globex_date"].nunique()),
                    "in_tape%": round(100 * g["in_tape"].mean(), 2),
                    "book_valid%": round(100 * g["book_valid"].mean(), 2),
                    "roll_block%": round(100 * g["roll_block"].mean(), 2),
                    "ofb_mismatch%": round(100 * g["ofb_mismatch"].mean(), 2),
                    "book_ok%": round(100 * g["book_ok"].mean(), 2),
                    "book_ok% (R sessions)": round(100 * g.loc[g["session"] != "", "book_ok"].mean(), 2),
                    "flow%": round(100 * g["f_volume"].notna().mean(), 2),
                    "flow% (RTH)": round(100 * g.loc[g["session"].isin(RTH), "f_volume"].notna().mean(), 2)})
    res["coverage"] = cov
    res["rows_by_session"] = {k or "(none)": int(v) for k, v in df["session"].value_counts().items()}
    res["book_ok_by_session%"] = {k or "(none)": round(100 * float(v), 2)
                                 for k, v in df.groupby("session")["book_ok"].mean().items()}

    # ---- hygiene
    rolls, sessions = D.roll_days()
    block = sorted(D.roll_block_dates(rolls, sessions))
    whole = df.groupby("globex_date")["ofb_mismatch"].all()
    mm = sorted(whole.index[whole])                                    # sessions flagged from the first row to the last
    res["rolls"] = [str(d) for d in rolls]
    res["roll_block_sessions"] = [str(d) for d in block]
    res["ofb_mismatch_sessions"] = [str(d) for d in mm]
    res["ofb_mismatch_outside_roll_block"] = [str(d) for d in mm if d not in set(block)]
    part = df[df["ofb_mismatch"] & ~df["roll_block"]]                  # per-minute flags outside the static block
    et = part.index.tz_convert(D.ET)
    res["ofb_mismatch_minutes_outside_roll_block"] = {
        "rows": int(len(part)), "rows_in_R_sessions": int((part["session"] != "").sum()),
        "book_ok_rows_removed": int((part["book_valid"] & part["in_tape"]).sum()),
        "by_session": {str(k): {"rows": int(len(g)), "first_usable_et": g.index[0].tz_convert(D.ET).strftime("%m-%d %H:%M"),
                                "last_usable_et": g.index[-1].tz_convert(D.ET).strftime("%m-%d %H:%M")}
                       for k, g in part.groupby("globex_date")}}
    okc = raw[raw["book_ok"] & raw["f_c"].notna()]
    off = ((okc["bid_px"] + okc["ask_px"]) / 2 - okc["f_c"]).abs()
    res["anchor_mid_vs_tape_close_pts_book_ok"] = {
        "n": int(len(off)), "q50": float(off.quantile(0.5)), "q90": float(off.quantile(0.9)),
        "q99": float(off.quantile(0.99)), "max": float(off.max()),
        "rows_gt_5pts": int((off > 5).sum()), "rows_gt_10pts": int((off > 10).sum()), "rows_gt_20pts": int((off > 20).sum())}
    n_rows = df.groupby("globex_date").size()
    res["rows_per_session"] = {str(int(k)): int(v) for k, v in n_rows.value_counts().items()}
    res["sessions_not_1380_rows"] = {str(k): int(v) for k, v in n_rows[n_rows != 1380].items()}
    diff = (raw["_mid"] - raw["f_c"]).where(raw["in_tape"])
    med = diff.groupby(raw["globex_date"]).median()
    res["mid_minus_tape_close_session_median_pts"] = {
        "roll_day": {str(r): (round(float(med.get(r, np.nan)), 2)) for r in rolls},
        "day_before": {str(sessions[sessions.index(r) - 1]): round(float(med.get(sessions[sessions.index(r) - 1], np.nan)), 2)
                       for r in rolls},
        "day_after": {str(sessions[sessions.index(r) + 1]): round(float(med.get(sessions[sessions.index(r) + 1], np.nan)), 2)
                      for r in rolls if sessions.index(r) + 1 < len(sessions)},
        "abs_median_other_sessions_max": round(float(med[~med.index.isin(block)].abs().max()), 2),
    }
    live = raw[raw["in_tape"] & raw["book_valid"]]
    res["invalid_book_in_tape_minutes"] = int((raw["in_tape"] & ~raw["book_valid"]).sum())
    res["levels_lt_10_share%"] = {"bid": round(100 * float((live["bid_n"] < 10).mean()), 4),
                                 "ask": round(100 * float((live["ask_n"] < 10).mean()), 4)}
    lt = (raw["bid_n"] < 10) | (raw["ask_n"] < 10)
    res["levels_lt_10_either_side"] = {
        "book_valid rows": int((lt & raw["book_valid"]).sum()),
        "book_valid share%": round(100 * float((lt & raw["book_valid"]).sum() / raw["book_valid"].sum()), 4),
        "in_tape & book_valid rows": int((lt & raw["book_valid"] & raw["in_tape"]).sum()),
        "book_ok rows": int((lt & raw["book_ok"]).sum())}

    # ---- NaN share (masked table, as load_features returns it)
    cols = D.BOOK_COLS + D.FLOW_COLS + D.RT_COLS
    res["nan_share%"] = {c: {"all": round(100 * float(df[c].isna().mean()), 2),
                             "R sessions": round(100 * float(df.loc[in_r, c].isna().mean()), 2),
                             "RTH": round(100 * float(df.loc[rth, c].isna().mean()), 2)} for c in cols}

    # ---- distributions
    dist = {}
    for c in D.BOOK_COLS + ["f_volume", "f_delta", "f_sweep_buy_vol", "f_sweeps_buy", "f_big_print", "f_big_order"] + D.RT_COLS:
        dist[c] = {"rth": [round(float(v), 3) for v in df.loc[rth, c].quantile(Q)],
                   "overnight": [round(float(v), 3) for v in df.loc[~rth, c].quantile(Q)]}
    res["quantiles"] = {"q": Q, "cols": dist}
    res["median_by_year_rth"] = {c: {str(int(y)): round(float(df.loc[rth & (year == y), c].median()), 2)
                                     for y in sorted(set(year))}
                                 for c in ["depth10", "bid_top1", "spread_ticks", "bid_wall_sz", "bid_med_sz", "f_volume"]}

    # ---- minute alignment of vendor cum_delta with our delta (lag in minutes of OUR series)
    t = raw["t_utc"].to_numpy()
    rt = pd.Series(raw["rt_cum_delta"].to_numpy(), index=t)
    d_rt = (rt - rt.reindex(t - 60).to_numpy()).to_numpy()
    own = pd.Series(raw["f_delta"].to_numpy(), index=t)
    okr = (raw["in_tape"] & ~raw["roll_block"] & ~raw["ofb_mismatch"]).to_numpy() & rth
    res["vendor_dcumdelta_vs_own_delta_corr_rth"] = {
        f"own minute M{lag:+d}": _corr(np.where(okr, d_rt, np.nan), own.reindex(t + 60 * lag).to_numpy())
        for lag in (-1, 0, 1)}

    # ---- I3 / I10 vs next 1 / 5 minute return (sanity only)
    c = pd.Series(raw["f_c"].to_numpy(), index=t)
    mid = pd.Series(np.where(raw["book_ok"], raw["_mid"], np.nan), index=t)
    corr = {}
    for feat in ("imb3", "imb10"):
        x = df[feat].to_numpy().astype(float)
        for k in (1, 5):
            r_tape = c.reindex(t + 60 * k).to_numpy() - c.to_numpy()
            r_mid = mid.reindex(t + 60 * k).to_numpy() - mid.to_numpy()
            for name, r in (("tape close-to-close", r_tape), ("OFB mid-to-mid", r_mid)):
                key = f"{feat} vs next {k}m {name}"
                corr[key] = {"all": _corr(x, r), "rth": _corr(np.where(rth, x, np.nan), r),
                             "overnight": _corr(np.where(~rth, x, np.nan), r)}
                if name == "OFB mid-to-mid":
                    corr[key]["by_year_rth"] = {str(int(y)): _corr(np.where(rth & (year == y), x, np.nan), r)
                                                for y in sorted(set(year))}
    res["imbalance_vs_forward_return"] = corr
    # same-minute relation to the PAST minute's return, to show the feature is not just lagged price
    r_back = mid.to_numpy() - mid.reindex(t - 60).to_numpy()
    res["imb10_vs_past_1m_mid_return_rth"] = _corr(np.where(rth, df["imb10"].to_numpy().astype(float), np.nan), r_back)

    res["desk_parity_design_only"] = desk_parity()
    ofb24 = df[rth & (year == 2024) & (pd.DatetimeIndex(pd.to_datetime(df["date"])).month >= 10)]
    res["ofb_2024Q4_rth_median"] = {c: round(float(ofb24[c].median()), 2) for c in
                                    ["bid_top1", "bid_top10", "ask_top10", "depth10", "spread_ticks", "bid_wall_sz",
                                     "bid_wall_dist", "bid_med_sz", "bid_n"]}
    res["ofb_2024Q4_abs_imb10_median_rth"] = round(float(ofb24["imb10"].abs().median()), 3)

    D.OUT.mkdir(exist_ok=True)
    (D.OUT / "data_sanity.json").write_text(json.dumps(res, indent=1, default=str))

    # ---- markdown fragment
    md = ["### Coverage per year", _md_table(cov, list(cov[0])), "",
          "### NaN share % (table as returned by load_features: book/rt columns NaN where book_ok is False)",
          _md_table([{"column": c, **v} for c, v in res["nan_share%"].items()], ["column", "all", "R sessions", "RTH"]), "",
          f"### Quantiles {Q} (RTH = nyam+mid+pm decisions | everything else)",
          _md_table([{"column": c, "RTH": " / ".join(f"{x:g}" for x in v["rth"]),
                      "overnight": " / ".join(f"{x:g}" for x in v["overnight"])} for c, v in dist.items()],
                    ["column", "RTH", "overnight"]), "",
          "### RTH medians by year",
          _md_table([{"column": c, **v} for c, v in res["median_by_year_rth"].items()],
                    ["column"] + [str(int(y)) for y in sorted(set(year))]), "",
          "### Imbalance vs forward return (sanity)",
          _md_table([{"pair": k, **{s: (f"{v[s]['pearson']:+.4f} / {v[s]['spearman']:+.4f} (n={v[s]['n']:,})" if v[s] else "")
                                    for s in ("all", "rth", "overnight")}} for k, v in corr.items()],
                    ["pair", "all", "rth", "overnight"])]
    (D.OUT / "data_sanity.md").write_text("\n".join(md) + "\n")
    print(json.dumps({k: res[k] for k in ("rows", "coverage", "ofb_mismatch_sessions", "ofb_mismatch_outside_roll_block",
                                          "ofb_mismatch_minutes_outside_roll_block", "anchor_mid_vs_tape_close_pts_book_ok", "rows_per_session",
                                          "sessions_not_1380_rows", "levels_lt_10_either_side",
                                          "vendor_dcumdelta_vs_own_delta_corr_rth", "imbalance_vs_forward_return",
                                          "imb10_vs_past_1m_mid_return_rth", "desk_parity_design_only",
                                          "ofb_2024Q4_rth_median", "ofb_2024Q4_abs_imb10_median_rth",
                                          "invalid_book_in_tape_minutes", "levels_lt_10_share%",
                                          "mid_minus_tape_close_session_median_pts")}, indent=1, default=str))


if __name__ == "__main__":
    main()
