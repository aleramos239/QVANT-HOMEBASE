"""out/oos_summary.md from out/exam2026/oos.json (collect.py). The verdict words are EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED
STRATEGIES": REAL = passes 2025 and 2026 · OVERFIT = the average variant is not profitable on 2025 · NOT PROVEN = in between."""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
D = json.loads((W / "out" / "exam2026" / "oos.json").read_text())
NAMES = {"straddle_tight_0830-NQ-tf30-pre": "tight bracket 08:30 NQ, all days", "straddle_tight_0830-NQ-tf30-pre@A": "tight bracket 08:30 NQ, release days (evA)",
         "straddle_tight_0830-NQ-tf30-pre@B": "tight bracket 08:30 NQ, tier-1 days (evB)", "straddle_tight_0830-GC-tf30-pre@A": "tight bracket 08:30 GC, release days (evA)",
         "straddle_tight_0830-GC-tf30-pre@B": "tight bracket 08:30 GC, tier-1 days (evB)", "straddle_tight_1000-NQ-tf30-nyam@C": "tight bracket 10:00 NQ, 10:00 release days (evC)",
         "straddle_tight_1000-GC-tf30-nyam@C": "tight bracket 10:00 GC, 10:00 release days (evC)", "first_bar_mom-NQ-tf30-mid": "first-bar momentum NQ 30-min midday",
         "first_bar_mom-NQ-tf15-mid": "first-bar momentum NQ 15-min midday", "first_bar_mom-ES-tf15-mid": "first-bar momentum ES 15-min midday",
         "orb-NQ-tf15-pre": "opening range break NQ 15-min pre-market", "tema_slope-NQ-tf30-eve": "TEMA slope NQ 30-min evening",
         "donchian-NQ-tf30-nyam": "Donchian break NQ 30-min morning (15th, fix F1)", "straddle_t_0830-NQ-tf30-pre": "wide bracket 08:30 NQ (DEMOTED)",
         "straddle_t_1800-NQ-tf30-eve": "bracket 18:00 NQ (DEMOTED)"}
YRS = ("2021", "2022", "2023", "2024", "2025", "2026")


def k(v):
    return "–" if v is None else (f"{v / 1000:+.1f}k")


def verdict(r):
    c, e = r["check"], r.get("exam")
    if c["avg_net"] <= 0:
        return "OVERFIT" + (" (and DEMOTED on 2024)" if r["demoted_2024"] and "2024" in r["pick_verdict"] else " (and DEMOTED on BUILD)" if r["demoted_2024"] else "")
    if r["demoted_2024"]:
        return "NOT PROVEN: DEMOTED on 2024 by the 10-seed control"
    if c["verdict"] != "CONFIRMED":
        return "NOT PROVEN: 2025 profitable, fails " + " and ".join({"5": "the random test (5)", "6": "the slippage test (6)", "4": "the median (4)"}[x] for x in c["failed"])
    if e["verdict"] == "CONFIRMED":
        return "REAL"
    return "NOT PROVEN: passes 2025, fails 2026 test " + ", ".join(f"({x})" for x in e["failed"])


def lift(y):
    if not y:
        return "–"
    c = y["controls"]
    v = c.get("shift") or c.get("c1")
    return f"{k(v['lift'])} ({100 * v['p_beat']:.0f} %)"


def fast(y):
    if not y:
        return "–"
    n, w = y["fast_net_share"], y["fast_profit_share"]
    return (f"{100 * n + 0.0:.0f} %".replace("-0 %", "0 %") if n is not None else "loss") + f" ({100 * (w or 0):.0f} %)"


rows = []
for r in D:
    a, d, c, e = r["avg_rows"], r["default_rows"], r["check"], r.get("exam")
    rows.append("| " + " | ".join([
        NAMES[r["unit"]], "**" + verdict(r) + "**",
        " · ".join(k(a[y]["net"]) if y in a else "–" for y in YRS), " · ".join(k(d[y]["net"]) if y in d else "–" for y in YRS),
        f"{a['2025']['trades']:.0f} / " + (f"{a['2026']['trades']:.0f}" if "2026" in a else "–"),
        f"{c['saved_profitable']} / " + (str(e["saved_profitable"]) if e else "–") + f" of {r['saved']}",
        lift(c) + " / " + lift(e), k(-a["2025"]["max_dd"]) + " / " + (k(-a["2026"]["max_dd"]) if "2026" in a else "–"),
        fast(c) + " / " + fast(e)]) + " |")
