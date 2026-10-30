"""VWAP hunt 2026-10-20: the RANDOM-ENTRY CONTROL of a version's out-of-sample read (PREREG.md section 5, line P3).

The lane keeps random entries for the build days only (runs/<name>__ctl*-NQ-tf*/), and `taught wf` runs them on the test days without
keeping them. This runs THE SAME random entries -- l2ref.Random with the store's own control cells (seeds, exit cells, p_entry), one
instance a session pass, the engine's default costs, exactly taught_wf.run's `rspecs` -- on the test-side OUT-OF-SAMPLE months only
(2025-09, 2026-01, 2026-05, 2026-09 to the read's last day), and keeps them in <store>/wf/rand_oos[_side].npz. No strategy trade is run
or read here: random entries read only the market.

    randctl.py run <name> [--workers=3]     the random entries (both sides, and the sheet's side for a one-side sheet)
    randctl.py line <name> <cell> <group>   P3 for one version: c1 draws over EVERY OOS month (build side from the stored pools,
                                            test side from rand_oos), pass by pass, day-matched; one-side: also its side (P4.2s)"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import taught as TA  # noqa: E402

import versions as V  # noqa: E402

TEST_OOS = ("2025-09", "2026-01", "2026-05", "2026-09")


def _file(base: Path, side: str) -> Path:
    return base / "wf" / f"rand_oos{'' if side == 'both' else '_' + side}.npz"


def run(name: str, workers: int = 3) -> None:
    import l2ref
    base = V.ROOT / name
    plan = json.loads((base / "result.json").read_text())["plan"]
    claim = json.loads((base / "wf" / "claim.json").read_text())
    tf, mkt = plan["bars"][0], plan["market"]
    days = [d for d in V.TW._test_days(mkt, dt.date.fromisoformat(claim["utc"][:10])) if claim["days"][0] <= d <= claim["days"][1] and d[:7] in TEST_OOS]
    RUN.may_start()
    for side in ["both"] + ([plan["dir"]] if plan["dir"] != "both" else []):
        if _file(base, side).exists():
            continue
        cmeta = json.loads((base / "runs" / TA._ctl_key(name, mkt, tf, side) / "run.json").read_text())
        rspecs = [(c["id"], {**c["inputs"], "sess": s}) for c in cmeta["cells"] for s in plan["sessions"]]
        res = S.run_many([(l2ref.Random, i) for _, i in rspecs], S._date(days[0]), S._date(days[-1]), days=days, root=mkt,
                         workers=max(1, min(workers, S.MAX_WORKERS)), allow_holdout=S.ALLOW_BT, **RUN._engine({}))
        out = {}
        for (cid, i), r in zip(rspecs, res):
            x = LB.pack(sorted(r["trades"], key=lambda q: q["entry_ms"]))
            for k in ("date", "entry_ms", "net"):
                out[f"{cid}|{i['sess']}|{k}"] = np.asarray(x[k])
        np.savez(_file(base, side), **out)
        print(f"{name} {side}: {len(rspecs)} random instances on {len(days)} test-side OOS days -> {_file(base, side).name}", flush=True)


def _test_pool(z, seeds: list, xid: str, sess: str):
    """taught_wf._pool's shape for one exit cell in one pass, from rand_oos."""
    D, N, C = [], [], []
    for sd in seeds:
        d = z[f"s{sd}_{xid}|{sess}|date"].astype(np.int64)
        e = z[f"s{sd}_{xid}|{sess}|entry_ms"]
        n = z[f"s{sd}_{xid}|{sess}|net"].astype(np.float64)
        o = np.lexsort((e, d))
        d, n = d[o], n[o]
        first = np.r_[True, d[1:] != d[:-1]] if len(d) else np.zeros(0, bool)
        rank = np.arange(len(d)) - np.maximum.accumulate(np.where(first, np.arange(len(d)), 0)) if len(d) else np.zeros(0, np.int64)
        D.append(d)
        N.append(n)
        C.append(d * 4096 + rank + (sd << 40))
    d, n, c = (np.concatenate(v) if v else np.zeros(0) for v in (D, N, C))
    o = np.argsort(d, kind="stable")
    return d[o].astype(np.int64), n[o], c[o].astype(J.U64), np.r_[0.0, np.cumsum(n[o])]


