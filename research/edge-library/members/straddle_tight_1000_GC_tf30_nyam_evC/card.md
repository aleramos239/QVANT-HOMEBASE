# straddle_tight_1000_GC_tf30_nyam_evC — ADMITTED

* family `straddle_tight_1000` · root GC · tf 30 · session nyam · cell `offA_pts1p6-r1` · 1 contract, costs included
* inputs: `{"at": "09:59:59", "cancel_min": 5, "dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "flat": "11:00:00", "hold_to": "day", "max_tr": 1, "off": "A", "off_mode": "menu", "off_val": 0.5, "sess": "all", "shift_max": 90, "shift_seed": 0, "stop_mode": "pts", "stop_val": 1.6, "tf": "30", "tgt_r": 1.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (10:00 ET).
* Complexity count (rules + free parameters): 6
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** no (2025-26 was never read for this family)
* **Penalty (EDGE_SPEC C):** none
* Notes: N7 straddle_tight 10:00 ET: OCO stop entries at last price +/- off points (A / B / C: NQ 3 / 5 / 8, ES 0.75 / 1.25 / 2, GC 0.6 / 1 / 1.6), placed at 09:59:59, unfilled legs cancelled 5 min later, entries until 11:00; own exits: stop NQ 5 / 8 / 10 pts (ES 1.25 / 2 / 2.5, GC 1 / 1.6 / 2) x target 1:1 / 1:2 / 1:3; null = the same bracket at random minutes (shift_seed). Second chance of the old NQ 09:30 straddle. CARD: the bracket is live within a second of the event -> the 2 ticks + 250 ms stress is the real gate; STAGE 3 EVENT FILTER `C`: trades only on days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim) (97 such sessions on BUILD, 46 in 2024; calendar = engine/cache/events.csv, official release dates, never checked against prices). STAGE 3 reason (written before any event-split number): a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way. The control in both periods is the same bracket fired at a random minute (2 seeds) on the same days. This is the BUILD central variant (library.plateau on the filtered table); no other variant may replace it.

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 27 | 27 | 0 | 0 | 8,202.00 | 100.0 % | yes | offA_pts1p6-r1 | 8,202.00 | 15,622.00 |
| pick | 27 | 27 | 0 | 0 | 3,396.00 | 100.0 % | yes | offA_pts1-r2 | 3,396.00 | 10,356.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 27 | 100.0 % | 8,202.00 | yes | yes | yes |
| stop: fixed | 27 | 27 | 100.0 % | 8,202.00 | yes | yes | yes |
| target: 1:1 | 9 | 9 | 100.0 % | 5,112.00 | yes | yes | yes |
| target: 1:2 | 9 | 9 | 100.0 % | 8,462.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 9,916.00 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 27 | 100.0 % | 3,396.00 | yes | yes | yes |
| stop: fixed | 27 | 27 | 100.0 % | 3,396.00 | yes | yes | yes |
| target: 1:1 | 9 | 9 | 100.0 % | 2,796.00 | yes | yes | yes |
| target: 1:2 | 9 | 9 | 100.0 % | 3,396.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 5,586.00 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 12 | 552.00 | 66.7 % | 1.79 | 540.00 | 1.85 | 46.00 | 164.00 |
| 2022 | 43 | 2,418.00 | 69.8 % | 2.07 | 1,116.00 | 2.31 | 56.23 | 164.00 |
| 2023 | 42 | 5,232.00 | 90.5 % | 8.52 | 348.00 | 5.42 | 124.57 | 164.00 |
| 2024 | 46 | 4,166.00 | 80.4 % | 3.59 | 386.00 | 3.93 | 90.57 | 184.00 |
| combined | 143 | 12,368.00 | 79.0 % | 3.35 | 1,656.00 | 3.66 | 86.49 | 184.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 62, min 62, max 62)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 12 | 2,976.00 | 66.7 % | 1.67 | 3,534.00 | 1.62 | 248.00 | 1,054.00 |
| 2022 | 43 | 13,392.00 | 69.8 % | 1.92 | 7,440.00 | 2.08 | 311.44 | 1,054.00 |
| 2023 | 42 | 30,876.00 | 90.5 % | 7.92 | 2,232.00 | 5.30 | 735.14 | 1,054.00 |
| 2024 | 46 | 24,118.00 | 80.4 % | 3.34 | 2,542.00 | 3.74 | 524.30 | 1,178.00 |
| combined | 143 | 71,362.00 | 79.0 % | 3.12 | 10,974.00 | 3.47 | 499.03 | 1,178.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 97 | 8,202.00 | 6.10 | 3.24 | 0.78 | 6,972.00 |
| pick | 46 | 4,166.00 | 4.58 | 3.59 | 0.80 | 3,396.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 11,056.00, mean -2,854.00, p95 -1,194.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 192 |
| beats_c1_pick | yes | lift 5,318.00, mean -1,152.00, p95 -900.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 91 |
| above_best_of_nulls_build | yes | t_build 6.10, bar 1.63, nulls 26, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 8,202.00 |
| net_pick | yes | net 4,166.00 |
| plateau_build | yes | cells 27, median_net 8,202.00, share_pos 1.00, member offA_pts1p6-r1 |
| beats_c1_build | yes | lift 11,056.00, mean -2,854.00, p95 -1,194.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 192 |
| stress_build | yes | base 8,202.00, stressed 6,972.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 5,318.00, mean -1,152.00, p95 -900.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 91 |
| stress_pick | yes | base 4,166.00, stressed 3,396.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 6.10, bar 1.63, nulls 26, thin NO |
| min_trades | yes | build 97, pick 46, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 19.00, micros_fit_worst 105, micros_fit_p99 110, limit 2,000.00 |
| rationale | yes | complexity 6 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

<!-- STAGE 3 RECORD -->
## Stage 3 record — event straddle `E3-C-GC` (2026-10-04): ADMITTED, FLAGGED (checker: confirm or demote)
* **Rule in plain words:** On days with a 10:00 ET release: at 09:59:59 ET a buy stop 0.6 points above and a sell stop 0.6 points below the gold price (one cancels the other; cancelled after 5 minutes if unfilled); stop 1.6 points, target 1.6 points (1:1); flat by 15:58. One trade a day at most.
* **Event days it trades:** days with a 10:00 ET release (ISM manufacturing, ISM services, JOLTS, Michigan sentiment prelim). 97 such sessions on BUILD, 46 in 2024. Calendar: `engine/cache/events.csv` (official release schedules; never checked against prices).
* **Reason (written before any number):** a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way.
* **Second look:** no: 2024 was opened for the first time for this unit
* BUILD tests: (a) 97 trades + 46 event days in 2024 · (b) 100 % of 27 variants positive, median $8,202 · (c) $85 a trade on event days vs -$30 on days without a release at that time (468 trades) · (d) t 6.10 vs bar 1.63 · (e) beats 100.00 % of 4,000 random same-size day subsets (needs 99.67 %).
* 2024: 100 % of 27 variants positive, median $3,396; this variant $4,166 (46 trades, rank 12 of 27); the same bracket at a random minute on the same days: -$1,152; on days without a release: -$32 a trade.
* Per year (1 contract): 2021* $552 (12) · 2022 $2,418 (43) · 2023 $5,232 (42) · 2024 $4,166 (46) · combined $12,368 (143).
* At about $1,000 of risk a trade (62 micros): 2021* $2,976 (12) · 2022 $13,392 (43) · 2023 $30,876 (42) · 2024 $24,118 (46) · combined $71,362 (143); worst open loss on one trade $1,178. Worst open loss per micro $19: at most 105 micros inside $2,000.
* Stress (2 ticks + 250 ms): BUILD $8,202 -> $6,972; 2024 $4,166 -> $3,396.
* **Speed flag:** 86 of 143 trades open AND close inside 2 seconds and earn $10,406 of the $12,368; the median trade lasts 0.3 s. The profit is the simulator's fills inside the burst.

### Event types it trades (BUILD / 2024; a day with two releases is counted under both)
| release | BUILD trades | BUILD net | 2024 trades | 2024 net |
|---|---|---|---|---|
| ISM manufacturing | 27 | $1,902 | 12 | $1,542 |
| ISM services | 27 | $2,562 | 12 | $1,192 |
| JOLTS | 27 | $2,232 | 12 | $202 |
| Michigan sentiment (prelim) | 27 | $2,562 | 12 | $1,212 |

### Fill realism (information, not a gate): what if the stop entry fills later than the trigger print?
| entry filled | BUILD net (never better than the stop price) | 2024 net | BUILD net (that print + 1 tick) | 2024 net | mean slip past the stop, BUILD / 2024 |
|---|---|---|---|---|---|
| on the trigger print (engine) | $8,202 | $4,166 | $8,202 | $4,166 | 0.109 / 0.163 pts |
| 1 ms later | $1,652 | -$1,004 | $1,652 | -$1,004 | 0.926 / 1.265 pts |
| 5 ms later | $1,852 | -$184 | $1,852 | -$184 | 1.015 / 1.343 pts |
| 25 ms later | -$88 | -$1,424 | -$88 | -$1,414 | 1.225 / 1.641 pts |
Own tick replay of the stored trades (it reproduces every engine trade to the cent at 0 ms). Median number of prints sharing the trigger print's timestamp: 17 (BUILD). **FILL-FRAGILE: the net is negative at 5 ms.**

| real account fills (desk journal, read-only) | fills | adverse slip past the stop price |
|---|---|---|
| NQ 09:30 straddle | 10 | mean 0.6 pt, median 0.375 pt, worst 1.75 pt |
| gold, jobs report 2026-10-02 | 1 | 0.0 |
| YM 09:30 | 2 | 4 and 5 pts |
Real fills sit near the engine's base fill (stop price + 1 tick) plus about one tick: far better than the 1 ms probe. None of them is an NQ or gold fill at an 08:30 / 10:00 release except the one gold jobs-report fill.

### Odds alone on a prop account (information; open losses count)
| account | fill model | size | micros | risk a trade | worst open loss | eval pass <= 10 days, any start | started the day before a tier-1 release | funded max payout <= 20 days |
|---|---|---|---|---|---|---|---|---|
| Lucid Flex 50K | trigger print | largest inside the drawdown | 40 | $640 | $760 | 0 % (bust 1 %) | 0 % | 0 % |
| Lucid Flex 50K | trigger print | about $1,000 risk | 40 | $640 | $760 | 0 % (bust 1 %) | 0 % | 0 % |
| Lucid Pro 50K (DLL) | trigger print | largest inside the drawdown | 40 | $640 | $760 | 0 % (bust 1 %) | 0 % | 0 % |
| Lucid Pro 50K (DLL) | trigger print | about $1,000 risk | 40 | $640 | $760 | 0 % (bust 1 %) | 0 % | 0 % |
| Lucid Pro 50K noDLL | trigger print | largest inside the drawdown | 40 | $640 | $760 | 0 % (bust 1 %) | 0 % | 0 % |
| Lucid Pro 50K noDLL | trigger print | about $1,000 risk | 40 | $640 | $760 | 0 % (bust 1 %) | 0 % | 0 % |
| Apex 50K | trigger print | largest inside the drawdown | 100 | $1,600 | $1,900 | 36 % (bust 7 %) | 29 % | 0 % |
| Apex 50K | trigger print | about $1,000 risk | 63 | $1,008 | $1,197 | 1 % (bust 6 %) | 1 % | 0 % |
| Lucid Flex 50K | 5 ms later | largest inside the drawdown | 40 | $640 | $880 | 0 % (bust 3 %) | 0 % | 0 % |
| Lucid Flex 50K | 5 ms later | about $1,000 risk | 40 | $640 | $880 | 0 % (bust 3 %) | 0 % | 0 % |
| Lucid Pro 50K (DLL) | 5 ms later | largest inside the drawdown | 40 | $640 | $880 | 0 % (bust 3 %) | 0 % | 0 % |
| Lucid Pro 50K (DLL) | 5 ms later | about $1,000 risk | 40 | $640 | $880 | 0 % (bust 3 %) | 0 % | 0 % |
| Lucid Pro 50K noDLL | 5 ms later | largest inside the drawdown | 40 | $640 | $880 | 0 % (bust 3 %) | 0 % | 0 % |
| Lucid Pro 50K noDLL | 5 ms later | about $1,000 risk | 40 | $640 | $880 | 0 % (bust 3 %) | 0 % | 0 % |
| Apex 50K | 5 ms later | largest inside the drawdown | 90 | $1,440 | $1,980 | 6 % (bust 21 %) | 4 % | 0 % |
| Apex 50K | 5 ms later | about $1,000 risk | 63 | $1,008 | $1,386 | 0 % (bust 14 %) | 0 % | 0 % |
Information only. Bar: 60 % eval / 75 % funded. Sizes are cut to the contract limit (Lucid 40 micros, Apex 100), so on Lucid the two sizes are often the same. A two-sided bracket is not allowed on Apex. The 5 ms trades keep the same stop and target distances from the later fill.

### Flags
* The whole profit needs the stop entry to fill on (or within about a tick of) the trigger print. One real gold fill and ten real NQ 09:30 fills support that; no real fill at an NQ 08:30 or a gold 10:00 release exists yet. Paper / small-size forward fills on release days are the missing evidence.
* FILL-FRAGILE. Only 143 trades in all (97 on BUILD). Different days from the 08:30 gold member (43 shared days of 143; daily correlation 0.03).
