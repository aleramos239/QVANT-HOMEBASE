# NQ holdout results (2025-01-01..latest), frozen finalists, frozen code
Window 2025-01-02..2026-09-30 (440 sessions, 436 rolling 5-day starts); mode holdout; manifest sha256 7d342e8751df9ddd...; no re-tuning, every number is the frozen finalist scored by the frozen code.
Holdout runs: 41 finalist + 105 control = 146 (146 done), counted in the 400-run screening cap.
Columns: IS = frozen in-sample (2021-09-22..2024-12-31, primary model) | WF = in-sample walk-forward OOS | HO = holdout. P1/P2/P3/P5 = P(pass <= k days), bust5 = P(bust within 5 days); bounds eod/realized/intraday; lift = P5 - day-matched random control (same days, same rules); decay = HO P5 - IS P5.

## 60% criterion per firm (P(pass <= 5d) >= 0.60, primary model; Apex firms: rule-compliant finalists only)
- apex: best eligible finalist apex:fast_single P5 0.431 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: Y/Y/n; passing: none
- apex_eod: best eligible finalist apex_eod:single P5 0.353 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucid: best eligible finalist lucid:single P5 0.780 -> primary PASS (CI lower bound >= 0.60: yes); bounds eod/realized/intraday: Y/Y/n; passing: ['lucid:single', 'lucid:best2', 'lucid:pf', 'lucid:fast_pf']
- lucidpro: best eligible finalist lucidpro:fastpass P5 0.413 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucidpro_nodll: best eligible finalist lucidpro_nodll:single P5 0.812 -> primary PASS (CI lower bound >= 0.60: yes); bounds eod/realized/intraday: Y/Y/n; passing: ['lucidpro_nodll:single', 'lucidpro_nodll:best2', 'lucidpro_nodll:pf', 'lucidpro_nodll:fast_pf', 'lucidpro_nodll:single:hm-orb-tf5#10|mid@40', 'lucidpro_nodll:speed_p3']

## lucid (lucid-flex-50k@2026-09-27; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucid:single | p5_single+fast_single+speed_p3 | hm2-straddle-tf30#10/nyam/40 | L750 K1500 S- T- TT | 0.69 | 0.67 | 0.00/0.00/0.75/0.78 [0.73,0.85] | 0.22 | 0.78/0.78/0.02 | +0.125 [0.06,0.21] | +0.088 | PASS |
| lucid:best2 | best2 | hm2-straddle-tf30#10/nyam/40 (90% of executed); hm2-tod_drift-tf30#19/mid/10 (10% of executed) | L750 K1500 S- T- TT | 0.69 | 0.67 | 0.00/0.00/0.75/0.78 [0.73,0.85] | 0.22 | 0.78/0.78/0.02 | +0.132 [0.07,0.21] | +0.088 | PASS |
| lucid:pf | portfolio_ge3 | hm2-straddle-tf30#8/nyam/40 (80% of executed); hm2-tod_drift-tf30#19/mid/10 (9% of executed); hm2-squeeze-tf5#21/pm/30 (11% of executed) | L750 K1500 S- T- TT | 0.69 | 0.67 | 0.00/0.00/0.75/0.78 [0.73,0.85] | 0.22 | 0.79/0.78/0.04 | +0.149 [0.08,0.23] | +0.092 | PASS |
| lucid:fast_pf | fast_portfolio | hm-first_bar_mom-tf15#22/nyam/40 (78% of executed); hm2-tod_drift-tf30#19/mid/40 (12% of executed); hm2-straddle-tf30#10/pm/40 (10% of executed) | L750 K1500 S- T- TT | 0.66 | n/a | 0.00/0.00/0.70/0.74 [0.69,0.79] | 0.26 | 0.80/0.74/0.02 | +0.044 [-0.01,0.10] | +0.078 | PASS |
| lucid:fastpass | fastpass | fp-tod_drift-tf5#13/mid/40 | L750 K1500 S- T- TT | 0.53 | n/a | 0.00/0.00/0.48/0.50 [0.44,0.57] | 0.50 | 0.50/0.50/0.24 | +0.055 [-0.01,0.13] | -0.024 | fail |

