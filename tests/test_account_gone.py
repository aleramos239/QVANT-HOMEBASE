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
_REAL_SLEEP = asyncio.sleep
KEY = "tv:demo:apex_326598"


def _gone_err(listed=("APEX3265980000053", "APEX3265980000050"), user_id=None):
    def make():
        e = AccountNotOnLogin("account APEX3265980000049 not on this login "
                              f"(has: {', '.join(listed)})")
        e.listed, e.user_id = list(listed), user_id
        return e
    return make


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
    cfg = AppCfg(armed=True,
                 accounts={"apex049": AccountCfg(keyring_key=KEY,
                                                 account_name="APEX3265980000049"),
                           "apex053": AccountCfg(keyring_key=KEY,
                                                 account_name="APEX3265980000053"),
                           "apex050": AccountCfg(keyring_key=KEY,
                                                 account_name="APEX3265980000050")},
                 book={"nq930": [{"account": "apex049", "qty": 1},
                                 {"account": "apex053", "qty": 1}],
                       "gc830": [{"account": "apex049", "qty": 1}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True),
                             "gc830": StrategyCfg(symbol="GC", qty=1, offset_pts=1.0,
                                                  sl_pts=3.0, tp_pts=6.0, enabled=True)})
    adapters = {a: FakeAdapter(a) for a in ("apex049", "apex053", "apex050")}
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

    real_sleep = _REAL_SLEEP

    async def fake_sleep_yielding(s):
        await real_sleep(0)            # let a confirming re-sync task run
        await real_sleep(0)
        await fake_sleep(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep_yielding)
    with pytest.raises(_Stop):
        run(desk.app.state.broker_loop())


def _events(desk):
    p = desk.tmp / "journal.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def _booked(desk, aid):
    return [n for n, rows in desk.cfg.book.items() if any(r["account"] == aid for r in rows)]


def test_first_sighting_parks_the_second_unbooks_and_removes(desk, monkeypatch):
    calls = _fails_with(desk.adapters["apex049"], _gone_err())
    _loop(desk, monkeypatch, passes=2, step=5)
    # first sighting: parked and journaled, still booked, still in the pool
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    assert "apex049" in desk.cfg.accounts and "apex049" in desk.app.state.parked
    ev = [e["event"] for e in _events(desk)]
    assert ev.count("account_gone") == 1 and "account_removed" not in ev
    assert calls["n"] == 1
    # ~5 minutes later: one confirming sync, still missing -> unbooked and removed
    _loop(desk, monkeypatch, passes=70, step=5)
    assert calls["n"] == 2
    assert "apex049" not in desk.cfg.accounts and "apex049" not in desk.adapters
    assert _booked(desk, "apex053") == ["nq930"]                # the others untouched
    rem = [e for e in _events(desk) if e["event"] == "account_removed"]
    assert len(rem) == 1 and rem[0]["reason"] == "not on the login any more"
    assert rem[0]["unbooked"] == ["gc830", "nq930"]
    saved = json.loads((desk.tmp / "config.json").read_text())
    assert "apex049" not in json.dumps(saved)
    st = desk.get("/api/status").json()
    assert st["notices"][0]["text"] == \
        "…049 is no longer on your Apex login — removed from the desk"
    assert "apex049" not in st["accounts"]


def test_a_second_sighting_under_five_minutes_does_not_confirm(desk, monkeypatch):
    _fails_with(desk.adapters["apex049"], _gone_err())
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
    state = {"err": _gone_err()}
    calls = _fails_with(ad, lambda: state["err"]())
    _loop(desk, monkeypatch, passes=2, step=5)
    state["err"] = lambda: RuntimeError("user/syncrequest failed: status=429 data=None")
    _loop(desk, monkeypatch, passes=70, step=5)
    assert calls["n"] == 2 and "apex049" in desk.cfg.accounts   # not evidence
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    state["err"] = _gone_err()
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


@pytest.mark.parametrize("err", [
    _gone_err(listed=("APEX9999",)),                    # none of the login's pins listed
    _gone_err(listed=("APEX3265980000050",)),           # 2 of 3 missing: not a minority
    _gone_err(user_id=777),                             # the Tradovate user changed
])
def test_a_changed_login_never_unbooks_or_removes(desk, monkeypatch, err):
    for aid in ("apex049", "apex053"):
        _fails_with(desk.adapters[aid], err)
    desk.app.state.login_uid[KEY] = 111
    _loop(desk, monkeypatch, passes=200, step=30)
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    assert set(desk.cfg.accounts) == {"apex049", "apex053", "apex050"}
    ev = [e["event"] for e in _events(desk)]
    assert "account_gone" not in ev and "account_removed" not in ev
    assert ev.count("login_changed_suspect") == 1
    st = desk.get("/api/status").json()
    assert "may have changed" in st["notices"][0]["text"]
    assert "apex049" in desk.app.state.parked                   # parked, nothing else


