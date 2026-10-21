"""taught_wf.py -- THE 3:1 WALK-FORWARD OF A TAUGHT SHEET, IN BLOCKS, EVERY CELL FIXED (the owner, 2026-10-19: "the 3:1 block walk-forward is
OOS on every route, taught lane and by-hand included"; 2026-10-20: every box fixed, the owner picks, the test months only on his word).

    bp.py taught wf <name> --owner-said=TEXT        every cell of the sheet -- its OWN cells, as taught (the taught cell and its neighbours,
                                                    not hm40) -- run fixed on the in-sample months of the 3:1 blocks (wfmonths.is_days,
                                                    l2sim.ALLOW_WF_IS); then the in-sample table. No cell changes between blocks, no
                                                    code picks. A heat-map-like run: only on the owner's words.
    bp.py taught wf-show <name>                     the table, the pick, the test months if read (runs nothing)
    bp.py taught wf-pick <name> <box>               the owner's cell (row number or id) = the lock, written once (hmwf.pick)
    bp.py taught wf-oos <name> <box> --owner-said=TEXT   the picked cell on the test months of its blocks, once, on his words (hmwf.run_oos:
                                                    claimed in the one-read log before a day is opened)

The store: <taught root>/<name>/wf_blocks/<name>__taught-<ROOT>-tf<tf>/{is, is-<session>-worse, is-ctl, lock.json, oos} (a folder name no
hm40 idea has: the one-read log keys a read by it). Beside the cells, on the same in-sample days: the same cells with worse fills (one store a
session) and the sheet's own random entries (is-ctl: each cell is held against s<seed>_<its id>). The lock, the read and the table are
hmwf's own. The build days were read by `taught run` (every cell): the table says so (`seen`), its test months inside them are not blind.

A sheet whose OLD walk-forward (2026-10-19, wf/: the middle cell re-picked per block on the test days) is on file is shown, never run
again: its test months are already seen. `wf-each` reads that old walk-forward only."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

import judge as J
import l2sim as S
import library as LB

from . import api
from . import hmwf as H
from . import pipe_gates as G
from . import pipe_rules as PR
from . import pipe_wf as WF
from . import rules as R
from . import runner as RUN
from . import tables as T
from . import taught as TA
from . import wfmonths as WM

WF_ = "taught wf"


def _arrays(trades: list) -> dict:
    x = LB.pack(trades)
    return {k: np.asarray(x[k]) for k in WF.FIELDS}


def _test_days(market: str, today: dt.date) -> list:
    rng = RUN.test_range(market)
    cal = [d.isoformat() for d in S.sessions(S._date(rng["start"]), S._date(rng["end"]), market, allow_holdout=S.ALLOW_BT)]
    return [d for d in cal if d[:7] < today.isoformat()[:7]]       # whole months only: the month under way is not a test month


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
        raise J.Refuse(f"{name}: no old walk-forward on file (wf-each reads the walk-forward of 2026-10-19 only; the 3:1 table is taught wf-show)")
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
        res = S.run_many([(TA._blocks().WRAPPED[umeta["family"]], ins[c]) for c in ids], S._date(days[0]), S._date(days[-1]), days=days, root=market, workers=n,
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


def _sheet(name: str, root):
    base = TA.where(root) / str(name)
    f = base / "result.json"
    if not f.exists():
        raise J.Refuse(f"{name}: no full result under {base.parent}: bp.py taught run <sheet> first")
    plan = json.loads(f.read_text())["plan"]
    if len(plan["bars"]) != 1:
        raise J.Refuse(f"{name}: {len(plan['bars'])} bar sizes; the walk-forward reads one (write a sheet per bar size)")
    return base, plan


OLD_SHOWN = "This is the old walk-forward: its test months are already seen. A new 3:1 run is a new sheet name."


def home(name: str, root=None, have: bool = False) -> Path:
    """The folder of the sheet's 3:1 stores (have: refused when an old walk-forward is on file, or the in-sample run is not)."""
    base, plan = _sheet(name, root)
    h = base / "wf_blocks" / f"{name}__taught-{plan['market']}-tf{plan['bars'][0]}"
    if have and _old(base, name) is not None:
        raise J.Refuse(f"{name}: {OLD_SHOWN} (bp.py taught wf-show {name} shows it)")
    if have and not (h / H.IS / "run.json").exists():
        raise J.Refuse(f"{name}: no 3:1 in-sample run on file: bp.py taught wf {name} --owner-said=... first (only on the owner's words)")
    return h


def _old(base: Path, name: str):
    """The OLD walk-forward on file (its document), or None. A claim with no result = a read that stopped: its months are seen too."""
    f = base / "wf" / "result.json"
    if f.exists():
        return json.loads(f.read_text())
    if (base / "wf" / "claim.json").exists():
        raise J.Refuse(f"{name}: an old walk-forward of this sheet was claimed and stopped: its test months are already seen; a new 3:1 run "
                       "is a new sheet name")
    return None


def _built(base: Path):
    """The day `taught run` read every cell on the build days (its full result), or None."""
    doc = json.loads((base / "result.json").read_text())
    return None if doc.get("smoke") else str(doc.get("utc") or "")[:10] or "on file"


