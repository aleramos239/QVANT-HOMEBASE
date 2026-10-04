import sys, math, collections, json, datetime as dt
SPD = sys.argv[1]; sys.argv = [sys.argv[0], SPD]
exec(open(SPD + "/dm/cmp.py").read())
sys.path.insert(0, str(HB / "research/prop-portfolio/2026-09-29")); sys.path.insert(0, str(HB))
import evalcore as E
import numpy as np
from homebase.backtest.tape import TapeStore, et_ns
PV, TICK, FEE = 20.0, 0.25, 4.0
STORE = TapeStore()
# (label, desk strategy, base dir, qty, X, mode, frozen key, flat time, cancel time)
CASES = [
 ("nyam Flex  4NQ day_take 1500", "nq_nyam_flex", "base3", 4, 1500.0, "take", "nq_nyam_flex", "11:00", "10:55"),
 ("nyam Pro   4NQ target 3000",   "nq_nyam_pro",  "b_pro", 4, 3000.0, "target", "nq_nyam_flex", "11:00", "10:55"),
 ("ORB  Pro   4NQ day_take 1000", "nq_orb_pro",   "base3", 4, 1000.0, "take", "nq_orb_pro", "13:30", "13:25"),
 ("pm   Flex  4NQ day_take 600",  "nq_pm_flex",   "base3", 4, 600.0, "take", "nq_pm_flex", "15:58", "15:53"),
 ("pm   Flex  3NQ day_take 600",  "nq_pm_flex",   "b_q3", 3, 600.0, "take", "nq_pm_flex", "15:58", "15:53"),
 ("pm   Flex  2NQ day_take 600",  "nq_pm_flex",   "b_q2", 2, 600.0, "take", "nq_pm_flex", "15:58", "15:53"),
]
def desk2(name, base):
    d = sorted((SP / "dm" / base / "runs").glob(f"*-{name}-*"))[-1]
    ts = {}
    for t in json.load(open(d/"trades.json")):
        assert t["date"] not in ts; ts[t["date"]] = t
    return ts, json.load(open(d/"run.json"))
