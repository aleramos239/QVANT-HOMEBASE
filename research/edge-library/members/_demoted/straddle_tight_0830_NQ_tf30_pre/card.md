# straddle_tight_0830_NQ_tf30_pre — ADMITTED

* family `straddle_tight_0830` · root NQ · tf 30 · session pre · cell `offB_pts5-r3` · 1 contract, costs included
* inputs: `{"at": "08:29:59", "cancel_min": 5, "dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "flat": "09:30:00", "hold_to": "day", "max_tr": 1, "off": "B", "off_mode": "menu", "off_val": 0.5, "sess": "all", "shift_max": 90, "shift_seed": 0, "stop_mode": "pts", "stop_val": 5.0, "tf": "30", "tgt_r": 3.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** The first seconds after a scheduled time are one-way; a tight bracket catches the burst with a small stop (08:30 ET).
* Complexity count (rules + free parameters): 6
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** no (2025-26 was never read for this family)
* **Penalty (EDGE_SPEC C):** none
* Notes: N7 straddle_tight 08:30 ET: OCO stop entries at last price +/- off points (A / B / C: NQ 3 / 5 / 8, ES 0.75 / 1.25 / 2, GC 0.6 / 1 / 1.6), placed at 08:29:59, unfilled legs cancelled 5 min later, entries until 09:30; own exits: stop NQ 5 / 8 / 10 pts (ES 1.25 / 2 / 2.5, GC 1 / 1.6 / 2) x target 1:1 / 1:2 / 1:3; null = the same bracket at random minutes (shift_seed). Second chance of the old NQ 09:30 straddle. CARD: the bracket is live within a second of the event -> the 2 ticks + 250 ms stress is the real gate; FLAGGED ADMISSION: the best-of-random bar of this unit is THIN (8 random replicates: the round-1 random-minute / random-direction stores of NQ; bar 0.84). Its BUILD t is 1.98: above that bar, but BELOW the same bar with stage 1's random-minute straddles pooled in (2.56, 26 replicates) and below the random-entry bar of NQ bar families (2.02). Admitted by the rule written before any number was opened (out/admit_r1/judge_build.py); checker / orchestrator: confirm or demote to near miss.

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 27 | 27 | 0 | 0 | 8,954.00 | 100.0 % | yes | offB_pts5-r3 | 8,954.00 | 20,862.00 |
| pick | 27 | 27 | 0 | 0 | 6,005.00 | 81.5 % | yes | offC_pts5-r2 | 6,005.00 | 16,415.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 27 | 100.0 % | 8,954.00 | yes | yes | yes |
| stop: fixed | 27 | 27 | 100.0 % | 8,954.00 | yes | yes | yes |
| target: 1:1 | 9 | 9 | 100.0 % | 4,831.00 | yes | yes | yes |
| target: 1:2 | 9 | 9 | 100.0 % | 10,506.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 13,739.00 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 27 | 22 | 81.5 % | 6,005.00 | yes | yes | yes |
| stop: fixed | 27 | 22 | 81.5 % | 6,005.00 | yes | yes | yes |
| target: 1:1 | 9 | 4 | 44.4 % | -365.00 | NO | NO | NO |
| target: 1:2 | 9 | 9 | 100.0 % | 6,005.00 | yes | yes | yes |
| target: 1:3 | 9 | 9 | 100.0 % | 8,644.00 | yes | yes | yes |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 62 | 862.00 | 30.6 % | 1.18 | 1,105.00 | 1.09 | 13.90 | 129.00 |
| 2022 | 247 | 4,412.00 | 32.4 % | 1.23 | 2,971.00 | 1.45 | 17.86 | 299.00 |
| 2023 | 240 | 3,680.00 | 31.7 % | 1.20 | 1,326.00 | 1.23 | 15.33 | 504.00 |
| 2024 | 244 | 4,869.00 | 33.6 % | 1.25 | 2,288.00 | 1.57 | 19.95 | 414.00 |
| combined | 793 | 13,823.00 | 32.4 % | 1.22 | 2,971.00 | 1.39 | 17.43 | 504.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 100, min 100, max 100)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 62 | 4,900.00 | 30.6 % | 1.10 | 11,650.00 | 0.62 | 79.03 | 1,350.00 |
| 2022 | 247 | 29,300.00 | 32.4 % | 1.14 | 33,250.00 | 0.96 | 118.62 | 3,050.00 |
| 2023 | 240 | 22,400.00 | 31.7 % | 1.11 | 14,400.00 | 0.75 | 93.33 | 5,100.00 |
| 2024 | 244 | 34,050.00 | 33.6 % | 1.17 | 27,200.00 | 1.10 | 139.55 | 4,200.00 |
| combined | 793 | 90,650.00 | 32.4 % | 1.14 | 33,250.00 | 0.91 | 114.31 | 5,100.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 549 | 8,954.00 | 1.98 | 1.21 | 0.32 | 6,619.00 |
| pick | 244 | 4,869.00 | 1.57 | 1.25 | 0.34 | 769.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 14,732.50, mean -5,778.50, p95 -2,140.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 1003 |
| beats_c1_pick | yes | lift 10,577.50, mean -5,708.50, p95 -5,525.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 443 |
| above_best_of_nulls_build | yes | t_build 1.98, bar 0.84, nulls 8, thin yes |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 8,954.00 |
| net_pick | yes | net 4,869.00 |
| plateau_build | yes | cells 27, median_net 8,954.00, share_pos 1.00, member offB_pts5-r3 |
| beats_c1_build | yes | lift 14,732.50, mean -5,778.50, p95 -2,140.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 1003 |
| stress_build | yes | base 8,954.00, stressed 6,619.00, stress 2 ticks + 250 ms |
| beats_c1_pick | yes | lift 10,577.50, mean -5,708.50, p95 -5,525.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 443 |
| stress_pick | yes | base 4,869.00, stressed 769.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 1.98, bar 0.84, nulls 8, thin yes |
| min_trades | yes | build 549, pick 244, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 51.00, micros_fit_worst 39, micros_fit_p99 95, limit 2,000.00 |
| rationale | yes | complexity 6 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

## Surviving set (19 of 27 judged cells: net > 0 on BUILD and on PICK, and > 0 under 2 ticks + 250 ms in both)
Net per year at 1 contract, then combined; stressed net BUILD / PICK; the same trades at about $1,000 of risk (micros). Full metric set per variant per year: `surviving_set.csv`. One variant per account (same trades).
| variant | 2021* | 2022 | 2023 | 2024 | combined | trades | stressed BUILD / PICK | $1,000-risk net | $1,000-risk Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| `offA_pts10-r2` | 1,899 | 6,998 | 3,804 | 5,887 | 18,588 | 818 | 8,461 / 4,462 | 68,400 | 0.89 |
| `offA_pts10-r3` | 49 | 5,648 | 10,304 | 9,357 | 25,358 | 818 | 11,541 / 7,612 | 102,250 | 1.07 |
| `offA_pts5-r3` | -661 | 3,618 | 8,999 | 4,047 | 16,003 | 818 | 9,066 / 2,347 | 110,950 | 1.10 |
| `offA_pts8-r2` | -531 | 5,183 | 5,854 | 4,902 | 15,408 | 818 | 6,516 / 4,047 | 65,100 | 0.85 |
| `offA_pts8-r3` | -1,371 | 5,343 | 7,619 | 7,982 | 19,573 | 818 | 8,451 / 6,392 | 90,923 | 0.95 |
| `offB_pts10-r1` | 797 | 2,582 | 2,010 | 2,439 | 7,828 | 793 | 2,359 / 449 | 15,350 | 0.30 |
| `offB_pts10-r2` | -1,498 | 5,947 | 1,965 | 7,014 | 13,428 | 793 | 3,574 / 4,859 | 43,350 | 0.58 |
| `offB_pts10-r3` | -918 | 5,807 | 8,850 | 8,644 | 22,383 | 793 | 8,674 / 5,154 | 88,125 | 0.93 |
| `offB_pts5-r3` **(default)** | 862 | 4,412 | 3,680 | 4,869 | 13,823 | 793 | 6,619 / 769 | 90,650 | 0.91 |
| `offB_pts8-r2` | 1,147 | 4,262 | 5,275 | 8,309 | 18,993 | 793 | 7,429 / 6,329 | 88,257 | 1.16 |
| `offB_pts8-r3` | -183 | 7,947 | 9,625 | 10,094 | 27,483 | 793 | 15,239 / 7,659 | 140,895 | 1.47 |
| `offC_pts10-r1` | -1,563 | 1,699 | 7,576 | 10,675 | 18,387 | 687 | 5,692 / 7,970 | 71,325 | 1.49 |
| `offC_pts10-r2` | -1,818 | 6,259 | 14,201 | 16,415 | 35,057 | 687 | 14,292 / 14,605 | 154,675 | 2.15 |
| `offC_pts10-r3` | -1,233 | 4,829 | 17,266 | 13,840 | 34,702 | 687 | 17,752 / 12,295 | 152,900 | 1.69 |
| `offC_pts5-r2` | -348 | 2,409 | 3,346 | 6,005 | 11,412 | 687 | 2,652 / 4,350 | 72,900 | 0.98 |
| `offC_pts5-r3` | -168 | 5,104 | 4,456 | 6,070 | 15,462 | 687 | 5,007 / 4,800 | 113,400 | 1.21 |
| `offC_pts8-r1` | -733 | 3,174 | 2,911 | 6,025 | 11,377 | 687 | 1,272 / 4,840 | 44,981 | 0.93 |
| `offC_pts8-r2` | -1,123 | 4,994 | 8,296 | 9,940 | 22,107 | 687 | 9,027 / 9,200 | 111,507 | 1.56 |
| `offC_pts8-r3` | -503 | 6,589 | 14,461 | 10,980 | 31,527 | 687 | 17,212 / 9,425 | 169,911 | 1.87 |

Trades per day (default variant, BUILD + PICK): 0.96. BUILD and PICK are both selection data: forward proof is still needed.

## Flags and execution caution (Admit stage 2b, 2026-10-04) — read before using this member
* **FLAGGED, checker to confirm or demote.** The best-of-random bar it cleared is thin: 8 random replicates for NQ (6 tight brackets at random minutes, whose best variant never made money, and 2 random-direction late-day trades), bar 0.84. Its BUILD t is 1.98. With stage 1's random-minute straddles pooled in (26 replicates) the bar is 2.56, and the bar of NQ's bar-based families is 2.02: it would fail both.
* **Same idea as the member orb_NQ_tf1_pre** (a bracket around the 08:30 ET data burst). On the 614 days both enter in the 08:30 minute they take the same side on 80 %; daily net correlation 0.41; 74 % of this member's losing days are losing days of orb_NQ_tf1_pre (which loses on 58 % of days). In a stack the two count as ONE strategy, never two.
* **2024 was not a clean look for this idea:** the 08:30 burst on NQ had already been seen in 2024 for orb_NQ_tf1_pre (+$12,437) and for the wider 08:30 straddle on news days (stage 2a).
* **Where the profit comes from** (default variant, BUILD + 2024, 793 trades, $13,823): 78 % of entries are in the 08:30 minute, 38 % within 2 seconds of 08:30:00. By holding time: <= 2 s: 187 trades, $13,352 (49 % win) · 2-10 s: 115, -$2,835 · 10-60 s: 151, -$8,509 · 1-5 min: 191, -$2,709 · > 5 min: 149, $14,524. So the trades that open and close inside 2 seconds of a data release earn about as much as the whole net profit: the part of the simulation that is hardest to trust.
* **Stress** (2 ticks + 250 ms): BUILD $8,954 -> $6,619; 2024 $4,869 -> $769. 2024 survives by $769 only (about $3 a trade).
* **Sizing:** the stop is 5 points ($10 per micro), but the worst open loss on one trade was $51 per micro (the stop was jumped at a release). At about $1,000 of nominal risk (100 micros) that one trade is an open loss of $5,100: above a $2,000 limit. Inside $2,000: at most 39 micros (95 at the 99th percentile), i.e. about $390 of nominal risk a trade.
* By side: short $10,519 (429 trades), long $3,304 (364). News days (CPI, jobs report, Fed): 102 trades, $3,282 ($32 a trade); other days: 691 trades, $10,541 ($15 a trade). After a quiet day $4,837 (377 trades), after an active day $8,766 (396).
* The pre-market session cannot be run in the Strategy Tester; its proof is the engine's own tests. Forward paper trading is the real test.
