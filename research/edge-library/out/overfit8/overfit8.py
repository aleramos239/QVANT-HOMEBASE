"""Overfitting diagnostics for the 8 NOT PROVEN saved strategies. ANALYSIS ONLY: reads stores already on disk through judge.py's
own readers (BUILD variant list, day filters, costs included, 1 contract). Runs no simulation, opens no year. 2026 stores are
read only for units on out/exam2026/allowed.json. Writes only under out/overfit8/.
In-sample = BUILD (22 Sep 2021 - 2023) + 2024. Unseen = 2025, and 2026 where the unit was allowed to be read on it.
Thresholds for the three labels are fixed at the top (LABEL RULES) before any number is computed."""
import csv, datetime as dt, json, math, sys
from pathlib import Path
import numpy as np

W = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(W))
import judge as J        # noqa: E402
import library as LB     # noqa: E402

OUT = Path(__file__).resolve().parent
UNITS = ["straddle_tight_1000-GC-tf30-nyam@C", "straddle_tight_0830-GC-tf30-pre@B", "straddle_tight_0830-GC-tf30-pre@A",
         "straddle_tight_1000-NQ-tf30-nyam@C", "first_bar_mom-NQ-tf15-mid", "first_bar_mom-ES-tf15-mid",
         "donchian-NQ-tf30-nyam", "straddle_t_1800-NQ-tf30-eve"]
PLAIN = {UNITS[0]: "tight bracket 10:00 gold, 10:00-release days (evC)", UNITS[1]: "tight bracket 08:30 gold, major releases (evB)",
         UNITS[2]: "tight bracket 08:30 gold, all release days (evA)", UNITS[3]: "tight bracket 10:00 NQ, 10:00-release days (evC)",
         UNITS[4]: "first-bar momentum NQ 15-min midday", UNITS[5]: "first-bar momentum ES 15-min midday",
         UNITS[6]: "Donchian break NQ 30-min morning", UNITS[7]: "bracket 18:00 NQ evening"}
# ---- LABEL RULES (fixed in advance; applied mechanically). "edge kept" = average-variant net PER TRADE, unseen years together /
# in-sample. "random" = the unit's entry control as in out/oos_summary.md (random minute for clock brackets, random entries for
# bar strategies). "together" = 2025 + 2026 where both exist (real sum against the sum of the two years' random draws).
KEPT_BAD, KEPT_GOOD = 0.25, 0.50
RAND_BAD_TOGETHER, RAND_GOOD_EACH = 0.75, 0.90
RHO_BAD = 0.10
FAST_S = J.FAST_S

OOS = {e["unit"]: e for e in json.loads((W / "out" / "exam2026" / "oos.json").read_text())}
ALLOWED = set(json.loads(J.ALLOWED.read_text())["units"])


def yr(o):
    return dt.date.fromordinal(int(o)).year


def cells(st, u, ids):
    return {c: J.cellx(st, c, u["sess"], u) for c in ids}


def cat(parts):
    """Concatenate one variant's trades over several period stores."""
    return {k: np.concatenate([p[k] for p in parts]) for k in ("date", "net", "dur_s")}


def daily_avg(X, ids):
    """Average variant: mean daily P&L across variants on the days at least one variant traded -> (days, daily)."""
    d = np.concatenate([X[c]["date"] for c in ids]).astype(np.int64)
    n = np.concatenate([X[c]["net"] for c in ids]).astype(np.float64)
    if not len(d):
        return np.zeros(0, np.int64), np.zeros(0)
    days, inv = np.unique(d, return_inverse=True)
    D = np.zeros(len(days))
    np.add.at(D, inv, n)
    return days, D / len(ids)


def block(X, ids):
    """Numbers of the average variant on one span."""
    nets = np.array([float(X[c]["net"].sum()) for c in ids])
    trs = np.array([len(X[c]["net"]) for c in ids])
    days, D = daily_avg(X, ids)
    pt = np.array([nets[i] / trs[i] if trs[i] else np.nan for i in range(len(ids))])
    n = len(D)
    t = float(D.mean() / (D.std(ddof=1) / math.sqrt(n))) if n > 2 and D.std(ddof=1) > 0 else None
    return {"avg_net": float(nets.mean()), "median_net": float(np.median(nets)), "avg_trades": float(trs.mean()),
            "per_trade": float(nets.sum() / trs.sum()) if trs.sum() else None,
            "traded_days": int(n), "per_traded_day": float(D.sum() / n) if n else None,
            "median_variant_per_trade": float(np.nanmedian(pt)) if np.isfinite(pt).any() else None,
            "share_profitable": float((nets > 0).mean()), "n_profitable": int((nets > 0).sum()), "t_daily": t,
            "_nets": nets, "_D": D}


