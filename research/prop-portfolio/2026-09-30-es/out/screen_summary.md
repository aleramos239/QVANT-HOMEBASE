# Screen analysis (Stage A1/A2), research window 2021-01-01..2024-12-31 (825 tape days; 2021 partial from 2021-09-22)
Runs: 80 screen + 16 ctrl analysed (0 jobs missing); self-check sum(session net)==ledger net OK on 96 runs (max |diff| $0.00). Configs (fam x tf x session): 400, with trades 314, >=300 trades 252.
Rules: 1 NQ stats; prop = target_stop ON, no other daily rules, breach eod (intraday in CSV); Lucid {10,20,40} / Apex {10,40,100} micros, best size = max P(pass<=5d). Apex rules UNCONFIRMED.
Survivor = >=300 trades AND edge_lift>0 (vs thinned random control, same size) AND expectancy z>0. **Survivors: Lucid 100, Apex 102, both 85** (of 252 configs with >=300 trades).
- lucid survivors by family: donchian:6 ema_pullback:7 ema_ribbon:6 first_bar_mom:3 gap:3 ib:7 orb:2 pinbar:4 rsi2:7 squeeze:2 straddle:7 supertrend:3 sweep_rev:7 tema_slope:10 tod_drift:7 vwap_band:6 vwap_flip:7 vwap_z:6
- lucid survivors by tf: 1:29 5:30 15:25 30:16 | by session: asia:7 london:24 nyam:20 mid:29 pm:20
- apex survivors by family: donchian:8 ema_pullback:7 ema_ribbon:6 first_bar_mom:1 gap:1 ib:8 orb:1 pinbar:6 rsi2:8 squeeze:4 straddle:3 supertrend:3 sweep_rev:7 tema_slope:10 tod_drift:7 vwap_band:8 vwap_flip:7 vwap_z:7
- apex survivors by tf: 1:38 5:26 15:21 30:17 | by session: asia:12 london:26 nyam:13 mid:31 pm:20
## Zero-edge baseline
- lucid: best P(pass<=5d) of the random controls at natural frequency, any tf/seed/size: asia 0.016 (random-s1 tf5 40mc) | london 0.076 (random-s3 tf5 40mc) | nyam 0.084 (random-s2 tf5 40mc) | mid 0.078 (random-s2 tf5 40mc) | pm 0.123 (random-s2 tf5 40mc)
  thinned control (mean of 10 draws, at config sizes): max 0.071 (rsi2/5/nyam), median 0.017 over 314 configs
- apex: best P(pass<=5d) of the random controls at natural frequency, any tf/seed/size: asia 0.231 (random-s2 tf15 100mc) | london 0.437 (random-s1 tf5 100mc) | nyam 0.443 (random-s1 tf1 100mc) | mid 0.443 (random-s1 tf1 100mc) | pm 0.474 (random-s2 tf5 100mc)
  thinned control (mean of 10 draws, at config sizes): max 0.435 (orb/30/pm), median 0.303 over 314 configs
