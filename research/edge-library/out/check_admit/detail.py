"""CHECKER: 5-unit recompute (own code), PICK plateaus, surviving sets, member claims, stage D, from-scratch re-runs."""
import json, sys, math, csv, collections, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, str(W / "out" / "check_admit"))
from scan import load, cells_in, plateau, tstat, SC, SESS7
sys.path.insert(0, str(W / "engine"))
BARS = json.loads((W / "out/check_admit/bars.json").read_text())["bars"]
P = lambda *a: print(*a, flush=True)


def cell(meta, a, cid, sess):
    i = next(k for k, c in enumerate(meta["cells"]) if c["id"] == cid)
    s, e = int(a["off"][i]), int(a["off"][i + 1])
    m = a["sess"][s:e] == SC[sess]
    return {k: a[k][s:e][m] for k in ("date", "entry_ms", "dur_s", "net", "mae", "side", "risk", "reason")}


def c1(member, pool, K=400, seed=777):
    rng = np.random.default_rng(seed)
    by = collections.defaultdict(list)
    for i, d in enumerate(pool["date"].tolist()):
        by[d].append(i)
    pn = pool["net"].astype(float); pdte = pool["date"].astype(np.int64)
    need = collections.Counter(member["date"].tolist())
    nets = np.zeros(K); fb = 0
    plan = []
    for d, k in sorted(need.items()):
        own = np.array(by.get(d, []), np.int64)
        if len(own) < k:
            other = np.flatnonzero(pdte != d)
            dist = np.abs(pdte[other] - d)
            cut = np.sort(dist)[k - len(own) - 1]
            ext = other[dist <= cut]; fb += k - len(own)
            plan.append((own, len(own), ext, k - len(own)))
        else:
            plan.append((own, k, None, 0))
    for j in range(K):
        t = 0.0
        for own, ko, ext, ke in plan:
            if ko:
                t += pn[own].sum() if ko == len(own) else pn[rng.choice(own, ko, replace=False)].sum()
            if ke:
                t += pn[rng.choice(ext, ke, replace=False)].sum()
        nets[j] = t
    mn = float(member["net"].sum())
    return {"lift": round(mn - nets.mean()), "ctrl_mean": round(nets.mean()), "p_beat": round(float((mn > nets).mean()), 3), "fallback": round(fb / max(1, len(member["net"])), 3)}


def pool_of(meta, a, xid, sess):
    parts = [cell(meta, a, f"s{sd}_{xid}", sess) for sd in (1, 2)]
    return {k: np.concatenate([p[k] for p in parts]) for k in ("date", "net")}


def years(x, cal):
    """per-year + combined: trades, net, win, pf, maxdd (daily), sharpe (daily, calendar days)"""
    out = []
    d = np.array([dt.date.fromordinal(int(o)).year for o in x["date"]]); cy = np.array([dt.date.fromordinal(int(o)).year for o in cal])
    for y in sorted(set(cy.tolist())) + ["all"]:
        m = np.ones(len(d), bool) if y == "all" else d == y
        c = cal if y == "all" else cal[cy == y]
        net = x["net"][m].astype(float)
        daily = np.zeros(len(c)); np.add.at(daily, np.searchsorted(c, x["date"][m]), net)
        cum = np.concatenate(([0.0], np.cumsum(daily)))
        dd = float((np.maximum.accumulate(cum) - cum).max())
        gw, gl = net[net > 0].sum(), -net[net < 0].sum()
        out.append((y, len(net), round(net.sum()), round(100 * (net > 0).mean(), 1) if len(net) else None, round(gw / gl, 2) if gl else None,
                    round(dd), round(daily.mean() / daily.std(ddof=1) * math.sqrt(252), 2) if daily.std() > 0 else None))
    return out


