"""Writes one idea spec (bp.py card format) per buildable idea of the owner's 100 breakout list (2026-10-28).
Fixed SL/TP only: exits hm60 and the table is read on its fixed-point cells (NQ 15/25/40/60 pts). One trade a day (max_tr 1)."""
import json, pathlib
OUT = pathlib.Path(__file__).parent / "specs"; OUT.mkdir(exist_ok=True)
# (idea no, name, session, bar, family, params, fixed, why)
I = [
 (2, "onr_orb", "nyam", "15", "onr_orb", {"k": [0.2, 0.3, 0.4]}, {}, "ORB with the overnight side"),
 (4, "orbclose_retest", "nyam", "5", "orb_close", {"or_min": [5, 15, 30, 60]}, {"entry": "limit", "start": "0930"}, "opening range broken on a close, enter on the retest"),
 (7, "orbclose_mkt", "nyam", "5", "orb_close", {"or_min": [5, 15, 30, 60]}, {"entry": "market", "start": "0930"}, "opening range broken on a close, market"),
 (12, "ibn_fade", "nyam", "5", "ib_n", {"ib_min": [5, 15, 30, 60]}, {"mode": "fade"}, "failed break of the opening range, fade back in"),
 (16, "pd_bracket", "nyam", "5", "pd_bracket", {"off_min": [0, 15, 30]}, {}, "prior day high/low break"),
 (18, "pd_bracket_on", "nyam", "5", "pd_bracket_x", {"off_min": [0, 15, 30]}, {"lvl": "pd_on"}, "prior day and overnight levels break"),
 (21, "pd_bracket_pw", "nyam", "5", "pd_bracket_x", {"off_min": [0, 15, 30]}, {"lvl": "pd_pw"}, "prior day and prior week levels break"),
 (22, "pd_bracket_mon", "nyam", "5", "pd_bracket", {"off_min": [0, 15, 30]}, {"days": "mon"}, "Monday break of the prior day range"),
 (28, "gap_go", "nyam", "5", "gap", {"min_gap_atr": [0.1, 0.25, 0.5]}, {"mode": "go"}, "gap and go"),
 (30, "va_break", "nyam", "5", "va_break", {"buf_pts": [2, 5, 10]}, {}, "prior value area high break"),
 (32, "lon_break", "nyam", "5", "lon_break", {"min_rng_atr": [0.0, 1.0, 2.0]}, {}, "London range break at the open"),
 (33, "on_bracket", "nyam", "5", "win_bracket", {"r_end": ["09:00", "09:15", "09:30"]}, {"r_start": "18:00"}, "overnight range break"),
 (34, "on_break_vol", "nyam", "5", "win_break_vol", {"vol_m": [1.5, 2.0, 3.0]}, {"r_start": "18:00", "r_end": "09:30", "mode": "follow"}, "overnight range break on volume"),
 (39, "pre_bracket", "nyam", "5", "win_bracket", {"r_end": ["09:15", "09:30"]}, {"r_start": "08:00"}, "premarket range break"),
 (40, "on_close_break", "nyam", "15", "win_break", {"r_end": ["09:00", "09:30"]}, {"r_start": "18:00", "mode": "follow"}, "overnight range broken on a 15m close"),
 (41, "london_kz_bracket", "london", "5", "win_bracket", {"r_end": ["04:00", "05:00"]}, {"r_start": "02:00"}, "London killzone range break"),
 (44, "squeeze_bbkc", "nyam", "5", "squeeze", {"sq_type": ["bbkc"]}, {}, "BB inside KC squeeze release"),
 (46, "squeeze_nr7", "nyam", "5", "squeeze", {"sq_type": ["nr7"]}, {}, "narrow range bar break"),
 (47, "squeeze_inside", "nyam", "5", "squeeze", {"sq_type": ["inside"]}, {}, "inside bar break"),
 (51, "donchian_bbw", "nyam", "5", "donchian", {"n": [10, 20, 40]}, {"gate": "bbw_rank", "g_lvl": 0.2, "g_side": "against"}, "Donchian break out of a squeeze"),
 (59, "donchian_trend", "nyam", "15", "donchian", {"n": [10, 20, 40]}, {"gate": "price_ema", "g_n": 50, "g_side": "with"}, "Donchian break with the 50 EMA"),
 (72, "donchian_atr", "nyam", "5", "donchian", {"n": [10, 20, 40]}, {"gate": "atr_rank", "g_lvl": 0.5, "g_side": "with"}, "Donchian break in expanding range"),
 (66, "open_atr_go", "nyam", "5", "open_atr_go_vwap", {"k": [0.5, 1.0, 1.5]}, {}, "open drive break with VWAP"),
 (73, "rvol_break", "nyam", "5", "rvol_break", {"m": [1.5, 2.0, 3.0]}, {}, "range break on relative volume"),
 (84, "w1030", "nyam", "5", "win_bracket", {"r_end": ["10:15", "10:30", "10:45"]}, {"r_start": "10:00"}, "10:00 range break"),
 (85, "w1300", "mid", "5", "win_bracket", {"r_end": ["12:45", "13:00", "13:15"]}, {"r_start": "12:30"}, "13:00 range break"),
 (86, "w1430", "pm", "5", "win_bracket", {"r_end": ["14:15", "14:30", "14:45"]}, {"r_start": "14:00"}, "14:30 range break"),
 (87, "w1500", "pm", "5", "win_bracket", {"r_end": ["14:45", "15:00", "15:15"]}, {"r_start": "14:30"}, "15:00 range break"),
 (88, "lunch_bracket", "mid", "5", "win_bracket", {"r_end": ["12:45", "13:00", "13:15"]}, {"r_start": "12:00"}, "lunch range break"),
 (89, "ib60_bracket", "nyam", "5", "ib_n", {"ib_min": [60]}, {"mode": "break"}, "first-hour range break"),
 (90, "w1530", "pm", "5", "win_bracket", {"r_end": ["15:15", "15:30"]}, {"r_start": "15:00"}, "late range break"),
]

