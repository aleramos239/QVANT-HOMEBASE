# first_bar_mom_ES_tf15_mid — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** first-bar momentum · **market** ES · **session** mid · **bar size** 15 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): WEAK** — default -$4,282, 20 of the 25 saved variants profitable.

**Reason (written before testing):** A session's first tf bar with range >= k x ATR (ATR before that bar) is momentum ignition; follow its direction at its close.

**Rules (default variant `k1p5_atr1p5-r2`):** If the session's first 15-minute bar is at least 1.5 x the average bar range, enter in its direction at its close. Stop 1.5 x the average bar range (ATR); target 2 x the stop. Session: midday (11:00-13:30 ET); flat by 15:58 ET.

**Flags:** 2025-26 penalty (the family's old favourite failed on 2025-26); SAME IDEA as first_bar_mom_NQ_tf15_mid, first_bar_mom_NQ_tf30_mid: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** 1-min: fails BUILD test 1,2; 30-min: fails BUILD test 1,2; 5-min: fails BUILD test 2.

## Average variant and default variant, per year then combined
Average = the 95 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 25 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 25 | $921 | 41 % | 1.15 | $2,112 | $37 |
| average variant | 2022 | 90 | $5,619 | 37 % | 1.21 | $5,072 | $62 |
| average variant | 2023 | 93 | -$1,908 | 36 % | 0.92 | $5,990 | -$20 |
| average variant | 2024 | 97 | $2,681 | 37 % | 1.10 | $4,238 | $28 |
| average variant | 2025 | 79 | $1,373 | 37 % | 1.05 | $8,457 | $17 |
| average variant | combined | 385 | $8,686 | 37 % | 1.08 | $13,054 | $23 |
| default `k1p5_atr1p5-r2` | 2021* | 17 | $2,794 | 53 % | 1.51 | $1,770 | $164 |
| default `k1p5_atr1p5-r2` | 2022 | 61 | $13,731 | 46 % | 1.53 | $5,844 | $225 |
| default `k1p5_atr1p5-r2` | 2023 | 72 | -$1,113 | 36 % | 0.95 | $4,908 | -$15 |
| default `k1p5_atr1p5-r2` | 2024 | 73 | $2,846 | 40 % | 1.11 | $5,534 | $39 |
| default `k1p5_atr1p5-r2` | 2025 | 61 | -$4,282 | 38 % | 0.88 | $17,028 | -$70 |
| default `k1p5_atr1p5-r2` | combined | 284 | $13,976 | 40 % | 1.12 | $17,601 | $49 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 95 | 65 | 68 % | pass | fail | fail | $4,632 | $2,562 |
| 2024 | 95 | 53 | 56 % | fail | fail | fail | $2,681 | $1,133 |
| 2024 under stress | 95 | 43 | 45 % | | | | $436 | -$1,032 |
| 2025 | 95 | 49 | 52 % | fail | fail | fail | $1,373 | $105 |
| 2025 under stress | 95 | 40 | 42 % | | | | -$777 | -$1,332 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| random entries, same exits and session (day-matched random tables) | BUILD | 10 | $11,743 | 99.6 % | $7,817, 98.3 % |
| random entries, same exits and session (day-matched random tables) | 2024 | 10 | $3,820 | 88.7 % | $3,410, 89.7 % |
| random entries, same exits and session (day-matched random tables) | 2025 | 10 | $4,312 | 89.2 % | $4,955, 94.0 % |

## Stress (2 ticks of slippage + 250 ms delay)
* Average variant, 2024: $2,681 -> $436 under stress.
* Average variant, 2025: $1,373 -> -$777 under stress.
* Default variant: BUILD $15,412 -> $12,238; 2024 $2,846 -> $1,083; 2025 -$4,282 -> -$8,569.
* Surviving set: 25 of 95 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 0 %, 2024 0 %, 2025 0 %, combined 0 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 0 %, 2024 0 %, 2025 -4 %, combined -1 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, 0 % of the net profit; those 0 trades net $0.

## Size
* Worst open loss on one trade (default, 1 contract): $6,688 = $670 per micro -> at most 2 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `first_bar_mom-ES-tf15|mid|`.