## lucidpro (lucid-pro-50k@2026-09-27b; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucidpro:single | p5_single+fast_single | hm2-tod_drift-tf15#19/mid/30 | L1000 K- S- T- TT | 0.45 | 0.43 | 0.15/0.25/0.27/0.28 [0.21,0.33] | 0.72 | 0.28/0.28/0.25 | -0.002 [-0.08,0.06] | -0.172 | fail |
| lucidpro:best2 | best2 | hm2-tod_drift-tf15#19/mid/30 (96% of executed); hm2-donchian-tf5#9/pm/30 (4% of executed) | L1000 K- S- T- TT | 0.45 | 0.43 | 0.15/0.26/0.27/0.27 [0.21,0.33] | 0.72 | 0.27/0.27/0.24 | -0.009 [-0.08,0.05] | -0.176 | fail |
| lucidpro:pf | portfolio_ge3 | hm2-tod_drift-tf15#19/mid/30 (1% of executed); hm2-donchian-tf5#9/pm/30 (0% of executed); hm-tod_drift-tf5#15/nyam/30 (6% of executed); hm2-tod_drift-tf15#6/london/40 (93% of executed) | L1000 K- S- T- TT | 0.42 | 0.42 | 0.19/0.31/0.33/0.34 [0.29,0.41] | 0.64 | 0.34/0.34/0.29 | -0.008 [-0.06,0.06] | -0.079 | fail |
| lucidpro:fast_pf | fast_portfolio | hm2-tod_drift-tf15#19/mid/30 (58% of executed); hm2-donchian-tf1#11/pm/30 (21% of executed); hm2-ema_pullback-tf1#22/pm/10 (21% of executed) | L- K- S- T- TT | 0.46 | n/a | 0.15/0.27/0.27/0.28 [0.22,0.33] | 0.72 | 0.28/0.28/0.25 | -0.014 [-0.08,0.03] | -0.185 | fail |
| lucidpro:speed_p1 | speed_p1 | fp-tod_drift-tf5#15/mid/40 | L1000 K- S- T- TT | 0.38 | n/a | 0.25/0.25/0.31/0.33 [0.29,0.39] | 0.67 | 0.33/0.33/0.31 | +0.027 [-0.02,0.08] | -0.045 | fail |
| lucidpro:speed_p3 | speed_p3 | hm2-rsi2-tf1#21/mid/40 | L- K- S- T- TT | 0.44 | 0.40 | 0.22/0.37/0.37/0.37 [0.32,0.44] | 0.63 | 0.37/0.37/0.31 | +0.024 [-0.06,0.10] | -0.067 | fail |
| lucidpro:fastpass | fastpass | fp-rsi2-tf5#11/mid/40 | L- K- S- T- TT | 0.43 | 0.37 | 0.25/0.37/0.40/0.41 [0.36,0.48] | 0.59 | 0.41/0.41/0.37 | +0.003 [-0.05,0.08] | -0.015 | fail |

