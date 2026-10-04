"""Independent re-simulation of variants A and B on every NFP with GC tick data (written fresh)."""
import datetime as dt, pickle, sys, math
import numpy as np, pandas as pd
from v1 import et_ns, OUT
D = pickle.load(open(OUT, "rb"))
TICK, PV = 0.10, 100.0
N = 4

def sim(d, df, off, sl_pts, tp_pts, comm_rt, place_ms=85, e_slip=0, s_slip=0, cascade=False, prot_ms=0, cancel_ms=0):
    ts = df.ts_ns.to_numpy(); px = df.price.to_numpy()
    t0 = et_ns(d, 8, 30)
    k = np.searchsorted(ts, t0, side="left") - 1
    if k < 0: return None
    anchor = px[k]
    live = t0 + place_ms * 1_000_000
    cancel_t = et_ns(d, 8, 45); flat_t = et_ns(d, 9, 55)
    buy, sell = round(anchor + off, 2), round(anchor - off, 2)
    m = (ts >= live) & (ts < cancel_t)
    idx = np.flatnonzero(m)
    if len(idx) == 0: return dict(out="NOFILL", net=0.0)
    p = px[idx]
    ib = np.flatnonzero(p >= buy); isl = np.flatnonzero(p <= sell)
    cand = []
    if len(ib): cand.append((ib[0], 1))
    if len(isl): cand.append((isl[0], -1))
    if not cand: return dict(out="NOFILL", net=0.0, anchor=anchor)
    j, side = min(cand)
    i_e = idx[j]; t_e = ts[i_e]
    trig = buy if side == 1 else sell
    fill = (max(trig, px[i_e]) + e_slip * TICK) if side == 1 else (min(trig, px[i_e]) - e_slip * TICK)
    slp = fill - side * sl_pts; tpp = fill + side * tp_pts
    # opposite leg touched within cancel_ms of entry? (double-fill exposure)
    opp = sell if side == 1 else buy
    w = (ts > t_e) & (ts <= t_e + cancel_ms * 1_000_000)
    dbl = bool(((px[w] <= opp) if side == 1 else (px[w] >= opp)).any()) if cancel_ms else False
    # protective orders live only after prot_ms
    t_prot = t_e + prot_ms * 1_000_000
    after = np.flatnonzero((ts >= t_prot) & (ts < flat_t))
    # if price already beyond stop at protection time, exit at first live tick
    pa = px[after]; ta = ts[after]
    if side == 1:
        hit_sl = pa <= slp; hit_tp = pa >= tpp + TICK
    else:
        hit_sl = pa >= slp; hit_tp = pa <= tpp - TICK
    a_sl = np.flatnonzero(hit_sl); a_tp = np.flatnonzero(hit_tp)
    ev = []
    if len(a_sl): ev.append((a_sl[0], "SL"))
    if len(a_tp): ev.append((a_tp[0], "TP"))
    mae = 0.0
    if ev:
        a, why = min(ev)
        ix = after[a]
        if why == "SL":
            base = min(slp, px[ix]) if side == 1 else max(slp, px[ix])
            if cascade and ts[ix] <= t0 + 2_000_000_000:
                jj = np.searchsorted(ts, ts[ix] + 1_000_000_000, side="right")
                ww = px[ix:jj]
                base = min(base, ww.min()) if side == 1 else max(base, ww.max())
            ex = base - side * s_slip * TICK
        else:
            ex = tpp
        t_x = ts[ix]
    else:
        ix = after[-1] if len(after) else i_e
        why, ex, t_x = "FLAT", px[ix] - side * s_slip * TICK, ts[ix]
    seg = px[i_e:ix + 1]
    mae = float((side * (seg - fill)).min() * PV * N)
    gross = side * (ex - fill) * PV * N
    return dict(out=why, net=gross - comm_rt * N, side=side, fill=fill, exit=ex, hold_s=(t_x - t_e) / 1e9, mae_usd=mae,
                dbl=dbl, anchor=anchor, t_e_ms=(t_e - t0) / 1e6)

def run(off, sl_pts, tp_pts, comm_rt, **kw):
    rows = []
    for d, (v, f, df) in sorted(D.items()):
        r = sim(d, df, off, sl_pts, tp_pts, comm_rt, **kw)
        if r is None: continue
        r["date"] = d; rows.append(r)
    return pd.DataFrame(rows)

if __name__ == "__main__":
    pass
