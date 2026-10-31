"""One HTML page: the 11 best FVG ideas (by average t of the fixed-point boxes), each with its stop x target heat maps (one grid per min gap).
Run from anywhere: python make_html.py. In-sample months only (the 3:1 blocks); test months not read."""
import json, os, subprocess, html
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
TOP = ["ovw15", "open15", "pdc15", "htf", "newterr", "ovw", "drive", "sma", "open", "ohr", "onb3"]
WHAT = {
    "ovw15": "15-min gap, only with the side where the open AND VWAP agree",
    "open15": "15-min gap, only with the day's drift from the open",
    "pdc15": "15-min gap, only with the side of the prior close",
    "htf": "5-min gap, only with the higher-timeframe side",
    "newterr": "5-min gap, only when the gap forms in new territory",
    "ovw": "5-min gap, only with the side where the open AND VWAP agree",
    "drive": "5-min gap, only with the side of the 09:30-10:00 opening drive",
    "sma": "5-min gap, only with the side of the SMA",
    "open": "5-min gap, only with the day's drift from the open",
    "ohr": "5-min gap, only with the break of the first-hour (09:30-10:30) range",
    "onb3": "5-min gap, only with the side that broke the overnight range",
}
STOPS, TGTS = [15, 25, 40, 60], [0.5, 0.75, 1.0, 1.5, 2.0]
SPEC = lambda n: json.load(open(os.path.expanduser("~/.homebase/ideas/f100_%s/spec.json" % n))) if os.path.exists(os.path.expanduser("~/.homebase/ideas/f100_%s/spec.json" % n)) else {}


EARLIEST = {"drive": "10:00 (the drive is read once 09:30-10:00 has closed)", "ohr": "10:30 (after the first-hour range has closed)"}
def window(n):
    f = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "specs", "f100_%s.json" % n)))
    fx, tf = f["fixed"], f["bar_sizes"][0]
    first = EARLIEST.get(n, "10:15" if tf == "15" else "09:45") + ("" if n in EARLIEST else " (a gap needs 3 closed %s-min bars)" % tf)
    return "entries %s-%s ET, flat 15:58, up to %d trades a day; earliest entry %s" % (fx.get("start", "09:30"), fx.get("end", "15:00"), f["limits"]["max_tr"], first)

def boxes(n):
    r = subprocess.run([PY, "bp.py", "wf", "show", "f100_%s-NQ-tf%s" % (n, "15" if n.endswith("15") else "5"), "--json"], cwd=ED, capture_output=True, text=True)
    return [b for b in json.loads(r.stdout)["wf"]["is"] if b["settings"].get("stop_mode") == "pts"]

def rr(b):                       # realized RR = average win / average loss, from profit factor and win rate
    w, pf = b["win_rate"], b["pf"]
    return pf * (1 - w) / w if w and pf else 0.0

def colour(v, scale):
    k = max(-1.0, min(1.0, v / scale))
    return "rgba(34,139,34,%.2f)" % (0.15 + 0.6 * k) if k >= 0 else "rgba(200,40,40,%.2f)" % (0.15 + 0.6 * -k)

def cell(b):
    if not b or not b["trades"]:
        return "<td class=e>-</td>"
    return ("<td style='background:%s'><b>%s$%s</b> /tr<br>win %.0f%% (b/e %.0f%%)<br>RR %.2f<br>Sharpe %.2f<br>%.1f tr/wk &middot; net %s<br>t %.2f</td>"
            % (colour(b["avg_trade"], 80), "-" if b["avg_trade"] < 0 else "", "{:,.0f}".format(abs(b["avg_trade"])), b["win_rate"] * 100, b["breakeven"] * 100,
               rr(b), b["sharpe"] or 0, b["per_week"], "{:,.0f}".format(b["net"]), b["t_stat"] or 0))

