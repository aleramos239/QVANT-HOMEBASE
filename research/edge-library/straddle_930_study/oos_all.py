"""OOS (owner 2026-11-01 "run them all OOS"): full-range runs 2021-10-01 -> 2026-11-01, split into 3:1 in-sample vs test months.
Only ≥1 hits full TP and ≥1 wins (owner). News = CPI+NFP 08:29:59. One account: a no-fill day = no TP, no win."""
import json, glob, datetime as dt, collections
from blueprint import wfmonths
R = "/Users/ramoscapital/ramos-quant-homebase/homebase/.state/tester/runs/"

def days(k):
    m = glob.glob(f"{R}2026110*-{k}"); assert len(m) == 1, k
    d = collections.defaultdict(lambda: [False, 0.0])
    for x in json.load(open(m[0] + "/trades.json")):
        d[x["date"]][0] |= x["exit_reason"] == "tp"; d[x["date"]][1] += x["net"]
    return d

SETS = {r: wfmonths._sets(r, dt.date.today().isoformat()) for r in ("NQ", "GC")}

def score(root, keys, base=None):
    ds = [days(k) for k in keys]
    allday = sorted(set().union(*[days(k) for k in base]) if base else set().union(*ds))
    out = []
    for months in SETS[root]:
        dd = [d for d in allday if d[:7] in months]
        tp = sum(any(x[d][0] for x in ds if d in x) for d in dd); w = sum(any(x[d][1] > 0 for x in ds if d in x) for d in dd)
        out.append((len(dd), 100 * tp / max(len(dd), 1), 100 * w / max(len(dd), 1)))
    return out

ROWS = [("4 contracts, 1:1.5", [
          ("Every day 9:30, two accounts", {"NQ": ("7352", "80fa"), "GC": ("f5d9", "d5ca")}, None),
          ("News 8:30, two accounts", {"NQ": ("a2df", "4a76"), "GC": ("a0b9", "ec34")}, None),
          ("News 8:30, one account (NQ ±15, GC ±2)", {"NQ": ("c184",), "GC": ("fe00",)}, {"NQ": ("a2df",), "GC": ("a0b9",)})]),
        ("2 contracts, 1:2", [
          ("Every day 9:30, two accounts", {"NQ": ("16bd", "20e3"), "GC": ("f006", "6657")}, None),
          ("News 8:30, two accounts", {"NQ": ("c55c", "cbc4"), "GC": ("e688", "cffc")}, None),
          ("News 8:30, one account (NQ ±15, GC ±2)", {"NQ": ("36df",), "GC": ("2910",)}, {"NQ": ("c55c",), "GC": ("e688",)})])]

if __name__ == "__main__":
    for title, rows in ROWS:
        print(f"\n### {title}\n| Setup | Mkt | Days in / test | ≥1 hits full TP in-sample | test months | ≥1 wins in-sample | test months |\n|---|---|---|---|---|---|---|")
        for lab, k, b in rows:
            for r in ("NQ", "GC"):
                (ni, ti, wi), (no, to, wo) = score(r, k[r], b[r] if b else None)
                print(f"| {lab} | {r} | {ni} / {no} | {ti:.1f}% | **{to:.1f}%** | {wi:.1f}% | **{wo:.1f}%** |")
