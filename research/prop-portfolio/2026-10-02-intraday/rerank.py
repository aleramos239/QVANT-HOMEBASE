#!/usr/bin/python3
"""Re-rank the 2026-09-29 NQ prop pilot (R) with the INTRADAY breach model as the selection model.

Lucid's drawdown counts OPEN losses (user, 2026-10-02) -> 'intraday' (bust when the day's worst open point reaches the floor) is the
true rule; R selected everything on 'realized'. This script changes NO rule, NO grid and NO code of R: it imports R's modules read-only
(through ../2026-10-01-l2/score.py, which pins R on sys.path, switches bytecode writing off and seals the 2025+ holdout) and either
re-reads what R already computed under intraday (R's pass 3 stored the intraday-stable cell of every config: cellset 'p5_intraday')
or re-runs R's own functions with model='intraday' where R only ran its old primary model (funded search, pass-3 walk-forward).

Run:  /usr/bin/python3 rerank.py --stage <stage> [--workers 4]
  heavy stages (multiprocess, resumable jsonl checkpoints in out/, <= 4 workers, compute windows honoured before every walk):
    funded_s1    coarse funded grid, model intraday, 1,283 configs x flex / flex_dll / pro_dll / pro_nodll  -> out/funded_s1.jsonl
    funded_pick  top K per variant by coarse E$40                                                           -> out/funded_pick.json
    funded_s2    R's full funded grid on the picks: stable E$40 cell, lift vs 8 day-matched controls, WF    -> out/funded_s2.jsonl
    funded_null  the first 30 of R's 60 zero-edge pseudo-configs through the same full search (20 with WF)  -> out/funded_null.jsonl
    verify       re-compute the top-10 eval picks per firm from the bundles and compare with R's stored rows -> out/verify_part.jsonl
    wf           R's offline quarterly walk-forward, objective intraday, top-10 pass-3 family grids / firm,
                 3 day-matched random controls each (R: 12 grids, 5 controls; cut for run time), each cell's
                 control from its own exit-profile pool (see task_wf)                                    -> out/wf_intraday_part.jsonl
    heavy        all of the above in that order
  light stages (single process; rerank_light.py, rerank_light2.py, rerank_summary.py):
    eval        R's stored intraday-stable cells -> out/eval_intraday.csv (all 1,283 configs x 5 firms), out/eval_top.json (+ the null)
    verify_agg  compare the re-computed top picks with R's stored rows -> out/verify.json
    wf_agg      out/wf_intraday.csv = this run's pass-3 Lucid walk-forwards + R's own intraday rows (pass-2 grids, Apex)
    funded_agg  out/funded_intraday.csv, out/funded_top.json
    second      SECOND LOOK: the top picks that have a 2025+ bundle in R, re-scored on 2025-01 -> 2026-09 -> out/second_look.json
    desk        the four desk algos: R's stored numbers + the tick-replayed desk-version runs (desk_runs/) -> out/desk_algos.json
    summary     out/summary.md (<= 80 lines), out/eval_top10.md, out/funded_top5.md
    light       all of the above in that order
  fix round (2026-10-02, after verification; each stage by name, resumable):
    eval_p2x     the 498 pass-2 configs R searched under intraday but never carried into pass 3 (>= 300 trades, net > 0 at 1 NQ), through
                 R's pass-3 analysis (a3p3.task_real3), 5 firms                                              -> out/eval_p2x_part.jsonl
    funded_nwf   NESTED funded walk-forward, config level: all 1,781 configs x 4 account types on the coarse grid; per test quarter the
                 cell with the best stable E$40 on the trailing 12 months and what it paid on the test quarter -> out/funded_nwf.jsonl
    funded_pick2 top K per variant by the full-sample coarse E$40 over the 1,781                              -> out/funded_pick2.json
    funded_s2b   R's full funded grid on the pairs funded_s2.jsonl does not hold yet                          -> out/funded_s2b.jsonl
    nwf_ctl      the nested walk-forward's picks start by start + 8 day-matched random controls (needs the light stage nwf_agg once
                 before it: that writes out/funded_nwf_picks.json)                                            -> out/funded_nwf_ctl.jsonl
    wf_p2        the pilot's pass-2 heat-map grids re-walked with own-pool controls (task_wf); --rev = heaviest first into a second part
                 file. Stopped by hand after 28 of 48 tasks (the 36-member grids need about 20 worker-minutes each)
                                                                                                             -> out/wf_intraday_p2_part*.jsonl
    lift         the reported eval top 10 / funded top 5 against their K day-matched controls at the pick's cell, replicate by replicate
                                                                                                             -> out/lift.jsonl, out/lift_u.jsonl
    wf_u         (RR_CTRL=overlap only) task_wf again for the own-pool grids that trade more than once a day: their control replicates
                 with the unbiased draw                                                                       -> out/wf_intraday_u_part.jsonl
  RR_CTRL=overlap (environment): the day-matched control is drawn WITHOUT R's no-overlap test (see 'control switch' below: R's draw is
  biased for configs with more than one trade a day). Run lift, nwf_ctl, wf_u and the LIGHT stages with it; outputs carry '_u' where both
  versions are kept.
  light stages added: nwf_agg (out/funded_nwf.json, funded_nwf.csv); wf_agg also writes the nested eval walk-forward (wf_summary.json 'nested');
  eval ranks R's stored intraday cells + the eval_p2x rows (1,781 configs x 5 firms); ctrl_bias (out/control_bias.json).
Order to reproduce everything: --stage heavy, then --stage wf --top 12 --kc 5 (if the chain ran it leaner), then eval_p2x, funded_nwf,
funded_pick2, funded_s2b, then --stage eval, funded_agg and nwf_agg (light), then nwf_ctl (with and without RR_CTRL=overlap), wf_p2 --kc 5,
verify, lift (with and without RR_CTRL=overlap), RR_CTRL=overlap wf_u --top 12 --kc 5, and RR_CTRL=overlap --stage light.
Nothing is written outside this directory. R is never edited; the live desk / homebase code / ~/.homebase are never touched.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse                         # noqa: E402
import csv                              # noqa: E402
import datetime as dt                   # noqa: E402
import json                             # noqa: E402
import math                             # noqa: E402
import time                             # noqa: E402
import zlib                             # noqa: E402
from collections import defaultdict     # noqa: E402
from pathlib import Path                # noqa: E402
from types import SimpleNamespace       # noqa: E402

import numpy as np                      # noqa: E402

HERE = Path(__file__).resolve().parent
L2 = HERE.parent / "2026-10-01-l2"
sys.path.insert(0, str(L2))
import score as S                       # noqa: E402  (R read-only, gates incl. today's NFP window, holdout sealed)

sys.path.remove(str(L2))                # L2 has its own screen_analyze.py: R's modules must resolve to R
sys.path.insert(0, str(S.R))
E, F, P = S.E, S.F, S.P
import a3_rules as A1                   # noqa: E402
import a3_pass2 as A2                   # noqa: E402
import a3p2_lp as LP                    # noqa: E402
import a3p3 as A3                       # noqa: E402
import screen_analyze as SA             # noqa: E402
import funded_search as FS              # noqa: E402
import wf_offline as WF                 # noqa: E402

assert Path(SA.__file__).resolve().parent == S.R.resolve() and Path(A2.__file__).resolve().parent == S.R.resolve()
ROUT = S.R / "out"
OUT = HERE / "out"
MODEL = "intraday"
LUCID = ("lucid", "lucidpro", "lucidpro_nodll")
FIRMS5 = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
FIRM_LABEL = {"lucid": "Lucid Flex", "lucidpro": "LucidPro +DLL", "lucidpro_nodll": "LucidPro noDLL", "apex": "Apex (user set, UNCONF.)",
              "apex_eod": "Apex EOD (UNCONF.)"}
LV = ("flex", "flex_dll", "pro_dll", "pro_nodll")
V_LABEL = {"flex": "Flex funded", "flex_dll": "Flex funded +DLL1200*", "pro_dll": "Pro funded +DLL", "pro_nodll": "Pro funded noDLL"}
EVAL_OF = {"flex": "lucid", "flex_dll": "lucid", "pro_dll": "lucidpro", "pro_nodll": "lucidpro_nodll"}
FEE = {"lucid": 100.0, "lucidpro": 115.0, "lucidpro_nodll": 140.0}
MICROS_COARSE = [10, 20, 40]            # R's coarse screen used [20, 40]; 10 added because intraday picks sit at the small end
K_PICK = 30                             # R used 150 (then kept 100); 30 per variant for run time
CRITERION = 0.60


# ------------------------------------------------------------------ control switch (fix round)
# R's day-matched control (evalcore.daymatched_pick, no_overlap=True) keeps, for a config with k > 1 trades on a day, only pool trades that do
# not overlap each other. That favours SHORT trades: winners where the exit is a tight target / wide stop, losers where it is a tight stop /
# trailing exit. Measured (K=5, 1 NQ): fp-rsi2-tf5#13 mid pool mean -$2 a trade -> control +$26 (first trade of the day +$74);
# hm2-donchian-tf1#35 pm pool +$4 -> control -$72 (first trade -$165). So R's control is not zero-edge for multi-trade configs (it is exact
# for one-trade-a-day configs: k = 1 never meets the overlap test). RR_CTRL=overlap (environment, inherited by the spawn workers) draws the
# same k trades per (date, session) WITHOUT the overlap test: a uniform draw, mean = the pool's. Outputs of that mode carry the tag '_u'.
import os                               # noqa: E402

CTRL_UNBIASED = os.environ.get("RR_CTRL") == "overlap"
CTAG = "_u" if CTRL_UNBIASED else ""
if CTRL_UNBIASED:
    _R_DMC = E.daymatched_controls

    def _dmc_overlap(*a, **k):
        k["no_overlap"] = False
        return _R_DMC(*a, **k)

    E.daymatched_controls = _dmc_overlap


# ------------------------------------------------------------------ compute windows

def gate(lead_s: float = 60.0) -> None:
    """Sleep out 09:18-09:36 ET (weekdays) and Fri 2026-10-02 08:15-08:50 ET (score.blackout_wait_s)."""
    while True:
        s = S.blackout_wait_s(lead_s=lead_s)
        if not s:
            return
        print(f"[gate] compute window, sleeping {s:.0f}s", flush=True)
        time.sleep(s)


LP.gate = lambda margin_min=12: gate(120.0)          # R's a3p3 / wf tasks call LP.gate() at task start
_R_MAKE_A = A2.make_A


def _make_A_gated(*a, **k):                          # every uncached eval walk (a3p3.make_A3, wf_offline.search_ps) checks the clock
    gate()
    return _R_MAKE_A(*a, **k)


A2.make_A = _make_A_gated                            # funded walks: FS.grid_arrays calls F.desk_window_wait (score's) before every cell


# ------------------------------------------------------------------ funded (model = intraday)

def task_s1i(c):
    gate()
    t, pl, pool, cal, idx, Pt = FS.build_cfg_port(c)
    rows = []
    for v in LV:
        Sp = FS.spec(v)
        g = FS.grid_of(Sp, {**FS.GRID_COARSE, "micros": MICROS_COARSE})
        cells, A = FS.grid_arrays(Pt, Sp, g, MODEL)
        M = FS.agg(A, np.arange(A["first"].shape[1]))
        i = FS.pick(M["e_net_40"], FS.nrules(g, cells), np.ones(len(cells), bool))
        r = dict(cid=c["cid"], variant=v, model=MODEL, cells=len(cells))
        if i is not None:
            r.update(FS.row_at(M, i))
            r["cell"] = FS.cellname(FS.cell_dict(g, cells[i]))
        rows.append(r)
    return rows


def _alt_models(Pt, Sp, row):
    """R's old primary (realized) and the eod bound at the intraday-chosen cell."""
    src = F.DaySrc(Pt, {k: row[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}, row["micros"], events=False)
    for m in ("realized", "eod"):
        mm = F.metrics(F.lifecycle(Sp, src, row["policy"], FS.H, m), FS.H)
        for a, b in (("e40", "e_net_40"), ("p20", "p_pay_20"), ("p40", "p_pay_40"), ("bust_pre", "p_bust_pre_first"), ("med", "med_days_first")):
            row[f"{m}_{a}"] = mm[b]


def task_s2i(a):
    c, variants = a
    gate()
    t, pl, pool, cal, idx, Pt = FS.build_cfg_port(c)
    FS.CAL_HOLDER[:] = [cal]
    cps = FS.lift_ports(c, t, pool, cal, idx, FS.K_CTRL)
    rows = []
    for v in variants:
        Sp = FS.spec(v)
        row, wf = FS.analyze(Pt, Sp, v, FS.grid_of(Sp, None), ctl_ports=cps, model=MODEL)
        row["model"] = MODEL
        row.update(FS.cfg_meta(c))
        row["pool_flag"] = pl["flag"]
        if row.get("status") == "ok":
            _alt_models(Pt, Sp, row)
        if wf:
            row["wf_picks"] = ";".join(f"{p['q']}:{p['cell']}" for p in wf["picks"])
        rows.append(row)
    return rows


def task_nulli(a):
    nid, st = a
    gate()
    r = FS.pseudo_port(st)
    if r is None:
        return []
    Pt, cal, n, seed = r
    FS.CAL_HOLDER[:] = [cal]
    rows = []
    for v in LV:
        Sp = FS.spec(v)
        row, wf = FS.analyze(Pt, Sp, v, FS.grid_of(Sp, None), ctl_ports=None, do_wf=(nid < FS.N_NULL_WF), model=MODEL)
        row["model"] = MODEL
        row.update(dict(cid=f"null{nid}", kind="null", sess=st[1], trades=n, seed=seed, pool_id=st[0], tgt_r=st[4]["tgt_r"]))
        rows.append(row)
    return rows


def jl(p):
    """Rows of a run_ckpt checkpoint; a task id that appears twice (a restart while a task was in flight) counts once (last wins)."""
    p = Path(p)
    by = {}
    for ln in (p.read_text().splitlines() if p.exists() else []):
        if ln.strip():
            j = json.loads(ln)
            by[j["id"]] = j["rows"]
    return [r for rows in by.values() for r in rows]


def stage_funded_s1(a):
    cs = FS.load_cands()
    if a.limit:
        cs = cs[a.offset:a.offset + a.limit]
    print(f"funded_s1: {len(cs)} configs x {len(LV)} variants, model {MODEL}, coarse micros {MICROS_COARSE}", flush=True)
    A2.run_ckpt(task_s1i, cs, lambda c: c["cid"], a.workers, "s1i", OUT / "funded_s1.jsonl")


def stage_funded_pick(a):
    by = defaultdict(list)
    for r in jl(OUT / "funded_s1.jsonl"):
        if r.get("e_net_40") is not None:
            by[r["variant"]].append(r)
    sel = defaultdict(list)
    for v in LV:
        rs = sorted(by[v], key=lambda r: -r["e_net_40"])
        for r in rs[:a.k]:
            sel[r["cid"]].append(v)
        print(v, "screened", len(rs), "top-K coarse E$40 >=", round(rs[min(a.k, len(rs)) - 1]["e_net_40"], 1), "max", round(rs[0]["e_net_40"], 1), flush=True)
    (OUT / "funded_pick.json").write_text(json.dumps(sel))
    print(len(sel), "configs,", sum(len(v) for v in sel.values()), "pairs selected", flush=True)


def stage_funded_s2(a):
    sel = json.loads((OUT / "funded_pick.json").read_text())
    cs = {c["cid"]: c for c in FS.load_cands()}
    tasks = sorted(((cs[k], v) for k, v in sel.items()), key=lambda t: -t[0]["trades"] * len(t[1]))
    if a.limit:
        tasks = tasks[a.offset:a.offset + a.limit]
    print(f"funded_s2: {len(tasks)} configs, {sum(len(t[1]) for t in tasks)} pairs", flush=True)
    A2.run_ckpt(task_s2i, tasks, lambda t: t[0]["cid"], a.workers, "s2i", OUT / "funded_s2.jsonl")


def stage_funded_null(a):
    cs = FS.load_cands()
    rg = np.random.default_rng(20260930)                 # R's stage_null seed -> the SAME 60 pseudo-configs as R's realized-model null
    strata = []
    for rep in range(FS.N_NULL):
        c = cs[int(rg.integers(len(cs)))]
        pid = json.dumps(A3.resolve(c["prof"])["profile"], sort_keys=True)
        strata.append((pid, c["sess"], c["trades"], rep, E.profile_from("random", json.loads(pid))))
    tasks = list(enumerate(strata))[: a.n_null]          # the first n of R's 60 (run time); the first 20 carry the walk-forward
    print(f"funded_null: {len(tasks)} pseudo-configs", flush=True)
    A2.run_ckpt(task_nulli, tasks, lambda t: f"null{t[0]}", a.workers, "nulli", OUT / "funded_null.jsonl")


# ------------------------------------------------------------------ eval walk-forward (objective = intraday)

def gather_wf(top=10):
    """Per Lucid firm: the `top` pass-3 family-grid x session sets ranked by the best INTRADAY P5 of any member (R's gather3 with the
    intraday cellset instead of the firm's old primary); members = every pass-3 (key, sess) of that grid x session."""
    srcs = {s[3]: s for s in A3.sources3()}
    best, mem = defaultdict(dict), defaultdict(set)
    for r in csv.DictReader((ROUT / "a3p3_rules.csv").open()):
        gs = (r["key"].split("#")[0], r["sess"])
        mem[gs].add(r["key"])
        if r["cellset"] == "p5_intraday" and r["firm"] in LUCID:
            best[r["firm"]][gs] = max(float(r["intraday_p5"]), best[r["firm"]].get(gs, -1.0))
    out = {}
    for f in LUCID:
        ts = sorted(best[f].items(), key=lambda kv: (-kv[1], kv[0]))[:top]
        out[f] = [(g, s, sorted((srcs[k] for k in mem[(g, s)]), key=lambda x: x[3]), v) for (g, s), v in ts]
    return out


def task_wf(a):
    """wf_offline.task (R) with ONE change: every member's day-matched random controls are drawn from ITS OWN exit-profile pool.
    R's task resolves a single pool from the grid's FIRST cell and uses it for every cell; on the fast-pass grids (16 different
    stop / target profiles, first cell = 10-pt stop with a 2.5-pt target) that control can never reach the target, so R's stored
    control P5 is 0.00 there and its 'lift' is the whole P5. Everything else (windows, search, stable pick, stitching) is R's code."""
    grid, sess, f, members, kc, mods = a
    mods = tuple(mods)
    gate(120.0)
    ts = {m[3]: A2.load_src(m[0]) for m in members}
    pools, pk, flags = {}, {}, set()
    for m in members:
        pl = A2.resolve(E.profile_from(m[1], dict(m[4], tf=m[2])))
        k = tuple(pl["srcs"])
        if k not in pools:
            pools[k] = A2.pool_of(pl["srcs"])
        pk[m[3]] = k
        if pl["flag"]:
            flags.add(pl["flag"])
    cal = SA.cal_for(*ts.values(), *pools.values())
    D = len(cal)
    W, tests, oos = WF.windows(cal)
    sc = E.SESS_CODE[sess]
    out = {"grid": grid, "sess": sess, "firm": f, "members": [m[3] for m in members], "D": D, "n_starts": D - E.H_EVAL + 1, "models": list(mods),
           "test_dates": [[int(cal[i]) for i in tt] for tt in tests], "reps": [], "pool_flags": sorted(flags), "n_pools": len(pools)}
    ports = {}
    for m in members:
        t = ts[m[3]]
        idx = np.flatnonzero(t.sess == sc)
        ports[m[3]] = [A2.port_of(t, idx, cal)]
        if kc:
            cps, _, _ = A2.ctl_ports(dict(date=t.date[idx], sess=t.sess[idx]), pools[pk[m[3]]], cal, zlib.crc32(f"{m[3]}|{sess}".encode()), kc)
            ports[m[3]] += cps
    for rep in range(kc + 1):                             # rep 0 = the real configs, 1..kc = day-matched controls
        per_cfg, walks = [], 0
        for m in members:
            PS, nr, shape, w = WF.search_ps(ports[m[3]][rep], D, f, mods)
            walks += w
            per_cfg.append(WF.reduce_cfg(PS, nr, shape, W, tests, oos, mods))
        sel = WF.pick_across(per_cfg, mods)
        sel["rep"], sel["walks"] = rep, walks
        for mod in mods:
            for x in [sel[mod]["full"]] + sel[mod]["q"]:
                x["rules"] = [int(A2.GR[f][ax][i]) for ax, i in zip(A2.AX, np.unravel_index(x["cell"], shape))]
        out["reps"].append(sel)
    return [out]


def stage_wf(a):
    tasks = []
    for f, sets in gather_wf(a.top).items():
        tasks += [(g, s, f, m, a.kc, (MODEL,)) for g, s, m, _ in sets]
    tasks.sort(key=lambda t: len(t[3]))                  # light first
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"wf: {len(tasks)} tasks (Lucid firm x top-{a.top} pass-3 family grid x session by intraday P5), kc={a.kc}", flush=True)
    A2.run_ckpt(task_wf, tasks, lambda t: f"{t[0]}|{t[1]}|{t[2]}", a.workers, "wfi", OUT / "wf_intraday_part.jsonl")


