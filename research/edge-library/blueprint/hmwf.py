"""hmwf.py -- EVERY BOX OF AN IDEA'S hm40 HEAT MAP, FIXED, ON THE IN-SAMPLE MONTHS OF THE 3:1 BLOCKS (the owner, 2026-10-20; spec
docs/superpowers/specs/2026-10-20-heatmap-40-and-fixed-box-walkforward-design.md 4.2-4.4, 4.7).

A box = one value of the idea's main setting x one hm40 exit cell (its id in the store: <value>_<cell id>). Every box is run ONCE on
the in-sample days of the blocks (wfmonths.is_days), under the engine's in-sample switch (l2sim.ALLOW_WF_IS): the test months are not
run, not stored and not shown here. The owner picks the box from the in-sample table; no code picks for him.

    run_is(spec, workers)    the idea's stores, by blueprint/runner.py's own runner (fingerprint: a rerun does no work, a changed
                             idea under the same name is refused):
        runs_wf/<name>-<ROOT>-tf<tf>/is/                every box (the unit: 120 cells, or 60 for a family with no stop of its own)
        runs_wf/<name>-<ROOT>-tf<tf>/is-<sess>-worse/   the same boxes with worse fills (runner.worse_part), one store a session
        runs_wf/c1h-<ROOT>-tf<tf>/is-<last month>/      the random-entry pool: 10 seeds x hm40's 20 ATR cells, all sessions
    is_table(name)           one row a box, sorted by win rate (the owner's pick list)
    block_rows(name, box)    one row a block: its 3 in-sample months
    numbers(x, days)         the numbers of one record (packed trades, the session days they were run on)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_idea as RI

from . import api
from . import rules as R
from . import runner as RUN
from . import wfmonths as WM

RUNS = RUN.RUNS_WF
IS = "is"
STAGE, WORSE, POOL = "wf_is", "wf_is_worse", "null_wf_is"      # the ledger stages (a pool's: not capped)


# ================================================================ the run

def _spec(spec) -> dict:
    if isinstance(spec, (str, Path)):
        try:
            spec = json.loads(Path(spec).read_text())
        except (OSError, ValueError) as e:
            raise J.Refuse(f"spec file {spec}: {e}") from None
    if not isinstance(spec, dict):
        raise J.Refuse("a spec is a JSON object")
    spec = {k: v for k, v in spec.items() if k != "variants"}      # (checked again, on hm40)
    sp = RUN.checked({**spec, "exits": RUN.HM40, "filter_exits": RUN.HM40})
    blocks = RUN._blocks()
    if any(blocks.reads(f, blocks.L2_BLOCKS) for f in sp["filters"]):
        raise J.Refuse(f"{sp['name']}: Level 2 is not open on the 3:1 months yet")
    if sp["filters"]:
        raise J.Refuse(f"{sp['name']}: a filter is not run on the 3:1 months yet: run the idea without it")
    if len(sp["markets"]) != 1 or len(sp["bar_sizes"]) != 1:
        raise J.Refuse(f"{sp['name']}: one market and one bar size a run (one spec each, as an idea's record holds them)")
    return sp


def run_is(spec, workers=None, *, ledger=None, progress=None, block=None) -> dict:
    """Every box of the idea on the in-sample months (module docstring) -> {"store": its path, "boxes": n, "rows": the runner's rows}."""
    import l2ref
    sp = _spec(spec)
    root, tf = sp["markets"][0], sp["bar_sizes"][0]
    days = WM.is_days(root)
    if not days:
        raise J.Refuse(f"{root}: no in-sample month of the 3:1 blocks yet")
    u = RI.spec_units(sp)[0]
    home = f"{u['key']}/{IS}"
    note = f"idea {sp['name']}: every hm40 box on the 3:1 in-sample months ({days[0]} .. {days[-1]})"
    todo = [{**RUN._part(home, "unit", root, tf, u["grid"], sp["sessions"], None, {**RI.unit_meta(sp, u), "wf": IS, "note": note},
                         sp["family"], RUN._kw(sp["family"])), "stage": STAGE}]
    todo += [{**RUN.worse_part(sp, u["key"], s), "key": f"{u['key']}/{IS}-{s}-worse", "stage": WORSE} for s in sp["sessions"]]
    if str(tf) in l2ref.Random.SCREEN_TFS and root in S.MENU_STOP_PTS:
        p = RUN.pool_part(root, tf, None, RUN.HM40)
        p["meta"]["note"] = f"10-seed random-entry pool on hm40's ATR cells, the 3:1 in-sample months {days[0]} .. {days[-1]}, all sessions"
        todo.append({**p, "key": f"{p['key']}/{IS}-{days[-1][:7]}", "stage": POOL})      # a new pool when the months grow
    for p in todo:
        (RUNS / p["key"]).parent.mkdir(parents=True, exist_ok=True)    # (the runner's lock files sit beside each store)
    rows = RUN._run(todo, workers, RUNS, ledger, days, None, progress, block, False, f"idea {sp['name']}, 3:1 in-sample", S.ALLOW_WF_IS)
    bad = [r for r in rows if r.get("ok") is False]
    if bad:
        raise J.Refuse(f"{bad[0]['key']}: sessions were dropped by a strategy error ({bad[0].get('error')}): no store was written")
    return {"store": str(RUNS / home), "boxes": todo[0]["cells"], "rows": rows}


# ================================================================ the numbers

def _month(x) -> np.ndarray:
    return np.array([dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in x["date"]], dtype=object)


def numbers(x: dict, days) -> dict:
    """One record's numbers at 1 contract after costs (spec 4.3). Sharpe and max drawdown: library.metrics (daily, $0 days counted,
    x sqrt 252). Month win rates: the months with 3 trades or more (pipe_stages' month_wr rule: a 1-trade month says nothing)."""
    m, net = LB.metrics(x, days), np.asarray(x["net"], np.float64)
    win = net > 0
    aw = float(net[win].mean()) if win.any() else None
    al = float(-net[~win].mean()) if (~win).any() else None
    be = 1 / (1 + aw / al) if aw and al else None
    mo, wr = _month(x), []
    pos = [float(net[mo == k].sum()) > 0 for k in sorted(set(mo))]
    for k in sorted(set(mo)):
        t = net[mo == k]
        if len(t) >= 3:
            wr.append(float((t > 0).mean()))
    side = np.asarray(x["side"])
    return {"win_rate": m["win"], "breakeven": be, "wr_minus_be": None if be is None or m["win"] is None else m["win"] - be,
            "trades": m["trades"], "per_week": m["trades"] / (len(days) / 5) if days else None, "avg_trade": m["avg_trade"],
            "avg_r": m["avg_trade"] / al if m["avg_trade"] is not None and al else None,     # R = the average loss (pipe_stages' avg_r)
            "net": m["net"], "pf": m["pf"], "sharpe": m["sharpe"], "max_dd": m["max_dd"],
            "months_pos": sum(pos) / len(pos) if pos else None, "months_wr60": sum(w >= 0.6 for w in wr) / len(wr) if wr else None,
            "worst_month_wr": min(wr) if wr else None, "long_net": round(float(net[side > 0].sum()), 2), "short_net": round(float(net[side < 0].sum()), 2)}


def store(name: str) -> Path:
    """The folder of an idea's 3:1 stores: by its store name (<name>-<ROOT>-tf<tf>), or by the idea's name when it has one."""
    if (RUNS / name / IS / "run.json").exists():
        return RUNS / name
    hits = sorted(p.parent.parent for p in RUNS.glob(f"{name}-*-tf*/{IS}/run.json"))
    if len(hits) != 1:
        raise J.Refuse(f"{name}: " + (f"{len(hits)} stores ({', '.join(p.name for p in hits)}): name one" if hits else "no 3:1 in-sample run on file (hmwf.run_is)"))
    return hits[0]


def _seen(name: str):
    """The months of this idea someone has already seen: tuned on the build days (a runs_bp store) and / or the test days read once."""
    b, out = R.template("ranges")["build"], []
    if any(RUN.RUNS.glob(f"{name}-*")) or any(RUN.RUNS.glob(f"{name}__*")):
        out.append(f"build days {b['start'][:7]}..{b['end'][:7]} tuned")
    line = api.ideastore().read_on_file(name)
    if line:
        out.append(f"test days read {str(line.get('utc'))[:10]}")
    return "; ".join(out) or None


def _beats(x: dict, cell: dict, pool, sess) -> float | None:
    """The share of the pool's seeds (the ATR cell of the box's multiplier and target, the box's sessions) whose average trade is below the box's."""
    if pool is None or not len(x["net"]):
        return None
    ex = {"stop_mode": "atr", "stop_val": cell["exit"]["stop_val"], "tgt_r": cell["exit"]["tgt_r"]}
    mine, avg = float(np.mean(x["net"])), []
    for i, c in enumerate(pool["meta"]["cells"]):
        if c["exit"] == ex:
            y = LB.unit_cell(pool, i)
            t = y["net"][np.isin(y["sess"], sess)]
            if len(t):
                avg.append(float(t.mean()))
    return sum(a < mine for a in avg) / len(avg) if avg else None


def _load(home: Path):
    u = LB.load_unit(IS, home)
    m = u["meta"]
    RUN.guard_wf(m, f"{home.name}/{IS}")
    return u, m


def is_table(name: str) -> list:
    """THE IN-SAMPLE TABLE: one row a box (module docstring), sorted by win rate, best first (no win rate: last)."""
    home = store(name)
    u, m = _load(home)
    days, root, tf = m["days"], m["root"], m["tf"]
    worse = {}
    for s in m["sessions"]:
        d = home / f"{IS}-{s}-worse"
        if (d / "cells.npz").exists():
            w = LB.load_unit(d.name, home)
            RUN.guard_wf(w["meta"], f"{home.name}/{d.name}")
            for i, c in enumerate(w["meta"]["cells"]):
                worse[c["id"]] = worse.get(c["id"], 0.0) + float(LB.unit_cell(w, i)["net"].sum())
    pd = RUNS / RUN.pool_key(root, tf, RUN.HM40) / f"{IS}-{days[-1][:7]}"
    pool = LB.load_unit(pd.name, pd.parent) if (pd / "cells.npz").exists() else None
    if pool is not None:
        RUN.guard_wf(pool["meta"], f"{pd.parent.name}/{pd.name}")
    sess, seen, rows = [LB.SESS7.index(s) for s in m["sessions"]], _seen(m["idea"]), []
    for i, c in enumerate(m["cells"]):
        x = LB.unit_cell(u, i)
        rows.append({"box": c["id"], "settings": {**c["variant"], **c["exit"]}, **numbers(x, days),
                     "worse_fills_net": round(worse[c["id"]], 2) if c["id"] in worse else None, "beats_random": _beats(x, c, pool, sess), "seen": seen})
    rows.sort(key=lambda r: (r["win_rate"] is None, -(r["win_rate"] or 0.0)))
    return [{"n": n, **r} for n, r in enumerate(rows, 1)]


def block_rows(name: str, box: str) -> list:
    """One row a block of the box's in-sample record: {i, is (its 3 months), is_trades, is_win_rate, is_net}. No test month is named."""
    home = store(name)
    u, m = _load(home)
    i = next((k for k, c in enumerate(m["cells"]) if c["id"] == box), None)
    if i is None:
        raise J.Refuse(f"{box}: not a box of {home.name}")
    x, have = LB.unit_cell(u, i), {d[:7] for d in m["days"]}
    mo, net, out = _month(LB.unit_cell(u, i)), np.asarray(x["net"], np.float64), []
    for b in WM.blocks(m["root"]):
        if set(b["is"]) <= have:
            t = net[np.isin(mo, b["is"])]
            out.append({"i": b["i"], "is": b["is"], "is_trades": len(t), "is_win_rate": float((t > 0).mean()) if len(t) else None,
                        "is_net": round(float(t.sum()), 2)})
    return out
