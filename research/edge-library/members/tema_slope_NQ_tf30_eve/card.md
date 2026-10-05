# tema_slope_NQ_tf30_eve — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** fast-average slope turn · **market** NQ · **session** eve · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): FAILED** — default $3,659, 21 of the 51 saved variants profitable.

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
| average variant | 2025 | 139 | -$4,118 | 30 % | 0.94 | $19,473 | -$30 |
| average variant | combined | 619 | $27,821 | 32 % | 1.10 | $26,474 | $45 |
| default `n40_pct0p1-r0` | 2021* | 32 | -$10,293 | 0 % | 0.00 | $10,293 | -$322 |
| default `n40_pct0p1-r0` | 2022 | 148 | $15,648 | 6 % | 1.43 | $13,021 | $106 |
| default `n40_pct0p1-r0` | 2023 | 101 | $23,176 | 13 % | 1.89 | $4,436 | $229 |
| default `n40_pct0p1-r0` | 2024 | 101 | $21,171 | 13 % | 1.61 | $6,139 | $210 |
| default `n40_pct0p1-r0` | 2025 | 99 | $3,659 | 10 % | 1.09 | $13,050 | $37 |
| default `n40_pct0p1-r0` | combined | 481 | $53,361 | 9 % | 1.36 | $13,050 | $111 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 96 | 83 | 86 % | pass | pass | pass | $19,972 | $18,928 |
| 2024 | 96 | 70 | 73 % | pass | pass | fail | $11,967 | $5,879 |
| 2024 under stress | 96 | 62 | 65 % | | | | $9,763 | $3,416 |
| 2025 | 96 | 34 | 35 % | fail | fail | fail | -$4,118 | -$3,398 |
| 2025 under stress | 96 | 28 | 29 % | | | | -$5,495 | -$6,720 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| random entries, same exits and session (day-matched random tables) | BUILD | 10 | $28,523 | 99.9 % | $15,493, 98.3 % |
| random entries, same exits and session (day-matched random tables) | 2024 | 10 | $12,548 | 95.8 % | $1,567, 61.5 % |
| random entries, same exits and session (day-matched random tables) | 2025 | 10 | $2,309 | 60.4 % | -$1,593, 41.3 % |

## Stress (2 ticks of slippage + 250 ms delay)
* Average variant, 2024: $11,967 -> $9,763 under stress.
* Average variant, 2025: -$4,118 -> -$5,495 under stress.
* Default variant: BUILD $28,531 -> $24,497; 2024 $21,171 -> $20,616; 2025 $3,659 -> -$4,951.
* Surviving set: 51 of 96 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 0 %, 2024 0 %, 2025 0 %, combined 0 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 0 %, 2024 0 %, 2025 n/a, combined 1 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, 0 % of the net profit; those 0 trades net $0.

## Size
* Worst open loss on one trade (default, 1 contract): $525 = $54 per micro -> at most 37 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `tema_slope-NQ-tf30|eve|`.
