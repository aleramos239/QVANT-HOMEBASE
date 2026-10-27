"""Audit 2026-10-27 (feed group): HOMEBASE_CHARTS_MD_ONLY=demo is honoured by every md connect and by Refresh data."""
from __future__ import annotations

import asyncio

import pytest

from homebase.charts import refresh as R
from homebase.data import ticks as T


def test_a_pinned_machine_never_connects_on_the_other_login(monkeypatch):
    monkeypatch.setenv("HOMEBASE_CHARTS_MD_ONLY", "demo")
    seen = []

    def tok(prefer_live, strict=False):
        seen.append(prefer_live)
        return "t", "live"                                    # only the live token is on disk
    monkeypatch.setattr(T, "md_token", tok)
    with pytest.raises(T.NoMdToken):
        asyncio.run(T.connect_md())
    assert seen == [False]                                    # it asked for the demo login first


def test_refresh_refuses_on_a_demo_only_machine(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBASE_CHARTS_MD_ONLY", "demo")
    mgr = R.RefreshManager.__new__(R.RefreshManager)
    import threading
    mgr._lock, mgr._status = threading.Lock(), {}
    with pytest.raises(ValueError, match="demo login only"):
        mgr.start()
