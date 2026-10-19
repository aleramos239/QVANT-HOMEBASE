"""candle930 (families/candle930.py): win_candle + the strong-candle gates, each pinned on a synthetic day; gates off = win_candle."""
from __future__ import annotations

import pytest

import l2sim as S
from families import blocks as B
from families import candle930 as C9
from test_blocks import D, TICK, minute_tape, rand_bars
from test_flex import go, trades
from test_orb830 import PX, hold

C930, WCAN = B.WRAPPED["candle930"], B.WRAPPED["win_candle"]
P = {"tf": "1", "sess": "nyam", "start": "09:30"}
K = S._sec("09:30") // 60
GREEN = (PX, PX + 7.0, PX - 1.0, PX + 6.0, 40)          # body 6, range 8, the close 1 under the high (0.125 of the range)
RED = (PX, PX + 1.0, PX - 7.0, PX - 6.0, 40)


def day(candle=GREEN, edits=None):
    b = [(PX, PX + TICK, PX - TICK, PX, 40)] * 960     # quiet: body 0, true range 0.5 -> ATR 0.5
    b[K] = candle
    b[K + 1:K + 5] = [hold(candle[3])] * 4
    for t, x in (edits or {}).items():
        b[S._sec(t) // 60] = x
    return b


def sides(params, bars):
    return [x[1] for x in trades(go(C930, {**P, **params}, bars)[1])]


@pytest.mark.parametrize("tf", ["1", "5"])
def test_gates_off_is_win_candle_trade_for_trade(tf):
    for seed in range(6):
        bars = rand_bars(960, 900 + seed, step=7.0)
        p = {**P, "tf": tf}
        assert trades(go(C930, p, bars)[1]) == trades(go(WCAN, p, bars)[1]), (tf, seed)


def test_close_r_and_atr_b():
    assert sides({}, day()) == ["long"]
    assert sides({"close_r": 0.15}, day()) == ["long"]
    assert sides({"close_r": 0.1}, day()) == []
    assert sides({"close_r": 0.15}, day(RED)) == ["short"]
    assert sides({"atr_b": 12.0}, day()) == ["long"]           # 6 >= 12 x 0.5
    assert sides({"atr_b": 12.5}, day()) == []


def test_big_n_reads_the_bars_before_the_candle_only():
    big = {"09:10": (PX, PX + 6.5, PX, PX + 6.25, 40), "09:11": (PX + 6.25, PX + 6.5, PX - TICK, PX, 40)}   # bodies 6.25 at 09:10 / 09:11
    assert sides({"big_n": 15}, day(edits=big)) == ["long"]
    assert sides({"big_n": 30}, day(edits=big)) == []
    assert sides({"tf": "5", "big_n": 100}, day()) == ["long"]
    assert sides({"tf": "5", "big_n": 200}, day()) == []       # 114 five-minute bars since 00:00: fewer than asked for


def test_pre_min_is_the_high_or_low_of_the_minutes_before():
    assert sides({"pre_min": 5}, day(edits={"09:20": (PX, PX + 8.0, PX - TICK, PX, 40)})) == ["long"]
    assert sides({"pre_min": 15}, day(edits={"09:20": (PX, PX + 8.0, PX - TICK, PX, 40)})) == []
    assert sides({"pre_min": 5}, day(RED, {"09:20": (PX, PX + TICK, PX - 8.0, PX, 40)})) == ["short"]
    assert sides({"pre_min": 15}, day(RED, {"09:20": (PX, PX + TICK, PX - 8.0, PX, 40)})) == []


def test_med_m_needs_ten_past_bodies(monkeypatch):
    monkeypatch.setattr(C9, "past_body", lambda root, iso, a, tf: 4.0)
    assert sides({"med_m": 1.5}, day()) == ["long"]            # 6 >= 1.5 x 4
    assert sides({"med_m": 1.6}, day()) == []
    got = []
    monkeypatch.setattr(C9, "past_body", lambda root, iso, a, tf: got.append(iso) or (None if len(got) <= 5 else 1.0))
    assert sides({"med_m": 1.0}, day()) == []                  # 9 of 14 dates
    assert len(got) == C9.MED_DAYS and max(got) < D.isoformat()


def test_past_body_is_the_candle_of_that_date(monkeypatch):
    bars = rand_bars(960, 77, step=7.0)
    monkeypatch.setattr(C9, "_DAY", {})
    monkeypatch.setattr(S, "load_tape", lambda iso, root, **kw: minute_tape(bars, "00:00", d=D))
    a = S._sec("09:30")
    assert C9.past_body("NQ", D.isoformat(), a, 60) == abs(bars[K][3] - bars[K][0])
    assert C9.past_body("NQ", D.isoformat(), a, 300) == abs(bars[K + 4][3] - bars[K][0])


def test_own_exits_are_twenty_stops_times_six_targets():
    cells = B.exits("own", "NQ", "candle930")
    assert len(cells) == 120 and len({S.cell_id(c) for c in cells}) == 120
    assert [c["tgt_r"] for c in cells[:6]] == [0.0, 0.5, 0.75, 1.0, 2.0, 3.0]
    assert {"struct1-r1", "datr10-r1", "pre1-r1", "onr1-r0", "pts100-r1"} <= {S.cell_id(c) for c in cells}


def dist(params, bars):
    (t,) = trades(go(C930, {**P, **params}, bars)[1])
    return t[1], abs(t[2] - t[3])


def test_the_stops_sit_where_they_say():
    assert dist({"stop_mode": "struct", "stop_val": 1.0}, day()) == ("long", 7.0)      # close PX + 6, low PX - 1
    assert dist({"stop_mode": "struct", "stop_val": 0.5}, day()) == ("long", 3.5)
    assert dist({"stop_mode": "struct", "stop_val": 2.0}, day()) == ("long", 14.0)
    assert dist({"stop_mode": "datr", "stop_val": 10.0}, day()) == ("long", 10.0)       # daily bars of range 100
    assert dist({"stop_mode": "pre", "stop_val": 1.0}, day(edits={"08:40": (PX, PX + TICK, PX - 12.0, PX, 40)})) == ("long", 18.0)
    assert dist({"stop_mode": "pre", "stop_val": 1.0}, day(RED, {"08:40": (PX, PX + 12.0, PX - TICK, PX, 40)})) == ("short", 18.0)
    assert dist({"stop_mode": "onr", "stop_val": 1.0}, day(RED, {"03:00": (PX, PX + 30.0, PX - TICK, PX, 40)})) == ("short", 36.0)
    assert dist({"stop_mode": "pre", "stop_val": 1.0}, day(edits={"03:00": (PX, PX + TICK, PX - 30.0, PX, 40)}))[1] == 6.0 + TICK   # 03:00 is not pre-open


def test_break_is_a_straddle_of_the_candle_with_the_stop_past_the_other_extreme():
    s1 = {"entry": "break", "stop_mode": "struct", "stop_val": 1.0}
    assert sides(s1, day()) == []                                                          # nothing trades through the candle
    assert dist(s1, day(edits={"09:40": (PX + 6.0, PX + 10.0, PX + 6.0, PX + 9.0, 40)})) == ("long", 8.25)      # PX + 7.25 down to PX - 1
    assert dist({**s1, "stop_val": 2.0}, day(edits={"09:40": (PX + 6.0, PX + 10.0, PX + 6.0, PX + 9.0, 40)})) == ("long", 16.5)
    assert dist(s1, day(RED, {"09:40": (PX - 6.0, PX - 6.0, PX - 10.0, PX - 9.0, 40)})) == ("short", 8.25)
    assert dist(s1, day(edits={"09:40": (PX + 6.0, PX + 6.0, PX - 3.0, PX - 2.0, 40)})) == ("short", 8.25)      # a green candle broken low


# ---- sec: the 30-second candle (owner 2026-10-18) --------------------------------------------------------------------------------------------
# minute_tape prints o at :00, then h at :15 for a DOWN minute -> the 09:30:00-09:30:30 candle of DOWN30 is (PX, PX + 8, PX, PX + 8): green,
# its low PX; the prints at :30 / :45 (PX - 1, PX - 2) come after the decision and must not change it.
DOWN30 = (PX, PX + 8.0, PX - 1.0, PX - 2.0, 40)
UP30 = (PX, PX + 1.0, PX - 8.0, PX + 2.0, 40)              # up minute: o, then l at :15 -> the candle (PX, PX, PX - 8, PX - 8): red
S30 = {"sec": 30, "stop_mode": "struct", "stop_val": 1.0}


def test_sec_candle_is_read_from_the_prints_at_its_close():
    got = trades(go(C930, {**P, **S30}, day(DOWN30))[1])
    assert len(got) == 1
    t, side, entry, sl = got[0]
    assert side == "long" and S._sec("09:30:30") < t < S._sec("09:31")   # ordered at the 30-second close, filled at the next print
    assert entry - sl == 8.0                                   # stop distance = the candle's close (PX + 8) to its low (PX), moved to the fill
    assert sides(S30, day(UP30)) == ["short"]
    assert sides({**S30, "mode": "fade"}, day(DOWN30)) == ["short"]


def test_pre_n_counts_candles_of_the_candle_size():
    hi = {"09:27": (PX, PX + 9.0, PX - TICK, PX - TICK, 40)}   # down minute: its high PX + 9 prints at 09:27:15
    assert sides({**S30, "pre_n": 5}, day(DOWN30, hi)) == ["long"]      # 5 x 30 s = from 09:27:30: the high is before it
    assert sides({**S30, "pre_n": 10}, day(DOWN30, hi)) == []           # 10 x 30 s = from 09:25:00: closes under PX + 9
    lo = {"09:27": (PX, PX + TICK, PX - 9.0, PX + TICK, 40)}   # up minute: its low PX - 9 prints at 09:27:15
    assert sides({**S30, "pre_n": 5}, day(UP30, lo)) == ["short"]
    assert sides({**S30, "pre_n": 10}, day(UP30, lo)) == []
    # on tf bars pre_n counts tf bars: 5 one-minute bars before 09:30
    assert sides({"pre_n": 5}, day(edits={"09:24": (PX, PX + 8.0, PX - TICK, PX, 40)})) == ["long"]
    assert sides({"pre_n": 10}, day(edits={"09:24": (PX, PX + 8.0, PX - TICK, PX, 40)})) == []


def test_sec_atr_b_med_m_vol_m_read_30_second_candles(monkeypatch):
    # quiet minutes split into 30 s candles of true range 0.25 / 0.5 alternating: ATR of the 14 before 09:30 = 0.375; body 8 = 21.3 x
    assert sides({**S30, "atr_b": 21.0}, day(DOWN30)) == ["long"]
    assert sides({**S30, "atr_b": 21.5}, day(DOWN30)) == []
    got = []
    monkeypatch.setattr(C9, "past_body", lambda root, iso, a, secs: got.append(secs) or 4.0)
    assert sides({**S30, "med_m": 2.0}, day(DOWN30)) == ["long"]      # 8 >= 2 x 4
    assert sides({**S30, "med_m": 2.1}, day(DOWN30)) == []
    assert set(got) == {30}                                           # the same 30 s candle of the dates before
    seen = []
    monkeypatch.setattr(C9, "past_candle", lambda root, iso, a, secs: seen.append(iso) or (1.0, 20.0 if iso == D.isoformat() else 10.0))
    assert sides({**S30, "vol_m": 2.0}, day(DOWN30)) == ["long"]      # today 20 >= 2 x the median 10
    assert sides({**S30, "vol_m": 2.1}, day(DOWN30)) == []
    assert max(x for x in seen if x != D.isoformat()) < D.isoformat()


@pytest.mark.parametrize("bad", [{"sec": 7}, {"sec": 30, "big_n": 3}, {"sec": 30, "k": 1.0}, {"sec": 30, "entry": "break"},
                                 {"sec": 20, "start": "09:30:10"}])
def test_sec_refuses_what_it_cannot_read(bad):
    with pytest.raises(ValueError):
        C930({**P, **bad})


def test_pre_dir_trades_only_with_the_0830_0930_move():
    up = {"09:29": (PX, PX + TICK, PX - TICK, PX + 1.0, 40)}   # 08:30 opens at PX, the 09:29 bar closes PX + 1: the hour went up
    dn = {"09:29": (PX, PX + TICK, PX - 1.0, PX - 1.0, 40)}
    assert sides({"pre_dir": "with"}, day(GREEN, up)) == ["long"]
    assert sides({"pre_dir": "with"}, day(GREEN, dn)) == []
    assert sides({"pre_dir": "with"}, day(RED, dn)) == ["short"]
    assert sides({"pre_dir": "with"}, day(RED, up)) == []
    assert sides({"pre_dir": "with"}, day(GREEN)) == []        # a flat hour
    assert sides({**S30, "pre_dir": "with"}, day(DOWN30, up)) == ["long"]
    assert sides({**S30, "pre_dir": "with"}, day(DOWN30, dn)) == []


def test_scan_end_takes_the_first_candle_of_the_window_that_passes():
    # 09:30 and 09:31 flat (every print PX: dojis); the 09:32 minute is DOWN30-shaped: its 09:32:00-09:32:30 candle is green, body 8, low PX
    flat = (PX, PX, PX, PX, 40)
    b = day(flat, {"09:31": flat, "09:32": DOWN30})
    assert sides(S30, b) == []                                         # the 09:30 candle alone: a doji, no trade
    got = trades(go(C930, {**P, **S30, "scan_end": "10:00"}, b)[1])
    assert len(got) == 1 and got[0][1] == "long" and S._sec("09:32:30") < got[0][0] < S._sec("09:33")
    assert got[0][2] - got[0][3] == 8.0                                # stop at THAT candle's low
    assert trades(go(C930, {**P, **S30, "scan_end": "09:32"}, b)[1]) == []        # the window ends before it
    assert sides({**S30, "scan_end": "10:00", "body_pts": 9.0}, b) == []          # the gates read that candle
    assert len(trades(go(C930, {**P, **S30, "scan_end": "10:00"}, day(DOWN30, {"09:32": DOWN30}))[1])) == 1   # one trade a session


@pytest.mark.parametrize("bad", ["09:30", "09:45:10", "11:00"])
def test_scan_end_refused(bad):
    with pytest.raises(ValueError):
        C930({**P, **S30, "scan_end": bad})
