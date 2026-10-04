# straddle_t_0830_NQ_tf30_pre_news_only — REJECTED

* family `straddle_t_0830` · root NQ · tf 30 · session pre · cell `offatr0p25_pct0p1-r2` · 1 contract, costs included
* inputs: `{"at": "08:30", "cancel_min": 60, "dir": "both", "exit_bars": 0, "f_book": "off", "f_depth": "off", "f_thin": "off", "f_trend": "off", "f_vwap": "off", "flat": "", "hold_to": "day", "max_tr": 1, "off": "atr0p25", "off_mode": "menu", "off_val": 0.5, "sess": "all", "shift_max": 90, "shift_seed": 0, "stop_mode": "pct", "stop_val": 0.1, "tf": "30", "tgt_r": 2.0, "trail_atr": 0.0, "x_book": "off"}`
* **Rationale (written before testing):** At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides whichever side breaks (08:30 ET: US data).
* Complexity count (rules + free parameters): 6
* Exits: stop / target of the cell, else flat at 15:58 ET of the trade date (13:13 on a half day); entries inside the session window only (hold_to = day)
* **WEAK:** no
* **Second look:** no (2025-26 was never read for this family)
* **Penalty (EDGE_SPEC C):** none
* Notes: A straddle_t 08:30 ET (US data): OCO stop entries at last price +/- offset, cancel unfilled after 60 min (entries live 55 min here: the Template cancels them 5 min before the flat time), flat 09:30, 1 trade per day; CARD: the bracket goes live 85 ms after a data release -> the 2 ticks + 250 ms stress is the gate; STAGE 2a FILTERED SIDE `news_only`: trades only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision (72 such days on BUILD, 32 in 2024). Why it should matter: the straddle is a bet on a burst at 08:30 ET; a CPI or jobs report is the scheduled burst (a Fed day has no 08:30 release and is in the split only because the pre-registered tool says so). SAME IDEA as the member orb_NQ_tf1_pre (a straddle of the 08:30 ET data burst): the two never count as two members of a stack. This is the BUILD central variant; by the orchestrator's ruling no other variant may replace it. beats_c1_pick: the random-minute control was NOT RUN on 2024 (the ruling asked for the menu only); it is listed as failed only because library.admission fails closed. The control on BUILD is the same straddle fired at a random minute (2 seeds), news days only.
* **Failed:** net_pick, beats_c1_pick, stress_pick

## Plateau (judged over the unit's parameter x exit cells: identical trade lists once, dead cells left out; the member is the CENTRAL cell, never the best)
| period | judged cells | of | dead | duplicates | median net | share > 0 | pass | member cell | member net | best cell net |
|---|---|---|---|---|---|---|---|---|---|---|
| build | 160 | 160 | 0 | 0 | 13,006.50 | 91.2 % | yes | offatr0p25_pct0p1-r2 | 12,951.00 | 30,521.00 |
| pick | 160 | 160 | 0 | 0 | 1,448.50 | 63.7 % | yes | offatr0p25_atr1p5-r2 | 1,466.00 | 31,701.00 |

### Share of cells with net > 0 — build (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 160 | 146 | 91.2 % | 13,006.50 | yes | yes | yes |
| stop: ATR | 40 | 26 | 65.0 % | 6,523.00 | yes | NO | NO |
| stop: fixed | 80 | 80 | 100.0 % | 15,899.00 | yes | yes | yes |
| stop: percent | 40 | 40 | 100.0 % | 12,469.50 | yes | yes | yes |
| target: none | 40 | 35 | 87.5 % | 16,841.50 | yes | yes | yes |
| target: 1:1 | 40 | 37 | 92.5 % | 7,369.50 | yes | yes | yes |
| target: 1:2 | 40 | 35 | 87.5 % | 11,816.50 | yes | yes | yes |
| target: 1:3 | 40 | 39 | 97.5 % | 14,541.50 | yes | yes | yes |

### Share of cells with net > 0 — pick (verdict = median > 0 and share >= the bar; the binding bar is 60 %)
| cells | n | > 0 | share > 0 | median net | pass 60 % | pass 70 % | pass 80 % |
|---|---|---|---|---|---|---|---|
| all judged cells | 160 | 102 | 63.7 % | 1,448.50 | yes | NO | NO |
| stop: ATR | 40 | 19 | 47.5 % | -314.00 | NO | NO | NO |
| stop: fixed | 80 | 54 | 67.5 % | 1,448.50 | yes | NO | NO |
| stop: percent | 40 | 29 | 72.5 % | 2,073.50 | yes | yes | NO |
| target: none | 40 | 40 | 100.0 % | 21,898.50 | yes | yes | yes |
| target: 1:1 | 40 | 18 | 45.0 % | -364.00 | NO | NO | NO |
| target: 1:2 | 40 | 20 | 50.0 % | -24.00 | NO | NO | NO |
| target: 1:3 | 40 | 24 | 60.0 % | 863.50 | yes | NO | NO |

