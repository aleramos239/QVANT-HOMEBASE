"""Vest Markets session: wallet-signed login, our own device key, refresh, per-account tokens.

The wallet signs ONCE (the browser does it; `challenge` hands the typed data out, `register` takes the signature back). From then on
the session renews itself with a refresh token plus a signature of OUR device key (no wallet, no Privy). The refresh token's own
expiry (~30 days) does not move on refresh: when it is spent, `NeedsSignature` says the owner must sign again.

Secrets (access / refresh tokens, signatures, the device PEM) are never logged, never in `repr`, never in an exception's text.
Stored through `secrets_store` under `self.key` (e.g. "vest:0xabc...").
"""
from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import time
import uuid

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from ..store import secrets_store
from .login_budget import LoginBudget, LoginDeferred

log = logging.getLogger(__name__)

BASE = "https://api-gateway.hz.vestmarkets.com"
HEADERS = {"Origin": "https://next.vestmarkets.com", "Referer": "https://next.vestmarkets.com/"}
CHAIN_ID = 8453
CHALLENGE_TTL_MS = 86_400_000
RENEW_LEFT_MS = 60_000          # a token with less than this left is renewed before use


def _now_ms() -> int:
    return int(time.time() * 1000)


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class NeedsSignature(RuntimeError):
    """No valid refresh token is left: the owner must sign with the wallet again."""


class DeviceKey:
    """ECDSA P-256 key of this machine; Vest ties the refresh token to its public half."""

    def __init__(self, key: ec.EllipticCurvePrivateKey):
        self._key = key

    @classmethod
    def new(cls) -> "DeviceKey":
        return cls(ec.generate_private_key(ec.SECP256R1()))

    @classmethod
    def from_pem(cls, pem: str) -> "DeviceKey":
        return cls(serialization.load_pem_private_key(pem.encode(), password=None))

    def pem(self) -> str:
        return self._key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()).decode()

    def public_b64(self) -> str:
        return _b64u(self._key.public_key().public_bytes(serialization.Encoding.DER,
                                                         serialization.PublicFormat.SubjectPublicKeyInfo))

    def sign_refresh(self, refresh_token_id: str) -> str:
        r, s = decode_dss_signature(self._key.sign(b"vest-refresh-v1:" + refresh_token_id.encode(),
                                                   ec.ECDSA(hashes.SHA256())))
        return _b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


