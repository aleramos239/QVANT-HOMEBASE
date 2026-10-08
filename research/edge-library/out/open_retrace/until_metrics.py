import pickle, json, csv, datetime as dt, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
d=pickle.load(open(P+"until.pkl","rb")); cal=json.load(open(P+"cal.json"))["cal"]
weeks=len({dt.date.fromisoformat(c).isocalendar()[:2] for c in cal})
print("K     until  stop/tgt   trades  /wk    net     avg   win   PF   maxDD  Sharpe  | 1-contract avg")
res={}
for k,tr in zip(d["keys"],d["trades"]):
    x=L.pack(tr); z=L.sized(x,"NQ",risk_usd=500.0); m=L.metrics(z,cal,z["cost"]); m1=L.metrics(x,cal)
    res[k]=(m,tr)
    print(f"{k[0]:.2f}  {k[1]:>5}  {int(k[2]*100):>3}/{int(k[3]*100):<3}   {m['trades']:>5} {m['trades']/weeks:5.2f} {m['net']:>7.0f} {m['avg_trade']:>6.1f} {100*m['win']:>4.0f}% {m['pf']:>5.2f} {m['max_dd']:>6.0f} {m['sharpe']:>6.2f}  | {m1['avg_trade']:>7.1f}")
# when do the late trades enter, and result by entry hour for the 15:55 / 0.3 / 50-50 case
tr=res[(0.3,"15:55",0.5,0.5)][1]
byh={}
for t in tr:
    h=dt.datetime.fromtimestamp(t["entry_ms"]/1000,S.ET).hour
    byh.setdefault(h,[]).append(t["net"])
print("entry hour (1 contract): hour trades net avg")
for h in sorted(byh): print(h,len(byh[h]),round(sum(byh[h])),round(sum(byh[h])/len(byh[h])))
