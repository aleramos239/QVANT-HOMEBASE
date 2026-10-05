# straddle_tight_0830_GC_tf30_pre_evA — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 08:30 ET, 08:30 release days · **market** GC · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 and 2026 each judged on its own. 2027+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): CONFIRMED** — default $342, 21 of the 24 saved variants profitable.
**2026 (read once, after choosing; nothing re-tuned): FAILED** — default -$1,146, 4 of the 24 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).

**Rules (default variant `offC_pts2-r2`):** One second before 08:30 ET: a buy stop 1.6 points above the price and a sell stop 1.6 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 2 points; target 2 x the stop. Session: pre-market (08:25-09:30 ET); flat by 15:58 ET. Traded ONLY on days with an 08:30 ET US data release (jobs report, CPI, PPI, retail sales, GDP, PCE or weekly jobless claims).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit); SAME IDEA as straddle_t_0830_NQ_tf30_pre, straddle_tight_0830_GC_tf30_pre_evB, straddle_tight_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre_evA, straddle_tight_0830_NQ_tf30_pre_evB: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 24 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 27 | $404 | 42 % | 1.16 | $1,229 | $15 |
| average variant | 2022 | 99 | $4,645 | 49 % | 1.54 | $1,728 | $47 |
| average variant | 2023 | 96 | $5,135 | 51 % | 1.63 | $1,422 | $53 |
| average variant | 2024 | 96 | $5,910 | 53 % | 1.72 | $1,216 | $62 |
| average variant | 2025 | 82 | $2,009 | 45 % | 1.25 | $1,964 | $24 |
| average variant | 2026 | 69 | -$2,029 | 37 % | 0.78 | $3,406 | -$29 |
| average variant | combined | 468 | $16,076 | 47 % | 1.36 | $3,833 | $34 |
| default `offC_pts2-r2` | 2021* | 26 | -$714 | 31 % | 0.82 | $1,776 | -$27 |
| default `offC_pts2-r2` | 2022 | 97 | $5,442 | 44 % | 1.47 | $2,032 | $56 |
| default `offC_pts2-r2` | 2023 | 96 | $6,206 | 46 % | 1.55 | $2,266 | $65 |
| default `offC_pts2-r2` | 2024 | 96 | $5,756 | 46 % | 1.49 | $1,786 | $60 |
| default `offC_pts2-r2` | 2025 | 82 | $342 | 37 % | 1.03 | $3,426 | $4 |
| default `offC_pts2-r2` | 2026* | 69 | -$1,146 | 36 % | 0.90 | $2,496 | -$17 |
| default `offC_pts2-r2` | combined | 466 | $15,886 | 42 % | 1.26 | $3,660 | $34 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 26 | 96 % | pass | pass | pass | $10,185 | $10,598 |
| 2024 | 27 | 27 | 100 % | pass | pass | pass | $5,910 | $5,756 |
| 2024 under stress | 27 | 26 | 96 % | | | | $4,105 | $4,158 |
| 2025 | 27 | 23 | 85 % | pass | pass | pass | $2,009 | $1,782 |
| 2025 under stress | 27 | 16 | 59 % | | | | $635 | $452 |
| 2026 | 27 | 4 | 15 % | fail | fail | fail | -$2,029 | -$2,106 |
| 2026 under stress | 27 | 3 | 11 % | | | | -$2,397 | -$2,524 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD |  | $36 a trade ($46 vs $10) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $14,149 | 100.0 % | $15,003, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 |  | $50 a trade ($62 vs $12) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $8,078 | 100.0 % | $9,590, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2025 |  | $25 a trade ($24 vs -$1) | 94.7 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $3,609 | 99.8 % | $4,391, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2026 |  | $5 a trade (-$29 vs -$35) | 63.1 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2026 | 10 | -$775 | 27.2 % | -$673, 25.8 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $5,910 -> $4,105 under stress.
* Average variant, 2025: $2,009 -> $635 under stress.
* Average variant, 2026: -$2,029 -> -$2,397 under stress.
* Default variant: BUILD $10,934 -> $8,798; 2024 $5,756 -> $5,188; 2025 $342 -> -$938; 2026 -$1,146 -> -$1,816.
* Surviving set: 24 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 45 %, 2024 67 %, 2025 67 %, 2026 67 %, combined 57 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 63 %, 2024 81 %, 2025 150 %, 2026 n/a, combined 72 %.
* Default variant (whole seconds from the store, held under 5 s): 54 % of the winners' profit, 108 % of the net profit; those 205 trades net $17,110.

## Size
* Worst open loss on one trade (default, 1 contract): $520 = $53 per micro -> at most 37 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E1-A-GC`.
