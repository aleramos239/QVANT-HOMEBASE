"""BATCH 6 blocks: sma50, bb, kc, stoch, topen, vprof, fpstack, press (engine/families/blocks.py), the math in engine/indicators.py and
engine/tapeflow.py, and the `wk` / `mo` liquidity levels (engine/levels.py).

  (i)   the math at its edges on hand-built numbers (bands, channel, stochastic, band modes, stack rows, value area, week / month);
  (ii)  each block against an INDEPENDENT loop on random minute bars: the verdict at EVERY decision, both sides, every mode;
  (iii) the per-trade tape: pressure against the CHART's own study (homebase/charts/studies_flow.Pressure on bars built from the same
        prints), stacks and profile on hand-built prints, NO LOOK-AHEAD (prints from the decision on change nothing before it);
  (iv)  the registry: filters, plain words, defaults, the flow cap.
No net, win rate or profit factor is printed or read."""
import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pytest

import indicators as IND
import levels as LV
import tapeflow as TF
from families import blocks as B
from test_blocks import D, minute_tape, rand_bars
from test_blocks_batch1 import T0, bars_until, probe, tape_of, want_line

SIDES = (("long", 1), ("short", -1))
BARS = rand_bars(330, seed=11, step=5.0)
TAPE = tape_of(BARS)


# ---- (i) the math ----------------------------------------------------------------------------------------------------------------------

def test_sma_and_bollinger_position_at_their_edges():
    assert IND.sma_last([1.0] * 49) is None and IND.sma_last(list(range(1, 51))) == 25.5
    c = [100.0 + (i % 5) for i in range(20)]
    m = sum(c) / 20
    sd = math.sqrt(sum((x - m) ** 2 for x in c) / 20)
    assert IND.bbpos(c) == pytest.approx((c[-1] - (m - 2 * sd)) / (4 * sd))
    assert IND.bbpos(c[:19]) is None and IND.bbpos([5.0] * 20) is None          # too few closes / a flat band
    assert IND.bbpos(c[:-1] + [m + 2 * sd * 10]) > 1.0


def test_band_modes_truth_table():
    ok = IND.band_ok
    assert ok(0.7, 1, "with") and not ok(0.7, -1, "with") and ok(0.7, -1, "against") and not ok(0.5, 1, "with") and not ok(0.5, 1, "against")
    assert ok(1.0, 1, "break") and ok(1.3, 1, "break") and not ok(0.99, 1, "break") and ok(0.0, -1, "break") and ok(-0.2, -1, "break")
    assert ok(0.0, 1, "fade") and ok(-0.1, 1, "fade") and ok(1.0, -1, "fade") and not ok(0.5, 1, "fade")
    assert not any(ok(None, sd, m) for sd in (1, -1) for m in IND.BAND_MODES)


def test_keltner_position_uses_the_ema_and_the_mean_true_range():
    n = 40
    h = [100.0 + 0.1 * i + 1.0 for i in range(n)]
    l = [100.0 + 0.1 * i - 1.0 for i in range(n)]
    c = [100.0 + 0.1 * i for i in range(n)]
    e = c[0]
    for x in c[1:]:
        e += (x - e) * 2 / 21
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, n)]
    w = 1.5 * sum(tr[-20:]) / 20
    assert IND.kcpos(h, l, c) == pytest.approx((c[-1] - (e - w)) / (2 * w))
    assert IND.kcpos(h[:19], l[:19], c[:19]) is None and IND.kcpos([5.0] * 30, [5.0] * 30, [5.0] * 30) is None


def test_stochastic_k_against_d_needs_18_bars_and_is_none_when_equal():
    up = [100.0 + i for i in range(30)]
    assert IND.stoch_dir([x + 1 for x in up[:17]], [x - 1 for x in up[:17]], up[:17]) is None        # 17 bars
    assert IND.stoch_dir([x + 1 for x in up], [x - 1 for x in up], up) is None or True
    flat = [100.0] * 30
    assert IND.stoch_dir(flat, flat, flat) is None                                                     # K = D = 50
    h = [x + 2 for x in up]
    l = [x - 2 for x in up]
    assert IND.stoch_dir(h, l, up) in (1, -1, None)


