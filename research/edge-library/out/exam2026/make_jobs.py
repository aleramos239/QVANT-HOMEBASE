"""The job list of the EXAM read (2026) -- only the units on out/exam2026/allowed.json (EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED
STRATEGIES"). Per all-days store: the whole menu, the menu under stress, and the control with 10 seeds (random minute for a
bracket, the random-entry pool for a bar-based unit). The menu = out/check2025/make_jobs.unit_info (the live cells of the BUILD
table in the unit's session), the same list the 2025 read used. Writes out/exam2026/jobs_exam.json for run_exam.py."""
import json
import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
sys.path.insert(0, str(W / "out" / "check2025"))
import make_jobs as MJ  # noqa: E402

OUT = W / "out" / "exam2026"


def main():
    a = json.loads((OUT / "allowed.json").read_text())
    stores = {}
    for addr in a["units"]:
        stores.setdefault(addr.split("@")[0], []).append(addr)
    jobs = []
    for base_addr, who in stores.items():
        m = re.match(r"^(.+)-([A-Z0-9]+)-tf(\d+)-([a-z]+)$", base_addr)
        fam, root, tf, sess = m.groups()
        ids, oco, timed = MJ.unit_info(fam, root, tf, sess)
        base = {"family": fam, "root": root, "tf": tf, "sess": sess, "unit": base_addr, "period": "exam"}
        w = "allowed unit(s) " + ", ".join(who)
        jobs.append({**base, "cells": ids, "why": f"EXAM 2026, whole menu ({len(ids)} variants): {w}"})
        jobs.append({**base, "stress": True, "oco": oco, "cells": ids,
                     "why": f"EXAM 2026, whole menu under stress (2 ticks + 250 ms{' + 100 ms late cancel' if oco else ''}): {w}"})
        if timed:
            jobs.append({**base, "shift": True, "cells": ids, "why": f"EXAM 2026, random-minute control, seeds 1-10: {w}"})
        else:
            jobs.append({"c1": True, "root": root, "tf": tf, "sess": sess, "unit": f"c1-{root}-tf{tf}-{sess}", "period": "exam",
                         "why": f"EXAM 2026, random-entry pool, seeds 1-10: {w}"})
    (OUT / "jobs_exam.json").write_text(json.dumps(jobs, indent=1))
    for j in jobs:
        print(j["unit"], "stress" if j.get("stress") else "shift" if j.get("shift") else "c1" if j.get("c1") else "menu", len(j.get("cells") or []), "oco" if j.get("oco") else "")


if __name__ == "__main__":
    main()
