"""One token per Tradovate login, shared by its entries (2026-09-29): a startup or a
renewal costs one login / one renewal per USER, not per entry. Each entry keeps its own
socket and pinned account; the 09:20-09:35 renewal rules are unchanged. Also: a healthy
entry whose socket drops while its user's logins are paused retries in place at once.
Fakes only."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

from homebase.broker import tradovate
from homebase.broker.tradovate import TradovateAdapter
from tests.test_login_budget import KEY, S429, _Stop, desk  # noqa: F401
from tests.test_token_renewal import Auth, Sock, at, mkadapter
from tests.test_engine import run


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    monkeypatch.setattr(tradovate, "_SHARED_AUTHS", {})


def test_entries_on_one_login_share_one_auth(tmp_path):
    mk = lambda aid, key="tv:demo:apex", env="demo", share=True: TradovateAdapter(  # noqa: E731
        aid, env=env, keyring_key=key, state_dir=tmp_path, share_auth=share)
    a, b = mk("a"), mk("b")
    assert a._auth is b._auth
    assert mk("c", key="tv:demo:other")._auth is not a._auth
    assert mk("d", env="live")._auth is not a._auth
    assert mk("e", share=False)._auth is not a._auth
    assert a.account_id != b.account_id and a._ws is None and b._ws is None   # own sockets


def test_desk_startup_costs_one_login_per_user(desk, monkeypatch):
    shared = NS(tokens=None)
    calls = {"connect": [], "reconnect": []}
    for aid, ad in desk.adapters.items():
        ad._connected, ad._auth = False, shared

        async def connect(ad=ad):
            calls["connect"].append(ad.account_id)
            shared.tokens = NS(access_token="T1", expires_at_unix=desk.clock.t + 4800)
            ad._connected = True

        async def reconnect(ad=ad):
            calls["reconnect"].append(ad.account_id)
            ad._connected = True

        ad.connect, ad.reconnect = connect, reconnect

    async def one_pass(_s):
        raise _Stop

    monkeypatch.setattr(asyncio, "sleep", one_pass)
    with pytest.raises(_Stop):
        run(desk.app.state.broker_loop())
    assert calls == {"connect": ["dead"], "reconnect": ["live"]}   # 1 login, 2 sockets


def _pair(tmp_path, now, expires):
    a, auth, clock = mkadapter(tmp_path, now, expires)
    b = TradovateAdapter("acct2", env="demo", keyring_key="k", state_dir=tmp_path)
    b._auth = a._auth                       # as share_auth wires it
    b._ws, b._connected, b._now = Sock(), True, a._now
    b._ws_expires = a._ws_expires
    return a, b, auth, clock


async def _both(a, b):
    return await asyncio.gather(a._renew_if_needed(), b._renew_if_needed())


def test_one_renewal_per_user_and_every_sibling_socket_rebuilt(tmp_path):
    a, b, auth, _ = _pair(tmp_path, at(11, 0), at(11, 5))           # normal rule: due
    assert run(_both(a, b)) == [True, True]
    assert auth.renews == 1 and auth.logins == 0
    assert a._ws.closed == 1 and b._ws.closed == 1


def test_the_fire_window_rule_is_unchanged_for_shared_tokens(tmp_path):
    a, b, auth, clock = _pair(tmp_path, at(9, 27), at(9, 36, 30))  # would die after 9:35
    assert run(_both(a, b)) == [False, False]
    assert auth.renews == 0 and a._ws.closed == 0 and b._ws.closed == 0
    clock["now"] = at(9, 29, 30)                                    # inside the fire guard
    assert run(_both(a, b)) == [False, False] and auth.renews == 0


def test_the_early_renewal_before_0920_is_one_per_user(tmp_path):
    a, b, auth, clock = _pair(tmp_path, at(9, 12), at(9, 40))
    assert run(_both(a, b)) == [True, True]
    assert auth.renews == 1
    # after it, nothing is due for either socket before 10:00
    for sock_ad in (a, b):
        sock_ad._ws = Sock(token=a._auth.access_token)
        sock_ad._ws_expires = a._auth.tokens.expires_at_unix
    clock["now"] = at(9, 29, 59)
    assert run(_both(a, b)) == [False, False] and auth.renews == 1


def test_a_dropped_healthy_socket_retries_in_place_at_once_during_a_cooldown(desk, monkeypatch):
    live = desk.adapters["live"]
    live._connected = False
    live._auth = NS(tokens=NS(expires_at_unix=desk.clock.t + 3600))   # still good
    tries = []

    async def reconnect():
        tries.append(desk.clock.t)
        if len(tries) < 3:
            raise RuntimeError(S429)
        live._connected = True

    async def connect():
        raise AssertionError("no login during a cool-down")

    live.reconnect, live.connect = reconnect, connect
    n = {"i": 0}

    async def fake_sleep(_s):
        n["i"] += 1
        desk.clock.t += 5
        if n["i"] >= 12:
            raise _Stop

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(_Stop):
        run(desk.app.state.broker_loop())
    assert len(tries) == 3 and live.connected                  # back within ~30 s, not 5 min
    assert tries[-1] - tries[0] <= 40
    assert desk.app.state.login_budget.cooling(KEY) > 0
