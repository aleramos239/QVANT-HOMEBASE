# Are the 8 NOT PROVEN strategies overfit? Second look, 2026-10-05

**Result: 0 HOLDING UP · 4 UNCLEAR · 4 LIKELY OVERFIT / NO EDGE.** Analysis only, on stores already on disk: no new run, no new year opened, 2026 read only for the 5 allowed units.
In-sample = BUILD (22 Sep 2021 - 2023) + 2024, the years used to choose. Unseen = 2025, plus 2026 (to 21 Sep) where it was run. Every number: the average of all BUILD variants, 1 contract, after costs.

| # | unit | label | edge kept (net per trade, in-sample → unseen) | variants profitable: in-sample / 2025 / 2026 | rank correlation, past vs unseen | random tables beaten: 2025 / 2026 (both together) | unseen net → without its best 3 days | unseen net with slippage: 2025 / 2026 = total | unseen profit from trades held 5 s or less |
|---|---|---|---|---|---|---|---|---|---|
| 1 | tight bracket 10:00 gold, 10:00-release days | **UNCLEAR** | 40 % ($88 → $35) | 100 % / 96 % / 67 % | 0.68 | 100 % / 96 % (100 %) | +$2,748 → +$1,840 | +$1,661 / -$661 = +$1,000 | 89 % |
| 2 | tight bracket 08:30 gold, major releases | **UNCLEAR** | 46 % ($59 → $27) | 100 % / 93 % / 26 % | 0.89 | 100 % / 33 % (99.8 %) | +$2,705 → +$1,797 | +$2,530 / -$1,429 = +$1,101 | 86 % |
| 3 | tight bracket 08:30 gold, all release days | **LIKELY OVERFIT / NO EDGE** | none ($51 → -$0.13) | 100 % / 85 % / 15 % | 0.90 | 100 % / 27 % (94 %) | -$19 → -$927 | +$635 / -$2,397 = -$1,763 | no profit |
| 4 | tight bracket 10:00 NQ, 10:00-release days | **LIKELY OVERFIT / NO EDGE** | none ($52 → -$1.57) | 96 % / 67 % / 4 % | 0.61 | 90 % / 55 % (86 %) | -$121 → -$1,029 | +$935 / -$1,134 = -$199 | no profit |
| 5 | first-bar momentum NQ 15-min midday | **UNCLEAR** | 98 % ($68 → $67) | 79 % / 55 % / 48 % | 0.17 | 63 % / 87 % (83 %) | +$8,445 → -$4,503 | +$962 / +$5,737 = +$6,699 | 0 % |
| 6 | first-bar momentum ES 15-min midday | **UNCLEAR** | 73 % ($24 → $17) | 65 % / 52 % / – | 0.48 | 89 % / – | +$1,373 → -$5,259 | -$777 / – | none (fast trades lost $52) |
| 7 | Donchian break NQ 30-min morning | **LIKELY OVERFIT / NO EDGE** | 54 % ($106 → $57) | 100 % / 73 % / – | 0.62 | 46 % / – | +$7,955 → -$1,229 | +$2,501 / – | none (fast trades lost $848) |
| 8 | bracket 18:00 NQ evening | **LIKELY OVERFIT / NO EDGE** | 84 % ($44 → $37) | 82 % / 62 % / – | 0.52 | 65 % / – | +$8,152 → -$3,547 | +$2,302 / – | none (fast trades lost $990) |

Net per trade of the average variant, year by year (2021 = 22 Sep - Dec; 2026 = to 21 Sep), and the t-statistic of the daily average in the unseen period:

| # | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | shape | unseen traded days · t |
|---|---|---|---|---|---|---|---|---|
| 1 | $36 | $73 | $111 | $94 | $49 | $16 | falling three years running | 78 · 1.8 |
| 2 | $20 | $53 | $70 | $65 | $63 | -$20 | level four years, then one bad year | 101 · 1.3 |
| 3 | $15 | $47 | $53 | $62 | $25 | -$29 | halved, then negative | 151 · 0.0 |
| 4 | -$25 | $49 | $55 | $70 | $22 | -$35 | cut to a third, then negative | 77 · -0.1 |
| 5 | $309 | $121 | -$24 | $42 | $29 | $125 | jumpy, no trend | 266 · 0.7 |
| 6 | $37 | $62 | -$20 | $28 | $17 | – | jumpy, small | 155 · 0.2 |
| 7 | $94 | $185 | $32 | $104 | $57 | – | jumpy | 170 · 0.7 |
| 8 | $62 | $69 | -$8 | $60 | $37 | – | jumpy | 244 · 0.5 |