## lucidpro_nodll (lucid-pro-50k-no-dll@2026-09-27b; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucidpro_nodll:single | p5_single+fast_single+speed_p1 | hm2-straddle-tf30#10/nyam/40 | L1000 K- S- T- TT | 0.71 | 0.67 | 0.79/0.81/0.81/0.81 [0.78,0.85] | 0.19 | 0.81/0.81/0.20 | +0.138 [0.09,0.20] | +0.105 | PASS |
| lucidpro_nodll:best2 | best2 | hm2-straddle-tf30#10/nyam/40 (77% of executed); hm-first_bar_mom-tf15#8/mid/10 (23% of executed) | L1000 K- S- T- TT | 0.71 | 0.67 | 0.79/0.81/0.81/0.81 [0.78,0.85] | 0.19 | 0.81/0.81/0.20 | +0.144 [0.10,0.20] | +0.107 | PASS |
| lucidpro_nodll:pf | portfolio_ge3 | hm2-straddle-tf30#9/nyam/40 (100% of executed); hm-first_bar_mom-tf15#8/mid/40 (0% of executed); hm2-straddle-tf30#10/pm/40 (0% of executed) | L1000 K- S- T1 TT | 0.71 | 0.66 | 0.79/0.81/0.81/0.81 [0.78,0.85] | 0.19 | 0.81/0.81/0.22 | +0.123 [0.08,0.18] | +0.105 | PASS |
| lucidpro_nodll:fast_pf | fast_portfolio | hm2-straddle-tf30#9/nyam/40 (55% of executed); hm-orb-tf5#10/mid/30 (24% of executed); hm2-straddle-tf30#10/pm/20 (21% of executed) | L1000 K- S- T- TT | 0.69 | n/a | 0.79/0.81/0.81/0.81 [0.77,0.85] | 0.19 | 0.84/0.81/0.22 | +0.137 [0.10,0.20] | +0.113 | PASS |
| lucidpro_nodll:single:hm-orb-tf5#10|mid@40 | mix_single | hm-orb-tf5#10/mid/40 | L1000 K- S- T- TT | 0.70 | n/a | 0.63/0.67/0.68/0.68 [0.64,0.72] | 0.32 | 0.68/0.68/0.23 | -0.044 [-0.09,0.00] | -0.017 | PASS |
| lucidpro_nodll:speed_p3 | speed_p3 | hm2-straddle-tf30#10/nyam/40 | L1000 K3000 S- T- TT | 0.70 | 0.66 | 0.00/0.77/0.81/0.81 [0.77,0.85] | 0.19 | 0.81/0.81/0.07 | +0.149 [0.10,0.21] | +0.112 | PASS |
| lucidpro_nodll:fastpass | fastpass | fp-tod_drift-tf5#15/pm/40 | L1000 K- S- T- TT | 0.57 | n/a | 0.50/0.52/0.54/0.54 [0.49,0.59] | 0.46 | 0.54/0.54/0.38 | -0.009 [-0.07,0.05] | -0.025 | fail |

