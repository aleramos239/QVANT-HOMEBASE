# straddle_tight_0830_NQ_tf30_pre_evB — ADMITTED

* family `straddle_tight_0830` · root NQ · tf 30 · session pre · cell `offB_pts5-r3` · 1 contract, costs included
* inputs: `{"at": "08:29:59", "cancel_min": 5, "dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "flat": "09:30:00", "hold_to": "day", "max_tr": 1, "off": "B", "off_mode": "menu", "off_val": 0.5, "sess": "all", "shift_max": 90, "shift_seed": 0, "stop_mode": "pts", "stop_val": 5.0, "tf": "30", "tgt_r": 3.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).
* Complexity count (rules + free parameters): 6
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** SECOND LOOK ON 2024: 2024 was already read for straddle_tight_0830 NQ on all days (stage 2b) (and 2025+ was never read)
* **Penalty (EDGE_SPEC C):** none
* Notes: N7 straddle_tight 08:30 ET: OCO stop entries at last price +/- off points (A / B / C: NQ 3 / 5 / 8, ES 0.75 / 1.25 / 2, GC 0.6 / 1 / 1.6), placed at 08:29:59, unfilled legs cancelled 5 min later, entries until 09:30; own exits: stop NQ 5 / 8 / 10 pts (ES 1.25 / 2 / 2.5, GC 1 / 1.6 / 2) x target 1:1 / 1:2 / 1:3; null = the same bracket at random minutes (shift_seed). Second chance of the old NQ 09:30 straddle. CARD: the bracket is live within a second of the event -> the 2 ticks + 250 ms stress is the real gate; STAGE 3 EVENT FILTER `B`: trades only on days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out) (159 such sessions on BUILD, 68 in 2024; calendar = engine/cache/events.csv, official release dates, never checked against prices). STAGE 3 reason (written before any event-split number): a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way. The control in both periods is the same bracket fired at a random minute (2 seeds) on the same days. This is the BUILD central variant (library.plateau on the filtered table); no other variant may replace it.

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 27 | 27 | 0 | 0 | 9,047.00 | 100.0 % | yes | offB_pts5-r3 | 9,047.00 | 16,282.00 |
| pick | 27 | 27 | 0 | 0 | 2,838.00 | 81.5 % | yes | offA_pts10-r3 | 2,838.00 | 9,263.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 27 | 100.0 % | 9,047.00 | yes | yes | yes |
| stop: fixed | 27 | 27 | 100.0 % | 9,047.00 | yes | yes | yes |
| target: 1:1 | 9 | 9 | 100.0 % | 5,662.00 | yes | yes | yes |
| target: 1:2 | 9 | 9 | 100.0 % | 9,712.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 12,247.00 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 22 | 81.5 % | 2,838.00 | yes | yes | yes |
| stop: fixed | 27 | 22 | 81.5 % | 2,838.00 | yes | yes | yes |
| target: 1:1 | 9 | 5 | 55.6 % | 573.00 | NO | NO | NO |
| target: 1:2 | 9 | 8 | 88.9 % | 4,513.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 5,623.00 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 19 | 1,124.00 | 42.1 % | 1.90 | 436.00 | 2.32 | 59.16 | 129.00 |
| 2022 | 71 | 5,961.00 | 50.7 % | 2.27 | 694.00 | 3.09 | 83.96 | 299.00 |
| 2023 | 67 | 1,962.00 | 37.3 % | 1.36 | 978.00 | 1.12 | 29.28 | 504.00 |
| 2024 | 68 | 2,383.00 | 41.2 % | 1.40 | 645.00 | 1.28 | 35.04 | 414.00 |
| combined | 225 | 11,430.00 | 43.1 % | 1.66 | 978.00 | 1.90 | 50.80 | 504.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 100, min 100, max 100)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 19 | 10,100.00 | 42.1 % | 1.77 | 4,600.00 | 2.09 | 531.58 | 1,350.00 |
| 2022 | 71 | 55,350.00 | 50.7 % | 2.13 | 7,300.00 | 2.89 | 779.58 | 3,050.00 |
| 2023 | 67 | 15,600.00 | 37.3 % | 1.27 | 10,500.00 | 0.90 | 232.84 | 5,100.00 |
| 2024 | 68 | 19,750.00 | 41.2 % | 1.32 | 6,750.00 | 1.06 | 290.44 | 4,200.00 |
| combined | 225 | 100,800.00 | 43.1 % | 1.56 | 10,500.00 | 1.68 | 448.00 | 5,100.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 157 | 9,047.00 | 3.35 | 1.80 | 0.44 | 8,637.00 |
| pick | 68 | 2,383.00 | 1.28 | 1.40 | 0.41 | 173.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 11,664.50, mean -2,617.50, p95 -1,200.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 280 |
| beats_c1_pick | yes | lift 4,041.50, mean -1,658.50, p95 -1,330.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 118 |
| above_best_of_nulls_build | yes | t_build 3.35, bar 2.56, nulls 26, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 9,047.00 |
| net_pick | yes | net 2,383.00 |
| plateau_build | yes | cells 27, median_net 9,047.00, share_pos 1.00, member offB_pts5-r3 |
| beats_c1_build | yes | lift 11,664.50, mean -2,617.50, p95 -1,200.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 280 |
| stress_build | yes | base 9,047.00, stressed 8,637.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 4,041.50, mean -1,658.50, p95 -1,330.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 118 |
| stress_pick | yes | base 2,383.00, stressed 173.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 3.35, bar 2.56, nulls 26, thin NO |
| min_trades | yes | build 157, pick 68, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 51.00, micros_fit_worst 39, micros_fit_p99 55, limit 2,000.00 |
| rationale | yes | complexity 6 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

<!-- STAGE 3 RECORD -->
## Stage 3 record — event straddle `E1-B-NQ` (2026-10-04): ADMITTED, FLAGGED (checker: confirm or demote)
* **Rule in plain words:** On tier-1 release days only: at 08:29:59 ET a buy stop 5 points above and a sell stop 5 points below the NQ price (one cancels the other; cancelled after 5 minutes if unfilled); stop 5 points, target 15 points (1:3); flat by 15:58. One trade a day at most.
* **Event days it trades:** days with a tier-1 08:30 ET release (jobs report, CPI, PPI, retail sales, GDP or PCE; claims-only days are out). 159 such sessions on BUILD, 68 in 2024. Calendar: `engine/cache/events.csv` (official release schedules; never checked against prices).
* **Reason (written before any number):** a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way.
* **Second look:** YES — 2024 was already read for straddle_tight_0830 NQ on all days (stage 2b). 2024 is not a clean test for this member.
* BUILD tests: (a) 157 trades + 68 event days in 2024 · (b) 100 % of 27 variants positive, median $9,047 · (c) $58 a trade on event days vs -$5 on days without a release at that time (324 trades) · (d) t 3.35 vs bar 2.56 · (e) beats 99.90 % of 4,000 random same-size day subsets (needs 99.67 %).
* 2024: 81 % of 27 variants positive, median $2,838; this variant $2,383 (68 trades, rank 18 of 27); the same bracket at a random minute on the same days: -$1,658; on days without a release: $2 a trade.
* Per year (1 contract): 2021* $1,124 (19) · 2022 $5,961 (71) · 2023 $1,962 (67) · 2024 $2,383 (68) · combined $11,430 (225).
* At about $1,000 of risk a trade (100 micros): 2021* $10,100 (19) · 2022 $55,350 (71) · 2023 $15,600 (67) · 2024 $19,750 (68) · combined $100,800 (225); worst open loss on one trade $5,100. Worst open loss per micro $51: at most 39 micros inside $2,000.
* Stress (2 ticks + 250 ms): BUILD $9,047 -> $8,637; 2024 $2,383 -> $173.
* **Speed flag:** 149 of 225 trades open AND close inside 2 seconds and earn $9,904 of the $11,430; the median trade lasts 0.7 s. The profit is the simulator's fills inside the burst.

### Event types it trades (BUILD / 2024; a day with two releases is counted under both)
| release | BUILD trades | BUILD net | 2024 trades | 2024 net |
|---|---|---|---|---|
| jobs report (NFP) | 25 | $1,795 | 12 | -$268 |
| CPI | 27 | $1,747 | 12 | -$353 |
| PPI | 27 | $3,462 | 12 | $1,832 |
| retail sales | 27 | $2,257 | 12 | $537 |
| GDP | 28 | -$342 | 12 | -$143 |
| PCE | 27 | $1,312 | 10 | $495 |
| weekly jobless claims | 51 | $266 | 24 | $1,239 |

### Fill realism (information, not a gate): what if the stop entry fills later than the trigger print?
| entry filled | BUILD net (never better than the stop price) | 2024 net | BUILD net (that print + 1 tick) | 2024 net | mean slip past the stop, BUILD / 2024 |
|---|---|---|---|---|---|
| on the trigger print (engine) | $9,047 | $2,383 | $9,047 | $2,383 | 0.849 / 1.305 pts |
| 1 ms later | $4,977 | $1,173 | $7,962 | $2,608 | 3.041 / 3.375 pts |
| 5 ms later | $5,122 | $473 | $7,017 | $1,478 | 3.494 / 4.566 pts |
| 25 ms later | $3,237 | -$1,157 | $5,092 | $1,298 | 5.033 / 5.607 pts |
Own tick replay of the stored trades (it reproduces every engine trade to the cent at 0 ms). Median number of prints sharing the trigger print's timestamp: 3 (BUILD). Not FILL-FRAGILE by the written rule (positive at 5 ms in both periods).

| real account fills (desk journal, read-only) | fills | adverse slip past the stop price |
|---|---|---|
| NQ 09:30 straddle | 10 | mean 0.6 pt, median 0.375 pt, worst 1.75 pt |
| gold, jobs report 2026-10-02 | 1 | 0.0 |
| YM 09:30 | 2 | 4 and 5 pts |
Real fills sit near the engine's base fill (stop price + 1 tick) plus about one tick: far better than the 1 ms probe. None of them is an NQ or gold fill at an 08:30 / 10:00 release except the one gold jobs-report fill.

### Odds alone on a prop account (information; open losses count)
| account | fill model | size | micros | risk a trade | worst open loss | eval pass <= 10 days, any start | started the day before a tier-1 release | funded max payout <= 20 days |
|---|---|---|---|---|---|---|---|---|
| Lucid Flex 50K | trigger print | largest inside the drawdown | 39 | $390 | $1,989 | 7 % (bust 2 %) | 10 % | 1 % |
| Lucid Flex 50K | trigger print | about $1,000 risk | 40 | $400 | $2,040 | 7 % (bust 2 %) | 10 % | 1 % |
| Lucid Pro 50K (DLL) | trigger print | largest inside the drawdown | 39 | $390 | $1,989 | 7 % (bust 1 %) | 10 % | 8 % |
| Lucid Pro 50K (DLL) | trigger print | about $1,000 risk | 40 | $400 | $2,040 | 7 % (bust 1 %) | 10 % | 9 % |
| Lucid Pro 50K noDLL | trigger print | largest inside the drawdown | 39 | $390 | $1,989 | 7 % (bust 2 %) | 10 % | 8 % |
| Lucid Pro 50K noDLL | trigger print | about $1,000 risk | 40 | $400 | $2,040 | 7 % (bust 2 %) | 10 % | 9 % |
| Apex 50K | trigger print | largest inside the drawdown | 39 | $390 | $1,989 | 7 % (bust 2 %) | 10 % | 0 % |
| Apex 50K | trigger print | about $1,000 risk | 100 | $1,000 | $5,100 | 30 % (bust 40 %) | 36 % | 0 % |
| Lucid Flex 50K | 5 ms later | largest inside the drawdown | 40 | $400 | $1,620 | 4 % (bust 3 %) | 5 % | 0 % |
| Lucid Flex 50K | 5 ms later | about $1,000 risk | 40 | $400 | $1,620 | 4 % (bust 3 %) | 5 % | 0 % |
| Lucid Pro 50K (DLL) | 5 ms later | largest inside the drawdown | 40 | $400 | $1,620 | 4 % (bust 2 %) | 5 % | 6 % |
| Lucid Pro 50K (DLL) | 5 ms later | about $1,000 risk | 40 | $400 | $1,620 | 4 % (bust 2 %) | 5 % | 6 % |
| Lucid Pro 50K noDLL | 5 ms later | largest inside the drawdown | 40 | $400 | $1,620 | 4 % (bust 3 %) | 5 % | 6 % |
| Lucid Pro 50K noDLL | 5 ms later | about $1,000 risk | 40 | $400 | $1,620 | 4 % (bust 3 %) | 5 % | 6 % |
| Apex 50K | 5 ms later | largest inside the drawdown | 49 | $490 | $1,984 | 5 % (bust 7 %) | 6 % | 0 % |
| Apex 50K | 5 ms later | about $1,000 risk | 100 | $1,000 | $4,050 | 22 % (bust 44 %) | 27 % | 0 % |
Information only. Bar: 60 % eval / 75 % funded. Sizes are cut to the contract limit (Lucid 40 micros, Apex 100), so on Lucid the two sizes are often the same. A two-sided bracket is not allowed on Apex. The 5 ms trades keep the same stop and target distances from the later fill.

### Flags
* The whole profit needs the stop entry to fill on (or within about a tick of) the trigger print. One real gold fill and ten real NQ 09:30 fills support that; no real fill at an NQ 08:30 or a gold 10:00 release exists yet. Paper / small-size forward fills on release days are the missing evidence.
* This is the variant the checker DEMOTED on all days (`members/_demoted/straddle_tight_0830_NQ_tf30_pre/`), now on tier-1 days only. Its t now clears the unchanged bar (3.35 vs 2.56; on all days 1.98). The second demotion reason still stands: the profit needs the fill on the trigger print, and 2024 survives the stress by $173 only.
* SAME IDEA as orb_NQ_tf1_pre (the 08:30 burst on NQ): same side on 77 % of shared days, daily correlation 0.36 on those days. One strategy for a stack, not two.