parts, rows = [], []
for n in TOP:
    bx = boxes(n)
    m = lambda k: sum((b[k] or 0) for b in bx) / len(bx)
    green, t2 = sum(b["net"] > 0 for b in bx), sum((b["t_stat"] or 0) >= 2 for b in bx)
    rows.append("<tr><td><a href='#%s'>%s</a></td><td>%s</td><td>%d/%d</td><td>%.1f</td><td>$%.0f</td><td>%.1f%%</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%d</td></tr>" % (
        n, n, WHAT[n], green, len(bx), m("per_week"), m("avg_trade"), m("win_rate") * 100, sum(rr(b) for b in bx) / len(bx), m("sharpe"), m("t_stat"), m("pf"), t2))
    grids = []
    for g in sorted({b["settings"]["min_gap"] for b in bx}):
        t = "<table class=g><tr><th>stop \\ target</th>" + "".join("<th>%gR</th>" % x for x in TGTS) + "</tr>"
        for s in STOPS:
            t += "<tr><th>%d pts</th>" % s
            for x in TGTS:
                c = [b for b in bx if b["settings"]["min_gap"] == g and b["settings"]["stop_val"] == s and abs(b["settings"]["tgt_r"] - x) < 1e-9]
                t += cell(c[0] if c else None)
            t += "</tr>"
        grids.append("<h4>smallest gap = %g x ATR</h4>%s</table>" % (g, t))
    parts.append("<section id=%s><h2>%s</h2><div class=sub>%s. <b>Window:</b> %s. Average of the 60 boxes: %d green, %.1f trades/week, $%.0f a trade, Sharpe %.2f, t %.2f.</div>%s</section>" % (
        n, n, WHAT[n], window(n), green, m("per_week"), m("avg_trade"), m("sharpe"), m("t_stat"), "".join(grids)))

import glob
singles = []
for d in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "done_f100_*")):
    n = os.path.basename(d)[10:]
    try:
        for b in boxes(n):
            if (b["t_stat"] or 0) >= 2.5 and b["years_green"] >= 5 and b["trades"] >= 300:
                singles.append((n, b))
    except Exception:
        pass
singles.sort(key=lambda x: -x[1]["t_stat"])
srows = "".join("<tr><td>%s</td><td>%s</td><td>%d</td><td>%.1f</td><td>$%.0f</td><td>%.0f%%</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%d/6</td><td>$%s</td></tr>" % (
    n, b["box"], b["trades"], b["per_week"], b["avg_trade"], b["win_rate"] * 100, rr(b), b["sharpe"] or 0, b["t_stat"], b["years_green"], "{:,.0f}".format(b["max_dd"] or 0))
    for n, b in singles[:40])
best = ("<section id=best><h2>Best single boxes (all 68 specs)</h2><div class=sub>%d boxes have t &ge; 2.5, 300+ trades and 5+ green years; the 40 best by t are listed. "
        "These are the best of about 4,000 boxes, so treat them as leads, not results (the idea averages above are the fairer read).</div>"
        "<table class=s><tr><th>idea</th><th>box</th><th>trades</th><th>tr/wk</th><th>avg $/tr</th><th>win</th><th>RR</th><th>Sharpe</th><th>t</th><th>years green</th><th>max drawdown</th></tr>%s</table></section>" % (len(singles), srows))
CSS = """body{font:13px -apple-system,Helvetica,sans-serif;margin:24px;color:#222;background:#fafafa}h1{margin:0 0 4px}.sub{color:#555;margin:4px 0 10px}
table{border-collapse:collapse}.g td{border:1px solid #ddd;padding:5px 7px;min-width:118px;font-size:12px;line-height:1.35}.g th{background:#eee;padding:5px 8px;border:1px solid #ddd}
.s td,.s th{border:1px solid #ddd;padding:4px 8px;text-align:right}.s td:nth-child(2),.s th:nth-child(2){text-align:left}.e{color:#aaa;text-align:center}
section{margin:34px 0;padding-top:10px;border-top:2px solid #ccc}h4{margin:14px 0 4px}"""
head = ("<h1>FVG: the 11 best ideas, fixed stop and target heat maps</h1><div class=sub>NQ, in-sample months of the 3:1 blocks only (test months not read, nothing picked). "
        "Fixed-point stops 15/25/40/60 pts, targets 0.5-2 R, flat 15:58, up to 3 trades a day. Ranked by the average t of the 60 boxes. "
        "Each cell: average trade, win rate (and break-even win rate), realized RR (average win / average loss), Sharpe (traded days only), trades per week, net, t-stat. "
        "Colour = average trade (green positive, red negative). Judge the average, not the best cell.</div>"
        "<table class=s><tr><th>idea</th><th>rule</th><th>boxes green</th><th>tr/week</th><th>avg $/tr</th><th>win</th><th>avg RR</th><th>Sharpe</th><th>avg t</th><th>PF</th><th>boxes t&ge;2</th></tr>"
        + "".join(rows) + "</table>")
out = os.path.join(os.path.dirname(__file__), "fvg_top10_heatmaps.html")
open(out, "w").write("<!doctype html><meta charset=utf-8><title>FVG top 11 heat maps</title><style>%s</style>%s%s" % (CSS, head, "".join(parts) + best))
print(out, os.path.getsize(out))
