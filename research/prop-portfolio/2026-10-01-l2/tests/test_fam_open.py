"""O1 open_dir (families/opendir.py; definition pre-registered in FAMILIES.md): the trigger fires exactly when defined,
reads only rows that are already usable and only at the declared open times, rests ONE stop entry, cancels it 60 minutes
later, never trades asia / the last 5 minutes / a NaN (book_ok False) window. Synthetic tapes + feature tables in the
style of tests/test_l2sim_lookahead.py (S.Tape, S.Features, S.run_session); one real-data check on fixed in-sample days
that compares each trade's side with the feature table read independently of ctx. No P&L is looked at anywhere."""
import datetime as dt
import inspect

import numpy as np
import pytest

import families
import l2sim as S
from families import opendir as OD

D = dt.date(2024, 3, 5)                             # in-sample, not a roll day, not a half day
T0 = S.et_ns(D, "00:00")
BASE, ATR = 15000.0, 8.0                            # every 30-minute bar of the synthetic tape has true range 8
OFF, STOP = 0.25 * ATR, 3.0 * ATR                   # the pre-registered entry offset and stop distance, in points
VARIANTS = {"book": OD.OpenDirBook, "flow": OD.OpenDirFlow, "both": OD.OpenDirBoth}
ALL4 = ["london", "nyam", "mid", "pm"]


def sec(hms: str) -> int:
    return S._sec(hms)


def tape(extra=(), quiet=()):
    """Prints at BASE at second 1 and 31 of every minute 00:00 .. 16:00 ET; in every 30-minute bucket one print at
    BASE + 4 (minute 10, second 15) and one at BASE - 4 (minute 20, second 15), so every 30-minute bar has open = close
    = BASE and true range 8 -> ATR30 = 8.0 exactly at every decision. quiet = [(a, b)] seconds after 00:00 without the
    excursions; extra = [(seconds after 00:00, price)] added prints."""
    rows = []
    for m in range(16 * 60):
        rows += [(m * 60 + 1, BASE), (m * 60 + 31, BASE)]
    for b in range(0, 16 * 60, 30):
        for mm, px in ((10, BASE + 4.0), (20, BASE - 4.0)):
            s = (b + mm) * 60 + 15
            if not any(a <= s < z for a, z in quiet):
                rows.append((s, px))
    rows = sorted(rows + list(extra))
    return S.Tape("NQ", D, "NQH4", [T0 + int(round(s * S.NS)) for s, _ in rows], [p for _, p in rows], [1] * len(rows))


