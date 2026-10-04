#!/usr/bin/env python3
"""Stage A screen ANALYSIS of the NQ Level-2 pilot (SPEC.md "Stage A screen"; the screen runner's bundles under runs/).
This is the implementation module; the command line is `screen_analyze.py` (same directory), which only calls `main()` here.
(The code cannot live in a module NAMED screen_analyze: the previous pilot has a module of that name which its own code
imports lazily -- R/wf_offline.py, a3p3.py ... through score.walk_forward -- and L comes before R on sys.path.)

    python screen_analyze.py score  [--workers 8] [--only fam[,fam]] [--firms f[,f]]   the firm searches + C1 / C2 lifts (cached)
    python screen_analyze.py nullc1 [--workers 8]                                     the C1 lift of the C2 nulls themselves
    python screen_analyze.py gates                                                    G1-G3 on the approved picks
    python screen_analyze.py stress [--workers 8]                                     stress re-runs of the top 15 + their scores
    python screen_analyze.py report                                                   out/screen_table.csv + out/screen_summary.md
    python screen_analyze.py status

Nothing here tunes anything: every family runs its pre-registered defaults, every search is score.py's (R's pass-3 eval grid,
R's funded grid, apex300.GRID). No row dated >= 2025-01-01 is read (score.py and l2sim raise on it). Writes only under L/out
(+ runs/<key>-stress and 'stress' ledger rows through screen.run_job). Heavy steps honour the offline compute windows (score.py
/ l2sim wait them out) and use <= 8 processes.

EVERY RULE BELOW WAS WRITTEN BEFORE ANY SCORED NUMBER OF THIS SCREEN WAS LOOKED AT (2026-10-02 ~02:00 ET), except where a
paragraph says AMENDED / written later, with its time.

PRIMARY BREACH MODEL (AMENDED 2026-10-02 09:30 ET, after the first complete pass had been read): SPEC.md gained "USER FACTS
2026-10-02 07:20 ET -- OVERRIDE everything above" while the first pass was running: Lucid's drawdown counts open losses, so the
primary model of EVERY account is `intraday`; realized / eod are side columns. The first pass scored the seven Lucid accounts
with `realized` as primary (cache namespace '<firm>'); they were scored again with `intraday` as primary (namespace
'<firm>@intraday': the search's p5_intraday pick for evals, search_funded(model='intraday') for funded, lifts, nulls, null C1
lifts, stress, shortlist). The first pass is kept as side columns (realized_pick_*). Apex accounts were real-time from the
start (eval: intraday; PA / 300K eval: the conservative event order 'pess'): unchanged. Bars under intraday: `baseline()`.
Also added then, for the SPEC's "APPROACH CHANGE" (edge library): per config the build (to 2023-12-31) / pick-year (2024)
split of the 1 NQ net and the stop size (period_extra) -- descriptive columns, no decision uses them.

CONFIG = family x tf x session (asia, london, nyam, mid, pm; dir both = the registered default). Sessions are split offline.
VARIANTS per config: real, c2s1, c2s2 (the screen's two feature-shuffle nulls).

1 Descriptive (1 NQ): trades, net, t-stat of the trade P&L, PF, max drawdown (cumulative net in exit order), win rate, for
  both / long / short and for each C2 seed. raw lift = real net - mean(C2 net); spread = half the range of the two seeds.
2 Firms. Eval (lucid, lucidpro, lucidpro_nodll, apex, apex_eod): score.search_rules -> the 'primary' pick = the cell with the
  best STABLE P(pass <= 5 d) under the primary model (first pass: Lucid realized, Apex intraday; now intraday for all, see
  PRIMARY BREACH MODEL above); headline metric = P5 of that cell;
  also its bust, the eod / realized / intraday P5 of that cell and each model's own stable pick. apex300_eval: the stable
  P(pass <= 20 d) pick (P10 beside it). Funded (flex, flex_dll, pro_dll, pro_nodll, apex50_pa, apex300_pa; start fresh,
  conservative consistency, compliance enforced: Apex picks come from compliant cells only): score.search_funded -> the
  'e40_stable' pick; headline metric = its E[$ to trader in 40 trading days]; P(payout <= 20 / 40 d), P(bust before first payout).
  A config that fails an Apex criterion at the SMALLEST grid size with no day rule (one direction; stop <= 5 x target, which
  in apex300.compliance also fails on any trade whose stop is >= 80% of the trailing threshold) has no compliant cell at any
  size: no search, no metric (status noncompliant_static; open_dir = no target by design). A null without a compliant cell
  has no optimised metric: the C2 lift of that cell is 'not comparable' = NOT PASSED (written 04:35 ET, before any Apex PA
  lift was looked at).
  Lifts (real configs only), at the pick's cell:
    C1 = score.lift_vs_control(day-matched random, K = 10, score.c1_pool of the run's exit profile; pool flag reported)
    C2 direct = the same cell on the two C2 null bundles (mode='direct')
    C2 opt = real pick metric - mean of the two nulls' OWN pick metric (the null gets its own optimised rules: R's 'optimised
             null'); spread = half the range of the two null picks.  THIS is the C2 lift used for every decision below.
  C2 reading rule (FAMILIES.md, walls addendum; pre-registered for B4 / B5): a C2 seed is informative only if its trade count
  in the session is >= 0.5 x the real one; else the cell's C2 lift is UNINFORMATIVE = NOT PASSED. For the other families the
  same ratio is reported as a flag only (c2_count_flag when a seed is < 0.5 x or > 2 x the real count).
3 Baseline: out/baseline_insample.json (the approved picks) next to every firm; flex_dll and apex50_pa have no cell of their
  own in that file, so the Flex funded pick is scored under flex_dll and the Apex PA pick under apex50_pa (labelled).
4 Gates: per approved pick x G1-G3 at the pick's approved cell(s) (gates.cell / score_cell / lift_cell): kept trades, net and
  PF in the pick's session against the ungated pick and the two permutation nulls, firm metric against both. A G3 cell over
  the firm's micro cap is scored at the cap-compliant unit against the pick at the same size (base_same_size).
5 Stress (l2sim.STRESS: 2 ticks, 250 ms): QUALIFYING cell = (config, firm) with status ok, C1 lift > 0 and C2 opt lift > 0 on
  the primary model, C2 informative. Cell strength = min(C1 lift, C2 opt lift). TOP 15 CONFIGS = round robin over the firms in
  the fixed order FIRMS: rank 1, 2, ... of each firm's qualifying configs by strength, added until 15 distinct configs. The
  stress runs are the distinct family x tf of those 15 (stage 'stress' in ledger.csv, not counted in the cap). Every
  qualifying cell of a stressed family x tf is then re-scored on the stressed bundle AT THE SAME CELL (no re-search):
  stress lift C1 = stressed metric - the C1 control mean, stress lift C2 = stressed metric - the mean optimised-null metric
  (controls are NOT stressed: the conservative reading). survives = both > 0.
6 Multiple testing: per firm, null p95 = the 95th percentile of the null picks' metric in the firm x session stratum (pooled
  per firm when a stratum has < 20 nulls); count of real configs above it against 5% expected by chance.
  AMENDED 2026-10-02 02:20 ET, AFTER the first partial results (the three Lucid evals) were looked at, and disclosed in the
  summary: the session stratum mixes exit profiles, and its p95 turned out to be set by the open_dir nulls alone (3 ATR30
  stop, no target: P5 .55-.70 for the NULL), so open_dir cells would clear "p95" about half the time by construction and
  no other family ever could. The stratum is now R's own convention (a3p3_merge: same firm, same exit-profile group,
  fallback to the pooled group below 20 nulls): firm x EXIT GROUP x session, exit group = atr (1.5 ATR x 2R: B1-B3, F1-F4) |
  wall (struct stop: B4, B5) | open (O1). This is STRICTER for the family that looked best (open_dir) and fairer to the
  rest. The count under the original session-only stratum stays in the table (above_null_p95_session_only). Added at the
  same time, as a like-for-like diagnostic only (no decision uses it): 'real above both of its own two nulls' (1/3 by chance).
  Family verdict (family = registry name; its cells = tf x session x firm with a metric):
    'information beats both nulls'  if  cells above the null p95 >= the 5% critical count of Binomial(cells, 0.05)
                                        AND more than half of the cells have C2 opt lift > 0 AND more than half C1 lift > 0
                                        AND the family's raw net at 1 NQ (all tfs, all sessions) is above BOTH C2 seeds' net
    'worse'                         if  fewer than 40% of the cells have C2 opt lift > 0 AND the raw net is below the mean C2 net
    'no better than shuffled book'  otherwise.
  (The 12 firms score the same trades, so the binomial count is generous to the family: stated in the summary.)
7 Shortlist for stage B: per account type the qualifying cells that were stressed and survive, best 8 by strength; intraday
  numbers beside them; Apex compliance marked; cells with net <= 0 at 1 NQ, a C2 count flag or a NEAREST C1 pool are flagged.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

import numpy as np

L = Path(__file__).resolve().parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))

RUNS = L / "runs"
OUT = L / "out"
CACHE = Path(os.environ.get("L2_ANALYZE_CACHE") or (OUT / "screen_analyze_cache"))
LOG = OUT / "screen_analyze.log"
SESSIONS = ("asia", "london", "nyam", "mid", "pm")
SEEDS = (1, 2)
VARIANTS = ("real", "c2s1", "c2s2")
K_C1 = 10
BOOTS = 1000
N_TOP = 15
N_SHORT = 8
MAX_WORKERS = 8
WALL_FAMS = ("wall_bounce", "wall_break")            # the pre-registered C2 informativeness rule applies (FAMILIES.md)
NOT_HAND = ("wall_bounce", "wall_break")             # FAMILIES.md walls addendum item 7: not hand-executable -> no Apex PA candidate
REVISIT = {"open_dir_flow": "REVISIT of a refuted family", "open_dir_both": "contains the REVISIT signal"}

# account types in the fixed order used everywhere (round robin of the stress top 15 included)
FIRMS = {
    "lucid": dict(kind="eval", prim="intraday", side="realized", label="Lucid Flex eval", unit="P5", cost=1),
    "lucidpro": dict(kind="eval", prim="intraday", side="realized", label="Lucid Pro DLL eval", unit="P5", cost=1),
    "lucidpro_nodll": dict(kind="eval", prim="intraday", side="realized", label="Lucid Pro noDLL eval", unit="P5", cost=1),
    "apex": dict(kind="eval", prim="intraday", label="Apex 50K eval", unit="P5", cost=2),
    "apex_eod": dict(kind="eval", prim="intraday", label="Apex 50K EOD eval", unit="P5", cost=2),
    "apex300_eval": dict(kind="eval300", prim="pess", label="Apex 300K eval", unit="P20", cost=2),
    "flex": dict(kind="funded", prim="intraday", side="realized", label="Flex funded", unit="E$40", cost=10),
    "flex_dll": dict(kind="funded", prim="intraday", side="realized", label="Flex+DLL funded", unit="E$40", cost=10),
    "pro_dll": dict(kind="funded", prim="intraday", side="realized", label="Pro DLL funded", unit="E$40", cost=10),
    "pro_nodll": dict(kind="funded", prim="intraday", side="realized", label="Pro noDLL funded", unit="E$40", cost=10),
    "apex50_pa": dict(kind="funded", prim="pess", label="Apex 50K PA", unit="E$40", cost=30, apex=True),
    "apex300_pa": dict(kind="funded", prim="pess", label="Apex 300K PA", unit="E$40", cost=100, apex=True),
}
EVAL_AX = ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take")
FUND_AX = ("micros", "day_take", "day_lock", "day_stop", "max_day_tr", "policy")


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    OUT.mkdir(exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")


def _js(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o).__name__)


def _write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, default=_js))
    tmp.replace(p)


# ------------------------------------------------------------------ the screen's runs

def run_key(fam_tf: str, variant: str = "real") -> str:
    return fam_tf if variant == "real" else f"{fam_tf}-{variant}"


def screen_keys(ledger=None) -> list:
    """The real screen runs of the ledger -> [{'key', 'family', 'tf', 'inputs'}], in ledger order."""
    out = []
    with open(ledger or (L / "ledger.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            if r["stage"] == "screen" and not r["control"]:
                out.append({"key": r["key"], "family": r["family"], "tf": r["tf"], "inputs": json.loads(r["inputs_json"])})
    return out


_TR_CACHE: dict = {}


def load_rows(key: str, runs=None) -> list:
    """trades.json of a bundle + the session of every row (l2sim.session_of on entry_ms = the offline split, as R)."""
    k = (str(runs or RUNS), key)
    if k not in _TR_CACHE:
        import l2sim
        rows = json.loads((Path(runs or RUNS) / key / "trades.json").read_text())
        rows = rows if isinstance(rows, list) else rows.get("trades", [])
        for t in rows:
            if t["date"] >= "2025-01-01":
                raise RuntimeError(f"{key}: a row dated {t['date']} (holdout is sealed)")
            t["_sess"] = l2sim.session_of(t["entry_ms"])
        _TR_CACHE[k] = rows
    return _TR_CACHE[k]


def trade_stats(rows: list) -> dict:
    """trades, net, t-stat of the trade P&L, profit factor, max drawdown (cumulative net in exit order), win rate."""
    n = len(rows)
    if not n:
        return {"trades": 0, "net": 0.0, "t": None, "pf": None, "maxdd": 0.0, "win": None}
    rows = sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"]))
    x = np.array([t["net"] for t in rows], float)
    sd = float(x.std(ddof=1)) if n > 1 else 0.0
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.maximum(cum, 0.0)) - cum).max())
    gw, gl = float(x[x > 0].sum()), float(-x[x < 0].sum())
    return {"trades": n, "net": float(x.sum()), "t": float(x.mean() / (sd / math.sqrt(n))) if sd > 0 else None,
            "pf": (gw / gl) if gl > 0 else None, "maxdd": dd, "win": float((x > 0).mean())}


def split_stats(key: str, runs=None) -> dict:
    """{(sess, dir): trade_stats} for sess in SESSIONS + 'all', dir in both / long / short."""
    rows = load_rows(key, runs)
    out = {}
    for s in SESSIONS + ("all",):
        rs = rows if s == "all" else [t for t in rows if t["_sess"] == s]
        for d in ("both", "long", "short"):
            out[(s, d)] = trade_stats(rs if d == "both" else [t for t in rs if t["side"] == d])
    return out


BUILD_END = "2023-12-31"                             # SPEC 'USER FACTS': build 2021-09-22 -> 2023-12-31, pick = 2024 (both in-sample)
PV_USD = 20.0                                        # $ per NQ point


def period_extra(key: str, sess: str) -> dict:
    """Build / pick-year split and stop size of one config at 1 NQ (for the edge-library admission: net > 0 in BOTH periods,
    an open-loss risk that can be sized inside $2,000)."""
    rows = [t for t in load_rows(key) if t["_sess"] == sess]
    b, pk = trade_stats([t for t in rows if t["date"] <= BUILD_END]), trade_stats([t for t in rows if t["date"] > BUILD_END])
    stops = [abs(t["entry_price"] - t["sl"]) * PV_USD for t in rows if t.get("sl") is not None]
    mae = [abs(t.get("mae_usd") or 0.0) for t in rows]
    return {"trades_build": b["trades"], "net_build": round(b["net"], 2), "t_build": b["t"], "trades_pick2024": pk["trades"], "net_pick2024": round(pk["net"], 2),
            "t_pick2024": pk["t"], "stop_usd_median_1nq": float(np.median(stops)) if stops else None,
            "stop_usd_p95_1nq": float(np.percentile(stops, 95)) if stops else None, "mae_usd_p95_1nq": float(np.percentile(mae, 95)) if mae else None}


def sess_counts(key: str) -> dict:
    c = defaultdict(int)
    for t in load_rows(key):
        c[t["_sess"]] += 1
    return dict(c)


# ------------------------------------------------------------------ scoring one (run, session, firm)

def ns(firm: str, side: bool = False) -> str:
    """Cache namespace of an account: '<firm>' for the firm's own default model (Apex accounts; the Lucid accounts' SIDE view =
    the superseded realized-balance model), '<firm>@intraday' for the Lucid accounts under the primary model."""
    return firm if (side or "side" not in FIRMS[firm]) else f"{firm}@{FIRMS[firm]['prim']}"


def prim_of(firm: str, side: bool = False) -> str:
    return FIRMS[firm]["side"] if side and "side" in FIRMS[firm] else FIRMS[firm]["prim"]


def cache_path(firm: str, key: str, sess: str, side: bool = False) -> Path:
    return CACHE / ns(firm, side) / f"{key}__{sess}.json"


def _eval_rules(cell: dict) -> dict:
    return {k: cell[k] for k in ("day_lock", "day_take", "day_stop", "max_day_tr", "target_take")}


def _fund_rules(cell: dict) -> dict:
    return {k: cell[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}


def _gate_kw(firm: str, family: str, inputs: dict) -> dict:
    """strategy / inputs for the Apex compliance gate (one direction is proven from the simulator's row stamps)."""
    return {"strategy": family, "inputs": dict(inputs)} if FIRMS[firm].get("apex") else {}


def metric_at(src, firm: str, cell: dict, sess, *, family: str = "", inputs: dict | None = None, boots: int = 0) -> dict:
    """Headline metric of ANY source at a fixed cell (no search): -> {'metric', 'bust', 'models': {model: {...}}, ...}."""
    import score as S
    kind, prim = FIRMS[firm]["kind"], FIRMS[firm]["prim"]
    if kind == "eval":
        r = S.score_eval(src, firm, _eval_rules(cell), prim, micros=cell["micros"], sess=sess, boots=boots)
        if "models" not in r:
            return {"metric": 0.0, "bust": 0.0, "models": {}, "skipped": r.get("skipped")}
        out = {"metric": r["p5"], "bust": r["bust5"], "p1": r["p1"], "p3": r["p3"],
               "models": {m: {"p5": v["p5"], "bust": v["bust5"], "p1": v["p1"], "p3": v["p3"], "ci": v.get("ci_p5")} for m, v in r["models"].items()},
               "cap_ok": r["walk"]["cap_ok"], "cost_ok": r["cost"]["ok_lt_3pct"]}
        return out
    if kind == "eval300":
        r = S.score_apex300_eval(src, _eval_rules(cell), micros=cell["micros"], sess=sess, boots=boots, variants=False)
        if "models" not in r:
            return {"metric": 0.0, "bust": 0.0, "models": {}, "skipped": r.get("skipped")}
        return {"metric": r["p_pass_20"], "bust": r["bust_20"], "p10": r["p_pass_10"],
                "models": {m: {"p20": v["p_pass_20"], "p10": v["p_pass_10"], "bust": v["bust_20"], "ci": v.get("ci_p20")} for m, v in r["models"].items()},
                "compliance": r.get("compliance"), "compliant": r.get("compliant")}
    r = S.score_funded(src, firm, cell["policy"], micros=cell["micros"], rules=_fund_rules(cell), sess=sess, boots=boots,
                       model=(None if FIRMS[firm].get("apex") else prim), **_gate_kw(firm, family, inputs or {}))
    if "models" not in r:
        return {"metric": 0.0, "bust": 0.0, "models": {}, "skipped": r.get("skipped")}
    out = {"metric": r["e_net_40"], "bust": r["p_bust_pre_first"], "p20": r["p_pay_20"], "p40": r["p_pay_40"], "med_days": r["med_days_first"],
           "ci": r.get("e_net_40_ci"),
           "models": {m: {"e40": v["e_net_40"], "p20": v["p_pay_20"], "p40": v["p_pay_40"], "bust": v["p_bust_pre_first"]} for m, v in r["models"].items()}}
    if FIRMS[firm].get("apex"):
        out.update(compliance=r.get("compliance"), compliant=r.get("compliant"), apex_flags=r.get("apex_flags"),
                   one_direction_basis=r.get("one_direction_basis"),
                   cons_alt_e40=(r.get("cons_alt") or {}).get(r["model"], {}).get("e_net_40"))
    return out


def _static_fail(src, firm: str, sess, family: str, inputs: dict):
    """Apex PA: None when the two STATIC criteria hold, else the compliance dict (no cell can be compliant: skip the search)."""
    import score as S
    r = S.score_funded(src, firm, 500, micros=10, rules={}, sess=sess, boots=0, **_gate_kw(firm, family, inputs))
    c = r.get("compliance") or {}
    if c.get("one_direction") == "ok" and c.get("stop_5x_target") == "ok":
        return None
    return c or {"one_direction": "UNCHECKED", "stop_5x_target": "UNCHECKED"}


def apex_search(src, firm: str, sess, family: str, inputs: dict, grid: dict | None = None) -> dict:
    """score.search_funded for an apex300.py firm WITHOUT the second lifecycle of every cell under the other consistency
    reading (apex300.search(both_cons=False)): the same members, port, grid, gate, eligible rows and picks, at half the time.
    The other reading of the PICKED cell comes from score.score_funded (`metric_at` -> cons_alt_e40). Equality with
    score.search_funded is a test (tests/test_screen_analyze.py)."""
    import score as S
    ax = S._ext()
    spec = S.funded_spec(firm)
    mem, cal = S._prep(src, sess, None, "all", None, False, "raise")
    port = S._port10(mem, cal)
    S.desk_window_wait()
    g = S.funded_grid(spec, grid)
    rows = ax.search(port, spec, g, None, S.H_FUNDED, 1, "fresh", strategy=family, inputs=dict(inputs), both_sides=None,
                     trades=S._raw_members(mem), allow_holdout=False, both_cons=False)
    ok = ax.compliant(rows)
    gate = {k: sorted({r[k] for r in rows}) for k in ("apex_one_direction", "apex_stop_5x_target", "apex_mae_rule")}
    return {"rows": rows, "eligible": len(ok), "picks": S.F.pick_cells(ok), "gate": gate, "grid": g}


def search_pick(src, firm: str, sess, *, family: str, inputs: dict, boots: int = 0) -> dict:
    """The firm's rule search on one source -> the stability pick: {'status', 'cell', 'metric', 'bust', 'stab', 'raw_max', ...}."""
    import score as S
    kind, prim = FIRMS[firm]["kind"], FIRMS[firm]["prim"]
    if kind == "eval":
        r = S.search_rules(src, firm, sess=sess, boots=boots)
        pk = r["picks"][f"p5_{prim}"]                             # the stable pick under THIS analysis' primary model
        md = pk["models"]
        out = {"status": "ok", "cell": pk["rules"], "stab": pk["stab"], "raw_max": pk["raw_max"], "metric": md[prim]["p5"], "bust": md[prim]["bust5"],
               "p1": md[prim]["p1"], "p3": md[prim]["p3"], "ci": md[prim].get("ci_p5"), "cells": r["cells"], "net_rules": pk["net_rules"],
               "executed": pk["executed"],
               "models": {m: {"p5": v["p5"], "bust": v["bust5"]} for m, v in md.items()},
               "own": {m: {"stab": r["picks"][f"p5_{m}"]["stab"], "p5": r["picks"][f"p5_{m}"]["models"][m]["p5"],
                           "bust": r["picks"][f"p5_{m}"]["models"][m]["bust5"], "cell": r["picks"][f"p5_{m}"]["rules"]} for m in md}}
        return out
    if kind == "eval300":
        r = S.search_rules(src, firm, sess=sess, boots=boots)
        if not r["picks"]:
            return {"status": "no_cell", "metric": None}
        pk = r["picks"]["primary"]
        d = pk["detail"]
        if "models" not in d:
            return {"status": "no_cell", "metric": None}
        return {"status": "ok", "cell": pk["rules"], "stab": pk["stab"], "raw_max": pk["raw_max"], "metric": d["p_pass_20"], "bust": d["bust_20"],
                "p10": d["p_pass_10"], "ci": d.get("ci_p20"), "med_days": d.get("med_days"), "cells": r["cells"],
                "models": {m: {"p20": v["p_pass_20"], "p10": v["p_pass_10"], "bust": v["bust_20"]} for m, v in d["models"].items()},
                "compliance": d.get("compliance"), "compliant": d.get("compliant")}
    if FIRMS[firm].get("apex"):
        bad = _static_fail(src, firm, sess, family, inputs)
        if bad is not None:
            return {"status": "noncompliant_static", "metric": None, "compliance": bad}
    r = (apex_search(src, firm, sess, family, inputs) if FIRMS[firm].get("apex") else
         S.search_funded(src, firm, sess=sess, workers=1, model=prim))
    pk = r["picks"].get("e40_stable")
    if not pk:
        return {"status": "no_compliant_cell", "metric": None, "cells": len(r["rows"]), "eligible": r["eligible"], "gate": r.get("gate")}
    cell = {a: pk[a] for a in FUND_AX}
    out = {"status": "ok", "cell": cell, "stab": pk["stab_e_net_40"], "raw_max": max(x["e_net_40"] for x in r["rows"]), "metric": pk["e_net_40"],
           "bust": pk["p_bust_pre_first"], "p20": pk["p_pay_20"], "p40": pk["p_pay_40"], "med_days": pk["med_days_first"],
           "cells": len(r["rows"]), "eligible": r["eligible"]}
    if FIRMS[firm].get("apex"):
        out.update(gate=r.get("gate"), mae_over=pk.get("mae_over_limit_share"))
    return out


def _lift_models(lv: dict, kind: str) -> dict:
    out = {}
    for m, v in (lv.get("models") or {}).items():
        if kind == "funded":
            out[m] = {"real": v["real_e40"], "ctrl": v["ctrl_e40"], "ctrl_sd": v.get("ctrl_e40_sd"), "lift": v["lift_e40"], "each": v.get("ctrl_e40_each")}
        else:
            out[m] = {"real": v["real_p5"], "ctrl": v["ctrl_p5"], "ctrl_sd": v.get("ctrl_p5_sd"), "lift": v["lift"], "ci": v.get("ci"),
                      "each": v.get("ctrl_p5_each")}
    return out


def lifts(src, firm: str, cell: dict, sess, *, key: str, family: str, inputs: dict, null_srcs: list, boots: int = BOOTS) -> dict:
    """C1 (day-matched random, K = 10) and C2 direct (the two null bundles) lifts of a config at its pick's cell.
    null_srcs = [] -> C1 only (used for the C2 null configs themselves: the null distribution of the C1 lift)."""
    import score as S
    kind, prim = FIRMS[firm]["kind"], FIRMS[firm]["prim"]
    pool = S.c1_pool(dict(inputs))
    out = {"c1_pool_exact": pool["exact"], "c1_pool_flag": pool["flag"]}
    if kind == "eval300":                                        # lift_vs_control knows R's eval firms only: the same recipe by hand
        real = metric_at(src, firm, cell, sess)
        cs = S.daymatched(src, pool["srcs"], sess=sess, K=K_C1, label=key)
        cm = [metric_at(S._ctl_tr(c), firm, cell, "all") for c in cs]
        out["c1"] = {"K": len(cs), "fallback_share": float(np.mean([c["fb_share"] for c in cs])) if cs else 0.0, "short": int(sum(c["short"] for c in cs)),
                     "ctrl_trades": [int(c["n"]) for c in cs],
                     "models": {m: {"real": real["models"][m]["p20"], "ctrl": float(np.mean([x["models"][m]["p20"] if x["models"] else 0.0 for x in cm])),
                                    "lift": float(real["models"][m]["p20"] - np.mean([x["models"][m]["p20"] if x["models"] else 0.0 for x in cm]))}
                                for m in real["models"]}}
        if not null_srcs:
            return out
        nm = [metric_at(n, firm, cell, sess) for n in null_srcs]
        out["c2d"] = {"K": len(nm), "ctrl_trades": None,
                      "models": {m: {"real": real["models"][m]["p20"], "ctrl": float(np.mean([x["models"][m]["p20"] if x["models"] else 0.0 for x in nm])),
                                     "each": [x["models"][m]["p20"] if x["models"] else 0.0 for x in nm],
                                     "lift": float(real["models"][m]["p20"] - np.mean([x["models"][m]["p20"] if x["models"] else 0.0 for x in nm]))}
                                 for m in real["models"]}}
        return out
    b = None
    if kind == "eval":
        kw = dict(micros=cell["micros"], sess=sess, boots=boots)
        a = S.lift_vs_control(src, pool["srcs"], firm, _eval_rules(cell), K=K_C1, label=key, **kw)
        if null_srcs:
            b = S.lift_vs_control(src, null_srcs, firm, _eval_rules(cell), mode="direct", **kw)
    else:
        kw = dict(micros=cell["micros"], sess=sess, kind="funded", policy=cell["policy"], boots=0)
        a = S.lift_vs_control(src, pool["srcs"], firm, _fund_rules(cell), K=K_C1, label=key, **kw)
        if null_srcs:
            b = S.lift_vs_control(src, null_srcs, firm, _fund_rules(cell), mode="direct", **kw)
    k2 = "funded" if kind == "funded" else "eval"
    out["c1"] = {"K": a.get("K"), "fallback_share": a.get("fallback_share"), "short": a.get("short"), "ctrl_trades": a.get("ctrl_trades"),
                 "skipped": a.get("skipped"), "models": _lift_models(a, k2)}
    if b is not None:
        out["c2d"] = {"K": b.get("K"), "ctrl_trades": b.get("ctrl_trades"), "skipped": b.get("skipped"), "models": _lift_models(b, k2)}
    return out


def nullc1_path(firm: str, key: str, sess: str, side: bool = False) -> Path:
    return CACHE / "_nullc1" / ns(firm, side) / f"{key}__{sess}.json"


def run_null_c1(t: dict) -> dict:
    """The C1 lift of a C2 NULL config at ITS OWN pick's cell (the null distribution of the C1 lift: a pick is the best of a
    rule grid, the controls are scored at that same cell, so the lift is biased upward for the null too)."""
    p = nullc1_path(t["firm"], t["key"], t["sess"])
    if p.exists():
        return {"cached": True}
    out = {k: t[k] for k in ("key", "fam_tf", "family", "tf", "variant", "sess", "firm")}
    t0 = time.monotonic()
    try:
        rec = json.loads(cache_path(t["firm"], t["key"], t["sess"]).read_text())
        if rec["status"] != "ok":
            out.update(status=rec["status"])
        else:
            lv = lifts(str(RUNS / t["key"]), t["firm"], rec["cell"], t["sess"], key=t["key"], family=t["family"], inputs=t["inputs"], null_srcs=[], boots=0)
            m = lv["c1"]["models"].get(FIRMS[t["firm"]]["prim"]) or {}
            out.update(status="ok", lift=m.get("lift"), ctrl=m.get("ctrl"), real=m.get("real"), skipped=lv["c1"].get("skipped"))
    except Exception as e:
        out.update(status="error", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
    out["elapsed_s"] = round(time.monotonic() - t0, 2)
    _write_json(p, out)
    return {"status": out["status"]}


def stage_null_c1(workers: int = MAX_WORKERS, firms=None) -> dict:
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing as mp
    import score as S
    todo = [t for t in tasks(None, firms) if t["variant"] != "real" and cache_path(t["firm"], t["key"], t["sess"]).exists()
            and not nullc1_path(t["firm"], t["key"], t["sess"]).exists()]
    workers = max(1, min(int(workers), MAX_WORKERS))
    _log(f"null C1 lifts: {len(todo)} tasks to run, workers {workers}")
    if not todo:
        return {"ran": 0}
    S.desk_window_wait()
    n, err, t0 = 0, 0, time.monotonic()
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init_worker) as ex:
        for f in as_completed([ex.submit(run_null_c1, t) for t in todo]):
            n += 1
            err += f.result().get("status") == "error"
            if n % 200 == 0:
                _log(f"null C1 lifts: {n}/{len(todo)} done ({err} errors), {time.monotonic() - t0:.0f} s")
    _log(f"null C1 lifts: finished {n} tasks, {err} errors, {time.monotonic() - t0:.0f} s")
    return {"ran": n, "errors": err}


def null_c1_stats(side: bool = False) -> dict:
    """{firm: {group: {n, mean, pos (share > 0), p95, max}}} of the C1 lift of the C2 null configs at their own picks;
    group = exit group ('atr' | 'wall' | 'open') or 'all'."""
    vals = defaultdict(list)
    for f in FIRMS:
        d = CACHE / "_nullc1" / ns(f, side)
        if d.exists():
            for p in d.glob("*.json"):
                r = json.loads(p.read_text())
                if r.get("status") == "ok" and r.get("lift") is not None:
                    vals[(f, exit_group(r["family"]))].append(float(r["lift"]))
                    vals[(f, "all")].append(float(r["lift"]))
    out = defaultdict(dict)
    for (f, g), v in vals.items():
        a = np.array(v)
        out[f][g] = {"n": len(a), "mean": float(a.mean()), "pos": float((a > 0).mean()), "p95": float(np.percentile(a, 95)), "max": float(a.max())}
    return dict(out)


def null_c1_p95(nc1: dict, firm: str, family: str):
    """The null's p95 C1 lift for a config: its firm x exit group (>= 20 nulls), else the firm's pooled nulls; None if not run."""
    d = nc1.get(firm, {})
    g = d.get(exit_group(family))
    if g and g["n"] >= 20:
        return g["p95"]
    return d["all"]["p95"] if "all" in d and d["all"]["n"] >= 20 else None


def run_task(t: dict) -> dict:
    """One (run key, session, firm): search + (real only) lifts. Cached as JSON; an exception is recorded, never raised."""
    p = cache_path(t["firm"], t["key"], t["sess"])
    if p.exists():
        return {"key": t["key"], "sess": t["sess"], "firm": t["firm"], "cached": True}
    t0 = time.monotonic()
    out = {k: t[k] for k in ("key", "fam_tf", "family", "tf", "variant", "sess", "firm", "n_trades")}
    try:
        src = str(RUNS / t["key"])
        if not t["n_trades"]:
            out.update(status="no_trades", metric=0.0, bust=0.0)
        else:
            out.update(search_pick(src, t["firm"], t["sess"], family=t["family"], inputs=t["inputs"], boots=BOOTS if t["variant"] == "real" else 0))
            if t["variant"] == "real" and out["status"] == "ok":
                det = metric_at(src, t["firm"], out["cell"], t["sess"], family=t["family"], inputs=t["inputs"], boots=BOOTS)
                out["at_pick"] = det
                try:
                    out["lifts"] = lifts(src, t["firm"], out["cell"], t["sess"], key=t["key"], family=t["family"], inputs=t["inputs"],
                                         null_srcs=[str(RUNS / run_key(t["fam_tf"], f"c2s{s}")) for s in SEEDS])
                except Exception as e:                           # a lift that cannot be computed is reported, the pick is kept
                    out["lifts_error"] = f"{type(e).__name__}: {e}"
                    out["lifts_trace"] = traceback.format_exc()[-1500:]
    except Exception as e:
        out.update(status="error", metric=None, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])
    out["elapsed_s"] = round(time.monotonic() - t0, 2)
    _write_json(p, out)
    return {"key": t["key"], "sess": t["sess"], "firm": t["firm"], "status": out["status"], "elapsed_s": out["elapsed_s"]}


