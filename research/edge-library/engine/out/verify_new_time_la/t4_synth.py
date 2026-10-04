"""Synthetic probes (no market data): the 60-minute cancel at each listed time, the break, a print AT the fire instant."""
import sys, datetime as dt
sys.dont_write_bytecode = True
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine")
import numpy as np
import l2sim as S
from families import timed as T

D = dt.date(2023, 5, 10)
NS = 10**9
WIDE = {"stop_mode": "pts", "stop_val": 45.0, "tgt_r": 0.0}

def tape(move_at_ns, to, base=15000.0):
    """One print every 10 s from 18:00 of the evening before to 16:30, flat at `base`; from move_at_ns on every print is `to`."""
    t0 = S.et_ns(D - dt.timedelta(days=1), "18:00"); t1 = S.et_ns(D, "16:30")
    ts = np.arange(t0 + 5 * NS, t1, 10 * NS, dtype=np.int64)       # prints at :05, :15, ... (never exactly on a minute)
    px = np.full(len(ts), base); px[ts >= move_at_ns] = to
    return S.Tape("NQ", D, "NQM3", ts, px, np.ones(len(ts), np.int64))

def run(at, tp, daily=None, **p):
    st = T.StraddleT({"at": at, "off": "ptsA", **WIDE, **p})
    out = []
    if st.eve_window:
        out += S.run_session(st, tp, daily=daily or [], window=st.eve_window, segment="eve", carry=8.0, on_error="raise").trades
    if st.session_window:
        out += S.run_session(st, tp, daily=daily or [], carry=8.0, on_error="raise").trades
    return out

FLAT = {"18:00": "20:00", "20:00": "23:59", "00:00": "02:00", "02:00": "03:00", "03:00": "08:25", "08:30": "09:30",
        "09:30": "11:00", "11:05": "13:30", "13:30": "15:58"}
daily = [{"date": "2023-05-09", "h": 15010.0, "l": 14990.0, "c": 15000.0, "contract": "NQM3"}]
print("last minute after the fire in which a break of the level still gives a trade (EDGE_SPEC: cancel unfilled after 60 min):")
for at in S.LISTED_TIMES:
    eve = at >= "18:00"
    fire = S.et_ns(D - dt.timedelta(days=1) if eve else D, at)
    last = None
    for m in range(1, 70):
        tr = run(at, tape(fire + m * 60 * NS, 15030.0), daily=daily)
        if tr:
            last = m
    print(f"  {at} (flat {FLAT[at]}): last minute with a fill = {last}  -> entries live for {last} < minutes" if last else f"  {at}: never")
for bad in ("17:00:01", "17:30", "17:59"):
    try:
        T.StraddleT({"at": bad}); print("  at", bad, "ACCEPTED (bad)")
    except ValueError as e:
        print("  at", bad, "raises:", str(e)[:70])
# a print exactly AT the fire instant is not the anchor
at = "09:30"; fire = S.et_ns(D, at)
tp = tape(2**62, 0.0)
i = int(np.searchsorted(tp.ts, fire))
ts = np.insert(tp.ts, i, fire); px = np.insert(tp.px, i, 15500.0); sz = np.insert(tp.size, i, 1)
px[i + 1:] = 15500.0
t2 = S.Tape("NQ", D, "NQM3", ts, px, sz)
tr = run(at, t2)
print("  print AT 09:30:00.000 = 15500, before = 15000 -> order_price", [t["order_price"] for t in tr], "(15010 = anchored on the print BEFORE the fire)")
