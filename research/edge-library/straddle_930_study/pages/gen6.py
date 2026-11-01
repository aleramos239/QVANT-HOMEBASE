import re,sys,json
SP,TR=sys.argv[1],sys.argv[2]
OFFS=[3,5,7,10,15]; STOPS=[0.5,1,1.5,2,2.5,3,3.5,4,4.5,5]; TGTS=[0.5,0.75,1,1.5,1.75,2,2.5,3,3.5,4]
C={}  # (off,stop,tgt)->(box,win,be,net,pf,sh,dd)
for l in open(TR):
    m=re.match(r"\| #(\d+) \| offset_pts=([\d.]+), ctl.stop_atr=([\d.]+), ctl.target_rr=([\d.]+) \| ([\d.]+) \| ([\d.]+) \| 942 \| [\d.]+ \| -?\$[\d,]+ \| (-?)\$([\d,]+) \| ([\d.]+) \| (-?[\d.]+) \| -\$([\d,]+) \|",l)
    if m:
        g=m.groups(); net=float(g[7].replace(",",""))*(-1 if g[6] else 1)
        C[(float(g[1]),float(g[2]),float(g[3]))]=("A"+g[0],float(g[4]),float(g[5]),net,float(g[8]),float(g[9]),-float(g[10].replace(",","")))
assert len(C)==400
n=0
for i,l in enumerate(open(SP+"/r15.txt")):
    w,be,net,pf,sh,dd=map(float,l.split())
    C[(15.0,STOPS[i//10],TGTS[i%10])]=("B%d"%(i+1),w,be,net,pf,sh,dd)
assert len(C)==500
for k,v in C.items():  # sign check: PF side matches net side
    assert (v[4]>=1)==(v[3]>=0) or abs(v[3])<6000,(k,v)
avg=lambda xs:sum(xs)/len(xs)
def at(f): return [v[3] for k,v in C.items() if f(k)]
a400=avg(at(lambda k:k[0]!=15)); a100=avg(at(lambda k:k[0]==15))
assert round(a400)==41651 and round(a100)==8554,(a400,a100)
allavg=avg(at(lambda k:True)); green=sum(1 for v in C.values() if v[3]>0)
k=lambda x:f"{x/1000:+.1f}k"
def col(net):
    a=max(min(abs(net)/50000,1)*0.8,0.06); return f"rgba({'30,160,70' if net>=0 else '210,50,50'},{a:.2f})"
def cell(o,s,t):
    b,w,be,net,pf,sh,dd=C[(o,s,t)]; rr=(100-be)/be
    return (f'<td style="background:{col(net)}"><b>Net {k(net)}</b><br>Win {w:.1f}%<br>Real RR {rr:.2f}<br>PF {pf:.2f}<br>Sharpe {sh:.2f}<br><i>{b}</i></td>')
H=['<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>NQ 9:30 straddle, 2 pt slippage</title>',
'<style>:root{--bg:#fff;--fg:#111;--mut:#666;--bd:#ccc}@media(prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#eee;--mut:#9aa;--bd:#444}}body{background:var(--bg);color:var(--fg);font:14px system-ui;margin:16px}h1{font-size:20px}h2{font-size:16px;margin:28px 0 6px}table{border-collapse:collapse;font-size:12px;line-height:1.35}td,th{border:1px solid var(--bd);padding:3px 5px;text-align:center;min-width:92px}th{font-weight:600}.w{overflow-x:auto}p,li{max-width:900px;color:var(--mut)}b{color:var(--fg)}</style>',
f'<h1>NQ 9:30 straddle, entry distance in points, ATR stop, RR target: slippage 2 points (8 ticks)</h1>',
f'<p>In-sample months only (3:1 blocks, 2021-10 to 2026-08), 942 trades a box, 1 NQ, $4 round turn, <b>2 points of slippage</b> (the earlier maps used 1 tick = 0.25 pt). Each box shows: net, win rate, realized RR, profit factor, Sharpe, box number (A = run 8e01 offsets 3-10, B = run 25c7 offset 15). Green profit, red loss; stronger colour = bigger. Rows: ATR stop. Columns: RR target.</p>',
f'<p><b>All 500 boxes: average {k(allavg)}, {green} green.</b> At 1 tick the same grid averaged +$90.1k, 374 green. Offsets 3-10 (400 boxes): {k(a400)} (was +$97.2k). Offset 15 (100 boxes): {k(a100)} (was +$61.9k).</p>']
H.append('<h2>Average net by offset / stop / target</h2><div class=w><table><tr><th>offset'+''.join(f'<th>{o:g} pt' for o in OFFS)+'<tr><th>avg'+''.join(f'<td>{k(avg(at(lambda x,o=o:x[0]==o)))}' for o in OFFS)+'</table></div><br><div class=w><table><tr><th>ATR stop'+''.join(f'<th>{s:g}' for s in STOPS)+'<tr><th>avg'+''.join(f'<td>{k(avg(at(lambda x,s=s:x[1]==s)))}' for s in STOPS)+'</table></div><br><div class=w><table><tr><th>RR target'+''.join(f'<th>{t:g}R' for t in TGTS)+'<tr><th>avg'+''.join(f'<td>{k(avg(at(lambda x,t=t:x[2]==t)))}' for t in TGTS)+'</table></div>')
for o in OFFS:
    H.append(f'<h2>Offset {o} pts from the 9:30 price (avg {k(avg(at(lambda x:x[0]==o)))})</h2><div class=w><table><tr><th>ATR stop \\ RR'+''.join(f'<th>{t:g}R' for t in TGTS))
    for s in STOPS: H.append(f'<tr><th>{s:g} ATR'+''.join(cell(float(o),s,t) for t in TGTS))
    H.append('</table></div>')
open(sys.argv[3],"w").write("\n".join(H))
print("avg all",round(allavg),"green",green,"A400",round(a400),"B100",round(a100))
print("by offset",[round(avg(at(lambda x,o=o:x[0]==o))) for o in OFFS])
print("by stop",[round(avg(at(lambda x,s=s:x[1]==s))) for s in STOPS])
print("by tgt",[round(avg(at(lambda x,t=t:x[2]==t))) for t in TGTS])
best=max(C.items(),key=lambda kv:kv[1][3]); print("best",best)
print("wf 5/4/4",C[(5.0,4.0,4.0)]); print("green by stop",[sum(1 for k2,v in C.items() if k2[1]==s and v[3]>0) for s in STOPS])
