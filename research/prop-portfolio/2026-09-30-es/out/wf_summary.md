# ES Homebase walk-forwards (15 jobs, 2026-10-01): param pick on 1 month by t_stat, test next 3 months, stitched OOS (phase 0), raw P&L at 1 ES
Window 2021-01..2024-12 (ticks from 2021-09-22). 4/15 positive OOS; costs: $4 RT/contract + 1 tick/side. 'fp' = fast-pass grid (tight stops/targets). ph = net of the 3 stitch phases (a robustness view of the same data).
| WF | OOS net $ | PF | Sharpe | trades | WR% | maxDD $ | avg $/tr | t | IS net $ | IS PF | phases net $ (0/1/2) | picks distinct/changes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| donchian-tf15-pm | +22,648 | 1.16 | 0.72 | 660 | 59 | -9,022 | +34.3 | 1.45 | +44,358 | 2.62 | +22,648/+14,740/+31,400 | 16/34 |
| donchian-tf30-pm | +15,864 | 1.16 | 0.63 | 456 | 59 | -12,380 | +34.8 | 1.22 | +33,543 | 2.72 | +15,864/+13,441/+9,412 | 14/31 |
| straddle-tf30-pm | +1,738 | 1.01 | 0.04 | 728 | 53 | -21,558 | +2.4 | 0.09 | +54,744 | 2.29 | +1,738/+7,918/+31,214 | 21/35 |
| vwap_flip-tf5-pm | +1,080 | 1.00 | 0.03 | 1233 | 55 | -11,300 | +0.9 | 0.06 | +48,106 | 2.03 | +1,080/-15,461/-3,505 | 23/34 |
| tod_drift-tf5-nyam | -5,841 | 0.97 | -0.18 | 754 | 34 | -30,302 | -7.7 | -0.35 | +51,783 | 2.19 | -5,841/-29,900/-38,502 | 15/34 |
| straddle-tf15-pm | -10,110 | 0.95 | -0.28 | 743 | 54 | -32,422 | -13.6 | -0.54 | +47,462 | 2.38 | -10,110/+12,248/+12,878 | 21/33 |
| tod_drift-tf5-pm-fp | -11,746 | 0.92 | -0.51 | 749 | 56 | -15,813 | -15.7 | -1.00 | +26,241 | 1.77 | -11,746/-13,092/-4,536 | 12/32 |
| tod_drift-tf15-nyam | -13,816 | 0.94 | -0.35 | 754 | 36 | -25,626 | -18.3 | -0.70 | +47,596 | 1.89 | -13,816/-27,087/-46,239 | 8/31 |
| vwap_z-tf5-mid | -14,877 | 0.90 | -0.61 | 788 | 54 | -21,298 | -18.9 | -1.19 | +23,462 | 1.72 | -14,877/-11,392/-26,234 | 21/35 |
| first_bar_mom-tf30-pm | -15,898 | 0.83 | -0.69 | 312 | 50 | -20,520 | -51.0 | -1.36 | +21,822 | 2.35 | -15,898/-4,916/+1,434 | 14/29 |
| tod_drift-tf5-nyam-fp | -19,604 | 0.81 | -1.12 | 754 | 65 | -20,262 | -26.0 | -2.20 | +15,533 | 1.76 | -19,604/-26,724/-15,052 | 14/34 |
| straddle-tf15-nyam | -20,828 | 0.89 | -0.69 | 754 | 55 | -30,487 | -27.6 | -1.36 | +34,583 | 1.94 | -20,828/-26,724/-28,439 | 20/34 |
| ib-tf30-pm | -25,158 | 0.71 | -1.23 | 302 | 47 | -27,609 | -83.3 | -2.44 | +13,950 | 1.74 | -25,158/-10,350/+11,896 | 11/32 |
| rsi2-tf5-nyam-fp | -33,454 | 0.87 | -1.16 | 1704 | 61 | -34,970 | -19.6 | -2.28 | +16,174 | 1.23 | -33,454/-45,894/-56,068 | 14/33 |
| rsi2-tf5-nyam | -39,322 | 0.88 | -0.90 | 1315 | 43 | -49,616 | -29.9 | -1.82 | +55,878 | 1.63 | -39,322/-56,590/-47,296 | 23/33 |

## Read
- Positive OOS in phase 0 (k/3 = stitch phases positive): donchian-tf15-pm (3/3 phases), donchian-tf30-pm (3/3 phases), straddle-tf30-pm (3/3 phases), vwap_flip-tf5-pm (1/3 phases)
- Sum of OOS net over all 15: -169,324; median OOS net -13,816; median OOS PF 0.92.
- Verdict: only donchian-tf15-pm (+$22.6k, PF 1.16, 660 tr, all 3 phases positive) and donchian-tf30-pm (+$15.9k, PF 1.16, 456 tr, 3/3) are clearly positive; straddle-tf30-pm (+$1.7k, PF 1.01) and vwap_flip-tf5-pm (+$1.1k, PF 1.00) are flat; the other 11 lose (rsi2 -$33k/-$39k, ib -$25k, straddle-tf15-nyam -$21k, tod_drift -$6k..-$20k). NQ had 6/15 positive (donchian-tf5-pm PF 1.22, up to +$82k); ES friction ($29 RT per ES vs $14 per NQ) halves the edge. IS->OOS Sharpe drop is large for every job (IS Sharpe is param-picked on 1 month): read OOS only.
- Use for the funded core: donchian PM (tf15, tf30). Everything else in the ES pass-rate rankings is rule-shape (day_take / lock) rather than expectancy.
