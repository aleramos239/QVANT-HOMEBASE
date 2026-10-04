import datetime as dt, sys
sys.dont_write_bytecode = True
L = "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2"
sys.path.insert(0, L)
import numpy as np, pyarrow.parquet as pq
import l2data as D, l2sim as S
NS = 10**9
GRID = np.round(np.arange(-1.2, 0.3001, 0.02), 2)
for iso in ["2023-11-06", "2023-11-14", "2024-12-05", "2024-12-10", "2022-08-17"]:
    d = dt.date.fromisoformat(iso); S.check_holdout(d)
    t = pq.ParquetFile(S.tape_path(d)).read(columns=["ts_ns", "price"])
    ts, px = t["ts_ns"].to_numpy(), t["price"].to_numpy()
    df = D.load_features(d - dt.timedelta(days=1), d, columns=["bid_px", "ask_px"])
    df = df[df["book_ok"]]
    ua, bid, ask = df.index.as_unit("ns").asi8, df["bid_px"].to_numpy(), df["ask_px"].to_numpy()
    for name, a, b in (("overnight 00:00-08:25", "00:00", "08:25"), ("rth 09:30-15:58", "09:30", "15:58")):
        k = (ua > S.et_ns(d, a)) & (ua <= S.et_ns(d, b))
        curve = []
        for dl in GRID:
            j = np.searchsorted(ts, ua[k] + int(round(dl * NS)), side="left") - 1
            p = px[j]
            curve.append(float(np.maximum(np.maximum(bid[k] - p, p - ask[k]), 0.0).mean()))
        curve = np.array(curve)
        i = int(curve.argmin())
        near0 = {float(g): round(float(c), 4) for g, c in zip(GRID, curve) if g in (-0.7, -0.1, -0.04, -0.02, 0.0, 0.02, 0.04, 0.1)}
        print(iso, name, "n", int(k.sum()), "argmin delta", GRID[i], "min", round(curve[i], 4), near0)
