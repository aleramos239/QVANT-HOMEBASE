# donchian_NQ_tf30_nyam — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** donchian · **market** NQ · **session** nyam · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): WEAK** — default -$3,914, 33 of the 43 saved variants profitable.

**Reason (written before testing):** Trend continuation: a close beyond the prior n-bar channel traps the other side, whose stops feed a continuation move.

**Rules (default variant `n20_pts30-r3`):** C donchian: close beyond the prior n-bar channel -> market with it. 2025-26 was already seen once for this family's old finalist (donchian-tf15): the EXAM is a SECOND look. Variant {"n": 20}; stop pts 30.0; target 3 x the stop. Session: New York morning (09:30-11:00 ET); flat by 15:58 ET.

**Flags:** 2025-26 was already seen once for this family's old favourite (an EXAM would be a second look); SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage)

**The same idea at other bar sizes (same market and session):** 15-min: fails BUILD test 2; 1-min: fails BUILD test 1,2; 5-min: fails BUILD test 2.

## Average variant and default variant, per year then combined
Average = the 64 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 43 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 44 | $4,148 | 41 % | 1.24 | $5,300 | $94 |
| average variant | 2022 | 142 | $26,220 | 41 % | 1.42 | $8,665 | $185 |
| average variant | 2023 | 138 | $4,405 | 35 % | 1.08 | $9,001 | $32 |
| average variant | 2024 | 130 | $13,446 | 39 % | 1.23 | $10,100 | $104 |
| average variant | 2025 | 139 | $7,955 | 36 % | 1.11 | $11,587 | $57 |
| average variant | combined | 593 | $56,175 | 38 % | 1.21 | $15,999 | $95 |
| default `n20_pts30-r3` | 2021* | 29 | $9,529 | 41 % | 1.96 | $3,226 | $329 |
| default `n20_pts30-r3` | 2022 | 85 | $22,810 | 38 % | 1.71 | $4,263 | $268 |
| default `n20_pts30-r3` | 2023 | 79 | $4,264 | 29 % | 1.13 | $6,570 | $54 |
| default `n20_pts30-r3` | 2024 | 83 | $25,358 | 40 % | 1.83 | $6,787 | $306 |
| default `n20_pts30-r3` | 2025 | 81 | -$3,914 | 25 % | 0.89 | $11,881 | -$48 |
| default `n20_pts30-r3` | combined | 357 | $58,047 | 34 % | 1.40 | $12,779 | $163 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 64 | 61 | 95 % | pass | pass | pass | $34,773 | $28,874 |
| 2024 | 64 | 57 | 89 % | pass | pass | pass | $13,446 | $11,115 |
| 2024 under stress | 64 | 56 | 88 % | | | | $11,266 | $9,497 |
| 2025 | 64 | 47 | 73 % | pass | pass | fail | $7,955 | $2,682 |
| 2025 under stress | 64 | 27 | 42 % | | | | $2,501 | -$1,596 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| random entries, same exits and session (day-matched random tables) | BUILD | 10 | $27,847 | 99.1 % | $12,378, 95.5 % |
| random entries, same exits and session (day-matched random tables) | 2024 | 10 | $7,493 | 79.7 % | $1,468, 60.8 % |
| random entries, same exits and session (day-matched random tables) | 2025 | 10 | -$960 | 46.2 % | $9,730, 95.3 % |

## Stress (2 ticks of slippage + 250 ms delay)
* Average variant, 2024: $13,446 -> $11,266 under stress.
* Average variant, 2025: $7,955 -> $2,501 under stress.
* Default variant: BUILD $36,603 -> $32,878; 2024 $25,358 -> $25,063; 2025 -$3,914 -> -$4,279.
* Surviving set: 43 of 64 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 0 %, 2024 0 %, 2025 1 %, combined 1 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD -1 %, 2024 -4 %, 2025 -11 %, combined -3 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, -1 % of the net profit; those 1 trades net -$614.

## Size
* Worst open loss on one trade (default, 1 contract): $610 = $62 per micro -> at most 32 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `donchian-NQ-tf30|nyam|`.
