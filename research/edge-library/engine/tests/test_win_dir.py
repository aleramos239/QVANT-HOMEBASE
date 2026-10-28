"""WIN_DIR (families/win_dir.py): a clock entry, the side from a direction rule. Synthetic minute days; no net or win rate read."""
import l2sim as S
from families import blocks as B
from families import win_dir as W  # noqa: F401  (registers the family)
from test_noise import DAILY, D, bar, day, flat, tape_of

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "exit_bars": 3}


def sides(params, bars, daily=DAILY):
    st = B.WRAPPED["win_dir"]({**BASE, **params})
    st.ROLLS = frozenset()
    return [t["side"] for t in S.run_session(st, tape_of(bars), daily=daily, on_error="raise").trades]


def ramp(n, step, start=15000.0):
    return [bar(start + i * step, start + (i + 1) * step) for i in range(n)]


def test_ret_follows_the_window_return_and_fade_flips_it():
    up = day(ramp(30, 1.0) + flat(30, 15030.0))
    dn = day(ramp(30, -1.0) + flat(30, 14970.0))
    p = {"src": "ret", "a_start": "09:30", "a_end": "10:00", "off_min": 30}
    assert sides(p, up) == ["long"] and sides(p, dn) == ["short"]
    assert sides({**p, "mode": "fade"}, up) == ["short"] and sides({**p, "mode": "fade"}, dn) == ["long"]


def test_a_window_that_ends_after_the_entry_is_not_read():
    assert sides({"src": "ret", "a_start": "09:30", "a_end": "10:00", "off_min": 15}, day(ramp(30, 1.0))) == []


def test_a_flat_window_is_no_trade():
    assert sides({"src": "ret", "off_min": 30}, day(flat(60))) == []


def test_dir_keeps_one_side_only():
    up, dn = day(ramp(30, 1.0)), day(ramp(30, -1.0))
    p = {"src": "ret", "off_min": 30, "dir": "long"}
    assert sides(p, up) == ["long"] and sides(p, dn) == []


def test_open_and_gap_read_the_last_price():
    assert sides({"src": "open", "a_start": "09:30", "off_min": 30}, day(ramp(30, 1.0))) == ["long"]
    # the prior daily close is 15050 (test_noise.rows): a tape at 15000 is a gap down
    assert sides({"src": "gap", "off_min": 5}, day(flat(30))) == ["short"]


def test_the_daily_rules_read_the_days_before_the_trade_date_only():
    rows = [{**r, "c": 15000.0 + i} for i, r in enumerate(DAILY)]                  # closes rising 15000 .. 15024
    assert sides({"src": "retd", "n_d": 5, "off_min": 5}, day(flat(30)), rows) == ["long"]
    assert sides({"src": "smad", "n_d": 5, "off_min": 5}, day(flat(30)), rows) == ["long"]
    assert sides({"src": "smad", "n_d": 300, "off_min": 5}, day(flat(30)), rows) == []        # too few daily bars: no trade
    lo = [{**r, "h": 15100.0, "l": 14900.0, "c": 14950.0} for r in DAILY]           # closed in the lower half of its range
    assert sides({"src": "loc", "off_min": 5}, day(flat(30)), lo) == ["short"]


def test_one_trade_a_session():
    assert len(sides({"src": "ret", "off_min": 30, "max_tr": 5}, day(ramp(30, 1.0) + ramp(30, 1.0, 15030.0)))) == 1


# ---- the sources added 2026-10-26 (D45 D56 D57 D60 E64 E68-E70 E72-E75) -----------------------------------------------------------------
def test_pret_reads_the_prior_session_and_the_evening_ret_reads_this_one(monkeypatch):
    calls = []
    monkeypatch.setattr(W, "window_ret", lambda root, iso, day, a, b: calls.append((iso, str(day), a, b)) or 5.0)
    assert sides({"src": "pret", "a_start": "15:00", "a_end": "16:00", "off_min": 5}, day(flat(30))) == ["long"]
    assert calls[-1][0] == DAILY[-1]["date"] and calls[-1][2:] == ("15:00", "16:00")          # the prior trade date, its own clock
    assert sides({"src": "ret", "a_start": "18:00", "a_end": "23:59", "off_min": 5}, day(flat(30))) == ["long"]
    assert calls[-1][0] == str(D) and calls[-1][1] == str(D - __import__("datetime").timedelta(days=1))     # this session, the evening before
    monkeypatch.setattr(W, "window_ret", lambda *a: None)
    assert sides({"src": "pret", "off_min": 5}, day(flat(30))) == []                           # no bars = no trade


