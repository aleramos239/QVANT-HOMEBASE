from __future__ import annotations

import asyncio
import base64
import json
import time

import httpx
import pytest

from homebase.broker import topstepx_auth
from homebase.broker.login_budget import LoginBudget, LoginDeferred
from homebase.broker.topstepx_auth import NeedsCode, TsxLoginFailed, TsxSession
from homebase.store import secrets_store

KEY = "topstepx:Owner"
PW = "pw-SECRET-1"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def jwt(exp: float) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")
    secrets_store.set_credentials(KEY, username="Owner", password=PW)


class Tsx:
    """A fake TopstepX userapi: records every call; `handlers` can override a path's answer."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.handlers: dict = {}
        self.logins = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        h = self.handlers.get(req.url.path)
        if h:
            r = h(req)
            if r is not None:
                return r
        if req.url.path == "/Login":
            self.logins += 1
            return httpx.Response(200, json={"success": True, "token": f"TOK-{self.logins}", "userId": 77})
        return httpx.Response(200, json={"ok": True})

    def paths(self):
        return [c.url.path for c in self.calls]


def make(tsx, **kw):
    return TsxSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(tsx)), **kw)


def test_login_posts_username_and_password_and_keeps_the_token_in_memory():
    t = Tsx()
    s = make(t)
    run(s.login())
    assert json.loads(t.calls[0].content) == {"userName": "Owner", "password": PW}
    assert t.calls[0].headers["origin"] == "https://topstepx.com"
    assert run(s.token()) == "TOK-1" and s.user_id == 77
    assert "TOK-1" not in json.dumps(secrets_store.get_credentials(KEY))
    assert set(secrets_store.get_credentials(KEY)) == {"username", "password"}


def test_a_code_is_sent_in_the_body_when_given():
    t = Tsx()
    run(make(t).login(code="123456"))
    assert json.loads(t.calls[0].content)["code"] == "123456"


def test_a_wrong_password_raises_TsxLoginFailed_with_topstepx_words_not_the_password():
    t = Tsx()
    t.handlers["/Login"] = lambda req: httpx.Response(
        200, json={"success": False, "token": None, "errorMessage": f"Invalid username or password {PW}"})
    with pytest.raises(TsxLoginFailed) as e:
        run(make(t).login())
    assert "Invalid username or password" in str(e.value) and PW not in str(e.value)


def test_a_code_request_raises_NeedsCode():
    t = Tsx()
    t.handlers["/Login"] = lambda req: httpx.Response(200, json={"success": False, "token": None, "twoFactorRequired": True})
    with pytest.raises(NeedsCode):
        run(make(t).login())
    t.handlers["/Login"] = lambda req: httpx.Response(200, json={"token": None, "errorMessage": "Enter the verification code"})
    with pytest.raises(NeedsCode):
        run(make(t).login())


@pytest.mark.parametrize("answer", [
    {"token": None, "success": False, "errorCode": 3, "errorMessage": "Invalid username or password"},
    {"token": None, "success": False, "statusCode": 401, "errorMessage": "error code 5"}])
def test_a_wrong_password_with_an_error_code_is_not_a_code_request(answer):
    t = Tsx()
    t.handlers["/Login"] = lambda req: httpx.Response(200, json=answer)
    with pytest.raises(TsxLoginFailed):
        run(make(t).login())


def test_a_token_in_the_answer_is_never_a_code_request():
    t = Tsx()
    t.handlers["/Login"] = lambda req: httpx.Response(200, json={"token": "TOK-X", "twoFactorCode": "yes"})
    run(make(t).login())


def test_request_sends_the_bearer_and_a_401_relogs_in_once_then_retries():
    t = Tsx()
    s = make(t)
    seen = []

    def acct(req):
        seen.append(req.headers["authorization"])
        return httpx.Response(401) if len(seen) == 1 else httpx.Response(200, json={"accounts": []})
    t.handlers["/TradingAccount"] = acct
    r = run(s.request("GET", "/TradingAccount"))
    assert r.status_code == 200 and seen == ["Bearer TOK-1", "Bearer TOK-2"] and t.paths().count("/Login") == 2

    t.handlers["/TradingAccount"] = lambda req: httpx.Response(401)
    before = t.paths().count("/TradingAccount")
    assert run(s.request("GET", "/TradingAccount")).status_code == 401      # returned, not looped
    assert t.paths().count("/TradingAccount") - before == 2 and t.paths().count("/Login") == 3


def test_relogin_refused_by_the_budget_sends_no_login():
    t = Tsx()
    b = LoginBudget()
    s = make(t, budget=b)
    run(s.login())
    for _ in range(4):
        b.record_login(KEY)                                    # the hourly cap, spent
    with pytest.raises(LoginDeferred):
        run(s.relogin("401"))
    assert t.logins == 1


def test_relogin_books_the_attempt_and_the_result_with_the_budget():
    t = Tsx()
    b = LoginBudget()
    s = make(t, budget=b)
    run(s.relogin("test"))
    assert len(b._u(KEY).logins) == 1 and b._u(KEY).streak == 0
    t.handlers["/Login"] = lambda req: httpx.Response(429)
    with pytest.raises(httpx.HTTPStatusError):
        run(s.relogin("test"))
    assert b.cooling(KEY) > 0


def test_token_renews_when_under_ten_minutes_left(monkeypatch):
    t = Tsx()
    s = make(t)
    now = time.time()
    t.handlers["/Login"] = lambda req: httpx.Response(200, json={"token": jwt(now + 300)})
    run(s.login())
    assert abs(s.expires_at - (now + 300)) < 1                 # the JWT exp is used
    t.handlers["/Login"] = lambda req: httpx.Response(200, json={"token": jwt(now + 7200)})
    assert run(s.token()).split(".")[1] != jwt(now + 300).split(".")[1]
    assert t.paths().count("/Login") == 2
    run(s.token())
    assert t.paths().count("/Login") == 2                      # plenty left: cached


def test_a_token_that_is_not_a_jwt_lasts_23_hours():
    t = Tsx()
    s = make(t)
    run(s.login())
    assert abs(s.expires_at - (time.time() + 23 * 3600)) < 5


def test_concurrent_token_renewals_log_in_once():
    t = Tsx()
    s = make(t)

    async def go():
        return await asyncio.gather(s.token(), s.token())
    assert run(go()) == ["TOK-1", "TOK-1"] and t.logins == 1


def test_nothing_secret_in_repr_or_errors():
    t = Tsx()
    s = make(t)
    run(s.login())
    texts = [repr(s)]
    for answer in (httpx.Response(200, json={"token": None, "errorMessage": f"bad {PW}"}),
                   httpx.Response(200, json={"token": None, "twoFactorRequired": True}),
                   httpx.Response(500, text=f"boom {PW}"), httpx.Response(200, text=PW)):
        t.handlers["/Login"] = lambda req, a=answer: a
        with pytest.raises(Exception) as e:
            run(s.login())
        texts.append(str(e.value) + repr(e.value))
    for text in texts:
        assert PW not in text and "TOK-1" not in text
