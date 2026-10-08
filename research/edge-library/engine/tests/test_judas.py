"""The judas family (engine/families/retrace.py, v2 of open_retrace): the first side to move thrust x the daily ATR from the 09:30 open,
half of it given back within cap_min minutes of its extreme, traded against it by a resting stop order; stop and target in units of the
move. (i) the registry; (ii) the rule on synthetic bars; (iii) no look-ahead; (iv) real BUILD days: identical trades at 1 and 8 workers.
Real-day tests assert counts only: no net, win rate or profit factor is printed."""
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

D = dt.date(2023, 3, 14)
# 20 prior daily bars, each 300 points high-to-low around an unchanged close: every true range is 300, so ATR14 = 300 and thrust 0.25 = 75 points
DAILY = [{"date": (D - dt.timedelta(days=30 - i)).isoformat(), "h": 15150.0, "l": 14850.0, "c": 15000.0, "contract": "NQM3"} for i in range(20)]
DAYS = list(RM.SMOKE_DAYS)
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
BASE = {"tf": "1", "sess": "nyam", "hold_to": "day"}
LAT = 85 * 10**6
OPEN_I = 30


def real_days():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def ns(hms, d=D):
    return S.et_ns(d, hms)


def hms(t_ns):
    return dt.datetime.fromtimestamp(t_ns / 1e9, S.ET).strftime("%H:%M:%S")


def minute_tape(bars, start="09:00"):
    ts, px = [], []
    t0 = ns(start)
    for i, (o, h, l, c) in enumerate(bars):
        mid = (l, h) if c >= o else (h, l)
        for k, p in enumerate((o, mid[0], mid[1], c)):
            ts.append(t0 + i * 60 * S.NS + k * 15 * S.NS)
            px.append(p)
    return S.Tape("NQ", D, "NQM3", np.array(ts, np.int64), np.array(px, float), np.full(len(ts), 10, np.int64))


def day(script, tail=150):
    last = script[-1][3]
    return [(15000.0, 15001.0, 14999.0, 15000.0)] * OPEN_I + list(script) + [(last, last + 1.0, last - 1.0, last)] * tail


def mirror(bars, px=15000.0):
    return [(2 * px - o, 2 * px - l, 2 * px - h, 2 * px - c) for o, h, l, c in bars]


def ramp(top, n=10, o=15000.0):
    """n one-minute up bars from o to top."""
    step = (top - o) / n
    return [(o + step * i, o + step * (i + 1), o + step * i, o + step * (i + 1)) for i in range(n)]


def flatbars(px, n):
    return [(px, px, px - 1.0, px)] * n


def fall(frm, to):
    return [(frm, frm, to, to)]


# A 100-point thrust in 10 minutes (09:30-09:39, the 75-point mark is crossed in the 8th), the extreme 15100 ends 09:40; half back = 15050
UP = ramp(15100.0) + fall(15100.0, 15049.75) + fall(15049.75, 15000.0)


def spy(cls):
    class Spy(cls):
        log: list = []

        def _arm(self, ctx, legs, **kw):
            os_ = super()._arm(ctx, legs, **kw)
            if os_:
                type(self).log.append((ctx.now_ns, *legs[0]))
            return os_
    Spy.log = []
    return Spy


def play(params, bars, daily=None):
    sp = spy(F.Judas)
    st = sp({**BASE, **params})
    res = S.run_session(st, minute_tape(bars), daily=list(DAILY if daily is None else daily), on_error="raise")
    return res.trades, list(sp.log)


def sig(trades):
    return hashlib.blake2b(json.dumps(trades, sort_keys=True, default=str).encode(), digest_size=12).hexdigest()


def test_the_registry_holds_judas_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["judas"]
    lib = families.library("judas")
    assert cls is F.Judas and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1",)
    assert lib["roots"] == ("NQ", "ES", "GC") and lib["complexity"] == 6
    assert [v["thrust"] for v in lib["variants"]] == [0.2, 0.25, 0.3]
    d = cls.defaults()
    assert (d["thrust"], d["stop_m"], d["tgt_m"], d["cap_min"], d["max_tr"]) == (0.25, 0.5, 0.5, 15, 1)
    assert issubclass(B.WRAPPED["judas"], F.Judas)
    assert [s for s in RM.DAY_PASSES if cls({"tf": "1", "sess": s, "hold_to": "day"}).sessions()] == ["nyam"]


def test_a_big_move_that_gives_half_back_is_faded_stop_at_the_extreme_target_at_the_open():
    tr, log = play({}, day(UP))
    assert len(tr) == 1
    t = tr[0]
    assert t["side"] == "short" and abs(t["entry_price"] - 15050.0) <= 0.5 and hms(t["entry_ms"] * 10**6) == "09:40:30"
    assert abs(t["sl"] - 15100.0) <= 0.5 and abs(t["tp"] - 15000.0) <= 0.5 and t["exit_reason"] == "tp"
    # the order moved up with the extreme: first placed when the 75 points were reached (09:38 close), then re-placed at every new extreme
    assert [px for _, _, px, _, _ in log] == [15040.0, 15045.0, 15050.0]


def test_a_down_move_is_bought_the_mirror_way():
    tr, _ = play({}, mirror(day(UP)))
    assert len(tr) == 1 and tr[0]["side"] == "long" and abs(tr[0]["entry_price"] - 14950.0) <= 0.5
    assert abs(tr[0]["sl"] - 14900.0) <= 0.5 and abs(tr[0]["tp"] - 15000.0) <= 0.5


