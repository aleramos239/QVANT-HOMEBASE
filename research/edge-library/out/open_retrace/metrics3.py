import pickle, json, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
d=pickle.load(open(P+"judas.pkl","rb")); cal=json.load(open(P+"cal.json"))["cal"]
cells={}
for k,tr in zip(d["keys"],d["trades"]):
    m=L.metrics(L.pack(tr),cal); cells[k]=m
json.dump({"|".join(map(str,k)):[m["trades"],round(m["net"]),m["avg_trade"],round(m["win"],3) if m["win"] is not None else None,round(m["pf"],2) if m["pf"] else None,round(m["max_dd"]),round(m["sharpe"],2) if m["sharpe"] else None] for k,m in cells.items()},open(P+"judas_cells.json","w"))
Ks=sorted({k[0] for k in cells}); Ss=sorted({k[1] for k in cells}); Ts=[0.25,0.5,0.75,1.0,1.5,2.0,3.0,0.0]
for K in Ks:
    sub=[m for k,m in cells.items() if k[0]==K]
    prof=sum(m["net"]>0 for m in sub)
    print(f"\nK={K}: trades {sub[0]['trades']}, profitable cells {prof}/{len(sub)} ({round(100*prof/len(sub))}%), mean avg trade ${np.mean([m['avg_trade'] for m in sub]):.1f}, median avg trade ${np.median([m['avg_trade'] for m in sub]):.1f}")
    print("avg $/trade  stop%\\target% | "+"  ".join(f"{('none' if t==0 else int(t*100)):>6}" for t in Ts))
    for s in Ss:
        print(f"   stop {int(s*100):>3}%        | "+"  ".join(f"{cells[(K,s,t)]['avg_trade']:>6.0f}" for t in Ts))
allp=sum(m["net"]>0 for m in cells.values()); print("\nALL:",allp,"/",len(cells), "mean avg trade", round(np.mean([m['avg_trade'] for m in cells.values()]),1))
# without the no-target column
nt=[m for k,m in cells.items() if k[2]!=0]; print("with a target:",sum(m['net']>0 for m in nt),"/",len(nt),"mean avg", round(np.mean([m['avg_trade'] for m in nt]),1))
