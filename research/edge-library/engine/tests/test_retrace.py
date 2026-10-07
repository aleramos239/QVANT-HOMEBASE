"""The open_retrace family (engine/families/retrace.py): fade the opening move when it gives back half.

(i) the registry entry and the block; (ii) the rule on small synthetic bars -- the first candle's side, the level of the give-back,
stop at the extreme and target at the open, a stale level re-placed, nothing rests while price is already through the level,
a doji and a one-minute-late candle trade nothing, one trade a day; (iii) NO LOOK-AHEAD: garbage after a cut changes no decision
before it; (iv) identical trades at 1 and 8 workers on real BUILD days, the hold checks at zero. The real-day test asserts counts
only: no net, win rate or profit factor is printed."""
import datetime as dt
import hashlib
import json
import os

import numpy as np
import pytest

import families
import l2sim as S
import run_menus as RM
from families import blocks as B
from families import retrace as F

D = dt.date(2023, 3, 14)                            # a BUILD weekday (EDT), not a roll day
DAILY = [{"date": "2023-03-13", "h": 15100.0, "l": 14900.0, "c": 15000.0, "contract": "NQM3"}]
DAYS = list(RM.SMOKE_DAYS)
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
BASE = {"tf": "1", "sess": "nyam", "hold_to": "day"}
LAT = 85 * 10**6                                    # the engine's order delay, ns
OPEN_I = 30                                         # the 09:30 bar is the 31st minute of a tape that starts at 09:00


def real_days():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def ns(hms, d=D):
    return S.et_ns(d, hms)


def hms(t_ns):
    return dt.datetime.fromtimestamp(t_ns / 1e9, S.ET).strftime("%H:%M:%S")


def minute_tape(bars, start="09:00"):
    """One (o, h, l, c) per minute from `start` -> 4 prints per minute at :00 (o), :15, :30 (the low then the high for an
    up bar, the high then the low for a down bar) and :45 (c), 10 contracts each."""
    ts, px = [], []
    t0 = ns(start)
    for i, (o, h, l, c) in enumerate(bars):
        mid = (l, h) if c >= o else (h, l)
        for k, p in enumerate((o, mid[0], mid[1], c)):
            ts.append(t0 + i * 60 * S.NS + k * 15 * S.NS)
            px.append(p)
    return S.Tape("NQ", D, "NQM3", np.array(ts, np.int64), np.array(px, float), np.full(len(ts), 10, np.int64))


def day(script, tail=120):
    """30 quiet minutes before the open, then `script` (one (o, h, l, c) a minute from 09:30), then quiet minutes at its last close."""
    last = script[-1][3]
    return [(15000.0, 15001.0, 14999.0, 15000.0)] * OPEN_I + list(script) + [(last, last + 1.0, last - 1.0, last)] * tail


def mirror(bars, px=15000.0):
    return [(2 * px - o, 2 * px - l, 2 * px - h, 2 * px - c) for o, h, l, c in bars]


# An up day: the first candle 15000 -> 15020 (09:30-09:34), the move runs on to 15040 (09:35), gives half of it back (09:36), then
# the rest to the open (09:37). The fall prints 15019.75: the first print through the 15020 stop.
UP = [(15000.0, 15006.0, 15000.0, 15006.0), (15006.0, 15012.0, 15006.0, 15012.0), (15012.0, 15016.0, 15012.0, 15016.0),
      (15016.0, 15018.0, 15016.0, 15018.0), (15018.0, 15020.0, 15018.0, 15020.0),
      (15020.0, 15040.0, 15020.0, 15040.0),
      (15040.0, 15040.0, 15019.75, 15019.75),
      (15019.75, 15019.75, 15000.0, 15000.0)]


def spy(cls):
    """A subclass that logs every resting order placed: (decision ns, side, price, struct, target) -- one row per _arm that placed one."""
    class Spy(cls):
        log: list = []

        def _arm(self, ctx, legs, **kw):
            os_ = super()._arm(ctx, legs, **kw)
            if os_:
                type(self).log.append((ctx.now_ns, *legs[0]))
            return os_
    Spy.log = []
    return Spy


def play(params, bars, cls=F.OpenRetrace):
    sp = spy(cls)
    st = sp({**BASE, **params})
    res = S.run_session(st, minute_tape(bars), daily=list(DAILY), on_error="raise")
    return res.trades, list(sp.log)


def sig(trades):
    return hashlib.blake2b(json.dumps(trades, sort_keys=True, default=str).encode(), digest_size=12).hexdigest()


# ---- (i) the registry and the block ------------------------------------------------------------------------------------------

