#!/usr/bin/env python3
"""RUN AGENT driver of the BUILD menus (EDGE_SPEC; plan pre-declared in progress.md 2026-10-02 14:58 ET, before any run).

Each unit is ONE subprocess of run_menus.py (its own memory; its store + ledger row are written by run_menus), in the fixed
order. Idempotent: run_menus skips a key that has its store and its ledger row. Nothing here reads PICK or EXAM; nothing
here looks at a P&L: the only numbers used are library.plateau's pass flags (the stage D seal, in staged.py).

    python driver.py base NQ          C1 pools -> straddle_t -> ported -> vwap_ema_x -> L2 ideas
    python driver.py base ES | GC     the same order without the L2 ideas, low-prior families last, minus cuts.json
    python driver.py all              base NQ -> staged.py grids -> staged.py nulls -> staged.py cuts -> base ES -> base GC
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
PY = sys.executable
LOG = HERE / "driver.jsonl"
CUTS = HERE / "cuts.json"
TFS = ("1", "5", "15", "30")
STRADDLE_T = [f"straddle_t_{t}" for t in ("1800", "2000", "0000", "0200", "0300", "0830", "0930", "1105", "1330")]
PORTED = ["orb", "straddle", "donchian", "squeeze", "ib", "lon_break", "gap",
          "ema_ribbon", "tema_slope", "ema_pullback", "supertrend", "rsi2", "first_bar_mom", "tod_drift", "mid_fade",
          "vwap_band", "vwap_z", "vwap_flip", "pinbar", "sweep_rev"]
LOW_PRIOR = ["mid_fade", "rsi2", "tema_slope", "ema_ribbon", "supertrend", "pinbar", "gap"]      # the cut order (GC, then ES)
L2_IDEAS = [("bimb_follow_d1", ("5",)), ("flow_exhaust", ("1", "5"))]
WORKERS = 8


def log(**row) -> None:
    row = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **row}
    print(json.dumps(row), flush=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def call(args: list, tag: str) -> int:
    t0 = time.monotonic()
    p = subprocess.run([PY, *args], cwd=str(W), capture_output=True, text=True)
    out = p.stdout.strip().splitlines()
    log(tag=tag, rc=p.returncode, wall_s=round(time.monotonic() - t0, 1), out=out[-1][:600] if out else "",
        err=p.stderr.strip()[-1500:] if p.returncode else p.stderr.strip()[-300:])
    return p.returncode


def cuts() -> set:
    if not CUTS.exists():
        return set()
    return {(c["family"], c["root"]) for c in json.loads(CUTS.read_text())["cut"]}


def plan(root: str) -> list:
    """[(kind, family, tf)] in the fixed order for a root."""
    out = [("c1", "", tf) for tf in TFS]
    out += [("unit", f, "30") for f in STRADDLE_T]
    cut = cuts()
    if root == "NQ":
        ported = list(PORTED)
    else:                                            # low-prior families LAST (reverse cut order), minus the cut ones
        ported = [f for f in PORTED if f not in LOW_PRIOR]
    out += [("unit", f, tf) for f in ported for tf in TFS]
    out += [("unit", "vwap_ema_x", tf) for tf in ("1", "5", "15")]
    if root == "NQ":
        out += [("unit", f, tf) for f, tfs in L2_IDEAS for tf in tfs]
    else:
        out += [("unit", f, tf) for f in reversed(LOW_PRIOR) if (f, root) not in cut for tf in TFS]
    return out


def base(root: str) -> int:
    bad = 0
    for kind, fam, tf in plan(root):
        if kind == "c1":
            rc = call(["run_menus.py", "nulls", "--roots", root, "--tf", tf, "--workers", str(WORKERS)], f"c1-{root}-tf{tf}")
        else:
            rc = call(["run_menus.py", "run", "--family", fam, "--roots", root, "--tf", tf, "--workers", str(WORKERS)],
                      f"{fam}-{root}-tf{tf}")
        if rc == 2:                                  # REFUSED: a cap, a broken registry or missing tapes -> stop, report
            log(tag="STOP", why=f"run_menus refused {fam}-{root}-tf{tf} (rc 2)")
            return 2
        bad += rc != 0
    log(tag=f"base-{root}-done", failed_units=bad)
    return 0 if not bad else 1


def main() -> int:
    cmd = sys.argv[1]
    if cmd == "base":
        return base(sys.argv[2].upper())
    if cmd == "all":
        if base("NQ") == 2:
            return 2
        for step in ("grids", "nulls", "cuts"):
            rc = call([str(HERE / "staged.py"), step], f"staged-{step}")
            if rc not in (0, 3):                     # 3 = the stage D budget is exhausted (listed in staged.json)
                log(tag="STOP", why=f"staged.py {step} rc {rc}")
                return 2
        for root in ("ES", "GC"):
            if base(root) == 2:
                return 2
        log(tag="ALL-DONE")
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
