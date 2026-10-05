# straddle_tight_0830_GC_tf30_pre_evB — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 08:30 ET, tier-1 08:30 release days · **market** GC · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 judged on its own. 2025+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).

**Rules (default variant `offC_pts2-r2`):** One second before 08:30 ET: a buy stop 1.6 points above the price and a sell stop 1.6 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 2 points; target 2 x the stop. Session: pre-market (08:25-09:30 ET); flat by 15:58 ET. Traded ONLY on days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); thin control (random-minute store: 2 seeds on disk); FAST: more than 50 % of the average variant's profit is from trades held under 5 s (Lucid account-level limit); SAME IDEA as straddle_t_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre_evA, straddle_tight_0830_GC_tf30_pre_evA, straddle_tight_0830_NQ_tf30_pre_evB: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 22 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 19 | $384 | 44 % | 1.21 | $866 | $20 |
| average variant | 2022 | 70 | $3,693 | 51 % | 1.62 | $1,619 | $52 |
| average variant | 2023 | 66 | $4,622 | 54 % | 1.87 | $1,032 | $70 |
| average variant | 2024 | 68 | $4,414 | 53 % | 1.75 | $1,008 | $65 |
| average variant | combined | 223 | $13,113 | 52 % | 1.69 | $2,025 | $59 |
| default `offC_pts2-r2` | 2021* | 19 | -$436 | 32 % | 0.84 | $1,348 | -$23 |
| default `offC_pts2-r2` | 2022 | 70 | $3,900 | 44 % | 1.47 | $2,128 | $56 |
| default `offC_pts2-r2` | 2023 | 66 | $6,536 | 52 % | 1.94 | $1,378 | $99 |
| default `offC_pts2-r2` | 2024 | 68 | $5,698 | 50 % | 1.73 | $920 | $84 |
| default `offC_pts2-r2` | combined | 223 | $15,698 | 47 % | 1.61 | $3,080 | $70 |

## Share of variants profitable (pass = that share reached and the average variant positive)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $8,698 | $8,066 |
| 2024 | 27 | 26 | 96 % | pass | pass | pass | $4,414 | $4,088 |
| 2024 under stress | 27 | 22 | 81 % | | | | $3,011 | $2,290 |

## Real edge: the table average against random (lift = table average minus the control's average)
| control | period | lift | beats this share of replicates | note |
|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD | $46 a trade ($56 vs $10) | 100 % |  |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | BUILD | $12,094 | 100 % | THIN CONTROL (2 real replicates) |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 | $53 a trade ($65 vs $12) | 100 % |  |
| the same table at random minutes / with a random direction (2 seeds: THIN; 200 day-mixes of them) | 2024 | $6,607 | 100 % | THIN CONTROL (2 real replicates) |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $4,414 -> $3,011 under stress.
* Default variant: BUILD $10,000 -> $8,874; 2024 $5,698 -> $5,260.
* Surviving set: 22 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, share of gross profit from trades held under 5 s: BUILD 57 %, 2024 79 %, combined 64 %.
* Default variant (exact times, held <= 5.000 s): 62 % of gross profit; those 111 trades net $15,316.

## Size
* Worst open loss on one trade (default, 1 contract): $350 = $36 per micro -> at most 55 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E1-B-GC`.
