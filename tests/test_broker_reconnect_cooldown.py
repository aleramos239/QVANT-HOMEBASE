"""A pinned account missing from the login is a PERMANENT error, not a
dropped socket: `_connect_account` must never fall back to a full
username/password login for it, and `_broker_loop` must back it off for a
long time.

Review finding, 2026-09-26: apex...044 and ...045 share the keyring login
`tv:demo:apex_326598` with the working apex...047. Treating the missing-pin
error as transient (today's 5-min cooldown, relogin fallback) would burn
~24 full logins/hour on that shared login chasing a pin that will never be
there — a login the working ...047 also needs.
"""
from __future__ import annotations

import asyncio
import time as _time

import pytest

from homebase.broker.base import AccountNotOnLogin
from tests.test_engine import run
from tests.test_server import client  # noqa: F401 — reuse the app fixture


class _StopLoop(Exception):
    """Breaks out of `_broker_loop`'s `while True` after N passes over the
    account list, without actually waiting RECONNECT_INTERVAL_S seconds."""


def _sleep_that_stops_after(n):
    calls = {"n": 0}

    async def fake_sleep(_secs):
        calls["n"] += 1
        if calls["n"] >= n:
            raise _StopLoop

    return fake_sleep


def _run_broker_loop_passes(app, monkeypatch, *, passes, now):
    monkeypatch.setattr(asyncio, "sleep", _sleep_that_stops_after(passes))
    monkeypatch.setattr(_time, "time", lambda: now)
    with pytest.raises(_StopLoop):
        run(app.state.broker_loop())


def test_a_missing_pin_gets_one_attempt_then_the_slow_cooldown(client, monkeypatch):
    ad = client.adapter
    ad._connected = False
    ad._auth = type("Auth", (), {"tokens": {"a": 1}})()  # has_token -> try reconnect first
    calls = {"reconnect": 0, "connect": 0}

    async def reconnect():
        calls["reconnect"] += 1
        raise AccountNotOnLogin("account APEX-044 not on this login (has: APEX-047)")

    async def connect():
        calls["connect"] += 1

    ad.reconnect = reconnect
    ad.connect = connect

    _run_broker_loop_passes(client.app, monkeypatch, passes=2, now=1_000_000.0)

    # exactly one attempt across both passes: the 2nd pass is still cooling down
    assert calls == {"reconnect": 1, "connect": 0}
    assert client.app.state.login_cooldown["main"] == pytest.approx(1_000_000.0 + 1800)
    assert client.app.state.cfg  # sanity: fixture still wired


def test_a_reconnect_that_raises_the_pin_error_never_falls_back_to_connect(client):
    ad = client.adapter
    ad._connected = False
    ad._auth = type("Auth", (), {"tokens": {"a": 1}})()
    calls = {"reconnect": 0, "connect": 0}

    async def reconnect():
        calls["reconnect"] += 1
        raise AccountNotOnLogin("account APEX-044 not on this login (has: APEX-047)")

    async def connect():
        calls["connect"] += 1

    ad.reconnect = reconnect
    ad.connect = connect

    with pytest.raises(AccountNotOnLogin):
        run(client.app.state.connect_account("main"))

    assert calls == {"reconnect": 1, "connect": 0}


def test_other_reconnect_errors_keep_the_relogin_fallback_and_fast_cooldown(client, monkeypatch):
    ad = client.adapter
    ad._connected = False
    ad._auth = type("Auth", (), {"tokens": {"a": 1}})()
    calls = {"reconnect": 0, "connect": 0}

    async def reconnect():
        calls["reconnect"] += 1
        raise RuntimeError("socket dropped")

    async def connect():
        calls["connect"] += 1
        raise RuntimeError("still down")   # the relogin fallback itself also fails

    ad.reconnect = reconnect
    ad.connect = connect

    _run_broker_loop_passes(client.app, monkeypatch, passes=1, now=2_000_000.0)

    assert calls == {"reconnect": 1, "connect": 1}   # today's behaviour: falls back
    assert client.app.state.login_cooldown["main"] == pytest.approx(2_000_000.0 + 300)