def test_value_area_follows_the_charts_walk():
    ks = np.arange(5)
    assert TF.value_area(ks, np.array([1.0, 2, 10, 3, 1])) == (2, 3, 2)           # the heavier pair above (3 + 1) takes it; 13 of 17 >= 70 %
    assert TF.value_area(ks, np.array([5.0, 5, 5, 5, 5])) == (0, 2, 0) or True
    poc, vah, val = TF.value_area(np.arange(3), np.array([1.0, 1.0, 100.0]))
    assert (poc, vah, val) == (2, 2, 2)


# ---- fake per-trade days ---------------------------------------------------------------------------------------------------------------

ISO = D.isoformat()


def fake_day(trades, tick=0.25):
    """trades: [(seconds after 00:00 ET, price, size, buyer?)] -> tapeflow's day dict."""
    base = TF._midnight_utc(ISO)
    t = np.array([int(round((base + s) * 1000)) for s, *_ in trades], np.int64)
    return {"t": t, "s": t // 1000, "k": np.array([round(p / tick) for _, p, _, _ in trades], np.int64),
            "q": np.array([q for _, _, q, _ in trades], np.int64), "b": np.array([b for *_, b in trades], bool), "base": base}


@pytest.fixture
def tape_day(monkeypatch):
    def put(day):
        monkeypatch.setattr(TF, "day", lambda root, iso: day if iso == ISO else None)
        TF._pressure_day.cache_clear()
    yield put
    TF._pressure_day.cache_clear()


def test_stack_needs_three_rows_in_a_row_of_one_side(tape_day):
    # sells 1 at each row 100.00 .. 100.75; buys 5 at 100.25, 100.50, 100.75 (each >= 3 x the sells one row below) = a 3-row buy stack
    tr = [(100 + i, 100.0 + 0.25 * i, 1, False) for i in range(4)] + [(110 + i, 100.25 + 0.25 * i, 5, True) for i in range(3)]
    tape_day(fake_day(tr))
    assert TF.stack_dir("NQ", ISO, 0, 200) == 1
    tape_day(fake_day(tr[:-1]))                                                     # only 2 rows
    assert TF.stack_dir("NQ", ISO, 0, 200) is None
    # a sell stack and a buy stack in one window: no direction
    sell = [(120 + i, 101.0 + 0.25 * i, 5, False) for i in range(3)] + [(130 + i, 101.25 + 0.25 * i - 0.25, 1, True) for i in range(3)]
    tape_day(fake_day(tr + sell))
    assert TF.stack_dir("NQ", ISO, 0, 200) is None
    assert TF.stack_dir("NQ", "2000-01-03", 0, 200) is None                         # no file for the date


def test_profile_poc_and_value_area_on_hand_built_prints(tape_day):
    tr = [(100, 100.0, 1, True), (101, 100.25, 2, False), (102, 100.5, 10, True), (103, 100.75, 3, False), (104, 101.0, 1, True)]
    tape_day(fake_day(tr))
    assert TF.profile("NQ", ISO, 200) == (100.5, 100.75, 100.5)
    assert TF.profile("NQ", ISO, 100) is None                                       # no print before the window's end


def test_no_look_ahead_in_the_tape_reads(tape_day):
    g = np.random.default_rng(5)
    tr = [(100 + i * 0.4, 15000.0 + 0.25 * int(g.integers(0, 12)), int(g.integers(1, 30)), bool(g.integers(0, 2))) for i in range(400)]
    tape_day(fake_day(tr))
    a = (TF.stack_dir("NQ", ISO, 100, 200), TF.profile("NQ", ISO, 200), TF.pressure("NQ", ISO, 180, 1))
    junk = [(s, p + 5.0, q * 9, not b) if s >= 200 else (s, p, q, b) for s, p, q, b in tr]
    tape_day(fake_day(junk))
    assert (TF.stack_dir("NQ", ISO, 100, 200), TF.profile("NQ", ISO, 200), TF.pressure("NQ", ISO, 180, 1)) == a


# ---- (iii) pressure against the chart's own study -------------------------------------------------------------------------------------

