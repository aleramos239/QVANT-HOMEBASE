"""One 3:1 in-sample spec (exits hm60: ATR + own stops + fixed points) per buildable idea 1-52 of ideas-100-asia-evening-2026-10-29.md.
NQ, evening (18:00-23:55 ET, w_flat 23:55). The idea number is in every name. Unbuildable: 18, 19, 20, 29, 30 (no RTH split in the daily bars)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
FL = {"w_flat": "23:55"}
# (name, tf, family, params (the main setting), fixed, limits, what the rule is)
I = [
 ("i01_tokyo_candle_follow", "5", "win_candle", {"k": [0.0]}, {"start": "19:00", "mode": "follow"}, {}, "follow the 19:00 Tokyo open candle"),
 ("i02_tokyo_orb15_follow", "5", "win_break", {"r_end": ["19:15"]}, {"r_start": "19:00", "mode": "follow"}, {}, "follow the first break of the 19:00 opening range"),
 ("i03_tokyo_orb15_fade", "5", "win_break", {"r_end": ["19:15"]}, {"r_start": "19:00", "mode": "fade"}, {}, "fade the first break of the 19:00 opening range"),
 ("i04_tokyo_sweep_fade", "5", "eve_rule", {"s_end": ["19:05"]}, {"rule": "sweep", "r_start": "18:00", "r_end": "19:00"}, {}, "fade the 19:00 candle that sweeps the first-hour range"),
 ("i05_hk_candle_follow", "5", "win_candle", {"k": [0.0]}, {"start": "21:30", "mode": "follow"}, {}, "follow the 21:30 Hong Kong open candle"),
 ("i06_hk_orb15_follow", "5", "win_break", {"r_end": ["21:45"]}, {"r_start": "21:30", "mode": "follow"}, {}, "follow the first break of the 21:30 opening range"),
 ("i07_hk_orb15_fade", "5", "win_break", {"r_end": ["21:45"]}, {"r_start": "21:30", "mode": "fade"}, {}, "fade the first break of the 21:30 opening range"),
 ("i08_hk_big_candle_follow", "5", "win_candle", {"k": [1.5, 2.0, 2.5]}, {"start": "21:30", "mode": "follow"}, {}, "follow a large 21:30 candle"),
 ("i09_lunch_lull_fade", "5", "win_break", {"r_end": ["22:30"]}, {"r_start": "21:30", "mode": "fade", "w_start": "22:30", "w_end": "23:30"}, {}, "fade the break of the 21:30 range in the Tokyo lunch"),
 ("i10_2000_break_follow", "5", "win_break", {"r_end": ["20:00"]}, {"r_start": "19:00", "mode": "follow"}, {}, "follow the break of the 19:00-20:00 range"),
 ("i11_sunday_candle_follow", "5", "win_candle", {"k": [0.0]}, {"start": "18:00", "mode": "follow", "days": "mon"}, {}, "follow the 18:00 candle on Sunday night only"),
 ("i12_sunday_gap_fade", "5", "eve_rule", {"off_min": [5, 15, 30]}, {"rule": "wkgap", "mode": "fade", "k": 0.3, "dow": "0"}, {}, "fade the Sunday weekend gap of 0.3 ATR or more"),
 ("i13a_c18_follow_tue", "5", "win_candle", {"k": [0.0]}, {"start": "18:00", "mode": "follow", "days": "tue"}, {}, "follow the 18:00 candle, Monday night"),
 ("i13b_c18_follow_wed", "5", "win_candle", {"k": [0.0]}, {"start": "18:00", "mode": "follow", "days": "wed"}, {}, "follow the 18:00 candle, Tuesday night"),
 ("i13c_c18_follow_thu", "5", "win_candle", {"k": [0.0]}, {"start": "18:00", "mode": "follow", "days": "thu"}, {}, "follow the 18:00 candle, Wednesday night"),
 ("i13d_c18_follow_fri", "5", "win_candle", {"k": [0.0]}, {"start": "18:00", "mode": "follow", "days": "fri"}, {}, "follow the 18:00 candle, Thursday night"),
 ("i14_sunday_long", "5", "tod_drift", {"off_min": [0]}, {"dir": "long", "exit_bars": 400, "days": "mon"}, {}, "always long on Sunday night"),
 ("i15_16_close_loc_follow", "5", "eve_rule", {"off_min": [5, 30, 60]}, {"rule": "loc10", "q": 0.9, "mode": "follow"}, {}, "long after a day that closed in its top 10 percent, short after the bottom 10"),
 ("i17_close_loc_fade", "5", "eve_rule", {"off_min": [5, 30, 60]}, {"rule": "loc10", "q": 0.9, "mode": "fade"}, {}, "the same close-location rule, faded"),
 ("i21_quiet_day_break", "5", "eve_rule", {"rq": [0.6, 0.8, 1.0]}, {"rule": "brk_win", "rg": "quiet", "r_start": "18:00", "r_end": "19:00", "mode": "follow"}, {}, "follow the 18:00-19:00 range break after a quiet day"),
 ("i22_wide_day_fade", "5", "eve_rule", {"off_min": [15, 30, 60]}, {"rule": "first_move", "rg": "wide", "rq": 1.5, "mode": "fade"}, {}, "fade the first evening move after a wide day"),
 ("i23_new_high_long", "5", "eve_rule", {"off_min": [5, 30, 60]}, {"rule": "newext", "which": "hi", "n_d": 20, "mode": "follow"}, {}, "long the evening after a 20-day high"),
 ("i24_new_low_bounce", "5", "eve_rule", {"off_min": [5, 30, 60]}, {"rule": "newext", "which": "lo", "n_d": 20, "mode": "follow"}, {}, "buy the bounce after a 20-day low"),
 ("i25_inside_day_break", "5", "pd_cond_bracket", {"off_min": [0, 30, 60]}, {"cond": "inside"}, {}, "break of the prior range after an inside day"),
 ("i26_close_return_limit", "5", "eve_rule", {"k": [0.15, 0.3, 0.5]}, {"rule": "away_lim", "anchor": "pdc", "ttl": 36}, {}, "limit at the prior close after the evening moved away from it"),
 ("i27_level_touch_follow", "5", "eve_rule", {"mode": ["follow"]}, {"rule": "lvl_touch"}, {}, "continue through the first touch of the prior high or low"),
 ("i28_level_touch_fade", "5", "eve_rule", {"mode": ["fade"]}, {"rule": "lvl_touch"}, {}, "fade the first touch of the prior high or low"),
 ("i31_open18_return_limit", "5", "eve_rule", {"k": [0.15, 0.3, 0.5]}, {"rule": "away_lim", "anchor": "o18", "ttl": 36}, {}, "limit at the 18:00 open after the evening moved away from it"),
 ("i32_vwap18_cross_follow", "5", "ind_signal", {"lvl": [0.0, 0.5, 1.0]}, {"ind": "vwap_dev", "edge": "enter", "mode": "follow"}, {}, "follow the first cross of the VWAP anchored at 18:00"),
 ("i33_above_open_and_vwap", "5", "eve_rule", {"off_min": [30, 60, 90]}, {"rule": "above_both", "mode": "follow"}, {}, "long above both the 18:00 open and its VWAP, short below both"),
 ("i34_35_first_range_break", "5", "win_break", {"r_end": ["18:15", "18:30", "18:45"]}, {"r_start": "18:00", "mode": "follow"}, {}, "follow the first break of the first 15, 30 or 45 minutes"),
 ("i36_gap_candle_disagree", "5", "eve_rule", {"mode": ["follow"]}, {"rule": "gap_disagree"}, {}, "trade the 18:00 candle when the gap points the other way"),
 ("i37_big_c18_fade", "5", "eve_rule", {"k": [0.05, 0.1, 0.15]}, {"rule": "c18", "ent": "fade"}, {}, "fade a large 18:00 candle at its close"),
 ("i38_big_c18_mid_limit", "5", "eve_rule", {"k": [0.05, 0.1, 0.15]}, {"rule": "c18", "ent": "mid", "ttl": 12}, {}, "limit at the middle of a large 18:00 candle in its direction"),
 ("i39a_open18_recross_follow", "5", "eve_rule", {"r_end": ["19:00", "20:00"]}, {"rule": "cross_open", "mode": "follow"}, {}, "follow the first close back across the 18:00 open"),
 ("i39b_open18_recross_fade", "5", "eve_rule", {"r_end": ["19:00", "20:00"]}, {"rule": "cross_open", "mode": "fade"}, {}, "fade the first close back across the 18:00 open"),
 ("i40_hour_sweep_fade", "5", "eve_rule", {"s_end": ["20:00"]}, {"rule": "sweep", "r_start": "18:00", "r_end": "19:00"}, {}, "fade a sweep of the first-hour range between 19:00 and 20:00"),
 ("i41_fvg15_limit", "15", "eve_rule", {"min_gap": [0.0, 0.1, 0.25]}, {"rule": "fvg"}, {}, "15m fair value gap limit on the 18:00 open side"),
 ("i42_fvg15_big_gap", "15", "eve_rule", {"min_gap": [0.5, 1.0, 1.5]}, {"rule": "fvg"}, {}, "15m fair value gap limit, large gaps only"),
 ("i43_fvg30_limit", "30", "eve_rule", {"min_gap": [0.0, 0.1, 0.25]}, {"rule": "fvg"}, {}, "30m fair value gap limit (the 1h bar is not built)"),
 ("i44_prev_candle_break", "15", "eve_rule", {"nr": [0.0]}, {"rule": "pcb"}, {"max_tr": 3}, "previous 15m candle break on the 18:00 open side"),
 ("i45_prev_candle_break_after_small", "15", "eve_rule", {"nr": [0.5, 0.75]}, {"rule": "pcb"}, {"max_tr": 3}, "previous candle break only after a small candle"),
 ("i46_outside_bar_follow", "15", "eve_rule", {"mode": ["follow"]}, {"rule": "outside"}, {"max_tr": 3}, "follow an outside 15m bar"),
 ("i47_failed_break_fade", "15", "candle_sweep", {"back": ["range", "body"]}, {"mode": "sweep"}, {"max_tr": 3}, "fade a failed 15m candle break"),
 ("i48_pin_bar_extreme", "15", "eve_rule", {"wick": [0.5, 0.6, 0.7]}, {"rule": "pin"}, {"max_tr": 3}, "pin bar at the evening high or low, trade the other way"),
 ("i49_order_block_limit", "5", "eve_rule", {"k": [1.5, 2.0, 2.5]}, {"rule": "ob", "ttl": 12}, {"max_tr": 3}, "limit at the open of the last opposite candle before a displacement"),
 ("i50_three_candles_fade", "15", "eve_rule", {"nbars": [3]}, {"rule": "streak", "mode": "fade"}, {"max_tr": 3}, "fade three same-colour 15m candles"),
 ("i51_three_candles_follow", "15", "eve_rule", {"nbars": [3]}, {"rule": "streak", "mode": "follow"}, {"max_tr": 3}, "follow three same-colour 15m candles"),
 ("i52_doji_extreme_break", "15", "eve_rule", {"dj": [0.1, 0.2]}, {"rule": "doji", "ttl": 3}, {"max_tr": 3}, "break of either side of a doji at the evening extreme"),
 ("ctl_c18_all_nights", "5", "win_candle", {"k": [0.0]}, {"start": "18:00", "mode": "follow"}, {}, "control: follow the 18:00 candle every night"),
]
for name, tf, fam, params, fixed, limits, why in I:
    spec = {"name": name, "reason": "Few traders are in the Asia evening, so a simple rule might hold; this tests: " + why, "family": fam,
            "markets": ["NQ"], "bar_sizes": [tf], "sessions": ["eve"], "params": params, "fixed": {**FL, **fixed}, "exits": "hm60",
            "limits": {"max_tr": 1, "dir": "both", **limits}}
    json.dump(spec, open(os.path.join(HERE, "specs", name + ".json"), "w"), indent=1)
print(len(I), "specs")
