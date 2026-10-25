# Tonight's new build-day runs (taught lane, 2026-10-20 00:30-00:50 ET)

NQ, 1 contract after costs ($4 RT + 1 tick), build days 2021-09-22..2025-06-30 (948 sessions). Taught cell = the sheet's own exit; "avg of 3" = the
taught cell and its two target neighbours (0.75x / 1.25x). Lines = the lane's 10 lines (P3.2, P3.3, 3.3-3.8, P4.1 reshuffle, P4.2 random).
Sheets: research/edge-library/taught/cl_*.json; results: ~/.homebase/taught/cl_*/result.json (`bp.py taught show <name>`).

| sheet | rule | trades | /day | avg (cell / avg of 3) | PF | Sharpe | months won | DD open | lines | beats random | per year 21*/22/23/24/25* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cl_fvg_oside_15_mid_r1_t2_gap0p1 | open-side FVG 15m, gap >= 0.1 ATR, middle-candle stop, 1R, 2 a day | 1,268 | 1.34 | $108 / $94 | 1.30 | 2.07 | 78 % | $15.1k | 10/10 | 100 % | 204 / 173 / -3 / 74 / 231 |
| cl_fvg_oside_15_mid_r1_t2 | same, any gap, 2 a day | 1,400 | 1.48 | $98 / $90 | 1.29 | 2.03 | 76 % | $18.4k | 10/10 | 100 % | 175 / 133 / -5 / 69 / 257 |
| cl_fvg_oside_15_mid_r1_t3 | same, 3 a day | 1,557 | 1.64 | $87 / $79 | 1.25 | 1.88 | 80 % | $19.6k | 10/10 | 100 % | 159 / 116 / -13 / 62 / 257 |
| cl_fvg_oside_15_mid_r1_nl | same, no cap (engine 20) | 1,575 | 1.66 | $86 / $80 | 1.25 | 1.88 | 78 % | $20.9k | 9/10 | 100 % | 159 / 114 / -12 / 58 / 257 |
| cl_fvg_oside_15_mid_r05_t2 | same, 0.5R (owner's taught target), 2 a day | 1,439 | 1.52 | $54 / $49 | 1.23 | 1.56 | 72 % | $13.5k | 10/10 | 100 % | 119 / 57 / -24 / 39 / 206 (win 70 %) |
| cl_fvg_oside_30_mid_r1_t2 | same on 30m bars | 704 | 0.74 | -$9 / -$16 | 0.98 | -0.11 | 46 % | $44.2k | 1/10 | -- | 30m FAILS |
| cl_fvg_oside_15_mid_r1_t2_newest / _midedge | pick / mode are NOT settings of fvg_oside (schema: min_gap, stop_atr, atr1): identical to _t2 | | | | | | | | | | duplicates |
| cl_disp15_ema_allday_k1p5 | 15m displacement follow, body >= 1.5 ATR, long only above EMA20 / short below, 10:00-15:00, 1 per pass (<=3/day), candle stop, 1R | 859 | 0.91 | $117 / $90 | 1.17 | 1.01 | 70 % | $28.9k | 8/10 (3.3 PF, 3.6 DD) | 99.8 % | 272 / 116 / 52 / 147 / 92 |
| cl_disp15_noema_allday_k1p5 | same without the EMA gate | 940 | 0.99 | $102 / $76 | 1.14 | 0.93 | 57 % | $28.8k | 7/10 | -- | 211 / 108 / 57 / 116 / 83 |
| cl_disp15_ema_allday_k2p0 | EMA gate, k 2.0 | 454 | 0.48 | $154 / $117 | 1.20 | 0.89 | 63 % | $32.8k | 7/10 | -- | 216 / 42 / 109 / 129 / 520 |
| cl_disp15_ema_allday_k1p0 | EMA gate, k 1.0 | 1,621 | 1.71 | $19 / $16 | 1.03 | 0.27 | 46 % | $33.0k | 2/10 | -- | k 1.0 all day FAILS |
| cl_disp15_noema_allday_k1p0 | no gate, k 1.0 | 1,784 | 1.88 | -$11 | 0.98 | -0.16 | 44 % | $48.0k | 1/10 | 62.7 % | FAILS |
| cl_disp5_allday_k1p5 | 5m displacement, k 1.5, candle stop, 1R, 1 per pass | 1,522 | 1.61 | -$15 / $5 | 0.97 | -0.26 | 52 % | $43.3k | 1/10 | 49.9 % | 5m FAILS |

## Status of the unseen days (2025-07-01 on) for these families -- the owner said: do not touch the OOS
- fvg_oside 15m: the SIBLING with a 3 x 1-minute-ATR stop had its 3:1 block walk-forward read on 2026-10-19 (1-a-day and no-cap sheets; all P6 lines passed
  for the no-cap sheet, 384 trades, $55/trade). The middle-candle-stop sheets were never walk-forwarded, but the family's unseen months are not fully blind.
  Its sibling fvg_odir had a single unseen read (2026-10-19, $49.5/trade at 1 NQ) and a 48-version walk-forward that FAILED (picks jumped between versions).
- displace 15m with the EMA gate: every tester and taught run was on build days only. Fully blind.
- nq_displace_nyam (pipeline, 5m displacement follow k1, 20-pt fixed stop, NO target, box k1_pts20-r0): $157 a trade, 937 trades (0.99/day), PF 1.45,
  Sharpe 1.52, beats 97.9 % of random on try 2; stopped at stage 6 only because flexind.py changed after its freeze. Unseen never read. Fully blind.
  Its map: 113 of 144 boxes profitable, 42 at the floor; median of the no-target cells strong. Trend follower, ~31 % wins; without its best 5 % of trades
  -$129k (fat-tail dependent).

## Lessons from these runs
1. The open-side FVG on 15m is stable to the cap (1, 2, 3, none: $86-$99 a trade), to the target (0.75R-1.25R all hold 9-10 lines) and gains from a
   minimum gap of 0.1 ATR ($108). It dies on 30m and on 5m (owner's earlier 5m runs lost): ONE bar size carries it (fragility flag).
   Every version loses a little in 2023 (-$1k to -$9k) and makes most in 2022 and 2025 H1.
2. The 15m displacement needs a big candle (k >= 1.5) to hold all day; k 1.0 holds only 10:00-11:00 ($219, 0.36/day) and drowns when the window is
   widened. The EMA20 side gate adds $15 a trade and 13 points of months won at k 1.5 (a filter that wins alone, by the build numbers).
3. 5-minute and 30-minute versions of both rules lose: the 15-minute bar is where both live.

## Batch 3: robustness of the two leaders (2026-10-20, finished 10:19 ET)
| sheet | change | trades | /day | avg (cell / avg of 3) | PF | Sharpe | months | DD open | lines | per year 21*/22/23/24/25* |
|---|---|---|---|---|---|---|---|---|---|---|
| cl_fvg_oside_15_mid_r1_t2_gap0p25 | open-side FVG, gap >= 0.25 ATR | 1,019 | 1.07 | $121 / $103 | 1.30 | 1.80 | 70 % | $15.0k | 10/10 | 240 / 165 / -4 / 73 / 375 |
| cl_fvg_oside_15_mid_r1_t2_gap0p1_es | same rule on ES | 1,242 | 1.31 | $4 / $8 | 1.02 | 0.13 | 48 % | $15.0k | 4/10 | ES FAILS |
| cl_fvg_oside_15_mid_r1_t2_gap0p1_gc | same rule on GC | 1,026 | 1.08 | -$19 | 0.89 | -0.73 | 39 % | $27.9k | 1/10 | GC FAILS |
| cl_disp15_ema_allday_k1p25 | displacement EMA20, k 1.25 | 1,194 | 1.26 | $55 / $49 | 1.08 | 0.62 | 61 % | $32.5k | 6/10 | 202 / 27 / 0 / 33 / 197 |
| cl_disp15_ema_allday_k1p75 | k 1.75 | 635 | 0.67 | $133 / $97 | 1.18 | 0.96 | 61 % | $35.7k | 6/10 | 208 / 57 / 67 / 182 / 278 |
| cl_disp15_ema50_allday_k1p5 | EMA50 gate | 157 | 0.17 | $139 | 1.20 | 0.50 | 49 % | $21.5k | 4/10 | EMA50 on intraday 15m bars barely fires |
| cl_disp15_ema_allday_k1p5_es | displacement on ES | 829 | 0.87 | -$27 | 0.94 | -0.40 | 41 % | $37.9k | 1/10 | ES FAILS |
| cl_disp15_ema_allday_k1p5_gc | displacement on GC | 413 | 0.44 | $1 | 1.00 | 0.01 | 44 % | $17.6k | 3/10 | GC FAILS |

Reading:
- Open-side FVG main setting min_gap 0 / 0.1 / 0.25 -> $98 / $108 / $121 a trade, 1.48 / 1.34 / 1.07 a day, all 10 of 10 lines: the knob ORDERS
  monotonically (bigger gap = bigger average, fewer trades), and the average of the three values is about $109. Not a lucky cell.
- Displacement k 1.0 / 1.25 / 1.5 / 1.75 / 2.0 -> $19 / $55 / $117 / $133 / $154 a trade: also monotone; k 1.5 is the smallest k that clears the floor.
- Both rules live on NQ only (ES and GC fail) and on 15-minute bars only (5m and 30m fail). NQ-only is the house pattern (every market but NQ
  fails almost everything); 15m-only is a fragility flag.
- Stack of the open-side FVG (gap 0.1, 2 a day) and the displacement (k 1.5, EMA20) on one account, 1 NQ each: 2.24 trades a day, $112 a trade,
  PF 1.22, Sharpe 1.71, net / closed-daily drawdown 8.0, months won 72 %, EVERY build year positive (2023 +$10.9k), daily correlation 0.40.
