"""HTML heat map of nq_first15_follow_own's 120 in-sample boxes (read-only: the saved 3:1 in-sample store, no test month)."""
import re, json
from pathlib import Path
import numpy as np, pandas as pd

import sys
NAME, TF, WFTXT = (sys.argv[1:4] + [None] * 3)[:3] if len(sys.argv) > 3 else ("nq_first15_follow_own", "15", "/tmp/wf_first15_own.txt")
W = Path(__file__).resolve().parents[2]
D = W / f"runs_wf/{NAME}-NQ-tf{TF}/is/"
z = np.load(D / "cells.npz")
t = pd.read_csv(D / "table.csv"); t = t[t.sess == "all"].reset_index(drop=True)
off = z["off"]
day_of = pd.to_datetime(z["entry_ms"], unit="ms").normalize()
weeks = 940 / 5.0                                                # the in-sample months' 940 trading days / 5 (the market-order idea trades them all; a limit idea skips days)
rank = {}                                                        # the number the owner picks by (the table's, best win rate first)
for ln in open(WFTXT):
    m = re.match(r"\s*(\d+)\s+((?:off_min|retr)\S+)\s", ln)
    if m: rank[m.group(2)] = int(m.group(1))

cells = []
for i, c in t.iterrows():
    s = slice(off[i], off[i + 1]); net = z["net"][s]
    w, l = net[net > 0], net[net <= 0]
    day = pd.Series(net, index=day_of[s]).groupby(level=0).sum()   # Sharpe: the days that had a trade only
    m = re.match(r"(?:off_min|retr)([\dp]+)_(atr|own)([\dp]+)-r([\dp]+)", c.cell)
    cells.append(dict(n=rank[c.cell], box=c.cell, off=m[1].replace("p", "."), stop=m[2], mult=m[3].replace("p", "."), tgt=m[4].replace("p", "."),
                      net=float(net.sum()), sharpe=float(day.mean() / day.std() * np.sqrt(252)), win=float((net > 0).mean() * 100),
                      rr=float(w.mean() / abs(l.mean())) if len(w) and len(l) else None, avg=float(net.mean()),
                      perwk=float(net.sum() / weeks), trwk=len(net) / weeks, trades=len(net)))
assert all(abs(c["net"] - float(t.net[i])) < 1 for i, c in enumerate(cells)), "net differs from the saved table"
assert len(cells) == 120 and len(rank) == 120
html = """<!doctype html><meta charset=utf-8><title>@NAME@: 120 in-sample boxes</title>
<style>
body{font:13px -apple-system,Helvetica,sans-serif;margin:20px;color:#222}h1{font-size:18px}h2{font-size:15px;margin:26px 0 6px}
table{border-collapse:collapse}th{font-weight:600;padding:4px 8px;color:#555}td{width:150px;padding:5px 7px;border:2px solid #fff;font-size:11.5px;line-height:1.35;vertical-align:top}
td b{font-size:14px;display:block}.n{float:right;color:#555;font-size:10px}.sub{color:#666;margin:4px 0 12px}select{font-size:13px}
</style>
<h1>@NAME@: every box, 3:1 in-sample months only (no test month)</h1>
<div class=sub>1 NQ contract. Rows = stop (ATR x, or candle extreme x), columns = target in R. Shade = <select id=by onchange=paint()><option value=net>net $</option><option value=sharpe>Sharpe (traded days)</option></select>, green profit, red loss, same scale in all three grids.
Cell: net $ (bold) · Sharpe · win % · realised RR (avg win / avg loss) · avg trade $ · $ per week · trades per week. Top-right: the box's table number (pick by it). Trades per week below 5 = days with no fill. Weeks = trading days in the sample / 5 (@WEEKS@).</div>
<div id=g></div>
<script>
const C=@CELLS@;const NAME="@NAME@";const T=["0.5","0.75","1","1.5","2"],S=[["atr","0.5"],["atr","1"],["atr","1.5"],["atr","2"],["own","0.5"],["own","1"],["own","1.5"],["own","2"]];
const f=(x,d=0)=>x.toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
function col(v,m){const a=Math.min(Math.abs(v)/m,1),h=v>=0?135:0;return `hsl(${h} 60% ${96-a*52}%)`}
function paint(){const by=document.getElementById("by").value,m=Math.max(...C.map(c=>Math.abs(c[by])));let h="";
for(const o of [...new Set(C.map(c=>c.off))].sort((a,b)=>a-b)){h+=`<h2>${NAME.includes("retr")?"Limit "+o+" of the candle range back":"Entry delay off_min "+o}</h2><table><tr><th>`+T.map(t=>`<th>target ${t} R`).join("");
for(const [s,k] of S){h+=`<tr><th>${s=="atr"?"ATR":"candle extreme"} x ${k}`;for(const t of T){const c=C.find(c=>c.off==o&&c.stop==s&&c.mult==k&&c.tgt==t);
h+=`<td style="background:${col(c[by],m)}"><span class=n>#${c.n}</span><b>${c.net<0?"-":""}$${f(Math.abs(c.net))}</b>Sharpe ${f(c.sharpe,2)} · win ${f(c.win)}%<br>RR ${c.rr==null?"-":f(c.rr,2)} · avg ${c.avg<0?"-":""}$${f(Math.abs(c.avg))}<br>${c.perwk<0?"-":""}$${f(Math.abs(c.perwk))}/wk · ${f(c.trwk,1)} tr/wk</td>`}}h+="</table>"}
document.getElementById("g").innerHTML=h}paint();
</script>""".replace("@NAME@", NAME).replace("@WEEKS@", f"{weeks:.1f}").replace("@CELLS@", json.dumps(cells))
out = Path(__file__).with_name(f"{NAME}.html"); out.write_text(html)
print(out, weeks, len(html))
