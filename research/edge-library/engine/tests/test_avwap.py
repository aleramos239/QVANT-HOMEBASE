"""AVWAP: the anchored-VWAP lines and their three entry triggers (families/avwap.py), written with the family (VWAP hunt 2026-10-20).

THE RULES UNDER TEST (module docstring of families/avwap.py):
    a line   = volume-weighted (h + l + c) / 3 of 1-minute bars from its anchor (rth 09:30, london 03:00, midnight 00:00, globex 18:00 the
               evening before, week, pdh / pdl / onh / onl = the minute of that high / low) or a fixed level (pdvwap)
    seal     = a past tape opens with the switch of ITS OWN date; of today's tape only the minutes before 00:00 ET are read
    avwap_touch = vwap_touch's rule on any line; avwap_flip = vwap_flip's rule on any line (+ vol_m, + also); orb_vwap_pb = the first
               pullback to the 09:30 VWAP after a close beyond the 09:30 range
Synthetic days with EXACT numbers (a quiet day at 15000) and synthetic past minutes (the loader `minutes` replaced); the parity tests
hold the new families trade for trade to vwap_touch / vwap_flip where the lines are the same. One real build day checks the minutes
built from a tape against the engine's own 1-minute bars. No net, win rate or profit factor is read.
"""
import numpy as np
import pytest

import families
import l2sim as S
from families import avwap as AV
from families import blocks as B
from families import port3 as P3
from families import vwap_touch as VT
from test_blocks import DAILY, D, TICK, minute_tape, real_days
from test_vwap_touch import AWAY_UP, PX, W50, day, hold, sec, tk, vwap

MS0 = S.et_ns(D, "00:00") // 1_000_000
MON = DAILY[-1]["date"]                              # 2023-03-13, the Monday before D (a Tuesday): the same ISO week
FRI = DAILY[-2]["date"]                              # the week before


def mins(rows):
    a = np.array(rows, float)
    return {"sec": a[:, 0].astype(np.int64), "h": a[:, 1], "l": a[:, 2], "tpv": a[:, 4] * (a[:, 1] + a[:, 2] + a[:, 3]) / 3.0, "v": a[:, 4]}


def flat_rows(a, b, px, v=40):
    return [(s, px + TICK, px - TICK, px, v) for s in range(a, b, 60)]


# the past the families may read: Monday's whole session, today's evening (18:00-24:00 the day before) -- and a POISON day part of
# today's tape (heavy minutes at 99000 from 00:00 on) that must never enter a line
EVE = flat_rows(-21600, 0, 15020.0, 400)
POISON = flat_rows(0, 61200, 99000.0, 10 ** 6)
MON_ROWS = flat_rows(-21600, 34200, 14990.0, 40) + [(34200, 15050.0, 14990.0, 15000.0, 400)] + flat_rows(34260, 50400, 15000.0, 40) \
    + [(50400, 15000.0 + TICK, 14900.0, 14950.0, 400)] + flat_rows(50460, 61200, 14960.0, 40)
PAST = {MON: mins(MON_ROWS), D.isoformat(): mins(EVE + POISON), FRI: mins(flat_rows(-21600, 61200, 14000.0, 40))}


@pytest.fixture
def past(monkeypatch):
    monkeypatch.setattr(AV, "minutes", lambda root, iso: PAST.get(iso))
    return PAST


def brute(rows, a=None, b=None):
    x = mins(rows)
    m = np.ones(len(x["sec"]), bool) if a is None else (x["sec"] >= a) & (x["sec"] < b)
    return float(x["tpv"][m].sum()), float(x["v"][m].sum())


def day_rows(bars, upto):
    return [(i * 60, h, lo, c, v) for i, (o, h, lo, c, v) in enumerate(bars[:upto])]


BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}


def run(cls, params, bars, rolls=()):
    st = cls({**BASE, **params})
    st.ROLLS = frozenset(rolls)
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(**getattr(cls, "SCREEN_RUN", {})), daily=list(DAILY), on_error="raise")
    return st, [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])], res


