"""ADMISSION v2, step 3: SAVE every unit that passes all six tests (final.json): members/<name>/ with surviving_set.csv, spec.json
(the DEFAULT = the middle survivor by BUILD net), trades + daily.csv of the default, card.md. Re-judges the folders already in
members/, members/_demoted, members/_rejected: a member that fails v2 moves to members/_v1_only/ with the reason; a demoted /
rejected folder gets v2_rejudge.md. Groups the members that are the same idea -> out/v2_members.md, out/v2/members.json.
  python out/v2/admit_v2.py"""
from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2 as V  # noqa: E402
import importlib.util  # noqa: E402

_sp = importlib.util.spec_from_file_location("v2_judge_pick", HERE / "judge_pick.py")   # out/events also holds a judge_pick.py
JP = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(JP)
import run_v2 as RV2  # noqa: E402
import l2sim as S  # noqa: E402
import families as F  # noqa: E402

LB = V.LB
MR = V.OUT / "member_runs"
MEM = LB.MEMBERS
SESS_PLAIN = {"eve": "evening (18:00-23:59 ET, the evening before the trade date)", "asia": "Asia (00:00-03:00 ET)",
              "london": "London (03:00-08:25 ET)", "pre": "pre-market (08:25-09:30 ET)", "nyam": "New York morning (09:30-11:00 ET)",
              "mid": "midday (11:00-13:30 ET)", "pm": "afternoon (13:30-15:58 ET)"}
TIGHT_OFF = {"NQ": {"A": 3, "B": 5, "C": 8}, "ES": {"A": 0.75, "B": 1.25, "C": 2}, "GC": {"A": 0.6, "B": 1, "C": 1.6}}
IDEA = {"donchian": "channel breakout", "donchian_thin": "channel breakout into a thin book (Level 2)", "ema_pullback": "trend pullback to the 20-bar average",
        "first_bar_mom": "first-bar momentum", "flow_exhaust": "exhaustion fade (order flow)", "ib": "first-hour range break",
        "orb": "opening range break", "rsi2": "2-bar RSI fade", "squeeze": "squeeze release", "supertrend": "Supertrend flip",
        "tema_slope": "fast-average slope turn", "tod_drift": "time-of-day drift", "vwap_band": "VWAP band fade", "vwap_flip": "VWAP side change",
        "orb_confirm": "opening range break on a bar close (one direction)", "vol_spike_break": "high-volume range break",
        "vwap_trend_pull": "VWAP trend pullback", "lon_break": "London range break", "gap": "gap", "pinbar": "pin bar", "sweep_rev": "sweep reversal",
        "vwap_z": "VWAP distance fade", "ema_ribbon": "average ribbon", "straddle": "session-open bracket", "va_reclaim": "value-area reclaim",
        "bimb_follow_d1": "book-imbalance follow (Level 2)"}


def idea_of(u: dict) -> str:
    f = u["family"]
    if f.startswith("straddle_tight_"):
        s = f"tight bracket at {f[-4:-2]}:{f[-2:]} ET"
    elif f.startswith("straddle_wide_"):
        s = f"wide bracket at {f[-4:-2]}:{f[-2:]} ET"
    elif f.startswith("straddle_t_"):
        s = f"bracket at {f[11:13]}:{f[13:15]} ET" + (" + Level 2 option" if u["stage_d"] else "")
    elif f.startswith("event_dir_"):
        s = f"market order with the first move after {f[-4:-2]}:{f[-2:]} ET"
    else:
        s = IDEA.get(f, f)
    if u["label"]:
        s += f" ({u['label'].split('=')[1]} only)" if u["label"].startswith("dir=") else ""
    if u["group"]:
        s += {"A": ", 08:30 release days", "B": ", tier-1 08:30 release days", "C": ", 10:00 release days"}[u["group"]]
    if u["side"]:
        s += {"vol_lo": ", quiet days only", "news_only": ", CPI / jobs / Fed days only"}[u["side"]]
    return s


