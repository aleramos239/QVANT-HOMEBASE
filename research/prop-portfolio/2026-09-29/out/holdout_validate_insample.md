# Scorer validation on the IN-SAMPLE window (same code; not holdout results)
Window 2021-09-22..2024-12-31 (825 sessions, 821 rolling 5-day starts); mode insample; manifest sha256 5e31b002e2e78096...; no re-tuning, every number is the frozen finalist scored by the frozen code.
In-sample validation: no 2025+ data read.
Columns: IS = frozen in-sample (2021-09-22..2024-12-31, primary model) | WF = in-sample walk-forward OOS | HO = holdout. P1/P2/P3/P5 = P(pass <= k days), bust5 = P(bust within 5 days); bounds eod/realized/intraday; lift = P5 - day-matched random control (same days, same rules); decay = HO P5 - IS P5.

## 60% criterion per firm (P(pass <= 5d) >= 0.60, primary model; Apex firms: rule-compliant finalists only)
- apex: best eligible finalist apex:best2 P5 0.447 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: Y/Y/n; passing: none
- apex_eod: best eligible finalist apex_eod:best2 P5 0.441 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucid: best eligible finalist lucid:single P5 0.692 -> primary PASS (CI lower bound >= 0.60: yes); bounds eod/realized/intraday: Y/Y/n; passing: ['lucid:single', 'lucid:best2', 'lucid:pf', 'lucid:fast_pf']
- lucidpro: best eligible finalist lucidpro:fast_pf P5 0.460 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucidpro_nodll: best eligible finalist lucidpro_nodll:single P5 0.706 -> primary PASS (CI lower bound >= 0.60: yes); bounds eod/realized/intraday: Y/Y/n; passing: ['lucidpro_nodll:single', 'lucidpro_nodll:best2', 'lucidpro_nodll:pf', 'lucidpro_nodll:fast_pf', 'lucidpro_nodll:single:hm-orb-tf5#10|mid@40', 'lucidpro_nodll:speed_p3']

## lucid (lucid-flex-50k@2026-09-27; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucid:single | p5_single+fast_single+speed_p3 | hm2-straddle-tf30#10/nyam/40 | L750 K1500 S- T- TT | 0.69 | 0.67 | 0.00/0.00/0.66/0.69 [0.64,0.74] | 0.31 | 0.69/0.69/0.01 | +0.093 [0.04,0.14] | +0.000 | PASS |
| lucid:best2 | best2 | hm2-straddle-tf30#10/nyam/40 (85% of executed); hm2-tod_drift-tf30#19/mid/10 (15% of executed) | L750 K1500 S- T- TT | 0.69 | 0.67 | 0.00/0.00/0.67/0.69 [0.65,0.74] | 0.31 | 0.69/0.69/0.01 | +0.101 [0.05,0.15] | +0.000 | PASS |
| lucid:pf | portfolio_ge3 | hm2-straddle-tf30#8/nyam/40 (71% of executed); hm2-tod_drift-tf30#19/mid/10 (13% of executed); hm2-squeeze-tf5#21/pm/30 (16% of executed) | L750 K1500 S- T- TT | 0.69 | 0.67 | 0.00/0.00/0.67/0.69 [0.64,0.74] | 0.31 | 0.73/0.69/0.07 | +0.132 [0.09,0.18] | +0.000 | PASS |
| lucid:fast_pf | fast_portfolio | hm-first_bar_mom-tf15#22/nyam/40 (74% of executed); hm2-tod_drift-tf30#19/mid/40 (15% of executed); hm2-straddle-tf30#10/pm/40 (12% of executed) | L750 K1500 S- T- TT | 0.66 | n/a | 0.00/0.00/0.65/0.66 [0.62,0.71] | 0.34 | 0.79/0.66/0.02 | +0.026 [-0.01,0.07] | +0.000 | PASS |
| lucid:fastpass | fastpass | fp-tod_drift-tf5#13/mid/40 | L750 K1500 S- T- TT | 0.53 | n/a | 0.00/0.00/0.50/0.53 [0.48,0.57] | 0.47 | 0.53/0.53/0.25 | +0.056 [0.00,0.10] | -0.000 | fail |