# ---- registration --------------------------------------------------------------------------------------------------------------
def test_the_families_are_registered_and_wrapped():
    assert families.ERRORS == {}
    for n in ("avwap_touch", "avwap_flip", "orb_vwap_pb"):
        assert n in families.REGISTRY and families.MODULE_OF[n] == "avwap" and B.WRAPPED[n].__name__ == f"B_{n}"


# ---- the lines -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,a", [("rth", 34200), ("london", 10800), ("midnight", 0)])
def test_a_clock_line_runs_from_its_anchor_on_the_days_own_bars(past, kind, a):
    bars = day({"04:00": (PX, 15100.0, PX - TICK, PX, 4000), "09:50": (PX, 15001.0, PX - TICK, 15001.0, 40)})
    st, _, _ = run(AV.AvwapTouch, {"line": kind}, bars)
    p, v = brute(day_rows(bars, st.mi), a, 10 ** 9)
    assert st.ln.value() == pytest.approx(p / v)


def test_the_globex_line_adds_this_evening_and_never_todays_tape_after_midnight(past):
    bars = day({"09:50": (PX, 15001.0, PX - TICK, 15001.0, 40)})
    st, _, _ = run(AV.AvwapTouch, {"line": "globex"}, bars)
    p1, v1 = brute(EVE)
    p2, v2 = brute(day_rows(bars, st.mi))
    assert st.ln.value() == pytest.approx((p1 + p2) / (v1 + v2))
    assert st.ln.value() < 16000                                                          # the poison (99000) never entered


def test_the_week_line_adds_the_weeks_earlier_sessions_and_not_last_weeks(past):
    bars = day()
    st, _, _ = run(AV.AvwapTouch, {"line": "week"}, bars)
    parts = [brute(MON_ROWS), brute(EVE), brute(day_rows(bars, st.mi))]
    assert st.ln.value() == pytest.approx(sum(p for p, _ in parts) / sum(v for _, v in parts))


def test_a_roll_inside_the_week_restarts_it(past):
    bars = day()
    st, _, _ = run(AV.AvwapTouch, {"line": "week"}, bars, rolls=[D.isoformat()])
    parts = [brute(EVE), brute(day_rows(bars, st.mi))]
    assert st.ln.value() == pytest.approx(sum(p for p, _ in parts) / sum(v for _, v in parts))


def test_yesterdays_closing_vwap_is_a_fixed_level_of_its_0930_1600_minutes(past):
    st, _, _ = run(AV.AvwapTouch, {"line": "pdvwap"}, day())
    p, v = brute(MON_ROWS, 34200, 57600)
    assert st.ln.value() == pytest.approx(p / v)


@pytest.mark.parametrize("kind,at", [("pdh", 34200), ("pdl", 50400)])
def test_the_prior_day_high_and_low_lines_start_at_the_minute_that_printed_it(past, kind, at):
    bars = day()
    st, _, _ = run(AV.AvwapTouch, {"line": kind}, bars)
    parts = [brute(MON_ROWS, at, 10 ** 9), brute(EVE), brute(day_rows(bars, st.mi))]
    assert st.ln.value() == pytest.approx(sum(p for p, _ in parts) / sum(v for _, v in parts))


def test_no_prior_day_line_on_a_roll_day(past):
    for kind in ("pdvwap", "pdh", "pdl"):
        st, got, _ = run(AV.AvwapTouch, {"line": kind}, day({"09:50": AWAY_UP}), rolls=[D.isoformat()])
        assert st.ln.value() is None and got == []


@pytest.mark.parametrize("kind", ["onh", "onl"])
def test_the_overnight_lines_start_at_the_overnight_extreme_and_exist_only_from_0930(past, kind):
    bars = day({"05:00": (PX, 15200.0, PX - TICK, PX, 400), "06:00": (PX, PX + TICK, 14800.0, PX, 400)})
    at = 5 * 3600 if kind == "onh" else 6 * 3600
    ln = AV.Line(kind, "NQ", D.isoformat(), DAILY, frozenset())
    rows = day_rows(bars, 960)
    for r in rows:
        if r[0] == 34200:
            assert ln.value() is None                                                  # not known before 09:30
        ln.feed((r[0], None, r[1], r[2], r[3], r[4]))
    p, v = brute(rows, at, 10 ** 9)
    assert ln.value() == pytest.approx(p / v)