def tasks(only=None, firms=None) -> list:
    out = []
    for k in screen_keys():
        if only and k["family"] not in only:
            continue
        for v in VARIANTS:
            rk = run_key(k["key"], v)
            cnt = sess_counts(rk)
            for s in SESSIONS:
                for f in (firms or FIRMS):
                    out.append({"key": rk, "fam_tf": k["key"], "family": k["family"], "tf": k["tf"], "inputs": k["inputs"], "variant": v, "sess": s,
                                "firm": f, "n_trades": int(cnt.get(s, 0))})
    out.sort(key=lambda t: (FIRMS[t["firm"]]["cost"], t["fam_tf"], t["sess"], t["variant"]))
    return out


def _init_worker():
    import score  # noqa: F401  (R's modules are imported once per worker)


def stage_score(workers: int = MAX_WORKERS, only=None, firms=None, reverse: bool = False) -> dict:
    """reverse: take the task list from its end (a second, small pool can then help the first one from the other side; a task
    both reach at the same moment is computed twice, with the same result)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing as mp
    import score as S
    todo = [t for t in tasks(only, firms) if not cache_path(t["firm"], t["key"], t["sess"]).exists()]
    if reverse:
        todo.reverse()
    workers = max(1, min(int(workers), MAX_WORKERS))
    _log(f"score: {len(todo)} tasks to run, workers {workers}")
    if not todo:
        return {"ran": 0}
    S.desk_window_wait()
    n, err, t0 = 0, 0, time.monotonic()
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init_worker) as ex:
        futs = [ex.submit(run_task, t) for t in todo]
        for f in as_completed(futs):
            r = f.result()
            n += 1
            err += r.get("status") == "error"
            if n % 50 == 0 or r.get("status") == "error":
                _log(f"score: {n}/{len(todo)} done ({err} errors), {time.monotonic() - t0:.0f} s; last {r['firm']} {r['key']} {r['sess']} {r.get('status')}")
    _log(f"score: finished {n} tasks, {err} errors, {time.monotonic() - t0:.0f} s")
    return {"ran": n, "errors": err}


def load_cache(side: bool = False) -> dict:
    """{(firm, run key, sess): record} of everything scored so far. side: the Lucid accounts under the superseded realized
    model (their first scoring pass), nothing for the other accounts."""
    out = {}
    for f in FIRMS:
        if side and "side" not in FIRMS[f]:
            continue
        d = CACHE / ns(f, side)
        if d.exists():
            for p in d.glob("*.json"):
                r = json.loads(p.read_text())
                out[(f, r["key"], r["sess"])] = r
    return out


# ------------------------------------------------------------------ cells: join real + nulls, lifts, null p95

def c2_ratio(fam_tf: str, sess: str) -> list:
    n = sess_counts(fam_tf).get(sess, 0)
    return [(sess_counts(run_key(fam_tf, f"c2s{s}")).get(sess, 0) / n) if n else None for s in SEEDS]


def build_cells(cache: dict, side: bool = False) -> list:
    """One dict per (config, firm): the real pick, the nulls' picks, the three lifts on the primary (and the intraday) model."""
    cells = []
    for k in screen_keys():
        for s in SESSIONS:
            ratio = c2_ratio(k["key"], s)
            for f, fm in FIRMS.items():
                r = cache.get((f, k["key"], s))
                if r is None:
                    continue
                nulls = [cache.get((f, run_key(k["key"], f"c2s{x}"), s)) for x in SEEDS]
                prim = prim_of(f, side)
                c = {"family": k["family"], "tf": k["tf"], "fam_tf": k["key"], "sess": s, "firm": f, "kind": fm["kind"], "status": r["status"],
                     "n_trades": r["n_trades"], "metric": r.get("metric"), "bust": r.get("bust"), "stab": r.get("stab"), "raw_max": r.get("raw_max"),
                     "cell": r.get("cell"), "rec": r, "c2_ratio": ratio, "inputs": k["inputs"],
                     "null_status": [n["status"] if n else "missing" for n in nulls],
                     "null_metric": [(n.get("metric") if n and n["status"] in ("ok", "no_trades") else None) if n else None for n in nulls]}
                c["c2_informative"] = all(x is not None and x >= 0.5 for x in ratio) if k["family"] in WALL_FAMS else True
                c["c2_count_flag"] = any(x is None or x < 0.5 or x > 2.0 for x in ratio)
                nm = [x for x in c["null_metric"] if x is not None]
                if r["status"] == "ok" and len(nm) == len(SEEDS):
                    c["c2_opt_null"] = float(np.mean(nm))
                    c["c2_opt_spread"] = float((max(nm) - min(nm)) / 2)
                    c["c2_opt_lift"] = float(r["metric"] - np.mean(nm))
                lv = r.get("lifts") or {}
                for nm_, tag in (("c1", "c1"), ("c2d", "c2d")):
                    m = ((lv.get(nm_) or {}).get("models") or {})
                    if prim in m:
                        c[f"{tag}_lift"], c[f"{tag}_ctrl"] = m[prim]["lift"], m[prim]["ctrl"]
                        c[f"{tag}_ci"] = m[prim].get("ci")
                    alt = (fm["prim"] if side else fm.get("side")) if "side" in fm else None
                    if alt and alt in m:
                        c[f"{tag}_lift_side"] = m[alt]["lift"]
                c["c1_pool_exact"] = lv.get("c1_pool_exact")
                c["c1_fallback"] = (lv.get("c1") or {}).get("fallback_share")
                c["qualifies"] = bool(r["status"] == "ok" and c.get("c1_lift") is not None and c.get("c2_opt_lift") is not None
                                      and c["c1_lift"] > 0 and c["c2_opt_lift"] > 0 and c["c2_informative"])
                c["strength"] = min(c["c1_lift"], c["c2_opt_lift"]) if c["qualifies"] else None
                cells.append(c)
    return cells


