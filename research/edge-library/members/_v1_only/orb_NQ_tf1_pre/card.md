# orb_NQ_tf1_pre — ADMITTED

* family `orb` · root NQ · tf 1 · session pre · cell `or_min5_atr1p5-r2` · 1 contract, costs included
* inputs: `{"dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "hold_to": "day", "max_tr": 3, "or_min": "5", "sess": "pre", "stop_mode": "atr", "stop_val": 1.5, "tf": "1", "tgt_r": 2.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** Opening range = the first balance of the session: the first or_min minutes set the range the rest of the session resolves, so a break of either side traps the other side and carries.
* Complexity count (rules + free parameters): 3
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** 2025-26 was already seen once for this family's old finalist (orb-tf5): the EXAM is a SECOND look
* **Penalty (EDGE_SPEC C):** none
* Notes: C orb: at session start + or_min, OCO stop entries one tick beyond the opening range. 2025-26 was already seen once for this family's old finalist (orb-tf5): the EXAM is a SECOND look

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 96 | 96 | 0 | 0 | 16,117.50 | 71.9 % | yes | or_min5_atr1p5-r2 | 16,362.00 | 89,112.00 |
| pick | 96 | 96 | 0 | 0 | 5,254.50 | 63.5 % | yes | or_min5_atr1p5-r1 | 5,177.00 | 75,237.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 96 | 69 | 71.9 % | 16,117.50 | yes | yes | NO |
| stop: ATR | 24 | 12 | 50.0 % | 6,785.00 | NO | NO | NO |
| stop: fixed | 48 | 39 | 81.2 % | 19,487.50 | yes | yes | yes |
| stop: percent | 24 | 18 | 75.0 % | 13,765.00 | yes | yes | NO |
| target: none | 24 | 24 | 100.0 % | 47,102.50 | yes | yes | yes |
| target: 1:1 | 24 | 14 | 58.3 % | 1,975.00 | NO | NO | NO |
| target: 1:2 | 24 | 14 | 58.3 % | 8,762.50 | NO | NO | NO |
| target: 1:3 | 24 | 17 | 70.8 % | 18,148.00 | yes | yes | NO |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 96 | 61 | 63.5 % | 5,254.50 | yes | NO | NO |
| stop: ATR | 24 | 16 | 66.7 % | 6,300.00 | yes | NO | NO |
| stop: fixed | 48 | 30 | 62.5 % | 4,648.00 | yes | NO | NO |
| stop: percent | 24 | 15 | 62.5 % | 4,262.50 | yes | NO | NO |
| target: none | 24 | 24 | 100.0 % | 32,021.50 | yes | yes | yes |
| target: 1:1 | 24 | 15 | 62.5 % | 2,061.50 | yes | NO | NO |
| target: 1:2 | 24 | 8 | 33.3 % | -4,401.50 | NO | NO | NO |
| target: 1:3 | 24 | 14 | 58.3 % | 1,148.50 | NO | NO | NO |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 70 | -840.00 | 31.4 % | 0.88 | 1,507.00 | -0.90 | -12.00 | 309.00 |
| 2022 | 248 | 9,878.00 | 41.5 % | 1.28 | 2,534.00 | 1.76 | 39.83 | 844.00 |
| 2023 | 249 | 7,324.00 | 40.6 % | 1.31 | 2,766.00 | 1.90 | 29.41 | 544.00 |
| 2024 | 252 | 12,437.00 | 44.8 % | 1.48 | 3,300.00 | 2.71 | 49.35 | 1,114.00 |
| combined | 819 | 28,799.00 | 41.4 % | 1.32 | 3,300.00 | 1.89 | 35.16 | 1,114.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 62, min 9, max 167)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 70 | -11,731.50 | 31.4 % | 0.78 | 16,307.50 | -1.84 | -167.59 | 1,240.00 |
| 2022 | 248 | 43,867.00 | 41.5 % | 1.28 | 8,830.50 | 1.86 | 176.88 | 1,200.00 |
| 2023 | 249 | 27,516.00 | 40.6 % | 1.16 | 22,885.50 | 1.16 | 110.51 | 1,430.00 |
| 2024 | 252 | 58,600.00 | 44.8 % | 1.37 | 14,063.50 | 2.39 | 232.54 | 3,332.00 |
| combined | 819 | 118,251.50 | 41.4 % | 1.22 | 22,885.50 | 1.51 | 144.39 | 3,332.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 567 | 16,362.00 | 2.32 | 1.25 | 0.40 | 8,462.00 |
| pick | 252 | 12,437.00 | 2.71 | 1.48 | 0.45 | 6,572.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 26,478.55, mean -10,116.55, p95 3,173.75, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 23681 |
| beats_c1_pick | yes | lift 17,611.67, mean -5,174.68, p95 2,648.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 1499 |
| above_best_of_nulls_build | yes | t_build 2.32, bar 2.02, nulls 56, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 16,362.00 |
| net_pick | yes | net 12,437.00 |
| plateau_build | yes | cells 96, median_net 16,117.50, share_pos 0.72, member or_min5_atr1p5-r2 |
| beats_c1_build | yes | lift 26,478.55, mean -10,116.55, p95 3,173.75, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 23681 |
| stress_build | yes | base 16,362.00, stressed 8,462.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 17,611.67, mean -5,174.68, p95 2,648.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 1499 |
| stress_pick | yes | base 12,437.00, stressed 6,572.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 2.32, bar 2.02, nulls 56, thin NO |
| min_trades | yes | build 567, pick 252, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 112.00, micros_fit_worst 17, micros_fit_p99 43, limit 2,000.00 |
| rationale | yes | complexity 3 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

## Surviving set (49 of 96 judged cells: net > 0 on BUILD and on PICK, and > 0 under 2 ticks + 250 ms in both)
Net per year at 1 contract, then combined; stressed net BUILD / PICK; the same trades at about $1,000 of risk (micros). Full metric set per variant per year: `surviving_set.csv`. One variant per account (same trades).
| variant | 2021* | 2022 | 2023 | 2024 | combined | trades | stressed BUILD / PICK | $1,000-risk net | $1,000-risk Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| `or_min5_atr1p5-r0` | -3,180 | 38,953 | 6,364 | 33,167 | 75,304 | 819 | 34,012 / 24,792 | 330,961 | 0.83 |
| `or_min5_atr1p5-r1` | 1,130 | 9,133 | 3,789 | 5,177 | 19,229 | 819 | 6,527 / 2,312 | 58,868 | 1.11 |
| `or_min5_atr1p5-r2` **(default)** | -840 | 9,878 | 7,324 | 12,437 | 28,799 | 819 | 8,462 / 6,572 | 118,252 | 1.51 |
| `or_min5_atr1p5-r3` | 265 | 10,358 | 12,199 | 13,782 | 36,604 | 819 | 11,122 / 10,397 | 136,068 | 1.39 |
| `or_min5_atr3-r0` | -2,560 | 80,158 | 11,514 | 58,272 | 147,384 | 819 | 90,867 / 47,902 | 366,743 | 1.42 |
| `or_min5_atr3-r1` | 530 | 13,838 | 10,619 | 10,412 | 35,399 | 819 | 17,577 / 4,587 | 68,110 | 1.31 |
| `or_min5_atr3-r2` | 3,830 | 24,893 | 17,184 | 13,357 | 59,264 | 819 | 35,677 / 6,567 | 117,826 | 1.54 |
| `or_min5_atr3-r3` | 6,635 | 15,598 | 14,589 | 22,572 | 59,394 | 819 | 29,822 / 14,432 | 142,648 | 1.49 |
| `or_min5_pts10-r0` | -2,000 | 35,193 | 14,894 | 41,212 | 89,299 | 819 | 40,177 / 28,492 | 421,925 | 1.20 |
| `or_min5_pts10-r1` | 2,785 | 6,933 | 4,944 | 5,402 | 20,064 | 819 | 7,682 / 912 | 75,750 | 1.44 |
| `or_min5_pts10-r2` | 2,290 | 13,698 | 5,179 | 8,597 | 29,764 | 819 | 12,287 / 2,027 | 124,250 | 1.59 |
| `or_min5_pts10-r3` | 1,445 | 12,108 | 12,229 | 11,477 | 37,259 | 819 | 12,872 / 5,522 | 161,725 | 1.64 |
| `or_min5_pts20-r0` | -9,970 | 64,008 | 6,769 | 53,217 | 114,024 | 819 | 54,537 / 40,517 | 272,775 | 1.19 |
| `or_min5_pts20-r2` | 275 | 15,068 | 1,334 | 12,827 | 29,504 | 819 | 7,372 / 2,142 | 61,475 | 0.81 |
| `or_min5_pts30-r0` | -11,545 | 71,973 | 15,589 | 75,237 | 151,254 | 819 | 60,632 / 75,767 | 248,778 | 1.35 |
| `or_min5_pts30-r1` | -2,865 | 15,133 | 8,564 | 12,617 | 33,449 | 819 | 6,132 / 2,237 | 48,510 | 0.91 |
| `or_min5_pts30-r3` | -4,150 | 26,648 | 19,684 | 12,217 | 54,399 | 819 | 30,367 / 8,807 | 84,124 | 0.88 |
| `or_min5_pts45-r0` | -3,570 | 53,978 | 23,294 | 60,952 | 134,654 | 819 | 70,032 / 67,972 | 142,714 | 1.08 |
| `or_min5_pts45-r1` | 1,335 | 9,698 | 5,869 | 7,312 | 24,214 | 819 | 12,357 / 6,697 | 21,230 | 0.41 |
| `or_min5_pts45-r2` | 705 | 18,558 | 19,479 | 14,752 | 53,494 | 819 | 31,852 / 19,347 | 53,438 | 0.73 |
| `or_min5_pts45-r3` | 2,525 | 7,833 | 46,954 | 30,252 | 87,564 | 819 | 51,862 / 35,297 | 90,915 | 1.01 |
| `or_min5_pct0p1-r0` | -7,290 | 64,308 | 6,089 | 54,552 | 117,659 | 819 | 52,307 / 44,262 | 369,046 | 1.29 |
| `or_min5_pct0p1-r2` | 35 | 11,023 | 1,404 | 12,997 | 25,459 | 819 | 2,412 / 6,277 | 71,708 | 0.94 |
| `or_min5_pct0p1-r3` | 2,525 | 11,948 | -1,381 | 7,012 | 20,104 | 819 | 3,907 / 2,617 | 57,046 | 0.61 |
| `or_min5_pct0p2-r0` | -15,820 | 53,308 | 19,039 | 75,047 | 131,574 | 819 | 43,432 / 83,002 | 192,852 | 1.11 |
| `or_min5_pct0p2-r1` | -3,085 | 11,313 | 7,309 | 15,082 | 30,619 | 819 | 2,847 / 13,657 | 42,496 | 0.82 |
| `or_min5_pct0p2-r2` | -1,345 | 19,263 | 6,164 | 5,332 | 29,414 | 819 | 11,902 / 7,427 | 44,948 | 0.60 |
| `or_min5_pct0p2-r3` | -1,870 | 26,558 | 11,809 | 24,692 | 61,189 | 819 | 23,707 / 27,237 | 94,096 | 1.01 |
| `or_min15_atr1p5-r0` | 3,723 | 20,828 | 12,116 | 10,964 | 47,631 | 751 | 30,647 / 4,279 | 235,172 | 0.83 |
| `or_min15_atr3-r0` | -3,847 | 41,603 | 7,916 | 32,669 | 78,341 | 751 | 42,152 / 31,389 | 235,402 | 1.09 |
| `or_min15_pts10-r0` | 1,708 | 21,883 | 22,831 | 17,539 | 63,961 | 751 | 43,617 / 16,349 | 297,275 | 0.90 |
| `or_min15_pts20-r0` | -3,027 | 45,338 | 15,191 | 31,374 | 88,876 | 751 | 51,227 / 30,024 | 210,925 | 1.04 |
| `or_min15_pts30-r0` | -9,007 | 80,313 | 5,681 | 21,794 | 98,781 | 751 | 73,917 / 19,814 | 160,268 | 0.98 |
| `or_min15_pts30-r1` | -4,067 | 11,738 | 8,161 | 2,699 | 18,531 | 751 | 9,772 / 2,154 | 23,842 | 0.47 |
| `or_min15_pts30-r3` | 1,868 | 37,988 | 7,646 | 3,894 | 51,396 | 751 | 45,627 / 2,394 | 79,713 | 0.88 |
| `or_min15_pts45-r0` | -8,817 | 84,908 | -1,514 | 13,374 | 87,951 | 751 | 71,382 / 2,444 | 91,790 | 0.76 |
| `or_min15_pct0p1-r0` | -872 | 15,793 | 23,571 | 35,934 | 74,426 | 751 | 35,642 / 28,219 | 192,472 | 0.82 |
| `or_min15_pct0p2-r0` | -10,782 | 45,458 | 2,101 | 13,289 | 50,066 | 751 | 33,802 / 11,864 | 80,784 | 0.54 |
| `or_min15_pct0p2-r3` | 1,708 | 17,388 | 1,106 | 1,124 | 21,326 | 751 | 18,317 / 179 | 26,838 | 0.31 |
| `or_min30_atr1p5-r0` | 4,150 | 18,813 | -5,130 | 12,753 | 30,586 | 606 | 14,368 / 11,813 | 154,208 | 0.57 |
| `or_min30_atr3-r0` | 7,185 | 22,683 | 5,375 | 36,228 | 71,471 | 606 | 29,603 / 35,173 | 164,012 | 0.91 |
| `or_min30_pts10-r0` | 3,915 | 14,253 | 805 | 12,698 | 31,671 | 606 | 12,063 / 11,728 | 140,175 | 0.56 |
| `or_min30_pts20-r0` | -5,630 | 11,843 | 23,435 | 19,898 | 49,546 | 606 | 27,238 / 13,913 | 114,775 | 0.70 |
| `or_min30_pts30-r0` | 2,875 | 36,508 | 15,485 | 36,553 | 91,421 | 606 | 52,343 / 35,458 | 149,234 | 1.06 |
| `or_min30_pts30-r1` | 8,675 | 4,763 | 2,435 | 6,633 | 22,506 | 606 | 14,888 / 4,998 | 32,079 | 0.70 |
| `or_min30_pts30-r3` | 5,090 | 2,048 | 12,675 | 768 | 20,581 | 606 | 18,218 / 63 | 28,806 | 0.36 |
| `or_min30_pts45-r0` | 1,125 | 29,548 | 10,730 | 25,358 | 66,761 | 606 | 38,753 / 14,713 | 69,438 | 0.68 |
| `or_min30_pct0p1-r0` | -1,915 | 9,128 | 7,225 | 27,103 | 41,541 | 606 | 6,468 / 19,668 | 102,395 | 0.52 |
| `or_min30_pct0p2-r0` | 1,515 | 26,488 | 19,780 | 20,733 | 68,516 | 606 | 45,283 / 19,613 | 105,932 | 0.79 |

Trades per day (default variant, BUILD + PICK): 0.99. BUILD and PICK are both selection data: forward proof is still needed.

## Execution caution (Admit stage, 2026-10-04)
76 % of entries are in the 08:30 ET minute. By holding time (BUILD + PICK, default variant): <= 2 s: 145 trades, net $18,020 (61 % win) · 2-10 s: 96, $4,301 · 10-60 s: 102, -$6,263 · 1-5 min: 198, -$5,072 · > 5 min: 278, $17,813. So 63 % of the profit comes from trades that open and close inside 2 seconds on data-release spikes: the part of the simulation that is hardest to trust (stop entry and target both filled within the placement latency window). Net by side: long $6,447, short $22,352. The 2 ticks + 250 ms stress halves the profit. Forward paper trading is the real test.
