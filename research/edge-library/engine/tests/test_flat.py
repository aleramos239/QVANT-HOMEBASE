"""The flat time of its own (families/_flat.py: `w_flat` on every wrapped family and on the control RandomFlat).

THE RULE UNDER TEST (the module docstring holds it in full)
  w_flat   "HH:MM" on the Globex-day clock; under hold_to 'day' the instance's flatten time is the EARLIER of w_flat and the day's own
           (15:58, 13:13 on a half day): the position is closed at market at w_flat (exit reason 'time'), working entries are cancelled 5 minutes
           before it, no entry is placed in those 5 minutes or after. OFF by default.
Checks: (i) the mixin is on every wrapped family and OFF = trade for trade a class without it; (ii) the flatten, the no-entry lead and the
cancel on exact synthetic days; (iii) an evening instance held past midnight; (iv) the control: RandomFlat off = l2ref.Random, on = the same
entries cut at the flat time; (v) the refusals; (vi) real BUILD days: same entries, exits cut at the flat time. No net or win rate is read."""
import datetime as dt

import pytest

import families
import l2ref
import l2sim as S
from families import _flat as FL
from families import _flex as FM
from families import blocks as B
from test_blocks import D, DAILY, days_of, minute_tape, rand_bars, real_days
from test_orb830 import BASE, CBASE, FILL, HI, LO, PX, breaks_up, candle, day, got, hold, run, sec, stay

families.load()
FL.apply()                                          # idempotent: the registry applies it too once it is wired in
ORB, CANDLE, WBRK = B.WRAPPED["orb_close"], B.WRAPPED["open_candle"], B.WRAPPED["win_break"]
MS0 = S.et_ns(D, "00:00") // 1_000_000
BREAK = [(sec(9, 37, FILL), "long", HI + 4, LO, None)]          # day(breaks_up("09:36")): the break bar closes 09:37:00, the fill is :15 later


