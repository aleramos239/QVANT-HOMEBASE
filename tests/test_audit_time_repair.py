"""Audit 2026-10-27, group time (repair pass): _before reads the day's own store, the warm is once per market-day and the
session event waits for it, early_close_et caches per year."""
import datetime as dt
import threading

from homebase.backtest import tape as T
from homebase.labrun import host

D = dt.date


class _Store:
    def __init__(self, have):
        self.have, self.asked = have, 0

    def manifests(self, root, d):
        self.asked += 1
        return ["m"] if d in self.have else []


def test_before_asks_the_given_store_and_not_a_new_default(monkeypatch):
    monkeypatch.setattr(host, "TapeStore", lambda: (_ for _ in ()).throw(AssertionError("default store built")))
    assert host._before(D(2027, 1, 4), "NQ", _Store(set())) == D(2026, 12, 31)       # Jan 1 2027: no tape of its own
    lagging = _Store({D(2027, 1, 1)})                                                  # its manifest arrived: it counts, the loader waits
    assert host._before(D(2027, 1, 4), "NQ", lagging) == D(2027, 1, 1) and lagging.asked


def test_a_day_uses_its_own_store_for_the_previous_session():
    day = host.StrategyDay.__new__(host.StrategyDay)
    day.date, day._root, day._tapes = D(2027, 1, 4), "NQ", _Store(set())
    assert day._prev() == D(2026, 12, 31)
    day._tapes = _Store({D(2027, 1, 1)})
    assert day._prev() == D(2027, 1, 1)


def _day(mv):
    day = host.StrategyDay.__new__(host.StrategyDay)
    day._root, day.date, day._mv_n, day._needs_delta, day._mv = "NQ", D(2026, 11, 24), 1, False, mv
    day._tapes = _Store({D(2026, 11, 23)})
    return day


def test_warm_runs_once_per_market_day_and_a_failed_warm_is_read_again():
    host._WARMED.clear()
    calls = []
    a, b = _day(lambda r, d, n: calls.append(1)), _day(lambda r, d, n: calls.append(2))
    a._warm(); b._warm()
    assert calls == [1]                                    # the second strategy on the same market-day does not build again
    host._WARMED.clear()
    boom = _day(lambda r, d, n: (_ for _ in ()).throw(OSError("no tape")))
    boom._warm()
    assert not host._WARMED                                # failed: not kept, so the next warm (and the session event) tries again


def test_session_event_waits_for_a_warm_in_progress_then_loads():
    host._WARMED.clear()
    started, release, order = threading.Event(), threading.Event(), []

    def mv(r, d, n):
        order.append("load")
        if len(order) == 1:
            started.set()
            assert release.wait(5)
        return [{"date": "2026-11-23", "vol": [1]}]

    day = _day(mv)
    w = threading.Thread(target=day._warm); w.start()
    assert started.wait(5)
    out = []
    s = threading.Thread(target=lambda: out.append(day._session_minvol())); s.start()
    s.join(0.3)
    assert s.is_alive() and order == ["load"]              # the session read is held behind the warm (one writer per cache file)
    release.set(); w.join(5); s.join(5)
    assert order == ["load", "load"] and out and out[0][-1]["date"] == "2026-11-23"


def test_early_close_builds_each_year_once():
    T._early_closes_of.cache_clear()
    for _ in range(3):
        assert T.early_close_et("NQ", D(2027, 11, 26)) == "13:15" and T.early_close_et("NQ", D(2027, 11, 24)) is None
    assert T._early_closes_of.cache_info().misses == 1
