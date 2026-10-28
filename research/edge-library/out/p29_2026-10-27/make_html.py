"""Build p29.html: one block per idea, 4 exit boxes each, shaded by $/trade, with a 5-session strip inside each box. Reads the same 92 runs as slices.py."""
import os, runpy, html
g = runpy.run_path(os.path.dirname(os.path.abspath(__file__)) + "/slices.py")
data, ideas, stats, SESS, VARS = g["data"], g["ideas"], g["stats"], g["SESS"], g["VARS"]
D = {"31": "EMA20 > EMA50 trend state turns on", "32": "EMA9 x EMA21 cross", "35": "close crosses the 1h EMA50", "36": "4 of last 6 bars make higher highs / lower lows",
     "37": "RSI(2) under 10 long / over 90 short", "38": "RSI(14) crosses 50", "41": "morning move, pullback to 50% (09:30-10:00 move, enter 10:00-11:00)",
     "42": "same, pullback to 38.2%", "43": "0.5 daily ATR move from the open, then touch of the open", "44": "RTH VWAP pullback in the morning direction",
     "45": "EMA20 pullback in an EMA50 trend", "49": "engulfing candle", "81": "range burst (2x avg of 20 bars), follow", "82": "range burst, fade",
     "83": "volume burst (3x avg), follow colour", "84": "close beyond the prior 4 bars' high / low (15m)", "87": "cross of yesterday's 16:00 close (proxy)",
     "89": "cross of yesterday's 09:30 open", "90": "cross of the 3-day high / low"}
EX = {"C0.5": "candle stop, 0.5R", "C1.5": "candle stop, 1.5R", "A0.5": "1.5 ATR stop, 0.5R", "A1.5": "1.5 ATR stop, 1.5R"}
CL = 60.0
def col(v, n=1):
    if n == 0: return "#222"
    a = min(abs(v) / CL, 1.0) ** 0.7
    r, g_, b = (30, 140, 70) if v > 0 else (170, 45, 45)
    return f"rgba({r},{g_},{b},{0.12 + 0.78 * a:.2f})"
out = ["""<!doctype html><meta charset=utf-8><title>p29: 22 simple ideas x 4 exits (NQ, 3:1 in-sample months)</title>
<style>body{background:#111;color:#ddd;font:14px -apple-system,sans-serif;margin:24px}h1{font-size:20px}h2{font-size:15px;margin:26px 0 2px}
.d{color:#999;font-size:12px;margin-bottom:6px}.row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.b{border:1px solid #333;border-radius:6px;padding:8px}
.n{font-size:11px;color:#aaa}.big{font-size:20px;font-weight:600}.m{font-size:12px;line-height:1.5}.s{display:flex;gap:2px;margin-top:6px}
.s div{flex:1;text-align:center;font-size:10px;padding:3px 0;border-radius:3px}.k{color:#999;font-size:12px;margin:4px 0 14px}</style>
<h1>22 simple ideas, 4 exits each (NQ, 3:1 in-sample months, 18:00-15:00)</h1>
<div class=k>Box shade = average $ per trade after costs (green profit, red loss, full colour at +/-$60). Box number = #idea.exit. Bottom strip = $/trade by entry session
(Eve 18-00, Asia 00-03, London 03-09:30, NY AM 09:30-12, NY PM 12-15); grey = no trades. In-sample only, no test months. t = per-trade t-statistic; real needs t 2+.</div>"""]
cell = 0
for i in ideas:
    base = i.split()[0]; lab = D[base] + (" - on 1-minute bars" if " 1m" in i else "")
    out.append(f"<h2>{html.escape(i)}</h2><div class=d>{html.escape(lab)}</div><div class=row>")
    for v in VARS:
        cell += 1; tr = data[(i, v)]; s = stats(tr)
        strip = ""
        for n, _, _ in SESS:
            ss = stats([x for x in tr if x["sess"] == n])
            strip += f"<div style='background:{col(ss['avg'], ss['n'])}' title='{n}: {ss['n']} trades, net ${ss['net']:,.0f}'>{ss['avg']:.0f}</div>" if ss["n"] else "<div style='background:#2a2a2a;color:#666'>-</div>"
        t = f"{s['t']:.2f}" if s["t"] is not None else "-"
        out.append(f"<div class=b style='background:{col(s['avg'])}'><div class=n>#{cell} &middot; {EX[v]}</div><div class=big>${s['net']:,.0f}</div>"
                   f"<div class=m>{s['avg']:.0f} $/trade &middot; {s['n']:,} trades<br>win {s['win']:.0f}% &middot; PF {s['pf']:.2f} &middot; t {t}</div><div class=s>{strip}</div></div>")
    out.append("</div>")
open(os.path.dirname(os.path.abspath(__file__)) + "/p29.html", "w").write("\n".join(out))
print(cell, "boxes")
