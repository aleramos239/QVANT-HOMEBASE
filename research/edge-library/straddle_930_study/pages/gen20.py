"""Median-vs-mean ATR page and the top-5 heat maps over every group (run x setting), 2026-11-01.
Run from this folder: python gen20.py <out_dir>. A group = one run at one setting (25 boxes: 5 stops x 5 targets)."""
import json,os,glob,collections,sys
W=os.path.expanduser("~/ramos-quant-homebase/homebase/.state/tester/walkforward/")
OUT=sys.argv[1] if len(sys.argv)>1 else "."
STOPS=[3,3.5,4,4.5,5]; TGTS=[0.5,0.75,1,1.5,2]
def d_of(pat): return os.path.basename(glob.glob(W+pat)[0])
def load(pat,kk,ks,sk="ctl.stop_atr"):
    d=d_of(pat); g=json.load(open(W+d+"/grid.json")); out={}
    if g.get("status")!="done": return out
    for c in g["cells"]:
        p=c["params"]; k=float(p[kk]); s=float(p[sk]); r=float(p["ctl.target_rr"])
        if k not in [float(x) for x in ks] or s not in STOPS or r not in TGTS: continue
        i=c["i"]; a=json.load(open(f"{W}{d}/cells/{i:02d}/run.json"))["report"]["summary"]["all"]
        t=json.load(open(f"{W}{d}/cells/{i:02d}/trades.json")); t=t if isinstance(t,list) else t["trades"]
        y=collections.Counter()
        for x in t: y[x["date"][:4]]+=x["net"]
        n=a["net_profit"]; yl=sum(v>0 for v in y.values())>=4 and n>0 and max(y.values())/n<=.5
        out[(k,s,r)]=dict(net=n,sh=a["sharpe"],dd=a["max_drawdown"],win=a["win_rate"],rr=a["rr"],tr=len(t),yl=yl,
                          tp=100*sum(1 for x in t if x["exit_reason"]=="tp")/max(len(t),1))
    return out
# (key, name, k label, k values, k param, [run patterns (mean ATR runs are split over two)], stop param)
P3=["about 3.6 pts","about 5.4 pts","about 7.2 pts"]
MEAN=[("pct","Percent of price",[0.02,0.03,0.04],"k",["*-411c","*-eb47"]),
("preopen","Pre-open range x k",[0.1,0.15,0.2],"k",["*-39ca","*-6d3d"]),
("rv","30-min realized vol x k",[0.7,1,1.5],"k",["*-7956","*-a608"]),
("rvd","20-day realized vol x k",[0.01,0.02,0.03],"k",["*-2b5e","*-cb9b"]),
("with","Trade WITH the gap, fixed pts",[3,5,7],"k",["*-00c8","*-feb0"]),
("against","Trade AGAINST the gap, fixed pts",[3,5,7],"k",["*-e316","*-4a30"]),
("ref","Both sides, fixed pts",[3,5,7],"offset_pts",["20261031-001728-draft_nq_930_straddle-8e01"])]
MED={"pct":"*-0141","preopen":"*-c641","rv":"*-0987","rvd":"*-97ab","with":"*-15be","against":"*-eac3","ref":"*-475e"}
VOL=[("Offset x RVOL (busy = wider)","*-f64a",[3,5,7],"k","pts","ctl.stop_atr"),
("Offset / RVOL (busy = tighter)","*-b8b9",[3,5,7],"k","pts","ctl.stop_atr"),
("Offset = k x |print - volume-weighted price|","*-d160",[0.25,0.4,0.55],"k","x","ctl.stop_atr"),
("Offset = k x volume-weighted band","*-d00c",[0.25,0.4,0.55],"k","x","ctl.stop_atr"),
("Stop = volume-weighted ATR","*-e00f",[3,5,7],"k","pts","sl_mult"),
("Stop = ATR x RVOL (busy = wider)","*-9ecd",[3,5,7],"k","pts","sl_mult"),
("Stop = ATR / RVOL (busy = tighter)","*-139a",[3,5,7],"k","pts","sl_mult"),
("Volume dry-up exit (5 pts)","*-4bfe",[0.2,0.35,0.5],"dryup","x","ctl.stop_atr"),
("Exit at the RTH VWAP (5 min)","*-bc48",[3,5,7],"offset_pts","pts","ctl.stop_atr"),
("Exit at the session VWAP (5 min)","*-22ea",[3,5,7],"offset_pts","pts","ctl.stop_atr")]
G={}   # (family, name, k) -> boxes
def add(fam,name,kk_vals,boxes):
    for kv in kk_vals:
        b={(s,r):v for (k,s,r),v in boxes.items() if k==float(kv)}
        if len(b)==25: G[(fam,name,kv)]=b
for key,name,ks,kk,pats in MEAN:
    bx={}
    for p in pats: bx.update(load(p,kk,ks))
    add("Mean ATR",name,ks,bx)
    add("Median ATR",name,ks,load(MED[key],kk,ks))
