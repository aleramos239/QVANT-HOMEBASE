# Scorer validation on the IN-SAMPLE window (same code; not holdout results)
Window 2021-09-22..2024-12-31 (825 sessions, 821 rolling 5-day starts); mode insample; manifest sha256 1ee2d901870bd380...; no re-tuning, every number is the frozen finalist scored by the frozen code.
In-sample validation: no 2025+ data read.
Columns: IS = frozen in-sample (2021-09-22..2024-12-31, primary model) | WF = in-sample walk-forward OOS | HO = holdout. P1/P2/P3/P5 = P(pass <= k days), bust5 = P(bust within 5 days); bounds eod/realized/intraday; lift = P5 - day-matched random control (same days, same rules); decay = HO P5 - IS P5.

## 60% criterion per firm (P(pass <= 5d) >= 0.60, primary model; Apex firms: rule-compliant finalists only)
- apex: best eligible finalist apex:pf P5 0.381 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: Y/Y/n; passing: none
- apex_eod: best eligible finalist apex_eod:pf P5 0.370 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucid: best eligible finalist lucid:pf P5 0.532 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucidpro: best eligible finalist lucidpro:fast_pf P5 0.437 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: n/n/n; passing: none
- lucidpro_nodll: best eligible finalist lucidpro_nodll:single P5 0.577 -> primary FAIL (CI lower bound >= 0.60: no); bounds eod/realized/intraday: Y/n/n; passing: none

## lucid (lucid-flex-50k@2026-09-27; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucid:single | p5_single+speed_p3 | hm-straddle-tf15#21/pm/40 | L750 K1500 S- T- TT | 0.49 | 0.47 | 0.00/0.00/0.41/0.49 [0.44,0.56] | 0.47 | 0.49/0.49/0.14 | +0.032 [-0.01,0.09] | +0.000 | fail |
| lucid:best2 | best2 | hm-straddle-tf15#8/mid/40 (38% of executed); fp-straddle-tf30#15/nyam/20 (62% of executed) | L1000 K1500 S- T- TT | 0.52 | 0.48 | 0.00/0.00/0.42/0.52 [0.46,0.57] | 0.46 | 0.52/0.52/0.27 | +0.163 [0.11,0.21] | +0.000 | fail |
| lucid:pf | portfolio_ge3 | hm-straddle-tf15#34/pm/40 (17% of executed); fp-straddle-tf30#15/nyam/20 (52% of executed); hm-straddle-tf15#10/mid/40 (31% of executed) | L750 K1500 S- T- TT | 0.53 | 0.48 | 0.00/0.00/0.50/0.53 [0.48,0.58] | 0.47 | 0.58/0.53/0.27 | +0.081 [0.03,0.13] | +0.000 | fail |
| lucid:fast_single | fast_single | fp-straddle-tf30#14/nyam/40 | L750 K- S- T- TT | 0.37 | n/a | 0.00/0.30/0.33/0.37 [0.33,0.41] | 0.62 | 0.37/0.37/0.26 | +0.110 [0.06,0.16] | +0.000 | fail |
| lucid:fast_pf | fast_portfolio | fp-straddle-tf30#14/nyam/40 (69% of executed); fp-straddle-tf30#14/pm/40 (31% of executed) | L1000 K- S- T- TT | 0.38 | n/a | 0.00/0.31/0.36/0.38 [0.34,0.42] | 0.62 | 0.46/0.38/0.26 | +0.099 [0.05,0.14] | +0.000 | fail |
| lucid:fx_single | flexext_single | hm-straddle-tf15#21/pm/40 | L750 K1560 S- T- TT | 0.51 | n/a | 0.00/0.39/0.43/0.51 [0.46,0.57] | 0.46 | 0.51/0.51/0.21 | +0.036 [-0.01,0.10] | +0.000 | fail |
| lucid:fx_best2 | flexext_best2 | hm-straddle-tf15#21/pm/40 (49% of executed); hm-ema_pullback-tf5#11/mid/10 (51% of executed) | L750 K1560 S- T- TT | 0.52 | n/a | 0.00/0.29/0.44/0.52 [0.46,0.58] | 0.46 | 0.52/0.52/0.24 | +0.057 [0.01,0.12] | +0.000 | fail |
| lucid:fxfast_best2 | flexext_fast_best2 | hm-straddle-tf15#21/pm/40 (36% of executed); hm-ema_pullback-tf5#10/mid/40 (64% of executed) | L- K1560 S- T- TT | 0.51 | n/a | 0.00/0.45/0.48/0.51 [0.47,0.57] | 0.49 | 0.58/0.51/0.21 | +0.007 [-0.04,0.07] | +0.000 | fail |
| lucid:fastpass | fastpass | fp-straddle-tf30#14/nyam/40 | L750 K1500 S- T- TT | 0.41 | 0.41 | 0.00/0.00/0.36/0.41 [0.37,0.45] | 0.58 | 0.41/0.41/0.18 | +0.110 [0.06,0.16] | +0.000 | fail |

