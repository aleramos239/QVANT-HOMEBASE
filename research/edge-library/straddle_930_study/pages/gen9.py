import sys,json,os,collections
SP=os.getcwd()
TR="/Users/ramoscapital/.claude/projects/-Users-ramoscapital-ramos-quant-homebase/780ea358-649f-4a7a-948b-e6ea92c100ae/tool-results/mcp-homebase-walkforward-1793422067471.txt"
src=open(SP+"/gen7.py").read().split("avg=lambda")[0]
sys.argv=["x",SP,TR,"/dev/null"]
exec(src)          # C (no breakeven map) and TP
W=os.path.expanduser("~/ramos-quant-homebase/homebase/.state/tester/walkforward/")
RUNS={"A":"20261031-160724-draft_nq_930_straddle-c907","B":"20261031-160726-draft_nq_930_straddle-63b8"}
BE={}
MIX={}
for p,d in RUNS.items():
    g=json.load(open(W+d+"/grid.json"))
    assert g["status"]=="done" and all(c["status"]=="done" for c in g["cells"])
    for c in g["cells"]:
        i=c["i"]; pr=c["params"]
        key=(float(pr["offset_pts"]),float(pr["ctl.stop_atr"]),float(pr["ctl.target_rr"]))
        r=json.load(open(f"{W}{d}/cells/{i:02d}/run.json"))
        assert r["controls"]["rules"]["trail_pts"]==5.0
        a=r["report"]["summary"]["all"]
        t=json.load(open(f"{W}{d}/cells/{i:02d}/trades.json")); t=t if isinstance(t,list) else t["trades"]
        assert a["trades"]==len(t)==942 and abs(sum(x["net"] for x in t)-a["net_profit"])<1
        n=len(t); sg=lambda x:1 if x["side"]=="long" else -1
        tp=100*sum(1 for x in t if x["exit_reason"]=="tp")/n
        beP=100*sum(1 for x in t if x["exit_reason"]=="sl" and (x["exit_price"]-x["entry_price"])*sg(x)>0)/n
        slP=100*sum(1 for x in t if x["exit_reason"]=="sl" and (x["exit_price"]-x["entry_price"])*sg(x)<=0)/n
        fl=100*sum(1 for x in t if x["exit_reason"] in ("time","eod"))/n
        assert abs(tp+beP+slP+fl-100)<1e-6
        MIX[key]=(tp,beP,slP,fl)
        BE[key]=(f"{p}{i+1}",a["win_rate"],a["net_profit"],a["profit_factor"],a["sharpe"],a["max_drawdown"],tp,a["rr"])
assert len(BE)==500 and set(BE)==set(C)
avg=lambda xs:sum(xs)/len(xs)
k=lambda x:f"{x/1000:+.1f}k"
def ag(f,i): return avg([f(BE[x]) if i else f(C[x]) for x in C])
# base idx: C=(box,win,be,net,pf,sh,dd) ; BE=(box,win,net,pf,sh,dd,tp)
rows=[("Average net",lambda: avg([C[x][3] for x in C]),avg([BE[x][2] for x in C]),k),
      ("Average Sharpe",None,None,None)]
bN=avg([C[x][3] for x in C]); eN=avg([BE[x][2] for x in C])
bS=avg([C[x][5] for x in C]); eS=avg([BE[x][4] for x in C])
bD=avg([C[x][6] for x in C]); eD=avg([BE[x][5] for x in C])
bW=avg([C[x][1] for x in C]); eW=avg([BE[x][1] for x in C])
bT=avg([TP[C[x][0]][0] for x in C]); eT=avg([BE[x][6] for x in C])
bG=sum(1 for x in C if C[x][3]>0); eG=sum(1 for x in C if BE[x][2]>0)
better=sum(1 for x in C if BE[x][2]>C[x][3]); ddb=sum(1 for x in C if BE[x][5]>C[x][6]); shb=sum(1 for x in C if BE[x][4]>C[x][5])
print(dict(bN=bN,eN=eN,bS=bS,eS=eS,bD=bD,eD=eD,bW=bW,eW=eW,bT=bT,eT=eT,bG=bG,eG=eG,better=better,ddb=ddb,shb=shb))
def at(f,i): return avg([ (BE[x][2] if i else C[x][3]) for x in C if f(x)])
def cell(o,s,t):
    b=BE[(o,s,t)]; c=C[(o,s,t)]; m=MIX[(o,s,t)]; net=b[2]
    a=max(min(abs(net)/50000,1)*0.8,0.06); bg=f"rgba({'30,160,70' if net>=0 else '210,50,50'},{a:.2f})"
    return (f'<td style="background:{bg}"><b>{k(net)}</b> <span class=w0>({k(c[3])})</span><br>Sharpe {b[4]:.2f} <span class=w0>({c[5]:.2f})</span><br>TP {m[0]:.0f}% <span class=w0>({TP[c[0]][0]:.0f}%)</span><br>Trail {m[1]:.0f}%<br>SL {m[2]:.0f}% <span class=w0>({TP[c[0]][1]:.0f}%)</span><br>Flat {m[3]:.0f}% <span class=w0>({TP[c[0]][2]:.0f}%)</span><br>Win {b[1]:.1f}%<br>Real RR {b[7]:.2f} <span class=w0>({(100-c[2])/c[2]:.2f})</span><br>DD {k(b[5])} <span class=w0>({k(c[6])})</span><br><i>{b[0]}</i></td>')
