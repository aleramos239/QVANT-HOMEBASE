"""taught_wf.py -- THE 3:1 WALK-FORWARD OF A TAUGHT SHEET (the owner, 2026-10-19: "the 3:1 block walk-forward is OOS on every route, taught
lane and by-hand included"; CLAUDE.md). `bp.py taught wf <name>`.

The sheet's cells (the taught cell and its neighbours, as `taught run` stored them on the build days) are run once more on the test days
(2025-07-01 .. the last WHOLE month of the market's complete sessions), with the sheet's own random entries (the same seeds, exits and passes).
Build and test trades are joined per cell, and pipe_wf does the rest exactly as the pipeline's stage 6: blocks of 3 months pick, the next month
trades the pick (the middle cell that holds: average trade above $0, 15+ trades, P3.15 -- never the best), the next block starts after it;
the stitched test months are judged by P6.1-P6.4.

THE ORDER: refusals first (no full result, a store written by other code -- the centre cell is run again on the build days and must give the
same trades and net, as `taught lab` checks); then the CLAIM is written (wf/claim.json: who, when, the days, the cells, the code) BEFORE any
test day is opened; a sheet whose walk-forward is on file is shown, never run again (those months are no longer blind for that rule).
Nothing is tuned here: the cells and their settings are the sheet's own."""
from __future__ import annotations

import datetime as dt
import json

import numpy as np

import judge as J
import l2sim as S
import library as LB
import run_idea as RI

from . import api
from . import pipe_gates as G
from . import pipe_rules as PR
from . import pipe_wf as WF
from . import runner as RUN
from . import tables as T
from . import taught as TA

WF_ = "taught wf"


def _arrays(trades: list) -> dict:
    x = LB.pack(trades)
    return {k: np.asarray(x[k]) for k in WF.FIELDS}


def _pool(per_seed: dict):
    """judge.pool_arrays' shape -- (date, net, slot code, cumulative net) -- from raw arrays per seed (the test days have no store)."""
    D, N, C = [], [], []
    for sd in sorted(per_seed):
        x = per_seed[sd]
        o = np.lexsort((x["entry_ms"], x["date"]))
        d, n = x["date"][o].astype(np.int64), x["net"][o].astype(np.float64)
        first = np.r_[True, d[1:] != d[:-1]] if len(d) else np.zeros(0, bool)
        rank = np.arange(len(d)) - np.maximum.accumulate(np.where(first, np.arange(len(d)), 0)) if len(d) else np.zeros(0, np.int64)
        D.append(d)
        N.append(n)
        C.append(d * 4096 + rank + (sd << 40))
    d, n, c = (np.concatenate(v) if v else np.zeros(0) for v in (D, N, C))
    o = np.argsort(d, kind="stable")
    return d[o].astype(np.int64), n[o], c[o].astype(J.U64), np.r_[0.0, np.cumsum(n[o])]


def _test_days(market: str, today: dt.date) -> list:
    rng = RUN.test_range(market)
    cal = [d.isoformat() for d in S.sessions(S._date(rng["start"]), S._date(rng["end"]), market, allow_holdout=S.ALLOW_BT)]
    return [d for d in cal if d[:7] < today.isoformat()[:7]]       # whole months only: the month under way is not a test month


def _run_cells(cls, cells: list, sessions: list, *a, **kw) -> list:
    """run_many of whole cells, one instance per session pass as `taught run` stored them (run_idea.cell_specs): one merged result a cell."""
    specs, cut = [], [0]
    for inp in cells:
        specs += RI.cell_specs({"spec": (cls, inp)}, sessions)
        cut.append(len(specs))
    res = S.run_many(specs, *a, **kw)
    return [{"trades": [t for r in res[i:j] for t in r["trades"]], "skipped_by_error": sum(r["skipped_by_error"] for r in res[i:j])}
            for i, j in zip(cut, cut[1:])]


def _save_test(base, test: dict) -> None:
    np.savez(base / "wf" / "test_cells.npz", **{f"{c}|{k}": v for c, x in test.items() for k, v in x.items()})


