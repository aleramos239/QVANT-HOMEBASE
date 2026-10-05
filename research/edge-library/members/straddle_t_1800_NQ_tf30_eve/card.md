# straddle_t_1800_NQ_tf30_eve — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** bracket at 18:00 ET · **market** NQ · **session** eve · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**

**Reason (written before testing):** At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (18:00 ET: Globex reopen).

**Rules (default variant `offatr0p25_pts45-r2`):** At 18:00 ET: a buy stop above and a sell stop below the last price (distance `atr0p25`: a fraction of the 30-minute average range, or fixed points); one cancels the other; unfilled orders are cancelled after 60 minutes. One trade a day. Stop 45 points; target 2 x the stop. Session: evening (18:00-23:59 ET, the evening before the trade date); flat by 15:58 ET.

**Flags:** thin control (random-minute store: 2 seeds on disk)

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 160 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 61 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 54 | $3,352 | 33 % | 1.15 | $5,733 | $62 |
| average variant | 2022 | 200 | $13,856 | 33 % | 1.16 | $13,587 | $69 |
| average variant | 2023 | 184 | -$1,450 | 31 % | 0.98 | $13,298 | -$8 |
| average variant | 2024 | 209 | $12,460 | 31 % | 1.14 | $14,969 | $60 |
| average variant | combined | 647 | $28,219 | 32 % | 1.10 | $23,301 | $44 |
| default `offatr0p25_pts45-r2` | 2021* | 68 | $9,703 | 40 % | 1.26 | $4,669 | $143 |
| default `offatr0p25_pts45-r2` | 2022 | 242 | $28,722 | 38 % | 1.21 | $12,834 | $119 |
| default `offatr0p25_pts45-r2` | 2023 | 246 | -$13,924 | 32 % | 0.91 | $27,527 | -$57 |
| default `offatr0p25_pts45-r2` | 2024 | 248 | $33,733 | 39 % | 1.25 | $13,754 | $136 |
| default `offatr0p25_pts45-r2` | combined | 804 | $58,234 | 37 % | 1.13 | $31,511 | $72 |

## Share of variants profitable (pass = that share reached and the average variant positive)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 160 | 134 | 84 % | pass | pass | pass | $15,759 | $13,127 |
| 2024 | 160 | 104 | 65 % | pass | fail | fail | $12,460 | $6,343 |
| 2024 under stress | 160 | 78 | 49 % | | | | $6,810 | -$278 |

## Real edge: the table average against random (lift = table average minus the control's average)
| control | period | lift | beats this share of replicates | note |
|---|---|---|---|---|
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | BUILD | $44,921 | 100 % | THIN CONTROL (2 real replicates) |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | 2024 | $142 | 49 % | THIN CONTROL (2 real replicates) |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $12,460 -> $6,810 under stress.
* Default variant: BUILD $24,501 -> $24,557; 2024 $33,733 -> $30,198.
* Surviving set: 61 of 160 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, share of gross profit from trades held under 5 s: BUILD 2 %, 2024 1 %, combined 1 %.
* Default variant (exact times, held <= 5.000 s): 0 % of gross profit; those 0 trades net $0.

## Size
* Worst open loss on one trade (default, 1 contract): $925 = $94 per micro -> at most 21 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `straddle_t_1800-NQ-tf30|eve|`.
