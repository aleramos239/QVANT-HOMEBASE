# straddle_t_0830_NQ_tf30_pre — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** bracket at 08:30 ET · **market** NQ · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**

**Reason (written before testing):** At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (08:30 ET: US data).

**Rules (default variant `offatr0p25_pct0p1-r0`):** At 08:30 ET: a buy stop above and a sell stop below the last price (distance `atr0p25`: a fraction of the 30-minute average range, or fixed points); one cancels the other; unfilled orders are cancelled after 60 minutes. One trade a day. Stop 0.1 % of price; no target (out at the stop or at the flat time). Session: pre-market (08:25-09:30 ET); flat by 15:58 ET.

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); thin control (random-minute store: 2 seeds on disk); SAME IDEA as straddle_tight_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre_evA, straddle_tight_0830_GC_tf30_pre_evA, straddle_tight_0830_NQ_tf30_pre_evB, straddle_tight_0830_GC_tf30_pre_evB: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 160 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 67 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 63 | -$2,667 | 30 % | 0.91 | $9,979 | -$42 |
| average variant | 2022 | 232 | $37,863 | 37 % | 1.35 | $12,487 | $163 |
| average variant | 2023 | 231 | $8,469 | 34 % | 1.09 | $14,884 | $37 |
| average variant | 2024 | 237 | $7,328 | 33 % | 1.06 | $19,279 | $31 |
| average variant | combined | 763 | $50,993 | 34 % | 1.15 | $25,074 | $67 |
| default `offatr0p25_pct0p1-r0` | 2021* | 70 | $6,515 | 13 % | 1.33 | $5,893 | $93 |
| default `offatr0p25_pct0p1-r0` | 2022 | 248 | $61,333 | 9 % | 2.00 | $11,451 | $247 |
| default `offatr0p25_pct0p1-r0` | 2023 | 250 | $1,300 | 8 % | 1.02 | $18,197 | $5 |
| default `offatr0p25_pct0p1-r0` | 2024 | 252 | $39,987 | 12 % | 1.46 | $17,483 | $159 |
| default `offatr0p25_pct0p1-r0` | combined | 820 | $109,135 | 10 % | 1.46 | $20,217 | $133 |

## Share of variants profitable (pass = that share reached and the average variant positive)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 160 | 147 | 92 % | pass | pass | pass | $43,665 | $35,920 |
| 2024 | 160 | 94 | 59 % | fail | fail | fail | $7,328 | $2,228 |
| 2024 under stress | 160 | 75 | 47 % | | | | $5,599 | -$1,016 |

## Real edge: the table average against random (lift = table average minus the control's average)
| control | period | lift | beats this share of replicates | note |
|---|---|---|---|---|
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | BUILD | $29,479 | 100 % | THIN CONTROL (2 real replicates) |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | 2024 | $11,284 | 94 % | THIN CONTROL (2 real replicates) |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $7,328 -> $5,599 under stress.
* Default variant: BUILD $69,148 -> $63,680; 2024 $39,987 -> $32,639.
* Surviving set: 67 of 160 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, share of gross profit from trades held under 5 s: BUILD 3 %, 2024 5 %, combined 4 %.
* Default variant (exact times, held <= 5.000 s): 0 % of gross profit; those 78 trades net -$27,077.

## Size
* Worst open loss on one trade (default, 1 contract): $805 = $82 per micro -> at most 24 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `straddle_t_0830-NQ-tf30|pre|`.
