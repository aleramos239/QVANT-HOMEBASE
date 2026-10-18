"""CANDLE_SWEEP: the `candle_sweep` entry trigger (families/candle_sweep.py), the owner's idea of 2026-10-17, written from his words.

THE RULE UNDER TEST:
    LONG  = this tf bar's low is strictly below the previous bar's low and its close is strictly above the `back` line of the previous bar
            (range: its low, body: the bottom of its body, far: the top of its body) -> market at the next bar's open, structure = this bar's low
    SHORT = the mirror;  both at once = no trade;  entries inside the idea's session, up to max_tr a session, one position at a time; flat 15:58.
Synthetic days with EXACT numbers cover each behaviour (a flat day at 15000 with single minutes changed); seeded random-walk days check the
signal list against an independent restatement of the rule at every bar size, session and `back`; the real BUILD days check the invariants
(window, one position, flat 15:58) at 1 worker. No net, win rate or profit factor is read.
"""
import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import candle_sweep as CS
from test_blocks import DAILY, TICK, days_of, minute_tape, ns, rand_bars, real_days

BASE = {"hold_to": "day", "tf": "15", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "back": "body"}
PX = 15000.0


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def flat(n, px=PX, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def m(o, h, l, c):
    return (o, h, l, c, 40)


def day(edits):
    """A full day of minute bars from 00:00 ET to 15:59, flat at 15000, with the minutes `edits` changed: {"09:20": m(...), ...}."""
    b = flat(960)
    for t, x in edits.items():
        b[S._sec(t) // 60] = x
    return b


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def run(params, bars, cls=None):
    st = (cls or CS.CandleSweep)({**BASE, **params})
    st.ROLLS = frozenset()
    return st, S.run_session(st, minute_tape(bars, "00:00"), daily=list(DAILY), on_error="raise")


class Sig(CS.CandleSweep):
    """Logs every signal the family sees at a close where an entry could be placed (no order is placed): (second, side)."""
    seen: list = []

    def fam_signal(self, ctx):
        if self.go:
            type(self).seen.append((sec_of(ctx), "long" if self.go > 0 else "short"))


def signals(params, bars):
    cls = type("Sig", (Sig,), {"seen": []})
    run(params, bars, cls)
    return list(cls.seen)


class Spy(CS.CandleSweep):
    """Logs every order: (second, side, the structure level passed, its stop, its target)."""
    log: list = []

    def _mkt(self, ctx, side, struct=None, **kw):
        o = super()._mkt(ctx, side, struct=struct, **kw)
        type(self).log.append((sec_of(ctx), side, struct, o and o.sl, o and o.tp))
        return o


def orders(params, bars):
    cls = type("Spy", (Spy,), {"log": []})
    st, res = run(params, bars, cls)
    return list(cls.log), res


# the PREVIOUS bar 09:15-09:30: open 15000, high 15012, low 14996, close 15010 (a green body 15000-15010)
GREEN = {"09:20": m(PX, PX + TICK, 14996.0, PX), "09:29": m(PX, 15012.0, PX - TICK, 15010.0)}
# the mirror: open 15000, high 15004, low 14988, close 14990 (a red body 14990-15000)
RED = {"09:20": m(PX, 15004.0, PX - TICK, PX), "09:29": m(PX, PX + TICK, 14988.0, 14990.0)}


def long_bar(c):
    """THIS bar 09:30-09:45 sweeps the green bar's low (14990 < 14996) and closes at c."""
    return {**GREEN, "09:35": m(PX, PX + TICK, 14990.0, PX), "09:44": m(PX, max(PX + TICK, c), min(PX - TICK, c), c)}


def short_bar(c):
    """THIS bar 09:30-09:45 sweeps the red bar's high (15010 > 15004) and closes at c."""
    return {**RED, "09:35": m(PX, 15010.0, PX - TICK, PX), "09:44": m(PX, max(PX + TICK, c), min(PX - TICK, c), c)}


# ---- (i) the sweep and the close back ----------------------------------------------------------------------------------------------------

def test_a_swept_low_with_a_close_back_into_the_body_is_a_long_and_the_mirror_is_a_short():
    assert signals({}, day({})) == []                                                  # a flat day sweeps nothing
    assert signals({}, day(long_bar(15005.0))) == [(sec(9, 45), "long")]
    assert signals({}, day(short_bar(14995.0))) == [(sec(9, 45), "short")]


@pytest.mark.parametrize("back,want", [("range", [True, True, True]), ("body", [False, True, True]), ("far", [False, False, True])])
def test_back_sets_the_line_the_close_must_pass(back, want):
    # long: 14998 is above the low 14996 only; 15005 is in the body; 15011 is above the body's top 15010
    assert [signals({"back": back}, day(long_bar(c))) == [(sec(9, 45), "long")] for c in (14998.0, 15005.0, 15011.0)] == want
    # short: 15002 is below the high 15004 only; 14995 is in the body; 14989 is below the body's bottom 14990
    assert [signals({"back": back}, day(short_bar(c))) == [(sec(9, 45), "short")] for c in (15002.0, 14995.0, 14989.0)] == want


def test_the_close_must_be_strictly_past_the_line_and_the_sweep_strictly_beyond():
    assert signals({}, day(long_bar(15000.0))) == []                                   # on the body's bottom: not back
    assert signals({}, day(long_bar(15000.0 + TICK))) == [(sec(9, 45), "long")]
    assert signals({"back": "range"}, day(long_bar(14996.0))) == []                    # on the previous low: not back
    touch = {**GREEN, "09:35": m(PX, PX + TICK, 14996.0, PX), "09:44": m(PX, 15005.0, PX - TICK, 15005.0)}
    assert signals({}, day(touch)) == []                                               # a low ON the previous low is no sweep


def test_no_close_back_is_no_signal():
    assert signals({}, day(long_bar(14992.0))) == [] and signals({"back": "range"}, day(long_bar(14992.0))) == []


def test_a_bar_that_sweeps_both_sides_trades_only_the_side_it_closed_past():
    def wide(c):
        return {**GREEN, "09:35": m(PX, 15014.0, 14990.0, PX), "09:44": m(PX, max(PX + TICK, c), min(PX - TICK, c), c)}
    assert signals({}, day(wide(15005.0))) == []                                       # inside the body: back on both sides = no trade
    assert signals({}, day(wide(15011.0))) == [(sec(9, 45), "long")]                   # above the body: not back for the short
    assert signals({}, day(wide(14998.0))) == [(sec(9, 45), "short")]                  # below the body: not back for the long


# ---- (ii) the order: market, the structure level is this bar's extreme ------------------------------------------------------------------

def test_the_structure_level_is_the_sweeping_bars_extreme_and_struct_takes_it():
    log, _ = orders({"stop_mode": "struct", "tgt_r": 0.5}, day(long_bar(15005.0)))
    assert log == [(sec(9, 45), "long", 14990.0, 14990.0, 15005.0 + 0.5 * 15.0)]    # stop at the low, target half the distance
    log, _ = orders({"stop_mode": "struct", "tgt_r": 0.5}, day(short_bar(14995.0)))
    assert log == [(sec(9, 45), "short", 15010.0, 15010.0, 14995.0 - 0.5 * 15.0)]
    log, _ = orders({"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}, day(long_bar(15005.0)))
    assert log == [(sec(9, 45), "long", 14990.0, 14985.0, 15025.0)]                  # the standard table's stops ignore it


def test_the_entry_is_the_next_bars_open():
    _, res = orders({"stop_mode": "struct", "tgt_r": 0.5}, day(long_bar(15005.0)))
    (t,), ms0 = res.trades, ns("00:00") // 1_000_000
    assert t["side"] == "long" and sec(9, 45) * 1000 + ms0 <= t["entry_ms"] < sec(9, 46) * 1000 + ms0


# ---- (iii) the session, the cap, one position, the side -----------------------------------------------------------------------------------

def test_entries_happen_only_inside_the_session():
    assert signals({"sess": "mid"}, day(long_bar(15005.0))) == []
    early = {k.replace("09:", "11:", 1): v for k, v in long_bar(15005.0).items()}        # the same bars two hours later
    # (the green bar 11:15-11:30 itself swept the flat bar before it and closed above its body: a long at 11:30 too; at 09:30 it was before nyam)
    assert signals({"sess": "mid"}, day(early)) == [(sec(11, 30), "long"), (sec(11, 45), "long")]
    assert signals({"sess": "nyam"}, day(early)) == []


def test_max_tr_caps_the_entries_and_one_position_at_a_time():
    two = {**long_bar(15005.0), **{k.replace("09:", "10:", 1): v for k, v in long_bar(15005.0).items()}}
    assert signals({}, day(two)) == [(sec(9, 45), "long"), (sec(10, 30), "long"), (sec(10, 45), "long")]     # 10:30: the green copy itself
    log, _ = orders({"stop_mode": "pts", "stop_val": 500.0, "max_tr": 20}, day(two))
    assert [x[0] for x in log] == [sec(9, 45)]                                         # the first trade is still open at 10:45
    log, _ = orders({"stop_mode": "struct", "tgt_r": 0.5, "max_tr": 1}, day(two))
    assert [x[0] for x in log] == [sec(9, 45)]


def test_dir_runs_one_side_only():
    assert [x[1] for x in orders({"dir": "short"}, day(long_bar(15005.0)))[0]] == ["long"] and \
           [x[4] for x in orders({"dir": "short"}, day(long_bar(15005.0)))[0]] == [None]   # asked, refused by dir: no order
    assert [x[1] for x in orders({"dir": "short"}, day(short_bar(14995.0)))[0]] == ["short"]


# ---- (iv) the written rule on random days --------------------------------------------------------------------------------------------------

def reference(bars, tf, sess, back, turn="off"):
    """The rule restated from the docstring on full days of minute bars from 00:00 (every clock slot has a print)."""
    s0, s1 = S.SESS[sess]
    tb = [(bars[j][0], max(b[1] for b in bars[j:j + tf]), min(b[2] for b in bars[j:j + tf]), bars[j + tf - 1][3])
          for j in range(0, len(bars) - tf + 1, tf)]
    out = []
    for k in range(2, len(tb)):                                      # the third bar of the day on (the Template's WARM)
        end = (k + 1) * tf * 60
        (po, ph, pl, pc), (o, h, l, c) = tb[k - 1], tb[k]
        lo = {"range": pl, "body": min(po, pc), "far": max(po, pc)}[back]
        hi = {"range": ph, "body": max(po, pc), "far": min(po, pc)}[back]
        long, short = l < pl and c > lo, h > ph and c < hi
        if turn == "on":
            long, short = long and pc < po and c > o, short and pc > po and c < o
        elif turn == "same":
            long, short = long and pc > po and c > o, short and pc < po and c < o
        if long != short and s0 < end <= s1 and end < s1 - 300:
            out.append((end, "long" if long else "short"))
    return out


@pytest.mark.parametrize("back", list(CS.BACKS))
@pytest.mark.parametrize("sess", ["asia", "london", "pre", "nyam", "mid", "pm"])
@pytest.mark.parametrize("tf", [1, 5, 15, 30])
def test_the_signals_equal_the_written_rule_on_random_days(tf, sess, back):
    n = 0
    for seed in (3, 8, 11, 21, 5, 13, 34, 55):
        bars = rand_bars(960, seed, p0=PX, step=4.0 if seed % 2 else 8.0)
        want = reference(bars, tf, sess, back)
        got = signals({"back": back, "tf": str(tf), "sess": sess}, bars)
        assert got == want, (seed, got[:5], want[:5])
        n += len(want)
    if (sess, tf) != ("pre", 30):                                    # pre at 30 minutes has one decision a day (09:00)
        assert n > 0, "the random days never swept a candle: the comparison would be empty"


# ---- (iv a) turn: the previous candle one colour, the sweeping candle the other -----------------------------------------------------

def red_long(c):
    """THIS bar 09:30-09:45 (open 15000) sweeps the RED bar's low (14985 < 14988) and closes at c."""
    return {**RED, "09:35": m(PX, PX + TICK, 14985.0, PX), "09:44": m(PX, max(PX + TICK, c), min(PX - TICK, c), c)}


def green_short(c):
    """THIS bar 09:30-09:45 (open 15000) sweeps the GREEN bar's high (15015 > 15012) and closes at c."""
    return {**GREEN, "09:35": m(PX, 15015.0, PX - TICK, PX), "09:44": m(PX, max(PX + TICK, c), min(PX - TICK, c), c)}


def test_turn_needs_a_red_then_green_candle_for_a_long_and_green_then_red_for_a_short():
    on = {"turn": "on"}
    assert signals(on, day(red_long(15002.0))) == [(sec(9, 45), "long")]               # red, then green back into its body
    assert signals({}, day(red_long(14995.0))) == [(sec(9, 45), "long")]               # off: a red sweeping bar still longs ...
    assert signals(on, day(red_long(14995.0))) == []                                   # ... on: it must close green (above its 15000 open)
    assert signals({}, day(long_bar(15005.0))) == [(sec(9, 45), "long")] and signals(on, day(long_bar(15005.0))) == []    # green before: no
    assert signals(on, day(green_short(14998.0))) == [(sec(9, 45), "short")]           # green, then red back into its body
    assert signals(on, day(green_short(15005.0))) == [] and signals({}, day(green_short(15005.0))) == [(sec(9, 45), "short")]
    assert signals(on, day(short_bar(14995.0))) == []                                  # red before a short: no
    doji = {**red_long(15002.0), "09:44": m(PX, PX + TICK, PX - TICK, PX)}              # this bar closes on its open: no colour
    assert signals(on, day(doji)) == [] and signals({}, day(doji)) == [(sec(9, 45), "long")]


def test_turn_same_needs_both_bars_the_trades_colour():
    same = {"turn": "same"}
    assert signals(same, day(long_bar(15005.0))) == [(sec(9, 45), "long")]            # green, then green back into its body
    assert signals(same, day(red_long(15002.0))) == []                                 # red before a long: no
    assert signals(same, day(long_bar(14999.0))) == [] and signals({"back": "range"}, day(long_bar(14999.0))) == [(sec(9, 45), "long")]
    assert signals(same, day(short_bar(14995.0))) == [(sec(9, 45), "short")]           # red, then red back into its body
    assert signals(same, day(green_short(14998.0))) == []                              # green before a short: no


@pytest.mark.parametrize("tf", [5, 15])
@pytest.mark.parametrize("sess", ["london", "nyam", "pm"])
def test_turn_signals_equal_the_written_rule_on_random_days(tf, sess):
    n = 0
    for seed in (3, 8, 11, 21, 5, 13):
        bars = rand_bars(960, seed, p0=PX, step=4.0 if seed % 2 else 8.0)
        for turn in ("on", "same"):
            want = reference(bars, tf, sess, "body", turn=turn)
            assert signals({"back": "body", "tf": str(tf), "sess": sess, "turn": turn}, bars) == want, (seed, turn)
            n += len(want)
    assert n > 0


# ---- (iv d) dir930: only the side of the 09:30-10:00 move ------------------------------------------------------------------------------

def later(edits, minutes):
    """The same minute edits `minutes` later in the day."""
    out = {}
    for t, x in edits.items():
        h, mm = map(int, t.split(":"))
        k = h * 60 + mm + minutes
        out["%02d:%02d" % (k // 60, k % 60)] = x
    return out


def test_dir930_trades_only_the_side_of_the_0930_1000_move_and_never_before_10():
    up = {"09:59": m(PX, 15002.0, PX - TICK, 15002.0)}                                 # 09:30 open 15000 -> 10:00 close 15002: up
    down = {"09:59": m(PX, PX + TICK, 14998.0, 14998.0)}
    p = {"dir930": "with"}
    sweep = later(long_bar(15005.0), 45)                                               # the green bar 10:00-10:15, its sweep 10:15-10:30
    assert [x[:2] for x in orders(p, day({**up, **sweep}))[0]] == [(sec(10, 15), "long")]          # (the green bar sweeps 09:45-10:00 too)
    assert orders(p, day({**down, **sweep}))[0] == []
    assert [x[:2] for x in orders({}, day({**down, **sweep}))[0]] == [(sec(10, 15), "long")]      # off: no side is read
    short = later(short_bar(14995.0), 45)
    assert [x[:2] for x in orders(p, day({**down, **short}))[0]] == [(sec(10, 15), "short")]
    assert orders(p, day({**up, **short}))[0] == []
    assert orders(p, day(long_bar(15005.0)))[0] == [] and orders({}, day(long_bar(15005.0)))[0] != []   # 09:45: the move is not known yet
    assert orders(p, day({**later(long_bar(15005.0), 45)}))[0] == []                  # a flat 09:30-10:00: no side, no trade


# ---- (iv b) the 1-hour EMA (ema1h) -------------------------------------------------------------------------------------------------------

def test_hour_closes_are_the_last_print_of_each_whole_hour_that_has_ended():
    t0 = ns("00:00")
    H = CS.HOUR
    ts = np.array([t0 + 10, t0 + H - 5, t0 + H + 1, t0 + 2 * H + 7, t0 + 2 * H + 9, t0 + 3 * H + 1], np.int64)
    px = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert CS.hour_closes(ts, px, t0, t0 + 3 * H + 30).tolist() == [2.0, 3.0, 5.0]       # the 03:00 hour has not ended
    assert CS.hour_closes(ts, px, t0, t0 + 3 * H).tolist() == [2.0, 3.0, 5.0]
    assert CS.hour_closes(ts, px, t0, t0 + 3 * H - 1).tolist() == [2.0, 3.0]
    assert CS.hour_closes(ts, px, t0 + H, t0 + 3 * H).tolist() == [3.0, 5.0]
    assert CS.hour_closes(ts, px, t0, t0 + H - 1).tolist() == []


def test_ema_last_is_seeded_with_the_first_close_and_needs_n_closes():
    assert CS.ema_last([1.0, 2.0], 3) is None
    a = 2.0 / 4
    e = 10.0
    for c in (12.0, 9.0, 15.0):
        e += a * (c - e)
    assert CS.ema_last([10.0, 12.0, 9.0, 15.0], 3) == pytest.approx(e)


def with_prior(monkeypatch, level, n=150):
    seen = []

    def fake(st, need):
        seen.append(need)
        return np.full(n, level)
    monkeypatch.setattr(CS, "prior_closes", fake)
    return seen


def test_ema1h_lets_a_long_above_the_ema_and_a_short_below_it_only(monkeypatch):
    with_prior(monkeypatch, 14000.0)                                                   # the EMA sits far under 15000
    assert [x[1] for x in orders({"ema1h": 50}, day(long_bar(15005.0)))[0]] == ["long"]
    assert orders({"ema1h": 50}, day(short_bar(14995.0)))[0] == []
    with_prior(monkeypatch, 16000.0)                                                   # far over it
    assert orders({"ema1h": 50}, day(long_bar(15005.0)))[0] == []
    assert [x[1] for x in orders({"ema1h": 50}, day(short_bar(14995.0)))[0]] == ["short"]
    assert [x[1] for x in orders({"ema1h": 0}, day(long_bar(15005.0)))[0]] == ["long"]     # off: no EMA is read


def test_ema1h_with_too_few_closes_is_no_trade_and_asks_for_three_times_n(monkeypatch):
    seen = with_prior(monkeypatch, 14000.0, n=0)
    assert orders({"ema1h": 50}, day(long_bar(15005.0)))[0] == []                      # today holds 9 hour closes (00:00 .. 09:00), not 50
    assert seen == [150 - 9]
    assert [x[1] for x in orders({"ema1h": 9}, day(long_bar(15005.0)))[0]] == ["long"]   # 9 closes are enough for EMA(9): 15000 < 15005


def test_ema1h_reads_only_the_hours_that_have_ended(monkeypatch):
    with_prior(monkeypatch, 14000.0)
    got = []

    class Look(CS.CandleSweep):
        def ema1h(self, ctx):
            e = super().ema1h(ctx)
            got.append(e)
            return e
    base = day(long_bar(15005.0))
    run({"ema1h": 50}, base, Look)
    moved = list(base)
    for i in range(9 * 60, 9 * 60 + 15):                                               # the 09:00 hour has not ended at 09:45
        o, h, l, c, v = moved[i]
        moved[i] = (o + 3, h + 3, l + 3, c + 3, v)
    run({"ema1h": 50}, moved, Look)
    assert len(got) == 2 and got[0] == got[1]


# ---- (iv c) candles of the family's own size (candle) ----------------------------------------------------------------------------------

def three(c):
    """The 3-minute candle 09:27-09:30 green (open 15000, high 15012, low 14996, close 15010); 09:30-09:33 sweeps its low and closes at c."""
    return {"09:28": m(PX, PX + TICK, 14996.0, PX), "09:29": m(PX, 15012.0, PX - TICK, 15010.0),
            "09:31": m(PX, PX + TICK, 14990.0, PX), "09:32": m(PX, max(PX + TICK, c), min(PX - TICK, c), c)}


def test_three_minute_candles_sweep_and_close_back_like_the_bars():
    p = {"tf": "1", "candle": 3}
    assert signals(p, day({})) == []
    assert signals(p, day(three(15005.0))) == [(sec(9, 33), "long")]
    assert signals(p, day(three(14998.0))) == [] and signals({**p, "back": "range"}, day(three(14998.0))) == [(sec(9, 33), "long")]
    log, _ = orders({**p, "stop_mode": "struct", "tgt_r": 0.5}, day(three(15005.0)))
    assert log == [(sec(9, 33), "long", 14990.0, 14990.0, 15005.0 + 0.5 * 15.0)]           # the candle's own low, half the distance
    assert signals({"tf": "1"}, day(three(15005.0))) != signals(p, day(three(15005.0)))      # off: the 1-minute bars decide instead


@pytest.mark.parametrize("n", [5, 15, 30])
@pytest.mark.parametrize("sess", ["london", "nyam", "mid", "pm"])
def test_candles_of_5_15_30_minutes_give_the_signals_of_those_bars(n, sess):
    k = 0
    for seed in (3, 8, 11, 21):
        bars = rand_bars(960, seed, p0=PX, step=4.0 if seed % 2 else 8.0)
        for back in ("range", "body"):
            want = signals({"tf": str(n), "sess": sess, "back": back}, bars)
            assert signals({"tf": "1", "candle": n, "sess": sess, "back": back}, bars) == want, (seed, back)
            k += len(want)
    assert k > 0


def test_candles_with_the_ema_read_the_candle_close(monkeypatch):
    with_prior(monkeypatch, 14000.0)
    assert [x[1] for x in orders({"tf": "1", "candle": 3, "ema1h": 50}, day(three(15005.0)))[0]] == ["long"]
    with_prior(monkeypatch, 16000.0)
    assert orders({"tf": "1", "candle": 3, "ema1h": 50}, day(three(15005.0)))[0] == []


# ---- (v) the settings and the registry -----------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = CS.CandleSweep.defaults(), CS.CandleSweep.schema()
    assert (d["back"], d["ema1h"], d["candle"], d["max_tr"], d["dir"]) == ("body", 0, 0, 20, "both")
    assert sc["back"] == ("choice", ("range", "body", "far")) and sc["max_tr"] == ("int", 1, 20) and sc["ema1h"] == ("int", 0, 500)
    assert sc["dir930"] == ("choice", ("off", "with")) and d["dir930"] == "off"
    assert sc["candle"] == ("int", 0, 60) and sc["turn"] == ("choice", ("off", "on", "same")) and d["turn"] == "off"
    for bad in ({"back": "wick"}, {"back": 1}, {"max_tr": 0}, {"max_tr": 21}, {"dir": "up"}, {"ema1h": -1}, {"ema1h": 501}, {"ema1h": 1.5},
                {"candle": -1}, {"candle": 61}, {"candle": 3}, {"candle": 3, "tf": "5"}):
        with pytest.raises(ValueError):
            CS.CandleSweep({"tf": "15", **bad})


def test_the_registry_holds_candle_sweep_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["candle_sweep"]
    lib = families.library("candle_sweep")
    assert cls is CS.CandleSweep and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15", "30")
    assert families.MODULE_OF["candle_sweep"] == "candle_sweep" and lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"]
    assert lib["mirror"] is None and lib["complexity"] == 4 and lib["variants"] == [{"back": "range"}, {"back": "body"}, {"back": "far"}]
    assert len(lib["rationale"]) > 60 and "previous bar" in notes
    from families import blocks as B
    assert issubclass(B.WRAPPED["candle_sweep"], CS.CandleSweep) and B.B_candle_sweep is B.WRAPPED["candle_sweep"]
    B.WRAPPED["candle_sweep"]({"tf": "15", "stop_mode": "struct", "tgt_r": 0.5})
    for s in RM.DAY_PASSES:
        assert cls({"tf": "15", "sess": s, "hold_to": "day"}).sessions() == [s]


# ---- (vi) real BUILD days: the invariants, at 1 worker -------------------------------------------------------------------------------------

def test_real_build_days_hold_the_window_one_position_and_the_flat_time():
    real_days()
    days = days_of("NQ", 4)
    hd = {"tf": "15", "hold_to": "day", "stop_mode": "struct", "tgt_r": 0.5}
    specs = [(CS.CandleSweep, {**hd, "sess": s, "back": b}) for s in ("london", "nyam", "pm") for b in CS.BACKS]
    out = S.run_many(specs, root="NQ", days=days, period="build", workers=1, on_error="raise")
    again = S.run_many(specs, root="NQ", days=days, period="build", workers=1, on_error="raise")
    assert [r["trades"] for r in out] == [r["trades"] for r in again]
    assert sum(r["skipped_by_error"] for r in out) == 0
    total = 0
    for (cls, p), r in zip(specs, out):
        s0, s1 = S.SESS[p["sess"]]
        last = {}
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d = S._date(t["date"])
            es = (t["entry_ms"] // 1000) - S.et_ns(d, "00:00") // S.NS
            assert s0 < es < s1 - 300 + 120, (p, t["date"], es)
            assert t["exit_ms"] <= S.et_ns(d, S.day_flat(d, "NQ")) // 1_000_000 + 60_000
            assert last.get(t["date"], 0) <= t["entry_ms"]
            last[t["date"]] = t["exit_ms"]
            total += 1
    assert total > 0
