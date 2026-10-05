#!/usr/bin/env python3
"""Edge-library tooling (EDGE_SPEC.md): the capped ledger, unit stores, plateau judging, the nulls, admission, member folders.

W = this directory (~/ramos-quant-homebase/research/edge-library). Engine: W/engine (l2sim.py = the offline tick sim).
numpy only: nothing here imports the old pilots (score.py does that, NQ only); every root (NQ / ES / GC) goes through here.

    ledger.csv           ONE file, HARD caps (EDGE_SPEC user rule 5): full strategy runs <= 2,000 . CANDIDATE grid cells <=
                         50,000 . walk-forwards <= 40. A menu grid of N cells counts N cells (failed batches included).
                         NULL / CONTROL cells (C1 pools, time-shuffle, C2) do NOT count toward the 50,000 (ORCHESTRATOR
                         DECISIONS 2026-10-03, 6): kind 'null', column `null_cells`, tracked separately (ledger_nulls).
    runs/<key>/          a unit's store, written by run_menus.py: run.json (range, period, cells, coverage), cells.npz (every
                         trade of every cell, compact), table.csv (cell x session: trades, net, t, ...)
    members/<name>/      an ADMITTED member: spec.json, trades_build.json, trades_pick.json (1 contract, tester schema),
                         daily.csv (date, period, net, worst_open_loss, minutes_in_market), card.md
    members/_rejected/<name>/   spec.json + card.md of a candidate that failed admission (the evidence is kept)

JUDGING (EDGE_SPEC "Variant menu" / "PROPER RE-RUN" 4 + 7 + "ORCHESTRATOR DECISIONS 2026-10-03" 2, 3, 7; never the best cell)
    plateau(table)       a unit (family x tf x session x root [x mirror value]) PASSES when, over its JUDGED (parameter x
                         exit) cells, the median net is > 0 after costs AND >= 60 % of them are > 0. JUDGED cells = all
                         cells, minus the structurally DEAD ones (they cannot trade: session_table marks a variant that has
                         no trade in the session in ANY of its exit cells), with cells of IDENTICAL trade lists counted
                         once (the first in (variant, exit) order stands for the group). The member is the CENTRAL cell =
                         the positive judged cell whose net is closest to the unit's MEDIAN net (by construction never
                         the best cell); ties -> the lowest (variant index, exit index).
                         The result also carries the share of cells > 0 overall, by stop type (fixed / ATR / percent) and
                         per reward ratio, each with its verdict at 60 %, 70 % and 80 % (the binding bar stays 60 %).
    plateau_units(u, s)  MIRROR families (opposite hypotheses on one axis: tod_drift dir, ib mode, gap mode) are judged as
                         SEPARATE units, one per value of the axis; every other family is one unit per session.
REPORTING (decision 7): metrics() / per_year() = trades, net, win rate, PF, max drawdown, Sharpe (daily, annualised), avg
    trade, worst open loss -- PER YEAR first (2021*, 2022, 2023; 2024 for PICK), then combined; sized() = the same trades
    sized to about $1,000 of risk per trade in micros.
    best_of_nulls(batch) the 95th percentile, over the batch's null replicates, of each replicate's BEST cell.
    admission(member)    every admission test of EDGE_SPEC "Library admission", fail closed (a missing input fails).

PERIODS: BUILD 2021-09-22..2023-12-31 . PICK 2024 . EXAM >= 2025-01-01 (sealed). run_member refuses a PICK run of a
candidate whose BUILD plateau did not pass (PICK is read only by the Admit stage, only for BUILD survivors).
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import fcntl
import json
import math
import sys
import zlib
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parent
ENGINE = W / "engine"
RUNS = W / "runs"
MEMBERS = W / "members"
LEDGER = W / "ledger.csv"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CAPS = {"runs": 2000, "cells": 80000, "wfs": 40}          # EDGE_SPEC user rule 5; cells 40,000 -> 50,000 by "STAGE 2b", -> 80,000 by "ADMISSION v2" part D (user): HARD
COLS = ("stage", "key", "kind", "family", "root", "tf", "period", "control", "seed", "runs", "cells", "null_cells", "wfs",
        "trades", "elapsed_s", "note", "finished_utc")
# what a row of each kind counts against; 'null' = a null / control grid: counted in `null_cells`, which has NO cap
KINDS = {"run": "runs", "grid": "cells", "null": "null_cells", "wf": "wfs", "smoke": None}
SESS7 = ("eve", "asia", "london", "pre", "nyam", "mid", "pm")
SESS_CODE = {s: i for i, s in enumerate(SESS7)}
REASONS = ("sl", "tp", "time", "eod", "trail", "bars", "book", "other")
PLATEAU_SHARE = 0.60
VERDICT_SHARES = (0.60, 0.70, 0.80)                        # decision 7: the pass verdict is shown at 60 %, 70 % and 80 %
STOP_TYPES = {"pts": "fixed", "atr": "ATR", "pct": "percent"}
RISK_USD = 1000.0                                          # decision 7: trades are also shown sized to about $1,000 of risk
COMM_RT = 4.00                                             # the engine's commission per round turn, 1 full contract (l2sim.Costs)
MIN_TRADES = 100
LOSS_LIMIT_USD = 2000.0                                    # the open loss a member must be sizeable inside (>= 1 micro)
MICRO_DIV = 10.0                                           # MNQ / MES / MGC = 1/10 of the full contract
MICRO_RT_USD = 1.00                                        # micro commission per round turn (the pilots' cost model)
WEAK_T = 3.0                                               # WEAK-rationale members: t >= 3 on BUILD
FIELDS = ("date", "entry_ms", "dur_s", "net", "mae", "side", "sess", "reason", "risk")
DTYPES = {"date": np.int32, "entry_ms": np.int64, "dur_s": np.int32, "net": np.float64, "mae": np.float32, "side": np.int8,
          "sess": np.int8, "reason": np.int8, "risk": np.float32}


class CapExceeded(RuntimeError):
    """The row / batch would take a ledger count past its HARD cap: nothing was appended, nothing may run."""


class PickSealed(RuntimeError):
    """A PICK (2024) run was asked for a candidate that is not a BUILD survivor."""


# ------------------------------------------------------------------ the ledger (hard caps)

@contextlib.contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def read_ledger(path=None) -> list:
    p = Path(path) if path is not None else LEDGER
    if not p.exists() or p.stat().st_size == 0:
        return []
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def ledger_used(rows: list | None = None, path=None) -> dict:
    """{'runs': n, 'cells': n, 'wfs': n} counted so far against the caps (failed candidate batches count; NULL / control
    cells do not: ledger_nulls)."""
    rows = read_ledger(path) if rows is None else rows
    return {k: sum(int(r.get(k) or 0) for r in rows) for k in CAPS}


def ledger_nulls(rows: list | None = None, path=None) -> int:
    """Null / control cells run so far (C1 pools, time-shuffle, C2): tracked, not capped (ORCHESTRATOR DECISIONS 6)."""
    rows = read_ledger(path) if rows is None else rows
    return sum(int(r.get("null_cells") or 0) for r in rows)


def ledger_left(path=None, caps: dict | None = None) -> dict:
    used, caps = ledger_used(path=path), caps or CAPS
    return {k: caps[k] - used[k] for k in caps}


def ledger_check(runs: int = 0, cells: int = 0, wfs: int = 0, path=None, caps: dict | None = None) -> dict:
    """Would a batch fit under the caps? Raises CapExceeded (naming the count) if not; -> what is left afterwards.
    Call it BEFORE a batch starts: a batch that would pass a cap is refused as a whole."""
    used, caps = ledger_used(path=path), caps or CAPS
    want = {"runs": int(runs), "cells": int(cells), "wfs": int(wfs)}
    over = [f"{k}: {used[k]} used + {want[k]} asked > cap {caps[k]}" for k in caps if want[k] and used[k] + want[k] > caps[k]]
    if over:
        raise CapExceeded("; ".join(over))
    return {k: caps[k] - used[k] - want[k] for k in caps}


def ledger_has(key: str, stage: str | None = None, path=None) -> bool:
    return any(r["key"] == key and (stage is None or r["stage"] == stage) for r in read_ledger(path))


def ledger_add(stage: str, key: str, kind: str, *, cells: int = 0, path=None, caps: dict | None = None, **info) -> dict:
    """Append ONE row under a lock. kind: 'run' (counts 1 run) | 'grid' (a CANDIDATE menu grid: counts `cells` cells against
    the 50,000 cap) | 'null' (a null / control grid: `cells` goes to the column null_cells, tracked and NOT capped) | 'wf'
    (counts 1 walk-forward) | 'smoke' (counts nothing). A row of stage 'null' / 'null_error' must be kind 'null' and no
    other stage may be. Raises CapExceeded -- and appends NOTHING -- when the row would pass a cap; ValueError for a second
    row of the same (stage, key) unless the stage ends with '_error'."""
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r}: one of {sorted(KINDS)}")
    if not stage or not key:
        raise ValueError("a ledger row needs a stage and a key")
    caps = caps or CAPS
    p = Path(path) if path is not None else LEDGER
    if (stage.split("_")[0] == "null") != (kind == "null") and kind in ("grid", "null"):
        raise ValueError(f"stage {stage!r} with kind {kind!r}: a null / control grid is stage 'null' + kind 'null' (not capped), "
                         "a candidate grid is kind 'grid' (capped)")
    row = {c: "" for c in COLS}
    row.update(stage=stage, key=key, kind=kind, runs=0, cells=0, null_cells=0, wfs=0)
    if kind == "run":
        row["runs"] = 1
    elif kind == "wf":
        row["wfs"] = 1
    elif kind in ("grid", "null"):
        if int(cells) < 1:
            raise ValueError("a grid row needs cells >= 1 (a menu grid of N cells counts N cells)")
        row["cells" if kind == "grid" else "null_cells"] = int(cells)
    unknown = sorted(set(info) - set(COLS))
    if unknown:
        raise ValueError(f"unknown ledger columns {unknown}; the columns are {COLS}")
    row.update({k: v for k, v in info.items() if k not in ("runs", "cells", "null_cells", "wfs")})
    row["finished_utc"] = row["finished_utc"] or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with _locked(p):
        rows = read_ledger(p)
        used = ledger_used(rows)
        over = [f"{k}: {used[k]} used + {row[k]} > cap {caps[k]}" for k in caps if row[k] and used[k] + row[k] > caps[k]]
        if over:
            raise CapExceeded(f"{key} refused -- " + "; ".join(over))
        if not stage.endswith("_error") and any(r["stage"] == stage and r["key"] == key for r in rows):
            raise ValueError(f"the ledger already holds a '{stage}' row for {key}")
        new = not p.exists() or p.stat().st_size == 0
        with p.open("a", newline="") as fh:
            w = csv.DictWriter(fh, COLS)
            if new:
                w.writeheader()
            w.writerow(row)
    return row


# ------------------------------------------------------------------ trades -> arrays, statistics

def session_code(entry_ms) -> np.ndarray:
    """Session code (index into SESS7; -1 = none) of each entry time, by its ET minute: l2sim.session_of, vectorised."""
    import l2sim
    return np.array([SESS_CODE.get(l2sim.session_of(int(m)), -1) for m in np.asarray(entry_ms).ravel()], np.int8)


def pack(trades: list) -> dict:
    """A trade list (l2sim / tester schema, 1 contract) -> compact arrays: date (ordinal of the TRADE date), entry_ms, dur_s,
    net, mae (USD), side (+1 / -1), sess (SESS7 code), reason (REASONS code), risk (|entry - sl| in points, NaN without a stop)."""
    n = len(trades)
    out = {k: np.zeros(n, DTYPES[k]) for k in FIELDS}
    if not n:
        return out
    out["date"][:] = [dt.date.fromisoformat(t["date"]).toordinal() for t in trades]
    out["entry_ms"][:] = [t["entry_ms"] for t in trades]
    out["dur_s"][:] = [max(0, (t["exit_ms"] - t["entry_ms"]) // 1000) for t in trades]
    out["net"][:] = [t["net"] for t in trades]
    out["mae"][:] = [abs(t.get("mae_usd") or 0.0) for t in trades]
    out["side"][:] = [1 if t["side"] == "long" else -1 for t in trades]
    out["sess"][:] = session_code(out["entry_ms"])
    rc = {r: i for i, r in enumerate(REASONS)}
    out["reason"][:] = [rc.get(t.get("exit_reason"), rc["other"]) for t in trades]
    out["risk"][:] = [abs(t["entry_price"] - t["sl"]) if t.get("sl") is not None else np.nan for t in trades]
    return out


def stats(net) -> dict:
    """trades, net, t (t-statistic of the per-trade net: mean / (sd / sqrt(n)); None with < 2 trades or sd 0), profit factor,
    win rate. The same definitions as the L2 pilot's screen analysis."""
    x = np.asarray(net, np.float64)
    n = int(len(x))
    if not n:
        return {"trades": 0, "net": 0.0, "t": None, "pf": None, "win": None}
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    gw, gl = float(x[x > 0].sum()), float(-x[x < 0].sum())
    return {"trades": n, "net": round(float(x.sum()), 2), "t": float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else None,
            "pf": (gw / gl) if gl > 0 else None, "win": float((x > 0).mean())}


