import sys, datetime as dt, numpy as np
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930")
import wide as W, l2data as D
# a sample of in-sample dates (no P&L involved)
df = D.load_features(dt.date(2023, 3, 1), dt.date(2023, 6, 30), columns=["imb10", "book_ok"])
et = df.index.tz_convert("America/New_York")
rows = df[(et.hour == 9) & (et.minute == 30)]
dates = [x.tz_convert("America/New_York").date() for x in rows.index]
v10, meta10, n = W.wide_imb_by_date(dates, cap=10)
vall, metaall, _ = W.wide_imb_by_date(dates, cap=None)
a = np.array([v10[d] for d in dates]); c = rows["imb10"].to_numpy(float)
m = np.isfinite(a) & np.isfinite(c)
print("slots per side in the file:", n, "| dates", len(dates), "| both finite", int(m.sum()))
print("cap=10 vs cached imb10: max abs diff %.2e" % np.max(np.abs(a[m] - c[m])), "(float32 cache)")
lv = np.array([metaall[d][0] for d in dates if d in metaall]); la = np.array([metaall[d][1] for d in dates if d in metaall])
print("near-ladder levels kept (no cap): bid median %d p10 %d p90 %d max %d | ask median %d p10 %d p90 %d max %d" % (np.median(lv), np.percentile(lv, 10), np.percentile(lv, 90), lv.max(), np.median(la), np.percentile(la, 10), np.percentile(la, 90), la.max()))
w = np.array([vall[d] for d in dates]); f = np.isfinite(w) & np.isfinite(c)
print("corr(wide imb, imb10) = %.3f ; sign agreement %.1f%% ; share wide != top10 sign" % (np.corrcoef(w[f], c[f])[0, 1], 100 * np.mean(np.sign(w[f]) == np.sign(c[f]))))
