"""ADMISSION v2, step 2a: the 2024 jobs of every unit that passed (1)-(3) on BUILD: whole menu + every control used on BUILD,
unless the store is already on disk (earlier stages: runs_admit / runs_admit_r1 / runs_deepen / runs_events).
  python out/v2/plan_pick.py -> out/v2/jobs_pick.json (+ a print-out of what is reused)"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v2 as V  # noqa: E402


def passers() -> list:
    ok = {r["uid"] for r in csv.DictReader((V.OUT / "build_units.csv").open()) if r["build_pass"] == "True"}
    return [u for u in V.units() if u["uid"] in ok]


def menu_ids(u: dict) -> list:
    st = V.store(u["key"], period="build")
    return [r["id"] for r in V.base_rows(st, u) if not r.get("info") and not r.get("dead")]


def main():
    P = passers()
    jobs, reuse, menus = [], [], {}
    for u in P:
        menus.setdefault((u["key"], u["sess"]), {"u": u, "ids": set(), "uids": []})
        menus[(u["key"], u["sess"])]["ids"] |= set(menu_ids(u))
        menus[(u["key"], u["sess"])]["uids"].append(u["uid"])
    seen = set()

    def want(key, job):
        if key in seen:
            return
        seen.add(key)
        d = V.find_pick(key)
        if d is not None:
            reuse.append((key, d.name))
        else:
            jobs.append(job)

    for (key, sess), m in sorted(menus.items()):
        u = m["u"]
        base = {"family": u["family"], "root": u["root"], "tf": u["tf"], "sess": sess, "period": "pick"}
        ids = sorted(m["ids"])
        want(f"{key}-{sess}-pick", {**base, "cells": ids, "why": f"v2 BUILD passer(s) {', '.join(m['uids'])}: whole menu on 2024"})
        for c in u["controls"]:
            if c == "c1":
                want(f"c1-{u['root']}-tf{u['tf']}-{sess}-pick", {"c1": True, "root": u["root"], "tf": u["tf"], "sess": sess, "period": "pick",
                                                              "why": f"C1 control of {m['uids'][0]}"})
            elif c == "shift":
                fam = u["base"] or u["family"]
                want(f"{fam}-{u['root']}-tf{u['tf']}-{sess}-pick-shift", {**base, "family": fam, "shift": True, "cells": ids,
                                                                        "why": f"random-minute control of {m['uids'][0]}"})
            elif c == "c2":
                for sd in (1, 2):
                    want(f"{key}-{sess}-pick-c2s{sd}", {**base, "c2_seed": sd, "cells": ids, "why": f"shuffled-book control (seed {sd}) of {m['uids'][0]}"})
            elif c == "base":
                want(f"{u['base']}-{u['root']}-tf{u['tf']}-{sess}-pick", {**base, "family": u["base"], "cells": ids,
                                                                        "why": f"the same strategy without the Level 2 option, for {m['uids'][0]}"})
    (V.OUT / "jobs_pick.json").write_text(json.dumps(jobs, indent=1))
    cand = [j for j in jobs if not (j.get("c1") or j.get("shift") or j.get("c2_seed"))]
    print("BUILD passers", len(P), "| menus", len(menus), "| jobs", len(jobs), "| candidate menus", len(cand), "cells", sum(len(j["cells"]) for j in cand),
          "| reused stores", len(reuse))
    for k, d in reuse:
        print("  reuse", d, k)


if __name__ == "__main__":
    main()
