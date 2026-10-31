"""Portfolio hunt: the RANDOM-ENTRY LINE of a picked box on its TEST months (PREREG_HM40.md section 5, P3). The lane's test-month read
(hmwf.run_oos) keeps the picked box's trades and nothing else; its random line exists on the in-sample months only (the c1f / c1h pool).
This runs THE SAME random entries as that pool (l2ref.Random, p_entry 0.5, the control's 10 seeds, all of the store's sessions) at the
exit cell the lane holds the box against (an ATR box: itself; an own-stop box: the ATR cell of its multiplier; a fixed-point box: itself),
on the same test months (one month a call, l2sim.ALLOW_WF_OOS), after the box's own read is on file. No strategy trade is run or read
here: random entries read only the market. Under the owner's standing word (2026-10-20) and logged in LUCK.md.

    oosrand.py <store> [--workers=3]     -> <store>/oos-rand.npz;   line(store) = the share of seeds below the box (its sessions, its side)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EL = HERE.parents[2]
sys.path.insert(0, str(EL))
sys.path.insert(0, str(EL / "engine"))

import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402
from blueprint import hmwf as H  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import wfmonths as WM  # noqa: E402

RUNS = RUN.RUNS_WF


def _cell(home: Path) -> tuple:
    lock = json.loads((home / "lock.json").read_text())
    u, m = H._load(home)
    c = next(c for c in m["cells"] if c["id"] == lock["box"])
    ex = c["exit"]
    yard = {"stop_mode": "pts" if ex["stop_mode"] == "pts" else "atr", "stop_val": ex["stop_val"], "tgt_r": ex["tgt_r"]}
    return lock, m, c, yard


def run(store: str, workers: int = 3) -> Path:
    import l2ref
    home = RUNS / store
    out = home / "oos-rand.npz"
    if out.exists():
        return out
    if not (home / "oos" / "cells.npz").exists():
        raise SystemExit(f"{store}: the box's own test-month read is not on file: nothing to compare yet")
    lock, m, c, yard = _cell(home)
    have = {d[:7] for d in m["days"]}
    months = [b["oos"] for b in WM.blocks(m["root"]) if set(b["is"]) <= have]
    seeds = list(range(1, R.template("control")["seeds"] + 1))
    import hmread as HR
    sess = [s for g in HR.groups_of(m["sessions"]) for s in HR.GROUPS[g]]     # the whole groups, as the in-sample pool's sessions
    specs = [(l2ref.Random, {"tf": str(m["tf"]), "sess": s, "hold_to": RM.HOLD, "p_entry": RM.C1_P_ENTRY, "seed": sd, **yard})
             for sd in seeds for s in sess]                    # one instance a session, hold_to day: run_idea.cell_specs, as the pool
    got = {sd: [] for sd in seeds}
    for mo in months:
        days = WM.oos_days(m["root"], mo)
        if not days:
            continue
        res = S.run_many(specs, S._date(days[0]), S._date(days[-1]), days=days, root=m["root"], workers=max(1, min(workers, S.MAX_WORKERS)),
                         allow_holdout=S.ALLOW_WF_OOS, **RUN._engine({}))
        for (cls, inp), r in zip(specs, res):
            got[inp["seed"]] += r["trades"]
    arrays = {}
    for sd, ts in got.items():
        x = LB.pack(sorted(ts, key=lambda t: t["entry_ms"]))
        for k in ("date", "net", "side", "sess"):
            arrays[f"s{sd}|{k}"] = np.asarray(x[k])
    np.savez(out, **arrays)
    print(f"{store}: {len(specs)} random instances on {len(months)} test months, exit {S.cell_id(yard)} -> {out.name}", flush=True)
    return out


def line(store: str, group_sessions=None, side=None) -> float | None:
    """The share of the 10 seeds whose average test-month trade (the box's sessions or `group_sessions`, its side when one-sided) is below
    the box's own test-month average trade."""
    home = RUNS / store
    z = np.load(home / "oos-rand.npz")
    box = LB.load_unit("oos", home)
    x = LB.unit_cell(box, 0)
    codes = None if group_sessions is None else [LB.SESS_CODE[s] for s in group_sessions]
    k = np.ones(len(x["net"]), bool) if codes is None else np.isin(x["sess"], codes)
    if not k.any():
        return None
    mine, below, n = float(np.asarray(x["net"])[k].mean()), 0, 0
    seeds = sorted({int(f.split("|")[0][1:]) for f in z.files})
    for sd in seeds:
        net, sess, sdd = z[f"s{sd}|net"], z[f"s{sd}|sess"], z[f"s{sd}|side"]
        q = np.ones(len(net), bool) if codes is None else np.isin(sess, codes)
        if side is not None:
            q &= sdd == side
        if q.any():
            n += 1
            below += float(net[q].mean()) < mine
    return below / n if n else None


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    w = next((int(x.split("=")[1]) for x in sys.argv[1:] if x.startswith("--workers=")), 3)
    run(a[0], w)
