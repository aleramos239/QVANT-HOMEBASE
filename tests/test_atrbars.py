"""Bars from ticks and the research's ATR (atrbars.py).

The reference is a literal port of the research template's bar aggregation + ATR (template.py on_bar/_close):
the desk's numbers must equal what the backtests computed."""
from __future__ import annotations

import datetime as dt
import random

import pytest

from homebase.atrbars import MIN_MS, TickBars, et_ms, et_midnight_ms, wilder_atr

D = dt.date(2026, 10, 2)


def ref_atr(minutes, tf_min, fire_s):
    """template.py: 1-minute bars [(start_sec, o, h, l, c)] -> tf bars keyed by start // step, closed when the
    next bucket starts or the minute ends on the step; TR from the previous bar's close; ATR = mean of the first
    14 TRs, then Wilder.  Bars that start at/after the fire are not seen (the bar ending AT the fire is)."""
    step = tf_min * 60
    H, L, C, TR = [], [], [], []
    state = {"atr": None, "cur": None}

    def close():
        k, o, h, l, c = state["cur"]
        state["cur"] = None
        n = len(C)
        tr = h - l if n == 0 else max(h - l, abs(h - C[-1]), abs(l - C[-1]))
        H.append(h), L.append(l), C.append(c), TR.append(tr)
        n += 1
        a = state["atr"]
        state["atr"] = sum(TR) / n if n <= 14 else (a * 13.0 + tr) / 14.0

    for s, o, h, l, c in minutes:
        if s >= fire_s:
            break
        k = s // step
        if state["cur"] is not None and state["cur"][0] != k:
            close()
        cur = state["cur"]
        if cur is None:
            state["cur"] = [k, o, h, l, c]
        else:
            cur[2], cur[3], cur[4] = max(cur[2], h), min(cur[3], l), c
        if (s + 60) % step == 0:
            close()
    return state["atr"], len(C)


def day_minutes(seed=1, until_s=11 * 3600 + 5 * 60, gaps=0.0, protect=()):
    """A random-walk 1-minute tape from 00:00 ET.  `gaps`: share of minutes with no print (never the minutes
    in `protect`, the last minute of the buckets under test)."""
    rnd, px, out = random.Random(seed), 20000.0, []
    for s in range(0, until_s, 60):
        if s not in protect and rnd.random() < gaps:
            continue
        o = px
        pts = [o] + [o + rnd.uniform(-6, 6) for _ in range(3)]
        pts = [round(p * 4) / 4 for p in pts]
        out.append((s, pts[0], max(pts), min(pts), pts[-1]))
        px = pts[-1]
    return out


def fed(minutes, as_ticks):
    tb = TickBars(D)
    base = tb.t0
    for s, o, h, l, c in minutes:
        if as_ticks:                                   # open, then the extremes, then the close
            for i, p in enumerate((o, h, l, c)):
                tb.add_tick(base + s * 1000 + 1000 * (i + 1), p, 1)
        else:
            tb.add_minute(base + s * 1000, o, h, l, c, 4)
    return tb


FIRE_NYAM, FIRE_ORB, FIRE_PM = 9 * 3600 + 1800, 11 * 3600 + 300, 13 * 3600 + 1800


@pytest.mark.parametrize("as_ticks", [False, True])
@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_atr_equals_the_templates_at_the_three_fires(seed, as_ticks):
    protect = {FIRE_NYAM - 60, FIRE_ORB - 60, FIRE_PM - 60}
    mins = day_minutes(seed, until_s=FIRE_PM, gaps=0.15, protect=protect)
    tb = fed(mins, as_ticks)
    for tf, fire in ((30, FIRE_NYAM), (5, FIRE_ORB), (30, FIRE_PM)):
        want, n = ref_atr(mins, tf, fire)
        got, m = tb.atr(tf, tb.t0 + fire * 1000)
        assert m == n and got == pytest.approx(want, rel=1e-12), (tf, fire)


def test_bar_counts_at_the_fires():
    """The review: 19 bars of 30 minutes at 09:30, 27 at 13:30; at 11:05 it says 132 bars of 5 minutes, counting to
    11:00 -- the 11:00-11:05 bar is closed at the 11:05 event (the tester delivers it first), so the ATR has 133."""
    mins = day_minutes(7, until_s=FIRE_PM)
    tb = fed(mins, False)
    assert tb.atr(30, tb.t0 + FIRE_NYAM * 1000)[1] == 19
    assert tb.atr(30, tb.t0 + FIRE_PM * 1000)[1] == 27
    assert tb.atr(5, tb.t0 + FIRE_ORB * 1000)[1] == 133
    assert tb.atr(5, tb.t0 + (FIRE_ORB - 300) * 1000)[1] == 132


