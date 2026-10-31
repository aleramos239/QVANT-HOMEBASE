"""The AlphaTrader login on the desk's routes and builder: /api/connect (new, saved, with a code), the login budget, add-many
(practice = demo, the rest live), one session per login, md_source, /api/logins, the booking refusal. No network: a real
AtrSession runs over an httpx MockTransport (the fake Alpha REST), registered in brokers._ATR_SESSIONS exactly as
build_adapter shares it; the T4 socket is a stub that answers its login with the accounts."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.broker import alphatrader
from homebase.broker import alphatrader_auth as aa
from homebase.broker.alphatrader import AlphaTraderAdapter
from homebase.broker.alphatrader_auth import AtrSession
from homebase.config import AccountCfg, AppCfg
from homebase.desk_app import brokers
from homebase.desk_app.brokers import _key_env, build_adapter, is_atr_key, md_source
from homebase.server import create_app
from homebase.store import secrets_store
from tests.test_engine import FakeAdapter
from tests.test_login_budget import S429

EMAIL = "Owner@Example.com"
KEY = "atr:owner@example.com"
PASSWORD = "pw-SECRET-123"
TOKEN = "TOK-SECRET-456"
ACCOUNTS = [{"accountId": "A1", "accountName": "AF-50K-1", "displayName": "Alpha 50K Eval"},
            {"accountId": "A2", "accountName": "AF-50K-2", "displayName": "Alpha 50K"}]
ET = ZoneInfo("America/New_York")


class Alpha:
    """The fake Alpha REST: every call recorded; the login answers `login` (a dict, or a function of the request body)."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.login = {"data": {"tokens": {"access_token": TOKEN, "refresh_token": "R-SECRET"}}}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        if req.url.path == aa.LOGIN_PATH:
            body = json.loads(req.content)
            return httpx.Response(200, json=self.login(body) if callable(self.login) else self.login)
        return httpx.Response(401, json={"detail": "no"})     # a refresh is refused: a renewal logs in

    def logins(self) -> list[dict]:
        return [json.loads(c.content) for c in self.calls if c.url.path == aa.LOGIN_PATH]


class StubSocket:
    """Stands in for AtrSocket: start() answers the T4 login with the accounts, or (refuse set) stops with those words."""
    made: list["StubSocket"] = []
    refuse: str | None = None

    def __init__(self, session, on_event, *, on_up=None, on_taken=None, url=None):
        self.session, self.on_event, self.on_up = session, on_event, on_up
        self.up = self.running = False
        self.stops = 0
        StubSocket.made.append(self)

    async def start(self):
        if self.up:
            return
        if StubSocket.refuse:
            self.session.lost = StubSocket.refuse
            return
        self.on_event("loginResponse", {"accounts": ACCOUNTS})
        self.up = self.running = True
        await self.on_up()

    async def stop(self):
        self.up = self.running = False
        self.stops += 1

    async def send(self, payload, data):
        raise ConnectionError("stub")


@pytest.fixture()
def api():
    return Alpha()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.desk.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(secrets_store, "_migrate_from_keychain", lambda key: None)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    StubSocket.made, StubSocket.refuse = [], None
    monkeypatch.setattr(alphatrader, "AtrSocket", StubSocket)
    monkeypatch.setattr(brokers, "_ATR_SESSIONS", {})

    async def pause(s):
        await asyncio.sleep(0)
    monkeypatch.setattr(alphatrader, "_pause", pause)


@pytest.fixture()
def client(tmp_path, api, monkeypatch):
    brokers._ATR_SESSIONS[KEY] = AtrSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(api)))
    # any other session would be a second one for the key and would reach the real AlphaTrader: never in a test
    monkeypatch.setattr(brokers, "AtrSession", lambda key, **kw: pytest.fail(f"a new AtrSession for {key}"))
    cfg = AppCfg(armed=False, accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")})
    app = create_app(cfg, {"main": FakeAdapter("main")}, background=False)
    app.state.engine.now_et = lambda: dt.datetime(2026, 10, 30, 11, 0, tzinfo=ET)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app = app
        yield c


def connect(client, **kw):
    return client.post("/api/connect", json={"broker": "atr", "email": EMAIL, "password": PASSWORD, **kw})


def budget_logins(client) -> int:
    return len(client.app.state.login_budget._users[KEY].logins)


def add_both(client):
    connect(client)
    return client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["Alpha 50K Eval", "Alpha 50K"]}).json()