## lucidpro (lucid-pro-50k@2026-09-27b; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucidpro:single | p5_single | hm-straddle-tf15#10/pm/30 | L1000 K- S- T- TT | 0.41 | 0.41 | 0.17/0.28/0.35/0.41 [0.35,0.46] | 0.54 | 0.41/0.41/0.36 | +0.081 [0.03,0.13] | +0.000 | fail |
| lucidpro:best2 | best2 | hm-straddle-tf15#10/pm/30 (13% of executed); hm-tod_drift-tf15#13/nyam/40 (87% of executed) | L1000 K- S- T- TT | 0.42 | 0.36 | 0.21/0.34/0.39/0.42 [0.36,0.46] | 0.57 | 0.42/0.42/0.37 | +0.075 [0.01,0.13] | +0.000 | fail |
| lucidpro:pf | portfolio_ge3 | hm-straddle-tf15#10/pm/20 (13% of executed); hm-tod_drift-tf15#13/nyam/40 (83% of executed); hm-donchian-tf15#10/pm/20 (5% of executed) | L1000 K- S- T- TT | 0.41 | 0.40 | 0.20/0.34/0.39/0.41 [0.36,0.46] | 0.58 | 0.41/0.41/0.37 | +0.078 [0.02,0.13] | +0.000 | fail |
| lucidpro:fast_single | fast_single+mix_single+mix_single+mix_single+mix_single+speed_p3 | hm-tod_drift-tf15#13/nyam/40 | L1000 K- S- T- TT | 0.40 | n/a | 0.19/0.32/0.37/0.40 [0.34,0.45] | 0.57 | 0.40/0.40/0.36 | +0.067 [0.00,0.12] | +0.000 | fail |
| lucidpro:fast_pf | fast_portfolio | hm-tod_drift-tf15#13/nyam/40 (72% of executed); hm-tod_drift-tf5#23/mid/40 (28% of executed) | L- K- S- T- TT | 0.44 | n/a | 0.24/0.39/0.42/0.44 [0.38,0.48] | 0.56 | 0.44/0.44/0.38 | +0.066 [0.01,0.12] | +0.000 | fail |
| lucidpro:speed_p1 | speed_p1 | hm-straddle-tf15#19/pm/40 | L1000 K- S- T- TT | 0.38 | 0.42 | 0.19/0.31/0.35/0.38 [0.33,0.43] | 0.61 | 0.38/0.38/0.32 | +0.029 [-0.02,0.09] | +0.000 | fail |
| lucidpro:fastpass | fastpass | fp-rsi2-tf5#15/nyam/40 | L- K- S- T- TT | 0.40 | 0.34 | 0.17/0.30/0.36/0.40 [0.34,0.45] | 0.57 | 0.40/0.40/0.36 | +0.023 [-0.04,0.08] | -0.000 | fail |

