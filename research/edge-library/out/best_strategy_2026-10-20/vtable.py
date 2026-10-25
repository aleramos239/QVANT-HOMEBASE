import json, os, sys
T = os.path.expanduser('~/.homebase/taught')
groups = [
 ("1. Open-side FVG, 15m (middle-candle stop, 1R)", [
   ("owner_fvg_oside_15_mid_r1", "1 a day, any gap (the owner's sheet)"),
   ("cl_fvg_oside_15_mid_r1_t2", "2 a day, any gap"),
   ("cl_fvg_oside_15_mid_r1_t2_gap0p1", "2 a day, gap >= 0.1 ATR  << PICK"),
   ("cl_fvg_oside_15_mid_r1_t2_gap0p25", "2 a day, gap >= 0.25 ATR"),
   ("cl_fvg_oside_15_mid_r1_t3", "3 a day, any gap"),
   ("cl_fvg_oside_15_mid_r1_nl", "no cap, any gap"),
   ("cl_fvg_oside_15_mid_r05_t2", "2 a day, target 0.5R (high win rate)"),
   ("cl_fx_fvg_oside_15_p37", "2 a day, fixed 37-pt stop and target"),
 ]),
 ("2. 10:00-11:00 displacement, 15m (body >= 1.5 ATR, candle stop, 1R, 1 a day)", [
   ("cl_am_disp15_vwap_10to11", "VWAP side gate  << PICK"),
   ("displace_ema15_1r_10to11_k1p5", "EMA20 side gate (the owner's sheet)"),
   ("displace_ema15_1r_10to11_k2p0", "EMA20 gate, body >= 2.0 ATR"),
   ("cl_disp15_ema_allday_k1p5", "EMA20 gate, window stretched to 10:00-15:00"),
 ]),
 ("3. 13:30 first bar, 15m (follow the 13:30-13:45 bar, candle stop, 1R, 1 a day)", [
   ("cl_pm_first_bar_cdl_ema_15", "EMA20 side gate  << PICK"),
   ("cl_pm_first_bar_cdl_15", "no gate"),
 ]),
 ("Controls (not strategies)", [
   ("cl_fx_fvg_noside_15_p37", "FVG with NO open-side rule, fixed 37 pt"),
   ("cl_fx_fvg_ema20side_15_p37", "FVG with EMA20 side instead of the open, fixed 37 pt"),
   ("cl_fvg_oside_15_mid_r1_t2_gap0p1_es", "the FVG pick on ES"),
   ("cl_fvg_oside_15_mid_r1_t2_gap0p1_gc", "the FVG pick on GC"),
   ("cl_fvg_oside_30_mid_r1_t2", "the FVG on 30m bars"),
   ("cl_disp5_allday_k1p5", "displacement on 5m bars"),
 ]),
]
print("| variant | sheet | trades/day | avg trade | avg of its 3 targets | PF | win | Sharpe | months won | worst DD | lines held | $ a trade by year: 2021* · 22 · 23 · 24 · 25* |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for g, items in groups:
    print(f"| **{g}** | | | | | | | | | | | |")
    for name, label in items:
        d = json.load(open(f"{T}/{name}/result.json"))
        tf = list(d['bars'])[0]; b = d['bars'][tf]; c = b['centre']; m = c['metrics']; a = b['average']
        ys = " · ".join(f"{y['avg_trade']:+.0f}" for y in c['years'] if y['period'] != 'combined')
        print(f"| {label} | `{name}` | {m['trades']/m['days']:.2f} | ${m['avg_trade']:.0f} | ${a['avg_trade']:.0f} | {m['pf']:.2f} | {m['win']*100:.0f} % | {m['sharpe']:.2f} | {m['months_won']*100:.0f} % | ${m['dd_open']/1000:.1f}k | {c.get('held')} of {c.get('of')} | {ys} |")
