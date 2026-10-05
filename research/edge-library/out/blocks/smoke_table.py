import json, glob, os, sys
SP = os.path.dirname(os.path.abspath(__file__)) + '/smoke'
tot = {}
for f in sorted(glob.glob(SP + "/smoke_r3_*.json")):
    try:
        o = json.load(open(f))
    except Exception as e:
        print(os.path.basename(f), "NOT READY / ERROR", str(e)[:80]); continue
    kinds = {"base": [0, 0.0, 0], "filter": [0, 0.0, 0], "book": [0, 0.0, 0], "volume": [0, 0.0, 0], "c1x": [0, 0.0, 0], "c1r": [0, 0.0, 0], "c2": [0, 0.0, 0]}
    bad = 0
    for r in o["rows"]:
        k = r["key"]
        kind = ("c2" if "-c2s" in k else "c1x" if k.startswith("c1x") else "c1r" if "__c1r" in k else "book" if "__book" in k
                else "volume" if "__volume" in k else "filter" if "__" in k else "base")
        kinds[kind][0] += r["instances"] * o["days"]; kinds[kind][1] += r["seconds"]; kinds[kind][2] += r["trades"]
        bad += r["skipped_by_error"] + r["exit_after_day_flat"] + r["overlap_in_session"] + r["entry_in_no_session"]
    line = " ".join(f"{k} {1000 * v[1] / v[0]:.2f}" for k, v in kinds.items() if v[0])
    print(f"{o['spec']:13s} {o['root']} tf{o['tf']:2s} ok {o['ok']!s:5s} bad-counts {bad} rows {len(o['rows']):2d} trades {sum(r['trades'] for r in o['rows']):7d} "
          f"no-trade cells {sum(r['cells_without_trades'] for r in o['rows']):5d} total s {sum(r['seconds'] for r in o['rows']):6.1f} | ms per instance-day: {line}")
