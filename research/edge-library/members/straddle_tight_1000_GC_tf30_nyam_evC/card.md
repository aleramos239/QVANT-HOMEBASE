# straddle_tight_1000_GC_tf30_nyam_evC — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 10:00 ET, 10:00 release days · **market** GC · **session** nyam · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 and 2026 each judged on its own. 2027+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): CONFIRMED** — default $2,250, 24 of the 25 saved variants profitable.
**2026 (read once, after choosing; nothing re-tuned): WEAK** — default $868, 17 of the 25 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (10:00 ET).

**Rules (default variant `offA_pts1-r2`):** One second before 10:00 ET: a buy stop 0.6 points above the price and a sell stop 0.6 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 1 points; target 2 x the stop. Session: New York morning (09:30-11:00 ET); flat by 15:58 ET. Traded ONLY on days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim).

**Flags:** SECOND LOOK on 2024 (this 2024 table was already opened in an earlier stage); BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went); FAST: more than 50 % of the average variant's net profit is from trades held under 5 s (Lucid account-level limit)

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 25 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 11 | $392 | 48 % | 1.41 | $473 | $36 |
| average variant | 2022 | 43 | $3,143 | 53 % | 1.93 | $1,082 | $73 |
| average variant | 2023 | 42 | $4,675 | 64 % | 2.80 | $572 | $111 |
| average variant | 2024 | 46 | $4,309 | 58 % | 2.32 | $550 | $94 |
| average variant | 2025 | 45 | $2,226 | 51 % | 1.58 | $984 | $49 |
| average variant | 2026 | 33 | $522 | 44 % | 1.15 | $1,171 | $16 |
| average variant | combined | 220 | $15,267 | 54 % | 1.87 | $1,584 | $69 |
| default `offA_pts1-r2` | 2021* | 12 | $182 | 42 % | 1.23 | $260 | $15 |
| default `offA_pts1-r2` | 2022 | 43 | $1,908 | 51 % | 1.79 | $872 | $44 |
| default `offA_pts1-r2` | 2023 | 42 | $6,372 | 86 % | 10.32 | $228 | $152 |
| default `offA_pts1-r2` | 2024 | 46 | $3,396 | 61 % | 2.62 | $466 | $74 |
| default `offA_pts1-r2` | 2025 | 45 | $2,250 | 53 % | 1.92 | $550 | $50 |
| default `offA_pts1-r2` | 2026* | 33 | $868 | 48 % | 1.38 | $422 | $26 |
| default `offA_pts1-r2` | combined | 221 | $14,976 | 59 % | 2.40 | $1,050 | $68 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 27 | 100 % | pass | pass | pass | $8,210 | $8,202 |
| 2024 | 27 | 27 | 100 % | pass | pass | pass | $4,309 | $3,396 |
| 2024 under stress | 27 | 27 | 100 % | | | | $3,301 | $2,376 |
| 2025 | 27 | 26 | 96 % | pass | pass | pass | $2,226 | $1,630 |
| 2025 under stress | 27 | 25 | 93 % | | | | $1,661 | $1,270 |
| 2026 | 27 | 18 | 67 % | pass | fail | fail | $522 | $708 |
| 2026 under stress | 27 | 7 | 26 % | | | | -$661 | -$594 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD |  | $95 a trade ($86 vs -$9) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $9,711 | 100.0 % | $9,603, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 |  | $97 a trade ($94 vs -$4) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $4,970 | 100.0 % | $4,711, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2025 |  | $58 a trade ($49 vs -$9) | 99.6 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $3,578 | 99.9 % | $4,280, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2026 |  | $52 a trade ($16 vs -$37) | 98.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2026 | 10 | $1,626 | 96.5 % | $1,590, 99.4 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $4,309 -> $3,301 under stress.
* Average variant, 2025: $2,226 -> $1,661 under stress.
* Average variant, 2026: $522 -> -$661 under stress.
* Default variant: BUILD $8,462 -> $6,918; 2024 $3,396 -> $2,372; 2025 $2,250 -> $1,586; 2026 $868 -> $16.
* Surviving set: 25 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 39 %, 2024 64 %, 2025 62 %, 2026 71 %, combined 53 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 53 %, 2024 68 %, 2025 104 %, 2026 24 %, combined 63 %.
* Default variant (whole seconds from the store, held under 5 s): 82 % of the winners' profit, 97 % of the net profit; those 162 trades net $14,592.

## Size
* Worst open loss on one trade (default, 1 contract): $210 = $22 per micro -> at most 90 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E3-C-GC`.
