"""EVE FAIR: the `eve_fair` entry trigger (families/eve_fair.py), the evening fade back to the 18:00 open (JJ Simon BLvsYJ4sqn8, step 2).

THE RULE UNDER TEST: a close dist+ points from fair and a displacement (or a break of structure) back toward it -> market toward fair; the
20:00 candle moving away makes the 20:00 open fair (switch on); a trade still open at 19:59 is flattened. Synthetic evening tapes."""
import datetime as dt

import l2sim as S
from families import blocks as B
from families import eve_fair as EF
from test_blocks import D, DAILY, minute_tape, ns

EVE = B.WRAPPED["eve_fair"]
BASE = {"hold_to": "day", "tf": "1", "sess": "eve", "stop_mode": "pts", "stop_val": 25.0, "tgt_r": 1.5}
PX = 15000.0
MS0 = ns("00:00") // 1_000_000


def bars_of(closes, px=PX):
    """One minute bar per close from 18:00 of the evening before; an up bar's high is its close + 1 tick, a down / flat bar's high its open."""
    out, o = [], px
    for c in closes:
        h, l = (c + 0.25, o) if c > o else (o, c - 0.25)
        out.append((o, h, l, c, 40))
        o = c
    return out + [(o, o, o, o, 40)] * (22 * 60 - len(out))      # quiet to 16:00 of the trade date


def play(closes, **kw):
    st = EVE({**BASE, **kw})
    st.ROLLS = frozenset()
    tp = minute_tape(bars_of(closes), "18:00", d=D - dt.timedelta(days=1))
    tape = S.Tape(tp.root, D, tp.contract, tp.ts, tp.px, tp.size)
    return S.run_session(st, tape, daily=list(DAILY), on_error="raise", window=st.eve_window, segment="eve").trades


def at(t):
    return (t["entry_ms"] - MS0) // 1000 + 86400        # second of the evening clock


FALL = [PX] * 10 + [PX - 2 * k for k in range(1, 21)]           # 18:10 -> 18:29: down to 14960, 40 under fair
DISP = FALL + [14966.0]                                         # 18:30: body 6 > 2, close over the last high 14962 -> long


def test_far_under_fair_an_up_displacement_goes_long_and_is_out_at_1959():
    t = play(DISP)
    assert len(t) == 1 and t[0]["side"] == "long" and at(t[0]) // 60 == 18 * 60 + 31
    assert abs(t[0]["entry_price"] - 14966.0) <= 1.0 and t[0]["sl"] == t[0]["entry_price"] - 25.0
    assert t[0]["exit_reason"] == "time" and (t[0]["exit_ms"] - MS0) // 1000 + 86400 == 19 * 3600 + 59 * 60
    up = play([2 * PX - c for c in DISP])                       # the mirror: far above fair, a down displacement -> short
    assert len(up) == 1 and up[0]["side"] == "short"


def test_too_close_or_bos_only_is_no_trade():
    assert play(DISP, dist=40.0) == []                          # 14966 is 34 under fair
    assert play(DISP, sig="bos") == []                          # a straight fall leaves no swing high to break


def test_a_break_of_the_last_swing_high_goes_long():
    g = [PX] * 10 + [PX - 2 * k for k in range(1, 26)] + [14953.0, 14956.0, 14952.0, 14949.0, 14947.0, 14957.0]
    t = play(g, sig="bos")                                      # swing high 14956.25 (3 lower highs each side), broken by the 14957 close
    assert len(t) == 1 and t[0]["side"] == "long" and at(t[0]) // 60 == 18 * 60 + 41


def test_the_2000_candle_moving_away_makes_the_2000_open_fair():
    g = [PX] * 110 + [PX + 0.5 * k for k in range(1, 11)]      # 19:50 -> 19:59 up to 15005
    g += [15010.0] + [15010.0 - 2.5 * k for k in range(1, 17)] + [14974.0]   # 20:00 green from 15005 (away); down to 14970; 20:17 displacement
    t = play(g)                                                 # 14974 is 31 under the new fair, the 20:00 open 15005
    assert len(t) == 1 and t[0]["side"] == "long" and at(t[0]) // 60 == 20 * 60 + 18
    assert play(g, switch="off") == []                          # 26 under the 18:00 open: too close


def test_registered_eve_only_with_the_window_1800_2130():
    assert "eve_fair" in B.WRAPPED and EF.ENTRY_WINDOWS["eve_fair"] == (-6 * 3600, -(2 * 3600 + 30 * 60))
    assert EVE({**BASE, "sess": "nyam"}).sessions() == []
