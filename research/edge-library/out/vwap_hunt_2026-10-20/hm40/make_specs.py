"""VWAP hunt on hm40 + the fixed 3:1 blocks (owner, 2026-10-20 23:2x ET: "redo the VWAP hunt on hm40 and the fixed 3:1 blocks once
feat/hm40-fixed-wf is merged. In-sample table and selection first, out-of-sample only for the picked boxes on my word.").

One spec (run_idea's format, exits hm40) per idea x bar size x session group: the idea's ONE main setting with 3 values, every other
setting fixed. `bp.py wf run <spec> --owner-said=...` runs its 120 boxes (60 for a family with no stop of its own) on the in-sample
months only. Written before any run; nothing here reads a result.

    make_specs.py [--write]      the list (and the spec files in specs/)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NY, NIGHT = ["nyam", "mid", "pm"], ["asia", "london", "eve"]
GATE = {"gate": "vwap_dev", "g_lvl": 0.0, "g_side": "with"}
ADX = {"gate": "adx", "g_n": 14, "g_side": "with"}

# (idea, key, family, main {setting: [3 values]}, fixed, bars, group -> sessions, max_tr, dir, reason)
R1 = "The VWAP is the session's average traded price; in a trend its first test is defended by the side in profit. Who loses: the traders who fade the trend at the VWAP."
R2 = "A pullback inside a trend that holds above its day-average price is a dip the trend's buyers take. Who loses: the sellers of the first red bar of an up day."
R3 = "A cross of the anchored day-average price that holds means control changed sides. Who loses: the side still positioned for the old trend."
R4 = "When the fast average crosses the day's fair price, control has changed sides (WEAK PRIOR). Who loses: the side that must exit."
R5 = "The first return to the VWAP after a run away meets the execution algorithms that benchmark to it. Who loses: those who chased the run."
R6 = "An entry on the side of the session's average price rides its in-profit side. Who loses: the traders fading the session's volume side."
R7 = "An opening-range break that agrees with the day's average price is the day choosing a side. Who loses: the opening-range faders."
R8 = "A stretch far from the average price reverts (the owner asked; fades have lost before). Who loses: the late chasers."
R9 = "A close beyond the VWAP band is one side taking control (the momentum twin of the fade). Who loses: the faders of the band."
R10 = "VWAP rules only when the market trends (ADX): the line holds when the trend is strong. Who loses: as the rule."
R11 = "Two anchors agree: the day session's and the whole Globex day's average buyers on the same side. Who loses: the side trapped against both."
R12 = "After the opening range breaks, the first return to the day's average price is where the breakout's side adds. Who loses: the faders at the VWAP."
R13 = "A reclaim of the day's average on real volume is the other side giving up. Who loses: the side that defended the VWAP and is now offside."
R14 = "The London session's average price carried into New York sets the side the European flow favours. Who loses: New York traders fighting it."
R15 = "Longer-anchored VWAPs (Globex day, week, yesterday's close, yesterday's / the overnight extremes) are the cost of bigger positions, defended on the first test. Who loses: those who sell into them."

SPECS = [
    (1, "pb", "jj_fair", {"vwap_slope": [15, 30, 60]}, {"entry": "mom", "fair": "vwap", "min_room": 0.0, "max_loss": 99, "end": "15:00", "wick": "off",
                                                         "pullback": "on", "cont": "off"}, ["1", "5", "15"], {"ny": ["nyam"]}, 20, "both", R1),     # one instance to 15:00 (end)
    (2, "tp", "vwap_trend_pull", {"x": [0.05, 0.1, 0.2]}, {"max_loss": 2}, ["1", "5", "15"], {"ny": NY}, 4, "both", R2),
    (3, "flip", "vwap_flip", {"hold": [1, 2, 3]}, {"anchor": "rth"}, ["1", "5", "15"], {"ny": NY}, 3, "both", R3),
    (3, "flip", "vwap_flip", {"hold": [1, 2, 3]}, {"anchor": "rth"}, ["5"], {"night": NIGHT}, 3, "both", R3),
    (4, "emax", "vwap_ema_x", {"n": [9, 21, 50]}, {"anchor": "rth"}, ["1", "5", "15"], {"ny": NY}, 3, "both", R4),
    (4, "emax", "vwap_ema_x", {"n": [9, 21, 50]}, {"anchor": "rth"}, ["5"], {"night": NIGHT}, 3, "both", R4),
    (5, "touch_us", "vwap_touch", {"away": [80, 160, 240]}, {"anchor": "us", "near": 3}, ["1", "5", "15"], {"ny": NY}, 3, "both", R5),
    (5, "touch_ldn", "vwap_touch", {"away": [80, 160, 240]}, {"anchor": "london", "near": 3}, ["5"], {"ldn": ["london"]}, 3, "both", R5),
    (5, "touch_day", "vwap_touch", {"away": [80, 160, 240]}, {"anchor": "day", "near": 3}, ["5"], {"asia": ["asia"]}, 3, "both", R5),
    (6, "g_fvg", "fvg", {"min_gap": [0.1, 0.25, 0.5]}, {"mode": "touch", "new_gap": "replace", **GATE}, ["5", "15"], {"ny": NY}, 3, "both", R6),
    (6, "g_fvg", "fvg", {"min_gap": [0.1, 0.25, 0.5]}, {"mode": "touch", "new_gap": "replace", **GATE}, ["5"], {"night": NIGHT}, 3, "both", R6),
    (6, "g_disp", "displace", {"k": [1.0, 1.5, 2.0]}, {"mode": "follow", "close_r": 0.0, **GATE}, ["5", "15"], {"ny": NY}, 3, "both", R6),
    (6, "g_disp", "displace", {"k": [1.0, 1.5, 2.0]}, {"mode": "follow", "close_r": 0.0, **GATE}, ["5"], {"night": NIGHT}, 3, "both", R6),
    (6, "g_cbrk", "candle_sweep", {"back": ["range", "body", "far"]}, {"mode": "break", **GATE}, ["5", "15"], {"ny": NY}, 3, "both", R6),
    (6, "g_cbrk", "candle_sweep", {"back": ["range", "body", "far"]}, {"mode": "break", **GATE}, ["5"], {"night": NIGHT}, 3, "both", R6),
    (6, "g_donch", "donchian", {"n": [10, 20, 40]}, GATE, ["5", "15"], {"ny": NY}, 3, "both", R6),
    (6, "g_donch", "donchian", {"n": [10, 20, 40]}, GATE, ["5"], {"night": NIGHT}, 3, "both", R6),
    (7, "orb", "win_break", {"r_end": ["09:45", "10:00", "10:30"]}, {"r_start": "09:30", "entry": "market", "mode": "follow", "wait": "0", **GATE},
     ["1", "5", "15"], {"ny": ["nyam"]}, 1, "both", R7),
    (7, "orbc_long", "orb_confirm", {"or_min": ["15", "30", "60"]}, GATE, ["5"], {"ny": NY}, 1, "long", R7),
    (7, "orbc_short", "orb_confirm", {"or_min": ["15", "30", "60"]}, GATE, ["5"], {"ny": NY}, 1, "short", R7),
    (8, "band", "vwap_band", {"band": [1.5, 2.0, 2.5]}, {}, ["1", "5", "15"], {"ny": NY}, 3, "both", R8),
    (8, "band", "vwap_band", {"band": [1.5, 2.0, 2.5]}, {}, ["5"], {"night": NIGHT}, 3, "both", R8),
    (8, "z", "vwap_z", {"zth": [1.5, 2.0, 2.5]}, {}, ["1", "5", "15"], {"ny": NY}, 3, "both", R8),
    (8, "z", "vwap_z", {"zth": [1.5, 2.0, 2.5]}, {}, ["5"], {"night": NIGHT}, 3, "both", R8),
    (9, "bbrk", "ind_signal", {"lvl": [1.0, 1.5, 2.0]}, {"ind": "vwap_dev", "mode": "follow", "edge": "enter"}, ["1", "5", "15"], {"ny": NY}, 3, "both", R9),
    (9, "bbrk", "ind_signal", {"lvl": [1.0, 1.5, 2.0]}, {"ind": "vwap_dev", "mode": "follow", "edge": "enter"}, ["5"], {"night": NIGHT}, 3, "both", R9),
    (9, "noise_long", "noise_band", {"k": [0.2, 0.3, 0.4]}, {"anchor": "rth"}, ["5"], {"ny": NY}, 1, "long", R9),
    (9, "noise_short", "noise_band", {"k": [0.2, 0.3, 0.4]}, {"anchor": "rth"}, ["5"], {"ny": NY}, 1, "short", R9),
    (10, "adx_flip", "vwap_flip", {"g_lvl": [20.0, 25.0, 30.0]}, {"anchor": "rth", "hold": 2, **ADX}, ["5"], {"ny": NY}, 3, "both", R10),
    (10, "adx_emax", "vwap_ema_x", {"g_lvl": [20.0, 25.0, 30.0]}, {"anchor": "rth", "n": 21, **ADX}, ["5"], {"ny": NY}, 3, "both", R10),
    (10, "adx_touch", "vwap_touch", {"g_lvl": [20.0, 25.0, 30.0]}, {"anchor": "us", "away": 160, "near": 3, **ADX}, ["5"], {"ny": NY}, 3, "both", R10),
    (10, "adx_tp", "vwap_trend_pull", {"g_lvl": [20.0, 25.0, 30.0]}, {"x": 0.1, "max_loss": 2, **ADX}, ["5"], {"ny": NY}, 4, "both", R10),
    (11, "flip_gx", "avwap_flip", {"hold": [1, 2, 3]}, {"line": "rth", "also": "globex"}, ["1", "5", "15"], {"ny": NY}, 3, "both", R11),
    (11, "touch_gx", "avwap_touch", {"away": [80, 160, 240]}, {"line": "rth", "also": "globex", "near": 3}, ["5"], {"ny": NY}, 3, "both", R11),
    (12, "orbpb", "orb_vwap_pb", {"or_min": [15, 30, 60]}, {"near": 0}, ["1", "5", "15"], {"ny": NY}, 1, "both", R12),
    (13, "reclaim", "avwap_flip", {"vol_m": [1.0, 1.5, 2.0]}, {"line": "rth", "hold": 1}, ["1", "5", "15"], {"ny": NY}, 3, "both", R13),
    (14, "flip_ldn", "avwap_flip", {"hold": [1, 2, 3]}, {"line": "rth", "also": "london"}, ["5", "15"], {"ny": NY}, 3, "both", R14),
    (15, "touch_long", "avwap_touch", {"line": ["globex", "week", "pdvwap"]}, {"away": 160, "near": 3}, ["5", "15"], {"ny": NY}, 3, "both", R15),
    (15, "touch_long", "avwap_touch", {"line": ["globex", "week", "pdvwap"]}, {"away": 160, "near": 3}, ["5"], {"ldnasia": ["asia", "london"]}, 3, "both", R15),
    (15, "touch_ext", "avwap_touch", {"line": ["pdh", "pdl", "onh"]}, {"away": 160, "near": 3}, ["5"], {"ny": NY}, 3, "both", R15),
    (15, "flip_long", "avwap_flip", {"line": ["globex", "week", "pdvwap"]}, {"hold": 2}, ["5", "15"], {"ny": NY}, 3, "both", R15),
    (15, "flip_wk", "avwap_flip", {"hold": [1, 2, 3]}, {"line": "rth", "also": "week"}, ["5", "15"], {"ny": NY}, 3, "both", R15),
]


# ---- AMENDMENT C (2026-10-21 ~00:30 ET, before any of these runs): batch 2 -- the new xflow blocks on NQ and the research ideas that are
# new rules (RESEARCH_IDEAS.md; old legs and both-sided brackets left out)
RX = "When a fast average crosses a slow one the recent flow has turned; with volume behind it the turn is participation, not drift. Who loses: the side still positioned for the old direction."
RV = "A breakout on far more volume than this time of day usually trades is new participation and carries. Who loses: the range traders fading it."
SPECS_C = [
    (16, "emax", "ma_x", {"fast_n": [5, 9, 13]}, {"fast": "ema", "slow": "ema", "slow_n": 21, "swing": 3}, ["5", "15"], {"ny": NY}, 3, "both", RX),
    (16, "emax", "ma_x", {"fast_n": [5, 9, 13]}, {"fast": "ema", "slow": "ema", "slow_n": 21, "swing": 3}, ["5"], {"night": NIGHT}, 3, "both", RX),
    (16, "emavwma", "ma_x", {"slow_n": [20, 34, 50]}, {"fast": "ema", "fast_n": 9, "slow": "vwma", "swing": 3}, ["5", "15"], {"ny": NY}, 3, "both", RX),
    (16, "emavwap_rv", "ma_x", {"fast_n": [5, 9, 13]}, {"fast": "ema", "slow": "rth", "rvol_m": 1.5, "swing": 3}, ["5"], {"ny": NY}, 3, "both", RX),
    (16, "emax_side", "ma_x", {"fast_n": [5, 9, 13]}, {"fast": "ema", "slow": "ema", "slow_n": 21, "side": "vwap", "swing": 3}, ["5"], {"ny": NY}, 3, "both", RX),
    (17, "rvbrk", "rvol_break", {"m": [1.5, 2.0, 3.0]}, {"n": 20}, ["5", "15"], {"ny": NY}, 3, "both", RV),
    (17, "rvbrk", "rvol_break", {"m": [1.5, 2.0, 3.0]}, {"n": 20}, ["5"], {"night": NIGHT}, 3, "both", RV),
    (17, "rvbrk_n", "rvol_break", {"n": [10, 20, 40]}, {"m": 2.0}, ["5"], {"ny": NY}, 3, "both", RV),
    (18, "es_noise_long", "noise_band", {"k": [0.25, 0.35, 0.5]}, {"anchor": "rth"}, ["30"], {"ny": NY}, 1, "long",
     "Intraday momentum (Zarattini et al.): a move beyond the day's noise band carries. Who loses: the faders of the open."),
    (18, "es_noise_short", "noise_band", {"k": [0.25, 0.35, 0.5]}, {"anchor": "rth"}, ["30"], {"ny": NY}, 1, "short",
     "As es_noise_long, the short side."),
    (18, "es_st_adx", "supertrend", {"mult": [2.0, 3.0, 4.0]}, {"gate": "adx", "g_n": 14, "g_lvl": 20.0, "g_side": "with"}, ["15"], {"ny": NY}, 2, "both",
     "A supertrend flip while ADX says the market trends is a trend change. Who loses: the side positioned for the old trend."),
    (18, "es_avwap_onh", "avwap_flip", {"vol_m": [0.0, 1.5, 2.5]}, {"line": "onh", "also": "rth", "hold": 2}, ["5"], {"ny": ["nyam"]}, 3, "both",
     "The VWAP anchored at the overnight high is the average cost of everyone who bought since the night's top; a decided cross of it, on the 09:30 VWAP's side, changes control. Who loses: the trapped overnight buyers / sellers."),
    (19, "gc_0300", "open_candle", {"body_r": [0.4, 0.55, 0.7]}, {"start": "0300"}, ["5"], {"ldn": ["london"]}, 1, "both",
     "The London open is gold's own handover from Asia: a decided first candle sets the morning's side. Who loses: the Asia range traders."),
    (19, "gc_us_short", "tod_drift", {"off_min": [0, 15, 30]}, {}, ["15"], {"ny": ["nyam"]}, 1, "short",
     "Gold's US hours give back the Asian buying (Blose 2018; WGC 2026). Who loses: US-morning gold buyers."),
    (19, "gc_eve_long", "tod_drift", {"off_min": [60, 120, 180]}, {}, ["30"], {"eve": ["eve"]}, 1, "long",
     "Gold's Asian hours buy what US hours sold (the mirror of gc_us_short). Who loses: evening gold sellers."),
    (19, "gc_asia_brk", "donchian", {"n": [8, 10, 12]}, {"w_start": "03:00", "w_end": "05:00"}, ["15"], {"ldn": ["london"]}, 1, "both",
     "The London open breaks the quiet Asia range of gold with real flow. Who loses: the Asia range faders."),
    (20, "holy_grail", "ema_pullback", {"g_lvl": [20.0, 25.0, 30.0]}, {"n": 20, "gate": "adx", "g_n": 14, "g_side": "with"}, ["5"], {"ny": ["nyam"]}, 2, "both",
     "The first pullback to the EMA(20) in a strong trend (ADX) is bought by the trend's side (Raschke's holy grail). Who loses: the counter-trend faders."),
    (20, "volspike_pm", "vol_spike_break", {"m": [2.0, 3.0, 4.0]}, {}, ["15"], {"ny": ["pm"]}, 2, "both",
     "An afternoon breakout on a volume spike is institutional flow into the close. Who loses: the faders of the afternoon range."),
]
MARKET_OF = {"es_": "ES", "gc_": "GC"}


# ---- AMENDMENT F (2026-10-21 ~03:50 ET, before any of these runs): batch 3 -- rule types not weaker in Jan / May / Sep on the build days
# (CALENDAR.md), on ES and GC (new rules), and NQ first bars on 5m bars
JJ = {"entry": "mom", "fair": "vwap", "min_room": 0.0, "max_loss": 99, "end": "15:00", "wick": "off", "pullback": "on", "cont": "off"}
RF = "The first bar of a session carries the session's opening flow: a decided first bar is followed. Who loses: the faders of the open."
RG = "The newest gap on the side of the day's open is unfilled demand of the side in control; the return to it is bought. Who loses: those fading the day's side."
SPECS_F = [
    (21, "es_pb", "jj_fair", {"vwap_slope": [15, 30, 60]}, JJ, ["5"], {"ny": ["nyam"]}, 20, "both", R1),
    (21, "gc_pb", "jj_fair", {"vwap_slope": [15, 30, 60]}, JJ, ["5"], {"ny": ["nyam"]}, 20, "both", R1),
    (22, "es_fvgos", "fvg_oside", {"min_gap": [0.0, 0.1, 0.25]}, {"mode": "touch", "pick": "newest", "atr1": 3.0}, ["15"], {"ny": ["nyam"]}, 20, "both", RG),
    (22, "gc_fvgos", "fvg_oside", {"min_gap": [0.0, 0.1, 0.25]}, {"mode": "touch", "pick": "newest", "atr1": 3.0}, ["15"], {"ny": ["nyam"]}, 20, "both", RG),
    (23, "fbar", "first_bar_mom", {"k": [0.5, 1.0, 1.5]}, {}, ["5"], {"all": ["asia", "london", "nyam", "mid", "pm", "eve"]}, 1, "both", RF),
    (23, "es_fbar", "first_bar_mom", {"k": [0.5, 1.0, 1.5]}, {}, ["15"], {"all": ["asia", "london", "nyam", "mid", "pm", "eve"]}, 1, "both", RF),
    (23, "gc_fbar", "first_bar_mom", {"k": [0.5, 1.0, 1.5]}, {}, ["15"], {"all": ["asia", "london", "nyam", "mid", "pm", "eve"]}, 1, "both", RF),
    (24, "es_touch", "vwap_touch", {"away": [20, 40, 60]}, {"anchor": "us", "near": 2}, ["5"], {"ny": NY}, 3, "both", R5),
    (24, "gc_touch", "vwap_touch", {"away": [30, 60, 90]}, {"anchor": "us", "near": 2}, ["5"], {"ny": NY}, 3, "both", R5),
    (25, "es_orbpb", "orb_vwap_pb", {"or_min": [15, 30, 60]}, {"near": 0}, ["5"], {"ny": NY}, 1, "both", R12),
    (25, "gc_orbpb", "orb_vwap_pb", {"or_min": [15, 30, 60]}, {"near": 0}, ["5"], {"ny": NY}, 1, "both", R12),
]


# ---- AMENDMENT H (2026-10-21 ~06:45 ET, before any of these runs): idea 26, relative value NQ <-> ES (the new rv_fade block)
RRV = ("NQ and ES price the same US large-cap flow; when one runs ahead of the other in minutes, index arbitrage and basket traders pull it "
       "back. Who loses: the momentum chaser who bought the leader at its stretch.")
SPECS_H = [
    (26, "rv", "rv_fade", {"k": [1.5, 2.0, 2.5]}, {"look": 60}, ["1", "5", "15"], {"ny": NY}, 4, "both", RRV),
    (26, "es_rv", "rv_fade", {"k": [1.5, 2.0, 2.5]}, {"look": 60}, ["1", "5", "15"], {"ny": NY}, 4, "both", RRV),
    (26, "rv", "rv_fade", {"k": [1.5, 2.0, 2.5]}, {"look": 60}, ["5"], {"night": NIGHT}, 4, "both", RRV),
    (26, "es_rv", "rv_fade", {"k": [1.5, 2.0, 2.5]}, {"look": 60}, ["5"], {"night": NIGHT}, 4, "both", RRV),
    (26, "rv_look", "rv_fade", {"look": [30, 60, 120]}, {"k": 2.0}, ["5"], {"ny": NY}, 4, "both", RRV),
    (26, "es_rv_look", "rv_fade", {"look": [30, 60, 120]}, {"k": 2.0}, ["5"], {"ny": NY}, 4, "both", RRV),
]


# ---- AMENDMENT I (2026-10-21, before any of these runs): the research workflow's kept candidates (with the judges' fixes)
RON = ("Where the 09:30 open lands in the 01:00-09:30 range shows which side the overnight session chose; an opening-range break that way "
       "on a trending (ADX) day is the day following it. Who loses: opening-range faders fighting the overnight side.")
RVB = ("A break of the recent range on far more volume than that clock window usually trades is new participation and carries. "
       "Who loses: the range traders fading the break.")
ONR = {"k": 0.3, "earliest": "10:30", "ov_from": "01:00"}
SPECS_I = [
    (27, "onrorb", "onr_orb", {"adx_min": [10.0, 15.0, 20.0]}, ONR, ["15"], {"ny": ["nyam"]}, 1, "both", RON + " SEEN (proxy): its 10:00 twin was read on 2025-07..2026-10."),
    (27, "es_onrorb", "onr_orb", {"adx_min": [10.0, 15.0, 20.0]}, ONR, ["15"], {"ny": ["nyam"]}, 1, "both", RON + " The ES twin of the NQ rule, not tuned on ES."),
    (31, "es_rvbrk", "rvol_break", {"m": [1.0, 1.25, 1.5]}, {"n": 20}, ["15"], {"ny": NY}, 3, "both", RVB),
    (31, "gc_rvbrk", "rvol_break", {"m": [1.0, 1.25, 1.5]}, {"n": 20}, ["15"], {"ny": NY}, 3, "both", RVB),
]


# ---- AMENDMENT O (2026-10-21, before any of these runs): batch 4a -- every untried bar-based NQ family (one-sided entries only)
RO = "An untried engine family on the hunt's own route (hm60, 3:1 in-sample, wide exits judged broadly). Who loses: as the family's own rationale."
SPECS_O = [
    (40, "bigprint", "big_print", {"lots": [15, 25, 40]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (41, "c930", "candle930", {"body_r": [0.0, 0.5, 0.7]}, {}, ["5", "15"], {"ny": ["nyam"]}, 3, "both", RO),
    (42, "ddiv", "ddiv", {"n": [3, 5, 8]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (43, "fvgodir", "fvg_odir", {"min_gap": [0.0, 0.1, 0.25]}, {}, ["15"], {"ny": ["nyam"]}, 3, "both", RO),
    (44, "ibtouch", "ib_touch", {"ib_min": [15, 30, 60]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (45, "ifvg", "ifvg", {"min_gap": [0.1, 0.25, 0.5]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (46, "liq", "liq", {"levels": ["ldn", "on", "pd"]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (47, "openfade", "open_fade", {"k": [0.5, 1.0, 1.5]}, {}, ["5", "15"], {"ny": ["nyam"]}, 3, "both", RO),
    (48, "openfvg", "open_fvg", {"oc_min": [5, 15, 30]}, {}, ["15"], {"ny": ["nyam"]}, 3, "both", RO),
    (49, "orbclose", "orb_close", {"or_min": [5, 15, 30]}, {}, ["15"], {"ny": ["nyam"]}, 3, "both", RO),
    (50, "pinbar", "pinbar", {"wick": [0.6, 0.667, 0.75]}, {}, ["5", "15"], {"ny": NY}, 3, "both", RO),
    (51, "pullback", "pullback", {"level": [0.5, 0.62, 0.79]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (52, "rsi2", "rsi2", {"th": [5.0, 10.0, 15.0]}, {}, ["5", "15"], {"ny": NY}, 3, "both", RO),
    (53, "sfp", "sfp", {"swing": [15, 30, 60]}, {}, ["5", "15"], {"ny": NY}, 3, "both", RO),
    (54, "sweeprev", "sweep_rev", {"levels": ["both", "on", "pd"]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (55, "tema", "tema_slope", {"n": [10, 20, 40]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (56, "vabreak", "va_break", {"buf_pts": [3.0, 6.0, 9.0]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (57, "vareclaim", "va_reclaim", {"d_atr": [0.0, 0.25, 0.5]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
    (58, "vault", "vault_break", {"k": [0.2, 0.3, 0.4]}, {}, ["30"], {"ny": NY}, 3, "both", RO),
    (59, "vwapadx", "vwap_adx", {"adx_min": [15.0, 20.0, 25.0]}, {}, ["15"], {"ny": ["nyam"]}, 3, "long", RO),
    (60, "wincandle", "win_candle", {"k": [0.0, 1.0, 1.5]}, {}, ["5", "15"], {"ny": ["nyam"]}, 3, "both", RO),
    (61, "squeeze", "squeeze", {"sq_type": ["bbkc"]}, {}, ["15"], {"ny": NY}, 3, "both", RO),
]


# ---- AMENDMENT O, batch 4b (2026-10-21, before any of these runs): the onr_side gate on the stack-A families, and day_move
# A family takes ONE open-layer gate: where stack A used gate vwap_dev, the gated version here swaps it for onr_side (a different rule).
RG = "The same entry, taken only on the side the 09:30 open's third of the overnight range gives (onr_side_study: +1.4 points in-sample). Who loses: the side trapped against the overnight session's choice."
ONS = {"gate": "onr_side", "g_side": "with"}
SPECS_P = [
    (70, "orbcl_ons", "orb_confirm", {"or_min": ["15", "30", "60"]}, ONS, ["5"], {"ny": NY}, 1, "long", RG),
    (70, "rvbrk15_ons", "rvol_break", {"m": [1.5, 2.0, 3.0]}, {"n": 20, **ONS}, ["15"], {"ny": NY}, 3, "both", RG),
    (70, "disp15_ons", "displace", {"k": [1.0, 1.5, 2.0]}, {"mode": "follow", "close_r": 0.0, **ONS}, ["15"], {"ny": NY}, 3, "both", RG),
    (70, "donch15_ons", "donchian", {"n": [10, 20, 40]}, ONS, ["15"], {"ny": NY}, 3, "both", RG),
    (70, "orbpb15_ons", "orb_vwap_pb", {"or_min": [15, 30, 60]}, {"near": 0, **ONS}, ["15"], {"ny": NY}, 1, "both", RG),
    (70, "winbrk15_ons", "win_break", {"r_end": ["09:45", "10:00", "10:30"]}, {"r_start": "09:30", "entry": "market", "mode": "follow", "wait": "0", **ONS}, ["15"], {"ny": ["nyam"]}, 1, "both", RG),
    (70, "noise_ons", "noise_band", {"k": [0.2, 0.3, 0.4]}, {"anchor": "rth", **ONS}, ["5"], {"ny": NY}, 1, "long", RG),
    (28, "daymove", "day_move", {"k": [0.15, 0.25, 0.35]}, {"at": "15:00"}, ["5"], {"pm": ["pm"]}, 1, "both",
     "At 15:00 a day that has already moved far from its open keeps going into the close (Gao-Han-Li-Zhou 2018: late-day momentum). Who loses: the afternoon faders and the close's forced hedgers."),
]


def specs(which=None) -> list:
    out = []
    for idea, key, fam, main, fixed, bars, groups, cap, side, reason in (which or SPECS):
        for g, sess in groups.items():
            for b in bars:
                name = f"vh_i{idea}_{key}_{b}_{g}"
                mkt = next((v for k, v in MARKET_OF.items() if key.startswith(k)), "NQ")
                out.append({"name": name, "reason": f"Portfolio hunt on hm60 (owner 2026-10-20), idea {idea}: {reason}", "family": fam, "markets": [mkt],
                            "bar_sizes": [b], "sessions": sess, "params": main, "fixed": fixed, "exits": "hm60",
                            "limits": {"max_tr": cap, "dir": side}})
    return out


def main(argv) -> None:
    docs = specs(SPECS_C if "--batch-c" in argv else SPECS_F if "--batch-f" in argv else SPECS_H if "--batch-h" in argv else SPECS_I if "--batch-i" in argv else SPECS_O if "--batch-o" in argv else SPECS_P if "--batch-p" in argv else None)
    for d in docs:
        print(d["name"], d["family"], d["bar_sizes"][0], ",".join(d["sessions"]), json.dumps(d["params"]), d["limits"]["dir"])
    print(len(docs), "specs")
    if "--write" in argv:
        (HERE / "specs").mkdir(exist_ok=True)
        for d in docs:
            (HERE / "specs" / f"{d['name']}.json").write_text(json.dumps(d, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
