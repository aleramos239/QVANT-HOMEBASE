# ES funded summary (2026-10-01; in-sample 2021-09-22..2024-12-31; funded_search.py --pilot es: 2,787 configs x 5 variants coarse -> 500 config x variant pairs full grid (6,415 cells) + WF + null + K=8 day-matched controls)
## Verdict (user objective: high payout %, high payout, short time to first payout; fewer rules better)
- ES funded is roughly HALF of NQ: best E$ to trader by 40 days (primary Lucid realised-balance model) Pro noDLL 2.7k (NQ 5.4k), Flex 1.6k (NQ 3.3k), Pro DLL 2.1k, Flex+DLL 1.5k, Apex PA 0.4k (UNCONFIRMED; equals the zero-edge null max 379). P(payout by 20d) 29-49%, median 6-11 days, bust before first payout 51-66%.
- Same-config headline (E[net $ per eval purchase] = eval P5 x funded E$60 - fee): Pro noDLL +1,457 (donchian-tf15-pm; eval P5 .57, P20 49%, median 6d, cheque ~$800, WF OOS E$40 1,497) > Flex +670 (straddle-tf15-pm) / +575 (donchian-tf15-pm) > Flex+DLL* +572 > Pro DLL +422 > Apex +40. WF-based (OOS E$60, OOS P5): Pro noDLL +605, Flex +415, Flex+DLL* +534, Pro DLL +398, Apex -37.
- Only real ES edge = donchian PM (tester WF PF 1.16 at tf15 and tf30). Use it as the funded core; the in-sample best Flex pick (straddle-tf15-pm, tester WF -$10k) and every fp/tod_drift/vwap_flip pick are payoff-shape artefacts of the rules grid.
- LUCID BREACH RISK: every Lucid number assumes breach on realised/closed balance. Intraday (open-P&L) bound E$40: Pro noDLL donchian 2,723 -> 189 (net per purchase -69), Flex donchian 1,624 -> 347; Flex straddle 1,352 -> 980; Pro DLL vwap_flip 1,123 -> 1,022 (most robust, but lowest payout).
- Null check: real best vs zero-edge null max E$40: Flex 1,618 vs 1,302, Pro noDLL 2,700 vs 1,751, Pro DLL 2,030 vs 1,081, Flex+DLL 1,503 vs 1,037, Apex 382 vs 379. WF OOS above null OOS max: 5/10, 8/10, 8/10, 6/10 (Flex, Flex+DLL, Pro DLL, Pro noDLL), Apex 4/10 at OOS E$40 median 79.
- Apex PA: not workable on ES (P20 13%, bust-pre 82%, OOS E$40 median 79; the PA 30% MAE rule also cuts 72-85% of trades at the eval-optimal sizes).

