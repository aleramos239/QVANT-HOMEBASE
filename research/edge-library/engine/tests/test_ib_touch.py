"""IB_TOUCH: the `ib_touch` entry trigger (families/ib_touch.py), the first touch of the morning range, written test-first from its rule.

THE RULE UNDER TEST (the owner's request of 2026-10-10):
    range      = the high and low of the 1-minute bars of the first `ib_min` minutes from 09:30 ET (5 | 15 | 30 | 60): ib_n's range
    orders     = a limit SELL at the range high and a limit BUY at the range low, placed at a tf close inside the idea's session from the
                 range's end on, while flat with entries left: every edge that is not used up and has no working order gets one (only when
                 the last print is inside the edge); the two are one OCO pair
    used up    = an edge is used up by the first 1-minute bar after the range's end that trades AT OR BEYOND it, with or without an order
                 there; a used edge never gets an order again that day and an order still working there is cancelled at that minute's close
    one trade  = one position at a time; the other edge gets its order back after the trade, when it is still unused (max_tr 2)
    NY day sessions only (nyam, mid, pm); the standard exits, flat 15:58.
Synthetic days with EXACT numbers cover each behaviour (a quiet day at 15000 whose 09:31 and 09:32 minutes make the range 14980 .. 15020,
with single minutes changed); seeded random days check every entry against an independent restatement of the rule at every bar size,
session and range length, and the range against ib_n's own; the real BUILD days check the invariants (window, one position, the edge
prices, the first touch on the tape itself, flat 15:58) at 1 worker. No net, win rate or profit factor is read.
"""
import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import blocks as B
from families import ib_touch as IT
from test_blocks import DAILY, TICK, days_of, garble, minute_tape, ns, rand_bars, real_days

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "ib_min": "15"}
PX, HI, LO = 15000.0, 15020.0, 14980.0
OPEN = 34200
NY = ("nyam", "mid", "pm")
SELL, BUY = ((-1, HI),), ((1, LO),)
BOTH = SELL + BUY
MS0 = ns("00:00") // 1_000_000


def sec(h, m=0, s=0):
    return h * 3600 + m * 60 + s


def quiet(n, px=PX, v=40):
    return [(px, px + TICK, px - TICK, px, v)] * n


def up(px, c=PX):
    """A minute that trades up to px and closes at c (its low is the quiet day's low). Prints: 15000 at :00, the low at :15, px at :30, c at :45."""
    return (PX, px, PX - TICK, c, 40)


def dn(px, c=PX):
    """A minute that trades down to px and closes at c. Prints: 15000 at :00, px at :15, the high at :30, c at :45."""
    return (PX, PX + TICK, px, c, 40)


RANGE = {"09:31": up(HI), "09:32": dn(LO)}           # the range of every ib_min: 14980 .. 15020