## lucidpro (lucid-pro-50k@2026-09-27b; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucidpro:single | p5_single+fast_single | hm2-tod_drift-tf15#19/mid/30 | L1000 K- S- T- TT | 0.45 | 0.43 | 0.24/0.38/0.42/0.45 [0.40,0.50] | 0.54 | 0.45/0.45/0.40 | +0.092 [0.03,0.15] | +0.000 | fail |
| lucidpro:best2 | best2 | hm2-tod_drift-tf15#19/mid/30 (92% of executed); hm2-donchian-tf5#9/pm/30 (8% of executed) | L1000 K- S- T- TT | 0.45 | 0.43 | 0.25/0.39/0.43/0.45 [0.40,0.50] | 0.55 | 0.45/0.45/0.40 | +0.095 [0.04,0.15] | +0.000 | fail |
| lucidpro:pf | portfolio_ge3 | hm2-tod_drift-tf15#19/mid/30 (1% of executed); hm2-donchian-tf5#9/pm/30 (0% of executed); hm-tod_drift-tf5#15/nyam/30 (17% of executed); hm2-tod_drift-tf15#6/london/40 (81% of executed) | L1000 K- S- T- TT | 0.42 | 0.42 | 0.21/0.34/0.39/0.42 [0.38,0.46] | 0.56 | 0.42/0.42/0.37 | +0.037 [-0.01,0.08] | +0.000 | fail |
| lucidpro:fast_pf | fast_portfolio | hm2-tod_drift-tf15#19/mid/30 (44% of executed); hm2-donchian-tf1#11/pm/30 (29% of executed); hm2-ema_pullback-tf1#22/pm/10 (28% of executed) | L- K- S- T- TT | 0.46 | n/a | 0.28/0.45/0.46/0.46 [0.41,0.50] | 0.54 | 0.46/0.46/0.42 | +0.108 [0.06,0.15] | +0.000 | fail |
| lucidpro:speed_p1 | speed_p1 | fp-tod_drift-tf5#15/mid/40 | L1000 K- S- T- TT | 0.38 | n/a | 0.27/0.28/0.33/0.38 [0.32,0.43] | 0.62 | 0.38/0.38/0.35 | +0.068 [0.01,0.12] | +0.000 | fail |
| lucidpro:speed_p3 | speed_p3 | hm2-rsi2-tf1#21/mid/40 | L- K- S- T- TT | 0.44 | 0.40 | 0.26/0.41/0.43/0.44 [0.40,0.49] | 0.56 | 0.44/0.44/0.38 | +0.045 [-0.01,0.10] | -0.000 | fail |
| lucidpro:fastpass | fastpass | fp-rsi2-tf5#11/mid/40 | L- K- S- T- TT | 0.43 | 0.37 | 0.25/0.39/0.42/0.43 [0.39,0.47] | 0.57 | 0.43/0.43/0.38 | -0.022 [-0.07,0.03] | +0.000 | fail |