DROP = {33, 34, 39, 40, 41, 44, 46, 47, 89, 90}
I = [x for x in I if x[0] not in DROP] + [
 (33, "on_bracket", "nyam", "5", "win_bracket", {"r_start": ["00:00", "01:00", "03:00"]}, {"r_end": "09:30"}, "overnight range break"),
 (34, "on_break_vol", "nyam", "5", "win_break_vol", {"vol_m": [1.5, 2.0, 3.0]}, {"r_start": "00:00", "r_end": "09:30", "mode": "follow"}, "overnight range break on volume"),
 (39, "pre_bracket", "nyam", "5", "win_bracket", {"r_start": ["08:00", "08:30", "09:00"]}, {"r_end": "09:30"}, "premarket range break"),
 (40, "on_close_break", "nyam", "15", "win_break", {"r_start": ["00:00", "01:00", "03:00"]}, {"r_end": "09:30", "mode": "follow"}, "overnight range broken on a 15m close"),
 (41, "london_kz_bracket", "london", "5", "win_bracket", {"r_end": ["03:30", "04:00", "05:00"]}, {"r_start": "02:00"}, "London killzone range break"),
 (44, "squeeze", "nyam", "5", "squeeze", {"sq_type": ["bbkc", "nr7", "inside"]}, {}, "squeeze release, narrow bar or inside bar break"),
 (89, "ib_break", "nyam", "5", "ib_n", {"ib_min": [15, 30, 60]}, {"mode": "break"}, "opening range break"),
 (90, "w1530", "pm", "5", "win_bracket", {"r_end": ["15:10", "15:20", "15:30"]}, {"r_start": "15:00"}, "closing hour range break"),
]
for no, nm, sess, bar, fam, params, fixed, why in I:
    name = f"nq_b{no:03d}_{nm}"
    spec = {"name": name, "version": 1,
      "card": {"why": f"Breakout idea #{no} of the owner's 100 list (2026-10-28): {why}, because the stops of the traders on the other side of the break feed the move.",
        "loser": "Traders on the wrong side of the break whose stops get hit.",
        "home": {"market": "NQ", "session": sess, "bar": bar}, "neighbors": ["ES nyam 15"] if fam == "onr_orb" else [f"NQ {sess} {"5" if bar == "15" else "15"}"],
        "main_setting": next(iter(params)), "sides": "both",
        "sides_why": "A break can go either way, one rule.", "loses_when": "Chop days where the break reverses at once."},
      "run": {"exits": "hm60", "family": fam, "params": params, **({"fixed": fixed} if fixed else {}), "limits": {"max_tr": 1}}}
    (OUT / f"{name}.json").write_text(json.dumps(spec, indent=1))
print(len(I), "specs")
