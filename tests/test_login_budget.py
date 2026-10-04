"""Logins are budgeted per Tradovate USER (2026-09-29).

Five desk entries on one Apex user each fell back to a full login on their own; a dead
entry (account closed at Apex) re-logged in every 5 minutes. Tradovate answered 429 to
the whole user: the 09:30 order failed and the holder's own web app was locked out.
Fakes only: no sockets, no broker.
"""
from __future__ import annotations

import asyncio
import json
import time as _time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from homebase import config as config_mod
from homebase.broker import login_budget as lb
from homebase.broker.base import AccountNotOnLogin
from homebase.broker.login_budget import LoginBudget
from homebase.broker.tradovate_auth import TradovateAuth
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.server import create_app
from tests.test_engine import FakeAdapter, run

KEY = "tv:demo:apex_326598"
ALERT = {"strategy": "nq930", "upper": 24510.0, "lower": 24490.0}
S429 = "user/syncrequest failed: status=429 data=None"


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _events(journal):
    return [e for e, _ in journal]


def _budget(clock):
    journal = []
    b = LoginBudget(clock=clock, journal=lambda ev, **kw: journal.append((ev, kw)))
    return b, journal


# ---------------------------------------------------------------- the budget itself
def test_rate_limit_detection_and_p_time():
    assert lb.is_rate_limited(S429)
    assert lb.is_rate_limited("HTTP 429 from https://demo/auth: Too Many Requests")
    assert lb.is_rate_limited('Login failed: {"p-ticket": "abc", "p-time": 42}')
    assert lb.is_rate_limited("authorize failed: {'s': 429, 'i': 1}")
    assert not lb.is_rate_limited("socket dropped")
    assert not lb.is_rate_limited("order 4290 rejected")
    assert lb.penalty_seconds('Login failed: {"p-ticket": "abc", "p-time": 42}') == 42.0
    assert lb.penalty_seconds(S429) is None


def test_a_429_cools_the_user_down_with_one_line_in_and_one_out():
    clock = Clock()
    b, journal = _budget(clock)
    assert b.note_error(KEY, S429) is True
    assert b.cooling(KEY) == pytest.approx(lb.COOLDOWN_DEFAULT_S)
    assert b.blocked(KEY, first=True, manual=True) is not None   # nothing bypasses a 429
    for _ in range(5):                                           # more 429s: quiet
        clock.t += 10
        b.note_error(KEY, S429)
    assert _events(journal) == ["login_cooldown_started"]
    clock.t += lb.COOLDOWN_DEFAULT_S + 60
    b.tick()
    b.tick()
    assert _events(journal) == ["login_cooldown_started", "login_cooldown_ended"]
    assert b.blocked(KEY) is None
    assert b.cooling("tv:demo:someone_else") == 0              # per user, not global


def test_p_time_is_honoured():
    clock = Clock()
    b, _ = _budget(clock)
    b.note_error(KEY, 'Login failed: {"p-ticket": "abc", "p-time": 42}')
    assert b.cooling(KEY) == pytest.approx(42)


def test_hourly_cap_and_backoff():
    clock = Clock()
    b, _ = _budget(clock)
    for _ in range(lb.MAX_LOGINS_PER_HOUR):
        assert b.blocked(KEY) is None
        b.record_login(KEY)
        b.login_result(KEY)
        clock.t += 60
    assert "last hour" in b.blocked(KEY)
    assert "last hour" in b.blocked(KEY, manual=True)           # manual: not past the cap
    assert b.blocked(KEY, first=True) is None                   # an entry's first login
    clock.t += 3600
    assert b.blocked(KEY) is None
    b.record_login(KEY)
    b.login_result(KEY, RuntimeError("Login failed: bad password"))
    assert "backing off" in b.blocked(KEY)
    assert b.blocked(KEY, manual=True) is None                  # manual skips the backoff
    clock.t += lb.BACKOFF_BASE_S
    assert b.blocked(KEY) is None
    b.record_login(KEY)
    b.login_result(KEY, RuntimeError("down"))                   # 2nd failure: doubled
    clock.t += lb.BACKOFF_BASE_S
    assert "backing off" in b.blocked(KEY)
    clock.t += lb.BACKOFF_BASE_S
    assert b.blocked(KEY) is None


def test_the_token_refresh_login_fallback_asks_the_budget(tmp_path):
    clock = Clock()
    b, _ = _budget(clock)
    auth = TradovateAuth(env="demo", token_persist_path=tmp_path / "t.json",
                         device_persist_path=tmp_path / "d.json")
    auth._username, auth._password = "u", "p"
    logins = []

    def renew():
        raise RuntimeError("HTTP 429 from https://demo/auth/renewaccesstoken: ")

    auth.renew = renew
    auth.login = lambda u, p: logins.append(u) or "tokens"
    auth.login_guard = b.guard(KEY)
    with pytest.raises(RuntimeError, match="429"):
        auth.refresh()                   # the 429 cools the user: renew only, no login
    assert logins == [] and b.cooling(KEY) > 0

    clock.t += 7200
    auth.renew = lambda: (_ for _ in ()).throw(RuntimeError("Renew failed: expired"))
    assert auth.refresh() == "tokens"    # budget allows: the login fallback runs
    assert logins == ["u"]


