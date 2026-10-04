# A3 pass 2: heat-map cells x session + screen configs, with day_take / target_take (in-sample 2021-09-22..2024-12-31; APEX = UNCONFIRMED)
Multiple-testing count: 1719 configs (1613 heat-map cell x session, 106 screen) x rule cells: lucid 1,320,192 + apex 1,650,240 = 2,970,432 config-rule cells, each raced eod + intraday (5,940,864 evals); null 398 pseudo-configs (687,744 cells). Lift = P5 - mean of K=10 day-matched controls at identical rules.
Grids: Lucid m{10,20,30,40} x L{-,750,1000,1500} x K(day_take){-,1000,1250,1500} x S{-,1000,2000} x T{1,-} x TT(target_take){off,on}; Apex m{20..100} x L{-,1000,2000} x K{-,1500,2000,3000} x S{-,1000,2000,3000} x T{1,-} x TT. target_stop always on (TT supersedes).
Stable cell = max over cells of the median P5 of the cell + its +-1-step neighbours (all 6 axes). eod row = eod-optimal rules (xi = same rules under intraday breach); intraday row = its own optimum.
## Null (pseudo-configs = random seed runs thinned to the stratum's median trade count, one per exit-profile x session, x2 reps; controls from the other seeds)
firm model | null n mean p95(THR) MAX | real n, lift>0, lift>THR (null expects ~5%), max real lift | null stable P5 mean p95 max
lucid eod      | 398 +0.010 +0.072 +0.139 | 1719, 987, 233 (14%), +0.225 | 0.336 0.568 0.624
lucid intraday | 398 +0.011 +0.060 +0.114 | 1719, 1129, 227 (13%), +0.159 | 0.152 0.258 0.296
apex  eod      | 398 +0.009 +0.061 +0.126 | 1719, 1094, 286 (17%), +0.175 | 0.680 0.806 0.834
apex  intraday | 398 +0.013 +0.066 +0.118 | 1719, 1234, 271 (16%), +0.197 | 0.300 0.351 0.376
## Effect of day_take / target_take (pass-1-like sub-grid = no take rules vs full grid), and vs pass 1
firm model | real mean stable P5 no-take -> full | null mean stable P5 no-take -> full | best real P5 (net>0, >=300tr) | pass-1 best (screen) | null max pass-1 -> pass-2 | null mean pass-1 -> pass-2
lucid eod      | 0.113 -> 0.371 | 0.091 -> 0.336 | 0.675 | 0.289 | 0.252 -> 0.624 | 0.061 -> 0.336
lucid intraday | 0.084 -> 0.176 | 0.068 -> 0.152 | 0.306 | 0.185 | 0.180 -> 0.296 | 0.052 -> 0.152
apex  eod      | 0.451 -> 0.662 | 0.451 -> 0.680 | 0.836 | 0.644 | 0.610 -> 0.834 | 0.393 -> 0.680
apex  intraday | 0.252 -> 0.309 | 0.243 -> 0.300 | 0.401 | 0.340 | 0.342 -> 0.376 | 0.235 -> 0.300
lucid eod chosen cells using: day_take 99%, target_take 100%, day_lock 93%, day_stop 0%, max_day_tr=1 0%
apex eod chosen cells using: day_take 50%, target_take 100%, day_lock 91%, day_stop 0%, max_day_tr=1 1%
Pass-1 above-null-threshold screen configs always kept: 52 (34 with net<=0 at 1 NQ, flagged net_le0; excluded from the shortlist by the net>0 filter). Quick-P5 dropping not needed (no config-firm dropped).
## Shortlist LUCID: 40 configs (eod lift > THR +0.072, intraday lift > 0 at the same rules, >=300 tr, net>0); top 10
id | rules | eod P5 [CI] bust5 | intra P5 (lift) | lift eod | base | 22/23/24 P5 | tr
vwap_band|hm-vwap_band-tf5#11|london | m40 L750 K1250 S- T- TT | 0.627 [0.580,0.692] 0.36 | 0.121 (+0.051) | +0.225 | 0.523 | 0.70/0.60/0.59 | 1419
vwap_band|hm-vwap_band-tf5#7|london | m40 L750 K1250 S- T- TT | 0.549 [0.501,0.616] 0.43 | 0.213 (+0.111) | +0.206 | 0.485 | 0.65/0.48/0.52 | 1853
vwap_band|hm-vwap_band-tf5#10|london | m40 L750 K1250 S- T- TT | 0.630 [0.582,0.694] 0.35 | 0.125 (+0.031) | +0.203 | 0.544 | 0.70/0.60/0.60 | 1575
vwap_band|hm-vwap_band-tf5#3|mid | m40 L750 K1250 S- T- TT | 0.559 [0.502,0.618] 0.42 | 0.110 (+0.066) | +0.185 | 0.481 | 0.67/0.45/0.60 | 1629
vwap_z|hm-vwap_z-tf5#11|london | m40 L750 K1250 S- T- TT | 0.571 [0.525,0.629] 0.41 | 0.105 (+0.040) | +0.180 | 0.523 | 0.63/0.53/0.60 | 1532
tod_drift|hm-tod_drift-tf5#16|asia | m40 L750 K1500 S- T- TT | 0.234 [0.179,0.284] 0.38 | 0.210 (+0.159) | +0.178 | 0.060 | 0.31/0.11/0.23 | 820
tod_drift|hm-tod_drift-tf5#10|asia | m40 L750 K1500 S- T- TT | 0.225 [0.174,0.276] 0.41 | 0.201 (+0.145) | +0.165 | 0.060 | 0.30/0.10/0.23 | 817
vwap_z|hm-vwap_z-tf5#7|london | m40 L750 K1250 S- T- TT | 0.533 [0.482,0.598] 0.46 | 0.169 (+0.075) | +0.159 | 0.485 | 0.65/0.47/0.51 | 1995
vwap_z|hm-vwap_z-tf5#3|mid | m40 L750 K1250 S- T- TT | 0.546 [0.498,0.594] 0.45 | 0.116 (+0.077) | +0.158 | 0.481 | 0.64/0.49/0.56 | 1842
vwap_z|hm-vwap_z-tf5#10|london | m40 L750 K1250 S- T- TT | 0.571 [0.526,0.629] 0.41 | 0.111 (+0.034) | +0.157 | 0.544 | 0.63/0.53/0.60 | 1716
## Shortlist APEX (UNCONFIRMED): 40 configs (eod lift > THR +0.061, intraday lift > 0 at the same rules, >=300 tr, net>0); top 10
id | rules | eod P5 [CI] bust5 | intra P5 (lift) | lift eod | base | 22/23/24 P5 | tr
vwap_band|hm-vwap_band-tf5#7|london | m100 L1000 K1500 S- T- TT | 0.752 [0.709,0.800] 0.25 | 0.018 (+0.011) | +0.170 | 0.705 | 0.81/0.71/0.75 | 1853
tod_drift|hm-tod_drift-tf5#16|asia | m100 L1000 K- S- T- TT | 0.491 [0.445,0.533] 0.51 | 0.337 (+0.078) | +0.160 | 0.342 | 0.53/0.41/0.49 | 820
vwap_band|hm-vwap_band-tf5#11|london | m100 L1000 K1500 S- T- TT | 0.797 [0.762,0.843] 0.20 | 0.011 (+0.008) | +0.157 | 0.731 | 0.86/0.78/0.78 | 1419
tod_drift|hm-tod_drift-tf5#22|asia | m100 L1000 K- S- T- TT | 0.480 [0.438,0.520] 0.52 | 0.306 (+0.045) | +0.146 | 0.342 | 0.52/0.43/0.52 | 820
vwap_band|hm-vwap_band-tf5#3|mid | m100 L1000 K1500 S- T- TT | 0.771 [0.731,0.817] 0.23 | 0.002 (+0.001) | +0.145 | 0.714 | 0.86/0.70/0.79 | 1629
vwap_flip|screen-vwap_flip-tf15|london | m100 L1000 K1500 S- T- TT | 0.704 [0.638,0.756] 0.29 | 0.021 (+0.010) | +0.143 | 0.627 | 0.78/0.68/0.68 | 1207
ema_pullback|screen-ema_pullback-tf5|asia | m100 L- K3000 S- T- TT | 0.547 [0.496,0.597] 0.43 | 0.309 (+0.098) | +0.141 | 0.446 | 0.58/0.55/0.57 | 1240
vwap_band|hm-vwap_band-tf5#10|london | m100 L1000 K1500 S- T- TT | 0.797 [0.762,0.843] 0.20 | 0.015 (+0.008) | +0.139 | 0.739 | 0.86/0.78/0.78 | 1575
vwap_band|hm-vwap_band-tf5#6|london | m100 L1000 K1500 S- T- TT | 0.752 [0.709,0.801] 0.25 | 0.021 (+0.006) | +0.137 | 0.711 | 0.81/0.71/0.75 | 2053
tema_slope|screen-tema_slope-tf5|london | m100 L1000 K1500 S- T- TT | 0.721 [0.678,0.767] 0.28 | 0.055 (+0.005) | +0.136 | 0.633 | 0.74/0.75/0.65 | 2364
lucid: shortlist median intraday-model P5 at the eod rules 0.156 vs eod 0.516 (eod-optimal rules lean on EOD-only breach); intraday-optimal rules for the same configs: median P5 0.249
## Best lucid INTRADAY-model configs (own optimum, lift > THR_intra +0.060, net>0): 77; top 5
tod_drift|hm-tod_drift-tf5#16|asia | m40 L750 K1500 S- T- TT | intra P5 0.210 [0.163,0.251] bust5 0.49 lift +0.159 | 820 tr
vwap_z|hm-vwap_z-tf5#3|mid | m20 L750 K1500 S- T- TT | intra P5 0.290 [0.252,0.337] bust5 0.70 lift +0.151 | 1842 tr
tod_drift|hm-tod_drift-tf5#10|asia | m40 L750 K1500 S- T- TT | intra P5 0.201 [0.157,0.245] bust5 0.53 lift +0.145 | 817 tr
vwap_band|hm-vwap_band-tf5#3|mid | m20 L750 K1500 S- T- TT | intra P5 0.264 [0.218,0.311] bust5 0.71 lift +0.120 | 1629 tr
vwap_band|hm-vwap_band-tf5#11|london | m20 L750 K1500 S- T- TT | intra P5 0.275 [0.234,0.326] bust5 0.70 lift +0.119 | 1419 tr
apex: shortlist median intraday-model P5 at the eod rules 0.111 vs eod 0.727 (eod-optimal rules lean on EOD-only breach); intraday-optimal rules for the same configs: median P5 0.350
## Best apex INTRADAY-model configs (own optimum, lift > THR_intra +0.066, net>0): 104; top 5
tod_drift|hm-tod_drift-tf5#16|asia | m60 L- K- S2000 T- TT | intra P5 0.369 [0.323,0.414] bust5 0.60 lift +0.197 | 820 tr
tod_drift|hm-tod_drift-tf5#22|asia | m60 L1000 K- S3000 T- TT | intra P5 0.352 [0.307,0.398] bust5 0.62 lift +0.178 | 820 tr
tod_drift|hm-tod_drift-tf5#4|pm | m20 L- K- S3000 T- TT | intra P5 0.380 [0.340,0.421] bust5 0.56 lift +0.146 | 813 tr
vwap_band|hm-vwap_band-tf5#7|mid | m20 L1000 K- S3000 T- TT | intra P5 0.376 [0.333,0.419] bust5 0.62 lift +0.137 | 1082 tr
vwap_z|hm-vwap_z-tf5#11|london | m20 L1000 K- S3000 T- TT | intra P5 0.357 [0.314,0.408] bust5 0.62 lift +0.135 | 1532 tr
## Shortlist composition (family / tf / session)
lucid: fam {'vwap_band': 14, 'vwap_z': 6, 'tod_drift': 4, 'vwap_flip': 4, 'ema_pullback': 3, 'rsi2': 3, 'ib': 3, 'tema_slope': 2} tf {'5': 31, '15': 5, '1': 2, '30': 2} sess {'london': 18, 'mid': 13, 'asia': 4, 'pm': 3, 'nyam': 2}
apex: fam {'vwap_band': 12, 'tod_drift': 7, 'ema_pullback': 5, 'donchian': 5, 'vwap_flip': 3, 'vwap_z': 3, 'rsi2': 3, 'tema_slope': 1} tf {'5': 29, '15': 4, '30': 5, '1': 2} sess {'london': 17, 'asia': 6, 'mid': 7, 'pm': 6, 'nyam': 4}
Caveats: single in-sample window, holdout untouched; take rules assume the trade's MFE was reached before its exit (pessimistic vs MAE/day_stop); 1 pseudo-config per stratum x2 reps; P5 windows overlap (block-bootstrap CI); Apex payout/rules UNCONFIRMED; nearest-profile pools (tod_drift exit_bars != 6) are flagged in pool_flag; cost_pass_mix uses RT cost < 3% of the median stop risk at the config's NQ/micro mix.
