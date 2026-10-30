"""VWAP hunt 2026-10-20: write every taught sheet of the hunt (taught/vwap_*.json) from one table, before any run.

Run: .venv-research/bin/python research/edge-library/out/vwap_hunt_2026-10-20/make_sheets.py [--write]
Without --write it only prints the list. Each sheet = one family setting x one bar size x one stop (s25 = 25 / 37.5, s40 = 40 / 60,
struct = the family's own level at 1.5R); the lane adds the neighbour cells. Nothing here reads a result."""
from __future__ import annotations

import json
import sys
from pathlib import Path

EL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EL))
sys.path.insert(0, str(EL / "engine"))

NY = ["nyam", "mid", "pm"]
ALL = ["asia", "london", "nyam", "mid", "pm", "eve"]
GATE = {"gate": "vwap_dev", "g_lvl": 0.0, "g_side": "with"}
ADX = {"gate": "adx", "g_n": 14, "g_lvl": 25.0, "g_side": "with"}

# idea, key, family, settings, bars, sessions(5m/15m; 1m sheets are NY only), dir, struct?, cap, words, why (reason + who loses)
IDEAS = [
    (1, "pb", "jj_fair", {"entry": "mom", "fair": "vwap", "min_room": 0.0, "max_loss": 99, "end": "15:00", "wick": "off", "pullback": "on",
                          "vwap_slope": 30, "cont": "off"}, ["1", "5", "15"], NY, "both", False, 20,
     "From 09:35 to 15:00: the bar before touched the session VWAP, then a displacement bar (body larger than the previous body, the previous "
     "bar the opposite colour) closes away from the VWAP in the direction of the VWAP's 30-minute slope -> market with it at the close.",
     "The owner's VWAP pullback without the 09:45 continuation: the VWAP is the session's average traded price; in a trend the first test "
     "of it is defended by the side in profit. Who loses: the traders who fade the trend at the VWAP and are run over by the displacement."),
    (2, "tp", "vwap_trend_pull", {"x": 0.1, "max_loss": 2}, ["1", "5", "15"], NY, "both", None, 4,
     "Above a rising 09:30 VWAP and up at least 0.1 % over the last 60 minutes, the first down bar -> market long (mirror short); entries "
     "10:30-15:30, at most 4 trades and no entry after 2 losers in a pass.",
     "A pullback inside a trend that holds above its day-average price is a dip the trend's buyers take. Who loses: the sellers of the "
     "first red bar of an up day."),
    (3, "flip_rth", "vwap_flip", {"anchor": "rth", "hold": 2}, ["1", "5", "15"], ALL, "both", None, 3,
     "A bar closes across the VWAP anchored at the session's open (09:30 in New York, 03:00 London, 00:00 Asia) and the next 2 closes stay "
     "on the new side -> market with it.",
     "A cross of the anchored day-average price that holds two bars means control of the day changed sides. Who loses: the side still "
     "positioned for the old trend, whose stops feed the move."),
    (3, "flip_ses", "vwap_flip", {"anchor": "session", "hold": 2}, ["5", "15"], ALL, "both", None, 3,
     "A bar closes across the session VWAP (restarted at every pass start) and the next 2 closes stay on the new side -> market with it.",
     "As flip_rth with the pass's own VWAP: control of the pass changed sides. Who loses: the side positioned for the old pass trend."),
    (4, "emax_rth21", "vwap_ema_x", {"anchor": "rth", "n": 21}, ["1", "5", "15"], ALL, "both", None, 3,
     "The EMA(21) of the bar closes crosses the anchored VWAP (09:30 New York) at a bar close -> market with the cross.",
     "When the fast average crosses the day's fair price, control of the day has changed sides. Who loses: the side that must exit. "
     "WEAK PRIOR (the old pilot's close-crosses-VWAP did not survive)."),
    (4, "emax_ses21", "vwap_ema_x", {"anchor": "session", "n": 21}, ["5", "15"], ALL, "both", None, 3,
     "The EMA(21) of the bar closes crosses the session VWAP (restarted every pass) at a bar close -> market with the cross.",
     "As emax_rth21 against the pass's own VWAP. WEAK PRIOR."),
    (4, "emax_rth9", "vwap_ema_x", {"anchor": "rth", "n": 9}, ["5"], ALL, "both", None, 3,
     "The EMA(9) of the bar closes crosses the anchored VWAP at a bar close -> market with the cross.",
     "The faster average of the same idea: more crosses, earlier. WEAK PRIOR."),
    (4, "emax_rth50", "vwap_ema_x", {"anchor": "rth", "n": 50}, ["5"], ALL, "both", None, 3,
     "The EMA(50) of the bar closes crosses the anchored VWAP at a bar close -> market with the cross.",
     "The slower average of the same idea: fewer, more decided crosses. WEAK PRIOR."),
    (5, "touch_us160", "vwap_touch", {"anchor": "us", "away": 160, "near": 3}, ["1", "5", "15"], NY, "both", None, 3,
     "After a 1-minute close at least 40 points from the 09:30 VWAP, a limit order AT the VWAP (re-priced every bar close) on the side "
     "price came from; the first touch uses it up.",
     "The first return to the VWAP after a run away meets the resting orders of the execution algorithms that benchmark to it. Who "
     "loses: those who chased the run and sell into the VWAP test (Rother)."),
    (5, "touch_ldn160", "vwap_touch", {"anchor": "london", "away": 160, "near": 3}, ["5", "15"], ["london"] + NY, "both", None, 3,
     "As touch_us160 with the VWAP anchored at 03:00 ET (London), traded in London and carried into New York.",
     "The London VWAP is the European session's benchmark; carried into New York it is the overnight fair price (idea 14, the part the "
     "menu can build). Who loses: as touch_us160."),
    (5, "touch_day160", "vwap_touch", {"anchor": "day", "away": 160, "near": 3}, ["5", "15"], ["asia", "london"] + NY, "both", None, 3,
     "As touch_us160 with the VWAP anchored at 00:00 ET (the Globex day without its evening hours).",
     "The whole day's average price as the level. Who loses: as touch_us160."),
    (5, "touch_us80", "vwap_touch", {"anchor": "us", "away": 80, "near": 3}, ["5"], NY, "both", None, 3,
     "As touch_us160 armed by a 20-point run away from the 09:30 VWAP.",
     "A smaller run away arms more first touches. Who loses: as touch_us160."),
    (6, "g_fvg", "fvg", {"min_gap": 0.1, "mode": "touch", "new_gap": "replace", "w_end": "15:00", **GATE}, ["5", "15"], ALL, "both", None, 3,
     "A fair value gap at least 0.1 x ATR(14): a limit at its near edge, with the gap, a buy only above the session VWAP and a sell only "
     "below; the newest gap replaces the order; no new order from 15:00.",
     "A gap left by the side that holds the session's average price is its unfilled demand; the return to it meets that interest. Who "
     "loses: the traders fading the session's volume side into the gap."),
    (6, "g_disp", "displace", {"k": 1.5, "mode": "follow", "close_r": 0.0, **GATE}, ["5", "15"], ALL, "both", None, 3,
     "A bar whose body is at least 1.5 x ATR(14) of the bars before it, on the session VWAP's side (a green bar above the VWAP, a red bar "
     "below) -> market with it at the close.",
     "A displacement away from the session's average price on its own side is fresh one-way flow. Who loses: the side caught on the "
     "wrong side of the average."),
    (6, "g_cbrk", "candle_sweep", {"mode": "break", "back": "body", **GATE}, ["5", "15"], ALL, "both", None, 3,
     "A bar closes beyond the previous bar's body (break mode) on the session VWAP's side -> market with the break.",
     "A candle break in the direction of the session's average-price side is the trend continuing. Who loses: the faders of the break."),
    (6, "g_donch", "donchian", {"n": 20, **GATE}, ["5", "15"], ALL, "both", None, 3,
     "A close beyond the prior 20-bar channel, on the session VWAP's side -> market with it.",
     "A channel break on the side of the session's average price is a trend leg starting. Who loses: the range traders fading it."),
    (7, "orb30", "win_break", {"r_start": "09:30", "r_end": "10:00", "entry": "market", "mode": "follow", "wait": 0, **GATE},
     ["1", "5", "15"], ["nyam"], "both", None, 1,
     "The 09:30-10:00 range broken by a bar CLOSE after 10:00, only on the 09:30 VWAP's side (a break up above the VWAP, down below) -> "
     "market with the break; one trade a day.",
     "An opening-range break that agrees with the day's average price is the day choosing a side. Who loses: the opening-range faders."),
    (7, "orbc30_long", "orb_confirm", {"or_min": 30, **GATE}, ["5"], NY, "long", None, 1,
     "LONG ONLY: a bar closes above the 09:30-10:00 range while above the session VWAP -> market long; one trade a pass.",
     "As orb30, the long side alone (the family is one-sided). Who loses: the sellers of the high."),
    (7, "orbc30_short", "orb_confirm", {"or_min": 30, **GATE}, ["5"], NY, "short", None, 1,
     "SHORT ONLY: a bar closes below the 09:30-10:00 range while below the session VWAP -> market short; one trade a pass.",
     "As orb30, the short side alone. Who loses: the buyers of the low."),
    (8, "band2", "vwap_band", {"band": 2.0}, ["1", "5", "15"], ALL, "both", None, 3,
     "A close back inside the session VWAP +/- 2 sigma after a close outside -> fade toward the VWAP at market.",
     "A failed extension beyond 2 sigma returns to the average price. Who loses: the late breakout buyers. Prior: fades have lost."),
    (8, "z2", "vwap_z", {"zth": 2.0}, ["1", "5", "15"], ALL, "both", None, 3,
     "A close at least 2 sigma from the session VWAP -> fade it at market.",
     "Stretched from the average price, it reverts. Who loses: the chasers. Prior: fades have lost."),
    (9, "bbrk1", "ind_signal", {"ind": "vwap_dev", "lvl": 1.0, "mode": "follow", "edge": "enter"}, ["1", "5", "15"], ALL, "both", None, 3,
     "BAND BREAK: (close - session VWAP) / sigma crosses above +1 at a bar close -> market long; below -1 -> short.",
     "The momentum twin of the fade: a close beyond the 1-sigma band is one side taking control. Who loses: the faders of the band."),
    (9, "bbrk2", "ind_signal", {"ind": "vwap_dev", "lvl": 2.0, "mode": "follow", "edge": "enter"}, ["5", "15"], ALL, "both", None, 3,
     "BAND BREAK at 2 sigma: the deviation crosses beyond +/-2 sigma -> market with it.",
     "As bbrk1 at the outer band: rarer, stronger pushes."),
    (9, "noise", "noise_band", {"anchor": "rth", "k": 0.3}, ["5"], NY, "both", None, 1,
     "A bar closes beyond the 09:30 open +/- 0.3 x the daily ATR AND beyond the 09:30 VWAP -> market with it at the next open.",
     "A move beyond the day's noise band on the VWAP's side is directional flow (Zarattini). Who loses: the faders of the open."),
    (10, "adx_flip", "vwap_flip", {"anchor": "rth", "hold": 2, **ADX}, ["5"], ALL, "both", None, 3,
     "vwap_flip (anchor rth, hold 2) only while ADX(14) of the bars is at least 25 (a trend regime).",
     "The VWAP cross is a trend change only when the market trends. Who loses: as vwap_flip."),
    (10, "adx_emax", "vwap_ema_x", {"anchor": "rth", "n": 21, **ADX}, ["5"], ALL, "both", None, 3,
     "vwap_ema_x (EMA 21, anchor rth) only while ADX(14) >= 25.",
     "As adx_flip. WEAK PRIOR."),
    (10, "adx_touch", "vwap_touch", {"anchor": "us", "away": 160, "near": 3, **ADX}, ["5"], NY, "both", None, 3,
     "vwap_touch (09:30 VWAP, 40-point run away) only while ADX(14) >= 25.",
     "The first VWAP test of a trending day holds better than one of a range day. Who loses: as vwap_touch."),
    (10, "adx_tp", "vwap_trend_pull", {"x": 0.1, "max_loss": 2, **ADX}, ["5"], NY, "both", None, 4,
     "vwap_trend_pull only while ADX(14) >= 25.",
     "The trend pullback when the trend is strong. Who loses: as vwap_trend_pull."),
]


