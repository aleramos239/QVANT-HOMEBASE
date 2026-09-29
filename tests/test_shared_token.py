"""One token per Tradovate login, shared by its entries (2026-09-29): a startup or a
renewal costs one login / one renewal per USER, not per entry. Each entry keeps its own
socket and pinned account; the 09:20-09:35 renewal rules are unchanged. Also: a healthy
entry whose socket drops while its user's logins are paused retries in place at once.
Fakes only."""
from __future__ import annotations

import asyncio
import datetime as dt
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


# ---------------------------------------------------------------- review 2026-09-29
from homebase import ticks  # noqa: E402
from homebase.broker.login_budget import LoginBudget  # noqa: E402
from homebase.broker.tradovate_auth import TradovateTokens  # noqa: E402
from tests.test_engine import FakeAdapter  # noqa: E402
from tests.test_token_renewal import iso  # noqa: E402


def test_the_shared_token_lands_in_every_sharing_entrys_file(tmp_path, monkeypatch):
    mk = lambda aid: TradovateAdapter(aid, env="demo", keyring_key="tv:demo:apex",  # noqa: E731
                                      state_dir=tmp_path, share_auth=True)
    a, b, c = mk("a"), mk("b"), mk("c")
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=80)
    a._auth.tokens = TradovateTokens(access_token="T", md_access_token="MD",
                                     expiration_time=iso(exp))
    a._auth._persist_tokens()
    monkeypatch.setattr(ticks, "state_dir", lambda: tmp_path)
    got = ticks._valid_md_tokens([("b", None), ("c", None)])     # "a" removed: still fine
    assert [(g[0], g[2]) for g in got] == [("b", "MD"), ("c", "MD")]
    c.go_private()                                               # a private entry: its own file
    a._auth.tokens.md_access_token = "MD2"
    a._auth._persist_tokens()
    assert [g[2] for g in ticks._valid_md_tokens([("b", None), ("c", None)])] == ["MD2", "MD"]


def test_go_private_leaves_the_shared_token_alone(tmp_path):
    mk = lambda aid: TradovateAdapter(aid, env="demo", keyring_key="tv:demo:apex",  # noqa: E731
                                      state_dir=tmp_path, share_auth=True)
    a, b = mk("a"), mk("b")
    shared = a._auth
    shared.tokens = TradovateTokens(access_token="SHARED")
    b.login_budget = LoginBudget()
    b.go_private()
    assert b._auth is not shared and b._auth.tokens is None and not b.auth_shared
    assert a.auth_shared and shared.tokens.access_token == "SHARED"
    assert b._auth.login_guard is not None                       # its login is budgeted
    b._auth.login = lambda u, p: setattr(b._auth, "tokens", TradovateTokens("PRIVATE"))
    b._auth.login("u", "p")
    assert shared.tokens.access_token == "SHARED"                # never re-rolled
    b2 = mk("b")                                                 # a new process shares again
    assert b2.auth_shared


class _SharedFake(FakeAdapter):
    def __init__(self, aid):
        super().__init__(aid)
        self.auth_shared, self.privates = True, 0

    def go_private(self):
        self.privates += 1
        self.auth_shared = False


@pytest.mark.parametrize("err, private, logins", [
    ("authorize failed: {'s': 401, 'd': 'Access is denied'}", 1, 1),   # refused: private login
    ("authorize failed: {'s': 429, 'd': None}", 0, 0),                 # 429: cool-down, nothing
])
def test_a_sibling_refused_on_the_shared_token(desk, err, private, logins):
    ad = _SharedFake("live")
    desk.adapters["live"] = ad
    ad._connected, ad._auth = False, NS(tokens=NS(access_token="SHARED",
                                                 expires_at_unix=desk.clock.t + 3600))
    n = {"login": 0}

    async def reconnect():
        raise RuntimeError(err)

    async def connect():
        n["login"] += 1
        ad._connected = True

    ad.reconnect, ad.connect = reconnect, connect
    try:
        run(desk.app.state.connect_account("live"))
    except Exception:  # noqa: BLE001 — the 429 path is deferred
        pass
    assert ad.privates == private and n["login"] == logins
    assert (desk.app.state.login_budget.cooling(KEY) > 0) is (private == 0)


def _renew_pair(tmp_path, now, expires, renew_error=None):
    a, auth, clock = mkadapter(tmp_path, now, expires, renew_error=renew_error)
    b = TradovateAdapter("acct2", env="demo", keyring_key="k", state_dir=tmp_path)
    b._auth = a._auth
    b._ws, b._connected, b._now, b._ws_expires = Sock(), True, a._now, a._ws_expires
    return a, b, auth, clock


def test_siblings_skip_renewing_for_60s_after_a_failed_renewal(tmp_path):
    a, b, auth, clock = _renew_pair(tmp_path, at(11, 0), at(11, 5), renew_error="HTTP 500")
    with pytest.raises(RuntimeError):
        run(a._renew_if_needed())
    assert auth.renews == 1
    assert run(b._renew_if_needed()) is False and auth.renews == 1    # held
    clock["now"] = at(11, 1, 1)
    with pytest.raises(RuntimeError):
        run(b._renew_if_needed())
    assert auth.renews == 2


def test_a_cooling_user_renews_only_a_token_about_to_die(tmp_path):
    a, auth, clock = mkadapter(tmp_path, at(11, 0), at(11, 8))       # due by the normal rule
    budget = LoginBudget(clock=lambda: at(11, 0).timestamp())
    budget.note_error("k", "status=429")
    a.login_budget = budget
    assert run(a._renew_if_needed()) is False and auth.renews == 0
    assert a._rebuild_buffer_s(at(11, 0)) == tradovate.COOL_RENEW_WITHIN_S
    clock["now"] = at(11, 5, 30)                                       # 2.5 min left
    assert run(a._renew_if_needed()) is True and auth.renews == 1


def test_a_cooling_user_keeps_the_0910_early_renewal(tmp_path):
    a, auth, _ = mkadapter(tmp_path, at(9, 12), at(9, 40))
    budget = LoginBudget(clock=lambda: at(9, 12).timestamp())
    budget.note_error("k", "status=429")
    a.login_budget = budget
    assert run(a._renew_if_needed()) is True and auth.renews == 1
