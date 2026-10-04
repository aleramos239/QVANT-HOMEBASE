"""Template additions of the edge library (all default off): the pre-registered MENU, the percent stop, the Level-2 filters
f_book / f_thin and the book exit x_book, ctx.exit_market. Synthetic tapes and synthetic feature tables (no market data)
except where stated. Nothing here looks at a result."""
import datetime as dt

import numpy as np
import pytest

import l2ref
import l2sim as S

D = dt.date(2023, 3, 14)                      # a BUILD weekday (EDT)


def et(hhmm):
    return S.et_ns(D, hhmm)


def tape(start="09:00", end="11:05", px=15000.0):
    """A print every 10 s, a 3-step wiggle of one tick: bars with a tiny true range, no stop is ever near."""
    ts = np.arange(et(start), et(end), 10 * S.NS, dtype=np.int64)
    return S.Tape("NQ", D, "NQM3", ts, px + 0.25 * (np.arange(len(ts)) % 3), np.ones(len(ts), np.int64))


def feats(cols: dict, start="08:55", end="11:05"):
    """One row per minute stamped [start, end): usable 60 s after its stamp. cols: name -> f(minute 'HH:MM') -> value."""
    m0 = np.arange(et(start), et(end), S.MIN_NS, dtype=np.int64)
    hhmm = [dt.datetime.fromtimestamp(t / 1e9, S.ET).strftime("%H:%M") for t in m0]
    data = {"t_utc": (m0 // S.NS).astype(np.int64)}
    for k, fn in cols.items():
        data[k] = np.array([fn(h) for h in hhmm], np.float32)
    return S.Features(m0 + S.MIN_NS, data)


class Always(S.Template):
    """Enters `go` at market at every tf-bar close the Template allows."""
    DEFAULTS = {"go": "long"}
    SCHEMA = {"go": ("choice", ("long", "short"))}

    def fam_signal(self, ctx):
        self._mkt(ctx, self.p["go"])


BASE = {"tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20}


def minutes(trades, key="entry_ms"):
    return [dt.datetime.fromtimestamp(t[key] / 1000, S.ET).strftime("%H:%M") for t in trades]


def run(params, f=None):
    return S.run_session(Always({**BASE, **params}), tape(), features=f, daily=[], on_error="raise").trades


# ---- the menu ---------------------------------------------------------------------------------------------------------------

def test_the_menu_is_exactly_the_amended_pre_registration():
    """EDGE_SPEC 'Variant menu' (amended 2026-10-02 10:10 ET): 8 stops x 4 targets = 32 exit cells per root."""
    pts = {"NQ": [10, 20, 30, 45], "ES": [2.5, 5, 8, 12], "GC": [2, 3, 5, 7]}
    for root in ("NQ", "ES", "GC"):
        m = S.menu(root)
        assert len(m) == 32 and len({S.cell_id(c) for c in m}) == 32
        stops = [(c["stop_mode"], c["stop_val"]) for c in m[::4]]
        assert stops == [("atr", 1.5), ("atr", 3.0)] + [("pts", float(v)) for v in pts[root]] + [("pct", 0.10), ("pct", 0.20)]
        assert S.menu_stops(root) == [{"stop_mode": a, "stop_val": b} for a, b in stops]
        for k in range(8):
            assert [c["tgt_r"] for c in m[4 * k:4 * k + 4]] == [0.0, 1.0, 2.0, 3.0]          # none / 1:1 / 1:2 / 1:3
            assert len({(c["stop_mode"], c["stop_val"]) for c in m[4 * k:4 * k + 4]}) == 1
        for c in m:
            assert set(c) == {"stop_mode", "stop_val", "tgt_r"}
            l2ref.Donchian({"tf": "15", **c})                   # every cell is a valid Template input set
    offs = {"NQ": [10, 20], "ES": [2.5, 5], "GC": [2, 4]}
    for root in offs:
        assert S.menu_offsets(root) == [{"off_mode": "atr", "off_val": v} for v in (0.25, 0.5, 1.0)] + [
            {"off_mode": "pts", "off_val": float(v)} for v in offs[root]]
        for o in S.menu_offsets(root):
            l2ref.StraddleT({"at": "09:30", **o})
    with pytest.raises(KeyError):
        S.menu("CL")
    assert S.cell_id({"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}) == "atr1p5-r2"
    assert S.cell_id({"stop_mode": "pct", "stop_val": 0.10, "tgt_r": 0.0}) == "pct0p1-r0" and S.cell_id({}) == "default"


def test_menu_grid_is_variants_times_exit_cells_in_one_spec_list():
    g = S.menu_grid(l2ref.Donchian, {"tf": "15", "sess": "globex"}, "ES", [{"n": 10}, {"n": 20}, {"n": 40}])
    assert len(g) == 96 and len({c["id"] for c in g}) == 96 and g[0]["id"] == "n10_atr1p5-r0" and g[-1]["id"] == "n40_pct0p2-r3"
    assert [c["vi"] for c in g[::32]] == [0, 1, 2] and [c["xi"] for c in g[:32]] == list(range(32))
    cls, p = g[40]["spec"]
    assert cls is l2ref.Donchian and p == {"tf": "15", "sess": "globex", "n": 20, **S.menu("ES")[8]} and g[40]["exit"] == S.menu("ES")[8]
    assert len(S.menu_grid(l2ref.Donchian, {"tf": "15"}, "NQ")) == 32                 # no variants: the defaults only
    with pytest.raises(ValueError, match="menu owns"):
        S.menu_grid(l2ref.Donchian, {}, "NQ", [{"tgt_r": 1.0}])
    with pytest.raises(ValueError, match="duplicate"):
        S.menu_grid(l2ref.Donchian, {}, "NQ", [{"n": 10}, {"n": 10}])


def test_new_inputs_default_off_and_are_validated():
    p = l2ref.Donchian({"tf": "15"}).p
    assert (p["f_book"], p["x_book"], p["f_thin"], p["sess"], p["stop_mode"]) == ("off", "off", "off", "all", "atr")
    for bad in ({"f_book": "yes"}, {"x_book": 1}, {"f_thin": "thin"}, {"stop_mode": "percent"}, {"sess": "evening"}):
        with pytest.raises(ValueError):
            l2ref.Donchian({"tf": "15", **bad})
    assert S.template_feature_needs({"f_book": "on", "f_thin": "on"}) == ("imb10", "t_utc", "bid10_rel15", "ask10_rel15")
    assert S.template_feature_needs({"x_book": "on", "f_depth": "thin"}) == (S.DEPTH_COL, "imb10", "t_utc")
    assert S.template_feature_needs(p) == ()
    with pytest.raises(ValueError, match="imb10"):               # the option names the columns it needs
        S.run(l2ref.Donchian, {"tf": "15", "x_book": "on"}, days=[D.isoformat()], workers=1)
    with pytest.raises(ValueError, match="bid10_rel15"):
        S.run(l2ref.Donchian, {"tf": "15", "f_thin": "on"}, days=[D.isoformat()], workers=1, features=S.L2Features(["imb10", "t_utc"]))


# ---- f_book -----------------------------------------------------------------------------------------------------------------

def imb(h):                                                      # + until 09:44, - 09:45..09:59, NaN 10:00..10:04, + after
    return 0.2 if h < "09:45" else -0.2 if h < "10:00" else float("nan") if h < "10:05" else 0.2


def test_f_book_skips_an_entry_when_the_five_minute_mean_opposes_its_side_and_passes_nothing_without_a_signal():
    f = feats({"imb10": imb})
    off = run({"exit_bars": 1})
    on = run({"exit_bars": 1, "f_book": "on"}, f)
    assert run({"exit_bars": 1}, f) == off and len(off) == 20      # the features alone change nothing; max_tr caps the count
    m_off, m_on = minutes(off), minutes(on)
    # decision at T reads the rows stamped T-5 .. T-1: long is allowed while their mean is >= 0
    #   .. 09:47 mean > 0 (allowed) | 09:48 .. 10:00 mean < 0 (opposed) | 10:01 .. 10:09 a NaN row in the window (no signal)
    assert m_on and all(not ("09:48" <= m <= "10:09") for m in m_on)
    assert any(m <= "09:47" for m in m_on) and any(m >= "10:10" for m in m_on) and min(m for m in m_on if m > "09:47") == "10:10"
    assert any("09:48" <= m <= "10:09" for m in m_off)
    short = minutes(run({"exit_bars": 1, "f_book": "on", "go": "short"}, f))
    assert short and all("09:48" <= m <= "10:00" for m in short)   # the mirror: short only while the mean is <= 0
    # no feature table at all / a stale table: no signal -> the filter passes nothing
    assert run({"f_book": "on"}, None) == []
    stale = feats({"imb10": lambda h: 0.2}, end="09:20")
    assert run({"f_book": "on"}, stale) == []


def test_book_mean5_is_the_gate_g1_signal():
    f = feats({"imb10": lambda h: {"09:35": 0.5, "09:36": -0.1, "09:37": 0.3, "09:38": 0.1, "09:39": 0.2}.get(h, 0.0)})

    class Sim:
        root, date, tick, pv, segment = "NQ", D, 0.25, 20.0, "day"
        lo = i = 0
        px = np.zeros(1)
        positions = ()
        now = et("09:40")
    ctx = S.Ctx(Sim, 1, [], f)
    assert S.feat_fresh(ctx) and S.book_mean5(ctx) == pytest.approx(0.2, abs=1e-7)
    Sim.now = et("09:40") + 59 * S.NS
    assert S.book_mean5(ctx) == pytest.approx(0.2, abs=1e-7)       # still the minute that just ended
    Sim.now = et("09:41") + 30 * S.NS + S.MIN_NS
    assert S.feat_fresh(ctx)                                       # the 09:41 row is usable from 09:42
    gap = S.Features(np.delete(f.usable_ns, 43), {k: np.delete(v, 43) for k, v in f.cols.items()})      # the 09:38 row is missing
    Sim.now = et("09:40")
    assert S.book_mean5(S.Ctx(Sim, 1, [], gap)) is None            # 5 rows, but not 5 consecutive minutes
    assert S.book_mean5(S.Ctx(Sim, 1, [], None)) is None


# ---- x_book -----------------------------------------------------------------------------------------------------------------

def test_x_book_exits_at_market_after_two_consecutive_usable_opposed_minutes():
    f = feats({"imb10": lambda h: 0.2 if h < "09:41" else -0.2})
    held = run({"max_tr": 1})
    assert len(held) == 1 and minutes(held) == ["09:31"] and held[0]["exit_reason"] == "time" and minutes(held, "exit_ms") == ["11:00"]
    assert run({"max_tr": 1}, f) == held                           # x_book off: the book is not read
    t = run({"max_tr": 1, "x_book": "on"}, f)
    assert len(t) == 1 and t[0]["exit_reason"] == "book" and minutes(t) == ["09:31"]
    # mean of the rows T-5 .. T-1: 09:43 -> +0.04, 09:44 -> -0.04 (opposed, 1), 09:45 -> -0.12 (opposed, 2) -> exit order at 09:45:00
    # it is a MARKET order: live 85 ms later, filled on the first print after that (09:45:10), one tick against
    assert t[0]["exit_ms"] == (et("09:45") + 10 * S.NS) // 1_000_000
    k = int(np.searchsorted(tape().ts, et("09:45") + 10 * S.NS))
    assert t[0]["exit_price"] == tape().px[k] - 0.25
    # a short is opposed by a POSITIVE mean: here the book agrees with it all along after 09:41 -> never exits on the book
    s = run({"max_tr": 1, "x_book": "on", "go": "short"}, feats({"imb10": lambda h: -0.2}))
    assert s[0]["exit_reason"] == "time"


def test_x_book_a_minute_without_a_signal_neither_counts_nor_resets_and_no_book_means_no_exit():
    # opposed at 09:44 (count 1); the 09:44 row is NaN -> the decisions 09:45 .. 09:49 have no signal; 09:50 opposed (count 2) -> exit
    f = feats({"imb10": lambda h: 0.2 if h < "09:41" else float("nan") if h == "09:44" else -0.2})
    t = run({"max_tr": 1, "x_book": "on"}, f)
    assert t[0]["exit_reason"] == "book" and minutes(t, "exit_ms") == ["09:50"]         # a reset would have made it 09:51
    nob = run({"max_tr": 1, "x_book": "on"}, feats({"imb10": lambda h: float("nan")}))
    assert nob[0]["exit_reason"] == "time"                           # book_ok False / NaN all day: the exit does nothing
    assert run({"max_tr": 1, "x_book": "on"}, None)[0]["exit_reason"] == "time"
    # ONE opposed minute, then agreement, twice: the count restarts in between -> no exit
    # (a -1.0 row followed by a +1.0 row: the 5-minute mean is < 0 at exactly one decision, 09:42 and again 09:52)
    f = feats({"imb10": lambda h: {"09:41": -1.0, "09:42": 1.0, "09:51": -1.0, "09:52": 1.0}.get(h, 0.2)})
    assert run({"max_tr": 1, "x_book": "on"}, f)[0]["exit_reason"] == "time"


def test_exit_market_respects_the_placement_latency_and_stress_and_a_stop_wins_the_same_print():
    class Xm(S.Strategy):
        session_window = ("09:30", "10:00")
        bar_minutes = 0

        def times(self):
            return ["09:31", "09:40"]

        def on_time(self, ctx, t):
            if t == "09:31":
                ctx.market("long", sl=14990.0)
            else:
                assert ctx.exit_market("book") == 1 and ctx.exit_market("book") == 0          # one order per position

    tp = tape("09:30", "10:00")
    t = S.run_session(Xm({}), tp).trades[0]
    assert t["exit_reason"] == "book" and t["exit_ms"] == (et("09:40") + 10 * S.NS) // 1_000_000
    slow = S.run_session(Xm({}), tp, S.Costs(latency_ms=15_000, slippage_ticks=2.0)).trades[0]
    assert slow["exit_ms"] == (et("09:40") + 20 * S.NS) // 1_000_000                      # live at +15 s: the 09:40:20 print
    k = int(np.searchsorted(tp.ts, et("09:40") + 20 * S.NS))
    assert slow["exit_price"] == tp.px[k] - 0.5                                             # 2 ticks under stress
    gapped = S.Tape("NQ", D, "NQM3", tp.ts, np.where(tp.ts >= et("09:40"), 14000.0, tp.px), tp.size)
    g = S.run_session(Xm({}), gapped).trades[0]
    assert g["exit_reason"] == "sl"                                 # the stop is the older order: it fills first on that print
    with pytest.raises(ValueError):
        S._Sim(tp, 0, 1, S.Costs(), 85).exit_market("sl")


# ---- f_thin -----------------------------------------------------------------------------------------------------------------

def test_f_thin_allows_a_breakout_only_when_the_break_side_depth_is_thin():
    cols = {"ask10_rel15": lambda h: -0.25 if h < "09:45" else float("nan") if h < "09:50" else -0.10 if h < "10:00" else -0.20,
            "bid10_rel15": lambda h: 0.0 if h < "10:30" else -0.5}
    f = feats(cols)
    lg = minutes(run({"exit_bars": 1, "f_thin": "on"}, f))
    # a decision at T reads the row stamped T-1: thin (ratio <= 0.8) until 09:45, NaN until 09:50, 0.90 until 10:00, exactly 0.80 after
    assert lg and all(m <= "09:45" or m >= "10:01" for m in lg) and any(m <= "09:45" for m in lg) and any(m >= "10:01" for m in lg)
    sh = minutes(run({"exit_bars": 1, "f_thin": "on", "go": "short"}, f))
    assert sh and min(sh) == "10:31"                                 # a short breaks into the BID side
    assert run({"f_thin": "on"}, None) == []
    f8 = feats({"ask10_rel15": lambda h: -0.2, "bid10_rel15": lambda h: 0.0})

    class Sim:
        root, date, tick, pv, segment = "NQ", D, 0.25, 20.0, "day"
        lo = i = 0
        px = np.zeros(1)
        positions = ()
        now = et("09:40")
    c = S.Ctx(Sim, 1, [], f8)
    assert S.thin_ahead(c, 1) is True and S.thin_ahead(c, -1) is False and S.thin_ahead(S.Ctx(Sim, 1, [], None), 1) is None