def test_the_registry_holds_open_retrace_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["open_retrace"]
    lib = families.library("open_retrace")
    assert cls is F.OpenRetrace and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5")
    assert lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"] and lib["mirror"] is None and lib["complexity"] == 6
    assert [v["level"] for v in lib["variants"]] == [0.4, 0.5, 0.6]
    d = cls.defaults()
    assert d["level"] == 0.5 and d["max_tr"] == 1 and d["stop_mode"] == "struct" and cls.schema()["level"] == ("float", 0.1, 0.9)
    assert issubclass(B.WRAPPED["open_retrace"], F.OpenRetrace) and B.BASES["open_retrace"][0] is F.OpenRetrace
    assert cls({"tf": "5", "sess": "nyam", "hold_to": "day"}).sessions() == ["nyam"]
    for s in RM.DAY_PASSES:                           # it trades in the New York morning only
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == (["nyam"] if s == "nyam" else [])


# ---- (ii) the rule -----------------------------------------------------------------------------------------------------------

def test_an_up_day_is_sold_at_half_the_move_stop_at_the_high_target_at_the_open():
    tr, log = play({}, day(UP))
    assert len(tr) == 1
    t = tr[0]
    assert t["side"] == "short" and abs(t["entry_price"] - 15020.0) <= 0.5       # the first print through, one tick of slippage
    assert abs(t["sl"] - 15040.0) <= 0.5 and abs(t["tp"] - 15000.0) <= 0.5       # the high of the move / the 09:30 open (the bracket follows the fill by its slippage)
    assert t["exit_reason"] == "tp" and abs(t["exit_price"] - 15000.0) <= 0.5
    assert hms(t["entry_ms"] * 10**6) == "09:36:30"                           # the 09:36 bar's first print through 15020
    # the order rested first at the 09:35 level (15010 = half of 15000..15020), then moved to 15020 at the next close
    assert [(hms(t_), side, px, st_, tp_) for t_, side, px, st_, tp_ in log] == [
        ("09:35:00", "short", 15010.0, 15020.0, 15000.0), ("09:36:00", "short", 15020.0, 15040.0, 15000.0)]


def test_a_down_day_is_bought_the_mirror_way():
    tr, log = play({}, mirror(day(UP)))
    assert len(tr) == 1 and tr[0]["side"] == "long" and abs(tr[0]["entry_price"] - 14980.0) <= 0.5
    assert abs(tr[0]["sl"] - 14960.0) <= 1.0 and abs(tr[0]["tp"] - 15000.0) <= 1.0 and tr[0]["exit_reason"] == "tp"


def test_the_level_is_the_setting_and_the_reward_follows_it():
    for lv, px in ((0.4, 15024.0), (0.6, 15016.0)):                           # the move is 40: 15040 - 0.4 x 40, 15040 - 0.6 x 40
        bars = UP[:6] + [(15040.0, 15040.0, px - 0.25, px - 0.25), (px - 0.25, px - 0.25, 15000.0, 15000.0)]
        tr, log = play({"level": lv}, day(bars))
        assert len(tr) == 1 and abs(tr[0]["entry_price"] - px) <= 0.5 and abs(tr[0]["sl"] - 15040.0) <= 1.0 and abs(tr[0]["tp"] - 15000.0) <= 1.0


def test_the_stop_at_the_extreme_is_hit_when_the_move_goes_on():
    bars = day(UP[:7] + [(15019.75, 15040.25, 15019.75, 15040.25)])             # it fell to 15019.75 (in at 15020), then rips on through 15040
    tr, _ = play({}, bars)
    assert len(tr) == 1 and tr[0]["exit_reason"] == "sl" and abs(tr[0]["exit_price"] - 15040.0) <= 1.0


def test_a_new_extreme_moves_the_level_and_the_old_order_is_cancelled():
    ups = UP[:5] + [(15020.0, 15030.0, 15020.0, 15030.0), (15030.0, 15040.0, 15030.0, 15040.0), (15040.0, 15040.0, 15019.75, 15019.75)]
    tr, log = play({}, day(ups))
    assert [px for _, _, px, _, _ in log] == [15010.0, 15015.0, 15020.0]       # 09:35, 09:36, 09:37: a level for every new extreme
    assert len(tr) == 1 and abs(tr[0]["entry_price"] - 15020.0) <= 0.5 and abs(tr[0]["sl"] - 15040.0) <= 0.5


def test_nothing_rests_while_price_is_already_through_the_level():
    # the first candle runs to 15020 and comes back to close at 15004: price is below its half (15010) -> no order
    first = UP[:4] + [(15018.0, 15020.0, 15003.0, 15004.0)]
    tr, log = play({}, day(first))
    assert log == [] and tr == []
    # a new high above puts price over the new level again: an order rests, and falls through to fill
    more = first + [(15004.0, 15040.0, 15004.0, 15040.0), (15040.0, 15040.0, 15016.0, 15016.0)]      # (gaps through the stop)
    tr, log = play({}, day(more))
    assert [hms(t) for t, *_ in log] == ["09:36:00"] and len(tr) == 1 and 15015.0 <= tr[0]["entry_price"] <= 15020.0


def test_a_doji_candle_has_no_side_and_no_trade():
    doji = UP[:4] + [(15018.0, 15030.0, 15000.0, 15000.0)]
    assert play({}, day(doji + UP[5:])) == ([], [])