def cell_stat(net, stat: str = "t") -> float:
    """One cell's statistic for the nulls bar: 't' (default; unit-free: comparable across roots, stops and trade counts;
    no trades / undefined -> 0.0) | 'net' | 'pf'."""
    s = stats(net)
    if stat == "net":
        return float(s["net"])
    if stat == "pf":
        return float(s["pf"]) if s["pf"] is not None else 0.0
    if stat == "t":
        return float(s["t"]) if s["t"] is not None else 0.0
    raise ValueError(f"stat {stat!r}: 't' | 'net' | 'pf'")


# ------------------------------------------------------------------ unit stores (runs/<key>/)

def write_unit(key: str, meta: dict, cells: list, results: list, runs_dir=None) -> Path:
    """Write one unit's store: run.json (meta + the cells + coverage), cells.npz (all trades, compact), table.csv.
    cells: l2sim.menu_grid rows (id, variant, exit, vi, xi); results: the matching l2sim.run_many results."""
    if len(cells) != len(results):
        raise ValueError("cells and results differ in length")
    out = (Path(runs_dir) if runs_dir is not None else RUNS) / key           # runs_dir: tests (tmp_path) only
    tmp = out.with_name(out.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    packs = [pack(r["trades"]) for r in results]
    off = np.zeros(len(packs) + 1, np.int64)
    off[1:] = np.cumsum([len(p["net"]) for p in packs])
    arrays = {k: (np.concatenate([p[k] for p in packs]) if packs else np.zeros(0, DTYPES[k])) for k in FIELDS}
    np.savez_compressed(tmp / "cells.npz", off=off, **arrays)
    r0 = results[0] if results else {"meta": {}, "sessions": 0, "used": 0, "skipped": [], "no_trade": [], "elapsed_s": 0.0}
    doc = dict(meta)
    doc.update(key=key, engine=r0["meta"].get("engine"), root=r0["meta"].get("root"), range=r0["meta"].get("range"),
               segments=r0["meta"].get("segments"), passes=r0["meta"].get("passes"), features=r0["meta"].get("features"),
               features_loader=r0["meta"].get("features_loader"), exec_guard=r0["meta"].get("exec_guard"),
               coverage={"sessions": r0["sessions"], "used": r0["used"], "skipped": r0["skipped"],
                         "eve_skipped": r0.get("eve_skipped", [])},
               elapsed_s=r0["elapsed_s"],
               cells=[{"id": c["id"], "vi": c["vi"], "xi": c["xi"], "variant": c["variant"], "exit": c["exit"],
                       "inputs": results[i]["meta"]["inputs"], "trades": len(results[i]["trades"]),
                       "both_sides_sessions": results[i].get("both_sides_sessions"),
                       "skipped_by_error": results[i].get("skipped_by_error", 0),
                       "unrealistic_winners": results[i].get("unrealistic_winners", 0),
                       **({"info": True} if c.get("info") else {})} for i, c in enumerate(cells)])
    (tmp / "run.json").write_text(json.dumps(doc, indent=1, default=str))
    rows = unit_table({"meta": doc, "off": off, **arrays})
    with (tmp / "table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]) if rows else ["cell"])
        w.writeheader()
        w.writerows(rows)
    if out.exists():
        import shutil
        shutil.rmtree(out)
    tmp.rename(out)
    return out


def load_unit(key: str, runs_dir=None) -> dict:
    """runs/<key>/ -> {'meta': run.json, 'off': cell offsets, <field>: flat arrays}. unit_cell(u, id) slices one cell."""
    d = (Path(runs_dir) if runs_dir is not None else RUNS) / key
    meta = json.loads((d / "run.json").read_text())
    z = np.load(d / "cells.npz")
    return {"meta": meta, **{k: z[k] for k in z.files}}


def unit_cell(u: dict, cell) -> dict:
    """The arrays of ONE cell (by id or index) of a loaded unit."""
    i = cell if isinstance(cell, int) else next(k for k, c in enumerate(u["meta"]["cells"]) if c["id"] == cell)
    a, b = int(u["off"][i]), int(u["off"][i + 1])
    return {k: u[k][a:b] for k in FIELDS}


def unit_table(u: dict) -> list:
    """One row per (cell, session) with >= 0 trades for every session that trades anywhere in the unit, + session 'all'."""
    cells = u["meta"]["cells"]
    seen = sorted({int(s) for s in np.unique(u["sess"]) if s >= 0}) if len(u["sess"]) else []
    rows = []
    for i, c in enumerate(cells):
        x = unit_cell(u, i)
        for name, m in [("all", np.ones(len(x["net"]), bool))] + [(SESS7[s], x["sess"] == s) for s in seen]:
            st = stats(x["net"][m])
            rows.append({"cell": c["id"], "vi": c["vi"], "xi": c["xi"], "sess": name, "trades": st["trades"], "net": st["net"],
                         "t": "" if st["t"] is None else round(st["t"], 4), "pf": "" if st["pf"] is None else round(st["pf"], 4),
                         "win": "" if st["win"] is None else round(st["win"], 4),
                         "max_mae_usd": round(float(x["mae"][m].max()), 2) if m.any() else 0.0})
    return rows


def trade_sig(x: dict, m=None) -> str:
    """Fingerprint of a cell's trade list (packed arrays, optionally masked): two cells with the same entries, sides,
    durations and nets are the SAME trades (ib fade / gap fill ignore the target: 4 identical cells per stop)."""
    import hashlib
    m = slice(None) if m is None else m
    if not len(x["net"][m]):
        return "empty"
    h = hashlib.blake2b(digest_size=12)
    for k, t in (("entry_ms", np.int64), ("dur_s", np.int64), ("side", np.int64)):
        h.update(np.ascontiguousarray(x[k][m], t).tobytes())
    h.update(np.round(np.asarray(x["net"][m], np.float64) * 100.0).astype(np.int64).tobytes())
    return h.hexdigest()


def session_table(u: dict, sess: str) -> list:
    """The plateau table of ONE unit-session over every cell of the unit: [{'id', 'vi', 'xi', 'net', 'trades', 't',
    'stop_mode', 'tgt_r' (the cell's exit), 'sig' (trade_sig: identical trade lists are judged once), 'dead'}].
    dead = STRUCTURALLY DEAD (ORCHESTRATOR DECISIONS 2: "cells that cannot trade by construction are excluded"): the
    cell's VARIANT has no trade in this session in ANY of its exit cells over the store's whole range. An entry never
    depends on the exit cell, so such a variant cannot enter there (warm-up longer than the session, a level that does
    not exist in it, a clock time outside it): a count of ENTRIES, never of P&L; fixed before any run."""
    out = []
    for i, c in enumerate(u["meta"]["cells"]):
        x = unit_cell(u, i)
        m = np.ones(len(x["net"]), bool) if sess == "all" else x["sess"] == SESS_CODE[sess]
        st = stats(x["net"][m])
        ex = c.get("exit") or {}
        out.append({"id": c["id"], "vi": c["vi"], "xi": c["xi"], "net": st["net"], "trades": st["trades"], "t": st["t"],
                    "stop_mode": ex.get("stop_mode"), "tgt_r": ex.get("tgt_r"), "sig": trade_sig(x, m),
                    "info": bool(c.get("info"))})         # EDGE_SPEC stage 2b "author cell": information only, never judged
    alive = {r["vi"] for r in out if r["trades"]}
    for r in out:
        r["dead"] = r["vi"] not in alive
    return out


def mirror_axis(u: dict):
    """The MIRROR axis of a unit store (run.json `mirror`: tod_drift dir, ib mode, gap mode), or None."""
    return u["meta"].get("mirror") or None


def plateau_units(u: dict, sess: str) -> dict:
    """The JUDGED UNITS of one unit-session (ORCHESTRATOR DECISIONS 2): {label: plateau table}. A family without a mirror
    axis is ONE unit ({'': table}); a MIRROR family is one unit per value of its axis ({'dir=long': ..., 'dir=short': ...}):
    opposite hypotheses never share a plateau. It only splits; plateau() judges each table."""
    table = session_table(u, sess)
    axis = mirror_axis(u)
    if not axis:
        return {"": table}
    variants = {c["vi"]: c["variant"] for c in u["meta"]["cells"]}
    out: dict = {}
    for r in table:
        out.setdefault(f"{axis}={variants[r['vi']][axis]}", []).append(r)
    return out


def judge(u: dict, sess: str, share: float = PLATEAU_SHARE) -> dict:
    """{label: plateau(...)} of every judged unit of one unit-session (plateau_units)."""
    return {k: plateau(t, share) for k, t in plateau_units(u, sess).items()}


def unit_sessions(u: dict) -> list:
    """The sessions (of the seven) in which the unit store holds a trade, in clock order."""
    return [SESS7[k] for k in sorted({int(v) for v in np.unique(u["sess"]) if v >= 0})] if len(u["sess"]) else []


# ------------------------------------------------------------------ judging: plateau

def _verdicts(med, sp) -> dict:
    return {f"{int(round(v * 100))}": bool(med is not None and med > 0 and sp is not None and sp >= v - 1e-12) for v in VERDICT_SHARES}


def _group(net) -> dict:
    net = np.asarray(net, np.float64)
    if not len(net):
        return {"cells": 0, "positive": 0, "share_pos": None, "median_net": None, "verdicts": _verdicts(None, None)}
    med, sp = float(np.median(net)), float((net > 0).mean())
    return {"cells": int(len(net)), "positive": int((net > 0).sum()), "share_pos": round(sp, 4), "median_net": round(med, 2),
            "verdicts": _verdicts(med, sp)}


def judged_rows(table: list) -> tuple:
    """(judged rows, n dead, n duplicates): the table minus the rows marked 'dead', with rows of the same 'sig' (identical
    trade lists) merged into the first one in (vi, xi) order. Rows without those keys are all judged (a bare table).
    Rows marked 'info' (EDGE_SPEC stage 2b author cells: information only) are left out before anything is counted."""
    rows = [dict(r) for r in table if not r.get("info")]
    live = [r for r in rows if not r.get("dead")]
    order = sorted(range(len(live)), key=lambda k: (live[k].get("vi", k), live[k].get("xi", k), k))
    seen, keep = set(), []
    for k in order:
        sig = live[k].get("sig")
        if sig is not None:
            if sig in seen:
                continue
            seen.add(sig)
        keep.append(k)
    keep.sort()
    return [live[k] for k in keep], len(rows) - len(live), len(live) - len(keep)


def plateau(table: list, share: float = PLATEAU_SHARE) -> dict:
    """EDGE_SPEC 'Judging' on ONE unit (family x tf x session x root [x mirror value]): `table` = one row per (parameter x
    exit) cell with 'id', 'net' (after costs, 1 contract) and optionally 'vi' / 'xi' (variant / exit index: the simplicity
    order; default = the row order), 'trades', 'dead', 'sig', 'stop_mode', 'tgt_r' (session_table writes them all).
      judged      the rows not marked dead, identical trade lists ('sig') counted once (judged_rows). A judged cell
                  without a trade has net 0 and is NOT > 0.
      pass        median net over the judged cells > 0  AND  share of judged cells with net > 0 >= 60 %
      member      the CENTRAL cell: the positive judged cell whose net is closest to the median net; ties -> the lowest
                  (vi, xi). None when no cell is positive. Never chosen by being the best.
      shares      the share of cells > 0 with its verdict at 60 / 70 / 80 % (verdict = median > 0 and share >= bar):
                  'overall', 'by_stop' (fixed / ATR / percent) and 'by_target' (r0 = no target, r1, r2, r3) -- of the judged
                  cells (a duplicate group sits where its first cell sits). For reading; the binding verdict is `pass`.
      info        rows marked 'info' (author cells, information only) are dropped first: never judged, never the member;
                  `info` = how many, `cells_all` = the rows without them.
    -> {'pass', 'cells' (judged), 'cells_all', 'info', 'dead', 'duplicates', 'median_net', 'share_pos', 'positive', 'member',
        'member_net', 'best', 'best_net', 'worst_net', 'verdicts', 'shares'}"""
    rows, n_dead, n_dup = judged_rows(table)
    n_info = sum(1 for r in table if r.get("info"))          # author cells: run and stored, never in the heat map
    table = [r for r in table if not r.get("info")]
    empty = {"pass": False, "cells": 0, "cells_all": len(table), "info": n_info, "dead": n_dead, "duplicates": n_dup, "median_net": None,
             "share_pos": None, "positive": 0, "member": None, "member_net": None, "best": None, "best_net": None,
             "worst_net": None, "verdicts": _verdicts(None, None), "shares": {"overall": _group([]), "by_stop": {}, "by_target": {}}}
    if not rows:
        return empty
    ids = [r["id"] for r in table]
    if len(set(ids)) != len(ids):
        raise ValueError("plateau: duplicate cell ids in the table")
    ids = [r["id"] for r in rows]
    net = np.array([float(r["net"]) for r in rows], np.float64)
    med = float(np.median(net))
    pos = net > 0
    sp = float(pos.mean())
    member = None
    if pos.any():
        order = sorted((k for k in range(len(rows)) if pos[k]),
                       key=lambda k: (round(abs(net[k] - med), 6), rows[k].get("vi", k), rows[k].get("xi", k), k))
        member = order[0]
    best = int(net.argmax())
    by_stop, by_tgt = {}, {}
    for k, r in enumerate(rows):
        if r.get("stop_mode") is not None:
            by_stop.setdefault(STOP_TYPES.get(r["stop_mode"], str(r["stop_mode"])), []).append(net[k])
        if r.get("tgt_r") is not None:
            by_tgt.setdefault("r%g" % float(r["tgt_r"]), []).append(net[k])
    shares = {"overall": _group(net), "by_stop": {k: _group(v) for k, v in by_stop.items()},
              "by_target": {k: _group(v) for k, v in sorted(by_tgt.items())}}
    return {"pass": bool(med > 0 and sp >= share - 1e-12), "cells": len(rows), "cells_all": len(table), "info": n_info, "dead": n_dead,
            "duplicates": n_dup, "median_net": round(med, 2),
            "share_pos": round(sp, 4), "positive": int(pos.sum()), "member": None if member is None else ids[member],
            "member_net": None if member is None else round(float(net[member]), 2), "best": ids[best],
            "best_net": round(float(net[best]), 2), "worst_net": round(float(net.min()), 2),
            "verdicts": _verdicts(med, sp), "shares": shares}


def shares_md(pl: dict) -> list:
    """Markdown lines of a plateau's share table (decision 7): overall, by stop type, per reward ratio; verdicts 60/70/80."""
    L = ["| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |", "|---|---|---|---|---|---|---|---|"]
    sh = pl.get("shares") or {}
    groups = [("all judged cells", sh.get("overall"))]
    groups += [(f"stop: {k}", v) for k, v in (sh.get("by_stop") or {}).items()]
    groups += [(f"target: {'none' if k == 'r0' else '1:' + k[1:]}", v) for k, v in (sh.get("by_target") or {}).items()]
    for name, g in groups:
        if g:
            v = g["verdicts"]
            L.append(f"| {name} | {g['cells']} | {g['positive']} | {_pct(g['share_pos'])} | {_fmt(g['median_net'])} | "
                     f"{_fmt(v['60'])} | {_fmt(v['70'])} | {_fmt(v['80'])} |")
    return L


# ------------------------------------------------------------------ nulls

def best_of_nulls(batch, q: float = 95.0, stat: str = "t") -> dict:
    """THE BEST-OF-NULLS BAR of a batch (EDGE_SPEC E): the q-th (95th) percentile, over the batch's null replicates, of each
    replicate's BEST cell. A replicate = ONE null run of ONE unit-session over the menu (one seed of the random control, the
    time-shuffle null or the feature-shuffle null) given as {cell id: statistic} or a sequence of cell statistics -- or of
    per-cell net ARRAYS, which are reduced with cell_stat(..., stat) ('t' by default: unit-free).
    A claim must beat this bar: it is what the best cell of a menu reaches with no edge at all.
    -> {'bar', 'q', 'stat', 'nulls', 'best': sorted best-cell values, 'thin': fewer than 20 replicates}"""
    best = []
    for rep in batch:
        vals = list(rep.values()) if isinstance(rep, dict) else list(rep)
        if not vals:
            continue
        vals = [cell_stat(v, stat) if isinstance(v, (np.ndarray, list, tuple)) else float(v) for v in vals]
        best.append(max(vals))
    if not best:
        raise ValueError("best_of_nulls: the batch holds no null replicate")
    best.sort()
    return {"bar": float(np.percentile(best, q)), "q": q, "stat": stat, "nulls": len(best), "best": [round(b, 4) for b in best],
            "thin": len(best) < 20}


def unit_null_replicates(u: dict, stat: str = "t", sessions=None, by: str = "seed") -> list:
    """The null replicates of a NULL unit store (run_menus: c1 / shift / c2 stores, whose cells carry `variant[by]` = the
    seed): one replicate per (seed, session) = {cell id without the seed: statistic}."""
    cells = u["meta"]["cells"]
    key = "shift_seed" if any("shift_seed" in c["variant"] for c in cells) else by
    seeds = sorted({c["variant"].get(key) for c in cells})
    sess = sessions or [SESS7[s] for s in sorted({int(s) for s in np.unique(u["sess"]) if s >= 0})]
    out = []
    for sd in seeds:
        idx = [i for i, c in enumerate(cells) if c["variant"].get(key) == sd]
        for s in sess:
            rep = {}
            for i in idx:
                x = unit_cell(u, i)
                rep[cells[i]["id"]] = cell_stat(x["net"][x["sess"] == SESS_CODE[s]], stat)
            out.append(rep)
    return out


def c1_draws(member: dict, pool: dict, K: int = 200, seed: int = 1) -> dict:
    """C1: K day- and session-matched random ledgers for a member, from a random-entry pool with the SAME exit profile.
    member / pool: packed arrays (pack(trades) or unit_cell(...)); only date, sess, net are read. For every (date, session)
    with k member trades a draw takes k pool trades of that date + session (uniform, without replacement); a shortfall is
    filled from the same session on the nearest dates (all pool trades within the smallest date distance that holds enough
    of them) and counted in `fallback_share`.
    -> {'nets': K control nets, 'mean', 'p95', 'lift' = member net - mean, 'p_beat' = share of draws the member beats,
        'fallback_share', 'short' (member trades that could not be matched at all), 'pool_trades'}"""
    rng = np.random.default_rng(int(seed))
    md, ms, mnet = np.asarray(member["date"]), np.asarray(member["sess"]), float(np.asarray(member["net"], np.float64).sum())
    pd_, ps, pn = np.asarray(pool["date"]), np.asarray(pool["sess"]), np.asarray(pool["net"], np.float64)
    by: dict = {}
    for i, (d, s) in enumerate(zip(pd_.tolist(), ps.tolist())):
        by.setdefault((d, s), []).append(i)
    by_sess = {s: np.flatnonzero(ps == s) for s in set(ps.tolist())}
    groups: dict = {}
    for d, s in zip(md.tolist(), ms.tolist()):
        groups[(d, s)] = groups.get((d, s), 0) + 1
    plan, fb, short = [], 0, 0
    for (d, s), k in sorted(groups.items()):
        own = np.array(by.get((d, s), []), np.int64)
        need = k - len(own)
        extra = np.zeros(0, np.int64)
        if need > 0:
            cand = by_sess.get(s, np.zeros(0, np.int64))
            cand = cand[pd_[cand] != d]
            if len(cand):                             # the nearest dates: every pool trade of the session within the smallest
                dist = np.abs(pd_[cand] - d)          # date distance that holds at least `need` of them
                cut = np.sort(dist)[min(need, len(dist)) - 1]
                extra = cand[dist <= cut]
            got = min(need, len(extra))
            fb += got
            short += need - got
        plan.append((own, min(k, len(own)), extra, max(0, min(need, len(extra)))))
    nets = np.zeros(K)
    for j in range(K):
        tot = 0.0
        for own, k_own, extra, k_ex in plan:
            if k_own:
                tot += pn[rng.choice(own, k_own, replace=False)].sum() if k_own < len(own) else pn[own].sum()
            if k_ex:
                tot += pn[rng.choice(extra, k_ex, replace=False)].sum() if k_ex < len(extra) else pn[extra].sum()
        nets[j] = tot
    n = int(len(md))
    return {"nets": nets, "mean": round(float(nets.mean()), 2), "p95": round(float(np.percentile(nets, 95)), 2),
            "lift": round(mnet - float(nets.mean()), 2), "p_beat": float((mnet > nets).mean()), "member_net": round(mnet, 2),
            "fallback_share": (fb / n) if n else 0.0, "short": int(short), "pool_trades": int(len(pn)), "K": K}


def default_seed(name: str, period: str) -> int:
    return zlib.crc32(f"{name}|{period}".encode()) % 100000


# ------------------------------------------------------------------ daily series

def _worst_open(rows: list) -> float:
    """How far a day's P&L, OPEN losses included, was below its start at the worst point (USD >= 0). rows = the day's trades
    as (entry_ms, exit_ms, net, open_cost) with open_cost = the trade's MAE + its commission, in entry order: at every
    entry, [P&L realised by the trades already closed] - [the open costs of every trade open then]. A trade is charged its
    whole MAE for as long as it is open (it may be held from the evening before to 15:58), overlapping trades add theirs:
    conservative."""
    worst, real, open_ = 0.0, 0.0, []
    for t in sorted(rows, key=lambda r: (r[0], r[1])):
        for o in [o for o in open_ if o[1] <= t[0]]:
            real += o[2]
            open_.remove(o)
        open_.append(t)
        worst = min(worst, real - sum(o[3] for o in open_))
    return -worst


def daily_rows(trades: list, calendar: list, period: str = "") -> list:
    """One row per session of `calendar` (ISO trade dates; a day without a trade is a 0 row): date, period, net (sum of the
    day's trade nets, 1 contract), worst_open_loss (USD >= 0: how far the day's P&L was below its start at the worst point,
    open losses included = max over the day's trades, in entry order, of [each trade's MAE + its commission - the P&L realised
    before it], floored at 0; overlapping trades add their MAEs: conservative), minutes_in_market (sum of exit - entry).
    A trade belongs to its TRADE date whatever its hold: an evening entry held to 15:58 (hold_to='day') is charged, with its
    whole MAE, to the trade date it carries."""
    by: dict = {}
    for t in trades:
        by.setdefault(t["date"], []).append(t)
    off = sorted(set(by) - set(calendar))
    if off:
        raise ValueError(f"{len(off)} trade dates are off the calendar ({off[:5]}...)")
    out = []
    for d in calendar:
        ts = by.get(d, [])
        worst = _worst_open([(t["entry_ms"], t["exit_ms"], t["net"], abs(t.get("mae_usd") or 0.0) + abs(t.get("commission") or 0.0))
                             for t in ts])
        out.append({"date": d, "period": period, "net": round(sum(t["net"] for t in ts), 2), "worst_open_loss": round(worst, 2),
                    "minutes_in_market": round(sum((t["exit_ms"] - t["entry_ms"]) / 60000.0 for t in ts), 2)})
    return out


# ------------------------------------------------------------------ the metric set, per year then combined (decision 7)

METRIC_KEYS = ("trades", "net", "win", "pf", "max_dd", "sharpe", "avg_trade", "worst_open_loss")


def _ordinals(calendar) -> np.ndarray:
    return np.array(sorted({dt.date.fromisoformat(d).toordinal() if isinstance(d, str) else int(d) for d in calendar}), np.int64)


def metrics(x: dict, calendar=None, comm=COMM_RT) -> dict:
    """THE METRIC SET of one trade list (packed arrays: pack(trades) / unit_cell(...) / sized(...)), 1 contract unless sized:
      trades, net, win (rate), pf, avg_trade
      max_dd           the largest peak-to-trough fall of the cumulative DAILY net (USD >= 0; days in trade-date order)
      sharpe           mean / sd of the DAILY net x sqrt(252) over every session of `calendar` (ISO dates or ordinals; a day
                       without a trade is a 0 day; without a calendar: the days that traded). None with < 2 days or sd 0.
      worst_open_loss  the worst single day's open drawdown from that day's start, open losses included (_worst_open with
                       each trade's MAE + `comm`: the engine's round-turn commission, or an array of per-trade costs)
      days, t          sessions counted; the per-trade t statistic (stats)."""
    net = np.asarray(x["net"], np.float64)
    st = stats(net)
    n = st["trades"]
    date = np.asarray(x["date"], np.int64)
    days = _ordinals(calendar) if calendar is not None else np.unique(date)
    daily = np.zeros(len(days))
    if n:
        idx = np.searchsorted(days, date)
        if (idx >= len(days)).any() or (days[np.minimum(idx, len(days) - 1)] != date).any():
            raise ValueError("metrics: trade dates off the calendar")
        np.add.at(daily, idx, net)
    cum = np.cumsum(daily)
    max_dd = float((np.maximum.accumulate(np.concatenate(([0.0], cum))) - np.concatenate(([0.0], cum))).max()) if len(cum) else 0.0
    sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    worst = 0.0
    if n:
        ent = np.asarray(x["entry_ms"], np.int64)
        ext = ent + np.asarray(x["dur_s"], np.int64) * 1000
        cost = np.abs(np.asarray(x["mae"], np.float64)) + np.broadcast_to(np.asarray(comm, np.float64), net.shape)
        order = np.argsort(date, kind="stable")
        cuts = np.flatnonzero(np.diff(date[order])) + 1
        for g in np.split(order, cuts):
            worst = max(worst, _worst_open([(int(ent[k]), int(ext[k]), float(net[k]), float(cost[k])) for k in g]))
    return {"trades": n, "net": st["net"], "win": st["win"], "pf": st["pf"], "max_dd": round(max_dd, 2),
            "sharpe": float(daily.mean() / sd * math.sqrt(252.0)) if sd > 0 else None,
            "avg_trade": round(st["net"] / n, 2) if n else None, "worst_open_loss": round(worst, 2), "days": int(len(days)), "t": st["t"]}


def per_year(x: dict, calendar=None, comm=COMM_RT) -> list:
    """Decision 7: the metric set PER YEAR first, then combined -> [{'period': '2021*', ...}, {'period': '2022', ...}, ...,
    {'period': 'combined', ...}]. Years by TRADE date; a year the calendar covers only in part is starred (BUILD starts
    2021-09-22). `comm` as metrics (a per-trade array is split with the trades)."""
    date = np.asarray(x["date"], np.int64)
    days = _ordinals(calendar) if calendar is not None else np.unique(date)
    yr = lambda o: dt.date.fromordinal(int(o)).year          # noqa: E731
    ty = np.array([yr(o) for o in date], np.int64)
    dy = np.array([yr(o) for o in days], np.int64)
    cm = np.broadcast_to(np.asarray(comm, np.float64), np.asarray(x["net"]).shape)
    out = []
    for y in sorted(set(dy.tolist()) | set(ty.tolist())):
        m, cal = ty == y, days[dy == y]
        part = bool(len(cal)) and (dt.date.fromordinal(int(cal[0])) > dt.date(y, 1, 10) or dt.date.fromordinal(int(cal[-1])) < dt.date(y, 12, 20))
        row = metrics({k: np.asarray(v)[m] for k, v in x.items() if k in FIELDS}, cal if calendar is not None else None, cm[m])
        out.append({"period": f"{y}*" if part else str(y), **row})
    out.append({"period": "combined", **metrics(x, days if calendar is not None else None, cm)})
    return out


def sized(x: dict, root: str, risk_usd: float = RISK_USD) -> dict:
    """Decision 7: the same trades sized to ABOUT `risk_usd` ($1,000) of risk per trade in MICROS. Per trade: micros =
    max(1, round(risk_usd / (stop distance in points x the micro's point value))); its net = micros x (the 1-contract gross
    / 10 - the micro round-turn commission), its MAE scales alike. A trade without a stop distance cannot be sized: 0 micros,
    net 0 (counted in 'unsized'). -> packed arrays + 'micros' (per trade), 'cost' (per-trade commission, for metrics(comm=)),
    'unsized', 'risk_usd'. The slippage of the 1-contract run is kept per micro (1 tick a side)."""
    import l2sim
    pv = l2sim.SPECS[root][0] / MICRO_DIV
    risk = np.asarray(x["risk"], np.float64)
    ok = np.isfinite(risk) & (risk > 0)
    micros = np.zeros(len(risk), np.int64)
    micros[ok] = np.maximum(1, np.rint(risk_usd / (risk[ok] * pv))).astype(np.int64)
    gross = (np.asarray(x["net"], np.float64) + COMM_RT) / MICRO_DIV
    out = {k: np.asarray(x[k]).copy() for k in FIELDS}
    out["net"] = micros * (gross - MICRO_RT_USD)
    out["mae"] = (micros * np.asarray(x["mae"], np.float64) / MICRO_DIV).astype(np.float32)
    out.update(micros=micros, cost=micros * MICRO_RT_USD, unsized=int((~ok).sum()), risk_usd=float(risk_usd))
    return out


def _pct(v) -> str:
    return "n/a" if v is None else f"{100.0 * float(v):.1f} %"


def metrics_md(rows: list) -> list:
    """Markdown lines of a per_year() table."""
    L = ["| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['period']} | {r['trades']} | {_fmt(r['net'])} | {_pct(r['win'])} | {_fmt(r['pf'])} | {_fmt(r['max_dd'])} | "
                 f"{_fmt(r['sharpe'])} | {_fmt(r['avg_trade'])} | {_fmt(r['worst_open_loss'])} |")
    return L


def report_md(x: dict, root: str, calendar=None, title: str = "") -> list:
    """Decision 7 for ONE trade list (a member cell or a unit's central cell): the metric set per year then combined, at 1
    contract and sized to about $1,000 of risk in micros."""
    z = sized(x, root)
    mic = z["micros"][z["micros"] > 0]
    L = [f"### {title}1 contract, costs included (* = partial year)"] + metrics_md(per_year(x, calendar)) + [
        "", f"### {title}sized to about ${RISK_USD:,.0f} of risk per trade in micros"
            + (f" (micros per trade: median {int(np.median(mic))}, min {int(mic.min())}, max {int(mic.max())}"
               f"{'; ' + str(z['unsized']) + ' trades without a stop left out' if z['unsized'] else ''})" if len(mic) else "")]
    return L + metrics_md(per_year(z, calendar, z["cost"]))


def unit_report_md(u: dict, sess: str, cal=None) -> str:
    """Decision 7 for ONE unit-session of a store (RESULTS: the Admit stage's report, never a smoke): its flags (WEAK, second
    look, the penalty where it applies, notes), then per JUDGED unit -- a mirror family: one per value of its axis -- the
    plateau line, the share table with the verdicts at 60 / 70 / 80 % (overall, by stop type, per reward ratio) and the
    CENTRAL cell's metric set per year then combined, at 1 contract and sized to about $1,000 of risk in micros.
    cal: the period's session calendar (default: calendar(the store's period, its root))."""
    meta = u["meta"]
    root = meta.get("root") or "NQ"
    cal = calendar(meta.get("period") or "build", root) if cal is None else cal
    ps = meta.get("penalty_sess")
    pen = meta.get("penalty") if meta.get("penalty") and (not ps or sess in ps) else None
    L = [f"# {meta.get('key')} — session {sess} ({meta.get('period') or 'build'}, hold_to = {meta.get('hold_to') or 'session'})", "",
         f"* Rationale: {meta.get('rationale')}", f"* WEAK: {'YES (t >= ' + _fmt(WEAK_T) + ' on BUILD)' if meta.get('weak') else 'no'}"
         f" · second look: {meta.get('second_look') or 'no'} · penalty: {pen or 'none'}",
         f"* Notes: {meta.get('notes')}"]
    for label, table in plateau_units(u, sess).items():
        pl = plateau(table)
        L += ["", f"## unit {label or 'all cells'} — plateau {'PASS' if pl['pass'] else 'fail'}",
              f"judged {pl['cells']} of {pl['cells_all']} cells (dead {pl['dead']}, duplicate trade lists {pl['duplicates']}) · median net "
              f"{_fmt(pl['median_net'])} · share > 0 {_pct(pl['share_pos'])} · central cell `{pl['member']}` (net {_fmt(pl['member_net'])}; "
              f"best cell {_fmt(pl['best_net'])}, worst {_fmt(pl['worst_net'])})", ""]
        L += shares_md(pl)
        if pl["member"] is not None:
            x = unit_cell(u, pl["member"])
            m = x["sess"] == SESS_CODE[sess]
            L += [""] + report_md({k: v[m] for k, v in x.items()}, root, cal, title=f"central cell `{pl['member']}` — ")
    return "\n".join(L) + "\n"


def calendar(period: str, root: str = "NQ") -> list:
    """The session calendar (ISO trade dates) of 'build' | 'pick' | 'insample' for a root (l2sim.sessions; EXAM raises)."""
    import l2sim
    a, b = l2sim.period(period)
    return [d.isoformat() for d in l2sim.sessions(a, b, root)]


# ------------------------------------------------------------------ admission

def _net(trades) -> float:
    return round(float(sum(t["net"] for t in trades)), 2)


def _test(ok, **detail) -> dict:
    return {"pass": bool(ok), **detail}


def admission(member: dict, write: bool = False, members_dir=None) -> dict:
    """EVERY library-admission test of EDGE_SPEC "Library admission" (BUILD + PICK only), fail closed: a missing input fails
    its test. `member`:
      name, family, root, tf, sess, inputs (the member cell's inputs), cell (its id)
      rationale (one sentence, written before testing), complexity (int), weak (bool), l2 (bool), penalty (str | None)
      plateau = {'build': plateau(...) of its unit on BUILD [, 'pick': ... on PICK]}
      nulls_bar = best_of_nulls(...) of its batch on BUILD (stat 't')
      build / pick = {'trades': [...1 contract...], 'stress': [...the same cell under l2sim.STRESS...],
                      'c1_pool': [random-entry trades, same tf + exit cell] (or 'c1': a ready c1_draws result),
                      'c2': [[trades of feature-shuffle seed 1], [seed 2]]   (L2 members only),
                      'calendar': [ISO trade dates of the period for the root]}
    Tests (all must pass): net_build > 0 . net_pick > 0 . plateau on BUILD (and on PICK for a penalised family) . beats C1 in
    both periods (lift > 0) . beats C2 in both (L2) . t on BUILD >= the batch's best-of-nulls bar . stressed net > 0 in both
    periods (2 ticks + 250 ms; base and stressed are reported side by side) . >= 100 trades (BUILD + PICK) . the worst
    per-trade open loss fits $2,000 at >= 1 micro . rationale + complexity present . a WEAK rationale needs t >= 3 on BUILD.
    -> {'admit': bool, 'tests': {...}, 'summary': {...}}; write=True also writes the member folder (write_member)."""
    name = member["name"]
    b, p = member.get("build") or {}, member.get("pick") or {}
    tb, tp = b.get("trades"), p.get("trades")
    tests: dict = {}
    sb = stats([t["net"] for t in tb]) if tb is not None else None
    sp = stats([t["net"] for t in tp]) if tp is not None else None
    tests["net_build"] = _test(sb is not None and sb["net"] > 0, net=None if sb is None else sb["net"])
    tests["net_pick"] = _test(sp is not None and sp["net"] > 0, net=None if sp is None else sp["net"])
    pl = member.get("plateau") or {}
    tests["plateau_build"] = _test(bool((pl.get("build") or {}).get("pass")), **{k: (pl.get("build") or {}).get(k) for k in
                                                                                 ("cells", "median_net", "share_pos", "member")})
    if member.get("penalty"):
        tests["plateau_pick"] = _test(bool((pl.get("pick") or {}).get("pass")), penalty=member["penalty"],
                                      **{k: (pl.get("pick") or {}).get(k) for k in ("cells", "median_net", "share_pos")})
    for per, blk, tr in (("build", b, tb), ("pick", p, tp)):
        c1 = blk.get("c1")
        if c1 is None and tr is not None and blk.get("c1_pool") is not None:
            c1 = c1_draws(pack(tr), pack(blk["c1_pool"]), K=int(member.get("K", 200)), seed=default_seed(name, per))
        tests[f"beats_c1_{per}"] = _test(c1 is not None and c1["lift"] > 0 and c1["short"] == 0,
                                         **({} if c1 is None else {k: c1[k] for k in ("lift", "mean", "p95", "p_beat", "fallback_share",
                                                                                      "short", "pool_trades")}))
        if member.get("l2"):
            c2 = blk.get("c2")
            ok = tr is not None and c2 is not None and len(c2) >= 2
            nets = [_net(x) for x in c2] if c2 is not None else []
            tests[f"beats_c2_{per}"] = _test(ok and _net(tr) - float(np.mean(nets)) > 0, c2_nets=nets,
                                             lift=None if not ok else round(_net(tr) - float(np.mean(nets)), 2))
        st = blk.get("stress")
        tests[f"stress_{per}"] = _test(st is not None and _net(st) > 0, base=None if tr is None else _net(tr),
                                       stressed=None if st is None else _net(st), stress="2 ticks + 250 ms")
    bar = member.get("nulls_bar")
    tb_t = None if sb is None else (sb["t"] if sb["t"] is not None else 0.0)
    tests["above_best_of_nulls_build"] = _test(bar is not None and bar.get("stat", "t") == "t" and tb_t is not None
                                               and tb_t > float(bar["bar"]), t_build=tb_t,
                                               bar=None if bar is None else bar.get("bar"), nulls=None if bar is None else bar.get("nulls"),
                                               thin=None if bar is None else bar.get("thin"))
    n_all = (sb["trades"] if sb else 0) + (sp["trades"] if sp else 0)
    tests["min_trades"] = _test(n_all >= MIN_TRADES, build=sb["trades"] if sb else None, pick=sp["trades"] if sp else None,
                                need=MIN_TRADES)
    both = (tb or []) + (tp or [])
    if both:
        loss = np.array([abs(t.get("mae_usd") or 0.0) / MICRO_DIV + MICRO_RT_USD for t in both])
        worst, p99 = float(loss.max()), float(np.percentile(loss, 99))
        tests["open_loss_fits"] = _test(math.floor(LOSS_LIMIT_USD / worst) >= 1, worst_open_loss_per_micro=round(worst, 2),
                                        micros_fit_worst=int(math.floor(LOSS_LIMIT_USD / worst)),
                                        micros_fit_p99=int(math.floor(LOSS_LIMIT_USD / p99)), limit=LOSS_LIMIT_USD)
    else:
        tests["open_loss_fits"] = _test(False, worst_open_loss_per_micro=None)
    rat, cx = member.get("rationale"), member.get("complexity")
    tests["rationale"] = _test(isinstance(rat, str) and len(rat.strip()) >= 20 and isinstance(cx, int) and not isinstance(cx, bool)
                               and cx >= 1, complexity=cx)
    if member.get("weak"):
        tests["weak_margin"] = _test(tb_t is not None and tb_t >= WEAK_T, t_build=tb_t, need=WEAK_T,
                                     note="WEAK rationale / prior: every test with margin (t >= 3 on BUILD)")
    out = {"name": name, "admit": all(t["pass"] for t in tests.values()), "tests": tests,
           "failed": [k for k, t in tests.items() if not t["pass"]],
           "summary": {"build": sb, "pick": sp, "cell": member.get("cell"), "root": member.get("root"), "tf": member.get("tf"),
                       "sess": member.get("sess"), "family": member.get("family")}}
    if write:
        out["dir"] = str(write_member(member, out, members_dir))
    return out


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "NO"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def card(member: dict, result: dict) -> str:
    """card.md: rationale, WEAK / second-look / penalty / notes (member_meta gives them), the plateau table with its share
    verdicts (60 / 70 / 80 %; overall, by stop type, per reward ratio), the metric set per year then combined at 1 contract
    and sized to about $1,000 of risk, the period table, nulls, stress, complexity count."""
    t, s = result["tests"], result["summary"]
    pl = member.get("plateau") or {}
    L = [f"# {member['name']} — {'ADMITTED' if result['admit'] else 'REJECTED'}", "",
         f"* family `{member.get('family')}` · root {member.get('root')} · tf {member.get('tf')} · session {member.get('sess')} · "
         f"cell `{member.get('cell')}` · 1 contract, costs included",
         f"* inputs: `{json.dumps(member.get('inputs') or {}, sort_keys=True)}`",
         f"* **Rationale (written before testing):** {member.get('rationale') or 'MISSING'}"
         + ("  — **WEAK RATIONALE / WEAK PRIOR**" if member.get("weak") else ""),
         f"* Complexity count (rules + free parameters): {member.get('complexity')}",
         f"* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); "
         f"entries inside the session window only (hold_to = {member.get('hold_to') or 'day'})",
         f"* **WEAK:** {'YES — admission needs t >= ' + _fmt(WEAK_T) + ' on BUILD' if member.get('weak') else 'no'}",
         f"* **Second look:** {member.get('second_look') or 'no (2025-26 was never read for this family)'}",
         f"* **Penalty (EDGE_SPEC C):** {member.get('penalty') or 'none'}"
         + (" — needs the plateau on BUILD and PICK" if member.get("penalty") else "")]
    if member.get("mirror"):
        L.append(f"* Mirror unit: `{member['mirror']}` (the opposite value of the axis is a separate unit, judged on its own)")
    if member.get("notes"):
        L.append(f"* Notes: {member['notes']}")
    if not result["admit"]:
        L.append(f"* **Failed:** {', '.join(result['failed'])}")
    L += ["", "## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; "
              "the member is the CENTRAL cell, never the best)",
          "| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for per in ("build", "pick"):
        q = pl.get(per)
        if q:
            L.append(f"| {per} | {q.get('cells')} | {q.get('cells_all', q.get('cells'))} | {q.get('dead', 0)} | {q.get('duplicates', 0)} | "
                     f"{_fmt(q.get('median_net'))} | {_pct(q.get('share_pos'))} | {_fmt(q.get('pass'))} | "
                     f"{q.get('member')} | {_fmt(q.get('member_net'))} | {_fmt(q.get('best_net'))} |")
    for per in ("build", "pick"):
        q = pl.get(per)
        if q and q.get("shares"):
            L += ["", f"### Share of cells with net > 0 — {per} (verdict = median > 0 and share >= the bar; the binding bar is 60 %)"]
            L += shares_md(q)
    both = [x for per in ("build", "pick") for x in ((member.get(per) or {}).get("trades") or [])]
    if both:
        cals = [(member.get(per) or {}).get("calendar") for per in ("build", "pick") if (member.get(per) or {}).get("trades") is not None]
        cal = [d for c in cals for d in c] if cals and all(c for c in cals) else None
        L += ["", "## Per year, then combined (the member cell)"] + report_md(pack(both), member.get("root") or "NQ", cal)
    L += ["", "## Periods (the member cell)", "| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |",
          "|---|---|---|---|---|---|---|"]
    for per in ("build", "pick"):
        x = s.get(per)
        if x:
            L.append(f"| {per} | {x['trades']} | {_fmt(x['net'])} | {_fmt(x['t'])} | {_fmt(x['pf'])} | {_fmt(x['win'])} | "
                     f"{_fmt(t.get('stress_' + per, {}).get('stressed'))} |")
    L += ["", "## Nulls", "| test | pass | detail |", "|---|---|---|"]
    for k in ("beats_c1_build", "beats_c1_pick", "beats_c2_build", "beats_c2_pick", "above_best_of_nulls_build"):
        if k in t:
            L.append(f"| {k} | {_fmt(t[k]['pass'])} | " + ", ".join(f"{a} {_fmt(v)}" for a, v in t[k].items() if a != "pass") + " |")
    L += ["", "## Every admission test", "| test | pass | detail |", "|---|---|---|"]
    for k, v in t.items():
        L.append(f"| {k} | {_fmt(v['pass'])} | " + ", ".join(f"{a} {_fmt(x)}" for a, x in v.items() if a != "pass") + " |")
    L += ["", "EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.", ""]
    return "\n".join(L)


def write_member(member: dict, result: dict, members_dir=None) -> Path:
    """members/<name>/{spec.json, trades_build.json, trades_pick.json, daily.csv, card.md} for an ADMITTED member;
    members/_rejected/<name>/{spec.json, card.md} for a rejected candidate."""
    base = Path(members_dir) if members_dir is not None else MEMBERS          # members_dir: tests (tmp_path) only
    d = (base if result["admit"] else base / "_rejected") / member["name"]
    d.mkdir(parents=True, exist_ok=True)
    spec = {k: member.get(k) for k in ("name", "family", "root", "tf", "sess", "cell", "inputs", "rationale", "complexity", "weak",
                                        "l2", "penalty", "second_look", "mirror", "notes", "hold_to")}
    spec.update(admit=result["admit"], failed=result["failed"], tests=result["tests"], plateau=member.get("plateau"),
                nulls_bar=member.get("nulls_bar"), contracts=1, periods={"build": ["2021-09-22", "2023-12-31"],
                                                                         "pick": ["2024-01-01", "2024-12-31"]},
                written_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    (d / "spec.json").write_text(json.dumps(spec, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (d / "card.md").write_text(card(member, result))
    if result["admit"]:
        rows = []
        for per in ("build", "pick"):
            blk = member[per]
            (d / f"trades_{per}.json").write_text(json.dumps(blk["trades"], separators=(",", ":")))
            cal = blk.get("calendar") or sorted({t["date"] for t in blk["trades"]})
            rows += daily_rows(blk["trades"], cal, per)
        with (d / "daily.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, ["date", "period", "net", "worst_open_loss", "minutes_in_market"])
            w.writeheader()
            w.writerows(rows)
    return d


# ------------------------------------------------------------------ member runs (the Admit stage)

def member_meta(family: str, sess: str | None = None, variant: dict | None = None) -> dict:
    """The registry fields a member dict / card needs, in ONE call (so none is forgotten): rationale, complexity, l2, weak,
    penalty (the text only where it applies: donchian in pm, first_bar_mom everywhere -- families.penalty_for), second_look,
    notes, mirror ('dir=long' for a mirror family's variant), hold_to. admission(member) reads weak / penalty / l2."""
    import families
    import l2sim
    lib = families.library(family)
    axis = lib.get("mirror")
    return {"family": family, "rationale": lib["rationale"], "complexity": lib["complexity"], "l2": lib["l2"], "weak": lib["weak"],
            "penalty": families.penalty_for(family, sess), "second_look": lib.get("second_look"), "notes": lib.get("notes"),
            "mirror": f"{axis}={variant[axis]}" if axis and variant and axis in variant else (axis or None),
            "hold_to": l2sim.LIBRARY_HOLD}


def run_member(family: str, root: str, tf: str, variant: dict, exit_cell: dict, period: str, *, sess: str | None = None,
               stress: bool = False, build_plateau: dict | None = None, c2_seed: int | None = None, extra: dict | None = None,
               workers: int | None = None, key: str | None = None, ledger=None, days=None) -> dict:
    """ONE full run of a member cell over a period (counts 1 strategy run in the ledger; refused past the cap).
    period 'build' | 'pick'. A PICK run needs build_plateau = the candidate's BUILD plateau with pass True (PickSealed
    otherwise): PICK is read only for BUILD survivors. sess: the member's session (one of the seven) -- the run is the
    same instance run_menus used for it (that ONE session, hold_to = 'day': flat at 15:58 ET of the trade date, never at
    the session end); omit it for a time-fired family (its clock time is in `variant`). stress=True runs l2sim.STRESS
    (2 ticks + 250 ms). c2_seed: the feature-shuffle null of an L2 member. extra: Template L2 options (f_book / x_book /
    f_thin) laid over the cell. -> the l2sim result. days: tests only (nothing is recorded)."""
    import families
    import l2sim
    if period not in ("build", "pick"):
        raise ValueError("period: 'build' or 'pick' (EXAM is sealed)")
    if period == "pick" and not (isinstance(build_plateau, dict) and build_plateau.get("pass") is True):
        raise PickSealed("a PICK (2024) run is allowed only for a BUILD survivor: pass build_plateau=<its BUILD plateau, pass True>")
    cls = families.REGISTRY[family][0]
    lib = families.library(family)
    if root not in lib["roots"]:
        raise ValueError(f"{family} is not registered for root {root}")
    timed = "shift_seed" in cls.defaults()
    if not timed and sess not in SESS7:
        raise ValueError(f"sess: the member's session, one of {SESS7}")
    run_sess = "all" if timed else sess               # hold_to='day': ONE session per instance (as run_menus.cell_specs)
    params = {**families.unit_inputs(family, tf, run_sess), **variant, **exit_cell, **(extra or {}), "hold_to": l2sim.LIBRARY_HOLD}
    feats = families.features_for(family, l2sim.template_feature_needs(params), c2_seed)
    key = key or "-".join(x for x in (family, root, f"tf{tf}", "" if timed else sess, l2sim.cell_id({**variant, **exit_cell}),
                                      l2sim.cell_id(extra) if extra else "", period, "stress" if stress else "",
                                      f"c2s{c2_seed}" if c2_seed is not None else "") if x)
    kw = dict(l2sim.STRESS) if stress else {}
    kw.update(getattr(cls, "SCREEN_RUN", {}))
    if days is None:
        ledger_check(runs=1, path=ledger)
        res = l2sim.run(cls, params, period=period, root=root, features=feats, workers=workers or l2sim.MAX_WORKERS, **kw)
        ledger_add("member", key, "run", family=family, root=root, tf=str(tf), period=period, path=ledger,
                   control="c2" if c2_seed is not None else ("stress" if stress else ""), seed="" if c2_seed is None else c2_seed,
                   trades=len(res["trades"]), elapsed_s=res["elapsed_s"])
    else:
        res = l2sim.run(cls, params, days=list(days), root=root, features=feats, workers=workers or 1, **kw)
    if not timed:
        res["trades"] = [t for t in res["trades"] if l2sim.session_of(t["entry_ms"]) == sess]
    res["key"], res["session"] = key, (None if timed else sess)
    return res


def main(argv=None) -> int:
    """python library.py ledger            counts against the caps (+ the null cells, tracked apart)
       python library.py plateau <unit key> [--sess pm]     the plateau of a unit store, per session and per MIRROR unit
       python library.py report  <unit key> [--sess pm]     unit_report_md: shares + verdicts, the central cell per year
                                                            (both print RESULTS: the Admit stage only)"""
    import argparse
    ap = argparse.ArgumentParser(prog="library.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ledger")
    for name in ("plateau", "report"):
        pl = sub.add_parser(name)
        pl.add_argument("key")
        pl.add_argument("--sess", default="")
    a = ap.parse_args(argv)
    if a.cmd == "ledger":
        used = ledger_used()
        print(json.dumps({"used": used, "caps": CAPS, "left": {k: CAPS[k] - used[k] for k in CAPS}, "null_cells": ledger_nulls(),
                          "rows": len(read_ledger())}))
        return 0
    u = load_unit(a.key)
    for s in ([a.sess] if a.sess else unit_sessions(u)):
        if a.cmd == "report":
            print(unit_report_md(u, s))
            continue
        for label, pl in judge(u, s).items():
            print(s, label or "-", json.dumps(pl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
