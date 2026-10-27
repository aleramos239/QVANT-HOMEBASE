"""Audit 2026-10-27, group time: the half-day / holiday calendar, the previous session, front_month's clock, the warm thread."""
import datetime as dt
import threading
import time

from homebase import symbols
from homebase.backtest import tape as T
from homebase.labrun import host

D = dt.date


def test_half_days_beyond_2026_and_table_unchanged():
    assert T.early_close_et("NQ", D(2027, 11, 26)) == "13:15"
    assert T.early_close_et("NQ", D(2027, 12, 24)) == "13:15"
    assert T.early_close_et("NQ", D(2027, 7, 2)) == "13:15"        # Jul 4 2027 is a Sunday
    assert T.early_close_et("NQ", D(2030, 11, 29)) == "13:15"
    assert T.early_close_et("NQ", D(2027, 11, 24)) is None
    assert T.early_close_et("GC", D(2027, 11, 26)) is None
    old = {D(2021, 7, 2), D(2023, 7, 3), D(2024, 7, 3), D(2025, 7, 3), D(2026, 7, 3)}
    assert old <= T.EARLY_CLOSES and D(2022, 7, 1) not in T.EARLY_CLOSES


def test_exchange_holiday_list():
    for d in (D(2026, 11, 26), D(2026, 12, 25), D(2027, 1, 1), D(2026, 9, 7), D(2026, 4, 3), D(2027, 3, 26), D(2026, 5, 25)):
        assert T.exchange_holiday(d), d
    assert not T.exchange_holiday(D(2026, 11, 25)) and not T.exchange_holiday(D(2026, 11, 27))


class _NoTapes:
    def manifests(self, root, d):
        return []


class _Tapes:
    def manifests(self, root, d):
        return ["m"]


def test_before_skips_a_holiday_with_no_tape(monkeypatch):
    monkeypatch.setattr(host, "TapeStore", _NoTapes)
    assert host._before(D(2026, 11, 27), "NQ") == D(2026, 11, 25)      # Thanksgiving Thursday has no file
    assert host._before(D(2026, 12, 28), "NQ") == D(2026, 12, 24)      # Fri Dec 25
    assert host._before(D(2027, 1, 4), "NQ") == D(2026, 12, 31)
    assert host._before(D(2026, 11, 27)) == D(2026, 11, 26)            # no root: the old weekday rule
    assert host._before(D(2026, 11, 24), "NQ") == D(2026, 11, 23)      # an ordinary day with no tape yet: still waits for it


def test_before_keeps_a_holiday_that_has_a_tape(monkeypatch):
    monkeypatch.setattr(host, "TapeStore", _Tapes)
    assert host._before(D(2026, 11, 27), "NQ") == D(2026, 11, 26)


def test_front_month_default_is_the_et_session_date(monkeypatch):
    from zoneinfo import ZoneInfo
    at = lambda h, m: dt_ms(D(2026, 12, 10), h, m)
    dt_ms = lambda d, h, m: int(dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo("America/New_York")).timestamp() * 1000)
    monkeypatch.setattr(time, "time", lambda: at(17, 30) / 1000)
    assert symbols.front_month("NQ") == "NQZ6"
    monkeypatch.setattr(time, "time", lambda: at(18, 30) / 1000)       # the 18:00 open: session Dec 11, the feed's contract
    assert symbols.front_month("NQ") == "NQH7"


def test_warm_runs_off_the_calling_thread_and_the_loaders_share_one_lock():
    seen = []
    day = host.StrategyDay.__new__(host.StrategyDay)
    day._root, day.date, day._hourly_n, day._mv_n, day._needs_delta = "NQ", D(2026, 11, 24), 1, 1, False
    host._WARMED.clear()
    day._mv = lambda r, d, n: seen.append(("mv", threading.current_thread().name, host._LOAD_LOCK.locked()))
    t = threading.Thread(target=day._warm, name="w")
    t.start(); t.join()
    assert seen == [("mv", "w", True)]
    assert host.StrategyDay._load([1], "x") == [1]
