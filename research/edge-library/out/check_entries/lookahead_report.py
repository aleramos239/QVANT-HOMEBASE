"""Reads out/check_entries/lookahead_<root>.json (lookahead_audit.py) and prints the audit counts + the store comparison."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lookahead_audit as L  # noqa: E402  (my own file: store_rows only)

for root in ("NQ", "GC", "ES"):
    res = json.loads((HERE / f"lookahead_{root}.json").read_text())
    used = [r for r in res if not r["skip"]]
    print(f"== {root}: sessions {len(res)}, used {len(used)}, skipped {[r['date'] for r in res if r['skip']]}")
    # ---- event_dir: raw reading vs engine, every day x cell
    c = Counter()
    gaps = {}
    for r in used:
        for x in r["dir"]:
            k = (x["fam"], x["x"])
            c[k + ("days",)] += 1
            c[k + ("release days",)] += x["release"]
            if not x["probe"]:
                c[k + ("no decision event",)] += 1
                continue
            for f in ("now_ok", "anchor_ok", "dec_ok", "side_ok", "live_ok"):
                c[k + ("BAD " + f,)] += (not x[f])
            c[k + ("prints AT the instant",)] += x["n_at_instant"] > 0
            if x["eng_trades"]:
                c[k + ("trades",)] += 1
                for f in ("tr_side_ok", "tr_time_ok", "tr_px_ok", "fill_after_live", "prev_print_before_live"):
                    c[k + ("BAD " + f,)] += (not x[f])
                gaps.setdefault(k, []).append(x["fill_gap_ms"])
            else:
                c[k + ("no trade, raw side 0",)] += x["raw_side"] == 0
                c[k + ("no trade BUT raw side != 0",)] += x["raw_side"] != 0
            if "rewrite" in x:
                c[k + ("rewrite days",)] += 1
                for how, v in x["rewrite"].items():
                    c[k + (f"BAD rewrite {how} decision changed",)] += (not v["same"])
                    c[k + (f"BAD rewrite {how} fill before live",)] += (not v["fill_after_live"])
                    c[k + (f"BAD rewrite {how} trade side changed",)] += (not v["side_trade_same"])
    for k in sorted({k[:2] for k in c}):
        d = {kk[2]: v for kk, v in c.items() if kk[:2] == k}
        bad = {a: b for a, b in d.items() if a.startswith("BAD") and b}
        g = sorted(gaps.get(k, [0]))
        print(f"  D {k[0]} x={k[1]}: days {d.get('days')} (release {d.get('release days')}), trades {d.get('trades')}, no-move days {d.get('no trade, raw side 0', 0)}, "
              f"no trade but a move {d.get('no trade BUT raw side != 0', 0)}, days with a print stamped exactly at the instant {d.get('prints AT the instant', 0)}, "
              f"rewrite days {d.get('rewrite days', 0)}, fill delay after the decision ms min/med/max {g[0]}/{g[len(g) // 2]}/{g[-1]} | BAD: {bad or 'none'}")
    # ---- straddle_wide
    c = Counter()
    ages = []
    for r in used:
        for x in r["wide"]:
            k = (x["fam"], x["cid"])
            c[k + ("days",)] += 1
            if not x["probe"]:
                c[k + ("not armed",)] += 1
                continue
            ages.append(x["anchor_age_ms"])
            for f in ("now_ok", "anchor_ok", "legs_ok", "live_ok", "fill_ok"):
                c[k + ("BAD " + f,)] += (not x[f])
            c[k + ("trades",)] += x["eng_trades"]
            if "rewrite" in x:
                c[k + ("rewrite days",)] += 1
                for how, v in x["rewrite"].items():
                    c[k + (f"BAD rewrite {how}",)] += (not v)
    for k in sorted({k[:2] for k in c}):
        d = {kk[2]: v for kk, v in c.items() if kk[:2] == k}
        bad = {a: b for a, b in d.items() if a.startswith("BAD") and b}
        print(f"  W {k[0]} {k[1]}: days {d.get('days')}, armed {d.get('days') - d.get('not armed', 0)}, trades {d.get('trades')}, rewrite days {d.get('rewrite days', 0)} | BAD: {bad or 'none'}")
    ages.sort()
    print(f"  W anchor age (ms before the arming instant) med {ages[len(ages) // 2]}, p95 {ages[int(len(ages) * .95)]}, max {ages[-1]}")
    # ---- from-scratch trades vs the store
    for fam, ids in L.SCRATCH[root].items():
        for cid in ids:
            by, skipped = L.store_rows(root, fam, cid)
            mine = {r["date"]: [tuple(t) for t in r["scratch"][f"{fam}|{cid}"]] for r in used if r["scratch"][f"{fam}|{cid}"]}
            my_skip = {r["date"] for r in res if r["skip"]}
            n_store = sum(len(v) for v in by.values())
            n_mine = sum(len(v) for v in mine.values())
            diff = [d for d in sorted(set(by) | set(mine)) if sorted(by.get(d, [])) != sorted(mine.get(d, []))]
            net_s, net_m = sum(t[2] for v in by.values() for t in v), sum(t[2] for v in mine.values() for t in v)
            print(f"  STORE {fam} {cid}: store {n_store} trades ${net_s:,.0f} | from scratch {n_mine} trades ${net_m:,.0f} | days that differ {len(diff)} {diff[:4]} | "
                  f"skipped days same {skipped == my_skip}")