for name,pat,ks,kk,u,sk in VOL: add("Volume",name,ks,load(pat,kk,ks,sk))
avg=lambda xs:sum(xs)/len(xs); K=lambda x:f"{x/1000:+.1f}k"
def col(n):
    a=max(min(abs(n)/50000,1)*0.8,0.06); return f"rgba({'30,160,70' if n>=0 else '210,50,50'},{a:.2f})"
css=open("gen9.py").read().split('css="""')[1].split('"""')[0]
def cell(b): return f'<td style="background:{col(b["net"])}"><b>{K(b["net"])}</b><br>Sharpe {b["sh"]:.2f}<br><b>Full target {b["tp"]:.1f}%</b><br>Win {b["win"]:.1f}%<br>Real RR {b["rr"]:.2f}<br>DD {K(b["dd"])}<br>{b["tr"]} trades</td>'
def stats(b): v=list(b.values()); return dict(net=avg([x["net"] for x in v]),green=sum(x["net"]>0 for x in v),yl=sum(x["yl"] for x in v),tp=avg([x["tp"] for x in v]),sh=avg([x["sh"] for x in v]),dd=avg([x["dd"] for x in v]),tr=avg([x["tr"] for x in v]))
def srow(label,s): return f'<tr><td style="text-align:left">{label}<td>{K(s["net"])}<td>{s["green"]}/25<td>{s["yl"]}/25<td>{s["tp"]:.1f}%<td>{s["sh"]:.2f}<td>{K(s["dd"])}<td>{s["tr"]:.0f}'
HDR='<tr><th>Group<th>Avg net<th>Boxes green<th>Years line<th>Full target<th>Sharpe<th>Avg drawdown<th>Trades / box'
HEAD='<meta name="viewport" content="width=device-width,initial-scale=1">'
def page(fn,title,body): open(os.path.join(OUT,fn),"w").write(f'<!doctype html><html lang="en"><head><meta charset="utf-8">{HEAD}<title>{title}</title>{css}</head><body>{body}</body></html>')
# --- median vs mean
rows=[]
for key,name,ks,kk,pats in MEAN:
    for kv in ks:
        a,m=G.get(("Mean ATR",name,kv)),G.get(("Median ATR",name,kv))
        if a and m:
            sa,sm=stats(a),stats(m); rows.append(f'<tr><td style="text-align:left">{name}<td>{kv:g}<td>{K(sa["net"])}<td>{K(sm["net"])}<td>{K(sm["net"]-sa["net"])}<td>{sa["green"]}/25<td>{sm["green"]}/25<td>{sa["yl"]}/25<td>{sm["yl"]}/25')
dm=[stats(G[("Median ATR",n,k)])["net"]-stats(G[("Mean ATR",n,k)])["net"] for (f,n,k) in G if f=="Median ATR" and ("Mean ATR",n,k) in G]
body=f'<h1>NQ 9:30 straddle: ATR stop from the median vs the mean true range</h1><p>3:1 in-sample months only, 1 NQ, $4 round turn, 8 ticks slippage, cancel rule. Same 25 boxes per row (stops 3-5 x ATR, targets 0.5-2R). Median averages {K(avg(dm))} per group vs the mean ({sum(d>0 for d in dm)} of {len(dm)} groups better).</p><div class=w><table><tr><th>Rule<th>k<th>Mean net<th>Median net<th>Median - mean<th>Mean green<th>Median green<th>Mean years line<th>Median years line'+"".join(rows)+'</table></div>'
page("nq_930_median_vs_mean_atr.html","NQ 9:30 Median vs Mean ATR",body)
# --- top 5
rank=sorted(G.items(),key=lambda kv:-stats(kv[1])["net"])
tabs=[srow(f"{f}: {n} ({kv:g})",stats(b)) for (f,n,kv),b in rank]
b2=[f'<h1>NQ 9:30 straddle: top 5 heat maps by average net</h1><p>3:1 in-sample months only, 1 NQ, $4 round turn, 8 ticks slippage, cancel rule. {len(G)} groups (one run at one setting, 25 boxes each) ranked by the AVERAGE net of their 25 boxes, not by the best box. Overlapping boxes are not independent. No box picked, no test months run.</p>']
for (f,n,kv),b in rank[:5]:
    s=stats(b)
    b2.append(f'<h2>{f}: {n}, setting {kv:g}: avg {K(s["net"])}, {s["green"]}/25 green, years line {s["yl"]}/25, full target {s["tp"]:.1f}%</h2><div class=w><table><tr><th>Stop \\ RR'+"".join(f"<th>{t:g}R" for t in TGTS))
    for sv in STOPS: b2.append(f'<tr><th>{sv:g}'+"".join(cell(b[(float(sv),float(t))]) for t in TGTS))
    b2.append('</table></div>')
b2.append('<h2>All groups ranked</h2><div class=w><table>'+HDR+"".join(tabs)+'</table></div>')
page("nq_930_top5_heatmaps.html","NQ 9:30 Top 5 Heat Maps","".join(b2))
for (f,n,kv),b in rank[:12]: s=stats(b); print(f"{f:10s} {n:48s} {kv:<6g} {K(s['net']):>9} green {s['green']:2d} yl {s['yl']:2d} tp {s['tp']:.1f}")
print("groups",len(G),"median-mean avg",K(avg(dm)))
