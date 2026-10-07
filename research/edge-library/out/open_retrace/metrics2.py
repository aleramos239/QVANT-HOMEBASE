import pickle, json, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
d=pickle.load(open(P+"heat.pkl","rb")); cal=json.load(open(P+"cal.json"))["cal"]
tr=dict(zip(d["keys"],d["trades"]))
def show(key,title):
    x=L.pack(tr[key]); print("\n".join(L.report_md(x,"NQ",cal,title)))
    for side,name in ((1,"LONG"),(-1,"SHORT")):
        m=x["side"]==side; y={k:np.asarray(v)[m] for k,v in x.items() if k in L.FIELDS}
        r=L.metrics(y,cal); print(f"{name}: trades {r['trades']} net {r['net']:.0f} avg {r['avg_trade']} win {r['win']:.3f} pf {r['pf']:.2f}")
    why={}
    for t in tr[key]: why[t['exit_reason']]=why.get(t['exit_reason'],0)+1
    print("exits:",why)
show((0.5,1.0),"open_retrace level 0.5, target 1R (the owner's rule), ")