def tick_cmp_ge(a, b): return a >= b - 1e-7
out = []
for label, name, base, N, X, mode, fkey, flat, canc in CASES:
    c = CFG[fkey]; F = frozen(c); D, run = desk2(name, base)
    tp = math.ceil((X + FEE*N) / (PV*N) / TICK - 1e-9) * TICK
    n = 10*N
    cnt = collections.Counter(); ex = collections.defaultdict(list)
    eday = dday = 0.0; take_days_diff = []
    tapechk = collections.Counter()
    for dte in sorted(set(F) | set(D)):
        f, d = F.get(dte), D.get(dte)
        if f is None or d is None:
            cnt["missing_" + ("desk" if d is None else "frozen")] += 1; ex["missing"].append(dte); continue
        cnt["days compared"] += 1
        if not all(f[k] == d[k] for k in ("side", "entry_ms", "entry_price", "order_price", "sl")):
            cnt["ENTRY_MISMATCH"] += 1; ex["entry"].append(dte); continue
        cnt["entry identical (side,time,fill,trigger,stop)"] += 1
        if d["qty"] != N: cnt["QTY_MISMATCH"] += 1
        g = f["gross"]/f["qty"]; mfe = max(abs(f["mfe_usd"])/f["qty"], max(g, 0.0)); mae = abs(f["mae_usd"])/f["qty"]
        tr = [(f["entry_ms"], f["exit_ms"], 1 if f["side"]=="long" else -1, g, mae, n, float("nan"), 0)]
        tot, *_ = E._walk_day(tr, n, 0, 0, 0, 1.0, 1.0, False, n, E._new_st(), [mfe], X if mode == "take" else 0.0, X if mode == "target" else 0.0)
        raw = n*g/10 - E.cost(n); best = max(n*mfe/10 - E.cost(n), raw)
        trig = (X if mode == "take" else X + 0.5*n)
        took = best >= trig - 1e-9
        dtook = d["exit_reason"] == "tp"
        eday += tot; dday += d["net"]
        if not took and not dtook:
            same = (f["exit_ms"] == d["exit_ms"] and f["exit_price"] == d["exit_price"] and f["exit_reason"] == d["exit_reason"]
                    and abs(d["gross"] - N*f["gross"]) < 1e-6 and abs(d["net"] - (N*f["gross"] - FEE*N)) < 1e-6)
            if same: cnt["no take: exit time/price/reason + $ identical"] += 1
            else: cnt["NO_TAKE_EXIT_MISMATCH"] += 1; ex["notake"].append(dte)
        elif took and dtook:
            sg = 1 if f["side"] == "long" else -1
            if abs(d["exit_price"] - (f["entry_price"] + sg*tp)) < 1e-9 and abs(d["net"] - (tp*PV*N - FEE*N)) < 1e-6:
                cnt["take: both take, desk exit = fill +/- take pts"] += 1; take_days_diff.append(d["net"] - tot)
            else: cnt["TAKE_PRICE_MISMATCH"] += 1; ex["takepx"].append(dte)
        elif took and not dtook:
            cnt["rule take, tester no fill (MFE exactly at limit, no penetration)"] += 1
            exact = abs(best - (tp*PV*N - FEE*N)) < 1e-6
            cnt["   ...of which MFE exactly = the limit price"] += exact
            ex["touch_only"].append((dte, round(best, 2), d["exit_reason"], d["net"], exact))
        else:
            cnt["DESK_TOOK_RULE_NOT"] += 1; ex["tookD"].append(dte)
        # independent tape check of the desk trade's exit (take / stop trigger times)
        if d["exit_reason"] in ("tp", "sl"):
            day = dt.date.fromisoformat(dte); tape = STORE.load("NQ", day)
            ts_ = np.frombuffer(tape.ts, dtype=np.int64); px_ = np.frombuffer(tape.px, dtype=np.float64)
            k = int(np.searchsorted(ts_, d["entry_ns"] if "entry_ns" in d else d["entry_ms"]*1_000_000))
            while ts_[k] != d["entry_ms"]*1_000_000 and k < len(ts_)-1 and ts_[k] < d["entry_ms"]*1_000_000: k += 1
            long_ = d["side"] == "long"
            fl = et_ns(day, flat)
            j_end = int(np.searchsorted(ts_, fl))
            seg = px_[k+1:j_end]
            tpl = d["entry_price"] + (tp if long_ else -tp)
            tp_hit = np.flatnonzero(seg >= tpl + TICK - 1e-7) if long_ else np.flatnonzero(seg <= tpl - TICK + 1e-7)
            sl_hit = np.flatnonzero(seg <= d["sl"] + 1e-7) if long_ else np.flatnonzero(seg >= d["sl"] - 1e-7)
            jt = tp_hit[0] if len(tp_hit) else 10**12; js = sl_hit[0] if len(sl_hit) else 10**12
            want = ("tp", ts_[k+1+jt]) if jt < js else ("sl", ts_[k+1+js]) if js < jt else ("?", 0)
            if want[0] == d["exit_reason"] and want[1] == d["exit_ms"]*1_000_000 + (d["exit_ms"]*0) or (want[0] == d["exit_reason"] and abs(want[1] - round(d["exit_ms"]*1_000_000)) < 1_000_000):
                tapechk["tape first-trigger = desk exit (reason+time)"] += 1
            else:
                tapechk["TAPE_MISMATCH"] += 1; ex["tape"].append((dte, d["exit_reason"], want))
        elif d["exit_reason"] in ("time", "eod"):
            tapechk["time exit (flat time)"] += 1
    for k, v in tapechk.items(): cnt[k] = v
    r = dict(label=label, frozen=len(F), desk=len(D), counts=dict(cnt), research_sum=round(eday), desk_sum=round(dday),
             take_day_net_diff=(round(min(take_days_diff), 2), round(max(take_days_diff), 2)) if take_days_diff else None,
             touch_only=ex.get("touch_only", []), missing=ex.get("missing", []),
             other={k: v[:5] for k, v in ex.items() if k not in ("touch_only", "missing")}, tp_pts=tp)
    out.append(r)
    print("=====", label, "take pts", tp, "| frozen", len(F), "desk", len(D))
    for k, v in cnt.items(): print("   %-62s %d" % (k, v))
    print("   day net $ sums: research rule %d | desk run %d | take-day net diff (desk - research) %s" % (eday, dday, r["take_day_net_diff"]))
    print("   missing", ex.get("missing", [])[:12]); print("   other", r["other"]); print("   touch-only", ex.get("touch_only", []))
json.dump(out, open(SP / "dm/compare2.json", "w"), indent=1, default=str)