def line(Sx: dict, c: str, g: str, side: str = "both") -> dict:
    """P3 of one version on every OOS month: build side vs the stored pools, test side vs rand_oos, pass by pass."""
    x = Sx["cells"][c]
    xid = c.rsplit("_", 1)[-1]
    oos = np.array([V.month_kind(m) == "oos" for m in x["month"]], bool) & (x["group"] == g)
    bpools = V._pools(Sx, xid, side)
    z = np.load(_file(Sx["base"], side))
    seeds_all = sorted({int(k.split("_", 1)[0][1:]) for k in z.files})
    seeds = J.block_seeds(J.seed_of(f"vwaphunt|{Sx['name']}|{c}|{g}|{side}", "oos"))
    total, short = np.zeros(J.BLOCK * len(seeds)), 0
    for p in V.GROUPS[g]:
        if p not in Sx["passes"]:
            continue
        sel_b = oos & ~x["test"] & (x["sess"] == p)
        d, _, s = J.c1_cell(x["date"][sel_b], bpools[p], seeds)
        total, short = total + d, short + s
        # test side: the pass is read off the entry clock (the group's passes are disjoint clock windows; NY's three are split here)
        sel_t = oos & x["test"]
        if p in ("nyam", "mid", "pm", "asia", "eve"):
            t = np.array([(lambda q: q.hour * 60 + q.minute)(dt.datetime.fromtimestamp(int(e) / 1000, V.NY)) for e in x["entry_ms"][sel_t]], np.int64)
            win = {"nyam": (570, 660), "mid": (660, 810), "pm": (810, 1080), "asia": (0, 180), "eve": (1080, 1440)}[p]
            keep = (t >= win[0]) & (t < win[1])
            idx = np.flatnonzero(sel_t)[keep]
        else:
            idx = np.flatnonzero(sel_t)
        d, _, s = J.c1_cell(x["date"][idx], _test_pool(z, seeds_all, xid, p), seeds)
        total, short = total + d, short + s
    dd = total[:J.RULE["draws"]]
    ctl = {"draws": dd, "mean": float(dd.mean()), "sd": float(dd.std(ddof=1)), "p95": float(np.percentile(dd, 95)), "replicates": len(dd),
           "real_replicates": len(seeds_all), "short": int(short)}
    v = J.verdict(float(x["net"][oos].sum()), ctl, True)
    return {"p_beat": v["p_beat"], "pass": bool(v["pass"]), "short": int(short), "lift": v["lift"], "side": side}


def main(argv: list) -> None:
    w = next((int(a.split("=")[1]) for a in argv if a.startswith("--workers=")), 3)
    argv = [a for a in argv if not a.startswith("--")]
    if argv[0] == "run":
        run(argv[1], w)
    elif argv[0] == "lines":                      # every candidate of grade.py (rand_cands.json) -> p3.json
        if "FROZEN" not in (HERE / "SELECTION.md").read_text():
            raise SystemExit("lines: refused -- SELECTION.md is not frozen yet")
        f = HERE / "p3.json"
        out = json.loads(f.read_text()) if f.exists() else {}
        cache: dict = {}
        for name, c, g in json.loads((HERE / "rand_cands.json").read_text()):
            Sx = cache.setdefault(name, V.store(name))
            r = {"both": line(Sx, c, g, "both")}
            if Sx["plan"]["dir"] != "both":
                r["side"] = line(Sx, c, g, Sx["plan"]["dir"])
            r["pass"] = all(v["pass"] for v in r.values() if isinstance(v, dict))
            out[f"{name}|{c}|{g}"] = r
            print(name, c, g, json.dumps(r), flush=True)
        f.write_text(json.dumps(out, indent=1))
    else:
        if "FROZEN" not in (HERE / "SELECTION.md").read_text():
            raise SystemExit("line: refused -- SELECTION.md is not frozen yet")
        Sx = V.store(argv[1])
        print(json.dumps(line(Sx, argv[2], argv[3])))


if __name__ == "__main__":
    main(sys.argv[1:])