## Unit by unit
1. **Gold 10:00 bracket — UNCLEAR, one test short of HOLDING UP** (edge kept 40 %, the bar is 50 %). It beats random minutes in both unseen years, 96 % then 67 % of variants make money, and it is still +$1,840 without its best 3 days.
   The worry is a steady fade ($111 → $94 → $49 → $16 a trade) and fills: 2 ticks of slippage turn 2026 into -$661 and 89 % of the unseen profit is in trades of 5 s or less. **Settles it:** real fills (paper or 1 micro) on the next 30 or so 10:00-release days.
2. **Gold 08:30 bracket, major releases — UNCLEAR.** 2025 kept all of the edge (108 %); 2026 lost $20 a trade, with 26 % of variants profitable and 33 % of random minutes beaten. One good unseen year against one bad one of 44 trades.
   The two years together still beat 99.8 % of random minutes and stay positive with slippage (+$1,101). **Settles it:** more major-release days, the next 50 or so (about a year), unseen.
3. **Gold 08:30 bracket, all release days — LIKELY OVERFIT / NO EDGE.** 151 unseen trades net -$19: nothing kept, and -$1,763 with slippage. This is unit 2 plus the minor release days, and those minor days lost about $2,700 on 50 trades.
   The high rank correlation (0.90) only says wide targets beat tight ones in good and bad years alike; the level is gone. Nothing here that unit 2 does not already hold.
4. **NQ 10:00 bracket — LIKELY OVERFIT / NO EDGE.** 77 unseen trades net -$121. In 2026 1 of 27 variants made money and it did no better than random minutes (55 %). The 2025 profit (+$984) was thin, and the saved default lost in both years (-$1,100, -$1,258).
5. **First-bar momentum NQ 15-min — UNCLEAR, leaning to no proven edge.** On paper it kept 98 % and survives slippage, but 3 days out of 266 hold all the profit (-$4,503 without them), it beats only 63 % and 87 % of random tables, and the median variant lost in 2026 (-$62).
   Which variant did well before said almost nothing about after (0.17; in 2025 -0.02), so the saved default's +$50,281 in 2026 is luck of the draw. Even in-sample it was weak (t 1.7; in 2024 half the variants lost). **Settles it:** more unseen trading days, until it clears 90 % of random tables or fails to.
6. **First-bar momentum ES 15-min — UNCLEAR, leaning to no edge.** +$1,373 in 2025 but t 0.2, -$777 with slippage, -$5,259 without the best 3 days; the median variant made $105 and the saved default lost $4,282. In-sample was already weak (t 1.0).
   **Settles it:** a 2026 result. None is on disk: under the rule it was not allowed onto 2026 because 2025 was only WEAK.
7. **Donchian break NQ — LIKELY OVERFIT / NO EDGE, and the plain reading is "no entry edge" rather than curve-fitting.** It kept 54 % and 73 % of variants made money, but random entries with the same exits made $960 more: it beats 46 % of random tables.
   The 2025 money came from the exits in a trending market, not from the break signal. Without the best 3 days -$1,229; the saved default lost $3,914.
8. **Bracket 18:00 NQ — LIKELY OVERFIT / NO EDGE.** It kept 84 % per trade, but beats only 65 % of random minutes in 2025 and 48 % in 2024 (why it was demoted). t 0.5; -$3,547 without the best 3 days. A bracket at a random evening minute does about as well.

## How the labels were set (thresholds fixed before any number was computed, applied mechanically)
- **LIKELY OVERFIT / NO EDGE:** edge kept 25 % or less (or unseen net not positive), OR under 75 % of random tables beaten in the unseen data together, OR (not positive without the best 3 days AND rank correlation 0.1 or less).
- **HOLDING UP:** edge kept 50 % or more, 90 % or more of random tables beaten in every unseen year, positive without the best 3 days, positive with slippage. **UNCLEAR:** the rest.
- Edge kept = net per trade, unseen years together over in-sample. Random = the same table at random minutes (brackets) or with random entries (bar strategies): judge.py's own figures; "together" adds the two years' draws.
- Slippage = 2 ticks + 250 ms, + a 100 ms late cancel of the other side for brackets. Rank correlation = each variant's in-sample net against its unseen net.

## Limits
- The best-3-days test is mild for the brackets (a full win is capped near $303 a day for the average variant) and harsh for units 5-8, which live on a few big days. That is why it only counts together with the rank correlation.
- Rank correlation is high for most units because variants share the same entries; it flags only unit 5.
- All 8 came out of a search of 1,916 units. No check on the same data can undo that; only new days or real fills can.
- **Agreement with out/oos_summary.md: no number disagrees.** Yearly averages, variants profitable, saved variants profitable, default nets, lift and share of random beaten, slippage averages and 5-second shares were re-derived from the stores and match. New here: the two-year "together" figures, edge kept, rank correlations, best-days and t-statistics.

Files: `out/overfit8/diagnostics.csv` and `.json` (every number, including the default and median variant, top and bottom third, best 5 % of days) · script `out/overfit8/overfit8.py`.
