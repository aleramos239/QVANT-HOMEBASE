# Offline walk-forward of the (heat-map cell, rules) search, test quarters 2022Q3..2024Q4 (wf_offline.py; details wf_offline.csv)
Each quarter SELECTS the (cell, rules) with the best stable rolling-start P5 on the trailing 12 months (attempts end before Q; 2022Q3 has ~9 months),
TESTS on attempts starting in Q, stitched. Rules grids = pass 2 / a3p2_lp, NOT coarsened. Control = the same selection on 10 day-matched random controls.
Entry = family-grid/session OOS-P5 (lift vs control OOS); * = survives (lift > 0 and lift CI upper > 0), ** = lift CI lower > 0. Apex UNCONFIRMED.
## eod / lucid_flex top 20 by OOS P5 (median IS .59)
  orb-tf5/mid .65(+0.37)** | tema_slope-tf5/mid .65(+0.22)** | first_bar_mom-tf15/nyam .64(+0.29)** | donchian-tf15/nyam .62(+0.27)**
  vwap_z-tf5/mid .62(+0.22)** | vwap_band-tf5/mid .58(+0.19)** | ema_pullback-tf5/mid .58(+0.23)** | s-tod_drift-tf30/mid .56(+0.05)*
  vwap_band-tf5/london .56(+0.50)** | orb-tf5/nyam .55(+0.35)** | first_bar_mom-tf15/mid .54(+0.21)** | s-tod_drift-tf30/pm .54(+0.03)*
  s-straddle-tf30/pm .53(+0.00)* | tema_slope-tf5/london .51(+0.44)** | donchian-tf15/pm .50(+0.19)** | s-tod_drift-tf5/mid .50(+0.07)**
  s-rsi2-tf1/mid .48(+0.12)** | s-donchian-tf15/nyam .47(+0.04)* | donchian-tf30/nyam .47(+0.19)** | s-tema_slope-tf5/london .47(+0.12)**
## eod / lucidpro top 20 by OOS P5 (median IS .40)
  s-tod_drift-tf5/mid .46(+0.12)** | s-tod_drift-tf30/mid .44(+0.11)** | s-donchian-tf15/nyam .43(+0.06)* | tod_drift-tf5/mid .41(+0.07)**
  donchian-tf15/nyam .40(+0.17)** | s-straddle-tf30/pm .40(+0.08)** | s-tod_drift-tf5/nyam .40(+0.06)* | s-tema_slope-tf5/london .39(+0.09)**
  donchian-tf15/pm .38(+0.17)** | vwap_band-tf5/london .38(+0.31)** | tod_drift-tf5/london .38(+0.12)** | s-rsi2-tf1/mid .37(+0.06)**
  s-tod_drift-tf30/pm .37(+0.02)* | first_bar_mom-tf15/nyam .36(+0.19)** | tod_drift-tf5/nyam .35(+0.02)* | tema_slope-tf5/london .34(+0.27)**
  orb-tf5/nyam .33(+0.24)** | donchian-tf30/nyam .33(+0.21)** | tema_slope-tf5/mid .32(-0.07) | vwap_band-tf5/mid .32(-0.02)
## eod / lucidpro_nodll top 20 by OOS P5 (median IS .64)
  orb-tf5/mid .66(+0.37)** | first_bar_mom-tf15/nyam .66(+0.31)** | donchian-tf30/nyam .66(+0.35)** | donchian-tf15/nyam .65(+0.27)**
  first_bar_mom-tf15/mid .65(+0.30)** | orb-tf5/nyam .65(+0.45)** | vwap_z-tf5/mid .65(+0.20)** | tema_slope-tf5/mid .64(+0.16)**
  s-straddle-tf30/pm .64(+0.07)** | s-tod_drift-tf30/mid .63(+0.09)** | ema_pullback-tf5/mid .62(+0.23)** | donchian-tf15/pm .60(+0.26)**
  s-tod_drift-tf30/pm .60(+0.02)* | vwap_band-tf5/mid .59(+0.15)** | vwap_band-tf5/london .58(+0.51)** | s-tod_drift-tf5/mid .57(+0.09)**
  s-donchian-tf15/nyam .55(+0.03)* | tema_slope-tf5/london .52(+0.43)** | s-rsi2-tf1/mid .50(+0.06)* | tod_drift-tf5/nyam .50(+0.03)*
