# Screen analysis (Stage A1/A2), research window 2021-01-01..2024-12-31 (825 tape days; 2021 partial from 2021-09-22)
Runs: 80 screen + 16 ctrl analysed (0 jobs missing); self-check sum(session net)==ledger net OK on 96 runs (max |diff| $0.00). Configs (fam x tf x session): 400, with trades 314, >=300 trades 252.
Rules: 1 NQ stats; prop = target_stop ON, no other daily rules, breach eod (intraday in CSV); Lucid {10,20,40} / Apex {10,40,100} micros, best size = max P(pass<=5d). Apex rules UNCONFIRMED.
Survivor = >=300 trades AND edge_lift>0 (vs thinned random control, same size) AND expectancy z>0. **Survivors: Lucid 118, Apex 106, both 92** (of 252 configs with >=300 trades).
- lucid survivors by family: donchian:4 ema_pullback:8 ema_ribbon:4 first_bar_mom:6 gap:2 ib:10 lon_break:1 orb:10 pinbar:5 rsi2:6 squeeze:3 straddle:9 supertrend:4 sweep_rev:9 tema_slope:6 tod_drift:6 vwap_band:8 vwap_flip:7 vwap_z:10
- lucid survivors by tf: 1:32 5:41 15:24 30:21 | by session: asia:13 london:28 nyam:26 mid:31 pm:20
- apex survivors by family: donchian:5 ema_pullback:12 ema_ribbon:4 first_bar_mom:2 gap:1 ib:9 orb:5 pinbar:6 rsi2:6 squeeze:3 straddle:1 supertrend:4 sweep_rev:4 tema_slope:6 tod_drift:6 vwap_band:12 vwap_flip:9 vwap_z:11
- apex survivors by tf: 1:34 5:36 15:21 30:15 | by session: asia:14 london:25 nyam:19 mid:30 pm:18
## Zero-edge baseline
- lucid: best P(pass<=5d) of the random controls at natural frequency, any tf/seed/size: asia 0.077 (random-s1 tf5 40mc) | london 0.107 (random-s3 tf5 40mc) | nyam 0.110 (random-s2 tf1 40mc) | mid 0.105 (random-s2 tf1 40mc) | pm 0.124 (random-s2 tf5 20mc)
  thinned control (mean of 10 draws, at config sizes): max 0.108 (donchian/1/nyam), median 0.028 over 314 configs
- apex: best P(pass<=5d) of the random controls at natural frequency, any tf/seed/size: asia 0.425 (random-s1 tf5 100mc) | london 0.581 (random-s3 tf5 100mc) | nyam 0.625 (random-s2 tf1 100mc) | mid 0.560 (random-s3 tf1 100mc) | pm 0.599 (random-s2 tf1 100mc)
  thinned control (mean of 10 draws, at config sizes): max 0.541 (donchian/1/nyam), median 0.386 over 314 configs