def one(X, c):
    x = X[c]
    n = x["net"].astype(np.float64)
    nd = len(np.unique(x["date"]))
    return {"net": float(n.sum()), "trades": int(len(n)), "per_trade": float(n.mean()) if len(n) else None,
            "per_traded_day": float(n.sum() / nd) if nd else None}


def ratio(a, b):
    return None if a is None or b is None or b <= 0 else float(a / b)


def spearman(a, b):
    def rk(v):
        o = np.argsort(v, kind="mergesort")
        r = np.empty(len(v))
        r[o] = np.arange(len(v), dtype=float)
        for val in np.unique(v):                       # average ranks of ties
            m = v == val
            r[m] = r[m].mean()
        return r
    ra, rb = rk(np.asarray(a, float)), rk(np.asarray(b, float))
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def thirds(ins, uns):
    o = np.argsort(-ins, kind="mergesort")
    k = max(1, len(o) // 3)
    return float(uns[o[:k]].mean()), float(uns[o[-k:]].mean()), k


def fast(X, ids):
    f = J.fast_share([X[c] for c in ids])
    return {"net": f["net"], "net_fast": f["net_fast"], "fast_net_share": f["fast_net_share"], "fast_winner_share": f["fast_profit_share"]}


def ctl_draws(u, yst, ids, period):
    """The unit's entry control on one year, exactly as judge.controls draws it -> (draws, control mean)."""
    c = "shift" if u["timed"] else "c1"
    sd = J.seed_of(u["uid"], f"{period}-{c}")
    S = J.seed_stores(u, period, c, sorted({i.rsplit("_", 1)[-1] for i in ids}) if c == "c1" else list(ids))
    t = J.c1_table(yst, u, ids, S, sd) if c == "c1" else J.shift_table(u, ids, S, period, sd)
    return c, np.asarray(t["draws"], float), float(t["mean"]), len(S)


def saved_set(u):
    rows = list(csv.DictReader((LB.MEMBERS / u["name"] / "surviving_set.csv").open()))
    return [r["cell"] for r in rows], next((r["cell"] for r in rows if r["default"] == "True"), None)


def do(addr):
    J.RULE["exam"] = False
    u = J.unit(addr)
    has26 = addr in ALLOWED
    bst, _ = J.build_store(u)
    brows = J.table(bst, u)
    ids = J.table_stats(brows)["ids"]
    saved, default = saved_set(u)
    o = OOS[addr]
    assert len(ids) == o["variants"] and len(saved) == o["saved"] and default == o["default"], (addr, len(ids), len(saved), default)
    assert all(c in ids for c in saved)
    P, S, used = {"build": cells(bst, u, ids)}, {}, {}
    periods = ["pick", "check"] + (["exam"] if has26 else [])
    draws = {}
    for p in periods:
        if p == "exam":
            J.RULE["exam"] = True
            J.exam_gate(u)                               # raises unless the unit is on allowed.json
        yst, yrec = J.find(J.skey(u["key"], u, p), p, lambda r: not r["stress"])
        sst, srec = J.stress_store(u, p, ids)
        P[p] = cells(yst, u, ids)
        S[p] = cells(sst, u, ids) if sst is not None else None
        used[p] = [J.where(yrec)] + ([J.where(srec)] if srec else [])
        if p in ("check", "exam"):
            draws[p] = ctl_draws(u, yst, ids, p)
    # BUILD cut by calendar year for the decay row
    by_year = {}
    for y in (2021, 2022, 2023):
        by_year[y] = {c: {k: v[np.array([yr(d) == y for d in P["build"][c]["date"]], bool)] if len(v) else v for k, v in P["build"][c].items()} for c in ids}
    by_year[2024], by_year[2025] = P["pick"], P["check"]
    if has26:
        by_year[2026] = P["exam"]
    ins = {c: cat([P["build"][c], P["pick"][c]]) for c in ids}
    uns = {c: cat([P[p][c] for p in periods[1:]]) for c in ids}
    B = {"insample": block(ins, ids), "build": block(P["build"], ids), "2024": block(P["pick"], ids), "2025": block(P["check"], ids),
         "unseen": block(uns, ids)}
    if has26:
        B["2026"] = block(P["exam"], ids)
    R = {"unit": addr, "plain": PLAIN[addr], "variants": len(ids), "saved": len(saved), "default": default, "has_2026": has26,
         "control": draws["check"][0], "stores": used}
    # ---- A. edge kept
    A = {"avg_variant": {k: {x: B[k][x] for x in ("avg_net", "avg_trades", "per_trade", "traded_days", "per_traded_day")} for k in B}}
    for k in ("2025", "2026", "unseen"):
        if k in B:
            A["avg_variant"][k]["kept_per_trade"] = ratio(B[k]["per_trade"], B["insample"]["per_trade"])
            A["avg_variant"][k]["kept_per_traded_day"] = ratio(B[k]["per_traded_day"], B["insample"]["per_traded_day"])
    D_ = {"insample": one(ins, default), "2025": one(P["check"], default), "unseen": one(uns, default)}
    if has26:
        D_["2026"] = one(P["exam"], default)
    for k in ("2025", "2026", "unseen"):
        if k in D_:
            D_[k]["kept_per_trade"] = ratio(D_[k]["per_trade"], D_["insample"]["per_trade"])
    A["default_variant"] = D_
    A["median_variant"] = {k: {"median_net": B[k]["median_net"], "median_per_trade": B[k]["median_variant_per_trade"]} for k in B}
    for k in ("2025", "2026", "unseen"):
        if k in B:
            A["median_variant"][k]["kept_per_trade"] = ratio(B[k]["median_variant_per_trade"], B["insample"]["median_variant_per_trade"])
    R["A_edge_kept"] = A
    # ---- B. breadth
    sv = [ids.index(c) for c in saved]
    R["B_breadth"] = {"share_profitable": {k: B[k]["share_profitable"] for k in B}, "n_profitable": {k: B[k]["n_profitable"] for k in B},
                      "saved_profitable": {k: int((B[k]["_nets"][sv] > 0).sum()) for k in ("2025", "2026", "unseen") if k in B}}
    # ---- C. did the choice mean anything
    C = {}
    for k in ("2025", "2026", "unseen"):
        if k in B:
            top, bot, n3 = thirds(B["insample"]["_nets"], B[k]["_nets"])
            C[k] = {"spearman": spearman(B["insample"]["_nets"], B[k]["_nets"]), "top_third_avg_net": top, "bottom_third_avg_net": bot, "third_size": n3}
    R["C_choice"] = C
    # ---- D. against random (per year from judge's own numbers in oos.json; together = redrawn sums, checked against oos.json)
    Dd = {}
    real_sum, dsum, msum = 0.0, 0.0, 0.0
    for p, k in (("check", "2025"), ("exam", "2026")):
        if p not in draws:
            continue
        c, dr, mean, nseed = draws[p]
        oc = o[p]["controls"][c]
        real = B[k]["avg_net"]
        mine = float((real > dr).mean())
        assert abs(mine - oc["p_beat"]) < 2e-4 and abs((real - mean) - oc["lift"]) < 0.02, (addr, p, mine, oc["p_beat"], real - mean, oc["lift"])
        Dd[k] = {"p_beat": oc["p_beat"], "lift": oc["lift"], "seeds": nseed}
        if "days" in o[p]["controls"]:
            Dd[k]["days_p_beat"] = o[p]["controls"]["days"].get("p_beat")
            Dd[k]["days_lift_per_trade"] = o[p]["controls"]["days"].get("lift_per_trade")
        real_sum, dsum, msum = real_sum + real, dsum + dr, msum + mean
    Dd["unseen"] = {"p_beat": float((real_sum > dsum).mean()), "lift": float(real_sum - msum)}
    R["D_random"] = Dd
    # ---- E. concentration (average variant, unseen years together)
    Dn = np.sort(B["unseen"]["_D"])[::-1]
    k5 = int(math.ceil(0.05 * len(Dn)))
    R["E_concentration"] = {"unseen_net": float(Dn.sum()), "traded_days": int(len(Dn)), "best3_sum": float(Dn[:3].sum()),
                            "net_without_best3": float(Dn[3:].sum()), "best5pct_days": k5, "net_without_best5pct": float(Dn[k5:].sum()),
                            "t_daily": B["unseen"]["t_daily"], "t_daily_2025": B["2025"]["t_daily"],
                            "t_daily_2026": B["2026"]["t_daily"] if has26 else None, "t_daily_insample": B["insample"]["t_daily"]}
    # ---- F. cost / fill sensitivity
    F = {}
    tot = 0.0
    for p, k in (("check", "2025"), ("exam", "2026")):
        if p in S and S[p] is not None:
            v = float(np.mean([S[p][c]["net"].sum() for c in ids]))
            assert abs(v - o[p]["stress_avg_net"]) < 0.01, (addr, p, v, o[p]["stress_avg_net"])
            F[k] = {"stress_avg_net": v, "stress_share_profitable": float(np.mean([S[p][c]["net"].sum() > 0 for c in ids])), **fast(P[p], ids)}
            tot += v
    F["unseen"] = {"stress_avg_net": tot, **fast(uns, ids)}
    F["insample"] = fast(ins, ids)
    R["F_cost_fill"] = F
    # ---- G. decay
    G = {}
    for y, X in by_year.items():
        n = sum(float(X[c]["net"].sum()) for c in ids)
        t = sum(len(X[c]["net"]) for c in ids)
        G[str(y)] = {"per_trade": n / t if t else None, "avg_net": n / len(ids), "avg_trades": t / len(ids)}
        ref = o["avg_rows"].get(str(y))
        assert ref is None or abs(ref["net"] - G[str(y)]["avg_net"]) < 0.02, (addr, y, ref["net"], G[str(y)]["avg_net"])
    R["G_decay"] = G
    # ---- label (mechanical)
    kept = A["avg_variant"]["unseen"]["kept_per_trade"]
    un_net = B["unseen"]["avg_net"]
    rho = C["unseen"]["spearman"]
    ex3 = R["E_concentration"]["net_without_best3"]
    p_tog = Dd["unseen"]["p_beat"]
    p_each = [Dd[k]["p_beat"] for k in ("2025", "2026") if k in Dd]
    why_bad = []
    if un_net <= 0 or kept is None or kept <= KEPT_BAD:
        why_bad.append("edge kept <= 25 % (or unseen net <= 0)")
    if p_tog < RAND_BAD_TOGETHER:
        why_bad.append("does not beat 75 % of random tables in the unseen data together")
    if ex3 <= 0 and rho is not None and rho <= RHO_BAD:
        why_bad.append("unseen net <= 0 without the best 3 days and rank correlation <= 0.1")
    good = {"edge kept >= 50 %": kept is not None and kept >= KEPT_GOOD, "beats >= 90 % of random in every unseen year": all(p >= RAND_GOOD_EACH for p in p_each),
            "positive without best 3 days": ex3 > 0, "positive under stress, unseen together": F["unseen"]["stress_avg_net"] > 0}
    label = "LIKELY OVERFIT / NO EDGE" if why_bad else "HOLDING UP" if all(good.values()) else "UNCLEAR"
    R["label"] = {"label": label, "overfit_reasons": why_bad, "holding_up_checks": good, "holding_up_failed": [k for k, v in good.items() if not v]}
    for b in B.values():
        b.pop("_nets"), b.pop("_D")
    J.RULE["exam"] = False
    return R


def r0(v, nd=0):
    return "" if v is None else round(v, nd)


def flat(R):
    A, Bb, C, D, E, F, G = (R[k] for k in ("A_edge_kept", "B_breadth", "C_choice", "D_random", "E_concentration", "F_cost_fill", "G_decay"))
    av, dv, mv = A["avg_variant"], A["default_variant"], A["median_variant"]
    g = lambda d, *ks: (lambda x: x)(__import__("functools").reduce(lambda a, k: a.get(k) if isinstance(a, dict) else None, ks, d))  # noqa: E731
    row = {"unit": R["unit"], "plain": R["plain"], "label": R["label"]["label"], "variants": R["variants"], "saved": R["saved"], "default": R["default"],
           "control": R["control"]}
    for k in ("insample", "2025", "2026", "unseen"):
        row[f"A_avg_net_{k}"] = r0(g(av, k, "avg_net"), 2)
        row[f"A_avg_trades_{k}"] = r0(g(av, k, "avg_trades"), 1)
        row[f"A_per_trade_{k}"] = r0(g(av, k, "per_trade"), 2)
        row[f"A_per_traded_day_{k}"] = r0(g(av, k, "per_traded_day"), 2)
    for k in ("2025", "2026", "unseen"):
        row[f"A_kept_per_trade_{k}"] = r0(g(av, k, "kept_per_trade"), 3)
        row[f"A_kept_per_day_{k}"] = r0(g(av, k, "kept_per_traded_day"), 3)
        row[f"A_default_kept_{k}"] = r0(g(dv, k, "kept_per_trade"), 3)
        row[f"A_median_kept_{k}"] = r0(g(mv, k, "kept_per_trade"), 3)
    for k in ("insample", "2025", "2026", "unseen"):
        row[f"A_default_per_trade_{k}"] = r0(g(dv, k, "per_trade"), 2)
        row[f"A_default_net_{k}"] = r0(g(dv, k, "net"), 2)
        row[f"A_median_per_trade_{k}"] = r0(g(mv, k, "median_per_trade"), 2)
    for k in ("insample", "build", "2024", "2025", "2026", "unseen"):
        row[f"B_share_profitable_{k}"] = r0(g(Bb, "share_profitable", k), 3)
    for k in ("2025", "2026"):
        row[f"B_saved_profitable_{k}"] = r0(g(Bb, "saved_profitable", k))
    for k in ("2025", "2026", "unseen"):
        row[f"C_spearman_{k}"] = r0(g(C, k, "spearman"), 3)
        row[f"C_top_third_{k}"] = r0(g(C, k, "top_third_avg_net"), 2)
        row[f"C_bottom_third_{k}"] = r0(g(C, k, "bottom_third_avg_net"), 2)
        row[f"D_p_beat_{k}"] = r0(g(D, k, "p_beat"), 4)
        row[f"D_lift_{k}"] = r0(g(D, k, "lift"), 2)
    for k in ("2025", "2026"):
        row[f"D_days_p_beat_{k}"] = r0(g(D, k, "days_p_beat"), 4)
    for k in ("unseen_net", "traded_days", "net_without_best3", "best5pct_days", "net_without_best5pct", "t_daily", "t_daily_2025", "t_daily_2026", "t_daily_insample"):
        row[f"E_{k}"] = r0(E[k], 2)
    for k in ("2025", "2026", "unseen"):
        row[f"F_stress_avg_net_{k}"] = r0(g(F, k, "stress_avg_net"), 2)
        row[f"F_fast_net_share_{k}"] = r0(g(F, k, "fast_net_share"), 3)
        row[f"F_net_fast_{k}"] = r0(g(F, k, "net_fast"), 2)
    for y in range(2021, 2027):
        row[f"G_per_trade_{y}"] = r0(g(G, str(y), "per_trade"), 2)
    row["overfit_reasons"] = "; ".join(R["label"]["overfit_reasons"])
    row["holding_up_failed"] = "; ".join(R["label"]["holding_up_failed"])
    return row


if __name__ == "__main__":
    res = [do(a) for a in UNITS]
    (OUT / "diagnostics.json").write_text(json.dumps({"rules": {"edge_kept": "average-variant net per trade, unseen years together / in-sample (BUILD + 2024)",
        "kept_bad": KEPT_BAD, "kept_good": KEPT_GOOD, "random_bad_together": RAND_BAD_TOGETHER, "random_good_each": RAND_GOOD_EACH, "rho_bad": RHO_BAD,
        "fast": f"held under {FAST_S} whole seconds (judge.fast_share)", "traded_day": "a day on which at least one variant traded"}, "units": res}, indent=1))
    rows = [flat(r) for r in res]
    with (OUT / "diagnostics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(json.dumps(r))
