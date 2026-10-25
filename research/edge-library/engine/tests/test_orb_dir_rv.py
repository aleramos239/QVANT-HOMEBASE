"""ORB_DIR_RV: the 5-minute opening range breakout with the paper's volume filter (families/orb_dir_rv.py), written with the family.
Synthetic days with exact numbers: flat at 15000 to 09:30, five opening minutes built by hand, then the path after. The 14-day mean
volume is patched (OD.ref_mean) except in the test of ref_mean itself. No net, win rate or profit factor is read."""
import numpy as np
import pytest

import l2sim as S
from families import blocks as B
from families import orb_dir_rv as OD
from test_blocks import D, DAILY, minute_tape

PX, V = 15000.0, 40
MS0 = S.et_ns(D, "00:00") // 1_000_000
BASE = {"hold_to": "day", "tf": "5", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
OPEN = 570                                          # minute index of 09:30


def q(n, px, v=V):
    return [(px, px, px, px, v)] * n


GREEN = [(PX, PX + 4, PX - 2, PX + 3, V), (PX + 3, PX + 8, PX + 2, PX + 7, V), (PX + 7, PX + 12, PX + 6, PX + 9, V),
         (PX + 9, PX + 10, PX + 5, PX + 6, V), (PX + 6, PX + 8, PX + 5, PX + 8, V)]          # open 15000, close 15008, high 15012, low 14998
RED = [(2 * PX - o, 2 * PX - l, 2 * PX - h, 2 * PX - c, v) for o, h, l, c, v in GREEN]           # the mirror: high 15002, low 14988
DOJI = GREEN[:4] + [(PX + 6, PX + 8, PX - 2, PX, V)]                                           # closes at its open


def day(opening, after):
    """00:00 .. 15:59: flat to 09:30, the five opening minutes, then `after` = [(o, h, l, c, v)] from 09:35, flat at its last close."""
    b = q(OPEN, PX) + list(opening) + list(after)
    return b + q(960 - len(b), b[-1][3])


def run(monkeypatch, bars, ref=150.0, params=None, cls=OD.OrbDirRv):
    """-> [(the fill's minute of the day, side)]; ref = the patched 14-day mean of the five opening minutes (their volume here is 200)."""
    monkeypatch.setattr(OD, "ref_mean", lambda root, dates, a, b: ref)
    st = cls({**BASE, **(params or {})})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), daily=list(DAILY), on_error="raise")
    return [((t["entry_ms"] - MS0) // 60000, t["side"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]


UP = [(PX + 8, PX + 20, PX + 8, PX + 20, V)] + q(30, PX + 20)          # a break above 15012.25 in the first minute after 09:35
DOWN = [(PX + 8, PX + 8, PX - 10, PX - 10, V)] + q(30, PX - 10)        # a break below 14997.75


def test_a_green_range_on_enough_volume_buys_the_break_of_its_high(monkeypatch):
    got = run(monkeypatch, day(GREEN, UP))
    assert [s for _, s in got] == ["long"] and got[0][0] == OPEN + 5


def test_a_green_range_never_sells_the_break_of_its_low(monkeypatch):
    assert run(monkeypatch, day(GREEN, DOWN)) == []


def test_a_red_range_sells_the_break_of_its_low_and_never_buys_its_high(monkeypatch):
    assert [s for _, s in run(monkeypatch, day(RED, [(PX - 8, PX - 8, PX + 10, PX + 10, V)] + q(30, PX + 10)))] == []
    assert [s for _, s in run(monkeypatch, day(RED, [(PX - 8, PX - 8, PX - 20, PX - 20, V)] + q(30, PX - 20)))] == ["short"]


def test_a_doji_range_places_no_order(monkeypatch):
    assert run(monkeypatch, day(DOJI, UP)) == []


def test_volume_below_rv_times_the_mean_places_no_order_and_the_setting_moves_the_line(monkeypatch):
    bars = day(GREEN, UP)                                               # the range trades 200
    assert run(monkeypatch, bars, ref=250.0) == []                      # 200 / 250 = 0.8 < 1.0
    assert len(run(monkeypatch, bars, ref=250.0, params={"rv": 0.8})) == 1
    assert run(monkeypatch, bars, ref=150.0, params={"rv": 1.5}) == []  # 200 / 150 = 1.33 < 1.5
    assert len(run(monkeypatch, bars, ref=200.0)) == 1                  # exactly 100 % counts


def test_no_reference_means_no_trade(monkeypatch):
    assert run(monkeypatch, day(GREEN, UP), ref=None) == []


def test_a_missing_09_30_bar_means_no_trade(monkeypatch):
    bars = day(GREEN, UP)
    bars[OPEN] = None
    tape = minute_tape(bars[:OPEN], "00:00"), minute_tape(bars[OPEN + 1:], "09:31")
    monkeypatch.setattr(OD, "ref_mean", lambda root, dates, a, b: 150.0)
    st = OD.OrbDirRv(BASE)
    st.ROLLS = frozenset()
    t = S.Tape("NQ", D, "NQM3", *(np.concatenate([getattr(x, f) for x in tape]) for f in ("ts", "px", "size")))
    assert S.run_session(st, t, daily=list(DAILY), on_error="raise").trades == []


def test_the_wrapped_class_the_hunt_runs_trades_like_the_bare_family(monkeypatch):
    bars = day(GREEN, UP)
    assert run(monkeypatch, bars, cls=B.WRAPPED["orb_dir_rv"]) == run(monkeypatch, bars)


def test_the_family_is_registered_and_one_sided():
    import families
    assert "orb_dir_rv" in B.BASES and families.REGISTRY["orb_dir_rv"][2] is False and not families.ERRORS


def test_ref_mean_is_the_mean_of_the_last_14_dates_window_and_none_without_them(monkeypatch):
    a, b = 34200, 34500
    i, j = a // 60 - B.MIN0, b // 60 - B.MIN0
    dates = [f"2023-02-{d:02d}" for d in range(1, 19)]                                  # 18 dates; the last 14 are read
    def cum(root, iso):
        n = int(iso[-2:])                                                               # date n trades n per opening minute
        v = np.zeros(B.NMIN, np.int64)
        v[i:j] = n
        return np.concatenate(([0], np.cumsum(v)))
    monkeypatch.setattr(B, "cum_volume", cum)
    assert OD.ref_mean("NQ", dates, a, b) == pytest.approx(5 * np.mean(range(5, 19)))
    assert OD.ref_mean("NQ", dates[:13], a, b) is None
    monkeypatch.setattr(B, "cum_volume", lambda root, iso: None if iso.endswith("10") else cum(root, iso))
    assert OD.ref_mean("NQ", dates, a, b) is None                                       # a date without a tape
    def sealed(root, iso):
        if iso.endswith("10"):
            raise OD.HoldoutSealed(iso)                                                     # a 2025+ date the cache lacks
        return cum(root, iso)
    monkeypatch.setattr(B, "cum_volume", sealed)
    assert OD.ref_mean("NQ", dates, a, b) is None


def test_the_pass_is_the_morning_only():
    st = OD.OrbDirRv({**BASE, "sess": "all"})
    assert list(st.sessions()) == ["nyam"]