def rule_text(u: dict, cell: dict) -> str:
    f, v, tf, root = u["family"], cell["variant"], u["tf"], u["root"]
    b = u["base"] or f
    if b == "donchian":
        t = f"When a {tf}-minute bar closes above the highest high (or below the lowest low) of the {v['n']} bars before it, enter at market in that direction."
    elif b == "ema_pullback":
        t = f"Trend = the slope of the 50-bar average ({tf}-minute bars). In an up-trend, when a bar dips to the 20-bar average and closes back above it, buy; the mirror for sells."
    elif b == "first_bar_mom":
        t = f"If the session's first {tf}-minute bar is at least {v['k']:g} x the average bar range, enter in its direction at its close."
    elif b == "flow_exhaust":
        t = (f"A {tf}-minute bar with very heavy one-sided aggressive volume (top {100 - v['q']:g} % of the last 60 bars) makes a new session high (low) "
             "but closes in the wrong half of its range: trade against it at market.")
    elif b == "ib":
        t = ("The first hour (09:30-10:30 ET) sets the range. From 10:30 a buy stop rests at its high and a sell stop at its low (one cancels the other)."
             if v.get("mode") == "break" else "After a close beyond the first-hour range, the first close back inside is faded to the middle of the range.")
    elif b == "orb":
        t = f"Range = the first {v['or_min']} minutes of the session. A buy stop one tick above it and a sell stop one tick below (one cancels the other)."
    elif b == "rsi2":
        t = f"At a {tf}-minute close: 2-bar RSI below {v['th']:g} -> buy; above {100 - v['th']:g} -> sell (a fade)."
    elif b == "squeeze":
        t = {"bbkc": f"Bollinger bands inside the Keltner channel for 3+ {tf}-minute bars, then they open: enter toward the side of the close.",
             "nr7": "After the narrowest bar of seven: a buy stop at its high and a sell stop at its low for one bar (one cancels the other).",
             "inside": "After an inside bar: a buy stop at its high and a sell stop at its low for one bar (one cancels the other)."}[v["sq_type"]]
    elif b == "supertrend":
        t = f"Supertrend(10, 3) on {tf}-minute bars flips at a bar close: enter in the new direction; the stop is the Supertrend line."
    elif b == "tema_slope":
        t = f"The slope of the triple-smoothed {v['n']}-bar average ({tf}-minute bars) changes sign at a bar close: enter in the new direction."
    elif b == "tod_drift":
        t = f"{'Buy' if v['dir'] == 'long' else 'Sell'} at market {v['off_min']} minutes after the session starts; out after 6 bars of {tf} minutes, the stop or the session end. One trade a session."
    elif b == "vwap_band":
        t = f"A {tf}-minute bar closes back inside session VWAP +/- {v['band']:g} standard deviations after a close outside: trade back toward VWAP."
    elif b == "vwap_flip":
        t = f"A {tf}-minute close crosses session VWAP and the next {v['hold']} close(s) stay on the new side: enter with the new side."
    elif b == "orb_confirm":
        t = (f"Range = the first {v['or_min']} minutes from 09:30 ET. When a {tf}-minute bar CLOSES {'above' if v['dir'] == 'long' else 'below'} it, "
             f"{'buy' if v['dir'] == 'long' else 'sell'} at market. {'Long' if v['dir'] == 'long' else 'Short'} only, one trade per session.")
    elif b == "vol_spike_break":
        t = f"A {tf}-minute bar closes beyond the high / low of the 20 bars before it on volume at least {v['m']:g} x their median: enter in that direction. At most 2 trades a session."
    elif b == "vwap_trend_pull":
        t = (f"Price is above a rising 09:30 VWAP and up at least {v['x']:g} % over 60 minutes: buy the first down bar ({tf}-minute bars); the mirror for sells. "
             "Entries 10:30-15:30 ET, at most 4 trades, stop for the day after 2 losers.")
    elif b.startswith("straddle_tight_"):
        hh = f"{b[-4:-2]}:{b[-2:]}"
        t = (f"One second before {hh} ET: a buy stop {TIGHT_OFF[root][v['off']]:g} points above the price and a sell stop {TIGHT_OFF[root][v['off']]:g} points below "
             "(one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day.")
    elif b.startswith("straddle_t_"):
        hh = f"{b[11:13]}:{b[13:15]}"
        t = (f"At {hh} ET: a buy stop above and a sell stop below the last price (distance `{v['off']}`: a fraction of the 30-minute average range, or fixed points); "
             "one cancels the other; unfilled orders are cancelled after 60 minutes. One trade a day.")
    else:
        t = F.REGISTRY[b][3]
    if u["stage_d"]:
        t += " Level 2 option: " + {"thin": "only when the book on the trade's side is thin.", "fbook": "skip when the 5-minute book imbalance opposes the trade.",
                                    "xbook": "leave when the book imbalance flips against the trade for 2 minutes."}[f.rsplit("_", 1)[1]]
    x = cell["exit"]
    stop = {"atr": f"{x['stop_val']:g} x the average bar range (ATR)", "pts": f"{x['stop_val']:g} points", "pct": f"{x['stop_val']:g} % of price"}.get(
        x["stop_mode"], f"{x['stop_mode']} {x['stop_val']}")
    tgt = "no target (out at the stop or at the flat time)" if not x.get("tgt_r") else f"target {x['tgt_r']:g} x the stop"
    days = ""
    if u["group"]:
        import ev as E
        days = f" Traded ONLY on {E.PLAIN[u['group']]}."
    if u["side"]:
        import labels as L
        days = f" Traded {L.PLAIN[u['side']]}."
    return f"{t} Stop {stop}; {tgt}. Session: {SESS_PLAIN[u['sess']]}; flat by 15:58 ET.{days}"


