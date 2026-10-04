#!/usr/bin/python3
"""Part 2: loader spot-check, session purity, caps / conflicts, the 50% net guard, consistency+min-days audit of every pass, and a cross-check of the eod
race against the Homebase engine propsim.run_eval on the very daily series each attempt used."""
import json, sys, datetime as dt
import numpy as np
from pathlib import Path
from zoneinfo import ZoneInfo
import verify_indep as V
import evalcore as E
from homebase.backtest.propsim import propsim as PS

R = Path(__file__).resolve().parent
OUT = R / "out"
ET = ZoneInfo("America/New_York")
res = json.load(open(OUT / "portfolio_results.json"))
rep_out = {"loader": [], "specs": {}}

# ---------------- loader spot check on every distinct source used
srcs = {}
for node in (res["firms"], res["fast_objective"]["firms"]):
    for f, F in node.items():
        for c in F["pool"]:
            srcs[c["src"]] = c
bad = []
SE = {"asia": 180, "london": 505, "nyam": 660, "mid": 810, "pm": 958}
sess_end_viol = 0
tot_tr = 0
for src, c in srcs.items():
    t = E.load(src)
    d = E._src_dir(src)
    rows = json.loads((d / "trades.json").read_text())
    rows = rows if isinstance(rows, list) else rows.get("trades", [])
    rows = [x for x in rows if x["date"] < "2025-01-01"]
    n_bad = 0
    if len(rows) != t.n:
        n_bad += 1
    for i, x in enumerate(rows):
        q = max(1.0, float(x.get("qty") or 1))
        ok = (abs(float(x["gross"]) / q - t.g[i]) < 1e-9 and int(x["entry_ms"]) == t.te[i]
              and abs(abs(float(x["mae_usd"])) / q - t.mae[i]) < 1e-9 if x.get("mae_usd") is not None else True)
        # date field = ET date of entry
        ed = dt.datetime.fromtimestamp(int(x["entry_ms"]) / 1000, ET).date().isoformat()
        if not ok or ed != x["date"] or V.sess_of(int(x["entry_ms"])) != (None if t.sess[i] < 0 else list(E.SESS)[t.sess[i]]):
            n_bad += 1
        # session purity: a trade entered in a session must be flat by that session's end (sessions independent)
        s = V.sess_of(int(x["entry_ms"]))
        if s:
            xm = dt.datetime.fromtimestamp(int(x.get("exit_ms", x["entry_ms"])) / 1000, ET)
            if xm.date().isoformat() != x["date"] or xm.hour * 60 + xm.minute > SE[s]:
                sess_end_viol += 1
        tot_tr += 1
    if n_bad:
        bad.append((src, n_bad))
rep_out["loader"] = {"sources": len(srcs), "trades_checked": tot_tr, "bad_sources": bad, "exit_after_session_end_or_next_day": sess_end_viol}
print("loader:", rep_out["loader"], flush=True)

# data sanity of MAE/MFE vs final: mae >= -g (loss within MAE), mfe >= g
viol_mae = viol_mfe = 0
for src in srcs:
    t = E.load(src)
    viol_mae += int((t.mae + 1e-9 < -t.g).sum())
    viol_mfe += int((t.mfe + 1e-9 < t.g).sum())
rep_out["mae_lt_loss"] = viol_mae; rep_out["mfe_lt_pnl"] = viol_mfe
print("trades with MAE < realised loss:", viol_mae, " MFE < pnl:", viol_mfe, flush=True)
for n in (1, 7, 10, 25, 40, 100):
    assert abs(V.cost(n) - E.cost(n)) < 1e-12
assert abs(V.TICK - E.TICK_USD) < 1e-12