## lucidpro_nodll (lucid-pro-50k-no-dll@2026-09-27b; primary realized)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lucidpro_nodll:single | p5_single | hm-straddle-tf15#35/pm/40 | L1000 K- S- T- TT | 0.58 | 0.58 | 0.32/0.46/0.53/0.58 [0.53,0.64] | 0.40 | 0.58/0.58/0.34 | +0.048 [-0.00,0.12] | +0.000 | fail |
| lucidpro_nodll:best2 | best2 | hm-straddle-tf15#35/pm/40 (45% of executed); hm-first_bar_mom-tf30#10/mid/40 (55% of executed) | L1000 K- S- T- TT | 0.54 | 0.50 | 0.35/0.49/0.52/0.54 [0.50,0.59] | 0.46 | 0.61/0.54/0.34 | +0.042 [0.00,0.09] | +0.000 | fail |
| lucidpro_nodll:pf | portfolio_ge3 | hm-donchian-tf15#10/pm/30 (32% of executed); hm-first_bar_mom-tf30#10/mid/40 (48% of executed); hm-first_bar_mom-tf30#10/pm/10 (21% of executed) | L1000 K- S- T- TT | 0.52 | 0.48 | 0.30/0.45/0.50/0.52 [0.48,0.58] | 0.47 | 0.57/0.52/0.33 | +0.060 [0.02,0.11] | +0.000 | fail |
| lucidpro_nodll:fast_single | fast_single | hm-straddle-tf15#23/pm/40 | L1000 K- S- T- TT | 0.56 | n/a | 0.35/0.48/0.54/0.56 [0.52,0.62] | 0.42 | 0.56/0.56/0.34 | +0.035 [-0.01,0.09] | +0.000 | fail |
| lucidpro_nodll:fast_pf | fast_portfolio | hm-straddle-tf15#23/pm/40 (39% of executed); hm-straddle-tf15#23/nyam/40 (61% of executed) | L1000 K- S- T- TT | 0.52 | n/a | 0.42/0.51/0.52/0.52 [0.49,0.56] | 0.48 | 0.62/0.52/0.33 | -0.011 [-0.05,0.03] | +0.000 | fail |
| lucidpro_nodll:single:hm-donchian-tf15#10|pm@40 | mix_single+mix_single+mix_single+mix_single | hm-donchian-tf15#10/pm/40 | L1000 K- S- T- TT | 0.57 | n/a | 0.23/0.38/0.46/0.57 [0.52,0.62] | 0.34 | 0.58/0.57/0.37 | +0.076 [0.02,0.14] | -0.000 | fail |
| lucidpro_nodll:speed_p1 | speed_p1 | hm-straddle-tf15#23/nyam/40 | L1000 K- S- T- TT | 0.50 | 0.46 | 0.38/0.47/0.49/0.50 [0.46,0.55] | 0.49 | 0.50/0.50/0.32 | -0.019 [-0.06,0.03] | +0.000 | fail |
| lucidpro_nodll:speed_p3 | speed_p3 | hm-straddle-tf15#22/pm/40 | L1000 K- S- T- TT | 0.56 | 0.55 | 0.35/0.48/0.54/0.56 [0.52,0.62] | 0.42 | 0.56/0.56/0.34 | +0.037 [-0.01,0.10] | +0.000 | fail |
| lucidpro_nodll:fastpass | fastpass | fp-straddle-tf30#15/pm/40 | L1000 K3000 S- T- TT | 0.47 | n/a | 0.00/0.37/0.43/0.47 [0.42,0.51] | 0.52 | 0.47/0.47/0.28 | +0.062 [0.01,0.12] | +0.000 | fail |

