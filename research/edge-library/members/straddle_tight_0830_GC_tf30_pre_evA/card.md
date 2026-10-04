# straddle_tight_0830_GC_tf30_pre_evA — ADMITTED

* family `straddle_tight_0830` · root GC · tf 30 · session pre · cell `offA_pts1p6-r1` · 1 contract, costs included
* inputs: `{"at": "08:29:59", "cancel_min": 5, "dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "flat": "09:30:00", "hold_to": "day", "max_tr": 1, "off": "A", "off_mode": "menu", "off_val": 0.5, "sess": "all", "shift_max": 90, "shift_seed": 0, "stop_mode": "pts", "stop_val": 1.6, "tf": "30", "tgt_r": 1.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).
* Complexity count (rules + free parameters): 6
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** SECOND LOOK ON 2024: 2024 was already read for straddle_tight_0830 GC on all days (stage 2b) (and 2025+ was never read)
* **Penalty (EDGE_SPEC C):** none
* Notes: N7 straddle_tight 08:30 ET: OCO stop entries at last price +/- off points (A / B / C: NQ 3 / 5 / 8, ES 0.75 / 1.25 / 2, GC 0.6 / 1 / 1.6), placed at 08:29:59, unfilled legs cancelled 5 min later, entries until 09:30; own exits: stop NQ 5 / 8 / 10 pts (ES 1.25 / 2 / 2.5, GC 1 / 1.6 / 2) x target 1:1 / 1:2 / 1:3; null = the same bracket at random minutes (shift_seed). Second chance of the old NQ 09:30 straddle. CARD: the bracket is live within a second of the event -> the 2 ticks + 250 ms stress is the real gate; STAGE 3 EVENT FILTER `A`: trades only on days with an 08:30 ET US data release (jobs report, CPI, PPI, retail sales, GDP, PCE or weekly jobless claims) (226 such sessions on BUILD, 96 in 2024; calendar = engine/cache/events.csv, official release dates, never checked against prices). STAGE 3 reason (written before any event-split number): a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way. The control in both periods is the same bracket fired at a random minute (2 seeds) on the same days. This is the BUILD central variant (library.plateau on the filtered table); no other variant may replace it.

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 27 | 27 | 0 | 0 | 10,598.00 | 96.3 % | yes | offA_pts1p6-r1 | 10,598.00 | 16,974.00 |
| pick | 27 | 27 | 0 | 0 | 5,756.00 | 100.0 % | yes | offC_pts2-r2 | 5,756.00 | 10,986.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 26 | 96.3 % | 10,598.00 | yes | yes | yes |
| stop: fixed | 27 | 26 | 96.3 % | 10,598.00 | yes | yes | yes |
| target: 1:1 | 9 | 8 | 88.9 % | 7,638.00 | yes | yes | yes |
| target: 1:2 | 9 | 9 | 100.0 % | 11,308.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 13,348.00 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 27 | 100.0 % | 5,756.00 | yes | yes | yes |
| stop: fixed | 27 | 27 | 100.0 % | 5,756.00 | yes | yes | yes |
| target: 1:1 | 9 | 9 | 100.0 % | 3,966.00 | yes | yes | yes |
| target: 1:2 | 9 | 9 | 100.0 % | 5,756.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 7,706.00 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 27 | 902.00 | 63.0 % | 1.52 | 622.00 | 2.00 | 33.41 | 174.00 |
| 2022 | 100 | 4,660.00 | 67.0 % | 1.80 | 796.00 | 2.91 | 46.60 | 194.00 |
| 2023 | 96 | 5,036.00 | 68.8 % | 1.96 | 696.00 | 3.24 | 52.46 | 184.00 |
| 2024 | 96 | 5,496.00 | 70.8 % | 2.08 | 684.00 | 3.48 | 57.25 | 234.00 |
| combined | 319 | 16,094.00 | 68.3 % | 1.90 | 796.00 | 3.11 | 50.45 | 234.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 62, min 62, max 62)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 27 | 4,588.00 | 63.0 % | 1.41 | 4,340.00 | 1.65 | 169.93 | 1,116.00 |
| 2022 | 100 | 25,172.00 | 67.0 % | 1.68 | 5,456.00 | 2.55 | 251.72 | 1,240.00 |
| 2023 | 96 | 27,652.00 | 68.8 % | 1.82 | 4,464.00 | 2.89 | 288.04 | 1,178.00 |
| 2024 | 96 | 30,504.00 | 70.8 % | 1.93 | 4,650.00 | 3.14 | 317.75 | 1,488.00 |
| combined | 319 | 87,916.00 | 68.3 % | 1.77 | 5,456.00 | 2.76 | 275.60 | 1,488.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 223 | 10,598.00 | 4.55 | 1.83 | 0.67 | 6,358.00 |
| pick | 96 | 5,496.00 | 3.62 | 2.08 | 0.71 | 4,126.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 16,295.00, mean -5,697.00, p95 -1,922.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 416 |
| beats_c1_pick | yes | lift 9,988.00, mean -4,492.00, p95 -2,690.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 186 |
| above_best_of_nulls_build | yes | t_build 4.55, bar 1.63, nulls 26, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 10,598.00 |
| net_pick | yes | net 5,496.00 |
| plateau_build | yes | cells 27, median_net 10,598.00, share_pos 0.96, member offA_pts1p6-r1 |
| beats_c1_build | yes | lift 16,295.00, mean -5,697.00, p95 -1,922.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 416 |
| stress_build | yes | base 10,598.00, stressed 6,358.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 9,988.00, mean -4,492.00, p95 -2,690.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 186 |
| stress_pick | yes | base 5,496.00, stressed 4,126.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 4.55, bar 1.63, nulls 26, thin NO |
| min_trades | yes | build 223, pick 96, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 24.00, micros_fit_worst 83, micros_fit_p99 100, limit 2,000.00 |
| rationale | yes | complexity 6 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

<!-- STAGE 3 RECORD -->
## Stage 3 record — event straddle `E1-A-GC` (2026-10-04): ADMITTED, FLAGGED (checker: confirm or demote)
* **Rule in plain words:** On days with an 08:30 ET US data release: at 08:29:59 ET a buy stop 0.6 points above and a sell stop 0.6 points below the gold price (one cancels the other; an unfilled bracket is cancelled after 5 minutes); stop 1.6 points, target 1.6 points (1:1); flat by 15:58. One trade a day at most.
* **Event days it trades:** days with an 08:30 ET US data release (jobs report, CPI, PPI, retail sales, GDP, PCE or weekly jobless claims). 226 such sessions on BUILD, 96 in 2024. Calendar: `engine/cache/events.csv` (official release schedules; never checked against prices).
* **Reason (written before any number):** a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before catches it whichever way.
* **Second look:** YES — 2024 was already read for straddle_tight_0830 GC on all days (stage 2b). 2024 is not a clean test for this member.
* BUILD tests: (a) 223 trades + 96 event days in 2024 · (b) 96 % of 27 variants positive, median $10,598 · (c) $48 a trade on event days vs -$19 on days without a release at that time (339 trades) · (d) t 4.55 vs bar 1.63 · (e) beats 100.00 % of 4,000 random same-size day subsets (needs 99.67 %).
* 2024: 100 % of 27 variants positive, median $5,756; this variant $5,496 (96 trades, rank 15 of 27); the same bracket at a random minute on the same days: -$4,492; on days without a release: -$7 a trade.
* Per year (1 contract): 2021* $902 (27) · 2022 $4,660 (100) · 2023 $5,036 (96) · 2024 $5,496 (96) · combined $16,094 (319).
* At about $1,000 of risk a trade (62 micros): 2021* $4,588 (27) · 2022 $25,172 (100) · 2023 $27,652 (96) · 2024 $30,504 (96) · combined $87,916 (319); worst open loss on one trade $1,488. Worst open loss per micro $24: at most 83 micros inside $2,000.
* Stress (2 ticks + 250 ms): BUILD $10,598 -> $6,358; 2024 $5,496 -> $4,126.
* **Speed flag:** 166 of 319 trades open AND close inside 2 seconds and earn $13,746 of the $16,094; the median trade lasts 1.9 s. The profit is the simulator's fills inside the burst.

### Event types it trades (BUILD / 2024; a day with two releases is counted under both)
| release | BUILD trades | BUILD net | 2024 trades | 2024 net |
|---|---|---|---|---|
| jobs report (NFP) | 26 | $716 | 12 | $492 |
| CPI | 26 | $1,716 | 12 | $52 |
| PPI | 27 | $2,552 | 12 | $542 |
| retail sales | 26 | $1,416 | 12 | $1,212 |
| GDP | 28 | $1,718 | 12 | $222 |
| PCE | 27 | $572 | 10 | -$90 |
| weekly jobless claims | 118 | $5,198 | 52 | $3,052 |

### Fill realism (information, not a gate): what if the stop entry fills later than the trigger print?
| entry filled | BUILD net (never better than the stop price) | 2024 net | BUILD net (that print + 1 tick) | 2024 net | mean slip past the stop, BUILD / 2024 |
|---|---|---|---|---|---|
| on the trigger print (engine) | $10,598 | $5,496 | $10,598 | $5,496 | 0.122 / 0.21 pts |
| 1 ms later | -$1,382 | $426 | -$712 | $1,846 | 0.757 / 0.785 pts |
| 5 ms later | $1,278 | $596 | $1,618 | $2,026 | 0.753 / 0.9 pts |
| 25 ms later | $1,758 | -$1,524 | $2,758 | -$104 | 0.812 / 1.215 pts |
Own tick replay of the stored trades (it reproduces every engine trade to the cent at 0 ms). Median number of prints sharing the trigger print's timestamp: 5 (BUILD). Not FILL-FRAGILE by the written rule (positive at 5 ms in both periods).

| real account fills (desk journal, read-only) | fills | adverse slip past the stop price |
|---|---|---|
| NQ 09:30 straddle | 10 | mean 0.6 pt, median 0.375 pt, worst 1.75 pt |
| gold, jobs report 2026-10-02 | 1 | 0.0 |
| YM 09:30 | 2 | 4 and 5 pts |
Real fills sit near the engine's base fill (stop price + 1 tick) plus about one tick: far better than the 1 ms probe. None of them is an NQ or gold fill at an 08:30 / 10:00 release except the one gold jobs-report fill.

### Odds alone on a prop account (information; open losses count)
| account | fill model | size | micros | risk a trade | worst open loss | eval pass <= 10 days, any start | started the day before a tier-1 release | funded max payout <= 20 days |
|---|---|---|---|---|---|---|---|---|
| Lucid Flex 50K | trigger print | largest inside the drawdown | 40 | $640 | $960 | 3 % (bust 9 %) | 5 % | 0 % |
| Lucid Flex 50K | trigger print | about $1,000 risk | 40 | $640 | $960 | 3 % (bust 9 %) | 5 % | 0 % |
| Lucid Pro 50K (DLL) | trigger print | largest inside the drawdown | 40 | $640 | $960 | 3 % (bust 9 %) | 5 % | 7 % |
| Lucid Pro 50K (DLL) | trigger print | about $1,000 risk | 40 | $640 | $960 | 3 % (bust 9 %) | 5 % | 7 % |
| Lucid Pro 50K noDLL | trigger print | largest inside the drawdown | 40 | $640 | $960 | 3 % (bust 9 %) | 5 % | 7 % |
| Lucid Pro 50K noDLL | trigger print | about $1,000 risk | 40 | $640 | $960 | 3 % (bust 9 %) | 5 % | 7 % |
| Apex 50K | trigger print | largest inside the drawdown | 83 | $1,328 | $1,992 | 36 % (bust 30 %) | 38 % | 14 % |
| Apex 50K | trigger print | about $1,000 risk | 63 | $1,008 | $1,512 | 14 % (bust 23 %) | 18 % | 12 % |
| Lucid Flex 50K | 5 ms later | largest inside the drawdown | 40 | $640 | $1,680 | 1 % (bust 15 %) | 1 % | 0 % |
| Lucid Flex 50K | 5 ms later | about $1,000 risk | 40 | $640 | $1,680 | 1 % (bust 15 %) | 1 % | 0 % |
| Lucid Pro 50K (DLL) | 5 ms later | largest inside the drawdown | 40 | $640 | $1,680 | 1 % (bust 13 %) | 1 % | 1 % |
| Lucid Pro 50K (DLL) | 5 ms later | about $1,000 risk | 40 | $640 | $1,680 | 1 % (bust 13 %) | 1 % | 1 % |
| Lucid Pro 50K noDLL | 5 ms later | largest inside the drawdown | 40 | $640 | $1,680 | 1 % (bust 15 %) | 1 % | 1 % |
| Lucid Pro 50K noDLL | 5 ms later | about $1,000 risk | 40 | $640 | $1,680 | 1 % (bust 15 %) | 1 % | 1 % |
| Apex 50K | 5 ms later | largest inside the drawdown | 47 | $752 | $1,974 | 1 % (bust 21 %) | 1 % | 3 % |
| Apex 50K | 5 ms later | about $1,000 risk | 63 | $1,008 | $2,646 | 6 % (bust 47 %) | 6 % | 3 % |
Information only. Bar: 60 % eval / 75 % funded. Sizes are cut to the contract limit (Lucid 40 micros, Apex 100), so on Lucid the two sizes are often the same. A two-sided bracket is not allowed on Apex. The 5 ms trades keep the same stop and target distances from the later fill.

### The tier-1-only version (unit E1-B-GC): the same variant on a subset of these days — the SAME strategy, no folder of its own
* BUILD: 156 trades, $8,066, t 4.18; 100 % of variants positive; beats 100.00 % of random day subsets. 2024: $2,448 (68 trades); table 96 % positive. Per year: 2021* $644 (19) · 2022 $3,106 (71) · 2023 $4,316 (66) · 2024 $2,448 (68) · combined $10,514 (224).
* Stress: BUILD $4,746, 2024 $1,128. Entry 5 ms later: BUILD $966, 2024 $88. It passes every admission test too.

### Flags
* The whole profit needs the stop entry to fill on (or within about a tick of) the trigger print. One real gold fill and ten real NQ 09:30 fills support that; no real fill at an NQ 08:30 or a gold 10:00 release exists yet. Paper / small-size forward fills on release days are the missing evidence.
* Same 08:30 burst as the NQ member on another market: same side on 64 % of shared days, daily correlation 0.19. At 1 ms the BUILD net is negative, at 25 ms the 2024 net is negative: close to FILL-FRAGILE.