def test_the_first_14_bars_average_then_wilder():
    h = [10 + i for i in range(20)]
    l = [8] * 20
    c = [9] * 20
    trs = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, 20)]
    a = sum(trs[:14]) / 14
    for tr in trs[14:]:
        a = (a * 13 + tr) / 14
    assert wilder_atr(h, l, c) == pytest.approx(a)
    assert wilder_atr(h[:3], l[:3], c[:3]) == pytest.approx(sum(trs[:3]) / 3)
    assert wilder_atr([], [], []) is None


def test_the_bar_ending_at_the_fire_is_closed_and_the_next_is_not():
    tb = TickBars(D)
    t = tb.t0
    tb.add_minute(t + 9 * 3600_000, 100, 110, 90, 105)                  # 09:00 bar (a 30-minute bucket, first minute)
    tb.add_minute(t + (9 * 3600 + 29 * 60) * 1000, 105, 120, 100, 118)  # 09:29: the bucket's last minute
    tb.add_minute(t + (9 * 3600 + 30 * 60) * 1000, 118, 125, 117, 124)  # 09:30: the next bucket's first
    bars = tb.tf_bars(30, et_ms(D, "09:30:00"))
    assert [(b[0], b[2], b[3], b[4]) for b in bars] == [(t + 9 * 3600_000, 120, 90, 118)]
    assert len(tb.tf_bars(30, et_ms(D, "09:30:00") - 1)) == 0           # one ms earlier it is still forming
    assert len(tb.tf_bars(30, et_ms(D, "10:00:00"))) == 2


def test_a_print_at_the_fire_instant_is_not_before_it():
    tb = TickBars(D)
    fire = et_ms(D, "09:30:00")
    tb.add_tick(fire - 400, 100.0, 1)
    tb.add_tick(fire, 101.0, 1)                                          # stamped AT the fire: after the anchor
    tb.add_tick(fire + 5, 102.0, 1)
    assert tb.last_before(fire) == 100.0
    assert tb.last_print_before(fire) == (fire - 400, 100.0)
    assert tb.last_before(fire + 1) == 101.0
    assert tb.last_before(fire - 1000) is None


def test_the_anchor_survives_an_exhausted_tail():
    tb = TickBars(D)
    tb.add_minute(et_ms(D, "09:29:00"), 100, 101, 99, 100.5)
    assert tb.last_before(et_ms(D, "09:30:00")) == 100.5                 # history only: the last finished minute


def test_ticks_outside_the_et_day_are_ignored():
    tb = TickBars(D)
    tb.add_tick(tb.t0 - 1, 1.0)
    tb.add_tick(tb.t1, 1.0)
    assert tb.ticks == 0 and not tb.minutes


def test_range_takes_only_whole_minutes_inside():
    tb = TickBars(D)
    for i, (h, l) in enumerate([(105, 100), (107, 101), (106, 99), (110, 98), (104, 102), (130, 70)]):
        tb.add_minute(et_ms(D, "11:00:00") + i * MIN_MS, 103, h, l, 103)
    assert tb.range(et_ms(D, "11:00:00"), et_ms(D, "11:05:00")) == (110, 98, 5)   # the 11:05 minute is not in it
    assert tb.range(et_ms(D, "11:00:30"), et_ms(D, "11:05:00")) == (110, 98, 4)   # a minute that started earlier is not whole
    assert tb.range(et_ms(D, "12:00:00"), et_ms(D, "12:05:00")) == (None, None, 0)


def test_history_is_exact_and_replaces_live_prints_with_a_record():
    tb = TickBars(D)
    m = et_ms(D, "08:56:00")
    tb.add_tick(m + 1000, 100.0, 1)
    tb.add_tick(m + 2000, 103.0, 1)
    tb.add_tick(m + 3000, 101.0, 1)                    # a coalescing quote feed saw 100/103/101
    tb.add_minute(m, 100.0, 104.0, 99.0, 101.0, 90)    # the chart's exact bar disagrees on the extremes
    assert tb.minutes[m][:4] == [100.0, 104.0, 99.0, 101.0]
    assert tb.parity == [{"minute": m, "live": [103.0, 100.0, 101.0], "history": [104.0, 99.0, 101.0]}]
    tb.add_tick(m + 4000, 200.0, 1)                    # a late print never edits a finished bar
    assert tb.minutes[m][1] == 104.0
    tb.add_minute(m, 100.0, 104.0, 99.0, 101.0, 90)    # the same bar again: no new record
    assert len(tb.parity) == 1