SHORT = dict(zip(NAMES, ("tight 08:30 NQ all days", "tight 08:30 NQ evA", "tight 08:30 NQ evB", "tight 08:30 GC evA", "tight 08:30 GC evB", "tight 10:00 NQ evC",
                         "tight 10:00 GC evC", "first-bar NQ 30-min", "first-bar NQ 15-min", "first-bar ES 15-min", "ORB NQ 15-min", "TEMA slope NQ",
                         "Donchian NQ 30-min", "wide bracket 08:30 NQ", "bracket 18:00 NQ")))


def d0(v):
    return "–" if v is None else (f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}")


t2 = []
for r in D:
    for p, yr in (("check", "2025"), ("exam", "2026")):
        if p not in r:
            continue
        y, a, d = r[p], r["avg_rows"][yr], r["default_rows"][yr]
        t2.append("| " + " | ".join([
            SHORT[r["unit"]], yr, y["verdict"], f"{y['positive']} of {y['cells']} ({100 * y['share_pos']:.0f} %)", f"{d0(y['avg_net'])} / {d0(y['median_net'])}",
            d0(y["stress_avg_net"]), f"{a['trades']:.0f} · {100 * a['win']:.0f} % · {a['pf']:.2f} · {d0(a['max_dd'])}",
            f"{d0(d['net'])} · {d['trades']} · {100 * d['win']:.0f} % · {d['pf']:.2f} · {d0(d['max_dd'])}"]) + " |")