def feats(imb=lambda m: 0.1, delta=lambda m: 50.0, drop=(), last=16 * 60, shift_s=0):
    """One row per minute stamped m = -360 .. last - 1 (ET minutes after 00:00), usable at the END of its minute.
    imb / delta: stamp minute -> value. drop: stamp minutes left out (a hole). shift_s moves usable_ns only (a
    mis-timed table: negative = rows visible too early)."""
    ms = [m for m in range(-360, last) if m not in drop]
    t = np.array([T0 // S.NS + 60 * m for m in ms], np.int64)
    return S.Features((t + 60 + shift_s) * S.NS, {"t_utc": t, "imb10": np.array([imb(m) for m in ms], np.float32),
                                                   "f_delta": np.array([delta(m) for m in ms], np.float32)})


def run(src, f, t=None, **params):
    st = VARIANTS[src]({"tf": "30", **params})
    st.ROLLS = frozenset()
    res = S.run_session(st, t if t is not None else tape(), features=f, on_error="raise")
    assert res.skip is None and res.both_sides is False
    return res.trades


def sides(trades):
    return [(S.session_of(t["entry_ms"]), t["side"]) for t in trades]


def opens_min():
    return {s: v // 60 for s, v in OD.OPENS.items()}


# ---- registry / pre-registered defaults ---------------------------------------------------------------------------
def test_registry_entries_are_the_pre_registered_o1_variants():
    assert families.ERRORS == {} or not any("open" in k for k in families.ERRORS), families.ERRORS
    for src, cls in VARIANTS.items():
        name = f"open_dir_{src}"
        c, inputs, both, notes = families.REGISTRY[name]
        assert c is cls and inputs == {"src": src} and both is False and notes.startswith("O1")
        assert families.check_entry(name, families.REGISTRY[name]) == [] and families.MODULE_OF[name] == "opendir"
        assert cls.SCREEN_TFS == ("30",) and cls.session_independent is True and not hasattr(cls, "SCREEN_RUN")
        p = cls(families.screen_inputs(name, "30")).p
        assert p == {"tf": "30", "sess": "all", "dir": "both", "stop_mode": "atr", "stop_val": 3.0, "tgt_r": 0.0,
                     "trail_atr": 0.0, "exit_bars": 0, "max_tr": 1, "f_trend": "off", "f_vwap": "off", "f_depth": "off",
                     "src": src, "off_atr": 0.25}
        with pytest.raises(ValueError):             # a variant loads only its own columns: another src is refused
            cls({"src": "flow" if src != "flow" else "book"})
    assert OD.OpenDirBook.FEATURES == ("imb10", "t_utc") and OD.OpenDirFlow.FEATURES == ("f_delta", "t_utc")
    assert OD.OpenDirBoth.FEATURES == ("imb10", "f_delta", "t_utc")
    assert "REVISIT" in families.REGISTRY["open_dir_flow"][3] and "REFUTED" in families.REGISTRY["open_dir_flow"][3]
    assert "REVISIT" in families.REGISTRY["open_dir_both"][3] and "REVISIT" not in families.REGISTRY["open_dir_book"][3]
    assert not S.needs_exec_guard(S.L2Features(OD.OpenDirFlow.FEATURES)) and S.needs_exec_guard(S.L2Features(OD.OpenDirBook.FEATURES))


def test_opens_are_the_spec_times_and_an_entry_can_never_be_in_the_last_five_minutes():
    assert OD.OPENS == {"london": sec("03:00:00"), "nyam": sec("09:30:00"), "mid": sec("11:05:00"), "pm": sec("13:30:00")}
    assert (OD.CANCEL_S, OD.BOOK_MIN, OD.FLOW_MIN, OD.FLOW_VALID) == (3600, 5, 15, 8)
    for s, t in OD.OPENS.items():
        a, b = S.SESS[s]
        assert a <= t and t + OD.CANCEL_S <= b - 300        # the entry lives inside [open, open + 60 min) only
    st = OD.OpenDirBook({"tf": "30"})
    assert st.sessions() == ALL4 and sorted(st.fam_times()) == ["03:00:00", "04:00:00", "09:30:00", "10:30:00", "11:05:00",
                                                                "12:05:00", "13:30:00", "14:30:00"]
    assert OD.OpenDirBook({"tf": "30", "sess": "asia"}).sessions() == []
    src = inspect.getsource(OD)
    assert "l2data" not in src and "._feat" not in src and "ctx.feat(" not in src      # features through feat_window only


# ---- the two signs (pure) -------------------------------------------------------------------------------------------
NAN = float("nan")


@pytest.mark.parametrize("w,want", [
    ([0.1] * 5, 1), ([-0.1] * 5, -1), ([0.9, -0.1, -0.1, -0.1, -0.1], 1), ([-0.9, 0.1, 0.1, 0.1, 0.1], -1),
    ([0.0] * 5, 0), ([0.25, -0.25, 0.5, -0.5, 0.0], 0),                 # mean exactly 0 -> no side
    ([0.1, 0.1, NAN, 0.1, 0.1], 0), ([NAN] * 5, 0), ([0.1, 0.1, 0.1, 0.1, float("inf")], 0),      # any NaN -> no signal
    ([0.1] * 4, 0), ([0.1] * 6, 0), ([], 0)])                           # not exactly 5 rows -> no signal
def test_book_sign(w, want):
    assert OD.book_sign(np.array(w, np.float32)) == want


@pytest.mark.parametrize("w,want", [
    ([10.0] * 15, 1), ([-10.0] * 15, -1), ([100.0] + [-1.0] * 14, 1), ([-100.0] + [1.0] * 14, -1),
    ([0.0] * 15, 0), ([5.0, -5.0] * 7 + [0.0], 0),                      # sum exactly 0 -> no side
    ([NAN] * 7 + [3.0] * 8, 1), ([NAN] * 8 + [3.0] * 7, 0), ([NAN] * 15, 0),       # >= 8 minutes with a print
    ([-2.0] * 8 + [NAN] * 7, -1), ([10.0] * 14, 0), ([10.0] * 16, 0)])
def test_flow_sign(w, want):
    assert OD.flow_sign(np.array(w, np.float32)) == want


# ---- end to end: the order -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("src", list(VARIANTS))
@pytest.mark.parametrize("sgn", [1, -1])
def test_one_stop_entry_per_open_on_the_signalled_side_with_the_pre_registered_stop(src, sgn):
    tr = run(src, feats(imb=lambda m: 0.1 * sgn, delta=lambda m: 50.0 * sgn))
    side = "long" if sgn > 0 else "short"
    assert sides(tr) == [(s, side) for s in ALL4]                       # one trade per open, never asia
    for t, s in zip(tr, ALL4):
        fill = BASE + sgn * (4.0 + 0.25)                                # the first print through the stop, + 1 tick slip
        hit = OD.OPENS[s] + (10 * 60 + 15 if sgn > 0 else 20 * 60 + 15) - (300 if s == "mid" else 0)
        assert t["order_price"] == BASE + sgn * OFF                     # last print before the open +/- 0.25 ATR30
        assert t["entry_price"] == fill and t["entry_ns"] == T0 + hit * S.NS
        assert t["sl"] == fill - sgn * STOP and t["tp"] is None         # stop 3 ATR30 from the fill, no target
        assert t["exit_reason"] == "time" and t["exit_ns"] == T0 + (S.SESS[s][1] + 1) * S.NS      # flat at the session end
        assert t["oco"] is False and t["both_sides"] is False and t["qty"] == 1


def test_src_decides_which_feature_picks_the_side():
    f = feats(imb=lambda m: 0.1, delta=lambda m: -50.0)                  # book says long, flow says short
    assert sides(run("book", f)) == [(s, "long") for s in ALL4]
    assert sides(run("flow", f)) == [(s, "short") for s in ALL4]
    assert run("both", f) == []                                         # they disagree: no trade
    assert sides(run("both", feats(imb=lambda m: -0.1, delta=lambda m: -50.0))) == [(s, "short") for s in ALL4]
    assert run("book", feats(imb=lambda m: 0.0)) == [] and run("flow", feats(delta=lambda m: 0.0)) == []
    assert run("both", feats(imb=lambda m: 0.0)) == [] and run("both", feats(delta=lambda m: 0.0)) == []
    assert sides(run("book", f, dir="short")) == [] and sides(run("flow", f, dir="short")) == [(s, "short") for s in ALL4]
    assert sides(run("book", f, sess="nyam")) == [("nyam", "long")] and run("book", f, sess="asia") == []


# ---- the window is exactly the minutes that just ended ---------------------------------------------------------------
def window_table(n, inside, outside, oldest=None):
    """stamp minute -> `inside` on the n minutes before each open (`oldest` on the first of them), `outside` elsewhere:
    in particular on the minute before the window and on the open minute itself (not usable at the open)."""
    val = {}
    for o in opens_min().values():
        for m in range(o - n, o):
            val[m] = inside
        if oldest is not None:
            val[o - n] = oldest
    return lambda m: val.get(m, outside)


@pytest.mark.parametrize("src", list(VARIANTS))
def test_the_side_comes_from_exactly_the_rows_before_the_open(src):
    """Everything outside the window says SHORT, loudly: the row before it, the row of the open minute (usable one
    minute AFTER the decision) and every later row. A window one row late (look-ahead), one row early (stale), or one
    row longer would turn the side short."""
    f = feats(imb=window_table(5, 0.1, -0.9), delta=window_table(15, 10.0, -1000.0))
    assert sides(run(src, f)) == [(s, "long") for s in ALL4]
    # the OLDEST row of the window decides (a window one row shorter would turn the side short)
    f = feats(imb=window_table(5, -0.1, -0.9, oldest=0.9), delta=window_table(15, -10.0, -1000.0, oldest=500.0))
    assert sides(run(src, f)) == [(s, "long") for s in ALL4]


@pytest.mark.parametrize("src", list(VARIANTS))
def test_every_feature_read_is_at_an_open_and_returns_only_usable_rows(src, monkeypatch):
    f = feats(imb=window_table(5, 0.1, -0.9), delta=window_table(15, 10.0, -1000.0))
    calls, single = [], []
    real = S.Ctx.feat_window

    def spy(self, name, n=None):
        w = real(self, name, n)
        calls.append((self.now_ns, name, n, w.tolist()))
        return w
    monkeypatch.setattr(S.Ctx, "feat_window", spy)
    monkeypatch.setattr(S.Ctx, "feat", lambda self, *a, **k: single.append(a) or None)
    assert len(run(src, f)) == 4
    assert single == []                                                 # the family reads windows only
    assert {c[0] for c in calls} == {T0 + t * S.NS for t in OD.OPENS.values()}      # only at the four declared opens
    assert {c[1] for c in calls} == set(VARIANTS[src].FEATURES)
    for now, name, n, got in calls:
        k = int((f.usable_ns <= now).sum())                             # rows usable at the decision
        assert n in (5, 15) and got == f.cols[name][k - n:k].tolist()
        assert f.usable_ns[k - 1] == now and f.usable_ns[k] == now + S.MIN_NS      # newest = the minute that just ended


@pytest.mark.parametrize("src", list(VARIANTS))
@pytest.mark.parametrize("shift_s", [-3600, -120, -60, 1, 60, 3600])
def test_a_mistimed_table_gives_no_signal(src, shift_s):
    """Power of the freshness rule: the same table made visible a minute early (the forming minute would be the newest
    row) or late (a constant adapter shift, as in test_l2sim_lookahead) is not the minutes that just ended -> no trade,
    never a trade on other rows. (One second EARLY shows the same rows at a minute boundary: that leak is the adapter's
    own M + 59 s test.)"""
    f = feats(imb=window_table(5, 0.1, -0.9), delta=window_table(15, 10.0, -1000.0), shift_s=shift_s)
    assert run(src, f) == []


def test_a_missing_or_stale_table_gives_no_signal():
    for src in VARIANTS:
        assert run(src, None) == []                                     # no feature table at all
        assert run(src, feats(last=sec("09:20:00") // 60), sess="nyam") == []          # the table stops 10 minutes early
        assert run(src, feats(drop={567}), sess="nyam") == []           # a hole inside both windows (09:27)
        assert sides(run(src, feats(drop={567}))) == [(s, "long") for s in ("london", "mid", "pm")]
    assert run("book", feats(drop={560}), sess="nyam") != [] and run("flow", feats(drop={560}), sess="nyam") == []
    assert run("book", feats(last=sec("09:30:00") // 60), sess="nyam") != []           # rows up to 09:29 are enough
    assert run("book", feats(last=sec("09:29:00") // 60), sess="nyam") == []


# ---- NaN rows (book_ok False / a minute without a print) -------------------------------------------------------------
def test_a_nan_book_row_is_no_signal_and_the_flow_variant_does_not_need_the_book():
    masked = feats(imb=lambda m: NAN)                                   # a roll day: every book row masked
    assert run("book", masked) == [] and run("both", masked) == []
    assert sides(run("flow", masked)) == [(s, "long") for s in ALL4]    # own tape: valid on roll days
    one = feats(imb=lambda m: NAN if m == 567 else 0.1)                 # one masked snapshot inside the 09:30 window
    assert sides(run("book", one)) == sides(run("both", one)) == [(s, "long") for s in ("london", "mid", "pm")]
    edge = feats(imb=lambda m: NAN if m in (564, 570) else 0.1)         # NaN just outside the window: still a signal
    assert sides(run("book", edge)) == [(s, "long") for s in ALL4]


def test_flow_needs_eight_minutes_with_a_print_and_a_nan_minute_adds_nothing():
    gap = lambda k: (lambda m: NAN if 555 <= m < 555 + k else 50.0)      # noqa: E731 - k no-print minutes before 09:30
    assert sides(run("flow", feats(delta=gap(7)), sess="nyam")) == [("nyam", "long")]       # 8 finite
    assert run("flow", feats(delta=gap(8)), sess="nyam") == []                              # 7 finite
    assert run("both", feats(delta=gap(8)), sess="nyam") == []
    assert sides(run("book", feats(delta=gap(15)), sess="nyam")) == [("nyam", "long")]      # book never reads the flow


# ---- the order's life ------------------------------------------------------------------------------------------------
NYAM_QUIET = [(sec("09:30:00"), sec("11:00:00"))]


@pytest.mark.parametrize("at,filled", [("09:30:00.050", False),         # before the order is live (85 ms placement)
                                       ("09:30:00.085", True), ("10:29:59.5", True),
                                       ("10:30:00", False), ("10:31:00.5", False)])       # cancelled 60 min after the open
def test_the_entry_lives_from_the_open_to_sixty_minutes_later(at, filled):
    h, m, s = at.split(":")
    t = int(h) * 3600 + int(m) * 60 + float(s)
    tr = run("book", feats(), tape(extra=[(t, BASE + 4.0)], quiet=NYAM_QUIET), sess="nyam")
    assert (len(tr) == 1) is filled
    if filled:
        assert tr[0]["entry_ns"] == T0 + int(round(t * S.NS)) and tr[0]["entry_price"] == BASE + 4.25 and tr[0]["side"] == "long"
        assert tr[0]["order_price"] == BASE + OFF and tr[0]["sl"] == BASE + 4.25 - STOP


def test_no_fill_in_the_hour_means_no_trade_in_the_session():
    assert run("book", feats(), tape(quiet=NYAM_QUIET), sess="nyam") == []            # excursions resume at 11:10: too late
    assert sides(run("book", feats(), tape(quiet=NYAM_QUIET))) == [(s, "long") for s in ("london", "mid", "pm")]


def test_one_trade_per_session_even_after_a_stop_out():
    """Stopped out 5 minutes after the fill; the price comes back through the old trigger again: no second entry."""
    t = tape(extra=[(sec("09:45:00"), BASE - 25.0)])
    tr = run("book", feats(), t, sess="nyam")
    assert len(tr) == 1 and tr[0]["exit_reason"] == "sl" and tr[0]["exit_ns"] == T0 + sec("09:45:00") * S.NS
    assert tr[0]["sl"] == BASE + 4.25 - STOP and tr[0]["exit_price"] == BASE - 25.25
    assert len(run("book", feats(), t)) == 4                            # the other sessions still take their one trade


def test_the_decision_needs_three_completed_atr_bars():
    """Fewer than 3 completed 30-minute bars before the open (Template WARM) -> no order: the family never guesses an ATR.
    The tape starts late and alternates BASE / BASE + 2 every 30 s (last print before 03:00 = BASE, ATR30 = 2)."""
    def late(start):
        a = sec(start)
        ks = range((sec("06:00:00") - a) // 30)
        return S.Tape("NQ", D, "NQH4", [T0 + (a + 30 * k) * S.NS for k in ks], [BASE + 2.0 * ((k + 1) % 2) for k in ks], [1] * len(ks))
    assert run("book", feats(), late("02:10:00"), sess="london") == []                 # 2 bars at 03:00
    tr = run("book", feats(), late("01:10:00"), sess="london")                         # 4 bars at 03:00
    assert len(tr) == 1 and tr[0]["order_price"] == BASE + 0.5 and tr[0]["sl"] == tr[0]["entry_price"] - 6.0


# ---- real in-sample days: the trade's side against the table, read without ctx ---------------------------------------
REAL_DAYS = ["2021-10-05", "2022-03-15", "2022-06-13", "2023-03-22", "2023-08-09", "2024-04-10"]


@pytest.mark.parametrize("src", list(VARIANTS))
def test_real_days_every_trade_matches_the_table_and_the_order_rules(src):
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    if not all((S.CACHE / f"l2feat_NQ_{y}.parquet").exists() for y in (2021, 2022, 2023, 2024)):
        pytest.skip("data-layer cache not built")
    name, cls = f"open_dir_{src}", VARIANTS[src]
    loader = S.L2Features(cls.FEATURES)
    try:
        res = S.run(cls, families.screen_inputs(name, "30"), days=REAL_DAYS, workers=1, features=loader)
    except FileNotFoundError as e:
        pytest.skip(f"tape not available: {e}")
    assert res["skipped_by_error"] == 0 and res["both_sides_sessions"] == 0 and res["sessions"] == len(REAL_DAYS)
    seen = set()
    for t in res["trades"]:
        d = dt.date.fromisoformat(t["date"])
        s = S.session_of(t["entry_ms"])
        assert s in OD.OPENS and (t["date"], s) not in seen             # never asia, one trade per session
        seen.add((t["date"], s))
        open_ns = S.et_ns(d, "00:00") + OD.OPENS[s] * S.NS
        assert open_ns // 10 ** 6 < t["entry_ms"] < (open_ns + OD.CANCEL_S * S.NS) // 10 ** 6      # in [open, open + 60 min)
        assert t["entry_ms"] < (S.et_ns(d, "00:00") + (S.SESS[s][1] - 300) * S.NS) // 10 ** 6      # never the last 5 minutes
        assert t["order_price"] is not None and t["sl"] is not None and t["tp"] is None
        assert t["oco"] is False and t["both_sides"] is False
        f = loader(d)
        n = int(np.searchsorted(f.usable_ns, open_ns, side="right"))    # rows usable at the open, straight from the table
        assert f.usable_ns[n - 1] == open_ns
        want = 0
        if src != "flow":
            w = f.cols["imb10"][n - 5:n].astype(np.float64)
            assert np.isfinite(w).all()
            want = int(np.sign(w.sum()))
        if src != "book":
            w = f.cols["f_delta"][n - 15:n].astype(np.float64)
            fs = int(np.sign(np.nansum(w)))
            assert np.isfinite(w).sum() >= 8 and (src == "flow" or fs == want)
            want = fs
        assert want != 0 and t["side"] == ("long" if want > 0 else "short")
