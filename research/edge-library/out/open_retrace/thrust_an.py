import json, numpy as np
D=json.load(open("thrust.json"))
meda=float(np.median([a for _,a,_ in D]))
print("days",len(D),"median daily ATR14 (pts):",round(meda))
def analyse(K, giveback=0.5):
    q=0; rev=0; mins=[]; thrust_t=[]; sizes=[]; both=0
    for iso,atr,bars in D:
        O=bars[0][1]; d=K*atr
        side=0; ext=None; t_ext=None
        for (m,o,h,l,c) in bars:
            if side==0:
                u = h-O>=d; w = O-l>=d
                if u and w: both+=1; break
                if u: side=1; ext=h; t_ext=m
                elif w: side=-1; ext=l; t_ext=m
                if side: q+=1
                continue
            if side==1:
                if h>ext: ext=h; t_ext=m
                lvl=ext-giveback*(ext-O)
                if l<=lvl and m>t_ext: rev+=1; mins.append(m-t_ext); sizes.append(ext-O); thrust_t.append(t_ext-570); break
            else:
                if l<ext: ext=l; t_ext=m
                lvl=ext+giveback*(O-ext)
                if h>=lvl and m>t_ext: rev+=1; mins.append(m-t_ext); sizes.append(O-ext); thrust_t.append(t_ext-570); break
    n=len(D); mins=np.array(mins)
    f=lambda x: None if not len(mins) else round(100*float((mins<=x).mean()))
    return dict(K=K,D=round(K*meda),q=q,qp=round(100*q/n),rev=rev,rp=round(100*rev/max(q,1)),med=float(np.median(mins)) if len(mins) else None,
                w5=f(5),w15=f(15),w30=f(30),th=round(float(np.median(sizes))) if sizes else None,tt=float(np.median(thrust_t)) if thrust_t else None,both=both)
print("K     D_pts  days_with_thrust   give_back_50%_by_11:00   min_from_extreme_to_50%: median | <=5 | <=15 | <=30   median_thrust_pts  min_open_to_extreme")
for K in (0.05,0.08,0.10,0.12,0.15,0.20,0.25,0.30):
    r=analyse(K)
    print(f"{r['K']:.2f}  {r['D']:>4}   {r['q']:>4} ({r['qp']}%)       {r['rev']:>4} ({r['rp']}% of those)        {r['med']} | {r['w5']}% | {r['w15']}% | {r['w30']}%       {r['th']}   {r['tt']}   (both sides in one bar: {r['both']})")
