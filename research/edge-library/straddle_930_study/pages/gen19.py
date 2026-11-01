import json,os,glob,collections
W=os.path.expanduser("~/ramos-quant-homebase/homebase/.state/tester/walkforward/")
g=lambda p:os.path.basename(glob.glob(W+p)[0])
STOPS=[3,3.5,4,4.5,5]; TGTS=[0.5,0.75,1,1.5,2]
GR=[("pct","Percent of price","*-411c",[0.02,0.03,0.04],"k","%",["about 3.6 pts","about 5.4 pts","about 7.2 pts"],None),
("preopen","Pre-open range (09:00-09:30 high-low) x k","*-39ca",[0.1,0.15,0.2],"k","x",["about 3.8 pts","about 5.7 pts","about 7.6 pts"],None),
("rv","30-minute realized vol (std of 1-min moves) x k","*-7956",[0.7,1,1.5],"k","x",["about 3.2 pts","about 4.5 pts","about 6.8 pts"],None),
("rvd","20-day realized vol (std of daily moves) x k","*-2b5e",[0.01,0.02,0.03],"k","x",["about 2.5 pts","about 5 pts","about 7.6 pts"],None),
("with","Gap side only: trade WITH the gap, fixed pts","*-00c8",[3,5,7],"k","pts",["3 pts","5 pts","7 pts"],None),
("against","Gap side only: trade AGAINST the gap, fixed pts","*-e316",[3,5,7],"k","pts",["3 pts","5 pts","7 pts"],None),
("ref","Reference: both sides, fixed pts (run 8e01)","20261031-001728-draft_nq_930_straddle-8e01",[3,5,7],"offset_pts","pts",["3 pts","5 pts","7 pts"],None)]
EXTRA={'pct':'*-eb47','preopen':'*-6d3d','rv':'*-a608','rvd':'*-cb9b','with':'*-feb0','against':'*-4a30','ref':None}
def load(pat,kk,ks,tag=''):
    d=g(pat) if "*" in pat else pat; gr=json.load(open(W+d+"/grid.json")); out={}
    for c in gr["cells"]:
        p=c["params"]; key=(float(p[kk]),float(p["ctl.stop_atr"]),float(p["ctl.target_rr"]))
        if key[1] not in STOPS or key[2] not in TGTS or key[0] not in [float(x) for x in ks]: continue
        i=c["i"]; r=json.load(open(f"{W}{d}/cells/{i:02d}/run.json")); a=r["report"]["summary"]["all"]
        t=json.load(open(f"{W}{d}/cells/{i:02d}/trades.json")); t=t if isinstance(t,list) else t["trades"]
        y=collections.Counter()
        for x in t: y[x["date"][:4]]+=x["net"]
        n=a["net_profit"]; yl=sum(v>0 for v in y.values())>=4 and n>0 and max(y.values())/n<=.5
        tp=100*sum(1 for x in t if x['exit_reason']=='tp')/len(t)
        out[key]=dict(tp=tp,box=tag+str(i+1),net=n,sh=a["sharpe"],dd=a["max_drawdown"],win=a["win_rate"],rr=a["rr"],tr=len(t),yl=yl,y=y)
    return out
D={}
for gid,_,pat,ks,kk,*_ in GR:
    D[gid]=load(pat,kk,ks)
    if EXTRA[gid]: D[gid].update(load(EXTRA[gid],kk,ks,'b'))
    assert len(D[gid])==75,(gid,len(D[gid]))
avg=lambda xs:sum(xs)/len(xs); K=lambda x:f"{x/1000:+.1f}k"
def col(net):
    a=max(min(abs(net)/50000,1)*0.8,0.06); return f"rgba({'30,160,70' if net>=0 else '210,50,50'},{a:.2f})"
css=open("gen9.py").read().split('css="""')[1].split('"""')[0]
def cell(b):
    return f'<td style="background:{col(b["net"])}"><b>{K(b["net"])}</b><br>Sharpe {b["sh"]:.2f}<br><b>Full target {b["tp"]:.1f}%</b><br>Win {b["win"]:.1f}%<br>Real RR {b["rr"]:.2f}<br>DD {K(b["dd"])}<br>{b["tr"]} trades<br><i>{b["box"]}</i></td>'
H=['<title>NQ 9:30 Distance Rule Maps v2</title>',css,'<h1>NQ 9:30 straddle: how far from the 9:30 print (2 pts slippage)</h1>',
'<p>3:1 in-sample months only, 1 NQ, $4 round turn, 8 ticks slippage, cancel rule (the other side is cancelled at the first fill). Full target = share of trades closed by the take-profit order (the rest: stopped out or closed by the clock). Each map: rows = ATR stop 3 / 3.5 / 4 / 4.5 / 5 (box numbers starting with b come from the second run with the 3 and 3.5 stops), columns = target 0.5 / 0.75 / 1 / 1.5 / 2R. Years line = 4 of 6 years green and no year over half the net. Averages are over the box group, never the best box. No box picked, no test months run.</p>']
rows=[]
for gid,name,pat,ks,kk,unit,pts,_ in GR:
    for kv,pt in zip(ks,pts):
        bs=[v for k,v in D[gid].items() if k[0]==float(kv)]
        rows.append(f'<tr><td style="text-align:left">{name}<td>{kv:g} {unit}<td>{pt}<td>{K(avg([b["net"] for b in bs]))}<td>{avg([b["tp"] for b in bs]):.1f}%<td>{avg([b["sh"] for b in bs]):.2f}<td>{K(avg([b["dd"] for b in bs]))}<td>{avg([b["tr"] for b in bs]):.0f}<td>{sum(b["net"]>0 for b in bs)}/25<td>{sum(b["yl"] for b in bs)}/25')
H.append('<h2>Summary: one row per distance (25 boxes each)</h2><div class=w><table><tr><th>Rule<th>k<th>Offset<th>Avg net<th>Hit full target<th>Sharpe<th>Drawdown<th>Trades / box<th>Boxes green<th>Years line'+''.join(rows)+'</table></div>')
for gid,name,pat,ks,kk,unit,pts,_ in GR:
    allb=list(D[gid].values())
    H.append(f'<h2>{name}: avg net {K(avg([b["net"] for b in allb]))} over 75 boxes, {sum(b["net"]>0 for b in allb)} green</h2>')
    for kv,pt in zip(ks,pts):
        bs=[v for k,v in D[gid].items() if k[0]==float(kv)]
        H.append(f'<h3>{kv:g} {unit} ({pt}): avg {K(avg([b["net"] for b in bs]))}</h3><div class=w><table><tr><th>ATR stop \\ RR'+''.join(f'<th>{t:g}R' for t in TGTS))
        for s in STOPS: H.append(f'<tr><th>{s:g} ATR'+''.join(cell(D[gid][(float(kv),float(s),t)]) for t in TGTS))
        H.append('</table></div>')
h="\n".join(H); open("nq_930_distance_maps_v2.html","w").write('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+h+"</body></html>")
for r in rows: print(r.replace("<td>"," | ").replace("<td style=\"text-align:left\">","")[:200])