## lucidpro_nodll (lucid-pro-50k-no-dll@2026-09-27b; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucidpro_nodll:single | p5_single+fast_single+speed_p1 | hm2-straddle-tf30#10/nyam/40 | L1000 K- S- T- TT | 0.71 | 0.67 | 0.67/0.70/0.71/0.71 [0.67,0.74] | 0.29 | 0.71/0.71/0.23 | +0.072 [0.03,0.11] | +0.000 | PASS |
| lucidpro_nodll:best2 | best2 | hm2-straddle-tf30#10/nyam/40 (71% of executed); hm-first_bar_mom-tf15#8/mid/10 (29% of executed) | L1000 K- S- T- TT | 0.71 | 0.67 | 0.67/0.70/0.71/0.71 [0.67,0.74] | 0.29 | 0.71/0.71/0.23 | +0.079 [0.04,0.12] | +0.000 | PASS |
| lucidpro_nodll:pf | portfolio_ge3 | hm2-straddle-tf30#9/nyam/40 (100% of executed); hm-first_bar_mom-tf15#8/mid/40 (0% of executed); hm2-straddle-tf30#10/pm/40 (0% of executed) | L1000 K- S- T1 TT | 0.71 | 0.66 | 0.67/0.70/0.70/0.71 [0.67,0.74] | 0.29 | 0.71/0.71/0.26 | +0.088 [0.05,0.13] | +0.000 | PASS |
| lucidpro_nodll:fast_pf | fast_portfolio | hm2-straddle-tf30#9/nyam/40 (52% of executed); hm-orb-tf5#10/mid/30 (26% of executed); hm2-straddle-tf30#10/pm/20 (22% of executed) | L1000 K- S- T- TT | 0.69 | n/a | 0.68/0.69/0.69/0.69 [0.66,0.73] | 0.31 | 0.74/0.69/0.26 | +0.087 [0.05,0.12] | +0.000 | PASS |
| lucidpro_nodll:single:hm-orb-tf5#10|mid@40 | mix_single | hm-orb-tf5#10/mid/40 | L1000 K- S- T- TT | 0.70 | n/a | 0.60/0.68/0.70/0.70 [0.66,0.73] | 0.30 | 0.70/0.70/0.27 | +0.030 [-0.01,0.07] | +0.000 | PASS |
| lucidpro_nodll:speed_p3 | speed_p3 | hm2-straddle-tf30#10/nyam/40 | L1000 K3000 S- T- TT | 0.70 | 0.66 | 0.00/0.67/0.69/0.70 [0.66,0.73] | 0.30 | 0.70/0.70/0.06 | +0.074 [0.03,0.11] | +0.000 | PASS |
| lucidpro_nodll:fastpass | fastpass | fp-tod_drift-tf5#15/pm/40 | L1000 K- S- T- TT | 0.57 | n/a | 0.51/0.55/0.56/0.57 [0.53,0.61] | 0.43 | 0.57/0.57/0.37 | +0.041 [-0.00,0.09] | -0.000 | fail |

