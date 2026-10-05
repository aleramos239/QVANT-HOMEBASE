"""CHECKER v2: compare my from-scratch re-runs (out/check_v2/rerun/) trade for trade with members/<name>/trades_{build,pick}.json
and with the stores (normal and stress). Also: the member's default cell = my middle survivor (chk_pick.json), not the best.
Reads only cells the analyst already read. -> chk_rerun_cmp.json"""
import csv, datetime as dt, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C

W = C.W
RR = C.OUT / "rerun"
P = json.loads((C.OUT / "chk_pick.json").read_text())
U = {u["uid"]: u for u in C.units()}
out = {}


def key_of(t):
    return (t["date"], int(t["entry_ms"]), int(t["exit_ms"]), t["side"], round(float(t["entry_price"]), 4), round(float(t["exit_price"]), 4), round(float(t["net"]), 2))


for sp in sorted((W / "members").glob("*/spec.json")):
    if sp.parent.name.startswith("_"):
        continue
    m = json.loads(sp.read_text())
    uid, cid = m["uid"], m["cell"]
    u = U[uid]
    dm = C.day_filter(u)
    o = {"uid": uid, "cell": cid}
    pk = P[uid]
    surv = pk.get("survivors") or []
    o["default_is_my_middle"] = bool(pk.get("default") == cid)
    o["n_survivors"] = len(surv)
    o["rank_in_survivors"] = (surv.index(cid) + 1) if cid in surv else None      # survivors are sorted by BUILD net ascending
    o["default_is_best"] = bool(surv and surv[-1] == cid)
    for period in ("build", "pick"):
        f = RR / f"{m['family']}-{m['root']}-tf{m['tf']}-{m['sess']}-{period}-normal.json"
        mine = json.loads(f.read_text())["trades"][cid]
        if dm is not None:
            d = np.array([dt.date.fromisoformat(t["date"]).toordinal() for t in mine], np.int64)
            keep = dm(d, np.array([1 if t["side"] == "long" else -1 for t in mine]))
            mine = [t for t, k in zip(mine, keep) if k]
        theirs = json.loads((sp.parent / f"trades_{period}.json").read_text())
        a, b = [key_of(t) for t in mine], [key_of(t) for t in theirs]
        same = a == b
        o[f"{period}_n_mine"], o[f"{period}_n_member"] = len(a), len(b)
        o[f"{period}_net_mine"], o[f"{period}_net_member"] = round(sum(t["net"] for t in mine), 2), round(sum(t["net"] for t in theirs), 2)
        o[f"{period}_trade_for_trade"] = bool(same)
        if not same:
            sa, sb = set(a), set(b)
            o[f"{period}_only_mine"], o[f"{period}_only_member"] = len(sa - sb), len(sb - sa)
        # the store (normal costs)
        st = C.build_store(u["key"]) if period == "build" else C.pick_store(f"{u['key']}-{u['sess']}-pick")
        x = C.cell(st, cid, u["sess"], dm)
        o[f"{period}_net_store"], o[f"{period}_n_store"] = round(float(x["net"].sum()), 2), int(len(x["net"]))
        # stress: my re-run vs the analyst's stress store
        fs = RR / f"{m['family']}-{m['root']}-tf{m['tf']}-{m['sess']}-{period}-stress.json"
        js = json.loads(fs.read_text())
        ms = js["trades"][cid]
        if dm is not None:
            d = np.array([dt.date.fromisoformat(t["date"]).toordinal() for t in ms], np.int64)
            ms = [t for t, k in zip(ms, dm(d)) if k]
        o[f"{period}_stress_mine"], o[f"{period}_stress_n_mine"] = round(sum(t["net"] for t in ms), 2), len(ms)
        o[f"{period}_stress_kw"] = js["kw"]
        skey = f"{u['key']}-{u['sess']}-{period}-stress"
        sst = C.pick_store(skey, [W / "runs_v2"]) if period == "pick" else (C.stress_build_store(skey) if (W / "runs_v2" / skey / "run.json").exists() else None)
        if sst is not None and cid in sst["idx"]:
            xs = C.cell(sst, cid, u["sess"], dm)
            o[f"{period}_stress_store"], o[f"{period}_stress_n_store"] = round(float(xs["net"].sum()), 2), int(len(xs["net"]))
            o[f"{period}_stress_store_meta"] = {k: sst["meta"].get(k) for k in ("stress", "oco_cancel_ms", "slip_ticks", "latency_ms", "both_sides_declared")}
        fn = RR / f"{m['family']}-{m['root']}-tf{m['tf']}-{m['sess']}-{period}-stress_no_oco.json"
        if fn.exists():
            mn = json.loads(fn.read_text())["trades"][cid]
            if dm is not None:
                d = np.array([dt.date.fromisoformat(t["date"]).toordinal() for t in mn], np.int64)
                mn = [t for t, k in zip(mn, dm(d)) if k]
            o[f"{period}_stress_no_oco_mine"], o[f"{period}_stress_no_oco_n"] = round(sum(t["net"] for t in mn), 2), len(mn)
    out[m["name"]] = o
    ok = o["build_trade_for_trade"] and o["pick_trade_for_trade"]
    print(f"{m['name']:40s} {cid:22s} mid {o['default_is_my_middle']} rank {o['rank_in_survivors']}/{o['n_survivors']} best {o['default_is_best']} | "
          f"BUILD {o['build_n_mine']}/{o['build_n_member']} {o['build_net_mine']:.0f}/{o['build_net_member']:.0f}/{o['build_net_store']:.0f} {'SAME' if o['build_trade_for_trade'] else 'DIFF'} | "
          f"2024 {o['pick_n_mine']}/{o['pick_n_member']} {o['pick_net_mine']:.0f}/{o['pick_net_member']:.0f}/{o['pick_net_store']:.0f} {'SAME' if o['pick_trade_for_trade'] else 'DIFF'} | "
          f"stress B {o['build_stress_mine']:.0f}/{o.get('build_stress_store')} P {o['pick_stress_mine']:.0f}/{o.get('pick_stress_store')} no-oco P {o.get('pick_stress_no_oco_mine')}", flush=True)
(C.OUT / "chk_rerun_cmp.json").write_text(json.dumps(out, indent=1))
with (C.OUT / "checker_pick_reads.csv").open("a", newline="") as fh:
    w = csv.writer(fh)
    for d, k in C.READS:
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), d, k, "chk_rerun_cmp.py: default cell compared with my re-run (already read by the analyst)"])