- gambler's-ruin static bound DD/(target+DD) = lucid 2000/(3000+2000) = 40%, apex 2000/(3000+2000) = 40% (continuous-path static-floor ceiling; NOT a ceiling here: Apex random P5 already exceeds it, see above).
- diagnostics: >=300-trade configs with lift>0: Lucid 204, Apex 163 of 252; survivors with PF<1: Lucid 63, Apex 58; configs with t-stat>=2 (any size): 2; net>0: 72. Lift is confounded by trade-day spread (config trades ~every day, thinned control clusters on fewer days): median trade-days config 770 vs control 556.
## Top 25 by edge lift at best size (configs with >=300 trades; S = survivor). P5 = P(pass<=5d) eod, lift = P5 - control P5
| # | Lucid cfg (*=S) | n | net$ | PF | mc | P5 | lift | Apex cfg (*=S) | n | net$ | PF | mc | P5 | lift |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | straddle/30/nyam* | 820 | +13585 | 1.03 | 20 | 0.107 | +0.088 | tema_slope/5/london* | 2364 | +7064 | 1.01 | 100 | 0.627 | +0.130 |
| 2 | ema_pullback/5/pm* | 1288 | +17383 | 1.04 | 40 | 0.145 | +0.074 | tema_slope/1/mid* | 2459 | -15976 | 0.97 | 100 | 0.613 | +0.129 |
| 3 | first_bar_mom/15/nyam* | 816 | +41766 | 1.10 | 20 | 0.114 | +0.072 | rsi2/1/mid* | 2457 | +18607 | 1.03 | 100 | 0.608 | +0.124 |
| 4 | tod_drift/30/mid | 820 | +23490 | 1.05 | 20 | 0.085 | +0.069 | vwap_flip/1/mid* | 2182 | -25948 | 0.95 | 100 | 0.596 | +0.122 |
| 5 | tod_drift/30/pm | 813 | +32918 | 1.07 | 20 | 0.072 | +0.069 | ema_pullback/5/london* | 2288 | -20907 | 0.96 | 100 | 0.614 | +0.121 |
| 6 | straddle/30/pm | 811 | +16211 | 1.04 | 20 | 0.106 | +0.069 | ema_pullback/1/pm* | 2431 | -18954 | 0.96 | 100 | 0.609 | +0.119 |
| 7 | straddle/15/london* | 820 | -995 | 1.00 | 40 | 0.104 | +0.069 | ib/5/nyam* | 495 | +10000 | 1.07 | 100 | 0.474 | +0.110 |
| 8 | straddle/15/nyam | 820 | -335 | 1.00 | 20 | 0.111 | +0.068 | tod_drift/30/pm | 813 | +32918 | 1.07 | 100 | 0.468 | +0.110 |
| 9 | orb/5/nyam* | 814 | +26419 | 1.08 | 20 | 0.104 | +0.067 | tod_drift/15/pm* | 813 | +38378 | 1.11 | 100 | 0.503 | +0.106 |
| 10 | tod_drift/15/mid* | 820 | +28365 | 1.07 | 20 | 0.099 | +0.066 | ema_pullback/5/nyam | 1686 | -97929 | 0.87 | 100 | 0.571 | +0.105 |
| 11 | lon_break/30/nyam | 794 | -55556 | 0.88 | 20 | 0.082 | +0.062 | ema_pullback/1/nyam* | 2427 | -10073 | 0.98 | 100 | 0.641 | +0.101 |
| 12 | tod_drift/15/pm* | 813 | +38378 | 1.11 | 40 | 0.096 | +0.062 | vwap_band/1/pm* | 2285 | +16700 | 1.04 | 100 | 0.581 | +0.100 |
| 13 | straddle/5/nyam* | 820 | -12115 | 0.95 | 20 | 0.099 | +0.062 | rsi2/1/nyam | 2458 | -35742 | 0.94 | 100 | 0.639 | +0.099 |
| 14 | orb/1/london* | 819 | +5229 | 1.05 | 40 | 0.094 | +0.061 | vwap_flip/5/london* | 1929 | -12401 | 0.97 | 100 | 0.570 | +0.097 |
| 15 | orb/5/london* | 819 | +2014 | 1.01 | 40 | 0.104 | +0.061 | ib/15/nyam* | 495 | +12650 | 1.08 | 100 | 0.485 | +0.097 |
| 16 | tod_drift/5/pm* | 813 | +20628 | 1.11 | 40 | 0.117 | +0.061 | squeeze/1/asia* | 1466 | -11944 | 0.89 | 100 | 0.281 | +0.096 |
| 17 | orb/15/london | 819 | -16236 | 0.94 | 20 | 0.089 | +0.060 | ema_pullback/5/asia* | 1240 | +3915 | 1.02 | 100 | 0.438 | +0.095 |
| 18 | vwap_z/5/asia* | 1519 | -7146 | 0.96 | 40 | 0.102 | +0.060 | ema_ribbon/15/london* | 643 | +11623 | 1.06 | 100 | 0.454 | +0.095 |
| 19 | first_bar_mom/30/nyam* | 815 | -3365 | 0.99 | 20 | 0.077 | +0.057 | tod_drift/1/mid* | 820 | -800 | 0.99 | 100 | 0.415 | +0.090 |
| 20 | orb/30/nyam* | 814 | +20149 | 1.05 | 20 | 0.077 | +0.057 | ema_ribbon/1/mid* | 2291 | -40149 | 0.92 | 100 | 0.566 | +0.088 |
| 21 | lon_break/15/nyam | 794 | -38761 | 0.90 | 20 | 0.096 | +0.056 | donchian/1/nyam* | 2444 | -22451 | 0.97 | 100 | 0.629 | +0.087 |
| 22 | lon_break/1/nyam* | 794 | -721 | 0.99 | 40 | 0.101 | +0.056 | vwap_flip/1/pm | 2248 | -61797 | 0.87 | 100 | 0.566 | +0.086 |
| 23 | straddle/15/mid* | 820 | -15725 | 0.97 | 20 | 0.082 | +0.055 | tod_drift/5/pm* | 813 | +20628 | 1.11 | 100 | 0.479 | +0.084 |
| 24 | tod_drift/5/mid* | 820 | +39490 | 1.16 | 40 | 0.141 | +0.055 | supertrend/1/mid* | 2113 | -20282 | 0.96 | 100 | 0.552 | +0.081 |
| 25 | straddle/1/pm* | 813 | -1972 | 0.99 | 40 | 0.096 | +0.054 | tema_slope/1/nyam | 2450 | -57710 | 0.92 | 100 | 0.621 | +0.081 |
Outputs: out/screen_table.csv (400 rows), out/screen_baseline.csv (480 rows). Elapsed 20s.