# ------------------------------------------------------------------ eval: R's stored intraday cells + verification

def read_rules():
    """R's pass-3 rows of the intraday-stable cell: one per (config, session, firm). 1,283 configs x 5 firms."""
    rows = []
    for fn, p2 in (("a3p3_rules.csv", 0), ("a3p3_rescore2.csv", 1)):
        for r in csv.DictReader((ROUT / fn).open()):
            if r["cellset"] == "p5_intraday":
                r["pass2"] = p2
                rows.append(r)
    for r in jl(OUT / "eval_p2x_part.jsonl"):     # fix round: the pass-2 configs R never carried into pass 3 (same task_real3, see stage_eval_p2x)
        rows.append(dict(r, pass2=1, p2x=1))
    return rows


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def top_eval(rows, f, k=10, cap=1, sigs=None):
    """Top k of firm f by the STABLE intraday P5 (R's neighbour-median score; ties by the cell's own P5), R's top-list convention:
    one per family grid x session (grid = the key before '#'), and the same TRADE never fills a second slot. With `sigs`
    ({(key, sess): signature of every entry time + side}) two configs are the same trade when their entries are identical and the
    outcome at the reported cell is identical (P1, P2, P3, P5, bust) -- e.g. one clock trade reached from three heat-map grids whose
    only difference (the ATR stop) is overridden by the day stop. Kept rows get r['same_trade'] = the twins' keys."""
    rs = sorted((r for r in rows if r["firm"] == f), key=lambda r: (-fnum(r["stab"]), -fnum(r["intraday_p5"]), r["key"]))

    def sig(r):
        if sigs is None:
            return (r["fam"], r["tf"], r["sess"], r["trades"], r["net_1nq"], r["intraday_p5"], r["realized_p5"])
        return (sigs[(r["key"], r["sess"])], r["sess"]) + tuple(round(fnum(r[c]), 6) for c in ("intraday_p1", "intraday_p2", "intraday_p3", "intraday_p5", "intraday_bust5"))

    twins = defaultdict(list)
    for r in rs:
        twins[sig(r)].append(r["key"])
    out, cnt, seen = [], defaultdict(int), set()
    for r in rs:
        g = (r["key"].split("#")[0], r["sess"])
        if sig(r) in seen or cnt[g] >= cap:
            continue
        seen.add(sig(r))
        cnt[g] += 1
        r["same_trade"] = [x for x in twins[sig(r)] if x != r["key"]]
        out.append(r)
        if len(out) >= k:
            break
    return out


