"""The fvg family (engine/families/fvg.py): the fair value gap as an entry trigger.

(i) the registry entry and the block; (ii) the rule on small synthetic bars -- the gap, its edges, the three entry modes,
the size floor, inside the session only, the newest gap replaces the older entry, none while a trade is open; (iii) NO
LOOK-AHEAD: garbage after a cut changes no decision at or before it and no entry before it, and an entry is never before
its decision plus the order delay; (iv) identical trades at 1 and 8 workers on real BUILD days, the hold checks at zero.
The real-day tests compare trades by fingerprint and assert counts only: no net, win rate or profit factor is printed."""
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
from families import fvg as F

D = dt.date(2023, 3, 14)                            # a BUILD weekday (EDT), not a roll day
DAILY = [{"date": "2023-03-13", "h": 15100.0, "l": 14900.0, "c": 15000.0, "contract": "NQM3"}]
DAYS = list(RM.SMOKE_DAYS)
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
WIDE = {"stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
BASE = {"tf": "1", "sess": "nyam", "min_gap": 0.25, **WIDE}
LAT = 85 * 10**6                                    # the engine's order delay, ns


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


def flat(n=120, px=15000.0):
    """n quiet minutes around px (range 2 points)."""
    return [(px, px + 1.0, px - 1.0, px)] * n


def up_gap(bars, i, base=15000.0, jump=10.0, low3=6.0):
    """Bars i-1, i, i+1 leave an UP gap: bar i-1 tops at base + 1, bar i runs to base + jump, bar i+1 bottoms at base + low3."""
    bars = list(bars)
    bars[i - 1] = (base, base + 1.0, base - 1.0, base)
    bars[i] = (base, base + jump, base, base + jump)
    bars[i + 1] = (base + jump, base + jump + 2.0, base + low3, base + jump + 1.0)
    for k in range(i + 2, len(bars)):                # afterwards price rests above the gap
        bars[k] = (base + jump + 1.0, base + jump + 2.0, base + jump, base + jump + 1.0)
    return bars


def mirror(bars, px=15000.0):
    return [(2 * px - o, 2 * px - l, 2 * px - h, 2 * px - c) for o, h, l, c in bars]


def spy(cls):
    """A subclass that logs every entry decision: (kind, decision ns, side, price, the order placed or None)."""
    class Spy(cls):
        log: list = []

        def _mkt(self, ctx, side, **kw):
            o = super()._mkt(ctx, side, **kw)
            type(self).log.append(("mkt", ctx.now_ns, side, self.C[-1], o is not None))
            return o

        def _lim(self, ctx, side, px, **kw):
            o = super()._lim(ctx, side, px, **kw)
            type(self).log.append(("lim", ctx.now_ns, side, px, o is not None))
            return o
    Spy.log = []
    return Spy


def play(params, tape, cls=F.Fvg, **kw):
    sp = spy(cls)
    st = sp({"hold_to": "day", **BASE, **params})
    res = S.run_session(st, tape, daily=list(DAILY), on_error="raise", **kw)
    return res.trades, list(sp.log)


def sig(trades):
    return hashlib.blake2b(json.dumps(trades, sort_keys=True, default=str).encode(), digest_size=12).hexdigest()


# ---- (i) the registry and the block ------------------------------------------------------------------------------------------

def test_the_registry_holds_fvg_as_written_and_it_is_a_block():
    assert families.ERRORS == {}
    cls, inputs, both, notes = families.REGISTRY["fvg"]
    lib = families.library("fvg")
    assert cls is F.Fvg and inputs == {} and both is False and cls.FEATURES == () and cls.SCREEN_TFS == ("1", "5", "15")
    assert lib["roots"] == ("NQ", "ES", "GC") and not lib["l2"] and not lib["weak"] and lib["mirror"] is None and lib["complexity"] == 6
    assert [v["min_gap"] for v in lib["variants"]] == [0.1, 0.25, 0.5]
    assert cls.defaults()["mode"] == "touch" and cls.schema()["mode"] == ("choice", ("touch", "mid", "go"))
    assert cls.SCREEN_RUN == {"strict_limit": True}
    assert issubclass(B.WRAPPED["fvg"], F.Fvg) and B.BASES["fvg"][0] is F.Fvg
    for s in RM.DAY_PASSES:                           # it trades in every session
        assert cls({"tf": "5", "sess": s, "hold_to": "day"}).sessions() == [s]


# ---- (ii) the rule -----------------------------------------------------------------------------------------------------------

def test_an_up_gap_is_bought_at_its_near_edge_its_middle_or_at_once():
    bars = up_gap(flat(), 41)                        # bars 09:40 / 09:41 / 09:42: bar 1 high 15001, bar 3 low 15006
    bars[44] = (15011.0, 15011.0, 15002.0, 15008.0)  # 09:44 comes back through the whole gap: its low prints at 09:44:30
    tape = minute_tape(bars)
    tr, log = play({"mode": "touch"}, tape)
    assert log == [("lim", ns("09:43:00"), "long", 15006.0, True)]
    assert len(tr) == 1 and tr[0]["side"] == "long" and tr[0]["entry_price"] == 15006.0 and hms(tr[0]["entry_ms"] * 10**6) == "09:44:30"
    tr, log = play({"mode": "mid"}, tape)
    assert log == [("lim", ns("09:43:00"), "long", 15003.5, True)] and tr[0]["entry_price"] == 15003.5
    tr, log = play({"mode": "go"}, tape)
    assert log == [("mkt", ns("09:43:00"), "long", 15011.0, True)] and hms(tr[0]["entry_ms"] * 10**6) == "09:43:15"
    # a limit needs a trade-through: a return that only touches the edge does not fill
    bars[44] = (15011.0, 15011.0, 15006.0, 15008.0)
    tr, log = play({"mode": "touch"}, minute_tape(bars))
    assert len(log) == 1 and tr == []


def test_a_down_gap_is_sold_the_mirror_way():
    bars = up_gap(flat(), 41)
    bars[44] = (15011.0, 15011.0, 15002.0, 15008.0)
    tr, log = play({"mode": "touch"}, minute_tape(mirror(bars)))
    assert log == [("lim", ns("09:43:00"), "short", 14994.0, True)]
    assert len(tr) == 1 and tr[0]["side"] == "short" and tr[0]["entry_price"] == 14994.0


def test_the_struct_stop_is_the_gaps_far_edge():
    bars = up_gap(flat(), 41)
    bars[44] = (15011.0, 15011.0, 15004.0, 15008.0)
    tr, _ = play({"mode": "touch", "stop_mode": "struct", "tgt_r": 1.0}, minute_tape(bars))
    assert (tr[0]["entry_price"], tr[0]["sl"], tr[0]["tp"]) == (15006.0, 15001.0, 15011.0)


def test_no_gap_no_entry_and_a_gap_smaller_than_min_gap_is_left():
    assert play({}, minute_tape(flat()))[1] == []
    bars = up_gap(flat(), 41)                        # 5 points high; the ATR there is about 3
    assert len(play({"min_gap": 1.0}, minute_tape(bars))[1]) == 1
    assert play({"min_gap": 5.0}, minute_tape(bars))[1] == []
    # bars that overlap by a tick, or only meet, leave no gap
    for low3 in (1.0, 0.75):
        assert play({"min_gap": 0.0}, minute_tape(up_gap(flat(), 41, low3=low3)))[1] == []
    assert len(play({"min_gap": 0.0}, minute_tape(up_gap(flat(), 41, low3=1.25)))[1]) == 1


def test_all_three_bars_are_bars_of_the_session():
    # bar 3 = the 09:31 bar (the second close of the session): bar 1 is a pre-open bar -> not this session's gap
    assert play({}, minute_tape(up_gap(flat(), 30)))[1] == []
    # bar 3 = the 09:32 bar: the third close
    assert [(k, hms(t)) for k, t, *_ in play({}, minute_tape(up_gap(flat(), 31)))[1]] == [("lim", "09:33:00")]
    # the pre-market instance takes the 09:2x gap, the morning instance does not
    bars = up_gap(flat(), 20)
    assert play({}, minute_tape(bars))[1] == [] and len(play({"sess": "pre"}, minute_tape(bars))[1]) == 1


def test_the_newest_gap_replaces_the_older_resting_entry():
    bars = up_gap(up_gap(flat(), 41), 51, base=15011.0)       # a second up gap ten minutes later, eleven points higher
    bars[60] = (15022.0, 15022.0, 15002.0, 15012.0)           # then price falls through BOTH gaps
    tr, log = play({"mode": "touch"}, minute_tape(bars))
    assert [(hms(t), px) for _, t, _, px, _ in log] == [("09:43:00", 15006.0), ("09:53:00", 15017.0)]
    assert len(tr) == 1 and tr[0]["entry_price"] == 15017.0  # the older entry at 15006 was cancelled: one fill, at the newer edge


def test_a_gap_that_forms_while_a_trade_is_open_is_not_traded():
    bars = up_gap(flat(), 41)
    bars[44] = (15011.0, 15011.0, 15004.0, 15011.0)           # fills the entry at 15006, the trade stays open (wide stop)
    bars = bars[:46] + up_gap(bars, 51, base=15011.0)[46:]
    tr, log = play({"mode": "touch"}, minute_tape(bars))
    assert len(log) == 1 and len(tr) == 1 and tr[0]["entry_price"] == 15006.0


def test_new_gap_stop_a_second_gap_before_the_fill_cancels_the_entry_and_the_day():
    # (the owner, 2026-10-07: "if a new gap was made, then cancel and we don't trade that day")
    bars = up_gap(up_gap(flat(), 41), 51, base=15011.0)       # a second up gap ten minutes later; price then falls through BOTH
    bars[60] = (15022.0, 15022.0, 15002.0, 15012.0)
    tape = minute_tape(bars)
    tr, log = play({"mode": "touch", "new_gap": "stop", "max_tr": 1}, tape)
    assert [(hms(t), px) for _, t, _, px, _ in log] == [("09:43:00", 15006.0)] and tr == []      # the second gap placed nothing and killed the first
    tr2, log2 = play({"mode": "touch", "new_gap": "replace", "max_tr": 1}, tape)                # the default: the newest replaces (as before)
    assert len(log2) == 2 and len(tr2) == 1 and tr2[0]["entry_price"] == 15017.0
    assert play({"mode": "touch", "max_tr": 1}, tape)[0] == tr2                                  # no input at all = replace


def test_new_gap_stop_a_fill_before_the_second_gap_keeps_the_trade():
    bars = up_gap(flat(), 41)
    bars[44] = (15011.0, 15011.0, 15004.0, 15011.0)           # fills the entry at 15006 before any second gap
    bars = bars[:46] + up_gap(bars, 51, base=15011.0)[46:]
    tr, log = play({"mode": "touch", "new_gap": "stop", "max_tr": 1}, minute_tape(bars))
    assert len(log) == 1 and len(tr) == 1 and tr[0]["entry_price"] == 15006.0


def test_new_gap_stop_a_gap_too_small_for_min_gap_does_not_cancel():
    bars = up_gap(flat(), 41)
    bars = up_gap(bars, 51, base=15011.0, jump=2.0, low3=1.5)  # a small second gap (0.5 points), under the 0.5 x ATR floor; the first gap (5 points) is over it
    bars[60] = (15014.0, 15014.0, 15002.0, 15004.0)           # price falls back through the first gap: it fills
    tr, log = play({"mode": "touch", "new_gap": "stop", "max_tr": 1, "min_gap": 0.5}, minute_tape(bars))
    assert len(log) == 1 and len(tr) == 1 and tr[0]["entry_price"] == 15006.0


# ---- (iii) no look-ahead --------------------------------------------------------------------------------------------------------

def walk_tape(seed=3, n=390):
    """A random walk of minute bars from 09:00 with jumps: it leaves gaps on both sides."""
    rng = np.random.default_rng(seed)
    bars, c = [], 15000.0
    for _ in range(n):
        o = c
        c = o + float(rng.choice([-12, -6, -2, -1, 0, 1, 2, 6, 12])) * 0.25 * 4
        bars.append((o, max(o, c) + 0.25 * int(rng.integers(0, 4)), min(o, c) - 0.25 * int(rng.integers(0, 4)), c))
    return minute_tape(bars)


LA = [{"mode": m, "tf": tf, "sess": s, "stop_mode": "pts", "stop_val": 6.0, "tgt_r": 1.0}
      for m in F.MODES for tf in ("1", "5") for s in ("nyam", "mid")]


def la_run(tape):
    return [play(p, tape) for p in LA]


def test_garbage_after_a_cut_changes_no_decision_and_no_entry_before_it():
    tape = walk_tape()
    real = la_run(tape)
    assert all(len(log) >= 2 for _, log in real) and sum(len(tr) for tr, _ in real) > 20
    rng = np.random.default_rng(7)
    rows = 0
    for cut in ("09:47", "10:00", "10:31", "11:00", "11:59", "12:44", "13:29"):
        c = ns(cut)
        k = int(np.searchsorted(tape.ts, c))
        px = tape.px.copy()
        px[k:] = np.round(tape.px[k:] * rng.uniform(0.99, 1.01, len(px) - k) / 0.25) * 0.25
        fake = la_run(S.Tape("NQ", D, "NQM3", tape.ts, px, tape.size))
        changed = 0
        for (tr, log), (tr2, log2) in zip(real, fake):
            assert [x for x in log if x[1] <= c] == [x for x in log2 if x[1] <= c], cut      # a decision AT the cut reads prints before it
            assert [t for t in tr if t["exit_ms"] < c // 10**6] == [t for t in tr2 if t["exit_ms"] < c // 10**6], cut
            rows += len([x for x in log if x[1] <= c])
            changed += tr != tr2
        assert changed > 0 or cut >= "12:00", cut     # the garbage really was replayed (late cuts leave no trade open to change)
    assert rows > 100


def test_an_entry_is_never_before_its_decision_plus_the_order_delay():
    tape, n = walk_tape(), 0
    for p, (tr, log) in zip(LA, la_run(tape)):
        step = int(p["tf"]) * 60 * S.NS
        assert all((t - ns("00:00")) % step == 0 for _, t, *_ in log)         # decisions at tf closes only
        dec = sorted(t for _, t, _, _, placed in log if placed)
        for t in tr:
            e = t["entry_ms"] * 10**6
            assert e >= max(x for x in dec if x <= e) + LAT
            n += 1
    assert n > 20


# ---- (iv) real BUILD days: counts and fingerprints only -----------------------------------------------------------------------

def real_specs():
    g = families.unit_grid("fvg", "NQ", "5")
    cells = g[1::max(1, len(g) // 8)]
    specs = []
    for c in cells:
        for mode in F.MODES:
            specs += [(cls, {**p, "mode": mode}) for cls, p in RM.cell_specs(c)]
    return specs


def test_identical_trades_at_1_and_8_workers_and_the_hold_checks_at_zero():
    real_days()
    specs = real_specs()
    a = S.run_many(specs, days=DAYS, workers=1, strict_limit=True)
    b = S.run_many(specs, days=DAYS, workers=W, strict_limit=True)
    assert len(specs) > 100
    n = {m: 0 for m in F.MODES}
    for (cls, p), x, y in zip(specs, a, b):
        assert sig(x["trades"]) == sig(y["trades"]), p
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["both_sides_sessions"] == 0
        assert not any(t["oco"] for t in x["trades"])
        per = {}
        for t in x["trades"]:
            assert S.session_of(t["entry_ms"]) == p["sess"], p                # entered inside its own session
            per[t["date"]] = per.get(t["date"], 0) + 1
        assert max(per.values(), default=0) <= cls.defaults()["max_tr"]
        n[p["mode"]] += len(x["trades"])
    assert all(v > 0 for v in n.values()), n
    assert RM.hold_checks(a, "NQ") == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