# Funded headline: same-config eval + funded economics (E[net $ per eval purchase] = P5 x E$60 - fee - P5 x act), primary model; bounds = eod / intraday (open-P&L) breach
Columns: eval P5 prim (eod|intraday) | funded P20/P40, median days to 1st payout, E[cheque] | E$40 / E$60 (eod|intraday E$40) | bust before 1st payout | WF OOS E$40 (P40) | lift E$40 vs day-matched random | net/purchase [prim | intraday-bound]
## Flex (eval fee $100, activation $0; rule file via eval firm lucid)
- 1. straddle/tf15/pm [hm-straddle-tf15#11] eval rules m40 L750 K1500 S- T- TT P5 0.46 (0.46|0.12) | funded m10K0L300S0T0P1000 P20/P40 40%/44% med 9d chq $687 | E$40 1352 / E$60 1658 (1352|980) | bust-pre 55% | WF OOS E$40 698 (P40 27%) | lift +776 | net/purchase +670 [+46] | 1-ct net $+48,636
- 2. straddle/tf15/pm [hm-straddle-tf15#10] eval rules m40 L750 K1500 S- T- TT P5 0.46 (0.46|0.12) | funded m10K0L300S0T0P1000 P20/P40 40%/44% med 9d chq $682 | E$40 1357 / E$60 1653 (1357|923) | bust-pre 55% | WF OOS E$40 827 (P40 33%) | lift +612 | net/purchase +667 [+37] | 1-ct net $+46,398
- 3. donchian/tf15/pm [hm-donchian-tf15#9] eval rules m40 L750 K1500 S- T- TT P5 0.41 (0.42|0.13) | funded m40K1000L300S0T0P1000 P20/P40 43%/43% med 8d chq $738 | E$40 1624 / E$60 1659 (1696|347) | bust-pre 57% | WF OOS E$40 1174 (P40 48%) | lift +696 | net/purchase +575 [-53] | 1-ct net $+36,012
- edge-backed: straddle/tf15/pm [hm-straddle-tf15#11] eval rules m40 L750 K1500 S- T- TT P5 0.46 (0.46|0.12) | funded m10K0L300S0T0P1000 P20/P40 40%/44% med 9d chq $687 | E$40 1352 / E$60 1658 (1352|980) | bust-pre 55% | WF OOS E$40 698 (P40 27%) | lift +776 | net/purchase +670 [+46] | 1-ct net $+48,636
## Flex+DLL1200* (eval fee $100, activation $0; rule file via eval firm lucid)
- 1. tod_drift/tf5/nyam [fp-tod_drift-tf5#13] eval rules m40 L- K1500 S- T- TT P5 0.40 (0.40|0.28) | funded m30K0L300S0T0Pmax P20/P40 31%/35% med 11d chq $697 | E$40 1605 / E$60 1683 (1605|1121) | bust-pre 65% | WF OOS E$40 1826 (P40 42%) | lift +1251 | net/purchase +572 [+225] | 1-ct net $-7,854
- 2. straddle/tf15/pm [hm-straddle-tf15#32] eval rules m40 L750 K1500 S- T- TT P5 0.48 (0.48|0.18) | funded m20K0L300S0T0P1000 P20/P40 38%/38% med 8d chq $611 | E$40 1302 / E$60 1393 (1302|974) | bust-pre 62% | WF OOS E$40 1194 (P40 44%) | lift +874 | net/purchase +572 [+85] | 1-ct net $-13,798
- 3. straddle/tf15/pm [hm-straddle-tf15#11] eval rules m40 L750 K1500 S- T- TT P5 0.46 (0.46|0.12) | funded m10K0L300S0T0P1000 P20/P40 37%/41% med 10d chq $638 | E$40 1169 / E$60 1425 (1172|856) | bust-pre 58% | WF OOS E$40 659 (P40 32%) | lift +605 | net/purchase +561 [+27] | 1-ct net $+48,636
- edge-backed: straddle/tf15/pm [hm-straddle-tf15#11] eval rules m40 L750 K1500 S- T- TT P5 0.46 (0.46|0.12) | funded m10K0L300S0T0P1000 P20/P40 37%/41% med 10d chq $638 | E$40 1169 / E$60 1425 (1172|856) | bust-pre 58% | WF OOS E$40 659 (P40 32%) | lift +605 | net/purchase +561 [+27] | 1-ct net $+48,636
## Pro DLL (eval fee $115, activation $0; rule file via eval firm lucidpro)
- 1. vwap_flip/tf5/pm [hm-vwap_flip-tf5#34] eval rules m30 L1000 K- S- T- TT P5 0.36 (0.36|0.33) | funded m10K1000L300S0T0P500 P20/P40 29%/34% med 11d chq $304 | E$40 1123 / E$60 1504 (1188|1022) | bust-pre 66% | WF OOS E$40 883 (P40 27%) | lift +620 | net/purchase +422 [+335] | 1-ct net $+15,652
- 2. vwap_flip/tf5/pm [hm-vwap_flip-tf5#22] eval rules m40 L- K- S- T- TT P5 0.37 (0.37|0.32) | funded m10K1000L300S0T0P1000 P20/P40 31%/40% med 14d chq $561 | E$40 1223 / E$60 1453 (1263|995) | bust-pre 59% | WF OOS E$40 818 (P40 38%) | lift +887 | net/purchase +418 [+261] | 1-ct net $+24,608
- 3. vwap_flip/tf5/pm [hm-vwap_flip-tf5#35] eval rules m40 L- K- S- T- TT P5 0.35 (0.35|0.30) | funded m10K1000L300S0T0P1000 P20/P40 23%/28% med 14d chq $380 | E$40 1124 / E$60 1508 (1179|1049) | bust-pre 72% | WF OOS E$40 921 (P40 29%) | lift +611 | net/purchase +414 [+312] | 1-ct net $+18,081
- edge-backed: vwap_flip/tf5/pm [hm-vwap_flip-tf5#34] eval rules m30 L1000 K- S- T- TT P5 0.36 (0.36|0.33) | funded m10K1000L300S0T0P500 P20/P40 29%/34% med 11d chq $304 | E$40 1123 / E$60 1504 (1188|1022) | bust-pre 66% | WF OOS E$40 883 (P40 27%) | lift +620 | net/purchase +422 [+335] | 1-ct net $+15,652
## Pro noDLL (eval fee $140, activation $0; rule file via eval firm lucidpro_nodll)
- 1. donchian/tf15/pm [hm-donchian-tf15#10] eval rules m40 L1000 K- S- T- TT P5 0.57 (0.58|0.37) | funded m40K1000L300S0T0P1000 P20/P40 49%/49% med 6d chq $797 | E$40 2723 / E$60 2814 (2790|189) | bust-pre 51% | WF OOS E$40 1497 (P40 42%) | lift +1272 | net/purchase +1457 [-69] | 1-ct net $+43,305
- 2. donchian/tf15/pm [hm-donchian-tf15#11] eval rules m40 L1000 K- S- T- TT P5 0.57 (0.58|0.37) | funded m40K1000L300S0T0P1000 P20/P40 49%/49% med 6d chq $797 | E$40 2723 / E$60 2814 (2790|177) | bust-pre 51% | WF OOS E$40 1497 (P40 42%) | lift +1341 | net/purchase +1457 [-73] | 1-ct net $+38,220
- 3. donchian/tf15/pm [hm-donchian-tf15#9] eval rules m40 L1000 K3000 S- T- TT P5 0.54 (0.54|0.26) | funded m40K1000L300S0T0P1000 P20/P40 49%/49% med 6d chq $797 | E$40 2723 / E$60 2814 (2790|189) | bust-pre 51% | WF OOS E$40 1497 (P40 42%) | lift +1232 | net/purchase +1371 [-89] | 1-ct net $+36,012
- edge-backed: donchian/tf15/pm [hm-donchian-tf15#10] eval rules m40 L1000 K- S- T- TT P5 0.57 (0.58|0.37) | funded m40K1000L300S0T0P1000 P20/P40 49%/49% med 6d chq $797 | E$40 2723 / E$60 2814 (2790|189) | bust-pre 51% | WF OOS E$40 1497 (P40 42%) | lift +1272 | net/purchase +1457 [-69] | 1-ct net $+43,305
## Apex PA (UNCONF.) (eval fee $35, activation $85; rule file via eval firm apex)
- 1. ema_pullback/tf5/pm [fp-ema_pullback-tf5#3] eval rules m100 L1000 K3000 S- T- TT P5 0.19 (0.28|0.19) | funded m30K0L300S1000T1P500 P20/P40 13%/17% med 17d chq $134 | E$40 382 / E$60 488 (382|382) | bust-pre 82% | WF OOS E$40 146 (P40 9%) | lift +324 | net/purchase +40 [+40] | 1-ct net $-68,572
- 2. vwap_z/tf5/london [hm-vwap_z-tf5#3] eval rules m80 L- K- S3000 T- TT P5 0.24 (0.30|0.24) | funded m20K1000L300S0T1P1000 P20/P40 5%/8% med 22d chq $149 | E$40 226 / E$60 354 (226|226) | bust-pre 87% | WF OOS E$40 35 (P40 3%) | lift +218 | net/purchase +30 [+30] | 1-ct net $-86,820
- 3. ema_pullback/tf5/london [hm-ema_pullback-tf5#15] eval rules m100 L- K- S3000 T- TT P5 0.25 (0.32|0.25) | funded m20K1000L300S300T1P500 P20/P40 6%/13% med 23d chq $233 | E$40 270 / E$60 336 (270|280) | bust-pre 83% | WF OOS E$40 78 (P40 5%) | lift +254 | net/purchase +27 [+30] | 1-ct net $-87,835

# ES funded search (500 config x firm pairs full-grid of 13935; 2021-09-22..2024-12-31; 60-session lives, rolling starts)
Metrics: P(>=1 payout by 20/40/60d) | med days to 1st payout | E[1st cheque] gross | E$ to trader by 40d / 60d | P(bust before 1st payout). Primary = E$40d, stable cell (min of own, median of neighbours). Top lists: <=2 per (family, session).
Breach: Lucid realized (bounds eod/intraday); Apex pess primary (MFE-before-MAE, extreme), nat/opt bounds shown. APEX UNCONFIRMED; Flex+DLL $1,200 assumed.
## Flex  (model realized; screened 2787 cfgs coarse, 100 full)
1. donchian/tf15/pm [hm-donchian-tf15#8] m40K1000L600S0T1P500 | P20/40/60 46%/47%/47% med 8d chq $742 | E$40 1618 [1055,2412] E$60 1643 | bust-pre 53% | lift442 alt:1618/542
2. donchian/tf15/pm [hm-donchian-tf15#9] m40K1000L300S0T0P1000 | P20/40/60 43%/43%/43% med 8d chq $738 | E$40 1624 [1062,2418] E$60 1659 | bust-pre 57% | lift696 alt:1696/347
3. ema_pullback/tf5/pm [hm-ema_pullback-tf5#9] m40K600L300S0T0P1500 | P20/40/60 34%/35%/35% med 7d chq $586 | E$40 1574 [1117,2541] E$60 1576 | bust-pre 65% | lift549 alt:1574/280
4. ema_pullback/tf5/pm [hm-ema_pullback-tf5#8] m40K600L300S0T0P1000 | P20/40/60 39%/39%/39% med 6d chq $505 | E$40 1485 [990,2476] E$60 1489 | bust-pre 61% | lift627 alt:1485/462
5. vwap_flip/tf5/pm [hm-vwap_flip-tf5#35] m10K1000L300S0T1P1000 | P20/40/60 39%/45%/45% med 11d chq $601 | E$40 1359 [691,2395] E$60 1554 | bust-pre 54% | lift616 alt:1359/1011
## Flex+DLL1200*  (model realized; screened 2787 cfgs coarse, 100 full)
1. tod_drift/tf5/nyam [fp-tod_drift-tf5#13] m30K0L300S0T0Pmax | P20/40/60 31%/35%/35% med 11d chq $697 | E$40 1605 [921,2503] E$60 1683 | bust-pre 65% | lift1251 alt:1605/1121
2. tod_drift/tf5/nyam [fp-tod_drift-tf5#10] m30K0L300S0T0P1500 | P20/40/60 36%/37%/37% med 9d chq $646 | E$40 1516 [931,2241] E$60 1542 | bust-pre 63% | lift960 alt:1530/1171
3. straddle/tf15/pm [hm-straddle-tf15#32] m20K0L300S0T0P1000 | P20/40/60 38%/38%/38% med 8d chq $611 | E$40 1302 [877,1978] E$60 1393 | bust-pre 62% | lift874 alt:1302/974
4. vwap_flip/tf5/pm [fp-vwap_flip-tf5#15] m20K0L600S0T0P1000 | P20/40/60 33%/33%/33% med 8d chq $593 | E$40 1222 [833,1896] E$60 1382 | bust-pre 67% | lift694 alt:1226/972
5. vwap_flip/tf5/pm [hm-vwap_flip-tf5#21] m10K600L300S0T1P1000 | P20/40/60 42%/49%/49% med 12d chq $569 | E$40 1270 [751,1923] E$60 1516 | bust-pre 51% | lift721 alt:1272/849
## Pro DLL  (model realized; screened 2787 cfgs coarse, 100 full)
1. tod_drift/tf5/nyam [fp-tod_drift-tf5#10] m30K0L300S0T0P1000 | P20/40/60 38%/39%/39% med 6d chq $534 | E$40 2093 [1289,3085] E$60 2148 | bust-pre 61% | lift1390 alt:2093/1108
2. ema_pullback/tf5/pm [fp-ema_pullback-tf5#12] m40K0L300S0T1P500 | P20/40/60 33%/33%/33% med 6d chq $289 | E$40 1671 [893,3003] E$60 1792 | bust-pre 67% | lift-18 alt:1671/911
3. tod_drift/tf5/nyam [fp-tod_drift-tf5#13] m30K0L300S0T0P1500 | P20/40/60 32%/33%/33% med 7d chq $622 | E$40 1634 [1069,2422] E$60 1634 | bust-pre 67% | lift1167 alt:1639/904
4. ema_pullback/tf5/pm [fp-ema_pullback-tf5#13] m40K0L600S0T0P500 | P20/40/60 32%/32%/32% med 4d chq $448 | E$40 1511 [800,2792] E$60 1652 | bust-pre 68% | lift106 alt:1632/972
5. vwap_flip/tf5/pm [hm-vwap_flip-tf5#4] m30K0L300S0T1P1500 | P20/40/60 30%/35%/35% med 12d chq $644 | E$40 1289 [776,2034] E$60 1533 | bust-pre 65% | lift463 alt:1289/886
## Pro noDLL  (model realized; screened 2787 cfgs coarse, 100 full)
1. donchian/tf15/pm [hm-donchian-tf15#9] m40K1000L300S0T0P1000 | P20/40/60 49%/49%/49% med 6d chq $797 | E$40 2723 [1419,4808] E$60 2814 | bust-pre 51% | lift1232 alt:2790/189
2. donchian/tf15/pm [hm-donchian-tf15#8] m40K1000L300S0T0P1000 | P20/40/60 49%/49%/49% med 6d chq $797 | E$40 2722 [1418,4807] E$60 2813 | bust-pre 51% | lift849 alt:2785/317
3. straddle/tf15/pm [hm-straddle-tf15#10] m40K1000L300S0T0P1000 | P20/40/60 39%/39%/39% med 4d chq $632 | E$40 2437 [790,5120] E$60 2701 | bust-pre 61% | lift401 alt:2437/85
4. straddle/tf15/pm [hm-straddle-tf15#8] m40K1000L300S0T0P1000 | P20/40/60 39%/39%/39% med 4d chq $632 | E$40 2416 [790,5118] E$60 2680 | bust-pre 61% | lift855 alt:2416/123
5. ema_pullback/tf5/pm [hm-ema_pullback-tf5#9] m40K1000L300S0T0P1000 | P20/40/60 36%/36%/36% med 4d chq $597 | E$40 2211 [1374,3936] E$60 2225 | bust-pre 64% | lift659 alt:2211/234
## Apex PA (UNCONF.)  (model pess; screened 2217 cfgs coarse, 100 full)
1. ema_pullback/tf5/pm [fp-ema_pullback-tf5#3] m30K0L300S1000T1P500 | P20/40/60 13%/17%/18% med 17d chq $134 | E$40 382 [126,782] E$60 488 | bust-pre 82% | lift324 alt:382/382 cut0.0% mae0% clean
2. ema_pullback/tf5/london [hm-ema_pullback-tf5#3] m20K1000L300S300T0P1000 | P20/40/60 6%/13%/15% med 23d chq $232 | E$40 269 [57,595] E$60 335 | bust-pre 83% | lift216 alt:269/279 cut0.6% mae1% FLAGS:mae30_cuts_0.006
3. ema_pullback/tf5/london [hm-ema_pullback-tf5#15] m20K1000L300S300T1P500 | P20/40/60 6%/13%/15% med 23d chq $233 | E$40 270 [60,596] E$60 336 | bust-pre 83% | lift254 alt:270/280 cut0.6% mae1% FLAGS:mae30_cuts_0.006
4. tod_drift/tf5/nyam [fp-tod_drift-tf5#3] m30K0L0S1000T0P500 | P20/40/60 10%/14%/15% med 17d chq $116 | E$40 239 [89,475] E$60 288 | bust-pre 85% | lift157 alt:239/239 cut0.0% mae0% clean
5. vwap_flip/tf5/london [hm-vwap_flip-tf5#3] m20K600L600S0T0P500 | P20/40/60 10%/12%/12% med 10d chq $114 | E$40 228 [55,551] E$60 241 | bust-pre 88% | lift188 alt:228/228 cut0.6% mae1% FLAGS:mae30_cuts_0.006
## Frontier (best cell per objective, any config; E$40 / P20 / med days)
Flex: E$40 max 1618 (P20 46%) | P20 max 62% (tema_slope/mid, E$40 1068) | fastest med 5d at P60 54% (E$40 1254)
Flex+DLL1200*: E$40 max 1503 (P20 31%) | P20 max 60% (vwap_flip/pm, E$40 871) | fastest med 5d at P60 55% (E$40 670)
Pro DLL: E$40 max 2030 (P20 38%) | P20 max 44% (tod_drift/nyam, E$40 2092) | fastest med n/a at P60 - (E$40 -)
Pro noDLL: E$40 max 2700 (P20 49%) | P20 max 55% (donchian/pm, E$40 2459) | fastest med 3d at P60 51% (E$40 1853)
Apex PA (UNCONF.): E$40 max 382 (P20 13%) | P20 max 13% (ema_pullback/pm, E$40 382) | fastest med n/a at P60 - (E$40 -)
## Null reference (random-control pseudo-configs thinned to candidate strata, same full search; score_E$40 | P20)
Flex: null n=60 E$40 mean 569 p95 1039 max 1302 | P20 mean 28% p95 43% max 56% | real best 1618; 100/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 509 max 1022
Flex+DLL1200*: null n=60 E$40 mean 469 p95 930 max 1037 | P20 mean 25% p95 44% max 52% | real best 1503; 68/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 474 max 937
Pro DLL: null n=60 E$40 mean 413 p95 884 max 1081 | P20 mean 15% p95 28% max 29% | real best 2030; 88/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 379 max 894
Pro noDLL: null n=60 E$40 mean 695 p95 1391 max 1751 | P20 mean 23% p95 38% max 42% | real best 2700; 100/100 full-grid cfgs above null p95 | WF OOS null (n=20) mean 608 max 1026
Apex PA (UNCONF.): null n=28 E$40 mean 102 p95 252 max 379 | P20 mean 4% p95 11% max 15% | real best 382; 2/100 full-grid cfgs above null p95 | WF OOS null (n=6) mean 43 max 120
## Walk-forward (top 10 per firm, 2022Q4-2024Q3 test quarters, trailing-12m selection, stitched OOS)
Flex: OOS E$40 median 956 (IS on same starts 1258), best 1250; OOS P40 median 36%, med days 9, bust-pre 64%; 5/10 above null OOS max
Flex+DLL1200*: OOS E$40 median 1177 (IS on same starts 1372), best 1826; OOS P40 median 38%, med days 9, bust-pre 62%; 8/10 above null OOS max
Pro DLL: OOS E$40 median 1123 (IS on same starts 1601), best 2590; OOS P40 median 32%, med days 6, bust-pre 68%; 8/10 above null OOS max
Pro noDLL: OOS E$40 median 1258 (IS on same starts 1490), best 2153; OOS P40 median 34%, med days 6, bust-pre 66%; 6/10 above null OOS max
Apex PA (UNCONF.): OOS E$40 median 79 (IS on same starts 167), best 265; OOS P40 median 6%, med days 18, bust-pre 92%; 4/10 above null OOS max
## Eval + funded economics: E[net $ per eval purchase] = P(pass<=5d, primary model) x E$60d funded - fee - P(pass) x activation (same-config line = headline)
Flex (fee $100+act $0): HEADLINE same-config 669.6 (eval P5 46% x funded E$60 1658, hm-straddle-tf15#11|pm) | cross-config best-eval P5 49% x best-funded E$60 1643 = 710.5 (optimistic: two different strategies) | WF: P5 49% x OOS E$60 med 1054 = 415.1
Flex+DLL1200* (fee $100+act $0): HEADLINE same-config 572.2 (eval P5 40% x funded E$60 1683, fp-tod_drift-tf5#13|nyam) | cross-config best-eval P5 49% x best-funded E$60 1683 = 730.0 (optimistic: two different strategies) | WF: P5 49% x OOS E$60 med 1296 = 533.6
Pro DLL (fee $115+act $0): HEADLINE same-config 421.9 (eval P5 36% x funded E$60 1504, hm-vwap_flip-tf5#34|pm) | cross-config best-eval P5 40% x best-funded E$60 2148 = 748.4 (optimistic: two different strategies) | WF: P5 42% x OOS E$60 med 1231 = 398.2
Pro noDLL (fee $140+act $0): HEADLINE same-config 1457.1 (eval P5 57% x funded E$60 2814, hm-donchian-tf15#10|pm) | cross-config best-eval P5 58% x best-funded E$60 2814 = 1484.5 (optimistic: two different strategies) | WF: P5 55% x OOS E$60 med 1360 = 605.4
Apex PA (UNCONF.) (fee $35+act $85): HEADLINE same-config 40.1 (eval P5 19% x funded E$60 488, fp-ema_pullback-tf5#3|pm) | cross-config best-eval P5 38% x best-funded E$60 488 = 117.1 (optimistic: two different strategies) | WF: P5 38% x OOS E$60 med 79 = -37.2
Caveats: Apex pess ordering extreme; Apex rules/fees UNCONFIRMED; Flex DLL $1,200 + activation $0 assumed; payout EOD-only, 2-day disbursement ignored; eval->funded uses eval P5 (primary model) at the eval-side best cell; WF/stability computed on overlapping rolling starts (CIs are block bootstraps).
