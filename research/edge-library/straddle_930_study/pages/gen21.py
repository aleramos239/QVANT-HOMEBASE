"""Heat maps of one volume group at several settings next to the plain-ATR reference. python gen21.py <out_dir>"""
import runpy,sys,os
OUT=sys.argv[1] if len(sys.argv)>1 else "."
g=runpy.run_path("gen20.py",run_name="g20")   # builds G and the helpers; also rewrites the gen20 pages
G,stats,cell,K,STOPS,TGTS,page=(g[x] for x in ("G","stats","cell","K","STOPS","TGTS","page"))
NAME="Stop = volume-weighted ATR"; body=['<h1>NQ 9:30 straddle: volume-weighted ATR stop at 3, 5 and 7 pts</h1><p>3:1 in-sample months only, 1 NQ, $4 round turn, 8 ticks slippage, cancel rule. Stop = row x the volume-weighted ATR of the last 14 five-minute bars (about 25% wider than plain ATR at the same multiple). Beside each: the plain-ATR group at the same offset.</p>']
for kv in (3,5,7):
    for fam,n in (("Volume",NAME),("Mean ATR","Both sides, fixed pts")):
        b=G[(fam,n,kv)]; s=stats(b)
        body.append(f'<h2>{n} at {kv} pts: avg {K(s["net"])}, {s["green"]}/25 green, years line {s["yl"]}/25, full target {s["tp"]:.1f}%</h2><div class=w><table><tr><th>Stop \\ RR'+"".join(f"<th>{t:g}R" for t in TGTS))
        for sv in STOPS: body.append(f'<tr><th>{sv:g}'+"".join(cell(b[(float(sv),float(t))]) for t in TGTS))
        body.append('</table></div>')
g["OUT"]=OUT; os.makedirs(OUT,exist_ok=True)
page("nq_930_vwatr_stop_3_5_7.html","NQ 9:30 Volume-Weighted ATR Stop","".join(body))
