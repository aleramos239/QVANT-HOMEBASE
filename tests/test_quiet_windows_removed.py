"""2026-10-16, the owner's word: NO limit at 9:30. Every 09:20-09:35 ET window (the tick job and the Refresh
button, the charts' decode / export / feed (re)connects, the level timer's data requests, the desk's account
add / remove / target refusals, the MCP operate tools, the broker's renewal pause) is EMPTY. The machinery
stays (tests/conftest.py puts the old windows back for the tests that prove it); this file pins production.
The fire's own protections -- the 09:28-09:31 socket guard and the 09:29:50-09:30:30 view pause -- are not windows
of this kind and are untouched."""
from __future__ import annotations

import datetime as dt

from homebase import leveltimer, server, ticks
from homebase.broker import tradovate
from homebase.charts import QUIET, export, refresh, tickfeed
from homebase.claude_mcp import desk_tools

ET = ticks.ET
FIRE_WEEKDAY = [dt.datetime(2026, 10, 14, h, m, tzinfo=ET) for h, m in ((9, 10), (9, 20), (9, 27), (9, 30), (9, 34))]


def empty(win) -> bool:
    return win[0] >= win[1]


def test_every_window_constant_is_empty():
    assert empty(QUIET)
    assert empty(ticks.QUIET) and empty(leveltimer.QUIET) and empty(desk_tools.QUIET)
    assert empty(server.GONE_QUIET) and empty(server.GONE_CHECK_QUIET) and empty(server.FEED_QUIET)
    assert empty(tradovate.RENEW_QUIET) and empty(server.RENEW_QUIET)


def test_no_helper_calls_930_quiet():
    for t in FIRE_WEEKDAY:
        assert not ticks.in_quiet(t) and not export.in_quiet(t) and not leveltimer.in_quiet(t)
        assert not tickfeed.in_quiet(t.timestamp())
        assert not desk_tools._in_quiet(t)
        assert not server.feed_deferred(t, {})


def test_refresh_data_starts_at_0930(tmp_path):
    class P:
        def wait(self):
            return 0

        def terminate(self):
            pass

    m = refresh.RefreshManager(tmp_path / "s", python="py", cwd=tmp_path, clock=lambda: FIRE_WEEKDAY[3],
                               popen=lambda *a, **k: P(), coverage_path=tmp_path / "c.json",
                               lock_path=tmp_path / "ticks.lock")
    assert m.start()["status"] == "running"


def test_the_tick_job_does_not_stand_down_at_0930(monkeypatch):
    monkeypatch.setattr(ticks, "now_et", lambda: FIRE_WEEKDAY[3])
    assert not ticks.in_quiet(ticks.now_et())


def test_the_token_renewal_does_not_hold_inside_0920_0935():
    now = FIRE_WEEKDAY[1].replace(minute=25)          # 09:25, a token with 5 min left, outside the fire guard
    due, why = tradovate.renewal_due(now, now.timestamp() + 300)
    assert why != "quiet"
