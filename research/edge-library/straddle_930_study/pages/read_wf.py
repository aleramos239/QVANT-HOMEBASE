import json,sys,collections
W="/Users/ramoscapital/ramos-quant-homebase/homebase/.state/tester/walkforward/"
def load(id):
    g=json.load(open(W+id+"/grid.json")); out={}
    for c in g["cells"]:
        t=json.load(open(f"{W}{id}/cells/{c['i']:02d}/trades.json")); t=t if isinstance(t,list) else t["trades"]
        out[tuple(float(c['params'][k]) for k in ('ctl.stop_atr','ctl.target_rr'))]=t
    return out
def summ(id,label):
    B=load(id); nets=[];ok=0;yrs=collections.Counter();pos=0;ntr=[]
    for k,t in B.items():
        y=collections.Counter()
        for x in t: y[x['date'][:4]]+=x['net']
        n=sum(y.values()); nets.append(n); pos+=n>0; ntr.append(len(t))
        ok+= sum(v>0 for v in y.values())>=4 and n>0 and max(y.values())/n<=.5
        for a,b in y.items(): yrs[a]+=b/12
    ex=collections.Counter(x['exit_reason'] for t in B.values() for x in t)
    print(f"{label}: avg net {sum(nets)/12:,.0f}  boxes>0 {pos}/12  trades/box {sum(ntr)/12:.0f}  years-line {ok}/12  yrs(k) {[round(yrs[a]/1e3,1) for a in sorted(yrs)]}  exits/12 { {k:round(v/12) for k,v in ex.items()} }")
    return B
if __name__=="__main__":
    for a in sys.argv[1:]:
        i,l=a.split("=",1); summ(i,l)
