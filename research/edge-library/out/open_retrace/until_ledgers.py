import pickle, json, csv, datetime as dt
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
d=pickle.load(open(P+"until.pkl","rb")); tr=dict(zip(d["keys"],d["trades"]))
for u in ("12:00","15:55"):
    for s in (0.5,0.75):
        t=tr[(0.3,u,s,0.5)]; x=L.pack(t); z=L.sized(x,"NQ",risk_usd=500.0); rows=[]
        for i,r in enumerate(t):
            mic=int(z["micros"][i]); rows.append([dt.datetime.fromtimestamp(r["entry_ms"]/1000,S.ET).strftime("%Y-%m-%d %H:%M:%S"),r["side"],mic,round(float(z["net"][i]),2),round(mic*abs(r["entry_price"]-r["sl"])*2.0,2)])
        with open(P+f"ledgers/U{u.replace(':','')}_K30_s{int(s*100)}_t50.csv","w",newline="") as fh:
            w=csv.writer(fh); w.writerow(["entry_time","side","qty","pnl","risk"]); w.writerows(rows)
print("ok")