def test_a_past_tape_opens_with_the_seal_of_its_own_date(monkeypatch):
    seen = []
    monkeypatch.setattr(S, "load_tape", lambda iso, root, allow_holdout=False: seen.append((iso, allow_holdout)))
    AV._MIN.clear()
    AV.minutes("NQ", "2025-06-30")
    AV.minutes("NQ", "2025-07-01")
    assert seen == [("2025-06-30", S.ALLOW_BP), ("2025-07-01", S.ALLOW_BT)]
    AV._MIN.clear()


def test_a_prior_session_that_is_not_before_today_is_look_ahead():
    with pytest.raises(S.LookAheadError):
        AV.Line("pdvwap", "NQ", MON, DAILY, frozenset())


def test_of_todays_tape_only_the_evening_is_returned(past):
    ev = AV.evening("NQ", D.isoformat())
    assert len(ev["sec"]) == len(EVE) and (ev["sec"] < 0).all()


# ---- the families --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("line,anchor", [("midnight", "day"), ("london", "london"), ("rth", "us")])
def test_avwap_touch_on_a_clock_line_is_vwap_touch_trade_for_trade(past, line, anchor):
    days = [day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, W50 - TICK, 15010.0, 40)}),
            day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, W50, 15003.0, 40),
                 **hold("09:56", "09:59", 15003.0), "10:00": (15003.0, 15010.0, 15003.0, 15010.0, 40),
                 **hold("10:01", "10:04", 15010.0), "10:05": (15010.0, 15010.0, 14999.0, 15010.0, 40)})]
    for bars in days:
        _, a, _ = run(AV.AvwapTouch, {"line": line, "away": 24, "near": 3, "max_tr": 5}, bars)
        st = VT.VwapTouch({**BASE, "anchor": anchor, "away": 24, "near": 3, "max_tr": 5})
        st.ROLLS = frozenset()
        res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(**VT.VwapTouch.SCREEN_RUN), daily=list(DAILY), on_error="raise")
        b = [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]
        assert a == b and a


