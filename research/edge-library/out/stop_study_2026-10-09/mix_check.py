"""Read-only, BUILD days only: the picked boxes of the ideas that stopped at the proof or the lock (never read on unseen days), each alone and
mixed at one size: months won, drawdown, and the pipeline's own prop odds (LucidPro 50K, 30 days). Runs no strategy."""
import sys, os, json, datetime as dt, itertools
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"; sys.path[:0] = [W, W + "/engine"]
import library as L, l2sim as S
from blueprint import pipe_prop as PP
RUNS = os.path.expanduser("~/.homebase/pipeline/runs")
NAMES = ["nq_orb_stops", "nq_ib_break_nyam", "nq_or_mid_long", "nq_noise_mid_long", "nq_pm_follow_long", "nq_vwap_pullback", "nq_vwap_pull_pm_long"]
cal = [d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)]
days = np.array([dt.date.fromisoformat(d).toordinal() for d in cal])
def box(n):
    s = json.load(open(os.path.expanduser(f"~/.homebase/pipeline/p/{n}/state.json")))["picked"]
    u = L.load_unit(f"{s['sub']}-NQ-tf{s['bar']}", RUNS)
    x = L.unit_cell(u, s["cell"])
    sess = json.load(open(os.path.expanduser(f"~/.homebase/pipeline/p/{n}/card.json")))["session"]
    return s["cell"], sess, {k: np.asarray(x[k]) for k in L.FIELDS}
def mix(xs):
    x = {k: np.concatenate([a[k] for a in xs]) for k in L.FIELDS}
    o = np.argsort(x["entry_ms"], kind="stable")
    return {k: v[o] for k, v in x.items()}
def daily(x):
    d = np.zeros(len(days)); np.add.at(d, np.searchsorted(days, x["date"]), x["net"]); return d
def row(tag, x):
    d = daily(x); cum = np.cumsum(d); dd = float((np.maximum.accumulate(np.concatenate(([0.0], cum))) - np.concatenate(([0.0], cum))).max())
    ym = np.array([dt.date.fromordinal(int(v)).year * 12 + dt.date.fromordinal(int(v)).month for v in days]); mu, mi = np.unique(ym, return_inverse=True)
    mon = np.zeros(len(mu)); np.add.at(mon, mi, d)
    run = best = 0
    for v in d:
        run = run + 1 if v < 0 else 0; best = max(best, run)
    sd = d.std(ddof=1); sharpe = d.mean() / sd * np.sqrt(252) if sd > 0 else 0
    o = PP.odds(x, cal)
    yr = [float(d[np.array([dt.date.fromordinal(int(v)).year for v in days]) == y].sum()) for y in (2021, 2022, 2023, 2024, 2025)]
    print(f"{tag:34s} {len(x['net']):5d} ${x['net'].mean():6.0f} | months won {100*(mon>0).mean():3.0f}% | losing-day run {best:2d} | Sharpe {sharpe:4.2f} | net/DD {x['net'].sum()/dd:4.1f} | DD 1 micro ${dd/10:5.0f} | "
          f"eval {100*o['eval']:4.1f}% at {o['size']} micros | payout {100*o['payout']:4.1f}% | by year $k " + " ".join(f"{v/1000:5.0f}" for v in yr))
    return d
B = {}
for n in NAMES:
    cell, sess, x = box(n); B[n] = x
    B[n + "#d"] = row(f"{n} ({sess}, {cell})", x)
C = np.corrcoef(np.array([B[n + "#d"] for n in NAMES]))
print("\ndaily P&L correlation between them: mean", round(float(C[np.triu_indices(len(NAMES), 1)].mean()), 2), "max", round(float(C[np.triu_indices(len(NAMES), 1)].max()), 2))
for i, a in enumerate(NAMES):
    print(f"  {a:22s}", " ".join(f"{C[i, j]:5.2f}" for j in range(len(NAMES))))
print()
row("MIX of all 7", mix([B[n] for n in NAMES]))
row("MIX one a session (orb, or_mid, pm_follow)", mix([B[n] for n in ("nq_orb_stops", "nq_or_mid_long", "nq_pm_follow_long")]))
row("MIX 4 (orb, or_mid, pm_follow, vwap_pullback)", mix([B[n] for n in ("nq_orb_stops", "nq_or_mid_long", "nq_pm_follow_long", "nq_vwap_pullback")]))
row("MIX 5 (+ noise_mid)", mix([B[n] for n in ("nq_orb_stops", "nq_or_mid_long", "nq_pm_follow_long", "nq_vwap_pullback", "nq_noise_mid_long")]))
