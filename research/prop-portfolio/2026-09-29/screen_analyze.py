#!/usr/bin/python3
"""Stage A1/A2 screen analysis (SPEC.md). Run with /usr/bin/python3, PYTHONPATH=~/ramos-quant-homebase.

  screen_analyze.py [--workers 8] [--allow-partial] [--out DIR]

Inputs : R/queue.jsonl (expected keys), R/ledger.csv (stage screen|ctrl), the run bundles' trades.json (research window only).
Outputs: R/out/screen_table.csv (one row per family x tf x session, both firms), R/out/screen_summary.md (<= 60 lines),
         R/out/screen_baseline.csv (random control at natural frequency, per tf/session/source/firm/size).

Per config (1 NQ): trade stats; prop metrics per firm with target_stop ON and no other daily rules (eod breach primary,
intraday sensitivity), sizes Lucid {10,20,40} / Apex {10,40,100} micros, best size = max P(pass<=5d) (ties -> smaller).
Edge lift vs a random control at the same tf+session: pooled default-exit random seeds (randomtod for tod_drift), thinned to
the config's trade count (keep prob q = n_cfg / n_pool, capped at 1), K=10 fixed-seed draws, same size/rules, mean over draws.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
import time
from multiprocessing import get_context
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E  # noqa: E402

R = E.D                                  # the pilot's data dir (NQ: the code dir)
SESSIONS = list(E.SESS)
FSHORT = {"lucid": "lu", "apex": "ap"}
SIZES = {"lucid": (10, 20, 40), "apex": (10, 40, 100)}
COMMON = 40
K_DRAWS = 10
MIN_TRADES = 300
MIN_CTRL_CFG = 1                          # controls are cheap: run them for every config that has a trade
RULES = E.norm_rules({"target_stop": True})
TICKS_RT_USD = {"nq": 2 * E.PL.TICK_FULL, "mnq": 2 * E.PL.TICK_USD}    # 2 ticks of slippage round trip, per contract (keys: full / micro)
COMM_RT_USD = {"nq": 4.0, "mnq": 1.0}
YEARS = (2021, 2022, 2023, 2024)


# ------------------------------------------------------------------ trade sets

class TS:
    """All trades of one run (or a pool of runs) as sorted numpy arrays + evalcore day-walk tuples."""

    def __init__(self, date, te, tx, side, g, mae, risk, net, sess, year):
        o = np.lexsort((te, date))
        self.date, self.te, self.tx, self.side, self.g, self.mae = (a[o] for a in (date, te, tx, side, g, mae))
        self.risk, self.net, self.sess, self.year = (a[o] for a in (risk, net, sess, year))
        self.n = len(date)
        self.rows = [(int(a), int(b), int(c), float(d), float(e), 10, float(f), 0) for a, b, c, d, e, f in
                     zip(self.te, self.tx, self.side, self.g, self.mae, self.risk)]

    @staticmethod
    def concat(parts):
        f = lambda k: np.concatenate([getattr(p, k) for p in parts])
        return TS(*(f(k) for k in ("date", "te", "tx", "side", "g", "mae", "risk", "net", "sess", "year")))

    def days(self, mask, cal):
        idx = np.flatnonzero(mask)
        pos = np.searchsorted(cal, self.date[idx])
        days = [[] for _ in range(len(cal))]
        for j, p in zip(idx, pos):
            days[p].append(self.rows[j])
        return days


class _Port:
    def __init__(self, days):
        self.days = days


def load_ts(run_id: str) -> TS:
    """evalcore loader (research window, per 1 NQ) + per-trade net straight from the same trades.json."""
    t = E.load(run_id)
    rows = [x for x in json.loads((E.RUNS / run_id / "trades.json").read_text()) if x["date"] < E.HOLDOUT]
    assert len(rows) == t.n, (run_id, len(rows), t.n)
    q = np.array([max(1.0, float(x.get("qty") or 1)) for x in rows])
    net = np.array([float(x["net"]) for x in rows]) / q
    year = np.array([int(d[:4]) for d in t.iso], np.int16)
    return TS(t.date, t.te, t.tx, t.side, t.g, t.mae, t.risk, net, t.sess, year)


# ------------------------------------------------------------------ evaluation

_FR = {}


def firm(f):
    if f not in _FR:
        rid, r = E.firm_rules(f)
        _FR[f] = (rid, r, E.PS._dll(r) or 0.0)
    return _FR[f]


def eval_days(days, D, sizes=SIZES, intraday=False, keep_out=False):
    """-> {(firm,size): {p, b, md, [pi, bi], [out]}} for the day lists (rolling 5-session eval starts, target_stop on)."""
    res = {}
    if D < E.H_EVAL:
        return res
    idx5 = np.arange(D - E.H_EVAL + 1)[:, None] + np.arange(E.H_EVAL)
    port = _Port(days)
    for f, szs in sizes.items():
        rid, r, dll = firm(f)
        for s in szs:
            A = E.walk(port, r["cap_micros"], RULES, want_chk=True, micros=s, dll=dll)
            o, d = E.race(idx5, A, r, "eod", True)
            ps = o == 1
            x = {"p": float(ps.mean()), "b": float((o == 2).mean()), "md": float(np.median(d[ps])) if ps.any() else float("nan")}
            if intraday:
                oi, _ = E.race(idx5, A, r, "intraday", True)
                x["pi"], x["bi"] = float((oi == 1).mean()), float((oi == 2).mean())
            if keep_out:
                x["out"] = ps
            res[(f, s)] = x
    return res


# ------------------------------------------------------------------ per-config trade stats

def trade_stats(ts: TS, m, cal, nd, D) -> dict:
    net, n = ts.net[m], int(m.sum())
    out = {"trades": n, "trades_per_day": n / D}
    if not n:
        return out
    win, los = net[net > 0], net[net <= 0]
    daily = np.zeros(D)
    np.add.at(daily, np.searchsorted(cal, ts.date[m]), net)
    sd = daily.std(ddof=1)
    sdn = net.std(ddof=1) if n > 1 else float("nan")
    out.update(
        wr=float((net > 0).mean()), net=float(net.sum()),
        pf=float(win.sum() / -los.sum()) if los.sum() < 0 else float("inf"),
        sharpe_d=float(daily.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan"),
        exp_usd=float(net.mean()), t_stat=float(net.mean() / (sdn / math.sqrt(n))) if sdn > 0 else float("nan"),
        rr=float(win.mean() / -los.mean()) if len(win) and len(los) and los.mean() < 0 else float("nan"))
    for y in YEARS:
        out[f"net_{y}"] = float(net[ts.year[m] == y].sum())
    out["net_long"], out["net_short"] = float(net[ts.side[m] > 0].sum()), float(net[ts.side[m] < 0].sum())
    isn = np.isin(ts.date[m], list(nd)) if nd else np.zeros(n, bool)
    out["net_news"], out["net_other"], out["n_news"] = float(net[isn].sum()), float(net[~isn].sum()), int(isn.sum())
    rk = ts.risk[m]
    med = float(np.nanmedian(rk)) if np.isfinite(rk).any() else float("nan")
    out["med_stop_pts"], out["stop_cover"] = med, float(np.isfinite(rk).mean())
    for ins, usd in (("nq", E.PL.PV), ("mnq", E.PL.PV_MICRO)):
        ratio = (COMM_RT_USD[ins] + TICKS_RT_USD[ins]) / (med * usd) if med == med and med > 0 else float("nan")
        out[f"cost_ratio_{ins}"], out[f"cost_pass_{ins}"] = ratio, bool(ratio == ratio and ratio < 0.03)
    return out


# ------------------------------------------------------------------ control pools

_POOL, _FULL = {}, {}


def pool(tf: str, kind: str, runs: dict, sess: str):
    """Pooled control trades of (tf, kind) in one session + K uniform vectors for thinning (fixed seeds)."""
    key = (tf, kind, sess)
    if key not in _POOL:
        if (tf, kind) not in _FULL:
            parts = [load_ts(r) for r in runs[(kind, tf)]]
            _FULL[(tf, kind)] = (TS.concat(parts), len(parts))
        ts, nparts = _FULL[(tf, kind)]
        m = ts.sess == E.SESS_CODE[sess]
        sel = np.flatnonzero(m)
        sub = TS(*(getattr(ts, k)[sel] for k in ("date", "te", "tx", "side", "g", "mae", "risk", "net", "sess", "year")))
        seedv = [E.SEED, E.SESS_CODE[sess], int(tf), 0 if kind == "random" else 1]
        U = np.stack([np.random.default_rng(seedv + [k]).random(sub.n) for k in range(K_DRAWS)]) if sub.n else np.zeros((K_DRAWS, 0))
        _POOL[key] = (sub, U, nparts)
    return _POOL[key]


def control(cfg_n: int, sub: TS, U, cal, D) -> dict:
    """Thin the pooled control to ~cfg_n trades (K draws); mean P/bust per (firm,size)."""
    q = min(1.0, cfg_n / sub.n) if sub.n else 0.0
    acc = {}
    ntr, ntd = [], []
    for k in range(K_DRAWS):
        m = U[k] < q
        ntr.append(int(m.sum()))
        dl = sub.days(m, cal)
        ntd.append(sum(1 for d in dl if d))
        for key, x in eval_days(dl, D).items():
            a = acc.setdefault(key, [[], [], []])
            a[0].append(x["p"]), a[1].append(x["b"]), a[2].append(x["md"])
    return {"q": q, "n_draw": float(np.mean(ntr)) if ntr else 0.0, "td_draw": float(np.mean(ntd)) if ntd else 0.0,
            "p": {k: float(np.mean(v[0])) for k, v in acc.items()}, "b": {k: float(np.mean(v[1])) for k, v in acc.items()},
            "p_sd": {k: float(np.std(v[0])) for k, v in acc.items()}}


# ------------------------------------------------------------------ tasks

def check_run(key: str, ts: TS, led: dict, warns: list) -> dict:
    """Self-check: sum of per-session net (+ trades) == the run's ledger total (tolerance $1)."""
    per = {s: float(ts.net[ts.sess == c].sum()) for s, c in E.SESS_CODE.items()}
    cnt = {s: int((ts.sess == c).sum()) for s, c in E.SESS_CODE.items()}
    un_n, un_net = int((ts.sess < 0).sum()), float(ts.net[ts.sess < 0].sum())
    tot, led_net = sum(per.values()), float(led["net"])
    if un_n:
        warns.append(f"{key}: {un_n} trades outside the 5 session windows (net {un_net:+.0f})")
    if abs(tot - led_net) > 1.0 or sum(cnt.values()) != int(led["trades"]):
        raise RuntimeError(f"SELF-CHECK FAILED {key}: sum(session net)={tot:.2f} vs ledger {led_net:.2f}; "
                           f"trades {sum(cnt.values())} vs {led['trades']}; unassigned {un_n} (net {un_net:+.2f})")
    return {"key": key, "diff": tot - led_net, "unassigned": un_n}


