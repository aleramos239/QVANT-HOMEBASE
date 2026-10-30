"""The Vest login on the desk's routes: the wallet challenge, the signed /api/connect, saved logins, add-many.
No network and no wallet: a real VestSession runs over an httpx MockTransport (the fake gateway), shared through
brokers._VEST_SESSIONS exactly as build_adapter shares it."""
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
from homebase.broker import vest
from homebase.broker.vest import VestAdapter
from homebase.broker.vest_auth import DeviceKey, VestSession
from homebase.config import AccountCfg, AppCfg
from homebase.desk_app import brokers
from homebase.routes import accounts as accounts_routes
from homebase.server import create_app
from homebase.store import secrets_store
from tests.test_engine import FakeAdapter

ADDR = "0xBbe10000000000000000000000000000000A1eab"
KEY = "vest:" + ADDR.lower()
SIG = "0x" + "5e" * 200                      # the wallet's signature: must never leave the session
FAR = 4_000_000_000_000
ET = ZoneInfo("America/New_York")
TYPED = {"domain": {"name": "Vest", "chainId": 8453}, "primaryType": "SignerProof", "message": {"x": 1}}


class Gateway:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.register_status = 200
        self.hold_register: tuple | None = None    # (entered, gate) threading events: the register waits for gate
        self.cancel_register = False               # the register is cancelled mid-flight
        self.challenge_status = 200

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        p = req.url.path
        if p == "/v3/auth/challenge" and self.challenge_status != 200:
            return httpx.Response(self.challenge_status)
        if p == "/v3/auth/register" and self.cancel_register:
            async def cancelled():
                raise asyncio.CancelledError()
            return cancelled()
        if p == "/v3/auth/challenge":
            return httpx.Response(200, json={"challengeId": "ch1", "message": TYPED})
        if p == "/v3/auth/register" and self.hold_register:
            entered, gate = self.hold_register

            async def later():
                entered.set()
                while not gate.is_set():
                    await asyncio.sleep(0.01)
                return httpx.Response(200, json=session_json("1"))
            return later()
        if p == "/v3/auth/register":
            if self.register_status != 200:     # a gateway that echoes what it got must not leak it
                return httpx.Response(self.register_status, json={"msg": "bad signature " + json.loads(req.content)["signature"]})
            return httpx.Response(200, json=session_json("1"))
        if p == "/v3/auth/refresh":
            return httpx.Response(200, json=session_json("2"))
        if p == "/v3/auth/account-token":
            return httpx.Response(200, json={"accessToken": "ACCT", "accessExpiresAtMs": FAR})
        if p == "/v3/accounts":
            return httpx.Response(200, json=[{"account_id": "prim-1", "account_type": 1, "active": True}])
        if p == "/v3/capital/accounts":
            return httpx.Response(200, json={"accounts": [{"accountId": "demo-111", "type": "demo"},
                                                          {"accountId": "fund-222", "status": "funded"}]})
        return httpx.Response(200, json={})

    def paths(self):
        return [c.url.path for c in self.calls]


def session_json(n):
    return {"apiKey": "APIKEY", "accessToken": f"AT-{n}", "refreshToken": f"RT-{n}", "refreshTokenId": f"RTID-{n}",
            "accessExpiresAtMs": FAR, "refreshExpiresAtMs": FAR, "userId": "u1"}


@pytest.fixture()
def gw():
    return Gateway()