def exit_group(family: str) -> str:
    """Exit-profile group of a family (= its C1 pool group): 'open' (O1: 3 ATR30, no target) | 'wall' (struct stop) | 'atr'."""
    return "open" if family.startswith("open_dir") else ("wall" if family in WALL_FAMS else "atr")


def null_p95(cache: dict) -> dict:
    """{firm: {(group, sess): {n, mean, sd, p95, max}}} of the null picks' metric (the optimised null); group = the exit group
    or 'all', sess = a session or 'pooled'."""
    vals = defaultdict(list)
    for (f, key, s), r in cache.items():
        if r.get("variant") == "real":
            continue
        v = r.get("metric")
        if r["status"] in ("no_compliant_cell", "no_cell"):
            v = 0.0
        if v is None:
            continue
        real = cache.get((f, r.get("fam_tf"), s))
        if real is not None and not real.get("n_trades"):        # a session the family never trades (open_dir in asia): not a null config
            continue
        g = exit_group(r.get("family", ""))
        for k in ((g, s), (g, "pooled"), ("all", s), ("all", "pooled")):
            vals[(f, k)].append(float(v))
    out = defaultdict(dict)
    for (f, k), v in vals.items():
        a = np.array(v)
        out[f][k] = {"n": len(a), "mean": float(a.mean()), "sd": float(a.std()), "p95": float(np.percentile(a, 95)), "max": float(a.max())}
    return dict(out)