_CAL0 = []


def cal_for(*tss) -> np.ndarray:
    """Weekday tape sessions of the research window, plus any trade date not on the tape."""
    if not _CAL0:
        _CAL0.append(np.array(sorted(dt.date.fromisoformat(d).toordinal()
                                     for d in E.tape_sessions("2021-01-01", "2024-12-31")), np.int64))
    ords = _CAL0[0]
    for t in tss:
        ords = np.union1d(ords, t.date)
    return ords


def cfg_task(a):
    """One (family, tf) run -> 5 config rows (+ self-check)."""
    fam, tf, key, led, runs = a
    warns = []
    ts = load_ts(led["run_id"])
    chk = check_run(key, ts, led, warns)
    kind = "randomtod" if fam == "tod_drift" else "random"
    nd = E.news_days()
    rows = []
    for sess in SESSIONS:
        m = ts.sess == E.SESS_CODE[sess]
        row = {"fam": fam, "tf": int(tf), "sess": sess, "run_id": led["run_id"]}
        n = int(m.sum())
        if (kind, tf) not in runs:
            warns.append(f"{key}/{sess}: no {kind} control run for tf{tf}")
        cs = None
        if n >= MIN_CTRL_CFG and (kind, tf) in runs:
            cs = pool(tf, kind, runs, sess)
        cal = cal_for(ts, cs[0]) if cs else cal_for(ts)
        D = len(cal)
        row.update(trade_stats(ts, m, cal, nd, D))
        row["days"] = D
        row["trade_days"] = int(len(np.unique(ts.date[m])))
        row["ctrl_kind"] = kind
        if n:
            ev = eval_days(ts.days(m, cal), D, intraday=True, keep_out=True)
            ctl = control(n, cs[0], cs[1], cal, D) if cs and cs[0].n else None
            sub = cs[0] if cs else None
            row["ctrl_seeds"], row["ctrl_n_pool"] = (cs[2], sub.n) if cs else (0, 0)
            if ctl:
                row["ctrl_q"], row["ctrl_n_draw"], row["ctrl_trade_days"] = ctl["q"], ctl["n_draw"], ctl["td_draw"]
                mu, sg = float(sub.net.mean()), float(sub.net.std(ddof=1))
                row["ctrl_exp"], row["ctrl_std"] = mu, sg
                row["exp_z"] = (row["exp_usd"] - mu) / (sg / math.sqrt(n)) if sg > 0 else float("nan")
            for f, szs in SIZES.items():
                p = FSHORT[f]
                for s in szs:
                    row[f"{p}_p5_{s}"] = ev[(f, s)]["p"]
                best = max(szs, key=lambda s: (round(ev[(f, s)]["p"], 12), -s))
                x = ev[(f, best)]
                lo, hi = E.block_ci([x["out"]], boots=2000)[0]
                row.update({f"{p}_best": best, f"{p}_p5": x["p"], f"{p}_ci_lo": lo, f"{p}_ci_hi": hi, f"{p}_bust5": x["b"],
                            f"{p}_med_days": x["md"], f"{p}_p5_intra": x["pi"], f"{p}_bust5_intra": x["bi"],
                            f"{p}_p5_{COMMON}": ev[(f, COMMON)]["p"], f"{p}_bust5_{COMMON}": ev[(f, COMMON)]["b"]})
                if ctl:
                    row.update({f"{p}_ctrl_p5": ctl["p"][(f, best)], f"{p}_ctrl_bust5": ctl["b"][(f, best)],
                                f"{p}_ctrl_p5_sd": ctl["p_sd"][(f, best)],
                                f"{p}_lift": x["p"] - ctl["p"][(f, best)],
                                f"{p}_ctrl_p5_{COMMON}": ctl["p"][(f, COMMON)],
                                f"{p}_lift_{COMMON}": ev[(f, COMMON)]["p"] - ctl["p"][(f, COMMON)]})
                    for s in szs:
                        row[f"{p}_ctrl_p5_{s}"] = ctl["p"][(f, s)]
        rows.append(row)
    return {"rows": rows, "chk": chk, "warns": warns}


