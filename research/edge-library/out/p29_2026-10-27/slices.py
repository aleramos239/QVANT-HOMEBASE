"""Read the 92 p29 runs (23 configs x 4 exits) and print: overall table, session slices. Analysis only; reads homebase/.state/tester/runs."""
import json, glob, os, sys, datetime as dt, statistics as st
from zoneinfo import ZoneInfo
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase")
from homebase.backtest.report import t_stat
ET = ZoneInfo("America/New_York")
R = "/Users/ramoscapital/ramos-quant-homebase/homebase/.state/tester/runs"
SESS = [("Eve 18-00", 1080, 1440), ("Asia 00-03", 0, 180), ("London 03-09:30", 180, 570), ("NY AM 09:30-12", 570, 720), ("NY PM 12-15", 720, 900)]
VARS = ["C0.5", "C1.5", "A0.5", "A1.5"]
runs = {}
for d in sorted(glob.glob(R + "/*draft_p29_*")):
    q = json.load(open(d + "/request.json")); c = q.get("controls") or {}
    var = ("C" if c.get("stop_mode") == "candle" else "A") + str(c.get("target_rr"))
    bm = c.get("bar_minutes") or 0
    idea = q["inputs"]["idea"] + (" 1m" if bm == 1 else "")
    runs[(idea, var)] = d
def sess_of(ms):
    t = dt.datetime.fromtimestamp(ms / 1000, ET); m = t.hour * 60 + t.minute
    for n, a, b in SESS:
        if a <= m < b: return n
    return "other"
def stats(tr):
    if not tr: return dict(n=0, net=0, win=0, pf=0, t=None, avg=0)
    n = [x["net"] for x in tr]; g = sum(v for v in n if v > 0); l = -sum(v for v in n if v < 0)
    return dict(n=len(n), net=sum(n), win=100 * sum(v > 0 for v in n) / len(n), pf=g / l if l else 9.99, t=t_stat(n), avg=sum(n) / len(n))
data = {}
for k, d in runs.items():
    tr = json.load(open(d + "/trades.json"))
    for x in tr: x["sess"] = sess_of(x["entry_ms"])
    data[k] = tr
ideas = sorted({k[0] for k in runs}, key=lambda s: (int(s.split()[0]), " 1m" in s))
out = []
out.append("## Overall: net $ (trades, t) per exit\n\n| idea | C 0.5R | C 1.5R | ATR 0.5R | ATR 1.5R | avg of 4 net $ |\n|---|---|---|---|---|---|")
for i in ideas:
    cells, tot = [], 0
    for v in VARS:
        s = stats(data[(i, v)]); tot += s["net"]
        cells.append(f"{s['net']:,.0f} ({s['n']}, t {s['t']:.1f})" if s["t"] is not None else f"{s['net']:,.0f} ({s['n']})")
    out.append(f"| {i} | " + " | ".join(cells) + f" | {tot/4:,.0f} |")
out.append("\n## Per-trade detail (win %, PF, median stop pts, share held <= 5 s)\n\n| idea | exit | trades | win % | PF | $/tr | med stop pts | <=5s % |\n|---|---|---|---|---|---|---|---|")
for i in ideas:
    for v in VARS:
        tr = data[(i, v)]; s = stats(tr)
        sp = st.median(abs(x["entry_price"] - x["sl"]) for x in tr if x.get("sl") is not None)
        f5 = 100 * sum(x["seconds"] <= 5 for x in tr) / len(tr)
        out.append(f"| {i} | {v} | {s['n']} | {s['win']:.1f} | {s['pf']:.2f} | {s['avg']:.1f} | {sp:.1f} | {f5:.1f} |")
out.append("\n## Session slices ($/trade (trades)); a slice is GOOD when positive in all 4 exits\n\n| idea | exit | " + " | ".join(n for n, _, _ in SESS) + " |\n|---|---|" + "---|" * len(SESS))
good = []
for i in ideas:
    sums = {n: [] for n, _, _ in SESS}
    for v in VARS:
        row = []
        for n, _, _ in SESS:
            s = stats([x for x in data[(i, v)] if x["sess"] == n]); sums[n].append(s)
            row.append(f"{s['avg']:.0f} ({s['n']})")
        out.append(f"| {i} | {v} | " + " | ".join(row) + " |")
    for n in sums:
        ss = sums[n]
        if all(s["n"] >= 100 and s["net"] > 0 for s in ss):
            good.append((i, n, [round(s["net"]) for s in ss], [round(s["t"], 1) for s in ss], [s["n"] for s in ss]))
out.append("\n## Slices positive in all 4 exits with 100+ trades each\n")
for g in good: out.append(f"- {g[0]} / {g[1]}: net {g[2]}, t {g[3]}, trades {g[4]}")
open(os.path.dirname(__file__) + "/results.md", "w").write("\n".join(out))
if __name__ == "__main__":
    print("\n".join(out))