## apex (apex-legacy-50k@2026-09-27b; primary intraday; UNCONFIRMED)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| apex:single APEX:day_stop_acts_as_trailing_threshold | p5_single | fp-donchian-tf15#15/pm/40 | L- K- S2000 T- TT | 0.42 | 0.40 | 0.19/0.30/0.36/0.42 [0.36,0.48] | 0.52 | 0.43/0.43/0.42 | +0.060 [-0.00,0.13] | +0.000 | fail |
| apex:best2 | best2 | fp-donchian-tf15#15/pm/40 (27% of executed); hm-donchian-tf15#7/nyam/20 (73% of executed) | L- K- S1000 T- TT | 0.45 | 0.45 | 0.21/0.36/0.41/0.45 [0.38,0.50] | 0.54 | 0.45/0.45/0.45 | +0.092 [0.03,0.15] | +0.000 | fail |
| apex:pf APEX:day_stop_acts_as_trailing_threshold,no_target_or_stop_gt_5x_target | portfolio_ge3 | fp-donchian-tf15#15/pm/40 (0% of executed); hm-donchian-tf15#7/nyam/20 (0% of executed); hm-first_bar_mom-tf15#34/nyam/20 (0% of executed); hm2-tod_drift-tf15#6/london/40 (100% of executed) | L1000 K- S3000 T1 TT | 0.40 | 0.40 | 0.23/0.32/0.37/0.40 [0.36,0.44] | 0.58 | 0.49/0.49/0.40 | +0.053 [0.01,0.10] | +0.000 | fail |
| apex:fast_single | fast_single | fp-tod_drift-tf5#7/mid/80 | L- K- S- T- tt | 0.41 | n/a | 0.41/0.41/0.41/0.41 [0.37,0.44] | 0.59 | 0.51/0.51/0.41 | +0.026 [-0.01,0.06] | +0.000 | fail |
| apex:fast_pf APEX:OCO_both_side_orders,day_stop_acts_as_trailing_threshold | fast_portfolio | fp-orb-tf5#7/nyam/80 (45% of executed); hm-vwap_z-tf5#1/mid/100 (36% of executed); hm2-ema_pullback-tf1#22/pm/100 (18% of executed) | L- K- S2000 T- tt | 0.41 | n/a | 0.40/0.41/0.41/0.41 [0.37,0.43] | 0.59 | 0.41/0.41/0.41 | +0.023 [-0.02,0.05] | +0.000 | fail |
| apex:speed_p1 | speed_p1 | fp-tod_drift-tf5#10/mid/100 | L- K- S- T- tt | 0.38 | 0.42 | 0.38/0.38/0.38/0.38 [0.34,0.41] | 0.62 | 0.64/0.64/0.38 | +0.041 [0.00,0.08] | +0.000 | fail |
| apex:speed_p3 | speed_p3+p5_single_compliant | hm2-rsi2-tf1#9/mid/40 | L- K- S1000 T- TT | 0.41 | 0.33 | 0.24/0.38/0.40/0.41 [0.37,0.46] | 0.59 | 0.42/0.42/0.41 | +0.061 [0.00,0.12] | +0.000 | fail |
| apex:fastpass | fastpass | fp-ema_pullback-tf5#9/london/60 | L- K- S- T- TT | 0.40 | n/a | 0.36/0.40/0.40/0.40 [0.36,0.43] | 0.60 | 0.65/0.51/0.40 | -0.038 [-0.08,0.00] | -0.000 | fail |

## apex_eod (apex-eod-50k@2026-09-27b; primary intraday; UNCONFIRMED)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| apex_eod:single | p5_single | hm-donchian-tf15#11/nyam/20 | L1000 K- S- T- TT | 0.40 | 0.38 | 0.16/0.27/0.33/0.40 [0.34,0.46] | 0.54 | 0.40/0.40/0.40 | +0.081 [0.02,0.14] | +0.000 | fail |
| apex_eod:best2 | best2 | hm-donchian-tf15#11/nyam/20 (60% of executed); hm2-donchian-tf5#21/pm/40 (40% of executed) | L- K- S- T- TT | 0.44 | 0.46 | 0.25/0.42/0.43/0.44 [0.39,0.48] | 0.56 | 0.44/0.44/0.44 | +0.083 [0.04,0.13] | +0.000 | fail |
| apex_eod:pf APEX:no_target_or_stop_gt_5x_target | portfolio_ge3 | hm-donchian-tf15#11/nyam/20 (51% of executed); hm2-donchian-tf5#21/pm/40 (20% of executed); hm-tod_drift-tf5#19/mid/50 (29% of executed) | L- K- S- T- TT | 0.42 | 0.44 | 0.25/0.41/0.42/0.42 [0.37,0.47] | 0.58 | 0.42/0.42/0.42 | +0.068 [0.02,0.11] | +0.000 | fail |
| apex_eod:fast_single APEX:no_target_or_stop_gt_5x_target | fast_single | hm2-tod_drift-tf15#19/mid/30 | L1000 K- S- T- TT | 0.40 | n/a | 0.21/0.35/0.38/0.40 [0.35,0.45] | 0.60 | 0.40/0.40/0.40 | +0.097 [0.04,0.15] | +0.000 | fail |
| apex_eod:fast_pf APEX:no_target_or_stop_gt_5x_target | fast_portfolio | hm2-tod_drift-tf15#19/mid/30 (92% of executed); hm2-donchian-tf5#5/pm/40 (3% of executed); hm2-tod_drift-tf15#0/pm/20 (6% of executed) | L1000 K- S- T- TT | 0.39 | n/a | 0.22/0.36/0.38/0.39 [0.35,0.44] | 0.61 | 0.40/0.40/0.39 | +0.093 [0.04,0.15] | +0.000 | fail |
| apex_eod:speed_p1 | speed_p1 | fp-tod_drift-tf5#14/pm/60 | L- K- S- T- tt | 0.34 | n/a | 0.25/0.25/0.31/0.34 [0.30,0.38] | 0.65 | 0.37/0.37/0.34 | +0.048 [0.01,0.09] | -0.000 | fail |
| apex_eod:speed_p3 | speed_p3 | hm2-rsi2-tf1#9/mid/40 | L- K- S- T- TT | 0.41 | 0.35 | 0.24/0.38/0.40/0.41 [0.37,0.46] | 0.59 | 0.42/0.42/0.41 | +0.058 [0.00,0.12] | +0.000 | fail |
| apex_eod:p5_single_compliant | p5_single_compliant | hm2-donchian-tf5#5/pm/30 | L- K- S- T- TT | 0.42 | 0.36 | 0.22/0.34/0.40/0.42 [0.37,0.48] | 0.57 | 0.42/0.42/0.42 | +0.067 [0.01,0.12] | +0.000 | fail |
| apex_eod:fastpass | fastpass | fp-rsi2-tf5#14/mid/30 | L- K- S- T- TT | 0.38 | 0.31 | 0.21/0.32/0.36/0.38 [0.34,0.43] | 0.61 | 0.39/0.39/0.38 | -0.056 [-0.10,-0.00] | +0.000 | fail |