# ---------------- per spec audits
CAL = None
for fam, node in (("main", res["firms"]), ("fast", res["fast_objective"]["firms"])):
    for f, F in node.items():
        pool = {c["cid"]: c for c in F["pool"]}
        for lab in ("single", "best2", "portfolio"):
            rep = F["reports"].get(lab)
            if not rep or "cell" not in rep:
                continue
            members = [(pool[m["name"]]["src"], pool[m["name"]]["sess"], m["micros"]) for m in rep["members"]]
            c = rep["cell"]
            rules = {k: c[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}
            sp = V.Spec(f, members, rules, CAL)
            CAL = CAL or sp.cal
            prim = F["primary"]
            ro = V.raw_overlap(sp)
            # executed-walk stats over the whole calendar (base walk, no target rule)
            ex = dict(overlap=0, conflicts=0, max_conc=0, cap_viol=0, executed=0, skipped=0)
            for i in range(sp.D):
                d = sp.day(i)
                for k in ("overlap", "conflicts", "cap_viol", "skipped"):
                    ex[k] += d.stat[k]
                ex["max_conc"] = max(ex["max_conc"], d.stat["max_conc"])
                ex["executed"] += len(d.execd)
            raw = V.member_nets(sp)
            pos = [max(x, 0.0) for x in raw]
            sh = [x / sum(pos) if sum(pos) > 0 else float("nan") for x in pos]
            # standalone under the SAME rules
            st_net = []
            for mi in range(len(members)):
                s1 = V.Spec(f, [members[mi]], rules, sp.cal)
                st_net.append(sum(s1.day(i).tot for i in range(s1.D)))
            ps = [max(x, 0.0) for x in st_net]
            sh_rules = [x / sum(ps) if sum(ps) > 0 else float("nan") for x in ps]
            # static per-session cap
            bysess = {}
            for (_, s, n) in members:
                bysess[s] = bysess.get(s, 0) + n
            # audit every pass of the primary model: consistency, min days, eod cross-check with propsim.run_eval
            aud = dict(n_pass=0, n_cons_viol=0, n_mindays_viol=0, eod_oracle_mismatch=0, eod_checked=0)
            for m in V.MODELS:
                for s in range(sp.S):
                    o, dd = sp.race(s, m)
                    used = sp.used
                    if m == prim and o == 1:
                        aud["n_pass"] += 1
                        pn = [u[0] for u in used[:dd]]
                        tr = [u[1] for u in used[:dd]]
                        tdn = sum(tr)
                        tot = sum(pn)
                        big = max(pn)
                        cons = sp.r.get("consistency")
                        if cons is not None and big > cons * tot + 1e-6:
                            aud["n_cons_viol"] += 1
                        if tdn < sp.r["eval_min_days"] or tot < sp.r["eval_target"] - 1e-6:
                            aud["n_mindays_viol"] += 1
                    if m == "eod":
                        # Homebase engine on the daily pnls the attempt used (clamped by its own _cap_day); outcome and day must agree
                        e = PS.run_eval([(u[0], bool(u[1])) for u in used], sp.r)
                        want = {"pass": 1, "bust": 2, "timeout": 0}[e["outcome"]]
                        got = (o, dd)
                        aud["eod_checked"] += 1
                        if want != o or (o and e["day"] != dd):
                            aud["eod_oracle_mismatch"] += 1
            rep_out["specs"][f"{fam}:{f}:{lab}"] = {
                "members": [(m["name"], m["micros"]) for m in rep["members"]], "rules": rules,
                "raw_overlap": ro, "reported_raw_overlap": rep.get("raw_overlap"),
                "executed": ex, "reported_walk": rep.get("walk"),
                "raw_net": raw, "raw_shares": sh, "reported_max_net_share": rep["guards"]["max_net_share"],
                "rules_standalone_net": st_net, "rules_shares": sh_rules,
                "static_session_micros": bysess, "cap": sp.cap, "audit": aud}
            print(f"{fam:4s} {f:15s} {lab:9s} overlapEntries(raw)={ro['overlap_entries']} opp={ro['opposite_overlaps']} maxconc={ro['max_concurrent_micros']}/{sp.cap} capviol={ro['cap_violations']}"
                  f" | exec: overlap={ex['overlap']} conflicts={ex['conflicts']} maxconc={ex['max_conc']} capviol={ex['cap_viol']}"
                  f" | maxshare raw {max([x for x in sh if x==x] or [float('nan')]):.3f} (rep {rep['guards']['max_net_share']}) rules {max([x for x in sh_rules if x==x] or [float('nan')]):.3f}"
                  f" | pass={aud['n_pass']} cons_viol={aud['n_cons_viol']} mind_viol={aud['n_mindays_viol']} oracle_mis={aud['eod_oracle_mismatch']}/{aud['eod_checked']}", flush=True)
json.dump(rep_out, open(OUT / "verify_part2.json", "w"), indent=1, default=str)