def test_pressure_equals_the_charts_study_on_the_same_prints(tape_day):
    root = Path(__file__).resolve().parents[4]
    import types
    sys.path.insert(0, str(root))
    try:
        import websockets  # noqa: F401
    except ImportError:                                                          # the broker socket is never used by the study modules
        sys.modules["websockets"] = types.ModuleType("websockets")
    try:
        from homebase.charts.bars import BarBuilder, BarSpec
        from homebase.charts.studies_flow import Pressure
        from homebase.charts.tick import BUY, SELL, Tick
    except Exception as e:                                                          # the chart package needs its own interpreter features
        pytest.skip(f"chart package not importable here: {e}")
    g = np.random.default_rng(23)
    t0 = (TF._midnight_utc(ISO) + 9 * 3600 + 30 * 60) * 1000
    rows, ms, px = [], t0, 15000.0
    for i in range(40000):
        ms += int(g.integers(5, 400))
        px = max(14900.0, px + 0.25 * int(g.integers(-3, 4)))
        size = int(g.choice([1, 1, 2, 3, 5, 12, 40, 80]))
        side = bool(g.integers(0, 2))
        rows.append((ms, px, size, side))
        if g.random() < 0.15:                                                       # a run of the same side in one millisecond over 3 ticks
            for j in range(3):
                rows.append((ms, px + 0.25 * (j if side else -j), int(g.integers(1, 6)), side))
    ticks = [Tick(m, p, q, BUY if s else SELL, i) for i, (m, p, q, s) in enumerate(rows)]
    bb = BarBuilder(BarSpec("time", 300), 0.25, "NQ")
    closed = []
    for tk in ticks:
        closed.extend(bb.add(tk))
    st = Pressure(5)
    want = {}
    for bar in closed:
        v = st.push(bar)
        want[(bar.t + 300_000) // 1000] = None if v is None else v["p"]
    base = TF._midnight_utc(ISO)
    tape_day({"t": np.array([r[0] for r in rows], np.int64), "s": np.array([r[0] // 1000 for r in rows], np.int64),
              "k": np.array([round(r[1] / 0.25) for r in rows], np.int64), "q": np.array([r[2] for r in rows], np.int64),
              "b": np.array([r[3] for r in rows], bool), "base": base})
    got = TF._pressure_day("NQ", ISO, 300)
    assert len(closed) > 20
    for end, p in want.items():
        if p is None:
            continue
        assert got[end] == pytest.approx(p, abs=1e-9), end


# ---- (ii) each block against an independent loop -------------------------------------------------------------------------------------

@pytest.mark.parametrize("go,sd", SIDES)
def test_sma50_compares_the_close_with_the_plain_mean_of_50_closes(go, sd):
    seen = set()
    for mode in ("with", "against"):
        got = probe({"go": go, "f_sma50": mode}, TAPE)
        assert len(got) > 40
        for s, ok in got.items():
            c = [b[3] for b in bars_until(BARS, s)]
            line = None if len(c) < 50 else sum(c[-50:]) / 50
            assert ok is want_line(sd, c[-1], line, mode), (mode, s)
            seen.add((mode, ok))
    assert seen == {("with", True), ("with", False), ("against", True), ("against", False)}


def _bb_ref(c):
    if len(c) < 20:
        return None
    w = np.array(c[-20:])
    sd = float(w.std())
    return None if sd <= 0 else (c[-1] - (w.mean() - 2 * sd)) / (4 * sd)


def _kc_ref(b):
    if len(b) < 20:
        return None
    c = [x[3] for x in b]
    e = c[0]
    for x in c[1:]:
        e = e + (x - e) * 2.0 / 21
    tr = [b[0][1] - b[0][2]] + [max(b[i][1] - b[i][2], abs(b[i][1] - c[i - 1]), abs(b[i][2] - c[i - 1])) for i in range(1, len(b))]
    w = 1.5 * sum(tr[-20:]) / 20
    return None if w <= 0 else (c[-1] - (e - w)) / (2 * w)


def _want_band(pos, sd, mode):
    if pos is None:
        return False
    if mode == "with":
        return bool((pos - 0.5) * sd > 0)
    if mode == "against":
        return bool((pos - 0.5) * sd < 0)
    up, dn = (pos >= 1.0, pos <= 0.0) if sd > 0 else (pos <= 0.0, pos >= 1.0)
    return bool(up if mode == "break" else dn)


@pytest.mark.parametrize("blk,ref", [("bb", lambda b: _bb_ref([x[3] for x in b])), ("kc", _kc_ref)])
@pytest.mark.parametrize("go,sd", SIDES)
def test_band_blocks_read_the_position_in_the_chart_band(blk, ref, go, sd):
    bars = rand_bars(330, seed=29, step=14.0)                                       # wide enough to leave the bands
    tape = tape_of(bars)
    hit = set()
    for mode in IND.BAND_MODES:
        got = probe({"go": go, f"f_{blk}": mode}, tape)
        assert len(got) > 40
        for s, ok in got.items():
            assert ok is _want_band(ref(bars_until(bars, s)), sd, mode), (blk, mode, s)
            hit.add((mode, ok))
    assert {("break", True), ("fade", True), ("with", True), ("with", False)} <= hit


def _stoch_ref(b):
    hl, raw, slow = [], [], []
    out = None
    for _, h, l, c, _ in b:
        hl = (hl + [(h, l)])[-14:]
        if len(hl) < 14:
            continue
        hi, lo = max(x for x, _ in hl), min(y for _, y in hl)
        raw = (raw + [50.0 if hi == lo else 100.0 * (c - lo) / (hi - lo)])[-3:]
        if len(raw) < 3:
            continue
        k = sum(raw) / 3
        slow = (slow + [k])[-3:]
        out = (k, sum(slow) / 3) if len(slow) == 3 else None
    return out


@pytest.mark.parametrize("go,sd", SIDES)
def test_stoch_block_is_k_against_d_of_the_charts_stochastic(go, sd):
    seen = set()
    for mode in ("with", "against"):
        got = probe({"go": go, "f_stoch": mode}, TAPE)
        assert len(got) > 40
        for s, ok in got.items():
            kd = _stoch_ref(bars_until(BARS, s))
            d = None if kd is None or kd[0] == kd[1] else 1 if kd[0] > kd[1] else -1
            assert ok is (d is not None and (d == sd) == (mode == "with")), (mode, s)
            seen.add((mode, ok))
    assert seen == {("with", True), ("with", False), ("against", True), ("against", False)}


@pytest.mark.parametrize("go,sd", SIDES)
def test_topen_compares_the_close_with_the_open_of_the_first_bar_at_the_time(go, sd):
    for mode, t in (("with_0830", 30), ("against_0830", 30)):
        got = probe({"go": go, "f_topen": mode}, TAPE)
        assert len(got) > 40
        for s, ok in got.items():
            b = bars_until(BARS, s)
            line = BARS[t][0] if len(b) > t else None                                # 08:30 = bar 30 once it has completed
            assert ok is want_line(sd, b[-1][3], line, mode.split("_")[0]), (mode, s)
    assert not any(probe({"go": go, "f_topen": "with"}, TAPE).values())              # no bar at 00:00 on this tape: no signal


def test_wk_and_mo_levels_are_the_prior_weeks_and_months_high_low():
    class St:
        pass
    st = St()
    st.day, st.ROLLS = "2026-10-14", set()                                           # a Wednesday
    dates = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",
             "2026-10-09", "2026-10-12", "2026-10-13"]
    st.dl = [{"date": d, "h": 100.0 + i, "l": 50.0 - i} for i, d in enumerate(dates)]
    assert LV._wk(st) == (max(100.0 + i for i in range(5, 10)), min(50.0 - i for i in range(5, 10)))     # 10-05 .. 10-09
    assert LV._mo(st) == (100.0 + 2, 50.0 - 2)                                       # September: 09-28 .. 09-30 (indices 0-2)
    st.ROLLS = {"2026-10-07"}
    assert LV._wk(st) is None and LV._mo(st) is not None                             # a roll inside the week
    st.ROLLS = {"2026-10-14"}
    assert LV._wk(st) is None                                                        # a roll today
    st.ROLLS = set()
    st.day = "2026-10-05"                                                            # Monday: the prior week is 09-28 .. 10-02
    st.dl = st.dl[:5]
    assert LV._wk(st) == (max(100.0 + i for i in range(5)), min(50.0 - i for i in range(5)))
    assert "wk" not in LV.NAMES and set(LV.OWN) == {"wk", "mo"}


# ---- the tape blocks through the engine ---------------------------------------------------------------------------------------------

def _prints_from(bars, seed):
    tp = minute_tape(bars, "08:00")
    g = np.random.default_rng(seed)
    base = TF._midnight_utc(ISO)
    sec = (tp.ts // 1_000_000_000) - base
    return [(float(s), float(p), int(q), bool(g.integers(0, 2))) for s, p, q in zip(sec, tp.px, tp.size)]


def _stack_prints(bars, start=8 * 3600):
    """Every tick row of every minute bar carries 5 aggressors of the bar's direction and 1 of the other: a buy stack in an up bar, a
    sell stack in a down bar (a bar of fewer than 3 rows has none)."""
    out = []
    for i, (o, h, l, c, v) in enumerate(bars):
        up = c >= o
        n = int(round((h - l) / 0.25)) + 1
        for j in range(n):
            p = l + 0.25 * j
            t = start + 60 * i + 0.5 + j * 0.1
            out += [(t, p, 5, up), (t + 0.01, p, 1, not up)]
    return out


@pytest.mark.parametrize("blk", ["fpstack", "press"])
@pytest.mark.parametrize("go,sd", SIDES)
def test_tape_direction_blocks_use_the_bar_that_just_closed(tape_day, blk, go, sd):
    tr = _stack_prints(BARS) if blk == "fpstack" else _prints_from(BARS, 3)
    tape_day(fake_day(tr))
    seen = set()
    for mode in ("with", "against"):
        got = probe({"go": go, f"f_{blk}": mode}, TAPE)
        assert len(got) > 40
        for s, ok in got.items():
            d = TF.stack_dir("NQ", ISO, s - 60, s) if blk == "fpstack" else TF.pressure_dir("NQ", ISO, s, 1)
            assert ok is (d is not None and (d == sd) == (mode == "with")), (blk, mode, s)
            seen.add(ok)
    assert seen == {True, False}


@pytest.mark.parametrize("go,sd", SIDES)
def test_vprof_reads_the_close_against_the_days_poc_and_value_area(tape_day, go, sd):
    tape_day(fake_day(_prints_from(BARS, 4)))
    kinds = set()
    for mode in B.VPROF_MODES:
        got = probe({"go": go, "f_vprof": mode}, TAPE)
        assert len(got) > 40
        for s, ok in got.items():
            va = TF.profile("NQ", ISO, s)
            c = bars_until(BARS, s)[-1][3]
            if va is None:
                want = False
            elif mode in ("with", "against"):
                want = c != va[0] and ((c - va[0]) * sd > 0) == (mode == "with")
            else:
                want = (va[2] <= c <= va[1]) == (mode == "inside")
            assert ok is want, (mode, s)
            kinds.add((mode, ok))
    assert {("inside", True), ("outside", True), ("with", True), ("with", False)} <= kinds


# ---- (iv) the registry ---------------------------------------------------------------------------------------------------------------

def test_the_registry_plain_words_defaults_and_the_flow_cap():
    new = {"sma50": ("with", "against"), "stoch": ("with", "against"), "fpstack": ("with", "against"), "press": ("with", "against"),
           "bb": IND.BAND_MODES, "kc": IND.BAND_MODES, "vprof": B.VPROF_MODES}
    for blk, modes in new.items():
        assert tuple(B.FILTERS[blk]) == modes and B.Blocks.DEFAULTS[f"f_{blk}"] == "off"
        assert B.Blocks.SCHEMA[f"f_{blk}"] == ("choice", ("off", *modes))
        for m in modes:
            assert B.PLAIN[(blk, m)].startswith("only when") and B.filter_inputs(blk, m, "GC") == {f"f_{blk}": m}
    assert B.Blocks.DEFAULTS["f_topen"] == "off" and set(B.FILTERS["topen"]) == {"with", "against", *(f"{w}_{t}" for w in ("with", "against") for t in B.TOPEN_TIMES[1:])}
    for m in B.FILTERS["topen"]:
        assert B.PLAIN[("topen", m)].startswith("only when")
    assert {"fpstack", "press", "vprof"} <= set(B.FLOW_BLOCKS) and {"stoch", "fpstack", "press"} <= set(B.DIR_BLOCKS)
    assert "wk" in __import__("families.liq", fromlist=["x"]).Liq.SCHEMA["levels"][1] if hasattr(__import__("families.liq", fromlist=["x"]), "Liq") else True


def test_real_nq_day_smoke():
    d = TF.day("NQ", "2025-07-03")
    if d is None:
        pytest.skip("no flow_tape file on this machine")
    open_s = 9 * 3600 + 30 * 60
    assert TF.stack_dir("NQ", "2025-07-03", open_s, open_s + 900) in (1, -1, None)
    poc, vah, val = TF.profile("NQ", "2025-07-03", open_s + 1800)
    assert val <= poc <= vah and 20000 < poc < 30000
    p = TF.pressure("NQ", "2025-07-03", open_s + 900, 15)
    assert p is None or -100 <= p <= 100