def test_avwap_touch_also_blocks_a_long_below_the_second_line(past):
    bars = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, W50 - TICK, 15010.0, 40)})
    w = tk(vwap(bars, 570, S._sec("09:55") // 60))                                         # the 09:30 VWAP when 09:54 has ended
    _, got, _ = run(AV.AvwapTouch, {"line": "rth", "away": 24, "also": "midnight"}, bars)
    assert got == [(sec(9, 55, 15), "long", w)]                                            # 15010 is above the midnight VWAP
    _, got, _ = run(AV.AvwapTouch, {"line": "rth", "away": 24, "also": "globex"}, bars)
    assert got == []                                                                       # ... but below the globex line (evening at 15020)


LOW = (PX, PX + 1.0, PX - 1.0, PX - 1.0, 40)           # a close one point under its own typical price: under the VWAP


def _flip_day():
    """Closes under the VWAP from 09:30; 10:00-10:02 at 15005 (a cross up that holds two closes: long at 10:02); back under it from
    10:03 (a cross down: short at 10:05); under it again from 11:00, 11:30-11:32 at 15010 (a cross up in the mid pass: long at 11:32)."""
    under = {f"{m // 60:02d}:{m % 60:02d}": LOW for m in range(570, 720)}
    return day({**under, **hold("10:00", "10:02", 15005.0), **hold("11:30", "11:32", 15010.0)})


def test_avwap_flip_on_the_0930_line_is_vwap_flip_rth_trade_for_trade(past):
    for sess in ("nyam", "mid"):
        bars = _flip_day()
        _, a, _ = run(AV.AvwapFlip, {"line": "rth", "hold": 2, "max_tr": 3, "sess": sess}, bars)
        st = P3.VwapFlip({**BASE, "anchor": "rth", "hold": 2, "max_tr": 3, "sess": sess})
        st.ROLLS = frozenset()
        res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(), daily=list(DAILY), on_error="raise")
        b = [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]
        assert a == b and a


def test_avwap_flip_vol_m_takes_a_cross_on_volume_and_drops_a_quiet_one(past, monkeypatch):
    bars = _flip_day()
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: 100.0)
    _, got, _ = run(AV.AvwapFlip, {"line": "rth", "hold": 2, "vol_m": 1.0}, bars)
    assert got == []                                                                       # the crossing bar traded 40 < 100
    monkeypatch.setattr(AV, "vol_ref", lambda root, dates, a, b: 30.0)
    _, got, _ = run(AV.AvwapFlip, {"line": "rth", "hold": 2, "vol_m": 1.0}, bars)
    assert [(g[0] // 60, g[1]) for g in got] == [(sec(10, 3) // 60, "long")]                # held to 15:58 (no target): one trade


def test_avwap_flip_vol_ref_reads_only_the_dates_before_today():
    with pytest.raises(S.LookAheadError):
        AV._before(D.isoformat(), DAILY + [{"date": D.isoformat()}])


def _orb_day(edits):
    """The 09:30-10:00 range 14998-15002, a close at 15010 at 10:05 (the break up), then `edits`."""
    rng = {f"09:{m:02d}": (PX, 15002.0, 14998.0, PX, 40) for m in range(30, 60)}
    return day({**rng, "10:05": (PX, 15010.0, PX, 15010.0, 40), **hold("10:06", "10:19", 15010.0), **edits})


def test_orb_vwap_pb_buys_the_first_pullback_to_the_0930_vwap_after_a_break_up(past):
    bars = _orb_day({})
    w = tk(vwap(bars, 570, S._sec("10:20") // 60))
    bars = _orb_day({"10:20": (15010.0, 15010.0, w - TICK, 15010.0, 40)})
    st, got, res = run(AV.OrbVwapPb, {"or_min": 30, "stop_mode": "struct", "tgt_r": 1.0}, bars)
    assert got == [(sec(10, 20, 15), "long", w)]
    assert res.trades[0]["sl"] == pytest.approx(14998.0)                                   # structure stop = the range's low


def test_orb_vwap_pb_waits_for_the_break_and_uses_the_arm_once(past):
    early = day({**{f"09:{m:02d}": (PX, 15002.0, 14998.0, PX, 40) for m in range(30, 60)}, "09:45": (PX, 15002.0, 14990.0, PX, 40)})
    assert run(AV.OrbVwapPb, {"or_min": 30}, early)[1] == []                               # inside the range, no break: nothing
    bars = _orb_day({})
    w = tk(vwap(bars, 570, S._sec("10:20") // 60))
    bars = _orb_day({"10:20": (15010.0, 15010.0, w + TICK, 15010.0, 40), **hold("10:21", "10:29", 15010.0),
                     "10:30": (15010.0, 15010.0, w - 2.0, 15010.0, 40)})
    assert run(AV.OrbVwapPb, {"or_min": 30, "near": 2}, bars)[1] == []                     # within 2 ticks at 10:20, no fill: used up
    assert run(AV.OrbVwapPb, {"or_min": 30, "near": 0}, bars)[1] != []                     # near 0: 10:20 is no touch, 10:30 trades


def test_orb_vwap_pb_runs_in_the_new_york_passes_only():
    st = AV.OrbVwapPb({**BASE, "sess": "all", "hold_to": "session"})
    assert st.sessions() == ["nyam", "mid", "pm"]
    st = AV.AvwapTouch({**BASE, "line": "globex", "sess": "all", "hold_to": "session"})
    assert st.sessions() == ["asia", "london", "nyam", "mid", "pm"]


# ---- a real build day: the minutes built from a tape are the engine's own bars --------------------------------------------------
def test_the_minutes_of_a_real_tape_are_the_engines_one_minute_bars():
    real_days()
    iso = "2023-03-14"
    AV._MIN.clear()
    m = AV.minutes("NQ", iso)
    t = S.load_tape(iso, "NQ", allow_holdout=S.ALLOW_BP)
    bars = S.build_bars(t.ts, t.px, t.size, 0, len(t.ts), S.et_ns(D, "00:00"), S.et_ns(D, "16:10"), 1)
    k = (m["sec"] >= 0) & (m["sec"] < 58200)
    assert len(bars) == int(k.sum()) > 900
    for f, g in (("h", "h"), ("l", "l"), ("v", "v")):
        assert np.allclose(m[f][k], [getattr(b, g) for b in bars])
    assert np.allclose(m["tpv"][k], [b.v * (b.h + b.l + b.c) / 3.0 for b in bars])
    AV._MIN.clear()


def test_orb_vwap_pb_sells_the_first_pullback_after_a_break_down_with_the_range_high_as_its_stop(past):
    rng = {f"09:{m:02d}": (PX, 15002.0, 14998.0, PX, 40) for m in range(30, 60)}
    base = {**rng, "10:05": (PX, PX, 14990.0, 14990.0, 40), **hold("10:06", "10:19", 14990.0)}
    w = tk(vwap(day(base), 570, S._sec("10:20") // 60))
    bars = day({**base, "10:20": (14990.0, w + TICK, 14990.0, 14990.0, 40)})
    _, got, res = run(AV.OrbVwapPb, {"or_min": 30, "stop_mode": "struct", "tgt_r": 1.0}, bars)
    assert got == [(sec(10, 20, 30), "short", w)] and res.trades[0]["sl"] == pytest.approx(15002.0)


# after a holiday the tape starts 30 hours back: a holiday session at 16000 from 18:00 two days before, then the real evening at 15020
HOLIDAY = flat_rows(-108000, -61200, 16000.0, 4000)


def test_after_a_holiday_the_evening_lines_start_at_1800_and_the_prior_day_lines_keep_every_minute_since_their_anchor(monkeypatch):
    past = {**PAST, D.isoformat(): mins(HOLIDAY + EVE + POISON)}
    monkeypatch.setattr(AV, "minutes", lambda root, iso: past.get(iso))
    bars = day()
    for kind in ("globex", "onh"):
        st, _, _ = run(AV.AvwapTouch, {"line": kind}, bars)
        assert st.ln.value() < 15100                                                       # the 16000 holiday session never entered
    first = AV.Line("week", "NQ", D.isoformat(), DAILY[:-1], frozenset())                   # today the week's first trade date
    p, v = brute(EVE)
    assert first.value() == pytest.approx(p / v)                                           # from 18:00 the evening before, no holiday
    inside = AV.Line("week", "NQ", D.isoformat(), DAILY, frozenset())                       # Monday traded: the holiday is inside the week
    parts = [brute(MON_ROWS), brute(HOLIDAY + EVE)]
    assert inside.value() == pytest.approx(sum(x for x, _ in parts) / sum(y for _, y in parts))
    ln = AV.Line("onh", "NQ", D.isoformat(), DAILY, frozenset())
    for r in day_rows(bars, 960):
        ln.feed((r[0], None, r[1], r[2], r[3], r[4]))
    p, v = brute(EVE[:1] + EVE[1:], -21600, 0)                                             # the evening's high is its first minute
    q, w = brute(day_rows(bars, 960))
    assert ln.value() == pytest.approx((p + q) / (v + w))
    st, _, _ = run(AV.AvwapTouch, {"line": "pdh"}, bars)
    parts = [brute(MON_ROWS, 34200, 10 ** 9), brute(HOLIDAY + EVE), brute(day_rows(bars, st.mi))]
    assert st.ln.value() == pytest.approx(sum(x for x, _ in parts) / sum(y for _, y in parts))


def test_avwap_flip_starts_every_session_without_a_side_as_vwap_flip(past):
    bars = _flip_day()
    p = {"hold_to": "session", "sess": "all", "hold": 2, "max_tr": 3}
    _, a, _ = run(AV.AvwapFlip, {**p, "line": "rth"}, bars)
    st = P3.VwapFlip({**BASE, **p, "anchor": "rth"})
    st.ROLLS = frozenset()
    res = S.run_session(st, minute_tape(bars, "00:00"), costs=S.Costs(), daily=list(DAILY), on_error="raise")
    b = [((t["entry_ms"] - MS0) // 1000, t["side"], t["entry_price"]) for t in sorted(res.trades, key=lambda t: t["entry_ms"])]
    assert a == b and a
