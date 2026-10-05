# tema_slope_NQ_tf30_eve — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** fast-average slope turn · **market** NQ · **session** eve · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**

**Reason (written before testing):** The low-lag TEMA(n) changing slope sign marks a turn early; enter in the new slope direction.

**Rules (default variant `n40_pct0p1-r0`):** The slope of the triple-smoothed 40-bar average (30-minute bars) changes sign at a bar close: enter in the new direction. Stop 0.1 % of price; no target (out at the stop or at the flat time). Session: evening (18:00-23:59 ET, the evening before the trade date); flat by 15:58 ET.

**Flags:** WEAK reason (the idea's reason is weak or only restates the trigger); 2025-26 was already seen once for this family's old favourite (an EXAM would be a second look)

**The same idea at other bar sizes (same market and session):** 15-min: fails BUILD test 2; 1-min: fails BUILD test 1,2; 5-min: fails BUILD test 1,2.

## Average variant and default variant, per year then combined
Average = the 96 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 51 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 40 | -$3,296 | 29 % | 0.81 | $7,843 | -$82 |
| average variant | 2022 | 166 | $1,542 | 30 % | 1.02 | $16,337 | $9 |
| average variant | 2023 | 134 | $21,726 | 39 % | 1.50 | $8,684 | $162 |
| average variant | 2024 | 140 | $11,967 | 33 % | 1.21 | $9,081 | $86 |
| average variant | combined | 480 | $31,939 | 33 % | 1.17 | $20,204 | $67 |
| default `n40_pct0p1-r0` | 2021* | 32 | -$10,293 | 0 % | 0.00 | $10,293 | -$322 |
| default `n40_pct0p1-r0` | 2022 | 148 | $15,648 | 6 % | 1.43 | $13,021 | $106 |
| default `n40_pct0p1-r0` | 2023 | 101 | $23,176 | 13 % | 1.89 | $4,436 | $229 |
| default `n40_pct0p1-r0` | 2024 | 101 | $21,171 | 13 % | 1.61 | $6,139 | $210 |
| default `n40_pct0p1-r0` | combined | 382 | $49,702 | 9 % | 1.46 | $13,021 | $130 |

## Share of variants profitable (pass = that share reached and the average variant positive)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 96 | 83 | 86 % | pass | pass | pass | $19,972 | $18,928 |
| 2024 | 96 | 70 | 73 % | pass | pass | fail | $11,967 | $5,879 |
| 2024 under stress | 96 | 62 | 65 % | | | | $9,763 | $3,416 |

## Real edge: the table average against random (lift = table average minus the control's average)
| control | period | lift | beats this share of replicates | note |
|---|---|---|---|---|
| random entries, same exits and session (2 random seeds on disk; 200 day-matched table draws) | BUILD | $16,123 | 98 % |  |
| random entries, same exits and session (2 random seeds on disk; 200 day-matched table draws) | 2024 | $1,988 | 68 % |  |

## Stress (2 ticks of slippage + 250 ms delay)
* Average variant, 2024: $11,967 -> $9,763 under stress.
* Default variant: BUILD $28,531 -> $24,497; 2024 $21,171 -> $20,616.
* Surviving set: 51 of 96 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, share of gross profit from trades held under 5 s: BUILD 0 %, 2024 0 %, combined 0 %.
* Default variant (exact times, held <= 5.000 s): 0 % of gross profit; those 0 trades net $0.

## Size
* Worst open loss on one trade (default, 1 contract): $445 = $46 per micro -> at most 43 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `tema_slope-NQ-tf30|eve|`.
