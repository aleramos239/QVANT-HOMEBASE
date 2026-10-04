# donchian_NQ_tf5_nyam_vol_lo — REJECTED

* family `donchian` · root NQ · tf 5 · session nyam · cell `n60_pts10-r0` · 1 contract, costs included
* inputs: `{"dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "hold_to": "day", "max_tr": 3, "n": 60, "sess": "nyam", "stop_mode": "pts", "stop_val": 10.0, "tf": "5", "tgt_r": 0.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** Trend continuation: a close beyond the prior n-bar channel traps the other side, whose stops feed a continuation move.
* Complexity count (rules + free parameters): 3
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** 2025-26 was already seen once for this family's old finalist (donchian-tf15): the EXAM is a SECOND look
* **Penalty (EDGE_SPEC C):** none
* Notes: C donchian: close beyond the prior n-bar channel -> market with it. 2025-26 was already seen once for this family's old finalist (donchian-tf15): the EXAM is a SECOND look; STAGE 2a FILTERED SIDE `vol_lo`: trades only days after a daily range at or below its own 20-day median (a quiet market). Why it should matter: After a quiet day (range at or below its 20-day median) the market is coiled: stops sit close to the range and a morning break of the channel has room to run; after a wide day much of the move is already done and breaks get faded. (This reason was written AFTER the BUILD split was seen; the tool itself was fixed before any number.) Labels use daily bars through the PRIOR day only (out/deepen/test_labels.py). DEFAULT MOVED: the BUILD central variant `n20_atr1p5-r1` is not in the surviving set (2024 net -4,715); `n60_pts10-r0` is the surviving variant closest to the BUILD median.
* **Failed:** beats_c1_build, beats_c1_pick, above_best_of_nulls_build

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 128 | 128 | 0 | 0 | 35,030.00 | 81.2 % | yes | n20_atr1p5-r1 | 34,460.00 | 112,565.00 |
| pick | 128 | 128 | 0 | 0 | 18,323.50 | 82.0 % | yes | n10_pct0p2-r1 | 18,451.00 | 53,546.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 128 | 104 | 81.2 % | 35,030.00 | yes | yes | yes |
| stop: ATR | 32 | 32 | 100.0 % | 66,890.00 | yes | yes | yes |
| stop: fixed | 64 | 50 | 78.1 % | 28,558.50 | yes | yes | NO |
| stop: percent | 32 | 22 | 68.8 % | 17,757.00 | yes | NO | NO |
| target: none | 32 | 32 | 100.0 % | 76,052.00 | yes | yes | yes |
| target: 1:1 | 32 | 22 | 68.8 % | 14,039.00 | yes | NO | NO |
| target: 1:2 | 32 | 24 | 75.0 % | 23,362.00 | yes | yes | NO |
| target: 1:3 | 32 | 26 | 81.2 % | 32,655.50 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 128 | 105 | 82.0 % | 18,323.50 | yes | yes | yes |
| stop: ATR | 32 | 29 | 90.6 % | 29,825.00 | yes | yes | yes |
| stop: fixed | 64 | 46 | 71.9 % | 10,645.50 | yes | yes | NO |
| stop: percent | 32 | 30 | 93.8 % | 18,194.00 | yes | yes | yes |
| target: none | 32 | 32 | 100.0 % | 28,281.00 | yes | yes | yes |
| target: 1:1 | 32 | 20 | 62.5 % | 4,439.50 | yes | NO | NO |
| target: 1:2 | 32 | 25 | 78.1 % | 19,414.50 | yes | yes | NO |
| target: 1:3 | 32 | 28 | 87.5 % | 23,793.50 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 45 | -4,990.00 | 4.4 % | 0.45 | 6,907.00 | -2.82 | -110.89 | 632.00 |
| 2022 | 197 | 40,242.00 | 10.2 % | 2.09 | 6,370.00 | 2.19 | 204.27 | 632.00 |
| 2023 | 178 | 348.00 | 9.6 % | 1.01 | 8,145.00 | 0.03 | 1.96 | 632.00 |
| 2024 | 186 | 6,431.00 | 5.9 % | 1.18 | 12,635.00 | 0.42 | 34.58 | 627.00 |
| combined | 606 | 42,031.00 | 8.3 % | 1.36 | 17,729.00 | 0.88 | 69.36 | 632.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 50, min 50, max 50)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 45 | -26,300.00 | 4.4 % | 0.43 | 35,525.00 | -2.95 | -584.44 | 3,250.00 |
| 2022 | 197 | 195,300.00 | 10.2 % | 2.02 | 33,350.00 | 2.13 | 991.37 | 3,250.00 |
| 2023 | 178 | -3,600.00 | 9.6 % | 0.98 | 42,075.00 | -0.07 | -20.22 | 3,250.00 |
| 2024 | 186 | 26,575.00 | 5.9 % | 1.14 | 65,425.00 | 0.35 | 142.88 | 3,225.00 |
| combined | 606 | 191,975.00 | 8.3 % | 1.32 | 92,425.00 | 0.80 | 316.79 | 3,250.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 420 | 35,600.00 | 1.65 | 1.45 | 0.09 | 13,184.00 |
| pick | 186 | 6,431.00 | 0.42 | 1.18 | 0.06 | 3,059.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | NO | lift -4,979.18, mean 40,579.18, p95 64,134.00, p_beat 0.36, fallback_share 0.00, short 0, pool_trades 9313 |
| beats_c1_pick | NO | lift -37,883.55, mean 44,314.55, p95 62,756.25, p_beat 0.00, fallback_share 0.00, short 0, pool_trades 621 |
| above_best_of_nulls_build | NO | t_build 1.65, bar 2.02, nulls 56, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 35,600.00 |
| net_pick | yes | net 6,431.00 |
| plateau_build | yes | cells 128, median_net 35,030.00, share_pos 0.81, member n20_atr1p5-r1 |
| beats_c1_build | NO | lift -4,979.18, mean 40,579.18, p95 64,134.00, p_beat 0.36, fallback_share 0.00, short 0, pool_trades 9313 |
| stress_build | yes | base 35,600.00, stressed 13,184.00, stress 2 ticks + 250 ms |
| beats_c1_pick | NO | lift -37,883.55, mean 44,314.55, p95 62,756.25, p_beat 0.00, fallback_share 0.00, short 0, pool_trades 621 |
| stress_pick | yes | base 6,431.00, stressed 3,059.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | NO | t_build 1.65, bar 2.02, nulls 56, thin NO |
| min_trades | yes | build 420, pick 186, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 22.50, micros_fit_worst 88, micros_fit_p99 93, limit 2,000.00 |
| rationale | yes | complexity 3 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

## Stage 2a record — side `vol_lo` (only days after a daily range at or below its own 20-day median (a quiet market))
* BUILD (side): 81 % of 128 variants positive, median 35,030; central variant `n20_atr1p5-r1` passed (a)-(e).
* 2024 (side): 82 % positive, median 18,324 -> the table PASSES; but the BUILD central variant made -4,715 in 2024 (lift over random entries -13,746).
* Surviving set: 84 of 128 variants are positive in both periods and under 2 ticks + 250 ms (`surviving_set.csv`); 46 of them have a BUILD t at or above the bar 2.02.
* library.admission on the BUILD central variant `n20_atr1p5-r1`: REJECT (net_pick, beats_c1_pick, stress_pick).
* library.admission on the rule-moved default `n60_pts10-r0`: REJECT (beats_c1_build, beats_c1_pick, above_best_of_nulls_build).
* Verdict: NOT ADMITTED (near miss; the orchestrator may rule on the surviving set).