def load_sigs():
    """{(key, sess): entry signature} from the light stage's cache (out/cfg_stats.json); None before the light stage has built it."""
    p = OUT / "cfg_stats.json"
    if not p.exists():
        return None
    d = {tuple(k.split("|")): v.get("sig") for k, v in json.loads(p.read_text()).items()}
    return d if all(v is not None for v in d.values()) else None


def task_verify(a):
    key, sess, f, p2 = a
    gate()
    srcs = {s[3]: s for s in (A3.sources2() if p2 else A3.sources3())}
    rows = A3.task_real3((*srcs[key][:5], [(sess, (f,), {})], A3.K_CTRL, bool(p2)))
    return [r for r in rows if r["cellset"] == "p5_intraday"]


def stage_verify(a):
    rows = read_rules()
    sigs = load_sigs()
    if sigs is not None and any((r["key"], r["sess"]) not in sigs for r in rows):
        sigs = None
    tasks = [(r["key"], r["sess"], f, int(r["pass2"])) for f in FIRMS5 for r in top_eval(rows, f, sigs=sigs)]
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"verify: {len(tasks)} (config, session, firm) re-computed from the bundles", flush=True)
    A2.run_ckpt(task_verify, tasks, lambda t: f"{t[0]}|{t[1]}|{t[2]}", a.workers, "verify", OUT / "verify_part.jsonl")


