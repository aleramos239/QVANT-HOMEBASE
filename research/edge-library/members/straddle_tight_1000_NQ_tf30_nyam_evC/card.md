# straddle_tight_1000_NQ_tf30_nyam_evC — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 10:00 ET, 10:00 release days · **market** NQ · **session** nyam · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (10:00 ET).

**Rules (default variant `offA_pts5-r3`):** One second before 10:00 ET: a buy stop 3 points above the price and a sell stop 3 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 5 points; target 3 x the stop. Session: New York morning (09:30-11:00 ET); flat by 15:58 ET. Traded ONLY on days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim).

**Flags:** BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); thin control (random-minute store: 2 seeds on disk); FAST: more than 50 % of the average variant's profit is from trades held under 5 s (Lucid account-level limit)

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 26 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 11 | -$279 | 31 % | 0.77 | $759 | -$25 |
| average variant | 2022 | 42 | $2,075 | 48 % | 1.57 | $1,270 | $49 |
| average variant | 2023 | 42 | $2,304 | 50 % | 1.66 | $980 | $55 |
| average variant | 2024 | 46 | $3,242 | 53 % | 1.89 | $759 | $70 |
| average variant | combined | 141 | $7,342 | 49 % | 1.61 | $1,740 | $52 |
| default `offA_pts5-r3` | 2021* | 11 | -$409 | 18 % | 0.59 | $596 | -$37 |
| default `offA_pts5-r3` | 2022 | 42 | $1,852 | 38 % | 1.64 | $1,810 | $44 |
| default `offA_pts5-r3` | 2023 | 42 | $1,772 | 38 % | 1.60 | $705 | $42 |
| default `offA_pts5-r3` | 2024 | 46 | $5,016 | 54 % | 3.10 | $531 | $109 |
| default `offA_pts5-r3` | combined | 141 | $8,231 | 42 % | 1.89 | $2,219 | $58 |

## Share of variants profitable (pass = that share reached and the average variant positive)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 26 | 96 % | pass | pass | pass | $4,100 | $3,215 |
| 2024 | 27 | 27 | 100 % | pass | pass | pass | $3,242 | $2,591 |
| 2024 under stress | 27 | 26 | 96 % | | | | $2,619 | $1,667 |

## Real edge: the table average against random (lift = table average minus the control's average)
| control | period | lift | beats this share of replicates | note |
|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD | $43 a trade ($43 vs $0) | 100 % |  |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | BUILD | $6,905 | 100 % | THIN CONTROL (2 real replicates) |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 | $75 a trade ($70 vs -$4) | 100 % |  |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | 2024 | $3,494 | 100 % | THIN CONTROL (2 real replicates) |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $3,242 -> $2,619 under stress.
* Default variant: BUILD $3,215 -> $3,937; 2024 $5,016 -> $3,092.
* Surviving set: 26 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, share of gross profit from trades held under 5 s: BUILD 52 %, 2024 64 %, combined 56 %.
* Default variant (exact times, held <= 5.000 s): 80 % of gross profit; those 112 trades net $6,552.

## Size
* Worst open loss on one trade (default, 1 contract): $195 = $20 per micro -> at most 97 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E3-C-NQ`.
