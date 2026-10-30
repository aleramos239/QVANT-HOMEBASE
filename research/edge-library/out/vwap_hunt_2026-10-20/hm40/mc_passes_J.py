"""Monte Carlo of the three Amendment-J passes on their TEST-MONTH trades (already read; nothing new is run): the house reshuffle
(blueprint/mc.py: 1,000 runs of whole days drawn with replacement, fixed seed). Bars written before running: R1 money in >= 90 % of runs;
R2 still money with winners cut by 15 %. Drawdown and years shown, not judged."""
import sys, datetime as dt
from pathlib import Path
import numpy as np
EL = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library"); sys.path.insert(0, str(EL)); sys.path.insert(0, str(EL / "engine"))
import library as LB
from blueprint import runner as RUN, wfmonths as WM, mc as MC
NY = [LB.SESS_CODE[s] for s in ("nyam", "mid", "pm")]
LEGS = {"VWAP touch, trending days (ADX)": "vh_i10_adx_touch_5_ny-NQ-tf5", "EMA crosses VWAP, high volume": "vh_i16_emavwap_rv_5_ny-NQ-tf5",
        "Volume breakout (5m)": "vh_i17_rvbrk_5_ny-NQ-tf5"}

def days_of(store):
    u = LB.load_unit("is", RUN.RUNS_WF / store); have = {d[:7] for d in u["meta"]["days"]}
    return [d for b in WM.blocks("NQ") if set(b["is"]) <= have for d in WM.oos_days("NQ", b["oos"])]

def daily(store, haircut=1.0):
    x = LB.unit_cell(LB.load_unit("oos", RUN.RUNS_WF / store), 0)
    k = np.isin(np.asarray(x["sess"]), NY)
    net = np.asarray(x["net"], float)[k]; net = np.where(net > 0, net * haircut, net)
    date = np.asarray(x["date"])[k]
    days = days_of(store); idx = {dt.date.fromisoformat(d).toordinal(): i for i, d in enumerate(days)}
    dn, dc = np.zeros(len(days)), np.zeros(len(days))
    for d, v in zip(date, net):
        dn[idx[int(d)]] += v; dc[idx[int(d)]] += 1
    return days, dn, dc, net, date

def mc(dn, dc):
    tot, _ = MC.reshuffle(dn[None, :], dc[None, :])
    h = MC.histories(dn[None, :])[0]                       # runs x days
    eq = np.cumsum(h, axis=1); dd = (np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq).max(axis=1)
    return tot[0], dd

def maxdd(x):
    eq = np.cumsum(x); return float((np.maximum.accumulate(np.maximum(eq, 0)) - eq).max())

all_dn = None
for name, st in LEGS.items():
    days, dn, dc, net, date = daily(st)
    tot, dd = mc(dn, dc)
    days_h, dn_h, dc_h, *_ = daily(st, 0.85)
    tot_h, dd_h = mc(dn_h, dc_h)
    print(f"\n=== {name}  ({st})")
    print(f"  test months: {len(net)} trades on {len(days)} days, net ${dn.sum():,.0f}, avg ${net.mean():.0f}, win {100*(net>0).mean():.1f} %, worst drawdown ${maxdd(dn):,.0f}")
    print(f"  R1 reshuffles: money in {100*(tot>0).mean():.1f} % of 1,000 runs | net p5 ${np.percentile(tot,5):,.0f} median ${np.median(tot):,.0f} p95 ${np.percentile(tot,95):,.0f}")
    print(f"     worst drawdown: median ${np.median(dd):,.0f}, p95 ${np.percentile(dd,95):,.0f}")
    print(f"  R2 winners -15 %: net ${dn_h.sum():,.0f}; money in {100*(tot_h>0).mean():.1f} % of runs; median ${np.median(tot_h):,.0f}")
    yrs = np.array([dt.date.fromordinal(int(d)).year for d in date]); mos = np.array([dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in date])
    print("  by year:", " | ".join(f"{y}: {int((yrs==y).sum())} tr ${net[yrs==y].sum():,.0f} win {100*(net[yrs==y]>0).mean():.0f}%" for y in sorted(set(yrs))))
    mm = sorted(set(d[:7] for d in days)); pos = sum(1 for m in mm if net[mos == m].sum() > 0)
    print(f"  test months positive: {pos} of {len(mm)}")
    all_dn = dn if all_dn is None else all_dn + dn
    assert days == days_of(LEGS[next(iter(LEGS))])
dc_all = np.ones_like(all_dn)
tot, dd = mc(all_dn, dc_all)
print(f"\n=== the three together (one account each, day nets added): net ${all_dn.sum():,.0f}; money in {100*(tot>0).mean():.1f} % of runs; "
      f"p5 ${np.percentile(tot,5):,.0f}; worst drawdown actual ${maxdd(all_dn):,.0f}, median ${np.median(dd):,.0f}, p95 ${np.percentile(dd,95):,.0f}")
