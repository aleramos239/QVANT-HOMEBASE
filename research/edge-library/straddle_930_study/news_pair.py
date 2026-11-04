"""Two accounts on CPI / NFP days, one long one short, 2 NQ, 50-pt stop: entry 08:29:59 (draft_nq_news_side)
vs the 09:30:00 entry on the same days (draft_nq_930_side runs). In-sample 3:1 months only."""
import json, sys, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from homebase.backtest.stats.stats import _sharpe
import pair_filters as P

R = P.RUNS
NEWS = {"1:1.5": ("165327", "9838", "2c0b"), "1:2": ("165328", "a4fa", "a8b4"),
        "1:3": ("165329", "1fad", "b3f2"), "1:4": ("165330", "cfe0", "af0c")}
EV = pd.read_csv(Path(__file__).resolve().parents[1] / "engine/cache/events.csv")
EV = EV[EV.type.isin(["CPI", "NFP"])].set_index("date").type

def load(t, k, name):
    return json.load(open(R / f"20261101-{t}-{name}-{k}/trades.json"))

def news_pairs():
    out = {}
    for rr, (t, lk, sk) in NEWS.items():
        L, S = ({x["date"]: x["net"] for x in load(t, k, "draft_nq_news_side")} for k in (lk, sk))
        out[rr] = pd.DataFrame({"l": L, "s": S}).dropna()
    return out

def row(label, q, months):
    c = q.l + q.s; eq = c.cumsum(); one = ((q.l > 0) | (q.s > 0)).mean() * 100
    return (f"| {label} | {len(q)} | {one:.1f}% | {100-one:.1f}% | {P.money(c.sum())} | {P.money(c.mean())} | "
            f"{P.money((eq - eq.cummax()).min())} | {_sharpe(list(c)):.2f} | {P.money(c.sum()/months)} |")

H = "| {} | Days | ≥1 wins | Both lose | Net | Avg/day | Max DD | Sharpe | Avg/month |\n|---|---|---|---|---|---|---|---|---|"
if __name__ == "__main__":
    t, lk, _ = NEWS["1:1.5"]
    tr = load(t, lk, "draft_nq_news_side")
    ent = pd.to_datetime([x["entry_ms"] for x in tr], unit="ms", utc=True).tz_convert("America/New_York").strftime("%H:%M:%S.%f")
    print("entry clock (first 5):", list(ent[:5]), "| latest entry:", max(ent))
    news, base = news_pairs(), P.paired()
    days = news["1:1.5"].index
    months = len({d[:7] for d in days})
    print(f"\n{len(days)} CPI/NFP days in-sample over {months} months ({(EV.reindex(days)=='CPI').sum()} CPI, {(EV.reindex(days)=='NFP').sum()} NFP)")
    print("\n### All years, CPI + NFP\n" + H.format("Entry / RR"))
    for rr in NEWS:
        print(row(f"08:29:59 {rr}", news[rr], months))
        print(row(f"09:30:00 {rr}", base[rr].reindex(days).dropna(), months))
    for ev in ["CPI", "NFP"]:
        dd = days[EV.reindex(days).values == ev]
        print(f"\n### {ev} only, 08:29:59\n" + H.format("RR"))
        for rr in NEWS:
            print(row(rr, news[rr].loc[dd], months))
    for rr in NEWS:
        print(f"\n### By year, 08:29:59, {rr}\n" + H.format("Year"))
        for y in sorted({d[:4] for d in days}):
            q = news[rr][news[rr].index.str[:4] == y]
            print(row(y, q, len({d[:7] for d in q.index})))
    print("\nExits, 1:2 (long / short):", pd.Series([x["exit_reason"] for x in load(*[NEWS["1:2"][0], NEWS["1:2"][1]], "draft_nq_news_side")]).value_counts().to_dict(),
          pd.Series([x["exit_reason"] for x in load(NEWS["1:2"][0], NEWS["1:2"][2], "draft_nq_news_side")]).value_counts().to_dict())