# ---- AMENDMENT A (2026-10-20 ~22:30 ET, before any of these runs): ideas 11-15 on the new blocks of families/avwap.py (owner: "if you
# need build new blocks, just make sure to save and add them"). Lines with an anchor before 00:00 trade asia, london and New York.
DAY5 = ["asia", "london", "nyam", "mid", "pm"]
IDEAS_A = [
    (11, "flip_rth_gx", "avwap_flip", {"line": "rth", "also": "globex", "hold": 2}, ["1", "5", "15"], NY, "both", None, 3,
     "A close crosses the 09:30 VWAP and the next 2 closes hold the new side, AND the close is on the same side of the 18:00 (Globex) "
     "VWAP -> market with it.",
     "Two anchors agree: the day session's and the whole Globex day's average buyers are on the same side. Who loses: the side "
     "trapped against both averages."),
    (11, "touch_rth_gx", "avwap_touch", {"line": "rth", "also": "globex", "away": 160, "near": 3}, ["5"], NY, "both", None, 3,
     "The first return to the 09:30 VWAP after a 40-point run away (a limit at it), only when the close is on the trade's side of the "
     "18:00 VWAP.",
     "The 09:30 VWAP test in the direction the Globex day agrees with. Who loses: those fading both averages."),
    (12, "orbpb30", "orb_vwap_pb", {"or_min": 30, "near": 0}, ["1", "5", "15"], NY, "both", None, 1,
     "The 09:30-10:00 range broken by a bar close -> a limit at the 09:30 VWAP, the way of the break, for the first pullback to it; "
     "one a day; the first touch uses it up.",
     "After the opening range breaks, the first return to the day's average price is where the breakout's side adds. Who loses: "
     "the faders of the break at the VWAP."),
    (12, "orbpb15", "orb_vwap_pb", {"or_min": 15, "near": 0}, ["5"], NY, "both", None, 1,
     "As orbpb30 with the 09:30-09:45 range.", "As orbpb30: an earlier, smaller range."),
    (12, "orbpb60", "orb_vwap_pb", {"or_min": 60, "near": 0}, ["5"], NY, "both", None, 1,
     "As orbpb30 with the 09:30-10:30 range.", "As orbpb30: the initial balance."),
    (13, "reclaim_vol", "avwap_flip", {"line": "rth", "hold": 1, "vol_m": 1.0}, ["1", "5", "15"], NY, "both", None, 3,
     "A close back across the 09:30 VWAP on a bar whose volume is at least the median of the same clock bar over the 14 days before, "
     "held one more close -> market with it.",
     "A reclaim of the day's average on real volume is the other side giving up, not noise. Who loses: the side that defended the "
     "VWAP and is now offside."),
    (14, "flip_rth_ldn", "avwap_flip", {"line": "rth", "also": "london", "hold": 2}, ["5", "15"], NY, "both", None, 3,
     "vwap_flip on the 09:30 VWAP (hold 2), only on the side of the London (03:00) VWAP.",
     "The London session's average price carried into New York sets the side the European flow favours. Who loses: New York traders "
     "fighting it."),
    (15, "touch_pdvwap", "avwap_touch", {"line": "pdvwap", "away": 160, "near": 3}, ["5", "15"], DAY5, "both", None, 3,
     "A limit at YESTERDAY's closing 09:30-16:00 VWAP on the first return after a 40-point run away from it.",
     "Yesterday's average price is the cost of yesterday's position holders; they defend it on the first test. Who loses: those who "
     "sell into it."),
    (15, "flip_pdvwap", "avwap_flip", {"line": "pdvwap", "hold": 2}, ["5", "15"], DAY5, "both", None, 3,
     "A close crosses yesterday's closing VWAP and holds 2 closes -> market with it.",
     "Acceptance beyond yesterday's average price. Who loses: yesterday's holders on the wrong side."),
    (15, "touch_pdh", "avwap_touch", {"line": "pdh", "away": 160, "near": 3}, ["5"], DAY5, "both", None, 3,
     "A limit at the VWAP anchored at yesterday's 09:30-16:00 high, first return after a 40-point run away.",
     "The average price of everyone who bought from yesterday's high (Shannon's anchored VWAP). Who loses: the trapped high buyers' "
     "counterparties."),
    (15, "touch_pdl", "avwap_touch", {"line": "pdl", "away": 160, "near": 3}, ["5"], DAY5, "both", None, 3,
     "A limit at the VWAP anchored at yesterday's 09:30-16:00 low, first return after a 40-point run away.", "As touch_pdh from the low."),
    (15, "touch_onh", "avwap_touch", {"line": "onh", "away": 160, "near": 3}, ["5"], NY, "both", None, 3,
     "A limit at the VWAP anchored at the overnight (18:00-09:30) high, first return after a 40-point run away.",
     "The average price since the overnight high. Who loses: as touch_pdh."),
    (15, "touch_onl", "avwap_touch", {"line": "onl", "away": 160, "near": 3}, ["5"], NY, "both", None, 3,
     "A limit at the VWAP anchored at the overnight low, first return after a 40-point run away.", "As touch_onh from the low."),
    (15, "flip_rth_wk", "avwap_flip", {"line": "rth", "also": "week", "hold": 2}, ["5", "15"], NY, "both", None, 3,
     "vwap_flip on the 09:30 VWAP (hold 2), only on the side of the weekly VWAP (from Sunday 18:00).",
     "The weekly VWAP side filter: trade the day's flips only with the week's average buyers. Who loses: the side against the week."),
    (15, "touch_week", "avwap_touch", {"line": "week", "away": 160, "near": 3}, ["5"], DAY5, "both", None, 3,
     "A limit at the weekly VWAP on the first return after a 40-point run away.", "The week's average price as the level."),
    (15, "flip_gx", "avwap_flip", {"line": "globex", "hold": 2}, ["5", "15"], DAY5, "both", None, 3,
     "A close crosses the 18:00 (Globex) VWAP and holds 2 closes -> market with it.",
     "The Globex day's average price as the line of control. Who loses: the side that must cover."),
    (15, "touch_gx", "avwap_touch", {"line": "globex", "away": 160, "near": 3}, ["5", "15"], DAY5, "both", None, 3,
     "A limit at the 18:00 (Globex) VWAP on the first return after a 40-point run away.", "As touch_us160 on the Globex day's VWAP."),
]