def test_rexp_follows_a_wide_prior_day_and_fades_a_narrow_one():
    rows = [{**r, "c": 15000.0 + i, "h": 15100.0, "l": 15000.0} for i, r in enumerate(DAILY)]    # closes rising, every range 100
    wide = rows[:-1] + [{**rows[-1], "h": 15300.0}]                                              # last day's range 300 > the mean
    narrow = rows[:-1] + [{**rows[-1], "h": 15010.0}]
    p = {"src": "rexp", "n_d": 10, "off_min": 5}
    assert sides(p, day(flat(30)), wide) == ["long"] and sides(p, day(flat(30)), narrow) == ["short"]


def test_gapagree_trades_only_when_the_overnight_move_and_the_window_agree():
    p = {"src": "gapagree", "a_start": "09:30", "a_end": "10:00", "off_min": 30}
    up = day(ramp(30, 1.0) + flat(30, 15030.0))                       # opens 15000, the prior close is 15050 (test_noise): a gap down
    assert sides(p, up) == []                                         # window up, overnight down: no trade
    dn = day(ramp(30, -1.0) + flat(30, 14970.0))
    assert sides(p, dn) == ["short"]                                  # both down


def test_vol5_follows_a_loud_open_and_fades_a_quiet_one(monkeypatch):
    p = {"src": "vol5", "a_start": "09:30", "a_end": "09:35", "off_min": 5}
    g = ramp(5, 1.0)                                                  # five up minutes, volume 40 each = 200
    monkeypatch.setattr(W, "ref_mean", lambda *a: 100.0)
    assert sides(p, day(g + flat(30, 15005.0))) == ["long"]
    monkeypatch.setattr(W, "ref_mean", lambda *a: 400.0)
    assert sides(p, day(g + flat(30, 15005.0))) == ["short"]
    monkeypatch.setattr(W, "ref_mean", lambda *a: None)
    assert sides(p, day(g + flat(30, 15005.0))) == []


def test_delta_and_vslope(monkeypatch):
    p = {"src": "delta", "a_start": "09:30", "a_end": "09:45", "off_min": 30}
    monkeypatch.setattr(W.flowtab, "window", lambda root, iso, a, b: (1000, -50, 0, 0))
    assert sides(p, day(flat(60))) == ["short"]
    assert sides({**p, "a_end": "10:30"}, day(flat(60))) == []        # the window ends after the entry: not read
    monkeypatch.setattr(W.flowtab, "window", lambda *a: None)
    assert sides(p, day(flat(60))) == []
    q = {"src": "vslope", "a_start": "09:30", "a_end": "09:45", "off_min": 60}
    assert sides(q, day(flat(15) + ramp(45, 1.0, 15000.0)), ) == ["long"]


def test_pd_bracket_arms_both_prior_day_levels_and_the_first_break_trades():
    st = B.WRAPPED["pd_bracket"]({**BASE, "off_min": 5, "exit_bars": 3})
    st.ROLLS = frozenset()
    rows = [{**r, "h": 15040.0, "l": 14960.0} for r in DAILY]
    t = S.run_session(st, tape_of(day(flat(5) + ramp(20, 3.0))), daily=rows, on_error="raise").trades
    assert [x["side"] for x in t] == ["long"]


def test_the_evening_instance_reads_the_prior_session_for_pret(monkeypatch):
    import datetime as dt
    from test_blocks import minute_tape
    calls = []
    monkeypatch.setattr(W, "window_ret", lambda root, iso, day_, a, b: calls.append(iso) or -3.0)
    st = B.WRAPPED["win_dir"]({**BASE, "sess": "eve", "tf": "5", "src": "pret", "a_start": "09:30", "a_end": "16:00", "off_min": 120, "exit_bars": 3})
    st.ROLLS = frozenset()
    tape = minute_tape([(15000.0, 15001.0, 14999.0, 15000.0, 40)] * 240, "18:00", D - dt.timedelta(days=1))
    tape.date = D
    t = S.run_session(st, tape, daily=DAILY, on_error="raise", window=st.eve_window, segment="eve").trades
    assert [x["side"] for x in t] == ["short"] and calls[-1] == DAILY[-1]["date"]
