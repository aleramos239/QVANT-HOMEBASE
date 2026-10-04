"""B4 wall_bounce / B5 wall_break (families/walls.py) against their pre-registered definitions (FAMILIES.md "Walls").

Synthetic tapes + synthetic feature tables only (no data file is read, no P&L of a real day is looked at): the trigger
fires exactly when defined -- hand-made cases, plus an INDEPENDENT oracle computed straight from the table arrays on
random days -- and never on a row that is not usable yet (the clock of tests/test_l2sim_lookahead.py: row of minute M
is usable at M + 60 s). The 1-vs-8-worker identity of both families runs through the registry in tests/test_families.py
(its CASES are built from families.REGISTRY; asserted here). The same look-ahead and oracle checks on REAL in-sample
days (tape AND features replaced after a cut) are in tests/test_fam_walls_real.py."""
import math

import numpy as np
import pytest

import families
import families.walls as W
import l2sim as S
import test_l2sim_lookahead as LA

D, T0, TICK = LA.D, LA.T0, 0.25                    # 2024-03-05, 09:30 ET (nyam start); minute m = [T0 + m min, + 60 s)
MIN = S.MIN_NS
MINUTES = range(-30, 90)                           # 09:00 .. 11:00 ET
QUIET = {"bid_px": 100.25, "ask_px": 100.75, "bid_wall_dist": 3, "bid_wall_sz": 10, "bid_med_sz": 5,
         "ask_wall_dist": 3, "ask_wall_sz": 10, "ask_med_sz": 5, "book_ok": True}      # a valid row without a wall (2 x median)
BOOK = [c for c in W.FEATURES if c not in ("t_utc", "book_ok")]
MASKED = {**{c: np.nan for c in BOOK}, "book_ok": False}                               # a roll / bad-book row as l2data masks it
DTYPE = {"book_ok": bool, "t_utc": np.int64, "bid_px": np.float64, "ask_px": np.float64}


def at(m: int) -> int:
    """Decision time of the close of minute m (= the instant row m becomes usable)."""
    return T0 + (m + 1) * MIN


