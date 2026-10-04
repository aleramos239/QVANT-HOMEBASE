# A3 pass 3 (ES): tuned heat-maps hm-* (13 family x tf grids) and fast-pass fp-* (pts stops x small targets), plus the ES screen configs re-scored (a3p3s), 2021-09-22..2024-12-31 in-sample
Configs (>=300 tr, ALL incl. net<=0 at 1 ES): 2535 tuned/fast-pass + 252 screen; rule cells per config 3600 (768+576+576+960+720) x 3 breach models; null 522 pseudo-configs (5 firms x 5 cellsets each; fp/atr/tod pool groups). Primary model: Lucid* realized, Apex* intraday; eod = optimistic bound. APEX both sets UNCONFIRMED.
Edge lift vs day-matched random (K=10, identical rules) = WARNING LABEL, not a filter. flags: NET<=0, ONE_YEAR (>60% of 1-contract net in one year), NEAREST_POOL, NO_EDGE_VS_RANDOM (lift <= null p95), COST_RULE_FAIL.
## Null (zero-edge random pseudo-configs, stable-cell optimum): P5 at each model's own stable cell, P1 / P3 at the primary-model speed cells: mean / p95 / max (lift p95)
Lucid Flex n=530: P5eod .16/.34/.43(.04) ; P5rlz .15/.33/.40(.05) ; P5int .10/.20/.27(.04) ; P1rea .00/.00/.00(.00) ; P3rea .07/.21/.28(.03)
LucidPro+DLL n=530: P5eod .16/.31/.38(.05) ; P5rlz .16/.31/.38(.05) ; P5int .15/.29/.34(.05) ; P1rea .04/.12/.18(.02) ; P3rea .12/.25/.34(.04)
LucidPro noDLL n=530: P5eod .22/.44/.56(.06) ; P5rlz .21/.42/.55(.06) ; P5int .17/.31/.35(.05) ; P1rea .06/.18/.28(.02) ; P3rea .16/.36/.47(.05)
Apex (user set, UNCONFIRMED) n=530: P5eod .44/.65/.73(.05) ; P5rlz .43/.64/.72(.06) ; P5int .24/.33/.35(.05) ; P1int .12/.23/.28(.03) ; P3int .21/.31/.34(.04)
Apex EOD (site, UNCONFIRMED) n=530: P5eod .18/.31/.36(.05) ; P5rlz .18/.31/.36(.05) ; P5int .18/.31/.35(.05) ; P1int .06/.14/.18(.02) ; P3int .14/.27/.32(.04)
## Best in-sample per firm (primary model; [eod|intraday] bounds). P1 = speed cell max P(pass<=1d), P3 = speed cell max P(pass<=3d), P5 = P5-stable cell
Lucid Flex: P1 .00 [.00|.00] bust5 .24 h-straddle-tf15#21|pm m10 L- K- S- T- tt- lift +0.00 | P3 .41 [.41|.13] h-straddle-tf15#21|pm m40 L750 K1500 S- T- TT lift +0.08 | P5 .49 [.49|.14] h-straddle-tf15#21|pm bust5 .47 lift +0.07 ONE_YEAR;NO_EDGE_VS_RANDOM
LucidPro+DLL: P1 .19 [.19|.19] bust5 .61 h-straddle-tf15#19|pm m40 L1000 K- S- T- TT lift +0.03 | P3 .37 [.37|.34] h-tod_drift-tf15#13|nyam m40 L1000 K- S- T- TT lift +0.08 | P5 .40 [.40|.36] h-tod_drift-tf15#13|nyam bust5 .57 lift +0.07 ONE_YEAR;COST_RULE_FAIL
LucidPro noDLL: P1 .38 [.38|.25] bust5 .49 h-straddle-tf15#23|nyam m40 L1000 K- S- T- TT lift +0.10 | P3 .54 [.54|.34] h-straddle-tf15#22|pm m40 L1000 K- S- T- TT lift +0.05 | P5 .58 [.58|.34] h-straddle-tf15#35|pm bust5 .40 lift +0.05 ONE_YEAR;NO_EDGE_VS_RANDOM
Apex (user set, UNCONFIRMED): P1 .35 [.43|.35] bust5 .65 fp-tod_drift-tf5#14|nyam m80 L1000 K- S3000 T- TT lift +0.07 | P3 .37 [.46|.37] fp-rsi2-tf5#9|mid m80 L- K- S3000 T- TT lift -0.05 | P5 .38 [.48|.38] fp-donchian-tf15#15|pm bust5 .57 lift +0.04 ONE_YEAR;COST_RULE_FAIL
Apex EOD (site, UNCONFIRMED): P1 .20 [.20|.20] bust5 .65 fp-tema_slope-tf5#11|london m60 L- K- S- T- TT lift +0.01 | P3 .35 [.35|.35] fp-vwap_flip-tf5#15|pm m60 L1000 K- S- T- TT lift +0.09 | P5 .37 [.37|.37] s-donchian-tf5|pm bust5 .62 lift +0.08 NET<=0;COST_RULE_FAIL
## Fast-pass structures (fp-*: pts stop x small target, both directions) vs null: best real P1 / P3 / P5 (primary) vs null mean/p95/max of the same fp-pool group; expectancy/trade after costs at the chosen size
Lucid Flex (n=848): P1 .00 vs null .00/.00/.00 (fp-straddle-tf30#14|nyam m10 L- K- S- T- tt-, net<=0 Y) | P3 .37 vs .05/.18/.24 (fp-tod_drift-tf5#13|nyam) | P5 .41 vs .11/.29/.36 (fp-straddle-tf30#14|nyam, exp $-110/tr @m40, lift +0.12, NET<=0;COST_RULE_FAIL)
LucidPro+DLL (n=848): P1 .15 vs null .01/.05/.10 (fp-rsi2-tf5#15|nyam m40 L- K- S1000 T- TT, net<=0 Y) | P3 .36 vs .05/.18/.27 (fp-rsi2-tf5#15|nyam) | P5 .40 vs .09/.26/.35 (fp-rsi2-tf5#15|nyam, exp $-140/tr @m40, lift +0.02, NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL)
LucidPro noDLL (n=848): P1 .26 vs null .01/.07/.16 (fp-rsi2-tf5#15|nyam m40 L- K- S- T- TT, net<=0 Y) | P3 .44 vs .08/.28/.34 (fp-tod_drift-tf5#15|nyam) | P5 .47 vs .13/.36/.41 (fp-straddle-tf30#15|pm, exp $+28/tr @m40, lift +0.07, ONE_YEAR;COST_RULE_FAIL)
Apex (user set, UNCONFIRMED) (n=848): P1 .35 vs null .08/.22/.28 (fp-tod_drift-tf5#14|nyam m80 L1000 K- S3000 T- TT, net<=0 Y) | P3 .37 vs .18/.32/.34 (fp-rsi2-tf5#9|mid) | P5 .38 vs .21/.33/.35 (fp-donchian-tf15#15|pm, exp $+315/tr @m60, lift +0.04, ONE_YEAR;COST_RULE_FAIL)
Apex EOD (site, UNCONFIRMED) (n=848): P1 .20 vs null .02/.12/.14 (fp-tema_slope-tf5#11|london m60 L- K- S- T- TT, net<=0 Y) | P3 .35 vs .09/.24/.30 (fp-vwap_flip-tf5#15|pm) | P5 .36 vs .13/.29/.33 (fp-vwap_flip-tf5#15|pm, exp $-36/tr @m60, lift +0.08, NET<=0;COST_RULE_FAIL)
## Top 8 per firm by primary-model P5 (one per family grid x session; Apex firms: Apex-compliant only = no OCO family, target tgt_r>=0.2): id | rules | P1/P3/P5 [P5 CI] bust5 | eod P5 | intr P5 | lift | WF OOS P5 (lift) | flags
FLX h-straddle-tf15#21|pm m40 L750 K1500 S- T- TT | .00/.41/.49 [.44,.56] b.47 | .49 | .14 | +0.07 WF .49(+0.36) | ONE_YEAR;NO_EDGE_VS_RANDOM
FLX h-straddle-tf15#10|mid m40 L750 K1500 S- T- TT | .00/.37/.46 [.41,.52] b.51 | .46 | .11 | +0.00 WF .42(+0.27) | NET<=0;NO_EDGE_VS_RANDOM
FLX h-first_bar_mom-tf30#10|nyam m40 L750 K1500 S- T- TT | .00/.35/.45 [.39,.50] b.52 | .45 | .14 | +0.07 WF .43(+0.31) | NET<=0;NO_EDGE_VS_RANDOM
FLX h-straddle-tf15#21|nyam m40 L750 K1500 S- T- TT | .00/.39/.44 [.39,.49] b.55 | .44 | .15 | +0.00 WF .38(+0.28) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
FLX h-vwap_flip-tf5#34|pm m40 L750 K1500 S- T- TT | .00/.30/.43 [.37,.50] b.52 | .46 | .18 | +0.03 WF .41(+0.36) | ONE_YEAR;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
FLX s-straddle-tf30|pm m40 L750 K1500 S- T- TT | .00/.34/.43 [.38,.48] b.55 | .43 | .18 | +0.05 WF .43(+0.07) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
FLX s-orb-tf30|pm m40 L750 K1500 S- T- TT | .00/.35/.42 [.37,.47] b.55 | .42 | .17 | +0.04 WF .43(+0.06) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
FLX h-first_bar_mom-tf30#10|mid m40 L750 K1500 S- T- TT | .00/.22/.41 [.36,.47] b.47 | .41 | .10 | +0.07 WF .40(+0.25) | NET<=0;NO_EDGE_VS_RANDOM
LP+ h-tod_drift-tf15#13|nyam m40 L1000 K- S- T- TT | .19/.37/.40 [.34,.45] b.57 | .40 | .36 | +0.07 WF .32(-0.02) | ONE_YEAR;COST_RULE_FAIL
LP+ fp-rsi2-tf5#15|nyam m40 L- K- S- T- TT | .17/.36/.40 [.34,.45] b.57 | .40 | .36 | +0.02 WF .34(+0.34) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
LP+ h-straddle-tf15#31|pm m40 L1000 K- S- T- TT | .18/.35/.40 [.34,.45] b.59 | .40 | .34 | +0.04 WF .42(+0.35) | ONE_YEAR;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
LP+ s-rsi2-tf5|nyam m40 L- K- S- T- TT | .18/.34/.39 [.33,.44] b.57 | .40 | .36 | +0.13 WF .38(+0.13) | NET<=0;COST_RULE_FAIL
LP+ h-tod_drift-tf5#15|nyam m40 L1000 K- S- T- TT | .19/.36/.39 [.33,.44] b.57 | .39 | .35 | +0.07 WF .31(+0.02) | ONE_YEAR;COST_RULE_FAIL
LP+ s-donchian-tf5|pm m40 L- K- S- T- TT | .16/.33/.39 [.33,.44] b.55 | .39 | .36 | +0.09 WF .41(+0.13) | NET<=0;COST_RULE_FAIL
LP+ s-straddle-tf30|pm m40 L1000 K- S- T- TT | .18/.34/.39 [.33,.45] b.60 | .39 | .34 | +0.06 WF .41(+0.08) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
LP+ h-tod_drift-tf5#23|mid m40 L1000 K- S- T- TT | .18/.34/.38 [.33,.43] b.57 | .38 | .35 | +0.05 WF .30(+0.07) | NET<=0;COST_RULE_FAIL
LP0 h-straddle-tf15#35|pm m40 L1000 K- S- T- TT | .32/.53/.58 [.53,.64] b.40 | .58 | .34 | +0.05 WF .55(+0.42) | ONE_YEAR;NO_EDGE_VS_RANDOM
LP0 h-donchian-tf15#10|pm m40 L1000 K- S- T- TT | .23/.46/.57 [.52,.62] b.34 | .58 | .37 | +0.06 WF .52(+0.39) | NO_EDGE_VS_RANDOM
LP0 h-straddle-tf15#9|mid m40 L1000 K- S- T- TT | .31/.48/.52 [.48,.57] b.47 | .52 | .29 | +0.03 WF .46(+0.30) | NET<=0;NO_EDGE_VS_RANDOM
LP0 h-tema_slope-tf15#11|pm m40 L1000 K- S- T1 TT | .26/.46/.51 [.46,.57] b.45 | .51 | .33 | -0.00 WF .48(+0.32) | NET<=0;NO_EDGE_VS_RANDOM
LP0 h-first_bar_mom-tf30#10|pm m40 L1000 K- S- T- TT | .19/.40/.51 [.45,.58] b.32 | .51 | .35 | +0.08 WF .51(+0.42) | ONE_YEAR;NO_EDGE_VS_RANDOM
LP0 h-vwap_flip-tf5#22|pm m40 L1000 K- S- T1 TT | .30/.48/.51 [.45,.58] b.46 | .51 | .37 | +0.06 WF .45(+0.38) | ONE_YEAR;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
LP0 h-ema_pullback-tf5#11|mid m40 L1000 K- S- T- TT | .23/.45/.51 [.46,.56] b.46 | .51 | .32 | +0.03 WF .50(+0.40) | ONE_YEAR;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
LP0 s-straddle-tf30|pm m40 L1000 K- S- T- TT | .31/.49/.51 [.46,.56] b.48 | .51 | .35 | +0.04 WF .51(+0.07) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL
APX fp-donchian-tf15#15|pm m60 L1000 K- S3000 T- TT | .17/.32/.38 [.33,.42] b.57 | .48 | .38 | +0.04 WF .37(+0.37) | ONE_YEAR;COST_RULE_FAIL | mae750 81% THR_STOP
APX h-donchian-tf15#7|pm m40 L1000 K- S3000 T- TT | .17/.32/.37 [.33,.41] b.59 | .47 | .37 | +0.05 WF .35(+0.15) | NO_EDGE_VS_RANDOM;COST_RULE_FAIL | mae750 75% THR_STOP
APX fp-rsi2-tf5#9|mid m80 L- K- S3000 T- TT | .34/.37/.37 [.34,.40] b.63 | .47 | .37 | -0.05 WF .34(+0.30) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL | mae750 72% THR_STOP
APX h-vwap_flip-tf5#22|pm m40 L1000 K- S3000 T- TT | .23/.35/.37 [.32,.42] b.62 | .43 | .37 | +0.07 WF .33(+0.14) | ONE_YEAR;COST_RULE_FAIL | mae750 78% THR_STOP
APX h-donchian-tf30#3|pm m60 L1000 K- S3000 T- TT | .14/.29/.36 [.31,.41] b.55 | .44 | .36 | +0.06 WF .33(+0.15) | ONE_YEAR;NO_EDGE_VS_RANDOM;COST_RULE_FAIL | mae750 85% THR_STOP
APX fp-rsi2-tf5#11|nyam m60 L- K- S2000 T- TT | .29/.35/.36 [.32,.39] b.64 | .37 | .36 | +0.02 WF .35(+0.30) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL | mae750 80% THR_STOP
APX fp-vwap_z-tf5#15|mid m60 L1000 K- S3000 T- TT | .23/.34/.35 [.32,.39] b.65 | .45 | .35 | +0.06 WF .36(+0.33) | NET<=0;COST_RULE_FAIL | mae750 81% THR_STOP
APX h-first_bar_mom-tf30#3|pm m40 L1000 K- S3000 T- TT | .12/.27/.35 [.29,.41] b.48 | .41 | .35 | +0.07 WF .38(+0.20) | NET<=0;COST_RULE_FAIL | mae750 79% THR_STOP
AEOD s-donchian-tf5|pm m60 L- K- S- T- TT | .17/.33/.37 [.31,.42] b.62 | .37 | .37 | +0.08 WF .40(+0.12) | NET<=0;COST_RULE_FAIL | mae750 83%
AEOD h-donchian-tf15#5|pm m60 L- K- S- T- TT | .14/.31/.36 [.31,.42] b.59 | .37 | .36 | +0.08 WF .32(+0.19) | COST_RULE_FAIL | mae750 82%
AEOD fp-vwap_flip-tf5#15|pm m60 L1000 K- S- T- TT | .20/.35/.36 [.31,.41] b.64 | .36 | .36 | +0.08 WF .36(+0.36) | NET<=0;COST_RULE_FAIL | mae750 84%
AEOD fp-donchian-tf15#15|pm m60 L1000 K- S- T- TT | .11/.28/.36 [.30,.41] b.48 | .36 | .36 | +0.02 WF .36(+0.36) | ONE_YEAR;NO_EDGE_VS_RANDOM;COST_RULE_FAIL | mae750 81%
AEOD fp-ema_pullback-tf5#15|mid m60 L1000 K- S- T- TT | .17/.33/.35 [.30,.39] b.65 | .35 | .35 | +0.05 WF .35(+0.35) | NET<=0;COST_RULE_FAIL | mae750 82%
AEOD fp-rsi2-tf5#11|nyam m60 L- K- S- T- TT | .18/.33/.35 [.30,.39] b.65 | .35 | .35 | +0.00 WF .35(+0.34) | NET<=0;NO_EDGE_VS_RANDOM;COST_RULE_FAIL | mae750 80%
AEOD fp-tod_drift-tf5#15|pm m60 L1000 K- S- T- TT | .19/.34/.34 [.30,.38] b.66 | .34 | .34 | +0.05 WF .34(+0.34) | ONE_YEAR;COST_RULE_FAIL | mae750 83%
AEOD s-rsi2-tf5|nyam m60 L- K- S- T- TT | .18/.32/.33 [.29,.38] b.66 | .34 | .33 | +0.09 | NET<=0;COST_RULE_FAIL | mae750 83%
## Positive-expectancy bias (funded use): best primary P5 among configs with net > 0 at 1 ES (before rules), one per family/tf/session; exp = $/trade after costs at the chosen size
FLX: h-straddle-tf15#21|pm m40 L750 K1500 S- T- TT P5 .49 [eod .49 intr .14] net1 $+17324 exp $+85/tr lift +0.07 | h-vwap_flip-tf5#34|pm m40 L750 K1500 S- T- TT P5 .43 [eod .46 intr .18] net1 $+15652 exp $+70/tr lift +0.03 | h-ema_pullback-tf5#10|mid m40 L750 K1500 S- T- TT P5 .41 [eod .41 intr .14] net1 $+9355 exp $+50/tr lift -0.04
LP+: h-tod_drift-tf15#13|nyam m40 L1000 K- S- T- TT P5 .40 [eod .40 intr .36] net1 $+1870 exp $+9/tr lift +0.07 | h-straddle-tf15#31|pm m40 L1000 K- S- T- TT P5 .40 [eod .40 intr .34] net1 $+3690 exp $+19/tr lift +0.04 | h-tod_drift-tf5#15|nyam m40 L1000 K- S- T- TT P5 .39 [eod .39 intr .35] net1 $+15520 exp $+75/tr lift +0.07
LP0: h-straddle-tf15#35|pm m40 L1000 K- S- T- TT P5 .58 [eod .58 intr .34] net1 $+6728 exp $+34/tr lift +0.05 | h-donchian-tf15#10|pm m40 L1000 K- S- T- TT P5 .57 [eod .58 intr .37] net1 $+43305 exp $+264/tr lift +0.06 | h-first_bar_mom-tf30#10|pm m40 L1000 K- S- T- TT P5 .51 [eod .51 intr .35] net1 $+6298 exp $+61/tr lift +0.08
APX: fp-donchian-tf15#15|pm m60 L1000 K- S3000 T- TT P5 .38 [eod .48 intr .38] net1 $+29560 exp $+315/tr lift +0.04 | h-vwap_flip-tf5#22|pm m40 L1000 K- S3000 T- TT P5 .37 [eod .43 intr .37] net1 $+24608 exp $+107/tr lift +0.07 | h-donchian-tf30#3|pm m60 L1000 K- S3000 T- TT P5 .36 [eod .44 intr .36] net1 $+20056 exp $+291/tr lift +0.06
AEOD: h-donchian-tf15#5|pm m60 L- K- S- T- TT P5 .36 [eod .37 intr .36] net1 $+30032 exp $+228/tr lift +0.08 | fp-tod_drift-tf5#15|pm m60 L1000 K- S- T- TT P5 .34 [eod .34 intr .34] net1 $+8811 exp $+65/tr lift +0.05 | fp-tema_slope-tf30#15|pm m60 L1000 K- S- T- TT P5 .33 [eod .33 intr .33] net1 $+5550 exp $+74/tr lift +0.04
## Offline walk-forward (top-12 family-grid x session sets per firm, quarterly re-selection on trailing 12m; eod / primary model; OOS lift vs same-procedure random controls)
FLX realized: median OOS P5 .41 (IS .43), lift>0 12/12, lift CI>0 10; median IS->OOS drop +0.019; eod median OOS P5 .42; best hm-straddle-tf15/pm OOS .49 (+0.36)
LP+ realized: median OOS P5 .34 (IS .39), lift>0 9/12, lift CI>0 7; median IS->OOS drop +0.028; eod median OOS P5 .34; best hm-straddle-tf15/pm OOS .42 (+0.35)
LP0 realized: median OOS P5 .47 (IS .51), lift>0 12/12, lift CI>0 12; median IS->OOS drop +0.036; eod median OOS P5 .49; best hm-straddle-tf15/pm OOS .55 (+0.42)
APX intraday: median OOS P5 .35 (IS .36), lift>0 12/12, lift CI>0 10; median IS->OOS drop +0.011; eod median OOS P5 .65; best hm-first_bar_mom-tf30/pm OOS .38 (+0.20)
AEOD intraday: median OOS P5 .34 (IS .35), lift>0 10/12, lift CI>0 9; median IS->OOS drop +0.003; eod median OOS P5 .34; best screen-donchian-tf5/pm OOS .40 (+0.12)
## Apex MAE-cut compliance bound (UNCONFIRMED): size capped so <= 2% of trades reach the $750 PA negative-P&L floor; top Apex-compliant configs re-searched (a3p3_apexmae.py)
APX: 12 configs, unrestricted best P5 .38 -> MAE-compliant stable P5 median .00 / max .05 (fp-rsi2-tf5#11|nyam, size <= 12 micros; P1 max .00); at the unrestricted sizes .81 (median) of trades hit the floor -> Apex is not workable on ES at eval size.
AEOD: 12 configs, unrestricted best P5 .37 -> MAE-compliant stable P5 median .01 / max .04 (fp-rsi2-tf5#11|nyam, size <= 12 micros; P1 max .00); at the unrestricted sizes .82 (median) of trades hit the floor -> Apex is not workable on ES at eval size.
## Tester walk-forwards submitted via hb.py (15/15, ES cap): straddle-tf15-pm, straddle-tf15-nyam, donchian-tf15-pm, rsi2-tf5-nyam-fp, straddle-tf30-pm, tod_drift-tf5-nyam-fp, tod_drift-tf5-pm-fp, vwap_flip-tf5-pm, rsi2-tf5-nyam, tod_drift-tf15-nyam, first_bar_mom-tf30-pm, tod_drift-tf5-nyam, donchian-tf30-pm, ib-tf30-pm, vwap_z-tf5-mid
Notes: Lucid Flex needs >=2 trading days (consistency cushion) so P1 is structurally 0; P1/P3 cells maximise speed and often carry bust5 >= .5; WF = top-12 family-grid x session sets per firm of the tuned grids + screen configs (one-config grids). WF lift CAVEAT: controls use the grid's FIRST member exit profile (an fp grid = 3-pt stop x 0.25R target, control P5 ~0; hm grids = stop 1 ATR x 0.5R), so multi-cell/fp lifts (+0.3..+0.4) are inflated: read OOS P5 and the IS->OOS drop; the in-sample lift (K=10 matched controls) is the edge label.
