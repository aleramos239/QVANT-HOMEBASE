import pickle, json, csv, datetime as dt, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
RISK=500.0
d=pickle.load(open(P+"judas.pkl","rb")); e=pickle.load(open(P+"judas122.pkl","rb")); cal=json.load(open(P+"cal.json"))["cal"]
tr=dict(zip(d["keys"],d["trades"])); tr.update(dict(zip(e["keys"],e["trades"])))
def fix(k): return (k[0],round(k[1],2),round(k[2],2))
grid={}
for k,t in tr.items():
    x=L.pack(t); z=L.sized(x,"NQ",risk_usd=RISK); m=L.metrics(z,cal,z["cost"])
    grid["|".join(map(str,k))]=[m["trades"],round(m["net"]),m["avg_trade"],round(m["win"],3),round(m["pf"],2) if m["pf"] else None,round(m["max_dd"]),round(m["sharpe"],2) if m["sharpe"] else None,round(m["worst_open_loss"])]
json.dump(grid,open(P+"grid500.json","w"),separators=(",",":"))
SEL=[(0.3,0.5,0.5),(0.3,0.5,3.0),(0.3,0.75,0.5),(0.3,1.0,1.22),(0.3,1.0,3.0),(0.3,1.5,0.5),(0.3,1.5,3.0),
     (0.25,0.5,0.5),(0.25,0.5,3.0),(0.25,0.75,0.5),(0.25,1.0,0.5),(0.25,1.5,0.5)]
curves=[]
for k in SEL:
    t=tr[k]; x=L.pack(t); z=L.sized(x,"NQ",risk_usd=RISK); m=L.metrics(z,cal,z["cost"])
    name=f"K{int(k[0]*100)}_s{int(k[1]*100)}_t{int(round(k[2]*100))}"
    rows=[]; daily={}
    order=np.argsort([ (r["date"],r["entry_ms"]) for r in t],axis=0)[:,0] if False else range(len(t))
    for i,r in enumerate(t):
        mic=int(z["micros"][i]); pnl=float(z["net"][i]); risk=mic*abs(r["entry_price"]-r["sl"])*2.0
        et=dt.datetime.fromtimestamp(r["entry_ms"]/1000,S.ET).strftime("%Y-%m-%d %H:%M:%S")
        rows.append([et,r["side"],mic,round(pnl,2),round(risk,2)])
        daily[r["date"]]=daily.get(r["date"],0.0)+pnl
    with open(P+f"ledgers/{name}.csv","w",newline="") as fh:
        w=csv.writer(fh); w.writerow(["entry_time","side","qty","pnl","risk"]); w.writerows(rows)
    cum=0.0; eq=[]
    for day in cal:
        cum+=daily.get(day,0.0)
        eq.append(round(cum,1))
    yr=L.per_year(z,cal,z["cost"])
    curves.append({"name":name,"K":k[0],"s":k[1],"t":k[2],"trades":m["trades"],"net":round(m["net"]),"avg":m["avg_trade"],"win":round(m["win"],3),"pf":round(m["pf"],2),
                   "dd":round(m["max_dd"]),"sharpe":round(m["sharpe"],2),"wol":round(m["worst_open_loss"]),"mic_med":int(np.median(z["micros"][z["micros"]>0])),
                   "eq":eq,"years":[[r["period"],r["trades"],round(r["net"]),r["avg_trade"]] for r in yr]})
json.dump({"cal":cal,"curves":curves},open(P+"curves500.json","w"),separators=(",",":"))
print("cells",len(grid))
print("curve                 trades  net      avg   win   PF   maxDD  Sharpe  worstOpen  medMicros")
for c in curves: print(f"{c['name']:<18} {c['trades']:>6} {c['net']:>8} {c['avg']:>7} {c['win']:.3f} {c['pf']:.2f} {c['dd']:>6} {c['sharpe']:>6} {c['wol']:>8} {c['mic_med']:>6}")