@pytest.fixture()
def client(tmp_path, monkeypatch, gw):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.desk.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    monkeypatch.setattr(secrets_store, "_migrate_from_keychain", lambda key: None)
    monkeypatch.setattr(vest, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(brokers, "_VEST_SESSIONS", {})
    monkeypatch.setattr(VestAdapter, "observe_fills", lambda self, cb: asyncio.sleep(0))    # no socket, no poll
    # the login's one session, on the fake gateway: the routes and build_adapter must both find THIS one
    brokers._VEST_SESSIONS[KEY] = VestSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(gw)))
    # any other session would be a second one for the key (R47) and would reach the real Vest: never in a test
    monkeypatch.setattr(brokers, "VestSession", lambda key, **kw: pytest.fail(f"a new VestSession for {key}"))
    cfg = AppCfg(armed=False, accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")})
    app = create_app(cfg, {"main": FakeAdapter("main")}, background=False)
    app.state.engine.now_et = lambda: dt.datetime(2026, 10, 29, 11, 0, tzinfo=ET)
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app = app
        yield c


def signed_in(client):
    r = client.post("/api/vest/challenge", json={"address": ADDR}).json()
    assert r == {"ok": True, "typed_data": TYPED}
    r = client.post("/api/connect", json={"broker": "vest", "address": ADDR, "signature": SIG}).json()
    assert r["ok"], r
    return r


def saved_login(**kw):
    secrets_store.set_credentials(KEY, **{"primary_addr": ADDR.lower(), "refresh_token": "RT-0", "refresh_token_id": "RTID-0",
                                          "refresh_expires_ms": FAR, "device_pem": DeviceKey.new().pem(), **kw})


def test_challenge_then_connect_lists_accounts(client, gw):
    r = signed_in(client)
    assert r["key"] == KEY and r["env"] == "vest"
    assert [(a["kind"], a["id"], a["demo"], a["on_desk"]) for a in r["accounts"]] == [
        ("primary", "prim-1", False, False), ("demo", "demo-111", True, False), ("funded", "fund-222", False, False)]
    assert secrets_store.get_credentials(KEY)["refresh_token"] == "RT-1"
    reg = json.loads(next(c for c in gw.calls if c.url.path == "/v3/auth/register").content)
    assert reg["signature"] == SIG and reg["primaryAddr"] == ADDR.lower()
    assert len(client.app.state.login_budget._users[KEY].logins) == 1        # one wallet login, booked once


def test_connect_saved_vest_key(client, gw):
    saved_login()
    r = client.post("/api/connect", json={"saved_key": KEY}).json()
    assert r["ok"] and r["env"] == "vest" and len(r["accounts"]) == 3
    assert "/v3/auth/register" not in gw.paths() and "/v3/auth/refresh" in gw.paths()


def test_connect_saved_needs_signature(client, gw):
    saved_login(refresh_expires_ms=0)                     # the 30-day login ran out
    r = client.post("/api/connect", json={"saved_key": KEY}).json()
    assert r == {"ok": False, "error": "needs a new wallet signature", "key": KEY}
    assert gw.calls == []


def test_add_many_vest_live_flag(client):
    r = signed_in(client)
    names = {a["kind"]: a["name"] for a in r["accounts"]}
    out = client.post("/api/accounts/add-many", json={"key": KEY, "accounts": [names["demo"], names["funded"]]}).json()
    assert out["ok"] and out["added"] == 2, out          # a Vest entry's connect never stops the batch
    accts = client.app.state.cfg.accounts
    demo, funded = (accts[row["id"]] for row in out["results"])
    assert (demo.vest_account_id, demo.live, demo.floors) == ("demo-111", False, {})     # no floors: entries refused
    assert (funded.vest_account_id, funded.live, funded.floors) == ("fund-222", True, {})
    assert {demo.keyring_key, funded.keyring_key} == {KEY}
    assert all(row["connected"] for row in out["results"]), out
    assert isinstance(client.app.state.adapters[out["results"][0]["id"]], VestAdapter)
    assert client.app.state.adapters[out["results"][0]["id"]].session is brokers._VEST_SESSIONS[KEY]   # R47
    assert len(client.app.state.login_budget._users[KEY].logins) == 1     # entries spend no login: the owner can re-sign
    # the same Vest account again is a duplicate: keyed on vest_account_id
    again = client.post("/api/accounts/add-many", json={"key": KEY, "accounts": [names["demo"]]}).json()
    assert again["results"][0]["status"] == "exists" and again["exists"] == 1
    assert [a["on_desk"] for a in client.post("/api/connect", json={"saved_key": KEY}).json()["accounts"]] == [
        False, True, True]


def test_single_add_refuses_vest(client):
    saved_login()
    r = client.post("/api/accounts/add", json={"key": KEY, "account_name": "Vest primary"})
    assert r.status_code == 400 and "wizard" in r.json()["detail"]


@pytest.mark.parametrize("addr", ["0x123", "bbe10000000000000000000000000000000a1eab", "0x" + "g" * 40, "", None, 7])
def test_challenge_rejects_bad_address(client, gw, addr):
    assert client.post("/api/vest/challenge", json={"address": addr}).status_code == 400
    assert gw.calls == []


def test_connect_needs_a_pending_challenge(client, gw, monkeypatch):
    r = client.post("/api/connect", json={"broker": "vest", "address": ADDR, "signature": SIG})
    assert r.status_code == 400 and SIG not in r.text
    clock = [1000.0]
    monkeypatch.setattr(accounts_routes, "_mono", lambda: clock[0])
    client.post("/api/vest/challenge", json={"address": ADDR})
    clock[0] += 301                                       # 5 minutes and a bit: gone
    assert client.post("/api/connect", json={"broker": "vest", "address": ADDR, "signature": SIG}).status_code == 400
    assert "/v3/auth/register" not in gw.paths()


def test_pending_challenges_are_capped(client, gw, monkeypatch):
    monkeypatch.setattr(accounts_routes, "VEST_PENDING_MAX", 1)
    other = "0x" + "1" * 40
    brokers._VEST_SESSIONS["vest:" + other] = VestSession("vest:" + other, http=httpx.AsyncClient(
        transport=httpx.MockTransport(gw)))
    client.post("/api/vest/challenge", json={"address": ADDR})
    client.post("/api/vest/challenge", json={"address": other})          # drops the oldest (ADDR)
    assert client.post("/api/connect", json={"broker": "vest", "address": ADDR, "signature": SIG}).status_code == 400
    assert KEY not in brokers._VEST_SESSIONS and "vest:" + other in brokers._VEST_SESSIONS   # never signed: dropped


def test_no_signature_in_journal(client, gw, tmp_path):
    r = signed_in(client)
    client.post("/api/accounts/add-many", json={"key": KEY, "accounts": [a["name"] for a in r["accounts"]]})
    gw.register_status = 400                              # a refused signature: its error carries no signature either
    client.post("/api/vest/challenge", json={"address": ADDR})
    bad = client.post("/api/connect", json={"broker": "vest", "address": ADDR, "signature": SIG})
    assert bad.json()["ok"] is False and SIG not in bad.text and SIG[2:40] not in bad.text
    text = (tmp_path / "journal.jsonl").read_text()
    assert "account_added" in text
    for secret in (SIG, SIG[2:40], "RT-1", "RTID-1", "AT-1", "ACCT", "APIKEY", "PRIVATE KEY"):
        assert secret not in text


def test_cross_site_challenge_refused(client, gw):
    r = client.post("/api/vest/challenge", json={"address": ADDR}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and gw.calls == []


def test_logins_row_for_vest(client):
    saved_login()
    row = next(x for x in client.get("/api/logins").json()["logins"] if x["key"] == KEY)
    assert row["label"] == "0xBBE1…1EAB" and row["env"] == "vest" and row["in_use"] is False


def test_a_double_connect_does_not_kill_the_login_in_flight(client, gw):
    entered, gate = threading.Event(), threading.Event()
    gw.hold_register = (entered, gate)
    assert client.post("/api/vest/challenge", json={"address": ADDR}).json()["ok"]
    body = {"broker": "vest", "address": ADDR, "signature": SIG}
    with ThreadPoolExecutor(1) as ex:
        first = ex.submit(client.post, "/api/connect", json=body)
        assert entered.wait(5)
        second = client.post("/api/connect", json=body)           # the double-click: its challenge is taken
        assert second.status_code == 400 and SIG not in second.text
        gate.set()
        r = first.result(10).json()
    assert r["ok"] and len(r["accounts"]) == 3, r
    assert secrets_store.get_credentials(KEY)["refresh_token"] == "RT-1"


def test_a_row_without_a_demo_flag_is_added_live(client, monkeypatch):
    async def rows(self):
        return [{"name": "Vest odd 1", "id": "odd-1", "kind": "funded"},                  # no demo flag
                {"name": "Vest demo 2", "id": "demo-2", "kind": "demo", "demo": True}]
    monkeypatch.setattr(VestAdapter, "list_accounts", rows)
    signed_in(client)
    out = client.post("/api/accounts/add-many", json={"key": KEY, "accounts": ["Vest odd 1", "Vest demo 2"]}).json()
    assert out["added"] == 2, out
    accts = client.app.state.cfg.accounts
    assert accts["vest-odd-1"].live is True and accts["vest-demo-2"].live is False


def test_a_cancelled_register_leaves_no_login_in_progress_mark(client, gw):
    """A register cancelled mid-flight (the request dropped) must not keep its session pinned for ever: a later failed
    challenge for that wallet, which never signed, forgets the session."""
    assert client.post("/api/vest/challenge", json={"address": ADDR}).json()["ok"]
    gw.cancel_register = True
    with pytest.raises(BaseException):                    # the cancel comes out of the request
        client.post("/api/connect", json={"broker": "vest", "address": ADDR, "signature": SIG})
    gw.challenge_status = 500
    assert client.post("/api/vest/challenge", json={"address": ADDR}).json()["ok"] is False
    assert KEY not in brokers._VEST_SESSIONS