- gambler's-ruin static bound DD/(target+DD) = lucid 2000/(3000+2000) = 40%, apex 2000/(3000+2000) = 40% (continuous-path static-floor ceiling; NOT a ceiling here: Apex random P5 already exceeds it, see above).
- diagnostics: >=300-trade configs with lift>0: Lucid 192, Apex 168 of 252; survivors with PF<1: Lucid 94, Apex 96; configs with t-stat>=2 (any size): 0; net>0: 8. Lift is confounded by trade-day spread (config trades ~every day, thinned control clusters on fewer days): median trade-days config 768 vs control 555.
## Top 25 by edge lift at best size (configs with >=300 trades; S = survivor). P5 = P(pass<=5d) eod, lift = P5 - control P5
| # | Lucid cfg (*=S) | n | net$ | PF | mc | P5 | lift | Apex cfg (*=S) | n | net$ | PF | mc | P5 | lift |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | straddle/30/pm | 816 | -464 | 1.00 | 40 | 0.101 | +0.074 | rsi2/1/mid* | 2466 | -40814 | 0.89 | 100 | 0.502 | +0.165 |
| 2 | straddle/5/pm* | 816 | -6289 | 0.97 | 40 | 0.105 | +0.074 | ema_ribbon/1/mid* | 2319 | -41014 | 0.87 | 100 | 0.476 | +0.144 |
| 3 | straddle/15/pm | 816 | +1861 | 1.01 | 20 | 0.100 | +0.073 | tema_slope/1/mid* | 2464 | -81931 | 0.78 | 100 | 0.473 | +0.136 |
| 4 | straddle/30/nyam | 823 | -38992 | 0.86 | 20 | 0.079 | +0.071 | ema_pullback/1/mid* | 2458 | -56607 | 0.84 | 100 | 0.458 | +0.122 |
| 5 | tod_drift/5/mid* | 823 | -3692 | 0.97 | 40 | 0.116 | +0.068 | vwap_z/1/mid* | 2364 | -56468 | 0.83 | 100 | 0.452 | +0.119 |
| 6 | orb/5/pm | 815 | -39710 | 0.81 | 40 | 0.097 | +0.067 | vwap_band/1/mid* | 2314 | -64144 | 0.81 | 100 | 0.435 | +0.102 |
| 7 | lon_break/30/nyam | 783 | -31070 | 0.88 | 20 | 0.073 | +0.065 | tod_drift/30/pm | 816 | -1764 | 0.99 | 100 | 0.417 | +0.101 |
| 8 | straddle/5/mid | 823 | -46980 | 0.81 | 20 | 0.080 | +0.061 | vwap_flip/15/london* | 1241 | -36702 | 0.84 | 100 | 0.434 | +0.098 |
| 9 | orb/30/nyam | 814 | -25606 | 0.90 | 40 | 0.066 | +0.055 | tod_drift/15/nyam | 823 | -42267 | 0.83 | 40 | 0.258 | +0.095 |
| 10 | vwap_flip/5/pm* | 1377 | -19408 | 0.94 | 40 | 0.112 | +0.055 | ema_pullback/1/pm* | 2443 | -51460 | 0.83 | 100 | 0.423 | +0.093 |
| 11 | vwap_flip/15/london* | 1241 | -36702 | 0.84 | 40 | 0.091 | +0.055 | tod_drift/15/pm* | 816 | -452 | 1.00 | 100 | 0.424 | +0.093 |
| 12 | tod_drift/30/mid | 823 | -10267 | 0.96 | 40 | 0.066 | +0.052 | donchian/15/pm* | 500 | +27938 | 1.22 | 100 | 0.440 | +0.087 |
| 13 | straddle/30/london* | 823 | -33567 | 0.83 | 40 | 0.074 | +0.052 | supertrend/1/mid* | 2120 | -47655 | 0.83 | 100 | 0.418 | +0.086 |
| 14 | straddle/30/mid* | 823 | -32704 | 0.88 | 20 | 0.063 | +0.052 | tema_slope/30/london* | 808 | -22420 | 0.86 | 100 | 0.393 | +0.085 |
| 15 | orb/30/pm | 815 | -9760 | 0.96 | 40 | 0.078 | +0.051 | ema_ribbon/1/pm* | 2297 | -62388 | 0.79 | 100 | 0.413 | +0.085 |
| 16 | straddle/15/nyam* | 823 | -13330 | 0.94 | 40 | 0.093 | +0.051 | vwap_flip/1/mid* | 2207 | -75266 | 0.77 | 100 | 0.417 | +0.083 |
| 17 | orb/15/pm | 815 | -16198 | 0.94 | 40 | 0.089 | +0.051 | tod_drift/30/nyam | 823 | -24104 | 0.92 | 100 | 0.309 | +0.082 |
| 18 | ema_ribbon/1/mid* | 2319 | -41014 | 0.87 | 40 | 0.084 | +0.050 | ema_pullback/30/nyam | 695 | -32942 | 0.84 | 100 | 0.419 | +0.082 |
| 19 | straddle/15/mid | 823 | -41942 | 0.85 | 20 | 0.067 | +0.050 | ib/30/mid* | 473 | -10542 | 0.92 | 100 | 0.385 | +0.081 |
| 20 | tod_drift/30/nyam | 823 | -24104 | 0.92 | 40 | 0.052 | +0.050 | vwap_flip/1/nyam* | 2101 | -69904 | 0.81 | 100 | 0.454 | +0.080 |
| 21 | straddle/15/london* | 823 | -30692 | 0.80 | 40 | 0.073 | +0.049 | vwap_flip/5/london | 1948 | -55367 | 0.81 | 100 | 0.432 | +0.080 |
| 22 | rsi2/1/mid* | 2466 | -40814 | 0.89 | 40 | 0.083 | +0.049 | donchian/1/mid* | 2460 | -85365 | 0.77 | 100 | 0.415 | +0.079 |
| 23 | first_bar_mom/30/nyam | 795 | -23580 | 0.90 | 40 | 0.060 | +0.049 | first_bar_mom/30/mid* | 354 | +884 | 1.01 | 100 | 0.343 | +0.078 |
| 24 | orb/30/london | 822 | -45813 | 0.77 | 40 | 0.069 | +0.047 | donchian/1/nyam | 2438 | -87527 | 0.78 | 100 | 0.458 | +0.078 |
| 25 | rsi2/15/london* | 1949 | -51934 | 0.85 | 40 | 0.085 | +0.047 | ema_pullback/5/london | 2303 | -66337 | 0.80 | 100 | 0.436 | +0.076 |
Outputs: out/screen_table.csv (400 rows), out/screen_baseline.csv (480 rows). Elapsed 48s.

