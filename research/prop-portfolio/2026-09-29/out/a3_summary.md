# A3 rules search (in-sample 2021-09-22..2024-12-31, offline; APEX = UNCONFIRMED rules)
Tested: 252 configs (>=300 trades) x 2 firms = 604,800 config-rule cells (lucid 960 + apex 1,440 per config, full grid, no coarse-to-fine), each raced under eod + intraday breach (1,209,600 evals); null 200 pseudo-configs (480,000 cells); K=10 day-matched controls per lift.
Stable cell = max of median P5 over the cell + its +-1-step neighbours on every axis; lift = P5 - mean control P5 at identical rules. Cell key: m=micros L=day_lock S=day_stop T=max_day_tr A=after_loss (- = off).
## Null threshold (95th pct of stable lift over random pseudo-configs; thinned random seeds, controls from other seeds)
firm model | null n mean med p95(THR) max | real n, lift>0, lift>THR (null expects ~5%) | real max lift
lucid eod      | 200 +0.011 +0.008 +0.050 +0.102 | 252, 180, 29 | +0.114
lucid intraday | 200 +0.011 +0.008 +0.046 +0.074 | 252, 187, 21 | +0.092
apex  eod      | 200 +0.022 +0.020 +0.088 +0.128 | 252, 180, 26 | +0.139
apex  intraday | 200 +0.025 +0.021 +0.072 +0.104 | 252, 214, 26 | +0.116
## Optimised zero-edge baseline (best STABLE P5 a random strategy reaches with the same search)
firm model | thinned pseudo-configs (300-2500 tr): mean p95 max | natural-frequency seed runs: mean max (n) [random | tod_drift-profile]
lucid eod      | 0.061 0.153 0.252 | 0.112 0.264 (120) | 0.042 0.086 (60)
lucid intraday | 0.052 0.127 0.180 | 0.086 0.190 (120) | 0.037 0.072 (60)
apex  eod      | 0.393 0.488 0.610 | 0.451 0.627 (120) | 0.335 0.465 (60)
apex  intraday | 0.235 0.294 0.342 | 0.250 0.342 (120) | 0.210 0.278 (60)
## Top 20 LUCID by eod stable lift (* = above THR +0.050); intraday alongside
fam/tf/sess n | eod stable cell | P5 [CI] bust5 days | ctrl lift | intra P5 lift (bust5)
*rsi2/1/mid 2457 | m40 L750 S- T- A- | 0.247 [0.196,0.312] 0.67 3d | +0.114 | 0.185 +0.092 (0.72)
*tema_slope/1/mid 2459 | m40 L750 S- T- A- | 0.236 [0.199,0.269] 0.63 3d | +0.090 | 0.185 +0.087 (0.69)
*ema_pullback/5/pm 1288 | m40 L1000 S- T- A- | 0.160 [0.114,0.208] 0.66 4d | +0.084 | 0.129 +0.064 (0.73)
*ema_pullback/5/london 2288 | m40 L750 S- T- A- | 0.262 [0.212,0.308] 0.66 3d | +0.083 | 0.169 +0.053 (0.79)
*ema_ribbon/1/mid 2291 | m40 L1000 S- T- A- | 0.201 [0.157,0.253] 0.70 3d | +0.080 | 0.151 +0.065 (0.71)
*vwap_flip/5/london 1929 | m40 L1000 S- T- A- | 0.229 [0.186,0.270] 0.67 3d | +0.078 | 0.150 +0.038 (0.82)
*vwap_flip/1/mid 2182 | m40 L750 S- T- A- | 0.194 [0.146,0.238] 0.70 3d | +0.068 | 0.147 +0.083 (0.61)
*tema_slope/5/london 2364 | m40 L750 S- T- A- | 0.258 [0.214,0.305] 0.66 3d | +0.067 | 0.181 +0.063 (0.77)
*ema_pullback/5/nyam 1686 | m40 L750 S- T- A- | 0.183 [0.145,0.222] 0.73 3d | +0.067 | 0.132 +0.057 (0.83)
*donchian/1/mid 2457 | m40 L750 S- T- A- | 0.195 [0.147,0.233] 0.71 4d | +0.066 | 0.138 +0.055 (0.73)
*squeeze/1/mid 1640 | m40 L750 S- T- A- | 0.166 [0.119,0.217] 0.65 4d | +0.065 | 0.130 +0.054 (0.72)
*tod_drift/5/mid 820 | m40 L- S- T- A- | 0.141 [0.105,0.184] 0.66 4d | +0.065 | 0.130 +0.076 (0.62)
*vwap_flip/5/mid 1163 | m20 L1000 S- T- A- | 0.100 [0.071,0.136] 0.64 4d | +0.063 | 0.073 +0.044 (0.81)
*rsi2/15/london 1890 | m30 L1250 S- T- A- | 0.177 [0.141,0.218] 0.67 3d | +0.062 | 0.136 +0.049 (0.76)
*ema_pullback/1/pm 2431 | m40 L1000 S- T- A- | 0.223 [0.178,0.272] 0.65 4d | +0.059 | 0.168 +0.051 (0.75)
*vwap_z/1/mid 2304 | m40 L750 S- T- A- | 0.191 [0.145,0.225] 0.71 3d | +0.059 | 0.134 +0.037 (0.74)
*vwap_flip/5/pm 1286 | m30 L1000 S- T- A- | 0.122 [0.088,0.158] 0.68 4d | +0.058 | 0.084 +0.032 (0.79)
*rsi2/5/mid 1582 | m20 L1000 S- T- A- | 0.116 [0.083,0.150] 0.67 4d | +0.058 | 0.101 +0.059 (0.64)
*vwap_flip/1/pm 2248 | m40 L1000 S- T- A- | 0.206 [0.157,0.253] 0.68 4d | +0.057 | 0.172 +0.067 (0.79)
*tema_slope/5/mid 1360 | m20 L1000 S- T- A- | 0.095 [0.065,0.133] 0.71 4d | +0.055 | 0.080 +0.048 (0.62)
## Top 20 APEX (UNCONFIRMED) by eod stable lift (* = above THR +0.088); intraday alongside
fam/tf/sess n | eod stable cell | P5 [CI] bust5 days | ctrl lift | intra P5 lift (bust5)
*rsi2/5/mid 1582 | m100 L1000 S- T- A- | 0.501 [0.469,0.535] 0.50 1d | +0.139 | 0.264 +0.095 (0.73)
*squeeze/1/asia 1466 | m100 L2000 S- T- A- | 0.275 [0.218,0.341] 0.55 2d | +0.127 | 0.217 +0.101 (0.68)
*ema_pullback/5/asia 1240 | m100 L1000 S- T- A- | 0.434 [0.376,0.490] 0.54 2d | +0.124 | 0.292 +0.078 (0.70)
*ema_pullback/5/mid 1097 | m100 L- S- T3 A- | 0.459 [0.423,0.498] 0.54 1d | +0.124 | 0.261 +0.076 (0.69)
*vwap_flip/1/mid 2182 | m100 L1000 S- T- A- | 0.587 [0.542,0.624] 0.41 1d | +0.117 | 0.340 +0.106 (0.66)
*vwap_flip/5/mid 1163 | m100 L1000 S- T- A- | 0.445 [0.409,0.491] 0.56 1d | +0.113 | 0.246 +0.094 (0.74)
*ib/5/nyam 495 | m100 L- S- T- A- | 0.474 [0.409,0.531] 0.48 2d | +0.112 | 0.248 +0.098 (0.63)
*vwap_band/5/mid 962 | m100 L1000 S- T- A- | 0.477 [0.434,0.521] 0.51 1d | +0.110 | 0.258 +0.084 (0.63)
*vwap_flip/15/london 1207 | m100 L1000 S- T- A- | 0.493 [0.446,0.526] 0.51 1d | +0.108 | 0.289 +0.063 (0.69)
*vwap_z/5/mid 1000 | m100 L1000 S- T- A- | 0.476 [0.434,0.525] 0.52 1d | +0.107 | 0.262 +0.076 (0.65)
*lon_break/1/nyam 794 | m100 L- S1500 T- A- | 0.376 [0.336,0.434] 0.62 1d | +0.106 | 0.295 +0.116 (0.70)
*tema_slope/5/mid 1360 | m100 L1000 S- T- A- | 0.436 [0.396,0.484] 0.56 1d | +0.104 | 0.240 +0.054 (0.71)
*ema_pullback/5/pm 1288 | m100 L1000 S- T- A- | 0.498 [0.456,0.546] 0.50 1d | +0.103 | 0.285 +0.084 (0.67)
*ema_pullback/15/london 917 | m100 L- S- T3 A- | 0.467 [0.417,0.514] 0.53 1d | +0.103 | 0.269 +0.050 (0.69)
*vwap_flip/5/london 1929 | m100 L1000 S- T- A- | 0.570 [0.530,0.605] 0.43 1d | +0.103 | 0.264 +0.018 (0.74)
*vwap_flip/5/pm 1286 | m100 L1000 S- T- A- | 0.480 [0.443,0.514] 0.52 1d | +0.102 | 0.276 +0.061 (0.72)
*tema_slope/15/london 1591 | m100 L1000 S- T- A- | 0.504 [0.469,0.540] 0.50 1d | +0.102 | 0.295 +0.065 (0.67)
*rsi2/1/mid 2457 | m100 L1000 S- T- A- | 0.598 [0.551,0.652] 0.40 1d | +0.101 | 0.328 +0.092 (0.67)
*supertrend/1/asia 2348 | m100 L1500 S- T- A- | 0.276 [0.216,0.340] 0.66 2d | +0.100 | 0.190 +0.062 (0.79)
*tema_slope/1/mid 2459 | m100 L- S- T- A- | 0.613 [0.571,0.652] 0.39 1d | +0.099 | 0.317 +0.072 (0.68)
## Configs above THR by family / tf / session
lucid eod [total 29] fam: ema_pullback:7, vwap_flip:6, rsi2:3, tema_slope:3, donchian:2, tod_drift:2, vwap_band:2, vwap_z:2, ema_ribbon:1, squeeze:1
  tf: 5:15, 1:13, 15:1; sess: mid:14, pm:7, london:5, asia:2, nyam:1
lucid intraday [total 21] fam: ema_pullback:5, rsi2:3, tema_slope:3, donchian:2, vwap_flip:2, ema_ribbon:1, first_bar_mom:1, squeeze:1, straddle:1, tod_drift:1, vwap_band:1
  tf: 5:10, 1:9, 15:2; sess: mid:11, london:4, pm:3, nyam:2, asia:1
apex eod [total 26] fam: ema_pullback:6, vwap_flip:6, tema_slope:4, rsi2:2, ema_ribbon:1, ib:1, lon_break:1, squeeze:1, supertrend:1, tod_drift:1, vwap_band:1, vwap_z:1
  tf: 5:16, 1:7, 15:3; sess: mid:10, london:7, asia:4, nyam:3, pm:2
apex intraday [total 26] fam: ema_pullback:4, ib:4, tod_drift:4, donchian:2, rsi2:2, tema_slope:2, vwap_flip:2, lon_break:1, squeeze:1, straddle:1, supertrend:1, vwap_band:1, vwap_z:1
  tf: 1:11, 5:11, 15:2, 30:2; sess: mid:9, nyam:7, pm:4, london:3, asia:3
