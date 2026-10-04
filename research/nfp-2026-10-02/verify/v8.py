import numpy as np, pandas as pd, datetime as dt
from v2 import *
import v2
from v3 import wil, IS_END

def sim2(d, df, off, sl_pts, tp_pts, comm_rt, tp_delay_s=0.0, e_slip=1, s_slip=1, place_ms=85):
    """Like v2.sim but target limit is only working from tp_delay_s after the fill (stop is active from the fill)."""
    ts = df.ts_ns.to_numpy(); px = df.price.to_numpy()
    t0 = et_ns(d, 8, 30); k = np.searchsorted(ts, t0, side="left") - 1
    anchor = px[k]; live = t0 + place_ms * 1_000_000
    cancel_t = et_ns(d, 8, 45); flat_t = et_ns(d, 9, 55)
    buy, sell = round(anchor + off, 2), round(anchor - off, 2)
    idx = np.flatnonzero((ts >= live) & (ts < cancel_t)); p = px[idx]
    ib = np.flatnonzero(p >= buy); isl = np.flatnonzero(p <= sell)
    cand = ([(ib[0], 1)] if len(ib) else []) + ([(isl[0], -1)] if len(isl) else [])
    if not cand: return dict(out="NOFILL", net=0.0, hold_s=np.nan)
    j, side = min(cand); i_e = idx[j]; t_e = ts[i_e]
    trig = buy if side == 1 else sell
    fill = (max(trig, px[i_e]) + e_slip * TICK) if side == 1 else (min(trig, px[i_e]) - e_slip * TICK)
    slp = fill - side * sl_pts; tpp = fill + side * tp_pts
    rng = np.flatnonzero((ts > t_e) & (ts < flat_t))
    pa, ta = px[rng], ts[rng]
    sl_hit = (pa <= slp) if side == 1 else (pa >= slp)
    tp_hit = ((pa >= tpp + TICK) if side == 1 else (pa <= tpp - TICK)) & (ta >= t_e + int(tp_delay_s * 1e9))
    # marketable at activation: price already beyond target when the limit is placed
    act = np.searchsorted(ta, t_e + int(tp_delay_s * 1e9), side="left")
    ev = []
    if sl_hit.any(): ev.append((np.flatnonzero(sl_hit)[0], "SL"))
    if tp_hit.any(): ev.append((np.flatnonzero(tp_hit)[0], "TP"))
    if ev:
        a, why = min(ev); ix = rng[a]
        if why == "SL":
            base = min(slp, px[ix]) if side == 1 else max(slp, px[ix]); ex = base - side * s_slip * TICK
        else: ex = tpp
        t_x = ts[ix]
    else:
        ix = rng[-1]; why, ex, t_x = "FLAT", px[ix] - side * s_slip * TICK, ts[ix]
    return dict(out=why, net=side * (ex - fill) * PV * N - comm_rt * N, hold_s=(t_x - t_e) / 1e9, side=side)

def runs(**kw):
    rows = []
    for d, (v, f, df) in sorted(D.items()):
        r = sim2(d, df, **kw); r["date"] = d; rows.append(r)
    return pd.DataFrame(rows)

def rep(label, r):
    for nm, m in (("IS", r.date <= IS_END), ("HO", r.date > IS_END), ("ALL", r.date > dt.date(1900, 1, 1))):
        x = r[m]; w = x.net >= 3000; lo, hi = wil(int(w.sum()), len(x))
        wins = x[w]; fast = int((wins.hold_s <= 5).sum())
        print(f"  {label:40s} {nm:3s} pass {int(w.sum())}/{len(x)} ({w.mean():.0%} [{lo:.0%}-{hi:.0%}]) bust(<=-2000) {int((x.net<=-2000).sum())}  wins held<=5s: {fast}/{len(wins)}  worst ${x.net.min():,.0f}")

C = 4.60
print("== fee margin: TP distance (A stop 3.7, off 2) first-print M1")
for tp in (7.5, 7.6, 7.7, 7.8, 8.0):
    rep(f"A TP {tp}", runs(off=2.0, sl_pts=3.7, tp_pts=tp, comm_rt=C))
print("== delayed target (limit only works 5.1 s after fill), TP 7.6/7.7")
for tp in (7.6, 7.7):
    rep(f"A TP {tp} immediate", runs(off=2.0, sl_pts=3.7, tp_pts=tp, comm_rt=C, tp_delay_s=0))
    rep(f"A TP {tp} delayed 5.1s", runs(off=2.0, sl_pts=3.7, tp_pts=tp, comm_rt=C, tp_delay_s=5.1))
    rep(f"B(SL5.0) TP {tp} delayed 5.1s", runs(off=2.0, sl_pts=5.0, tp_pts=tp, comm_rt=C, tp_delay_s=5.1))