def show(name: str, root=None, command: str = "taught wf-show") -> dict:
    """The in-sample table, the pick, the test months if read (hmwf.show on the sheet's store). Runs nothing. An old walk-forward on file
    is shown as it is."""
    base, _ = _sheet(name, root)
    doc = _old(base, name)
    if doc is not None:
        return api.result(command, name, status="on file", result=doc, text=doc["text"] + "\n" + OLD_SHOWN)
    s = H.show(name, store=home(name, root, have=True))
    text, day = api._wf_text(name, s), _built(base)
    if day:                                         # the build days were read, all cells, by taught run: their months are not blind
        seen = f"build days read by taught run {day}"
        for x in s["is"] + ([s["oos"]["record"]] if s["oos"] and s["oos"].get("record") else []):
            x["seen"] = "; ".join(v for v in (x.get("seen"), seen) if v)
        b = R.template("ranges")["build"]
        text += (f"\nSEEN: taught run read every cell on the build days {b['start']} .. {b['end']} ({day}): the test months inside them "
                 "are not blind.")
    r = api.result(command, name, wf=s, text=text)
    r["next"] = (f"The owner picks a cell by its number: bp.py taught wf-pick {name} <n>." if s["lock"] is None else
                 f"The test months run only when the owner says so: bp.py taught wf-oos {name} {s['lock']['box']} --owner-said=\"...\"."
                 if s["oos"] is None else "")
    return r


def _parts(base: Path, plan: dict, h: Path, days: list) -> list:
    """The in-sample stores: every cell of the sheet; the same cells with worse fills, one store a session; the sheet's own random
    entries (its control: the same exit cells and passes; a structure stop takes the median stop size of the build-day store)."""
    name, market, tf = plan["name"], plan["market"], plan["bars"][0]
    span = f"the 3:1 in-sample months ({days[0]} .. {days[-1]})"
    u = TA._unit_part(plan, tf)
    out = [{**u, "key": f"{h.name}/{H.IS}", "stage": H.STAGE, "meta": {**u["meta"], "root": market, "plan": plan, "wf": H.IS,
                                                                       "note": f"taught rule {name}: every cell of the sheet on {span}"}}]
    two = bool(TA._blocks().BASES[plan["family"]][2])
    for ss in plan["sessions"]:
        meta = {**out[0]["meta"], "sessions": [ss], "sess_instance": ss, "worse": RUN.worse_kw(two),
                "note": f"taught rule {name}: session {ss} with worse fills ({RUN.worse_words(RUN.worse_kw(two))}) on {span}"}
        out.append({**RUN._part(f"{h.name}/{H.IS}-{ss}-worse", "worse", market, tf, u["grid"], [ss], None, meta, plan["family"],
                                {**RUN._kw(plan["family"]), **RUN.worse_kw(two)}), "stage": H.WORSE})
    stop = None
    if plan["struct"]:
        stop = TA._median_stop(T._open(base / "runs", TA._unit_key(name, market, tf))[0], plan)     # a size, as the build's control took it
    if stop or not plan["struct"]:
        c = TA._control_part(plan, tf, "both", stop)
        out.append({**c, "key": f"{h.name}/{H.IS}-ctl", "stage": H.POOL, "meta": {**c["meta"], "root": market, "note": c["meta"]["note"] + f", on {span}"}})
    return out


def run(name: str, root=None, workers=None, owner_said=None, *, progress=None) -> dict:
    """`bp.py taught wf <name> --owner-said=...`: every cell of the sheet fixed on the 3:1 in-sample months (module docstring), with its
    worse fills and its own random entries, then the table. A rerun does no work (the runner's fingerprint); an old walk-forward on file
    is shown instead."""
    base, plan = _sheet(name, root)
    if _old(base, name) is not None:
        return show(name, root, WF_)
    said = api._said(owner_said)
    days = WM.is_days(plan["market"])
    if not days:
        raise J.Refuse(f"{plan['market']}: no in-sample month of the 3:1 blocks yet")
    h = home(name, root)
    todo = _parts(base, plan, h, days)
    h.mkdir(parents=True, exist_ok=True)            # (the runner's lock files sit beside each store)
    rows = RUN._run(todo, workers, h.parent, base / "ledger.csv", days, None, progress, None, False, f"taught {name}, 3:1 in-sample", S.ALLOW_WF_IS)
    bad = [r for r in rows if r.get("ok") is False]
    if bad:
        raise J.Refuse(f"{bad[0]['key']}: sessions were dropped by a strategy error ({bad[0].get('error')}): no store was written")
    return {**show(name, root, WF_), "owner_said": said}


def pick(name: str, box, root=None, who: str = "owner") -> dict:
    """`bp.py taught wf-pick <name> <box>`: the owner's cell = the lock, written once (hmwf.pick)."""
    H.pick(name, box, who=who, store=home(name, root, have=True))
    return show(name, root, "taught wf-pick")


def oos(name: str, box, owner_said, root=None, workers=None, *, progress=None) -> dict:
    """`bp.py taught wf-oos <name> <box> --owner-said=...`: the picked cell on its test months, once, on the owner's words (hmwf.run_oos)."""
    said = api._said(owner_said)
    base, _ = _sheet(name, root)
    H.run_oos(name, box, said, workers, store=home(name, root, have=True), ledger=base / "ledger.csv", progress=progress)
    return {**show(name, root, "taught wf-oos"), "owner_said": said}
