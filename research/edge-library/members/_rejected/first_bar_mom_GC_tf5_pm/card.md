# first_bar_mom_GC_tf5_pm — REJECTED

* family `first_bar_mom` · root GC · tf 5 · session pm · cell `k2_pts3-r1` · 1 contract, costs included
* inputs: `{"dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "hold_to": "day", "k": 2.0, "max_tr": 3, "sess": "pm", "stop_mode": "pts", "stop_val": 3.0, "tf": "5", "tgt_r": 1.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** A session's first tf bar with range >= k x ATR (ATR before that bar) is momentum ignition; follow its direction at its close.
* Complexity count (rules + free parameters): 3
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** SECOND LOOK: 2025-26 was already read once for this family's old finalists (NQ tf 15; ES tf 30); the EXAM is not a first look for it -- its real proof is forward paper / shadow trading
* **Penalty (EDGE_SPEC C):** in-sample favourite (first_bar_mom tf15 nyam) FAILED on 2025-26: needs the plateau on BUILD and PICK and a reason why the failure was noise — needs the plateau on BUILD and PICK
* Notes: C (R 20): the session's first tf bar has range >= k x ATR -> market in its direction at its close; struct stop = the bar's other extreme. 2025-26 was already read once for this family's old finalists (R / RE jobs.jsonl stage holdout): EXAM = a SECOND look; DEFAULT MOVED: the BUILD central cell `k2_pct0p1-r1` is not in the surviving set; default = the surviving cell closest to the BUILD median (`k2_pts3-r1`)
* **Failed:** min_trades

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 95 | 96 | 0 | 1 | 1,362.00 | 61.1 % | yes | k2_pct0p1-r1 | 1,362.00 | 6,940.00 |
| pick | 72 | 96 | 0 | 24 | 461.00 | 63.9 % | yes | k1p5_pts2-r2 | 426.00 | 10,018.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 95 | 58 | 61.1 % | 1,362.00 | yes | NO | NO |
| stop: ATR | 24 | 14 | 58.3 % | 1,182.00 | NO | NO | NO |
| stop: fixed | 47 | 30 | 63.8 % | 1,412.00 | yes | NO | NO |
| stop: percent | 24 | 14 | 58.3 % | 1,396.00 | NO | NO | NO |
| target: none | 24 | 16 | 66.7 % | 4,176.00 | yes | NO | NO |
| target: 1:1 | 24 | 13 | 54.2 % | 235.00 | NO | NO | NO |
| target: 1:2 | 24 | 14 | 58.3 % | 1,140.00 | NO | NO | NO |
| target: 1:3 | 23 | 15 | 65.2 % | 1,940.00 | yes | NO | NO |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 72 | 46 | 63.9 % | 461.00 | yes | NO | NO |
| stop: ATR | 19 | 7 | 36.8 % | -232.00 | NO | NO | NO |
| stop: fixed | 35 | 27 | 77.1 % | 826.00 | yes | yes | NO |
| stop: percent | 18 | 12 | 66.7 % | 602.00 | yes | NO | NO |
| target: none | 23 | 11 | 47.8 % | -54.00 | NO | NO | NO |
| target: 1:1 | 18 | 9 | 50.0 % | 47.00 | NO | NO | NO |
| target: 1:2 | 16 | 14 | 87.5 % | 677.00 | yes | yes | yes |
| target: 1:3 | 15 | 12 | 80.0 % | 676.00 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 1 | 296.00 | 100.0 % | n/a | 0.00 | 1.88 | 296.00 | 84.00 |
| 2022 | 5 | 870.00 | 80.0 % | 3.77 | 314.00 | 1.30 | 174.00 | 304.00 |
| 2023 | 6 | 246.00 | 50.0 % | 1.38 | 642.00 | 0.36 | 41.00 | 314.00 |
| 2024 | 3 | 108.00 | 66.7 % | 1.34 | 314.00 | 0.24 | 36.00 | 304.00 |
| combined | 15 | 1,520.00 | 66.7 % | 2.20 | 642.00 | 0.77 | 101.33 | 314.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 33, min 33, max 33)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 1 | 957.00 | 100.0 % | n/a | 0.00 | 1.88 | 957.00 | 297.00 |
| 2022 | 5 | 2,772.00 | 80.0 % | 3.62 | 1,056.00 | 1.27 | 554.40 | 1,023.00 |
| 2023 | 6 | 693.00 | 50.0 % | 1.32 | 2,178.00 | 0.31 | 115.50 | 1,056.00 |
| 2024 | 3 | 297.00 | 66.7 % | 1.28 | 1,056.00 | 0.20 | 99.00 | 1,023.00 |
| combined | 15 | 4,719.00 | 66.7 % | 2.10 | 2,178.00 | 0.73 | 314.60 | 1,056.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 12 | 1,412.00 | 1.48 | 2.48 | 0.67 | 1,382.00 |
| pick | 3 | 108.00 | 0.20 | 1.34 | 0.67 | 78.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 1,728.25, mean -316.25, p95 1,062.00, p_beat 0.99, fallback_share 0.00, short 0, pool_trades 18894 |
| beats_c1_pick | yes | lift 393.00, mean -285.00, p95 458.00, p_beat 0.72, fallback_share 0.00, short 0, pool_trades 1137 |
| above_best_of_nulls_build | yes | t_build 1.48, bar 1.24, nulls 56, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 1,412.00 |
| net_pick | yes | net 108.00 |
| plateau_build | yes | cells 95, median_net 1,362.00, share_pos 0.61, member k2_pct0p1-r1 |
| plateau_pick | yes | penalty in-sample favourite (first_bar_mom tf15 nyam) FAILED on 2025-26: needs the plateau on BUILD and PICK and a reason why the failure was noise, cells 72, median_net 461.00, share_pos 0.64 |
| beats_c1_build | yes | lift 1,728.25, mean -316.25, p95 1,062.00, p_beat 0.99, fallback_share 0.00, short 0, pool_trades 18894 |
| stress_build | yes | base 1,412.00, stressed 1,382.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 393.00, mean -285.00, p95 458.00, p_beat 0.72, fallback_share 0.00, short 0, pool_trades 1137 |
| stress_pick | yes | base 108.00, stressed 78.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 1.48, bar 1.24, nulls 56, thin NO |
| min_trades | NO | build 12, pick 3, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 32.00, micros_fit_worst 62, micros_fit_p99 62, limit 2,000.00 |
| rationale | yes | complexity 3 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

## Surviving set (12 of 95 judged cells: net > 0 on BUILD and on PICK, and > 0 under 2 ticks + 250 ms in both)
Net per year at 1 contract, then combined; stressed net BUILD / PICK; the same trades at about $1,000 of risk (micros). Full metric set per variant per year: `surviving_set.csv`. One variant per account (same trades).
| variant | 2021* | 2022 | 2023 | 2024 | combined | trades | stressed BUILD / PICK | $1,000-risk net | $1,000-risk Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| `k1p5_pts3-r0` | 1,054 | 2,124 | -188 | 1,106 | 4,096 | 61 | 2,170 / 936 | 12,309 | 0.48 |
| `k1p5_pts3-r2` | 1,054 | 444 | -338 | 826 | 1,986 | 61 | 550 / 706 | 5,346 | 0.31 |
| `k1p5_pts3-r3` | 1,054 | 144 | -348 | 556 | 1,406 | 61 | 180 / 396 | 3,432 | 0.18 |
| `k1p5_pts5-r0` | 1,054 | 1,844 | 1,682 | 826 | 5,406 | 61 | 3,670 / 646 | 10,080 | 0.54 |
| `k1p5_pts5-r1` | 1,084 | 884 | -698 | 2,266 | 3,536 | 61 | 660 / 2,156 | 6,340 | 0.58 |
| `k1p5_pts5-r2` | 1,054 | -226 | 292 | 376 | 1,496 | 61 | 360 / 206 | 2,260 | 0.16 |
| `k1p5_pts5-r3` | 1,054 | 1,274 | 1,802 | 876 | 5,006 | 61 | 3,350 / 706 | 9,280 | 0.53 |
| `k1p5_pts7-r0` | 1,054 | 3,384 | 1,282 | 216 | 5,936 | 61 | 4,750 / 36 | 7,798 | 0.58 |
| `k1p5_pts7-r3` | 1,054 | 3,494 | 852 | 216 | 5,616 | 61 | 4,470 / 36 | 7,350 | 0.56 |
| `k1p5_pct0p2-r0` | 1,054 | 2,664 | -968 | 886 | 3,636 | 61 | 1,280 / 706 | 9,661 | 0.46 |
| `k1p5_pct0p2-r3` | 1,054 | 924 | -428 | 676 | 2,226 | 61 | 190 / 506 | 5,776 | 0.32 |
| `k2_pts3-r1` **(default)** | 296 | 870 | 246 | 108 | 1,520 | 15 | 1,382 / 78 | 4,719 | 0.73 |

Trades per day (default variant, BUILD + PICK): 0.02. BUILD and PICK are both selection data: forward proof is still needed.
