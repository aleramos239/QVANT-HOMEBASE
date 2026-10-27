"""settings.json "md_account" reaches the chart feed: the default TickFeed connects on that account's md
token (ticks.connect_md(account=...)). No pin: connect_md is called as before. Fakes only, no login."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from homebase import ticks as T
from homebase.charts.server import create_app
from tests.charts_util import D, session_ms
from tests.test_charts_server import archive
from tests.test_charts_settings_server import BASE_URL, FakeLink, FakeMdWS, wait_for


def _run(tmp_path, monkeypatch, settings):
    calls = []

    async def fake_connect_md(prefer_live=True, strict=False, account=None):
        calls.append((prefer_live, account))
        return FakeMdWS("demo")

    monkeypatch.setattr(T, "connect_md", fake_connect_md)
    monkeypatch.setenv("HOMEBASE_CHARTS_MD", "demo")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "settings.json").write_text(json.dumps(settings))
    app = create_app(roots=["NQ"], base=archive(tmp_path), state=tmp_path / "state",
                     now_ms=lambda: session_ms(D, 9, 45), desk_factory=FakeLink,
                     depth_roots=[], depth_base=tmp_path / "depth")
    with TestClient(app, base_url=BASE_URL):
        wait_for(lambda: calls)
    return calls


def test_the_feed_connects_on_the_pinned_account(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, {"md_account": "apex1"})[0] == (False, "apex1")


def test_without_a_pin_the_feed_asks_for_no_account(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, {})[0] == (False, None)