def p95_of(np95: dict, firm: str, sess: str, family: str | None = None):
    """-> (null p95, stratum name). family given: firm x exit group x session, falling back to the exit group pooled over
    sessions, then to the firm's pooled nulls, when a stratum has < 20 nulls. family None: the session-only stratum (the
    rule as first written), falling back to the firm's pooled nulls."""
    d = np95.get(firm, {})
    g = exit_group(family) if family is not None else "all"
    for k in ((g, sess), (g, "pooled"), ("all", "pooled")):
        st = d.get(k)
        if st and (st["n"] >= 20 or k == ("all", "pooled")):
            return st["p95"], f"{k[0]}/{k[1]}"
    return None, None


def binom_crit(n: int, p: float = 0.05, alpha: float = 0.05) -> int:
    """Smallest k with P(Binomial(n, p) >= k) <= alpha."""
    if n <= 0:
        return 1
    pmf = [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    tail = 0.0
    for k in range(n, -1, -1):
        tail += pmf[k]
        if tail > alpha:
            return k + 1
    return 0


def family_verdicts(cells: list, np95: dict, raw: dict) -> dict:
    """The pre-declared verdict per family (module docstring, item 6). raw: {family: (real net, [c2 nets])} at 1 NQ, all tfs."""
    out = {}
    by = defaultdict(list)
    for c in cells:
        if c["status"] == "ok" and c.get("metric") is not None:
            by[c["family"]].append(c)
    for fam in sorted({c["family"] for c in cells}):
        cs = by.get(fam, [])
        n = len(cs)
        above = sum(1 for c in cs if (p95_of(np95, c["firm"], c["sess"], c["family"])[0] is not None
                                      and c["metric"] > p95_of(np95, c["firm"], c["sess"], c["family"])[0]))
        own = [c for c in cs if all(x is not None for x in c.get("null_metric", [None]))]
        own_top = sum(1 for c in own if c["metric"] > max(c["null_metric"]))
        c2pos = sum(1 for c in cs if c.get("c2_opt_lift") is not None and c["c2_opt_lift"] > 0 and c["c2_informative"])
        c1pos = sum(1 for c in cs if c.get("c1_lift") is not None and c["c1_lift"] > 0)
        both = sum(1 for c in cs if c["qualifies"])
        rn, cn = raw.get(fam, (0.0, [0.0, 0.0]))
        crit = binom_crit(n)
        if n and above >= crit and c2pos > n / 2 and c1pos > n / 2 and rn > max(cn):
            v = "information beats both nulls"
        elif n and c2pos < 0.4 * n and rn < float(np.mean(cn)):
            v = "worse"
        else:
            v = "no better than shuffled book"
        if fam in WALL_FAMS and n and not any(c["c2_informative"] for c in cs):
            v += " (C2 uninformative = not passed)"
        out[fam] = {"cells": n, "above_p95": above, "crit": crit, "own_n": len(own), "own_top": own_top, "c2pos": c2pos, "c1pos": c1pos, "both": both, "raw_net": rn, "raw_c2": cn, "verdict": v}
    return out


def top_configs(cells: list, n_top: int = N_TOP) -> list:
    """Round robin over FIRMS (fixed order): each firm's qualifying configs by strength, rank by rank, until n_top distinct
    configs (fam_tf, sess). -> [(fam_tf, sess), ...] in the order they were added."""
    per = {}
    for f in FIRMS:
        q = [c for c in cells if c["firm"] == f and c["qualifies"]]
        q.sort(key=lambda c: (-c["strength"], c["fam_tf"], c["sess"]))
        per[f] = q
    out, rank = [], 0
    while len(out) < n_top and any(rank < len(q) for q in per.values()):
        for f in FIRMS:
            if rank < len(per[f]):
                k = (per[f][rank]["fam_tf"], per[f][rank]["sess"])
                if k not in out:
                    out.append(k)
                    if len(out) >= n_top:
                        break
        rank += 1
    return out


# ------------------------------------------------------------------ stress

STRESS_FILE = OUT / "screen_stress.json"


def stage_stress(workers: int = MAX_WORKERS) -> dict:
    import screen
    cache = load_cache()
    cells = build_cells(cache)
    top = top_configs(cells)
    fam_tfs = sorted({k for k, _ in top})
    reg = screen.registry()
    done = screen.done_keys(screen.read_ledger(), "stress")
    ran = []
    for job in screen.jobs(reg, "stress"):
        ft = f"{job['family']}-tf{job['tf']}"
        if ft in fam_tfs and job["key"] not in done:
            row = screen.run_job(job, reg, workers=max(1, min(int(workers), MAX_WORKERS)))
            ran.append(job["key"])
            _log(f"stress run {job['key']}: {row['stage']} {row['trades']} trades")
    on_disk = sorted(r["key"][:-len("-stress")] for r in screen.read_ledger() if r["stage"] == "stress")      # incl. runs of an earlier top 15
    res = {"top": [list(k) for k in top], "fam_tfs": fam_tfs, "stressed_fam_tfs": on_disk, "ran": ran, "cells": {}}
    for c in cells:
        if c["fam_tf"] not in on_disk or not c["qualifies"]:
            continue
        src = str(RUNS / f"{c['fam_tf']}-stress")
        if not (Path(src) / "trades.json").exists():
            continue
        try:
            m = metric_at(src, c["firm"], c["cell"], c["sess"], family=c["family"], inputs=c["inputs"])
            st = trade_stats([t for t in load_rows(f"{c['fam_tf']}-stress") if t["_sess"] == c["sess"]])
            res["cells"][f"{c['firm']}|{c['fam_tf']}|{c['sess']}"] = {
                "metric": m["metric"], "bust": m["bust"], "models": m["models"], "lift_c1": m["metric"] - c["c1_ctrl"],
                "lift_c2": m["metric"] - c["c2_opt_null"], "survives": bool(m["metric"] - c["c1_ctrl"] > 0 and m["metric"] - c["c2_opt_null"] > 0),
                "trades": st["trades"], "net": st["net"]}
        except Exception as e:
            res["cells"][f"{c['firm']}|{c['fam_tf']}|{c['sess']}"] = {"error": f"{type(e).__name__}: {e}"}
    _write_json(STRESS_FILE, res)
    _log(f"stress: top {len(top)} configs, {len(fam_tfs)} family x tf, {len(ran)} new runs, {len(res['cells'])} cells re-scored")
    return res


# ------------------------------------------------------------------ gates

GATES_FILE = OUT / "screen_gates.json"


def _sized_stats(members: list) -> dict:
    """members: [(mult, rows)] -> trade_stats of the sized P&L (net x mult per trade)."""
    rows = [{**t, "net": t["net"] * m} for m, rs in members for t in rs]
    return trade_stats(rows)


def stage_gates() -> dict:
    import gates as G
    import l2sim
    out = {"rows": []}
    for pick, pi in G.PICKS.items():
        base_rows, _ = G.pick_rows(pick)
        sess = pi["sess"]

        def in_sess(rows):
            return [t for t in rows if l2sim.session_of(t["entry_ms"]) == sess]

        b_all, b_s = trade_stats(base_rows), trade_stats(in_sess(base_rows))
        for gate in G.GATES:
            st = {}
            for which, seed in (("real", None), ("perm1", 1), ("perm2", 2)):
                d = RUNS / G.gate_key(pick, gate, seed)
                if gate == "G3":
                    mem = []
                    for mult, name in G.TIERS:
                        p = d / name / "trades.json"
                        rows = json.loads(p.read_text()) if p.exists() else []
                        rows = rows if isinstance(rows, list) else rows.get("trades", [])
                        mem.append((mult, rows))
                    st[which] = {"sess": _sized_stats([(m, in_sess(r)) for m, r in mem]), "all": _sized_stats(mem),
                                 "tiers": {name: len(in_sess(r)) for (m, name), (_, r) in zip(G.TIERS, mem)}}
                else:
                    rows = json.loads((d / "trades.json").read_text())
                    rows = rows if isinstance(rows, list) else rows.get("trades", [])
                    st[which] = {"sess": trade_stats(in_sess(rows)), "all": trade_stats(rows)}
            rj = json.loads((RUNS / G.gate_key(pick, gate) / "run.json").read_text())
            counts = ((rj.get("gate") or {}).get("counts") or {})
            for slot, b in G.slots(pick).items():
                rec = {"pick": pick, "gate": gate, "slot": slot, "firm": b["firm"], "kind": b["kind"], "sess": sess,
                       "base": {"sess": b_s, "all": b_all}, "stats": st, "guard_check": counts.get("guard_check"),
                       "no_signal": counts.get("no_signal")}
                try:
                    c = G.cell(pick, gate, slot)
                    unit, base_which = None, "base"
                    if gate == "G3":
                        if not c["cap_ok"]:
                            unit = c["unit_cap"]
                            c = G.cell(pick, gate, slot, unit=unit)
                        base_which = "base_same_size" if "base_same_size_kw" in c else "base"
                        rec.update(unit=c["unit"], tier_micros=c["tier_micros"], cap=c["cap"])
                    key = "p5" if b["kind"] == "eval" else "e_net_40"
                    bkey = "bust5" if b["kind"] == "eval" else "p_bust_pre_first"
                    sc = {w: G.score_cell(pick, gate, slot, w, unit=unit, boots=0) for w in (base_which, "real", 1, 2)}
                    rec["base_which"] = base_which
                    rec["metric"] = {str(w): sc[w].get(key) for w in sc}
                    rec["bust"] = {str(w): sc[w].get(bkey) for w in sc}
                    rec["model"] = sc["real"].get("model")
                    alt = "intraday" if "intraday" in (sc["real"].get("models") or {}) else None
                    if alt:
                        rec["metric_intraday"] = {str(w): (sc[w].get("models") or {}).get(alt, {}).get(key) for w in sc}
                    lf = G.lift_cell(pick, gate, slot, unit=unit, boots=BOOTS)
                    rec["lift_perm"] = lf.get("lift")
                    rec["lift_perm_ci"] = lf.get("ci")
                    if alt:                                      # Lucid cells: the primary model is intraday; realized kept beside it
                        lm = (lf.get("models") or {}).get(alt) or {}
                        rec.update(metric_realized=rec["metric"], lift_perm_realized=rec["lift_perm"], metric=rec["metric_intraday"],
                                   lift_perm=lm.get("lift", lm.get("lift_e40")), lift_perm_ci=lm.get("ci"),
                                   bust={str(w): (sc[w].get("models") or {}).get(alt, {}).get(bkey) for w in sc})
                    rec["primary_model"] = alt or rec["model"]
                    rec["compliant"] = sc["real"].get("compliant")
                    rec["compliance"] = sc["real"].get("compliance")
                    rec["apex_flags"] = sc["real"].get("apex_flags")
                except Exception as e:
                    rec["error"] = f"{type(e).__name__}: {e}"
                out["rows"].append(rec)
                _log(f"gate {pick} {gate} {slot}: {'ERROR ' + rec['error'] if 'error' in rec else 'ok'}")
    _write_json(GATES_FILE, out)
    return out


# ------------------------------------------------------------------ baseline

BASE_FILE = OUT / "screen_baseline.json"


RERANK = L.parent / "2026-10-02-intraday" / "out" / "eval_top.json"        # the old pilot re-ranked under intraday (read-only)
RERANK_FALLBACK = {"lucid": (0.36, "fp-tod_drift-tf5#15 mid"), "lucidpro": (0.40, "hm-tod_drift-tf5#23 mid"),
                   "lucidpro_nodll": (0.42, "fp-donchian-tf15#15 pm"), "apex": (0.42, "fp-donchian-tf15#15 pm"),
                   "apex_eod": (0.40, "hm-donchian-tf15#11 nyam")}             # its summary.md as read 2026-10-02 09:25 ET


def baseline() -> dict:
    """The bar per account under the PRIMARY (intraday) model + the approved pick's numbers under both models.
    Evals: the old pilot's best config under intraday (../2026-10-02-intraday/out/eval_top.json; SPEC 'USER FACTS 07:20 ET').
    Lucid funded: the approved pick under intraday where it still earns something (Pro DLL); Flex / Pro noDLL collapse to
    ~$0 and their re-rank is still running -> no bar yet. Apex PA: unchanged (their model was already real-time)."""
    if BASE_FILE.exists():
        return json.loads(BASE_FILE.read_text())
    import score as S
    b = json.loads((OUT / "baseline_insample.json").read_text())
    own = b["own_firm"]
    out = {}
    try:
        top = json.loads(RERANK.read_text())["top"]
        rr = {f: (float(v[0]["intraday_p5"]), f"{v[0]['key']} {v[0]['sess']}") for f, v in top.items() if v}
        src = "../2026-10-02-intraday/out/eval_top.json"
    except Exception:
        rr, src = dict(RERANK_FALLBACK), "../2026-10-02-intraday/out/summary.md (read 09:25 ET)"

    def appr(name, key):
        r = own[name]
        return {"pick": f"{r['pick']['key']} {r['pick']['sess']}", "realized": r["models"]["realized"][key], "intraday": r["models"]["intraday"][key]}

    for f, name in (("lucid", "flex_eval"), ("lucidpro", None), ("lucidpro_nodll", "pro_nodll_eval"), ("apex", None), ("apex_eod", None)):
        v, pk = rr.get(f, RERANK_FALLBACK[f])
        out[f] = {"pick": f"old pilot's best under intraday: {pk}", "metric": v, "bust": None, "source": src,
                  "approved": appr(name, "p5") if name else None}
    out["apex300_eval"] = {"pick": "no approved pick", "metric": None, "bust": None, "source": "none", "approved": None}
    for f, name in (("flex", "flex_funded"), ("pro_dll", "pro_dll_funded"), ("pro_nodll", "pro_nodll_funded")):
        a = appr(name, "e_net_40")
        keep = a["intraday"] >= 500.0                            # an approved pick that still pays under intraday stays the bar
        out[f] = {"pick": (f"approved pick under intraday: {a['pick']}" if keep else "no bar yet (approved pick collapses under intraday; re-rank running)"),
                  "metric": a["intraday"] if keep else None, "bust": own[name]["models"]["intraday"]["p_bust_pre_first"] if keep else None,
                  "source": "baseline_insample.json", "approved": a}
    bf = S.BASELINE["flex_funded"]
    r = S.score_funded("file:" + S.export_name(bf["key"]), "flex_dll", bf["policy"], micros=bf["micros"], rules=bf["rules"], sess=bf["sess"], boots=0,
                       model="intraday")
    out["flex_dll"] = {"pick": "no approved pick", "metric": None, "bust": None, "source": "none",
                       "approved": {"pick": f"{bf['key']} {bf['sess']} (the Flex pick's cell under the DLL)", "realized": r["models"]["realized"]["e_net_40"],
                                    "intraday": r["models"]["intraday"]["e_net_40"]}}
    ba = S.BASELINE["apex_pa_funded"]
    r = S.score_funded("file:" + S.export_name(ba["key"]), "apex50_pa", ba["policy"], micros=ba["micros"], rules=ba["rules"], sess=ba["sess"], boots=0,
                       **S.BASELINE_META[ba["key"]])
    out["apex50_pa"] = {"pick": f"approved pick: {ba['key']} {ba['sess']}", "metric": r["e_net_40"], "bust": r["p_bust_pre_first"], "p20": r["p_pay_20"],
                        "p40": r["p_pay_40"], "r_frozen_e40": own["apex_pa_funded"]["e_net_40"], "compliant": r.get("compliant"), "source": "scored here",
                        "approved": None}
    bar = b["apex300_pa"]["bar"]["fresh"]
    out["apex300_pa"] = {"pick": f"approved strategy on the 300K: {bar['from'].split(' search')[0].replace('|', ' ')}", "metric": bar["e_net_40"],
                         "bust": bar["p_bust_pre_first"], "p20": bar["p_pay_20"], "p40": bar["p_pay_40"],
                         "cell": {**bar["rules"], "micros": bar["micros"], "policy": bar["policy"]}, "source": "baseline_insample.json", "approved": None}
    _write_json(BASE_FILE, out)
    return out


# ------------------------------------------------------------------ report

def _f(x, nd=3, dollar=False, sign=False):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    if dollar:
        return f"{x:+,.0f}" if sign else f"{x:,.0f}"
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace("0.", ".", 1) if abs(x) < 1 else s


def _fm(firm: str, x, sign=False):
    """Format a firm metric: probability for eval firms, dollars for funded."""
    return _f(x, 2, sign=sign) if FIRMS[firm]["kind"] != "funded" else _f(x, dollar=True, sign=sign)


def _cell_txt(firm: str, c: dict | None) -> str:
    if not c:
        return "-"
    if FIRMS[firm]["kind"] == "funded":
        return f"m{c['micros']} tk{c['day_take']:g} lk{c['day_lock']:g} st{c['day_stop']:g} mt{c['max_day_tr']} T{c['policy']}"
    return f"m{c['micros']} lk{c['day_lock']:g} tk{c['day_take']:g} st{c['day_stop']:g} mt{c['max_day_tr']} tt{int(bool(c['target_take']))}"


def apex_ok(c: dict) -> str:
    """Apex compliance mark of a cell's FAMILY at this pick: 'yes' | 'no (...)' | 'info only (not hand-executable)'."""
    inp = c["inputs"]
    if float(inp.get("tgt_r") or 0.0) < 0.2:
        return "no (no target: stop <= 5x target fails)"
    comp = (c["rec"].get("at_pick") or {}).get("compliance") or c["rec"].get("compliance")
    if FIRMS[c["firm"]].get("apex") and comp and any(v != "ok" for v in comp.values()):
        return "no (" + ", ".join(k for k, v in comp.items() if v != "ok") + ")"
    if c["family"] in NOT_HAND:
        return "info only (not hand-executable)"
    return "yes"


def table_rows(cells: list, np95: dict, base: dict, stress: dict, verd: dict, stats: dict, nc1: dict | None = None, side: dict | None = None,
               extra: dict | None = None) -> list:
    """side: {(firm, fam_tf, sess): cell} of the Lucid accounts under the superseded realized model; extra: {(fam_tf, sess): period / stop columns}."""
    rows = []
    nc1, side, extra = nc1 or {}, side or {}, extra or {}
    for c in cells:
        f, fm, r = c["firm"], FIRMS[c["firm"]], c["rec"]
        st = stats[c["fam_tf"]]
        p95, strat = p95_of(np95, f, c["sess"], c["family"])
        p95s, _ = p95_of(np95, f, c["sess"])
        sc = (stress.get("cells") or {}).get(f"{f}|{c['fam_tf']}|{c['sess']}", {})
        ap = r.get("at_pick") or {}
        md = ap.get("models") or r.get("models") or {}
        mk = "p5" if fm["kind"] == "eval" else ("p20" if fm["kind"] == "eval300" else "e40")
        row = {"family": c["family"], "tf": c["tf"], "sess": c["sess"], "firm": f, "account": fm["label"], "metric_name": fm["unit"],
               "primary_model": fm["prim"], "label": REVISIT.get(c["family"], ""), "status": c["status"]}
        for d in ("both", "long", "short"):
            s = st["real"][(c["sess"], d)]
            sfx = "" if d == "both" else f"_{d}"
            row.update({f"trades{sfx}": s["trades"], f"net{sfx}": round(s["net"], 2), f"t{sfx}": s["t"], f"pf{sfx}": s["pf"], f"maxdd{sfx}": round(s["maxdd"], 2),
                        f"win{sfx}": s["win"]})
        for i, sd in enumerate(SEEDS):
            s = st[f"c2s{sd}"][(c["sess"], "both")]
            row.update({f"c2s{sd}_trades": s["trades"], f"c2s{sd}_net": round(s["net"], 2), f"c2s{sd}_t": s["t"], f"c2s{sd}_pf": s["pf"],
                        f"c2s{sd}_maxdd": round(s["maxdd"], 2), f"c2s{sd}_win": s["win"]})
        nets = [st[f"c2s{sd}"][(c["sess"], "both")]["net"] for sd in SEEDS]
        row["raw_lift_net"] = round(st["real"][(c["sess"], "both")]["net"] - float(np.mean(nets)), 2)
        row["raw_c2_spread"] = round((max(nets) - min(nets)) / 2, 2)
        row.update({"pick_cell": _cell_txt(f, c.get("cell")), "metric": c.get("metric"), "stable_value": c.get("stab"), "raw_max": c.get("raw_max"),
                    "bust": c.get("bust"), "ci_lo": (r.get("ci") or ap.get("ci") or [None, None])[0], "ci_hi": (r.get("ci") or ap.get("ci") or [None, None])[1]})
        for m in ("eod", "realized", "intraday", "pess", "nat", "opt"):
            if m in md:
                row[f"metric_{m}"], row[f"bust_{m}"] = md[m].get(mk), md[m].get("bust")
        own = r.get("own") or {}
        for m in ("realized", "intraday"):
            if m in own:
                row[f"own_pick_p5_{m}"] = own[m]["p5"]
        if fm["kind"] == "funded":
            row.update({"p_pay_20": r.get("p20"), "p_pay_40": r.get("p40"), "med_days_first": r.get("med_days")})
        if fm["kind"] == "eval300":
            row["p_pass_10"] = r.get("p10")
        if fm["kind"] == "eval":
            row.update({"p1": r.get("p1"), "p3": r.get("p3")})
        b = base.get(f, {})
        ap_ = b.get("approved") or {}
        row.update({"baseline_pick": b.get("pick"), "baseline_metric": b.get("metric"), "baseline_bust": b.get("bust"),
                    "approved_pick": ap_.get("pick"), "approved_pick_intraday": ap_.get("intraday"), "approved_pick_realized": ap_.get("realized"),
                    "beats_baseline": (c.get("metric") is not None and b.get("metric") is not None and c["metric"] > b["metric"])})
        row.update({"c1_ctrl": c.get("c1_ctrl"), "c1_lift": c.get("c1_lift"), "c1_ci_lo": (c.get("c1_ci") or [None, None])[0],
                    "c1_ci_hi": (c.get("c1_ci") or [None, None])[1], "c1_lift_realized_model": c.get("c1_lift_side"), "c1_pool_exact": c.get("c1_pool_exact"),
                    "c1_fallback_share": c.get("c1_fallback"),
                    "c2_direct_ctrl": c.get("c2d_ctrl"), "c2_direct_lift": c.get("c2d_lift"), "c2_direct_lift_realized_model": c.get("c2d_lift_side"),
                    "c2_null1_metric": c["null_metric"][0], "c2_null2_metric": c["null_metric"][1], "c2_opt_null_mean": c.get("c2_opt_null"),
                    "c2_opt_spread": c.get("c2_opt_spread"), "c2_opt_lift": c.get("c2_opt_lift"),
                    "c2_trade_ratio_s1": c["c2_ratio"][0], "c2_trade_ratio_s2": c["c2_ratio"][1], "c2_informative": c["c2_informative"],
                    "c2_count_flag": c["c2_count_flag"], "null_p95": p95, "null_p95_stratum": strat,
                    "above_null_p95": (c.get("metric") is not None and p95 is not None and c["metric"] > p95),
                    "above_null_p95_session_only": (c.get("metric") is not None and p95s is not None and c["metric"] > p95s),
                    "above_both_own_nulls": (c.get("metric") is not None and all(x is not None for x in c["null_metric"])
                                             and c["metric"] > max(c["null_metric"])),
                    "qualifies": c["qualifies"], "strength": c.get("strength")})
        q95 = null_c1_p95(nc1, f, c["family"])
        row.update({"null_c1_lift_p95": q95, "c1_lift_above_null_p95": (None if q95 is None or c.get("c1_lift") is None else bool(c["c1_lift"] > q95))})
        sd = side.get((f, c["fam_tf"], c["sess"]))
        if sd is not None:
            row.update({"realized_pick_metric": sd.get("metric"), "realized_pick_bust": sd.get("bust"), "realized_pick_cell": _cell_txt(f, sd.get("cell")),
                        "realized_pick_c1_lift": sd.get("c1_lift"), "realized_pick_c2_opt_lift": sd.get("c2_opt_lift"),
                        "realized_pick_qualifies": sd.get("qualifies"), "realized_pick_metric_under_intraday": sd.get("metric_under_intraday")})
        row.update(extra.get((c["fam_tf"], c["sess"]), {}))
        row.update({"stress_metric": sc.get("metric"), "stress_lift_c1": sc.get("lift_c1"), "stress_lift_c2": sc.get("lift_c2"),
                    "stress_survives": sc.get("survives"), "stress_net_1nq": sc.get("net"),
                    "apex_compliant": apex_ok(c), "net_le0": st["real"][(c["sess"], "both")]["net"] <= 0,
                    "family_verdict": verd.get(c["family"], {}).get("verdict"), "error": r.get("error") or r.get("lifts_error")})
        rows.append(row)
    return rows


def write_csv(rows: list, path: Path) -> None:
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})


