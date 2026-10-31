"""VWAP hunt 2026-10-20: every VERSION's record off the stores (PREREG.md sections 2-5). Reads stored trades only; runs nothing.

    versions.py is  [names...]    in-sample side only -> is.json (+ is_table.csv); no out-of-sample number is computed
    versions.py oos [names...]    REFUSED until SELECTION.md holds the line "FROZEN"; -> oos.json
    (no names = every store of the hunt that has its walk-forward on file: vwap_* + the stores of PREREG 3b)

A version = (store, exit cell, session group). Build-side trades from runs/<name>-NQ-tf*/cells.npz (session codes on file), test-side
trades from wf/test_cells.npz (group read off the entry clock). Months by the blocks: OOS = Jan / May / Sep 2022-2026, IS = the rest
from 2021-10 to 2026-08. The win line is pipe_gates.wr_rr (row P3.15); the random line is judge.c1_cell drawn as pipe_wf.against_random,
pass by pass, on the build-side months of the read (IS: build-side IS months; OOS: see randctl.py for the test side)."""
from __future__ import annotations

import datetime as dt
import json
import sys
import zoneinfo
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EL = HERE.parents[1]
sys.path.insert(0, str(EL))

import judge as J  # noqa: E402
import library as LB  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import tables as T  # noqa: E402
from blueprint import taught as TA  # noqa: E402
from blueprint import taught_wf as TW  # noqa: E402

ROOT = Path.home() / ".homebase" / "taught"
NY = zoneinfo.ZoneInfo("America/New_York")
TICK_RT = 10.0                                  # one extra tick a side on NQ = 2 x $5
FRESH = ("2025-09", "2026-01", "2026-05", "2026-09")
TEST_FROM = "2025-07"
GROUPS = {"NY": ("nyam", "mid", "pm"), "LDN": ("london",), "PRE": ("pre",), "ON": ("asia", "eve")}
OF = {s: g for g, ss in GROUPS.items() for s in ss}
# PREREG 3b: the stores on file, by idea
OLD = {"owner_vwap_pullback_25_38": 1, "owner_vwap_pullback_50_76": 1, "owner_vwap_pullback_c15": 1, "owner_vwap_pullback_c15_fix": 1,
       "owner_vwap_pb_near10_c15": 1, "hunt_pb_jj_vwap15": 1, "hunt_dm_vwflip15_rth_midpm": 3, "hunt_pb_vwaptouch_us40": 5,
       "cl_am_disp15_vwap_10to11": 6, "hunt_fv_fvg15_vwap_p30": 6, "hunt_fv_ifvg5_vwap": 6, "hunt_fv_oside5_a1m3_vwap": 6,
       "displace_vwap_1r_k1p0": 6, "displace_vwap_1r_k1p5": 6, "displace_vwap_1r_k2p0": 6, "displace_vwap_1r_10to11_k1p0": 6,
       "displace_vwap_1r_10to11_k1p5": 6, "displace_vwap_1r_10to11_k2p0": 6, "cl_fx_disp15_vwap_10to11_long": 6,
       "cl_fx_disp15_vwap_10to11_short": 6, "ddiv_n1_vwap_with_15_15": 6, "hunt_dm_noise15_ny": 9, "conti_vwap_adx": 10,
       "conti_vwap_adx_tp10": 10, "conti_vwap_adx_tp15": 10, "conti_vwap_adx_tp20": 10}


def idea_of(name: str) -> int:
    return int(name.split("_")[1][1:]) if name.startswith("vwap_i") else OLD[name]


def month_kind(m: str) -> str:
    return "oos" if m[5:7] in ("01", "05", "09") and m >= "2022-01" else "is" if "2021-10" <= m <= "2026-08" else "out"


def _months(ordinals) -> np.ndarray:
    return np.array([dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in ordinals], dtype="<U7")


def clock_group(entry_ms: np.ndarray, passes: list) -> np.ndarray:
    """ON 18:00-03:00, LDN 03:00-08:25 (to 09:30 when the sheet has no pre pass), PRE 08:25-09:30, NY 09:30-18:00 (ET)."""
    t = np.array([(lambda x: x.hour * 60 + x.minute)(dt.datetime.fromtimestamp(int(e) / 1000, NY)) for e in entry_ms], np.int64)
    ldn_end = 505 if "pre" in passes else 570
    return np.where((t >= 1080) | (t < 180), "ON", np.where(t < ldn_end, "LDN", np.where(t < 570, "PRE", "NY")))


