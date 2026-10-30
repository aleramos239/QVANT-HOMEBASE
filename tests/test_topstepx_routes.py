"""The TopstepX login on the desk's routes and builder: /api/connect (new, saved, with a code), the login budget, add-many
(practice = demo, the rest live), one session per login, md_source, /api/logins. No network: a real TsxSession runs over an
httpx MockTransport (the fake userapi), registered in brokers._TSX_SESSIONS exactly as build_adapter shares it."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.broker import topstepx
from homebase.broker.topstepx import TopstepXAdapter
from homebase.broker.topstepx_auth import TsxSession
from homebase.config import AccountCfg, AppCfg
from homebase.desk_app import brokers
from homebase.desk_app.brokers import _key_env, build_adapter, is_tsx_key, md_source
from homebase.server import create_app
from homebase.store import secrets_store
from tests.test_engine import FakeAdapter
from tests.test_login_budget import S429

USER = "Owner@Example.com"
KEY = "tsx:owner@example.com"
PASSWORD = "pw-SECRET-123"
TOKEN = "TOK-SECRET-456"
ACCOUNTS = [{"id": 11, "name": "PRAC-V2-1", "balance": 150000.0}, {"id": 22, "name": "Combine-50K", "balance": 50000.0}]
ET = ZoneInfo("America/New_York")


class Api:
    """The fake userapi: every call recorded; /Login answers `login` (a dict, or a function of the request body)."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.login = {"token": TOKEN, "userId": 5}
        self.hold: tuple | None = None        # (entered, gate): the NEXT /Login waits for gate, then answers token TOK-2

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        p = req.url.path
        if p == "/Login" and self.hold:
            entered, gate = self.hold
            self.hold = None

            async def later():
                entered.set()
                while not gate.is_set():
                    await asyncio.sleep(0.01)
                return httpx.Response(200, json={"token": "TOK-2", "userId": 5})
            return later()
        if p == "/Login":
            return httpx.Response(200, json=self.login(json.loads(req.content)) if callable(self.login) else self.login)
        if p == "/TradingAccount":
            return httpx.Response(200, json=ACCOUNTS)
        if req.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"success": True})

    def logins(self) -> list[dict]:
        return [json.loads(c.content) for c in self.calls if c.url.path == "/Login"]


class StubHub:
    up = False

    def __init__(self, session, on_event, *, on_up=None, on_auth_lost=None, **kw):
        self.on_auth_lost = on_auth_lost
        self._token = session._token        # what the socket was opened with

    async def start(self):
        pass

    async def stop(self):
        pass


@pytest.fixture()
def api():
    return Api()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.desk.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(secrets_store, "_migrate_from_keychain", lambda key: None)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(topstepx, "TsxHub", StubHub)
    monkeypatch.setattr(brokers, "_TSX_SESSIONS", {})


