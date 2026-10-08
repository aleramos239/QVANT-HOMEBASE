import pickle, json, numpy as np
import l2sim as S, library as L
P="/private/tmp/claude-501/-Users-ramoscapital-ramos-quant-homebase/bdbddd8a-a60a-4914-96dc-cac21a5eb2eb/scratchpad/retrace/"
d=pickle.load(open(P+"judas.pkl","rb")); cal=json.load(open(P+"cal.json"))["cal"]
tr=dict(zip(d["keys"],d["trades"]))
for K in (0.3,0.25,0.2):
    key=(K,0.5,0.5); x=L.pack(tr[key])
    print(f"\n### thrust {K} (x daily ATR), stop at the extreme, target at the open — 1 contract, costs on")
    print("\n".join(L.metrics_md(L.per_year(x,cal))))
    for side,name in ((1,"long"),(-1,"short")):
        m=x["side"]==side; y={k:np.asarray(v)[m] for k,v in x.items() if k in L.FIELDS}; r=L.metrics(y,cal)
        print(f"{name}: trades {r['trades']} net {r['net']:.0f} avg {r['avg_trade']} win {r['win']:.3f} pf {r['pf']:.2f}")
    why={}
    for t in tr[key]: why[t['exit_reason']]=why.get(t['exit_reason'],0)+1
    print("exits:",why, " median stop pts:", round(float(np.median([abs(t['entry_price']-t['sl']) for t in tr[key]])),1))
    z=L.sized(x,"NQ"); print("sized to ~$1,000 risk in micros:", {k:v for k,v in L.metrics(z,cal,z["cost"]).items() if k in ("trades","net","avg_trade","pf","max_dd","sharpe")})
