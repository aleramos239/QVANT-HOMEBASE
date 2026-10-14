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


def test_pressure_parts_are_shrunk_and_blended_volume_three_to_one():
    s = make("press:1", 0.25)                                       # n = 1: the bar alone
    v = s.push(pbar(0, buy=300, sell=100, big=[(50, 1), (10, -1)], sw=[(40, 1)]))
    assert v["vol"] == pytest.approx(50.0)                          # (300-100)/400, nothing added to the volume part
    assert v["big"] == pytest.approx(100.0 * 40 / (60 + 30))        # a little neutral weight: not +67 but +44
    assert v["swp"] == pytest.approx(100.0 * 40 / (40 + 30))
    assert v["ord"] is None                                         # no orders on either side
    assert v["p"] == pytest.approx((3 * 50.0 + v["big"] + v["swp"]) / 5)
    lone = make("press:1", 0.25).push(pbar(0, buy=100, sell=100, big=[(10, 1)]))
    assert lone["big"] == pytest.approx(25.0)                       # one 10-lot print is no longer +100


def test_pressure_newest_bar_weighs_most_so_the_line_turns_with_the_move():
    s = make("press:3", 0.25)                                       # keeps half the weight per bar
    s.push(pbar(0, buy=300, sell=100))
    v = s.push(pbar(1, buy=100, sell=300))
    assert v["vol"] == pytest.approx(100.0 * (250 - 350) / 600)     # 300/2+100 buy vs 100/2+300 sell: already negative
    assert v["tot"] == pytest.approx(0.0)                           # the session's whole balance is still level
    old_box = 100.0 * (400 - 400) / 800
    assert v["vol"] < old_box                                       # a plain two-bar window would still read 0


def test_pressure_counts_the_orders_each_side_sent_and_skips_bars_cached_before_the_counts():
    s = make("press:1", 0.25)
    b0 = pbar(0, buy=100, sell=100)
    b0.ords_b, b0.ords_s = 30, 10
    first = s.push(b0)
    assert first["ord"] == pytest.approx(100.0 * 20 / (40 + 20))    # (30-10) / (30+10+shrink)
    assert first["p"] == pytest.approx((3 * 0.0 + first["ord"]) / 4)    # volume level, orders lean to buyers
    old = pbar(1, buy=100, sell=100)
    old.ords_b = old.ords_s = -1                                    # a bar cached before the counts: the class default
    assert s.push(old)["ord"] is None                               # n = 1: nothing of bar 0 is left, the old bar adds none
    assert make("press:1", 0.25).push(old)["ord"] is None


def test_pressure_leaves_out_a_part_with_nothing_to_say_and_is_none_when_all_are():
    s = make("press:3", 0.25)
    v = s.push(pbar(0, buy=10, sell=30))                            # no big prints, no sweeps, no orders
    assert v["big"] is None and v["swp"] is None
    assert v["p"] == pytest.approx(v["vol"]) == pytest.approx(-50.0)
    empty = make("press:3", 0.25).push(pbar(0, 0, 0))
    assert empty["p"] is None and empty["tot"] is None


def test_pressure_a_big_print_is_scaled_to_the_markets_average_print():
    quiet = pbar(0, buy=100, sell=0, big=[(30, 1)])
    quiet.v, quiet.n = 100, 100                                     # average print 1: 30 lots clears max(10, 8 x 1)
    assert make("press:1", 0.25).push(quiet)["big"] == pytest.approx(100.0 * 30 / 60)
    busy = pbar(0, buy=100, sell=0, big=[(30, 1), (50, 1)])
    busy.v, busy.n = 1000, 200                                      # average print 5: only 40+ lots are big
    assert make("press:1", 0.25).push(busy)["big"] == pytest.approx(100.0 * 50 / 80)
    hushed = pbar(0, buy=100, sell=0, big=[(30, 1)])
    hushed.v, hushed.n = 1000, 200
    assert make("press:1", 0.25).push(hushed)["big"] is None        # 30 is no longer big: the part has nothing to say


def test_pressure_restarts_with_the_session_and_the_developing_bar_changes_nothing():
    s = make("press:5", 0.25)
    s.push(pbar(0, 500, 0, session="a"))
    new = s.push(pbar(1, 0, 100, session="b"))
    assert new["vol"] == pytest.approx(-100.0) and new["tot"] == pytest.approx(-100.0)
    before = s.state
    pre = s.preview(pbar(2, 900, 0, session="b"))
    keep = 1 - 2 / 6
    assert s.state is before
    assert pre["vol"] == pytest.approx(100.0 * (900 - 100 * keep) / (900 + 100 * keep))


def test_pressure_wire_key_defaults_and_limits():
    assert make("press", 0.25).n == 5 and make("press:20", 0.25).n == 20
    for bad in ("press:0", "press:51", "press:5:5"):
        with pytest.raises(ValueError):
            make(bad, 0.25)
    assert warm_bars("press:20") >= 21


# ---- smt: NQ against ES, live ------------------------------------------------------------------------------------------------------------
from types import SimpleNamespace          # noqa: E402

from homebase.charts.studies_flow import SMT      # noqa: E402


def hl_bars(highs, lows=None, **kw):
    lows = lows if lows is not None else [h - 1 for h in highs]
    return [bar(i, h, l, **kw) for i, (h, l) in enumerate(zip(highs, lows))]


def peer_of(highs, lows=None):
    return SimpleNamespace(bars=hl_bars(highs, lows), builder=None)


def smt_run(study, bars):
    return [study.push(b) for b in bars]