## Funded finalists (rolling 60-session lives, primary breach model; payout policy as frozen)
| finalist | config / cell | IS P20/40/60, med d, E[1st chq], E$40, E$60, bust-pre | WF E$40 | HO P20/40/60, med d, E[1st chq], E$40 [CI], E$60, bust-pre | lift E$40 | decay E$40 | alt models E$40 | flags |
|---|---|---|---|---|---|---|---|---|
| flex#1 | hm2-straddle-tf30#32|pm m40K600L300S0T0P1500 | 0.61/0.62/0.62, 7d, $1064, $3330, $3365, 0.38 | $3753 | 0.61/0.62/0.62, 7d, $1064, $3330 [2542.88,4262.22], $3365, 0.38 | +1870 | +0 | eod 3330, intraday 41 | - |
| flex#2 | hm2-straddle-tf30#28|pm m40K600L300S0T0Pmax | 0.55/0.56/0.56, 8d, $1125, $3339, $3407, 0.44 | $3737 | 0.55/0.56/0.56, 8d, $1125, $3339 [2504.78,4330.93], $3407, 0.44 | +1994 | +0 | eod 3339, intraday 26 | - |
| flex_dll#1 | hm2-squeeze-tf5#28|pm m20K0L600S0T0P1500 | 0.36/0.37/0.37, 8d, $649, $1734, $1856, 0.63 | $2034 | 0.36/0.37/0.37, 8d, $649, $1734 [703.59,2970.46], $1856, 0.63 | +271 | +0 | eod 1741, intraday 1202 | - |
| flex_dll#2 | fp-donchian-tf15#10|pm m20K0L300S0T1P1000 | 0.55/0.62/0.62, 13d, $863, $1612, $2092, 0.38 | $1949 | 0.55/0.62/0.62, 13d, $863, $1612 [1078.02,2135.53], $2092, 0.38 | +790 | -0 | eod 1612, intraday 1273 | - |
| pro_dll#1 | fp-donchian-tf15#10|pm m30K0L600S0T0P1500 | 0.40/0.44/0.44, 12d, $863, $1996, $2583, 0.56 | $1994 | 0.40/0.44/0.44, 12d, $863, $1996 [1131.72,2891.85], $2583, 0.56 | +950 | +0 | eod 1996, intraday 1520 | - |
| pro_dll#2 | fp-donchian-tf15#13|pm m20K0L300S0T1P1000 | 0.42/0.57/0.57, 15d, $803, $1881, $2687, 0.43 | $2423 | 0.42/0.57/0.57, 15d, $803, $1881 [1217.95,2595.87], $2687, 0.43 | +855 | -0 | eod 1881, intraday 1431 | - |
| pro_nodll#1 | hm-orb-tf5#10|mid m40K1000L300S0T0P1000 | 0.61/0.61/0.61, 4d, $1107, $5426, $5688, 0.39 | $3140 | 0.61/0.61/0.61, 4d, $1107, $5426 [3652.68,8071.02], $5688, 0.39 | +1525 | -0 | eod 5426, intraday 22 | - |
| pro_nodll#2 | hm2-straddle-tf30#32|pm m40K600L300S0T0P1000 | 0.69/0.69/0.69, 7d, $936, $4861, $5518, 0.31 | $4680 | 0.69/0.69/0.69, 7d, $936, $4861 [3667.25,6331.45], $5518, 0.31 | +2580 | -0 | eod 4861, intraday 8 | - |
| apex#1 | fp-donchian-tf15#1|nyam m30K1000L1000S0T0P1000 | 0.23/0.42/0.44, 20d, $558, $1093, $1979, 0.56 | $981 | 0.23/0.42/0.44, 20d, $558, $1093 [577.73,1808.12], $1979, 0.56 | +992 | +0 | nat 1093, opt 1093 | - |
| apex#2 | fp-tod_drift-tf5#3|pm m30K1000L300S600T0P1000 | 0.21/0.36/0.37, 18d, $477, $926, $1386, 0.63 | $951 | 0.21/0.36/0.37, 18d, $477, $926 [375.63,1191.41], $1386, 0.63 | +593 | +0 | nat 926, opt 929 | - |