## apex (apex-legacy-50k@2026-09-27b; primary intraday; UNCONFIRMED)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| apex:single APEX:day_stop_acts_as_trailing_threshold | p5_single | fp-donchian-tf15#15/pm/40 | L- K- S2000 T- TT | 0.42 | 0.40 | 0.12/0.20/0.25/0.30 [0.22,0.38] | 0.61 | 0.30/0.30/0.30 | -0.050 [-0.13,0.04] | -0.121 | fail |
| apex:best2 | best2 | fp-donchian-tf15#15/pm/40 (17% of executed); hm-donchian-tf15#7/nyam/20 (83% of executed) | L- K- S1000 T- TT | 0.45 | 0.45 | 0.17/0.28/0.31/0.32 [0.26,0.37] | 0.66 | 0.33/0.33/0.32 | +0.001 [-0.05,0.05] | -0.124 | fail |
| apex:pf APEX:day_stop_acts_as_trailing_threshold,no_target_or_stop_gt_5x_target | portfolio_ge3 | fp-donchian-tf15#15/pm/40 (0% of executed); hm-donchian-tf15#7/nyam/20 (0% of executed); hm-first_bar_mom-tf15#34/nyam/20 (0% of executed); hm2-tod_drift-tf15#6/london/40 (100% of executed) | L1000 K- S3000 T1 TT | 0.40 | 0.40 | 0.26/0.30/0.31/0.31 [0.27,0.36] | 0.69 | 0.45/0.45/0.31 | -0.017 [-0.06,0.05] | -0.095 | fail |
| apex:fast_single | fast_single | fp-tod_drift-tf5#7/mid/80 | L- K- S- T- tt | 0.41 | n/a | 0.42/0.43/0.43/0.43 [0.39,0.48] | 0.57 | 0.53/0.53/0.43 | +0.057 [0.01,0.12] | +0.019 | fail |
| apex:fast_pf APEX:OCO_both_side_orders,day_stop_acts_as_trailing_threshold | fast_portfolio | fp-orb-tf5#7/nyam/80 (51% of executed); hm-vwap_z-tf5#1/mid/100 (36% of executed); hm2-ema_pullback-tf1#22/pm/100 (13% of executed) | L- K- S2000 T- tt | 0.41 | n/a | 0.40/0.41/0.41/0.41 [0.35,0.45] | 0.59 | 0.41/0.41/0.41 | +0.029 [-0.03,0.08] | -0.001 | fail |
| apex:speed_p1 | speed_p1 | fp-tod_drift-tf5#10/mid/100 | L- K- S- T- tt | 0.38 | 0.42 | 0.40/0.41/0.41/0.41 [0.38,0.46] | 0.59 | 0.65/0.65/0.41 | +0.080 [0.04,0.14] | +0.027 | fail |
| apex:speed_p3 | speed_p3+p5_single_compliant | hm2-rsi2-tf1#9/mid/40 | L- K- S1000 T- TT | 0.41 | 0.33 | 0.20/0.33/0.33/0.33 [0.27,0.39] | 0.67 | 0.34/0.34/0.33 | +0.032 [-0.05,0.10] | -0.080 | fail |
| apex:fastpass | fastpass | fp-ema_pullback-tf5#9/london/60 | L- K- S- T- TT | 0.40 | n/a | 0.35/0.38/0.38/0.38 [0.33,0.43] | 0.62 | 0.59/0.48/0.38 | -0.025 [-0.08,0.03] | -0.015 | fail |

## apex_eod (apex-eod-50k@2026-09-27b; primary intraday; UNCONFIRMED)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| apex_eod:single | p5_single | hm-donchian-tf15#11/nyam/20 | L1000 K- S- T- TT | 0.40 | 0.38 | 0.16/0.27/0.33/0.35 [0.29,0.40] | 0.61 | 0.35/0.35/0.35 | +0.076 [0.01,0.13] | -0.045 | fail |
| apex_eod:best2 | best2 | hm-donchian-tf15#11/nyam/20 (69% of executed); hm2-donchian-tf5#21/pm/40 (31% of executed) | L- K- S- T- TT | 0.44 | 0.46 | 0.19/0.31/0.33/0.34 [0.27,0.39] | 0.66 | 0.34/0.34/0.34 | +0.045 [-0.02,0.10] | -0.104 | fail |
| apex_eod:pf APEX:no_target_or_stop_gt_5x_target | portfolio_ge3 | hm-donchian-tf15#11/nyam/20 (60% of executed); hm2-donchian-tf5#21/pm/40 (13% of executed); hm-tod_drift-tf5#19/mid/50 (27% of executed) | L- K- S- T- TT | 0.42 | 0.44 | 0.20/0.32/0.33/0.33 [0.28,0.37] | 0.67 | 0.33/0.33/0.33 | +0.044 [-0.02,0.09] | -0.089 | fail |
| apex_eod:fast_single APEX:no_target_or_stop_gt_5x_target | fast_single | hm2-tod_drift-tf15#19/mid/30 | L1000 K- S- T- TT | 0.40 | n/a | 0.13/0.23/0.25/0.25 [0.19,0.31] | 0.75 | 0.25/0.25/0.25 | +0.009 [-0.06,0.07] | -0.147 | fail |
| apex_eod:fast_pf APEX:no_target_or_stop_gt_5x_target | fast_portfolio | hm2-tod_drift-tf15#19/mid/30 (95% of executed); hm2-donchian-tf5#5/pm/40 (2% of executed); hm2-tod_drift-tf15#0/pm/20 (3% of executed) | L1000 K- S- T- TT | 0.39 | n/a | 0.13/0.24/0.24/0.24 [0.19,0.29] | 0.76 | 0.24/0.24/0.24 | -0.000 [-0.06,0.05] | -0.151 | fail |
| apex_eod:speed_p1 | speed_p1 | fp-tod_drift-tf5#14/pm/60 | L- K- S- T- tt | 0.34 | n/a | 0.24/0.25/0.28/0.33 [0.28,0.42] | 0.66 | 0.35/0.35/0.33 | +0.057 [-0.00,0.13] | -0.011 | fail |
| apex_eod:speed_p3 | speed_p3 | hm2-rsi2-tf1#9/mid/40 | L- K- S- T- TT | 0.41 | 0.35 | 0.20/0.33/0.34/0.34 [0.27,0.39] | 0.66 | 0.34/0.34/0.34 | +0.034 [-0.05,0.10] | -0.076 | fail |
| apex_eod:p5_single_compliant | p5_single_compliant | hm2-donchian-tf5#5/pm/30 | L- K- S- T- TT | 0.42 | 0.36 | 0.14/0.23/0.25/0.27 [0.21,0.33] | 0.73 | 0.27/0.27/0.27 | -0.047 [-0.11,0.01] | -0.154 | fail |
| apex_eod:fastpass | fastpass | fp-rsi2-tf5#14/mid/30 | L- K- S- T- TT | 0.38 | 0.31 | 0.19/0.29/0.32/0.34 [0.29,0.40] | 0.66 | 0.34/0.34/0.34 | -0.021 [-0.08,0.06] | -0.047 | fail |