def each(name: str, root=None, workers=None) -> dict:
    """`bp.py taught wf-each <name>`: EVERY CELL ALONE on the walk-forward's own test months (the owner, 2026-10-19: "just run each variant
    individually"): no pick between cells. Two reads a cell: `always` = the cell in every test month of the blocks; `own` = pipe_wf's walk with
    that cell as the only box (a month whose pick months it fails stands aside). Needs the sheet's claimed read (wf/claim.json, same code); the
    test-day trades are the read's own (wf/test_cells.npz), run again under that claim only when an older read did not keep them."""
    base = TA.where(root) / str(name)
    claim, res_f = base / "wf" / "claim.json", base / "wf" / "result.json"
    if not (claim.exists() and res_f.exists()):
        raise J.Refuse(f"{name}: no walk-forward on file: bp.py taught wf {name} first")
    cl, wf = json.loads(claim.read_text()), json.loads(res_f.read_text())
    plan = json.loads((base / "result.json").read_text())["plan"]
    if cl["code"] != TA._code(plan["family"]):
        raise J.Refuse(f"{name}: the code changed since the claimed read ({cl['utc']}): the cells cannot be read again as that read")
    tf, market = plan["bars"][0], plan["market"]
    ukey = TA._unit_key(name, market, tf)
    st, _ = T._open(base / "runs", ukey)
    u, ids = TA._unit_row(plan, tf), cl["cells"]
    f = base / "wf" / "test_cells.npz"
    if not f.exists():
        umeta = json.loads((base / "runs" / ukey / "run.json").read_text())
        ins = {c["id"]: c["inputs"] for c in umeta["cells"]}
        days = [d for d in _test_days(market, dt.date.fromisoformat(cl["utc"][:10])) if cl["days"][0] <= d <= cl["days"][1]]
        RUN.may_start()
        n = max(1, min(int(workers or 6), S.MAX_WORKERS))
        res = _run_cells(TA._blocks().WRAPPED[umeta["family"]], [ins[c] for c in ids], plan["sessions"], S._date(days[0]), S._date(days[-1]), days=days, root=market, workers=n,
                         allow_holdout=S.ALLOW_BT, **RUN._engine(RUN._kw(umeta["family"], umeta.get("filter"))))
        if any(r["skipped_by_error"] for r in res):
            raise J.Refuse(f"{name}: sessions of the test days were dropped by a strategy error")
        _save_test(base, {c: _arrays(r["trades"]) for c, r in zip(ids, res)})
    z = np.load(f)
    first, w = cl["days"][0][:7], PR.need("walkforward")
    tested = [q["month"] for q in wf["months"]]
    cal = sorted({*T.build_days(u, None), *[d for d in _test_days(market, dt.date.fromisoformat(cl["utc"][:10])) if cl["days"][0] <= d <= cl["days"][1]]})
    rows, lines = [], [f"{name}: every cell alone on the {len(tested)} block test months ({tested[0]} .. {tested[-1]}); test days {cl['days'][0]} .. {cl['days'][1]}"]
    for c in ids:
        b = {k: np.asarray(v) for k, v in J.cellx(st, c, None, u).items() if k in WF.FIELDS}
        x = {k: np.concatenate([b[k], z[f"{c}|{k}"]]) for k in WF.FIELDS}
        x["month"] = WF._month(x["date"])
        own = WF.walk({c: x}, J.table(st, {**u, "sess": "all"}), WF.months(cal), w["select_months"], w["window_trades"], cl["utc"][:10], w["step_months"])
        row = {"cell": c}
        for kind, ms in (("always", tested), ("own", [p["month"] for p in own["picks"] if p["cell"]])):
            m = np.isin(x["month"], ms)
            y = {k: x[k][m] for k in WF.FIELDS}
            met = TA._metrics(y, LB._ordinals([d for d in cal if d[:7] in set(ms)]))
            late = WF._month(y["date"]) >= first if len(y["date"]) else np.zeros(0, bool)
            row[kind] = {**met, "months": len(ms), "unseen_net": float(y["net"][late].sum()), "unseen_trades": int(late.sum()), "p63": G.wr_rr(y["net"])["passed"]}
            lines.append(f"  {c:16} {kind:6} {len(ms):2} months  {met['trades']:3} trades  net ${met['net']:,.0f}  avg ${met['avg_trade'] or 0:,.0f}  "
                         f"win {100 * (met['win'] or 0):.1f} %  PF {met['pf'] or 0:.2f}  DD ${met['max_dd'] or 0:,.0f}  unseen ${row[kind]['unseen_net']:,.0f} "
                         f"({row[kind]['unseen_trades']})")
        rows.append(row)
    doc = {"name": name, "cells": rows, "text": "\n".join(lines)}
    TA._write(base / "wf" / "each.json", doc)
    return api.result(WF_, name, status="done", result=doc, text=doc["text"], saved=[str(base / "wf" / "each.json")])


