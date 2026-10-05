"""The analyst's REPORT lines (typed from the report) against my own numbers; read-log audit; 10:00-PCE-day sensitivity."""
import json, glob, csv, datetime as dt
import numpy as np
import chk as C
R = {}
for f in sorted(glob.glob("res/*.json")):
    r = json.load(open(f)); R[r["unit"]] = r
U = [C.addr(u) for u in C.UNITS]
REP = [  # verdict, avg 2021..2026, default 2025, 2026
 ("OVERFIT", [-230, 4051, 5915, 5548, -1450, None], -3922, None),
 ("OVERFIT", [380, 4411, 5294, 3937, -2806, None], -3367, None),
 ("OVERFIT", [554, 5350, 3241, 3272, -730, None], -1358, None),
 ("NOT PROVEN", [404, 4645, 5135, 5910, 2009, -2029], 342, -1146),
 ("NOT PROVEN", [384, 3693, 4622, 4414, 3601, -896], 3962, -846),
 ("NOT PROVEN", [-279, 2075, 2304, 3242, 984, -1105], -1100, -1258),
 ("NOT PROVEN", [392, 3143, 4675, 4309, 2226, 522], 2250, 868),
 ("OVERFIT", [5291, 8201, 876, 11239, -6182, None], 13896, None),
 ("NOT PROVEN", [8025, 11082, -2185, 3985, 2176, 6269], 11104, 50281),
 ("NOT PROVEN", [921, 5619, -1908, 2681, 1373, None], -4282, None),
 ("OVERFIT", [-468, 17005, 6170, 10886, -9371, None], 24446, None),
 ("OVERFIT", [-3296, 1542, 21726, 11967, -4118, None], 3659, None),
 ("NOT PROVEN", [4148, 26220, 4405, 13446, 7955, None], -3914, None),
 ("OVERFIT", [-2667, 37863, 8469, 7328, -310, None], -18292, None),
 ("NOT PROVEN", [3352, 13856, -1450, 12460, 8152, None], 27309, None)]
bad = 0
for u, (v, avg, d25, d26) in zip(U, REP):
    r = R[u]
    c, e = r["check"], r.get("exam")
    mine = "OVERFIT" if not c["avg"] > 0 else ("REAL" if (c["verdict"] == "CONFIRMED" and r["member_all_seeds"] and e and e["verdict"] == "CONFIRMED") else "NOT PROVEN")
    ys = [r["avg_by_year"].get(str(y)) for y in range(2021, 2027)]
    ok = mine == v and all((a is None and b is None) or (a is not None and b is not None and abs(round(b) - a) <= 1) for a, b in zip(avg, ys))
    ok &= abs(round(c["default"]["net"]) - d25) <= 1 and ((d26 is None and e is None) or abs(round(e["default"]["net"]) - d26) <= 1)
    bad += not ok
    print("OK  " if ok else "BAD ", u.ljust(38), mine.ljust(10), [None if y is None else round(y) for y in ys], round(c["default"]["net"]), None if not e else round(e["default"]["net"]),
          "| member(all seeds):", r["member_all_seeds"], "| 2025:", c["verdict"], "| 2026:", e["verdict"] if e else "-",
          "| 2026 fails:", ",".join(t[1] for t in (("t4", "4"), ("t5", "5"), ("t6", "6")) if e and not e[t[0]]) if e else "")
print("report lines that differ:", bad)
allowed = set(json.load(open(C.W / "out/exam2026/allowed.json"))["units"])
mine_allowed = {u for u in U if R[u]["member_all_seeds"] and R[u]["check"]["verdict"] == "CONFIRMED"}
print("allowed.json == my list:", allowed == mine_allowed, sorted(mine_allowed))
print("units with a 2026 store:", sorted(u for u in U if "exam" in R[u]), "== allowed:", {u for u in U if "exam" in R[u]} == allowed)

# ---- read logs: one line per store, logged before the store was written
idx = {f"{r['dir']}/{r['key']}": r for r in json.load(open("idx.json"))}
for name, path, stores in (("2025", C.W / "out/check2025/reads.csv", [k for k, r in idx.items() if r["start"] >= "2025-01-01" and r["end"] <= "2025-12-31"]),
                           ("2026", C.W / "out/exam2026/reads.csv", [k for k, r in idx.items() if r["start"] >= "2026-01-01"])):
    rows = list(csv.DictReader(open(path)))
    logged = [x["store"] for x in rows]
    late = []
    for x in rows:
        t = dt.datetime.fromisoformat(x["utc"]).astimezone().replace(tzinfo=None)
        m = dt.datetime.fromisoformat(idx[x["store"]]["mtime_npz"]) if x["store"] in idx else None
        if m is None or t > m:
            late.append((x["store"], x["utc"], m))
    print(name, "stores on disk", len(stores), "read-log lines", len(rows), "each store logged exactly once:", sorted(logged) == sorted(stores),
          "| logged before the store file was written:", not late, late[:3])
    ts = [x["utc"] for x in rows]
    print("   first / last read", min(ts), max(ts))

# ---- sensitivity: group C without the days whose ONLY 10:00 release is PCE (2025-04-30, 2026-01-22; BUILD 2021-11-24; 2024-11-27)
ev = list(csv.DictReader(open(C.W / "engine/cache/events.csv")))
t10 = {}
for x in ev:
    if x["time_et"] == "10:00":
        t10.setdefault(x["date"], set()).add(x["type"])
pce_only = sorted(d for d, t in t10.items() if t == {"PCE"})
print("10:00 days where PCE is the only release:", pce_only)
days = np.array(sorted(dt.date.fromisoformat(d).toordinal() for d, t in t10.items() if t != {"PCE"}), np.int64)
for k in (5, 6):
    u = C.UNITS[k]
    rng = np.random.default_rng(7)
    bst, brec, rows, judged, cnt = C.build_table(u, C.event_days("C"))
    ids = [r["id"] for r in judged]
    for per in ("check", "exam"):
        b, _ = C.year_block(u, per, ids, days, 4000, rng)
        print("  without PCE-only days", C.addr(u), per, "avg", round(b["avg"]), "median", round(b["median"]), "stress", round(b["stress_avg"]),
              {n: round(v["lift"], 1) for n, v in b["controls"].items()}, "t4", b["t4"], "t5", b["t5"], "t6", b["t6"], "| as scored:", round(R[C.addr(u)][per]["avg"]), round(R[C.addr(u)][per]["stress_avg"]))