def default_runs(todo: list) -> None:
    """Full trade rows of every default variant (BUILD, 2024, both under stress): one tape pass per (market, period, stress
    setting), the menu's own spec (run_v2.job_grid). Cached in out/v2/member_runs/. One `member` run per row in the ledger."""
    MR.mkdir(exist_ok=True)
    tasks: dict = {}
    for u, cid, oco in todo:
        for per in ("build", "pick"):
            for stress in (False, True):
                p = MR / f"{V.member_name(u)}-{cid}-{per}{'-stress' if stress else ''}.json"
                if p.exists():
                    continue
                grid, cls, feats, timed = RV2.job_grid({"family": u["family"], "root": u["root"], "tf": u["tf"], "sess": u["sess"], "cells": [cid]})
                assert len(grid) == 1
                solo = feats is not None or u["family"] in RV2.L2I.STAGE_D
                k = (u["root"], per, stress, bool(oco and stress), json.dumps(getattr(cls, "SCREEN_RUN", {}), sort_keys=True), u["uid"] if solo else "")
                tasks.setdefault(k, []).append((u, cid, p, grid[0], feats, timed))
    for (root, per, stress, oco, skw, _), items in sorted(tasks.items(), key=lambda kv: str(kv[0])):
        kw = dict(S.STRESS) if stress else {}
        if oco:
            kw["costs"] = S.Costs(oco_cancel_ms=RV2.OCO_MS)
        kw.update(json.loads(skw))
        if per == "pick":
            with (V.OUT / "pick_reads.csv").open("a", newline="") as fh:
                w = csv.writer(fh)
                for u, cid, p, g, feats, timed in items:
                    w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), p.stem, u["family"], u["root"], u["tf"], u["sess"],
                                "member run (default variant)" + (" under stress" if stress else ""), 1,
                                "full trade rows for the card; same cell as the whole-menu pass"])
        LB.ledger_check(runs=len(items))
        S.wait_compute_window()
        res = S.run_many([g["spec"] for _, _, _, g, _, _ in items], period=per, root=root, workers=RV2.RM.auto_workers(), features=items[0][4], **kw)
        for (u, cid, p, g, feats, timed), r in zip(items, res):
            assert not r["skipped_by_error"], p.stem
            tr = r["trades"]
            if u["family"] in RV2.L2I.STAGE_D:
                tr = RV2.L2I.kept(tr)
            tr = [t for t in tr if S.session_of(t["entry_ms"]) == u["sess"]]      # the unit = this session's trades (as its table)
            p.write_text(json.dumps({"trades": tr, "inputs": r["meta"]["inputs"]}, separators=(",", ":"), default=str))
            LB.ledger_add("member", p.stem, "run", family=u["family"], root=root, tf=u["tf"], period=per, control="stress" if stress else "",
                          trades=len(tr), elapsed_s=r["elapsed_s"], note="admission v2: default variant, full trade rows")
        print(f"member runs {root} {per}{' stress' if stress else ''}{' oco' if oco else ''}: {len(items)} cells", flush=True)


def scoped(u: dict, trades: list) -> list:
    if not (u["group"] or u["side"]) or not trades:
        return trades
    o = np.array([dt.date.fromisoformat(t["date"]).toordinal() for t in trades])
    sd = np.array([1 if t["side"] == "long" else -1 for t in trades])
    m = V.day_mask(u, o, sd)
    return [t for t, k in zip(trades, m) if k]


def load_run(u: dict, cid: str, per: str, stress: bool) -> dict:
    d = json.loads((MR / f"{V.member_name(u)}-{cid}-{per}{'-stress' if stress else ''}.json").read_text())
    d["trades"] = scoped(u, d["trades"])
    return d


def money(v) -> str:
    return "n/a" if v is None else (f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}")


def pct(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f} %"


def fast_exact(trades: list) -> dict:
    gw = sum(t["net"] for t in trades if t["net"] > 0)
    fw = sum(t["net"] for t in trades if t["net"] > 0 and t["exit_ms"] - t["entry_ms"] <= 5000)
    fn = sum(t["net"] for t in trades if t["exit_ms"] - t["entry_ms"] <= 5000)
    return {"share": fw / gw if gw > 0 else None, "net_fast": fn, "n_fast": sum(1 for t in trades if t["exit_ms"] - t["entry_ms"] <= 5000)}


