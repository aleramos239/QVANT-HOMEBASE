# ES a3 pass-1 style rules search (screen configs, take rules, 5 firms, primary breach models)
Configs: 252 family x tf x session with >= 300 trades (80 screen runs, tf 1/5/15/30, sess all split offline), 6300 rows = config x firm x cellset. Null: 2700 rows (108 pseudo-configs). Machinery = a3p3 (a3p3_screen.py): rule grid per firm incl. day_take / target_take, stable cell (median of +-1-step neighbours), K=10 day-matched random controls at identical rules, moving-block CI. PRIMARY model: Lucid* = realized, Apex* = intraday (Apex UNCONFIRMED everywhere). Research window 2021-09-22..2024-12-31, no 2025+.
Apex compliance filter applied to apex / apex_eod rankings: comp_oco=0 (no OCO / both-side orders: orb, straddle, lon_break, ib excluded) and comp_target=1 (has a target so stop <= 5x target: tod_drift time-exit excluded). Non-compliant rows stay in the CSV, flagged. The 30% MAE rule / threshold-as-stop are not modelled in this screen pass.
## Null (optimised zero-edge random, stable P5 at primary model) and lift threshold
- lucid (realized): null mean 0.165, max 0.387 (n=108); lift p95 threshold +0.062
- lucidpro (realized): null mean 0.205, max 0.359 (n=108); lift p95 threshold +0.057
- lucidpro_nodll (realized): null mean 0.255, max 0.490 (n=108); lift p95 threshold +0.075
- apex (intraday): null mean 0.257, max 0.343 (n=108); lift p95 threshold +0.061
- apex_eod (intraday): null mean 0.222, max 0.324 (n=108); lift p95 threshold +0.058
## Best stable P(pass<=5d) per firm (primary model; P1/P3 at that same cell; lift vs day-matched random at identical rules)
### lucid: 252 configs, 39 above null-lift threshold, 1 of those net>0 under the rules
| config | n | net1 | P5 | P1 | P3 | bust5 | lift | P5 eod/real/intra | rules |
|---|---|---|---|---|---|---|---|---|---|
| straddle/30/pm | 816 | -464 | 0.430 | 0.000 | 0.343 | 0.546 | +0.051 | 0.43/0.43/0.18 | 40mc lock750 take1500 stop0 mx0 tt1 |
| orb/30/pm | 815 | -9760 | 0.421 | 0.000 | 0.350 | 0.553 | +0.044 | 0.42/0.42/0.17 | 40mc lock750 take1500 stop0 mx0 tt1 |
| tod_drift/30/mid* | 823 | -10267 | 0.406 | 0.000 | 0.340 | 0.563 | +0.079 | 0.41/0.41/0.15 | 40mc lock750 take1500 stop0 mx0 tt1 |
| straddle/15/pm | 816 | +1861 | 0.404 | 0.000 | 0.322 | 0.569 | +0.029 | 0.40/0.40/0.19 | 40mc lock750 take1500 stop0 mx0 tt1 |
| orb/15/pm | 815 | -16198 | 0.398 | 0.000 | 0.325 | 0.562 | +0.019 | 0.40/0.40/0.19 | 40mc lock750 take1500 stop0 mx0 tt1 |
| straddle/30/mid | 823 | -32704 | 0.391 | 0.000 | 0.308 | 0.571 | +0.059 | 0.39/0.39/0.12 | 40mc lock750 take1500 stop0 mx0 tt1 |
### lucidpro: 252 configs, 34 above null-lift threshold, 1 of those net>0 under the rules
| config | n | net1 | P5 | P1 | P3 | bust5 | lift | P5 eod/real/intra | rules |
|---|---|---|---|---|---|---|---|---|---|
| rsi2/5/nyam* | 1900 | -50962 | 0.395 | 0.180 | 0.343 | 0.570 | +0.133 | 0.40/0.39/0.36 | 40mc lock0 take0 stop0 mx0 tt1 |
| donchian/5/pm* | 1320 | -15455 | 0.390 | 0.162 | 0.335 | 0.548 | +0.092 | 0.39/0.39/0.36 | 40mc lock0 take0 stop0 mx0 tt1 |
| straddle/30/pm* | 816 | -464 | 0.387 | 0.177 | 0.336 | 0.597 | +0.062 | 0.39/0.39/0.34 | 40mc lock1000 take0 stop0 mx0 tt1 |
| tod_drift/30/pm | 816 | -1764 | 0.375 | 0.189 | 0.345 | 0.605 | +0.023 | 0.38/0.38/0.32 | 40mc lock0 take0 stop0 mx0 tt1 |
| straddle/15/pm | 816 | +1861 | 0.359 | 0.179 | 0.325 | 0.622 | +0.035 | 0.36/0.36/0.32 | 40mc lock1000 take0 stop0 mx0 tt1 |
| tod_drift/15/pm | 816 | -452 | 0.354 | 0.140 | 0.295 | 0.558 | +0.008 | 0.36/0.35/0.30 | 40mc lock1000 take0 stop0 mx0 tt1 |
### lucidpro_nodll: 252 configs, 25 above null-lift threshold, 3 of those net>0 under the rules
| config | n | net1 | P5 | P1 | P3 | bust5 | lift | P5 eod/real/intra | rules |
|---|---|---|---|---|---|---|---|---|---|
| straddle/30/pm | 816 | -464 | 0.505 | 0.311 | 0.486 | 0.480 | +0.042 | 0.51/0.51/0.35 | 40mc lock1000 take0 stop0 mx0 tt1 |
| orb/30/pm | 815 | -9760 | 0.492 | 0.298 | 0.468 | 0.497 | +0.032 | 0.49/0.49/0.33 | 40mc lock1000 take0 stop0 mx0 tt1 |
| tod_drift/30/pm | 816 | -1764 | 0.482 | 0.324 | 0.464 | 0.507 | -0.004 | 0.48/0.48/0.34 | 40mc lock1000 take0 stop0 mx0 tt1 |
| orb/15/pm | 815 | -16198 | 0.481 | 0.285 | 0.451 | 0.507 | +0.033 | 0.48/0.48/0.33 | 40mc lock1000 take0 stop0 mx0 tt1 |
| straddle/15/pm | 816 | +1861 | 0.464 | 0.296 | 0.448 | 0.525 | +0.016 | 0.46/0.46/0.34 | 40mc lock1000 take0 stop0 mx0 tt1 |
| tod_drift/30/nyam | 823 | -24104 | 0.449 | 0.323 | 0.430 | 0.546 | +0.066 | 0.45/0.45/0.31 | 40mc lock1000 take0 stop0 mx0 tt1 |
### apex (compliant only): 186 configs, 34 above null-lift threshold, 2 of those net>0 under the rules
| config | n | net1 | P5 | P1 | P3 | bust5 | lift | P5 eod/real/intra | rules |
|---|---|---|---|---|---|---|---|---|---|
| donchian/15/pm | 500 | +27938 | 0.350 | 0.152 | 0.297 | 0.592 | +0.058 | 0.36/0.36/0.35 | 60mc lock0 take0 stop2000 mx0 tt1 |
| donchian/5/pm* | 1320 | -15455 | 0.347 | 0.225 | 0.329 | 0.647 | +0.084 | 0.45/0.45/0.35 | 60mc lock1000 take0 stop3000 mx1 tt1 |
| rsi2/5/nyam* | 1900 | -50962 | 0.345 | 0.294 | 0.341 | 0.654 | +0.094 | 0.44/0.41/0.34 | 60mc lock0 take0 stop3000 mx0 tt1 |
| donchian/30/pm | 369 | +21749 | 0.335 | 0.122 | 0.267 | 0.548 | +0.043 | 0.42/0.41/0.33 | 60mc lock1000 take0 stop3000 mx0 tt1 |
| vwap_flip/15/london* | 1241 | -36702 | 0.328 | 0.149 | 0.305 | 0.664 | +0.116 | 0.42/0.40/0.33 | 60mc lock1000 take0 stop3000 mx0 tt1 |
| vwap_z/5/mid* | 1083 | -14320 | 0.328 | 0.207 | 0.313 | 0.671 | +0.091 | 0.44/0.43/0.33 | 60mc lock0 take0 stop3000 mx0 tt1 |
### apex_eod (compliant only): 186 configs, 31 above null-lift threshold, 1 of those net>0 under the rules
| config | n | net1 | P5 | P1 | P3 | bust5 | lift | P5 eod/real/intra | rules |
|---|---|---|---|---|---|---|---|---|---|
| donchian/5/pm* | 1320 | -15455 | 0.367 | 0.172 | 0.335 | 0.622 | +0.084 | 0.37/0.37/0.37 | 60mc lock0 take0 stop0 mx0 tt1 |
| rsi2/5/nyam* | 1900 | -50962 | 0.335 | 0.183 | 0.322 | 0.657 | +0.093 | 0.34/0.34/0.33 | 60mc lock0 take0 stop0 mx0 tt1 |
| donchian/15/pm | 500 | +27938 | 0.329 | 0.102 | 0.255 | 0.503 | +0.056 | 0.33/0.33/0.33 | 60mc lock0 take0 stop0 mx0 tt1 |
| rsi2/15/london* | 1949 | -51934 | 0.320 | 0.166 | 0.306 | 0.672 | +0.081 | 0.32/0.32/0.32 | 60mc lock0 take0 stop0 mx0 tt1 |
| ema_pullback/5/mid* | 1207 | -30278 | 0.311 | 0.156 | 0.295 | 0.675 | +0.095 | 0.31/0.31/0.31 | 60mc lock0 take0 stop0 mx0 tt1 |
| rsi2/30/london* | 1218 | -38097 | 0.311 | 0.143 | 0.281 | 0.666 | +0.066 | 0.31/0.31/0.31 | 60mc lock0 take0 stop0 mx0 tt1 |
(* = lift above that firm's null p95 threshold)
## Speed: best P(pass<=1d) and P(pass<=3d) at the speed-optimal stable cell (primary model)
- lucid P1: 0.000 donchian/1/asia (P5 0.000, bust5 0.006, lift P5 +0.000) 10mc lock0 take0 stop0 mx0 tt0
- lucid P3: 0.350 orb/30/pm (P5 0.421, bust5 0.553, lift P5 +0.044) 40mc lock750 take1500 stop0 mx0 tt1
- lucidpro P1: 0.189 tod_drift/30/pm (P5 0.375, bust5 0.605, lift P5 +0.023) 40mc lock1000 take0 stop0 mx0 tt1
- lucidpro P3: 0.345 tod_drift/30/pm (P5 0.375, bust5 0.605, lift P5 +0.023) 40mc lock0 take0 stop0 mx0 tt1
- lucidpro_nodll P1: 0.324 tod_drift/30/pm (P5 0.482, bust5 0.507, lift P5 -0.004) 40mc lock1000 take0 stop0 mx0 tt1
- lucidpro_nodll P3: 0.486 straddle/30/pm (P5 0.505, bust5 0.480, lift P5 +0.042) 40mc lock1000 take0 stop0 mx0 tt1
- apex P1: 0.285 rsi2/1/nyam (P5 0.295, bust5 0.705, lift P5 +0.062) 100mc lock0 take0 stop3000 mx0 tt1
- apex P3: 0.341 rsi2/5/nyam (P5 0.345, bust5 0.654, lift P5 +0.094) 60mc lock0 take0 stop3000 mx0 tt1
- apex_eod P1: 0.183 rsi2/5/nyam (P5 0.335, bust5 0.657, lift P5 +0.093) 60mc lock0 take0 stop0 mx0 tt1
- apex_eod P3: 0.335 donchian/5/pm (P5 0.367, bust5 0.622, lift P5 +0.084) 60mc lock0 take0 stop0 mx0 tt1
## Expectancy check (funded needs positive expectancy): configs >= 300 trades with net > 0 at 1 ES (before daily rules)
- donchian/15/pm: n=500 net1 $+27938 exp1 $+55.9/trade, by year 21/22/23/24: +2164/+24391/+4642/-3260
- donchian/30/pm: n=369 net1 $+21749 exp1 $+58.9/trade, by year 21/22/23/24: +3566/+19067/+2914/-3798
- vwap_flip/15/pm: n=624 net1 $+11716 exp1 $+18.8/trade, by year 21/22/23/24: -1144/+11823/+6611/-5573
- ib/30/pm: n=325 net1 $+6675 exp1 $+20.5/trade, by year 21/22/23/24: +2129/+6428/+2284/-4166
- tema_slope/30/mid: n=422 net1 $+4474 exp1 $+10.6/trade, by year 21/22/23/24: +1785/+5288/-2624/+26
- ib/15/pm: n=325 net1 $+2125 exp1 $+6.5/trade, by year 21/22/23/24: +754/+6628/-2504/-2754
- straddle/15/pm: n=816 net1 $+1861 exp1 $+2.3/trade, by year 21/22/23/24: -6518/+15316/-9930/+2992
- first_bar_mom/30/mid: n=354 net1 $+884 exp1 $+2.5/trade, by year 21/22/23/24: -930/+1862/+3556/-3604
## ES vs NQ (same machinery; NQ = pass-2 screen configs, eod model stable P5, Lucid Flex / Apex user set)
- lucid: stable P5(eod) median/max  NQ 0.415/0.610 (n=106)  vs  ES 0.176/0.430 (n=252); null mean/max NQ 0.336/0.624  ES 0.170/0.387
- apex: stable P5(eod) median/max  NQ 0.718/0.811 (n=106)  vs  ES 0.497/0.680 (n=252); null mean/max NQ 0.680/0.834  ES 0.461/0.674
