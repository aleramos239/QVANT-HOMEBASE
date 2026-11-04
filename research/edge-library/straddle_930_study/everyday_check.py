"""Why similar '≥1 hits TP' % gives very different net: day outcomes for the NQ 9:30 two-account setup, 1:2, 2 NQ, 50/100.
Also checks the full-range run (16bd/20e3) gives the same in-sample days as the in-sample-only run (90c7/ca6c)."""
import json, datetime as dt, warnings; warnings.filterwarnings("ignore")
import pandas as pd
import pair_filters as P
from blueprint import wfmonths

def load(k):
    m = list(P.RUNS.glob(f"20261101-*-draft_nq_930_side-{k}")); assert len(m) == 1
    return {x["date"]: x for x in json.load(open(m[0] / "trades.json"))}

L, S = load("16bd"), load("20e3")
oL, oS = load("90c7"), load("ca6c")
ins_s, oos_s = wfmonths._sets("NQ", dt.date.today().isoformat())
same = [d for d in oL if d in L]
diff = sum(abs(L[d]["net"] - oL[d]["net"]) + abs(S[d]["net"] - oS[d]["net"]) for d in same)
print(f"check: in-sample-only run {len(oL)} days, full run has {len(same)} of them, total $ difference on those days: ${diff:,.0f}")
print(f"check: trades.json sums = long {P.money(sum(x['net'] for x in L.values()))}, short {P.money(sum(x['net'] for x in S.values()))} "
      f"(tester said +$82,452 / −$25,418)\n")

def kind(l, s):
    r = {l["exit_reason"], s["exit_reason"]}
    if "tp" in r and "sl" in r: return "one hits TP, other stopped"
    if r == {"sl"}: return "both stopped"
    if r == {"tp"}: return "both hit TP"
    return "a time exit (15:55)"

rows = []
for d in L:
    if d in S and d[:7] in ins_s | oos_s:
        rows.append((d, "in-sample" if d[:7] in ins_s else "test months", kind(L[d], S[d]), L[d]["net"] + S[d]["net"]))
df = pd.DataFrame(rows, columns=["date", "part", "kind", "net"])
print("| Day outcome | In-sample days | In-sample % | In-sample avg $ | Test days | Test % | Test avg $ |\n|---|---|---|---|---|---|---|")
for k in ["one hits TP, other stopped", "both stopped", "a time exit (15:55)", "both hit TP"]:
    a = [df[(df.part == p) & (df.kind == k)] for p in ("in-sample", "test months")]
    n = [len(df[df.part == p]) for p in ("in-sample", "test months")]
    print(f"| {k} | {len(a[0])} | {len(a[0])/n[0]*100:.1f}% | {P.money(a[0].net.mean()) if len(a[0]) else '-'} | "
          f"{len(a[1])} | {len(a[1])/n[1]*100:.1f}% | {P.money(a[1].net.mean()) if len(a[1]) else '-'} |")
for p in ("in-sample", "test months"):
    q = df[df.part == p]; print(f"{p}: {len(q)} days, avg/day {P.money(q.net.mean())}, net {P.money(q.net.sum())}")
t = df[df.kind == "a time exit (15:55)"]
print("\ntime-exit days avg $: in-sample", P.money(t[t.part == "in-sample"].net.mean()), "| test", P.money(t[t.part == "test months"].net.mean()))
