# first_bar_mom_NQ_tf15_mid — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** first-bar momentum · **market** NQ · **session** mid · **bar size** 15 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 and 2026 each judged on its own. 2027+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): CONFIRMED** — default $11,104, 21 of the 39 saved variants profitable.
**2026 (read once, after choosing; nothing re-tuned): WEAK** — default $50,281, 21 of the 39 saved variants profitable.

**Reason (written before testing):** A session's first tf bar with range >= k x ATR (ATR before that bar) is momentum ignition; follow its direction at its close.

**Rules (default variant `k1p5_atr3-r2`):** If the session's first 15-minute bar is at least 1.5 x the average bar range, enter in its direction at its close. Stop 3 x the average bar range (ATR); target 2 x the stop. Session: midday (11:00-13:30 ET); flat by 15:58 ET.

**Flags:** 2025-26 penalty (the family's old favourite failed on 2025-26); SAME IDEA as first_bar_mom_ES_tf15_mid, first_bar_mom_NQ_tf30_mid: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** 1-min: fails BUILD test 1,2; 30-min: member; 5-min: passes BUILD, fails 2024 test 5 (6 not run).

## Average variant and default variant, per year then combined
Average = the 96 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 39 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 26 | $8,025 | 50 % | 2.00 | $2,247 | $309 |
| average variant | 2022 | 92 | $11,082 | 38 % | 1.27 | $7,276 | $121 |
| average variant | 2023 | 92 | -$2,185 | 35 % | 0.94 | $10,013 | -$24 |
| average variant | 2024 | 96 | $3,985 | 36 % | 1.09 | $8,813 | $42 |
| average variant | 2025 | 75 | $2,176 | 33 % | 1.05 | $15,117 | $29 |
| average variant | 2026 | 50 | $6,269 | 37 % | 1.23 | $8,708 | $125 |
| average variant | combined | 431 | $29,351 | 37 % | 1.15 | $22,971 | $68 |
| default `k1p5_atr3-r2` | 2021* | 16 | $18,406 | 75 % | 4.33 | $3,768 | $1,150 |
| default `k1p5_atr3-r2` | 2022 | 68 | $15,993 | 47 % | 1.23 | $14,080 | $235 |
| default `k1p5_atr3-r2` | 2023 | 70 | -$10,780 | 44 % | 0.81 | $23,979 | -$154 |
| default `k1p5_atr3-r2` | 2024 | 82 | $12,292 | 50 % | 1.19 | $11,690 | $150 |
| default `k1p5_atr3-r2` | 2025 | 54 | $11,104 | 46 % | 1.18 | $20,458 | $206 |
| default `k1p5_atr3-r2` | 2026* | 36 | $50,281 | 64 % | 2.52 | $6,742 | $1,397 |
| default `k1p5_atr3-r2` | combined | 326 | $97,296 | 50 % | 1.33 | $33,755 | $298 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 96 | 89 | 93 % | pass | pass | pass | $16,922 | $11,828 |
| 2024 | 96 | 48 | 50 % | fail | fail | fail | $3,985 | $170 |
| 2024 under stress | 96 | 41 | 43 % | | | | $3,251 | -$656 |
| 2025 | 96 | 53 | 55 % | fail | fail | fail | $2,176 | $1,324 |
| 2025 under stress | 96 | 50 | 52 % | | | | $962 | $390 |
| 2026 | 96 | 46 | 48 % | fail | fail | fail | $6,269 | -$62 |
| 2026 under stress | 96 | 46 | 48 % | | | | $5,737 | -$74 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| random entries, same exits and session (day-matched random tables) | BUILD | 10 | $20,772 | 99.8 % | $17,290, 99.9 % |
| random entries, same exits and session (day-matched random tables) | 2024 | 10 | $4,190 | 79.1 % | $3,546, 77.4 % |
| random entries, same exits and session (day-matched random tables) | 2025 | 10 | $2,029 | 63.5 % | $1,701, 61.9 % |
| random entries, same exits and session (day-matched random tables) | 2026 | 10 | $5,457 | 86.8 % | $5,106, 90.0 % |

## Stress (2 ticks of slippage + 250 ms delay)
* Average variant, 2024: $3,985 -> $3,251 under stress.
* Average variant, 2025: $2,176 -> $962 under stress.
* Average variant, 2026: $6,269 -> $5,737 under stress.
* Default variant: BUILD $23,619 -> $21,904; 2024 $12,292 -> $11,567; 2025 $11,104 -> $9,279; 2026 $50,281 -> $49,686.
* Surviving set: 39 of 96 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 0 %, 2024 0 %, 2025 0 %, 2026 0 %, combined 0 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 0 %, 2024 -1 %, 2025 3 %, 2026 0 %, combined 0 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, 0 % of the net profit; those 0 trades net $0.

## Size
* Worst open loss on one trade (default, 1 contract): $10,765 = $1,078 per micro -> at most 1 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `first_bar_mom-NQ-tf15|mid|`.
