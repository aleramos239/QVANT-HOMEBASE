"""GC vs NQ 9:30 two accounts, 4 contracts, $2,000 stop, 1:1.5, in-sample: CPI days and ADP days only. Hit rates only.
CPI: the calendar csv (ForexFactory). ADP has no calendar here: taken as the Wednesday on or before each NFP day
(ADP's usual slot; shortcut: misses the odd Thursday release and the 2025 shutdown months, when ADP came out but NFP slipped)."""
import csv, datetime as dt
import pandas as pd
from gc_vs_nq_hits import pair, pct
import homebase.strategies, pathlib
CAL = pathlib.Path(homebase.strategies.__file__).parent / "data/gc_0830_redfolder_days_2021_2026.csv"
rows = list(csv.DictReader(open(CAL)))
cpi = {r["date"] for r in rows if "CPI" in r["tag"].split("+")}
nfp = [dt.date.fromisoformat(r["date"]) for r in rows if "NFP" in r["tag"].split("+")]
adp = {(d - dt.timedelta(days=(d.weekday() - 2) % 7)).isoformat() for d in nfp}
M = {"NQ": pair("draft_nq_930_side", "ed1f", "f64c"), "GC": pair("draft_gc_930_side", "1d07", "ce3e")}
for lab, days in (("CPI + ADP days", cpi | adp), ("CPI days", cpi), ("ADP days", adp)):
    print(f"\n### {lab}\n| Market | Days | ≥1 hits full TP | ≥1 wins |\n|---|---|---|---|")
    for k, q in M.items():
        s = q[q.index.isin(days)]; t, w = pct(s); print(f"| {k} | {len(s)} | {t:.1f}% | {w:.1f}% |")
both = cpi | adp
print("\n### CPI + ADP days by year\n| Year | NQ ≥1 TP | NQ ≥1 wins | GC ≥1 TP | GC ≥1 wins | Days (NQ/GC) |\n|---|---|---|---|---|---|")
for y in sorted(set(M["NQ"].index.str[:4])):
    cells, n = [], []
    for k in M:
        s = M[k][M[k].index.isin(both) & (M[k].index.str[:4] == y)]
        cells += [f"{v:.1f}%" for v in pct(s)] if len(s) else ["-", "-"]; n.append(str(len(s)))
    print(f"| {y} | " + " | ".join(cells) + f" | {'/'.join(n)} |")
