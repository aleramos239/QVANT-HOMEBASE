import numpy as np, pandas as pd, datetime as dt
from v2 import *
from v3 import summ, IS_END
C = 4.60
print("=== hold time of winners / OCO double-touch (A, M1, 85ms place, NFP only)")
for nm, sl in (("A", 3.7), ("B", 5.0)):
    r = run(2.0, sl, 7.6, C, e_slip=1, s_slip=1, cancel_ms=250)
    w = r[r.net >= 3000]
    print(nm, "wins", len(w), "hold<=5s", int((w.hold_s <= 5).sum()), "hold<=2s", int((w.hold_s <= 2).sum()), " median hold of wins %.1fs" % w.hold_s.median(), " min %.2fs max %.1fs" % (w.hold_s.min(), w.hold_s.max()))
    print("   pnl share from <=5s holds: %.0f%%" % (100 * w[w.hold_s <= 5].net.sum() / w.net.sum()))
    print("   opposite leg touched within 250ms of entry (double-fill exposure):", int(r.dbl.sum()), "of", len(r))
    for ms in (50, 100, 500, 1000):
        rr = run(2.0, sl, 7.6, C, e_slip=1, s_slip=1, cancel_ms=ms)
        print("   opp touched within %4dms: %d" % (ms, int(rr.dbl.sum())))
    ls = r[r.out == "SL"]
    print("   stop-outs:", len(ls), "hold<=5s", int((ls.hold_s <= 5).sum()), "median hold %.1fs" % ls.hold_s.median())
print("=== placement latency sensitivity (M1 slip), NFP pass count IS/HO, A and B")
for pm in (0, 85, 250, 500, 1000):
    for nm, sl in (("A", 3.7), ("B", 5.0)):
        r = run(2.0, sl, 7.6, C, place_ms=pm, e_slip=1, s_slip=1)
        i = r[r.date <= IS_END]; h = r[r.date > IS_END]
        print(f"place {pm:4d}ms {nm}: IS {int((i.net>=3000).sum())}/{len(i)} HO {int((h.net>=3000).sum())}/{len(h)} nofill {int((r.out=='NOFILL').sum())}  bust1stprint {int((r.net<=-2000).sum())}")
print("=== protective-order latency (stop+target live only after X ms), M1 slip")
for pr in (0, 100, 250, 500, 1000):
    for nm, sl in (("A", 3.7), ("B", 5.0)):
        r = run(2.0, sl, 7.6, C, e_slip=1, s_slip=1, prot_ms=pr)
        i = r[r.date <= IS_END]; h = r[r.date > IS_END]
        print(f"prot {pr:4d}ms {nm}: IS {int((i.net>=3000).sum())}/{len(i)} HO {int((h.net>=3000).sum())}/{len(h)} bust {int((r.net<=-2000).sum())} worst ${r.net.min():,.0f}  losers mean ${r[r.net<0].net.mean():,.0f}")
