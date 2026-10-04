# A3 pass 2 for LucidPro 50K (+DLL $1,200 soft / no DLL) and fast-pass metrics for all four firms (in-sample 2021-09-22..2024-12-31; holdout untouched; Apex UNCONFIRMED)
Same 1719 configs / stable-cell / day-matched-control (K=10) / per-profile null method as pass 2. Grid m{10,20,30,40} x L{-,1000,2000} x K{-,1500,2000,3000} x S{-,1000,2000} x T{1,-} x TT{off,on} = 576 cells/firm; multiple-testing count 1,980,288 config-rule cells (990,144 DLL + 990,144 noDLL), each raced eod + intraday; null 398 pseudo-configs. Rule-file DLL applies automatically (day_stop 0/2000 == $1,200 on +DLL).
Rankings: eod P5 = P(pass <= 5 sessions), rolling starts, at the eod-stable cell (eod breach = Homebase). intra = intraday-breach sensitivity. Lift = P5 - day-matched control (warning label, not a filter); flag = lift > null p95.
## Null (zero-edge pseudo-configs: random seed runs thinned to each stratum's trade count; optimised over the same grid)
firm model | null n mean-lift p95(THR) max | real n, lift>THR (null expects ~5%), max real lift | null stable P5 mean p95 max
lucid          eod      | 398 +0.010 +0.072 +0.139 | 1719, 233 (14%), +0.225 | 0.336 0.568 0.624
lucid          intraday | 398 +0.011 +0.060 +0.114 | 1719, 227 (13%), +0.159 | 0.152 0.258 0.296
lucidpro       eod      | 398 +0.010 +0.069 +0.114 | 1719, 282 (16%), +0.228 | 0.278 0.377 0.415
lucidpro       intraday | 398 +0.010 +0.065 +0.106 | 1719, 296 (17%), +0.215 | 0.254 0.335 0.363
lucidpro_nodll eod      | 398 +0.010 +0.068 +0.129 | 1719, 264 (15%), +0.245 | 0.471 0.639 0.687
lucidpro_nodll intraday | 398 +0.013 +0.066 +0.104 | 1719, 259 (15%), +0.215 | 0.282 0.353 0.389
apex           eod      | 398 +0.009 +0.061 +0.126 | 1719, 286 (17%), +0.175 | 0.680 0.806 0.834
apex           intraday | 398 +0.013 +0.066 +0.118 | 1719, 271 (16%), +0.197 | 0.300 0.351 0.376
## Effect of the take rules (day_take/target_take) on LucidPro: mean stable P5 no-take sub-grid -> full grid (real | null)
lucidpro       eod      | real 0.239 -> 0.289 | null 0.227 -> 0.278
lucidpro       intraday | real 0.216 -> 0.263 | null 0.207 -> 0.254
lucidpro_nodll eod      | real 0.339 -> 0.458 | null 0.340 -> 0.471
lucidpro_nodll intraday | real 0.229 -> 0.286 | null 0.224 -> 0.282
lucidpro eod chosen cells: day_take 7%, target_take 95%, day_lock 42%, day_stop 4%, max_day_tr=1 3%, micros=40 73%
lucidpro_nodll eod chosen cells: day_take 58%, target_take 100%, day_lock 85%, day_stop 0%, max_day_tr=1 2%, micros=40 100%
## Best fast-pass numbers per firm (configs with >=300 tr and net>0; each metric's max over configs, at that config's own P5-optimised cell; eod = eod cell/eod breach, intra = intraday-optimal cell/intraday breach)
firm | eod best P1 P3 P5 | intra best P1 P3 P5 | null stable P5 mean/max eod, intra | cheapest cost per funded eod, intra ($)
lucid          | 0.000 0.638 0.675 | 0.000 0.242 0.306 | 0.336/0.624, 0.152/0.296 | 148, 327
lucidpro       | 0.233 0.407 0.445 | 0.212 0.381 0.396 | 0.278/0.415, 0.254/0.363 | 259, 291
lucidpro_nodll | 0.638 0.691 0.691 | 0.314 0.380 0.400 | 0.471/0.687, 0.282/0.389 | 203, 350
apex           | 0.806 0.836 0.836 | 0.313 0.385 0.401 | 0.680/0.834, 0.300/0.376 | 127, 172
## Top 5 LucidPro+DLL by eod P5 (fee $115; cost per funded = fee/P5 under the 5-day policy) | flag ! = lift <= null p95
id | rules | eod P1/P2/P3/P5 bust5 | lift | intra P5 same rules | intra-opt P5 (rules) | $/funded eod, intra
tod_drift|hm-tod_drift-tf5#19|mid | m40 L1000 K- S- T- TT | 0.20/0.33/0.39/0.44 0.52 | +0.090 | 0.39 | 0.39 (m40 L1000 K- S- T- TT) | 259, 291
donchian|hm-donchian-tf15#5|nyam | m30 L- K- S- T- TT | 0.19/0.33/0.39/0.44 0.53 | +0.046! | 0.39 | 0.38 (m30 L- K- S1000 T- TT) | 263, 296
donchian|hm-donchian-tf15#11|nyam | m20 L1000 K- S- T- TT | 0.17/0.28/0.35/0.43 0.50 | +0.064! | 0.39 | 0.39 (m20 L- K- S1000 T- TT) | 271, 295
donchian|hm-donchian-tf15#17|nyam | m30 L- K- S- T- TT | 0.18/0.31/0.37/0.42 0.52 | +0.049! | 0.37 | 0.37 (m30 L- K- S1000 T- TT) | 273, 308
tod_drift|hm-tod_drift-tf5#23|mid | m40 L- K- S- T- TT | 0.23/0.39/0.41/0.42 0.58 | +0.073 | 0.36 | 0.40 (m30 L- K- S1000 T- TT) | 275, 322
## Top 5 LucidPro noDLL by eod P5 (fee $140; cost per funded = fee/P5 under the 5-day policy) | flag ! = lift <= null p95
id | rules | eod P1/P2/P3/P5 bust5 | lift | intra P5 same rules | intra-opt P5 (rules) | $/funded eod, intra
first_bar_mom|hm-first_bar_mom-tf15#9|nyam | m40 L1000 K- S- T- TT | 0.64/0.68/0.69/0.69 0.31 | +0.046! | 0.29 | 0.36 (m20 L1000 K- S- T- TT) | 203, 477
first_bar_mom|hm-first_bar_mom-tf15#21|nyam | m40 L1000 K- S- T- TT | 0.63/0.68/0.69/0.69 0.31 | +0.044! | 0.29 | 0.36 (m20 L1000 K- S- T- TT) | 203, 479
first_bar_mom|hm-first_bar_mom-tf15#22|nyam | m40 L1000 K- S- T- TT | 0.64/0.68/0.69/0.69 0.31 | +0.027! | 0.27 | 0.36 (m20 L- K- S1000 T- TT) | 203, 520
first_bar_mom|hm-first_bar_mom-tf15#10|nyam | m40 L1000 K- S- T- TT | 0.64/0.68/0.69/0.69 0.31 | +0.025! | 0.27 | 0.36 (m20 L- K- S1000 T- TT) | 203, 518
first_bar_mom|hm-first_bar_mom-tf15#11|nyam | m40 L1000 K- S- T- TT | 0.64/0.68/0.69/0.69 0.31 | +0.023! | 0.27 | 0.36 (m20 L- K- S1000 T- TT) | 203, 520
Shortlist counts above null p95 (eod lift) among each firm's top 40 by eod P5: lucid 7/40, lucidpro 11/40, lucidpro_nodll 3/40, apex 2/40
Caveats: single in-sample window, holdout untouched; take rules assume the trade's MFE was reached before its exit; shortlist_all ranks by eod P5 (not lift): the eod breach model lets intraday drawdowns recover, so eod P5 overstates what an intraday-trailing rule would allow (see intra columns); a large share of high-P5 configs is explained by the zero-edge null (compare null max P5); P5 windows overlap (block-bootstrap CI); null P1/P3 not computed; LucidPro activation assumed $0; Apex UNCONFIRMED.
Reading P1/P2/P3: cells are chosen for P5, not for speed. A day_take <= the $3,000 target flattens a day just below target (take fill at the MFE touch, less 1 tick/contract), so those cells need >= 2 days (P1 = 0); Lucid Flex has a 2-day minimum (P1 = 0 always). Fast-pass-optimal cells (max P1/P3) were not searched separately.
