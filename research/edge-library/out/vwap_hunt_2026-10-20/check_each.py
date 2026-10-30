"""VWAP hunt 2026-10-20: my month tables against the lane's own numbers (brief section 4), AFTER SELECTION.md is frozen.

For every store: (1) each month the lane's walk-forward traded (wf/result.json months: its pick) = my cell's trades and net in that month,
all groups added; (2) `bp.py taught wf-each <name>` ("always": every cell in every test month) = my cell's OOS trades and net, all groups
added. Writes check_each.json; prints every mismatch."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import versions as V  # noqa: E402


def main(argv: list) -> None:
    if "FROZEN" not in (HERE / "SELECTION.md").read_text():
        raise SystemExit("refused: SELECTION.md is not frozen")
    names = argv or V.names_on_file()
    out, bad = {}, 0
    for n in names:
        Sx = V.store(n)
        wf = json.loads((Sx["base"] / "wf" / "result.json").read_text())
        rows = []
        for m in wf["months"]:
            if not m["cell"]:
                continue
            x = Sx["cells"][m["cell"]]
            k = x["month"] == m["month"]
            ok = int(k.sum()) == m["trades"] and abs(float(x["net"][k].sum()) - m["net"]) < 1.0
            rows.append({"month": m["month"], "cell": m["cell"], "ok": ok, "mine": [int(k.sum()), round(float(x["net"][k].sum()))], "lane": [m["trades"], round(m["net"])]})
        ef = Sx["base"] / "wf" / "each.json"
        if not ef.exists():
            subprocess.run([str(V.EL.parents[1] / ".venv-research" / "bin" / "python"), "bp.py", "taught", "wf-each", n], cwd=V.EL,
                           stdout=open(HERE / "logs" / f"each_{n}.log", "w"), stderr=subprocess.STDOUT, check=False)
        each = json.loads(ef.read_text()) if ef.exists() else {"cells": []}
        for r in each["cells"]:
            x = Sx["cells"][r["cell"]]
            k = np.array([V.month_kind(mo) == "oos" for mo in x["month"]], bool)
            a = r["always"]
            ok = int(k.sum()) == a["trades"] and abs(float(x["net"][k].sum()) - a["net"]) < 1.0
            rows.append({"each": r["cell"], "ok": ok, "mine": [int(k.sum()), round(float(x["net"][k].sum()))], "lane": [a["trades"], round(a["net"])]})
        if not each["cells"]:
            rows.append({"each": None, "ok": False, "note": "wf-each gave no file"})
        out[n] = rows
        miss = [r for r in rows if not r["ok"]]
        bad += len(miss)
        print(f"{n}: {len(rows)} checks, {len(miss)} mismatches" + (f": {miss[:3]}" if miss else ""), flush=True)
    (HERE / "check_each.json").write_text(json.dumps(out, indent=1))
    print(f"TOTAL mismatches: {bad}")


if __name__ == "__main__":
    main(sys.argv[1:])
