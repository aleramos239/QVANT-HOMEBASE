"""One HTML page: hm60 heat maps (stop x target, one grid per entry offset) for ideas 15-16 and 23. In-sample months of the 3:1 blocks only."""
import json, os, subprocess
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
IDEAS = [("i15_16_close_loc_follow", "#15-16 follow the Globex-day close location: closed in the top 10% -> long, bottom 10% -> short"),
         ("i23_new_high_long", "#23 the day made a new 20-day high -> long the evening")]
STOPS = [("atr", v, "ATR x%g" % v) for v in (0.5, 1, 1.5, 2)] + [("own", v, "own stop x%g" % v) for v in (0.5, 1, 1.5, 2)] + [("pts", v, "%d pts" % v) for v in (15, 25, 40, 60)]
TGTS = [0.5, 0.75, 1.0, 1.5, 2.0]
def boxes(n):
    r = subprocess.run([PY, "bp.py", "wf", "show", "%s-NQ-tf5" % n, "--json"], cwd=ED, capture_output=True, text=True)
    return json.loads(r.stdout)["wf"]["is"]
def rr(b):                       # realized RR = average win / average loss, from profit factor and win rate
    w, pf = b["win_rate"], b["pf"]
    return pf * (1 - w) / w if w and pf else 0.0
def colour(v, s):
    k = max(-1.0, min(1.0, v / s))
    return "rgba(34,139,34,%.2f)" % (0.15 + 0.6 * k) if k >= 0 else "rgba(200,40,40,%.2f)" % (0.15 + 0.6 * -k)
def money(x): return ("-" if x < 0 else "") + "${:,.0f}".format(abs(x))
def cell(b):
    if not b or not b["trades"]: return "<td class=e>no trades</td>"
    return ("<td style='background:%s'><b>%s</b> avg trade<br>net %s<br>win %.0f%% (b/e %.0f%%)<br>realized RR %.2f<br>Sharpe %.2f<br>%.1f trades/wk<br>t %.2f &middot; %s/6 yrs<br>worse fills %s</td>"
            % (colour(b["avg_trade"], 80), money(b["avg_trade"]), money(b["net"]), b["win_rate"] * 100, b["breakeven"] * 100, rr(b), b["sharpe"] or 0,
               b["per_week"], b["t_stat"] or 0, b["years_green"], money(b["worse_fills_net"]) if b["worse_fills_net"] is not None else "-"))
sections, rows = [], []
for n, what in IDEAS:
    bx = boxes(n)
    ok = [b for b in bx if b["trades"] and b["settings"]["stop_mode"] != "own"]
    m = lambda k: sum((b[k] or 0) for b in ok) / len(ok)
    green, t2 = sum(b["net"] > 0 for b in ok), sum((b["t_stat"] or 0) >= 2 for b in ok)
    rows.append("<tr><td><a href='#%s'>%s</a></td><td>%s</td><td>%d/%d</td><td>%d</td><td>%.1f</td><td>%s</td><td>%s</td><td>%.1f%%</td><td>%.2f</td><td>%.2f</td><td>%.2f</td></tr>" % (
        n, n, what, green, len(ok), t2, m("per_week"), money(m("avg_trade")), money(m("net")), m("win_rate") * 100, sum(rr(b) for b in ok) / len(ok), m("sharpe"), m("t_stat")))
    grids = []
    for om in sorted({b["settings"]["off_min"] for b in bx}):
        t = "<table class=g><tr><th>stop \\ target</th>" + "".join("<th>%gR</th>" % x for x in TGTS) + "</tr>"
        for sm, sv, lab in STOPS:
            t += "<tr><th>%s</th>" % lab
            for x in TGTS:
                c = [b for b in bx if b["settings"]["off_min"] == om and b["settings"]["stop_mode"] == sm and abs(b["settings"]["stop_val"] - sv) < 1e-9 and abs(b["settings"]["tgt_r"] - x) < 1e-9]
                t += cell(c[0] if c else None)
            t += "</tr>"
        grids.append("<h4>entry %d min after 18:00</h4>%s</table>" % (om, t))
    sections.append("<section id=%s><h2>%s</h2><div class=sub>%s. Average of the %d ATR and fixed-point boxes (own-stop boxes left out of the averages): %d green, %d with t&ge;2, %.1f trades/week, %s a trade, Sharpe %.2f.</div>%s</section>" % (
        n, n, what, len(ok), green, t2, m("per_week"), money(m("avg_trade")), m("sharpe"), "".join(grids)))
CSS = """body{font:13px -apple-system,Helvetica,sans-serif;margin:24px;color:#222;background:#fafafa}h1{margin:0 0 4px}.sub{color:#555;margin:4px 0 10px}
table{border-collapse:collapse}.g td{border:1px solid #ddd;padding:5px 7px;min-width:132px;font-size:11.5px;line-height:1.35}.g th{background:#eee;padding:5px 8px;border:1px solid #ddd}
.s td,.s th{border:1px solid #ddd;padding:4px 8px;text-align:right}.s td:nth-child(2),.s th:nth-child(2){text-align:left}.e{color:#aaa;text-align:center}
section{margin:34px 0;padding-top:10px;border-top:2px solid #ccc}h4{margin:14px 0 4px}"""
head = ("<h1>Evening ideas 15-16 and 23: hm60 heat maps</h1><div class=sub>NQ 5-min, evening 18:00-23:55 ET, flat 23:55, one trade a night, both sides. In-sample months of the 3:1 blocks only (test months not read, nothing picked). "
        "Each cell: average trade, net, win rate (and break-even win rate), realized RR (average win / average loss), Sharpe (traded days only), trades per week, t-stat, green years, net with worse fills. "
        "Colour = average trade (green positive, red negative). Judge the average, not the best cell. Own-stop rows are empty or thin where the rule gives no structure level.</div>"
        "<table class=s><tr><th>idea</th><th>rule</th><th>boxes green</th><th>boxes t&ge;2</th><th>trades/wk</th><th>avg trade</th><th>avg net</th><th>win</th><th>avg realized RR</th><th>Sharpe</th><th>avg t</th></tr>" + "".join(rows) + "</table>")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eve_15_16_23_heatmaps.html")
open(out, "w").write("<!doctype html><meta charset=utf-8><title>Evening 15-16, 23 heat maps</title><style>%s</style>%s%s" % (CSS, head, "".join(sections)))
print(out, os.path.getsize(out))
