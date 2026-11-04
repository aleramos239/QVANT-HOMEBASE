"""CPI/NFP, two accounts, 4 NQ each, 50-pt stop, 1:1.5 (75-pt target): market vs stop entries 5-25 pts. In-sample."""
import news_stop_offsets as X, pair_filters as P
RUNS = {"Market": ("57ce", "736a"), "Stop ±5": ("4d43", "2a61"), "Stop ±10": ("4af8", "299d"), "Stop ±15": ("7967", "af63"),
        "Stop ±20": ("6c73", "6f4f"), "Stop ±25": ("abf7", "8cc7")}
print("| Entry | ≥1 hits full TP | Both hit TP | Net | Avg/day | Max DD | Sharpe | Green years |\n|---|---|---|---|---|---|---|---|")
for lab, (l, s) in RUNS.items():
    r = X.stats(X.side(l, ""), X.side(s, ""))
    print(f"| {lab} | {r['tp']:.1f}% | {r['both_tp']:.1f}% | {P.money(r['net'])} | {P.money(r['net']/r['days'])} | {P.money(r['dd'])} | {r['sh']:.2f} | {r['yrs']} |")
