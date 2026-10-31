# The stack (Amendment K's one rule; in-sample months only; nothing read from a test month)

21 stores passed S1-S6; 13 after S7; the stack takes 8 (S8), 9.01 in-sample trades a day in total.

| # | Idea | Store | Family | Bars | Box | Trades/day | Avg $ | Win | Break-even | Margin | Recent avg $ | Blocks + | Block t | Months + | Share of boxes + | Eligible versions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 7 | vh_i7_orbc_long_5_ny-NQ-tf5 | orb_confirm | 5m | or_min60_own1p5-r2 | 1.10 | 250 | 60.0 % | 51.6 % | +8.4 | 340 | 10/14 | 2.56 | 8/9 | 90 % | 13 |
| 2 | 17 | vh_i17_rvbrk_15_ny-NQ-tf15 | rvol_break | 15m | m1p5_own1-r2 | 0.57 | 218 | 48.2 % | 41.4 % | +6.8 | 294 | 11/14 | 3.35 | 9/9 | 87 % | 3 |
| 3 | 6 | vh_i6_g_disp_15_ny-NQ-tf15 | displace | 15m | k1_own2-r2 | 2.19 | 142 | 49.8 % | 46.2 % | +3.6 | 189 | 12/14 | 3.59 | 8/9 | 85 % | 16 |
| 4 | 6 | vh_i6_g_donch_15_ny-NQ-tf15 | donchian | 15m | n10_own1-r1p5 | 2.32 | 235 | 53.8 % | 47.1 % | +6.8 | 352 | 12/14 | 3.49 | 8/9 | 82 % | 19 |
| 5 | 12 | vh_i12_orbpb_15_ny-NQ-tf15 | orb_vwap_pb | 15m | or_min15_pts60-r2 | 0.55 | 176 | 43.7 % | 37.7 % | +6.0 | 181 | 10/14 | 3.33 | 9/9 | 81 % | 4 |
| 6 | 7 | vh_i7_orb_15_ny-NQ-tf15 | win_break | 15m | r_end0945_own2-r1p5 | 0.86 | 251 | 56.0 % | 50.7 % | +5.3 | 230 | 10/14 | 3.10 | 8/9 | 79 % | 7 |
| 7 | 27 | vh_i27_onrorb_15_ny-NQ-tf15 | onr_orb | 15m | adx_min10_own2-r2 | 0.40 | 414 | 59.8 % | 49.6 % | +10.3 | 479 | 11/14 | 3.74 | 8/9 | 77 % | 17 |
| 8 | 9 | vh_i9_noise_long_5_ny-NQ-tf5 | noise_band | 5m | k0p3_pts60-r2 | 1.02 | 102 | 46.9 % | 42.8 % | +4.1 | 50 | 9/14 | 2.19 | 8/9 | 76 % | 1 |

Not taken (passed S1-S7, after the stack filled):

- vh_i6_g_cbrk_15_ny-NQ-tf15 backrange_own1p5-r2: share 72 %, 4.16 a day, avg $112
- vh_i10_adx_tp_5_ny-NQ-tf5 g_lvl20_atr2-r2: share 71 %, 2.59 a day, avg $128
- vh_i2_tp_15_ny-NQ-tf15 x0p2_atr2-r1p5: share 68 %, 1.43 a day, avg $133
- vh_i11_touch_gx_5_ny-NQ-tf5 away160_pts60-r2: share 59 %, 1.41 a day, avg $117
- vh_i1_pb_5_ny-NQ-tf5 vwap_slope60_pts60-r2: share 54 %, 1.01 a day, avg $94
