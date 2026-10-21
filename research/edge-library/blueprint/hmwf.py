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

THE OWNER'S PICK AND THE OUT-OF-SAMPLE READ (spec 4.4, 4.7; the owner: "run them when i say"). `box` = its row number n in the
in-sample table, or its id; `store` = the folder of the 3:1 stores (default: the idea's, under runs_wf/).
    pick(name, box, who)     THE LOCK: <store>/lock.json {box, settings, code, at, who}, written once; another box is refused (a new pick
                             is a new idea name)
    run_oos(name, box, owner_said)   only the picked box, only on the owner's words, once: the claim goes to the one-read log
                             (reads.claim_wf_oos) BEFORE a day is opened; then the box runs on every test month of its blocks, one month
                             a call (l2sim.ALLOW_WF_OOS), into <store>/oos/ (that box's test-month trades and nothing else)
    show(name)               the in-sample table, the lock if any, the out-of-sample record if it was read
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_idea as RI

from . import api
from . import reads as RD
from . import rules as R
from . import runner as RUN
from . import wfmonths as WM

RUNS = RUN.RUNS_WF
IS, OOS, LOCK = "is", "oos", "lock.json"
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
    line = next((r for r in reversed(api.ideastore().reads()) if r.get("name") == name and r.get("kind") != RD.WF_OOS), None)   # (a 3:1 read is not one)
    if line:
        out.append(f"test days read {str(line.get('utc'))[:10]}")
    return "; ".join(out) or None


def _beats(x: dict, cell: dict, pool, sess) -> tuple:
    """(the share of the pool's seeds -- the ATR cell of the box's multiplier and target, the box's sessions -- whose average trade is
    below the box's, the id of that ATR cell): an own-stop box is compared with the ATR cell of its own multiplier."""
    ex = {"stop_mode": "atr", "stop_val": cell["exit"]["stop_val"], "tgt_r": cell["exit"]["tgt_r"]}
    if pool is None or not len(x["net"]) or cell["exit"]["stop_mode"] not in ("atr", "own"):     # (a taught sheet's points stop: not hm40's pool)
        return None, None
    mine, avg = float(np.mean(x["net"])), []
    for i, c in enumerate(pool["meta"]["cells"]):
        if c["exit"] == ex:
            y = LB.unit_cell(pool, i)
            t = y["net"][np.isin(y["sess"], sess)]
            if len(t):
                avg.append(float(t.mean()))
    return (sum(a < mine for a in avg) / len(avg), S.cell_id(ex)) if avg else (None, None)


def _load(home: Path, sub: str = IS, period: str = S.ALLOW_WF_IS):
    u = LB.load_unit(sub, home)
    m = u["meta"]
    RUN.guard_wf(m, f"{home.name}/{sub}", period)
    return u, m


def _home(name: str, at) -> Path:
    return Path(at) if at is not None else store(name)


def is_table(name: str, store=None) -> list:
    """THE IN-SAMPLE TABLE: one row a box (module docstring), sorted by win rate, best first (no win rate: last)."""
    home = _home(name, store)
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
        beats, vs = _beats(x, c, pool, sess)
        rows.append({"box": c["id"], "settings": {**c["variant"], **c["exit"]}, **numbers(x, days),
                     "worse_fills_net": round(worse[c["id"]], 2) if c["id"] in worse else None, "beats_random": beats, "random_vs": vs, "seen": seen})
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


# ================================================================ the owner's pick (the lock) and the out-of-sample read

def _row(name: str, home: Path, box) -> dict:
    """The in-sample row of a box: by its row number n (an int, or digits) or by its id."""
    rows = is_table(name, home)
    by_n = isinstance(box, int) and not isinstance(box, bool) or isinstance(box, str) and box.isdigit()
    hit = next((r for r in rows if (r["n"] == int(box) if by_n else r["box"] == box)), None)
    if hit is None:
        raise J.Refuse(f"{box!r}: not a box of {home.name} (a row number 1..{len(rows)} of its in-sample table, or a box id)")
    return hit


def _lock(home: Path):
    f = home / LOCK
    return json.loads(f.read_text()) if f.exists() else None


def pick(name: str, box, who: str = "owner", store=None) -> dict:
    """THE OWNER'S PICK = THE LOCK (module docstring): written once, before any test month is read. The same box again: the lock on file."""
    home = _home(name, store)
    r, m = _row(name, home, box), _load(home)[1]
    _grid(m, home)                                  # a changed idea is refused before a lock is written for good
    lock = {"box": r["box"], "settings": r["settings"], "code": RUN.code(m["family"]),
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "who": who}
    fd, tmp = tempfile.mkstemp(dir=home, prefix=f".{LOCK}.")
    tmp = Path(tmp)
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(lock, indent=1))
    try:
        os.link(tmp, home / LOCK)                   # one step, and never over a lock on file (two picks at once: one wins)
    except FileExistsError:
        was = _lock(home)
        if was.get("box") != r["box"]:
            raise J.Refuse(f"{home.name}: box {was.get('box')} is picked already ({was.get('at')}, {was.get('who')}): a new pick is a new idea name") from None
        return was
    finally:
        tmp.unlink()
    return lock


def _grid(m: dict, home: Path) -> list:
    """The in-sample store's grid, rebuilt from its run.json -- and proved the same by the store's own fingerprint."""
    root, tf = m["root"], m["tf"]
    if m.get("taught"):                             # a taught sheet's own cells (blueprint/taught_wf.py), from the plan in its store
        from . import taught as TA
        grid = TA._unit_part(m["plan"], tf)["grid"]
    else:
        sp = {"name": m["idea"], "family": m["family"], "markets": [root], "bar_sizes": [tf], "filters": [], "exits": m["exits"],
              "filter_exits": m["exits"], "fixed": m["fixed"], "limits": m["limits"], "variants": m["variants"]}
        grid = RI.spec_units(sp)[0]["grid"]
    p = RUN._part(f"{home.name}/{IS}", "unit", root, tf, grid, m["sessions"], None, m, m["family"], RUN._kw(m["family"]))
    if RUN.fingerprint(p, m["days"], S.ALLOW_WF_IS) != m.get("inputs_hash"):
        raise J.Refuse(f"{home.name}: the idea's table is not the one its in-sample store was run from (the code or the settings changed): "
                       "the box is not run on its test months")
    return grid


USED = "read used, no record (it stopped)"


def _stopped(home: Path, box: str) -> str:
    return f"the test months of box {box} of {home.name} are used: this read stopped and is not run again"


def _oos(home: Path, rows: list):
    """The out-of-sample record on file -> {"store", "record" (the in-sample table's columns), "blocks"}; a read that was claimed and
    stopped before its store was written -> {"state": USED, "claim": its line in the one-read log}; nothing read -> None."""
    if not (home / OOS / "cells.npz").exists():
        claim = RD.wf_oos_on_file(home.name, (_lock(home) or {}).get("box"))
        return {"state": USED, "claim": claim[-1]} if claim else None
    u, m = _load(home, OOS, S.ALLOW_WF_OOS)
    lock = _lock(home) or {}
    if [c["id"] for c in m["cells"]] != [lock.get("box")]:
        raise J.Refuse(f"{home.name}/{OOS} holds {[c['id'] for c in m['cells']]}, not the picked box {lock.get('box')}: it is not read")
    c, x, days = m["cells"][0], LB.unit_cell(u, 0), m["days"]
    n = next((r["n"] for r in rows if r["box"] == c["id"]), None)
    rec = {"n": n, "box": c["id"], "settings": {**c["variant"], **c["exit"]}, **numbers(x, days), "worse_fills_net": None, "beats_random": None,
           "random_vs": None, "seen": next((r["seen"] for r in rows if r["box"] == c["id"]), None)}
    mo, net, have = _month(x), np.asarray(x["net"], np.float64), {d[:7] for d in days}
    blocks = []
    for b in WM.blocks(m["root"]):
        if b["oos"] in have:
            t = net[mo == b["oos"]]
            blocks.append({"i": b["i"], "oos": b["oos"], "trades": len(t), "win_rate": float((t > 0).mean()) if len(t) else None,
                           "net": round(float(t.sum()), 2)})
    return {"store": str(home / OOS), "record": rec, "blocks": blocks}


def run_oos(name: str, box, owner_said: str, workers=None, store=None, *, who: str = "owner", ledger=None, progress=None, block=None) -> dict:
    """THE OUT-OF-SAMPLE READ of the picked box, on the owner's word, once (module docstring) -> what show() gives as "oos".
    THE ORDER: every refusal first (the runner's own included); then, with the store locked, the claim in the one-read log; only then a
    test day. Anything that stops the run after the claim is refused as a used read (its cause chained): it is not run again."""
    home = _home(name, store)
    lock = _lock(home)
    if lock is None:
        raise J.Refuse(f"{home.name}: no box is picked: the owner picks one first (pick), then says to run it")
    if not isinstance(owner_said, str) or not owner_said.strip():
        raise J.Refuse(f"{home.name}: the test months run only on the owner's word (owner_said is empty)")
    r = _row(name, home, box)
    if r["box"] != lock["box"]:
        raise J.Refuse(f"{r['box']}: the picked box of {home.name} is {lock['box']}: only the picked box is run")
    if (home / OOS).exists():
        raise J.Refuse(f"{home.name} box {r['box']}: its out-of-sample read is on file: it is shown (show), never run again")
    if RD.wf_oos_on_file(home.name, r["box"]):
        raise J.Refuse(_stopped(home, r["box"]) + " (show says so)")
    _, m = _load(home)
    have = {d[:7] for d in m["days"]}
    bl = [b for b in WM.blocks(m["root"]) if set(b["is"]) <= have]      # the blocks the box was picked on
    if not bl:
        raise J.Refuse(f"{home.name}: no block of its in-sample months has a test month yet")
    days = [d for b in bl for d in WM.oos_days(m["root"], b["oos"])]
    cell = next(c for c in _grid(m, home) if c["id"] == r["box"])
    note = f"idea {m['idea']}: the picked box {r['box']} on the 3:1 test months ({bl[0]['oos']} .. {bl[-1]['oos']}), on the owner's word"
    todo = [{**RUN._part(f"{home.name}/{OOS}", "unit", m["root"], m["tf"], [cell], m["sessions"], None, {**m, "wf": OOS, "box": r["box"], "note": note},
                         m["family"], RUN._kw(m["family"])), "stage": S.ALLOW_WF_OOS}]
    claimed = []

    def claim():
        claimed.append(RD.claim_wf_oos(m["idea"], home.name, r["box"], rng={"start": days[0], "end": days[-1]}, who=who, owner_said=owner_said,
                                       code=RUN.code(m["family"])))
    try:
        rows = RUN._run(todo, workers, home.parent, ledger, days, None, progress, block, False, f"idea {m['idea']}, 3:1 test months of box {r['box']}",
                        S.ALLOW_WF_OOS, before=claim)
    except Exception as e:
        if claimed:
            raise J.Refuse(f"{_stopped(home, r['box'])} ({type(e).__name__}: {e})") from e
        raise                                       # refused before the claim: the read is not used
    if rows[0].get("ok") is False:
        raise J.Refuse(f"{_stopped(home, r['box'])} (sessions were dropped by a strategy error: {rows[0].get('error')}; no store was written)")
    return _oos(home, is_table(name, home))


def show(name: str, store=None) -> dict:
    """The in-sample table, the lock if any, the out-of-sample record if it was read (never run here)."""
    home = _home(name, store)
    rows = is_table(name, home)
    return {"is": rows, "lock": _lock(home), "oos": _oos(home, rows)}
