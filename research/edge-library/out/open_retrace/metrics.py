import pickle, json, datetime as dt, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
d=pickle.load(open(P+"heat.pkl","rb"))
a,b=S.BP_BUILD
cal=[x.isoformat() for x in S.sessions(a,b,"NQ",allow_holdout=S.ALLOW_BP)]
print("build sessions",len(cal),cal[0],cal[-1])
cells={}
for k,tr in zip(d["keys"],d["trades"]):
    x=L.pack(tr); cells[k]=(x,L.metrics(x,cal))
print("lvl  rr    trades   net      avg   win   pf   maxDD   sharpe")
for k,(x,m) in cells.items():
    print(k, m["trades"], round(m["net"]), m["avg_trade"], round(m["win"],3), round(m["pf"],2) if m["pf"] else None, round(m["max_dd"]), round(m["sharpe"],2) if m["sharpe"] else None)
nets=[m["net"] for _,m in cells.values()]
print("profitable cells:",sum(n>0 for n in nets),"/",len(nets), " mean avg trade:", round(np.mean([m['avg_trade'] for _,m in cells.values()]),2))
json.dump({"cal":cal},open(P+"cal.json","w"))