## Funded finalists (rolling 60-session lives, primary breach model; payout policy as frozen)
| finalist | config / cell | IS P20/40/60, med d, E[1st chq], E$40, E$60, bust-pre | WF E$40 | HO P20/40/60, med d, E[1st chq], E$40 [CI], E$60, bust-pre | lift E$40 | decay E$40 | alt models E$40 | flags |
|---|---|---|---|---|---|---|---|---|
| flex#1 | hm2-straddle-tf30#32|pm m40K600L300S0T0P1500 | 0.61/0.62/0.62, 7d, $1064, $3330, $3365, 0.38 | $3753 | 0.55/0.56/0.56, 8d, $966, $2488 [1623.21,3473.10], $2544, 0.44 | +441 | -842 | eod 2488, intraday 0 | - |
| flex#2 | hm2-straddle-tf30#28|pm m40K600L300S0T0Pmax | 0.55/0.56/0.56, 8d, $1125, $3339, $3407, 0.44 | $3737 | 0.51/0.52/0.52, 9d, $1045, $2329 [1483.46,3278.86], $2476, 0.48 | +853 | -1010 | eod 2329, intraday 0 | - |
| flex_dll#1 | hm2-squeeze-tf5#28|pm m20K0L600S0T0P1500 | 0.36/0.37/0.37, 8d, $649, $1734, $1856, 0.63 | $2034 | 0.21/0.21/0.21, 7d, $377, $703 [257.87,1410.81], $703, 0.79 | -154 | -1031 | eod 703, intraday 522 | - |
| flex_dll#2 | fp-donchian-tf15#10|pm m20K0L300S0T1P1000 | 0.55/0.62/0.62, 13d, $863, $1612, $2092, 0.38 | $1949 | 0.32/0.37/0.37, 14d, $504, $751 [483.06,1312.81], $926, 0.63 | +179 | -860 | eod 751, intraday 680 | - |
| pro_dll#1 | fp-donchian-tf15#10|pm m30K0L600S0T0P1500 | 0.40/0.44/0.44, 12d, $863, $1996, $2583, 0.56 | $1994 | 0.32/0.36/0.36, 14d, $703, $1252 [752.92,2073.85], $1512, 0.64 | +530 | -743 | eod 1252, intraday 1134 | - |
| pro_dll#2 | fp-donchian-tf15#13|pm m20K0L300S0T1P1000 | 0.42/0.57/0.57, 15d, $803, $1881, $2687, 0.43 | $2423 | 0.22/0.34/0.34, 18d, $466, $744 [471.88,1303.65], $1026, 0.66 | +46 | -1137 | eod 744, intraday 660 | - |
| pro_nodll#1 | hm-orb-tf5#10|mid m40K1000L300S0T0P1000 | 0.61/0.61/0.61, 4d, $1107, $5426, $5688, 0.39 | $3140 | 0.69/0.69/0.69, 4d, $1233, $4824 [3401.23,5476.09], $4836, 0.31 | -753 | -602 | eod 4824, intraday 17 | - |
| pro_nodll#2 | hm2-straddle-tf30#32|pm m40K600L300S0T0P1000 | 0.69/0.69/0.69, 7d, $936, $4861, $5518, 0.31 | $4680 | 0.58/0.58/0.58, 7d, $788, $3607 [2317.68,5145.79], $3785, 0.42 | +334 | -1254 | eod 3607, intraday 0 | - |
| apex#1 | fp-donchian-tf15#1|nyam m30K1000L1000S0T0P1000 | 0.23/0.42/0.44, 20d, $558, $1093, $1979, 0.56 | $981 | 0.23/0.51/0.57, 23d, $684, $1133 [437.39,1781.10], $1951, 0.38 | +1009 | +40 | nat 1133, opt 1133 | mae30_cuts_0.000 |
| apex#2 | fp-tod_drift-tf5#3|pm m30K1000L300S600T0P1000 | 0.21/0.36/0.37, 18d, $477, $926, $1386, 0.63 | $951 | 0.20/0.28/0.30, 16d, $389, $705 [307.27,1208.86], $913, 0.70 | +312 | -221 | nat 705, opt 822 | - |