# ---------------------------------------------------------------- the desk
class _Stop(Exception):
    pass


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """Two entries on ONE Apex user: `dead` (closed at Apex) and `live` (the 9:30 one)."""
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=True,
                 accounts={"dead": AccountCfg(keyring_key=KEY, account_name="APEX-049"),
                           "live": AccountCfg(keyring_key=KEY, account_name="APEX-053")},
                 book={"nq930": [{"account": "live", "qty": 1}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True)})
    adapters = {"dead": FakeAdapter("dead"), "live": FakeAdapter("live")}
    clock = Clock()
    monkeypatch.setattr(_time, "time", clock)
    app = create_app(cfg, adapters, background=False,
                     adapter_factory=lambda aid, a: FakeAdapter(aid),
                     login_budget=LoginBudget(clock=clock))
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app, c.adapters, c.clock, c.tmp = app, adapters, clock, tmp_path
        yield c


def _instrument(ad, *, reconnect_err=None, connect_err=None):
    ad._connected = False
    ad._auth = NS(tokens={"a": 1})
    calls = {"reconnect": 0, "connect": 0}

    async def reconnect():
        calls["reconnect"] += 1
        if reconnect_err:
            raise reconnect_err
        ad._connected = True

    async def connect():
        calls["connect"] += 1
        if connect_err:
            raise connect_err
        ad._connected = True

    ad.reconnect, ad.connect = reconnect, connect
    return calls


def _loop(desk, monkeypatch, passes, *, step=0.0):
    n = {"i": 0}

    async def fake_sleep(_s):
        n["i"] += 1
        desk.clock.t += step
        if n["i"] >= passes:
            raise _Stop

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(_Stop):
        run(desk.app.state.broker_loop())


def _journal(tmp):
    p = tmp / "journal.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_the_dead_account_stops_looping(desk, monkeypatch):
    calls = _instrument(desk.adapters["dead"],
                        reconnect_err=AccountNotOnLogin("account APEX-049 not on this login "
                                                        "(has: APEX-053)"))
    # a whole day of 5-second passes (in 10-minute steps)
    _loop(desk, monkeypatch, passes=150, step=600)
    assert calls == {"reconnect": 1, "connect": 0}
    st = desk.get("/api/status").json()["accounts"]["dead"]
    assert "APEX-049 is not on this login — remove it from the desk" in st["error"]
    assert [e["event"] for e in _journal(desk.tmp)].count("account_parked") == 1


def test_manual_reconnect_retries_a_parked_account_once(desk, monkeypatch):
    ad = desk.adapters["dead"]
    calls = _instrument(ad, reconnect_err=AccountNotOnLogin("account APEX-049 not on this login"))
    _loop(desk, monkeypatch, passes=3, step=600)
    assert calls["reconnect"] == 1
    r = desk.post("/api/accounts/reconnect", json={"account": "dead"}).json()
    assert r["ok"] is False and "remove it from the desk" in r["results"]["dead"]["error"]
    assert calls == {"reconnect": 2, "connect": 0}              # exactly one more attempt
    _loop(desk, monkeypatch, passes=5, step=600)
    assert calls["reconnect"] == 2                              # still parked
    # the account came back on the login (re-added at Apex): a manual reconnect un-parks it
    ad.reconnect = lambda: _ok(ad)
    r = desk.post("/api/accounts/reconnect", json={"account": "dead"}).json()
    assert r["results"]["dead"]["ok"] is True
    assert "dead" not in desk.app.state.parked


async def _ok(ad):
    ad._connected = True


def test_a_429_cools_down_every_login_on_that_user(desk, monkeypatch):
    dead = _instrument(desk.adapters["dead"], reconnect_err=RuntimeError(S429))
    live = _instrument(desk.adapters["live"], reconnect_err=RuntimeError(S429))
    _loop(desk, monkeypatch, passes=40, step=60)                # 40 minutes of retries
    budget = desk.app.state.login_budget
    # the first 429 cools the user: no entry falls back to a login
    assert dead["connect"] == 0 and live["connect"] == 0
    ev = [e["event"] for e in _journal(desk.tmp)]
    assert ev.count("reconnect_fell_back_to_login") == 0
    assert ev.count("login_cooldown_started") >= 1
    # never more than one line per cool-down in and out (no per-attempt spam)
    assert ev.count("login_cooldown_started") - ev.count("login_cooldown_ended") in (0, 1)
    assert ev.count("login_cooldown_started") <= 3
    assert budget.cooling(KEY) >= 0


def test_logins_per_user_per_hour_are_capped(desk, monkeypatch):
    # every reconnect and every login fails (not a 429): the user's logins are capped
    # however many entries ride it
    d = _instrument(desk.adapters["dead"], reconnect_err=RuntimeError("socket dropped"),
                    connect_err=RuntimeError("still down"))
    l = _instrument(desk.adapters["live"], reconnect_err=RuntimeError("socket dropped"),
                    connect_err=RuntimeError("still down"))
    _loop(desk, monkeypatch, passes=60, step=60)                # one hour
    assert 0 < d["connect"] + l["connect"] <= lb.MAX_LOGINS_PER_HOUR
    _loop(desk, monkeypatch, passes=120, step=60)               # two more hours
    assert d["connect"] + l["connect"] <= 3 * lb.MAX_LOGINS_PER_HOUR


def test_a_healthy_entry_keeps_placing_orders_while_its_user_cools(desk, monkeypatch):
    _instrument(desk.adapters["dead"], reconnect_err=RuntimeError(S429))
    live = desk.adapters["live"]                                 # up, never touched
    _loop(desk, monkeypatch, passes=3, step=5)
    assert desk.app.state.login_budget.cooling(KEY) > 0
    out = run(desk.app.state.engine.handle_alert(dict(ALERT), force_window=True))
    assert out["ok"] and out["armed"]
    assert [r.side for r in live.brackets] == ["Buy", "Sell"]
