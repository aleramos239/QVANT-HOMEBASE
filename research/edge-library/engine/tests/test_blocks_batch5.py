"""BATCH 5 filter blocks of engine/families/blocks.py: the tape-and-flow blocks tspeed, absorb, exhaust, stoprun (flowtab.py, the completed
1-minute bars and engine/levels.py) and the book blocks micro, iceberg, pulled, qdepl (the Level-2 table; the last three are the vendor's
research tier).

  (i)   the math of engine/indicators.py at its thresholds on hand-built windows;
  (ii)  flowtab.prints: the trade count of the engine's minute grid;
  (iii) every flow block against an INDEPENDENT loop on shaped minute bars and a random flow table: the verdict at EVERY decision of a
        session, both sides, and every mode; both outcomes are met; no signal (too few reference dates, no row) blocks both sides;
  (iv)  every book block on a hand-built feature table: the sides, the 5-row window, NaN / a gap / a stale table = no signal;
  (v)   NO LOOK-AHEAD: prints, flow rows and feature rows from a decision on change nothing decided up to it;
  (vi)  the registry: filters, plain words, defaults, markets, columns, the research tier; (vii) real BUILD days: identical trades at
        1 and 8 workers.
No net, win rate or profit factor is printed or read."""
import datetime as dt

import numpy as np
import pytest

import flowtab as FT
import indicators as IND
import l2data as DATA
import l2sim as S
import levels as LV
import run_menus as RM
from families import blocks as B
from test_blocks import D, QUIET, W, days_of, garble, minute_tape, ns, prior_dates, real_days
from test_blocks_batch1 import tape_of
from test_blocks_batch4 import shaped_bars
from test_blocks_flow import minute_index, prefix, probe as flow_probe
from test_blocks_l2 import hhmm, probe as book_probe, table as feat_table

NMIN = FT.NMIN
SIDES = (("long", 1), ("short", -1))
MID = {"sess": "mid"}                               # 11:00 .. 13:30, decisions every minute
LEVELS = {}                                         # the levels a test hands to engine/levels.py (see the `levels` fixture)


# ---- (i) the math ----------------------------------------------------------------------------------------------------------------

def bar(h, l, s=0):
    return (s, l, h, l, h, 1)                       # (start, o, h, l, c, v): only high - low is read


def test_the_unit_is_the_mean_range_of_the_last_20_minutes_and_needs_10():
    bars = [bar(10.0 + (i % 3), 10.0, 60 * i) for i in range(30)]
    assert IND.minute_unit(bars) == pytest.approx(np.mean([b[2] - b[3] for b in bars[-20:]]))
    assert IND.minute_unit(bars[:9]) is None and IND.minute_unit(bars[:10]) is not None
    assert IND.minute_unit([bar(5.0, 5.0)] * 12) is None                           # no range at all: no unit


def test_absorb_wants_a_push_and_no_more_than_one_unit_of_progress_the_pushs_way():
    u = 2.0
    assert IND.absorb(40, 0.0, u) == -1 and IND.absorb(-40, 0.0, u) == 1           # buyers absorbed: bearish
    assert IND.absorb(40, 2.0, u) == -1 and IND.absorb(40, 2.25, u) is None        # exactly one unit of progress is still absorbed
    assert IND.absorb(40, -9.0, u) == -1 and IND.absorb(-40, 9.0, u) == 1          # price went the other way: absorbed all the more
    assert IND.absorb(-40, -2.25, u) is None and IND.absorb(0, 0.0, u) is None and IND.absorb(5, 0.0, 0.0) is None


