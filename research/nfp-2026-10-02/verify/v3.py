import sys, numpy as np, pandas as pd, datetime as dt
from v2 import *
from math import sqrt
def wil(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    p = k/n; den = 1+z*z/n; c = (p+z*z/(2*n))/den; h = z*sqrt(p*(1-p)/n+z*z/(4*n*n))/den; return c-h, c+h
IS_END = dt.date(2024,12,31)
def summ(df, label, win=3000.0):
    for nm, m in (("IS", df.date <= IS_END), ("HO", df.date > IS_END), ("ALL", df.date > dt.date(1900,1,1))):
        x = df[m]; n = len(x); w = int((x.net >= win).sum()); b = int((x.net <= -2000).sum())
        lo, hi = wil(w, n)
        print(f"  {label:34s} {nm:3s} n={n:2d} fills={int((x.out!='NOFILL').sum()):2d} pass={w:2d} ({w/n:.0%} [{lo:.0%}-{hi:.0%}]) SL={int((x.out=='SL').sum()):2d} FLAT={int((x.out=='FLAT').sum()):2d} bust(<=-2000)={b} meannet=${x.net.mean():,.0f} worst=${x.net.min():,.0f}")
if __name__ == "__main__":
    for comm in (16.0/4, 4.60):
        print("== commission per GC round turn", comm, " (x4 =", comm*4, ")")
        for nm, off, sl, tp in (("A off2 SL3.7 TP7.6", 2.0, 3.7, 7.6), ("B off2 SL5.0 TP7.6", 2.0, 5.0, 7.6)):
            summ(run(off, sl, tp, comm), nm+" M0 (no slip)")
            summ(run(off, sl, tp, comm, e_slip=1, s_slip=1), nm+" M1 1t/1t")
            summ(run(off, sl, tp, comm, e_slip=2, s_slip=2, cascade=True), nm+" P2 2t+casc")