def table(rows=None, drop=()):
    """One feature row per minute of MINUTES (QUIET unless overridden in `rows`), usable at the END of its minute;
    minutes in `drop` have no row at all. dtypes as the data layer's (float32 features, float64 anchors, int64 t_utc)."""
    rows = rows or {}
    ms = [m for m in MINUTES if m not in drop]
    full = [{**QUIET, **rows.get(m, {}), "t_utc": T0 // S.NS + 60 * m} for m in ms]
    return S.Features([at(m) for m in ms], {c: np.array([r[c] for r in full], dtype=DTYPE.get(c, np.float32)) for c in W.FEATURES})


def tape(prints=None, base=100.50):
    """Print j of minute m at m + (j + 1) s; `base` once a minute unless `prints[m]` lists the minute's prices."""
    prints = prints or {}
    ts, px = [], []
    for m in MINUTES:
        for j, p in enumerate(prints.get(m, [base])):
            ts.append(T0 + m * MIN + (j + 1) * S.NS)
            px.append(float(p))
    return S.Tape("NQ", D, "NQH4", ts, px, [1] * len(ts))


class Spy:
    """Records every decision the Template hands to the family (`seen`) and every order request it makes (`calls`)."""

    def __init__(self, params=None):
        super().__init__({"tf": "1", "sess": "nyam", **(params or {})})
        self.seen, self.calls = [], []

    def fam_signal(self, ctx):
        self.seen.append((ctx.now_ns, ctx.last_price))
        super().fam_signal(ctx)

    def _lim(self, ctx, side, px, struct=None, tp_px=None, ttl=None, tag=None):
        o = super()._lim(ctx, side, px, struct=struct, tp_px=tp_px, ttl=ttl, tag=tag)
        self.calls.append({"t": ctx.now_ns, "kind": "limit", "side": side, "px": px, "struct": struct, "ttl": ttl,
                           "placed": o is not None, "atr": self.atr})
        return o

    def _arm(self, ctx, legs, ttl=None, imm=False, tag=None):
        os_ = super()._arm(ctx, legs, ttl=ttl, imm=imm, tag=tag)
        assert len(legs) == 1 and not imm and legs[0][3] is None            # ONE leg, never an OCO pair, Template target
        self.calls.append({"t": ctx.now_ns, "kind": "stop", "side": legs[0][0], "px": legs[0][1], "struct": legs[0][2],
                           "ttl": ttl, "placed": len(os_) == 1, "atr": self.atr})
        return os_

    def _mkt(self, *a, **k):
        raise AssertionError("the wall families never enter at market")


class Bounce(Spy, W.WallBounce):
    pass


class Break(Spy, W.WallBreak):
    pass


def go(cls, rows=None, prints=None, params=None, drop=(), base=100.50, **costs):
    st = cls(params)
    res = S.run_session(st, tape(prints, base), costs=S.Costs(**costs) if costs else None, features=table(rows, drop))
    assert res.skip is None and res.both_sides is False                     # no strategy error; one direction (evidence)
    assert not any(t["oco"] or t["both_sides"] for t in res.trades)
    return st, res


def sig(st):
    return [(c["t"], c["side"], c["px"], c["struct"], c["placed"]) for c in st.calls]


# ---- registry / pre-registered defaults --------------------------------------------------------------------------
def test_registry_entries_carry_the_preregistered_defaults():
    for name, cls in (("wall_bounce", W.WallBounce), ("wall_break", W.WallBreak)):
        e = families.REGISTRY[name]
        assert e[0] is cls and e[1] == {} and e[2] is False and families.check_entry(name, e) == []
        assert cls.SCREEN_TFS == ("1", "5") and cls.session_independent is True and cls.FEATURES == W.FEATURES
        p = cls(families.screen_inputs(name, "5")).p
        assert (p["stop_mode"], p["tgt_r"], p["trail_atr"], p["exit_bars"], p["max_tr"], p["dir"], p["sess"]) == \
            ("struct", 2.0, 0.0, 0, 3, "both", "all")
        assert (p["f_trend"], p["f_vwap"], p["f_depth"], p["m"]) == ("off", "off", "off", 5.0)
    assert W.WallBounce({}).p["near"] == 2 and W.WallBreak({}).p["stand"] == 2 and (W.FRONT, W.BEYOND) == (1, 4)
    assert W.WallBounce.SCREEN_RUN == {"strict_limit": True} and getattr(W.WallBreak, "SCREEN_RUN", {}) == {}
    tiers = families.feature_columns()
    assert sorted(c for c in W.FEATURES if tiers[c] == "fixed") == ["ask_px", "bid_px", "book_ok", "t_utc"]


def test_the_c2_null_shuffles_the_wall_columns_and_keeps_the_anchors():
    import score
    null = score.C2Features(W.FEATURES, seed=1)
    assert set(null.shuffle_cols) == {"bid_wall_dist", "bid_wall_sz", "bid_med_sz", "ask_wall_dist", "ask_wall_sz", "ask_med_sz"}


def test_the_worker_identity_test_of_the_registry_covers_both_families():
    import test_families as TF
    assert {("wall_bounce", "1"), ("wall_bounce", "5"), ("wall_break", "1"), ("wall_break", "5")} <= set(TF.CASES)


# ---- B4 wall_bounce ----------------------------------------------------------------------------------------------
def bid_wall(sz=40, med=5, dist=1, bid=100.00, **kw):          # wall price = bid - dist ticks (default 99.75)
    return {"bid_px": bid, "ask_px": bid + 0.50, "bid_wall_dist": dist, "bid_wall_sz": sz, "bid_med_sz": med, **kw}


def ask_wall(sz=40, med=5, dist=1, ask=101.00, **kw):          # wall price = ask + dist ticks (default 101.25)
    return {"ask_px": ask, "bid_px": ask - 0.50, "ask_wall_dist": dist, "ask_wall_sz": sz, "ask_med_sz": med, **kw}


def test_bounce_bid_wall_two_ticks_below_the_last_print_rests_a_buy_limit_one_tick_in_front():
    st, res = go(Bounce, {5: bid_wall()}, {5: [100.50, 100.25], 6: [100.00, 99.75]})
    assert sig(st) == [(at(5), "long", 100.00, 98.75, True)] and st.calls[0]["ttl"] == 1 and st.calls[0]["kind"] == "limit"
    (t,) = res.trades                                          # filled only by the print AT the wall price (1-tick trade-through)
    assert (t["side"], t["order_price"], t["entry_price"], t["sl"], t["tp"]) == ("long", 100.00, 100.00, 98.75, 102.50)
    assert t["entry_ns"] == T0 + 6 * MIN + 2 * S.NS            # the 99.75 print, not the 100.00 one
    assert t["entry_price"] - t["sl"] <= 5 * (t["tp"] - t["entry_price"])              # Apex: stop <= 5 x target


def test_bounce_ask_wall_mirrors_into_a_sell_limit():
    st, res = go(Bounce, {5: ask_wall()}, {5: [100.50, 100.75], 6: [101.00, 101.25]})
    assert sig(st) == [(at(5), "short", 101.00, 102.25, True)]
    (t,) = res.trades
    assert (t["side"], t["entry_price"], t["sl"], t["tp"]) == ("short", 101.00, 102.25, 98.50)


def test_bounce_stop_is_floored_at_a_quarter_atr():
    wild = {m: [100.50, 110.50, 90.50, 100.50] for m in range(-30, 5)}                 # 20-point bars: ATR ~ 18.6
    st, res = go(Bounce, {5: bid_wall()}, {**wild, 5: [100.50, 100.25], 6: [100.00, 99.75]})
    (c,), (t,) = st.calls, res.trades
    d = 0.25 * c["atr"]
    assert d > 4.0 and c["struct"] == 98.75                    # the 5-tick structure stop is inside the floor
    assert t["sl"] == S.to_tick(100.00 - d, TICK) and t["tp"] == S.to_tick(100.00 + 2.0 * d, TICK)


@pytest.mark.parametrize("row,last,params,want", [
    (bid_wall(sz=25), 100.25, {}, True),                       # exactly 5 x the median is a wall
    (bid_wall(sz=24), 100.25, {}, False),                      # 4.8 x is not
    (bid_wall(sz=24), 100.25, {"m": 4.8}, True),               # ... unless m says so
    (bid_wall(), 100.50, {}, False),                           # 3 ticks in front: out of reach (near = 2)
    (bid_wall(), 100.50, {"near": 3}, True),
    (bid_wall(), 100.00, {}, True),                            # 1 tick in front: in reach, the limit rests AT the last print
    (bid_wall(), 100.00, {"near": 1}, True),                   # near = 1 is a live value (the 1-tick case alone)
    (bid_wall(), 100.25, {"near": 1}, False),
    (bid_wall(), 99.75, {}, False),                            # the last print is AT the wall
    (bid_wall(), 99.50, {}, False),                            # ... or through it
    (bid_wall(dist=0, bid=99.75), 100.25, {}, True),           # the wall is the best bid itself
    (bid_wall(dist=9, bid=102.00), 100.25, {}, True),          # same wall price from another anchor / distance
    (bid_wall(med=0), 100.25, {}, False),                      # degenerate median: not a valid row
])
def test_bounce_fires_exactly_on_the_definition(row, last, params, want):
    st, _ = go(Bounce, {5: row}, {5: [100.50, last]}, params)
    assert sig(st) == ([(at(5), "long", 100.00, 98.75, True)] if want else [])


def test_bounce_one_tick_from_the_wall_rests_the_limit_at_the_last_print_and_fills_only_at_the_wall():
    """SPEC: 'price within 2 ticks of it -> limit entry 1 tick in front of the wall'. One tick in front, that limit is AT
    the last print: it must rest (Template._lim alone would refuse it) and fill only on a print at the wall price."""
    st, res = go(Bounce, {5: bid_wall()}, {5: [100.50, 100.00], 6: [100.00, 100.00, 100.25]})
    assert sig(st) == [(at(5), "long", 100.00, 98.75, True)] and st.calls[0]["ttl"] == 1
    assert res.trades == []                                    # prints AT the limit price never fill it; cancelled at 09:37
    st, res = go(Bounce, {5: bid_wall()}, {5: [100.50, 100.00], 6: [100.00, 99.75]})
    (t,) = res.trades
    assert (t["side"], t["order_price"], t["entry_price"], t["sl"], t["tp"]) == ("long", 100.00, 100.00, 98.75, 102.50)
    assert t["entry_ns"] == T0 + 6 * MIN + 2 * S.NS            # the 99.75 print (the wall price), not the 100.00 one
    st, res = go(Bounce, {5: ask_wall()}, {5: [100.50, 101.00], 6: [101.00, 101.25]})  # mirror: ask wall at 101.25
    assert sig(st) == [(at(5), "short", 101.00, 102.25, True)]
    assert [(t["side"], t["entry_price"], t["sl"], t["tp"]) for t in res.trades] == [("short", 101.00, 102.25, 98.50)]


def test_bounce_one_tick_case_when_the_limit_sits_on_the_snapshots_other_side_still_fills_only_at_the_wall():
    """The wall IS the best bid (99.75) and the spread is one tick (ask 100.00); the last print is at 100.00. The limit at
    100.00 would be marketable against the snapshot's ask. The simulator does not fill it at once: only on a print at the
    wall price, at the limit price (FAMILIES.md walls addendum: pessimistic on which of these orders become trades)."""
    row = {**bid_wall(dist=0, bid=99.75), "ask_px": 100.00}
    st, res = go(Bounce, {5: row}, {5: [100.50, 100.00], 6: [100.00, 100.25]})
    assert sig(st) == [(at(5), "long", 100.00, 98.75, True)] and res.trades == []
    _, res = go(Bounce, {5: row}, {5: [100.50, 100.00], 6: [100.25, 99.75]})
    assert [(t["entry_price"], t["entry_ns"]) for t in res.trades] == [(100.00, T0 + 6 * MIN + 2 * S.NS)]


def test_bounce_never_rests_a_limit_beyond_the_last_print():
    """The override of Template._lim relaxes ONE thing (a limit AT the last print): beyond it nothing is placed."""
    st = Bounce()
    seen = []

    def probe(ctx):
        seen.append([W.WallBounce._lim(st, ctx, side, px, ttl=1) is not None
                     for side, px in (("long", 100.25), ("long", 100.50), ("long", 100.75),
                                      ("short", 100.75), ("short", 100.50), ("short", 100.25))])
        st._cancel(ctx)
    st.fam_signal = probe
    S.run_session(st, tape(), features=table())
    assert seen and all(x == [True, True, False, True, True, False] for x in seen)     # the last print is 100.50


def test_bounce_a_wall_on_each_side_in_reach_places_nothing():
    both = {**bid_wall(), **ask_wall(ask=100.50), "bid_px": 100.00}                    # walls at 99.75 and 100.75, last 100.25
    assert sig(go(Bounce, {5: both}, {5: [100.50, 100.25]})[0]) == []
    one = {**both, "ask_wall_sz": 10}
    assert sig(go(Bounce, {5: one}, {5: [100.50, 100.25]})[0]) == [(at(5), "long", 100.00, 98.75, True)]


@pytest.mark.parametrize("bad", [MASKED, {**bid_wall(), "book_ok": False}, bid_wall(med=np.nan), bid_wall(sz=np.nan),
                                 bid_wall(dist=np.nan), bid_wall(bid=np.nan)])
def test_bounce_masked_or_nan_row_is_no_signal_and_is_never_forward_filled(bad):
    prints = {4: [100.50, 101.00], 5: [100.50, 100.25], 6: [100.00, 99.75]}            # minute 4 closes out of reach
    st, res = go(Bounce, {4: bid_wall(), 5: bad}, prints)      # the wall of minute 4 must not carry into minute 5
    assert sig(st) == [] and res.trades == []


def test_bounce_reads_the_wall_only_once_its_minute_has_ended():
    """The wall is in the row of minute 5 (usable 09:36:00). The last print is 2 ticks in front of it already at the
    09:35:00 decision: nothing may happen there; the order is placed at 09:36:00."""
    st, _ = go(Bounce, {5: bid_wall()}, {4: [100.50, 100.25], 5: [100.25]})
    assert (at(4), 100.25) in st.seen and sig(st) == [(at(5), "long", 100.00, 98.75, True)]


def test_bounce_stale_newest_row_is_no_signal():
    """Minute 5 has no row at all: at 09:36:00 the newest usable row is minute 4's (a wall, in reach) -- one minute old."""
    prints = {4: [100.50, 101.00], 5: [100.50, 100.25]}
    assert sig(go(Bounce, {4: bid_wall()}, prints, drop=(5,))[0]) == []
    assert sig(go(Bounce, {4: bid_wall(), 5: bid_wall()}, prints)[0]) == [(at(5), "long", 100.00, 98.75, True)]


def test_bounce_order_lives_one_tf_bar():
    st, res = go(Bounce, {5: bid_wall()}, {5: [100.50, 100.25], 6: [100.25], 7: [99.75, 99.50]})
    assert sig(st) == [(at(5), "long", 100.00, 98.75, True)] and res.trades == []      # cancelled at 09:37:00, before 99.75
    st, res = go(Bounce, {5: bid_wall(), 6: bid_wall()}, {5: [100.50, 100.25], 6: [100.25], 7: [99.75, 99.50]})
    assert [c["t"] for c in st.calls] == [at(5), at(6)] and len(res.trades) == 1       # re-evaluated and re-placed


def test_bounce_strict_limit_stops_a_fill_print_that_is_already_through_the_stop():
    prints = {5: [100.50, 100.25], 6: [98.00, 103.00]}         # the fill print is beyond the 98.75 stop, then a rally
    _, lax = go(Bounce, {5: bid_wall()}, prints)
    _, strict = go(Bounce, {5: bid_wall()}, prints, strict_limit=True)
    assert lax.trades[0]["exit_reason"] == "tp" and strict.trades[0]["exit_reason"] == "sl"
    assert strict.trades[0]["entry_ns"] == strict.trades[0]["exit_ns"]


def test_no_entry_in_the_last_five_minutes_of_the_session():
    rows = {m: bid_wall() for m in range(80, 90)}              # the trigger holds at every close 10:51:00 .. 11:00:00
    prints = {m: [100.25] for m in range(80, 90)}
    st, res = go(Bounce, rows, prints, {"max_tr": 20})
    assert [c["t"] for c in st.calls] == [at(m) for m in range(80, 84)] and res.trades == []       # 10:51 .. 10:54 only
    brk = {m: (bid_wall(dist=0, bid=100.00) if m % 3 else {"bid_px": 99.00, "ask_px": 99.50}) for m in range(75, 90)}
    st, _ = go(Break, brk, {m: [99.50] for m in range(75, 90)}, {"max_tr": 20})
    assert st.calls and all(c["t"] < at(84) for c in st.calls) and max(t for t, _ in st.seen) == at(83)


# ---- B5 wall_break -----------------------------------------------------------------------------------------------
STAND = bid_wall(dist=1, bid=100.25)                           # bid wall at 100.00
GONE = {"bid_px": 99.50, "ask_px": 100.00}                     # the book has moved below it (no wall: QUIET sizes)
A_STAND = ask_wall(dist=1, ask=100.75)                         # ask wall at 101.00
A_GONE = {"bid_px": 101.00, "ask_px": 101.50}


def test_break_bid_wall_gone_and_traded_through_rests_a_sell_stop_one_tick_below_the_last_print():
    st, res = go(Break, {3: STAND, 4: STAND, 5: GONE}, {5: [100.25, 99.75], 6: [99.50]})
    assert sig(st) == [(at(5), "short", 99.50, 101.00, True)] and st.calls[0]["ttl"] == 1 and st.calls[0]["kind"] == "stop"
    (t,) = res.trades                                          # stop at 99.50 fills 1 tick worse; brackets keep 1.5 pts / 3 pts
    assert (t["side"], t["order_price"], t["entry_price"], t["sl"], t["tp"]) == ("short", 99.50, 99.25, 100.75, 96.25)
    assert t["sl"] - t["entry_price"] <= 5 * (t["entry_price"] - t["tp"])


def test_break_ask_wall_mirrors_into_a_buy_stop():
    st, res = go(Break, {3: A_STAND, 4: A_STAND, 5: A_GONE}, {5: [100.75, 101.25], 6: [101.50]})
    assert sig(st) == [(at(5), "long", 101.50, 100.00, True)]
    (t,) = res.trades
    assert (t["side"], t["entry_price"], t["sl"], t["tp"]) == ("long", 101.75, 100.25, 104.75)


def test_break_stop_is_floored_at_a_quarter_atr():
    wild = {m: [100.50, 110.50, 90.50, 100.50] for m in range(-30, 5)}
    st, res = go(Break, {3: STAND, 4: STAND, 5: GONE}, {**wild, 5: [100.25, 99.75], 6: [99.50]})
    (c,), (t,) = st.calls, res.trades
    d = 0.25 * c["atr"]
    assert d > 4.0 and t["sl"] == S.to_tick(99.50 + d, TICK) - TICK and t["tp"] == S.to_tick(99.50 - 2.0 * d, TICK) - TICK


@pytest.mark.parametrize("rows,last,params,want", [
    ({3: STAND, 4: STAND, 5: GONE}, 99.75, {}, True),
    ({4: STAND, 5: GONE}, 99.75, {}, False),                                           # stood on ONE snapshot only
    ({3: bid_wall(dist=2, bid=100.25), 4: STAND, 5: GONE}, 99.75, {}, False),          # two walls at different prices
    ({3: bid_wall(dist=3, bid=100.75), 4: STAND, 5: GONE}, 99.75, {}, True),           # same price, other anchor / distance
    ({3: bid_wall(sz=24, dist=1, bid=100.25), 4: STAND, 5: GONE}, 99.75, {}, False),   # 4.8 x the median is no wall
    ({3: STAND, 4: STAND, 5: STAND}, 99.75, {}, False),                                # still standing in the newest row
    ({3: STAND, 4: STAND, 5: bid_wall(sz=24, dist=1, bid=100.25)}, 99.75, {}, True),   # same level, no longer a wall
    ({3: STAND, 4: STAND, 5: bid_wall(dist=2, bid=100.25)}, 99.75, {}, True),          # the largest level is elsewhere
    ({3: STAND, 4: STAND, 5: GONE}, 100.00, {}, False),                                # last print AT the wall price
    ({3: STAND, 4: STAND, 5: GONE}, 100.25, {}, False),                                # ... or still in front of it
    ({3: STAND, 4: STAND, 5: MASKED}, 99.75, {}, False),                               # newest row unknown, not "gone"
    ({3: MASKED, 4: STAND, 5: GONE}, 99.75, {}, False),
    ({3: STAND, 4: {**STAND, "book_ok": False}, 5: GONE}, 99.75, {}, False),
    ({3: STAND, 4: STAND, 5: {**GONE, "bid_med_sz": np.nan}}, 99.75, {}, False),
    ({3: STAND, 4: STAND, 5: GONE}, 99.75, {"stand": 3}, False),                       # stand = 3 needs minute 2 as well
    ({2: STAND, 3: STAND, 4: STAND, 5: GONE}, 99.75, {"stand": 3}, True),
])
def test_break_fires_exactly_on_the_definition(rows, last, params, want):
    st, _ = go(Break, rows, {5: [100.25, last]}, params)
    assert sig(st) == ([(at(5), "short", last - TICK, 101.00, True)] if want else [])


def test_break_needs_consecutive_minutes():
    """Minute 3 has no row: the wall of minutes 2 and 4 did not stand on two CONSECUTIVE snapshots."""
    prints = {5: [100.25, 99.75]}
    assert sig(go(Break, {2: STAND, 4: STAND, 5: GONE}, prints, drop=(3,))[0]) == []
    late = {5: [100.25, 99.75], 6: [99.75]}                    # minute 5 has no row: at 09:37:00 rows 6, 4, 3 are not consecutive
    assert sig(go(Break, {3: STAND, 4: STAND}, late, drop=(5,))[0]) == []
    assert sig(go(Break, {3: STAND, 4: STAND}, late)[0]) == [(at(5), "short", 99.50, 101.00, True)]


def test_break_reads_the_gone_row_only_once_its_minute_has_ended():
    """The price is through the wall already during minute 4, the wall is gone in the row of minute 5 (usable 09:36:00):
    at 09:35:00 the newest usable row still shows it standing -> nothing; the order is placed at 09:36:00."""
    st, _ = go(Break, {3: STAND, 4: STAND, 5: GONE}, {4: [100.25, 99.75], 5: [99.75]})
    assert (at(4), 99.75) in st.seen and sig(st) == [(at(5), "short", 99.50, 101.00, True)]


def test_break_order_lives_one_tf_bar():
    st, res = go(Break, {3: STAND, 4: STAND, 5: GONE}, {5: [100.25, 99.75], 6: [99.75], 7: [99.50, 99.00]})
    assert sig(st) == [(at(5), "short", 99.50, 101.00, True)] and res.trades == []


# ---- random days: an independent oracle, and no dependence on rows that are not usable yet -------------------------
def random_day(seed: int):
    """Random-walk tape (4 prints a minute) + a table with frequent walls near the touch, standing walls that vanish,
    masked rows and missing rows. Returns (rows, prints, drop)."""
    g = np.random.default_rng(seed)
    p, wb, wa, rows, prints = 400, None, None, {}, {}          # prices in ticks
    for m in MINUTES:
        seq = []
        for s in g.integers(-2, 3, size=4):
            p += int(s)
            seq.append(p * TICK)
        prints[m] = seq
        bid = p - int(g.integers(0, 2))
        ask = bid + int(g.integers(1, 3))
        if wb is None or wb > bid or g.random() < 0.3:
            wb = bid - int(g.integers(0, 4))
        if wa is None or wa < ask or g.random() < 0.3:
            wa = ask + int(g.integers(0, 4))
        rows[m] = MASKED if g.random() < 0.05 else {
            "bid_px": bid * TICK, "ask_px": ask * TICK, "bid_wall_dist": bid - wb, "ask_wall_dist": wa - ask,
            "bid_wall_sz": float(g.choice([40, 25, 24, 10])), "ask_wall_sz": float(g.choice([40, 25, 24, 10])),
            "bid_med_sz": 5, "ask_med_sz": 5, "book_ok": True}
    return rows, prints, tuple(int(x) for x in g.choice(list(MINUTES), 4, replace=False))


def oracle(f, kind: str, now: int, last: float, p: dict):
    """The definition, straight from the table arrays (no ctx): the order request expected at a decision, or None."""
    row = {int(u): i for i, u in enumerate(f.usable_ns)}
    c = f.cols

    def side(i, s):                                            # (valid, wall price in ticks, is a wall)
        px, dist, sz, med = (float(c[f"{s}_{k}"][i]) for k in ("px", "wall_dist", "wall_sz", "med_sz"))
        if not c["book_ok"][i] or not all(map(math.isfinite, (px, dist, sz, med))) or med <= 0:
            return False, None, False
        return True, round(px / TICK + (-dist if s == "bid" else dist)), sz >= p["m"] * med

    lt, hits = round(last / TICK), []
    if kind == "limit":
        i = row.get(now)
        for s, sd in (("bid", 1), ("ask", -1)):
            ok, w, big = side(i, s) if i is not None else (False, None, False)
            if ok and big and 1 <= sd * (lt - w) <= p["near"]:
                hits.append(("long" if sd > 0 else "short", (w + sd) * TICK, (w - 4 * sd) * TICK))
    else:
        idx = [row.get(now - k * MIN) for k in range(p["stand"] + 1)]
        for s, sd in (("bid", -1), ("ask", 1)):
            if None in idx:
                continue
            new, old = side(idx[0], s), [side(i, s) for i in idx[1:]]
            w = old[0][1]
            if all(ok and big and wk == w for ok, wk, big in old) and new[0] and not (new[1] == w and new[2]) and sd * (lt - w) > 0:
                hits.append(("long" if sd > 0 else "short", (lt + sd) * TICK, (w - 4 * sd) * TICK))
    return hits[0] if len(hits) == 1 else None


@pytest.mark.parametrize("cls", [Bounce, Break])
@pytest.mark.parametrize("tf", ["1", "5"])
def test_random_days_match_the_oracle_at_every_decision(cls, tf):
    fired, reach = 0, set()
    for seed in range(40):
        rows, prints, drop = random_day(seed)
        st = cls({"tf": tf, "max_tr": 20})
        f = table(rows, drop)
        res = S.run_session(st, tape(prints), features=f)
        assert res.skip is None and res.both_sides is False and st.seen
        assert all(t % (int(tf) * MIN) == 0 and T0 < t < at(84) for t, _ in st.seen)   # tf-bar closes, never the last 5 min
        calls = {c["t"]: (c["side"], c["px"], c["struct"]) for c in st.calls}
        last_at = dict(st.seen)
        for c in st.calls:                                     # every request rests; a limit is never beyond the last print
            gap = round((last_at[c["t"]] - c["px"]) * (1 if c["side"] == "long" else -1) / TICK)
            assert c["placed"] and (gap == -1 if c["kind"] == "stop" else 0 <= gap <= st.p["near"] - 1)
            reach.add((c["kind"], gap))
        assert len(calls) == len(st.calls) and all(c["ttl"] == 1 for c in st.calls)    # at most one request per decision
        kind = "limit" if cls is Bounce else "stop"
        for now, last in st.seen:
            assert calls.get(now) == oracle(f, kind, now, last, st.p), (seed, (now - T0) // MIN)
        fired += len(calls)
    assert fired >= (40 if tf == "1" else 12)                  # the comparison is not vacuous
    assert reach == ({("limit", 0), ("limit", 1)} if cls is Bounce else {("stop", -1)})        # B4: the 1- AND the 2-tick case


ENTRY = ("side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ns")


def upto(st, res, log, cut_ns):
    """Everything already settled at `cut_ns`: the decisions, the walls the family read and its order requests at
    t <= cut, the trades closed before it (every field) and the entry side of the trades opened before it."""
    return ([x for x in st.seen if x[0] <= cut_ns], [c for c in st.calls if c["t"] <= cut_ns],
            [r for r in log if r[0] <= cut_ns], [t for t in res.trades if t["exit_ns"] < cut_ns],
            [tuple(t[k] for k in ENTRY) for t in res.trades if t["entry_ns"] < cut_ns])


def peek_wall(ctx, side, m, back=0):
    """A BROKEN families.walls.wall: reads the table directly, ONE ROW AHEAD of ctx.feat (the minute still forming)."""
    f = ctx._feat
    k = f.n_usable(ctx.now_ns) - back
    if k < 0 or k >= len(f.usable_ns) or not f.cols["book_ok"][k]:
        return None
    px, dist, sz, med = (float(f.cols[c][k]) for c in W.COLS[side])
    if not all(math.isfinite(v) for v in (px, dist, sz, med)) or med <= 0:
        return None
    return round(px / ctx.tick) + (-1 if side == "bid" else 1) * round(dist), sz >= m * med


def logged_run(cls, tf, prints, rows, drop, monkeypatch, fn):
    """One session with families.walls.wall = `fn`, every wall it returns logged: -> (strategy, result, log)."""
    log = []

    def wall(ctx, side, m, back=0):
        r = fn(ctx, side, m, back)
        log.append((ctx.now_ns, side, back, r))
        return r
    monkeypatch.setattr(W, "wall", wall)
    st = cls({"tf": tf, "max_tr": 20})
    res = S.run_session(st, tape(prints), features=table(rows, drop))
    assert res.skip is None and st.seen and log
    return st, res, log


def cut_violations(cls, tf, monkeypatch, fn=W.wall, cuts=(7, 23, 40, 58, 71), seeds=6):
    """(comparisons, violations, runs whose requests differ somewhere): for `seeds` random days x every cut, each row
    that becomes usable AFTER the cut and each print AT / AFTER it is replaced by another day's."""
    n = bad = differs = 0
    for seed in range(seeds):
        rows, prints, drop = random_day(seed)
        o_rows, o_prints, _ = random_day(100 + seed)
        a = logged_run(cls, tf, prints, rows, drop, monkeypatch, fn)
        for cut in cuts:                                       # rows / minutes < cut are the day's own
            b = logged_run(cls, tf, {m: (prints if m < cut else o_prints)[m] for m in MINUTES},
                           {m: (rows if m < cut else o_rows)[m] for m in MINUTES}, drop, monkeypatch, fn)
            n += 1
            bad += upto(*a, at(cut - 1)) != upto(*b, at(cut - 1))
            differs += a[0].calls != b[0].calls
    return n, bad, differs


@pytest.mark.parametrize("cls", [Bounce, Break])
@pytest.mark.parametrize("tf", ["1", "5"])
def test_nothing_after_a_cut_can_change_what_was_settled_before_it(cls, tf, monkeypatch):
    """Synthetic days, tape AND feature rows replaced after the cut: decisions, walls read, order requests, closed
    trades and entries up to the cut are identical (and the replacement does matter after it). Real days:
    tests/test_fam_walls_real.py."""
    n, bad, differs = cut_violations(cls, tf, monkeypatch)
    assert n == 30 and bad == 0 and differs >= 10


@pytest.mark.parametrize("cls", [Bounce, Break])
def test_the_cut_comparison_catches_a_family_that_reads_one_row_ahead(cls, monkeypatch):
    """Power of the test above: the same comparison FAILS for a mutant that peeks at the row still forming."""
    n, bad, _ = cut_violations(cls, "1", monkeypatch, fn=peek_wall, cuts=range(5, 80), seeds=3)
    assert n == 225 and bad >= (100 if cls is Bounce else 30)


def test_tf5_late_close_decides_on_the_rows_usable_then_and_on_nothing_later():
    """Inherited from the Template: when the last minute of a tf bucket has no print (09:34 here), the bucket is closed
    -- and the family asked -- at the end of the next minute that has one: 09:36:00, off the 5-minute grid. The family
    reads the rows usable at THAT instant (row 09:35 is the fresh one) and nothing later."""
    hole = {4: []}
    st, _ = go(Bounce, {5: bid_wall()}, {**hole, 5: [100.50, 100.25]}, {"tf": "5"})
    assert at(5) in dict(st.seen) and at(4) not in dict(st.seen) and at(5) % (5 * MIN) != 0
    assert sig(st) == [(at(5), "long", 100.00, 98.75, True)]
    assert sig(go(Bounce, {4: bid_wall()}, {**hole, 5: [100.50, 100.25]}, {"tf": "5"})[0]) == []       # row 09:34 is stale
    st, _ = go(Bounce, {6: bid_wall()}, {**hole, 5: [100.50, 100.25], 6: [100.25]}, {"tf": "5"})
    assert [c for c in st.calls if c["t"] <= at(5)] == []                                              # row 09:36: not yet
    st, _ = go(Break, {3: STAND, 4: STAND, 5: GONE}, {**hole, 5: [100.25, 99.75]}, {"tf": "5"})
    assert sig(st) == [(at(5), "short", 99.50, 101.00, True)]
    st, _ = go(Break, {3: STAND, 4: STAND, 5: STAND, 6: GONE}, {**hole, 5: [100.25, 99.75], 6: [99.75]}, {"tf": "5"})
    assert [c for c in st.calls if c["t"] <= at(5)] == []                                              # gone only at 09:37
    st, _ = go(Bounce, {10: bid_wall()}, {9: [100.50, 100.25], 10: [100.25]}, {"tf": "5"})             # on-grid close 09:40
    assert at(9) in dict(st.seen) and [c for c in st.calls if c["t"] <= at(9)] == []


@pytest.mark.parametrize("cls", [Bounce, Break])
def test_every_feature_read_is_a_row_already_usable_at_the_decision(cls, monkeypatch):
    """Independent of the guard inside ctx.feat: each read is checked against the table's own usable_ns."""
    reads, real = [], S.Ctx.feat

    def spy(self, name, back=0, default=None):
        f, now = self._feat, self._s.now
        k = int(np.searchsorted(f.usable_ns, now, side="right")) - 1 - back
        assert isinstance(back, int) and back >= 0 and (k < 0 or f.usable_ns[k] <= now)
        v = real(self, name, back, default)
        assert k < 0 or v == f.cols[name][k] or v != v
        reads.append((now, name, back))
        return v

    def window(self, name, n=None):
        raise AssertionError("the wall families read single rows only")
    monkeypatch.setattr(S.Ctx, "feat", spy)
    monkeypatch.setattr(S.Ctx, "feat_window", window)
    for seed in range(4):
        rows, prints, drop = random_day(seed)
        st = cls({"max_tr": 20})
        assert S.run_session(st, tape(prints), features=table(rows, drop)).skip is None and st.calls
    assert len(reads) > 500 and {n for _, n, _ in reads} <= set(W.FEATURES)
    assert max(b for _, _, b in reads) == (0 if cls is Bounce else 2)
    assert all(now % MIN == 0 for now, _, _ in reads)          # decisions at minute boundaries only
