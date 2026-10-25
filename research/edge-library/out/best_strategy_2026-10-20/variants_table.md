| variant | sheet | trades/day | avg trade | avg of its 3 targets | PF | win | Sharpe | months won | worst DD | lines held | $ a trade by year: 2021* · 22 · 23 · 24 · 25* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1. Open-side FVG, 15m (middle-candle stop, 1R)** | | | | | | | | | | | |
| 1 a day, any gap (the owner's sheet) | `owner_fvg_oside_15_mid_r1` | 0.94 | $99 | $92 | 1.27 | 54 % | 1.51 | 70 % | $19.8k | 10 of 10 | +169 · +137 · -28 · +87 · +272 |
| 2 a day, any gap | `cl_fvg_oside_15_mid_r1_t2` | 1.48 | $98 | $90 | 1.29 | 55 % | 2.03 | 76 % | $18.4k | 10 of 10 | +175 · +133 · -5 · +69 · +257 |
| 2 a day, gap >= 0.1 ATR  << PICK | `cl_fvg_oside_15_mid_r1_t2_gap0p1` | 1.34 | $108 | $94 | 1.30 | 56 % | 2.07 | 78 % | $15.1k | 10 of 10 | +204 · +173 · -3 · +74 · +231 |
| 2 a day, gap >= 0.25 ATR | `cl_fvg_oside_15_mid_r1_t2_gap0p25` | 1.07 | $121 | $103 | 1.30 | 56 % | 1.80 | 70 % | $15.0k | 10 of 10 | +240 · +165 · -4 · +73 · +375 |
| 3 a day, any gap | `cl_fvg_oside_15_mid_r1_t3` | 1.64 | $87 | $79 | 1.25 | 55 % | 1.88 | 80 % | $19.6k | 10 of 10 | +159 · +116 · -13 · +62 · +257 |
| no cap, any gap | `cl_fvg_oside_15_mid_r1_nl` | 1.66 | $86 | $80 | 1.25 | 55 % | 1.88 | 78 % | $20.9k | 9 of 10 | +159 · +114 · -12 · +58 · +257 |
| 2 a day, target 0.5R (high win rate) | `cl_fvg_oside_15_mid_r05_t2` | 1.52 | $54 | $49 | 1.23 | 70 % | 1.56 | 72 % | $13.5k | 10 of 10 | +119 · +57 · -24 · +39 · +206 |
| 2 a day, fixed 37-pt stop and target | `cl_fx_fvg_oside_15_p37` | 1.37 | $53 | $51 | 1.16 | 54 % | 1.35 | 63 % | $16.4k | 9 of 10 | +64 · +120 · -6 · +36 · +58 |
| **2. 10:00-11:00 displacement, 15m (body >= 1.5 ATR, candle stop, 1R, 1 a day)** | | | | | | | | | | | |
| VWAP side gate  << PICK | `cl_am_disp15_vwap_10to11` | 0.64 | $171 | $129 | 1.25 | 56 % | 1.25 | 65 % | $17.6k | 10 of 10 | +233 · +206 · +56 · +288 · +46 |
| EMA20 side gate (the owner's sheet) | `displace_ema15_1r_10to11_k1p5` | 0.60 | $177 | $135 | 1.26 | 56 % | 1.25 | 67 % | $19.9k | 10 of 10 | +247 · +219 · +29 · +309 · +85 |
| EMA20 gate, body >= 2.0 ATR | `displace_ema15_1r_10to11_k2p0` | 0.36 | $219 | $166 | 1.31 | 56 % | 1.10 | 59 % | $17.1k | 10 of 10 | -74 · +165 · +110 · +161 · +892 |
| EMA20 gate, window stretched to 10:00-15:00 | `cl_disp15_ema_allday_k1p5` | 0.91 | $117 | $90 | 1.17 | 54 % | 1.01 | 70 % | $28.9k | 8 of 10 | +272 · +116 · +52 · +147 · +92 |
| **3. 13:30 first bar, 15m (follow the 13:30-13:45 bar, candle stop, 1R, 1 a day)** | | | | | | | | | | | |
| EMA20 side gate  << PICK | `cl_pm_first_bar_cdl_ema_15` | 0.63 | $93 | $94 | 1.38 | 57 % | 1.64 | 72 % | $7.1k | 10 of 10 | -21 · +111 · +98 · +47 · +223 |
| no gate | `cl_pm_first_bar_cdl_15` | 0.98 | $64 | $61 | 1.25 | 55 % | 1.42 | 70 % | $8.6k | 10 of 10 | +8 · +70 · +62 · +52 · +109 |
| **Controls (not strategies)** | | | | | | | | | | | |
| FVG with NO open-side rule, fixed 37 pt | `cl_fx_fvg_noside_15_p37` | 1.10 | $12 | $12 | 1.04 | 52 % | 0.29 | 54 % | $14.3k | 3 of 10 | -48 · +4 · +8 · +45 · +11 |
| FVG with EMA20 side instead of the open, fixed 37 pt | `cl_fx_fvg_ema20side_15_p37` | 0.99 | $31 | $32 | 1.09 | 53 % | 0.68 | 57 % | $15.7k | 7 of 10 | -11 · +36 · -2 · +73 · +24 |
| the FVG pick on ES | `cl_fvg_oside_15_mid_r1_t2_gap0p1_es` | 1.31 | $4 | $8 | 1.02 | 52 % | 0.13 | 48 % | $15.0k | 4 of 10 | +45 · +9 · +3 · -34 · +47 |
| the FVG pick on GC | `cl_fvg_oside_15_mid_r1_t2_gap0p1_gc` | 1.08 | -$19 | $-16 | 0.89 | 49 % | -0.73 | 39 % | $27.9k | 1 of 10 | -49 · -40 · +8 · -6 · -36 |
| the FVG on 30m bars | `cl_fvg_oside_30_mid_r1_t2` | 0.74 | -$9 | $-16 | 0.98 | 51 % | -0.11 | 46 % | $44.2k | 1 of 10 | +293 · -21 · +17 · -105 · -8 |
| displacement on 5m bars | `cl_disp5_allday_k1p5` | 1.61 | -$15 | $5 | 0.97 | 51 % | -0.26 | 52 % | $43.3k | 1 of 10 | +36 · -8 · +26 · -1 · -177 |
