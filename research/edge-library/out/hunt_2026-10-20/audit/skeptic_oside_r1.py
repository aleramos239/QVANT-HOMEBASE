"""Skeptic audit of owner_fvg_oside_15_a1m3_nl_r1 -- stored arrays only, no new run of any kind.

Run: .venv-research/bin/python research/edge-library/out/hunt_2026-10-20/audit/skeptic_oside_r1.py
Reads ~/.homebase/taught/<store>/ (build cells.npz, wf/test_cells.npz, wf/result.json) and the Desk port's stored
walk-forward trades (homebase/.state/tester/walkforward/*draft_nq_fvg_oside_15_r1*/cells/00/trades.json)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

HOME = Path.home() / ".homebase" / "taught"
REPO = Path(__file__).resolve().parents[5]
NAME = "owner_fvg_oside_15_a1m3_nl_r1"
CELLS = ["struct-r0p75", "struct-r1", "struct-r1p25"]       # order of `off` in the build cells.npz (checked against table.csv below)
BLIND_FROM = "2025-07"
APEX_MAE = 2250.0                                             # Apex Legacy PA open-loss limit on a fresh account (apex300.mae_min)
PT = 20.0                                                     # $ a point, 1 NQ


def month(o: int) -> str:
    return dt.date.fromordinal(int(o)).isoformat()[:7]


def load(name: str) -> tuple[dict, dict, dict]:
    base = HOME / name
    run = next(p for p in (base / "runs").iterdir() if p.is_dir() and "__ctl" not in p.name)
    z = np.load(run / "cells.npz")
    off = z["off"]
    build = {c: {k: z[k][off[i]:off[i + 1]] for k in z.files if k != "off"} for i, c in enumerate(CELLS)}
    t = np.load(base / "wf" / "test_cells.npz")
    test = {c: {k.split("|")[1]: t[k] for k in t.files if k.startswith(c + "|")} for c in CELLS}
    return build, test, json.loads((base / "wf" / "result.json").read_text())


def table_counts(name: str) -> dict:
    run = next(p for p in (HOME / name / "runs").iterdir() if p.is_dir() and "__ctl" not in p.name)
    rows = [ln.split(",") for ln in (run / "table.csv").read_text().splitlines()[1:]]
    return {r[0]: (int(r[4]), float(r[5])) for r in rows if r[3] == "all"}


def stitched(build: dict, test: dict, wf: dict) -> list[dict]:
    out = []
    for m in wf["months"]:
        c = m["cell"]
        if not c:
            continue
        src = test[c] if m["month"] >= BLIND_FROM else build[c]
        sel = np.array([month(d) == m["month"] for d in src["date"]])
        for i in np.flatnonzero(sel):
            out.append({"month": m["month"], "cell": c, "date": int(src["date"][i]), "entry_ms": int(src["entry_ms"][i]),
                        "net": float(src["net"][i]), "mae": float(src["mae"][i]),
                        "side": int(src["side"][i]) if "side" in src else None,
                        "risk": float(src["risk"][i]) if "risk" in src else None, "blind": m["month"] >= BLIND_FROM})
    return out


def stats(n: np.ndarray) -> dict:
    if not len(n):
        return {"trades": 0}
    w, l_ = n[n > 0], n[n <= 0]
    sd = n.std(ddof=1) if len(n) > 1 else 0.0
    return {"trades": len(n), "net": round(float(n.sum())), "avg": round(float(n.mean()), 1), "win": round(float((n > 0).mean()), 3),
            "pf": round(float(w.sum() / -l_.sum()), 2) if l_.sum() < 0 else None, "t": round(float(n.mean() / (sd / np.sqrt(len(n)))), 2) if sd else None}


def boot_p(n: np.ndarray, draws=20000, seed=7) -> float:
    """share of bootstrap means <= 0 (one-sided p of 'no edge')."""
    r = np.random.default_rng(seed)
    m = n[r.integers(0, len(n), (draws, len(n)))].mean(1)
    return float((m <= 0).mean())


def desk_trades() -> list[dict]:
    wf = REPO / "homebase" / ".state" / "tester" / "walkforward"
    d = next(p for p in wf.iterdir() if "draft_nq_fvg_oside_15_r1-" in p.name)
    return json.loads((d / "cells" / "00" / "trades.json").read_text())


def main() -> None:
    R: dict = {}
    build, test, wf = load(NAME)
    tc = table_counts(NAME)
    for c in CELLS:                                            # the cell order is right: counts and nets match table.csv
        assert len(build[c]["net"]) == tc[c][0] and abs(build[c]["net"].sum() - tc[c][1]) < 1, (c, len(build[c]["net"]), tc[c])
    X = stitched(build, test, wf)
    n = np.array([x["net"] for x in X])
    blind = np.array([x["blind"] for x in X])
    assert len(n) == wf["metrics"]["trades"] and abs(n.sum() - wf["metrics"]["net"]) < 1, (len(n), n.sum())
    assert blind.sum() == wf["split"]["test_days"]["trades"] and abs(n[blind].sum() - wf["split"]["test_days"]["net"]) < 1
    R["reproduced"] = {"wf": stats(n), "build_months": stats(n[~blind]), "blind": stats(n[blind])}

    # ---- concentration
    mon = {}
    for x in X:
        mon[x["month"]] = mon.get(x["month"], 0.0) + x["net"]
    ms = sorted(mon.items(), key=lambda kv: -kv[1])
    day = {}
    for x in X:
        day[x["date"]] = day.get(x["date"], 0.0) + x["net"]
    dv = np.array(sorted(day.values(), reverse=True))
    top5pct = int(np.ceil(0.05 * len(n)))
    srt = np.sort(n)[::-1]
    nb = np.sort(n[blind])[::-1]
    R["concentration"] = {
        "months": {k: round(v) for k, v in sorted(mon.items())},
        "top2_months": [ms[0][0], ms[1][0]], "top2_share": round((ms[0][1] + ms[1][1]) / n.sum(), 3),
        "wf_without_top2_months": round(n.sum() - ms[0][1] - ms[1][1]),
        "days_traded": len(dv), "top5_days_net": round(dv[:5].sum()), "top5_days_share": round(dv[:5].sum() / n.sum(), 3),
        "top10_days_share": round(dv[:10].sum() / n.sum(), 3),
        "best5pct_trades": top5pct, "wf_without_best5pct": round(srt[top5pct:].sum()),
        "blind_without_best5pct": round(nb[int(np.ceil(0.05 * len(nb))):].sum()),
        "blind_without_best3_trades": round(nb[3:].sum()), "blind_best_trade": round(nb[0]),
        "build_r1_cell_without_best5pct": round(np.sort(build["struct-r1"]["net"])[::-1][int(np.ceil(0.05 * len(build["struct-r1"]["net"]))):].sum()),
    }

    # ---- blind months one by one, plus every cell in each blind month (how much hangs on the pick)
    bm = {}
    for mo in sorted({x["month"] for x in X if x["blind"]} | {"2026-09"}):
        pick = next(m["cell"] for m in wf["months"] if m["month"] == mo)
        row = {"pick": pick}
        if pick:
            row.update(stats(np.array([x["net"] for x in X if x["month"] == mo])))
        for c in CELLS:
            s = np.array([month(d) == mo for d in test[c]["date"]])
            row[c] = stats(test[c]["net"][s])
        bm[mo] = row
    R["blind_months"] = bm
    allblind = {c: stats(test[c]["net"][np.array([month(d) >= "2025-07" for d in test[c]["date"]])]) for c in CELLS}
    R["every_test_day_2025-07_on_each_cell"] = allblind
    R["blind_p_boot"] = round(boot_p(n[blind]), 3)

    # ---- slippage: one extra tick a side = 2 ticks x $5 = $10 a trade at 1 NQ; two extra ticks a side = $20
    R["slippage"] = {f"+{k}_tick_a_side": {"wf": round(n.sum() - 10 * k * len(n)), "wf_avg": round(n.mean() - 10 * k, 1),
                                           "blind": round(n[blind].sum() - 10 * k * blind.sum()), "blind_avg": round(n[blind].mean() - 10 * k, 1),
                                           "build_months": round(n[~blind].sum() - 10 * k * (~blind).sum())} for k in (1, 2, 3)}
    R["slippage"]["blind_breakeven_extra_usd_a_trade"] = round(n[blind].mean(), 1)

    # ---- the Desk port's stored walk-forward trades (1 MNQ, $1 RT + 1 tick): match to the lane by entry_ms
    D = desk_trades()
    dk = {int(t["entry_ms"]): t for t in D}
    for x in X:
        t = dk.get(x["entry_ms"])
        if t is not None:
            x["desk_side"] = 1 if t["side"] == "long" else -1
            x["desk_risk"] = abs(t["entry_price"] - t["sl"])
    matched = sum(1 for x in X if "desk_side" in x)
    side_ok = sum(1 for x in X if x["side"] is not None and "desk_side" in x and x["side"] == x["desk_side"])
    side_known = sum(1 for x in X if x["side"] is not None and "desk_side" in x)
    R["desk_match"] = {"stitched_trades": len(X), "matched_by_entry_ms": matched, "build_side_agree": f"{side_ok}/{side_known}",
                       "blind_matched": sum(1 for x in X if x["blind"] and "desk_side" in x), "blind_trades": int(blind.sum())}

    # ---- long vs short (build months: the store's side; blind months: the Desk twin's side, same entry_ms)
    def sd(x):
        return x["side"] if x["side"] is not None else x.get("desk_side")
    ls = {}
    for part, f in (("wf", lambda x: True), ("build_months", lambda x: not x["blind"]), ("blind", lambda x: x["blind"])):
        for s, nm in ((1, "long"), (-1, "short")):
            ls[f"{part}_{nm}"] = stats(np.array([x["net"] for x in X if f(x) and sd(x) == s]))
        ls[f"{part}_side_unknown"] = sum(1 for x in X if f(x) and sd(x) is None)
    for c in ("struct-r1",):
        b = build[c]
        ls["build_days_r1_cell_long"] = stats(b["net"][b["side"] == 1])
        ls["build_days_r1_cell_short"] = stats(b["net"][b["side"] == -1])
    R["long_short"] = ls

    # ---- stop size (points) and Apex 1-mini open-loss rule
    def dist(v):
        v = np.asarray([q for q in v if q is not None], float)
        lim = (APEX_MAE - 9) / PT                             # stop distance at which a full stop-out passes $2,250 (costs ~$9)
        return {"n": len(v), "median": round(float(np.median(v)), 2), "p90": round(float(np.percentile(v, 90)), 2),
                "p99": round(float(np.percentile(v, 99)), 2), "max": round(float(v.max()), 2),
                "median_usd_1NQ": round(float(np.median(v)) * PT), "p90_usd": round(float(np.percentile(v, 90)) * PT), "max_usd": round(float(v.max()) * PT),
                "share_over_apex": round(float((v > lim).mean()), 4), "n_over_apex": int((v > lim).sum()), "apex_limit_pts": round(lim, 1)}
    b1 = build["struct-r1"]
    R["stops"] = {
        "build_days_r1_cell": dist(b1["risk"]),
        "wf_build_months": dist([x["risk"] for x in X if not x["blind"]]),
        "wf_blind_months_desk_twin": dist([x.get("desk_risk") for x in X if x["blind"]]),
        "desk_all_2021_09_to_2026_09": dist([abs(t["entry_price"] - t["sl"]) for t in D]),
        "desk_2025_07_on": dist([abs(t["entry_price"] - t["sl"]) for t in D if t["date"] >= "2025-07"]),
    }
    mae_usd = np.array([x["mae"] for x in X])
    R["stops"]["wf_mae_usd"] = {"max": round(float(mae_usd.max())), "n_over_2250": int((mae_usd > APEX_MAE).sum()),
                                "share_over_2250": round(float((mae_usd > APEX_MAE).mean()), 4)}
    # what the WF would have been with the >112 pt trades skipped (a per-trade risk cap the owner could set)
    lim = (APEX_MAE - 9) / PT
    keep = np.array([((x["risk"] if x["risk"] is not None else x.get("desk_risk")) or 0) <= lim for x in X])
    R["stops"]["wf_if_stops_over_apex_skipped"] = {"wf": stats(n[keep]), "blind": stats(n[keep & blind]), "skipped": int((~keep).sum()),
                                                   "skipped_net": round(float(n[~keep].sum()))}
    bmae = b1["mae"]
    R["stops"]["build_r1_mae_over_2250"] = {"n": int((bmae > APEX_MAE).sum()), "share": round(float((bmae > APEX_MAE).mean()), 4),
                                            "net_of_those": round(float(b1["net"][bmae > APEX_MAE].sum()))}

    # ---- lane vs Desk on the same test days, same rule (r1 cell, every test day 2025-07-01 .. 2026-09-22)
    L = test["struct-r1"]
    lane = {int(e): (float(nn), month(d)) for e, nn, d in zip(L["entry_ms"], L["net"], L["date"])}
    last = dt.date.fromordinal(int(L["date"].max())).isoformat()
    Dt = [t for t in D if "2025-07-01" <= t["date"] <= last]
    desk = {int(t["entry_ms"]): t for t in Dt}
    both = sorted(set(lane) & set(desk))
    lo, do = sorted(set(lane) - set(desk)), sorted(set(desk) - set(lane))
    # Desk $ in NQ terms: x10 (MNQ -> NQ), then its $1 RT micro commission (= $10 NQ) put back to the lane's $4
    conv = lambda t: t["net"] * 10 + 6.0                      # noqa: E731
    dl = np.array([lane[e][0] for e in both])
    dd = np.array([conv(desk[e]) for e in both])
    diff = dd - dl
    big = np.argsort(np.abs(diff))[::-1][:8]
    per_m = {}
    for mo in sorted({lane[e][1] for e in lane} | {t["date"][:7] for t in Dt}):
        per_m[mo] = {"lane": round(sum(v for v, m in lane.values() if m == mo)), "lane_n": sum(1 for v, m in lane.values() if m == mo),
                     "desk_nq_eq": round(sum(conv(t) for t in Dt if t["date"][:7] == mo)), "desk_n": sum(1 for t in Dt if t["date"][:7] == mo)}
    R["lane_vs_desk_test_days_r1"] = {
        "lane": stats(L["net"]), "desk_nq_eq": stats(np.array([conv(t) for t in Dt])), "matched": len(both),
        "lane_only": {"n": len(lo), "net": round(sum(lane[e][0] for e in lo))},
        "desk_only": {"n": len(do), "net_nq_eq": round(sum(conv(desk[e]) for e in do))},
        "matched_lane_net": round(float(dl.sum())), "matched_desk_net": round(float(dd.sum())),
        "matched_same_sign": round(float((np.sign(dl) == np.sign(dd)).mean()), 3),
        "matched_abs_diff_median": round(float(np.median(np.abs(diff))), 1),
        "biggest_gaps": [{"day": dt.datetime.fromtimestamp(both[i] / 1000).isoformat(timespec="minutes"), "lane": dl[i], "desk": round(dd[i]),
                          "desk_exit": desk[both[i]]["exit_reason"], "desk_entry": desk[both[i]]["entry_price"], "desk_sl": desk[both[i]]["sl"],
                          "desk_tp": desk[both[i]]["tp"], "desk_secs": round(desk[both[i]]["seconds"])} for i in big],
        "per_month": per_m,
    }
    # the same comparison on build days (the lane's r1 build store vs the Desk's build-day trades)
    Db = [t for t in D if t["date"] <= "2025-06-30"]
    lb = {int(e): float(v) for e, v in zip(b1["entry_ms"], b1["net"])}
    dbk = {int(t["entry_ms"]): t for t in Db}
    bb = sorted(set(lb) & set(dbk))
    R["lane_vs_desk_build_days_r1"] = {"lane": stats(b1["net"]), "desk_nq_eq": stats(np.array([conv(t) for t in Db])), "matched": len(bb),
                                       "lane_only": len(set(lb) - set(dbk)), "desk_only": len(set(dbk) - set(lb)),
                                       "matched_lane_net": round(sum(lb[e] for e in bb)), "matched_desk_net": round(sum(conv(dbk[e]) for e in bb))}
    print(json.dumps(R, indent=1, default=float))
    (Path(__file__).with_suffix(".json")).write_text(json.dumps(R, indent=1, default=float))


if __name__ == "__main__":
    main()
