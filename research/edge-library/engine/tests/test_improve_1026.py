"""improve_1026 (families/improve_1026.py): the code variants of the g93 / noise / g94 / g92 ideas. Synthetic minute days; no net or win rate read."""
import l2sim as S
from families import blocks as B
from families import improve_1026 as I  # noqa: F401  (registers the families)
from test_flex import BIG, go
from test_noise import DAILY, bar, day, flat, tape_of
from test_orb830 import HI, LO, PX, hold
from test_orb830 import day as qday

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "exit_bars": 0}
PD = [{**r, "h": 15040.0, "l": 14960.0} for r in DAILY]


def run(name, params, bars, daily=DAILY):
    st = B.WRAPPED[name]({**BASE, **params})
    st.ROLLS = frozenset()
    return S.run_session(st, tape_of(bars), daily=daily, on_error="raise").trades


def sides(name, params, bars, daily=DAILY):
    return [t["side"] for t in sorted(run(name, params, bars, daily), key=lambda t: t["entry_ms"])]


def ramp(n, step, start=15000.0):
    return [bar(start + i * step, start + (i + 1) * step) for i in range(n)]


# ---- win_bracket_rev ---------------------------------------------------------------------------------------------------------------------------
def test_the_bracket_reverses_after_the_first_trade_stops_out_through_the_far_edge():
    P = {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "stop_mode": "struct", "stop_val": 1.0}
    edits = {"09:50": (PX, HI + 10, PX, HI + 8, 40), "10:00": (HI + 8, HI + 8, LO - 30, LO - 30, 40)}
    edits.update({f"10:{m:02d}": hold(LO - 30) for m in range(1, 60)})
    edits.update({f"09:{m:02d}": hold(HI + 8) for m in range(51, 60)})
    bars = qday(edits)
    for h in range(11, 16):
        bars[h * 60:(h + 1) * 60] = [hold(LO - 30)] * 60
    st, res = go(B.WRAPPED["win_bracket_rev"], P, bars)
    assert [t["side"] for t in sorted(res.trades, key=lambda t: t["entry_ms"])] == ["long", "short"]
    st, res = go(B.WRAPPED["win_bracket"], P, bars)
    assert [t["side"] for t in res.trades] == ["long"]                                       # the plain bracket stops at one


def test_the_bracket_does_not_reverse_while_the_first_trade_holds():
    P = {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "stop_mode": "struct", "stop_val": 1.0}
    edits = {"09:50": (PX, HI + 10, PX, HI + 8, 40)}
    edits.update({f"09:{m:02d}": hold(HI + 8) for m in range(51, 60)})
    bars = qday(edits)
    for h in range(10, 16):
        bars[h * 60:(h + 1) * 60] = [hold(HI + 8)] * 60
    assert [t["side"] for t in go(B.WRAPPED["win_bracket_rev"], P, bars)[1].trades] == ["long"]


# ---- noise_band_x ------------------------------------------------------------------------------------------------------------------------------
NB = {"k": 0.25, "anchor": "rth", "max_tr": 1}
UP = day(ramp(40, 1.0) + flat(40, 15040.0) + ramp(20, -1.0, 15040.0) + flat(60, 15020.0))      # band 15025: through at the 26th minute, back inside later


def test_x_in_flattens_when_a_close_falls_back_inside_the_band():
    plain = run("noise_band_x", NB, UP)
    out = run("noise_band_x", {**NB, "x_in": "on"}, UP)
    assert len(plain) == len(out) == 1 and out[0]["exit_ms"] < plain[0]["exit_ms"] and out[0]["exit_reason"] == "band"


def test_adx_min_delays_a_one_bar_jump_until_the_adx_has_built_up_and_passes_a_trend():
    jump = day([bar(15000.0, 15030.0)] + flat(60, 15030.0))                                   # one gap through the band: the ADX starts near 0
    t0, t1 = run("noise_band_x", {**NB, "adx_min": 0.0}, jump), run("noise_band_x", {**NB, "adx_min": 20.0}, jump)
    assert len(t0) == len(t1) == 1 and t1[0]["entry_ms"] > t0[0]["entry_ms"]
    assert sides("noise_band_x", {**NB, "adx_min": 20.0}, UP) == ["long"]                     # a clean ramp: ADX far above 20


