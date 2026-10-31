from __future__ import annotations

import asyncio
import base64
import json
import time

import httpx
import pytest

from homebase.broker import alphatrader_auth as aa
from homebase.broker.alphatrader_auth import AtrLoginFailed, AtrSession, NeedsCode, T4Creds
from homebase.broker.login_budget import LoginBudget, LoginDeferred
from homebase.store import secrets_store

KEY = "atr:o@x.com"
PW = "pw-SECRET-1"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def jwt(payload: dict) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    secrets_store.set_credentials(KEY, username="o@x.com", password=PW)


class Alpha:
    """A fake Alpha REST: records every call; `handlers` can override a path's answer."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.handlers: dict = {}
        self.logins = 0
        self.refreshes = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        h = self.handlers.get(req.url.path)
        if h:
            r = h(req)
            if r is not None:
                return r
        if req.url.path == aa.LOGIN_PATH:
            self.logins += 1
            return httpx.Response(200, json={"data": {"tokens": self.tokens(f"LOGIN{self.logins}")}})
        if req.url.path == aa.REFRESH_PATH:
            self.refreshes += 1
            return httpx.Response(200, json={"data": {"tokens": self.tokens(f"REFRESH{self.refreshes}")}})
        return httpx.Response(200, json={"ok": True})

    @staticmethod
    def tokens(tag: str, ttl: float = 3600) -> dict:
        return {"access_token": jwt({"exp": time.time() + ttl, "tag": tag}), "refresh_token": f"REF-{tag}",
                "id_token": f"ID-{tag}"}

    def paths(self):
        return [c.url.path for c in self.calls]


def make(alpha, **kw):
    return AtrSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(alpha)), **kw)


def tag_of(token: str) -> str:
    return aa._payload(token)["tag"]


def test_login_posts_email_and_password_and_keeps_tokens_in_memory():
    a = Alpha()
    s = make(a)
    run(s.login())
    assert json.loads(a.calls[0].content) == {"email": "o@x.com", "password": PW}
    assert a.calls[0].headers["origin"] == "https://futures.alphatrader.com"
    assert tag_of(run(s.access())) == "LOGIN1"
    assert set(secrets_store.get_credentials(KEY)) == {"username", "password"}
    assert "LOGIN1" not in json.dumps(secrets_store.get_credentials(KEY))


def test_a_code_is_sent_in_the_body_when_given():
    a = Alpha()
    run(make(a).login(code="123456"))
    assert json.loads(a.calls[0].content)[aa.CODE_FIELD] == "123456"


def test_wrong_password_raises_AtrLoginFailed_without_the_password():
    a = Alpha()
    a.handlers[aa.LOGIN_PATH] = lambda req: httpx.Response(400, json={"message": f"Invalid email or password {PW}"})
    with pytest.raises(AtrLoginFailed) as e:
        run(make(a).login())
    assert "Invalid email or password" in str(e.value) and PW not in str(e.value)


@pytest.mark.parametrize("answer", [{"mfa_required": True}, {"data": {"next_step": "verify_email_code"}}])
def test_a_code_step_raises_NeedsCode(answer):
    a = Alpha()
    a.handlers[aa.LOGIN_PATH] = lambda req: httpx.Response(200, json=answer)
    with pytest.raises(NeedsCode):
        run(make(a).login())


def test_a_login_with_tokens_is_never_a_code_step():
    a = Alpha()
    a.handlers[aa.LOGIN_PATH] = lambda req: httpx.Response(
        200, json={"mfa_enabled": True, "data": {"tokens": a.tokens("X")}})
    run(make(a).login())


def test_access_renews_by_refresh_without_a_budget_slot():
    a = Alpha()
    b = LoginBudget()
    s = make(a, budget=b)
    run(s.login())
    booked = len(b._u(KEY).logins)
    s.expires_at = time.time() + 100                       # under RENEW_LEFT_S
    assert tag_of(run(s.access())) == "REFRESH1"
    assert json.loads(a.calls[-1].content) == {aa.REFRESH_FIELD: "REF-LOGIN1"}
    assert a.logins == 1 and a.refreshes == 1 and len(b._u(KEY).logins) == booked
    run(s.access())
    assert a.refreshes == 1                                # plenty left: cached


def test_expired_refresh_falls_back_to_one_password_login_through_the_budget():
    a = Alpha()
    b = LoginBudget()
    s = make(a, budget=b)
    run(s.login())
    a.handlers[aa.REFRESH_PATH] = lambda req: httpx.Response(401, json={"message": "token expired"})
    s.expires_at = 0
    assert tag_of(run(s.access())) == "LOGIN2"
    assert a.logins == 2 and a.paths().count(aa.REFRESH_PATH) == 1 and len(b._u(KEY).logins) == 2 and s.lost is None

    s.expires_at = 0                                       # and with the budget spent: no login at all
    for _ in range(4):
        b.record_login(KEY)
    with pytest.raises(LoginDeferred):
        run(s.access())
    assert a.logins == 2 and s.lost


def test_expired_refresh_and_a_code_request_stops_with_needs_a_code():
    a = Alpha()
    s = make(a)
    run(s.login())
    a.handlers[aa.REFRESH_PATH] = lambda req: httpx.Response(401)
    a.handlers[aa.LOGIN_PATH] = lambda req: httpx.Response(200, json={"mfa_required": True})
    s.expires_at = 0
    with pytest.raises(NeedsCode, match="needs a code"):
        run(s.access())
    assert s.lost == "AlphaTrader needs a code" and a.paths().count(aa.LOGIN_PATH) == 2


def test_request_sends_the_bearer_and_a_401_renews_once_then_retries():
    a = Alpha()
    s = make(a)
    seen = []

    def me(req):
        seen.append(tag_of(req.headers["authorization"].split()[1]))
        return httpx.Response(401) if len(seen) == 1 else httpx.Response(200, json={"id": 1})
    a.handlers[aa.ME_PATH] = me
    assert run(s.request("GET", aa.ME_PATH)).status_code == 200
    assert seen == ["LOGIN1", "REFRESH1"] and a.logins == 1

    a.handlers[aa.ME_PATH] = lambda req: httpx.Response(401)
    before = a.paths().count(aa.ME_PATH)
    assert run(s.request("GET", aa.ME_PATH)).status_code == 401           # returned, not looped
    assert a.paths().count(aa.ME_PATH) - before == 2


def test_the_caller_may_hold_the_lock_around_access_and_request():
    a = Alpha()
    s = make(a)
    run(s.login())
    s.expires_at = 0

    async def go():
        async with s.lock:
            await asyncio.wait_for(s.access(), 2)
            s.expires_at = 0
            await asyncio.wait_for(s.request("GET", aa.ME_PATH), 2)
    run(go())
    assert a.refreshes == 2


def test_concurrent_renewals_refresh_once():
    a = Alpha()
    s = make(a)
    run(s.login())
    s.expires_at = 0

    async def go():
        return await asyncio.gather(s.access(), s.access())
    t1, t2 = run(go())
    assert t1 == t2 and a.refreshes == 1


def test_t4_creds_decodes_the_jwt_payload_and_repr_hides_the_password():
    a = Alpha()
    signed = jwt({"t4_firm": "alpha", "t4_username": "u1", "t4_password": "t4pw", "t4_app_name": "AlphaApp",
                  "t4_app_license": "LIC"})
    a.handlers[aa.CRED_PATH] = lambda req: httpx.Response(200, json={"data": {"signed_credential_token": signed}})
    creds = run(make(a).t4_creds())
    assert creds == T4Creds("alpha", "u1", "t4pw", "AlphaApp", "LIC")
    assert a.calls[-1].method == "POST" and a.calls[-1].headers["authorization"].startswith("Bearer ")
    assert "t4pw" not in repr(creds) and "LIC" not in repr(creds) and "alpha" in repr(creds)


def test_t4_creds_refused_or_unreadable_raises_AtrLoginFailed_without_the_token():
    a = Alpha()
    s = make(a)
    for answer in (httpx.Response(403, json={"message": "no"}), httpx.Response(200, json={"data": {}}),
                   httpx.Response(200, json={"data": {"signed_credential_token": "not-a-jwt"}})):
        a.handlers[aa.CRED_PATH] = lambda req, r=answer: r
        with pytest.raises(AtrLoginFailed) as e:
            run(s.t4_creds())
        assert "not-a-jwt" not in str(e.value)


def test_t4_login_slot_books_the_budget():
    a = Alpha()
    b = LoginBudget()
    s = make(a, budget=b)
    run(s.t4_login_slot())
    assert len(b._u(KEY).logins) == 1 and not a.calls
    for _ in range(3):
        b.record_login(KEY)
    with pytest.raises(LoginDeferred):
        run(s.t4_login_slot())
    assert len(b._u(KEY).logins) == 4


def test_nothing_secret_in_repr_or_errors():
    a = Alpha()
    s = make(a)
    run(s.login())
    access = run(s.access())
    texts = [repr(s)]
    for answer in (httpx.Response(400, json={"message": f"bad {PW}"}), httpx.Response(200, json={"mfa_required": True}),
                   httpx.Response(500, text=f"boom {PW}"), httpx.Response(200, text=PW)):
        a.handlers[aa.LOGIN_PATH] = lambda req, r=answer: r
        with pytest.raises(Exception) as e:
            run(s.login())
        texts.append(str(e.value) + repr(e.value))
    a.handlers[aa.CRED_PATH] = lambda req: httpx.Response(200, json={"data": {"signed_credential_token": "SIGNED.x.y"}})
    with pytest.raises(AtrLoginFailed) as e:
        run(s.t4_creds())
    texts.append(str(e.value))
    for text in texts:
        for secret in (PW, access, "REF-LOGIN1", "ID-LOGIN1", "SIGNED"):
            assert secret not in text
