import json,os
W=os.path.expanduser("~/ramos-quant-homebase/homebase/.state/tester/walkforward/")
import glob
g=lambda p:os.path.basename(glob.glob(W+p)[0])
ID0=dict(base="20261031-001728-draft_nq_930_straddle-8e01",)
ID=dict(c45=ID0["base"],l45=g("20261101-095028-*-a5e3"),h45=g("20261101-095028-*-dac5"),c68=g("20261031-232810-*-8eee"),l68=g("20261101-095029-*-31bd"),h68=g("20261101-095030-*-d901"),n45=g("20261101-112316-*-1482"),n68=g("20261101-112317-*-aca8"))
def load(d,only=None):
    g=json.load(open(W+d+"/grid.json")); out={}
    for c in g["cells"]:
        p=c["params"]; key=(float(p["offset_pts"]),float(p["ctl.stop_atr"]),float(p["ctl.target_rr"]))
        if only and not only(key): continue
        i=c["i"]; r=json.load(open(f"{W}{d}/cells/{i:02d}/run.json")); a=r["report"]["summary"]["all"]
        t=json.load(open(f"{W}{d}/cells/{i:02d}/trades.json")); t=t if isinstance(t,list) else t["trades"]
        n=len(t); assert n==a["trades"],(d,key,n)
        pc=lambda f:100*sum(1 for x in t if f(x))/n
        out[key]=dict(box=i+1,net=a["net_profit"],sh=a["sharpe"],dd=a["max_drawdown"],win=a["win_rate"],rr=a["rr"],tr=n,
          tp=pc(lambda x:x["exit_reason"]=="tp"),slw=pc(lambda x:x["exit_reason"]=="sl" and x["net"]>0),
          sll=pc(lambda x:x["exit_reason"]=="sl" and x["net"]<=0),ot=pc(lambda x:x["exit_reason"] in("time","eod")))
    return out
EXTRA={"c45":g("20261101-113333-*-d1fe"),"c68":g("20261101-113334-*-2b41")}
D={k:load(v,(lambda k:k[0]==5 and k[1]>=4 and k[2] in (.5,.75,1.5,2.0)) if k=="c45" else None) for k,v in ID.items()}
for k in list(D):
    if k in EXTRA: D[k].update(load(EXTRA[k]))
for k in list(D):
    if k not in ("c45","c68"): del D[k]
    else: assert len(D[k])==15,(k,len(D[k]))
STOPS={"45":[4,4.5,5],"68":[6,7,8]}; TGTS=[0.5,0.75,1,1.5,2]
avg=lambda xs:sum(xs)/len(xs); k_=lambda x:f"{x/1000:+.1f}k"
A=lambda v,f:avg([D[v][x][f] for x in D[v]])
def col(net):
    a=max(min(abs(net)/50000,1)*0.8,0.06); return f"rgba({'30,160,70' if net>=0 else '210,50,50'},{a:.2f})"
def cell(v,s,t):
    b=D[v][(5.0,s,t)]
    return (f'<td style="background:{col(b["net"])}"><b>{k_(b["net"])}</b><br>Sharpe {b["sh"]:.2f}<br>TP {b["tp"]:.0f}%<br>SL loss {b["sll"]:.0f}%<br>Stopped in profit {b["slw"]:.0f}%<br>Clock {b["ot"]:.0f}%<br>Win {b["win"]:.1f}%<br>Real RR {b["rr"]:.2f}<br>DD {k_(b["dd"])}<br><i>{b["box"]}</i></td>')
css=open("gen9.py").read().split('css="""')[1].split('"""')[0]
V=[("c45","45","A. Stops 4-5x: cancel the other side when the first order fills"),("c68","68","D. Stops 6-8x: cancel the other side when the first order fills")]
H=['<title>NQ 9:30 Cancel Rule Maps</title>',css,
'<h1>NQ 9:30 straddle, offset 5 pts: maps A and D with 1R (cancel the other side at the first fill) (2 pts slippage)</h1>',
'<p>Rows: ATR stop. Columns: target 0.5 / 0.75 / 1 / 1.5 / 2R. 15 boxes a map. Each box: net, Sharpe, exit mix (TP, stopped at a loss, stopped in profit, closed by the clock), win rate, realized RR, drawdown, box number. 3:1 in-sample months only, 1 NQ, $4 round turn. 942 trades a box.</p>']
H.append('<table><tr><th>Map<th>Avg net<th>Sharpe<th>Drawdown<th>Trades / box<th>Boxes green'+''.join(f'<tr><td style="text-align:left">{n}<td>{k_(A(v,"net"))}<td>{A(v,"sh"):.2f}<td>{k_(A(v,"dd"))}<td>{A(v,"tr"):.0f}<td>{sum(1 for x in D[v].values() if x["net"]>0)}/15' for v,_,n in V)+'</table>')
for v,sk,n in V:
    H.append(f'<h2>{n}: avg net {k_(A(v,"net"))}, Sharpe {A(v,"sh"):.2f}, drawdown {k_(A(v,"dd"))}</h2><div class=w><table><tr><th>ATR stop \\ RR'+''.join(f'<th>{t:g}R' for t in TGTS))
    for s in STOPS[sk]: H.append(f'<tr><th>{s:g} ATR'+''.join(cell(v,s,t) for t in TGTS))
    H.append('</table></div>')
h="\n".join(H); open("nq_930_cancel_rule_maps.html","w").write(h)
st='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+h+"</body></html>"
open("nq_930_cancel_rule_maps_standalone.html","w").write(st)
open("print17b.html","w").write(st.replace('<title>','<style>@page{size:1000px 1700px;margin:14px}h2{break-inside:avoid}</style><title>',1))