def all_stats() -> dict:
    return {k["key"]: {v: split_stats(run_key(k["key"], v)) for v in VARIANTS} for k in screen_keys()}


def stats_rows(stats: dict) -> list:
    out = []
    for k in screen_keys():
        for s in SESSIONS + ("all",):
            for d in ("both", "long", "short"):
                r = {"family": k["family"], "tf": k["tf"], "sess": s, "dir": d}
                for v in VARIANTS:
                    x = stats[k["key"]][v][(s, d)]
                    r.update({f"{v}_{a}": x[a] for a in ("trades", "net", "t", "pf", "maxdd", "win")})
                nets = [stats[k["key"]][f"c2s{sd}"][(s, d)]["net"] for sd in SEEDS]
                r["raw_lift_net"] = r["real_net"] - float(np.mean(nets))
                r["c2_spread"] = (max(nets) - min(nets)) / 2
                out.append(r)
    return out


def shortlist(cells: list, stress: dict) -> dict:
    """{firm: {'picked': [cell, ...] (<= 8, stressed + survive, by strength), 'qualified': n, 'unstressed': n, 'failed_stress': n}}."""
    sc = stress.get("cells") or {}
    out = {}
    for f in FIRMS:
        q = sorted([c for c in cells if c["firm"] == f and c["qualifies"]], key=lambda c: (-c["strength"], c["fam_tf"], c["sess"]))
        surv = [c for c in q if sc.get(f"{f}|{c['fam_tf']}|{c['sess']}", {}).get("survives")]
        out[f] = {"picked": surv[:N_SHORT], "qualified": len(q), "survive": len(surv),
                  "unstressed": sum(1 for c in q if f"{f}|{c['fam_tf']}|{c['sess']}" not in sc),
                  "failed_stress": sum(1 for c in q if f"{f}|{c['fam_tf']}|{c['sess']}" in sc and not sc[f"{f}|{c['fam_tf']}|{c['sess']}"].get("survives"))}
    return out


