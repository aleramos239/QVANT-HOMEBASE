# straddle_tight_0830_NQ_tf30_pre — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 08:30 ET · **market** NQ · **session** pre · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 each judged on its own. 2026+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): FAILED** — default -$3,922, 8 of the 19 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).

**Rules (default variant `offA_pts8-r3`):** One second before 08:30 ET: a buy stop 3 points above the price and a sell stop 3 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 8 points; target 3 x the stop. Session: pre-market (08:25-09:30 ET); flat by 15:58 ET.

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit); SAME IDEA as straddle_t_0830_NQ_tf30_pre, straddle_tight_0830_GC_tf30_pre_evA, straddle_tight_0830_GC_tf30_pre_evB, straddle_tight_0830_NQ_tf30_pre_evA, straddle_tight_0830_NQ_tf30_pre_evB: one strategy for a stack, never two

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 19 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 61 | -$230 | 38 % | 0.96 | $1,459 | -$4 |
| average variant | 2022 | 241 | $4,051 | 42 % | 1.17 | $2,755 | $17 |
| average variant | 2023 | 228 | $5,915 | 44 % | 1.27 | $2,071 | $26 |
| average variant | 2024 | 235 | $5,548 | 43 % | 1.25 | $3,135 | $24 |
| average variant | 2025 | 238 | -$1,450 | 38 % | 0.94 | $4,287 | -$6 |
| average variant | combined | 1004 | $13,833 | 41 % | 1.14 | $5,855 | $14 |
| default `offA_pts8-r3` | 2021* | 69 | -$1,371 | 23 % | 0.85 | $2,269 | -$20 |
| default `offA_pts8-r3` | 2022 | 248 | $5,343 | 30 % | 1.18 | $4,108 | $22 |
| default `offA_pts8-r3` | 2023 | 249 | $7,619 | 31 % | 1.26 | $3,077 | $31 |
| default `offA_pts8-r3` | 2024 | 252 | $7,982 | 32 % | 1.27 | $3,903 | $32 |
| default `offA_pts8-r3` | 2025 | 248 | -$3,922 | 25 % | 0.88 | $6,017 | -$16 |
| default `offA_pts8-r3` | combined | 1066 | $15,651 | 29 % | 1.12 | $7,349 | $15 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $9,736 | $8,954 |
| 2024 | 27 | 22 | 81 % | pass | pass | pass | $5,548 | $6,005 |
| 2024 under stress | 27 | 19 | 70 % | | | | $3,474 | $3,984 |
| 2025 | 27 | 8 | 30 % | fail | fail | fail | -$1,450 | -$1,538 |
| 2025 under stress | 27 | 2 | 7 % | | | | -$3,650 | -$3,535 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $18,673 | 100.0 % | $16,617, 100.0 % |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $9,786 | 100.0 % | $9,354, 100.0 % |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $2,739 | 89.6 % | $3,243, 97.9 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $5,548 -> $3,474 under stress.
* Average variant, 2025: -$1,450 -> -$3,650 under stress.
* Default variant: BUILD $11,591 -> $9,337; 2024 $7,982 -> $5,827; 2025 -$3,922 -> -$6,465.
* Surviving set: 19 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 32 %, 2024 39 %, 2025 27 %, combined 33 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 96 %, 2024 68 %, 2025 n/a, combined 85 %.
* Default variant (whole seconds from the store, held under 5 s): 27 % of the winners' profit, 61 % of the net profit; those 239 trades net $9,569.

## Size
* Worst open loss on one trade (default, 1 contract): $375 = $38 per micro -> at most 51 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `straddle_tight_0830-NQ-tf30|pre|`.
