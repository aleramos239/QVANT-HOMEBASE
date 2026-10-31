# The 3:1 blocks always test on January, May and September (2026-10-21, ~03:45 ET)

Found while checking why the opening-range picks (idea 7) lost on their test months after +$200 a trade in-sample. Not used to pick
anything. Old taught stores on BUILD days (2021-09-22 .. 2025-06-30, every cell, months read long ago), Jan / May / Sep vs the rest:

| Store | Jan/May/Sep avg trade (n) | Other months (n) |
|---|---|---|
| cl_am_orb30_close15 (opening-range close break) | -$51.5 (486) | +$158.0 (1,485) |
| cl_disp15_noema_allday_k1p5 (15m displacement) | -$12.6 (696) | +$105.4 (2,124) |
| cl_disp15_ema_allday_k1p5 | +$45.9 (660) | +$105.0 (1,917) |
| hunt_dm_noise15_ny (noise band) | -$35.1 (3,564) | +$49.9 (11,583) |
| hunt_dm_hurst15_ny (trend break) | +$13.8 (555) | +$117.0 (1,910) |
| hunt_fv_cbreak15_ema1h_midpm (candle break) | +$45.2 (1,299) | +$73.7 (3,900) |
| conti_long_x020 (VWAP trend) | +$44.9 (3,802) | +$66.3 (11,273) |
| cl_pm_first_bar_cdl_15 (13:30 bar) | +$67.2 (699) | +$59.1 (2,091) |
| displace_ema15_1r_k1p5 | +$62.2 (546) | +$54.4 (1,713) |
| owner_vwap_pullback_25_38 | +$22.2 (2,890) | +$16.5 (8,709) |
| owner_fvg_oside_15_a1m3_nl_r1 | +$76.2 (1,226) | +$54.5 (3,724) |
| conti_onr_orb_e1000 / e1030 | +$373.6 / +$525.6 | +$385.8 / +$436.4 |

Breakout / trend rules on NQ made much less (or lost) in exactly the calendar months the blocks always test. With 4 years x 3 months
it may be chance (2022's bear months weigh heavily) or real seasonality; either way the fixed block layout tests trend rules on their
worst months every time, and the in-sample months overstate them. Options (the owner's call): judge trend rules also on a SHIFTED block
layout (blocks starting a month later, so every calendar month is a test month in one of the layouts), or the 3:1 rolling layout he
already allows on request. Not done without his word.