@pytest.fixture()
def client(tmp_path, api, monkeypatch):
    brokers._TSX_SESSIONS[KEY] = TsxSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(api)))
    # any other session would be a second one for the key and would reach the real TopstepX: never in a test
    monkeypatch.setattr(brokers, "TsxSession", lambda key, **kw: pytest.fail(f"a new TsxSession for {key}"))
    cfg = AppCfg(armed=False, accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")})
    app = create_app(cfg, {"main": FakeAdapter("main")}, background=False)
    app.state.engine.now_et = lambda: dt.datetime(2026, 10, 30, 11, 0, tzinfo=ET)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app = app
        yield c


def connect(client, **kw):
    return client.post("/api/connect", json={"broker": "tsx", "username": USER, "password": PASSWORD, **kw})


def budget_logins(client) -> int:
    return len(client.app.state.login_budget._users[KEY].logins)


def test_connect_with_broker_tsx_saves_tsx_key_and_lists_accounts(client, api, tmp_path):
    r = connect(client)
    assert r.json() == {"ok": True, "key": KEY, "env": "tsx", "accounts": [
        {"id": 11, "name": "PRAC-V2-1", "active": True, "practice": True, "on_desk": False},
        {"id": 22, "name": "Combine-50K", "active": True, "practice": False, "on_desk": False}]}
    assert secrets_store.get_credentials(KEY) == {"username": USER, "password": PASSWORD}
    assert api.logins() == [{"userName": USER, "password": PASSWORD}]      # one /Login; the probe rode its token
    assert budget_logins(client) == 1
    assert PASSWORD not in r.text and TOKEN not in r.text
    # a saved login goes through the same route: the live token, no second /Login
    assert client.post("/api/connect", json={"saved_key": KEY}).json()["ok"]
    assert len(api.logins()) == 1 and budget_logins(client) == 1
    for p in tmp_path.glob("*.jsonl"):
        assert PASSWORD not in p.read_text() and TOKEN not in p.read_text()
    assert all("authorization" not in k.lower() or TOKEN in v for c in api.calls for k, v in c.headers.items())


def test_a_wrong_password_answers_the_words_not_the_password(client, api):
    api.login = lambda body: {"errorMessage": f"bad login for {body['password']}", "result": 3}
    r = connect(client)
    assert r.json()["ok"] is False and "bad login" in r.json()["error"]
    assert PASSWORD not in r.text and TOKEN not in r.text


def test_connect_goes_through_the_login_budget(client, api):
    client.app.state.login_budget.note_error(KEY, S429)             # TopstepX said 429: the cool-down
    r = connect(client).json()
    assert r["ok"] is False and r["error"].startswith("TopstepX rate-limited this login") and r["key"] == KEY
    assert api.logins() == []
    r = client.post("/api/connect", json={"saved_key": KEY}).json()   # a saved login is refused the same way
    assert r["ok"] is False and "TopstepX rate-limited" in r["error"] and api.logins() == []


def test_needs_code_answers_needs_code_true(client, api):
    api.login = lambda body: {"verificationCode": True} if "code" not in body else {"token": TOKEN, "userId": 5}
    r = connect(client)
    assert r.json() == {"ok": False, "needs_code": True, "key": KEY}
    assert PASSWORD not in r.text and TOKEN not in r.text
    r = connect(client, code="123456").json()
    assert r["ok"] and r["env"] == "tsx" and len(r["accounts"]) == 2
    assert api.logins()[-1]["code"] == "123456" and len(api.logins()) == 2    # the probe rode the coded login's token
    # a saved login with no token and no code is asked for a code again: needs_code, not an error
    brokers._TSX_SESSIONS[KEY]._token = None
    assert client.post("/api/connect", json={"saved_key": KEY}).json() == {"ok": False, "needs_code": True, "key": KEY}


def test_add_many_marks_practice_demo_and_the_rest_live(client):
    connect(client)
    out = client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1", "Combine-50K"]}).json()
    assert out["ok"] and out["added"] == 2, out        # a TopstepX entry's "login" mode never stops the batch
    accts = client.app.state.cfg.accounts
    assert (accts["prac-v2-1"].live, accts["combine-50k"].live) == (False, True)
    assert {accts["prac-v2-1"].keyring_key, accts["combine-50k"].keyring_key} == {KEY}
    assert all(r["connected"] for r in out["results"]), out
    ads = client.app.state.adapters
    assert isinstance(ads["prac-v2-1"], TopstepXAdapter) and ads["prac-v2-1"].session is ads["combine-50k"].session
    assert ads["prac-v2-1"].session.budget is client.app.state.login_budget
    assert ads["prac-v2-1"].journal == ads["prac-v2-1"].session.journal == client.app.state.engine.journal
    assert budget_logins(client) == 1                  # the wizard's login; entries rode its token
    assert client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]}).json()["exists"] == 1
    assert client.post("/api/accounts/add", json={"key": KEY, "account_name": "PRAC-V2-1"}).status_code == 400


def test_the_desk_books_a_login_only_when_the_session_sends_one(client, api):
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    sess = brokers._TSX_SESSIONS[KEY]
    ad = client.app.state.adapters["prac-v2-1"]
    assert budget_logins(client) == 1 and len(api.logins()) == 1
    r = client.post("/api/accounts/reconnect", json={"account": "prac-v2-1"}).json()          # token held: no /Login
    assert r["results"]["prac-v2-1"]["ok"] and budget_logins(client) == 1 and len(api.logins()) == 1
    sess._token = None                                                                          # token gone: connect logs in
    r = client.post("/api/accounts/reconnect", json={"account": "prac-v2-1"}).json()
    assert r["results"]["prac-v2-1"]["ok"] and len(api.logins()) == 2 and budget_logins(client) == 2   # once, not twice
    assert client.app.state.adapters["prac-v2-1"] is ad                                         # the same object: its seen-trades survive


