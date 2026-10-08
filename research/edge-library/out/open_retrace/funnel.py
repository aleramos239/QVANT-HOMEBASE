import json, csv, collections
import numpy as np
D=json.load(open("thrust.json"))
def run(K, cap, end=655):          # end 10:55 = last entry minute
    n=len(D); thr=0; amb=0; half=0; within=0; trades=0; trend=0
    for iso,atr,bars in D:
        O=bars[0][1]; d=K*atr; side=0; ext=None; t_ext=None; got=False; got_cap=False
        for (m,o,h,l,c) in bars:
            if m>end: break
            if side==0:
                u=h-O>=d; w=O-l>=d
                if u and w: amb+=1; break
                if u: side=1; ext=h; t_ext=m
                elif w: side=-1; ext=l; t_ext=m
                if side: thr+=1
                continue
            if side==1:
                if h>ext: ext=h; t_ext=m
                lvl=ext-0.5*(ext-O)
                if l<=lvl and m>t_ext:
                    got=True
                    if m-t_ext<=cap: got_cap=True
                    break
            else:
                if l<ext: ext=l; t_ext=m
                lvl=ext+0.5*(O-ext)
                if h>=lvl and m>t_ext:
                    got=True
                    if m-t_ext<=cap: got_cap=True
                    break
        half+=got; within+=got_cap
    return dict(days=n,thrust=thr,half_back=half,within_cap=within)
for K in (0.3,0.25):
    print("K",K)
    for cap in (15,30,60,999):
        r=run(K,cap); print(f"  cap {cap if cap<999 else 'none':>4} min: days {r['days']}  thrust {r['thrust']} ({100*r['thrust']/r['days']:.0f}%)  gave back 50% by 10:55 {r['half_back']} ({100*r['half_back']/r['days']:.0f}%)  AND within cap {r['within_cap']} ({100*r['within_cap']/r['days']:.0f}%)")
rows=list(csv.DictReader(open("ledgers/K30_s50_t50.csv")))
hrs=collections.Counter()
for r in rows:
    t=r["entry_time"][11:16]; h,m=int(t[:2]),int(t[3:]); k=h*60+m
    b="09:30-09:45" if k<585 else "09:45-10:00" if k<600 else "10:00-10:15" if k<615 else "10:15-10:30" if k<630 else "10:30-10:55"
    hrs[b]+=1
print({b:f"{v} ({100*v/len(rows):.0f}%)" for b,v in sorted(hrs.items())})