def test_nothing_is_rechecked_0910_0935_nor_removed_0920_0935(desk, monkeypatch):
    desk.clock.et = dt.datetime(2026, 9, 29, 9, 5, tzinfo=ET)
    calls = _fails_with(desk.adapters["apex049"], _gone_err())
    _loop(desk, monkeypatch, passes=2, step=5)                   # first sighting 09:05
    _loop(desk, monkeypatch, passes=340, step=5)                 # to ~09:33
    assert calls["n"] == 1                                       # no re-check 09:10-09:35
    assert "apex049" in desk.cfg.accounts
    _loop(desk, monkeypatch, passes=40, step=5)                  # past 09:35
    assert calls["n"] == 2 and "apex049" not in desk.cfg.accounts


def test_a_confirmed_removal_waits_out_0920_0935(desk, monkeypatch):
    _fails_with(desk.adapters["apex049"], _gone_err())
    _loop(desk, monkeypatch, passes=2, step=5)
    desk.clock.advance(GONE_CONFIRM_S)
    desk.clock.et = dt.datetime(2026, 9, 29, 9, 22, tzinfo=ET)
    desk.post("/api/accounts/reconnect", json={"account": "apex049"})   # confirms
    _loop(desk, monkeypatch, passes=100, step=5)                 # to ~09:30
    assert "apex049" in desk.cfg.accounts and _booked(desk, "apex049") == ["nq930", "gc830"]
    _loop(desk, monkeypatch, passes=80, step=5)                  # past 09:35
    assert "apex049" not in desk.cfg.accounts


def test_a_hung_recheck_never_holds_the_supervisor(desk, monkeypatch):
    ad = desk.adapters["apex049"]
    _fails_with(ad, _gone_err())
    _loop(desk, monkeypatch, passes=2, step=5)
    hung = asyncio.Event()

    async def hang():
        await hung.wait()

    ad.reconnect = ad.connect = hang
    other = desk.adapters["apex053"]
    _loop(desk, monkeypatch, passes=62, step=5)                  # the re-check starts, hangs
    other._connected = False                                     # meanwhile a healthy drop
    other._auth = type("Auth", (), {"tokens": {"a": 1}})()

    async def ok():
        other._connected = True

    other.reconnect = ok
    _loop(desk, monkeypatch, passes=3, step=5)
    assert other.connected                                       # the supervisor kept going
    assert "apex049" in desk.cfg.accounts


def test_an_account_that_comes_back_is_kept_with_its_bookings(desk, monkeypatch):
    ad = desk.adapters["apex049"]
    _fails_with(ad, _gone_err())
    _loop(desk, monkeypatch, passes=2, step=5)
    desk.app.state.gone["apex049"]["booked"] = {"nq930": [{"account": "apex049", "qty": 1}]}
    desk.cfg.book["nq930"] = [r for r in desk.cfg.book["nq930"] if r["account"] != "apex049"]

    async def ok():
        ad._connected = True

    ad.reconnect = ok
    _loop(desk, monkeypatch, passes=70, step=5)
    assert "apex049" in desk.cfg.accounts and ad.connected
    assert _booked(desk, "apex049") == ["nq930", "gc830"]
    back = [e for e in _events(desk) if e["event"] == "account_back"]
    assert back and back[0]["rebooked"] == ["nq930"]
    assert "account_removed" not in [e["event"] for e in _events(desk)]


def test_a_removal_cancels_an_in_flight_recheck_and_is_never_reconnected(desk, monkeypatch):
    """N2: per-account connect lock; a removed account is never reconnected."""
    ad = desk.adapters["apex049"]
    _fails_with(ad, _gone_err())
    _loop(desk, monkeypatch, passes=2, step=5)                   # first sighting
    desk.clock.advance(GONE_CONFIRM_S + 1)
    started, hung = [], asyncio.Event()

    async def hang():
        started.append(1)
        await hung.wait()

    ad.reconnect = ad.connect = hang
    state = desk.app.state

    async def scenario():
        await state.gone_step()                                  # spawns the re-check task
        for _ in range(3):
            await _REAL_SLEEP(0)
        assert started == [1]                                    # in flight, holding the lock
        await state.drop_account("apex049")                      # cancels it, then removes
        with pytest.raises(RuntimeError, match="no longer on the desk"):
            await state.connect_account("apex049")

    run(scenario())
    assert "apex049" not in desk.cfg.accounts and "apex049" not in desk.adapters
    assert "apex049" not in state.gone and "apex049" not in state.parked
    state.connect_failed("apex049", _gone_err()())               # a late failure: ignored
    assert "apex049" not in state.gone and "apex049" not in state.parked


def test_connects_of_one_account_never_overlap(desk):
    ad = desk.adapters["apex049"]
    ad._connected = False
    ad._auth = type("Auth", (), {"tokens": {"a": 1}})()
    live, peak = {"n": 0}, {"n": 0}

    async def reconnect():
        live["n"] += 1
        peak["n"] = max(peak["n"], live["n"])
        await _REAL_SLEEP(0)
        await _REAL_SLEEP(0)
        live["n"] -= 1
        ad._connected = True

    ad.reconnect = reconnect

    async def race():
        await asyncio.gather(*(desk.app.state.connect_account("apex049") for _ in range(3)))

    run(race())
    assert peak["n"] == 1