def test_connect_with_broker_atr_saves_atr_key_and_lists_accounts(client, api, tmp_path):
    r = connect(client)
    assert r.json() == {"ok": True, "key": KEY, "env": "atr", "accounts": [
        {"id": "A1", "name": "Alpha 50K Eval", "active": True, "practice": True, "on_desk": False},
        {"id": "A2", "name": "Alpha 50K", "active": True, "practice": False, "on_desk": False}]}
    assert secrets_store.get_credentials(KEY) == {"username": EMAIL, "password": PASSWORD}
    assert api.logins() == [{"email": EMAIL, "password": PASSWORD}]
    assert budget_logins(client) == 1
    assert PASSWORD not in r.text and TOKEN not in r.text
    sess = brokers._ATR_SESSIONS[KEY]
    assert sess.adapters == [] and sess.socket is None and StubSocket.made[0].stops == 1     # the probe left no socket
    # a saved login goes through the same route: the held token, no second login
    assert client.post("/api/connect", json={"saved_key": KEY}).json()["ok"]
    assert len(api.logins()) == 1 and budget_logins(client) == 1
    assert sess.adapters == [] and sess.socket is None
    for p in tmp_path.glob("*.jsonl"):
        assert PASSWORD not in p.read_text() and TOKEN not in p.read_text()


def test_a_wrong_password_answers_the_words_not_the_password(client, api):
    api.login = lambda body: {"message": f"bad login for {body['password']}"}
    r = connect(client)
    assert r.json()["ok"] is False and "bad login" in r.json()["error"]
    assert PASSWORD not in r.text and TOKEN not in r.text


def test_connect_goes_through_the_login_budget(client, api):
    client.app.state.login_budget.note_error(KEY, S429)             # AlphaTrader said 429: the cool-down
    r = connect(client).json()
    assert r["ok"] is False and r["error"].startswith("AlphaTrader rate-limited this login") and r["key"] == KEY
    assert api.logins() == []
    r = client.post("/api/connect", json={"saved_key": KEY}).json()   # a saved login is refused the same way
    assert r["ok"] is False and "AlphaTrader rate-limited" in r["error"] and api.logins() == []


def test_needs_code_answers_needs_code_true(client, api):
    api.login = lambda body: {"detail": "mfa verification required"} if "code" not in body else \
        {"data": {"tokens": {"access_token": TOKEN}}}
    r = connect(client)
    assert r.json() == {"ok": False, "needs_code": True, "key": KEY}
    assert PASSWORD not in r.text
    r = connect(client, code="123456").json()
    assert r["ok"] and r["env"] == "atr" and len(r["accounts"]) == 2
    assert api.logins()[-1]["code"] == "123456" and len(api.logins()) == 2
    # a saved login with no token and no code is asked for a code again: needs_code, not an error
    brokers._ATR_SESSIONS[KEY]._access = None
    assert client.post("/api/connect", json={"saved_key": KEY}).json() == {"ok": False, "needs_code": True, "key": KEY}
    # the T4 socket asking for a code (not the Alpha login) answers the same
    brokers._ATR_SESSIONS[KEY]._access, brokers._ATR_SESSIONS[KEY].expires_at = TOKEN, 9e12
    StubSocket.refuse = "AlphaTrader needs a code"
    assert client.post("/api/connect", json={"saved_key": KEY}).json() == {"ok": False, "needs_code": True, "key": KEY}


def test_add_many_marks_practice_demo_and_the_rest_live(client):
    out = add_both(client)
    assert out["ok"] and out["added"] == 2, out
    accts = client.app.state.cfg.accounts
    assert (accts["alpha-50k-eval"].live, accts["alpha-50k"].live) == (False, True)
    assert (accts["alpha-50k-eval"].account_name, accts["alpha-50k"].account_name) == ("A1", "A2")   # pinned by id
    assert accts["alpha-50k-eval"].label == "Alpha 50K Eval"
    assert all(r["connected"] for r in out["results"]), out
    ads = client.app.state.adapters
    a, b = ads["alpha-50k-eval"], ads["alpha-50k"]
    assert isinstance(a, AlphaTraderAdapter) and a.session is b.session is brokers._ATR_SESSIONS[KEY]
    assert a.broker_key == ("alphatrader", "A1") and b.broker_key == ("alphatrader", "A2")
    assert a.session.budget is client.app.state.login_budget
    assert a.journal == a.session.journal == client.app.state.engine.journal
    assert budget_logins(client) == 1                  # the wizard's login; the entries rode its token
    again = client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["Alpha 50K Eval"]}).json()
    assert again["exists"] == 1
    assert connect(client).json()["accounts"][0]["on_desk"] is True
    assert client.post("/api/accounts/add", json={"key": KEY, "account_name": "A1"}).status_code == 400


def test_build_adapter_makes_an_AlphaTraderAdapter_sharing_one_session_per_login():
    a = build_adapter("a", AccountCfg(keyring_key=KEY, account_name="A1", live=False))
    b = build_adapter("b", AccountCfg(keyring_key=KEY, account_name="A2", live=True))
    probe = build_adapter("probe", AccountCfg(keyring_key=KEY))
    assert all(isinstance(x, AlphaTraderAdapter) for x in (a, b, probe))
    assert a.session is b.session is probe.session is brokers.atr_session(KEY)
    assert isinstance(a.session, AtrSession) and list(brokers._ATR_SESSIONS) == [KEY]
    assert (a.account_name, a.live, b.live, probe.account_name, a.keyring_key) == ("A1", False, True, "", KEY)
    assert build_adapter("c", AccountCfg(keyring_key="atr:other")).session is not a.session


