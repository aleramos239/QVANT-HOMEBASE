# Hunt 2026-10-20: the sheets to run

Curated 2026-10-20 before any hunt sheet was run. No P&L of any hunt sheet was read.

**19 sheets to run, 17 rejected.** All 36 designer sheets were checked against PREREG.md:
- every one passes `bp.py taught check` (exit 0, re-run at curation)
- every centre target is 1.5 x the stop
- no family rests orders on both sides
- every sheet has a reason and a "who loses", and `control: random`

**No exact duplicates.** No sheet has entries identical to an already-run store in `~/.homebase/taught/` (264 stores compared), and no two hunt sheets match each other.

The rejected files are in `taught/hunt_rejected/`, so `run_all.sh` cannot pick them up.

## The final list (run in this order)

"a day" is the designer's estimate, not counted on data. "Passes" means each engine session is its own pass, so the cap applies per pass: nyam 09:30-11:00, mid 11:00-13:30, pm 13:30-16:00.

| # | Sheet | Mkt | Family | Bars | Sessions | a day | Entry times (ET) | Why |
|---|---|---|---|---|---|---|---|---|
| 1 | hunt_dm_noise15_ny | NQ | noise_band | 15 | nyam, mid, pm | 1.2 | 09:45-10:45, 11:15+, 13:45+ | A close beyond the open's noise band (0.3 x daily ATR) on the VWAP side means one-way flow. Has a published basis (Zarattini et al.); never run on NQ both sides in cash hours |
| 2 | hunt_fv_openfvg5_oc15 | NQ | open_fvg | 5 | nyam, mid, pm | 1.0 | 09:50-10:55, some 11:15-13:25, 13:45-15:50 | Casper's FVG day trade: the first 5m gap that breaks the 09:30 candle. Family never run (fully blind) |
| 3 | hunt_fv_cbreak15_ema1h_midpm | NQ | candle_sweep (break) | 15 | mid, pm | 1.6 | 11:15-15:45 | The owner's 15m candle break on the 1h EMA50 side, moved to the hours the morning legs leave empty |
| 4 | hunt_fv_ifvg5_vwap | NQ | ifvg | 5 | nyam, mid, pm | 1.6 | 09:45-15:50 | A close through a whole gap traps the gap traders. Family never run (fully blind) |
| 5 | hunt_fv_oside5_a1m3_vwap | NQ | fvg_oside | 5 | one instance 09:30-15:00 | 1.4 | 09:45-15:00 | The only family that passed both gates, on 5m bars. Its entries differ from the 15m leg already in the stack. Partly seen |
| 6 | hunt_dm_hurst15_ny | NQ | hurst_ac_break | 15 | one instance 10:00-15:30 | 1.2 | 10:00-15:15 | A trend regime plus a 5-bar break: a trend resuming after a pause, both sides, cash hours |
| 7 | hunt_pb_leg15_ema20 | NQ | pullback | 15 | nyam, mid, pm | 0.9 | 10:00-15:50 | A 62% limit into a fresh 15m structure leg, on the EMA20 side, stop at the leg's start. Fully blind |
| 8 | hunt_fv_fvg15_vwap_p30 | NQ | fvg | 15 | nyam, mid, pm | 1.0 | 10:15-15:00 | The plain 15m FVG retest with a VWAP side. The no-side and EMA-side versions ran as controls; no walk-forward was read |
| 9 | hunt_fv_pullback5_s30_midpm | NQ | pullback | 5 | mid, pm | 0.8 | 11:00-15:50 | A half-way limit into a 30m structure leg after 11:00, wide stop at the leg's start. Fully blind |
| 10 | hunt_mx_es_noise_30 | ES | noise_band | 30 | nyam, mid, pm | 1.2 | 10:00-10:30, 11:30-13:00, 14:00-15:30 | The S&P version of #1, driven by dealer gamma and leveraged-ETF rebalancing. The only idea whose ES map was green |
| 11 | hunt_pb_ema15_first | NQ | ema_pullback | 15 | nyam, mid, pm | 1.0 | 09:45-15:45 | The first dip through EMA20 that closes back, with EMA50 sloping that way. Weakest prior |
| 12 | hunt_dm_vwflip15_rth_midpm | NQ | vwap_flip | 15 | mid, pm | 0.7 | 11:45+, 14:15+ | A cross of the 09:30 VWAP that holds 2 closes. It fires on turning days, when the trend legs stand aside |
| 13 | hunt_dm_ribbon15_ny | NQ | ema_ribbon | 15 | nyam, mid, pm | 0.8 | 09:45-15:45 | The first bar where the 8/21/55 EMAs stack. Weakest reason of the set |
| 14 | hunt_pb_vwaptouch_us40 | NQ | vwap_touch | 5 | nyam, mid, pm | 0.6 | 10:15-15:50 | A limit at the 09:30 VWAP on the first return after a 40-pt run away |
| 15 | hunt_pb_jj_vwap15 | NQ | jj_fair (vwap, mom, pullback) | 15 | one instance, cap 3 a day | 0.6 | 09:45-15:00 | The owner's VWAP pullback on 15m candles (the 1m version is noise). The idea's months are partly seen |
| 16 | hunt_dm_donch15_adx_midpm | NQ | donchian | 15 | mid, pm | 0.6 | 11:15-13:15, 13:45-15:45 | An afternoon break of the 5-hour channel while ADX >= 25 |
| 17 | hunt_dm_stflip15_midpm | NQ | supertrend | 15 | mid, pm | 0.6 | 11:15-13:15, 13:45-15:45 | A Supertrend(10,3) flip: a real change of side |
| 18 | hunt_mx_gc_noise_gx_30 | GC | noise_band | 30 | nyam, mid | 0.9 | 10:00-10:30, 11:30-13:00 | Gold's London + NY move from 01:00, followed in COMEX hours |
| 19 | hunt_mx_gc_pm_fix_candle_15 | GC | win_candle | 15 | nyam | 0.95 | 10:15 | Follows the LBMA PM gold auction candle; exits at the 13:30 settlement |