def pick_plateau(key, sess, lab=""):
    mb, ab = load(W / "runs" / key); mp, ap = load(W / "runs_admit" / f"{key}-{sess}-pick")
    rb, rp = cells_in(mb, ab, sess), cells_in(mp, ap, sess)
    alive_b = {r["vi"] for r in rb if r["n"]}
    # (a) analyst's rule: BUILD dead flags, identical lists once (empty lists merge)   (b) every BUILD-alive cell counted one by one
    live = sorted((r for r in rp if r["vi"] in alive_b), key=lambda r: (r["vi"], r["xi"]))
    seen, j = set(), []
    for r in live:
        if r["sig"] in seen: continue
        seen.add(r["sig"]); j.append(r)
    na = np.array([r["net"] for r in j]); nb = np.array([r["net"] for r in live])
    pb = plateau(rb)
    return {"build": (pb["cells"], round(pb["share"], 4), round(pb["median"], 1), pb["member"], round(pb["t"], 3), pb["pass"]),
            "pick_dedup": (len(j), round(float((na > 0).mean()), 4), round(float(np.median(na)), 1), bool(np.median(na) > 0 and (na > 0).mean() >= 0.6)),
            "pick_all_alive_cells": (len(live), round(float((nb > 0).mean()), 4), round(float(np.median(nb)), 1), bool(np.median(nb) > 0 and (nb > 0).mean() >= 0.6)),
            "pick_cells_no_trade": int(sum(r["n"] == 0 for r in live))}, rb, rp


