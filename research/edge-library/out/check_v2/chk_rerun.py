"""CHECKER v2: every member's DEFAULT variant re-run from scratch with the engine (l2sim + the family code; no analyst judging
code), on BUILD and on 2024, normal costs and stress (2 ticks + 250 ms, + 100 ms late cancel for two-sided brackets).
Compared trade for trade with members/<name>/trades_{build,pick}.json and with the stores. Restartable: one json per
(store key, period, mode) under out/check_v2/rerun/. EXAM is never named. 2024 cells run here were already read by the analyst.
  nohup python chk_rerun.py > chk_rerun.log 2>&1 &"""
import csv, datetime as dt, json, sys
from pathlib import Path
import numpy as np
W = Path("/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, str(W)); sys.path.insert(0, str(W / "engine")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import families as F
import l2sim as S
import run_menus as RM
OUT = W / "out" / "check_v2" / "rerun"
OUT.mkdir(exist_ok=True)


def members():
    out = []
    for p in sorted((W / "members").glob("*/spec.json")):
        if p.parent.name.startswith("_"):
            continue
        out.append(json.loads(p.read_text()))
    return out


def main():
    ms = members()
    groups = {}
    for m in ms:
        groups.setdefault((m["family"], m["root"], str(m["tf"]), m["sess"]), set()).add(m["cell"])
    for (fam, root, tf, sess), cells in sorted(groups.items()):
        grid = F.unit_grid(fam, root, tf)
        cls = F.REGISTRY[fam][0]
        feats = F.features_for(fam)
        timed = RM.is_time_fired(cls)
        two_sided = any(m.get("two_sided") for m in ms)  # placeholder, replaced below from the BUILD store
        st_meta = json.loads((W / "runs" / f"{fam}-{root}-tf{tf}" / "run.json").read_text())
        oco = bool(st_meta.get("both_sides_declared"))
        pick = [c for c in grid if c["id"] in cells]
        assert len(pick) == len(cells), (fam, root, tf, cells)
        specs = []
        for c in pick:
            k, p = c["spec"]
            specs.append((k, {**p, "hold_to": "day"} if timed else {**p, "sess": sess, "hold_to": "day"}))
        for period in ("build", "pick"):
            for mode in ("normal", "stress", "stress_no_oco"):
                if mode == "stress_no_oco" and not (oco and period == "pick"):
                    continue
                f = OUT / f"{fam}-{root}-tf{tf}-{sess}-{period}-{mode}.json"
                if f.exists():
                    continue
                kw = {}
                if mode != "normal":
                    kw.update(S.STRESS)
                    if mode == "stress" and oco:
                        kw["costs"] = S.Costs(oco_cancel_ms=100)
                kw.update(getattr(cls, "SCREEN_RUN", {}))
                S.wait_compute_window()
                res = S.run_many(specs, period=period, root=root, workers=RM.auto_workers(8), features=feats, **kw)
                out = {}
                for c, r in zip(pick, res):
                    tr = r["trades"] if timed else [t for t in r["trades"] if S.session_of(t["entry_ms"]) == sess]
                    assert not r["skipped_by_error"]
                    assert all(t["date"] < "2025-01-01" for t in tr)
                    out[c["id"]] = [{k: t.get(k) for k in ("date", "side", "entry_price", "exit_price", "exit_reason", "net", "entry_ms", "exit_ms", "seconds", "oco", "both_sides")} for t in tr]
                f.write_text(json.dumps({"family": fam, "root": root, "tf": tf, "sess": sess, "period": period, "mode": mode, "oco_declared": oco, "timed": timed,
                                         "kw": {k: (v if not isinstance(v, S.Costs) else {"oco_cancel_ms": v.oco_cancel_ms}) for k, v in kw.items()}, "trades": out}))
                print("done", f.name, {k: len(v) for k, v in out.items()}, "elapsed", round(res[0]["elapsed_s"]), flush=True)
                if period == "pick":
                    with (W / "out" / "check_v2" / "checker_pick_reads.csv").open("a", newline="") as fh:
                        csv.writer(fh).writerow([dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "engine re-run", f"{fam}-{root}-tf{tf}-{sess}-pick" + ("" if mode == "normal" else "-stress"),
                                                 f"chk_rerun.py: default cell(s) {sorted(out)} re-run from scratch, {mode} (cells already read by the analyst)"])


if __name__ == "__main__":
    main()