def day(edits=None, rng=RANGE):
    """A full day of minute bars from 00:00 ET to 15:59, quiet at 15000 (one tick either side), with the range minutes and `edits` changed."""
    b = quiet(960)
    for t, x in {**rng, **(edits or {})}.items():
        b[S._sec(t) // 60] = x
    return b


def tape_of(bars):
    return minute_tape(bars, "00:00")


def sec_of(ctx):
    return (ctx.now_ns - ns("00:00")) // S.NS


def at(t):
    """The second of the day a trade was filled at."""
    return (t["entry_ms"] - MS0) // 1000


def entries(res):
    return [(at(t), t["side"], t["entry_price"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


def run(params, bars, cls=None, tape=None, costs=None, **kw):
    """One instance through one day, with the fills the family runs with (strict_limit) and the explicit roll list: none. -> (the instance, the result)."""
    st = (cls or IT.IbTouch)({**BASE, **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, tape or tape_of(bars), costs=costs or S.Costs(**IT.IbTouch.SCREEN_RUN), daily=list(DAILY), on_error="raise", **kw)
    return st, res


def trades(bars, tape=None, **params):
    return entries(run(params, bars, tape=tape)[1])


class Look(IT.IbTouch):
    """Logs, after every 1-minute bar close: (the second, the working entry orders as (side, price), the used edges as order sides)."""
    seen: list = []

    def on_bar(self, ctx, bar):
        super().on_bar(ctx, bar)
        type(self).seen.append((sec_of(ctx), tuple(sorted((o.side, o.price) for o in ctx._s.orders if o.role == "entry")),
                                tuple(k for k in (-1, 1) if self.used[k])))


def watch(params, bars, tape=None, base=Look):
    """-> ({second: the working entry orders after that minute close}, {second: the used edges}, the entries, the instance)."""
    cls = type("Look", (base,), {"seen": []})
    st, res = run(params, bars, cls, tape)
    return {s: o for s, o, _ in cls.seen}, {s: u for s, _, u in cls.seen}, entries(res), st


def resting(params, bars, tape=None):
    return watch(params, bars, tape)[0]


def minutes(a, b):
    """The minute closes a .. b, both included."""
    return range(a, b + 1, 60)


# ---- (i) the orders: a sell at the high and a buy at the low, from the range's end ----------------------------------------------------------------

def test_from_the_range_end_a_sell_rests_at_the_high_and_a_buy_at_the_low_until_five_minutes_before_the_session_ends():
    r, used, got, st = watch({}, day())
    assert (st.hi, st.lo) == (HI, LO) and got == []
    assert all(r[s] == () for s in minutes(60, sec(9, 44)))                             # nothing before the range has ended
    assert all(r[s] == BOTH for s in minutes(sec(9, 45), sec(10, 55)))                  # both from 09:45 to 10:55
    assert all(r[s] == () for s in r if s > sec(10, 55)) and max(r) >= sec(10, 56)      # the session's entries end 5 minutes before 11:00
    assert all(u == () for u in used.values())
    _, res = run({}, day())
    assert res.both_sides is True                                                       # orders on both sides at once: the family is marked for it


def test_ib_min_60_gives_a_nyam_idea_25_minutes():
    r = resting({"ib_min": "60"}, day())
    assert [s for s in sorted(r) if r[s]] == list(minutes(sec(10, 30), sec(10, 55)))
    assert trades(day({"10:29": up(HI + 5.0)}), ib_min="60") == []                     # (that minute is still the range: it makes the high)
    assert trades(day({"10:30": up(HI + 5.0)}), ib_min="60") == [(sec(10, 30, 30), "short", HI)]
    assert trades(day({"10:54": dn(LO - 5.0)}), ib_min="60") == [(sec(10, 54, 15), "long", LO)]
    assert trades(day({"10:55": dn(LO - 5.0)}), ib_min="60") == []


def test_the_first_return_to_the_high_is_sold_and_to_the_low_is_bought_at_the_edge_itself():
    _, res = run({}, day({"09:50": up(HI + 5.0)}))
    t, = res.trades
    assert (at(t), t["side"], t["entry_price"], t["order_price"]) == (sec(9, 50, 30), "short", HI, HI) and t["oco"] is True and t["both_sides"] is True
    _, res = run({}, day({"09:50": dn(LO - 5.0)}))
    t, = res.trades
    assert (at(t), t["side"], t["entry_price"], t["order_price"]) == (sec(9, 50, 15), "long", LO, LO) and t["oco"] is True


def test_a_fill_needs_a_one_tick_trade_through_and_a_touch_to_the_tick_uses_the_edge_up_without_a_trade():
    assert trades(day({"09:50": up(HI + TICK)})) == [(sec(9, 50, 30), "short", HI)]
    assert trades(day({"09:50": dn(LO - TICK)})) == [(sec(9, 50, 15), "long", LO)]
    r, used, got, _ = watch({}, day({"09:50": up(HI), "09:52": up(HI + 5.0)}))          # to the tick, then through it two minutes later
    assert got == [] and r[sec(9, 50)] == BOTH and used[sec(9, 50)] == ()
    assert used[sec(9, 51)] == (-1,) and all(r[s] == BUY for s in minutes(sec(9, 51), sec(10, 55)))      # the sell went at the close of the minute that touched
    r, used, got, _ = watch({}, day({"09:50": dn(LO), "09:52": dn(LO - 5.0)}))
    assert got == [] and used[sec(9, 51)] == (1,) and all(r[s] == SELL for s in minutes(sec(9, 51), sec(10, 55)))
    # one tick short of the edge is no touch: the order stays and trades the next return
    assert trades(day({"09:50": up(HI - TICK), "09:52": up(HI + 5.0)})) == [(sec(9, 52, 30), "short", HI)]
    assert trades(day({"09:50": dn(LO + TICK), "09:52": dn(LO - 5.0)})) == [(sec(9, 52, 15), "long", LO)]
    # the first minute after the range's end counts already (09:45), the last minute of the range does not (09:44 is the range itself)
    r, used, got, _ = watch({}, day({"09:45": up(HI), "09:47": up(HI + 5.0)}))
    assert got == [] and r[sec(9, 45)] == BOTH and r[sec(9, 46)] == BUY and used[sec(9, 46)] == (-1,)
    r, used, got, _ = watch({}, day({"09:44": up(HI), "09:47": up(HI + 5.0)}))
    assert got == [(sec(9, 47, 30), "short", HI)] and r[sec(9, 46)] == BOTH and used[sec(9, 46)] == ()


def test_the_order_lives_through_the_minute_of_the_first_touch():
    # 09:50 opens ON the high (two prints at 15020: a touch, no fill) and trades one tick through it at :30 -> filled in that same minute
    assert trades(day({"09:50": (HI, HI + TICK, HI, HI + TICK, 40)})) == [(sec(9, 50, 30), "short", HI)]
    assert trades(day({"09:50": (LO, LO, LO - TICK, LO - TICK, 40)})) == [(sec(9, 50, 30), "long", LO)]


def test_an_edge_trades_once_and_the_other_edge_still_trades():
    g = day({"09:50": up(HI + 5.0), "09:56": up(HI + 5.0), "10:00": dn(LO - 5.0), "10:06": dn(LO - 5.0), "10:10": up(HI + 5.0)})
    assert trades(g, exit_bars=2) == [(sec(9, 50, 30), "short", HI), (sec(10, 0, 15), "long", LO)]
    r, used, _, _ = watch({"exit_bars": 2}, g)
    assert used[sec(9, 51)] == (-1,) and used[sec(10, 1)] == (-1, 1)
    assert all(r[s] == () for s in minutes(sec(10, 1), sec(10, 55)))                    # both edges are used up: nothing rests again
    g = day({"09:50": dn(LO - 5.0), "09:56": dn(LO - 5.0), "10:00": up(HI + 5.0), "10:06": up(HI + 5.0)})
    assert trades(g, exit_bars=2) == [(sec(9, 50, 15), "long", LO), (sec(10, 0, 30), "short", HI)]


def test_one_position_at_a_time_the_other_order_goes_on_the_fill_and_comes_back_after_the_trade():
    g = day({"09:50": up(HI + 5.0)})
    r, _, got, _ = watch({"exit_bars": 3}, g)
    assert got == [(sec(9, 50, 30), "short", HI)] and r[sec(9, 50)] == BOTH
    assert all(r[s] == () for s in minutes(sec(9, 51), sec(9, 53)))                     # in the trade (it leaves at the 09:53 close): no entry order works
    assert all(r[s] == BUY for s in minutes(sec(9, 54), sec(10, 55)))                   # the buy is back at the next close; the high is used up
    r, _, got, _ = watch({}, g)                                                         # no exit: the one trade is open to 15:58
    assert got == [(sec(9, 50, 30), "short", HI)] and all(r[s] == () for s in r if s > sec(9, 50))
    _, res = run({"exit_bars": 3}, day({"09:50": up(HI + 5.0), "10:00": dn(LO - 5.0)}))
    a, b = sorted(res.trades, key=lambda t: t["entry_ms"])
    assert a["exit_ms"] <= b["entry_ms"] and (a["side"], b["side"]) == ("short", "long")


def test_an_edge_reached_while_a_trade_is_open_is_used_up_too():
    g = day({"09:50": up(HI + 5.0), "09:51": dn(LO - 5.0), "10:00": dn(LO - 5.0)})      # the low is reached at 09:51 with the short open
    r, used, got, _ = watch({"exit_bars": 3}, g)
    assert got == [(sec(9, 50, 30), "short", HI)] and used[sec(9, 52)] == (-1, 1)
    assert all(r[s] == () for s in r if s > sec(9, 50))
    # ... and without that 09:51 minute the low trades at 10:00
    assert trades(day({"09:50": up(HI + 5.0), "10:00": dn(LO - 5.0)}), exit_bars=3) == [(sec(9, 50, 30), "short", HI), (sec(10, 0, 15), "long", LO)]


def test_a_bar_that_reaches_both_edges_trades_the_one_reached_first_and_uses_up_both():
    lo_first = (PX, HI + 5.0, LO - 5.0, PX, 40)                                         # the low prints at :15, the high at :30
    hi_first = (PX, HI + 5.0, LO - 5.0, PX - TICK, 40)                                  # the high prints at :15, the low at :30
    later = {"10:00": up(HI + 5.0), "10:05": dn(LO - 5.0)}
    for bar, want in ((lo_first, (sec(9, 50, 15), "long", LO)), (hi_first, (sec(9, 50, 15), "short", HI))):
        r, used, got, _ = watch({"exit_bars": 2}, day({"09:50": bar, **later}))
        assert got == [want] and used[sec(9, 51)] == (-1, 1)                            # one trade; both edges gone, also after the trade has left
        assert all(r[s] == () for s in r if s > sec(9, 50))


def test_an_order_is_placed_only_when_the_last_print_is_inside_its_edge():
    g = day({"09:44": up(HI, HI)})                                                      # the range ends on its high: the last print is 15020
    r, _, got, _ = watch({}, g)
    assert r[sec(9, 45)] == BUY and r[sec(9, 46)] == BOTH and got == []                 # no sell at the range's end; it goes in one close later
    assert trades(day({"09:44": up(HI, HI), "09:47": up(HI + 5.0)})) == [(sec(9, 47, 30), "short", HI)]
    r, _, got, _ = watch({}, day({"09:44": dn(LO, LO)}))
    assert r[sec(9, 45)] == SELL and r[sec(9, 46)] == BOTH
    # a buy added later is the sell's pair all the same: its fill cancels the sell
    r, _, got, _ = watch({}, day({"09:44": dn(LO, LO), "09:50": dn(LO - 5.0)}))
    assert got == [(sec(9, 50, 15), "long", LO)] and r[sec(9, 51)] == ()
    _, res = run({}, day({"09:44": dn(LO, LO), "09:50": dn(LO - 5.0)}))
    assert res.trades[0]["oco"] is True


# ---- (ii) the session, the bar size and the range length -------------------------------------------------------------------------------------------

FIRST = [(1, "5", "nyam", sec(9, 35)), (1, "15", "nyam", sec(9, 45)), (1, "30", "nyam", sec(10)), (1, "60", "nyam", sec(10, 30)),
         (5, "5", "nyam", sec(9, 35)), (5, "15", "nyam", sec(9, 45)), (5, "60", "nyam", sec(10, 30)),
         (15, "5", "nyam", sec(9, 45)), (15, "15", "nyam", sec(9, 45)), (15, "30", "nyam", sec(10)),
         (30, "5", "nyam", sec(10)), (30, "15", "nyam", sec(10)), (30, "30", "nyam", sec(10)), (30, "60", "nyam", sec(10, 30)),
         (1, "15", "mid", sec(11, 1)), (5, "15", "mid", sec(11, 5)), (15, "60", "mid", sec(11, 15)), (30, "60", "mid", sec(11, 30)),
         (1, "15", "pm", sec(13, 31)), (5, "60", "pm", sec(13, 35)), (15, "15", "pm", sec(13, 45)), (30, "60", "pm", sec(14))]


@pytest.mark.parametrize("tf,ib,sess,first", FIRST)
def test_the_first_orders_go_in_at_the_first_tf_close_at_or_after_the_range_end_inside_the_session(tf, ib, sess, first):
    r = resting({"tf": str(tf), "ib_min": ib, "sess": sess}, day())
    last = S.SESS[sess][1] - 300
    assert [s for s in sorted(r) if r[s]] == list(minutes(first, last)) and all(r[s] == BOTH for s in minutes(first, last))


def test_an_edge_reached_between_the_range_end_and_the_first_order_never_had_one():
    p = {"tf": "30"}                                                                    # ib_min 15: the range ends 09:45, the first orders go in at 10:00
    r, used, got, _ = watch(p, day({"09:50": up(HI), "10:10": up(HI + 5.0)}))
    assert got == [] and used[sec(9, 51)] == (-1,) and all(r[s] == BUY for s in minutes(sec(10), sec(10, 55)))
    assert run(p, day({"09:50": up(HI)}))[1].both_sides is False                        # no sell was ever sent that day, not even for an instant
    assert trades(day({"10:10": up(HI + 5.0)}), tf="30") == [(sec(10, 10, 30), "short", HI)]


def test_an_edge_price_went_back_to_before_the_session_is_gone_for_a_later_session():
    for sess, t0, when in (("mid", sec(11, 1), "11:20"), ("pm", sec(13, 31), "13:50")):
        hh, mm = (int(x) for x in when.split(":"))
        r, _, got, _ = watch({"sess": sess}, day({"10:10": up(HI), when: up(HI + 5.0)}))            # back to the high at 10:10, to the tick
        assert got == [] and r[t0 - 60] == () and r[t0] == BUY, sess
        assert trades(day({when: up(HI + 5.0)}), sess=sess) == [(sec(hh, mm, 30), "short", HI)], sess
        r, _, got, _ = watch({"sess": sess}, day({"10:10": dn(LO - 5.0), when: dn(LO - 5.0)}))
        assert got == [] and r[t0] == SELL, sess
        r, _, got, _ = watch({"sess": sess}, day({"09:50": up(HI + 5.0), "10:10": dn(LO)}))         # both: the session never has an order
        assert got == [] and all(v == () for v in r.values()), sess
    # an edge reached AFTER a session's entries ended is gone for the next session too: 10:56 is inside the last 5 minutes of nyam
    g = day({"10:56": up(HI + 5.0)})
    assert trades(g) == [] and resting({"sess": "mid"}, g)[sec(11, 1)] == BUY
    assert trades(day({"10:54": up(HI + 5.0)})) == [(sec(10, 54, 30), "short", HI)]


def test_the_bar_size_sets_when_orders_are_placed_and_the_touch_is_read_every_minute():
    p = {"tf": "5"}
    r, used, got, _ = watch(p, day({"09:46": up(HI), "09:48": up(HI + 5.0)}))           # a touch to the tick at 09:46, through it at 09:48: one 5-minute bar
    assert got == [] and r[sec(9, 46)] == BOTH and r[sec(9, 47)] == BUY and used[sec(9, 47)] == (-1,)
    # after a trade the other order comes back at a 5-minute close, not before
    r, _, got, _ = watch({**p, "exit_bars": 1}, day({"09:46": up(HI + 5.0)}))           # sold 09:46:30, out at the 09:50 close
    assert got == [(sec(9, 46, 30), "short", HI)] and all(r[s] == () for s in minutes(sec(9, 47), sec(9, 54)))
    assert all(r[s] == BUY for s in minutes(sec(9, 55), sec(10, 55)))


def test_new_york_day_sessions_only():
    g = day({"09:50": up(HI + 5.0), "11:20": dn(LO - 5.0)})
    for s in RM.DAY_PASSES:
        st = IT.IbTouch({**BASE, "sess": s})
        assert st.sessions() == ([s] if s in NY else []), s
    assert IT.IbTouch({**BASE, "sess": "all", "hold_to": "session"}).sessions() == list(NY)
    for s in ("asia", "london", "pre"):
        r, _, got, _ = watch({"sess": s}, g)
        assert got == [] and all(v == () for v in r.values()), s


def test_the_edges_are_the_days_not_the_sessions_one_instance_over_all_three_sessions():
    p = {"hold_to": "session", "sess": "all"}                                           # the tester's shape: flat at each session end
    g = day({"09:50": up(HI + 5.0), "11:20": up(HI + 5.0), "11:30": dn(LO - 5.0), "13:40": up(HI + 5.0), "13:50": dn(LO - 5.0)})
    r, used, got, _ = watch(p, g)
    assert got == [(sec(9, 50, 30), "short", HI), (sec(11, 30, 15), "long", LO)]         # the high in the morning, the low at midday, nothing after
    assert r[sec(11, 1)] == BUY and all(r[s] == () for s in r if s >= sec(11, 31))


# ---- (iii) max_tr, dir -------------------------------------------------------------------------------------------------------------------------------

def test_max_tr_is_one_an_edge_and_one_ends_the_day_after_the_first_trade():
    assert IT.IbTouch.defaults()["max_tr"] == 2
    g = day({"09:50": up(HI + 5.0), "10:00": dn(LO - 5.0)})
    assert trades(g, exit_bars=2) == [(sec(9, 50, 30), "short", HI), (sec(10, 0, 15), "long", LO)]
    r, used, got, _ = watch({"max_tr": 1, "exit_bars": 2}, g)
    assert got == [(sec(9, 50, 30), "short", HI)] and r[sec(9, 50)] == BOTH             # both orders rest; the first fill is the day's trade
    assert all(r[s] == () for s in r if s > sec(9, 50)) and used[sec(10, 1)] == (-1, 1)  # the low is used up at 10:00 all the same


def test_dir_runs_one_side_only_and_the_switched_off_edge_is_used_up_all_the_same():
    assert IT.IbTouch.defaults()["dir"] == "both"
    hi, lo = day({"09:50": up(HI + 5.0)}), day({"09:50": dn(LO - 5.0)})
    assert trades(hi, dir="short") == [(sec(9, 50, 30), "short", HI)] and trades(hi, dir="long") == []
    assert trades(lo, dir="long") == [(sec(9, 50, 15), "long", LO)] and trades(lo, dir="short") == []
    r, used, _, _ = watch({"dir": "long"}, hi)
    assert all(r[s] == BUY for s in minutes(sec(9, 45), sec(10, 55))) and used[sec(9, 51)] == (-1,)
    r, used, _, _ = watch({"dir": "short"}, lo)
    assert all(r[s] == SELL for s in minutes(sec(9, 45), sec(10, 55))) and used[sec(9, 51)] == (1,)
    _, res = run({"dir": "long"}, lo)
    assert res.both_sides is False and res.trades[0]["oco"] is False                    # one side only: no pair


# ---- (iv) flat by 15:58 and the standard exits -------------------------------------------------------------------------------------------------------

def test_a_trade_with_no_stop_hit_is_flat_by_15_58_and_the_standard_stop_and_target_act():
    for sess, when in (("nyam", "09:50"), ("mid", "11:20"), ("pm", "13:50")):
        _, res = run({"sess": sess}, day({when: up(HI + 5.0)}))
        t, = res.trades
        assert t["side"] == "short" and t["exit_reason"] == "time" and ns("15:58") // 1_000_000 <= t["exit_ms"] <= ns("15:58") // 1_000_000 + 60_000, sess
    # a 10-point stop, target 1R: sold at 15020, the stop is 15030 and the target 15010
    _, res = run({"stop_val": 10.0, "tgt_r": 1.0}, day({"09:50": up(HI + 5.0), "09:52": up(HI + 15.0)}))
    t, = res.trades
    assert (t["side"], t["sl"], t["tp"]) == ("short", HI + 10.0, HI - 10.0)
    assert t["exit_reason"] == "tp" and at(t) == sec(9, 50, 30)                         # the 09:50 minute closes at 15000: through the target
    _, res = run({"stop_val": 10.0, "tgt_r": 0.0}, day({"09:50": up(HI + 5.0, HI), "09:51": (HI, HI + 15.0, HI, HI + 12.0, 40)}))
    t, = res.trades
    assert t["exit_reason"] == "sl" and t["net"] < 0
    # no structure level goes with the order: stop_mode struct is the ATR stop
    a = run({"stop_mode": "struct", "stop_val": 2.0, "tgt_r": 1.0}, day({"09:50": up(HI + 5.0)}))[1].trades
    b = run({"stop_mode": "atr", "stop_val": 2.0, "tgt_r": 1.0}, day({"09:50": up(HI + 5.0)}))[1].trades
    assert a == b and len(a) == 1


def test_the_family_runs_with_strict_limit_a_fill_print_through_the_stop_is_a_loss():
    assert IT.IbTouch.SCREEN_RUN == {"strict_limit": True}
    g = day({"09:50": up(HI + 5.0)})                                                    # the fill print is 15025: 3 points through a 2-point stop
    _, res = run({"stop_val": 2.0, "tgt_r": 1.0}, g)
    t, = res.trades
    assert t["exit_reason"] == "sl" and t["exit_ms"] == t["entry_ms"] and t["net"] < 0
    _, res = run({"stop_val": 2.0, "tgt_r": 1.0}, g, costs=S.Costs())                   # (the tester's law would hold it and book the target)
    assert res.trades[0]["exit_reason"] == "tp"


# ---- (v) the range is ib_n's range -------------------------------------------------------------------------------------------------------------------

def walk(seed, swing=0.0):
    """A seeded day: quiet at 15000 to 09:30, then a walk on the tick grid that is lively for 5 / 15 / 30 / 60 minutes and calm after (the
    edges of the range are then reached at any time of the day, or never). swing > 0: the calm part also drifts up and down in legs of
    25 / 45 / 70 minutes, `swing` points a minute (such a day goes from one edge of the range to the other)."""
    g = np.random.default_rng(seed)
    live, calm, leg = (5, 15, 30, 60)[seed % 4], (0.75, 1.5, 2.5)[seed // 4 % 3], (25, 45, 70)[seed % 3]
    out, o = quiet(570), PX
    for m in range(390):
        drift = 0.0 if m < live else swing * (1 if ((m - live + leg // 2) // leg) % 2 else -1) * (1 if seed % 2 else -1)
        c = o + round(float(g.normal(drift, 6.0 if m < live else calm)) / TICK) * TICK
        w = 8 if m < live else 3
        h, l = max(o, c) + int(g.integers(0, w)) * TICK, min(o, c) - int(g.integers(0, w)) * TICK
        out.append((o, h, l, c, 40))
        o = c
    return out


def ib_n_range(tape, ib, tf="5", root=None):
    """The range ib_n itself reads on this tape (mode fade reads it at the first tf close at or after the range's end)."""
    st = B.IbN({"hold_to": "day", "tf": tf, "sess": "pm", "mode": "fade", "ib_min": ib})
    st.ROLLS = frozenset()
    if root:
        st.root = root
    S.run_session(st, tape, daily=[], on_error="raise")
    return st.ibh, st.ibl


@pytest.mark.parametrize("ib", ["5", "15", "30", "60"])
def test_the_range_is_ib_ns_range_on_random_days(ib):
    for seed in range(12):
        bars = walk(seed) if seed % 2 else quiet(60) + rand_bars(900, seed, p0=PX, step=4.0)
        tape = tape_of(bars)
        n = int(ib)
        want = (max(b[1] for b in bars[570:570 + n]), min(b[2] for b in bars[570:570 + n]))
        assert ib_n_range(tape, ib) == want, seed
        for tf in ("1", "5", "15", "30"):
            st, _ = run({"tf": tf, "ib_min": ib, "sess": "pm"}, bars, tape=tape)
            assert (st.hi, st.lo) == want, (seed, tf)


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_the_range_is_ib_ns_range_on_real_build_days(root):
    real_days()
    for d in days_of(root, 4):
        tape = S.load_tape(d, root)
        a, b60 = np.searchsorted(tape.ts, [S.et_ns(tape.date, "09:30"), S.et_ns(tape.date, "10:30")])
        assert b60 > a
        for ib in ("5", "15", "30", "60"):
            b = int(np.searchsorted(tape.ts, S.et_ns(tape.date, "09:30") + int(ib) * 60 * S.NS))
            want = (float(tape.px[a:b].max()), float(tape.px[a:b].min()))                # the prints of 09:30 .. the range's end, no more
            st = IT.IbTouch({"hold_to": "day", "tf": "5", "sess": "pm", "ib_min": ib})
            st.ROLLS, st.root = frozenset(), root
            S.run_session(st, tape, daily=[], on_error="raise")
            assert (st.hi, st.lo) == want == ib_n_range(tape, ib, root=root), (root, d, ib)


# ---- (vi) NO LOOK-AHEAD ------------------------------------------------------------------------------------------------------------------------------

MIX = {"09:50": up(HI + 5.0), "10:00": dn(LO - 5.0)}


def test_a_future_print_cannot_change_an_order_a_touch_or_a_trade_before_it():
    bars = day(MIX)
    tape = tape_of(bars)
    p = {"exit_bars": 2}
    r, used, got, _ = watch(p, bars, tape)
    assert got == [(sec(9, 50, 30), "short", HI), (sec(10, 0, 15), "long", LO)]
    for cut in (sec(9, 45), sec(9, 46), sec(9, 50), sec(9, 50, 30), sec(9, 51), sec(9, 53), sec(10), sec(10, 0, 15), sec(10, 30)):
        r2, used2, got2, _ = watch(p, bars, garble(tape, ns("00:00") + cut * S.NS))
        assert {s: v for s, v in r2.items() if s <= cut} == {s: v for s, v in r.items() if s <= cut}, cut
        assert {s: v for s, v in used2.items() if s <= cut} == {s: v for s, v in used.items() if s <= cut}, cut
        assert [x for x in got2 if x[0] < cut] == [x for x in got if x[0] < cut], cut


def test_the_range_is_the_prints_of_its_own_minutes_no_more_and_no_less():
    bars = day()
    tape = tape_of(bars)
    for ib, end in (("5", sec(9, 35)), ("15", sec(9, 45)), ("30", sec(10)), ("60", sec(10, 30))):
        for tf in ("1", "5", "15", "30"):
            p = {"tf": tf, "ib_min": ib}
            # every print from the range's end on rewritten: the range, and the orders placed at its end, stay
            r, _, _, st = watch(p, bars, garble(tape, ns("00:00") + end * S.NS))
            assert (st.hi, st.lo) == (HI, LO), (ib, tf)
            if end % (int(tf) * 60) == 0:
                assert r[end] == BOTH and all(r[s] == () for s in r if s < end), (ib, tf)
            # the last minute of the range rewritten: the range is the rewritten prints'
            dirty = garble(tape, ns("00:00") + (end - 60) * S.NS)
            a, b = np.searchsorted(dirty.ts, [ns("09:30"), ns("00:00") + end * S.NS])
            st, _ = run(p, bars, tape=dirty)
            assert (st.hi, st.lo) == (float(dirty.px[a:b].max()), float(dirty.px[a:b].min())) != (HI, LO), (ib, tf)


def test_no_order_exists_before_the_range_has_ended_whatever_the_range_holds_so_far():
    for seed in range(6):
        bars = walk(seed)
        for ib in ("5", "15", "30", "60"):
            for tf in ("1", "5", "15", "30"):
                r, used, _, _ = watch({"tf": tf, "ib_min": ib}, bars)
                end = OPEN + int(ib) * 60
                assert all(r[s] == () and used[s] == () for s in r if s < end), (seed, ib, tf)


def hole(tape, a, b):
    """The tape without the prints of [a, b) (ET clock times of the day)."""
    keep = ~((tape.ts >= ns(a)) & (tape.ts < ns(b)))
    return S.Tape(tape.root, tape.date, tape.contract, tape.ts[keep], tape.px[keep], tape.size[keep])


def test_a_bar_closed_late_after_a_hole_in_the_tape_does_not_make_the_range_early():
    # 5-minute bars, ib_min 15. The minutes 09:39-09:43 never printed, so the Template closes the bar 09:35-09:40 late: at 09:45:00, when the
    # 09:44 minute bar arrives and BEFORE that minute is added. The 09:44 minute holds the high of the range (15030). A rule that took the wall
    # clock of that late close (09:45 = the range's end) would read the range without its last minute: 15020.
    bars = day({"09:44": up(15030.0)})
    t = hole(tape_of(bars), "09:39", "09:44")
    r, _, got, st = watch({"tf": "5"}, bars, t)
    assert (st.hi, st.lo) == (15030.0, LO) and r[sec(9, 45)] == ((-1, 15030.0), (1, LO)) and got == []
    assert all(r[s] == () for s in r if s < sec(9, 45))
    assert ib_n_range(t, "15") == (HI, LO)                           # ib_n (fade) takes the wall clock there: the one day the two ranges differ
    inside = day({"09:44": up(15030.0), "09:50": up(15025.0)})       # 15025 at 09:50 is inside the range: no touch, no trade
    assert trades(inside, tape=hole(tape_of(inside), "09:39", "09:44"), tf="5") == []


def test_a_hole_at_the_end_of_the_range_does_not_let_the_minute_after_it_into_the_range():
    # The 09:44 minute never printed, so the first bar that shows the range has ended is the 09:45 minute itself -- and it trades up to 15030.
    # That minute is AFTER the range: the range stays 14980 .. 15020 and the minute is the first touch of the high (no order was there yet).
    bars = day({"09:45": up(15030.0), "09:50": up(15040.0)})
    r, used, got, st = watch({}, bars, hole(tape_of(bars), "09:44", "09:45"))
    assert (st.hi, st.lo) == (HI, LO) and got == [] and used[sec(9, 46)] == (-1,)
    assert all(r[s] == () for s in r if s < sec(9, 46)) and all(r[s] == BUY for s in minutes(sec(9, 46), sec(10, 55)))


def test_a_day_without_a_print_in_the_range_has_no_range_and_no_trade():
    bars = day({"09:50": up(HI + 5.0), "10:00": dn(LO - 5.0)})
    for tf in ("1", "5"):
        r, used, got, st = watch({"tf": tf}, bars, hole(tape_of(bars), "09:30", "09:45"))
        assert (st.hi, st.lo) == (None, None) and got == [] and all(v == () for v in r.values()) and all(v == () for v in used.values()), tf


def test_can_enter_counts_a_fill_it_has_not_seen_yet():
    # 5-minute bars, max_tr 1, a 2-point stop: sold at 09:46:30 and stopped on the fill print. At the 09:47 minute close (no tf close: the
    # Template has not looked at the orders since) the instance is flat again, but its one entry is spent.
    asked = []

    class Ask(IT.IbTouch):
        def on_bar(self, ctx, bar):
            super().on_bar(ctx, bar)
            if sec_of(ctx) == sec(9, 47):
                asked.append((self.can_enter(ctx), self.n_ent, ctx.flat))

    _, res = run({"tf": "5", "max_tr": 1, "stop_val": 2.0, "tgt_r": 1.0}, day({"09:46": up(HI + 5.0)}), cls=Ask)
    assert asked == [(False, 1, True)] and len(res.trades) == 1


def test_an_order_placed_at_a_late_close_does_not_outlive_the_minute_it_could_not_see():
    # 5-minute bars, a mid idea. The 11:04 minute never printed, so the bar 11:00-11:05 (the session's first close) is closed late, at
    # 11:06:00, before the 11:05 minute is added -- and that minute went to the high, to the tick. The sell placed at that late close is
    # taken away at once, when the 11:05 minute is read: the trade-through at 11:07 finds no order.
    p = {"tf": "5", "sess": "mid"}
    bars = day({"11:05": up(HI), "11:07": up(HI + 5.0)})
    t = hole(tape_of(bars), "11:04", "11:05")
    r, used, got, _ = watch(p, bars, t)
    assert got == [] and r[sec(11, 6)] == BUY and used[sec(11, 6)] == (-1,)
    # the same hole without the 11:05 touch: both orders go in at the late close and the 11:07 minute is sold
    bars = day({"11:07": up(HI + 5.0)})
    r, _, got, _ = watch(p, bars, hole(tape_of(bars), "11:04", "11:05"))
    assert r[sec(11, 6)] == BOTH and got == [(sec(11, 7, 30), "short", HI)]


# ---- (vii) the rule against an independent restatement, on random days ---------------------------------------------------------------------------------

def reference(bars, tf, sess, ib, max_tr=2, exit_bars=0, side="both"):
    """Every entry of the day as (second, side, price), from the written rule alone, on minute_tape's four prints a minute (:00 the open, :15
    and :30 the low and the high -- the high first in a down minute --, :45 the close). The stop is far away and there is no target: a trade
    ends after `exit_bars` tf closes (0 = never before 15:58)."""
    s0, s1 = S.SESS[sess]
    end = OPEN + ib * 60
    hi, lo = max(b[1] for b in bars[OPEN // 60:end // 60]), min(b[2] for b in bars[OPEN // 60:end // 60])
    edge, used, live = {"short": hi, "long": lo}, {"short": False, "long": False}, {}
    pos, n, held, out = None, 0, 0, []
    for m in range(end // 60 - 1, len(bars)):                        # from the last minute of the range: its close is the range's end
        o, h, l, c, _ = bars[m]
        T = (m + 1) * 60                                             # the second this minute ends at
        if T > end:
            for k, p in enumerate((o, *((l, h) if c >= o else (h, l)), c)):
                t = m * 60 + 15 * k
                for sd in list(live):                                # an order is live 85 ms after the close it was placed at
                    if t >= live[sd] + 0.085 and (p >= hi + TICK if sd == "short" else p <= lo - TICK):
                        out.append((t, sd, edge[sd]))
                        pos, n, held, live = t, n + 1, 0, {}         # the fill takes the other order with it
                        break
            used["short"], used["long"] = used["short"] or h >= hi, used["long"] or l <= lo
            live = {sd: v for sd, v in live.items() if not used[sd]}
        if T >= s1 - 300:                                            # the session's entries end here
            break
        if T % (tf * 60):
            continue
        if pos is not None:
            held += 1
            if exit_bars and held >= exit_bars:
                pos = None                                           # out at this close; the next close can place an order
            continue
        if T > s0 and n < max_tr:
            for sd in ("short", "long"):
                if not used[sd] and sd not in live and side in ("both", sd) and (c < hi if sd == "short" else c > lo):
                    live[sd] = T
    return out


DAYS = [walk(seed) for seed in range(24)] + [walk(100 + seed, swing=(0.6, 1.2)[seed // 12]) for seed in range(24)]


@pytest.mark.parametrize("ib", [5, 15, 30, 60])
@pytest.mark.parametrize("sess", NY)
@pytest.mark.parametrize("tf", [1, 5, 15, 30])
def test_the_entries_equal_the_written_rule_on_random_days(tf, sess, ib):
    n = two = 0
    for i, bars in enumerate(DAYS):
        p = {"tf": str(tf), "sess": sess, "ib_min": str(ib), "exit_bars": 3}
        want = reference(bars, tf, sess, ib, exit_bars=3)
        r, _, got, _ = watch(p, bars)
        assert got == want, (i, got, want)
        for t, sd, px in got:                                        # the order was resting at the last minute close before its fill
            assert (1 if sd == "long" else -1, px) in r[t // 60 * 60], (i, t)
        n += len(want)
        two += len(want) == 2
    assert n > 0, "the random days never came back to an edge in this session: the comparison would be empty"
    if sess == "nyam" and tf <= 5 and ib <= 30:                      # (with ib_min 60 the orders rest 25 minutes: no random day crosses the range in that)
        assert two > 0, "no day traded both edges"


@pytest.mark.parametrize("more", [{"max_tr": 1}, {"side": "long"}, {"side": "short"}, {"exit_bars": 0}, {"exit_bars": 1}])
def test_the_entries_equal_the_written_rule_with_one_entry_one_side_and_other_exits(more):
    n = 0
    kw = {"exit_bars": 3, **more}
    for i, bars in enumerate(DAYS):
        for tf, sess, ib in ((1, "nyam", 15), (5, "nyam", 30), (5, "mid", 15), (15, "pm", 5), (1, "pm", 60)):
            p = {"tf": str(tf), "sess": sess, "ib_min": str(ib), "exit_bars": kw["exit_bars"], "max_tr": kw.get("max_tr", 2), "dir": kw.get("side", "both")}
            want = reference(bars, tf, sess, ib, **kw)
            assert trades(bars, **p) == want, (i, tf, sess, ib)
            n += len(want)
    assert n > 0


def test_the_worse_fills_of_a_two_sided_family_leave_the_entries_as_they_are():
    # the blueprint's worse fills for a family that rests orders on both sides: 2 ticks, 250 ms, and the other order cancelled 100 ms late.
    # On these tapes (a print every 15 s) nothing can trade inside those windows: the entries are the rule's, and no late leg fills twice.
    n = 0
    for i, bars in enumerate(DAYS[::3]):
        for tf, sess, ib in ((1, "nyam", 5), (5, "nyam", 15), (5, "mid", 30)):
            p = {"tf": str(tf), "sess": sess, "ib_min": str(ib), "exit_bars": 3}
            _, res = run(p, bars, costs=S.Costs(slippage_ticks=2.0, latency_ms=250, strict_limit=True, oco_cancel_ms=100))
            assert entries(res) == reference(bars, tf, sess, ib, exit_bars=3), (i, tf, sess, ib)
            assert not any(t.get("double_fill") for t in res.trades)
            n += len(res.trades)
    assert n > 0


def test_a_side_a_filter_blocks_is_asked_again_at_each_close_and_an_order_that_rests_is_not():
    """A filter block is read inside allowed(side) when an order is placed. Here a stand-in for one: shorts are allowed 09:50-09:52 only."""
    class Gate(Look):
        def allowed(self, side):
            return super().allowed(side) and (side == "long" or sec(9, 50) <= sec_of(self._cx) <= sec(9, 52))

    r, _, got, _ = watch({}, day({"10:20": up(HI + 5.0)}), base=Gate)
    assert all(r[s] == BUY for s in minutes(sec(9, 45), sec(9, 49)))                    # the sell is asked for at every close and refused
    assert all(r[s] == BOTH for s in minutes(sec(9, 50), sec(10, 20)))                  # placed at 09:50; it rests on after 09:52
    assert got == [(sec(10, 20, 30), "short", HI)]
    r, _, got, _ = watch({}, day({"09:47": up(HI), "10:20": up(HI + 5.0)}), base=Gate)  # the high is touched while its order was kept out: gone
    assert got == [] and all(r[s] == BUY for s in minutes(sec(9, 45), sec(10, 55)))


def test_the_wrapped_family_with_every_block_off_is_the_family_trade_for_trade():
    n = 0
    for bars in DAYS[:8]:
        for tf, sess, ib in ((1, "nyam", "15"), (5, "nyam", "30"), (5, "mid", "15"), (15, "pm", "5")):
            p = {"tf": str(tf), "sess": sess, "ib_min": ib, "exit_bars": 3}
            a = run(p, bars)[1].trades
            b = run(p, bars, cls=B.WRAPPED["ib_touch"])[1].trades
            assert a == b
            n += len(a)
    assert n > 0


# ---- (viii) the settings and the registry ----------------------------------------------------------------------------------------------------------------

def test_the_settings_and_their_limits():
    d, sc = IT.IbTouch.defaults(), IT.IbTouch.schema()
    assert (d["ib_min"], d["max_tr"], d["dir"]) == ("60", 2, "both")
    assert sc["ib_min"] == ("choice", ("5", "15", "30", "60")) == B.IbN.schema()["ib_min"] and sc["max_tr"] == ("int", 1, 2)
    assert d["ib_min"] == B.IbN.defaults()["ib_min"]
    for bad in ({"ib_min": "45"}, {"ib_min": "10"}, {"ib_min": 60}, {"max_tr": 0}, {"max_tr": 3}, {"max_tr": 1.5}, {"dir": "up"}, {"mode": "fade"}, {"offset": 1}):
        with pytest.raises(ValueError):
            IT.IbTouch({"tf": "5", **bad})
    for ok in ({"ib_min": "5"}, {"ib_min": "15"}, {"ib_min": "30"}, {"ib_min": "60"}, {"max_tr": 1}, {"max_tr": 2}, {"dir": "short"}, {"dir": "long"}):
        IT.IbTouch({"tf": "5", **ok})


def test_the_registry_holds_ib_touch_as_written_it_rests_orders_on_both_sides_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["ib_touch"]
    lib = families.library("ib_touch")
    assert cls is IT.IbTouch and inputs == {} and both is True and cls.FEATURES == ()
    assert cls.SCREEN_TFS == ("1", "5", "15", "30") and set(B.IbN.SCREEN_TFS) < set(cls.SCREEN_TFS)      # ib_n's bar sizes, and 1
    assert both is families.REGISTRY["ib_n"][2] is families.REGISTRY["orb"][2]                             # marked as ib_n and orb are
    assert families.MODULE_OF["ib_touch"] == "ib_touch" and lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"]
    assert lib["mirror"] is None and lib["complexity"] == 6 and lib["variants"] == [{"ib_min": "15"}, {"ib_min": "30"}, {"ib_min": "60"}]
    assert len(lib["rationale"]) > 60 and lib["rationale"].count(". ") == 0 and "first" in notes and ". " not in notes
    assert issubclass(B.WRAPPED["ib_touch"], IT.IbTouch) and B.BASES["ib_touch"][0] is IT.IbTouch and B.B_ib_touch is B.WRAPPED["ib_touch"]
    assert B.BASES["ib_touch"][2] is True and not RM.is_time_fired(cls)
    with pytest.raises(ValueError):
        B.WRAPPED["ib_touch"]({"tf": "5", "stop_mode": "rng"})        # no structure height: only the standard table's stops


# ---- (ix) real BUILD days: the invariants of the code check, at 1 worker ------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_real_build_days_hold_the_window_one_position_the_edges_the_first_touch_and_the_flat_time(root):
    real_days()
    days = days_of(root, 4)
    hd = {"hold_to": "day", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}
    specs = [(IT.IbTouch, {**hd, "tf": tf, "sess": s, "ib_min": w}) for tf in ("1", "5") for s in NY for w in ("15", "30", "60")]
    kw = dict(root=root, days=days, period="build", workers=1, on_error="raise", **IT.IbTouch.SCREEN_RUN)
    out = S.run_many(specs, **kw)
    again = S.run_many(specs, **kw)
    assert [r["trades"] for r in out] == [r["trades"] for r in again]
    assert sum(r["skipped_by_error"] for r in out) == 0
    tapes = {d: S.load_tape(d, root) for d in days}
    total = pairs = 0
    for (cls, p), r in zip(specs, out):
        s0, s1 = S.SESS[p["sess"]]
        end = OPEN + int(p["ib_min"]) * 60
        last, sides = {}, set()
        pairs += r["both_sides_sessions"]
        for t in sorted(r["trades"], key=lambda t: t["entry_ms"]):
            d, tp = S._date(t["date"]), tapes[t["date"]]
            t0 = S.et_ns(d, "00:00")
            es = t["entry_ms"] / 1000 - t0 / S.NS
            assert max(s0, end) < es < s1 - 300, (p, t["date"], es)                    # while the orders rest: after the range's end, inside the session
            assert t["exit_ms"] <= S.et_ns(d, S.day_flat(d, root)) // 1_000_000 + 60_000
            assert last.get(t["date"], 0) <= t["entry_ms"]                            # one position at a time
            last[t["date"]] = t["exit_ms"]
            assert (t["date"], t["side"]) not in sides                                # an edge trades once a day
            sides.add((t["date"], t["side"]))
            a, b, c = np.searchsorted(tp.ts, [S.et_ns(d, "09:30"), t0 + end * S.NS, t["entry_ms"] // 60_000 * 60_000 * 1_000_000])
            hi, lo = float(tp.px[a:b].max()), float(tp.px[a:b].min())
            assert t["entry_price"] == t["order_price"] == (hi if t["side"] == "short" else lo)      # sold at the range high, bought at the range low
            if c > b:                                                                 # the FIRST touch: no print at or beyond the edge from the range's end to the minute of the fill
                assert tp.px[b:c].max() < hi if t["side"] == "short" else tp.px[b:c].min() > lo, (p, t["date"])
            total += 1
    assert total > 0 and pairs > 0
