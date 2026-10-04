"""ONE holdout scoring run (2025-01 -> 2026-09) of the frozen finalists. Refuses to run if the freeze hash does not match."""
import hashlib, json, sys
import pandas as pd
from nfp_lib import *
import grid, analyze
txt = (HERE / "frozen_finalists.json").read_text()
assert hashlib.sha256(txt.encode()).hexdigest() == (HERE / "frozen_finalists.sha256").read_text().split()[0], "freeze hash mismatch"
assert not (CACHE / "grid_HO.csv.gz").exists(), "holdout already scored once -- no second pass"
cells = json.loads(txt)["finalists"]
df, meta, Vs = grid.run("HO", cells)
meta.to_csv(CACHE / "cells_HO.csv"); df.to_csv(CACHE / "grid_HO.csv.gz", index=False)
json.dump({r: {d.isoformat(): v for d, v in Vs[r].items()} for r in Vs}, open(CACHE / "vprev_HO.json", "w"))
s = analyze.summarize("HO"); s.to_csv(CACHE / "summary_HO.csv", index=False)
print("scored", len(cells), "cells,", df.date.nunique(), "event days")
