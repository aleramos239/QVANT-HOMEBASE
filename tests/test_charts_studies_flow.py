"""DeltaDiv and TapeSpeed (studies_flow.py): the Study contract and the two rules, on hand-made bars."""
from __future__ import annotations

import pytest

from homebase.charts.bars import Bar
from homebase.charts.hub import warm_bars
from homebase.charts.studies import make
from homebase.charts.studies_flow import DeltaDiv, TapeSpeed

MIN = 60_000


def bar(i, h, l, buy=0, sell=0, session="2026-10-09", n=10, closed=True, te=None, span=MIN):
    b = Bar.open_at(i * MIN, session, (h + l) / 2)
    b.h, b.l, b.buy, b.sell, b.n, b.closed = h, l, buy, sell, n, closed
    b.te, b.span = (i * MIN + 30_000) if te is None else te, span
    return b


def run(study, bars):
    return [(study.preview(b), study.push(b)) for b in bars]


def test_bearish_divergence_is_emitted_n_bars_later_and_only_by_a_closed_bar():
    # swing high 10 at bar 2 (cum delta +20), higher swing high 12 at bar 7 on LOWER cum delta (+20 +10 -40 ...)
    hs = [5, 6, 10, 6, 5, 6, 9, 12, 9, 6, 5, 5]
    flows = [(20, 0)] * 3 + [(0, 10)] * 3 + [(0, 30)] * 6
    bars = [bar(i, h, h - 1, *f) for i, (h, f) in enumerate(zip(hs, flows))]
    out = run(DeltaDiv(2), bars)
    hits = [(i, push) for i, (_, push) in enumerate(out) if push]
    assert hits == [(9, {"dir": -1, "ago": 2, "px": 12})]       # bar 7's swing, confirmed by bar 9
    assert all(pre is None for pre, _ in out)                   # the developing bar never draws one


def test_bullish_divergence_and_a_higher_low_on_higher_delta_is_not_one():
    ls = [10, 9, 5, 9, 10, 9, 6, 4, 6, 9, 10, 10]
    flows = [(0, 20)] * 3 + [(10, 0)] * 3 + [(40, 0)] * 6        # cum delta rises while price makes a lower low
    bars = [bar(i, l + 1, l, *f) for i, (l, f) in enumerate(zip(ls, flows))]
    hits = [v for _, v in run(DeltaDiv(2), bars) if v]
    assert hits == [{"dir": 1, "ago": 2, "px": 4}]
    agree = [bar(i, l + 1, l, 10, 0) for i, l in enumerate(ls)]   # delta keeps rising with price: no divergence
    assert [v for _, v in run(DeltaDiv(2), agree) if v and v["dir"] == -1] == []


def test_a_new_session_resets_the_cumulative_delta_and_the_swings():
    d = DeltaDiv(1)
    d.push(bar(0, 5, 4, 100, 0))
    assert d.state[0] == "2026-10-09" and d.state[1] == 100
    d.push(bar(1, 5, 4, 10, 0, session="2026-10-10"))
    assert d.state[0] == "2026-10-10" and d.state[1] == 10 and d.state[3] is None


def test_tape_speed_rate_burst_and_hot():
    t = TapeSpeed(20)
    last = None
    for i in range(12):
        last = t.push(bar(i, 10, 9, n=60 if i < 11 else 600))
    assert last == {"rate": 10.0, "burst": 3.0, "hot": 10.0}
    quiet = t.preview(bar(12, 10, 9, n=30))
    assert quiet["hot"] is None and quiet["rate"] == 0.5


def test_tape_speed_uses_the_elapsed_time_of_a_developing_bar_and_one_second_at_least():
    t = TapeSpeed(20)
    dev = bar(0, 10, 9, n=90, closed=False, te=45_000)            # 45 s into its minute
    assert t.preview(dev)["rate"] == pytest.approx(2.0)
    one = bar(0, 10, 9, n=5, closed=False, te=100)
    assert t.preview(one)["rate"] == 5.0                          # under a second counts as one second
    assert t.preview(bar(0, 10, 9, n=0)) is None


def test_the_wire_keys():
    assert isinstance(make("ddiv"), DeltaDiv) and make("ddiv:7").n == 7
    assert make("tspeed:100").n == 100
    with pytest.raises(ValueError):
        make("ddiv:0")
    with pytest.raises(ValueError):
        make("tspeed:5000")
    with pytest.raises(ValueError):
        make("ddiv:5:6")
    assert warm_bars("ddiv:5") == 22 and warm_bars("tspeed:200") == 201


# ---- press: buy / sell pressure

def pbar(i, buy, sell, big=(), sw=(), session="2026-10-09"):
    b = bar(i, 100, 99, buy, sell, session=session)
    b.big = [[i * MIN + k, 100.0, size, side] for k, (size, side) in enumerate(big)]
    b.sw = [[i * MIN + k, 100.0, 101.0, size, side] for k, (size, side) in enumerate(sw)]
    return b


def test_pressure_is_the_mean_of_volume_big_print_and_sweep_balance_over_the_window():
    s = make("press:2", 0.25)
    first = s.push(pbar(0, buy=300, sell=100, big=[(50, 1), (10, -1)], sw=[(40, 1)]))
    assert first["vol"] == pytest.approx(50.0)                      # (300-100)/400
    assert first["big"] == pytest.approx(100.0 * 40 / 60)
    assert first["swp"] == pytest.approx(100.0)
    assert first["p"] == pytest.approx((50.0 + 100.0 * 40 / 60 + 100.0) / 3)
    second = s.push(pbar(1, buy=100, sell=300, big=[(50, -1)], sw=[(40, -1)]))   # window of 2: both bars
    assert second["vol"] == pytest.approx(0.0)                      # 400 buy vs 400 sell
    assert second["big"] == pytest.approx(100.0 * (50 - 60) / 110)
    assert second["swp"] == pytest.approx(0.0)
    third = s.push(pbar(2, buy=0, sell=200))                        # bar 0 has left the window
    assert third["vol"] == pytest.approx(100.0 * (100 - 500) / 600)
    assert third["tot"] == pytest.approx(100.0 * (400 - 600) / 1000)    # the session's balance so far


def test_pressure_leaves_out_a_part_with_nothing_to_say_and_is_none_when_all_are():
    s = make("press:3", 0.25)
    v = s.push(pbar(0, buy=10, sell=30))                            # no big prints, no sweeps
    assert v["big"] is None and v["swp"] is None
    assert v["p"] == pytest.approx(v["vol"]) == pytest.approx(-50.0)
    empty = make("press:3", 0.25).push(pbar(0, 0, 0))
    assert empty["p"] is None and empty["tot"] is None


def test_pressure_restarts_with_the_session_and_the_developing_bar_changes_nothing():
    s = make("press:5", 0.25)
    s.push(pbar(0, 500, 0, session="a"))
    new = s.push(pbar(1, 0, 100, session="b"))
    assert new["vol"] == pytest.approx(-100.0) and new["tot"] == pytest.approx(-100.0)
    before = s.state
    pre = s.preview(pbar(2, 900, 0, session="b"))
    assert s.state is before and pre["vol"] == pytest.approx(100.0 * (900 - 100) / 1000)


def test_pressure_wire_key_defaults_and_limits():
    assert make("press", 0.25).n == 5 and make("press:20", 0.25).n == 20
    for bad in ("press:0", "press:51", "press:5:5"):
        with pytest.raises(ValueError):
            make(bad, 0.25)
    assert warm_bars("press:20") >= 21