def stage_report() -> dict:
    cache = load_cache()
    cells = build_cells(cache)
    np95 = null_p95(cache)
    base = baseline()
    stress = json.loads(STRESS_FILE.read_text()) if STRESS_FILE.exists() else {}
    gates = json.loads(GATES_FILE.read_text()) if GATES_FILE.exists() else {"rows": []}
    stats = all_stats()
    raw = {}
    for k in screen_keys():
        rn, cn = raw.setdefault(k["family"], [0.0, [0.0] * len(SEEDS)])
        raw[k["family"]][0] = rn + stats[k["key"]]["real"][("all", "both")]["net"]
        raw[k["family"]][1] = [a + stats[k["key"]][f"c2s{sd}"][("all", "both")]["net"] for a, sd in zip(cn, SEEDS)]
    raw = {f: (v[0], v[1]) for f, v in raw.items()}
    verd = family_verdicts(cells, np95, raw)
    nc1 = null_c1_stats()
    side_cells = build_cells(load_cache(side=True), side=True)   # the Lucid accounts under the superseded realized model
    for c in side_cells:
        m = ((c["rec"].get("at_pick") or {}).get("models") or {}).get("intraday") or {}
        c["metric_under_intraday"] = m.get("p5", m.get("e40"))
    side = {(c["firm"], c["fam_tf"], c["sess"]): c for c in side_cells}
    extra = {(k["key"], s_): period_extra(k["key"], s_) for k in screen_keys() for s_ in SESSIONS}
    rows = table_rows(cells, np95, base, stress, verd, stats, nc1, side, extra)
    write_csv(rows, OUT / "screen_table.csv")
    write_csv(stats_rows(stats), OUT / "screen_stats.csv")
    sl = shortlist(cells, stress)
    sl_rows = []
    by_row = {(r["firm"], r["family"], r["tf"], r["sess"]): r for r in rows}
    for f, d in sl.items():
        for i, c in enumerate(d["picked"], 1):
            sl_rows.append({"account": FIRMS[f]["label"], "rank": i, **by_row[(f, c["family"], c["tf"], c["sess"])]})
    write_csv(sl_rows, OUT / "screen_shortlist.csv")
    g_rows = []
    for g in gates["rows"]:
        s, b = g["stats"], g["base"]["sess"]
        g_rows.append({"pick": g["pick"], "gate": g["gate"], "slot": g["slot"], "firm": g["firm"], "sess": g["sess"], "base_trades": b["trades"],
                       "kept_trades": s["real"]["sess"]["trades"], "base_net": b["net"], "gate_net": s["real"]["sess"]["net"],
                       "perm1_net": s["perm1"]["sess"]["net"], "perm2_net": s["perm2"]["sess"]["net"], "base_pf": b["pf"], "gate_pf": s["real"]["sess"]["pf"],
                       "perm1_pf": s["perm1"]["sess"]["pf"], "perm2_pf": s["perm2"]["sess"]["pf"], "base_which": g.get("base_which"),
                       "metric_base": (g.get("metric") or {}).get(g.get("base_which", "base")), "metric_gate": (g.get("metric") or {}).get("real"),
                       "metric_perm1": (g.get("metric") or {}).get("1"), "metric_perm2": (g.get("metric") or {}).get("2"),
                       "lift_vs_perm": g.get("lift_perm"), "lift_ci": g.get("lift_perm_ci"), "primary_model": g.get("primary_model"),
                       "realized_model_metric": g.get("metric_realized"), "realized_model_lift_vs_perm": g.get("lift_perm_realized"),
                       "unit": g.get("unit"), "tier_micros": g.get("tier_micros"), "tiers": s["real"].get("tiers"), "guard_check": g.get("guard_check"),
                       "error": g.get("error")})
    write_csv(g_rows, OUT / "screen_gates.csv")
    md = summary_md(cells, rows, np95, base, stress, gates, verd, stats, sl, cache, nc1, side_cells)
    if len(md) > MAX_LINES:
        raise RuntimeError(f"screen_summary.md would have {len(md)} lines (cap {MAX_LINES})")
    (OUT / "screen_summary.md").write_text("\n".join(md) + "\n")
    _log(f"report: {len(rows)} table rows, {len(md)} summary lines")
    return {"rows": len(rows), "lines": len(md)}


def _row_of(rows: list, c: dict) -> dict:
    return next(y for y in rows if y["firm"] == c["firm"] and y["family"] == c["family"] and y["tf"] == c["tf"] and y["sess"] == c["sess"])