def run(name: str, root=None, workers=None, who: str = "owner in chat") -> dict:
    base = TA.where(root) / str(name)
    out = base / "wf" / "result.json"
    if out.exists():
        doc = json.loads(out.read_text())
        return api.result(WF_, name, status="on file", result=doc, text=doc["text"])
    f = base / "result.json"
    if not f.exists():
        raise J.Refuse(f"{name}: no full result under {base.parent}: bp.py taught run <sheet> first")
    plan = json.loads(f.read_text())["plan"]
    if len(plan["bars"]) != 1:
        raise J.Refuse(f"{name}: {len(plan['bars'])} bar sizes; the walk-forward reads one (write a sheet per bar size)")
    tf, market, blocks = plan["bars"][0], plan["market"], TA._blocks()
    ukey, ckey = TA._unit_key(name, market, tf), TA._ctl_key(name, market, tf, "both")
    st, _ = T._open(base / "runs", ukey)
    umeta = json.loads((base / "runs" / ukey / "run.json").read_text())
    cmeta = json.loads((base / "runs" / ckey / "run.json").read_text())
    ids = [c["id"] for c in plan["cells"]]
    centre = next(c["id"] for c in plan["cells"] if c.get("centre"))
    u = TA._unit_row(plan, tf)
    build = {c: {k: np.asarray(v) for k, v in J.cellx(st, c, None, u).items() if k in WF.FIELDS} for c in ids}
    cls, ins = blocks.WRAPPED[umeta["family"]], {c["id"]: c["inputs"] for c in umeta["cells"]}
    ueng = RUN._engine(RUN._kw(umeta["family"], umeta.get("filter")))
    n = max(1, min(int(workers or 6), S.MAX_WORKERS))
    RUN.may_start()
    # ---- the code is the code of the store: the centre cell again on the build days (taught lab's check)
    bdays = [d.isoformat() for d in S.sessions(*S.period(RUN.PERIOD), market, allow_holdout=RUN.PERIOD)]
    again = _run_cells(cls, [ins[centre]], plan["sessions"], period=RUN.PERIOD, days=bdays, root=market, workers=n, **ueng)[0]
    got, want = _arrays(again["trades"]), build[centre]
    if again["skipped_by_error"] or len(got["net"]) != len(want["net"]) or abs(float(got["net"].sum() - want["net"].sum())) >= 0.01:
        raise J.Refuse(f"{name} {centre}: run again on the build days it has {len(got['net']):,} trades and ${got['net'].sum():,.0f} where its store has "
                       f"{len(want['net']):,} and ${want['net'].sum():,.0f}: the code changed since `taught run`; run the sheet again under a new name")
    # ---- THE CLAIM, before any test day is opened
    today = RUN.clock().date()
    days = _test_days(market, today)
    if not days:
        raise J.Refuse(f"{market}: no whole test month on disk yet")
    TA._write(base / "wf" / "claim.json", {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "who": who, "days": [days[0], days[-1]],
                                           "cells": ids, "code": TA._code(plan["family"])})
    a, b = S._date(days[0]), S._date(days[-1])
    res = _run_cells(cls, [ins[c] for c in ids], plan["sessions"], a, b, days=days, root=market, workers=n, allow_holdout=S.ALLOW_BT, **ueng)
    if any(r["skipped_by_error"] for r in res):
        raise J.Refuse(f"{name}: sessions of the test days were dropped by a strategy error: nothing is judged (the claim stays on file)")
    test = {c: _arrays(r["trades"]) for c, r in zip(ids, res)}
    _save_test(base, test)
    seeds = sorted({c["inputs"]["seed"] for c in cmeta["cells"]})
    rspecs = [(c["id"], {**c["inputs"], "sess": s}) for c in cmeta["cells"] for s in plan["sessions"]]     # one instance a pass, as the store's runs
    import l2ref
    rres = S.run_many([(l2ref.Random, i) for _, i in rspecs], a, b, days=days, root=market, workers=n, allow_holdout=S.ALLOW_BT, **RUN._engine({}))
    tpool: dict = {}
    for (cid, i), r in zip(rspecs, rres):
        tpool.setdefault(cid.split("_", 1)[1], {}).setdefault(i["seed"], []).extend(r["trades"])
    tpool = {xid: {sd: _arrays(sorted(t, key=lambda q: q["entry_ms"])) for sd, t in by.items()} for xid, by in tpool.items()}
    # ---- the walk-forward, pipe_wf's own
    boxes = {c: {k: np.concatenate([build[c][k], test[c][k]]) for k in WF.FIELDS} for c in ids}
    for x in boxes.values():
        x["month"] = WF._month(x["date"])
    cal = sorted({*T.build_days(u, None), *days})
    w = PR.need("walkforward")
    walk = WF.walk(boxes, J.table(st, {**u, "sess": "all"}), WF.months(cal), w["select_months"], w["window_trades"], today.isoformat(), w["step_months"])
    x = WF.stitch(boxes, walk["picks"])
    bpool = T.pool_seeds(base / "runs", ckey, ids, len(seeds))
    first, cache = days[0][:7], {}

    def pool(xid, month):
        side = "test" if month >= first else "build"
        if (xid, side) not in cache:
            cache[(xid, side)] = _pool(tpool[xid]) if side == "test" else J.pool_arrays(bpool, None, xid)
        return cache[(xid, side)]

    beat = WF.against_random(boxes, walk["picks"], pool, J.block_seeds(J.seed_of(f"taught|{name}", "wf")), J.RULE["draws"], float(np.sum(x["net"])),
                             min(len(bpool), len(seeds)))
    rows = WF.rows(x, beat, PR.need("variant", "region_trades"))
    late = WF._month(x["date"]) >= first if len(x["date"]) else np.zeros(0, bool)
    m = TA._metrics(x, LB._ordinals([d for d in cal if d[:7] in {p["month"] for p in walk["picks"]}]))
    months = [{"month": p["month"], "cell": p["cell"], "trades": int((boxes[p["cell"]]["month"] == p["month"]).sum()) if p["cell"] else 0,
               "net": float(boxes[p["cell"]]["net"][boxes[p["cell"]]["month"] == p["month"]].sum()) if p["cell"] else 0.0} for p in walk["picks"]]
    split = {k: {"net": float(x["net"][s].sum()), "trades": int(s.sum())} for k, s in (("build_days", ~late), ("test_days", late))}
    text = "\n".join([f"{name}: 3:1 walk-forward in blocks, {len(months)} test months ({months[0]['month']} .. {months[-1]['month']}), "
                      f"{sum(1 for q in months if q['cell'] is None)} stood aside; test days read {days[0]} .. {days[-1]}",
                      f"stitched: {m['trades']} trades, net ${m['net']:,.0f}, avg ${m['avg_trade'] or 0:,.0f}, win {100 * (m['win'] or 0):.1f} %, PF {m['pf'] or 0:.2f}, "
                      f"worst DD ${m['max_dd'] or 0:,.0f}; build-day months ${split['build_days']['net']:,.0f} ({split['build_days']['trades']}), "
                      f"test-day months ${split['test_days']['net']:,.0f} ({split['test_days']['trades']})"]
                     + [f"  {r['text']}" for r in rows]
                     + [f"  {q['month']}  {q['cell'] or 'stood aside':14} {q['trades']:3}  ${q['net']:,.0f}" for q in months]
                     + [f"next month ({walk['next']['month']}): {walk['next']['cell'] or 'stand aside'}"])
    doc = {"name": name, "days": [days[0], days[-1]], "months": months, "next": walk["next"], "metrics": m, "split": split, "random": {k: beat.get(k) for k in ("p_beat", "passed") if k in beat},
           "rows": rows, "passed": all(r["passed"] is True for r in rows), "code": TA._code(plan["family"]), "text": text,
           "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    TA._write(out, doc)
    return api.result(WF_, name, status="done", result=doc, text=text, saved=[str(out)])