def test_a_reconnect_asked_for_a_code_shows_it_on_the_card(client, api):
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    api.login = {"verificationCode": True}
    brokers._TSX_SESSIONS[KEY]._token = None
    r = client.post("/api/accounts/reconnect", json={"account": "prac-v2-1"}).json()
    assert r["results"]["prac-v2-1"] == {"ok": False, "error": "TopstepX needs a code"}


def test_build_adapter_makes_a_TopstepXAdapter_sharing_one_session_per_login():
    a = build_adapter("a", AccountCfg(keyring_key=KEY, account_name="PRAC-V2-1", live=False))
    b = build_adapter("b", AccountCfg(keyring_key=KEY, account_name="Combine-50K", live=True))
    probe = build_adapter("probe", AccountCfg(keyring_key=KEY))
    assert all(isinstance(x, TopstepXAdapter) for x in (a, b, probe))
    assert a.session is b.session is probe.session is brokers.tsx_session(KEY)
    assert (a.account_name, a.live, b.live, probe.account_name) == ("PRAC-V2-1", False, True, "")
    assert build_adapter("c", AccountCfg(keyring_key="tsx:other")).session is not a.session


def test_md_source_never_picks_a_tsx_login():
    cfg = AppCfg(accounts={"t": AccountCfg(keyring_key=KEY, account_name="Combine-50K", live=True)})
    with pytest.raises(RuntimeError, match="no accounts configured for market data"):
        md_source(cfg, {})
    cfg.accounts["tv"] = AccountCfg(keyring_key="tv:demo:u")
    assert md_source(cfg, {})[0] == "tv:demo:u"


def test_logins_lists_tsx_with_env_tsx(client):
    secrets_store.set_credentials(KEY, username=USER, password=PASSWORD)
    row = next(x for x in client.get("/api/logins").json()["logins"] if x["key"] == KEY)
    assert row == {"key": KEY, "label": USER, "env": "tsx", "in_use": False}
    assert _key_env(KEY) == "tsx" and is_tsx_key(KEY) and not is_tsx_key("tv:live:u")
    assert PASSWORD not in client.get("/api/logins").text
    assert client.post("/api/logins/delete", json={"key": KEY}).json() == {"ok": True}
    assert KEY not in brokers._TSX_SESSIONS


def spend_the_cap(client):
    for _ in range(10):
        client.app.state.login_budget.record_login(KEY)


def test_the_hourly_cap_refuses_a_login_that_is_not_the_first(client, api):
    connect(client)                                      # the first login (exempt) is spent
    spend_the_cap(client)
    n = len(api.logins())
    for r in (connect(client).json(), connect(client, code="1").json(),
              client.post("/api/connect", json={"saved_key": KEY}).json()):
        assert r["ok"] is False and "logins on this user in the last hour" in r["error"] and r["key"] == KEY
    assert len(api.logins()) == n


def test_a_reconnect_on_a_held_token_is_not_refused_by_the_cap(client, api):
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    spend_the_cap(client)
    booked, sent = budget_logins(client), len(api.logins())
    r = client.post("/api/accounts/reconnect", json={"account": "prac-v2-1"}).json()["results"]["prac-v2-1"]
    assert r["ok"] and budget_logins(client) == booked and len(api.logins()) == sent      # no /Login, no booking
    brokers._TSX_SESSIONS[KEY]._token = None             # a real /Login is needed: the budget still refuses it
    r = client.post("/api/accounts/reconnect", json={"account": "prac-v2-1"}).json()["results"]["prac-v2-1"]
    assert r["ok"] is False and "logins on this user in the last hour" in r["error"] and len(api.logins()) == sent


def test_answering_the_code_frees_the_accounts_cooldown(client, api):
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1", "Combine-50K"]})
    api.login = lambda body: {"verificationCode": True} if "code" not in body else {"token": TOKEN, "userId": 5}
    brokers._TSX_SESSIONS[KEY]._token = None
    client.post("/api/accounts/reconnect", json={})      # both cards ask for a code and wait 30 minutes
    cool = client.app.state.login_cooldown
    assert {"prac-v2-1", "combine-50k"} <= set(cool) and "main" not in cool
    assert client.post("/api/connect", json={"saved_key": KEY, "code": "123456"}).json()["ok"]
    assert "prac-v2-1" not in cool and "combine-50k" not in cool


