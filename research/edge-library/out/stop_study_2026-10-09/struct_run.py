"""Stop study, old-library BUILD days (2021-09-22..2023-12-31), nothing written to runs/ or the ledger: the library's own
families with the engine's own input stop_mode='struct' (no new rule, no new exit code), next to the stored fixed-stop cells.
One fixed cell per variant is run again as a check that the fresh run repeats the store."""
import sys, time, json
import numpy as np
W = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library"
sys.path[:0] = [W, W + "/engine"]
import run_menus as RM, library as L, l2sim
def main():
    OUT = sys.argv[1]
    FAMS = ("pinbar", "sweep_rev", "ema_pullback", "vol_spike_break", "supertrend", "donchian", "orb")
    TGT = (0.0, 1.0, 2.0, 3.0)
    fam = RM.registry()
    for root in ("NQ", "ES", "GC"):
        for family in FAMS:
            cls = fam.REGISTRY[family][0]
            for tf in ("5", "1"):
                key = f"{family}-{root}-tf{tf}"
                dst = f"{OUT}/{key}.npz"
                try:
                    open(dst).close(); print("have", key, flush=True); continue
                except OSError:
                    pass
                grid = fam.unit_grid(family, root, tf)
                first = {}
                for c in grid:
                    first.setdefault(c["vi"], c)
                new = []
                for vi, c in sorted(first.items()):
                    _, params = c["spec"]
                    new.append({"id": f"v{vi}_chk", "variant": c["variant"], "exit": c["exit"], "vi": vi, "xi": -1, "spec": (cls, dict(params)), "old": c["id"]})
                    for r in TGT:
                        x = {"stop_mode": "struct", "stop_val": 1.5, "tgt_r": r}
                        new.append({"id": f"v{vi}_struct-r{r:g}", "variant": c["variant"], "exit": x, "vi": vi, "xi": 100, "spec": (cls, {**params, **x})})
                l2sim.wait_compute_window()
                t0 = time.monotonic()
                res = RM.run_grid(new, root, features=fam.features_for(family), workers=RM.auto_workers(8), kw=dict(getattr(cls, "SCREEN_RUN", {})))
                arrs, meta = {}, []
                for c, r in zip(new, res):
                    p = L.pack(r["trades"])
                    for k in L.FIELDS:
                        arrs[f"{c['id']}|{k}"] = p[k]
                    meta.append({"id": c["id"], "vi": c["vi"], "variant": c["variant"], "exit": c["exit"], "old": c.get("old"), "trades": len(r["trades"]),
                                 "net": float(sum(t["net"] for t in r["trades"])), "errors": r["skipped_by_error"]})
                np.savez_compressed(dst, **arrs)
                json.dump(meta, open(f"{OUT}/{key}.json", "w"))
                print(key, len(new), "cells", round(time.monotonic() - t0), "s", [(m["id"], m["trades"]) for m in meta[:3]], flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
