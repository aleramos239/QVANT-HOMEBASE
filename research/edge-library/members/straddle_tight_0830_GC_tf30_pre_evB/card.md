# straddle_tight_0830_GC_tf30_pre_evB — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 08:30 ET, tier-1 08:30 release days · **market** GC · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 and 2026 each judged on its own. 2027+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): CONFIRMED** — default $3,962, 22 of the 22 saved variants profitable.
**2026 (read once, after choosing; nothing re-tuned): FAILED** — default -$846, 7 of the 22 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).

**Rules (default variant `offC_pts2-r2`):** One second before 08:30 ET: a buy stop 1.6 points above the price and a sell stop 1.6 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 2 points; target 2 x the stop. Session: pre-market (08:25-09:30 ET); flat by 15:58 ET. Traded ONLY on days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit); SAME IDEA as straddle_t_0830_NQ_tf30_pre, straddle_tight_0830_GC_tf30_pre_evA, straddle_tight_0830_NQ_tf30_pre, straddle_tight_0830_NQ_tf30_pre_evA, straddle_tight_0830_NQ_tf30_pre_evB: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 22 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 19 | $384 | 44 % | 1.21 | $866 | $20 |
| average variant | 2022 | 70 | $3,693 | 51 % | 1.62 | $1,619 | $52 |
| average variant | 2023 | 66 | $4,622 | 54 % | 1.87 | $1,032 | $70 |
| average variant | 2024 | 68 | $4,414 | 53 % | 1.75 | $1,008 | $65 |
| average variant | 2025 | 57 | $3,601 | 53 % | 1.74 | $1,071 | $63 |
| average variant | 2026 | 44 | -$896 | 40 % | 0.84 | $2,704 | -$20 |
| average variant | combined | 324 | $15,818 | 50 % | 1.53 | $2,945 | $49 |
| default `offC_pts2-r2` | 2021* | 19 | -$436 | 32 % | 0.84 | $1,348 | -$23 |
| default `offC_pts2-r2` | 2022 | 70 | $3,900 | 44 % | 1.47 | $2,128 | $56 |
| default `offC_pts2-r2` | 2023 | 66 | $6,536 | 52 % | 1.94 | $1,378 | $99 |
| default `offC_pts2-r2` | 2024 | 68 | $5,698 | 50 % | 1.73 | $920 | $84 |
| default `offC_pts2-r2` | 2025 | 57 | $3,962 | 47 % | 1.59 | $1,232 | $70 |
| default `offC_pts2-r2` | 2026* | 44 | -$846 | 36 % | 0.88 | $2,714 | -$19 |
| default `offC_pts2-r2` | combined | 324 | $18,814 | 46 % | 1.47 | $3,080 | $58 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $8,698 | $8,066 |
| 2024 | 27 | 26 | 96 % | pass | pass | pass | $4,414 | $4,088 |
| 2024 under stress | 27 | 22 | 81 % | | | | $3,011 | $2,290 |
| 2025 | 27 | 25 | 93 % | pass | pass | pass | $3,601 | $3,292 |
| 2025 under stress | 27 | 24 | 89 % | | | | $2,530 | $2,384 |
| 2026 | 27 | 7 | 26 % | fail | fail | fail | -$896 | -$846 |
| 2026 under stress | 27 | 4 | 15 % | | | | -$1,429 | -$1,410 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD |  | $46 a trade ($56 vs $10) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $11,097 | 100.0 % | $12,094, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 |  | $53 a trade ($65 vs $12) | 99.7 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $5,983 | 100.0 % | $6,607, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2025 |  | $64 a trade ($63 vs -$1) | 99.9 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $4,815 | 100.0 % | $5,660, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2026 |  | $14 a trade (-$20 vs -$35) | 72.4 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2026 | 10 | -$469 | 32.9 % | -$816, 16.0 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $4,414 -> $3,011 under stress.
* Average variant, 2025: $3,601 -> $2,530 under stress.
* Average variant, 2026: -$896 -> -$1,429 under stress.
* Default variant: BUILD $10,000 -> $8,874; 2024 $5,698 -> $5,260; 2025 $3,962 -> $2,962; 2026 -$846 -> -$1,256.
* Surviving set: 22 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 57 %, 2024 79 %, 2025 74 %, 2026 82 %, combined 68 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 78 %, 2024 92 %, 2025 95 %, 2026 n/a, combined 83 %.
* Default variant (whole seconds from the store, held under 5 s): 67 % of the winners' profit, 107 % of the net profit; those 179 trades net $20,064.

## Size
* Worst open loss on one trade (default, 1 contract): $520 = $53 per micro -> at most 37 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E1-B-GC`.