def test_smt_one_market_takes_the_high_the_other_does_not_is_bearish_once():
    nq = [10, 11, 10, 9, 10, 13, 12]
    es = [10, 11, 10, 9, 10, 10, 10]
    st = SMT(2, 4)
    st.peer = peer_of(es, [8] * 7)          # constant lows on both sides: nothing bullish
    out = smt_run(st, hl_bars(nq, [8] * 7))
    assert out[:5] == [None] * 5
    assert out[5] == {"dir": -1, "ago": 0, "px": 13, "aago": 4, "apx": 11, "lead": 1, "live": False}
    assert out[6] is None                    # still the same signal: no second mark


def test_smt_the_partner_taking_the_high_is_the_chart_market_failing_it():
    nq = [10, 11, 10, 9, 10, 10.5, 10.5]
    es = [10, 11, 10, 9, 10, 13, 12]
    st = SMT(2, 4)
    st.peer = peer_of(es, [8] * 7)
    out = smt_run(st, hl_bars(nq, [8] * 7))
    assert out[5] == {"dir": -1, "ago": 0, "px": 10.5, "aago": 4, "apx": 11, "lead": -1, "live": False}


def test_smt_both_taking_the_high_is_no_divergence_and_a_low_takes_the_bull_side():
    both = SMT(2, 4)
    both.peer = peer_of([10, 11, 10, 9, 10, 13], [8] * 6)
    assert [v for v in smt_run(both, hl_bars([10, 11, 10, 9, 10, 14], [8] * 6)) if v] == []
    lows_nq = [8, 7, 8, 9, 8, 5]
    lows_es = [8, 7, 8, 9, 8, 7.5]
    bull = SMT(2, 4)
    bull.peer = peer_of([20] * 6, lows_es)
    hits = [v for v in smt_run(bull, hl_bars([20] * 6, lows_nq)) if v]
    assert hits == [{"dir": 1, "ago": 0, "px": 5, "aago": 4, "apx": 7, "lead": 1, "live": False}]


def test_smt_the_developing_bar_fires_live_and_changes_nothing():
    st = SMT(2, 4)
    st.peer = peer_of([10, 11, 10, 9, 10, 10], [8] * 6)
    bars = hl_bars([10, 11, 10, 9, 10, 13], [8] * 6)
    for b in bars[:5]:
        st.push(b)
    before = st.state
    forming = bars[5]
    forming.closed = False
    live = st.preview(forming)
    assert live["dir"] == -1 and live["live"] is True
    assert st.state is before
    forming.closed = True
    assert st.push(forming)["live"] is False


def test_smt_the_live_signal_goes_when_the_partner_takes_the_extreme_too():
    st = SMT(2, 4)
    forming_es = bar(5, 10, 8, closed=False)
    peer = SimpleNamespace(bars=hl_bars([10, 11, 10, 9, 10], [8] * 5), builder=SimpleNamespace(cur=forming_es))
    st.peer = peer
    bars = hl_bars([10, 11, 10, 9, 10, 13], [8] * 6)
    for b in bars[:5]:
        st.push(b)
    forming = bars[5]
    forming.closed = False
    assert st.preview(forming)["dir"] == -1          # NQ at 13, ES still at 10: a divergence, live
    forming_es.h = 13.5                              # ES makes its high too, while the minute is still open
    assert st.preview(forming) is None               # nothing to mark any more: the page takes the mark off
    forming_es.h = 10
    assert st.preview(forming)["dir"] == -1          # and it is back if the partner's bar is rebuilt without it


def test_smt_without_a_partner_or_without_its_bar_there_is_nothing_to_say():
    none = SMT(2, 4)
    assert smt_run(none, hl_bars([10, 11, 10, 9, 10, 13])) == [None] * 6
    gap = SMT(2, 4)
    gap.peer = SimpleNamespace(bars=[b for b in hl_bars([10, 11, 10, 9, 10, 10], [8] * 6) if b.t != 4 * MIN], builder=None)
    out = smt_run(gap, hl_bars([10, 11, 10, 9, 10, 13], [8] * 6))
    assert out[4] is None and out[5] is None         # one common bar short of window + reference: not enough yet


def test_smt_a_partner_bar_still_forming_counts_as_it_stands():
    st = SMT(1, 2)
    forming = bar(2, 10, 8, closed=False)
    st.peer = SimpleNamespace(bars=hl_bars([10, 11], [8, 8]), builder=SimpleNamespace(cur=forming))
    out = smt_run(st, hl_bars([10, 11, 13], [8, 8, 8]))
    assert out[2]["dir"] == -1 and out[2]["lead"] == 1


def test_smt_a_new_session_starts_over():
    st = SMT(2, 4)
    st.peer = peer_of([10, 11, 10, 9, 10, 10, 10], [8] * 7)
    bs = hl_bars([10, 11, 10, 9, 10, 13], [8] * 6)
    bs.append(bar(6, 13, 8, session="2026-10-10"))
    out = smt_run(st, bs)
    assert out[5]["dir"] == -1 and out[6] is None and st.state[1] == 1


def test_smt_wire_key_defaults_and_limits():
    assert (make("smt").w, make("smt").l) == (6, 36)
    assert (make("smt:3:20").w, make("smt:3:20").l) == (3, 20)
    for bad in ("smt:0", "smt:51", "smt:6:1", "smt:6:501", "smt:6:36:1", "smt:x", "smt@300"):
        with pytest.raises(ValueError):
            make(bad)
    assert warm_bars("smt") == 44 and warm_bars("smt:3:20") == 25
