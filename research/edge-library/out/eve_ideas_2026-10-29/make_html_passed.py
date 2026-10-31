"""HTML: the boxes of ideas 15-16 and 23 that PASSED (green in-sample and on the test months, every touching box green in both), table + hm60 heat maps with in-sample and test-month numbers per cell."""
import json, os, subprocess
ED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PY = os.path.expanduser("~/ramos-quant-homebase/.venv-research/bin/python")
IDEAS = [("i15_16_close_loc_follow", "#15-16 follow the Globex-day close location (top 10% -> long, bottom 10% -> short)"),
         ("i23_new_high_long", "#23 the day made a new 20-day high -> long the evening")]
STOPS = {"atr": [0.5, 1, 1.5, 2], "pts": [15, 25, 40, 60]}; TG = [0.5, 0.75, 1, 1.5, 2]
LAB = {"atr": "ATR x%g", "pts": "%g pts"}
def show(store): return json.loads(subprocess.run([PY, "bp.py", "wf", "show", store, "--json"], cwd=ED, capture_output=True, text=True).stdout)["wf"]
def rr(b):
    w, pf = b["win_rate"], b["pf"]
    return pf * (1 - w) / w if w and pf else 0.0
def money(x): return ("-" if x < 0 else "") + "${:,.0f}".format(abs(x))
def colour(v, s):
    k = max(-1.0, min(1.0, v / s))
    return "rgba(34,139,34,%.2f)" % (0.15 + 0.6 * k) if k >= 0 else "rgba(200,40,40,%.2f)" % (0.15 + 0.6 * -k)
def line(tag, r):
    return "%s: %s/tr, net %s, win %.0f%% (b/e %.0f%%), RR %.2f, Sharpe %.2f, %.1f tr/wk, t %.2f" % (tag, money(r["avg_trade"]), money(r["net"]), r["win_rate"] * 100, r["breakeven"] * 100, rr(r), r["sharpe"] or 0, r["per_week"], r["t_stat"] or 0)
data, summary, tables, sections = {}, [], [], []
for n, what in IDEAS:
    parent = n + "-NQ-tf5"
    G = {}
    for b in show(parent)["is"]:
        s = b["settings"]
        if s["stop_mode"] == "own": continue
        o = show(parent + "__" + b["box"])["oos"]["record"]
        G[(s["off_min"], s["stop_mode"], s["stop_val"], s["tgt_r"])] = (b, o)
    ok = lambda k: k in G and G[k][0]["net"] > 0 and G[k][1]["net"] > 0
    passed = set()
    for (om, sm, sv, tg) in G:
        if not ok((om, sm, sv, tg)): continue
        si, ti = STOPS[sm].index(sv), TG.index(tg)
        if all(ok((om, sm, STOPS[sm][a], TG[c])) for a in range(max(0, si - 1), min(4, si + 2)) for c in range(max(0, ti - 1), min(5, ti + 2))):
            passed.add((om, sm, sv, tg))
    data[n] = (G, passed)
    rows = ""
    for k in sorted(passed, key=lambda k: -G[k][1]["net"]):
        i, o = G[k][0], G[k][1]
        rows += ("<tr><td>%s</td><td>%d</td><td>%s</td><td>%gR</td><td>%s</td><td>%s</td><td>%.0f%% / %.0f%%</td><td>%.2f / %.2f</td><td>%.2f / %.2f</td><td>%.1f / %.1f</td><td>%.2f / %.2f</td></tr>" % (
            "23" if n.startswith("i23") else "15-16", k[0], LAB[k[1]] % k[2], k[3], money(i["net"]) + " / " + money(o["net"]), money(i["avg_trade"]) + " / " + money(o["avg_trade"]),
            i["win_rate"] * 100, o["win_rate"] * 100, rr(i), rr(o), i["sharpe"] or 0, o["sharpe"] or 0, i["per_week"], o["per_week"], i["t_stat"] or 0, o["t_stat"] or 0))
    summary.append((n, what, len(passed), len(G)))
    tables.append((n, what, rows))
    grids = ""
    for om in sorted({k[0] for k in G}):
        t = "<h4>entry %d min after 18:00</h4>" % om
        for sm in ("atr", "pts"):
            t += "<table class=g><tr><th>stop \\ target</th>" + "".join("<th>%gR</th>" % x for x in TG) + "</tr>"
            for sv in STOPS[sm]:
                t += "<tr><th>%s</th>" % (LAB[sm] % sv)
                for x in TG:
                    k = (om, sm, sv, x); i, o = G[k]; p = k in passed
                    blk = lambda tag, r: "<div class=blk><b>%s</b> (%d tr)<br>avg trade %s &middot; net %s<br>win %.0f%% (b/e %.0f%%) &middot; RR %.2f<br>Sharpe %.2f &middot; %.1f tr/wk &middot; t %.2f</div>" % (tag, r["trades"], money(r["avg_trade"]), money(r["net"]), r["win_rate"] * 100, r["breakeven"] * 100, rr(r), r["sharpe"] or 0, r["per_week"], r["t_stat"] or 0)
                    t += "<td class='%s' style='background:%s'>%s%s</td>" % ("pass" if p else "", colour(o["avg_trade"], 120), blk("IN-SAMPLE", i), blk("OUT-OF-SAMPLE (test months)", o))
                t += "</tr>"
            t += "</table>"
        grids += t
    sections.append("<section id=%s><h2>%s</h2><div class=sub>%s. Passed: %d of %d ATR and fixed-point boxes (thick green border). Each cell shows in-sample and out-of-sample (test months) metrics; colour = out-of-sample average trade.</div>%s</section>" % (n, n, what, len(passed), len(G), grids))