def test_exhaust_wants_a_push_of_3_units_that_ends_at_a_level_and_a_last_minute_that_gives_back():
    u, hi = 2.0, [110.0]
    base = dict(delta=50, o=100.0, h=109.5, l=99.0, c_prev=108.5, c=108.0, unit=u, highs=hi, lows=[])
    assert IND.exhaust(**base) == -1                                               # +8 = 4 units, the high 0.5 under the level, closed back
    assert IND.exhaust(**{**base, "c": 106.0, "h": 107.0, "c_prev": 106.5}) is None            # 6 = exactly 3 units but 3 under the level: too far
    assert IND.exhaust(**{**base, "h": 111.9}) == -1 and IND.exhaust(**{**base, "h": 112.1}) is None   # within one unit beyond the level, not 2.1
    assert IND.exhaust(**{**base, "c": 109.0}) is None                              # the last minute did not give back (c >= c_prev)
    assert IND.exhaust(**{**base, "c": 105.9, "c_prev": 106.0}) is None            # the push is 5.9 < 6 = 3 units
    assert IND.exhaust(**{**base, "c": 106.0, "c_prev": 107.0, "h": 108.0}) == -1  # a push of exactly 3 units, ending exactly 1 unit under the level
    dn = IND.exhaust(-50, 100.0, 101.0, 90.5, 91.5, 92.0, u, [], [90.0])
    assert dn == 1                                                                 # a push down into a level low, closed back up
    assert IND.exhaust(50, 100.0, 109.5, 99.0, 108.5, 108.0, u, [], [90.0]) is None            # a push up needs a level HIGH


def test_stoprun_is_beyond_a_level_and_back_inside_at_the_last_close():
    hi, lo = [110.0], [90.0]
    assert IND.stoprun(111.0, 100.0, 109.5, hi, lo) == -1 and IND.stoprun(110.0, 100.0, 109.5, hi, lo) is None     # must trade BEYOND
    assert IND.stoprun(111.0, 100.0, 110.0, hi, lo) == -1 and IND.stoprun(111.0, 100.0, 110.25, hi, lo) is None    # back AT the level counts
    assert IND.stoprun(105.0, 89.0, 90.5, hi, lo) == 1 and IND.stoprun(105.0, 89.0, 89.5, hi, lo) is None
    assert IND.stoprun(111.0, 89.0, 100.0, hi, lo) is None                         # both levels run and back: no direction
    assert IND.stoprun(105.0, 95.0, 100.0, hi, lo) is None and IND.stoprun(105.0, 95.0, 100.0, [], []) is None


# ---- (ii) flowtab.prints ------------------------------------------------------------------------------------------------------------

def test_flowtab_prints_counts_the_trades_of_the_completed_minutes(tmp_path, monkeypatch):
    import pandas as pd
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    d = dt.date(2023, 1, 18)

    def utc(h, m):
        return int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=et).timestamp())
    rows = [{"t_utc": utc(9, 30), "session": d, "prints": 40}, {"t_utc": utc(9, 31), "session": d, "prints": 7},
            {"t_utc": utc(9, 33), "session": d, "prints": 5}]
    pd.DataFrame(rows).to_parquet(tmp_path / "NQ.parquet")
    monkeypatch.setattr(FT, "FLOW", tmp_path)
    FT._prints.cache_clear()
    try:
        s = 34200
        assert FT.prints("NQ", d.isoformat(), s, s + 240) == 52 and FT.prints("NQ", d.isoformat(), s + 60, s + 120) == 7
        assert FT.prints("NQ", d.isoformat(), s + 120, s + 180) == 0               # a minute without a print adds nothing
        assert FT.prints("NQ", d.isoformat(), s, s) is None and FT.prints("NQ", "2023-01-19", s, s + 60) is None
        assert FT.prints("ES", d.isoformat(), s, s + 60) is None
    finally:
        FT._prints.cache_clear()


# ---- (iii) the flow blocks against an independent loop --------------------------------------------------------------------------------

BARS = shaped_bars(330, 11)                         # 08:00 .. 13:30; an impulse bar of 36 points every 29th bar
TAPE = tape_of(BARS)
T0 = 8 * 3600
UP = [b for i, b in enumerate(BARS) if i % 29 == 28]