def test_md_source_never_picks_an_atr_login():
    cfg = AppCfg(accounts={"t": AccountCfg(keyring_key=KEY, account_name="A2", live=True)})
    with pytest.raises(RuntimeError, match="no accounts configured for market data"):
        md_source(cfg, {})
    cfg.accounts["tv"] = AccountCfg(keyring_key="tv:demo:u")
    assert md_source(cfg, {})[0] == "tv:demo:u"


def test_booking_an_atr_account_is_refused_with_ATR_BOOKING_CLOSED(client):
    from homebase.config import StrategyCfg
    add_both(client)
    cfg = client.app.state.cfg
    cfg.strategies["nq930"] = StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0)
    assert alphatrader.ATR_BOOKING_OPEN is False
    r = client.post("/api/book", json={"strategy": "nq930", "assignments": [
        {"account": "main", "qty": 1}, {"account": "alpha-50k", "qty": 1}]})
    assert r.status_code == 409 and r.json()["detail"] == alphatrader.ATR_BOOKING_CLOSED
    assert "nq930" not in cfg.book                                  # nothing written, not even the other row
    assert client.post("/api/book", json={"strategy": "nq930", "assignments": [
        {"account": "main", "qty": 1}]}).json()["ok"]               # other accounts book as before


def test_a_restore_does_not_rebook_an_atr_account(client):
    add_both(client)
    gone = client.app.state.gone
    gone["alpha-50k"] = {"first": 0.0, "next_check": 0.0, "booked": {"nq930": [{"account": "alpha-50k", "qty": 1}]}}
    r = client.post("/api/accounts/reconnect", json={"account": "alpha-50k"}).json()
    assert r["results"]["alpha-50k"]["ok"], r
    assert "alpha-50k" not in gone and not client.app.state.cfg.book.get("nq930")


def test_logins_lists_atr_with_env_atr(client):
    secrets_store.set_credentials(KEY, username=EMAIL, password=PASSWORD)
    row = next(x for x in client.get("/api/logins").json()["logins"] if x["key"] == KEY)
    assert row == {"key": KEY, "label": EMAIL, "env": "atr", "in_use": False}
    assert _key_env(KEY) == "atr" and is_atr_key(KEY) and not is_atr_key("tsx:u")
    assert PASSWORD not in client.get("/api/logins").text
    assert client.post("/api/logins/delete", json={"key": KEY}).json() == {"ok": True}
    assert KEY not in brokers._ATR_SESSIONS


def test_a_reconnect_asked_for_a_code_shows_it_on_the_card(client):
    add_both(client)
    sess = brokers._ATR_SESSIONS[KEY]
    sess.socket.up = sess.socket.running = False          # the socket stopped: T4 asked for a code
    StubSocket.refuse = "AlphaTrader needs a code"
    r = client.post("/api/accounts/reconnect", json={"account": "alpha-50k"}).json()
    assert r["results"]["alpha-50k"] == {"ok": False, "error": "AlphaTrader needs a code"}
    assert client.app.state.login_cooldown["alpha-50k"] > 0
    StubSocket.refuse = None                              # the code is answered in the wizard: the cool-down is freed
    api_ok = connect(client, code="123456").json()
    assert api_ok["ok"] and "alpha-50k" not in client.app.state.login_cooldown


class _Stop(Exception):
    pass


def test_a_lost_session_shows_the_account_disconnected_with_the_reason(client, monkeypatch):
    add_both(client)
    ad, sess = client.app.state.adapters["alpha-50k"], brokers._ATR_SESSIONS[KEY]
    assert ad.connected
    sess.socket.up = False
    sess.lost = "4 logins on this user in the last hour — next allowed at 11:40:00"

    async def stop(_s):
        raise _Stop
    monkeypatch.setattr(brokers, "asyncio", type("A", (), {"sleep": staticmethod(stop), "Lock": asyncio.Lock}))

    async def one_pass():
        with pytest.raises(_Stop):
            await client.app.state.broker_loop()
    client.portal.call(one_pass)
    assert not ad.connected and ad not in sess.adapters
    acct = client.get("/api/status").json()["accounts"]["alpha-50k"]
    assert acct["connected"] is False and acct["error"].startswith("4 logins on this user")
    assert client.app.state.login_cooldown["alpha-50k"] > 0


def test_a_kicked_session_logging_in_again_is_not_shown_lost(client, monkeypatch):
    add_both(client)
    ad, sess = client.app.state.adapters["alpha-50k"], brokers._ATR_SESSIONS[KEY]
    sess.socket.up = False
    sess.lost = "T4 session taken (logged in elsewhere): logging in again"

    async def stop(_s):
        raise _Stop
    monkeypatch.setattr(brokers, "asyncio", type("A", (), {"sleep": staticmethod(stop), "Lock": asyncio.Lock}))

    async def one_pass():
        with pytest.raises(_Stop):
            await client.app.state.broker_loop()
    client.portal.call(one_pass)
    assert ad.connected and ad in sess.adapters
