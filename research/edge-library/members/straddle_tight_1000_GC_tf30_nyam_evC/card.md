# straddle_tight_1000_GC_tf30_nyam_evC — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 10:00 ET, 10:00 release days · **market** GC · **session** nyam · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (10:00 ET).

**Rules (default variant `offA_pts1-r2`):** One second before 10:00 ET: a buy stop 0.6 points above the price and a sell stop 0.6 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 1 points; target 2 x the stop. Session: New York morning (09:30-11:00 ET); flat by 15:58 ET. Traded ONLY on days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); thin control (random-minute store: 2 seeds on disk)

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 25 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 11 | $392 | 48 % | 1.41 | $473 | $36 |
| average variant | 2022 | 43 | $3,143 | 53 % | 1.93 | $1,082 | $73 |
| average variant | 2023 | 42 | $4,675 | 64 % | 2.80 | $572 | $111 |
| average variant | 2024 | 46 | $4,309 | 58 % | 2.32 | $550 | $94 |
| average variant | combined | 142 | $12,519 | 58 % | 2.23 | $1,273 | $88 |
| default `offA_pts1-r2` | 2021* | 12 | $182 | 42 % | 1.23 | $260 | $15 |
| default `offA_pts1-r2` | 2022 | 43 | $1,908 | 51 % | 1.79 | $872 | $44 |
| default `offA_pts1-r2` | 2023 | 42 | $6,372 | 86 % | 10.32 | $228 | $152 |
| default `offA_pts1-r2` | 2024 | 46 | $3,396 | 61 % | 2.62 | $466 | $74 |
| default `offA_pts1-r2` | combined | 143 | $11,858 | 64 % | 2.98 | $1,050 | $83 |

## Share of variants profitable (pass = that share reached and the average variant positive)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $8,210 | $8,202 |
| 2024 | 27 | 27 | 100 % | pass | pass | pass | $4,309 | $3,396 |
| 2024 under stress | 27 | 27 | 100 % | | | | $3,301 | $2,376 |

## Real edge: the table average against random (lift = table average minus the control's average)
| control | period | lift | beats this share of replicates | note |
|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD | $95 a trade ($86 vs -$9) | 100 % |  |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | BUILD | $9,603 | 100 % | THIN CONTROL (2 real replicates) |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 | $97 a trade ($94 vs -$4) | 100 % |  |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | 2024 | $4,711 | 100 % | THIN CONTROL (2 real replicates) |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $4,309 -> $3,301 under stress.
* Default variant: BUILD $8,462 -> $6,918; 2024 $3,396 -> $2,372.
* Surviving set: 25 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, share of gross profit from trades held under 5 s: BUILD 39 %, 2024 64 %, combined 47 %.
* Default variant (exact times, held <= 5.000 s): 77 % of gross profit; those 95 trades net $10,830.

## Size
* Worst open loss on one trade (default, 1 contract): $130 = $14 per micro -> at most 142 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E3-C-GC`.
