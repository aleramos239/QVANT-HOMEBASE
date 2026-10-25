"""Hunt 2026-10-20: a stack's walk-forward trades (stack.py --json) through the Apex Legacy 300K PA simulator, five fresh accounts.

Run: .venv-research/bin/python research/edge-library/out/hunt_2026-10-20/apex_stack.py stack.json [--micros 5,10,20] [--no-edge] [--seeds 3]
How: the stack's test months put back to back (weekdays of each month, zero-trade days kept), a day bootstrap into 700-day paths,
each path through research/prop-portfolio/2026-10-01-l2/apex300.py (evaluate_funded, start fresh, model pess, H = 250 trading days).
Two layouts: COPY (every account takes every trade = one account's numbers, $ x 5) and TURNS (trade i -> account i % 5, which never
holds two positions at once because the stack is one position at a time). Policies: request $500 as soon as allowed, or the $3,500
maximum (needs +$10,600). Guesses: a loser's best open profit (mfe) is drawn up to 0.8 x its stop; a trade's side is random (the
stack is one position at a time, so the side changes nothing in the simulator)."""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "research" / "prop-portfolio" / "2026-10-01-l2"))
import apex300 as A  # noqa: E402

E = A.E
H, N = 250, 700


def load(path: str, no_edge: bool) -> tuple[list[list[dict]], float, float]:
    d = json.loads(Path(path).read_text())
    ts = d["taken"]
    avg = st.mean(t["net"] for t in ts)
    risks = [t["risk_pts"] for t in ts if t.get("risk_pts")]
    risk_med = st.median(risks) if risks else 30.0
    days: dict[str, list[dict]] = {}
    for mo in sorted({t["date"][:7] for t in ts}):
        x = dt.date.fromisoformat(mo + "-01")
        while x.strftime("%Y-%m") == mo:
            if x.weekday() < 5:
                days[x.isoformat()] = []
            x += dt.timedelta(1)
    for t in sorted(ts, key=lambda t: t["entry_ms"]):
        days.setdefault(t["date"], []).append({**t, "net": t["net"] - (avg if no_edge else 0.0)})
    return list(days.values()), avg, risk_med


def row(date: str, t: dict, risk_med: float, rng: random.Random) -> dict:
    net = t["net"]
    g = net + 4.0
    risk = t.get("risk_pts") or risk_med
    win = g > 0
    mae = min(t.get("mae") or 0.0, risk * 20) if win else max(t.get("mae") or 0.0, -g)
    mfe = g if win else rng.random() * risk * 20 * 0.8
    side = "long" if rng.random() < 0.5 else "short"
    sg = 1 if side == "long" else -1
    t0 = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, E.ET).time()
    ms = int(dt.datetime.combine(dt.date.fromisoformat(date), t0, E.ET).timestamp() * 1000)
    dur = max(60_000, int(t["exit_ms"]) - int(t["entry_ms"]))
    return {"date": date, "side": side, "qty": 1, "entry_price": 15000.0, "exit_price": 15000.0 + sg * g / 20, "exit_reason": "x",
            "gross": g, "commission": 4.0, "net": net, "mae_usd": mae, "mfe_usd": mfe, "mae_pts": mae / 20, "mfe_pts": mfe / 20,
            "entry_ms": ms, "exit_ms": ms + dur, "sl": 15000.0 - sg * risk, "tp": 15000.0 + sg * risk * 1.5, "order_price": None}


def synth(pool, risk_med, seed):
    rng = random.Random(seed)
    cal, out, d = [], [], dt.date(2021, 9, 22)
    while len(cal) < N:
        if d.weekday() < 5:
            s = d.isoformat()
            cal.append(s)
            out += [row(s, t, risk_med, rng) for t in rng.choice(pool)]
        d += dt.timedelta(1)
    return cal, out


def run(trades, cal, mic, pol):
    P = A.port_from_trades(trades, micros=mic, calendar=cal, start=cal[0], end=cal[-1], allow_holdout=True)
    return A.evaluate_funded(P, micros=mic, policy=pol, both_sides=False, models=("pess",), H=H, allow_holdout=True)["pess"]


def main(argv):
    path = argv[0]
    no_edge = "--no-edge" in argv
    mics = [int(x) for x in (argv[argv.index("--micros") + 1] if "--micros" in argv else "5,10,20").split(",")]
    seeds = int(argv[argv.index("--seeds") + 1]) if "--seeds" in argv else 3
    pool, avg, risk_med = load(path, no_edge)
    n = sum(len(p) for p in pool)
    print(f"{path}: {n} trades over {len(pool)} weekdays ({n / len(pool):.2f} a day), avg ${avg:.0f} a trade at 1 NQ, "
          f"median stop {risk_med:.1f} pts, edge removed={no_edge}")
    out = []
    for mic in mics:
        for pol in (500, "max"):
            cp, rt = [], []
            for seed in range(seeds):
                cal, tr = synth(pool, risk_med, seed)
                cp.append(run(tr, cal, mic, pol))
                rt.append([run([t for i, t in enumerate(tr) if i % 5 == j], cal, mic, pol) for j in range(5)])
            c = {k: st.mean(r[k] for r in cp) for k in ("p_pay_60", "p_bust_any", "e_net_60")}
            rp = st.mean(r["p_pay_60"] for s in rt for r in s)
            rb = st.mean(r["p_bust_any"] for s in rt for r in s)
            re_ = st.mean(sum(r["e_net_60"] for r in s) for s in rt)
            rec = {"micros": mic, "ask": pol, "copy_paid": c["p_pay_60"], "copy_bust": c["p_bust_any"], "copy_usd_5": 5 * c["e_net_60"],
                   "turns_paid_each": rp, "turns_any_paid": 1 - (1 - rp) ** 5, "turns_bust_each": rb, "turns_all5_bust": rb ** 5,
                   "turns_usd_5": re_}
            out.append(rec)
            print(f"{mic:>3} micros ask {str(pol):>4} | COPY: paid {c['p_pay_60']:.0%} bust {c['p_bust_any']:.0%} $/yr all 5 "
                  f"{5 * c['e_net_60']:>9,.0f} | TURNS: each paid {rp:.0%} (any {1 - (1 - rp) ** 5:.0%}) each bust {rb:.0%} "
                  f"(all 5 {rb ** 5:.0%}) $/yr all 5 {re_:>9,.0f}", flush=True)
    Path(path).with_suffix(".apex" + (".noedge" if no_edge else "") + ".json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
