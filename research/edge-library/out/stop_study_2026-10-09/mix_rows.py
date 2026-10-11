"""Read-only, BUILD days: the same boxes, eval odds on the PLAIN row and on the "live is worse" row, alone and mixed. Runs no strategy."""
import sys, os, json, datetime as dt
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"; sys.path[:0] = [W, W + "/engine"]
import library as L, l2sim as S
from blueprint import pipe_prop as PP, propodds as PO, pipe_rules as PR
RUNS = os.path.expanduser("~/.homebase/pipeline/runs")
NAMES = ["nq_orb_stops", "nq_ib_break_nyam", "nq_or_mid_long", "nq_noise_mid_long", "nq_pm_follow_long", "nq_vwap_pullback", "nq_vwap_pull_pm_long"]
cal = [d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)]
need, A = PR.need("prop"), PO.app(); r = A.load_rules(need["account"]); N = int(need["days"])
print("account:", r.get("name"), "| days", N, "| worse row:", PR.need("degrade") if False else "win rate -5 points, winners -15 %")
def box(n):
    s = json.load(open(os.path.expanduser(f"~/.homebase/pipeline/p/{n}/state.json")))["picked"]
    u = L.load_unit(f"{s['sub']}-NQ-tf{s['bar']}", RUNS); x = L.unit_cell(u, s["cell"])
    return {k: np.asarray(x[k]) for k in L.FIELDS}
def mix(xs):
    x = {k: np.concatenate([a[k] for a in xs]) for k in L.FIELDS}; o = np.argsort(x["entry_ms"], kind="stable"); return {k: v[o] for k, v in x.items()}
def both(x, days_n=N):
    ev, _ = PO.steps(r); out = {}
    for tag in ("plain", "worse"):
        best = (0.0, None)
        for size in ev:
            net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, cal)
            if tag == "worse": net, opn = PO.worse(net, traded, opn)
            idx = PO.draws(len(net), A.N_PATHS, max(days_n, PO.horizon(r)), A.SEED)[:, :days_n]
            e = PO.eval_walk(net[idx], traded[idx], opn[idx], r)
            p = float(((e["outcome"] == PO.PASS) & (e["day"] <= days_n)).mean())
            if p > best[0]: best = (p, size)
        out[tag] = best
    return out
def line(tag, x):
    net = x["net"]; w = net > 0
    o = both(x)
    print(f"{tag:44s} win {100*w.mean():3.0f}% avg win ${net[w].mean():5.0f} avg loss ${-net[~w].mean():5.0f} avg ${net.mean():4.0f} | eval in {N} days: plain {100*o['plain'][0]:4.1f}% ({o['plain'][1]} micros)   live-is-worse {100*o['worse'][0]:4.1f}% ({o['worse'][1]} micros)")
B = {n: box(n) for n in NAMES}
for n in NAMES: line(n, B[n])
print()
line("MIX one a session (orb, or_mid, pm_follow)", mix([B[n] for n in ("nq_orb_stops", "nq_or_mid_long", "nq_pm_follow_long")]))
line("MIX 4 (+ vwap_pullback)", mix([B[n] for n in ("nq_orb_stops", "nq_or_mid_long", "nq_pm_follow_long", "nq_vwap_pullback")]))
line("MIX of all 7", mix([B[n] for n in NAMES]))
