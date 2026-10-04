"""State leak across days: ONE instance through 10 days in order (workers=1) == a fresh instance per day (what an N-worker
run does: run_many cuts <= 10 days into one-day chunks for any worker count > 1). Every field of every trade is compared,
nothing is printed but counts. Also 2 real worker processes on the same specs."""
import sys, datetime as dt
sys.dont_write_bytecode = True
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine")
import l2sim as S
import families
import run_menus as RM

DAYS = {"NQ": ["2021-12-09", "2021-12-10", "2021-12-13", "2022-03-11", "2022-03-14", "2022-11-04", "2022-11-07", "2023-07-03", "2023-07-05", "2023-11-24"],
        "ES": ["2022-03-10", "2022-03-11", "2022-03-14", "2022-11-25", "2022-11-28", "2023-04-06", "2023-04-10", "2023-06-09", "2023-06-12", "2023-12-11"],
        "GC": ["2021-11-26", "2021-11-29", "2021-11-30", "2022-01-26", "2022-01-27", "2022-01-28", "2023-03-10", "2023-03-13", "2023-11-03", "2023-11-06"]}

def specs_of(root):
    out = []
    for at in S.LISTED_TIMES:
        g = families.unit_grid("straddle_t_" + at.replace(":", ""), root, "30")
        sub = g[2::29]
        out += [c["spec"] for c in sub] + [c["spec"] for c in RM.shift_grid(sub)]
    for tf in ("1", "5", "15"):
        for c in families.unit_grid("vwap_ema_x", root, tf)[5::31]:
            out += RM.cell_specs(c)
    return out

if __name__ == "__main__":
    for root, days in DAYS.items():
        specs = specs_of(root)
        a = S.run_many(specs, days=days, root=root, workers=1)
        per = [S.run_many(specs, days=[d], root=root, workers=1) for d in days]
        b = S.run_many(specs, days=days, root=root, workers=2)
        bad = 0
        for k, x in enumerate(a):
            fresh = sorted((t for p in per for t in p[k]["trades"]), key=lambda t: (t["exit_ms"], t["entry_ms"]))
            one = sorted(x["trades"], key=lambda t: (t["exit_ms"], t["entry_ms"]))
            if one != fresh or x["trades"] != b[k]["trades"] or x["skipped"] != b[k]["skipped"] or x["skipped_by_error"] or b[k]["skipped_by_error"]:
                bad += 1
        print(f"{root}: specs={len(specs)} trades={sum(len(x['trades']) for x in a)} one-instance vs fresh-per-day vs 2 processes: MISMATCHES={bad} (workers used {b[0]['meta']['workers']})")
