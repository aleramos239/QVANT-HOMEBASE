import pickle, json, csv, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
RISK=500.0
d=pickle.load(open(P+"judas.pkl","rb")); cal=json.load(open(P+"cal.json"))["cal"]
tr=dict(zip(d["keys"],d["trades"]))
B={0.25:[0.25,0.5,0.75,1.0,1.5,2.0,3.0],0.5:[2.0,3.0,0.25,0.5,0.75],0.75:[0.25,0.5,0.75,2.0,3.0],1.0:[0.25,0.5,0.75,2.0,3.0],1.5:[0.25,0.5,0.75,2.0,3.0],2.0:[0.25,0.5,0.75]}
SEL=[(0.3,s,t) for s,ts in B.items() for t in ts]
print(len(SEL),"cells")
curves=json.load(open(P+"curves500.json"))["curves"]
byname={c["name"]:c for c in curves}
out=[]
for k in SEL:
    name=f"K{int(k[0]*100)}_s{int(round(k[1]*100))}_t{int(round(k[2]*100))}"
    t=tr[k]; x=L.pack(t); z=L.sized(x,"NQ",risk_usd=RISK); m=L.metrics(z,cal,z["cost"])
    import datetime as dt
    rows=[]; daily={}
    for i,r in enumerate(t):
        mic=int(z["micros"][i]); pnl=float(z["net"][i]); risk=mic*abs(r["entry_price"]-r["sl"])*2.0
        et=dt.datetime.fromtimestamp(r["entry_ms"]/1000,S.ET).strftime("%Y-%m-%d %H:%M:%S")
        rows.append([et,r["side"],mic,round(pnl,2),round(risk,2)]); daily[r["date"]]=daily.get(r["date"],0.0)+pnl
    with open(P+f"ledgers/{name}.csv","w",newline="") as fh:
        w=csv.writer(fh); w.writerow(["entry_time","side","qty","pnl","risk"]); w.writerows(rows)
    cum=0.0; eq=[]
    for day in cal:
        cum+=daily.get(day,0.0); eq.append(round(cum,1))
    yr=L.per_year(z,cal,z["cost"])
    out.append({"name":name,"K":k[0],"s":k[1],"t":k[2],"trades":m["trades"],"net":round(m["net"]),"avg":m["avg_trade"],"win":round(m["win"],3),"pf":round(m["pf"],2),"dd":round(m["max_dd"]),
                "sharpe":round(m["sharpe"],2),"wol":round(m["worst_open_loss"]),"mic_med":int(np.median(z["micros"][z["micros"]>0])),"eq":eq,
                "years":[[r["period"],r["trades"],round(r["net"]),r["avg_trade"]] for r in yr]})
a25=[c for c in curves if c["K"]==0.25]
json.dump({"cal":cal,"k30":out,"k25":a25},open(P+"curves_all.json","w"),separators=(",",":"))
print("saved")
