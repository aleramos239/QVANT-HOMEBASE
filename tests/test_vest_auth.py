from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from homebase.broker import vest_auth
from homebase.broker.login_budget import LoginBudget
from homebase.broker.vest_auth import DeviceKey, NeedsSignature, VestSession
from homebase.store import secrets_store

ADDR = "0xabc0000000000000000000000000000000000001"
KEY = "vest:" + ADDR
FAR = 4_000_000_000_000        # ms, far in the future
SECRETS = ("AT-1", "RT-1", "RTID-1", "SIG-WALLET", "AT-2", "RT-2", "RTID-2", "APIKEY-1", "ACCT-1", "ACCT-2", "BODY-SECRET")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets_store, "_store_path", lambda: tmp_path / "credentials.json")


class Vest:
    """A fake Vest gateway: records every call; `handlers` can override a path's answer."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.handlers: dict = {}
        self.n = 0                 # refreshes
        self.acct_n = 0            # account tokens minted

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        h = self.handlers.get(req.url.path)
        if h:
            r = h(req)
            if r is not None:
                return r
        p = req.url.path
        if p == "/v3/auth/challenge":
            return httpx.Response(200, json={"challengeId": "ch1", "message": {"typed": "data"}, "nonce": "n"})
        if p == "/v3/auth/register":
            return httpx.Response(200, json=self.session("1", FAR))
        if p == "/v3/auth/refresh":
            self.n += 1
            return httpx.Response(200, json=self.session("2", FAR))
        if p == "/v3/auth/account-token":
            self.acct_n += 1
            return httpx.Response(200, json={"accessToken": f"ACCT-{self.acct_n}", "accessExpiresAtMs": FAR})
        return httpx.Response(200, json={"ok": True})

    @staticmethod
    def session(n: str, access_exp: int) -> dict:
        return {"apiKey": "APIKEY-1", "accessToken": f"AT-{n}", "refreshToken": f"RT-{n}", "refreshTokenId": f"RTID-{n}",
                "accessExpiresAtMs": access_exp, "refreshExpiresAtMs": FAR + int(n), "userId": "u1", "primaryAddr": ADDR,
                "signingAddr": "0xsig", "isFunded": True, "isNewRegistration": False}

    def paths(self):
        return [c.url.path for c in self.calls]

    def body(self, path):
        return json.loads(next(c for c in self.calls if c.url.path == path).content)


def make(vest, **kw):
    return VestSession(KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(vest)), **kw)


def registered(vest, **kw):
    s = make(vest, **kw)

    async def go():
        await s.challenge(ADDR)
        await s.register(ADDR, "SIG-WALLET")
    run(go())
    return s


def expire_user_token(s):
    s._user = (s._user[0], 0)


def test_device_signature_verifies():
    k = DeviceKey.new()
    pub = serialization.load_der_public_key(b64u_dec(k.public_b64()))
    raw = b64u_dec(k.sign_refresh("rt1"))
    assert len(raw) == 64
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    pub.verify(der, b"vest-refresh-v1:rt1", ec.ECDSA(hashes.SHA256()))
    assert DeviceKey.from_pem(k.pem()).public_b64() == k.public_b64()


def test_register_body_and_store():
    v = Vest()
    s = make(v)

    async def go():
        ch = await s.challenge(ADDR.upper().replace("0X", "0x"))
        assert set(ch) == {"challengeId", "message", "signingAddr", "expiryTime"}
        assert ch["message"] == {"typed": "data"}
        return await s.register(ADDR, "SIG-WALLET")
    out = run(go())
    chal = v.body("/v3/auth/challenge")
    assert chal["primaryAddr"] == ADDR and chal["chainId"] == 8453 and chal["networkType"] == 0
    assert chal["signingAddr"].startswith("0x") and len(chal["signingAddr"]) == 42
    body = v.body("/v3/auth/register")
    assert body["rememberMe"] is True and body["devicePublicKey"] and "privyAccessToken" not in body
    assert body["signature"] == "SIG-WALLET" and body["challengeId"] == "ch1" and body["signingAddr"] == chal["signingAddr"]
    for c in v.calls:
        assert c.headers["origin"] == "https://next.vestmarkets.com"
    creds = secrets_store.get_credentials(KEY)
    assert creds["refresh_token"] == "RT-1" and creds["refresh_token_id"] == "RTID-1" and creds["device_pem"]
    assert creds["primary_addr"] == ADDR and creds["refresh_expires_ms"] == FAR + 1
    assert s.refresh_expires_ms == FAR + 1 and not s.needs_signature
    text = repr(s) + json.dumps(out)
    assert not any(x in text for x in SECRETS) and creds["device_pem"][:30] not in text


def test_register_without_challenge_refuses():
    with pytest.raises(RuntimeError):
        run(make(Vest()).register(ADDR, "SIG-WALLET"))


def test_user_token_cached_until_near_expiry():
    v = Vest()
    s = registered(v)
    assert run(s.user_token()) == "AT-1" and "/v3/auth/refresh" not in v.paths()


def test_refresh_body():
    v = Vest()
    s = registered(v)
    expire_user_token(s)
    assert run(s.user_token()) == "AT-2"
    assert v.paths().count("/v3/auth/refresh") == 1
    body = v.body("/v3/auth/refresh")
    assert body["refreshToken"] == "RT-1" and str(uuid.UUID(body["requestId"])) == body["requestId"]
    pub = serialization.load_pem_private_key(secrets_store.get_credentials(KEY)["device_pem"].encode(), None).public_key()
    raw = b64u_dec(body["deviceSignature"])
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
               b"vest-refresh-v1:RTID-1", ec.ECDSA(hashes.SHA256()))
    creds = secrets_store.get_credentials(KEY)
    assert creds["refresh_token"] == "RT-2" and creds["refresh_token_id"] == "RTID-2" and creds["refresh_expires_ms"] == FAR + 2


def test_refresh_from_stored_creds_in_a_new_process():
    v = Vest()
    registered(v)
    s2 = make(v)                                  # fresh object, same store: no token in memory
    assert run(s2.user_token()) == "AT-2"


def test_refresh_rejected_needs_signature():
    v = Vest()
    s = registered(v)
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(401, json={"error": "RT-1 bad"})
    expire_user_token(s)
    with pytest.raises(NeedsSignature) as e:
        run(s.user_token())
    assert "RT-1" not in str(e.value)
    assert s.needs_signature is True
    with pytest.raises(NeedsSignature):
        run(s.user_token())
    assert v.paths().count("/v3/auth/refresh") == 1


def test_refresh_backoff_after_server_error():
    v = Vest()
    s = registered(v, budget=LoginBudget())
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(500)
    expire_user_token(s)
    with pytest.raises(httpx.HTTPStatusError):
        run(s.user_token())
    with pytest.raises(RuntimeError, match="backing off"):      # LoginDeferred, no second call
        run(s.user_token())
    assert v.paths().count("/v3/auth/refresh") == 1


def test_refresh_token_spent_needs_signature_without_a_call(monkeypatch):
    v = Vest()
    s = registered(v)
    monkeypatch.setattr(vest_auth, "_now_ms", lambda: FAR + 5)
    assert s.needs_signature
    with pytest.raises(NeedsSignature):
        run(s.user_token())
    assert "/v3/auth/refresh" not in v.paths()


def test_account_token_cached_and_bearer():
    v = Vest()
    s = registered(v)

    async def go():
        a = await s.account_token("acc1")
        b = await s.account_token("acc1")
        r = await s.request("GET", "/v3/account", account_id="acc1")
        return a, b, r
    a, b, _ = run(go())
    assert a == b == "ACCT-1" and v.paths().count("/v3/auth/account-token") == 1
    assert v.body("/v3/auth/account-token") == {"accountId": "acc1"}
    assert v.calls[-1].headers["authorization"] == "Bearer ACCT-1"
    mint = next(c for c in v.calls if c.url.path == "/v3/auth/account-token")
    assert mint.headers["authorization"] == "Bearer AT-1"


def test_401_resend_once():
    v = Vest()
    s = registered(v)
    run(s.account_token("acc1"))
    mints0 = v.paths().count("/v3/auth/account-token")
    seen = []

    def orders(req):
        seen.append(req.headers["authorization"])
        return httpx.Response(401) if len(seen) == 1 else httpx.Response(200, json={"id": 7})
    v.handlers["/v3/orders"] = orders
    r = run(s.request("POST", "/v3/orders", account_id="acc1", json={"x": 1}))
    assert r.json() == {"id": 7}
    assert v.paths().count("/v3/auth/account-token") - mints0 == 1
    assert seen == ["Bearer ACCT-1", "Bearer ACCT-2"]
    assert [json.loads(c.content) for c in v.calls if c.url.path == "/v3/orders"] == [{"x": 1}, {"x": 1}]

    v.handlers["/v3/orders"] = lambda req: httpx.Response(401)
    before = v.paths().count("/v3/orders")
    with pytest.raises(httpx.HTTPStatusError):
        run(s.request("POST", "/v3/orders", account_id="acc1", json={"x": 1}))
    assert v.paths().count("/v3/orders") - before == 2


@pytest.mark.parametrize("fail", [httpx.ReadTimeout("slow"), httpx.Response(500)])
def test_no_resend_on_timeout_or_500(fail):
    v = Vest()
    s = registered(v)
    run(s.account_token("acc1"))

    def orders(req):
        if isinstance(fail, Exception):
            raise fail
        return fail
    v.handlers["/v3/orders"] = orders
    with pytest.raises((httpx.ReadTimeout, httpx.HTTPStatusError)):
        run(s.request("POST", "/v3/orders", account_id="acc1", json={}))
    assert v.paths().count("/v3/orders") == 1


def test_user_level_401_refreshes_and_resends():
    v = Vest()
    s = registered(v)
    seen = []

    def me(req):
        seen.append(req.headers["authorization"])
        return httpx.Response(401) if len(seen) == 1 else httpx.Response(200, json={})
    v.handlers["/v3/me"] = me
    run(s.request("GET", "/v3/me"))
    assert seen == ["Bearer AT-1", "Bearer AT-2"]


def test_refresh_403_is_not_sticky(monkeypatch):
    v = Vest()
    s = registered(v)
    clock = [1_000_000]
    monkeypatch.setattr(vest_auth, "_now_ms", lambda: clock[0])
    expire_user_token(s)
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(403, text="waf")
    with pytest.raises(httpx.HTTPStatusError):
        run(s.user_token())
    assert not s.needs_signature
    with pytest.raises(RuntimeError, match="backing off"):                 # still inside the refresh's own backoff
        run(s.user_token())
    assert v.paths().count("/v3/auth/refresh") == 1
    clock[0] += 11_000                                                     # past the first 10 s
    v.handlers.pop("/v3/auth/refresh")
    assert run(s.user_token()) == "AT-2"


def test_needs_signature_clears_when_another_process_re_registers():
    v = Vest()
    s = registered(v)
    expire_user_token(s)
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(401)
    with pytest.raises(NeedsSignature):
        run(s.user_token())
    assert s.needs_signature
    creds = secrets_store.get_credentials(KEY)
    secrets_store.set_credentials(KEY, **{**creds, "refresh_token": "RT-9", "refresh_token_id": "RTID-9"})
    assert not s.needs_signature


def test_resend_keeps_a_token_a_sibling_already_replaced():
    v = Vest()
    s = registered(v)
    run(s.account_token("acc1"))

    def orders(req):
        if req.headers["authorization"] == "Bearer ACCT-1":
            s._accounts["acc1"] = ("ACCT-SIBLING", FAR)               # a sibling re-minted while we were in flight
            return httpx.Response(401)
        return httpx.Response(200, json={})
    v.handlers["/v3/orders"] = orders
    run(s.request("POST", "/v3/orders", account_id="acc1"))
    assert v.paths().count("/v3/auth/account-token") == 1              # no second mint: the sibling's token was used
    assert v.calls[-1].headers["authorization"] == "Bearer ACCT-SIBLING"


def test_concurrent_user_token_refreshes_once():
    v = Vest()
    s = registered(v)
    expire_user_token(s)

    async def go():
        return await asyncio.gather(s.user_token(), s.user_token())
    assert run(go()) == ["AT-2", "AT-2"]
    assert v.paths().count("/v3/auth/refresh") == 1


def test_secrets_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    v = Vest()
    s = registered(v)
    expire_user_token(s)
    run(s.user_token())
    run(s.request("GET", "/v3/x", account_id="acc1"))
    pem = secrets_store.get_credentials(KEY)["device_pem"]
    sigs = [json.loads(c.content)["deviceSignature"] for c in v.calls if c.url.path == "/v3/auth/refresh"]
    errs = []
    for answer in (httpx.Response(500, text="BODY-SECRET"), httpx.Response(401, text="BODY-SECRET")):   # error paths too
        v.handlers["/v3/auth/refresh"] = lambda req, a=answer: a
        expire_user_token(s)
        s._refresh_next_ms = 0                                         # lift the backoff the 500 started
        with pytest.raises((httpx.HTTPStatusError, NeedsSignature)) as e:
            run(s.user_token())
        errs.append(str(e.value) + repr(e.value))
        sigs += [json.loads(c.content)["deviceSignature"] for c in v.calls if c.url.path == "/v3/auth/refresh"][len(sigs):]
    assert s.needs_signature and caplog.text
    for secret in SECRETS + (pem.splitlines()[1],) + tuple(sigs):
        assert secret not in caplog.text
        assert not any(secret in e for e in errs)


def _held(gate: asyncio.Event, entered: asyncio.Event, resp):
    """A gateway answer that waits for `gate` (the call is in flight until the test lets it go)."""
    async def answer():
        entered.set()
        await gate.wait()
        return resp
    return answer()


def test_a_challenge_issued_during_a_register_survives_it():
    v = Vest()
    s = make(v)

    async def go():
        gate, entered = asyncio.Event(), asyncio.Event()
        await s.challenge(ADDR)
        v.handlers["/v3/auth/register"] = lambda req: _held(gate, entered, httpx.Response(200, json=Vest.session("1", FAR)))
        reg = asyncio.ensure_future(s.register(ADDR, "SIG-WALLET"))
        await entered.wait()
        b = await s.challenge(ADDR)                       # the owner asked again while A was registering
        gate.set()
        await reg
        assert s._chal is not None and s._chal["signingAddr"] == b["signingAddr"]
        v.handlers.pop("/v3/auth/register")
        await s.register(ADDR, "SIG-WALLET")              # B is still usable
        return b
    b = run(go())
    bodies = [json.loads(c.content) for c in v.calls if c.url.path == "/v3/auth/register"]
    assert bodies[-1]["signingAddr"] == b["signingAddr"]


def test_a_refresh_in_flight_never_overwrites_a_fresh_register():
    v = Vest()
    s = registered(v)
    expire_user_token(s)

    async def go():
        gate, entered = asyncio.Event(), asyncio.Event()
        v.handlers["/v3/auth/refresh"] = lambda req: _held(gate, entered, httpx.Response(200, json=Vest.session("2", FAR)))
        v.handlers["/v3/auth/register"] = lambda req: httpx.Response(200, json=Vest.session("7", FAR))
        ref = asyncio.ensure_future(s.user_token())       # the old chain's refresh, in flight
        await entered.wait()
        await s.challenge(ADDR)
        reg = asyncio.ensure_future(s.register(ADDR, "SIG-WALLET"))
        await asyncio.sleep(0.05)                         # the register's answer is in: it waits for the refresh
        gate.set()
        await asyncio.gather(ref, reg)
    run(go())
    creds = secrets_store.get_credentials(KEY)
    assert creds["refresh_token_id"] == "RTID-7" and creds["refresh_expires_ms"] == FAR + 7
    assert s._user[0] == "AT-7"


# ---- final fix I3 (R57) --------------------------------------------------------------------------------------
def test_a_429_on_a_trading_call_books_no_cooldown_an_auth_429_does():
    v = Vest()
    b = LoginBudget()
    s = registered(v, budget=b)
    v.handlers["/v3/orders"] = lambda req: httpx.Response(429)
    with pytest.raises(httpx.HTTPStatusError):
        run(s.request("GET", "/v3/orders"))
    assert b.blocked(KEY, manual=True) is None
    expire_user_token(s)
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(429)
    with pytest.raises(httpx.HTTPStatusError):
        run(s.user_token())
    assert "429" in (b.blocked(KEY, manual=True) or "")


def test_a_failed_refresh_retries_after_about_10s_doubling_to_60s(monkeypatch):
    v = Vest()
    b = LoginBudget()
    s = registered(v, budget=b)
    clock = [1_000_000]
    monkeypatch.setattr(vest_auth, "_now_ms", lambda: clock[0])
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(500)
    waits = []
    expire_user_token(s)
    with pytest.raises(httpx.HTTPStatusError):
        run(s.user_token())
    for _ in range(5):
        t0 = clock[0]                                               # the last failure: the wait starts here
        while clock[0] - t0 < 400_000:                               # bounded: the old 300 s backoff would loop
            clock[0] += 1_000
            try:
                run(s.user_token())
            except httpx.HTTPStatusError:
                break                                               # it tried again (and failed again)
            except RuntimeError as e:
                assert "backing off" in str(e)
        waits.append((clock[0] - t0) // 1000)
    assert waits[:4] == [10, 20, 40, 60] and waits[4] == 60
    assert b.blocked(KEY) is None                                   # the wallet-login budget is untouched by refreshes


def test_tokens_renew_with_5_minutes_left(monkeypatch):
    v = Vest()
    s = registered(v)
    monkeypatch.setattr(vest_auth, "_now_ms", lambda: 1_000_000)
    s._user = ("AT-1", 1_000_000 + 299_000)
    assert run(s.user_token()) == "AT-2"
    s._accounts["a1"] = ("ACCT-old", 1_000_000 + 299_000)
    assert run(s.account_token("a1")) != "ACCT-old"


def test_urgent_skips_the_refresh_backoff_but_never_a_rejected_login(monkeypatch):
    v = Vest()
    s = registered(v)
    clock = [1_000_000]
    monkeypatch.setattr(vest_auth, "_now_ms", lambda: clock[0])
    expire_user_token(s)
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(500)
    with pytest.raises(httpx.HTTPStatusError):
        run(s.user_token())
    v.handlers.pop("/v3/auth/refresh")

    async def go():
        with vest_auth.urgent():
            return await s.user_token()
    assert run(go()) == "AT-2"                                      # a kill/flatten refreshes at once
    expire_user_token(s)
    v.handlers["/v3/auth/refresh"] = lambda req: httpx.Response(401)
    with pytest.raises(NeedsSignature):
        run(go())


def test_a_vest_login_block_never_says_tradovate():
    from homebase.broker.login_budget import LoginBudget
    b = LoginBudget(clock=lambda: 1_000_000.0, journal=lambda ev, **kw: None)
    for key in ("vest:0xabc", "tv:demo:u"):
        assert b.note_error(key, RuntimeError("429 Too Many Requests"))
    assert "Vest rate-limited" in b.blocked("vest:0xabc") and "Tradovate" not in b.blocked("vest:0xabc")
    assert "Tradovate rate-limited" in b.blocked("tv:demo:u")
