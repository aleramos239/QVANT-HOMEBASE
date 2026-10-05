# straddle_tight_0830_NQ_tf30_pre_evB — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 08:30 ET, tier-1 08:30 release days · **market** NQ · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): FAILED** — default -$1,358, 6 of the 20 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).

**Rules (default variant `offA_pts5-r3`):** One second before 08:30 ET: a buy stop 3 points above the price and a sell stop 3 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 5 points; target 3 x the stop. Session: pre-market (08:25-09:30 ET); flat by 15:58 ET. Traded ONLY on days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit); SAME IDEA as straddle_t_0830_NQ_tf30_pre, straddle_tight_0830_GC_tf30_pre_evA, straddle_tight_0830_GC_tf30_pre_evB, straddle_tight_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre_evA: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 20 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 19 | $554 | 47 % | 1.33 | $778 | $29 |
| average variant | 2022 | 71 | $5,350 | 56 % | 1.95 | $986 | $75 |
| average variant | 2023 | 67 | $3,241 | 51 % | 1.54 | $1,317 | $48 |
| average variant | 2024 | 68 | $3,272 | 50 % | 1.51 | $1,342 | $48 |
| average variant | 2025 | 57 | -$730 | 40 % | 0.90 | $1,944 | -$13 |
| average variant | combined | 282 | $11,688 | 49 % | 1.44 | $2,706 | $41 |
| default `offA_pts5-r3` | 2021* | 19 | $344 | 32 % | 1.24 | $436 | $18 |
| default `offA_pts5-r3` | 2022 | 71 | $5,326 | 48 % | 2.12 | $679 | $75 |
| default `offA_pts5-r3` | 2023 | 67 | $4,177 | 45 % | 1.89 | $805 | $62 |
| default `offA_pts5-r3` | 2024 | 68 | $1,133 | 37 % | 1.18 | $1,840 | $17 |
| default `offA_pts5-r3` | 2025 | 57 | -$1,358 | 28 % | 0.78 | $1,756 | -$24 |
| default `offA_pts5-r3` | combined | 282 | $9,622 | 39 % | 1.41 | $3,198 | $34 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $9,146 | $9,047 |
| 2024 | 27 | 22 | 81 % | pass | pass | pass | $3,272 | $2,838 |
| 2024 under stress | 27 | 20 | 74 % | | | | $2,674 | $3,165 |
| 2025 | 27 | 6 | 22 % | fail | fail | fail | -$730 | -$838 |
| 2025 under stress | 27 | 3 | 11 % | | | | -$1,638 | -$1,870 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD |  | $40 a trade ($58 vs $18) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $11,519 | 100.0 % | $11,069, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 |  | $25 a trade ($48 vs $24) | 90.7 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $4,462 | 100.0 % | $4,453, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2025 |  | -$7 a trade (-$13 vs -$6) | 36.4 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $1,353 | 91.7 % | $1,629, 98.8 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $3,272 -> $2,674 under stress.
* Average variant, 2025: -$730 -> -$1,638 under stress.
* Default variant: BUILD $9,847 -> $9,942; 2024 $1,133 -> $701; 2025 -$1,358 -> -$2,276.
* Surviving set: 20 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 74 %, 2024 85 %, 2025 82 %, combined 78 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 87 %, 2024 85 %, 2025 n/a, combined 86 %.
* Default variant (whole seconds from the store, held under 5 s): 85 % of the winners' profit, 88 % of the net profit; those 231 trades net $8,481.

## Size
* Worst open loss on one trade (default, 1 contract): $375 = $38 per micro -> at most 51 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E1-B-NQ`.