STOPS = {"s25": {"stop_pts": 25, "target_pts": 37.5}, "s40": {"stop_pts": 40, "target_pts": 60}}


def sheets(which=None) -> list:
    from blueprint import taught as TA
    out = []
    for idea, key, fam, st, bars, sess, side, _, cap, words, why in (which or IDEAS):
        struct = TA.passes_structure(fam)
        for b in bars:
            ss = NY if b == "1" and sess != ["nyam"] else sess
            stops = ["s25", "s40"] + (["struct"] if struct else [])
            if fam == "jj_fair":
                stops = ["s25", "s40"]               # its structure stop IS 25 points (jj_fair._stop): the s25 sheet
            for sp in stops:
                name = f"vwap_i{idea}_{key}_{b}_{sp}"
                ex = dict(STOPS[sp]) if sp != "struct" else {"stop": "struct", "target_r": 1.5}
                ex["max_trades"] = cap
                sw = "stop 25 / target 37.5 points" if sp == "s25" else "stop 40 / target 60 points" if sp == "s40" else \
                    "the family's own structure stop, target 1.5 x its distance"
                doc = {
                    "name": name,
                    "source": {"title": f"VWAP hunt 2026-10-20 (owner's brief, idea {idea}): {why}"},
                    "market": "NQ", "bars": [b], "sessions": ss, "dir": side,
                    "entry": {"family": fam, "settings": st, "words": words + f" {sw}; at most {cap} a pass; flat 15:58."},
                    "exits": ex,
                    "taught": [f"[owner 2026-10-20, brief prompt-vwap-5-10-a-day-3to1-blocks, idea {idea}] {words}",
                               f"[owner 2026-10-20, brief section 3] versions: bars 1 / 5 / 15, NY cash and London / overnight where the family "
                               f"runs, stops 25 / 30 / 40 and a structure stop, target 1.5 x the stop: this sheet is bars {b}, {sw}"],
                    "not_run": ["PRE-REGISTERED in out/vwap_hunt_2026-10-20/PREREG.md before any run; nothing tuned on a result.",
                                "1-MINUTE SHEETS run the New York passes only (machine time); 5 / 15-minute sheets every pass the family runs "
                                "except pre (08:25-09:30), which the brief does not ask for.",
                                "THE SESSION VWAP of the engine restarts at every pass start (09:30, 11:00, 13:30; 03:00 London; 00:00 "
                                "Asia; 18:00 evening); 'rth' / 'us' anchors stay at 09:30 for the New York passes.",
                                f"THE CAP: {cap} trades per session pass (several passes: a day can hold more, and a trade of one pass may "
                                "still be open when the next pass enters).",
                                "COSTS AND FILLS: the engine's own (1 tick of slippage, $4 a round turn, tick replay).",
                                "THE TEST DAYS are read only by `bp.py taught wf` (the 3:1 block walk-forward, once), its output sent to a log "
                                "unread until SELECTION.md is written."],
                    "control": "random"}
                out.append(doc)
    return out


def main(argv) -> None:
    docs = sheets(IDEAS_A if "--amend-a" in argv else None)
    for d in docs:
        print(d["name"], d["bars"], ",".join(d["sessions"]), d["dir"], d["entry"]["family"], json.dumps(d["exits"]))
    print(len(docs), "sheets")
    if "--write" in argv:
        for d in docs:
            (EL / "taught" / f"{d['name']}.json").write_text(json.dumps(d, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
