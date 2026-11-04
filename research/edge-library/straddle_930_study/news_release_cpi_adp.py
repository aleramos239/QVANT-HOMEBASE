"""CPI + ADP days, entry AT the release (CPI 08:29:59, ADP 08:14:59; ADP dates estimated), in-sample. Hit rates only.
Two accounts (market, one long one short): 4c 1:1.5 (NQ 25/37.5 7528/5025, GC 5/7.5 75d2/2dca);
2c 1:2 (NQ 50/100 dff1/a2cd, GC 10/20 ef58/62cd). One account, +-15 stop orders, first fill cancels the other:
2c 1:2 (NQ 0e8b, GC c598), 4c 1:1.5 (NQ 462d, GC d26c). Days = the market-order run's days; no fill = no TP, no win."""
import glob, json
import pandas as pd
R = "/Users/ramoscapital/ramos-quant-homebase/homebase/.state/tester/runs/"

def day(mk, k):
    m = glob.glob(f"{R}20261101-*-draft_{mk}_news_side-{k}"); assert len(m) == 1
    t = pd.DataFrame(json.load(open(m[0] + "/trades.json")))
    t["hm"] = pd.to_datetime(t.entry_ms, unit="ms", utc=True).dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    return t.groupby("date").agg(net=("net", "sum"), tp=("exit_reason", lambda s: (s == "tp").any()), hm=("hm", "first"))

TWO = {("4 contracts, 1:1.5", "NQ"): ("nq", "7528", "5025"), ("4 contracts, 1:1.5", "GC"): ("gc", "75d2", "2dca"),
       ("2 contracts, 1:2", "NQ"): ("nq", "dff1", "a2cd"), ("2 contracts, 1:2", "GC"): ("gc", "ef58", "62cd")}
ONE = {("4 contracts, 1:1.5", "NQ"): ("nq", "462d"), ("4 contracts, 1:1.5", "GC"): ("gc", "d26c"),
       ("2 contracts, 1:2", "NQ"): ("nq", "0e8b"), ("2 contracts, 1:2", "GC"): ("gc", "c598")}
rows, yr = [], {}
for key, (mk, lk, sk) in TWO.items():
    L, S = day(mk, lk), day(mk, sk); days = L.index
    o = day(mk, ONE[key][1]).reindex(days)
    two_tp, two_w = L.tp | S.tp, (L.net > 0) | (S.net > 0)
    one_tp, one_w = o.tp.astype("boolean").fillna(False), (o.net > 0)
    rows.append((*key, len(days), two_tp.mean() * 100, two_w.mean() * 100, o.net.notna().mean() * 100, one_tp.mean() * 100, one_w.mean() * 100))
    yr[key] = pd.DataFrame({"a": two_tp, "b": two_w, "c": one_tp, "d": one_w}).groupby(days.str[:4]).mean() * 100
    assert set(L.hm) <= {"08:14", "08:15", "08:29", "08:30"}, set(L.hm)
print("| Setup | Market | Days | Two accounts: ≥1 hits full TP | Two accounts: ≥1 wins | One account ±15: filled | One account: hits full TP | One account: wins |\n|---|---|---|---|---|---|---|---|")
for r in rows: print("| {} | {} | {} | {:.1f}% | {:.1f}% | {:.1f}% | {:.1f}% | {:.1f}% |".format(*r))
for key, y in yr.items():
    print(f"\n#### {key[0]}, {key[1]} by year\n| Year | Two: ≥1 TP | Two: ≥1 wins | One: TP | One: wins |\n|---|---|---|---|---|")
    for i, v in y.iterrows(): print(f"| {i} | {v.a:.1f}% | {v.b:.1f}% | {v.c:.1f}% | {v.d:.1f}% |")