def test_a_kick_arriving_during_the_wizards_login_makes_no_second_login(client, api):
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    sess = brokers._TSX_SESSIONS[KEY]
    hub = sess.hub
    assert hub is not None and hub._token == TOKEN
    entered, gate = threading.Event(), threading.Event()
    api.hold = (entered, gate)
    before = len(api.logins())
    with ThreadPoolExecutor(1) as pool:
        wiz = pool.submit(connect, client, code="123456")
        assert entered.wait(5)                           # the wizard's login is in flight, holding the session's lock
        kick = client.portal.start_task_soon(hub.on_auth_lost)    # the old token is refused by the socket meanwhile
        gate.wait(0.3)                                   # give the kick time to reach (and wait on) the lock
        gate.set()
        assert wiz.result(10).json()["ok"]
        kick.result(10)
    assert len(api.logins()) == before + 1               # one /Login: the kick found the token already replaced
    assert sess._token == "TOK-2" and sess.taken == 1


def test_deleting_a_login_closes_its_session(client):
    secrets_store.set_credentials(KEY, username=USER, password=PASSWORD)
    closed = []
    sess = brokers._TSX_SESSIONS[KEY]
    sess.aclose = lambda: _closed(closed)
    assert client.post("/api/logins/delete", json={"key": KEY}).json() == {"ok": True}
    assert closed == [1]


async def _closed(box):
    box.append(1)


def test_booking_a_tsx_account_is_refused_in_words_and_the_self_test_waits_for_the_caches(client, api):
    from homebase.config import StrategyCfg
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    cfg = client.app.state.cfg
    cfg.strategies["nq930"] = StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0)
    assert topstepx.TSX_BOOKING_OPEN is False
    r = client.post("/api/book", json={"strategy": "nq930", "assignments": [
        {"account": "main", "qty": 1}, {"account": "prac-v2-1", "qty": 1}]})
    assert r.status_code == 409 and r.json()["detail"] == topstepx.TSX_BOOKING_CLOSED
    assert "nq930" not in cfg.book                                  # nothing written, not even the non-TopstepX row
    assert client.post("/api/book", json={"strategy": "nq930", "assignments": [
        {"account": "main", "qty": 1}]}).json()["ok"]               # other accounts book as before
    # the self-test route stays: it waits for the caches (the stub socket is not up: unknown is not idle)
    r = client.post("/api/selftest-order", json={"account": "prac-v2-1", "ref_price": 20000})
    assert r.status_code == 409 and "not read yet" in r.json()["detail"]


def test_an_account_gone_and_back_never_gets_a_tsx_booking_back(client):
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    gone = client.app.state.gone
    gone["prac-v2-1"] = {"first": 0.0, "next_check": 0.0, "booked": {"nq930": [{"account": "prac-v2-1", "qty": 1}]}}
    r = client.post("/api/accounts/reconnect", json={"account": "prac-v2-1"}).json()
    assert r["results"]["prac-v2-1"]["ok"], r
    assert "prac-v2-1" not in gone and not client.app.state.cfg.book.get("nq930")


class _Stop(Exception):
    pass


def test_a_lost_session_shows_the_account_disconnected_with_the_reason(client, api, monkeypatch):
    from homebase.broker.login_budget import LoginDeferred
    connect(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["PRAC-V2-1"]})
    ad, sess = client.app.state.adapters["prac-v2-1"], brokers._TSX_SESSIONS[KEY]
    assert ad.connected
    sess.lost = LoginDeferred("4 logins on this user in the last hour — next allowed at 11:40:00")

    async def stop(_s):
        raise _Stop
    monkeypatch.setattr(brokers, "asyncio", type("A", (), {"sleep": staticmethod(stop), "Lock": asyncio.Lock}))

    async def one_pass():
        with pytest.raises(_Stop):
            await client.app.state.broker_loop()
    client.portal.call(one_pass)
    assert not ad.connected and ad not in sess.listeners
    acct = client.get("/api/status").json()["accounts"]["prac-v2-1"]
    assert acct["connected"] is False and acct["error"].startswith("4 logins on this user")
    assert client.app.state.login_cooldown["prac-v2-1"] > 0          # paced: the next pass does not log in at once
