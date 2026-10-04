"""EDGE_SPEC "STAGE 4 -- EVENT ENTRY VARIANTS": the round2 families (engine/families/round2.py), W straddle_wide and
D event_dir at 08:30 and 10:00 ET.

(i) the registry and the plan are the written stage; (ii) the entry logic on synthetic prints; (iii) NO LOOK-AHEAD: the
D direction reads only prints at or before release + X, the anchor is strictly before the release, rewriting any print
after the decision instant changes no decision, the order is live only after the decision instant plus the engine's
order delay; W's bracket reads only prints before it is placed; (iv) one trade per day; (v) identical trades at 1 and 8
workers on real BUILD days. The real-day tests compare trades by fingerprint and assert counts only: no net, win rate or
profit factor is printed."""
import datetime as dt
import hashlib
import json
import os

import numpy as np
import pytest

import families
import l2sim as S
import library as LB
import run_menus as RM
from families import round2 as R2

D = dt.date(2023, 3, 14)                            # a BUILD weekday (EDT), not a roll day
DAILY = [{"date": "2023-03-13", "h": 15100.0, "l": 14900.0, "c": 15000.0, "contract": "NQM3"}]
DAYS = list(RM.SMOKE_DAYS)
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
MS = 10**6                                          # ns in a millisecond
LAT = 85 * MS                                       # the engine's order delay
WIDE = {"stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
NAMES = ["event_dir_0830", "event_dir_1000", "straddle_wide_0830", "straddle_wide_1000"]
XS = (0.25, 0.5, 1.0, 2.0, 5.0, 15.0, 60.0)


def real_days():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def ns(hms, d=D):
    return S.et_ns(d, hms)


def xn(x):
    return int(round(x * S.NS))


def hms(ms):
    return dt.datetime.fromtimestamp(ms / 1000, S.ET).strftime("%H:%M:%S")


def ev_tape(extra=(), at="08:30", base=15000.0, root="NQ", contract="NQM3", tail=None, d=D):
    """A print every second at `base` from 2 h before `at` up to 1 s before it; then ONLY the prints of `extra` = (ns
    after `at`, price) for 2 minutes; then a print every second at `tail` (default: the last extra price) to 40 min after."""
    a = S._sec(at)
    t = ns(S._hms(a), d)
    pre = np.arange(ns(S._hms(a - 7200), d), t, S.NS, dtype=np.int64)
    ex = sorted(extra)
    assert all(-S.NS < o < 120 * S.NS for o, _ in ex)
    post = np.arange(t + 120 * S.NS, t + 2400 * S.NS, S.NS, dtype=np.int64)
    last = tail if tail is not None else (ex[-1][1] if ex else base)
    ts = np.concatenate([pre, np.array([t + int(o) for o, _ in ex], np.int64), post])
    px = np.concatenate([np.full(len(pre), base), np.array([p for _, p in ex], float), np.full(len(post), float(last))])
    return S.Tape(root, d, contract, ts, px, np.ones(len(ts), np.int64))


def sec_tape(moves=(), root="NQ", base=15000.0, at="08:30", contract="NQM3", step=S.NS):
    """A print every `step` ns from 2 h before `at` to 40 min after it, resting at `base`; a move (hms, price) sets every
    print from that time on (round1's straddle tape)."""
    a = S._sec(at)
    ts = np.arange(ns(S._hms(a - 7200)), ns(S._hms(a + 2400)), step, dtype=np.int64)
    px = np.full(len(ts), base)
    for t, p in moves:
        px[ts >= ns(t)] = p
    return S.Tape(root, D, contract, ts, px, np.ones(len(ts), np.int64))


def spy(cls):
    """A subclass that logs every entry decision: ('mkt' | 'arm', decision ns, sides, reference prices, placed orders)."""
    class Spy(cls):
        log: list = []

        def _mkt(self, ctx, side, **kw):
            o = super()._mkt(ctx, side, **kw)
            type(self).log.append(("mkt", ctx.now_ns, side, kw.get("ref"), None if o is None else (o.sl, o.tp)))
            return o

        def _arm(self, ctx, legs, **kw):
            out = super()._arm(ctx, legs, **kw)
            type(self).log.append(("arm", ctx.now_ns, tuple(x[0] for x in legs), tuple(x[1] for x in legs),
                                   tuple((o.price, o.sl, o.tp) for o in out)))
            return out
    Spy.log = []
    return Spy


def play(cls, params, tape, daily=DAILY, root=None, **kw):
    """One synthetic session through one instance (hold_to day) -> (trades, the Spy log, the instance)."""
    sp = spy(cls)
    st = sp({"hold_to": "day", **params})
    if root:
        st.root = root
    res = S.run_session(st, tape, daily=list(daily), on_error="raise", **kw)
    return res.trades, list(sp.log), st


def dirp(name, x, **kw):
    c, inputs, _, _ = families.REGISTRY[name]
    return c, {**inputs, "x": x, **WIDE, **kw}


def wide(name, off, mult, r, **kw):
    c, inputs, _, _ = families.REGISTRY[name]
    return c, {**inputs, "off": off, "stop_mode": "offx", "stop_val": mult, "tgt_r": r, **kw}


def sig(trades):
    """Fingerprint of a trade list: every field of every trade, in order (compared, never printed)."""
    return hashlib.blake2b(json.dumps(trades, sort_keys=True, default=str).encode(), digest_size=12).hexdigest()


# ---- (i) the registry and the plan = the written stage ------------------------------------------------------------------------

def test_the_registry_holds_the_two_entries_at_both_clock_times_as_written():
    assert families.ERRORS == {}
    assert RM.group_families("round2") == NAMES
    assert R2.EVENT_TIMES == ("08:30", "10:00") and R2.EVENT_X == XS
    lib = {n: families.library(n) for n in NAMES}
    cls = {n: families.REGISTRY[n][0] for n in NAMES}
    assert all(lb["roots"] == ("NQ", "ES", "GC") and not lb["l2"] and not lb["weak"] and lb["mirror"] is None
               and lb["second_look"] is None and "scheduled release reprices the market in one burst" in lb["rationale"]
               for lb in lib.values())
    assert all(RM.is_time_fired(c) and c.SCREEN_TFS == ("30",) and c.FEATURES == () for c in cls.values())
    # W: declared as resting orders on both sides; D: one direction, never opposite orders
    assert [families.REGISTRY[n][2] for n in NAMES] == [False, False, True, True]
    assert [cls[n] for n in NAMES] == [R2.EventDir, R2.EventDir, R2.StraddleWide, R2.StraddleWide]
    assert all(cls[n].defaults()["max_tr"] == 1 for n in NAMES)
    for n in NAMES[:2]:
        assert [v["x"] for v in lib[n]["variants"]] == list(XS)
    for n in NAMES[2:]:
        assert [v["off"] for v in lib[n]["variants"]] == ["A", "B", "C", "D"]
    # every unit is ONE instance held to the day's flatten time
    for n in NAMES:
        (c, p), = RM.cell_specs(families.unit_grid(n, "NQ", "30")[0])
        assert p["hold_to"] == "day" and c(p).sessions() == ["t"]


def test_w_grid_is_4_offsets_x_3_stops_of_the_offset_x_3_targets_per_root():
    assert R2.StraddleWide.OFF == {"NQ": (10.0, 15.0, 20.0, 30.0), "ES": (2.5, 4.0, 5.0, 8.0), "GC": (2.0, 3.0, 4.0, 6.0)}
    assert R2.StraddleWide.STOP_X == (0.5, 1.0, 1.5) and R2.StraddleWide.TGT == (1.0, 2.0, 3.0)
    want = {"08:30": ("08:29:59", "09:30:00"), "10:00": ("09:59:59", "11:00:00")}
    for t, (at, flat) in want.items():
        c, inputs, both, _ = families.REGISTRY["straddle_wide_" + t.replace(":", "")]
        assert inputs == {"at": at, "flat": flat} and c(inputs).p["cancel_min"] == 5
        assert c(inputs).fam_times() == [at, S._hms(S._sec(at) + 300)]
    for root in ("NQ", "ES", "GC"):
        tick = S.SPECS[root][1]
        for name in NAMES[2:]:
            g = families.unit_grid(name, root, "30")
            assert len(g) == 36 and len({c["id"] for c in g}) == 36 and not any(c.get("info") for c in g)
            assert [c["exit"] for c in g[:9]] == [{"stop_mode": "offx", "stop_val": m, "tgt_r": r}
                                                  for m in (0.5, 1.0, 1.5) for r in (1.0, 2.0, 3.0)]
            assert [c["variant"] for c in g[::9]] == [{"off": k} for k in "ABCD"]
        # every offset and every stop distance sits on the root's tick grid
        for off in R2.StraddleWide.OFF[root]:
            for m in (1.0,) + R2.StraddleWide.STOP_X:
                assert abs(off * m / tick - round(off * m / tick)) < 1e-9, (root, off, m)
    assert families.unit_grid("straddle_wide_0830", "NQ", "30")[0]["id"] == "offA_offx0p5-r1"


def test_d_grid_is_7_delays_x_the_32_menu_cells():
    for root in ("NQ", "ES", "GC"):
        for name, at in (("event_dir_0830", "08:30"), ("event_dir_1000", "10:00")):
            g = families.unit_grid(name, root, "30")
            assert len(g) == 224 and len({c["id"] for c in g}) == 224 and not any(c.get("info") for c in g)
            assert [c["exit"] for c in g[:32]] == S.menu(root)
            assert [c["variant"] for c in g[::32]] == [{"x": x} for x in XS]
            assert all(c["spec"][1]["at"] == at for c in g)
    assert [c["id"].split("_")[0] for c in families.unit_grid("event_dir_0830", "NQ", "30")[::32]] == [
        "x0p25", "x0p5", "x1", "x2", "x5", "x15", "x60"]
    # the decision instant of each cell = the release time + x, to the nanosecond (sub-second ones too)
    for at in ("08:30", "10:00"):
        for x in XS:
            st = R2.EventDir({"at": at, "x": x})
            rel, dec = st.fam_times()
            assert rel == at + ":00" and ns(dec) == ns(at) + xn(x) and "." in dec
            assert st.S["t"] == (S._sec(at), S._sec("09:30" if at == "08:30" else "11:00"))
    assert R2.EventDir({"at": "08:30", "x": 0.25}).dec_time() == "08:30:00.250000"
    assert R2.EventDir({"at": "10:00", "x": 60.0}).dec_time() == "10:01:00.000000"
    with pytest.raises(ValueError):
        R2.EventDir({"at": "08:30", "x": 3.0})      # not a written delay
    with pytest.raises(ValueError):
        R2.EventDir({"at": "09:30", "x": 1.0})      # not a written clock time


def test_the_round2_plan_and_the_cap(tmp_path):
    assert LB.CAPS["cells"] == 50000
    g = RM.group_plan("round2", ledger=tmp_path / "none.csv", runs_dir=tmp_path)
    by = {(r["family"], r["root"]): r for r in g["rows"]}
    assert len(by) == 12 and g["run_units"] == 12
    for (name, root), r in by.items():
        n = 224 if name.startswith("event_dir") else 36
        assert (r["units"], r["cells"], r["info_cells"], r["null_cells"], r["instances_per_cell"]) == (1, n, 0, 2 * n, 1)
        assert "shift" in r["control"]
    assert g["candidate_cells"] == 1560 and g["info_cells"] == 0 and g["unit_null_cells"] == 3120
    assert g["c1_pools_needed"] == 0 and g["c1_pools_missing"] == []
    assert g["ledger_cells_used"] == RM.PAPER_CELLS and g["pending_cells"] == 1560 and g["fits"]
    real = RM.group_plan("round2")
    assert real["cells_after"] == real["ledger_cells_used"] + real["pending_cells"] <= LB.CAPS["cells"] and real["fits"]
    # the nulls: both through shift_seed 1, 2 (W: random minutes; D: random direction)
    for name in NAMES:
        grid = families.unit_grid(name, "GC", "30")
        sh = RM.shift_grid(grid)
        assert len(sh) == 2 * len(grid) and {c["spec"][1]["shift_seed"] for c in sh} == {1, 2}


# ---- the sub-second clock --------------------------------------------------------------------------------------------------

def test_et_ns_keeps_a_fraction_of_a_second_and_whole_seconds_are_unchanged():
    def old(d, t):                                  # the function as it was before the fraction was kept
        return int(dt.datetime.combine(d, dt.time.fromisoformat(t), tzinfo=S.ET).timestamp()) * S.NS
    days = (D, dt.date(2021, 11, 5), dt.date(2021, 11, 8), dt.date(2022, 3, 11), dt.date(2022, 3, 14), dt.date(2023, 12, 29))
    for d in days:
        for t in ("00:00", "08:30", "08:29:59", "09:30:00", "13:13", "15:58", "18:00", "23:59:59"):
            assert S.et_ns(d, t) == old(d, t)
        assert S.et_ns(d, "08:30:00.250000") == old(d, "08:30") + 250 * MS
        assert S.et_ns(d, "08:30:00.500") == old(d, "08:30") + 500 * MS
        assert S.et_ns(d, "10:01:00.000000") == old(d, "10:01")
        assert S.et_ns(d, "08:30:00.000001") == old(d, "08:30") + 1000


# ---- (ii) D event_dir: the entry logic on synthetic prints ---------------------------------------------------------------------

def test_d_one_market_order_in_the_direction_of_the_move_since_the_last_print_before_the_release():
    t = ns("08:30")
    c, p = dirp("event_dir_0830", 0.25)
    tr, log, st = play(c, p, ev_tape([(100 * MS, 15001.0)]))
    assert log == [("mkt", t + 250 * MS, "long", 15001.0, log[0][4])] and st.anchor == 15000.0 and st.dec_px == 15001.0
    assert len(tr) == 1 and tr[0]["side"] == "long" and tr[0]["order_price"] is None and tr[0]["oco"] is False
    assert tr[0]["both_sides"] is False
    tr, log, _ = play(c, p, ev_tape([(100 * MS, 14999.75)]))
    assert [(k, s, ref) for k, _, s, ref, _ in log] == [("mkt", "short", 14999.75)] and tr[0]["side"] == "short"
    # no move = no trade: the print after the release is at the anchor price
    assert play(c, p, ev_tape([(100 * MS, 15000.0)]))[1] == []
    # no print between the release and the decision = no move = no trade (the 300 ms print comes after x = 0.25 s) ...
    tr, log, st = play(c, p, ev_tape([(300 * MS, 15010.0)]))
    assert tr == [] and log == [] and st.dec_px == st.anchor == 15000.0
    # ... and it is a move for x = 0.5 s
    assert [x[2] for x in play(*dirp("event_dir_0830", 0.5), ev_tape([(300 * MS, 15010.0)]))[1]] == ["long"]
    # the LAST print at the decision counts, not the first move
    tr, log, st = play(c, p, ev_tape([(50 * MS, 15005.0), (200 * MS, 14990.0), (400 * MS, 15020.0)]))
    assert [x[2] for x in log] == ["short"] and st.dec_px == 14990.0
    # a move that has come back to the anchor price by the decision = no trade
    assert play(c, p, ev_tape([(50 * MS, 15005.0), (200 * MS, 15000.0), (400 * MS, 15020.0)]))[1] == []
    # 10:00 ET has its own entry
    tr, log, _ = play(*dirp("event_dir_1000", 2.0), ev_tape([(1500 * MS, 14990.0)], at="10:00"))
    assert [(k, tt, s) for k, tt, s, _, _ in log] == [("mkt", ns("10:00") + 2 * S.NS, "short")]


def test_d_the_anchor_is_the_last_print_strictly_before_the_release_time():
    c, p = dirp("event_dir_0830", 1.0)
    # a print 1 ms before 08:30:00 is the anchor; a print stamped 08:30:00.000 itself is already after the release
    tr, log, st = play(c, p, ev_tape([(-MS, 15004.0), (0, 15010.0)]))
    assert st.anchor == 15004.0 and st.dec_px == 15010.0 and [x[2] for x in log] == ["long"]
    tr, log, st = play(c, p, ev_tape([(-MS, 15004.0), (0, 15004.0)]))
    assert st.anchor == 15004.0 and log == []
    # with only a print AT 08:30:00.000: the anchor is the 08:29:59 print (15000), so that print is a move
    tr, log, st = play(c, p, ev_tape([(0, 15010.0)]))
    assert st.anchor == 15000.0 and [x[2] for x in log] == ["long"]
    # whatever prints at or after the release, the anchor does not change
    for extra in ([(0, 14000.0)], [(1, 16000.0), (500 * MS, 14000.0)], [(999 * MS, 15000.25)]):
        assert play(c, p, ev_tape([(-MS, 15004.0)] + extra))[2].anchor == 15004.0
    # no print before the release in the day window: no anchor, no trade
    t = ns("08:30")
    ts = np.concatenate([[t + 100 * MS], np.arange(t + S.NS, t + 600 * S.NS, S.NS)]).astype(np.int64)
    tape = S.Tape("NQ", D, "NQM3", ts, np.full(len(ts), 15010.0), np.ones(len(ts), np.int64))
    tr, log, st = play(c, p, tape)
    assert st.anchor is None and tr == [] and log == []


@pytest.mark.parametrize("at", ["08:30", "10:00"])
def test_d_the_decision_reads_only_prints_at_or_before_release_plus_x(at):
    t = ns(at)
    name = "event_dir_" + at.replace(":", "")
    for x in XS:
        c, p = dirp(name, x)
        # decided exactly at release + x, on the last print before it
        tr, log, st = play(c, p, ev_tape([(xn(x) - MS, 15002.0)], at=at))
        assert [(k, tt, s, ref) for k, tt, s, ref, _ in log] == [("mkt", t + xn(x), "long", 15002.0)], x
        # a print 1 ms (or 1 ns) AFTER the decision instant is not read
        assert play(c, p, ev_tape([(xn(x) + MS, 15002.0)], at=at))[1] == [], x
        assert play(c, p, ev_tape([(xn(x) + 1, 15002.0)], at=at))[1] == [], x
        # a print stamped exactly AT the decision instant is read ("at or before")
        tr, log, st = play(c, p, ev_tape([(xn(x), 14998.0)], at=at))
        assert [(tt, s, ref) for _, tt, s, ref, _ in log] == [(t + xn(x), "short", 14998.0)], x
        # the direction is the one at the decision: an opposite print right after it changes nothing
        a = play(c, p, ev_tape([(xn(x) - MS, 15002.0), (xn(x) + 1, 14000.0)], at=at))
        assert [(tt, s, ref) for _, tt, s, ref, _ in a[1]] == [(t + xn(x), "long", 15002.0)], x


@pytest.mark.parametrize("at", ["08:30", "10:00"])
def test_d_the_order_is_live_only_after_the_decision_plus_the_order_delay(at):
    t = ns(at)
    name = "event_dir_" + at.replace(":", "")
    for x in XS:
        c, p = dirp(name, x)
        d = xn(x)
        tape = ev_tape([(MS, 15002.0), (d + 10 * MS, 15010.0), (d + 84 * MS, 15012.0), (d + LAT - 1, 15013.0), (d + LAT, 15020.0),
                        (d + 90 * MS, 15030.0), (d + 249 * MS, 15040.0), (d + 250 * MS, 15050.0), (d + 400 * MS, 15060.0)], at=at)
        (tr,), log, _ = play(c, p, tape)
        # the three prints inside the 85 ms after the decision cannot fill it; the first print from then on does, + 1 tick
        assert tr["entry_ns"] == t + d + LAT and tr["entry_price"] == 15020.25 and tr["side"] == "long", x
        assert log[0][1] == t + d and log[0][3] == 15002.0
        # the stop keeps its distance to the FILL (brackets re-priced to the fill)
        assert tr["entry_price"] - tr["sl"] == pytest.approx(500.0)
        # stress: 2 ticks + 250 ms
        (tr,), log, _ = play(c, p, tape, costs=S.Costs(slippage_ticks=2.0, latency_ms=250))
        assert tr["entry_ns"] == t + d + 250 * MS and tr["entry_price"] == 15050.5, x
        # no print for a while after the decision: the fill is the first print whenever it comes (here 2 minutes later)
        (tr,), log, _ = play(c, p, ev_tape([(MS, 14998.0)], at=at))
        assert tr["entry_ns"] == t + 120 * S.NS and tr["side"] == "short" and tr["entry_price"] == 14997.75


def test_d_exits_are_the_menu_cells_and_one_trade_a_day():
    t = ns("08:30")
    # menu stops: fixed points, percent of the decision price; the target is a multiple of the stop distance
    c, p = dirp("event_dir_0830", 1.0, stop_mode="pts", stop_val=10.0, tgt_r=2.0)
    (tr,), log, _ = play(c, p, ev_tape([(500 * MS, 15003.0), (2 * S.NS, 15003.0), (30 * S.NS, 15030.0)]))
    e = tr["entry_price"]
    assert e == 15003.25 and e - tr["sl"] == pytest.approx(10.0) and tr["tp"] - e == pytest.approx(20.0)
    assert tr["exit_reason"] == "tp"
    c, p = dirp("event_dir_0830", 1.0, stop_mode="pct", stop_val=0.10, tgt_r=0.0)
    (tr,), log, _ = play(c, p, ev_tape([(500 * MS, 15003.0), (2 * S.NS, 15003.0)]))
    assert tr["entry_price"] - tr["sl"] == pytest.approx(15.0, abs=0.25) and tr["tp"] is None
    assert tr["exit_reason"] == "eod"                 # the synthetic tape ends before 15:58
    # ONE trade a day: stopped out within seconds, price keeps running both ways -> nothing more
    c, p = dirp("event_dir_0830", 0.25, stop_mode="pts", stop_val=10.0, tgt_r=1.0)
    tr, log, _ = play(c, p, ev_tape([(100 * MS, 15002.0), (S.NS, 15002.0), (3 * S.NS, 14980.0), (9 * S.NS, 15040.0),
                                     (40 * S.NS, 14900.0), (90 * S.NS, 15100.0)]))
    assert len(log) == 1 and len(tr) == 1 and tr[0]["exit_reason"] == "sl" and tr[0]["side"] == "long"
    # hold_to day on a full day: flat at 15:58
    ts = np.arange(ns("06:00"), ns("16:05"), S.NS, dtype=np.int64)
    px = np.full(len(ts), 15000.0)
    px[ts >= t] = 15001.0
    (tr,), log, _ = play(*dirp("event_dir_0830", 1.0), S.Tape("NQ", D, "NQM3", ts, px, np.ones(len(ts), np.int64)))
    assert hms(tr["exit_ms"]) == "15:58:00" and tr["exit_reason"] == "time" and hms(tr["entry_ms"]) == "08:30:02"


def test_d_runs_on_es_and_gc_ticks():
    for root, base, contract, tick in (("ES", 4000.0, "ESM3", 0.25), ("GC", 1900.0, "GCJ3", 0.10)):
        daily = [{**DAILY[0], "contract": contract}]
        c, p = dirp("event_dir_1000", 0.5, stop_mode="pts", stop_val=S.MENU_STOP_PTS[root][0], tgt_r=1.0)
        tape = ev_tape([(200 * MS, base + tick), (700 * MS, base + tick)], at="10:00", base=base, root=root, contract=contract)
        (tr,), log, st = play(c, p, tape, daily=daily, root=root)
        assert st.anchor == base and tr["side"] == "long" and tr["entry_price"] == pytest.approx(base + 2 * tick)
        assert tr["entry_price"] - tr["sl"] == pytest.approx(S.MENU_STOP_PTS[root][0])
        tape = ev_tape([(200 * MS, base - tick)], at="10:00", base=base, root=root, contract=contract)
        assert play(c, p, tape, daily=daily, root=root)[0][0]["side"] == "short"


def test_d_the_null_is_the_same_entry_with_a_seeded_random_direction():
    tape = ev_tape([(100 * MS, 15002.0), (700 * MS, 15004.0), (3 * S.NS, 15006.0)])
    real = play(*dirp("event_dir_0830", 0.25), tape)[0]
    sides = {}
    for seed in range(1, 13):
        a = play(*dirp("event_dir_0830", 0.25, shift_seed=seed), tape)[0]
        b = play(*dirp("event_dir_0830", 5.0, shift_seed=seed, stop_mode="atr", stop_val=1.5, tgt_r=2.0), tape)[0]
        assert len(a) == len(b) == 1 and a[0]["side"] == b[0]["side"]              # the same flip for every x and exit cell
        assert a[0]["entry_ns"] == real[0]["entry_ns"]                             # the same instant as the real entry
        sides[seed] = a[0]["side"]
    assert set(sides.values()) == {"long", "short"}                                # a coin, not the move
    # the flip depends on the date and the clock time, not on the tape
    down = ev_tape([(100 * MS, 14998.0)])
    assert {s: play(*dirp("event_dir_0830", 0.25, shift_seed=s), down)[0][0]["side"] for s in sides} == sides
    # the null trades the same days: no move, no null trade
    assert play(*dirp("event_dir_0830", 0.25, shift_seed=1), ev_tape([(100 * MS, 15000.0)]))[1] == []
    assert play(*dirp("event_dir_0830", 0.25, shift_seed=1), ev_tape([(300 * MS, 15010.0)]))[1] == []


# ---- (iii) D: no look-ahead ----------------------------------------------------------------------------------------------------

def burst_tape(seed, at="08:30"):
    """Random prints around the release: ~2,400 prints at random nanoseconds from 60 s before to 100 s after `at` (a
    random walk on the tick grid that jumps at the release), on top of the one-second background before and after."""
    rng = np.random.default_rng(seed)
    off = np.unique(rng.integers(-60 * S.NS + 1, 100 * S.NS, 2400))
    step = rng.choice([-0.5, -0.25, 0.0, 0.25, 0.5], len(off))
    step[off >= 0] += rng.choice([-1, 1]) * 0.05
    px = 15000.0 + np.round(np.cumsum(step) / 0.25) * 0.25
    a = S._sec(at)
    t = ns(S._hms(a))
    pre = np.arange(ns(S._hms(a - 7200)), t - 60 * S.NS, S.NS, dtype=np.int64)
    post = np.arange(t + 120 * S.NS, t + 2400 * S.NS, S.NS, dtype=np.int64)
    ts = np.concatenate([pre, t + off, post]).astype(np.int64)
    pxs = np.concatenate([np.full(len(pre), 15000.0), px, np.full(len(post), px[-1])])
    return S.Tape("NQ", D, "NQM3", ts, pxs, np.ones(len(ts), np.int64))


def garbage_after(tape, cut_ns, rng, inclusive=False):
    """The same tape with every print stamped after `cut_ns` (inclusive: at or after) rewritten with random prices."""
    k = int(np.searchsorted(tape.ts, cut_ns, side="left" if inclusive else "right"))
    px = tape.px.copy()
    px[k:] = np.round(tape.px[k:] * rng.uniform(0.9, 1.1, len(px) - k) / 0.25) * 0.25
    return S.Tape("NQ", D, "NQM3", tape.ts, px, tape.size), len(px) - k


@pytest.mark.parametrize("at", ["08:30", "10:00"])
def test_d_rewriting_any_print_after_the_decision_instant_changes_no_decision(at):
    t = ns(at)
    name = "event_dir_" + at.replace(":", "")
    rng = np.random.default_rng(5)
    decided = changed = flipped = 0
    for seed in range(1, 9):
        tape = burst_tape(seed, at)
        for x in XS:
            for extra in ({}, {"shift_seed": 1}):
                c, p = dirp(name, x, stop_mode="pts", stop_val=6.0, tgt_r=1.0, **extra)
                tr, log, st = play(c, p, tape)
                # every print AFTER the decision instant is garbage: the same decision (time, side, reference, brackets)
                fake, n = garbage_after(tape, t + xn(x), rng)
                tr2, log2, st2 = play(c, p, fake)
                assert n > 0 and log2 == log and (st2.anchor, st2.dec_px) == (st.anchor, st.dec_px), (seed, x)
                assert all(tt == t + xn(x) for _, tt, _, _, _ in log)
                # every print AT or after the release is garbage: the same anchor
                fake, _ = garbage_after(tape, t, rng, inclusive=True)
                assert play(c, p, fake)[2].anchor == st.anchor, (seed, x)
                # the entry is never before the decision + the order delay
                assert all(r["entry_ns"] >= t + xn(x) + LAT for r in tr + tr2)
                if tr:
                    k = int(np.searchsorted(tape.ts, t + xn(x) + LAT))
                    assert tr[0]["entry_ns"] == tape.ts[k] and len(tr) == 1
                decided += len(log)
                changed += tr != tr2
            # the test has teeth: mirroring the prints BETWEEN the release and the decision flips the real direction
            c, p = dirp(name, x)
            tr, log, st = play(c, p, tape)
            a, b = np.searchsorted(tape.ts, [t, t + xn(x)], side="left")
            b = int(np.searchsorted(tape.ts, t + xn(x), side="right"))
            px = tape.px.copy()
            px[a:b] = 2 * st.anchor - px[a:b]
            log3 = play(c, p, S.Tape("NQ", D, "NQM3", tape.ts, px, tape.size))[1]
            if log:
                assert [z[2] for z in log3] == ["short" if log[0][2] == "long" else "long"], (seed, x)
                flipped += 1
    assert decided > 60 and changed > 30 and flipped > 30          # decisions were made, and the garbage really was replayed


# ---- W straddle_wide --------------------------------------------------------------------------------------------------------------

def test_w_the_bracket_is_placed_one_second_before_the_time_around_the_last_print():
    c, p = wide("straddle_wide_0830", "A", 1.0, 2.0)
    # the burst starts at 08:30:00: +11 through the +10 leg
    tr, log, _ = play(c, p, sec_tape([("08:30:00", 15011.0), ("08:30:30", 15060.0)]))
    assert [(k, hms(t // MS), sides, px) for k, t, sides, px, _ in log] == [("arm", "08:29:59", ("long", "short"), (15010.0, 14990.0))]
    assert len(tr) == 1 and tr[0]["side"] == "long" and tr[0]["order_price"] == 15010.0 and tr[0]["oco"] is True
    assert hms(tr[0]["entry_ms"]) == "08:30:00" and tr[0]["both_sides"] is True
    e = tr[0]["entry_price"]
    assert e - tr[0]["sl"] == pytest.approx(10.0) and tr[0]["tp"] - e == pytest.approx(20.0) and tr[0]["exit_reason"] == "tp"
    # the anchor is the last print BEFORE 08:29:59: a jump at 08:29:59 itself moves no leg; the bracket is live 85 ms
    # later, so the next print (08:29:59.5 on a half-second tape) fills the long leg
    tr, log, _ = play(c, p, sec_tape([("08:29:59", 15012.0)], step=S.NS // 2))
    assert log[0][3] == (15010.0, 14990.0) and tr[0]["entry_ms"] == ns("08:29:59") // MS + 500
    # the short leg; the other leg is cancelled by the fill (one trade, no re-entry after the stop-out)
    tr, log, _ = play(c, p, sec_tape([("08:30:02", 14989.0), ("08:30:10", 15020.0), ("08:31:00", 15060.0)]))
    assert len(tr) == 1 and tr[0]["side"] == "short" and tr[0]["exit_reason"] == "sl" and len(log) == 1
    # a move smaller than the offset fills nothing
    assert play(c, p, sec_tape([("08:30:00", 15009.75), ("08:30:20", 14990.25)]))[0] == []
    # the four offsets, the three stops (x the offset) and the three targets (x the stop), from the fill
    for off, pts in zip("ABCD", (10.0, 15.0, 20.0, 30.0)):
        for mult in (0.5, 1.0, 1.5):
            for r in (1.0, 2.0, 3.0):
                tr, log, _ = play(*wide("straddle_wide_0830", off, mult, r), sec_tape([("08:30:05", 15000.0 + pts + 0.25)]))
                assert log[0][3] == (15000.0 + pts, 15000.0 - pts)
                e = tr[0]["entry_price"]
                assert e - tr[0]["sl"] == pytest.approx(mult * pts) and tr[0]["tp"] - e == pytest.approx(r * mult * pts)


def test_w_unfilled_legs_are_cancelled_after_five_minutes_and_each_time_has_its_own_entry():
    c, p = wide("straddle_wide_0830", "A", 0.5, 1.0)
    tr, log, _ = play(c, p, sec_tape([("08:34:50", 15011.0)]))                    # a fill 4 min 51 s after the bracket was placed
    assert len(tr) == 1 and hms(tr[0]["entry_ms"]) == "08:34:50"
    tr, log, _ = play(c, p, sec_tape([("08:35:05", 15040.0)]))                    # after the cancel: nothing
    assert tr == [] and len(log) == 1
    cc, pp = wide("straddle_wide_1000", "B", 1.0, 1.0)
    tr, log, _ = play(cc, pp, sec_tape([("10:00:01", 15016.0)], at="10:00"))
    assert [hms(t // MS) for _, t, _, _, _ in log] == ["09:59:59"] and len(tr) == 1 and hms(tr[0]["entry_ms"]) == "10:00:01"
    assert tr[0]["order_price"] == 15015.0
    # ES and GC: the written offsets, the stop a multiple of the offset
    for root, base, contract, off, key in (("ES", 4000.0, "ESM3", 4.0, "B"), ("GC", 1900.0, "GCJ3", 6.0, "D")):
        cc, pp = wide("straddle_wide_0830", key, 1.5, 3.0)
        tape = sec_tape([("08:30:03", base + off + S.SPECS[root][1])], root=root, base=base, contract=contract)
        (t,), log, _ = play(cc, pp, tape, daily=[{**DAILY[0], "contract": contract}], root=root)
        assert t["order_price"] == pytest.approx(base + off) and t["entry_price"] - t["sl"] == pytest.approx(1.5 * off)
        assert t["tp"] - t["entry_price"] == pytest.approx(4.5 * off)


def test_w_the_bracket_reads_only_prints_before_it_is_placed():
    rng = np.random.default_rng(3)
    for at, armed in (("08:30", "08:29:59"), ("10:00", "09:59:59")):
        c, p = wide("straddle_wide_" + at.replace(":", ""), "A", 1.0, 1.0)
        tape = burst_tape(4, at)
        tr, log, _ = play(c, p, tape)
        fake, n = garbage_after(tape, ns(armed), rng, inclusive=True)
        tr2, log2, _ = play(c, p, fake)
        assert n > 0 and len(log) == 1 and log2 == log and log[0][1] == ns(armed)
        k = int(np.searchsorted(tape.ts, ns(armed)))
        assert log[0][3] == (tape.px[k - 1] + 10.0, tape.px[k - 1] - 10.0)        # around the last print before 1 s to the time
        assert all(r["entry_ns"] >= ns(armed) + LAT for r in tr + tr2)


def test_w_the_null_fires_the_same_bracket_at_random_minutes():
    c, p = wide("straddle_wide_1000", "B", 1.0, 2.0)
    st = c({**p, "shift_seed": 1})
    ks = [st.shift_of(d) for d in DAYS]
    assert len(set(ks)) > 5 and all(-90 <= k <= 90 for k in ks)
    assert ks == [c({**p, "off": "D", "stop_val": 0.5, "shift_seed": 1}).shift_of(d) for d in DAYS]       # the same minutes for every cell
    assert ks != [c({**p, "shift_seed": 2}).shift_of(d) for d in DAYS]
    st.begin_day(D)
    a, b = st.S["t"]
    assert (a - (S._sec("10:00") - 1)) % 60 == 0 and b - a == S._sec("11:00") - S._sec("10:00") + 1 and st.fam_times()[1] == S._hms(a + 300)


# ---- (iv) + (v) real BUILD days: 1 vs 8 workers, one trade a day, the delay, the windows (counts only) ---------------------------

def parity_specs(root="NQ"):
    specs = []
    for name in NAMES:
        g = families.unit_grid(name, root, "30")
        cells = g[2::max(1, len(g) // 12)]
        for c in cells:
            specs += RM.cell_specs(c)
        for c in RM.shift_grid(cells[:4]):
            specs += RM.cell_specs(c)
    return specs


def test_identical_trades_at_1_and_8_workers():
    real_days()
    n = {}
    for root in ("NQ", "GC"):
        specs = parity_specs(root)
        a = S.run_many(specs, days=DAYS, root=root, workers=1)
        b = S.run_many(specs, days=DAYS, root=root, workers=W)
        assert len(specs) > 60 and a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == min(W, len(DAYS))
        for (cls, p), x, y in zip(specs, a, b):
            assert sig(x["trades"]) == sig(y["trades"]), (root, cls.__name__, p)   # every field of every trade, in order
            assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["skipped"] == y["skipped"]
            assert [e["reason"] for e in x["no_trade"]] == [e["reason"] for e in y["no_trade"]]
            n[(root, cls.__name__)] = n.get((root, cls.__name__), 0) + len(x["trades"])
            if cls is R2.EventDir:                 # one direction: never opposite orders, never a resting entry
                assert x["both_sides_sessions"] == 0 and not any(t["oco"] or t["order_price"] is not None for t in x["trades"])
    assert all(n[(r, c)] > 0 for r in ("NQ", "GC") for c in ("EventDir", "StraddleWide")), n


def test_real_days_one_trade_a_day_the_delay_and_the_windows_counts_only():
    real_days()
    total = {}
    for root in ("NQ", "GC"):
        for name in NAMES:
            cls, inputs = families.REGISTRY[name][:2]
            g = families.unit_grid(name, root, "30")
            cells = g[1::max(1, len(g) // 14)]
            cells += RM.shift_grid(cells[:3])
            specs = [s for c in cells for s in RM.cell_specs(c)]
            res = S.run_many(specs, days=DAYS, root=root, workers=2, keep_ns=True)
            assert sum(r["skipped_by_error"] for r in res) == 0, name
            chk = RM.hold_checks(res, root)
            assert chk == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}, (name, chk)
            win = R2.ENTRY_WINDOWS[name]
            for c, r in zip(cells, res):
                per = {}
                for t in r["trades"]:
                    per[t["date"]] = per.get(t["date"], 0) + 1
                    if cls is R2.EventDir:
                        d = S._date(t["date"])
                        dec = S.et_ns(d, inputs["at"]) + xn(c["variant"]["x"])
                        assert t["entry_ns"] >= dec + LAT, (name, c["id"], t["date"])  # live only after the decision + the delay
                    if not c["variant"].get("shift_seed") or cls is R2.EventDir:    # W's null fires at other minutes
                        assert win[0] <= RM._et_sec(t["entry_ms"]) <= win[1], (name, c["id"], hms(t["entry_ms"]))
                assert max(per.values(), default=0) <= 1, (name, c["id"])           # ONE trade per day
                total[(root, name)] = total.get((root, name), 0) + len(r["trades"])
            if cls is R2.EventDir:                 # the null trades the same days at the same instant as its real cell
                for c, r, z in zip(cells[:3], res[:3], res[len(cells) - 6:len(cells) - 3]):
                    assert [(t["date"], t["entry_ns"]) for t in r["trades"]] == [(t["date"], t["entry_ns"]) for t in z["trades"]]
    assert all(v > 0 for v in total.values()) and len(total) == 8, total


def test_a_real_day_decision_does_not_change_when_the_prints_after_it_are_rewritten():
    real_days()
    rng = np.random.default_rng(9)
    n = 0
    for iso in DAYS[1:4]:
        d = dt.date.fromisoformat(iso)
        tape = S.load_tape(d, "NQ")
        for at in ("08:30", "10:00"):
            for x in XS:
                c, p = dirp("event_dir_" + at.replace(":", ""), x)
                cut = S.et_ns(d, at) + xn(x)
                tr, log, st = play(c, p, tape, daily=[])
                k = int(np.searchsorted(tape.ts, cut, side="right"))
                px = tape.px.copy()
                px[k:] = np.round(px[k:] * rng.uniform(0.9, 1.1, len(px) - k) / 0.25) * 0.25
                tr2, log2, st2 = play(c, p, S.Tape("NQ", d, tape.contract, tape.ts, px, tape.size), daily=[])
                assert log2 == log and (st2.anchor, st2.dec_px) == (st.anchor, st.dec_px), (iso, at, x)
                assert len(log) <= 1 and all(tt == cut for _, tt, _, _, _ in log)
                ka = int(np.searchsorted(tape.ts, S.et_ns(d, at), side="left"))
                assert st.anchor == tape.px[ka - 1] and st.dec_px == tape.px[k - 1]  # hand-read from the tape
                n += len(log)
    assert n > 20