# ------------------------------------------------------------------ fix round (2026-10-02, after verification)

def p2x_keys(eligible=True):
    """Pass-2 configs R searched under intraday in pass 2 (a3p2_rules.csv) but never carried into pass 3: a3p3's rescore2 kept its OLD-model
    shortlists plus the top-40 intraday configs of lucid / apex only (none for the two LucidPro firms). eligible = R's candidate filter for
    heat-map cells (>= 300 trades, net > 0 at 1 NQ). -> {(key, sess): dict(trades, net_1nq)}"""
    have = {(r["key"], r["sess"]) for r in csv.DictReader((ROUT / "a3p3_rescore2_cfgs.csv").open())}
    out = {}
    for r in csv.DictReader((ROUT / "a3p2_rules.csv").open()):
        if r["firm"] == "lucid" and r["model"] == "intraday" and (r["key"], r["sess"]) not in have:
            n, net = int(float(r["trades"])), float(r["net_1nq"])
            if not eligible or (n >= 300 and net > 0):
                out[(r["key"], r["sess"])] = dict(trades=n, net_1nq=net)
    return out


def task_p2x(a):
    return [r for r in A3.task_real3(a) if r["cellset"] == "p5_intraday"]          # task_real3 gates itself (LP.gate, patched above)


def stage_eval_p2x(a):
    srcs = {s[3]: s for s in A3.sources2()}
    by = defaultdict(list)
    for key, sess in sorted(p2x_keys()):
        by[key].append((sess, FIRMS5, dict(net_le0=0, fastpass=0, pass2=1)))
    tasks = [(*srcs[k][:5], sorted(v, key=lambda e: list(E.SESS).index(e[0])), A3.K_CTRL, True) for k, v in by.items()]
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"eval_p2x: {sum(len(t[5]) for t in tasks)} pass-2 configs in {len(tasks)} sources x {len(FIRMS5)} firms (R's pass-3 analysis)", flush=True)
    A2.run_ckpt(task_p2x, tasks, lambda t: t[3], a.workers, "p2x", OUT / "eval_p2x_part.jsonl")


