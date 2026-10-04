# A3 pass 3: new heat-maps hm2-* (16 family grids + tod_drift tf15/30) and fp-* (fast-pass pts stops x small targets), 2021-09-22..2024-12-31 in-sample
Configs (>=300 tr; hm2 also net>0 at 1 NQ, fp not): 1159 pass-3 + 124 pass-2 shortlist re-scored; rule cells per config 3600 (768+576+576+960+720) x 3 breach models; null 407 pseudo-configs (5 firms x 5 cellsets each; fp/atr/tod pool groups). Primary model: Lucid* realized, Apex* intraday; eod = optimistic bound. APEX both sets UNCONFIRMED.
Edge lift vs day-matched random (K=10, identical rules) = WARNING LABEL, not a filter. flags: NET<=0, ONE_YEAR (>60% of 1-NQ net in one year), NEAREST_POOL, NO_EDGE_VS_RANDOM (lift <= null p95), COST_RULE_FAIL.
## Null (zero-edge random pseudo-configs, stable-cell optimum): P5 at each model's own stable cell, P1 / P3 at the primary-model speed cells: mean / p95 / max (lift p95)
Lucid Flex n=407: P5eod .33/.56/.65(.05) ; P5rlz .31/.54/.60(.05) ; P5int .18/.27/.34(.05) ; P1rea .00/.00/.00(.00) ; P3rea .18/.42/.52(.04)
LucidPro+DLL n=407: P5eod .24/.39/.42(.04) ; P5rlz .24/.39/.42(.05) ; P5int .22/.35/.38(.04) ; P1rea .07/.19/.25(.02) ; P3rea .19/.35/.40(.04)
LucidPro noDLL n=407: P5eod .38/.60/.67(.06) ; P5rlz .36/.58/.67(.05) ; P5int .25/.35/.39(.05) ; P1rea .16/.42/.53(.04) ; P3rea .31/.56/.63(.05)
Apex (user set, UNCONFIRMED) n=407: P5eod .61/.79/.84(.05) ; P5rlz .58/.78/.83(.05) ; P5int .31/.37/.41(.05) ; P1int .19/.31/.37(.03) ; P3int .28/.35/.41(.04)
Apex EOD (site, UNCONFIRMED) n=407: P5eod .24/.35/.38(.04) ; P5rlz .24/.35/.38(.04) ; P5int .24/.34/.38(.04) ; P1int .09/.18/.23(.02) ; P3int .19/.31/.35(.04)
## Best in-sample per firm (primary model; [eod|intraday] bounds). P1 = speed cell max P(pass<=1d), P3 = speed cell max P(pass<=3d), P5 = P5-stable cell
Lucid Flex: P1 .00 [.00|.00] bust5 .55 straddle-tf30#10|nyam m10 L- K- S- T- tt- lift +0.00 | P3 .66 [.66|.01] straddle-tf30#10|nyam m40 L750 K1500 S- T- TT lift +0.13 | P5 .69 [.69|.01] straddle-tf30#10|nyam bust5 .31 lift +0.10 
LucidPro+DLL: P1 .27 [.27|.27] bust5 .62 fp-tod_drift-tf5#15|mid m40 L1000 K- S- T- TT lift +0.06 | P3 .43 [.43|.38] rsi2-tf1#21|mid m40 L- K- S- T- TT lift +0.03 | P5 .48 [.48|.41] donchian-tf5#5|pm bust5 .51 lift +0.09 ONE_YEAR
LucidPro noDLL: P1 .67 [.67|.22] bust5 .29 straddle-tf30#10|nyam m40 L1000 K- S- T- TT lift +0.17 | P3 .69 [.69|.06] straddle-tf30#10|nyam m40 L1000 K3000 S- T- TT lift +0.08 | P5 .71 [.71|.23] straddle-tf30#10|nyam bust5 .29 lift +0.07 NO_EDGE_VS_RANDOM
Apex (user set, UNCONFIRMED): P1 .41 [.41|.41] bust5 .59 fp-tod_drift-tf5#7|mid m80 L- K- S2000 T- tt- lift +0.03 | P3 .41 [.41|.41] fp-tod_drift-tf5#7|mid m80 L- K- S2000 T- tt- lift +0.03 | P5 .42 [.43|.42] ema_pullback-tf1#22|pm bust5 .57 lift +0.13 ONE_YEAR
Apex EOD (site, UNCONFIRMED): P1 .26 [.26|.26] bust5 .63 fp-orb-tf5#14|nyam m60 L1000 K- S- T- TT lift +0.06 | P3 .40 [.40|.40] rsi2-tf1#9|mid m40 L- K- S- T- TT lift +0.04 | P5 .42 [.42|.42] donchian-tf5#5|pm bust5 .57 lift +0.08 ONE_YEAR
## Fast-pass structures (fp-*: pts stop x small target, both directions) vs null: best real P1 / P3 / P5 (primary) vs null mean/p95/max of the same fp-pool group; expectancy/trade after costs at the chosen size
Lucid Flex (n=672): P1 .00 vs null .00/.00/.00 (fp-tod_drift-tf5#13|mid m10 L- K- S- T- tt-, net<=0 N) | P3 .50 vs .14/.35/.43 (fp-tod_drift-tf5#13|mid) | P5 .53 vs .24/.48/.51 (fp-tod_drift-tf5#13|mid, exp $+68/tr @m40, lift +0.06, ONE_YEAR)
LucidPro+DLL (n=672): P1 .27 vs null .04/.17/.23 (fp-tod_drift-tf5#15|mid m40 L1000 K- S- T- TT, net<=0 N) | P3 .42 vs .14/.35/.40 (fp-rsi2-tf5#11|mid) | P5 .43 vs .20/.39/.42 (fp-rsi2-tf5#11|mid, exp $-49/tr @m40, lift -0.02, NET<=0;NO_EDGE_VS_RANDOM)
LucidPro noDLL (n=672): P1 .54 vs null .06/.32/.46 (fp-orb-tf5#15|nyam m40 L1000 K- S- T- TT, net<=0 N) | P3 .56 vs .21/.48/.56 (fp-tod_drift-tf5#15|pm) | P5 .57 vs .27/.51/.57 (fp-tod_drift-tf5#15|pm, exp $+138/tr @m40, lift +0.03, ONE_YEAR;NO_EDGE_VS_RANDOM)
Apex (user set, UNCONFIRMED) (n=672): P1 .41 vs null .17/.35/.37 (fp-tod_drift-tf5#7|mid m80 L- K- S2000 T- tt-, net<=0 Y) | P3 .41 vs .28/.38/.41 (fp-tod_drift-tf5#7|mid) | P5 .42 vs .30/.38/.41 (fp-donchian-tf15#15|pm, exp $+298/tr @m40, lift +0.05, ONE_YEAR;NEAREST_POOL)
Apex EOD (site, UNCONFIRMED) (n=672): P1 .26 vs null .06/.19/.23 (fp-orb-tf5#14|nyam m60 L1000 K- S- T- TT, net<=0 N) | P3 .37 vs .16/.32/.35 (fp-tod_drift-tf5#15|mid) | P5 .38 vs .21/.34/.38 (fp-rsi2-tf5#14|mid, exp $-27/tr @m30, lift -0.06, NET<=0;NO_EDGE_VS_RANDOM)
## Top 8 per firm by primary-model P5 (one per family grid x session): id | rules | P1/P3/P5 [P5 CI] bust5 | eod P5 | intr P5 | lift | WF OOS P5 (lift) | flags
FLX straddle-tf30#10|nyam m40 L750 K1500 S- T- TT | .00/.66/.69 [.64,.74] b.31 | .69 | .01 | +0.10 WF .65(+0.08) | 
FLX h-orb-tf5#10|mid m40 L750 K1500 S- T- TT | .00/.63/.67 [.62,.73] b.32 | .67 | .04 | +0.01 | ONE_YEAR;NO_EDGE_VS_RANDOM
FLX h-first_bar_mom-tf15#8|nyam m40 L750 K1500 S- T- TT | .00/.64/.66 [.62,.71] b.34 | .66 | .09 | +0.07 | NO_EDGE_VS_RANDOM
FLX straddle-tf30#8|mid m40 L750 K1500 S- T- TT | .00/.61/.66 [.61,.71] b.34 | .66 | .03 | +0.09 WF .60(+0.10) | ONE_YEAR
FLX squeeze-tf5#20|mid m40 L750 K1500 S- T- TT | .00/.60/.64 [.58,.69] b.35 | .65 | .08 | -0.01 WF .60(+0.27) | ONE_YEAR;NO_EDGE_VS_RANDOM
FLX h-vwap_z-tf5#10|mid m40 L750 K1500 S- T- TT | .00/.58/.63 [.58,.68] b.37 | .64 | .05 | +0.06 | NO_EDGE_VS_RANDOM
FLX h-vwap_band-tf5#8|mid m40 L- K1500 S- T- TT | .00/.54/.62 [.57,.67] b.38 | .62 | .07 | -0.02 | ONE_YEAR;NO_EDGE_VS_RANDOM
FLX h-donchian-tf15#10|nyam m40 L750 K1500 S- T- TT | .00/.31/.62 [.57,.67] b.34 | .62 | .05 | +0.05 | ONE_YEAR;NO_EDGE_VS_RANDOM
LP+ donchian-tf5#5|pm m30 L- K- S- T- TT | .24/.44/.48 [.43,.53] b.51 | .48 | .41 | +0.09 WF .43(+0.11) | ONE_YEAR
LP+ rsi2-tf1#9|mid m30 L- K- S- T- TT | .24/.43/.46 [.41,.51] b.54 | .46 | .41 | +0.04 WF .40(+0.19) | ONE_YEAR;NO_EDGE_VS_RANDOM
LP+ squeeze-tf1#22|pm m30 L- K- S- T- TT | .24/.43/.45 [.40,.49] b.54 | .45 | .40 | +0.12 WF .39(+0.06) | ONE_YEAR
LP+ h-tod_drift-tf5#19|mid m40 L1000 K- S- T- TT | .20/.39/.44 [.38,.51] b.52 | .44 | .39 | +0.09 | ONE_YEAR
LP+ h-donchian-tf15#5|nyam m30 L- K- S- T- TT | .19/.39/.44 [.37,.49] b.53 | .44 | .39 | +0.05 | ONE_YEAR;NO_EDGE_VS_RANDOM
LP+ ema_pullback-tf1#23|pm m20 L- K- S- T- TT | .19/.39/.44 [.39,.48] b.53 | .44 | .40 | +0.16 WF .41(+0.10) | ONE_YEAR
LP+ ema_pullback-tf1#19|nyam m20 L- K- S- T- TT | .23/.41/.43 [.39,.48] b.56 | .44 | .40 | +0.18 WF .40(+0.11) | ONE_YEAR
LP+ tema_slope-tf1#16|nyam m40 L- K- S- T- TT | .17/.38/.43 [.38,.49] b.54 | .44 | .38 | +0.09 WF .42(+0.10) | ONE_YEAR
LP0 straddle-tf30#10|nyam m40 L1000 K- S- T- TT | .67/.71/.71 [.67,.74] b.29 | .71 | .23 | +0.07 WF .66(+0.06) | NO_EDGE_VS_RANDOM
LP0 h-first_bar_mom-tf15#21|nyam m40 L1000 K- S- T- TT | .63/.69/.69 [.66,.73] b.31 | .69 | .29 | +0.04 | NO_EDGE_VS_RANDOM
LP0 h-orb-tf5#10|mid m40 L1000 K3000 S- T- TT | .00/.68/.69 [.65,.73] b.31 | .69 | .13 | +0.02 | ONE_YEAR;NO_EDGE_VS_RANDOM
LP0 straddle-tf30#20|mid m40 L1000 K3000 S- T- TT | .00/.67/.68 [.64,.72] b.32 | .68 | .13 | +0.10 WF .66(+0.13) | ONE_YEAR
LP0 straddle-tf30#10|pm m40 L1000 K- S- T- TT | .56/.67/.68 [.65,.71] b.32 | .68 | .27 | +0.05 WF .66(+0.15) | ONE_YEAR;NO_EDGE_VS_RANDOM
LP0 h-donchian-tf15#10|nyam m40 L1000 K3000 S- T- TT | .00/.60/.67 [.64,.72] b.32 | .68 | .13 | +0.07 | ONE_YEAR;NO_EDGE_VS_RANDOM
LP0 h-vwap_z-tf5#8|mid m40 L1000 K3000 S- T1 TT | .00/.65/.66 [.63,.70] b.34 | .66 | .19 | -0.04 | NO_EDGE_VS_RANDOM
LP0 h-donchian-tf30#10|nyam m40 L1000 K- S- T- TT | .35/.60/.66 [.61,.71] b.32 | .66 | .33 | +0.06 | NO_EDGE_VS_RANDOM
APX ema_pullback-tf1#22|pm m20 L- K- S2000 T- TT | .22/.38/.42 [.38,.47] b.57 | .43 | .42 | +0.13 WF .42(+0.11) | ONE_YEAR
APX fp-donchian-tf15#15|pm m40 L1000 K- S3000 T- TT | .19/.36/.42 [.36,.48] b.53 | .49 | .42 | +0.05 WF .42(+0.38) | ONE_YEAR;NEAREST_POOL
APX rsi2-tf1#9|mid m40 L- K- S1000 T- TT | .24/.40/.41 [.37,.46] b.59 | .42 | .41 | +0.05 WF .33(+0.15) | ONE_YEAR;NO_EDGE_VS_RANDOM
APX fp-tod_drift-tf5#7|mid m80 L- K- S2000 T- tt- | .41/.41/.41 [.37,.44] b.59 | .41 | .41 | +0.03 WF .42(+0.42) | NET<=0;COST_RULE_FAIL
APX tod_drift-tf15#13|nyam m20 L- K- S3000 T- TT | .26/.40/.41 [.37,.45] b.59 | .49 | .41 | +0.06 WF .37(-0.01) | 
APX fp-orb-tf5#7|nyam m80 L- K- S2000 T- tt- | .40/.41/.41 [.37,.43] b.59 | .41 | .41 | +0.03 WF .35(+0.35) | COST_RULE_FAIL
APX fp-vwap_flip-tf1#14|mid m60 L1000 K- S3000 T- TT | .39/.40/.40 [.37,.43] b.60 | .48 | .40 | -0.02 WF .36(+0.16) | NET<=0;NO_EDGE_VS_RANDOM
APX donchian-tf5#8|pm m40 L- K- S1000 T- TT | .23/.39/.40 [.35,.45] b.59 | .41 | .40 | +0.03 WF .41(+0.10) | ONE_YEAR;NO_EDGE_VS_RANDOM
AEOD donchian-tf5#5|pm m30 L- K- S- T- TT | .22/.40/.42 [.37,.48] b.57 | .42 | .42 | +0.08 WF .36(+0.08) | ONE_YEAR
AEOD rsi2-tf1#9|mid m40 L- K- S- T- TT | .24/.40/.41 [.37,.46] b.59 | .42 | .41 | +0.05 WF .35(+0.16) | ONE_YEAR;NO_EDGE_VS_RANDOM
AEOD donchian-tf1#35|pm m30 L- K- S- T- TT | .22/.40/.41 [.36,.45] b.59 | .41 | .41 | +0.17 WF .42(+0.18) | ONE_YEAR
AEOD h-donchian-tf15#11|nyam m20 L1000 K- S- T- TT | .16/.33/.40 [.34,.46] b.54 | .40 | .40 | +0.07 | ONE_YEAR;NO_EDGE_VS_RANDOM
AEOD donchian-tf1#18|nyam m30 L- K- S- T- TT | .23/.39/.40 [.35,.44] b.60 | .40 | .40 | +0.11 WF .39(+0.14) | ONE_YEAR
AEOD tod_drift-tf15#19|mid m30 L1000 K- S- T- TT | .21/.38/.40 [.35,.45] b.60 | .40 | .40 | +0.09 WF .33(+0.04) | ONE_YEAR
AEOD tod_drift-tf30#19|mid m30 L1000 K- S- T- TT | .21/.38/.40 [.35,.45] b.60 | .40 | .40 | +0.10 WF .33(+0.03) | ONE_YEAR
AEOD squeeze-tf1#22|pm m30 L- K- S- T- TT | .21/.38/.40 [.35,.44] b.60 | .40 | .40 | +0.10 WF .38(+0.04) | ONE_YEAR
## Offline walk-forward (top-12 family-grid x session sets per firm, quarterly re-selection on trailing 12m; eod / primary model; OOS lift vs same-procedure random controls)
FLX realized: median OOS P5 .56 (IS .60), lift>0 10/12, lift CI>0 6; eod median OOS P5 .58; best straddle-tf30/nyam OOS .65 (+0.08)
LP+ realized: median OOS P5 .40 (IS .43), lift>0 12/12, lift CI>0 10; eod median OOS P5 .40; best donchian-tf1/pm OOS .44 (+0.18)
LP0 realized: median OOS P5 .61 (IS .65), lift>0 11/12, lift CI>0 8; eod median OOS P5 .61; best straddle-tf30/pm OOS .66 (+0.15)
APX intraday: median OOS P5 .37 (IS .40), lift>0 11/12, lift CI>0 10; eod median OOS P5 .77; best fp-tod_drift-tf5/mid OOS .42 (+0.42)
AEOD intraday: median OOS P5 .35 (IS .40), lift>0 11/12, lift CI>0 8; eod median OOS P5 .35; best donchian-tf1/pm OOS .42 (+0.18)
Notes: Lucid Flex needs >=2 trading days (consistency cushion) so P1 is structurally 0; P1/P3 cells maximise speed and often carry bust5 >= .5; WF grids with pass-2 members use out/wf_offline.csv (eod + intraday).