def summary_md(cells, rows, np95, base, stress, gates, verd, stats, sl, cache, nc1=None, side_cells=None) -> list:
    """out/screen_summary.md, <= MAX_LINES lines (asserted by stage_report)."""
    Lm = []
    keys = screen_keys()
    sc = stress.get("cells") or {}
    n_cfg = len({(c["fam_tf"], c["sess"]) for c in cells if c["n_trades"]})
    n_ok = sum(1 for c in cells if c["status"] == "ok")
    n_err = sum(1 for r in cache.values() if r["status"] == "error")
    n_lift_err = sum(1 for c in cells if c["rec"].get("lifts_error"))
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).strftime("%Y-%m-%d %H:%M")
    Lm.append("# Stage A screen: analysis (NQ Level-2 pilot, in-sample 2021-09-22 to 2024-12-31)")
    Lm.append(f"Made {now} ET by `screen_analyze.py` from the 129 screen and gate bundles: {len(keys)} family x tf runs, {n_cfg} family x tf x session "
              f"configs with trades, 12 account types, 2 shuffled-book (C2) null seeds per run. Nothing was tuned and no 2025+ row was read. "
              f"Scoring errors: {n_err}; lifts that could not be computed: {n_lift_err}. The decision rules were written into the script before any scored "
              "number was read; what changed afterwards is listed in section 6. Full numbers: `out/screen_table.csv` (one row per config x account), "
              "`out/screen_stats.csv` (long / short, every session), `out/screen_gates.csv`, `out/screen_shortlist.csv`.")
    Lm.append("**Breach model: intraday (open losses count) is the primary model for EVERY account**, as SPEC 'USER FACTS 2026-10-02 07:20 ET' orders (it was "
              "written while this analysis was running). The Lucid accounts were first scored with the old realized-balance model as primary; that pass is kept "
              "as side columns (`realized_pick_*`) and summed up in one bullet below. Old approved picks are no longer the bar on Lucid.")
    # ---- bottom line
    q_tot, s_tot = sum(d["qualified"] for d in sl.values()), sum(d["survive"] for d in sl.values())
    beats = [f for f, v in verd.items() if v["verdict"].startswith("information beats")]
    worse = [f for f, v in verd.items() if v["verdict"].startswith("worse")]
    above = sum(1 for r in rows if r["above_null_p95"])
    Lm.append("## Bottom line")
    bt = []
    for fam in beats:
        v = verd[fam]
        ks = [k["key"] for k in keys if k["family"] == fam]
        tr = [t for k_ in ks for t in load_rows(k_)]
        a = trade_stats(tr)
        ss = sorted(((se, trade_stats([t for t in tr if t["_sess"] == se])) for se in SESSIONS), key=lambda x: -x[1]["net"])
        ss = [(se, x) for se, x in ss if x["trades"]]
        nn = np95.get("lucid", {}).get((exit_group(fam), "pooled"), {}).get("n", 0)
        pool_exact = all(c.get("c1_pool_exact") for c in cells if c["family"] == fam and c["status"] == "ok")
        bt.append(f"{fam}" + (f", a {REVISIT[fam]}" if fam in REVISIT else "") + f": {v['above_p95']} of {v['cells']} cells above the null p95 where chance needs "
                  f"{v['crit']}, but its whole edge at 1 NQ is {_f(a['net'], dollar=True, sign=True)} over {a['trades']:,} trades (t {_f(a['t'], 1, sign=True)}), carried by "
                  f"{ss[0][0]} ({_f(ss[0][1]['net'], dollar=True, sign=True)}, t {_f(ss[0][1]['t'], 1, sign=True)}) while {sum(1 for _, x in ss if x['net'] < 0)} of its "
                  f"{len(ss)} sessions lose; its null p95 rests on {nn} nulls per account and its C1 pool is {'exact' if pool_exact else 'a nearest profile only'}")
    Lm.append(f"- {len(beats)} of {len(verd)} families pass the pre-declared 'information beats both nulls' rule"
              + (" (" + "; ".join(bt) + ": a lead to re-test, not a finding)" if bt else "")
              + f"; {len(worse)} are worse than their own shuffled book" + (f" ({', '.join(worse)})" if worse else "")
              + f"; the other {len(verd) - len(beats) - len(worse)} are no better than a shuffled book.")
    Lm.append(f"- Config x account cells with lift > 0 against both C1 and C2 (primary model): {q_tot} of {n_ok} scored ({q_tot / max(n_ok, 1):.0%}; two coin "
              f"flips would give about 25%). "
              f"Of the {len(sc)} that were stress-tested (2 ticks, 250 ms), {s_tot} keep lift > 0 against both.")
    Lm.append(f"- Cells above their null's 95th percentile: {above} of {n_ok} ({above / max(n_ok, 1):.1%}). Chance alone gives about 5% ({0.05 * n_ok:.0f}).")
    bb = [r for r in rows if r["beats_baseline"] and r["qualifies"]]
    bs_ = [r for r in bb if r.get("stress_survives")]
    n60 = sum(1 for r in rows if FIRMS[r["firm"]]["kind"] == "eval" and r["status"] == "ok" and r["metric"] is not None and r["metric"] >= 0.60)
    Lm.append(f"- Bars: evals = the old pilot's best config under intraday (Flex {_f(base['lucid']['metric'], 2)}, Pro DLL {_f(base['lucidpro']['metric'], 2)}, "
              f"Pro noDLL {_f(base['lucidpro_nodll']['metric'], 2)}, Apex {_f(base['apex']['metric'], 2)}, Apex EOD {_f(base['apex_eod']['metric'], 2)}); the promotion "
              f"criterion stays P5 >= .60 and {n60} L2 cells reach it. Cells that beat their account's bar AND have lift > 0 against both controls: {len(bb)}"
              + (" (" + "; ".join(f"{r['family']}-tf{r['tf']} {r['sess']} on {r['account']} {_fm(r['firm'], r['metric'])} vs {_fm(r['firm'], r['baseline_metric'])}"
                                  for r in bb[:6]) + (" ..." if len(bb) > 6 else "") + ")" if bb else "")
              + f"; {len(bs_)} of them also survive stress. Flex, Flex+DLL and Pro noDLL funded have no bar yet (the approved picks earn about $0 under intraday; "
              "the old pilot's funded re-rank was still running).")
    if side_cells:
        sq = [c for c in side_cells if c["qualifies"]]
        ob = json.loads((OUT / "baseline_insample.json").read_text())["own_firm"]
        old_bar = {"lucid": ob["flex_eval"]["p5"], "lucidpro_nodll": ob["pro_nodll_eval"]["p5"], "flex": ob["flex_funded"]["e_net_40"],
                   "pro_dll": ob["pro_dll_funded"]["e_net_40"], "pro_nodll": ob["pro_nodll_funded"]["e_net_40"]}
        sb = [c for c in sq if c["firm"] in old_bar and c["metric"] > old_bar[c["firm"]]]
        Lm.append(f"- Under the superseded realized model (Lucid accounts only, first pass): {len(sq)} of {sum(1 for c in side_cells if c['status'] == 'ok')} cells had "
                  f"lift > 0 against both controls and {len(sb)} beat the old approved pick"
                  + (" (" + "; ".join(f"{c['fam_tf']} {c['sess']} on {FIRMS[c['firm']]['label']}: {_fm(c['firm'], c['metric'])} vs {_fm(c['firm'], old_bar[c['firm']])}, "
                                      f"{_fm(c['firm'], c.get('metric_under_intraday'))} once open losses count" for c in sb[:4]) + ")" if sb else "")
                  + ". That model ignores open losses, so these numbers are not usable; they are in the CSV for reference only.")
    lead = [r for r in rows if r["family"] == "bimb_follow" and r["tf"] == "5" and r["sess"] == "mid"]
    if lead:
        st_l = stats["bimb_follow-tf5"]
        a_l = st_l["real"][("mid", "both")]
        Lm.append(f"- The cleanest single config is bimb_follow-tf5 in the mid session (when the top-10 book imbalance is 2 sigma away from its last hour, follow "
                  f"the heavier side; checked at 5-minute bar closes, 11:00-13:30 ET): {a_l['trades']} trades, {_f(a_l['net'], dollar=True, sign=True)} at 1 NQ, t {_f(a_l['t'], 1, sign=True)}, PF {_f(a_l['pf'], 2)}, "
                  f"against {_f(st_l['c2s1'][('mid', 'both')]['net'], dollar=True, sign=True)} / {_f(st_l['c2s2'][('mid', 'both')]['net'], dollar=True, sign=True)} for its two "
                  f"shuffled twins; lift > 0 against both controls on {sum(1 for r in lead if r['qualifies'])} of {len(lead)} accounts and on "
                  f"{sum(1 for r in lead if r.get('stress_survives'))} after stress. It is one session of one run out of {n_cfg} configs, picked after the fact, and it beats "
                  f"no account's bar ({sum(1 for r in lead if r['beats_baseline'])} of them).")
    alls = {k["key"]: stats[k["key"]]["real"][("all", "both")] for k in keys}
    pos = [k for k, a in alls.items() if a["net"] > 0]
    tmax = max(alls, key=lambda k: alls[k]["t"] if alls[k]["t"] is not None else -9e9)
    twin = [k["key"] for k in keys if alls[k["key"]]["net"] > max(stats[k["key"]][f"c2s{sd}"][("all", "both")]["net"] for sd in SEEDS)]
    Lm.append(f"- At 1 NQ only {len(pos)} of {len(keys)} runs make money after costs" + (f" ({', '.join(pos)})" if pos else "")
              + f". The largest t-stat is {_f(alls[tmax]['t'], 1, sign=True)} ({tmax}); with {len(keys)} runs tried, a t-stat needs to be about 3.1 to count at the 5% level. "
              f"{len(twin)} of {len(keys)} runs do better than both of their shuffled twins (about {len(keys) / 3:.0f} expected by chance): if the book carries "
              "information it is small next to the costs.")
    # ---- family x tf table
    Lm.append("## 1. Families at 1 NQ (all sessions; net in $; C2 = shuffled-book null, seed 1 / seed 2)")
    Lm.append("| family-tf | trades | net | t | PF | max DD | win | C2 net s1 / s2 | raw lift | best session (net, t) | long / short net | cells q / n |")
    Lm.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k in keys:
        st = stats[k["key"]]
        a = st["real"][("all", "both")]
        n1, n2 = (st[f"c2s{sd}"][("all", "both")]["net"] for sd in SEEDS)
        bs = max(SESSIONS, key=lambda s: st["real"][(s, "both")]["net"])
        b = st["real"][(bs, "both")]
        cs = [c for c in cells if c["fam_tf"] == k["key"] and c["status"] == "ok"]
        tag = " (REVISIT)" if k["family"] in REVISIT else ""
        Lm.append(f"| {k['key']}{tag} | {a['trades']:,} | {_f(a['net'], dollar=True, sign=True)} | {_f(a['t'], 1, sign=True)} | {_f(a['pf'], 2)} | "
                  f"{_f(a['maxdd'], dollar=True)} | {_f(a['win'], 2)} | {_f(n1, dollar=True, sign=True)} / {_f(n2, dollar=True, sign=True)} | "
                  f"{_f(a['net'] - (n1 + n2) / 2, dollar=True, sign=True)} | {bs} ({_f(b['net'], dollar=True, sign=True)}, {_f(b['t'], 1, sign=True)}) | "
                  f"{_f(st['real'][('all', 'long')]['net'], dollar=True, sign=True)} / {_f(st['real'][('all', 'short')]['net'], dollar=True, sign=True)} | "
                  f"{sum(1 for c in cs if c['qualifies'])} / {len(cs)} |")
    Lm.append("'cells q / n' = account cells with lift > 0 against both controls / cells scored. The best session is picked after the fact: read its t-stat with that in mind.")
    # ---- per firm
    Lm.append("## 2-3. Per account: the bar, the best L2 config, and the nulls through the same rule search (primary model in the first column)")
    Lm.append("| account (metric, primary model) | bar under the primary model [approved pick: intraday / old realized model] | best L2 config: metric (same cell, "
              "old realized model), bust | its lift vs C1 / C2 | null mean / p95 / max | configs above null p95 (expected by chance) | lift > 0 vs both |")
    Lm.append("|---|---|---|---|---|---|---|")
    for f, fm in FIRMS.items():
        cs = [c for c in cells if c["firm"] == f and c["status"] == "ok" and c.get("metric") is not None]
        b = base.get(f, {})
        nb = np95.get(f, {}).get(("all", "pooled"), {})
        if cs:
            top = max(cs, key=lambda c: c["metric"])
            intr = _row_of(rows, top).get("metric_realized") if fm.get("side") else None
            best = f"{top['fam_tf']} {top['sess']}: {_fm(f, top['metric'])}" + (f" ({_fm(f, intr)})" if intr is not None else "") + f", bust {_f(top['bust'], 2)}"
            lf = f"{_fm(f, top.get('c1_lift'), True)} / {_fm(f, top.get('c2_opt_lift'), True)}"
        else:
            best, lf = "no scored config", "-"
        ab = sum(1 for r in rows if r["firm"] == f and r["above_null_p95"])
        ap_ = b.get("approved") or {}
        bar = ((_fm(f, b["metric"]) + (f", bust {_f(b['bust'], 2)}" if b.get("bust") is not None else "") + "; ") if b.get("metric") is not None else "") + str(b.get("pick"))
        if ap_:
            bar += f" [{ap_['pick']}: {_fm(f, ap_['intraday'])} / {_fm(f, ap_['realized'])}]"
        Lm.append(f"| {fm['label']} ({fm['unit']}, {fm['prim']}) | {bar} | {best} | {lf} | {_fm(f, nb.get('mean'))} / {_fm(f, nb.get('p95'))} / {_fm(f, nb.get('max'))} | "
                  f"{ab} of {len(cs)} ({0.05 * len(cs):.1f}) | {sum(1 for c in cs if c['qualifies'])} |")
    Lm.append("P5 = P(pass <= 5 days). P20 = P(pass <= 20 days): the 300K evaluation needs 7 days. E$40 = expected $ to the trader in 40 trading days, "
              "fresh account. Every number is the metric of the cell the search picks on STABILITY (best median with its grid neighbours), not the raw maximum of "
              "the grid. 'Best' is the highest metric, not a recommendation: read its lifts. C2 lift = real pick minus the mean of the two nulls' own picks (the "
              "null gets its own optimised rules). Null mean / p95 / max are pooled over everything; the count compares each config with the nulls of its own "
              "exit-profile group and session. The Apex 50K PA bar is the approved cell re-scored with apex300.py's conservative readings. "
              f"Apex PA cells without any compliant cell (no metric): {sum(1 for c in cells if c['status'] == 'noncompliant_static' and float(c['inputs'].get('tgt_r') or 0) < 0.2)} "
              f"by design (open_dir has no target), {sum(1 for c in cells if c['status'] == 'noncompliant_static' and float(c['inputs'].get('tgt_r') or 0) >= 0.2)} because a "
              f"trade's stop reaches 80% of the trailing threshold even at 10 micros, {sum(1 for c in cells if c['status'] == 'no_compliant_cell')} under the MAE rule; "
              f"{sum(1 for c in cells if c['status'] == 'ok' and FIRMS[c['firm']].get('apex') and c.get('c2_opt_lift') is None)} more have a null without a compliant cell "
              "(C2 not comparable = not passed).")
    # ---- gates
    Lm.append("## 4. Gates G1-G3 on the approved picks (pick's own session and approved cell; perm = the gate's permutation null, seed 1 / seed 2)")
    Lm.append("| pick, gate (account) | trades kept | net: pick -> gated (perm 1 / 2) | PF: pick -> gated (perm mean) | account metric, primary model: pick -> gated (perm 1 / 2) "
              "[old realized model: pick -> gated] | lift vs perm | verdicts changed 1 s earlier |")
    Lm.append("|---|---|---|---|---|---|---|")
    first_slot = {}
    for g in gates["rows"]:
        first_slot.setdefault(g["pick"], g["slot"])
    extra = []
    for g in gates["rows"]:
        s, b = g["stats"], g["base"]["sess"]
        money = g["kind"] != "eval"
        fmf = (lambda x, sign=False: _f(x, dollar=True, sign=sign)) if money else (lambda x, sign=False: _f(x, 2, sign=sign))
        mt, bw = g.get("metric") or {}, g.get("base_which", "base")
        mtxt = ("ERROR " + g["error"][:50]) if g.get("error") else f"{fmf(mt.get(bw))} -> {fmf(mt.get('real'))} ({fmf(mt.get('1'))} / {fmf(mt.get('2'))})"
        if g.get("metric_realized") and not g.get("error"):
            mtxt += f" [{fmf(g['metric_realized'].get(bw))} -> {fmf(g['metric_realized'].get('real'))}]"
        if g["slot"] != first_slot[g["pick"]]:
            extra.append(f"{g['pick']} {g['gate']} on {g['slot']}: {mtxt}, lift vs perm {fmf(g.get('lift_perm'), True)}")
            continue
        pfs = [x for x in (s["perm1"]["sess"]["pf"], s["perm2"]["sess"]["pf"]) if x is not None]
        note = f", unit {g['unit']} = {'/'.join(str(v) for v in g['tier_micros'].values())} micros vs the pick at {2 * g['unit']}" if g["gate"] == "G3" and bw == "base_same_size" else ""
        gc = g.get("guard_check") or {}
        Lm.append(f"| {g['pick']} {g['gate']} ({g['slot']}{note}) | {s['real']['sess']['trades']} of {b['trades']} | {_f(b['net'], dollar=True, sign=True)} -> "
                  f"{_f(s['real']['sess']['net'], dollar=True, sign=True)} ({_f(s['perm1']['sess']['net'], dollar=True, sign=True)} / "
                  f"{_f(s['perm2']['sess']['net'], dollar=True, sign=True)}) | {_f(b['pf'], 2)} -> {_f(s['real']['sess']['pf'], 2)} ({_f(float(np.mean(pfs)) if pfs else None, 2)}) | "
                  f"{mtxt} | {'-' if g.get('error') else fmf(g.get('lift_perm'), True)} | {gc.get('verdicts_changed', '-')} |")
    nc = sorted({f"{g['pick']} {g['gate']} on {g['slot']} ({', '.join(k for k, v in (g.get('compliance') or {}).items() if v != 'ok')})"
                 for g in gates["rows"] if g.get("compliant") is False and g["pick"].startswith("donchian")})
    Lm.append("G3 nets are the sized P&L (x0.5 / x1 / x1.5 per trade, at 1 NQ). Other cells of the same picks: " + "; ".join(extra) + ". "
              + (f"Fails the Apex compliance gate: {'; '.join(nc)}. " if nc else "")
              + "A gate only removes or resizes listed trades, so a survivor would still need an l2sim replay; straddle #10 and #9 share their entries (one test, not two); "
              "the donchian verdicts flip often when the clock is 1 s earlier, so their gate numbers are not deployable as they stand.")
    # ---- stress
    Lm.append("## 5. Stress (2 ticks of slip + 250 ms latency) on the top 15 configs by lift")
    if not stress.get("top"):
        Lm.append("No config has lift > 0 against both controls on any account, so there was nothing to stress." if STRESS_FILE.exists() else "Stress stage not run yet.")
    else:
        parts = []
        for ft, s in stress["top"]:
            q = [c for c in cells if c["fam_tf"] == ft and c["sess"] == s and c["qualifies"]]
            ok = [c for c in q if sc.get(f"{c['firm']}|{ft}|{s}", {}).get("survives")]
            neta = next((sc[f"{c['firm']}|{ft}|{s}"].get("net") for c in q if f"{c['firm']}|{ft}|{s}" in sc), None)
            parts.append(f"{ft} {s} (net {_f(stats[ft]['real'][(s, 'both')]['net'], dollar=True, sign=True)} -> {_f(neta, dollar=True, sign=True)}; accounts {len(q)} -> {len(ok)})")
        Lm.append(f"Top {len(stress['top'])} configs (round robin over the accounts by the smaller of the two lifts); in brackets the 1 NQ net before -> after stress and the "
                  "number of accounts with lift > 0 against both controls before -> after: " + "; ".join(parts) + ".")
        sf = stress.get("stressed_fam_tfs") or stress.get("fam_tfs", [])
        Lm.append(f"Stress runs: {len(sf)} family x tf ({', '.join(sf)}; {len(stress.get('fam_tfs', []))} for this top 15, the rest from the first pass's top 15), "
                  f"logged in ledger.csv as stage `stress`, not counted in the run cap. Every qualifying cell of those runs was re-scored at its own cell without a new "
                  f"search: {sum(1 for x in sc.values() if x.get('survives'))} of {len(sc)} survive. The controls were not stressed, so this is the conservative reading.")
    # ---- multiple testing
    Lm.append("## 6. Multiple-testing honesty and the verdict per family")
    Lm.append(f"- Screened: {len(keys)} family x tf runs = {n_cfg} configs x 12 accounts = {n_ok} scored cells, plus 18 gate runs. Each cell also had a rule search of "
              "768 to 7,680 cells, so a high P5 or E$40 by itself means little: the same search lifts the shuffled-book null too (see the null columns above).")
    Lm.append("| family | cells above null p95 / cells (count needed to beat chance) | above both own nulls (1/3 by chance) | cells with C2 lift > 0 | cells with C1 lift > 0 | "
              "raw net vs C2 nets (1 NQ) | verdict |")
    Lm.append("|---|---|---|---|---|---|---|")
    for fam, v in verd.items():
        n = max(v["cells"], 1)
        Lm.append(f"| {fam}{' (' + REVISIT[fam] + ')' if fam in REVISIT else ''} | {v['above_p95']} / {v['cells']} ({v['crit']}) | {v['own_top']} / {v['own_n']} | {v['c2pos'] / n:.0%} | {v['c1pos'] / n:.0%} | "
                  f"{_f(v['raw_net'], dollar=True, sign=True)} vs {_f(v['raw_c2'][0], dollar=True, sign=True)} / {_f(v['raw_c2'][1], dollar=True, sign=True)} | **{v['verdict']}** |")
    near = []
    for fam, v in verd.items():
        if v["cells"] and v["above_p95"] >= v["crit"] and not v["verdict"].startswith("information beats"):
            why = [t for t, bad in (("under half of its cells have C2 lift > 0", v["c2pos"] <= v["cells"] / 2),
                                    ("under half have C1 lift > 0", v["c1pos"] <= v["cells"] / 2),
                                    ("its 1 NQ net is not above both shuffled twins", not v["raw_net"] > max(v["raw_c2"]))) if bad]
            near.append(f"{fam} ({v['above_p95']} of {v['cells']}; fails because {' and '.join(why)})")
    if near:
        Lm.append("- Families with more cells above the null p95 than chance gives, which still fail the verdict: " + "; ".join(near)
                  + ". For the wall families the count is an artefact: their nulls barely trade, so the null p95 is close to zero.")
    if nc1:
        na = [(f, d["all"]) for f, d in nc1.items() if "all" in d and d["all"]["n"] >= 20]
        ev = [d for f, d in na if FIRMS[f]["kind"] != "funded"]
        fu = [d for f, d in na if FIRMS[f]["kind"] == "funded"]
        c1ok = [r for r in rows if r.get("c1_lift_above_null_p95") is not None]
        txt = (f"evals: {np.mean([d['pos'] for d in ev]):.0%} of the null cells have C1 lift > 0, mean {np.mean([d['mean'] for d in ev]):+.3f}" if ev else "")
        txt += ("; " if ev and fu else "") + (f"funded: {np.mean([d['pos'] for d in fu]):.0%}, mean {np.mean([d['mean'] for d in fu]):+,.0f} $" if fu else "")
        Lm.append(f"- The C1 lift is inflated by the rule search (the pick is the best of a grid, the random control is scored at that same cell). The shuffled-book nulls, "
                  f"put through the same search and the same C1 control, show it too: {txt}. Real cells whose C1 lift is above their null's 95th percentile C1 lift: "
                  f"{sum(1 for r in c1ok if r['c1_lift_above_null_p95'])} of {len(c1ok)} (5% by chance). So 'C1 lift > 0' alone is not evidence.")
    so = sum(1 for r in rows if r["above_null_p95_session_only"])
    Lm.append(f"- Changed after the first partial results were seen (all in the script's docstring): (1) 02:20 ET, the null p95 is taken within the config's "
              f"exit-profile group (as R did), not over all families of a session. The session-only version is set by the open_dir nulls alone (their NULL passes "
              f"Lucid evals 55-70% of the time), so it flatters open_dir and shuts out everything else; it would give {so} cells above p95 instead of {above}. "
              "(2) Added as diagnostics, used for no decision: 'above both own nulls', the C1 lift of the nulls, and the flags of section 7. (3) 04:35 ET, before any "
              "Apex PA lift was read: a null without a compliant cell makes the C2 lift 'not comparable = not passed'. (4) 11:50 ET: nulls of a session the family never trades (open_dir in asia: structural zeros) "
              "are left out of the null p95, which is stricter for open_dir. (5) 09:30 ET, after the realized-primary pass "
              "was complete and read: the Lucid accounts were re-scored with intraday as the primary model (searches, lifts, nulls, stress, shortlist) because the "
              "SPEC now orders it; the bars changed with it (old pilot's best under intraday; none yet for three Lucid funded accounts).")
    Lm.append("- Caveats: the 12 accounts score the same trades, so the cell counts overstate the evidence (the 'count needed' is generous to the family). Two C2 seeds give "
              "only a rough spread. C2 trade counts differ from the real run for absorption (2.4-3.5x), cvd_div (1.3-1.9x), delta_follow-tf5 (0.74x) and wall_break "
              "(0.06-0.12x: uninformative = not passed, as pre-registered). The C1 pools for the wall and open_dir families are the nearest exit profile, not an exact one.")
    # ---- shortlist
    Lm.append("## 7. Shortlist proposal for stage B (lift > 0 vs C1 and C2 on the primary model AND still > 0 after stress; best 8 per account by the smaller lift)")
    Lm.append("Each entry: config, metric (Lucid: the same cell under the old realized model), lift vs C1 / C2, then the stressed metric and its lifts in square brackets, then flags. "
              "Flags: N = loses money at 1 NQ; P = not above its null's 95th percentile; C = its C1 lift is not above what the shuffled nulls get; "
              "K = C1 pool is the nearest exit profile, not an exact one; M = C2 trade count mismatch; R = REVISIT of a refuted family (or contains its signal); "
              "X = not Apex-compliant as registered (no target). No flag = none of these. Everything not marked X is one-direction with a 2R target (Apex-compliant).")
    any_pick = False
    counts = defaultdict(int)
    for f, d in sl.items():
        fm = FIRMS[f]
        bm = base.get(f, {}).get("metric")
        head = f"- **{fm['label']}** ({'bar ' + _fm(f, bm) if bm is not None else 'no bar yet'}): "
        if not d["picked"]:
            why = ("no config has lift > 0 against both controls" if not d["qualified"] else
                   f"{d['qualified']} had lift > 0 against both before stress; {d['failed_stress']} failed stress, {d['unstressed']} were outside the stressed top 15")
            Lm.append(head + f"NOTHING QUALIFIES ({why}).")
            continue
        any_pick = True
        parts = []
        for c in d["picked"]:
            x, r = sc[f"{f}|{c['fam_tf']}|{c['sess']}"], _row_of(rows, c)
            counts[(c["fam_tf"], c["sess"])] += 1
            intr = r.get("metric_realized") if fm.get("side") else None
            flags = "".join(t for t, on in (("N", r["net_le0"]), ("P", not r["above_null_p95"]), ("C", r.get("c1_lift_above_null_p95") is False),
                                            ("K", c.get("c1_pool_exact") is False), ("M", c["c2_count_flag"]), ("R", c["family"] in REVISIT),
                                            ("X", not apex_ok(c).startswith(("yes", "info")))) if on)
            parts.append(f"{c['fam_tf']} {c['sess']} {_fm(f, c['metric'])}" + (f" ({_fm(f, intr)})" if intr is not None else "")
                         + f", {_fm(f, c['c1_lift'], True)} / {_fm(f, c['c2_opt_lift'], True)} [{_fm(f, x['metric'])}, {_fm(f, x['lift_c1'], True)} / {_fm(f, x['lift_c2'], True)}]"
                         + (f" {flags}" if flags else " (no flag)"))
        Lm.append(head + "; ".join(f"{i}) {p}" for i, p in enumerate(parts, 1))
                  + (f"; +{d['survive'] - len(d['picked'])} more survive (CSV)" if d["survive"] > len(d["picked"]) else "") + ".")
    if any_pick:
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        noflag = sorted({f"{r['family']}-tf{r['tf']} {r['sess']}" for f, d in sl.items() for c in d["picked"] for r in [_row_of(rows, c)]
                         if not r["net_le0"] and r["above_null_p95"] and r.get("c1_lift_above_null_p95") is not False and c.get("c1_pool_exact") is not False
                         and not c["c2_count_flag"] and c["family"] not in REVISIT and apex_ok(c).startswith("yes")})
        Lm.append("Read it this way: the same few configs fill most lists (" + ", ".join(f"{k[0]} {k[1]} on {n} of 12" for k, n in top)
                  + "). Configs with at least one entry without any flag: " + (", ".join(noflag) if noflag else "none") + ". "
                  "About a third of all cells pass 'lift > 0 against both' by chance, so the flagged entries are what chance leaves behind, not leads.")
    lib = []
    ex = {(r["family"], r["tf"], r["sess"]): r for r in rows}
    for (fam, tf, se), r in sorted(ex.items()):
        ft = f"{fam}-tf{tf}"
        twins = [stats[ft][f"c2s{sd}"][(se, "both")]["net"] for sd in SEEDS]
        sn = next((x.get("net") for k_, x in sc.items() if k_.endswith(f"|{ft}|{se}") and x.get("net") is not None), None)
        if (r.get("trades_build", 0) >= 100 and r.get("trades_pick2024", 0) >= 30 and r["net_build"] > 0 and r["net_pick2024"] > 0 and r["net"] > max(twins)
                and (sn is None or sn > 0)):
            lib.append((r["t"] or 0.0, f"{ft} {se} (build {_f(r['net_build'], dollar=True, sign=True)}, 2024 {_f(r['net_pick2024'], dollar=True, sign=True)}, t {_f(r['t'], 1, sign=True)}, "
                                       f"median stop ${_f(r.get('stop_usd_median_1nq'), dollar=True)} per NQ, " + ("stressed " + _f(sn, dollar=True, sign=True) if sn is not None else "not stressed") + ")"))
    lib.sort(reverse=True)
    Lm.append(f"For the edge library (SPEC 'APPROACH CHANGE'): configs with net > 0 at 1 NQ in BOTH the build period (to 2023-12-31) and the pick year 2024, above both "
              f"shuffled twins, and still > 0 under stress where stressed: {len(lib)} of {n_cfg}. By t-stat: " + ("; ".join(x for _, x in lib[:8]) if lib else "none")
              + (f"; +{len(lib) - 8} more (columns net_build / net_pick2024 in the CSV)" if len(lib) > 8 else "") + ". None of these t-stats survives a correction for "
              f"{n_cfg} configs tried; this is a list to re-test, not a result.")
    Lm.append(("**No account type has a candidate: keep the approved picks.** " if not any_pick else "")
              + "A shortlist entry is a lead for stage B tuning, not a pick: the SPEC's promotion criteria are untouched and nothing here meets them. "
              "Apex PA accounts ban automation: the book and flow families need a live z-score / percentile read at every bar close "
              "(semi-manual at best, to be labelled so), the wall families cannot be traded by hand, and open_dir, the only one simple enough, has no target and so "
              "fails the 5:1 rule as registered.")
    return Lm