if __name__ == "__main__":
    import l2sim as S, families as F
    cal = {(p, r): np.array([d.toordinal() for d in S.sessions(*S.period(p), r)]) for p in ("build", "pick") for r in ("NQ", "ES", "GC")}
    P("calendar NQ build/pick", len(cal[("build", "NQ")]), len(cal[("pick", "NQ")]))
    # ---------- 1. PICK heat maps of the 5 BUILD passers
    PK = {}
    for key, sess in (("orb-NQ-tf1", "pre"), ("donchian-NQ-tf30", "nyam"), ("donchian-NQ-tf30", "pm"), ("donchian-ES-tf30", "pm"), ("first_bar_mom-GC-tf5", "pm")):
        r, rb, rp = pick_plateau(key, sess); PK[(key, sess)] = (rb, rp)
        P("PICK", key, sess, r)
    # ---------- 2. surviving sets + default
    for key, sess in (("orb-NQ-tf1", "pre"), ("donchian-NQ-tf30", "nyam")):
        rb, rp = PK[(key, sess)]
        sb = {r["id"]: r["net"] for r in cells_in(*load(W / "runs_admit" / f"{key}-{sess}-build-stress"), sess)}
        sp = {r["id"]: r["net"] for r in cells_in(*load(W / "runs_admit" / f"{key}-{sess}-pick-stress"), sess)}
        b = {r["id"]: r for r in rb}; p = {r["id"]: r for r in rp}
        alive = {r["vi"] for r in rb if r["n"]}
        both = [i for i in b if b[i]["vi"] in alive and b[i]["net"] > 0 and p[i]["net"] > 0]
        surv = [i for i in both if sb.get(i, -1) > 0 and sp.get(i, -1) > 0]
        pl = plateau(rb)
        dflt = pl["member"] if pl["member"] in surv else min(surv, key=lambda i: abs(b[i]["net"] - pl["median"]))
        P("SURV", key, sess, "both-positive", len(both), "stress stores hold", len(sb), len(sp), "surviving", len(surv), "central", pl["member"],
          "central in set", pl["member"] in surv, "default", dflt, "| central: build", round(b[pl["member"]]["net"]), "pick", round(p[pl["member"]]["net"]),
          "stress build/pick", sb.get(pl["member"]), sp.get(pl["member"]), "| default t build", round(b[dflt]["t"], 3), "bar", round(BARS["c1-NQ"], 3),
          "| surviving cells with BUILD t > bar:", sum((b[i]["t"] or 0) > BARS["c1-NQ"] for i in surv))
    # ---------- 3. five units: controls, per-year
    def unit(key, sess, cid, tf, root="NQ", pick=False, label=""):
        m, a = load(W / "runs" / key); x = cell(m, a, cid, sess)
        xid = cid.rsplit("_", 1)[-1]
        pm_, pa_ = load(W / "runs" / f"c1-{root}-tf{tf}")
        r = {"build": (len(x["net"]), round(x["net"].sum()), round(tstat(x["net"].astype(float)), 3)), "c1_build": c1(x, pool_of(pm_, pa_, xid, sess))}
        xx = x
        if pick:
            mp, ap = load(W / "runs_admit" / f"{key}-{sess}-pick"); xp = cell(mp, ap, cid, sess)
            qm, qa = load(W / "runs_admit" / f"c1-{root}-tf{tf}-{sess}-pick")
            r["pick"] = (len(xp["net"]), round(xp["net"].sum()), round(tstat(xp["net"].astype(float)), 3)); r["c1_pick"] = c1(xp, pool_of(qm, qa, xid, sess))
            xx = {k: np.concatenate([x[k], xp[k]]) for k in x}
        c = np.concatenate([cal[("build", root)], cal[("pick", root)]]) if pick else cal[("build", root)]
        r["years"] = years(xx, c)
        P("UNIT", label or f"{key}|{sess}|{cid}", json.dumps(r, default=str))
        return xx
    orb = unit("orb-NQ-tf1", "pre", "or_min5_atr1p5-r2", "1", pick=True)
    don = unit("donchian-NQ-tf30", "nyam", "n10_pct0p2-r2", "30", pick=True, label="donchian default n10_pct0p2-r2")
    unit("donchian-NQ-tf30", "nyam", "n10_pts20-r2", "30", pick=True, label="donchian BUILD central n10_pts20-r2")
    mi, ai = load(W / "runs" / "ib-NQ-tf5"); rows = [r for r in cells_in(mi, ai, "mid") if r["variant"]["mode"] == "break"]; pl = plateau(rows)
    P("NEAR-MISS ib-NQ-tf5|mid|break plateau", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in pl.items()}, "bar", round(BARS["c1-NQ"], 4))
    unit("ib-NQ-tf5", "mid", pl["member"], "5")
    # straddle ES 08:30 + its time-shuffle null
    ms, as_ = load(W / "runs" / "straddle_t_0830-ES-tf30"); rows = cells_in(ms, as_, "all"); pl = plateau(rows)
    mn, an = load(W / "runs" / "straddle_t_0830-ES-tf30-shift"); nr = {r["id"]: r for r in cells_in(mn, an, "all")}
    best = max(rows, key=lambda r: r["t"] or -9)
    P("STRADDLE ES 08:30", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in pl.items()}, "| central vs shift seeds", [round(nr[f"s{sd}_{pl['member']}"]["net"]) for sd in (1, 2)] if pl["member"] else None,
      "| best cell t", round(best["t"], 2), "bar", round(BARS["shift-ES"], 2), "| shift seeds share>0", [round(float(np.mean([r["net"] > 0 for r in nr.values() if r["id"].startswith(f's{sd}_')])), 3) for sd in (1, 2)])
    x = {k: np.concatenate([as_[k][int(as_["off"][i]):int(as_["off"][i + 1])] for i in [next(j for j, c in enumerate(ms["cells"]) if c["id"] == (pl["member"] or best["id"]))]]) for k in ("date", "net")}
    P("  years (cell %s)" % (pl["member"] or best["id"]), years(x, cal[("build", "ES")]))
    for nm in ("straddle_t_0830-NQ-tf30", "straddle_t_1800-NQ-tf30", "straddle_t_0300-NQ-tf30", "straddle_t_1105-NQ-tf30"):
        m2, a2 = load(W / "runs" / nm); pl2 = plateau(cells_in(m2, a2, "all")); m3, a3 = load(W / "runs" / (nm + "-shift")); n3 = {r["id"]: r for r in cells_in(m3, a3, "all")}
        P("  ", nm, "central", pl2["member"], "net", round(pl2["net"]), "t", round(pl2["t"], 2), "lift vs shift mean", round(pl2["net"] - np.mean([n3[f"s{sd}_{pl2['member']}"]["net"] for sd in (1, 2)])))
    # ---------- 4. stage D: orb_fbook-NQ-tf1 pre vs base, + the summary's aggregates
    mb, ab = load(W / "runs" / "orb-NQ-tf1")
    for nm in ("orb_fbook-NQ-tf1", "orb_thin-NQ-tf1", "orb_xbook-NQ-tf1"):
        mv, av = load(W / "runs" / nm)
        b = {r["id"]: r for r in cells_in(mb, ab, "pre")}; v = {r["id"]: r for r in cells_in(mv, av, "pre")}
        nulls = [{r["id"]: r for r in cells_in(*load(W / "runs" / f"{nm}-c2s{sd}"), "pre")} for sd in (1, 2) if (W / "runs" / f"{nm}-c2s{sd}").exists()]
        ids = list(b)
        d = np.array([v[i]["net"] - b[i]["net"] for i in ids])
        dn = np.mean([[n[i]["net"] - b[i]["net"] for i in ids] for n in nulls], axis=0) if nulls else None
        P("STAGE D", nm, "pre: median d", round(float(np.median(d))), "share d>0", round(float((d > 0).mean()), 3), "kept", round(sum(v[i]["n"] for i in ids) / sum(b[i]["n"] for i in ids), 3),
          "share d>null", None if dn is None else round(float((d > dn).mean()), 3), "variant plateau", plateau(list(v.values()))["pass"], round(plateau(list(v.values()))["share"], 3))
    sd = pd.read_csv(W / "out/admit/stage_d_paired.csv")
    sd["opt"] = sd.key.str.extract(r"_(fbook|thin|xbook)-")
    P("STAGE D csv:", sd[sd.key == "orb_fbook-NQ-tf1"][["sess", "median_d", "share_d_pos", "trades_kept_share", "share_d_above_null"]].to_dict("records"))
    P("STAGE D aggregates:", {o: {"n": len(g), "median of median_d": round(g.median_d.median()), "d>0 units": int((g.median_d > 0).sum()), "added": int((g.added == True).sum()),
                                  "kept": round(g.trades_kept_share.median(), 2), "share_above_null min/med/max": (round(g.share_d_above_null.min(), 2), round(g.share_d_above_null.median(), 2), round(g.share_d_above_null.max(), 2)),
                                  "no_null": int(g.share_d_above_null.isna().sum())} for o, g in sd.groupby("opt")})
    # ---------- 5. member claims from the member folders
    for name, x in (("orb_NQ_tf1_pre", orb), ("donchian_NQ_tf30_nyam", don)):
        T = json.loads((W / "members" / name / "trades_build.json").read_text()) + json.loads((W / "members" / name / "trades_pick.json").read_text())
        net = np.array([t["net"] for t in T]); dur = np.array([(t["exit_ms"] - t["entry_ms"]) / 1000 for t in T]); side = np.array([1 if t["side"] == "long" else -1 for t in T])
        et = pd.DatetimeIndex(np.array([t["entry_ms"] for t in T]) * 1_000_000, tz="UTC").tz_convert("America/New_York")
        xt = pd.DatetimeIndex(np.array([t["exit_ms"] for t in T]) * 1_000_000, tz="UTC").tz_convert("America/New_York")
        reasons = collections.Counter(t["exit_reason"] for t in T)
        tm = collections.Counter(xt[i].strftime("%H:%M") for i, t in enumerate(T) if t["exit_reason"] not in ("sl", "tp"))
        slip_e = np.array([(t["entry_price"] - t["order_price"]) * (1 if t["side"] == "long" else -1) / 0.25 for t in T if t.get("order_price") is not None] or [float("nan")])
        slip_x = np.array([(t["sl"] - t["exit_price"]) * (1 if t["side"] == "long" else -1) / 0.25 for t in T if t["exit_reason"] == "sl"] or [float("nan")])
        risk = np.array([abs(t["entry_price"] - t["sl"]) for t in T]); mic = np.maximum(1, np.rint(1000 / (risk * 2)))
        szn = mic * ((net + 4) / 10 - 1)
        P("MEMBER", name, "trades", len(T), "net", round(net.sum()), "max date", max(t["date"] for t in T), "store match", len(x["net"]) == len(T) and abs(x["net"].sum() - net.sum()) < 0.01,
          "| reasons", dict(reasons), "| non-stop/target exit minutes", dict(tm), "| latest exit", max(xt.strftime("%H:%M:%S")), "| entry minutes top", collections.Counter(et.strftime("%H:%M")).most_common(3),
          "| <=2s", int((dur <= 2).sum()), round(net[dur <= 2].sum()), "| long/short", round(net[side > 0].sum()), round(net[side < 0].sum()),
          "| worst mae", max(t["mae_usd"] for t in T), "micros fit", math.floor(2000 / (max(abs(t["mae_usd"]) for t in T) / 10 + 1)),
          "| $1000-risk net", round(szn.sum()), "| entry slip ticks: min/median/max", slip_e.min(), np.median(slip_e), slip_e.max(), "share>1tick", round(float((slip_e > 1.01).mean()), 3),
          "| sl exit slip ticks median/max", np.median(slip_x), slip_x.max(), "| stop pts median", np.median(risk))
        if name.startswith("orb"):
            f = dur <= 2
            P("   fast trades: reasons", collections.Counter(T[i]["exit_reason"] for i in np.flatnonzero(f)), "entry slip max (ticks)", slip_e[f].max(), "win", round(float((net[f] > 0).mean()), 2),
              "| net without the <=2 s trades", round(net[~f].sum()), "| 08:30-minute entries share", round(float((et.strftime("%H:%M") == "08:30").mean()), 3))
    # loss-day overlap
    D = {n: pd.read_csv(W / "members" / n / "daily.csv").set_index("date") for n in ("orb_NQ_tf1_pre", "donchian_NQ_tf30_nyam")}
    a, b = D["orb_NQ_tf1_pre"], D["donchian_NQ_tf30_nyam"]
    for lab, m in (("2024", a.period == "pick"), ("all", a.period != "")):
        la, lb = (a.net[m] < 0), (b.net.reindex(a.index)[m] < 0)
        P("OVERLAP", lab, "orb loses on", round(la.mean(), 3), "don loses on", round(lb.mean(), 3), "orb->don", round((la & lb).sum() / la.sum(), 3), "don->orb", round((la & lb).sum() / lb.sum(), 3),
          "corr", round(np.corrcoef(a.net[m], b.net.reindex(a.index)[m])[0, 1], 3), "days", int(m.sum()))
    # ---------- 6. from-scratch re-runs (not booked in the ledger: checker runs)
    def rerun(fam, key, cid, sess, tf, per, stress):
        m = json.loads((W / "runs" / key / "run.json").read_text()); c = next(c for c in m["cells"] if c["id"] == cid)
        params = {**F.REGISTRY[fam][1], "tf": tf, "sess": sess, **c["variant"], **c["exit"], "hold_to": "day"}
        kw = {"slip_ticks": 2.0, "latency_ms": 250} if stress else {}
        res = S.run(F.REGISTRY[fam][0], params, period=per, root="NQ", workers=4, **kw)
        return [t for t in res["trades"] if S.session_of(t["entry_ms"]) == sess], res
    for fam, key, cid, sess, tf, name in (("orb", "orb-NQ-tf1", "or_min5_atr1p5-r2", "pre", "1", "orb_NQ_tf1_pre"), ("donchian", "donchian-NQ-tf30", "n10_pct0p2-r2", "nyam", "30", "donchian_NQ_tf30_nyam"),
                                          ("donchian", "donchian-NQ-tf30", "n10_pts20-r2", "nyam", "30", None)):
        for per in ("build", "pick"):
            tr, res = rerun(fam, key, cid, sess, tf, per, False)
            ts, _ = rerun(fam, key, cid, sess, tf, per, True)
            line = [f"RERUN {key} {cid} {per}: trades {len(tr)} net {round(sum(t['net'] for t in tr))} | stressed trades {len(ts)} net {round(sum(t['net'] for t in ts))}",
                    f"max date {max(t['date'] for t in tr)}", f"exit reasons {dict(collections.Counter(t['exit_reason'] for t in tr))}"]
            if name:
                ref = json.loads((W / "members" / name / f"trades_{per}.json").read_text())
                k = lambda t: (t["date"], t["side"], t["entry_ms"], t["exit_ms"], t["entry_price"], t["exit_price"], t["exit_reason"], round(t["net"], 2))
                line.append(f"identical to members/ trades: {sorted(map(k, tr)) == sorted(map(k, ref))} ({len(ref)} stored)")
                sref = json.loads((W / "out/admit/member_runs" / f"{name}-{cid}-{per}-stress.json").read_text())["trades"]
                line.append(f"stress identical to analyst's: {sorted(map(k, ts)) == sorted(map(k, sref))}")
            se = np.array([(t["entry_price"] - t["order_price"]) * (1 if t["side"] == "long" else -1) / 0.25 for t in ts if t.get("order_price") is not None] or [float("nan")])
            be = np.array([(t["entry_price"] - t["order_price"]) * (1 if t["side"] == "long" else -1) / 0.25 for t in tr if t.get("order_price") is not None] or [float("nan")])
            line.append(f"entry slip ticks base min/med {be.min() if len(be) else None}/{np.median(be) if len(be) else None} stress min/med {se.min() if len(se) else None}/{np.median(se) if len(se) else None}")
            xt = pd.DatetimeIndex(np.array([t["exit_ms"] for t in tr if t["exit_reason"] not in ("sl", "tp")]) * 1_000_000, tz="UTC").tz_convert("America/New_York")
            line.append(f"clock exits at {dict(collections.Counter(xt.strftime('%H:%M')))}")
            P(" | ".join(line))
