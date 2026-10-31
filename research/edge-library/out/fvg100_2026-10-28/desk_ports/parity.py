import json,sys,csv,numpy as np,collections,datetime as dt
BOX={"b1":("min_gap0p25_pts60-r1","20261029-193633-draft_nq_fvg15_ovw_g25_s60_r1-595b"),
     "b5":("min_gap0p25_pts25-r2","20261029-193633-draft_nq_fvg15_ovw_g25_s25_r2-d102"),
     "b7":("min_gap0p1_pts60-r0p75","20261029-193633-draft_nq_fvg15_ovw_g10_s60_r075-8c49"),
     "b8":("min_gap0p1_pts25-r1p5","20261029-193633-draft_nq_fvg15_ovw_g10_s25_r15-088e")}
S="research/edge-library/runs_wf/f100_ovw15-NQ-tf15/is/"
rows=[r for r in csv.DictReader(open(S+"table.csv")) if r["sess"]=="all"]
z=np.load(S+"cells.npz",allow_pickle=True)
def cmp(k, rid=None):
    cell,rid0=BOX[k]; rid=rid or rid0
    i=[r["cell"] for r in rows].index(cell)
    o=z["off"]; m=slice(int(o[i]),int(o[i+1]))
    E=collections.OrderedDict(); 
    for e,s,n,rs,du in zip(z["entry_ms"][m],z["side"][m],z["net"][m],z["reason"][m],z["dur_s"][m]): E[int(e)//60000]=(int(s),float(n),str(rs),float(du))
    T=json.load(open("homebase/.state/tester/runs/%s/trades.json"%rid))
    D={t["entry_ms"]//60000:(1 if t["side"]=="long" else -1,t["net"],t["exit_reason"],t["seconds"]) for t in T}
    both=set(E)&set(D); eo=sorted(set(E)-set(D)); do=sorted(set(D)-set(E))
    print(k,"engine",len(E),"desk",len(D),"shared",len(both),"engine-only",len(eo),"desk-only",len(do))
    f=lambda ms: dt.datetime.utcfromtimestamp(ms*60).strftime("%Y-%m-%d %H:%M")
    print(" engine-only first:",[f(x) for x in eo[:8]]); print(" desk-only first:",[f(x) for x in do[:8]])
    # sides equal and exits
    print(" side mismatches",sum(E[x][0]!=D[x][0] for x in both))
    return E,D
if __name__=="__main__":
    for k in sys.argv[1:] or BOX: cmp(k)