## Day-matched lift (screen_lift_daymatched.py, K=20) and ES vs NQ
- Lucid: mean lift old +0.015 -> day-matched +0.007 (lift>0 in 151 of 252, >2 sd in 57); Apex: +0.017 -> +0.016 (161 of 252, >2 sd in 77). Same pattern as NQ (Lucid lift halves once day-spread is matched; Apex holds).
- day-matched top lift lucid: tod_drift/5/mid +0.068 (P5 0.116 vs ctrl 0.047); vwap_flip/5/pm +0.062 (P5 0.112 vs ctrl 0.050); vwap_flip/15/london +0.053 (P5 0.091 vs ctrl 0.038); vwap_flip/5/mid +0.050 (P5 0.080 vs ctrl 0.030); rsi2/1/mid +0.050 (P5 0.083 vs ctrl 0.033)
- day-matched top lift apex: rsi2/1/mid +0.129 (P5 0.502 vs ctrl 0.373); ema_pullback/5/mid +0.122 (P5 0.429 vs ctrl 0.307); vwap_flip/15/london +0.119 (P5 0.434 vs ctrl 0.315); ema_ribbon/1/mid +0.114 (P5 0.476 vs ctrl 0.362); vwap_flip/5/pm +0.114 (P5 0.465 vs ctrl 0.351)
- ES vs NQ: configs with t-stat >= 2: ES 0 vs NQ 2; net > 0 at 1 contract (>=300 trades): ES 8 of 252 vs NQ 72; best PF ES donchian/15/pm 1.22 (NQ 1.45, t 3.05). ES round-trip friction $29/contract vs NQ $14 (2x), so the whole screen sits lower: 0 of 252 configs have t >= 2 (ES best t-stat 1.72, donchian/15/pm).
- Zero-edge random baseline is lower on ES: best natural-frequency random P5 eod Lucid 0.12 (NQ 0.12), Apex 0.47 (NQ 0.63).
- Tuning selection (queued 18:30 ET as tune1.jsonl): rank = rank(best-session t-stat) + rank(best day-matched lift); top 13 family x tf = vwap_flip/15, tema_slope/30, donchian/15, first_bar_mom/30, tod_drift/5, vwap_z/5, donchian/30, vwap_flip/5, tema_slope/15, tod_drift/15, ema_pullback/30, straddle/15, ema_pullback/5; fast-pass (stop_mode pts {3,6,10,15} x tgt_r {0.25,0.4,0.6,1.0}) on the top 6 = vwap_flip/15, tema_slope/30, donchian/15, first_bar_mom/30, tod_drift/5, vwap_z/5. Random controls: hmctrl (3 seeds) + fpctrl (3 seeds).