def store(name: str) -> dict:
    """Every cell of one store: its trades with month, group and side; the calendar; the control keys."""
    base = ROOT / name
    res = json.loads((base / "result.json").read_text())
    plan = res["plan"]
    tf, mkt = plan["bars"][0], plan["market"]
    st, _ = T._open(base / "runs", TA._unit_key(name, mkt, tf))
    claim = json.loads((base / "wf" / "claim.json").read_text())
    z = np.load(base / "wf" / "test_cells.npz")
    u = TA._unit_row(plan, tf)
    bdays = T.build_days(u, None)
    tdays = [d for d in TW._test_days(mkt, dt.date.fromisoformat(claim["utc"][:10])) if claim["days"][0] <= d <= claim["days"][1]]
    passes = list(plan["sessions"])
    cells, mis = {}, [0, 0]
    for c in claim["cells"]:
        b = J.cellx(st, c, None, None)
        bg = np.array([OF[LB.SESS7[int(s)]] for s in b["sess"]], dtype="<U3")
        chk = clock_group(b["entry_ms"], passes) if len(b["entry_ms"]) else np.zeros(0, "<U3")
        mis[0] += int((chk != bg).sum())
        mis[1] += len(bg)
        n_t = len(z[f"{c}|date"])
        side_t = np.full(n_t, {"long": 1, "short": -1}.get(plan["dir"], 0), np.int8)   # test side unknown for a both-sides sheet
        cells[c] = {"date": np.r_[b["date"].astype(np.int64), z[f"{c}|date"].astype(np.int64)],
                    "entry_ms": np.r_[b["entry_ms"].astype(np.int64), z[f"{c}|entry_ms"].astype(np.int64)],
                    "dur_s": np.r_[b["dur_s"].astype(np.int64), z[f"{c}|dur_s"].astype(np.int64)],
                    "net": np.r_[b["net"].astype(np.float64), z[f"{c}|net"].astype(np.float64)],
                    "sess": np.r_[np.array([LB.SESS7[int(s)] for s in b["sess"]], dtype="<U6"),
                                  np.array(["?"] * n_t, dtype="<U6")],
                    "group": np.r_[bg, clock_group(z[f"{c}|entry_ms"], passes) if n_t else np.zeros(0, "<U3")],
                    "side": np.r_[b["side"].astype(np.int8), side_t], "test": np.r_[np.zeros(len(bg), bool), np.ones(n_t, bool)]}
        cells[c]["month"] = _months(cells[c]["date"])
    groups = sorted({OF[s] for s in passes})
    return {"name": name, "plan": plan, "tf": tf, "market": mkt, "cells": cells, "groups": groups, "passes": passes, "base": base,
            "bdays": bdays, "tdays": tdays, "claim": claim, "mislabel": mis, "u": u}


def sessions_in(S: dict, kind: str) -> int:
    return sum(1 for d in S["bdays"] + S["tdays"] if month_kind(d[:7]) == kind)


def metrics(net: np.ndarray, days: int) -> dict:
    n = len(net)
    wr = G.wr_rr(net)
    win = net > 0
    return {"trades": n, "per_day": round(n / days, 3) if days else None, "net": round(float(net.sum()), 1),
            "avg": round(float(net.mean()), 2) if n else None, "win": round(float(win.mean()), 4) if n else None,
            "rr": wr.get("rr"), "breakeven": wr.get("breakeven"), "need": wr.get("need"), "p1": bool(wr["passed"]) if n else False,
            "net_tick": round(float(net.sum()) - TICK_RT * n, 1)}


def _pools(S: dict, xid: str, side: str) -> dict:
    """{pass: judge.pool_arrays} of the store's build-side random entries for one exit cell (side 'both' or the sheet's own)."""
    key = TA._ctl_key(S["name"], S["market"], S["tf"], side)
    ctl = json.loads((S["base"] / "runs" / key / "run.json").read_text())
    seeds = sorted({c["inputs"]["seed"] for c in ctl["cells"]})
    bpool = T.pool_seeds(S["base"] / "runs", key, [xid], len(seeds))
    return {p: J.pool_arrays(bpool, p, xid) for p in S["passes"]}


