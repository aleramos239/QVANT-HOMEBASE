# straddle_t_1800_NQ_tf30_eve — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** bracket at 18:00 ET · **market** NQ · **session** eve · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**DEMOTED: luck not excluded (2024 test (5) fails with every control seed on disk; it passes with the first 2). Kept on file, NOT counted as edge.**
**2025 (read once, after choosing; nothing re-tuned): CONFIRMED** — default $27,309, 49 of the 61 saved variants profitable.

**Reason (written before testing):** At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (18:00 ET: Globex reopen).

**Rules (default variant `offatr0p25_pts45-r2`):** At 18:00 ET: a buy stop above and a sell stop below the last price (distance `atr0p25`: a fraction of the 30-minute average range, or fixed points); one cancels the other; unfilled orders are cancelled after 60 minutes. One trade a day. Stop 45 points; target 2 x the stop. Session: evening (18:00-23:59 ET, the evening before the trade date); flat by 15:58 ET.

**Flags:** DEMOTED: luck not excluded (a real-edge test fails with every control seed on disk; kept on file, not counted as edge)

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 160 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 61 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 54 | $3,352 | 33 % | 1.15 | $5,733 | $62 |
| average variant | 2022 | 200 | $13,856 | 33 % | 1.16 | $13,587 | $69 |
| average variant | 2023 | 184 | -$1,450 | 31 % | 0.98 | $13,298 | -$8 |
| average variant | 2024 | 209 | $12,460 | 31 % | 1.14 | $14,969 | $60 |
| average variant | 2025 | 223 | $8,152 | 31 % | 1.07 | $21,129 | $37 |
| average variant | combined | 870 | $36,371 | 32 % | 1.09 | $28,948 | $42 |
| default `offatr0p25_pts45-r2` | 2021* | 68 | $9,703 | 40 % | 1.26 | $4,669 | $143 |
| default `offatr0p25_pts45-r2` | 2022 | 242 | $28,722 | 38 % | 1.21 | $12,834 | $119 |
| default `offatr0p25_pts45-r2` | 2023 | 246 | -$13,924 | 32 % | 0.91 | $27,527 | -$57 |
| default `offatr0p25_pts45-r2` | 2024 | 248 | $33,733 | 39 % | 1.25 | $13,754 | $136 |
| default `offatr0p25_pts45-r2` | 2025 | 244 | $27,309 | 38 % | 1.20 | $14,059 | $112 |
| default `offatr0p25_pts45-r2` | combined | 1048 | $85,543 | 37 % | 1.14 | $31,511 | $82 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 160 | 134 | 84 % | pass | pass | pass | $15,759 | $13,127 |
| 2024 | 160 | 104 | 65 % | pass | fail | fail | $12,460 | $6,343 |
| 2024 under stress | 160 | 78 | 49 % | | | | $6,810 | -$278 |
| 2025 | 160 | 99 | 62 % | pass | fail | fail | $8,152 | $5,360 |
| 2025 under stress | 160 | 78 | 49 % | | | | $2,302 | -$978 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $40,659 | 100.0 % | $44,921, 100.0 % |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | -$360 | 48.0 % | $142, 50.6 % |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $3,513 | 65.1 % | $10,344, 94.2 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $12,460 -> $6,810 under stress.
* Average variant, 2025: $8,152 -> $2,302 under stress.
* Default variant: BUILD $24,501 -> $24,557; 2024 $33,733 -> $30,198; 2025 $27,309 -> $13,814.
* Surviving set: 61 of 160 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 2 %, 2024 1 %, 2025 3 %, combined 2 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 5 %, 2024 0 %, 2025 -12 %, combined 0 %.
* Default variant (whole seconds from the store, held under 5 s): 0 % of the winners' profit, -2 % of the net profit; those 2 trades net -$1,953.

## Size
* Worst open loss on one trade (default, 1 contract): $1,065 = $108 per micro -> at most 18 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `straddle_t_1800-NQ-tf30|eve|`.