class VestSession:
    def __init__(self, key: str, *, http: httpx.AsyncClient | None = None, budget: LoginBudget | None = None):
        self.key = key
        self._http = http
        self._own_http = http is None
        self.budget = budget or LoginBudget()
        self._chal: dict | None = None
        self._device: DeviceKey | None = None
        self._user: tuple[str, int] | None = None            # (access token, expiry ms)
        self._accounts: dict[str, tuple[str, int]] = {}
        self._needs_sig = False
        self._user_lock = asyncio.Lock()                      # refresh tokens rotate: one refresh at a time
        self._acct_lock = asyncio.Lock()

    def __repr__(self) -> str:
        return (f"VestSession(key={self.key!r}, refresh_expires_ms={self.refresh_expires_ms}, "
                f"access_expires_ms={self._user[1] if self._user else 0})")

    # -- state -------------------------------------------------------------------------------------------------
    def _creds(self) -> dict:
        return secrets_store.get_credentials(self.key) or {}

    @property
    def refresh_expires_ms(self) -> int:
        return int(self._creds().get("refresh_expires_ms") or 0)

    @property
    def needs_signature(self) -> bool:
        c = self._creds()
        return bool(self._needs_sig or not c.get("refresh_token") or _now_ms() >= self.refresh_expires_ms)

    async def aclose(self) -> None:
        if self._own_http and self._http is not None:
            await self._http.aclose()

    # -- http --------------------------------------------------------------------------------------------------
    async def _send(self, method: str, path: str, **kw) -> httpx.Response:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=15.0)
        kw["headers"] = {**HEADERS, **kw.get("headers", {})}
        resp = await self._http.request(method, BASE + path, **kw)
        if resp.status_code == 429:
            self.budget.note_error(self.key, "status=429")
        return resp

    async def _auth_call(self, path: str, body: dict, *, ok_codes=(200,)) -> httpx.Response:
        """A login-class call (challenge excluded): the budget's result is booked here; the error carries no body text."""
        try:
            resp = await self._send("POST", path, json=body)
        except httpx.HTTPError as e:
            self.budget.login_result(self.key, type(e).__name__)
            raise
        if resp.status_code not in ok_codes:
            self.budget.login_result(self.key, f"status={resp.status_code}")
        else:
            self.budget.login_result(self.key)
        return resp

    # -- wallet login ------------------------------------------------------------------------------------------
    async def challenge(self, primary_addr: str) -> dict:
        signing = "0x" + secrets.token_hex(20)               # a fresh throwaway address per challenge
        expiry = _now_ms() + CHALLENGE_TTL_MS
        primary = primary_addr.lower()
        resp = await self._send("POST", "/v3/auth/challenge", json={
            "networkType": 0, "signingAddr": signing, "primaryAddr": primary, "chainId": CHAIN_ID, "expiryTime": expiry})
        resp.raise_for_status()
        j = resp.json()
        self._chal = {"challengeId": j["challengeId"], "message": j["message"], "signingAddr": signing,
                      "expiryTime": expiry, "primaryAddr": primary}
        return {k: self._chal[k] for k in ("challengeId", "message", "signingAddr", "expiryTime")}

    async def register(self, primary_addr: str, signature: str) -> dict:
        c = self._chal
        if c is None or c["primaryAddr"] != primary_addr.lower():
            raise RuntimeError("register needs a challenge for this wallet first")
        why = self.budget.blocked(self.key, manual=True)
        if why:
            raise LoginDeferred(why)
        self.budget.record_login(self.key)
        device = DeviceKey.new()
        resp = await self._auth_call("/v3/auth/register", {
            "networkType": 0, "signingAddr": c["signingAddr"], "primaryAddr": c["primaryAddr"], "signature": signature,
            "expiryTime": c["expiryTime"], "challengeId": c["challengeId"], "chainId": CHAIN_ID, "rememberMe": True,
            "devicePublicKey": device.public_b64()})
        resp.raise_for_status()
        j = resp.json()
        self._device, self._chal, self._needs_sig = device, None, False
        self._accounts.clear()
        self._take(j, device.pem(), c["primaryAddr"])
        log.info("vest %s: registered", self.key)
        return {k: j.get(k) for k in ("userId", "primaryAddr", "signingAddr", "isFunded", "isNewRegistration",
                                      "accessExpiresAtMs", "refreshExpiresAtMs")}

    def _take(self, j: dict, device_pem: str, primary_addr: str) -> None:
        """Keep the user token in memory; the refresh side goes to the secrets store."""
        self._user = (j["accessToken"], int(j["accessExpiresAtMs"]))
        secrets_store.set_credentials(
            self.key, primary_addr=primary_addr, refresh_token=j["refreshToken"], refresh_token_id=j["refreshTokenId"],
            refresh_expires_ms=int(j.get("refreshExpiresAtMs") or self.refresh_expires_ms), device_pem=device_pem)

    # -- renewal -----------------------------------------------------------------------------------------------
    async def _refresh(self) -> None:
        c = self._creds()
        if self.needs_signature:
            raise NeedsSignature(f"{self.key}: sign with the wallet again")
        # Routine refreshes (every ~15 min) are not booked as logins (they would fill the hourly cap): the cool-down and
        # the failure backoff still apply.
        why = self.budget.blocked(self.key)
        if why:
            raise LoginDeferred(why)
        device = self._device or DeviceKey.from_pem(c["device_pem"])
        resp = await self._auth_call("/v3/auth/refresh", {
            "refreshToken": c["refresh_token"], "requestId": str(uuid.uuid4()),
            "deviceSignature": device.sign_refresh(c["refresh_token_id"])}, ok_codes=(200, 401, 403))
        if resp.status_code in (401, 403):
            self._needs_sig = True
            self._user = None
            raise NeedsSignature(f"{self.key}: refresh rejected, sign with the wallet again")
        resp.raise_for_status()
        self._device = device
        self._take(resp.json(), c["device_pem"], c["primary_addr"])
        log.debug("vest %s: refreshed", self.key)

    async def user_token(self) -> str:
        if self._user and self._user[1] - _now_ms() > RENEW_LEFT_MS:
            return self._user[0]
        async with self._user_lock:
            if not (self._user and self._user[1] - _now_ms() > RENEW_LEFT_MS):    # a sibling may have refreshed
                await self._refresh()
            return self._user[0]

    async def account_token(self, account_id: str) -> str:
        have = self._accounts.get(account_id)
        if have and have[1] - _now_ms() > RENEW_LEFT_MS:
            return have[0]
        async with self._acct_lock:
            have = self._accounts.get(account_id)
            if have and have[1] - _now_ms() > RENEW_LEFT_MS:
                return have[0]
            resp = await self._send("POST", "/v3/auth/account-token", json={"accountId": account_id},
                                    headers={"Authorization": f"Bearer {await self.user_token()}"})
            resp.raise_for_status()
            j = resp.json()
            self._accounts[account_id] = (j["accessToken"], int(j["accessExpiresAtMs"]))
            return j["accessToken"]

    # -- calls -------------------------------------------------------------------------------------------------
    async def request(self, method: str, path: str, *, account_id: str | None = None, **kw) -> httpx.Response:
        """Send with the user's (or the account's) Bearer. A 401 mints a fresh token and resends ONCE; a timeout, a 5xx
        or anything else is raised as it is, never resent (an order must not go twice)."""
        extra = kw.pop("headers", {})
        for attempt in (0, 1):
            tok = await (self.account_token(account_id) if account_id else self.user_token())
            resp = await self._send(method, path, headers={**extra, "Authorization": f"Bearer {tok}"}, **kw)
            if resp.status_code != 401 or attempt:
                resp.raise_for_status()
                return resp
            if account_id:
                self._accounts.pop(account_id, None)
            else:
                self._user = None