## apex (apex-legacy-50k@2026-09-27b; primary intraday; UNCONFIRMED)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| apex:single | p5_single | fp-ema_pullback-tf5#15/mid/60 | L1000 K- S1000 T- TT | 0.34 | 0.33 | 0.17/0.29/0.33/0.34 [0.29,0.38] | 0.65 | 0.35/0.35/0.34 | +0.056 [-0.00,0.11] | +0.000 | fail |
| apex:best2 | best2 | fp-ema_pullback-tf5#15/mid/60 (96% of executed); hm-first_bar_mom-tf30#0/pm/40 (4% of executed) | L1000 K- S1000 T1 TT | 0.34 | 0.34 | 0.17/0.29/0.33/0.34 [0.29,0.38] | 0.65 | 0.35/0.35/0.34 | +0.058 [0.00,0.11] | +0.000 | fail |
| apex:pf | portfolio_ge3 | hm-first_bar_mom-tf30#2/pm/40 (29% of executed); hm-vwap_z-tf5#27/mid/60 (36% of executed); hm-first_bar_mom-tf30#17/mid/40 (35% of executed) | L1000 K- S- T- TT | 0.38 | 0.36 | 0.19/0.30/0.35/0.38 [0.33,0.42] | 0.61 | 0.54/0.51/0.38 | +0.111 [0.06,0.16] | +0.001 | fail |
| apex:fast_single | fast_single | fp-ema_pullback-tf5#15/mid/60 | L1000 K- S- T- TT | 0.33 | n/a | 0.26/0.32/0.33/0.33 [0.30,0.37] | 0.67 | 0.58/0.55/0.33 | +0.031 [-0.00,0.08] | +0.000 | fail |
| apex:fast_pf | fast_portfolio | fp-ema_pullback-tf5#15/mid/60 (61% of executed); hm-vwap_flip-tf15#2/pm/60 (39% of executed) | L1000 K- S- T- TT | 0.33 | n/a | 0.29/0.33/0.33/0.33 [0.30,0.37] | 0.67 | 0.61/0.53/0.33 | +0.035 [0.00,0.08] | +0.000 | fail |
| apex:speed_p1 | speed_p1 | fp-rsi2-tf5#12/nyam/100 | L- K- S- T- TT | 0.31 | 0.35 | 0.27/0.31/0.31/0.31 [0.28,0.35] | 0.69 | 0.64/0.64/0.31 | -0.048 [-0.09,-0.01] | -0.000 | fail |
| apex:speed_p3 | speed_p3 | fp-vwap_flip-tf5#10/pm/60 | L- K- S- T- TT | 0.32 | n/a | 0.15/0.29/0.32/0.32 [0.27,0.36] | 0.68 | 0.52/0.46/0.32 | -0.013 [-0.06,0.03] | -0.000 | fail |
| apex:p5_single_compliant | p5_single_compliant | hm-donchian-tf15#2/pm/60 | L- K- S- T- TT | 0.36 | 0.35 | 0.21/0.30/0.33/0.36 [0.32,0.40] | 0.63 | 0.56/0.53/0.36 | +0.041 [0.00,0.08] | -0.000 | fail |
| apex:fastpass | fastpass | fp-ema_pullback-tf5#15/mid/60 | L- K- S1000 T- TT | 0.34 | n/a | 0.17/0.29/0.33/0.34 [0.29,0.38] | 0.65 | 0.35/0.35/0.34 | +0.055 [-0.00,0.11] | -0.000 | fail |