STOPS=[0.5,1,1.5,2,2.5,3,3.5,4,4.5,5]; TGTS=[0.5,0.75,1,1.5,1.75,2,2.5,3,3.5,4]; OFFS=[3,5,7,10,15]
css="""<style>
:root{--bg:#fbfaf7;--fg:#16181b;--mut:#5d636b;--bd:#d6d3cb;--card:#fff;--acc:#1f6f4a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#14161a;--fg:#ecebe6;--mut:#9aa0a8;--bd:#3a3e45;--card:#1b1e23;--acc:#5fc590;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#14161a;--fg:#ecebe6;--mut:#9aa0a8;--bd:#3a3e45;--card:#1b1e23;--acc:#5fc590;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,sans-serif;padding-block:16px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:20px;margin:0 0 8px;text-wrap:balance}h2{font-size:16px;margin:28px 0 6px}
p{max-width:70ch;color:var(--mut);margin:6px 0}b{color:var(--fg)}
.w{overflow-x:auto;max-width:100%}table{border-collapse:collapse;font-size:12px;line-height:1.35}
td,th{border:1px solid var(--bd);padding:3px 6px;text-align:center;min-width:104px;color:var(--fg)}th{font-weight:600;background:var(--card)}
.w0{color:var(--mut);font-size:11px}i{color:var(--mut)}
</style>"""
H=['<title>NQ 9:30 Trail Map</title>','<meta name="claude:viewport-fit-sides" content="cover">',css,
'<h1>NQ 9:30 straddle with a 5-point trailing stop (2 pts slippage)</h1>',
'<p>Same 500 boxes as the no-breakeven map (3:1 in-sample months only, 942 trades a box, 1 NQ, $4 round turn, 2 pts slippage), but the stop is a 5-point trailing stop from the fill (it follows price 5 pts behind, and the target stays). <b>The 5 pt trail replaces the ATR stop, so every box has the same 5 pt stop; the ATR stop row only changes how far away the target is.</b> Each box: <b>with the trail</b>, then (in grey) the same box <b>without</b>. Net, Sharpe, how the trades ended (TP full target, Trail stopped by the trail with the trade in profit, SL stopped with the trade at a loss, Flat closed at 15:55; grey = same box with no trail), win rate, realized RR (average win / average loss), max drawdown, box number (A = offsets 3-10, B = offset 15; same numbers as before). Rows: ATR stop. Columns: RR target.</p>']
tab=lambda hdr,rowsx:'<div class=w><table><tr>'+''.join(f'<th>{h}' for h in hdr)+''.join('<tr>'+''.join(f'<{"th" if j==0 else "td"}>{v}' for j,v in enumerate(r)) for r in rowsx)+'</table></div>'
H.append('<h2>All 500 boxes, average</h2>'+tab(["","No trail","5 pt trail"],[
 ["Net",k(bN),k(eN)],["Sharpe",f"{bS:.2f}",f"{eS:.2f}"],["Max drawdown",k(bD),k(eD)],["Win rate",f"{bW:.1f}%",f"{eW:.1f}%"],["Hit full target (TP)",f"{bT:.1f}%",f"{eT:.1f}%"],["Trail stop in profit (Trail)","0%",f"{avg([MIX[x][1] for x in C]):.1f}%"],["Stopped at a loss (SL)",f"{avg([TP[C[x][0]][1] for x in C]):.1f}%",f"{avg([MIX[x][2] for x in C]):.1f}%"],["Flat at 15:55 (Flat)",f"{avg([TP[C[x][0]][2] for x in C]):.1f}%",f"{avg([MIX[x][3] for x in C]):.1f}%"],["Realized RR",f"{avg([(100-C[x][2])/C[x][2] for x in C]):.2f}",f"{avg([BE[x][7] for x in C]):.2f}"],["Boxes green",str(bG),str(eG)]]))
H.append(f'<p>The 5 pt trail made more money in {better} of 500 boxes, a higher Sharpe in {shb}, and a smaller drawdown in {ddb}. Judge the average, not the best box. Nothing is picked and no test month was read.</p>')
H.append('<h2>Average net by offset / stop / target</h2>'+tab(["Offset"]+[f"{o:g} pt" for o in OFFS],[["No trail"]+[k(at(lambda x,o=o:x[0]==o,0)) for o in OFFS],["5 pt trail"]+[k(at(lambda x,o=o:x[0]==o,1)) for o in OFFS]])+'<br>'+tab(["ATR stop"]+[f"{s:g}" for s in STOPS],[["No trail"]+[k(at(lambda x,s=s:x[1]==s,0)) for s in STOPS],["5 pt trail"]+[k(at(lambda x,s=s:x[1]==s,1)) for s in STOPS]])+'<br>'+tab(["RR target"]+[f"{t:g}R" for t in TGTS],[["No trail"]+[k(at(lambda x,t=t:x[2]==t,0)) for t in TGTS],["5 pt trail"]+[k(at(lambda x,t=t:x[2]==t,1)) for t in TGTS]]))
for o in OFFS:
    H.append(f'<h2>Offset {o} pts (avg {k(at(lambda x:x[0]==o,1))}, was {k(at(lambda x:x[0]==o,0))})</h2><div class=w><table><tr><th>ATR stop \\ RR'+''.join(f'<th>{t:g}R' for t in TGTS))
    for s in STOPS: H.append(f'<tr><th>{s:g} ATR'+''.join(cell(float(o),s,t) for t in TGTS))
    H.append('</table></div>')
open(SP+"/nq_930_trail5_map.html","w").write("\n".join(H))
