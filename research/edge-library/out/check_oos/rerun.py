"""CHECKER OOS: every saved strategy's DEFAULT variant re-run from scratch with the engine (l2sim + the family code; no analyst
judging / runner code), on 2025 (allow_check=True) and -- ONLY for the 5 units on out/exam2026/allowed.json -- on 2026
(2026-01-01..allowed end date, allow_exam=True). Normal costs and stress (2 ticks + 250 ms, + 100 ms late cancel for a
two-sided bracket). Compared trade for trade with the analyst's stores. Restartable: one json per (store key, period, mode)
in out/check_oos/rerun/. Every pass is logged in checker_reads.csv BEFORE it runs; all cells were already read by the analyst.
  nohup python rerun.py > logs/rerun.log 2>&1 &"""
import csv, datetime as dt, glob, json, sys
from pathlib import Path
import numpy as np
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(W)); sys.path.insert(0, str(W / "engine"))
import families as F
import l2sim as S
OUT = HERE / "rerun"; OUT.mkdir(exist_ok=True)
READS = HERE / "checker_reads.csv"
ALLOWED = json.loads((W / "out/exam2026/allowed.json").read_text())
EXAM_UNITS = set(ALLOWED["units"])
EXAM_END = ALLOWED["period"]["end"]
WORKERS = 8


def log(period, key, cells, mode, why):
    new = not READS.exists()
    with READS.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["utc", "what", "store_compared", "period", "cells", "mode", "why"])
        w.writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "engine re-run", key, period, " ".join(sorted(cells)), mode, why])


def main():
    groups = {}
    for f in sorted(glob.glob(str(HERE / "res" / "*.json"))):
        r = json.load(open(f))
        fam, root, tf, sess = r["unit"].split("@")[0].rsplit("-", 3)[0], *r["unit"].split("@")[0].rsplit("-", 3)[1:]
        tf = tf[2:]
        g = groups.setdefault((fam, root, tf, sess), {"cells": set(), "exam_cells": set()})
        g["cells"].add(r["default"])
        if r["unit"] in EXAM_UNITS:
            g["exam_cells"].add(r["default"])
    for (fam, root, tf, sess), g in sorted(groups.items()):
        grid = F.unit_grid(fam, root, tf)
        cls = F.REGISTRY[fam][0]
        assert F.features_for(fam) is None
        timed = "shift_seed" in cls.defaults()
        oco = bool(json.loads((W / "runs" / f"{fam}-{root}-tf{tf}" / "run.json").read_text()).get("both_sides_declared"))
        for period in ("check", "exam"):
            cells = g["cells"] if period == "check" else g["exam_cells"]
            if not cells:
                continue
            pick = [c for c in grid if c["id"] in cells]
            assert len(pick) == len(cells), (fam, root, tf, cells)
            specs = []
            for c in pick:
                k, p = c["spec"]
                specs.append((k, {**p, "hold_to": "day"} if timed else {**p, "sess": sess, "hold_to": "day"}))
            for mode in ("normal", "stress"):
                key = f"{fam}-{root}-tf{tf}-{sess}-{period}" + ("-stress" if mode == "stress" else "")
                f = OUT / f"{key}.json"
                if f.exists():
                    print("skip", f.name, flush=True)
                    continue
                kw = {}
                if mode == "stress":
                    kw.update(S.STRESS)
                    if oco:
                        kw["costs"] = S.Costs(oco_cancel_ms=100)
                kw.update(getattr(cls, "SCREEN_RUN", {}))
                S.wait_compute_window()
                if period == "check":
                    log("check 2025", f"runs_check2025/{key}", cells, mode, "default variant(s) re-run from scratch; cells already read by the analyst")
                    res = S.run_many(specs, period="check", root=root, workers=WORKERS, allow_check=True, **kw)
                    lo, hi = "2025-01-01", "2025-12-31"
                else:
                    assert all(u.split("@")[0] != f"{fam}-{root}-tf{tf}-{sess}" or u in EXAM_UNITS for u in EXAM_UNITS)
                    end = dt.date.fromisoformat(EXAM_END[root])
                    log(f"exam 2026-01-01..{end}", f"runs_exam2026/{key}", cells, mode, "default variant(s) of an ALLOWED unit re-run from scratch, allow_exam=True; cells already read by the analyst")
                    res = S.run_many(specs, dt.date(2026, 1, 1), end, root=root, workers=WORKERS, allow_exam=True, **kw)
                    lo, hi = "2026-01-01", end.isoformat()
                out = {}
                for c, r in zip(pick, res):
                    tr = r["trades"] if timed else [t for t in r["trades"] if S.session_of(t["entry_ms"]) == sess]
                    assert not r["skipped_by_error"], (key, c["id"])
                    assert all(lo <= t["date"] <= hi for t in tr), key
                    out[c["id"]] = [{k: t.get(k) for k in ("date", "side", "entry_price", "exit_price", "exit_reason", "net", "entry_ms", "exit_ms", "sl", "oco", "both_sides")} for t in tr]
                f.write_text(json.dumps({"family": fam, "root": root, "tf": tf, "sess": sess, "period": period, "mode": mode, "oco_declared": oco, "timed": timed,
                                         "sessions": res[0]["sessions"], "used": res[0]["used"], "skipped": res[0]["skipped"],
                                         "trades": out}, default=str))
                print("done", f.name, {k: len(v) for k, v in out.items()}, "sessions", res[0]["sessions"], "used", res[0]["used"], "elapsed", round(res[0]["elapsed_s"]), flush=True)


if __name__ == "__main__":
    main()
