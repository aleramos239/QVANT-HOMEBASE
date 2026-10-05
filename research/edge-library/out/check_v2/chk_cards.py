"""CHECKER v2: the average-variant table per year and the <= 5 s profit share of every member, from the stores, my own code.
2024 stores opened here were already read by the analyst (logged in checker_pick_reads.csv)."""
import csv, datetime as dt, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chk_lib as C

REPORT = {  # the analyst's report: trades, 2021, 2022, 2023, 2024, win %, PF, max DD, share <= 5 s %
 "straddle_t_0830-NQ-tf30|pre|": (763, -2667, 37863, 8469, 7328, 34, 1.15, 25074, 4),
 "straddle_tight_0830-NQ-tf30|pre|": (766, -230, 4051, 5915, 5548, 43, 1.21, 3464, 35),
 "E1-A-NQ": (320, 380, 4411, 5294, 3937, 49, 1.49, 1932, 67),
 "E1-B-NQ": (225, 554, 5350, 3241, 3272, 52, 1.63, 1673, 77),
 "E1-A-GC": (317, 404, 4645, 5135, 5910, 50, 1.58, 2426, 52),
 "E1-B-GC": (223, 384, 3693, 4622, 4414, 52, 1.69, 2025, 64),
 "E3-C-NQ": (141, -279, 2075, 2304, 3242, 49, 1.61, 1740, 56),
 "E3-C-GC": (142, 392, 3143, 4675, 4309, 58, 2.23, 1273, 47),
 "first_bar_mom-NQ-tf30|mid|": (413, 5291, 8201, 876, 11239, 38, 1.15, 16291, 0),
 "first_bar_mom-NQ-tf15|mid|": (305, 8025, 11082, -2185, 3985, 38, 1.16, 15056, 0),
 "first_bar_mom-ES-tf15|mid|": (306, 921, 5619, -1908, 2681, 37, 1.09, 10270, 0),
 "orb-NQ-tf15|pre|": (725, -468, 17005, 6170, 10886, 33, 1.11, 22228, 2),
 "straddle_t_1800-NQ-tf30|eve|": (647, 3352, 13856, -1450, 12460, 32, 1.10, 23301, 1),
 "tema_slope-NQ-tf30|eve|": (480, -3296, 1542, 21726, 11967, 33, 1.17, 20204, 0),
}
U = {u["uid"]: u for u in C.units()}
P = json.loads((C.OUT / "chk_pick.json").read_text())
out = {}
for uid, rep in REPORT.items():
    u = U[uid]
    bst = C.build_store(u["key"]); pst = C.pick_store(f"{u['key']}-{u['sess']}-pick")
    ids = C.tstats(C.build_rows(bst, u))["ids"]
    dm = C.day_filter(u)
    yr = {2021: 0.0, 2022: 0.0, 2023: 0.0, 2024: 0.0}
    tr = gw = gl = wins = fw = 0.0; dds = []; pos24 = 0
    cal = np.concatenate([C.cal("build", u["root"]), C.cal("pick", u["root"])])
    for c in ids:
        xs = [C.cell(bst, c, u["sess"], dm), C.cell(pst, c, u["sess"], dm)]
        net = np.concatenate([x["net"] for x in xs]).astype(float); date = np.concatenate([x["date"] for x in xs]).astype(np.int64)
        dur = np.concatenate([x["dur_s"] for x in xs])
        y = np.array([dt.date.fromordinal(int(o)).year for o in date])
        for k in yr: yr[k] += net[y == k].sum()
        tr += len(net); wins += (net > 0).sum(); gw += net[net > 0].sum(); gl += -net[net < 0].sum(); fw += net[(net > 0) & (dur < 5)].sum()
        days = np.unique(np.concatenate([cal, date])); daily = np.zeros(len(days)); np.add.at(daily, np.searchsorted(days, date), net)
        eq = np.cumsum(daily); dds.append(float((np.maximum.accumulate(np.maximum(eq, 0)) - eq).max()))
    V = len(ids)
    mine = (round(tr / V), round(yr[2021] / V), round(yr[2022] / V), round(yr[2023] / V), round(yr[2024] / V), round(100 * wins / tr), round(gw / gl, 2), round(np.mean(dds)), round(100 * fw / gw))
    ok = all(abs(a - b) <= (0.011 if i == 6 else 1) for i, (a, b) in enumerate(zip(mine, rep)))
    out[uid] = {"mine": mine, "report": rep, "match": ok, "variants": V, "survivors": len(P[uid]["survivors"])}
    print(f"{uid:34s} V {V:3d}/{len(P[uid]['survivors']):2d} mine {mine} {'OK' if ok else 'DIFF vs ' + str(rep)}")
(C.OUT / "chk_cards.json").write_text(json.dumps(out, default=float))
with (C.OUT / "checker_pick_reads.csv").open("a", newline="") as fh:
    w = csv.writer(fh)
    for d, k in C.READS:
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), d, k, "chk_cards.py: average-variant table per year and <= 5 s share of a member (already read by the analyst)"])