CSS = """body{font:13px -apple-system,Helvetica,sans-serif;margin:24px;color:#222;background:#fafafa}h1{margin:0 0 4px}.sub{color:#555;margin:4px 0 10px}
table{border-collapse:collapse;margin-bottom:10px}.g td{border:1px solid #ddd;padding:5px 7px;min-width:230px;font-size:11px;line-height:1.35;opacity:.7}.blk{padding:2px 0}.blk+.blk{border-top:1px dashed #888;margin-top:3px;padding-top:4px}.g td.pass{opacity:1;outline:3px solid #1a7f1a;outline-offset:-3px}
.g th{background:#eee;padding:5px 8px;border:1px solid #ddd}.is{color:#555}.s td,.s th{border:1px solid #ddd;padding:4px 8px;text-align:right}.s td:first-child{text-align:left}
section{margin:34px 0;padding-top:10px;border-top:2px solid #ccc}h4{margin:14px 0 4px}"""
head = ("<h1>Evening ideas 15-16 and 23: the boxes that passed</h1><div class=sub>NQ 5-min, evening, one trade a night, both sides. <b>Passed</b> = net above $0 in-sample AND on the test months, and every touching box (adjacent stop and target, same entry time and stop type) also above $0 in both. "
        "In the table each pair is in-sample / test months. Test months were read once (2026-10-30, owner's word); nothing picked or approved. Both ideas lean long, so part of this may be the 2021-26 bull market. RR = average win / average loss; Sharpe = traded days only.</div>")
tbl = ""
for n, what, rows in tables:
    tbl += "<h3>%s</h3><table class=s><tr><th>idea</th><th>entry min</th><th>stop</th><th>target</th><th>net (in-sample / test)</th><th>avg trade</th><th>win</th><th>realized RR</th><th>Sharpe</th><th>trades/wk</th><th>t</th></tr>%s</table>" % (what, rows)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "eve_passed_boxes.html"), "w").write("<!doctype html><meta charset=utf-8><title>Passed boxes</title><style>%s</style>%s%s%s" % (CSS, head, tbl, "".join(sections)))
for s in summary: print(s)
