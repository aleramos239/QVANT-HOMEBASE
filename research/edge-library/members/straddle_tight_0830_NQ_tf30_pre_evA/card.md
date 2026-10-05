# straddle_tight_0830_NQ_tf30_pre_evA — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 08:30 ET, 08:30 release days · **market** NQ · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): FAILED** — default -$3,367, 0 of the 24 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).

**Rules (default variant `offB_pts5-r3`):** One second before 08:30 ET: a buy stop 5 points above the price and a sell stop 5 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 5 points; target 3 x the stop. Session: pre-market (08:25-09:30 ET); flat by 15:58 ET. Traded ONLY on days with an 08:30 ET US data release (jobs report, CPI, PPI, retail sales, GDP, PCE or weekly jobless claims).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit); SAME IDEA as straddle_t_0830_NQ_tf30_pre, straddle_tight_0830_GC_tf30_pre_evA, straddle_tight_0830_GC_tf30_pre_evB, straddle_tight_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre_evB: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 24 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 28 | $380 | 43 % | 1.14 | $764 | $14 |
| average variant | 2022 | 100 | $4,411 | 49 % | 1.49 | $1,633 | $44 |
| average variant | 2023 | 97 | $5,294 | 51 % | 1.63 | $1,429 | $55 |
| average variant | 2024 | 96 | $3,937 | 49 % | 1.44 | $1,454 | $41 |
| average variant | 2025 | 82 | -$2,806 | 34 % | 0.73 | $3,353 | -$34 |
| average variant | combined | 403 | $11,214 | 46 % | 1.29 | $4,138 | $28 |
| default `offB_pts5-r3` | 2021* | 28 | $943 | 36 % | 1.47 | $550 | $34 |
| default `offB_pts5-r3` | 2022 | 100 | $4,775 | 41 % | 1.65 | $1,176 | $48 |
| default `offB_pts5-r3` | 2023 | 97 | $4,732 | 41 % | 1.67 | $1,398 | $49 |
| default `offB_pts5-r3` | 2024 | 96 | $4,506 | 43 % | 1.59 | $826 | $47 |
| default `offB_pts5-r3` | 2025 | 83 | -$3,367 | 24 % | 0.64 | $3,367 | -$41 |
| default `offB_pts5-r3` | combined | 404 | $11,589 | 38 % | 1.35 | $3,716 | $29 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $10,084 | $10,305 |
| 2024 | 27 | 26 | 96 % | pass | pass | pass | $3,937 | $4,506 |
| 2024 under stress | 27 | 24 | 89 % | | | | $3,001 | $3,391 |
| 2025 | 27 | 0 | 0 % | fail | fail | fail | -$2,806 | -$2,887 |
| 2025 under stress | 27 | 0 | 0 % | | | | -$3,872 | -$4,119 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD |  | $27 a trade ($45 vs $18) | 99.7 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $13,502 | 100.0 % | $13,240, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 |  | $17 a trade ($41 vs $24) | 88.6 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $5,839 | 100.0 % | $5,414, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2025 |  | -$28 a trade (-$34 vs -$6) | 3.5 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | -$941 | 22.7 % | -$1,979, 2.3 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $3,937 -> $3,001 under stress.
* Average variant, 2025: -$2,806 -> -$3,872 under stress.
* Default variant: BUILD $10,450 -> $9,426; 2024 $4,506 -> $1,851; 2025 -$3,367 -> -$5,034.
* Surviving set: 24 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 63 %, 2024 77 %, 2025 77 %, combined 69 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 90 %, 2024 85 %, 2025 n/a, combined 98 %.
* Default variant (whole seconds from the store, held under 5 s): 78 % of the winners' profit, 87 % of the net profit; those 294 trades net $10,064.

## Size
* Worst open loss on one trade (default, 1 contract): $500 = $51 per micro -> at most 39 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E1-A-NQ`.