HEAD = """# Out-of-sample result of the 15 saved strategies — 2025 (check year) and 2026 (final exam). Scored 2026-10-05

**No saved strategy is proven REAL. 8 are NOT PROVEN, 7 are OVERFIT.** 2025 was read once for all 15; 2026 (1 Jan - 22 Sep) once for the 5
members that passed 2025, and all 5 failed at least one test there. Nothing was tuned, re-picked or re-run after a result was seen.
**Closest to real:** the tight bracket at 10:00 ET on gold on 10:00-release days — the average variant made money in every year 2021-2026 and
beat random minutes in both unseen years; it fails only the slippage test on 2026. Rule: EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES".

## Verdict table (dollars = 1 contract after costs; k = thousands; years 2021* (Sep-Dec) · 2022 · 2023 · 2024 · 2025 · 2026 (to 22 Sep); – = not run)
| unit | verdict | average variant, net per year | default variant, net per year | trades 2025 / 2026 (average variant) | saved variants profitable 2025 / 2026 | lift over random 2025 / 2026 (share of random tables beaten) | max drawdown 2025 / 2026 (average variant) | profit from trades held 5 s or less, 2025 / 2026: net share (winners' share) |
|---|---|---|---|---|---|---|---|---|
"""
MID = """
REAL = passes tests (4)-(6) on 2025 and on 2026 · OVERFIT = the average variant loses on 2025 · NOT PROVEN = in between. BUILD = 2021*-2023 and 2024 were used to choose.

## Test by test (4 = average and median variant profitable · 5 = beats random · 6 = profitable with 2 ticks + 250 ms, + 100 ms late cancel for brackets)
| unit | year | result | variants profitable | average / median variant | stressed average | average variant: trades · win rate · profit factor · max drawdown | default variant: net · trades · win rate · profit factor · max drawdown |
|---|---|---|---|---|---|---|---|
"""
TAIL = """
## The ideas in plain words (one line per idea; groups from out/v2_members.md)
1. **Bracket around the 08:30 data burst (NQ + gold, 6 units): NQ OVERFIT, gold NOT PROVEN.** All four NQ versions lost in 2025 (release days: 0 of 27 variants profitable). Gold passed 2025 clearly (85-93 % of variants, above random), then lost in 2026 (-$2,029 / -$896) and fell below random minutes: one good unseen year, one bad.
2. **Tight bracket at 10:00 on NQ, 10:00-release days: NOT PROVEN.** Small profit in 2025 (+$984), loss in 2026 (-$1,105; 1 of 27 variants profitable).
3. **Tight bracket at 10:00 on gold, 10:00-release days: NOT PROVEN, the nearest miss.** +$2,226 then +$522; beats random minutes and other days in both years. But 33 trades and $16 a trade in 2026: 2 ticks of slippage turn it to -$661.
4. **First-bar momentum at midday (NQ 30-min, NQ 15-min, ES 15-min): NOT PROVEN (30-min OVERFIT).** NQ 15-min made money on average in both unseen years (+$2,176, +$6,269, also under stress) but only about half its variants did (2026 median -$62), and in 2025 it beat just 63 % of random tables. Its default made +$50,281 in 2026: one variant, not proof. ES: +$1,373 in 2025, -$777 under stress.
5. **Opening range break NQ 15-min pre-market: OVERFIT.** -$9,371 in 2025, far below random entries (lift -$12,180). The judge also demotes it: with 10 random seeds its BUILD table beats 79 % of random tables, not 95 %.
6. **Bracket at 18:00 NQ: NOT PROVEN.** Demoted on 2024 (it does not beat 10 random-minute seeds, lift -$360). 2025 was good (+$8,152, passes all three), shown as information; by the rule it did not go to 2026.
7. **TEMA slope NQ evening: OVERFIT.** -$4,118 in 2025; 35 % of variants profitable.
8. **Donchian break NQ 30-min morning (15th saved, fix F1): NOT PROVEN.** +$7,955 in 2025 and +$2,501 under stress, but random entries with the same exits made more (lift -$960): the 2025 profit is not from the entry.

## Honest limits
- **Search size.** 1,916 units (about 50,000 candidate variants) were judged to find these 15; 1 of 168 random-entry tables passed the same six tests. Most picks failing on unseen data is what that much search predicts.
- **2026 is short.** 1 Jan - 22 Sep 2026, 179-180 sessions used (22 Sep itself was dropped for a hole 13:00-15:00, so the last day traded is 21 Sep). Release-day units have only 32-69 trades in it: a one-year verdict on so few trades is noisy both ways.
- **Event controls are still thin.** 10 random-minute seeds and 4,000 random day subsets, but no placebo for day filters, and only 45-82 release-day trades a year.
- **Burst fills.** The simulator fills a stop on the trigger print; in a release burst real fills slip. The four release-day brackets that made money in 2025 made 57-150 % of that profit in trades held 5 s or less (Lucid allows 50 % per account). The stress test is the only guard; one live gold fill is the only real evidence.
- **2025 data.** 4 sessions per market were dropped (NQ / ES: 9 Jan closure, 30 Jan hole, 4 Jul, 28 Nov; gold: 30 Jan, 4 Jul, 28 Nov, 24 Dec); 30 Jan was a GDP + claims day. Three kept days have holes of 21-46 minutes in regular hours: 16 Jan, 23 Jan, 13 Feb (all claims days).
- **2026 data.** NQ also lost 3 Apr (half day, jobs report) and 11 Sep (hole; a 10:00-release day that gold kept). Sessions after 22 Sep are desk recordings with gaps: not used.
- **Second looks.** 2024 had been opened before for several units, and the first-bar, opening-range and TEMA families had an old favourite seen on 2025-26 in a pilot. A pass would still have needed paper trading.

Files: cards `members/<unit>/card.md` (rows for 2025 and 2026) · numbers `out/exam2026/oos.json` · 2026 seal `out/exam2026/allowed.json`, read log `out/exam2026/reads.csv`,
stores `runs_exam2026/` · calendar check `out/exam2026/calendar_check.md` · how: `JUDGE.md` (`judge.py year <unit> --period check`, `--period exam --exam`).
"""
doc = HEAD + "\n".join(rows) + "\n" + MID + "\n".join(t2) + "\n" + TAIL
out = W / "out" / "oos_summary.md"
out.write_text(doc)
print(out, len(doc.splitlines()), "lines")