## Multi-account (one eval per account, same start day; P(>=1 pass within 5 days))
| N | accounts | IS primary [eod/intraday] | HO primary [CI] | HO eod/realized/intraday | HO by-day 1..5 | E[funded] | eval cost | decay |
|---|---|---|---|---|---|---|---|---|
| 2 | lucid:best2, apex:best2 | 0.839 [0.84/0.45] | 0.860 [0.81,0.91] | 0.86/0.86/0.33 | 0.17, 0.28, 0.83, 0.86, 0.86 | 1.10 | $135 | +0.021 |
| 3 | lucid:best2, lucidpro:pf, apex:best2 | 0.916 [0.92/0.67] | 0.913 [0.88,0.95] | 0.91/0.91/0.51 | 0.32, 0.50, 0.89, 0.91, 0.91 | 1.45 | $250 | -0.003 |
| 4 | lucid:best2, lucid:single, lucidpro:best2, apex:best2 | 0.928 [0.93/0.69] | 0.899 [0.87,0.94] | 0.90/0.90/0.48 | 0.29, 0.45, 0.88, 0.90, 0.90 | 2.15 | $350 | -0.029 |
| 5 | lucid:best2, lucid:single, lucidpro:best2, lucidpro:pf, apex:best2 | 0.960 [0.96/0.81] | 0.936 [0.91,0.97] | 0.94/0.94/0.63 | 0.42, 0.61, 0.92, 0.94, 0.94 | 2.50 | $465 | -0.024 |
| 6 | lucid:best2, lucid:single, lucidpro:best2, lucidpro_nodll:single:hm-orb-tf5#10|mid@40, apex:best2, apex_eod:best2 | 0.981 [0.98/0.81] | 0.968 [0.95,0.99] | 0.97/0.97/0.61 | 0.73, 0.85, 0.97, 0.97, 0.97 | 3.17 | $525 | -0.013 |
