"""One line per finished idea: only the fixed-point (pts) boxes, averaged over the boxes (never the best one)."""
import glob, json, os, subprocess, sys
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
rows = []
for d in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "done_f100_*"))):
    n = os.path.basename(d)[5:]
    r = subprocess.run([PY, "bp.py", "wf", "show", n + "-NQ-tf" + ("15" if n.endswith("15") else "5"), "--json"], cwd=ED, capture_output=True, text=True)
    try:
        bx = [b for b in json.loads(r.stdout)["wf"]["is"] if b["settings"].get("stop_mode") == "pts"]
    except Exception:
        continue
    if not bx:
        continue
    m = lambda k: sum(b[k] or 0 for b in bx) / len(bx)
    rows.append((n[5:], len(bx), sum(b["net"] > 0 for b in bx) / len(bx), m("trades") / 947 * 1.0, m("per_week") / 5, m("avg_trade"),
                 m("t_stat"), sum((b["t_stat"] or 0) >= 2 for b in bx), m("pf"), m("wr_minus_be"), m("years_green")))
rows.sort(key=lambda x: -x[6])
print("%-14s %4s %6s %6s %8s %6s %4s %5s %7s %5s" % ("idea", "box", "green", "tr/day", "avg$/tr", "avg_t", "t>=2", "PF", "wr-be", "yrs+"))
for n, k, g, _, td, at, t, t2, pf, wb, yg in rows:
    print("%-14s %4d %5.0f%% %6.2f %8.1f %6.2f %4d %5.2f %6.1f%% %5.1f" % (n, k, g * 100, td, at, t, t2, pf, wb * 100, yg))
