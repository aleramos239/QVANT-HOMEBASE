import json,sys,csv,numpy as np,collections,datetime as dt
BOX={"cl":("i15_16_close_loc_follow","off_min5_pts15-r2","20261030-110539-draft_nq_eve_cl_e5_p15_r2-c704"),
     "a15r15":("i23_new_high_long","off_min5_atr1p5-r1p5","20261030-110539-draft_nq_eve_nh_e5_a15_r15-bbf1"),
     "p25r05":("i23_new_high_long","off_min5_pts25-r0p5","20261030-110539-draft_nq_eve_nh_e5_p25_r05-95f4"),
     "a15r1":("i23_new_high_long","off_min5_atr1p5-r1","20261030-110539-draft_nq_eve_nh_e5_a15_r1-d312")}
def cmp(k):
    idea,cell,rid=BOX[k]; S="research/edge-library/runs_wf/%s-NQ-tf5/is/"%idea
    rows=[r for r in csv.DictReader(open(S+"table.csv")) if r["sess"]=="all"]; z=np.load(S+"cells.npz",allow_pickle=True)
    i=[r["cell"] for r in rows].index(cell); o=z["off"]; m=slice(int(o[i]),int(o[i+1]))
    E={int(e)//60000:(int(s),float(n),str(rs)) for e,s,n,rs in zip(z["entry_ms"][m],z["side"][m],z["net"][m],z["reason"][m])}
    T=json.load(open("homebase/.state/tester/runs/%s/trades.json"%rid))
    D={t["entry_ms"]//60000:(1 if t["side"]=="long" else -1,t["net"],t["exit_reason"]) for t in T}
    both=set(E)&set(D); eo=sorted(set(E)-set(D)); do=sorted(set(D)-set(E))
    f=lambda x: dt.datetime.utcfromtimestamp(x*60).strftime("%Y-%m-%d %H:%M")
    print(k,"engine",len(E),"desk",len(D),"shared",len(both),"engine-only",len(eo),"desk-only",len(do),"side mismatch",sum(E[x][0]!=D[x][0] for x in both),
          "| engine-only",[f(x) for x in eo[:5]],"desk-only",[f(x) for x in do[:5]])
    print("   exit reasons engine",collections.Counter(v[2] for v in E.values()).most_common(4),"desk",collections.Counter(v[2] for v in D.values()).most_common(4))
for k in sys.argv[1:] or BOX: cmp(k)