def test_coverage_needs_history_from_midnight_and_no_hole_to_the_live_prints():
    tb = TickBars(D)
    up = et_ms(D, "09:30:00")
    assert tb.coverage(up) == (False, "no history bars")
    tb.add_minute(et_ms(D, "00:00:00"), 1, 1, 1, 1)
    tb.add_minute(et_ms(D, "08:57:00"), 1, 1, 1, 1)                      # history through 08:58
    assert tb.coverage(up) == (False, "no live prints after the history")
    tb.start_live(et_ms(D, "08:58:30"))                                  # live began 30 s after the history ends: a hole
    tb.add_tick(et_ms(D, "08:58:31"), 1.0)
    assert tb.coverage(up) == (False, "a hole between the history and the live prints")
    tb.start_live(et_ms(D, "08:55:05"))                                  # live began before the history ends: whole
    assert tb.coverage(up)[0] is True
    tb.start_live(et_ms(D, "09:10:00"), reset=True)                      # the feed dropped and came back: a hole again
    assert tb.coverage(up)[0] is False


def test_a_silent_live_feed_is_a_hole_until_history_covers_it():
    tb = TickBars(D)
    up = et_ms(D, "09:30:00")
    tb.add_minute(et_ms(D, "00:00:00"), 1, 1, 1, 1)
    tb.add_minute(et_ms(D, "08:57:00"), 1, 1, 1, 1)                      # history through 08:58
    tb.start_live(et_ms(D, "08:55:05"))
    tb.add_tick(et_ms(D, "09:00:00"), 1.0)
    tb.add_tick(et_ms(D, "09:01:30"), 1.0)                               # 90 s apart: a quiet moment, not a hole
    assert tb.coverage(up)[0] is True and tb.live_gaps == []
    tb.add_tick(et_ms(D, "09:05:00"), 1.0)                               # 3.5 minutes of silence on a live feed
    assert tb.live_gaps == [(et_ms(D, "09:01:30"), et_ms(D, "09:05:00"))]
    assert tb.coverage(up) == (False, "a gap in the live prints that the history does not cover")
    tb.add_minute(et_ms(D, "09:03:00"), 1, 1, 1, 1)                      # history through 09:04: the gap's last minute is still open
    assert tb.coverage(up)[0] is False
    tb.add_minute(et_ms(D, "09:04:00"), 1, 1, 1, 1)                      # history through 09:05: every minute of the silence is exact
    assert tb.coverage(up)[0] is True


def test_coverage_refuses_a_history_that_starts_late():
    tb = TickBars(D)
    tb.add_minute(et_ms(D, "06:00:00"), 1, 1, 1, 1)
    tb.add_minute(et_ms(D, "09:29:00"), 1, 1, 1, 1)
    assert tb.coverage(et_ms(D, "09:30:00")) == (False, "history does not reach the start of the ET day")


def test_history_alone_covers_when_it_reaches_the_event():
    tb = fed(day_minutes(3, until_s=FIRE_NYAM), as_ticks=False)
    assert tb.coverage(tb.t0 + FIRE_NYAM * 1000)[0] is True              # the tester's path: no live prints at all


def test_alignment_is_to_et_midnight_on_a_dst_day():
    d = dt.date(2026, 3, 8)                                              # clocks go forward at 02:00 ET
    tb = TickBars(d)
    assert tb.t1 - tb.t0 == 23 * 3600_000
    tb.add_minute(et_ms(d, "09:00:00"), 1, 2, 0, 1)
    tb.add_minute(et_ms(d, "09:29:00"), 1, 3, 0, 2)
    bars = tb.tf_bars(30, et_ms(d, "09:30:00"))
    assert len(bars) == 1 and bars[0][0] == et_ms(d, "09:00:00") and (bars[0][2], bars[0][3]) == (3, 0)
    assert et_midnight_ms(d) == tb.t0