def random_line(S: dict, c: str, g: str, m: np.ndarray, side: str, salt: str, pools_cache: dict) -> dict:
    """The version's build-side trades `m` (a mask of its trades) against the lane's random entries, pass by pass, day-matched (c1)."""
    x = S["cells"][c]
    xid = c.rsplit("_", 1)[-1]
    if (xid, side) not in pools_cache:
        pools_cache[(xid, side)] = _pools(S, xid, side)
    pools = pools_cache[(xid, side)]
    seeds = J.block_seeds(J.seed_of(f"vwaphunt|{S['name']}|{c}|{g}|{side}", salt))
    total, short = np.zeros(J.BLOCK * len(seeds)), 0
    for p in GROUPS[g]:
        if p not in pools:
            continue
        sel = m & (x["sess"] == p)
        d, _, s = J.c1_cell(x["date"][sel], pools[p], seeds)
        total, short = total + d, short + s
    d = total[:J.RULE["draws"]]
    ctl = {"draws": d, "mean": float(d.mean()), "sd": float(d.std(ddof=1)), "p95": float(np.percentile(d, 95)), "replicates": len(d),
           "real_replicates": 10, "short": int(short)}
    v = J.verdict(float(x["net"][m].sum()), ctl, True)
    return {"p_beat": v["p_beat"], "pass": bool(v["pass"]), "short": int(short), "lift": v["lift"]}


def read(S: dict, kind: str) -> list:
    rows, days = [], sessions_in(S, kind)
    one_side = S["plan"]["dir"] in ("long", "short")
    pc: dict = {}
    for c, x in S["cells"].items():
        mk = np.array([month_kind(mo) == kind for mo in x["month"]], bool)
        for g in S["groups"]:
            m = mk & (x["group"] == g)
            if not m.any():
                rows.append({"store": S["name"], "idea": idea_of(S["name"]), "cell": c, "group": g, "kind": kind, "trades": 0})
                continue
            r = {"store": S["name"], "idea": idea_of(S["name"]), "bars": S["tf"], "family": S["plan"]["family"], "dir": S["plan"]["dir"],
                 "cell": c, "group": g, "kind": kind, **metrics(x["net"][m], days)}
            late = m & (x["month"] >= TEST_FROM)
            r["late_net"], r["late_trades"] = round(float(x["net"][late].sum()), 1), int(late.sum())
            if kind == "oos":
                fr = m & np.isin(x["month"], FRESH)
                r["fresh_net"], r["fresh_trades"] = round(float(x["net"][fr].sum()), 1), int(fr.sum())
                r["months"] = {mo: round(float(x["net"][m & (x["month"] == mo)].sum())) for mo in sorted(set(x["month"][m]))}
            if kind == "is":                      # C3 on the build-side IS months (stored pools)
                bm = m & ~x["test"]
                r["rand"] = random_line(S, c, g, bm, "both", "is", pc)
                if one_side:
                    r["rand_side"] = random_line(S, c, g, bm, S["plan"]["dir"], "is", pc)
            rows.append(r)
    return rows


def names_on_file() -> list:
    new = [p.stem for p in sorted((EL / "taught").glob("vwap_i*.json"))]
    return [n for n in new + list(OLD) if (ROOT / n / "wf" / "test_cells.npz").exists() and (ROOT / n / "wf" / "result.json").exists()]


def main(argv: list) -> None:
    kind, names = argv[0], argv[1:] or names_on_file()
    if kind == "oos" and "FROZEN" not in ((HERE / "SELECTION.md").read_text() if (HERE / "SELECTION.md").exists() else ""):
        raise SystemExit("oos: refused -- SELECTION.md is not frozen yet (PREREG.md section 4)")
    out = HERE / f"{kind}.json"
    have = {(r["store"], r["cell"], r["group"]): r for r in json.loads(out.read_text())} if out.exists() else {}
    mis = {}
    for n in names:
        S = store(n)
        mis[n] = S["mislabel"]
        for r in read(S, kind):
            have[(r["store"], r["cell"], r["group"])] = r
        print(f"{n}: {len(S['cells'])} cells x {S['groups']}; build-side clock vs session code mislabels {S['mislabel'][0]} of {S['mislabel'][1]}",
              flush=True)
    out.write_text(json.dumps(sorted(have.values(), key=lambda r: (r["idea"], r["store"], r["cell"], r["group"])), indent=1))
    (HERE / f"mislabel_{kind}.json").write_text(json.dumps(mis, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