def test_a_move_under_the_size_is_left_and_the_size_is_the_setting():
    small = ramp(15060.0) + fall(15060.0, 15029.75) + fall(15029.75, 15000.0)
    assert play({}, day(small)) == ([], [])
    assert len(play({"thrust": 0.2}, day(UP))[0]) == 1                          # 60 points: the 100-point move counts
    assert play({"thrust": 0.4}, day(UP)) == ([], [])                           # 120 points: it does not


def test_the_give_back_must_come_within_the_time_cap_of_the_extreme():
    slow = ramp(15100.0) + flatbars(15100.0, 20) + fall(15100.0, 15049.75)       # 20 quiet minutes, then it falls through half
    tr, log = play({}, day(slow))
    assert tr == []
    assert max(t for t, *_ in log) < ns("09:40:00") + 16 * 60 * S.NS            # nothing rests after the cap ran out
    tr, _ = play({"cap_min": 30}, day(slow))
    assert len(tr) == 1 and abs(tr[0]["entry_price"] - 15050.0) <= 0.5


def test_a_new_extreme_restarts_the_clock_and_moves_the_level():
    bars = ramp(15100.0) + flatbars(15100.0, 10) + [(15100.0, 15110.0, 15100.0, 15110.0)] + flatbars(15110.0, 11) + fall(15110.0, 15054.75)
    tr, _ = play({}, day(bars))                                                  # 09:51 extreme + 15 min = 10:06; the fall is at 10:02
    assert len(tr) == 1 and abs(tr[0]["entry_price"] - 15055.0) <= 0.5 and abs(tr[0]["sl"] - 15110.0) <= 0.5


def test_the_exits_are_in_units_of_the_move():
    (t,), _ = play({"stop_m": 1.0, "tgt_m": 1.0}, day(UP[:10] + fall(15100.0, 15049.75) + [(15049.75, 15049.75, 14940.0, 14940.0)]))
    assert abs(t["sl"] - 15150.0) <= 0.5 and abs(t["tp"] - 14950.0) <= 0.5 and t["exit_reason"] == "tp"
    (t,), _ = play({"stop_m": 0.25, "tgt_m": 0.25}, day(UP))                    # stop 25 points above the entry, target 25 below
    assert abs(t["sl"] - 15075.0) <= 0.5 and abs(t["tp"] - 15025.0) <= 0.5
    (t,), _ = play({"tgt_m": 0.0}, day(UP))
    assert t["tp"] is None and t["exit_reason"] != "tp"


def test_both_sides_in_one_bar_no_daily_atr_and_one_trade_a_day_leave_nothing_or_one():
    wild = [(15000.0, 15100.0, 14900.0, 15000.0)] + UP[1:]
    assert play({}, day(wild)) == ([], [])
    assert play({}, day(UP), daily=[]) == ([], [])
    again = UP + ramp(15200.0, 10, 15000.0) + fall(15200.0, 15100.0) + fall(15100.0, 15000.0)
    assert len(play({}, day(again))[0]) == 1


def walk(seed=3, n=390):
    rng = np.random.default_rng(seed)
    bars, c = [], 15000.0
    for _ in range(n):
        o = c
        c = o + float(rng.choice([-12, -6, -2, -1, 0, 1, 2, 6, 12])) * 0.25 * 4
        bars.append((o, max(o, c) + 0.25 * int(rng.integers(0, 4)), min(o, c) - 0.25 * int(rng.integers(0, 4)), c))
    return bars


LA = [{"thrust": k, "stop_m": s, "tgt_m": t} for k in (0.05, 0.1) for s, t in ((0.5, 0.5), (1.0, 1.0), (0.25, 2.0))]


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
                sp = spy(F.Judas)
                res = S.run_session(sp({**BASE, **p}), S.Tape("NQ", D, "NQM3", tape.ts, px, tape.size), daily=list(DAILY), on_error="raise")
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
            assert all((t - ns("00:00")) % (60 * S.NS) == 0 for t, *_ in log)
            for t in tr:
                e = t["entry_ms"] * 10**6
                assert e >= max(x for x, *_ in log if x <= e) + LAT
                n += 1
    assert n > 5


def test_identical_trades_at_1_and_8_workers_and_the_hold_checks_at_zero():
    real_days()
    specs = [(F.Judas, {**BASE, "thrust": k, "stop_m": s, "tgt_m": t}) for k in (0.1, 0.25) for s, t in ((0.5, 0.5), (1.0, 2.0), (0.25, 0.0))]
    a = S.run_many(specs, days=DAYS, workers=1)
    b = S.run_many(specs, days=DAYS, workers=W)
    n = 0
    for (cls, p), x, y in zip(specs, a, b):
        assert sig(x["trades"]) == sig(y["trades"]), p
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["both_sides_sessions"] == 0
        per = {}
        for t in x["trades"]:
            assert S.session_of(t["entry_ms"]) == "nyam", p
            assert (t["side"] == "short") == (t["sl"] > t["entry_price"])
            per[t["date"]] = per.get(t["date"], 0) + 1
        assert max(per.values(), default=0) <= 1
        n += len(x["trades"])
    assert n > 0
    assert RM.hold_checks(a, "NQ") == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