def year_rows_default(tr_b: list, tr_p: list, cal: list) -> list:
    x = LB.pack(tr_b + tr_p)
    return LB.per_year(x, cal)


def build_member(u: dict, b: dict, o: dict, fin: dict) -> dict:
    name, sess = V.member_name(u), u["sess"]
    bst = V.store(u["key"], period="build")
    brows = V.table(bst, u)
    bts = V.table_stats(brows)
    pst = JP.pick_store(f"{u['key']}-{sess}-pick")
    sst = JP.pick_store(f"{u['key']}-{sess}-pick-stress", [V.RV])
    bss = V.store(f"{u['key']}-{sess}-build-stress", V.RV, "build")
    prow = JP.table_on(pst, u, brows)
    pts = V.table_stats(prow)
    sts = V.table_stats(JP.table_on(sst, u, brows))
    cid = fin["default"]
    cell = next(c for c in bst["meta"]["cells"] if c["id"] == cid)
    cal_b, cal_p = LB.calendar("build", u["root"]), LB.calendar("pick", u["root"])
    cal = LB._ordinals(cal_b + cal_p)
    R = {(per, st): load_run(u, cid, per, st) for per in ("build", "pick") for st in (False, True)}
    for per, st_ in (("build", bst), ("pick", pst)):
        ref = V.cellx(st_, cid, sess, u)
        got = R[(per, False)]["trades"]
        assert len(got) == len(ref["net"]) and abs(sum(t["net"] for t in got) - float(ref["net"].sum())) < 0.01, (name, per, len(got), len(ref["net"]))
    for per, st_ in (("build", bss), ("pick", sst)):
        ref = V.cellx(st_, cid, sess, u)
        got = R[(per, True)]["trades"]
        assert abs(sum(t["net"] for t in got) - float(ref["net"].sum())) < 0.01, (name, per, "stress")
    # the average variant (the BUILD-judged variants, BUILD + 2024 trades of each)
    ids = bts["ids"]
    xs_b = [V.cellx(bst, c, sess, u) for c in ids]
    xs_p = [V.cellx(pst, c, sess, u) for c in ids]
    xs = [{k: np.concatenate([a[k], p[k]]) for k in LB.FIELDS} for a, p in zip(xs_b, xs_p)]
    avg_rows = V.avg_variant(xs, cal, [2021, 2022, 2023, 2024])
    d_rows = year_rows_default(R[("build", False)]["trades"], R[("pick", False)]["trades"], cal_b + cal_p)
    fast_avg = {"build": V.fast_share(xs_b), "pick": V.fast_share(xs_p), "all": V.fast_share(xs)}
    fast_def = fast_exact(R[("build", False)]["trades"] + R[("pick", False)]["trades"])
    # surviving set
    surv = fin["survivors"]
    rows = []
    net = lambda s, c: float(V.cellx(s, c, sess, u)["net"].sum())  # noqa: E731
    for c in surv:
        xb, xp = V.cellx(bst, c, sess, u), V.cellx(pst, c, sess, u)
        yr = {y: float(xb["net"][np.array([dt.date.fromordinal(int(d)).year == y for d in xb["date"]], bool)].sum()) if len(xb["net"]) else 0.0
              for y in (2021, 2022, 2023)}
        allx = np.concatenate([xb["net"], xp["net"]])
        s = LB.stats(allx)
        rows.append({"cell": c, "default": c == cid, "net_2021": round(yr[2021], 2), "net_2022": round(yr[2022], 2), "net_2023": round(yr[2023], 2),
                     "net_build": round(float(xb["net"].sum()), 2), "net_2024": round(float(xp["net"].sum()), 2), "trades_build": len(xb["net"]),
                     "trades_2024": len(xp["net"]), "stress_build": round(net(bss, c), 2), "stress_2024": round(net(sst, c), 2),
                     "win": round(s["win"], 4), "pf": round(s["pf"], 3) if s["pf"] else "", "net_combined": s["net"]})
    # flags
    bdet = json.loads(b["detail"]) if isinstance(b.get("detail"), str) else (b.get("detail") or {})
    flags = []
    if u["weak"]:
        flags.append("WEAK reason (the idea's reason is weak or only restates the trigger)")
    if u["penalty"]:
        flags.append("2025-26 penalty (the family's old favourite failed on 2025-26)")
    sl = F.library(u["base"] or u["family"]).get("second_look") if (u["base"] or u["family"]) in F.LIBRARY else None
    if sl and not u["penalty"]:
        flags.append("2025-26 was already seen once for this family's old favourite (an EXAM would be a second look)")
    if pst is not None and V.find_pick(f"{u['key']}-{sess}-pick") != V.RV:
        flags.append("SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage)")
    elif any(r["family"] == u["family"] and r["root"] == u["root"] and r["sess"] == sess and str(r["tf"]) != u["tf"] for r in EARLIER_READS):
        flags.append("2024 was already read for this idea at another bar size (an earlier stage)")
    if bst["meta"].get("both_sides_declared") and (sess == "pre" or u["group"]):
        flags.append("BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print "
                     "(out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went)")
    thin = [c for c in u["controls"] if c in ("shift", "c2")]
    if thin:
        flags.append("thin control (" + ", ".join({"shift": "random-minute store", "c2": "shuffled book"}[c] for c in thin) + ": 2 seeds on disk)")
    if b.get("exact60"):
        flags.append("exactly 60 % of variants profitable on BUILD")
    if u["label"].startswith("dir="):
        flags.append("one-direction unit compared with two-sided random entries (a tilted control)")
    if fast_avg["all"]["fast_profit_share"] is not None and fast_avg["all"]["fast_profit_share"] > 0.5:
        flags.append("FAST: more than 50 % of the average variant's profit is from trades held under 5 s (Lucid account-level limit)")
    sib = []
    for r in ALL_BUILD:
        if (r["family"], r["root"], r["sess"], r["label"], r["group"], r["side"]) == (u["family"], u["root"], sess, u["label"], u["group"] or "", u["side"] or "") \
                and str(r["tf"]) != u["tf"]:
            if r["build_pass"]:
                f_ = ALL_FINAL[r["uid"]]
                sib.append(f"{r['tf']}-min: " + ("member" if f_["admit"] else "passes BUILD, fails 2024 test " + ", ".join(f_["failed"])))
            else:
                sib.append(f"{r['tf']}-min: fails BUILD test {r['fail']}")
    worst = max([abs(t.get("mae_usd") or 0.0) for t in R[("build", False)]["trades"] + R[("pick", False)]["trades"]] + [0.0])
    m = {"uid": u["uid"], "name": name, "idea": idea_of(u), "family": u["family"], "root": u["root"], "tf": u["tf"], "sess": sess, "label": u["label"],
         "group": u["group"], "side": u["side"], "default": cid, "inputs": R[("build", False)]["inputs"], "rule": rule_text(u, cell),
         "rationale": bst["meta"].get("rationale"), "complexity": bst["meta"].get("complexity"), "flags": flags,
         "siblings": sib, "variants_judged": bts["cells"], "survivors": len(surv), "avg_rows": avg_rows, "default_rows": d_rows,
         "build": {k: bts[k] for k in ("cells", "positive", "share_pos", "avg_net", "median_net", "avg_trades", "v60", "v70", "v80")},
         "pick": {k: pts[k] for k in ("cells", "positive", "share_pos", "avg_net", "median_net", "avg_trades", "v60", "v70", "v80")},
         "pick_stress": {k: sts[k] for k in ("cells", "positive", "share_pos", "avg_net", "median_net")},
         "controls_build": bdet, "controls_pick": o["controls"], "oco_cancel_ms": sst["meta"].get("oco_cancel_ms", 0),
         "default_stress": {"build": [LB._net(R[("build", False)]["trades"]), LB._net(R[("build", True)]["trades"])],
                            "pick": [LB._net(R[("pick", False)]["trades"]), LB._net(R[("pick", True)]["trades"])]},
         "fast_avg": fast_avg, "fast_default": fast_def, "worst_open_loss": worst, "tie_rule": "survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones"}
    # ---- files
    d = MEM / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    with (d / "surviving_set.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    daily = []
    for per, c in (("build", cal_b), ("pick", cal_p)):
        (d / f"trades_{per}.json").write_text(json.dumps(R[(per, False)]["trades"], separators=(",", ":"), default=str))
        daily += LB.daily_rows(R[(per, False)]["trades"], c, per)
    with (d / "daily.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["date", "period", "net", "worst_open_loss", "minutes_in_market"])
        w.writeheader()
        w.writerows(daily)
    spec = {k: m[k] for k in ("name", "uid", "idea", "family", "root", "tf", "sess", "label", "group", "side", "inputs", "rule", "rationale", "complexity", "flags")}
    spec.update(cell=cid, default_rule=m["tie_rule"], admission="v2 (EDGE_SPEC ADMISSION v2: the average of all variants)", admit=True,
                variants_judged=bts["cells"], survivors=len(surv), contracts=1, hold_to="day",
                day_filter=(u["group"] and f"event group {u['group']}") or u["side"] or None,
                periods={"build": ["2021-09-22", "2023-12-31"], "pick": ["2024-01-01", "2024-12-31"]},
                tests={"1_build_share_and_average": True, "2_build_real_edge": bdet, "3_trades": {"build_avg": bts["avg_trades"], "build_plus_2024_avg": o["trades_build_plus_2024"]},
                       "4_2024_average_and_median": {"avg": pts["avg_net"], "median": pts["median_net"]}, "5_2024_lift": o["controls"],
                       "6_2024_stress_average": sts["avg_net"]},
                written_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    (d / "spec.json").write_text(json.dumps(spec, indent=1, default=lambda o_: o_.tolist() if hasattr(o_, "tolist") else str(o_)))
    m["dir"] = str(d)
    m["_trades"] = R[("build", False)]["trades"] + R[("pick", False)]["trades"]
    return m


CTL_PLAIN = {"c1": "random entries, same exits and session (2 random seeds on disk; 200 day-matched table draws)",
             "shift": "the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them)",
             "c2": "the same table with a shuffled book (2 seeds: THIN; 200 day-mixes)", "base": "the same strategy without the Level 2 option (net per trade)",
             "days": "the same table on all days (net per trade) and 4,000 random same-size day subsets"}


def card(m: dict, same: list) -> str:
    L = [f"# {m['name']} — library member (admission v2: judged on the AVERAGE of all variants)", "",
         f"**Idea:** {m['idea']} · **market** {m['root']} · **session** {m['sess']} · **bar size** {m['tf']} min · 1 contract, after costs. "
         "BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.",
         "**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**", "",
         f"**Reason (written before testing):** {m['rationale']}", "",
         f"**Rules (default variant `{m['default']}`):** {m['rule']}", "",
         "**Flags:** " + ("; ".join(m["flags"] + ([f"SAME IDEA as {', '.join(same)}: one strategy for a stack, never two"] if same else [])) or "none"), "",
         "**The same idea at other bar sizes (same market and session):** " + ("; ".join(m["siblings"]) or "none stored") + ".", "",
         "## Average variant and default variant, per year then combined",
         f"Average = the {m['variants_judged']} judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). "
         f"Default = the middle of the {m['survivors']} surviving variants by BUILD net ({m['tie_rule']}).", "",
         "| | period | trades | net | win rate | profit factor | max drawdown | average trade |", "|---|---|---|---|---|---|---|---|"]
    for r in m["avg_rows"]:
        nm = "2021*" if r["period"] == "2021" else r["period"]
        L.append(f"| average variant | {nm} | {r['trades']:.0f} | {money(r['net'])} | {pct(r['win'])} | {'n/a' if r['pf'] is None else format(r['pf'], '.2f')} | "
                 f"{money(r['max_dd'])} | {money(r['avg_trade'])} |")
    for r in m["default_rows"]:
        nm = str(r["period"])
        nm = "2021*" if nm.startswith("2021") else nm
        L.append(f"| default `{m['default']}` | {nm} | {r['trades']} | {money(r['net'])} | {pct(r['win'])} | {'n/a' if r['pf'] is None else format(r['pf'], '.2f')} | "
                 f"{money(r['max_dd'])} | {money(r['avg_trade'])} |")
    L += ["", "## Share of variants profitable (pass = that share reached and the average variant positive)",
          "| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |", "|---|---|---|---|---|---|---|---|---|"]
    for nm, g in (("BUILD", m["build"]), ("2024", m["pick"])):
        L.append(f"| {nm} | {g['cells']} | {g['positive']} | {pct(g['share_pos'])} | {'pass' if g['v60'] else 'fail'} | {'pass' if g['v70'] else 'fail'} | "
                 f"{'pass' if g['v80'] else 'fail'} | {money(g['avg_net'])} | {money(g['median_net'])} |")
    g = m["pick_stress"]
    L.append(f"| 2024 under stress | {g['cells']} | {g['positive']} | {pct(g['share_pos'])} | | | | {money(g['avg_net'])} | {money(g['median_net'])} |")
    L += ["", "## Real edge: the table average against random (lift = table average minus the control's average)",
          "| control | period | lift | beats this share of replicates | note |", "|---|---|---|---|---|"]
    for per, det in (("BUILD", m["controls_build"]), ("2024", m["controls_pick"])):
        for c, v in det.items():
            if c in ("base", "days"):
                lift = f"{money(v.get('lift_per_trade'))} a trade ({money(v.get('per_trade'))} vs {money(v.get('unfiltered_per_trade', v.get('base_per_trade')))})"
            else:
                lift = money(v.get("lift"))
            L.append(f"| {CTL_PLAIN[c]} | {per} | {lift} | {pct(v.get('p_beat')) if v.get('p_beat') is not None else 'n/a'} | "
                     f"{'THIN CONTROL (2 real replicates)' if c in ('shift', 'c2') else ''} |")
    ds = m["default_stress"]
    oco = " + 100 ms late cancel of the other bracket side" if m["oco_cancel_ms"] else ""
    L += ["", f"## Stress (2 ticks of slippage + 250 ms delay{oco})",
          f"* Average variant, 2024: {money(m['pick']['avg_net'])} -> {money(m['pick_stress']['avg_net'])} under stress.",
          f"* Default variant: BUILD {money(ds['build'][0])} -> {money(ds['build'][1])}; 2024 {money(ds['pick'][0])} -> {money(ds['pick'][1])}.",
          f"* Surviving set: {m['survivors']} of {m['variants_judged']} variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).",
          "", "## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)",
          f"* Average variant, share of gross profit from trades held under 5 s: BUILD {pct(m['fast_avg']['build']['fast_profit_share'])}, "
          f"2024 {pct(m['fast_avg']['pick']['fast_profit_share'])}, combined {pct(m['fast_avg']['all']['fast_profit_share'])}.",
          f"* Default variant (exact times, held <= 5.000 s): {pct(m['fast_default']['share'])} of gross profit; those {m['fast_default']['n_fast']} trades net {money(m['fast_default']['net_fast'])}.",
          "", "## Size",
          f"* Worst open loss on one trade (default, 1 contract): {money(m['worst_open_loss'])} = {money(m['worst_open_loss'] / 10 + 1)} per micro -> "
          f"at most {int(2000 // (m['worst_open_loss'] / 10 + 1)) if m['worst_open_loss'] > 0 else 'n/a'} micros inside $2,000.",
          "", f"Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `{m['uid']}`."]
    return "\n".join(L) + "\n"


def day_side(trades: list) -> dict:
    out = {}
    for t in sorted(trades, key=lambda t: t["entry_ms"]):
        out.setdefault(t["date"], 1 if t["side"] == "long" else -1)
    return out


def group_ideas(M: list) -> list:
    """Same idea = same family + market + session, or the same side on >= 70 % of shared trading days (>= 30 shared days;
    side of a day = the side of the default variant's first trade that day). Union of the two relations."""
    par = list(range(len(M)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    sides = [day_side(m["_trades"]) for m in M]
    pairs = []
    for i in range(len(M)):
        for j in range(i + 1, len(M)):
            a, b = M[i], M[j]
            fam = (a["family"], a["root"], a["sess"]) == (b["family"], b["root"], b["sess"])
            sh = [d for d in sides[i] if d in sides[j]]
            same = sum(sides[i][d] == sides[j][d] for d in sh) / len(sh) if sh else 0.0
            link = fam or (len(sh) >= 30 and same >= 0.70)
            pairs.append({"a": a["name"], "b": b["name"], "shared_days": len(sh), "same_side": round(same, 3), "same_family_market_session": fam, "linked": bool(link)})
            if link:
                par[find(i)] = find(j)
    groups: dict = {}
    for i, m in enumerate(M):
        groups.setdefault(find(i), []).append(m)
    return list(groups.values()), pairs


EARLIER_READS: list = []
ALL_BUILD: list = []
ALL_FINAL: dict = {}


def main():
    for f in ("admit", "admit_r1", "deepen", "events"):
        EARLIER_READS.extend(csv.DictReader((V.W / "out" / f / "pick_reads.csv").open()))
    ALL_BUILD.extend(json.loads((V.OUT / "build_units.json").read_text()))
    ALL_FINAL.update(json.loads((V.OUT / "final.json").read_text()))
    B = {r["uid"]: r for r in json.loads((V.OUT / "build_units.json").read_text())}
    P = json.loads((V.OUT / "pick_units.json").read_text())
    FIN = json.loads((V.OUT / "final.json").read_text())
    U = {u["uid"]: u for u in V.units()}
    adm = [uid for uid, r in FIN.items() if r["admit"]]
    todo = []
    for uid in adm:
        u = U[uid]
        oco = bool(V.store(u["key"], period="build")["meta"].get("both_sides_declared"))
        todo.append((u, FIN[uid]["default"], oco))
    default_runs(todo)
    names_new = {V.member_name(U[uid]) for uid in adm}
    # 1. existing members that fail v2 -> _v1_only (before the new folders are written)
    name_uid = {V.member_name(u): u["uid"] for u in U.values()}
    moved = []
    for d in sorted(p for p in MEM.iterdir() if p.is_dir() and not p.name.startswith("_")):
        uid = name_uid.get(d.name)
        if d.name in names_new:
            continue
        if not (d / "spec.json").exists():
            continue
        try:
            if json.loads((d / "spec.json").read_text()).get("admission", "").startswith("v2"):
                shutil.rmtree(d)                      # a v2 folder of an earlier run of this script that no longer passes
                continue
        except Exception:
            pass
        why = why_not(uid, B, P, FIN)
        dst = MEM / "_v1_only" / d.name
        dst.parent.mkdir(exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(d), str(dst))
        (dst / "V2_FAIL.md").write_text(f"# {d.name}: admitted under the v1 rules, NOT under ADMISSION v2 ({dt.date.today().isoformat()})\n\n{why}\n")
        moved.append((d.name, why))
    v1 = MEM / "_v1_only"
    if v1.exists():                                   # folders moved by an earlier run of this script
        for d in sorted(p for p in v1.iterdir() if p.is_dir() and p.name not in [n for n, _ in moved]):
            moved.append((d.name, why_not(name_uid.get(d.name), B, P, FIN)))
    M = [build_member(U[uid], B[uid], P[uid], FIN[uid]) for uid in adm]
    groups, pairs = group_ideas(M)
    same_of = {}
    for g in groups:
        for m in g:
            same_of[m["name"]] = [x["name"] for x in g if x["name"] != m["name"]]
    for m in M:
        (Path(m["dir"]) / "card.md").write_text(card(m, same_of[m["name"]]))
    # 2. demoted / rejected folders: the v2 verdict beside them
    notes = []
    for sub in ("_demoted", "_rejected"):
        for d in sorted(p for p in (MEM / sub).iterdir() if p.is_dir()):
            uid = name_uid.get(d.name)
            if d.name in names_new:
                txt = f"ADMISSION v2: this unit PASSES all six tests and is now a member: `members/{d.name}/` (this folder keeps the v1 record)."
            else:
                txt = "ADMISSION v2: still not a member. " + why_not(uid, B, P, FIN)
            (d / "v2_rejudge.md").write_text(f"# {d.name} — re-judged under ADMISSION v2 ({dt.date.today().isoformat()})\n\n{txt}\n")
            notes.append((sub, d.name, txt))
    for m in M:
        m.pop("_trades")
    (V.OUT / "members.json").write_text(json.dumps({"members": M, "groups": [[m["name"] for m in g] for g in groups], "pairs": pairs,
                                                    "moved_v1_only": moved, "rejudged": notes}, indent=1,
                                                   default=lambda o_: o_.tolist() if hasattr(o_, "tolist") else str(o_)))
    print("members", len(M), "| ideas", len(groups), "| moved to _v1_only", [n for n, _ in moved])
    for g in groups:
        print("  idea:", [m["name"] for m in g])


def why_not(uid, B, P, FIN) -> str:
    if uid is None:
        return "No stored unit matches this folder name."
    b = B[uid]
    if not b["build_pass"]:
        det = json.loads(b["detail"]) if isinstance(b.get("detail"), str) and b.get("detail") else {}
        bits = []
        if not b["t1"]:
            bits.append(f"test (1): {pct(b['share_pos'])} of {b['cells']} variants profitable, average variant {money(b['avg_net'])}")
        if b["t2"] is False:
            for c, v in det.items():
                if not v.get("pass"):
                    bits.append(f"test (2) real edge, control `{c}`: lift {money(v.get('lift', v.get('lift_per_trade')))}, beats {pct(v.get('p_beat'))} of replicates (needs lift > 0 and 95 %)"
                                if "why" not in v else f"test (2), control `{c}`: {v['why']}")
        if not b["t3"]:
            bits.append(f"test (3): the average variant has {b['avg_trades']:.0f} BUILD trades, {b.get('reach_trades')} with 2024 at the same rate (100 needed)")
        return (f"Fails on BUILD ({'; '.join(bits)}). BUILD table: {pct(b['share_pos'])} of {b['cells']} variants profitable, average variant {money(b['avg_net'])}. "
                "2024 was not judged under v2.")
    o, f = P[uid], FIN[uid]
    bits = []
    if not o["t4"]:
        bits.append(f"test (4): 2024 average variant {money(o['avg_net'])}, median {money(o['median_net'])} ({pct(o['share_pos'])} of variants profitable)")
    if not o["t5"]:
        bits.append("test (5): 2024 lift over random " + ", ".join(f"`{c}` {money(v.get('lift', v.get('lift_per_trade')))}" for c, v in o["controls"].items()))
    if o["t4"] and o["t5"] and not o.get("t6"):
        bits.append(f"test (6): 2024 average variant under stress {money(o.get('stress_avg_net'))}")
    if not o["t3_final"]:
        bits.append(f"trade minimum: {o['trades_build_plus_2024']:.0f} trades BUILD + 2024 on the average variant (100 needed)")
    if o["t4"] and o["t5"] and o.get("t6") and not f["survivors"]:
        bits.append("no variant is profitable in both periods under stress")
    return "Passes BUILD (1)-(3); fails on 2024: " + "; ".join(bits) + "."


if __name__ == "__main__":
    main()
