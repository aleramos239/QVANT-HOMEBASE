"""One line per finished idea: the boxes averaged (never the best one). Headline = the ATR-stop and fixed-point boxes (every idea has them);
own-stop boxes are summed up apart because a rule with no structure level places no order there."""
import glob, json, os, subprocess
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
rows = []
for d in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "done_*"))):
    n = os.path.basename(d)[5:]
    sp = json.load(open(os.path.join(os.path.dirname(__file__), "specs", n + ".json")))
    r = subprocess.run([PY, "bp.py", "wf", "show", f"{n}-NQ-tf{sp['bar_sizes'][0]}", "--json"], cwd=ED, capture_output=True, text=True)
    try:
        allb = json.loads(r.stdout)["wf"]["is"]
    except Exception:
        rows.append((n, None)); continue
    def agg(bx):
        if not bx: return None
        m = lambda k: sum(b[k] or 0 for b in bx) / len(bx)
        return dict(n=len(bx), green=sum(b["net"] > 0 for b in bx) / len(bx), tr=m("trades"), avg=m("avg_trade"), t=m("t_stat"), t2=sum((b["t_stat"] or 0) >= 2 for b in bx),
                    pf=m("pf"), yg=m("years_green"), net=m("net"))
    rows.append((n, agg([b for b in allb if b["settings"].get("stop_mode") in ("atr", "pts")]), agg([b for b in allb if b["settings"].get("stop_mode") == "own"])))
print("%-34s %4s %6s %7s %8s %6s %4s %5s %5s %9s | own: %4s %6s %6s" % ("idea", "box", "green", "trades", "avg$/tr", "avg_t", "t>=2", "PF", "yrs+", "avg net", "box", "green", "avg_t"))
for row in sorted(rows, key=lambda x: -(x[1]["t"] if x[1] else -9)):
    if row[1] is None:
        print(row[0], "no result"); continue
    n, a, o = row
    print("%-34s %4d %5.0f%% %7.0f %8.1f %6.2f %4d %5.2f %5.1f %9.0f | %4s %6s %6s" % (n, a["n"], a["green"] * 100, a["tr"], a["avg"], a["t"], a["t2"], a["pf"], a["yg"], a["net"],
          o["n"] if o else "-", "%.0f%%" % (o["green"] * 100) if o else "-", "%.2f" % o["t"] if o else "-"))