## Multi-account (one eval per account, same start day; P(>=1 pass within 5 days))
| N | accounts | IS primary [eod/intraday] | HO primary [CI] | HO eod/realized/intraday | HO by-day 1..5 | E[funded] | eval cost | decay |
|---|---|---|---|---|---|---|---|---|
| 2 | lucid:best2, apex:best2 | 0.839 [0.84/0.45] | 0.839 [0.80,0.87] | 0.84/0.84/0.45 | 0.21, 0.36, 0.81, 0.84, 0.84 | 1.14 | $135 | +0.000 |
| 3 | lucid:best2, lucidpro:pf, apex:best2 | 0.916 [0.92/0.67] | 0.916 [0.89,0.94] | 0.92/0.92/0.67 | 0.37, 0.58, 0.90, 0.91, 0.92 | 1.56 | $250 | +0.000 |
| 4 | lucid:best2, lucid:single, lucidpro:best2, apex:best2 | 0.928 [0.93/0.69] | 0.928 [0.91,0.95] | 0.93/0.93/0.69 | 0.41, 0.62, 0.91, 0.92, 0.93 | 2.28 | $350 | +0.000 |
| 5 | lucid:best2, lucid:single, lucidpro:best2, lucidpro:pf, apex:best2 | 0.960 [0.96/0.81] | 0.960 [0.94,0.97] | 0.96/0.96/0.81 | 0.53, 0.75, 0.95, 0.96, 0.96 | 2.70 | $465 | +0.000 |
| 6 | lucid:best2, lucid:single, lucidpro:best2, lucidpro_nodll:single:hm-orb-tf5#10|mid@40, apex:best2, apex_eod:best2 | 0.981 [0.98/0.81] | 0.981 [0.97,0.99] | 0.98/0.98/0.81 | 0.78, 0.90, 0.98, 0.98, 0.98 | 3.41 | $525 | +0.000 |