## eod / apex (UNCONFIRMED) top 20 by OOS P5 (median IS .81)
  orb-tf5/mid .85(+0.27)** | tema_slope-tf5/mid .83(+0.12)** | first_bar_mom-tf15/nyam .82(+0.21)** | vwap_z-tf5/mid .81(+0.15)**
  vwap_band-tf5/mid .81(+0.16)** | donchian-tf30/nyam .81(+0.15)** | donchian-tf15/pm .80(+0.16)** | vwap_band-tf5/london .79(+0.45)**
  first_bar_mom-tf15/mid .79(+0.14)** | donchian-tf15/nyam .79(+0.16)** | s-tod_drift-tf30/mid .79(+0.04)* | orb-tf5/nyam .79(+0.29)**
  s-tod_drift-tf30/pm .78(+0.06)** | ema_pullback-tf5/mid .78(+0.14)** | s-straddle-tf30/pm .76(+0.02)* | s-donchian-tf15/nyam .75(+0.03)*
  tema_slope-tf5/london .73(+0.40)** | s-tod_drift-tf5/mid .71(+0.03)* | s-tema_slope-tf5/london .70(+0.08)** | tod_drift-tf5/nyam .70(+0.08)**
## intraday / lucid_flex top 20 by OOS P5 (median IS .27)
  s-tod_drift-tf5/mid .32(+0.11)** | s-tema_slope-tf5/london .28(+0.09)** | s-rsi2-tf1/mid .27(+0.10)** | tema_slope-tf5/london .27(+0.21)**
  tod_drift-tf5/mid .26(+0.05)* | orb-tf5/mid .26(+0.02)* | vwap_band-tf5/london .26(+0.20)** | donchian-tf15/nyam .25(+0.02)*
  first_bar_mom-tf15/nyam .25(+0.01)* | vwap_z-tf5/mid .25(+0.02)* | s-tod_drift-tf30/mid .25(+0.04)* | ema_pullback-tf5/mid .23(+0.00)*
  vwap_band-tf5/mid .23(-0.02) | s-straddle-tf30/pm .23(+0.03)* | first_bar_mom-tf15/mid .23(+0.03)* | orb-tf5/nyam .22(+0.06)**
  tema_slope-tf5/mid .22(-0.03) | donchian-tf15/pm .21(+0.03)* | tod_drift-tf5/nyam .21(+0.03)* | s-donchian-tf15/nyam .21(+0.01)*
## intraday / lucidpro top 20 by OOS P5 (median IS .36)
  s-tod_drift-tf5/mid .41(+0.11)** | s-tod_drift-tf30/mid .39(+0.09)** | s-donchian-tf15/nyam .38(+0.04)* | tod_drift-tf5/mid .37(+0.07)**
  s-straddle-tf30/pm .37(+0.06)** | s-tod_drift-tf5/nyam .36(+0.06)* | s-tema_slope-tf5/london .36(+0.09)** | first_bar_mom-tf15/nyam .36(+0.20)**
  donchian-tf15/nyam .36(+0.14)** | s-tod_drift-tf30/pm .35(+0.03)* | s-rsi2-tf1/mid .34(+0.06)** | tema_slope-tf5/london .34(+0.28)**
  vwap_band-tf5/london .34(+0.27)** | orb-tf5/nyam .33(+0.24)** | donchian-tf15/pm .32(+0.13)** | tod_drift-tf5/nyam .32(+0.01)*
  tod_drift-tf5/london .32(+0.07)** | first_bar_mom-tf15/mid .32(+0.19)** | vwap_z-tf5/mid .31(+0.00)* | donchian-tf30/nyam .30(+0.18)**