def flow_days(seed, n_ref=20, today=True):
    """Raw per-minute series {iso: dict(vol, delta, sweep, prints)} for the 20 weekdays before D and D."""
    g = np.random.default_rng(seed)

    def day():
        return {"vol": g.integers(60, 140, NMIN), "delta": g.integers(-60, 61, NMIN), "sweep": g.integers(-30, 31, NMIN),
                "prints": g.integers(20, 200, NMIN)}
    dates = prior_dates(n_ref) + ([D.isoformat()] if today else [])
    out = {iso: day() for iso in dates}
    if today:                                       # today's tape speeds up four-fold in every 4th block of 10 minutes (a burst somewhere)
        p = out[D.isoformat()]["prints"]
        p[(np.arange(NMIN) // 10) % 4 == 0] *= 4
    return out


def install(monkeypatch, days):
    """Hand the days to flowtab as prefix sums: the same arrays `flowtab._table` would build from a file."""
    tab = {iso: prefix(vol=x["vol"], delta=x["delta"], sweep=x["sweep"], big=0) for iso, x in days.items()}
    pr = {iso: np.concatenate(([0], np.cumsum(x["prints"])))[None, :] for iso, x in days.items()}
    monkeypatch.setattr(FT, "_table", lambda r: tab if r == "NQ" else {})
    monkeypatch.setattr(FT, "_prints", lambda r: pr if r == "NQ" else {})


@pytest.fixture
def levels(monkeypatch):
    """engine/levels.py hands out the levels in LEVELS: {name: (high, low)}, the same at every decision."""
    LEVELS.clear()
    monkeypatch.setattr(LV, "levels", lambda st, which="all": dict(LEVELS))
    yield LEVELS
    LEVELS.clear()


def impulse_levels():
    """Levels a little inside every impulse bar's extremes (so a push ends at one and a run beyond it is a trade-off of the walk)."""
    out = {}
    for k, (o, h, l, c, v) in enumerate(UP):
        out[f"i{k}"] = (h - 0.5, l + 0.5)
    return out


def minute(i):
    """The i-th minute bar of the tape: (start second, o, h, l, c)."""
    o, h, l, c, v = BARS[i]
    return T0 + 60 * i, o, h, l, c


def window5(s):
    """The five minute bars completed before the decision at second s, or None (before the tape has five)."""
    b = s // 60 * 60
    i = (b - T0) // 60
    return [minute(j) for j in range(i - 5, i)] if i >= 5 else None


def unit_at(s):
    b = s // 60 * 60
    i = (b - T0) // 60
    xs = [BARS[j][1] - BARS[j][2] for j in range(max(0, i - 20), i)]
    return float(np.mean(xs)) if len(xs) >= 10 else None


def ref_value(days, s, fn):
    """(today's fn over the window, [fn over the same window of the 20 dates before]) -- None where a window has no volume."""
    b = s // 60 * 60
    i, j = minute_index(b - 300), minute_index(b)
    out = {}
    for iso, x in days.items():
        out[iso] = fn({k: v[i:j] for k, v in x.items()})
    return out[D.isoformat()], [v for iso, v in out.items() if iso != D.isoformat() and v is not None]


def verdict_tspeed(days, s, mode):
    x, ref = ref_value(days, s, lambda w: int(w["prints"].sum()))
    med = float(np.median(ref))
    if mode == "fast":
        return x > med
    if mode == "slow":
        return x < med
    return med > 0 and x >= 2.0 * med


def share_vol(w, key):
    v = int(w["vol"].sum())
    return None if v <= 0 else (int(w[key].sum()) / v, v)


def verdict_dir(days, s, block, sd, mode):
    """The independent loop of absorb / exhaust / stoprun at decision second s: True / False for `go` with `mode`."""
    w, u = window5(s), unit_at(s)
    if w is None or u is None:
        return False
    x, ref = ref_value(days, s, lambda d: share_vol(d, "sweep" if block == "stoprun" else "delta"))
    if x is None or len(ref) < 15:
        return False
    xs, vol = x
    ref_s = [abs(a) for a, _ in ref]
    o, c, cp = w[0][1], w[-1][4], w[-2][4]
    hi, lo = max(m[2] for m in w), min(m[3] for m in w)
    highs = [a for a, _ in LEVELS.values()]
    lows = [b for _, b in LEVELS.values()]
    d = None
    if block == "absorb":
        if abs(xs) >= np.median(ref_s) and vol >= np.median([v for _, v in ref]) and xs != 0:
            sgn = 1 if xs > 0 else -1
            d = -sgn if (c - o) * sgn <= 1.0 * u else None
    elif block == "exhaust":
        if abs(xs) >= np.quantile(ref_s, 0.8) and xs != 0:
            sgn = 1 if xs > 0 else -1
            ext, lv = (hi, highs) if sgn > 0 else (lo, lows)
            if (c - o) * sgn >= 3.0 * u and (c - cp) * sgn < 0 and any(abs(ext - a) <= 1.0 * u for a in lv):
                d = -sgn
    else:
        up = any(hi > a and c <= a for a in highs)
        dn = any(lo < a and c >= a for a in lows)
        if up != dn:
            br = 1 if up else -1                                                   # the side that broke
            if xs * br > 0 and abs(xs) >= np.median(ref_s):
                d = -br
    return d is not None and ((d == sd) == (mode == "with"))


def run_flow(monkeypatch, days, params, tape=TAPE, daily=None):
    install(monkeypatch, days)
    from test_blocks import daily_rows
    return flow_probe({**MID, **params}, tape, daily or daily_rows([100.0] * 20))


@pytest.mark.parametrize("mode", ["fast", "slow", "burst"])
def test_tspeed_compares_the_prints_of_the_last_5_minutes_with_the_median_of_the_same_window(monkeypatch, mode):
    days = flow_days(5)
    got = dict(run_flow(monkeypatch, days, {"go": "long", "f_tspeed": mode}))
    assert len(got) > 100
    for s, v in got.items():
        assert v is verdict_tspeed(days, s, mode), (mode, s)
    assert set(got.values()) == {True, False}, mode                                # both outcomes met
    # the same on the short side (direction-free)
    assert dict(run_flow(monkeypatch, days, {"go": "short", "f_tspeed": mode})) == got


def test_tspeed_equality_and_no_signal_block_both_sides(monkeypatch):
    days = flow_days(5)
    # make today's window prints exactly the median of the references at one decision: a flat table of 100 a minute, today 100 a minute
    flat = {iso: {**x, "prints": np.full(NMIN, 100)} for iso, x in days.items()}
    for m in ("fast", "slow", "burst"):
        assert not any(v for _, v in run_flow(monkeypatch, flat, {"go": "long", "f_tspeed": m})) or m == "burst"
    assert not any(v for _, v in run_flow(monkeypatch, flat, {"go": "long", "f_tspeed": "fast"}))
    assert any(v for _, v in run_flow(monkeypatch, flat, {"go": "long", "f_tspeed": "burst"})) is False        # 100 < 2 x 100
    few = flow_days(5, n_ref=14)                                                     # fewer than 15 reference dates
    for m in ("fast", "slow", "burst"):
        assert not any(v for _, v in run_flow(monkeypatch, few, {"go": "long", "f_tspeed": m}))
    norow = flow_days(5, today=False)                                                # no row for today
    for m in ("fast", "slow", "burst"):
        assert not any(v for _, v in run_flow(monkeypatch, norow, {"go": "long", "f_tspeed": m}))


@pytest.mark.parametrize("block", ["absorb", "exhaust", "stoprun"])
@pytest.mark.parametrize("seed", [3, 8])
def test_the_flow_direction_blocks_equal_an_independent_loop_at_every_decision(monkeypatch, levels, block, seed):
    levels.update(impulse_levels())
    days = flow_days(seed)
    seen = {}
    for mode in ("with", "against"):
        for go, sd in SIDES:
            got = dict(run_flow(monkeypatch, days, {"go": go, f"f_{block}": mode}))
            assert len(got) > 100
            for s, v in got.items():
                assert v is verdict_dir(days, s, block, sd, mode), (block, mode, go, s)
            seen[mode, go] = got
    # a decision can allow at most one side of one mode: with-long = against-short, and the two modes never both allow a side
    for s in seen["with", "long"]:
        assert seen["with", "long"][s] == seen["against", "short"][s] and seen["with", "short"][s] == seen["against", "long"][s]
        assert not (seen["with", "long"][s] and seen["against", "long"][s])


def test_every_flow_direction_block_fires_somewhere_on_the_shaped_tape(monkeypatch, levels):
    levels.update(impulse_levels())
    for block in ("absorb", "exhaust", "stoprun"):
        n = 0
        for seed in range(1, 25):
            days = flow_days(seed)
            for mode in ("with", "against"):
                n += sum(v for _, v in run_flow(monkeypatch, days, {"go": "long", f"f_{block}": mode}))
        assert n > 0, f"{block} never allowed an entry on 24 seeds: the test cannot fail"


def test_a_flow_block_without_a_row_or_without_20_reference_dates_has_no_signal(monkeypatch, levels):
    levels.update(impulse_levels())
    for block in ("absorb", "exhaust", "stoprun"):
        for days in (flow_days(8, n_ref=14), flow_days(8, today=False)):
            for mode in ("with", "against"):
                assert not any(v for _, v in run_flow(monkeypatch, days, {"go": "long", f"f_{block}": mode}))


# ---- (iv) the book blocks ------------------------------------------------------------------------------------------------------------

def feats(cols, start="08:55", end="11:05"):
    return feat_table(cols, start, end)


def rows5(s):
    """The five feature-row stamps (hh:mm) the decision at second s reads: the minutes [s - 300, s - 60]."""
    return [hhmm(s - 60 * k) for k in range(5, 0, -1)]


def micro_expected(f_bid, f_ask, f_sp, s):
    offs = [f_sp(h) / 2.0 * (f_bid(h) - f_ask(h)) / (f_bid(h) + f_ask(h)) for h in rows5(s)]
    m = float(np.mean(offs))
    return 1 if m > 0 else -1 if m < 0 else None


def test_micro_is_the_sign_of_the_5_minute_mean_spread_weighted_imbalance_of_the_best_levels():
    # bids 9 / asks 1 (a lean up) with a 1-tick spread until 09:50; then a LEAN DOWN on a 9-tick spread in every 5th minute while
    # the other minutes lean up on a 1-tick spread: the unweighted majority is up, the spread-weighted mean is down.
    def bid(h): return 9 if h < "09:50" else (1 if int(h[3:]) % 5 == 4 else 9)
    def ask(h): return 1 if h < "09:50" else (9 if int(h[3:]) % 5 == 4 else 1)
    def sp(h): return 1 if h < "09:50" else (9 if int(h[3:]) % 5 == 4 else 1)
    f = feats({"bid_top1": bid, "ask_top1": ask, "spread_ticks": sp})
    differs = 0
    for mode in ("with", "against"):
        for go, sd in SIDES:
            got = book_probe({"go": go, "f_micro": mode}, f)
            assert len(got) > 60
            for s, v in got.items():
                d = micro_expected(bid, ask, sp, s)
                assert v is (d is not None and ((d == sd) == (mode == "with"))), (mode, go, hhmm(s))
                vote = sum(1 if bid(h) > ask(h) else -1 for h in rows5(s))
                differs += (d is not None) and ((d > 0) != (vote > 0))
    assert differs > 0                                                             # the weighting decides some decisions: dropping it fails
    even = feats({"bid_top1": lambda h: 3, "ask_top1": lambda h: 3, "spread_ticks": lambda h: 2})
    for m in ("with", "against"):
        for go, _ in SIDES:
            assert not any(book_probe({"go": go, "f_micro": m}, even).values())      # a balanced book is no signal, on either side


def test_micro_has_no_signal_on_nan_a_gap_or_a_stale_table():
    ok = {"bid_top1": lambda h: 4, "ask_top1": lambda h: 2, "spread_ticks": lambda h: 1}
    assert any(book_probe({"go": "long", "f_micro": "with"}, feats(ok)).values())
    for bad in ({"bid_top1": lambda h: float("nan")}, {"spread_ticks": lambda h: float("nan")}):
        f = feats({**ok, **bad})
        for m in ("with", "against"):
            assert not any(book_probe({"go": "long", "f_micro": m}, f).values())
    stale = feats(ok, end="09:20")
    assert not any(book_probe({"go": "long", "f_micro": "with"}, stale).values())
    assert not any(book_probe({"go": "long", "f_micro": "with"}, None).values())


@pytest.mark.parametrize("name,col,bid_is_bull", [("iceberg", "ice", True), ("pulled", "pulled", False), ("qdepl", "qdepl", False)])
def test_the_vendor_blocks_compare_the_bid_and_the_ask_series_summed_over_5_minutes(name, col, bid_is_bull):
    # bid 3 / ask 1 until 09:40, then ask 5 / bid 1, then a tie from 10:00: (the sum of 5 rows decides; a mixed window follows the sum)
    def bid(h): return 3.0 if h < "09:40" else 1.0 if h < "10:00" else 2.0
    def ask(h): return 1.0 if h < "09:40" else 5.0 if h < "10:00" else 2.0
    f = feats({f"rt_{col}_bid": bid, f"rt_{col}_ask": ask})
    mixed = 0
    for mode in ("with", "against"):
        for go, sd in SIDES:
            got = book_probe({"go": go, f"f_{name}": mode}, f)
            assert len(got) > 60
            for s, v in got.items():
                b, a = sum(bid(h) for h in rows5(s)), sum(ask(h) for h in rows5(s))
                d = None if b == a else (1 if (b > a) == bid_is_bull else -1)
                assert v is (d is not None and ((d == sd) == (mode == "with"))), (name, mode, go, hhmm(s))
                mixed += len({h < "09:40" for h in rows5(s)}) == 2
    assert mixed > 0
    nan = feats({f"rt_{col}_bid": lambda h: float("nan"), f"rt_{col}_ask": ask})
    assert not any(book_probe({"go": "long", f"f_{name}": "with"}, nan).values())


def test_the_book_blocks_need_five_consecutive_minutes():
    f = feats({"rt_ice_bid": lambda h: 3.0, "rt_ice_ask": lambda h: 1.0})
    holes = {ns("09:50") // S.NS, ns("09:51") // S.NS}                               # two minutes missing from the table
    keep = np.array([int(t) not in holes for t in f.cols["t_utc"]])
    g = S.Features(f.usable_ns[keep], {k: v[keep] for k, v in f.cols.items()})
    got = book_probe({"go": "long", "f_iceberg": "with"}, g)
    for s, v in got.items():
        has_hole = bool({ns(h) // S.NS for h in rows5(s)} & holes)
        assert v is (not has_hole), hhmm(s)
    assert any(got.values()) and not all(got.values())


# ---- (v) no look-ahead ------------------------------------------------------------------------------------------------------------

def test_flow_and_bar_blocks_never_read_from_the_decision_on(monkeypatch, levels):
    levels.update(impulse_levels())
    days = flow_days(8)
    for params in ({"go": "long", "f_absorb": "with"}, {"go": "short", "f_exhaust": "against"}, {"go": "long", "f_stoprun": "with"},
                   {"go": "long", "f_tspeed": "fast"}):
        clean = dict(run_flow(monkeypatch, days, params))
        for cut_hm in ("11:20", "12:05", "12:40"):
            cut = ns(cut_hm)
            c = (cut - ns("00:00")) // S.NS
            dirty_days = {}
            for iso, x in days.items():
                x = {k: v.copy() for k, v in x.items()}
                if iso == D.isoformat():                                            # every minute from the cut on is rewritten
                    k = minute_index(c)
                    g = np.random.default_rng(99)
                    x["vol"][k:] = g.integers(1, 400, NMIN - k)
                    x["delta"][k:] = g.integers(-300, 301, NMIN - k)
                    x["sweep"][k:] = g.integers(-200, 201, NMIN - k)
                    x["prints"][k:] = g.integers(1, 900, NMIN - k)
                dirty_days[iso] = x
            dirty = dict(run_flow(monkeypatch, dirty_days, params, tape=garble(TAPE, cut)))
            assert {s: v for s, v in dirty.items() if s <= c} == {s: v for s, v in clean.items() if s <= c}, (params, cut_hm)


def test_book_blocks_never_read_rows_that_are_not_usable_yet():
    def make(flip_from):
        return feats({"bid_top1": lambda h: 5 if h < flip_from else 1, "ask_top1": lambda h: 1 if h < flip_from else 5,
                      "spread_ticks": lambda h: 2, "rt_ice_bid": lambda h: 3.0 if h < flip_from else 1.0,
                      "rt_ice_ask": lambda h: 1.0 if h < flip_from else 3.0})
    for block in ("micro", "iceberg"):
        late, never = make("10:30"), make("23:59")
        a = book_probe({"go": "long", f"f_{block}": "with"}, late)
        b = book_probe({"go": "long", f"f_{block}": "with"}, never)
        # the row stamped 10:30 is usable at 10:31: nothing before the decision at 10:31 can know about it
        cut = (ns("10:31") - ns("00:00")) // S.NS
        assert {s: v for s, v in a.items() if s <= cut} == {s: v for s, v in b.items() if s <= cut}
        assert any(a[s] != b[s] for s in a if s > cut)


# ---- (vi) the registry ------------------------------------------------------------------------------------------------------------

NEW_FLOW = {"tspeed": ("fast", "slow", "burst"), "absorb": ("with", "against"), "exhaust": ("with", "against"), "stoprun": ("with", "against")}
NEW_BOOK = {"micro": ("with", "against"), "iceberg": ("with", "against"), "pulled": ("with", "against"), "qdepl": ("with", "against")}


def test_the_registry_the_plain_words_the_defaults_the_markets_and_the_research_tier():
    for blk, modes in {**NEW_FLOW, **NEW_BOOK}.items():
        assert tuple(B.FILTERS[blk]) == modes and B.Blocks.DEFAULTS[f"f_{blk}"] == "off"
        assert B.Blocks.SCHEMA[f"f_{blk}"] == ("choice", ("off", *modes))
        for m in modes:
            assert B.PLAIN[(blk, m)].startswith("only when") and B.filter_inputs(blk, m, "NQ") == {f"f_{blk}": m}
    for blk in NEW_FLOW:                                                           # NQ, ES and GC; the flow cap applies
        assert blk in B.FLOW_BLOCKS and blk not in B.L2_BLOCKS and blk not in B.BLOCK_MARKETS and B.filter_inputs(blk, NEW_FLOW[blk][0], "GC")
    for blk in NEW_BOOK:                                                           # NQ only: Level 2
        assert blk in B.L2_BLOCKS and blk not in B.FLOW_BLOCKS
        with pytest.raises(ValueError):
            B.filter_inputs(blk, "with", "ES")
    assert set(B.RT_BLOCKS) == {"iceberg", "pulled", "qdepl"} and "micro" not in B.RT_BLOCKS
    for blk in B.RT_BLOCKS:
        assert all("Research tier" in B.PLAIN[(blk, m)] for m in ("with", "against"))
    assert {"absorb", "exhaust", "stoprun", "micro", "iceberg", "pulled", "qdepl"} <= set(B.DIR_BLOCKS) and "tspeed" not in B.DIR_BLOCKS
    assert all((b, s) in B.PLAIN for b, sides in B.FILTERS.items() for s in sides)
    # every column a Level-2 block reads is a column of the feature table
    known = set(DATA.BOOK_COLS) | set(DATA.RT_COLS) | set(DATA.TAG_COLS)
    assert set(B.BOOK_COLS) <= known, set(B.BOOK_COLS) - known


def test_a_flow_block_and_a_book_block_can_be_paired_but_not_three_filters():
    f = B.combine([("absorb", "with"), ("micro", "against")])
    assert f == ("absorb+micro", "with+against") and B.reads(f, B.FLOW_BLOCKS) and B.reads(f, B.L2_BLOCKS)
    assert B.filter_inputs(*f, root="NQ") == {"f_absorb": "with", "f_micro": "against"}
    with pytest.raises(ValueError):
        B.filter_inputs("absorb+micro", "with+against", "ES")                      # the Level-2 half is NQ only


# ---- (vii) real BUILD days ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_identical_trades_at_1_and_8_workers_with_the_batch_5_flow_blocks(root):
    real_days()
    FT._table.cache_clear()
    FT._prints.cache_clear()
    days = days_of(root)
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0, "n": 10}
    specs = [(B.WRAPPED["donchian"], {**hd, "sess": sess, f"f_{blk}": mode})
             for sess in ("nyam", "pm") for blk, modes in NEW_FLOW.items() for mode in modes]
    a = S.run_many(specs, days=days, root=root, workers=1)
    b = S.run_many(specs, days=days, root=root, workers=W)
    seen = {}
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        k = next(k for k in p if k.startswith("f_"))
        seen[k] = seen.get(k, 0) + len(x["trades"])
    assert seen.get("f_tspeed", 0) > 0 and len(seen) == len(NEW_FLOW), seen          # the tape-speed block let some trades through on every market
    assert RM.hold_checks(a, root) == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}


def _book_specs():
    hd = {"tf": "5", "hold_to": "day", "stop_mode": "atr", "stop_val": 2.0, "tgt_r": 2.0, "sess": "nyam", "n": 10}
    return [(B.WRAPPED["donchian"], {**hd, f"f_{blk}": mode}) for blk, modes in NEW_BOOK.items() for mode in modes]


def _check_book_runs(specs, a, b):
    n = 0
    for (cls, p), x, y in zip(specs, a, b):
        assert x["skipped_by_error"] == 0 and y["skipped_by_error"] == 0, (p, x["no_trade"][:2])
        assert x["trades"] == y["trades"], p
        n += len(x["trades"])
    assert n > 0
    for i in range(0, len(specs), 2):                                               # with / against of one block never share a signal
        w, g = ({(t["entry_ms"], t["side"]) for t in a[k]["trades"]} for k in (i, i + 1))
        assert not w & g, specs[i][1]


def test_identical_trades_at_1_and_8_workers_with_the_batch_5_book_blocks_on_build_days_of_2021_to_2023():
    real_days()
    days = days_of("NQ")
    specs = _book_specs()
    try:
        f = S.L2Features(B.BOOK_COLS)
        a = S.run_many(specs, days=days, root="NQ", workers=1, features=f)
        b = S.run_many(specs, days=days, root="NQ", workers=W, features=f)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    _check_book_runs(specs, a, b)


def test_identical_trades_at_1_and_8_workers_with_the_batch_5_book_blocks_on_days_of_2024_and_of_2025s_first_half():
    import bpfeat
    real_days()
    if not bpfeat.cache_file().exists():
        pytest.skip("the 2025 first-half table is not built here")
    have = {d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), "NQ", allow_holdout=S.ALLOW_BP)}
    days = [d for d in ("2024-03-12", "2024-06-18", "2024-11-14", "2025-01-14", "2025-02-20", "2025-03-25", "2025-04-30", "2025-06-12", "2025-06-30")
            if d in have]
    assert len(days) >= 8
    specs = _book_specs()
    f = bpfeat.BpL2Features(B.BOOK_COLS)
    a = S.run_many(specs, period=S.ALLOW_BP, days=days, root="NQ", workers=1, features=f)
    b = S.run_many(specs, period=S.ALLOW_BP, days=days, root="NQ", workers=W, features=f)
    _check_book_runs(specs, a, b)