def all_cands():
    """R's 1,283 candidates + the pass-2 extension configs, in FS.load_cands' shape."""
    cs = FS.load_cands()
    srcs = {s[3]: s for s in A3.sources2()}
    for (key, sess), v in sorted(p2x_keys().items()):
        src, fam, tf, _, params = srcs[key]
        cs.append(dict(cid=f"{key}|{sess}", key=key, sess=sess, src=src, fam=fam, tf=tf, params=params, prof=E.profile_from(fam, dict(params, tf=tf)),
                       trades=v["trades"], net_1nq=v["net_1nq"], fastpass=0, pool_group="", apex_cfg_flags=[], eval={}, p2x=1))
    return sorted(cs, key=lambda c: -c["trades"])


def wf_windows(cal, nS, H_=None, train_days=365):
    """FS.walk_forward's windows: per test quarter (label, train start indices, test start indices). Train = starts in the trailing 12 months
    whose whole 60-session life ends before the quarter; test = starts inside the quarter (>= 20 of them, >= 60 train starts)."""
    H_ = H_ or FS.H
    dts, qs = FS.quarters(cal)
    out = []
    for q0, q1 in qs:
        te = [s for s, d in enumerate(dts) if q0 <= d < q1 and s < nS]
        if len(te) < 20:
            continue
        i0 = next(s for s, d in enumerate(dts) if d >= q0)
        lo = q0 - dt.timedelta(days=train_days)
        tr = [s for s, d in enumerate(dts) if d >= lo and s + H_ <= i0]
        if len(tr) < 60:
            continue
        out.append((f"{q0.year}Q{(q0.month - 1) // 3 + 1}", np.array(tr), np.array(te)))
    return out