## apex_eod (apex-eod-50k@2026-09-27b; primary intraday; UNCONFIRMED)
| finalist | roles | members (cfg/sess/micros) | rules | IS P5 | WF P5 | HO P1/P2/P3/P5 [CI] | bust5 | eod/rlz/intra P5 | lift [CI] | decay | crit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| apex_eod:single | p5_single+fast_single+speed_p3+fastpass | fp-vwap_flip-tf5#15/pm/60 | L1000 K- S- T- TT | 0.36 | 0.36 | 0.20/0.34/0.35/0.36 [0.31,0.41] | 0.64 | 0.36/0.36/0.36 | +0.063 [0.02,0.11] | +0.000 | fail |
| apex_eod:best2 | best2+fast_portfolio | fp-tod_drift-tf5#15/pm/60 (12% of executed); fp-ema_pullback-tf5#15/mid/60 (88% of executed) | L1000 K- S- T- TT | 0.35 | 0.35 | 0.20/0.34/0.35/0.35 [0.31,0.40] | 0.64 | 0.35/0.35/0.35 | +0.052 [0.00,0.10] | +0.000 | fail |
| apex_eod:pf | portfolio_ge3 | hm-donchian-tf15#6/pm/60 (0% of executed); hm-donchian-tf15#19/nyam/40 (66% of executed); fp-tod_drift-tf5#15/mid/60 (34% of executed) | L1000 K- S- T- TT | 0.37 | 0.37 | 0.19/0.32/0.35/0.37 [0.32,0.41] | 0.62 | 0.37/0.37/0.37 | +0.059 [0.00,0.11] | +0.000 | fail |
| apex_eod:speed_p1 | speed_p1 | fp-tema_slope-tf5#11/london/60 | L- K- S- T- TT | 0.35 | n/a | 0.20/0.32/0.34/0.35 [0.31,0.39] | 0.65 | 0.35/0.35/0.35 | +0.008 [-0.03,0.05] | -0.000 | fail |
| apex_eod:p5_single_compliant | p5_single_compliant | screen-donchian-tf5/pm/60 | L- K- S- T- TT | 0.37 | 0.40 | 0.17/0.29/0.33/0.37 [0.31,0.42] | 0.62 | 0.37/0.37/0.37 | +0.094 [0.05,0.14] | +0.000 | fail |