## intraday / lucidpro_nodll top 20 by OOS P5 (median IS .37)
  s-tod_drift-tf30/mid .39(+0.08)** | s-tod_drift-tf5/mid .38(+0.04)* | s-tod_drift-tf30/pm .37(+0.06)* | s-rsi2-tf1/mid .37(+0.08)**
  s-tod_drift-tf5/nyam .37(+0.05)* | s-tema_slope-tf5/london .37(+0.10)** | donchian-tf15/nyam .36(+0.10)** | tod_drift-tf5/mid .36(+0.03)*
  s-straddle-tf30/pm .35(+0.05)* | first_bar_mom-tf15/nyam .35(+0.11)** | s-donchian-tf15/nyam .35(+0.01)* | donchian-tf15/pm .35(+0.13)**
  tod_drift-tf5/london .34(+0.09)** | vwap_z-tf5/mid .33(+0.02)* | orb-tf5/nyam .32(+0.15)** | vwap_band-tf5/mid .32(+0.02)*
  first_bar_mom-tf15/mid .31(+0.09)** | donchian-tf30/nyam .31(+0.13)** | ema_pullback-tf5/mid .31(+0.04)* | tod_drift-tf5/nyam .31(-0.01)
## intraday / apex (UNCONFIRMED) top 20 by OOS P5 (median IS .37)
  s-straddle-tf30/pm .40(+0.08)** | first_bar_mom-tf15/nyam .39(+0.15)** | s-tod_drift-tf30/mid .38(+0.05)* | s-tod_drift-tf5/mid .37(+0.04)*
  tod_drift-tf5/mid .36(+0.04)* | donchian-tf15/pm .36(+0.09)** | s-tod_drift-tf30/pm .36(+0.02)* | s-tod_drift-tf5/nyam .36(+0.04)*
  tod_drift-tf5/nyam .36(+0.03)* | vwap_band-tf5/london .35(+0.14)** | donchian-tf15/nyam .35(+0.08)** | s-rsi2-tf1/mid .34(+0.07)**
  vwap_z-tf5/mid .34(+0.01)* | s-donchian-tf15/nyam .34(+0.02)* | s-tema_slope-tf5/london .34(+0.06)** | ema_pullback-tf5/mid .33(+0.04)*
  vwap_band-tf5/mid .33(+0.01)* | orb-tf5/mid .33(+0.09)** | donchian-tf30/nyam .33(+0.08)** | tema_slope-tf5/london .31(+0.09)**
## Families x sessions that survive OOS (rows surviving of 8 = 4 firms x 2 models; strict in brackets)
  donchian-tf15/nyam 8/8(7) | donchian-tf15/pm 8/8(7) | donchian-tf30/nyam 8/8(7) | first_bar_mom-tf15/mid 8/8(7)
  first_bar_mom-tf15/nyam 8/8(7) | orb-tf5/mid 8/8(6) | orb-tf5/nyam 8/8(8) | s-donchian-tf15/nyam 8/8(0)
  s-rsi2-tf1/mid 8/8(6) | s-straddle-tf30/pm 8/8(4) | s-tema_slope-tf5/london 8/8(8) | s-tod_drift-tf30/mid 8/8(4)
  s-tod_drift-tf5/mid 8/8(5) | tema_slope-tf5/london 8/8(8) | tod_drift-tf5/mid 8/8(2) | vwap_band-tf5/london 8/8(8)
  s-tod_drift-tf30/pm 7/8(1) | tod_drift-tf5/nyam 7/8(1) | vwap_z-tf5/mid 7/8(3) | ema_pullback-tf5/mid 6/8(3)
  s-tod_drift-tf5/nyam 6/8(0) | tod_drift-tf5/london 6/8(4) | vwap_band-tf5/mid 5/8(3) | tema_slope-tf5/mid 3/8(3)
Median IS->OOS drop 0.025; median OOS lift +0.078; median share of quarter-to-quarter pick changes 0.56.