# ---- win_break_vol -----------------------------------------------------------------------------------------------------------------------------
def test_a_break_bar_needs_vol_m_times_the_normal_volume(monkeypatch):
    P = {"tf": "5", "sess": "nyam", "r_start": "09:30", "r_end": "09:45", "stop_mode": "struct", "stop_val": 1.0, "mode": "follow", "entry": "market"}
    edits = {"09:50": (PX, HI + 10, PX, HI + 8, 40)}
    edits.update({f"09:{m:02d}": hold(HI + 8) for m in range(51, 60)})
    bars = qday(edits)
    for h in range(10, 16):
        bars[h * 60:(h + 1) * 60] = [hold(HI + 8)] * 60
    cls = B.WRAPPED["win_break_vol"]
    monkeypatch.setattr(cls, "blk_rvol", lambda self: (200.0, 100.0))
    assert [t["side"] for t in go(cls, {**P, "vol_m": 1.5}, bars)[1].trades] == ["long"]
    monkeypatch.setattr(cls, "blk_rvol", lambda self: (100.0, 100.0))
    assert go(cls, {**P, "vol_m": 1.5}, bars)[1].trades == []
    assert [t["side"] for t in go(cls, {**P, "vol_m": 0.0}, bars)[1].trades] == ["long"]


def test_a_sealed_reference_date_counts_as_no_tape_not_a_crash(monkeypatch):
    def sealed(root, iso):
        raise S.HoldoutSealed(iso)
    monkeypatch.setattr(B, "cum_volume", sealed)
    from families.improve_1026 import _rvol_no_seal
    assert _rvol_no_seal(lambda: B.cum_volume("NQ", "2026-09-23")) is None
    assert B.cum_volume is sealed                                                             # put back after the call


# ---- pd_bracket_x ------------------------------------------------------------------------------------------------------------------------------
def test_gate_loc_arms_only_the_side_of_yesterdays_close_location():
    up = day(flat(5) + ramp(20, 3.0))
    hi_c = [{**r, "c": 15030.0} for r in PD]                                                  # closed above the middle (15000)
    lo_c = [{**r, "c": 14970.0} for r in PD]
    p = {"off_min": 5}
    assert sides("pd_bracket_x", {**p, "dgate": "loc"}, up, hi_c) == ["long"]
    assert sides("pd_bracket_x", {**p, "dgate": "loc"}, up, lo_c) == []
    assert sides("pd_bracket_x", {**p, "dgate": "off"}, up, lo_c) == ["long"]


def test_gate_sma_follows_the_close_against_its_n_day_mean():
    up = day(flat(5) + ramp(20, 3.0))
    rising = [{**r, "c": 14900.0 + i, "h": 15040.0, "l": 14960.0} for i, r in enumerate(PD)]
    falling = [{**r, "c": 15100.0 - i, "h": 15040.0, "l": 14960.0} for i, r in enumerate(PD)]
    p = {"off_min": 5, "dgate": "sma", "n_d": 5}
    assert sides("pd_bracket_x", p, up, rising) == ["long"] and sides("pd_bracket_x", p, up, falling) == []


def test_extra_levels_add_the_overnight_range_and_the_rearm_catches_a_side_that_was_passed():
    up = day(flat(5) + ramp(8, 1.0))                                                          # rises 8 points: past the overnight high only
    assert sides("pd_bracket_x", {"off_min": 5, "lvl": "pd"}, up, PD) == []
    assert sides("pd_bracket_x", {"off_min": 5, "lvl": "pd_on"}, up, PD) == ["long"]
    g = flat(25, 15050.0) + [bar(15050.0, 15000.0)] + flat(34, 15000.0) + ramp(30, 3.0, 15000.0)    # above the prior high at 09:30, back inside by 10:00
    day2 = day(g, pre=15050.0)
    assert sides("pd_bracket_x", {"off_min": 0}, day2, PD) == []                              # the long leg was passed at 09:30 and is never armed
    assert sides("pd_bracket_x", {"off_min": 0, "re_min": 30, "alive_to": "12:00"}, day2, PD) == ["long"]


# ---- pd_fade -----------------------------------------------------------------------------------------------------------------------------------
def test_a_break_taken_back_inside_in_the_window_is_faded_and_a_held_break_is_not():
    p = {"tf": "5", "wait": "15", "stop_mode": "pts", "stop_val": 500.0}
    failed = day(flat(14, 15000.0) + [(15000.0, 15050.0, 15000.0, 15030.0, 40)] + flat(45, 15030.0))
    held = day(flat(14, 15000.0) + [(15000.0, 15050.0, 15000.0, 15045.0, 40)] + flat(45, 15045.0))
    assert sides("pd_fade", p, failed, PD) == ["short"]
    assert sides("pd_fade", p, held, PD) == []
