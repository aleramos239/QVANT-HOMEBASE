# donchian_NQ_tf30_nyam — ADMITTED, FLAGGED (confirm or demote: see Notes)

* family `donchian` · root NQ · tf 30 · session nyam · cell `n10_pct0p2-r2` · 1 contract, costs included
* inputs: `{"dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "hold_to": "day", "max_tr": 3, "n": 10, "sess": "nyam", "stop_mode": "pct", "stop_val": 0.2, "tf": "30", "tgt_r": 2.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** Trend continuation: a close beyond the prior n-bar channel traps the other side, whose stops feed a continuation move.
* Complexity count (rules + free parameters): 3
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** 2025-26 was already seen once for this family's old finalist (donchian-tf15): the EXAM is a SECOND look
* **Penalty (EDGE_SPEC C):** none
* Notes: C donchian: close beyond the prior n-bar channel -> market with it. 2025-26 was already seen once for this family's old finalist (donchian-tf15): the EXAM is a SECOND look; DEFAULT MOVED: the BUILD central cell `n10_pts20-r2` is not in the surviving set; default = the surviving cell closest to the BUILD median (`n10_pct0p2-r2`); FLAGGED ADMISSION: the unit passed BUILD on its central cell `n10_pts20-r2` (t 2.19 > bar 2.02), but that cell's 2024 net under 2 ticks + 250 ms is negative, so the default moved to `n10_pct0p2-r2`, whose own BUILD t (1.65) is BELOW the best-of-nulls bar. Admitted by the Admit stage's pre-registered rule (progress.md 2026-10-04 04:33 ET, D / E); library.admission run on the moved default alone says REJECT. Checker / orchestrator: confirm or demote to near-miss.

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 64 | 128 | 64 | 0 | 28,874.50 | 95.3 % | yes | n10_pts20-r2 | 28,761.00 | 107,619.00 |
| pick | 63 | 128 | 64 | 1 | 11,147.00 | 90.5 % | yes | n10_pts30-r2 | 11,147.00 | 35,916.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 64 | 61 | 95.3 % | 28,874.50 | yes | yes | yes |
| stop: ATR | 16 | 16 | 100.0 % | 65,519.00 | yes | yes | yes |
| stop: fixed | 32 | 30 | 93.8 % | 23,538.00 | yes | yes | yes |
| stop: percent | 16 | 15 | 93.8 % | 9,593.00 | yes | yes | yes |
| target: none | 16 | 16 | 100.0 % | 49,300.50 | yes | yes | yes |
| target: 1:1 | 16 | 16 | 100.0 % | 6,170.50 | yes | yes | yes |
| target: 1:2 | 16 | 14 | 87.5 % | 26,244.50 | yes | yes | yes |
| target: 1:3 | 16 | 15 | 93.8 % | 37,813.00 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 63 | 57 | 90.5 % | 11,147.00 | yes | yes | yes |
| stop: ATR | 15 | 13 | 86.7 % | 15,576.00 | yes | yes | yes |
| stop: fixed | 32 | 30 | 93.8 % | 10,815.50 | yes | yes | yes |
| stop: percent | 16 | 14 | 87.5 % | 12,265.00 | yes | yes | yes |
| target: none | 16 | 15 | 93.8 % | 15,817.50 | yes | yes | yes |
| target: 1:1 | 16 | 13 | 81.2 % | 6,693.00 | yes | yes | yes |
| target: 1:2 | 16 | 15 | 93.8 % | 13,347.50 | yes | yes | yes |
| target: 1:3 | 15 | 14 | 93.3 % | 19,501.00 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 58 | 6,093.00 | 39.7 % | 1.27 | 4,066.00 | 1.53 | 105.05 | 1,263.00 |
| 2022 | 215 | 27,595.00 | 42.3 % | 1.43 | 7,467.00 | 2.26 | 128.35 | 1,188.00 |
| 2023 | 200 | -4,700.00 | 32.0 % | 0.94 | 9,562.00 | -0.39 | -23.50 | 1,278.00 |
| 2024 | 174 | 16,974.00 | 37.9 % | 1.20 | 8,650.00 | 1.13 | 97.55 | 1,713.00 |
| combined | 647 | 45,962.00 | 37.7 % | 1.18 | 10,150.00 | 1.06 | 71.04 | 1,713.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 17, min 11, max 23)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 58 | 9,382.00 | 39.7 % | 1.26 | 6,452.50 | 1.48 | 161.76 | 2,040.00 |
| 2022 | 215 | 52,479.00 | 42.3 % | 1.41 | 13,293.50 | 2.21 | 244.09 | 2,080.50 |
| 2023 | 200 | -13,093.00 | 32.0 % | 0.91 | 20,584.50 | -0.63 | -65.47 | 2,091.00 |
| 2024 | 174 | 18,639.50 | 37.9 % | 1.17 | 11,967.50 | 0.97 | 107.12 | 2,072.00 |
| combined | 647 | 67,407.50 | 37.7 % | 1.16 | 20,653.00 | 0.96 | 104.18 | 2,091.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 473 | 28,988.00 | 1.65 | 1.18 | 0.38 | 15,855.00 |
| pick | 174 | 16,974.00 | 1.13 | 1.20 | 0.38 | 9,364.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 8,784.28, mean 20,203.72, p95 33,146.00, p_beat 0.85, fallback_share 0.13, short 0, pool_trades 10791 |
| beats_c1_pick | yes | lift 5,975.55, mean 10,998.45, p95 25,355.00, p_beat 0.76, fallback_share 0.08, short 0, pool_trades 475 |
| above_best_of_nulls_build | NO | t_build 1.65, bar 2.02, nulls 56, thin NO |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 28,988.00 |
| net_pick | yes | net 16,974.00 |
| plateau_build | yes | cells 64, median_net 28,874.50, share_pos 0.95, member n10_pts20-r2 |
| beats_c1_build | yes | lift 8,784.28, mean 20,203.72, p95 33,146.00, p_beat 0.85, fallback_share 0.13, short 0, pool_trades 10791 |
| stress_build | yes | base 28,988.00, stressed 15,855.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 5,975.55, mean 10,998.45, p95 25,355.00, p_beat 0.76, fallback_share 0.08, short 0, pool_trades 475 |
| stress_pick | yes | base 16,974.00, stressed 9,364.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | NO | t_build 1.65, bar 2.02, nulls 56, thin NO |
| min_trades | yes | build 473, pick 174, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 90.00, micros_fit_worst 22, micros_fit_p99 23, limit 2,000.00 |
| rationale | yes | complexity 3 |
| bar_on_build_central_cell | yes | cell n10_pts20-r2, t_build 2.19, bar 2.02 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

## Surviving set (43 of 64 judged cells: net > 0 on BUILD and on PICK, and > 0 under 2 ticks + 250 ms in both)
Net per year at 1 contract, then combined; stressed net BUILD / PICK; the same trades at about $1,000 of risk (micros). Full metric set per variant per year: `surviving_set.csv`. One variant per account (same trades).
| variant | 2021* | 2022 | 2023 | 2024 | combined | trades | stressed BUILD / PICK | $1,000-risk net | $1,000-risk Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| `n10_atr1p5-r0` | 4,274 | 70,268 | 32,034 | 27,449 | 134,025 | 555 | 93,396 / 25,074 | 119,908 | 1.50 |
| `n10_atr1p5-r1` | -1,267 | 14,516 | 635 | 12,236 | 26,120 | 655 | 2,737 / 7,224 | 22,584 | 0.48 |
| `n10_atr1p5-r2` | 235 | 44,506 | 21,664 | 16,321 | 82,726 | 576 | 60,900 / 11,461 | 73,446 | 1.18 |
| `n10_atr1p5-r3` | 7,754 | 54,710 | 33,605 | 32,030 | 128,099 | 559 | 79,468 / 27,520 | 111,563 | 1.54 |
| `n10_atr3-r0` | 9,573 | 39,671 | 47,890 | 10,936 | 108,070 | 545 | 82,189 / 11,136 | 53,346 | 1.14 |
| `n10_atr3-r1` | 4,635 | 31,089 | 44,995 | 9,493 | 90,212 | 567 | 66,464 / 7,308 | 48,316 | 1.24 |
| `n10_atr3-r2` | 9,498 | 30,026 | 49,625 | 15,576 | 104,725 | 545 | 72,899 / 16,436 | 53,788 | 1.18 |
| `n10_atr3-r3` | 9,573 | 45,921 | 52,125 | 19,501 | 127,120 | 545 | 92,764 / 19,801 | 63,154 | 1.32 |
| `n10_pts10-r0` | -288 | 43,853 | -16,016 | 10,608 | 38,157 | 657 | 10,581 / 6,572 | 171,075 | 0.70 |
| `n10_pts20-r0` | 9,821 | 62,121 | -798 | 12,547 | 83,691 | 601 | 51,867 / 15,037 | 200,212 | 1.28 |
| `n10_pts20-r1` | 358 | 14,584 | 139 | 5,146 | 20,227 | 712 | 3,434 / 1,025 | 39,888 | 0.81 |
| `n10_pts20-r3` | 6,623 | 32,774 | -374 | 5,363 | 44,386 | 656 | 24,612 / 1,857 | 101,125 | 1.13 |
| `n10_pts30-r0` | 14,185 | 68,560 | 5,049 | 25,929 | 113,723 | 583 | 72,431 / 24,758 | 187,382 | 1.52 |
| `n10_pts30-r2` | 6,048 | 20,085 | 4,322 | 11,147 | 41,602 | 647 | 21,625 / 5,706 | 64,124 | 0.91 |
| `n10_pts30-r3` | 8,261 | 27,217 | 5,481 | 17,125 | 58,084 | 609 | 36,289 / 16,455 | 92,531 | 1.08 |
| `n10_pts45-r0` | 8,578 | 54,212 | 23,730 | 35,916 | 122,436 | 561 | 82,085 / 26,520 | 130,977 | 1.46 |
| `n10_pts45-r1` | -4,023 | 14,821 | 604 | 13,387 | 24,789 | 674 | 4,808 / 5,736 | 22,820 | 0.48 |
| `n10_pts45-r2` | 1,674 | 14,703 | 17,758 | 27,326 | 61,461 | 596 | 33,284 / 18,850 | 63,674 | 0.99 |
| `n10_pts45-r3` | 4,813 | 21,579 | 27,792 | 30,144 | 84,328 | 568 | 51,904 / 23,318 | 89,012 | 1.20 |
| `n10_pct0p1-r0` | 7,463 | 48,725 | -17,854 | 13,447 | 51,781 | 631 | 26,812 / 12,354 | 163,323 | 0.86 |
| `n10_pct0p2-r0` | 15,185 | 66,726 | -1,258 | 35,891 | 116,544 | 579 | 62,233 / 26,505 | 180,469 | 1.47 |
| `n10_pct0p2-r2` **(default)** | 6,093 | 27,595 | -4,700 | 16,974 | 45,962 | 647 | 15,855 / 9,364 | 67,408 | 0.96 |
| `n10_pct0p2-r3` | 10,586 | 34,210 | 1,755 | 24,174 | 70,725 | 605 | 28,149 / 17,832 | 105,504 | 1.26 |
| `n20_atr1p5-r0` | 6,129 | 57,300 | -2,866 | 18,188 | 78,751 | 276 | 57,868 / 17,063 | 49,293 | 1.05 |
| `n20_atr1p5-r1` | 6,754 | 12,045 | -4,196 | 6,103 | 20,706 | 276 | 14,113 / 5,923 | 11,191 | 0.37 |
| `n20_atr1p5-r2` | 10,924 | 47,710 | 2,814 | 20,868 | 82,316 | 276 | 59,618 / 16,158 | 58,896 | 1.41 |
| `n20_atr1p5-r3` | 6,169 | 54,810 | -426 | 19,678 | 80,231 | 276 | 58,408 / 18,948 | 50,781 | 1.12 |
| `n20_pts10-r0` | -111 | 13,000 | -4,836 | 7,643 | 15,696 | 276 | 1,868 / 4,173 | 70,200 | 0.51 |
| `n20_pts20-r0` | 1,774 | 30,870 | -1,606 | 11,023 | 42,061 | 276 | 19,483 / 10,428 | 101,012 | 1.06 |
| `n20_pts20-r2` | -1,021 | 10,990 | 1,424 | 5,813 | 17,206 | 276 | 2,373 / 3,138 | 38,875 | 0.88 |
| `n20_pts20-r3` | 2,434 | 16,560 | 6,204 | 7,778 | 32,976 | 276 | 14,903 / 5,878 | 78,300 | 1.37 |
| `n20_pts30-r0` | 7,169 | 40,385 | -7,176 | 30,158 | 70,536 | 276 | 32,553 / 29,348 | 117,096 | 1.47 |
| `n20_pts30-r2` | 7,464 | 15,015 | 869 | 15,548 | 38,896 | 276 | 19,098 / 15,313 | 63,308 | 1.39 |
| `n20_pts30-r3` | 9,529 | 22,810 | 4,264 | 25,358 | 61,961 | 276 | 32,878 / 25,063 | 102,518 | 1.77 |
| `n20_pts45-r0` | 4,209 | 29,390 | -3,831 | 28,153 | 57,921 | 276 | 27,213 / 27,163 | 61,892 | 1.08 |
| `n20_pts45-r2` | 6,569 | 12,330 | 4,829 | 23,103 | 46,831 | 276 | 22,843 / 22,788 | 49,692 | 1.16 |
| `n20_pts45-r3` | 6,644 | 20,385 | -4,836 | 26,978 | 49,171 | 276 | 20,493 / 26,433 | 52,266 | 1.06 |
| `n20_pct0p1-r0` | 829 | 13,020 | -1,606 | 9,073 | 21,316 | 276 | 9,128 / 12,468 | 67,800 | 0.61 |
| `n20_pct0p1-r3` | -736 | 4,340 | 1,809 | 5,078 | 10,491 | 276 | 708 / 6,278 | 27,250 | 0.50 |
| `n20_pct0p2-r0` | 6,719 | 36,715 | -6,771 | 28,413 | 65,076 | 276 | 30,663 / 27,508 | 101,640 | 1.31 |
| `n20_pct0p2-r1` | 1,624 | 6,890 | -7,101 | 11,083 | 12,496 | 276 | 943 / 10,908 | 16,747 | 0.56 |
| `n20_pct0p2-r2` | 7,614 | 12,775 | 1,009 | 21,903 | 43,301 | 276 | 15,548 / 21,628 | 62,656 | 1.40 |
| `n20_pct0p2-r3` | 8,629 | 20,305 | 3,359 | 25,143 | 57,436 | 276 | 26,543 / 24,723 | 88,248 | 1.58 |

Trades per day (default variant, BUILD + PICK): 0.78. BUILD and PICK are both selection data: forward proof is still needed.

## Why this admission is flagged (Admit stage, 2026-10-04)
1. Default moved: the BUILD central cell `n10_pts20-r2` (t 2.19 > bar 2.02) has a stressed 2024 net of -$2,113; the default `n10_pct0p2-r2` has BUILD t 1.65, below the bar: `library.admission` on it alone says REJECT (above_best_of_nulls_build).
2. Random entries with the same exit in the same session earned +$20,204 on BUILD and +$10,998 in 2024; the signal's lift is $8,784 / $5,976 and it beats 86 % / 76 % of 200 random draws.
3. Net by side over 2021-2024: long -$1,122, short +$47,084 (2022 +$25,393, 2024 +$21,288). 2023: -$4,700.
