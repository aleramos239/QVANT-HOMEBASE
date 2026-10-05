# straddle_tight_1000_NQ_tf30_nyam_evC — library member (admission v2: judged on the AVERAGE of all variants)

**Idea:** tight bracket at 10:00 ET, 10:00 release days · **market** NQ · **session** nyam · **bar size** 30 min · 1 contract, after costs. BUILD = 22 Sep 2021 to end 2023 (2021* = Sep-Dec), 2024 and 2025 and 2026 each judged on its own. 2027+ was never read.
**BUILD and 2024 were both used to choose, so neither is proof. Paper trading is still needed.**
**2025 (read once, after choosing; nothing re-tuned): CONFIRMED** — default -$1,100, 18 of the 26 saved variants profitable.
**2026 (read once, after choosing; nothing re-tuned): FAILED** — default -$1,258, 1 of the 26 saved variants profitable.

**Reason (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (10:00 ET).

**Rules (default variant `offA_pts5-r3`):** One second before 10:00 ET: a buy stop 3 points above the price and a sell stop 3 points below (one cancels the other; unfilled orders are cancelled after 5 minutes). One trade a day. Stop 5 points; target 3 x the stop. Session: New York morning (09:30-11:00 ET); flat by 15:58 ET. Traded ONLY on days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim).

**Flags:** BURST FILL RISK: a two-sided bracket over a data release; the simulator fills the stop on the trigger print (out/events_summary.md section 5: with a fill 1-25 ms later most of the profit of the v1 defaults went)

**The same idea at other bar sizes (same market and session):** none stored.

## Average variant and default variant, per year then combined
Average = the 27 judged variants (trades, net, max drawdown: mean over variants; win rate, profit factor, average trade: all their trades pooled). Default = the middle of the 26 surviving variants by BUILD net (survivors sorted by (BUILD net, variant order); the middle one; an even count takes the lower of the two middle ones).

| | period | trades | net | win rate | profit factor | max drawdown | average trade |
|---|---|---|---|---|---|---|---|
| average variant | 2021* | 11 | -$279 | 31 % | 0.77 | $759 | -$25 |
| average variant | 2022 | 42 | $2,075 | 48 % | 1.57 | $1,270 | $49 |
| average variant | 2023 | 42 | $2,304 | 50 % | 1.66 | $980 | $55 |
| average variant | 2024 | 46 | $3,242 | 53 % | 1.89 | $759 | $70 |
| average variant | 2025 | 45 | $984 | 42 % | 1.22 | $1,922 | $22 |
| average variant | 2026 | 32 | -$1,105 | 31 % | 0.71 | $1,752 | -$35 |
| average variant | combined | 218 | $7,221 | 45 % | 1.35 | $3,019 | $33 |
| default `offA_pts5-r3` | 2021* | 11 | -$409 | 18 % | 0.59 | $596 | -$37 |
| default `offA_pts5-r3` | 2022 | 42 | $1,852 | 38 % | 1.64 | $1,810 | $44 |
| default `offA_pts5-r3` | 2023 | 42 | $1,772 | 38 % | 1.60 | $705 | $42 |
| default `offA_pts5-r3` | 2024 | 46 | $5,016 | 54 % | 3.10 | $531 | $109 |
| default `offA_pts5-r3` | 2025 | 45 | -$1,100 | 24 % | 0.75 | $2,549 | -$24 |
| default `offA_pts5-r3` | 2026* | 32 | -$1,258 | 19 % | 0.59 | $1,554 | -$39 |
| default `offA_pts5-r3` | combined | 218 | $5,873 | 35 % | 1.35 | $3,620 | $27 |

## Share of variants profitable (pass = that share reached and the average variant positive; 60 % = more than 60 %)
| period | variants | profitable | share | 60 % | 70 % | 80 % | average net | median net |
|---|---|---|---|---|---|---|---|---|
| BUILD | 27 | 26 | 96 % | pass | pass | pass | $4,100 | $3,215 |
| 2024 | 27 | 27 | 100 % | pass | pass | pass | $3,242 | $2,591 |
| 2024 under stress | 27 | 26 | 96 % | | | | $2,619 | $1,667 |
| 2025 | 27 | 18 | 67 % | pass | fail | fail | $984 | $580 |
| 2025 under stress | 27 | 15 | 56 % | | | | $935 | $536 |
| 2026 | 27 | 1 | 4 % | fail | fail | fail | -$1,105 | -$1,068 |
| 2026 under stress | 27 | 0 | 0 % | | | | -$1,134 | -$991 |

## Real edge: the table average against random (lift = table average minus the control's average; 4,000 random tables per control)
| control | period | seeds on disk | lift | beats this share of random tables | the first 2 seeds only |
|---|---|---|---|---|---|
| the same table on all days (net per trade) and 4,000 random same-size day subsets | BUILD |  | $43 a trade ($43 vs $0) | 99.6 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | BUILD | 10 | $6,424 | 100.0 % | $6,905, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2024 |  | $75 a trade ($70 vs -$4) | 100.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2024 | 10 | $3,077 | 99.8 % | $3,494, 100.0 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2025 |  | $19 a trade ($22 vs $3) | 82.2 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2025 | 10 | $1,307 | 90.4 % | $1,732, 98.2 % |
| the same table on all days (net per trade) and 4,000 random same-size day subsets | 2026 |  | $5 a trade (-$35 vs -$40) | 60.0 % |  |
| the same table at random minutes / with a random direction (day-mixes of the seeds) | 2026 | 10 | $105 | 55.0 % | -$981, 10.1 % |

## Stress (2 ticks of slippage + 250 ms delay + 100 ms late cancel of the other bracket side)
* Average variant, 2024: $3,242 -> $2,619 under stress.
* Average variant, 2025: $984 -> $935 under stress.
* Average variant, 2026: -$1,105 -> -$1,134 under stress.
* Default variant: BUILD $3,215 -> $3,937; 2024 $5,016 -> $3,092; 2025 -$1,100 -> -$613; 2026 -$1,258 -> -$1,226.
* Surviving set: 26 of 27 variants are profitable on BUILD, on 2024 and under stress in both (`surviving_set.csv`).

## Speed (Lucid: an ACCOUNT must not make more than 50 % of its profit from trades held 5 s or less; not an admission gate)
* Average variant, trades held under 5 s, winners only (fast winners / all winners): BUILD 52 %, 2024 64 %, 2025 84 %, 2026 69 %, combined 63 %.
* Average variant, trades held under 5 s, net (their net profit / the total net profit; the FAST flag): BUILD 35 %, 2024 53 %, 2025 57 %, 2026 n/a, combined 29 %.
* Default variant (whole seconds from the store, held under 5 s): 82 % of the winners' profit, 61 % of the net profit; those 187 trades net $3,602.

## Size
* Worst open loss on one trade (default, 1 contract): $210 = $22 per micro -> at most 90 micros inside $2,000.

Files: `spec.json` (default variant inputs, tests), `surviving_set.csv`, `trades_build.json`, `trades_pick.json`, `daily.csv`. Unit `E3-C-NQ`.