def base_task(a):
    """One control run -> self-check + natural-frequency P(pass<=5d) per session/firm/size (zero-edge baseline)."""
    kind, tf, seed, key, led = a
    warns = []
    ts = load_ts(led["run_id"])
    chk = check_run(key, ts, led, warns)
    cal = cal_for(ts)
    out = []
    for sess in SESSIONS:
        m = ts.sess == E.SESS_CODE[sess]
        if not m.any():
            continue
        for (f, s), x in eval_days(ts.days(m, cal), len(cal)).items():
            out.append({"kind": kind, "tf": int(tf), "seed": seed, "sess": sess, "firm": f, "micros": s,
                        "trades": int(m.sum()), "p5": x["p"], "bust5": x["b"], "exp_usd": float(ts.net[m].mean())})
    return {"base": out, "chk": chk, "warns": warns}


# ------------------------------------------------------------------ orchestration

def read_inputs(allow_partial: bool):
    led = {}
    with (R / "ledger.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["stage"] in ("screen", "ctrl") and r["run_id"]:
                led[r["key"]] = r                       # last row wins
    want = {}
    for ln in (R / "queue.jsonl").read_text().splitlines():
        if ln.strip():
            j = json.loads(ln)
            if j["stage"] in ("screen", "ctrl"):
                want[j["key"]] = j
    missing = sorted(set(want) - set(led))
    if missing and not allow_partial:
        raise SystemExit(f"screen/ctrl jobs not finished ({len(missing)} missing, e.g. {missing[:4]}); wait for hb.py or --allow-partial")
    screen, ctrls = {}, {}
    for k, r in led.items():
        m = re.fullmatch(r"screen-(.+)-tf(\d+)", k)
        if m:
            screen[(m.group(1), m.group(2))] = (k, r)
            continue
        m = re.fullmatch(r"ctrl-(random|randomtod)-tf(\d+)-s(\d+)", k)
        if m:
            ctrls[(m.group(1), m.group(2), int(m.group(3)))] = (k, r)
    return screen, ctrls, missing


def fmt_p(x):
    return "" if x is None or (isinstance(x, float) and x != x) else f"{x:.3f}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--out", default=str(R / "out"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    screen, ctrls, missing = read_inputs(a.allow_partial)
    runs = {}
    for (kind, tf, seed), (k, r) in sorted(ctrls.items()):
        runs.setdefault((kind, tf), []).append(r["run_id"])
    ctx = get_context("spawn")
    ctasks = [(fam, tf, k, r, runs) for (fam, tf), (k, r) in sorted(screen.items(), key=lambda kv: -int(kv[1][1]["trades"]))]
    btasks = [(kind, tf, seed, k, r) for (kind, tf, seed), (k, r) in sorted(ctrls.items())]
    with ctx.Pool(a.workers) as pool_:
        bres = pool_.map(base_task, btasks, chunksize=1)
        cres = pool_.map(cfg_task, ctasks, chunksize=1)
    rows = [r for c in cres for r in c["rows"]]
    checks = [c["chk"] for c in cres + bres]
    warns = [w for c in cres + bres for w in c["warns"]]
    base = [x for b in bres for x in b["base"]]
    D0 = len(cal_for())

    # ---- survivors
    for r in rows:
        for f, p in FSHORT.items():
            lift, z = r.get(f"{p}_lift"), r.get("exp_z")
            r[f"{p}_survivor"] = bool(r["trades"] >= MIN_TRADES and lift is not None and lift > 0 and z is not None and z == z and z > 0)
    rows.sort(key=lambda r: (r["fam"], r["tf"], SESSIONS.index(r["sess"])))

    # ---- table
    cols = ["fam", "tf", "sess", "run_id", "days", "trades", "trades_per_day", "trade_days", "wr", "net", "pf", "sharpe_d", "exp_usd", "t_stat", "rr",
            *[f"net_{y}" for y in YEARS], "net_long", "net_short", "net_news", "net_other", "n_news", "med_stop_pts", "stop_cover",
            "cost_ratio_nq", "cost_pass_nq", "cost_ratio_mnq", "cost_pass_mnq", "ctrl_kind", "ctrl_seeds", "ctrl_n_pool", "ctrl_q",
            "ctrl_n_draw", "ctrl_trade_days", "ctrl_exp", "ctrl_std", "exp_z"]
    for f, p in FSHORT.items():
        cols += [f"{p}_best", f"{p}_p5", f"{p}_ci_lo", f"{p}_ci_hi", f"{p}_bust5", f"{p}_med_days", f"{p}_p5_intra", f"{p}_bust5_intra",
                 *[f"{p}_p5_{s}" for s in SIZES[f]], f"{p}_ctrl_p5", f"{p}_ctrl_bust5", f"{p}_ctrl_p5_sd", f"{p}_lift",
                 f"{p}_p5_{COMMON}", f"{p}_ctrl_p5_{COMMON}", f"{p}_lift_{COMMON}", f"{p}_bust5_{COMMON}",
                 *[f"{p}_ctrl_p5_{s}" for s in SIZES[f]], f"{p}_survivor"]
    with (out / "screen_table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: (round(r[c], 6) if isinstance(r.get(c), float) else r.get(c, "")) for c in cols})
    bcols = ["kind", "tf", "seed", "sess", "firm", "micros", "trades", "p5", "bust5", "exp_usd"]
    with (out / "screen_baseline.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, bcols)
        w.writeheader()
        for x in sorted(base, key=lambda x: (x["kind"], x["tf"], x["seed"], x["sess"], x["firm"], x["micros"])):
            w.writerow({c: (round(x[c], 6) if isinstance(x[c], float) else x[c]) for c in bcols})

    # ---- summary
    L = []
    have = [r for r in rows if r["trades"] > 0]
    big = [r for r in rows if r["trades"] >= MIN_TRADES]
    surv = {f: [r for r in rows if r[f"{p}_survivor"]] for f, p in FSHORT.items()}
    both = [r for r in rows if r["lu_survivor"] and r["ap_survivor"]]
    md = max((abs(c["diff"]) for c in checks), default=0.0)
    L.append(f"# Screen analysis (Stage A1/A2), research window 2021-01-01..2024-12-31 ({D0} tape days; 2021 partial from 2021-09-22)")
    L.append(f"Runs: {len(screen)} screen + {len(ctrls)} ctrl analysed ({len(missing)} jobs missing); self-check sum(session net)==ledger net "
             f"OK on {len(checks)} runs (max |diff| ${md:.2f}). Configs (fam x tf x session): {len(rows)}, with trades {len(have)}, "
             f">={MIN_TRADES} trades {len(big)}.")
    L.append("Rules: 1 NQ stats; prop = target_stop ON, no other daily rules, breach eod (intraday in CSV); Lucid {10,20,40} / Apex {10,40,100} micros, "
             "best size = max P(pass<=5d). Apex rules UNCONFIRMED.")
    L.append(f"Survivor = >={MIN_TRADES} trades AND edge_lift>0 (vs thinned random control, same size) AND expectancy z>0. "
             f"**Survivors: Lucid {len(surv['lucid'])}, Apex {len(surv['apex'])}, both {len(both)}** (of {len(big)} configs with >={MIN_TRADES} trades).")
    fams = sorted({r["fam"] for r in rows})
    for f, p in FSHORT.items():
        s = surv[f]
        cnt = lambda key, vals: " ".join(f"{v}:{sum(1 for r in s if r[key] == v)}" for v in vals if any(r[key] == v for r in s)) or "none"
        L.append(f"- {f} survivors by family: {cnt('fam', fams)}")
        L.append(f"- {f} survivors by tf: {cnt('tf', (1, 5, 15, 30))} | by session: {cnt('sess', SESSIONS)}")
    # baseline
    L.append("## Zero-edge baseline")
    for f in FSHORT:
        best = {}
        for x in base:
            if x["firm"] == f and (x["sess"] not in best or x["p5"] > best[x["sess"]]["p5"]):
                best[x["sess"]] = x
        L.append(f"- {f}: best P(pass<=5d) of the random controls at natural frequency, any tf/seed/size: " +
                 " | ".join(f"{s} {best[s]['p5']:.3f} ({best[s]['kind']}-s{best[s]['seed']} tf{best[s]['tf']} {best[s]['micros']}mc)"
                            for s in SESSIONS if s in best))
        cp = [(r[f"{FSHORT[f]}_ctrl_p5"], r) for r in rows if r.get(f"{FSHORT[f]}_ctrl_p5") is not None]
        if cp:
            v, r = max(cp, key=lambda t: t[0])
            L.append(f"  thinned control (mean of {K_DRAWS} draws, at config sizes): max {v:.3f} ({r['fam']}/{r['tf']}/{r['sess']}), "
                     f"median {np.median([c[0] for c in cp]):.3f} over {len(cp)} configs")
    rl = {f: firm(f)[1] for f in FSHORT}
    L.append("- gambler's-ruin static bound DD/(target+DD) = " + ", ".join(
        f"{f} {rl[f]['trailing_mll']}/({rl[f]['eval_target']}+{rl[f]['trailing_mll']}) = {rl[f]['trailing_mll'] / (rl[f]['eval_target'] + rl[f]['trailing_mll']):.0%}"
        for f in FSHORT) + " (continuous-path static-floor ceiling; NOT a ceiling here: Apex random P5 already exceeds it, see above).")
    fl = lambda p: [r for r in big if r[f"{p}_survivor"]]
    L.append("- diagnostics: >=300-trade configs with lift>0: Lucid " + str(sum(1 for r in big if (r.get('lu_lift') or -1) > 0)) + ", Apex "
             + str(sum(1 for r in big if (r.get('ap_lift') or -1) > 0)) + f" of {len(big)}; survivors with PF<1: Lucid "
             + str(sum(1 for r in fl('lu') if r['pf'] < 1)) + ", Apex " + str(sum(1 for r in fl('ap') if r['pf'] < 1))
             + f"; configs with t-stat>=2 (any size): {sum(1 for r in big if r['t_stat'] >= 2)}; net>0: {sum(1 for r in big if r['net'] > 0)}."
             + " Lift is confounded by trade-day spread (config trades ~every day, thinned control clusters on fewer days): median trade-days config "
             + f"{np.median([r['trade_days'] for r in big]):.0f} vs control {np.median([r['ctrl_trade_days'] for r in big if r.get('ctrl_trade_days') is not None]):.0f}.")
    # top 25
    L.append(f"## Top 25 by edge lift at best size (configs with >={MIN_TRADES} trades; S = survivor). P5 = P(pass<=5d) eod, lift = P5 - control P5")
    tops = {}
    for f, p in FSHORT.items():
        tops[f] = sorted([r for r in big if r.get(f"{p}_lift") is not None], key=lambda r: -r[f"{p}_lift"])[:25]

    def cell(r, f):
        if r is None:
            return "| | | | | | | "
        p = FSHORT[f]
        return (f"| {r['fam']}/{r['tf']}/{r['sess']}{'*' if r[f'{p}_survivor'] else ''} | {r['trades']} | {r['net']:+.0f} | {r['pf']:.2f} | "
                f"{r[f'{p}_best']} | {r[f'{p}_p5']:.3f} | {r[f'{p}_lift']:+.3f} ")
    hd = "| # | Lucid cfg (*=S) | n | net$ | PF | mc | P5 | lift | Apex cfg (*=S) | n | net$ | PF | mc | P5 | lift |"
    L.append(hd)
    L.append("|" + "---|" * 15)
    for i in range(25):
        L.append(f"| {i + 1} " + cell(tops['lucid'][i] if i < len(tops['lucid']) else None, "lucid")
                 + cell(tops['apex'][i] if i < len(tops['apex']) else None, "apex") + "|")
    if warns:
        L.append(f"Warnings ({len(warns)}): " + "; ".join(warns[:3]) + (" ..." if len(warns) > 3 else ""))
    L.append(f"Outputs: out/screen_table.csv ({len(rows)} rows), out/screen_baseline.csv ({len(base)} rows). Elapsed {time.time() - t0:.0f}s.")
    if len(L) > 60:
        raise RuntimeError(f"summary has {len(L)} lines (> 60)")
    (out / "screen_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return rows


if __name__ == "__main__":
    main()