MAX_LINES = 120


def status() -> dict:
    ts = tasks()
    done = sum(cache_path(t["firm"], t["key"], t["sess"]).exists() for t in ts)
    return {"tasks": len(ts), "done": done, "pending": len(ts) - done}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="screen_analyze.py", description="Stage A screen analysis (see screen_analysis.py)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--workers", type=int, default=MAX_WORKERS)
    s.add_argument("--only", default="")
    s.add_argument("--firms", default="")
    s.add_argument("--reverse", action="store_true")
    n = sub.add_parser("nullc1")
    n.add_argument("--workers", type=int, default=MAX_WORKERS)
    n.add_argument("--firms", default="")
    sub.add_parser("gates")
    t = sub.add_parser("stress")
    t.add_argument("--workers", type=int, default=MAX_WORKERS)
    sub.add_parser("report")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "score":
        r = stage_score(a.workers, [x for x in a.only.split(",") if x] or None, [x for x in a.firms.split(",") if x] or None, a.reverse)
    elif a.cmd == "nullc1":
        r = stage_null_c1(a.workers, [x for x in a.firms.split(",") if x] or None)
    elif a.cmd == "gates":
        r = {"rows": len(stage_gates()["rows"])}
    elif a.cmd == "stress":
        r = stage_stress(a.workers)
        r = {"top": r["top"], "ran": r["ran"], "cells": len(r["cells"])}
    elif a.cmd == "report":
        r = stage_report()
    else:
        r = status()
    print(json.dumps(r, default=_js))
    return 0


if __name__ == "__main__":
    sys.exit(main())