## Funded finalists (rolling 60-session lives, primary breach model; payout policy as frozen)
| finalist | config / cell | IS P20/40/60, med d, E[1st chq], E$40, E$60, bust-pre | WF E$40 | HO P20/40/60, med d, E[1st chq], E$40 [CI], E$60, bust-pre | lift E$40 | decay E$40 | alt models E$40 | flags |
|---|---|---|---|---|---|---|---|---|
| flex#1 | hm-donchian-tf15#8|pm m40K1000L600S0T1P500 | 0.46/0.47/0.47, 8d, $742, $1618, $1643, 0.53 | $1185 | 0.46/0.47/0.47, 8d, $742, $1618 [1007.21,2492.89], $1643, 0.53 | +457 | -0 | eod 1618, intraday 542 | - |
| flex#2 | hm-donchian-tf15#9|pm m40K1000L300S0T0P1000 | 0.43/0.43/0.43, 8d, $738, $1624, $1659, 0.57 | $1174 | 0.43/0.43/0.43, 8d, $738, $1624 [1020.92,2497.36], $1659, 0.57 | +746 | -0 | eod 1696, intraday 347 | - |
| flex_dll#1 | fp-tod_drift-tf5#13|nyam m30K0L300S0T0Pmax | 0.31/0.35/0.35, 11d, $697, $1605, $1683, 0.65 | $1826 | 0.31/0.35/0.35, 11d, $697, $1605 [897.53,2495.74], $1683, 0.65 | +1233 | +0 | eod 1605, intraday 1121 | - |
| flex_dll#2 | fp-tod_drift-tf5#10|nyam m30K0L300S0T0P1500 | 0.36/0.37/0.37, 9d, $646, $1516, $1542, 0.63 | $1658 | 0.36/0.37/0.37, 9d, $646, $1516 [889.41,2273.29], $1542, 0.63 | +967 | -0 | eod 1530, intraday 1171 | - |
| pro_dll#1 | fp-tod_drift-tf5#10|nyam m30K0L300S0T0P1000 | 0.38/0.39/0.39, 6d, $534, $2093, $2148, 0.61 | $2590 | 0.38/0.39/0.39, 6d, $534, $2093 [1267.31,3134.80], $2148, 0.61 | +1410 | -0 | eod 2093, intraday 1108 | - |
| pro_dll#2 | fp-ema_pullback-tf5#12|pm m40K0L300S0T1P500 | 0.33/0.33/0.33, 6d, $289, $1671, $1792, 0.67 | $1005 | 0.33/0.33/0.33, 6d, $289, $1671 [842.75,2954.37], $1792, 0.67 | +17 | -0 | eod 1671, intraday 911 | - |
| pro_nodll#1 | hm-donchian-tf15#9|pm m40K1000L300S0T0P1000 | 0.49/0.49/0.49, 6d, $797, $2723, $2814, 0.51 | $1497 | 0.49/0.49/0.49, 6d, $797, $2723 [1366.68,4962.04], $2814, 0.51 | +1310 | -0 | eod 2790, intraday 189 | - |
| pro_nodll#2 | hm-donchian-tf15#8|pm m40K1000L300S0T0P1000 | 0.49/0.49/0.49, 6d, $797, $2722, $2813, 0.51 | $1496 | 0.49/0.49/0.49, 6d, $797, $2722 [1365.19,4962.00], $2813, 0.51 | +873 | -0 | eod 2785, intraday 317 | - |
| apex#1 | fp-ema_pullback-tf5#3|pm m30K0L300S1000T1P500 | 0.13/0.17/0.18, 17d, $134, $382, $488, 0.82 | $146 | 0.13/0.17/0.18, 17d, $134, $382 [136.09,762.04], $488, 0.82 | +330 | +0 | nat 382, opt 382 | - |
| apex#2 | hm-ema_pullback-tf5#3|london m20K1000L300S300T0P1000 | 0.06/0.13/0.15, 23d, $232, $269, $335, 0.83 | $80 | 0.06/0.13/0.15, 23d, $232, $269 [65.99,589.73], $335, 0.83 | +224 | +0 | nat 269, opt 279 | mae30_cuts_0.006 |
| flex#h1 | hm-straddle-tf15#11|pm m10K0L300S0T0P1000 | 0.40/0.44/0.45, 9d, $687, $1352, $1658, 0.55 | $698 | 0.40/0.44/0.45, 9d, $687, $1352 [789.47,1797.89], $1658, 0.55 | +723 | +0 | eod 1352, intraday 980 | - |
| flex#h2 | hm-straddle-tf15#10|pm m10K0L300S0T0P1000 | 0.40/0.44/0.45, 9d, $682, $1357, $1653, 0.55 | $827 | 0.40/0.44/0.45, 9d, $682, $1357 [780.75,1863.54], $1653, 0.55 | +581 | -0 | eod 1357, intraday 923 | - |
| flex_dll#h2 | hm-straddle-tf15#32|pm m20K0L300S0T0P1000 | 0.38/0.38/0.38, 8d, $611, $1302, $1393, 0.62 | $1194 | 0.38/0.38/0.38, 8d, $611, $1302 [853.45,1963.68], $1393, 0.62 | +860 | -0 | eod 1302, intraday 974 | - |
| pro_dll#h1 | hm-vwap_flip-tf5#34|pm m10K1000L300S0T0P500 | 0.29/0.34/0.34, 11d, $304, $1123, $1504, 0.66 | $883 | 0.29/0.34/0.34, 11d, $304, $1123 [424.03,2200.62], $1504, 0.66 | +608 | +0 | eod 1188, intraday 1022 | - |
| pro_dll#h2 | hm-vwap_flip-tf5#22|pm m10K1000L300S0T0P1000 | 0.31/0.40/0.41, 14d, $561, $1223, $1453, 0.59 | $818 | 0.31/0.40/0.41, 14d, $561, $1223 [540.21,2467.80], $1453, 0.59 | +865 | +0 | eod 1263, intraday 995 | - |
| pro_nodll#h1 | hm-donchian-tf15#10|pm m40K1000L300S0T0P1000 | 0.49/0.49/0.49, 6d, $797, $2723, $2814, 0.51 | $1497 | 0.49/0.49/0.49, 6d, $797, $2723 [1366.68,4962.04], $2814, 0.51 | +1340 | -0 | eod 2790, intraday 189 | - |
| pro_nodll#h2 | hm-donchian-tf15#11|pm m40K1000L300S0T0P1000 | 0.49/0.49/0.49, 6d, $797, $2723, $2814, 0.51 | $1497 | 0.49/0.49/0.49, 6d, $797, $2723 [1366.68,4962.04], $2814, 0.51 | +1312 | -0 | eod 2790, intraday 177 | - |
| apex#h2 | hm-vwap_z-tf5#3|london m20K1000L300S0T1P1000 | 0.05/0.08/0.10, 22d, $149, $226, $354, 0.87 | $35 | 0.05/0.08/0.10, 22d, $149, $226 [1.65,626.55], $354, 0.87 | +220 | +0 | nat 226, opt 226 | mae30_cuts_0.002 |