def task_nwf(c):
    """NESTED funded walk-forward, config level. For one config x account type: the coarse funded grid (192 cells) once, then per test quarter
    the cell with the best stable E$40 on the TRAINING window only (R's walk_forward score) and what that cell paid on the test quarter.
    The light stage then picks, per quarter, the best CONFIG by the same training score: nothing from the test quarter (or later) is used."""
    gate()
    t, pl, pool, cal, idx, Pt = FS.build_cfg_port(c)
    rows = []
    for v in LV:
        Sp = FS.spec(v)
        g = FS.grid_of(Sp, {**FS.GRID_COARSE, "micros": MICROS_COARSE})
        cells, A = FS.grid_arrays(Pt, Sp, g, MODEL)
        nS = A["first"].shape[1]
        shape, nr, ok = FS.shape_of(g), FS.nrules(g, cells), np.ones(len(cells), bool)
        M = FS.agg(A, np.arange(nS))
        i = FS.pick(M["e_net_40"], nr, ok)                                    # the full-sample coarse row (= task_s1i)
        r = dict(cid=c["cid"], variant=v, model=MODEL, cells=len(cells), n_starts=int(nS), q=[])
        if i is not None:
            r.update(FS.row_at(M, i))
            r["cell"] = FS.cellname(FS.cell_dict(g, cells[i]))
        for lab, tr, te in wf_windows(cal, nS):
            Mt = FS.agg(A, tr)
            sc = np.minimum(Mt["e_net_40"], FS.stability(Mt["e_net_40"], shape))
            ci = FS.pick(sc, nr, ok)
            if ci is None:
                continue
            first = A["first"][ci, te]
            paid = first > 0
            r["q"].append(dict(q=lab, score=float(sc[ci]), train_e40=float(Mt["e_net_40"][ci]), n_train=int(len(tr)), n_test=int(len(te)),
                               cd=FS.cell_dict(g, cells[ci]), sum_n40=float(A["n40"][ci, te].sum()), n_pay40=int((paid & (first <= 40)).sum()),
                               n_bust_pre=int(((A["bust"][ci, te] > 0) & ~paid).sum())))
        rows.append(r)
    return rows


def stage_funded_nwf(a):
    cs = all_cands()
    if a.limit:
        cs = cs[a.offset:a.offset + a.limit]
    print(f"funded_nwf: {len(cs)} configs x {len(LV)} variants, model {MODEL}, coarse grid, per-quarter train pick + test outcome", flush=True)
    A2.run_ckpt(task_nwf, cs, lambda c: c["cid"], a.workers, "nwf", OUT / "funded_nwf.jsonl")


def stage_funded_pick2(a):
    """Top K per variant by the full-sample coarse E$40 over the EXTENDED universe (funded_nwf.jsonl carries the task_s1i row of every config)."""
    by = defaultdict(list)
    for r in jl(OUT / "funded_nwf.jsonl"):
        if r.get("e_net_40") is not None:
            by[r["variant"]].append(r)
    sel = defaultdict(list)
    for v in LV:
        rs = sorted(by[v], key=lambda r: -r["e_net_40"])
        for r in rs[:a.k]:
            sel[r["cid"]].append(v)
        print(v, "screened", len(rs), "top-K coarse E$40 >=", round(rs[min(a.k, len(rs)) - 1]["e_net_40"], 1), "max", round(rs[0]["e_net_40"], 1), flush=True)
    (OUT / "funded_pick2.json").write_text(json.dumps(sel))


def stage_funded_s2b(a):
    """R's full funded grid on the (config, variant) pairs of funded_pick2.json that funded_s2.jsonl does not hold yet."""
    sel = json.loads((OUT / "funded_pick2.json").read_text())
    have = {(r["cid"], r["variant"]) for r in jl(OUT / "funded_s2.jsonl")}
    cs = {c["cid"]: c for c in all_cands()}
    tasks = [(cs[k], [x for x in v if (k, x) not in have]) for k, v in sel.items()]
    tasks = sorted((t for t in tasks if t[1]), key=lambda t: -t[0]["trades"] * len(t[1]))
    print(f"funded_s2b: {len(tasks)} configs, {sum(len(t[1]) for t in tasks)} new pairs", flush=True)
    A2.run_ckpt(task_s2i, tasks, lambda t: t[0]["cid"], a.workers, "s2b", OUT / "funded_s2b.jsonl")


