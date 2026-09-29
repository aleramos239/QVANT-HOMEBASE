"""An account that left its login (blown / closed at the prop firm) is removed from the
desk on its own (2026-09-29, apex...049) -- but only on the evidence of successful syncs.

A successful sync that lists the login's OTHER accounts and not this one: unbook it from
every strategy at once, stop connecting it, journal account_gone. A second such sync at
least GONE_CONFIRM_S later: remove the entry (account_removed, "not on the login any
more"). Never on a failed / 429 / empty sync; never inside 09:20-09:35 ET. Fakes only.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time as _time

import pytest
from fastapi.testclient import TestClient

from homebase import config as config_mod
from homebase.broker.base import AccountNotOnLogin
from homebase.broker.login_budget import LoginBudget
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.server import GONE_CONFIRM_S, create_app
from tests.test_engine import FakeAdapter, run

ET = dt.timezone(dt.timedelta(hours=-4))
KEY = "tv:demo:apex_326598"


def _gone_err():
    e = AccountNotOnLogin("account APEX3265980000049 not on this login "
                          "(has: APEX3265980000053)")
    e.listed = ["APEX3265980000053"]
    return e


class _Stop(Exception):
    pass


class Clock:
    def __init__(self):
        self.t = 1_000_000.0
        self.et = dt.datetime(2026, 9, 29, 11, 0, tzinfo=ET)     # a Tuesday, 11:00 ET

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s
        self.et += dt.timedelta(seconds=s)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=True, webhook_secret="s",
                 accounts={"apex049": AccountCfg(keyring_key=KEY,
                                                 account_name="APEX3265980000049"),
                           "apex053": AccountCfg(keyring_key=KEY,
                                                 account_name="APEX3265980000053")},
                 book={"nq930": [{"account": "apex049", "qty": 1},
                                 {"account": "apex053", "qty": 1}],
                       "gc830": [{"account": "apex049", "qty": 1}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True),
                             "gc830": StrategyCfg(symbol="GC", qty=1, offset_pts=1.0,
                                                  sl_pts=3.0, tp_pts=6.0, enabled=True)})
    adapters = {"apex049": FakeAdapter("apex049"), "apex053": FakeAdapter("apex053")}
    clock = Clock()
    monkeypatch.setattr(_time, "time", clock)
    app = create_app(cfg, adapters, background=False,
                     adapter_factory=lambda aid, a: FakeAdapter(aid),
                     login_budget=LoginBudget(clock=clock))
    app.state.engine.now_et = lambda: clock.et
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app, c.cfg, c.adapters, c.clock, c.tmp = app, cfg, adapters, clock, tmp_path
        yield c


def _fails_with(ad, err):
    ad._connected = False
    ad._auth = type("Auth", (), {"tokens": {"a": 1}})()
    calls = {"n": 0}

    async def reconnect():
        calls["n"] += 1
        raise (err() if callable(err) else err)

    ad.reconnect = ad.connect = reconnect      # a login fallback syncs the same answer
    return calls


def _loop(desk, monkeypatch, passes, step):
    n = {"i": 0}

    async def fake_sleep(_s):
        n["i"] += 1
        desk.clock.advance(step)
        if n["i"] >= passes:
            raise _Stop

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(_Stop):
        run(desk.app.state.broker_loop())


def _events(desk):
    p = desk.tmp / "journal.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def _booked(desk, aid):
    return [n for n, rows in desk.cfg.book.items() if any(r["account"] == aid for r in rows)]


def test_gone_account_is_unbooked_at_once_then_removed_after_a_second_sync(desk, monkeypatch):
    calls = _fails_with(desk.adapters["apex049"], _gone_err)
    _loop(desk, monkeypatch, passes=2, step=5)
    # first sighting: unbooked everywhere, parked, account_gone -- still in the pool
    assert _booked(desk, "apex049") == []
    assert _booked(desk, "apex053") == ["nq930"]                 # the others untouched
    assert "apex049" in desk.cfg.accounts
    ev = [e["event"] for e in _events(desk)]
    assert ev.count("account_gone") == 1 and "account_removed" not in ev
    assert calls["n"] == 1                                       # stopped connecting it
    saved = json.loads((desk.tmp / "config.json").read_text())
    assert "apex049" not in json.dumps(saved.get("book", {}))
    # ~5 minutes later: one confirming sync, still missing -> removed
    _loop(desk, monkeypatch, passes=70, step=5)
    assert calls["n"] == 2
    assert "apex049" not in desk.cfg.accounts and "apex049" not in desk.adapters
    rem = [e for e in _events(desk) if e["event"] == "account_removed"]
    assert len(rem) == 1 and rem[0]["reason"] == "not on the login any more"
    st = desk.get("/api/status").json()
    assert st["notices"][0]["text"] == \
        "…049 is no longer on your Apex login — removed from the desk"
    assert "apex049" not in st["accounts"]


def test_a_second_sighting_under_five_minutes_does_not_confirm(desk, monkeypatch):
    _fails_with(desk.adapters["apex049"], _gone_err)
    _loop(desk, monkeypatch, passes=2, step=5)
    r = desk.post("/api/accounts/reconnect", json={"account": "apex049"}).json()
    assert r["ok"] is False
    _loop(desk, monkeypatch, passes=2, step=5)
    assert "apex049" in desk.cfg.accounts                       # not yet
    desk.clock.advance(GONE_CONFIRM_S)
    desk.post("/api/accounts/reconnect", json={"account": "apex049"})
    _loop(desk, monkeypatch, passes=2, step=5)
    assert "apex049" not in desk.cfg.accounts                   # a manual sync confirms too


@pytest.mark.parametrize("err", [
    RuntimeError("user/syncrequest failed: status=429 data=None"),
    RuntimeError("websocket not connected"),
    AccountNotOnLogin("account APEX3265980000049 not on this login (has: )"),  # no listing
])
def test_a_failed_429_or_unlisted_sync_never_acts(desk, monkeypatch, err):
    _fails_with(desk.adapters["apex049"], err)
    _loop(desk, monkeypatch, passes=200, step=30)
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    assert "apex049" in desk.cfg.accounts
    ev = [e["event"] for e in _events(desk)]
    assert "account_gone" not in ev and "account_removed" not in ev


def test_a_429_on_the_confirming_sync_does_not_remove(desk, monkeypatch):
    ad = desk.adapters["apex049"]
    state = {"err": _gone_err}
    calls = _fails_with(ad, lambda: state["err"]())
    _loop(desk, monkeypatch, passes=2, step=5)
    assert _booked(desk, "apex049") == []
    state["err"] = lambda: RuntimeError("user/syncrequest failed: status=429 data=None")
    _loop(desk, monkeypatch, passes=70, step=5)
    assert calls["n"] == 2 and "apex049" in desk.cfg.accounts   # not evidence
    state["err"] = _gone_err
    _loop(desk, monkeypatch, passes=70, step=5)
    assert "apex049" not in desk.cfg.accounts


def test_an_empty_account_list_warns_and_does_nothing(desk, monkeypatch):
    _fails_with(desk.adapters["apex049"],
                RuntimeError("apex049: login exposes no accounts"))
    _loop(desk, monkeypatch, passes=200, step=30)
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    assert "apex049" in desk.cfg.accounts
    ev = [e["event"] for e in _events(desk)]
    assert ev.count("login_lists_no_accounts") == 1
    assert "account_gone" not in ev
    st = desk.get("/api/status").json()
    assert "listed no accounts" in st["notices"][0]["text"]


def test_nothing_is_unbooked_or_removed_inside_0920_0935(desk, monkeypatch):
    desk.clock.et = dt.datetime(2026, 9, 29, 9, 22, tzinfo=ET)
    _fails_with(desk.adapters["apex049"], _gone_err)
    _loop(desk, monkeypatch, passes=100, step=5)                 # to 09:30:20
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    assert "account_gone" not in [e["event"] for e in _events(desk)]
    _loop(desk, monkeypatch, passes=60, step=5)                  # to 09:35:20
    # deferred, then done at 09:35: unbooked, and the first sighting (09:22) is more
    # than GONE_CONFIRM_S old, so the confirming sync runs and removes it
    assert _booked(desk, "apex049") == []
    ev = [e["event"] for e in _events(desk)]
    assert ev.index("account_gone") < ev.index("account_removed")
    assert "apex049" not in desk.cfg.accounts


def test_an_account_that_comes_back_is_kept(desk, monkeypatch):
    ad = desk.adapters["apex049"]
    _fails_with(ad, _gone_err)
    _loop(desk, monkeypatch, passes=2, step=5)

    async def ok():
        ad._connected = True

    ad.reconnect = ok
    _loop(desk, monkeypatch, passes=70, step=5)
    assert "apex049" in desk.cfg.accounts and ad.connected
    ev = [e["event"] for e in _events(desk)]
    assert "account_back" in ev and "account_removed" not in ev