## Multi-account (one eval per account, same start day; P(>=1 pass within 5 days))
| N | accounts | IS primary [eod/intraday] | HO primary [CI] | HO eod/realized/intraday | HO by-day 1..5 | E[funded] | eval cost | decay |
|---|---|---|---|---|---|---|---|---|
| 2 | lucid:pf, apex:pf | 0.704 [0.80/0.54] | 0.705 [0.66,0.75] | 0.80/0.77/0.54 | 0.19, 0.30, 0.68, 0.70, 0.71 | 0.91 | $135 | +0.001 |
| 3 | lucid:pf, lucidpro:best2, apex:best2 | 0.825 [0.85/0.70] | 0.825 [0.79,0.86] | 0.85/0.82/0.70 | 0.35, 0.53, 0.79, 0.82, 0.82 | 1.29 | $250 | +0.000 |
| 4 | lucid:pf, lucid:single, lucidpro:fast_single, apex:best2 | 0.895 [0.90/0.74] | 0.895 [0.86,0.93] | 0.90/0.90/0.74 | 0.33, 0.52, 0.85, 0.89, 0.90 | 1.77 | $350 | +0.000 |
| 5 | lucid:pf, lucid:single, lucidpro:fast_single, lucidpro:single, apex:best2 | 0.928 [0.93/0.81] | 0.928 [0.90,0.95] | 0.93/0.93/0.81 | 0.44, 0.65, 0.89, 0.92, 0.93 | 2.17 | $465 | +0.000 |
| 6 | lucid:pf, lucid:single, lucidpro:fast_single, lucidpro_nodll:single:hm-donchian-tf15#10|pm@40, apex:best2, apex_eod:pf | 0.966 [0.97/0.88] | 0.966 [0.95,0.98] | 0.97/0.97/0.88 | 0.57, 0.79, 0.93, 0.95, 0.97 | 2.71 | $525 | +0.000 |
| Lo2 | lucid:pf, lucidpro_nodll:single | 0.781 [0.79/0.52] | 0.781 [0.74,0.82] | 0.79/0.78/0.52 | 0.32, 0.46, 0.74, 0.77, 0.78 | 1.11 | $240 | +0.000 |
| Lo3 | lucid:pf, lucidpro:best2, lucidpro_nodll:single | 0.873 [0.88/0.70] | 0.873 [0.84,0.90] | 0.88/0.87/0.70 | 0.44, 0.63, 0.84, 0.86, 0.87 | 1.53 | $355 | +0.000 |
| Lo4 | lucid:pf, lucid:fxfast_best2, lucidpro:best2, lucidpro_nodll:single:hm-donchian-tf15#10|pm@40 | 0.920 [0.93/0.76] | 0.920 [0.90,0.94] | 0.93/0.92/0.76 | 0.38, 0.73, 0.88, 0.90, 0.92 | 2.03 | $455 | +0.000 |
| Lo5 | lucid:pf, lucid:fxfast_best2, lucidpro:best2, lucidpro_nodll:single:hm-donchian-tf15#10|pm@40, lucidpro_nodll:best2 | 0.944 [0.95/0.82] | 0.944 [0.93,0.96] | 0.95/0.94/0.82 | 0.53, 0.82, 0.92, 0.93, 0.94 | 2.57 | $595 | +0.000 |
| Lo6 | lucid:pf, lucid:fxfast_best2, lucid:fx_single, lucidpro:fast_single, lucidpro_nodll:single:hm-donchian-tf15#10|pm@40, lucidpro_nodll:pf | 0.960 [0.96/0.84] | 0.960 [0.95,0.98] | 0.96/0.96/0.84 | 0.51, 0.85, 0.93, 0.95, 0.96 | 3.05 | $695 | +0.000 |