**Trades a day if every leg passed:** about 18.7, plus 1.74 from the Amendment A leg (`owner_fvg_oside_15_a1m3_nl_r1`). That is an upper bound. Most legs will fail Gate 1, and one-position-at-a-time skips signals that overlap.

### Things the runner must know

- **The 200-trade line on the walk-forward (P6.4).** Old 1-a-day legs got 130-245 test trades, and only those near 1 a day reached 200:
  - cl_am_disp15_vwap_10to11: 0.64 a day, 130 test trades
  - cl_pm_first_bar_cdl_ema_15: 0.63 a day, 165
  - owner_mid_first_bar_15: 0.99 a day, 182
  - owner_pm_first_bar_15: 0.98 a day, 245

  So rows 12-17 (0.6-0.8 a day) are at risk of failing P6.4 on count alone, unless the real count beats the estimate. Their per-pass caps allow 2-3 a day. Row 19 (one a day, 0.95) is a coin flip.
- **The VWAP gate restarts at 11:00 and 13:30.** Rows 4, 5 and 8 use `vwap_dev`, so in the mid and pm passes their "session VWAP" side starts again at 11:00 and 13:30. The sheets say so in not_run.
- **Struct stops must average more than 20 pts.** This can only be read on the result. The ones to check are rows 2, 5, 7 and 9.
- **ES and GC stops.** The 8-pt ES stop and 5-pt GC stop pass the 20-NQ-point line in dollars ($400 and $500) and in percent of price. They pay more slippage per point of stop than NQ (ES tick $12.50, GC tick $10).
- **Partly seen.** For rows 3, 5, 15, 1 and 16, the same family's months were read before (the family, not these entries). Say so with every result.

## Rejected (17), files moved to taught/hunt_rejected/

| Sheet | Reason |
|---|---|
| hunt_ck_c15_1030_ema | Clock ladder, dropped whole. Each slot is one candle a day after an EMA gate, about 0.6 a day at most. On the walk-forward that gives about 130-165 test trades (the 13:30 twin at 0.63 a day got 165), under P6.4's 200, so no slot can pass Gate 2. Reading their walk-forwards would only spend blind months. The same reason applies to all 8 slots |
| hunt_ck_c15_1100_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_ck_c15_1130_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_ck_c15_1200_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_ck_c15_1230_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_ck_c15_1300_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_ck_c15_1400_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_ck_c15_1430_ema | Clock ladder, dropped whole (see 10:30) |
| hunt_mx_es_orb30_close_5 | One a day in the nyam pass only, about 0.6 a day: cannot reach P6.4's 200 test trades |
| hunt_mx_es_ctrl_pm_first_bar_ema_15 | Control for an NQ leg that already failed its walk-forward (cl_pm_first_bar_cdl_ema_15: 165 test trades). One a day at about 0.55, so it cannot pass P6.4 itself |
| hunt_mx_es_ctrl_disp15_vwap_10to11 | Control for an NQ leg that already failed its walk-forward (cl_am_disp15_vwap_10to11: 130 test trades). One a day at about 0.6, so it cannot pass P6.4 |
| hunt_mx_gc_ldn_open_bar_15 | One a day at about 0.75, so P6.4 is out of reach. Its stop is small: the 03:00 GC candle's median range is 2.8 pts ($280), under the $400 that 20 NQ pts stands for. Every prior GC bar rule lost |
| hunt_fv_oside15_ema_r15 | Same family and bars as the Amendment A leg already in the stack, and its entries are a subset of that leg's (gap 0.1 with an EMA side, inside gap 0 with no cap). Amendment A allows ONE 15m oside leg. Its parent's blind months lost -$12.4k |
| hunt_pb_leg15_adx25 | Same trigger as hunt_pb_leg15_ema20 (the designer: "pick one"). It has an ADX gate instead of a side gate, and its count is lower (0.7) |
| hunt_pb_leg30_ema20 | Overlaps leg15_ema20 and pullback5_s30 (30m legs). About 0.5 a day, so it is at risk on both G3 and P6.4 |
| hunt_pb_vwaptouch_day40 | Same trigger as vwaptouch_us40 on a since-midnight VWAP, sharing touches with it. The 09:30 VWAP version is kept |
| hunt_pb_conti_both5_40 | Same 5m signals, filters and window as conti_day_both, which already ran on 5m bars; only the stop and target change. That signal stream's unseen months were read (-$19 a trade on 999 trades), so its blind months are spent. WHAT_WORKS lists the family as dead |

## Looks

19 sheets will be built. With a 95% random gate, about 1 passes Gate 1's random check by luck alone. Each walk-forward read adds another 5% chance of a pass by luck.