## Per year, then combined (the member cell)
### 1 contract, costs included (* = partial year)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 9 | -46.00 | 33.3 % | 0.98 | 1,625.00 | -0.06 | -5.11 | 334.00 |
| 2022 | 31 | 7,896.00 | 67.7 % | 3.65 | 839.00 | 3.11 | 254.71 | 574.00 |
| 2023 | 31 | 5,101.00 | 54.8 % | 2.17 | 1,979.00 | 1.99 | 164.55 | 359.00 |
| 2024 | 31 | -1,129.00 | 32.3 % | 0.87 | 5,554.00 | -0.38 | -36.42 | 434.00 |
| combined | 102 | 11,822.00 | 50.0 % | 1.66 | 5,554.00 | 1.33 | 115.90 | 574.00 |

### sized to about $1,000 of risk per trade in micros (micros per trade: median 33, min 22, max 47)
| period | trades | net | win rate | PF | max drawdown | Sharpe (daily, ann.) | avg trade | worst open loss |
|---|---|---|---|---|---|---|---|---|
| 2021* | 9 | -439.50 | 33.3 % | 0.93 | 5,323.00 | -0.19 | -48.83 | 1,105.50 |
| 2022 | 31 | 28,886.50 | 67.7 % | 3.36 | 3,535.50 | 2.98 | 931.82 | 2,436.00 |
| 2023 | 31 | 17,908.00 | 54.8 % | 2.17 | 6,485.00 | 2.00 | 577.68 | 1,292.50 |
| 2024 | 31 | -2,584.50 | 32.3 % | 0.88 | 13,986.50 | -0.33 | -83.37 | 1,161.00 |
| combined | 102 | 43,770.50 | 50.0 % | 1.78 | 13,986.50 | 1.51 | 429.12 | 2,436.00 |

## Periods (the member cell)
| period | trades | net | t | PF | win | stressed net (2 ticks + 250 ms) |
|---|---|---|---|---|---|---|
| build | 71 | 12,951.00 | 3.59 | 2.39 | 0.58 | 11,476.00 |
| pick | 31 | -1,129.00 | -0.37 | 0.87 | 0.32 | -2,349.00 |

## Nulls
| test | pass | detail |
|---|---|---|
| beats_c1_build | yes | lift 16,332.50, mean -3,381.50, p95 -3,224.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 142 |
| beats_c1_pick | NO |  |
| above_best_of_nulls_build | yes | t_build 3.59, bar 2.62, nulls 18, thin yes |

## Every admission test
| test | pass | detail |
|---|---|---|
| net_build | yes | net 12,951.00 |
| net_pick | NO | net -1,129.00 |
| plateau_build | yes | cells 160, median_net 13,006.50, share_pos 0.91, member offatr0p25_pct0p1-r2 |
| beats_c1_build | yes | lift 16,332.50, mean -3,381.50, p95 -3,224.00, p_beat 1.00, fallback_share 0.00, short 0, pool_trades 142 |
| stress_build | yes | base 12,951.00, stressed 11,476.00, stress 2 ticks + 250 ms |
| beats_c1_pick | NO |  |
| stress_pick | NO | base -1,129.00, stressed -2,349.00, stress 2 ticks + 250 ms |
| above_best_of_nulls_build | yes | t_build 3.59, bar 2.62, nulls 18, thin yes |
| min_trades | yes | build 71, pick 31, need 100 |
| open_loss_fits | yes | worst_open_loss_per_micro 58.00, micros_fit_worst 34, micros_fit_p99 45, limit 2,000.00 |
| rationale | yes | complexity 6 |

EXAM (>= 2025-01-01) was not read. Sizing (micros) is chosen later by the account-rules layer.

## Stage 2a record — side `news_only` (only days with an 08:30 ET CPI or jobs (NFP) release or a Fed (FOMC) decision), opened on 2024 by the orchestrator's ruling of 2026-10-04
* SAME IDEA as the member orb_NQ_tf1_pre (a straddle of the 08:30 ET data burst): the two never count as two members of a stack.
* BUILD (news days): 91 % of 160 variants positive, median 13,006; central variant `offatr0p25_pct0p1-r2`: 71 trades, 12,951, t 3.59 (bar 2.62).
* 2024 (news days): 63.7 % of 160 variants positive, median 1,448 -> the table PASSES (at 60 % only). The BUILD central variant: 31 trades, -1,129.
* Trades BUILD + 2024: 102 (100 needed).
* Per year (1 contract): 2021* -46 (9 trades) · 2022 7,896 (31 trades) · 2023 5,101 (31 trades) · 2024 -1,129 (31 trades) · combined 11,822 (102 trades).
* Stress (2 ticks + 250 ms), central variant: BUILD 12,951 -> 11,476; 2024 -1,129 -> -2,349.
* Surviving set: 86 of 160 variants are positive in both periods and under stress (`surviving_set.csv`); the BUILD central variant is not one of them, and by the ruling no other variant may take its place.
* Verdict: NOT ADMITTED: the BUILD central variant loses money in 2024 (and under stress there).
