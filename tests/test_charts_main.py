"""python -m homebase.charts: argument parsing, and (final fix wave) that a --replay run never
fetches ForexFactory -- only the cached weeks already on disk are served."""
from __future__ import annotations

import datetime as dt

from homebase.charts import __main__ as main_mod


def _patch_run(monkeypatch, captured):
    def fake_create_app(**kw):
        captured.update(kw)
        return "the app"

    def fake_run(app, **kw):
        assert app == "the app"
        captured["uvicorn"] = kw

    monkeypatch.setattr(main_mod, "create_app", fake_create_app)
    monkeypatch.setattr(main_mod.uvicorn, "run", fake_run)


def test_replay_mode_passes_no_calendar_fetch(monkeypatch):
    captured: dict = {}
    _patch_run(monkeypatch, captured)
    assert main_mod.main(["--replay", "2026-09-24"]) == 0
    assert captured["replay"] == dt.date(2026, 9, 24)
    assert captured["calendar_fetch"] is None
    assert captured["news_fetch"] is None       # a replay never fetches FinancialJuice/trumpstruth either


def test_live_mode_passes_the_real_http_get(monkeypatch):
    captured: dict = {}
    _patch_run(monkeypatch, captured)
    assert main_mod.main([]) == 0
    assert captured["replay"] is None
    assert captured["calendar_fetch"] is main_mod.http_get
    assert captured["news_fetch"] is main_mod.news_http_get


def test_the_loopback_socket_is_not_compressed(monkeypatch):
    """permessage-deflate would run zlib over every multi-megabyte history message on the event loop."""
    captured: dict = {}
    _patch_run(monkeypatch, captured)
    assert main_mod.main([]) == 0
    assert captured["uvicorn"]["ws_per_message_deflate"] is False


def test_the_event_loop_gets_a_short_gil_slice(monkeypatch):
    """Worker threads (bars from ticks, prop simulations) hold the GIL in 5 ms slices; the loop must not queue
    behind each of them for a whole slice on every re-acquire."""
    import sys
    before = sys.getswitchinterval()
    try:
        _patch_run(monkeypatch, {})
        assert main_mod.main([]) == 0
        assert sys.getswitchinterval() == main_mod.SWITCH_INTERVAL_S < 0.005
    finally:
        sys.setswitchinterval(before)
