# NQ funded search (500 config x firm pairs full-grid of 6415; 2021-09-22..2024-12-31; 60-session lives, rolling starts)
Metrics: P(>=1 payout by 20/40/60d) | med days to 1st payout | E[1st cheque] gross | E$ to trader by 40d / 60d | P(bust before 1st payout). Primary = E$40d, stable cell (min of own, median of neighbours). Top lists: <=2 per (family, session).
Breach: Lucid realized (bounds eod/intraday); Apex pess primary (MFE-before-MAE, extreme), nat/opt bounds shown. APEX UNCONFIRMED; Flex+DLL $1,200 assumed.
## Flex  (model realized; screened 1283 cfgs coarse, 100 full)
1. straddle/tf30/pm [hm2-straddle-tf30#32] m40K600L300S0T0P1500 | P20/40/60 61%/62%/62% med 7d chq $1064 | E$40 3330 [2563,4259] E$60 3365 | bust-pre 38% | lift1806 alt:3330/41
2. straddle/tf30/pm [hm2-straddle-tf30#28] m40K600L300S0T0Pmax | P20/40/60 55%/56%/56% med 8d chq $1125 | E$40 3339 [2526,4321] E$60 3407 | bust-pre 44% | lift1949 alt:3339/26
3. first_bar_mom/tf15/mid [hm-first_bar_mom-tf15#10] m40K400L300S0T0P1500 | P20/40/60 57%/57%/57% med 11d chq $881 | E$40 3180 [1923,4063] E$60 3304 | bust-pre 43% | lift614 alt:3180/4
4. straddle/tf30/nyam [hm2-straddle-tf30#21] m40K400L300S0T0P1500 | P20/40/60 59%/59%/59% med 8d chq $911 | E$40 2830 [2211,3668] E$60 2830 | bust-pre 41% | lift495 alt:2830/0
5. straddle/tf30/mid [hm2-straddle-tf30#20] m40K600L300S0T0P1000 | P20/40/60 59%/59%/59% med 5d chq $837 | E$40 2664 [2140,3386] E$60 2664 | bust-pre 41% | lift506 alt:2664/16
## Flex+DLL1200*  (model realized; screened 1283 cfgs coarse, 100 full)
1. squeeze/tf5/pm [hm2-squeeze-tf5#28] m20K0L600S0T0P1500 | P20/40/60 36%/37%/37% med 8d chq $649 | E$40 1734 [694,2745] E$60 1856 | bust-pre 63% | lift248 alt:1741/1202
2. donchian/tf15/pm [fp-donchian-tf15#10] m20K0L300S0T1P1000 | P20/40/60 55%/62%/62% med 13d chq $863 | E$40 1612 [1109,2173] E$60 2092 | bust-pre 38% | lift739 alt:1612/1273
3. orb/tf5/london [fp-orb-tf5#12] m20K1000L300S0T0P1000 | P20/40/60 57%/60%/60% med 9d chq $665 | E$40 1508 [995,1929] E$60 1535 | bust-pre 40% | lift751 alt:1511/1083
4. squeeze/tf5/nyam [hm2-squeeze-tf5#32] m20K0L600S0T0P1000 | P20/40/60 33%/33%/33% med 8d chq $584 | E$40 1445 [685,2622] E$60 1552 | bust-pre 67% | lift524 alt:1453/1020
5. orb/tf5/london [fp-orb-tf5#14] m20K0L300S0T0P1000 | P20/40/60 37%/37%/37% med 7d chq $621 | E$40 1415 [776,2012] E$60 1445 | bust-pre 63% | lift638 alt:1418/991
## Pro DLL  (model realized; screened 1283 cfgs coarse, 100 full)
1. donchian/tf15/pm [fp-donchian-tf15#10] m30K0L300S0T1P1000 | P20/40/60 46%/49%/49% med 9d chq $665 | E$40 2099 [1252,3002] E$60 2608 | bust-pre 51% | lift905 alt:2099/1408
2. donchian/tf15/pm [fp-donchian-tf15#13] m30K0L600S0T0P1500 | P20/40/60 40%/44%/44% med 11d chq $856 | E$40 1934 [1266,2525] E$60 2395 | bust-pre 56% | lift779 alt:2052/1320
3. orb/tf5/london [fp-orb-tf5#12] m40K1000L300S0T0P500 | P20/40/60 43%/43%/43% med 6d chq $353 | E$40 1883 [1032,2685] E$60 2063 | bust-pre 57% | lift766 alt:1883/920
4. orb/tf5/nyam [fp-orb-tf5#3] m40K0L300S0T0P1000 | P20/40/60 37%/41%/41% med 11d chq $600 | E$40 1837 [913,2911] E$60 2312 | bust-pre 59% | lift1090 alt:1837/1465
5. vwap_flip/tf5/nyam [fp-vwap_flip-tf5#12] m40K0L300S0T1P500 | P20/40/60 37%/37%/37% med 6d chq $302 | E$40 1720 [1089,2591] E$60 1793 | bust-pre 63% | lift245 alt:1720/881
## Pro noDLL  (model realized; screened 1283 cfgs coarse, 100 full)
1. orb/tf5/mid [hm-orb-tf5#10] m40K1000L300S0T0P1000 | P20/40/60 61%/61%/61% med 4d chq $1107 | E$40 5426 [3524,8027] E$60 5688 | bust-pre 39% | lift1561 alt:5426/22
2. straddle/tf30/pm [hm2-straddle-tf30#32] m40K600L300S0T0P1000 | P20/40/60 69%/69%/69% med 7d chq $936 | E$40 4861 [3706,6234] E$60 5518 | bust-pre 31% | lift2455 alt:4861/8
3. straddle/tf30/pm [hm2-straddle-tf30#28] m40K600L300S0T0P1000 | P20/40/60 67%/67%/67% med 7d chq $920 | E$40 4871 [3780,6246] E$60 5574 | bust-pre 33% | lift2543 alt:4871/13
4. first_bar_mom/tf15/mid [hm-first_bar_mom-tf15#10] m40K600L300S0T0P1000 | P20/40/60 65%/65%/65% med 8d chq $892 | E$40 4678 [2658,6051] E$60 5549 | bust-pre 35% | lift1036 alt:4678/0
5. squeeze/tf5/mid [hm2-squeeze-tf5#20] m40K600L300S0T0P1000 | P20/40/60 61%/61%/61% med 6d chq $830 | E$40 4524 [2675,6810] E$60 5135 | bust-pre 39% | lift879 alt:4704/5
## Apex PA (UNCONF.)  (model pess; screened 888 cfgs coarse, 100 full)
1. donchian/tf15/nyam [fp-donchian-tf15#1] m30K1000L1000S0T0P1000 | P20/40/60 23%/42%/44% med 20d chq $558 | E$40 1093 [610,1893] E$60 1979 | bust-pre 56% | lift998 alt:1093/1093 cut0.0% mae0% clean
2. tod_drift/tf5/pm [fp-tod_drift-tf5#3] m30K1000L300S600T0P1000 | P20/40/60 21%/36%/37% med 18d chq $477 | E$40 926 [354,1182] E$60 1386 | bust-pre 63% | lift608 alt:926/929 cut0.0% mae0% clean
3. ema_pullback/tf5/nyam [fp-ema_pullback-tf5#3] m30K0L300S600T1P500 | P20/40/60 25%/35%/35% med 15d chq $274 | E$40 732 [321,1093] E$60 1076 | bust-pre 65% | lift304 alt:732/793 cut0.0% mae0% clean
4. donchian/tf15/nyam [fp-donchian-tf15#2] m30K0L1000S1000T0P1000 | P20/40/60 15%/32%/36% med 22d chq $598 | E$40 796 [333,1234] E$60 1292 | bust-pre 63% | lift601 alt:796/796 cut0.0% mae0% clean
5. tema_slope/tf5/london [fp-tema_slope-tf5#3] m30K1000L300S600T1P500 | P20/40/60 28%/36%/36% med 13d chq $287 | E$40 713 [386,1210] E$60 946 | bust-pre 64% | lift220 alt:713/716 cut0.0% mae0% clean
## Frontier (best cell per objective, any config; E$40 / P20 / med days)
Flex: E$40 max 3196 (P20 61%) | P20 max 79% (straddle/pm, E$40 2077) | fastest med 5d at P60 59% (E$40 2664)
Flex+DLL1200*: E$40 max 1620 (P20 36%) | P20 max 67% (orb/london, E$40 1321) | fastest med 5d at P60 53% (E$40 777)
Pro DLL: E$40 max 2056 (P20 46%) | P20 max 53% (donchian/pm, E$40 1791) | fastest med 9d at P60 51% (E$40 2094)
Pro noDLL: E$40 max 5370 (P20 61%) | P20 max 75% (first_bar_mom/mid, E$40 4252) | fastest med 3d at P60 69% (E$40 5342)
Apex PA (UNCONF.): E$40 max 1022 (P20 23%) | P20 max 31% (tod_drift/pm, E$40 848) | fastest med 29d at P60 55% (E$40 566)
## Null reference (random-control pseudo-configs thinned to candidate strata, same full search; score_E$40 | P20)
Flex: null n=60 E$40 mean 1038 p95 1819 max 2028 | P20 mean 38% p95 53% max 58% | real best 3196; 100/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 792 max 2015
Flex+DLL1200*: null n=60 E$40 mean 661 p95 1008 max 1146 | P20 mean 30% p95 46% max 52% | real best 1620; 95/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 569 max 1107
Pro DLL: null n=60 E$40 mean 673 p95 1109 max 1710 | P20 mean 22% p95 31% max 37% | real best 2056; 97/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 641 max 1983
Pro noDLL: null n=60 E$40 mean 1500 p95 2935 max 3602 | P20 mean 37% p95 54% max 60% | real best 5370; 100/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 1143 max 2721
Apex PA (UNCONF.): null n=30 E$40 mean 228 p95 510 max 523 | P20 mean 7% p95 16% max 17% | real best 1022; 14/100 full-grid cfgs above null p95 | WF OOS null (n=11) mean 153 max 441
## Walk-forward (top 10 per firm, 2022Q4-2024Q3 test quarters, trailing-12m selection, stitched OOS)
Flex: OOS E$40 median 2169 (IS on same starts 2267), best 3753; OOS P40 median 52%, med days 8, bust-pre 48%; 7/10 above null OOS max
Flex+DLL1200*: OOS E$40 median 1398 (IS on same starts 1591), best 2034; OOS P40 median 42%, med days 8, bust-pre 58%; 9/10 above null OOS max
Pro DLL: OOS E$40 median 1504 (IS on same starts 1871), best 2154; OOS P40 median 36%, med days 8, bust-pre 64%; 1/10 above null OOS max
Pro noDLL: OOS E$40 median 3177 (IS on same starts 3707), best 4853; OOS P40 median 56%, med days 6, bust-pre 44%; 9/10 above null OOS max
Apex PA (UNCONF.): OOS E$40 median 468 (IS on same starts 812), best 1070; OOS P40 median 24%, med days 16, bust-pre 72%; 7/10 above null OOS max
## Eval + funded economics: E[net $ per eval purchase] = P(pass<=5d, primary model) x E$60d funded - fee - P(pass) x activation
Flex (fee $100+act $0): best eval P5 69% x E$60 3365 = 2227.8 | same-config best 1962.6 (P5 61%, E$60 3407) | WF: P5 65% x OOS E$60 med 2303 = 1397.1
Flex+DLL1200* (fee $100+act $0): best eval P5 69% x E$60 1856 = 1184.2 | same-config best 847.1 (P5 59%, E$60 1617) | WF: P5 65% x OOS E$60 med 1466 = 853.0
Pro DLL (fee $115+act $0): best eval P5 48% x E$60 2608 = 1123.7 | same-config best 787.1 (P5 40%, E$60 2244) | WF: P5 44% x OOS E$60 med 1607 = 596.0
Pro noDLL (fee $140+act $0): best eval P5 71% x E$60 5688 = 3878.1 | same-config best 3767.2 (P5 69%, E$60 5688) | WF: P5 66% x OOS E$60 med 3477 = 2165.1
Apex PA (UNCONF.) (fee $35+act $85): best eval P5 42% x E$60 1979 = 758.6 | same-config best 657.1 (P5 37%, E$60 1979) | WF: P5 42% x OOS E$60 med 673 = 214.0
Caveats: Apex pess ordering extreme; Apex rules/fees UNCONFIRMED; Flex DLL $1,200 + activation $0 assumed; payout EOD-only, 2-day disbursement ignored; eval->funded uses eval P5 (primary model) at the eval-side best cell; WF/stability computed on overlapping rolling starts (CIs are block bootstraps).