def ends(res):
    return [((t["exit_ms"] - MS0) // 1000, t["exit_reason"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


# ---- (i) the mixin is on every wrapped family and off = a class without it -------------------------------------------------------------------------
def test_every_wrapped_family_carries_the_flat_time_and_it_is_off_by_default():
    assert B.WRAPPED
    for n, c in B.WRAPPED.items():
        assert FL.FlatMods in c.__mro__, n
        assert c.defaults()["w_flat"] == "", n
        assert c.schema()["w_flat"] == ("str",), n


def test_apply_is_idempotent_and_the_off_switch_exists(monkeypatch):
    before = [c.__bases__ for c in B.WRAPPED.values()]
    assert FL.apply() == 0
    assert [c.__bases__ for c in B.WRAPPED.values()] == before
    monkeypatch.setenv("HOMEBASE_FLAT", "0")
    assert FL.apply() == 0


@pytest.mark.parametrize("name", sorted(B.WRAPPED))
def test_off_is_trade_for_trade_a_class_without_it(name):
    """A fresh B._wrap (no layer, no flat time) and the patched class give the same inputs (old keys) and the same trades on a seeded day."""
    cls = B.WRAPPED[name]
    fresh = B._wrap(name, B.BASES[name][0])
    assert FL.FlatMods not in fresh.__mro__
    tape = minute_tape(rand_bars(960, 11), "00:00")
    ran = {}
    for tf in ("5", "1"):                                                                 # (a family of 1-minute bars only refuses 5: the same refusal from both)
        ran[tf] = 0
        for s in ("london", "pre", "nyam"):
            out = []
            for c in (cls, fresh):
                try:
                    st = c({"hold_to": "day", "tf": tf, "sess": s})
                    st.ROLLS = frozenset()
                    r = S.run_session(st, tape, costs=S.Costs(**getattr(c, "SCREEN_RUN", {})), daily=list(DAILY), on_error="raise")
                    out.append(({x: v for x, v in st.p.items() if x not in FM.KEYS + FL.KEYS}, r.trades))
                except Exception as e:                                                   # noqa: BLE001 - the same refusal from both is a match
                    out.append((type(e).__name__, str(e)))
            assert out[0] == out[1], (name, tf, s)
            ran[tf] += isinstance(out[0][0], dict)
    assert max(ran.values()) == 3, (name, ran)


# ---- (ii) the flatten, the lead and the cancel on exact days ----------------------------------------------------------------------------------------
def test_the_position_is_closed_at_the_flat_time_and_at_1558_without_it():
    bars = day(breaks_up("09:36"))                                                        # long at 09:37:15, then quiet at the break's close all day
    plain = run(ORB, BASE, {}, bars)[1]
    assert got(plain) == BREAK and ends(plain) == [(sec(15, 58), "time")]
    cut = run(ORB, BASE, {"w_flat": "10:30"}, bars)[1]
    assert got(cut) == BREAK and ends(cut) == [(sec(10, 30), "time")]                     # the same entry, closed at 10:30:00
    assert cut.trades[0]["exit_price"] == PX - 0.25                                       # the print of 10:30:00 (the day is back at 15000), one tick of slippage on the sell


def test_a_trade_that_ends_before_the_flat_time_is_untouched():
    bars = day({**breaks_up("09:36"), "09:50": (HI + 4, HI + 60, HI + 4, HI + 50, 40)})   # the 1R target (40 points over the fill) trades at 09:50
    base = {**BASE, "tgt_r": 1.0}
    a, b = run(ORB, base, {}, bars)[1], run(ORB, base, {"w_flat": "10:30"}, bars)[1]
    assert ends(a) == ends(b) and ends(a)[0][1] == "tp" and ends(a)[0][0] < sec(9, 51)
    assert a.trades == b.trades


def test_no_entry_in_the_five_minutes_before_the_flat_time_or_after_it():
    bars = day(breaks_up("10:26"))                                                        # the break is decided at 10:27:00
    assert got(run(ORB, BASE, {}, bars)[1]) == [(sec(10, 27, FILL), "long", HI + 4, LO, None)]
    assert got(run(ORB, BASE, {"w_flat": "10:33"}, bars)[1])                              # 10:27 is before 10:28: entered, flat at 10:33
    assert ends(run(ORB, BASE, {"w_flat": "10:33"}, bars)[1]) == [(sec(10, 33), "time")]
    assert got(run(ORB, BASE, {"w_flat": "10:32"}, bars)[1]) == []                        # 10:27 is inside the last 5 minutes (from 10:27)
    assert got(run(ORB, BASE, {"w_flat": "10:20"}, bars)[1]) == []                        # after the flat time: nothing


def test_a_working_limit_is_cancelled_five_minutes_before_the_flat_time():
    edits = {**breaks_up("09:36"), **stay(HI + 4, "09:38", "10:30"), "10:10": (HI + 4, HI + 5, HI - 2, HI + 4, 40)}   # price holds over the edge; the retest (the limit at HI) is at 10:10
    lim = {"entry": "limit", "wait": "0"}
    assert len(run(ORB, BASE, lim, day(edits))[1].trades) == 1                            # filled at the retest
    assert len(run(ORB, BASE, {**lim, "w_flat": "10:20"}, day(edits))[1].trades) == 1     # the limit lives to 10:15: filled, flat 10:20
    assert ends(run(ORB, BASE, {**lim, "w_flat": "10:20"}, day(edits))[1])[0] == (sec(10, 20), "time")
    assert run(ORB, BASE, {**lim, "w_flat": "10:14"}, day(edits))[1].trades == []         # cancelled at 10:09: the retest finds no order


def test_the_flat_time_is_listed_among_the_instance_times_and_only_when_set():
    assert "10:30:00" not in ORB(BASE).times() and "10:25:00" not in ORB(BASE).times()
    ts = ORB({**BASE, "w_flat": "10:30"}).times()
    assert "10:30:00" in ts and "10:25:00" in ts and ts == sorted(ts)
    assert set(ORB(BASE).times()) < set(ts)


# ---- (iii) an evening instance, held past midnight ----------------------------------------------------------------------------------------------------
def _eve(params):
    """The 20:00 candle of the evening BEFORE the trade date (green, +10), quiet at its close all night and the next day."""
    n = 22 * 60                                                                           # 18:00 of D-1 .. 16:00 of D
    bars = [(PX, PX + 3.0, PX - 3.0, PX, 40)] * n
    k = (20 * 3600 - 18 * 3600) // 60
    for t, b in candle(PX, PX + 10.0, PX + 12.0, PX - 2.0, t0="20:00").items():
        bars[(S._sec(t) - 18 * 3600) // 60] = b
    for i in range(k + 5, n):
        bars[i] = hold(PX + 10.0)
    tp = minute_tape(bars, "18:00", d=D - dt.timedelta(days=1))
    tape = S.Tape(tp.root, D, tp.contract, tp.ts, tp.px, tp.size)
    st = CANDLE({**CBASE, "sess": "eve", "start": "2000", **params})
    st.ROLLS = frozenset()
    return S.run_session(st, tape, costs=S.Costs(**getattr(CANDLE, "SCREEN_RUN", {})), daily=list(DAILY), on_error="raise", window=st.eve_window, segment="eve")


def test_an_evening_trade_is_flat_at_0155_of_the_trade_date_or_at_2355_of_the_evening():
    entry = [(sec(20, 5, FILL) - 86400, "long", PX + 10.0, PX - 2.0, None)]
    plain = _eve({})
    assert got(plain) == entry and ends(plain) == [(sec(15, 58), "time")]                 # held to 15:58 of the trade date
    night = _eve({"w_flat": "01:55"})
    assert got(night) == entry and ends(night) == [(sec(1, 55), "time")]                  # past midnight, flat at 01:55
    late = _eve({"w_flat": "23:55"})
    assert got(late) == entry and ends(late) == [(sec(23, 55) - 86400, "time")]           # an evening flat time: the same evening
    assert _eve({"w_flat": "20:08"}).trades == []                                          # decided at 20:05, inside the last 5 minutes before 20:08


# ---- (iv) the control ---------------------------------------------------------------------------------------------------------------------------------
RND = {"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": 1.0, "p_entry": 0.5, "seed": 3, "max_tr": 3}


def _rnd(cls, params, seed=11):
    st = cls({**RND, **params})
    st.ROLLS = frozenset()
    return S.run_session(st, minute_tape(rand_bars(960, seed), "00:00"), daily=list(DAILY), on_error="raise")


def test_the_control_off_is_the_random_control_and_on_is_cut_at_the_flat_time():
    assert issubclass(FL.RandomFlat, l2ref.Random) and FL.RandomFlat.defaults()["w_flat"] == ""
    for seed in (11, 12, 13):
        plain, off = _rnd(l2ref.Random, {}, seed), _rnd(FL.RandomFlat, {}, seed)
        assert plain.trades and plain.trades == off.trades                               # off: the control itself
        cut = _rnd(FL.RandomFlat, {"w_flat": "10:15"}, seed)
        lim = MS0 + sec(10, 15) * 1000
        assert cut.trades and all(t["exit_ms"] <= lim and t["entry_ms"] < lim - 300_000 for t in cut.trades)
        first, same = plain.trades[0], cut.trades[0]                                      # the same stream: the first entry is the same one
        assert (first["entry_ms"], first["side"], first["entry_price"]) == (same["entry_ms"], same["side"], same["entry_price"])
        if first["exit_ms"] < lim:
            assert first == same                                                          # a trade that ended before the flat time is untouched
        else:
            assert (same["exit_ms"], same["exit_reason"]) == (lim, "time")


# ---- (v) the refusals -------------------------------------------------------------------------------------------------------------------------------------
def test_flat_times_that_cannot_work_are_refused_when_the_instance_is_built():
    for bad in ("25:00", "17:30", "soon"):                                                # not a clock time; the 17:00-18:00 break of the Globex day
        with pytest.raises(ValueError):
            ORB({**BASE, "w_flat": bad})
    with pytest.raises(ValueError):
        ORB({**BASE, "w_flat": "15:58"})                                                  # not before the day's own flatten time
    with pytest.raises(ValueError):
        ORB({**BASE, "w_flat": "16:30"})
    with pytest.raises(ValueError, match="hold_to 'day'"):                               # hold_to session is flat at each session end already:
        run(ORB, {**BASE, "hold_to": "session"}, {"w_flat": "10:30"}, day(breaks_up("09:36")))   # refused when the session is run, not silently ignored
    assert ORB({**BASE, "hold_to": "session", "w_flat": "10:30"})                         # (a card's check builds the class with the default hold)
    with pytest.raises(ValueError):
        ORB({**BASE, "w_flat": "23:55"})                                                  # an evening time, a New York instance
    with pytest.raises(ValueError):
        ORB({**BASE, "w_flat": "09:35"})                                                  # no room: the session starts 09:30
    with pytest.raises(ValueError):
        ORB({**BASE, "w_flat": "09:00"})                                                  # before the session
    assert ORB({**BASE, "w_flat": "09:36"})                                               # 09:31 is after the start: allowed
    assert ORB({**BASE, "w_flat": ""}) and ORB({**BASE, "w_flat": "  "})


# ---- (vi) real build days ---------------------------------------------------------------------------------------------------------------------------------
BIG = {"hold_to": "day", "stop_mode": "pts", "stop_val": 400.0, "tgt_r": 0.0}        # a stop and no target that a day rarely reaches: held to the flat time


def _real(cls, params, root="NQ", n=6, workers=1):
    real_days()
    days = days_of(root, n)
    out = S.run_many([(cls, {**BIG, **params})], days=days, root=root, workers=workers, **dict(getattr(cls, "SCREEN_RUN", {})))
    return days, out[0]


@pytest.mark.parametrize("root", ["NQ", "ES"])
def test_real_build_days_same_entries_exits_cut_at_the_flat_time_and_the_same_at_1_and_4_workers(root):
    p = {"tf": "5", "sess": "london", "r_start": "03:00", "r_end": "03:15"}
    _, plain = _real(WBRK, p, root=root)
    _, cut = _real(WBRK, {**p, "w_flat": "09:25"}, root=root)
    _, cut4 = _real(WBRK, {**p, "w_flat": "09:25"}, root=root, workers=4)
    assert plain["trades"] and cut["trades"] == cut4["trades"]
    a = {t["date"]: t for t in plain["trades"]}
    b = {t["date"]: t for t in cut["trades"]}
    assert set(a) == set(b)                                                               # the London entries are hours before 09:20: every one is kept
    held = 0
    for d, t in b.items():
        o = a[d]
        assert (t["entry_ms"], t["side"], t["entry_price"]) == (o["entry_ms"], o["side"], o["entry_price"])
        lim = int(dt.datetime.fromisoformat(d).replace(tzinfo=S.ET).timestamp()) + sec(9, 25)
        if o["exit_ms"] // 1000 < lim:
            assert t == o                                                                 # ended before 09:25: the same trade
        else:
            held += 1
            assert t["exit_reason"] == "time" and lim <= t["exit_ms"] // 1000 <= lim + 60  # flat 09:25; a thin tape fills at its next print
    assert held                                                                           # the cut was exercised