def test_nothing_is_decided_before_the_first_candle_is_whole():
    tr, log = play({}, day(UP))
    assert min(t for t, *_ in log) == ns("09:35:00")


def test_one_trade_a_day():
    again = UP + [(15000.0, 15060.0, 15000.0, 15060.0), (15060.0, 15060.0, 15030.0, 15030.0), (15030.0, 15030.0, 15000.0, 15000.0)]
    tr, log = play({}, day(again))
    assert len(tr) == 1


def test_the_table_cell_does_not_change_the_structure():
    a, _ = play({}, day(UP))
    b, _ = play({"stop_mode": "pts", "stop_val": 5.0, "tgt_r": 3.0}, day(UP))
    assert [(t["entry_price"], t["sl"], t["tp"]) for t in a] == [(t["entry_price"], t["sl"], t["tp"]) for t in b] and a


def test_the_five_minute_bar_reads_the_same_candle():
    tr, log = play({"tf": "5"}, day(UP))
    assert all((t - ns("00:00")) % (300 * S.NS) == 0 for t, *_ in log)
    assert all(side == "short" for _, side, *_ in log)


# ---- (iii) no look-ahead --------------------------------------------------------------------------------------------------------

def walk(seed=3, n=390):
    """A random walk of minute bars from 09:00 whose 09:30 candle has a side and whose moves give back half now and then."""
    rng = np.random.default_rng(seed)
    bars, c = [], 15000.0
    for _ in range(n):
        o = c
        c = o + float(rng.choice([-12, -6, -2, -1, 0, 1, 2, 6, 12])) * 0.25 * 4
        bars.append((o, max(o, c) + 0.25 * int(rng.integers(0, 4)), min(o, c) - 0.25 * int(rng.integers(0, 4)), c))
    return bars


LA = [{"level": lv, "tf": tf} for lv in (0.4, 0.5, 0.6) for tf in ("1", "5")]


def test_garbage_after_a_cut_changes_no_decision_before_it():
    n_dec = n_tr = 0
    for seed in range(3, 9):
        bars = walk(seed)
        tape = minute_tape(bars)
        real = [play(p, bars) for p in LA]
        rng = np.random.default_rng(7)
        for cut in ("09:47", "10:00", "10:31", "10:50"):
            c = ns(cut)
            k = int(np.searchsorted(tape.ts, c))
            px = tape.px.copy()
            px[k:] = np.round(tape.px[k:] * rng.uniform(0.99, 1.01, len(px) - k) / 0.25) * 0.25
            for p, (tr, log) in zip(LA, real):
                sp = spy(F.OpenRetrace)
                st = sp({**BASE, **p})
                res = S.run_session(st, S.Tape("NQ", D, "NQM3", tape.ts, px, tape.size), daily=list(DAILY), on_error="raise")
                assert [x for x in log if x[0] <= c] == [x for x in sp.log if x[0] <= c], (seed, cut, p)
                assert [t for t in tr if t["exit_ms"] < c // 10**6] == [t for t in res.trades if t["exit_ms"] < c // 10**6], (seed, cut, p)
                n_dec += len([x for x in log if x[0] <= c])
        n_tr += sum(len(tr) for tr, _ in real)
    assert n_dec > 20 and n_tr > 5


def test_an_entry_is_never_before_its_decision_plus_the_order_delay():
    n = 0
    for seed in range(3, 9):
        for p in LA:
            tr, log = play(p, walk(seed))
            step = int(p["tf"]) * 60 * S.NS
            assert all((t - ns("00:00")) % step == 0 for t, *_ in log)       # decisions at tf closes only
            for t in tr:
                e = t["entry_ms"] * 10**6
                assert e >= max(x for x, *_ in log if x <= e) + LAT
                n += 1
    assert n > 5


# ---- (iv) real BUILD days: counts and fingerprints only -----------------------------------------------------------------------

def real_specs():
    return [(F.OpenRetrace, {**BASE, "tf": tf, "level": lv}) for tf in ("1", "5") for lv in (0.4, 0.5, 0.6)]


def test_identical_trades_at_1_and_8_workers_and_the_hold_checks_at_zero():
    real_days()
    specs = real_specs()
    a = S.run_many(specs, days=DAYS, workers=1)
    b = S.run_many(specs, days=DAYS, workers=W)
    n = 0
    for (cls, p), x, y in zip(specs, a, b):
        assert sig(x["trades"]) == sig(y["trades"]), p
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["both_sides_sessions"] == 0
        per = {}
        for t in x["trades"]:
            assert S.session_of(t["entry_ms"]) == "nyam", p                  # entered inside its own session
            assert (t["side"] == "short") == (t["sl"] > t["entry_price"]) and (t["tp"] < t["entry_price"]) == (t["side"] == "short")
            per[t["date"]] = per.get(t["date"], 0) + 1
        assert max(per.values(), default=0) <= 1
        n += len(x["trades"])
    assert n > 0
    assert RM.hold_checks(a, "NQ") == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