def task_nwf_ctl(a):
    """The nested walk-forward's picks, start by start: the picked (config, cell) on its test quarter and K day-matched random controls
    (same days, same session, the config's exit-profile pool) at the same rules, same starts."""
    c, jobs = a
    gate()
    t, pl, pool, cal, idx, Pt = FS.build_cfg_port(c)
    cps = FS.lift_ports(c, t, pool, cal, idx, FS.K_CTRL)
    wins = {lab: te for lab, _, te in wf_windows(cal, len(cal) - FS.H + 1)}
    rows = []
    for v, lab, cd in jobs:
        Sp = FS.spec(v)
        rl = {k: cd[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}
        te = wins[lab]

        def arr(port):
            return FS.start_arrays(F.lifecycle(Sp, F.DaySrc(port, rl, cd["micros"], events=False), cd["policy"], FS.H, MODEL, [int(s) for s in te]))
        real = arr(Pt)
        ctl = [arr(cp)["n40"] for cp in cps]
        rows.append(dict(cid=c["cid"], variant=v, q=lab, cell=FS.cellname(cd), dates=[int(cal[s]) for s in te], n40=real["n40"].tolist(),
                         first=real["first"].tolist(), bust=real["bust"].tolist(), ctl_n40=np.mean(ctl, 0).tolist(),
                         ctl_e40=[float(x.mean()) for x in ctl], pool_flag=pl["flag"]))
    return rows


def stage_nwf_ctl(a):
    jobs = json.loads((OUT / "funded_nwf_picks.json").read_text())           # written by the light stage nwf_agg: {cid: [[variant, q, cell dict]]}
    cs = {c["cid"]: c for c in all_cands()}
    tasks = [(cs[k], v) for k, v in jobs.items()]
    print(f"nwf_ctl: {len(tasks)} configs, {sum(len(t[1]) for t in tasks)} (variant, quarter) picks, K={FS.K_CTRL} controls", flush=True)
    p = OUT / f"funded_nwf_ctl{CTAG}.jsonl"
    if p.exists():
        p.unlink()                                                             # small stage, always re-run for the current picks
    A2.run_ckpt(task_nwf_ctl, tasks, lambda t: t[0]["cid"], a.workers, "nwfc", p)


def stage_wf_p2(a):
    """The pilot's pass-2 heat-map grids (R's wf_offline, first-MEMBER control pool) re-run with task_wf: each member's controls from its own
    exit-profile pool. Only the grids whose members resolve to more than one pool (single-config screen grids are already own-pool)."""
    tasks = []
    for g, s, mem in WF.gather():
        if len({tuple(A2.resolve(E.profile_from(m[1], dict(m[4], tf=m[2])))["srcs"]) for m in mem}) > 1:
            tasks += [(g, s, f, mem, a.kc, (MODEL,)) for f in LUCID]
    tasks.sort(key=lambda t: len(t[3]))
    # --rev: a second process works from the heaviest end into its own part file; each process skips what either file already holds at its start
    files = [OUT / "wf_intraday_p2_part.jsonl", OUT / "wf_intraday_p2_part_b.jsonl"]
    done = {json.loads(ln)["id"] for fp in files if fp.exists() for ln in fp.read_text().splitlines() if ln.strip()}
    idf = lambda t: f"{t[0]}|{t[1]}|{t[2]}"                                  # noqa: E731
    tasks = [t for t in tasks if idf(t) not in done]
    if a.rev:
        tasks = tasks[::-1]
    if a.limit:
        tasks = tasks[: a.limit]
    print(f"wf_p2: {len(tasks)} tasks to run, {len(done)} done (Lucid firm x pass-2 multi-pool grid x session), kc={a.kc}, rev={a.rev}", flush=True)
    A2.run_ckpt(task_wf, tasks, idf, a.workers, "wfp2", files[1] if a.rev else files[0])


def max_trades_per_day(members, sess):
    """Largest number of trades on one day in session `sess` over the grid's members (1 = R's control is exact for this grid)."""
    mx = 0
    for m in members:
        t = A2.load_src(m[0])
        d = t.date[t.sess == E.SESS_CODE[sess]]
        if len(d):
            mx = max(mx, int(np.unique(d, return_counts=True)[1].max()))
    return mx


def stage_wf_u(a):
    """Eval walk-forward with the UNBIASED control (RR_CTRL=overlap) for the own-pool grids that trade more than once a day: this run's
    pass-3 grids and the pilot's one-config screen grids. (The pilot's multi-trade pass-2 heat-map grids are not re-run: about 20
    worker-minutes each.) Only the control replicates of these records are used; replicate 0 (the real configs) is unchanged."""
    assert CTRL_UNBIASED, "run with RR_CTRL=overlap"
    tasks, seen = [], {}
    for f, sets in gather_wf(a.top).items():
        for g, s, m, _ in sets:
            if (g, s) not in seen:
                seen[(g, s)] = max_trades_per_day(m, s)
            if seen[(g, s)] > 1:
                tasks.append((g, s, f, m, a.kc, (MODEL,)))
    for g, s, m in WF.gather():
        if len(m) == 1 and max_trades_per_day(m, s) > 1:
            tasks += [(g, s, f, m, a.kc, (MODEL,)) for f in LUCID]
    tasks.sort(key=lambda t: len(t[3]))
    print(f"wf_u: {len(tasks)} tasks (own-pool multi-trade grids), kc={a.kc}, unbiased control", flush=True)
    A2.run_ckpt(task_wf, tasks, lambda t: f"{t[0]}|{t[1]}|{t[2]}", a.workers, "wfu", OUT / "wf_intraday_u_part.jsonl")


def task_lift(a):
    """One reported pick against its K day-matched random controls at the pick's own cell, replicate by replicate."""
    kind, key, sess, fv, cell, p2 = a
    gate()
    if kind == "eval":
        src, fam, tf, _, params = {s[3]: s for s in (A3.sources2() if p2 else A3.sources3())}[key]
        t = A2.load_src(src)
        pl = A3.resolve(E.profile_from(fam, dict(params, tf=tf)), bool(p2))
        pool = A2.pool_of(pl["srcs"])
        idx = np.flatnonzero(t.sess == E.SESS_CODE[sess])
        cal = SA.cal_for(t, pool)
        D = len(cal)
        cps, fb, _ = A2.ctl_ports(dict(date=t.date[idx], sess=t.sess[idx]), pool, cal, zlib.crc32(f"{key}|{sess}".encode()), A3.K_CTRL)

        def val(port):
            return float((A3.eval_cell3(port, D, fv, tuple(cell))[0]["intraday"][0] == 1).mean())
        own = val(A2.port_of(t, idx, cal))
    else:
        c = {x["cid"]: x for x in all_cands()}[f"{key}|{sess}"]
        t, pl, pool, cal, idx, Pt = FS.build_cfg_port(c)
        cps = FS.lift_ports(c, t, pool, cal, idx, FS.K_CTRL)
        Sp = FS.spec(fv)
        rl = {k: cell[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}

        def val(port):
            return float(F.metrics(F.lifecycle(Sp, F.DaySrc(port, rl, cell["micros"], events=False), cell["policy"], FS.H, MODEL), FS.H)["e_net_40"])
        own = val(Pt)
    cv = [val(cp) for cp in cps]
    d = t.date[idx]
    return [dict(kind=kind, key=key, sess=sess, fv=fv, own=own, ctrl=float(np.mean(cv)), ctrl_reps=cv, lift=own - float(np.mean(cv)), beats=int(sum(own > x for x in cv)),
                 K=len(cv), max_tr_day=int(np.unique(d, return_counts=True)[1].max()), pool_flag=pl["flag"], control="overlap allowed" if CTRL_UNBIASED else "R (no overlap)")]


def stage_lift(a):
    """The reported eval top 10 (5 firms) and funded top 5 (4 account types) against their controls, replicate by replicate. With
    RR_CTRL=overlap the control is the unbiased draw -> out/lift_u.jsonl (else R's control -> out/lift.jsonl)."""
    et = json.loads((OUT / "eval_top.json").read_text())
    ft = json.loads((OUT / "funded_top.json").read_text())
    tasks = [("eval", r["key"], r["sess"], f, [r[k] for k in A2.AX], int(r["pass"] == 2)) for f in FIRMS5 for r in et["top"][f]]
    tasks += [("funded", r["key"], r["sess"], v, {k: r[k] for k in ("micros", "day_take", "day_lock", "day_stop", "max_day_tr", "policy")}, 0) for v in LV for r in ft["top"][v]]
    print(f"lift{CTAG}: {len(tasks)} picks", flush=True)
    p = OUT / f"lift{CTAG}.jsonl"
    if p.exists():
        p.unlink()
    A2.run_ckpt(task_lift, tasks, lambda t: f"{t[0]}|{t[1]}|{t[2]}|{t[3]}", a.workers, "lift", p)


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--k", type=int, default=K_PICK)
    ap.add_argument("--kc", type=int, default=3, help="walk-forward: day-matched random controls per grid (R used 5)")
    ap.add_argument("--top", type=int, default=10, help="walk-forward: family grids per firm (R used 12)")
    ap.add_argument("--n-null", type=int, default=30, help="funded null: pseudo-configs (R used 60)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--rev", action="store_true", help="wf_p2: heaviest first into wf_intraday_p2_part_b.jsonl (second process)")
    a = ap.parse_args(argv)
    if a.workers > 4:
        raise SystemExit("<= 4 workers (another research job shares the machine)")
    OUT.mkdir(exist_ok=True)
    heavy = {"funded_s1": stage_funded_s1, "funded_pick": stage_funded_pick, "funded_s2": stage_funded_s2, "funded_null": stage_funded_null,
             "verify": stage_verify, "wf": stage_wf}
    fix = {"eval_p2x": stage_eval_p2x, "funded_nwf": stage_funded_nwf, "funded_pick2": stage_funded_pick2, "funded_s2b": stage_funded_s2b,
           "nwf_ctl": stage_nwf_ctl, "wf_p2": stage_wf_p2, "wf_u": stage_wf_u, "lift": stage_lift}                       # fix round: run by name (order in the module docstring)
    if a.stage in fix:
        fix[a.stage](a)
        return
    if a.stage == "heavy":
        for nm, fn in heavy.items():
            print(f"=== {nm} {dt.datetime.now(S.ET):%H:%M:%S} ET", flush=True)
            fn(a)
        return
    if a.stage in heavy:
        heavy[a.stage](a)
        return
    import rerank_light as RL
    RL.run(a.stage, sys.modules[__name__])


if __name__ == "__main__":
    main()
