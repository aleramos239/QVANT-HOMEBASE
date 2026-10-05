# first_bar_mom_NQ_tf30_mid — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** first-bar momentum · **market** NQ · **session** mid · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): FAILED** — default $13,896, 12 of the 43 saved variants profitable.

**Reason (written before testing):** A session's first tf bar with range >= k x ATR (ATR before that bar) is momentum ignition; follow its direction at its close.

**Rules (default variant `k1p5_pts45-r3`):** If the session's first 30-minute bar is at least 1.5 x the average bar range, enter in its direction at its close. Stop 45 points; target 3 x the stop. Session: midday (11:00-13:30 ET); flat by 15:58 ET.

**Flags:** 2025-26 penalty (the family's old favourite failed on 2025-26); SAME IDEA as first_bar_mom_ES_tf15_mid, first_bar_mom_NQ_tf15_mid: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** 15-min: member; 1-min: fails BUILD test 1,2; 5-min: passes BUILD, fails 2024 test 5 (6 not run).

## Average variant and default variant, per year then combined
Average = the 96 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 43 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 34 | $5,291 | 42 % | 1.44 | $3,218 | $156 |
| average variant | 2022 | 118 | $8,201 | 37 % | 1.15 | $9,819 | $70 |
| average variant | 2023 | 131 | $876 | 36 % | 1.02 | $11,163 | $7 |
| average variant | 2024 | 131 | $11,239 | 39 % | 1.20 | $9,004 | $86 |
| average variant | 2025 | 119 | -$6,182 | 34 % | 0.91 | $18,901 | -$52 |
| average variant | combined | 532 | $19,425 | 37 % | 1.08 | $23,645 | $37 |
| default `k1p5_pts45-r3` | 2021* | 34 | $5,804 | 41 % | 1.32 | $4,545 | $171 |
| default `k1p5_pts45-r3` | 2022 | 102 | $18,562 | 35 % | 1.31 | $12,280 | $182 |
| default `k1p5_pts45-r3` | 2023 | 118 | $7,223 | 36 % | 1.11 | $17,997 | $61 |
| default `k1p5_pts45-r3` | 2024 | 120 | $11,195 | 36 % | 1.16 | $13,846 | $93 |
| default `k1p5_pts45-r3` | 2025 | 111 | $13,896 | 34 % | 1.22 | $10,727 | $125 |
| default `k1p5_pts45-r3` | combined | 485 | $56,680 | 36 % | 1.21 | $20,580 | $117 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 96 | 63 | 66 % | pass | fail | fail | $14,368 | $5,784 |
| 2024 | 96 | 83 | 86 % | pass | pass | pass | $11,239 | $6,914 |
| 2024 under stress | 96 | 70 | 73 % | | | | $9,150 | $3,954 |
| 2025 | 96 | 29 | 30 % | fail | fail | fail | -$6,182 | -$3,871 |
| 2025 under stress | 96 | 15 | 16 % | | | | -$8,076 | -$4,948 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| random entries, same exits and session (day-matched random tables) | BUILD | 10 | $18,992 | 98.4 % | $17,379, 99.0 % |
| random entries, same exits and session (day-matched random tables) | 2024 | 10 | $11,867 | 94.1 % | $8,215, 92.1 % |
| random entries, same exits and session (day-matched random tables) | 2025 | 10 | -$4,443 | 28.5 % | $2,080, 63.3 % |

## Stress (2 ticks of slippage + 250 ms delay)
* Average variant, 2024: $11,239 -> $9,150 under stress.
* Average variant, 2025: -$6,182 -> -$8,076 under stress.
* Default variant: BUILD $31,589 -> $26,019; 2024 $11,195 -> $12,430; 2025 $13,896 -> $6,136.
* Surviving set: 43 of 96 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 0 %, 2024 0 %, 2025 0 %, combined 0 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 0 %, 2024 -1 %, 2025 n/a, combined -2 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, 0 % of the net profit; those 0 trades net $0.

## Size
* Worst open loss on one trade (default, 1 contract): $910 = $92 per micro -> at most 21 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `first_bar_mom-NQ-tf30|mid|`.
