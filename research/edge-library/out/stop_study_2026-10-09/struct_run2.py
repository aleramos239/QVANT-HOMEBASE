"""Stop study, part 2: the LATER build days (2024-01-01..2025-06-30, inside the blueprint's build range; nothing from 2025-07-01 on),
range-type rules only, NQ 5-minute bars: structure stop + the 8 fixed stops x 4 targets, same entries. Nothing written to runs/ or a ledger."""
import sys, time, json, datetime as dt
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import run_menus as RM, library as L, l2sim
TGT = (0.0, 1.0, 2.0, 3.0)

def main():
    OUT = sys.argv[1]
    fam = RM.registry()
    for root, family, tf in (("NQ", "donchian", "5"), ("NQ", "orb", "5"), ("NQ", "supertrend", "5")):
        cls = fam.REGISTRY[family][0]
        key = f"{family}-{root}-tf{tf}"
        days = [d.isoformat() for d in l2sim.sessions(dt.date(2024, 1, 1), dt.date(2025, 6, 30), root, allow_holdout=l2sim.ALLOW_BP)]
        grid = [c for c in fam.unit_grid(family, root, tf) if not c.get("info") and c["exit"]["tgt_r"] in TGT]
        first = {}
        for c in grid:
            first.setdefault(c["vi"], c)
        new = list(grid)
        for vi, c in sorted(first.items()):
            for r in TGT:
                x = {"stop_mode": "struct", "stop_val": 1.5, "tgt_r": r}
                new.append({"id": f"v{vi}_struct-r{r:g}", "variant": c["variant"], "exit": x, "vi": vi, "xi": 100, "spec": (cls, {**c["spec"][1], **x})})
        specs, cut = [], [0]
        for c in new:
            specs += RM.cell_specs(c)
            cut.append(len(specs))
        l2sim.wait_compute_window()
        t0 = time.monotonic()
        res = l2sim.run_many(specs, period=l2sim.ALLOW_BP, days=days, root=root, workers=RM.auto_workers(8), features=fam.features_for(family),
                             **dict(getattr(cls, "SCREEN_RUN", {})))
        res = [RM.merge(res[a:b]) for a, b in zip(cut, cut[1:])]
        arrs, meta = {}, []
        for c, r in zip(new, res):
            p = L.pack(r["trades"])
            for k in L.FIELDS:
                arrs[f"{c['id']}|{k}"] = p[k]
            meta.append({"id": c["id"], "vi": c["vi"], "variant": c["variant"], "exit": c["exit"], "trades": len(r["trades"]), "errors": r["skipped_by_error"]})
        np.savez_compressed(f"{OUT}/{key}.npz", **arrs)
        json.dump({"days": [days[0], days[-1], len(days)], "cells": meta}, open(f"{OUT}/{key}.json", "w"))
        print(key, len(new), "cells", len(days), "days", round(time.monotonic() - t0), "s", flush=True)
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
