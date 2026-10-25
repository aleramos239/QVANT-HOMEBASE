"""avwap_touch_flow (families/avwap_flow.py): avwap_touch + `cumd`, the session's net flow since 09:30 on the trade's side.

THE RULES UNDER TEST (module docstring of families/avwap_flow.py):
    cumd off  = avwap_touch trade for trade, the flow table never read
    cumd with = a limit AT the line only when the net aggressor flow of the whole minutes 09:30 -> this tf close points the trade's way
    med / p80 = also |share| reaches the 50th / 80th percentile of the same clock window on the 20 dates before (15 needed)
    no flow row / no volume = no order; only minutes that have ended are read
Synthetic days with EXACT numbers (test_avwap / test_vwap_touch) and a flowtab.window that answers by date. No net or win rate is read.
"""
import numpy as np
import pytest

import families
import l2sim as S
from families import avwap as AV
from families import avwap_flow as AF
from families import blocks as B
from test_avwap import BASE, past, run  # noqa: F401  (past = the fixture)
from test_blocks import DAILY, D
from test_vwap_touch import AWAY_UP, PX, TICK, day, hold, sec, tk, vwap

REF20 = [i / 100 for i in range(1, 21)]                       # |shares| 1 % .. 20 %: median 10.5 %, 80th percentile 16.2 %
UP = day({"09:50": AWAY_UP, **hold("09:51", "09:54", 15010.0), "09:55": (15010.0, 15010.0, tk(vwap(day({"09:50": AWAY_UP}), 0, 591)) - TICK, 15010.0, 40)})
AWAY_DN = (PX, PX + TICK, 14990.0, 14990.0, 40)
W_DN = tk(vwap(day({"09:50": AWAY_DN}), 0, 591))
DN = day({"09:50": AWAY_DN, **hold("09:51", "09:54", 14990.0), "09:55": (14990.0, W_DN + TICK, 14990.0, 14990.0, 40)})


def with_flow(monkeypatch, today, ref=REF20):
    """flowtab.window: volume 1000 and delta share `today` on D, ref[k] on the k-th earlier date, for any window that starts at 09:30."""
    shares = dict(zip([r["date"] for r in DAILY[-20:]], ref))
    asked = []

    def window(root, iso, a, b):
        asked.append((iso, a, b))
        if a != sec(9, 30) or b <= a:
            return None
        s = today if iso == D.isoformat() else shares.get(iso)
        return None if s is None else (1000, int(round(s * 1000)), 0, 0)
    monkeypatch.setattr(AF.flowtab, "window", window)
    return asked


def sides(params, bars):
    _, got, _ = run(AF.AvwapTouchFlow, {"line": "rth", "away": 24, **params}, bars)
    return [t[1] for t in got]


def test_the_family_is_registered_and_wrapped():
    assert families.ERRORS == {}
    assert families.MODULE_OF["avwap_touch_flow"] == "avwap_flow" and B.WRAPPED["avwap_touch_flow"].__name__ == "B_avwap_touch_flow"


def test_cumd_off_is_avwap_touch_trade_for_trade_and_never_reads_the_flow(past, monkeypatch):
    asked = with_flow(monkeypatch, -0.9)
    for bars in (UP, DN):
        _, a, _ = run(AF.AvwapTouchFlow, {"line": "rth", "away": 24}, bars)
        _, b, _ = run(AV.AvwapTouch, {"line": "rth", "away": 24}, bars)
        assert a == b and a
    assert asked == []


@pytest.mark.parametrize("today, w, med, p80", [(0.18, True, True, True), (0.12, True, True, False), (0.05, True, False, False),
                                               (-0.18, False, False, False), (None, False, False, False)])
def test_a_long_needs_the_flow_since_0930_to_point_up_and_reach_its_quantile(past, monkeypatch, today, w, med, p80):
    for mode, want in (("with", w), ("med", med), ("p80", p80)):
        with_flow(monkeypatch, today)
        assert sides({"cumd": mode}, UP) == (["long"] if want else []), (today, mode)


@pytest.mark.parametrize("today, want", [(-0.18, ["short"]), (0.18, [])])
def test_a_short_is_the_mirror_it_needs_net_selling(past, monkeypatch, today, want):
    for mode in ("with", "p80"):
        with_flow(monkeypatch, today)
        assert sides({"cumd": mode}, DN) == want


def test_only_minutes_that_have_ended_before_the_decision_are_read(past, monkeypatch):
    asked = with_flow(monkeypatch, 0.18)
    assert sides({"cumd": "with"}, UP) == ["long"]
    today = [(a, b) for iso, a, b in asked if iso == D.isoformat()]
    assert today and all(a == sec(9, 30) and b <= sec(9, 55) for a, b in today)       # the order is decided at the 09:54 minute's close


def test_fewer_than_15_earlier_dates_is_no_trade_for_a_quantile_but_not_for_the_sign(past, monkeypatch):
    with_flow(monkeypatch, 0.5, REF20[:14] + [None] * 6)
    assert sides({"cumd": "med"}, UP) == [] and sides({"cumd": "with"}, UP) == ["long"]
    with_flow(monkeypatch, 0.5, REF20[:15] + [None] * 5)
    assert sides({"cumd": "med"}, UP) == ["long"]
