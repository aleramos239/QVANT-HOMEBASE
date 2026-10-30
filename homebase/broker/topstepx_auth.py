"""TopstepX (Topstep) session: logs in the way the topstepx.com website does (username + password, no paid API key).

The token lives in memory only; the store holds just the username and password. It renews itself before it runs out, and a
401 re-logs in once. A one-time code request (`NeedsCode`) is the owner's to answer: `login(code=...)`.

The password, the token and the Authorization header are never logged, never in `repr`, never in an exception's text.

The answer shapes below come from reading the site's code and are NOT yet confirmed against the live API: each guess is one
constant or one small function, so a correction touches one place.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time

import httpx

from ..store import secrets_store
from .login_budget import LoginBudget, LoginDeferred
from .tradovate_auth import USER_AGENT

log = logging.getLogger(__name__)

BASE = "https://userapi.topstepx.com"
HUB_URL = "wss://userapi.topstepx.com/hubs/account"
HEADERS = {"Origin": "https://topstepx.com", "Referer": "https://topstepx.com/", "User-Agent": USER_AGENT,
           "Accept": "application/json"}
RENEW_LEFT_S = 600              # a token with less than this left is renewed before use (room for a retry)
TOKEN_TTL_S = 23 * 3600         # when the token is not a JWT (or has no exp)
TOKEN_FIELD = "token"           # unconfirmed: the token's name in the /Login answer
USER_ID_FIELD = "userId"        # unconfirmed
_CODE_ASKED = re.compile(r"verification code|one-time code|enter (the |your )?code|code (was )?sent|two-factor|2fa", re.I)


class NeedsCode(RuntimeError):
    """TopstepX wants a one-time code for this login."""


class TsxLoginFailed(RuntimeError):
    """Wrong username / password. The message is TopstepX's own words, never the password."""


def _needs_code(answer: dict) -> bool:
    """Unconfirmed shape: no token, and a code-request key is set (error / status keys never count: `errorCode: 3` is a
    bad password) or the error message asks for a code in so many words ("error code 5" does not)."""
    if answer.get(TOKEN_FIELD):
        return False
    for k, v in answer.items():
        k = k.lower()
        if v and ("code" in k or "twofactor" in k) and "error" not in k and "status" not in k:
            return True
    return bool(_CODE_ASKED.search(str(answer.get("errorMessage") or "")))


def _expiry(token: str) -> float:
    """The JWT's `exp` (epoch seconds) when the token decodes as one, else now + 23 h."""
    try:
        seg = token.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        return time.time() + TOKEN_TTL_S


class TsxSession:
    def __init__(self, key: str, *, http: httpx.AsyncClient | None = None, budget: LoginBudget | None = None):
        self.key = key
        self._http = http
        self._own_http = http is None
        self.budget = budget                  # the desk sets it after construction; None = no budget checks
        self.journal = lambda event, **kw: None   # the desk sets it later
        self.hub = None                       # the one account socket for this login (a later task creates it)
        self.listeners: list = []             # adapters on this login register here (a later task)
        self.taken = 0                        # times TopstepX ended the session (a later task adds to it)
        self.user_id: int | None = None
        self.expires_at = 0.0
        self.lost: Exception | None = None    # why a kick's re-login failed (deferred, needs a code): the supervisor shows it
        self._token: str | None = None
        self._renew_left = RENEW_LEFT_S       # renew when less than this is left (min(600 s, half the token's life))
        self._lock = asyncio.Lock()           # one login at a time

    def __repr__(self) -> str:
        return f"TsxSession(key={self.key!r}, token={'held' if self._token else 'none'})"

    async def aclose(self) -> None:
        if self._own_http and self._http is not None:
            await self._http.aclose()

    async def _send(self, method: str, path: str, **kw) -> httpx.Response:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=15.0)
        kw["headers"] = {**HEADERS, **kw.get("headers", {})}
        return await self._http.request(method, BASE + path, **kw)

    # -- login -------------------------------------------------------------------------------------------------
    async def login(self, code: str | None = None) -> None:
        c = secrets_store.get_credentials(self.key) or {}
        if not c.get("username") or not c.get("password"):
            raise TsxLoginFailed(f"{self.key}: no username / password stored")
        body = {"userName": c["username"], "password": c["password"]}
        if code:
            body["code"] = code
        resp = await self._send("POST", "/Login", json=body)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()           # its message carries the status and URL only, no body
        try:
            answer = resp.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise TsxLoginFailed(f"login answer unreadable (status {resp.status_code})")
        if _needs_code(answer):
            raise NeedsCode(f"{self.key}: TopstepX wants a one-time code")
        token = answer.get(TOKEN_FIELD)
        if not isinstance(token, str) or not token:
            why = str(answer.get("errorMessage") or f"status {resp.status_code}").replace(c["password"], "***")
            raise TsxLoginFailed(why)
        self._token, self.expires_at = token, _expiry(token)
        # a short-lived token renews at half its life, not on every call
        self._renew_left = min(RENEW_LEFT_S, max(0.0, (self.expires_at - time.time()) / 2))
        self.user_id = answer.get(USER_ID_FIELD)
        self.lost = None
        log.info("topstepx %s: logged in", self.key)

    async def relogin(self, why: str) -> None:
        """A login through the budget: refused (LoginDeferred) when the cap, backoff or a 429 cool-down says so."""
        b = self.budget
        if b is not None:
            blocked = b.blocked(self.key, first=self._token is None)
            if blocked:
                raise LoginDeferred(blocked)
            b.record_login(self.key)
        log.info("topstepx %s: login (%s)", self.key, why)
        try:
            await self.login()
        except Exception as e:
            if b is not None:
                b.login_result(self.key, e)
            raise
        if b is not None:
            b.login_result(self.key)

    async def token(self) -> str:
        if self._token and self.expires_at - time.time() > self._renew_left:
            return self._token
        async with self._lock:
            if not (self._token and self.expires_at - time.time() > self._renew_left):    # a sibling may have renewed
                await self.relogin("renew")
            return self._token

    # -- calls -------------------------------------------------------------------------------------------------
    async def request(self, method: str, path: str, **kw) -> httpx.Response:
        """Send with the Bearer. A 401 logs in again ONCE and resends once; the second answer is returned as it is.
        A timeout or a 5xx is never resent here (an order must not go twice)."""
        extra = kw.pop("headers", {})
        for attempt in (0, 1):
            tok = await self.token()
            resp = await self._send(method, path, headers={**extra, "Authorization": f"Bearer {tok}"}, **kw)
            if resp.status_code != 401 or attempt:
                return resp
            async with self._lock:
                if self._token == tok:        # a sibling that already re-logged in has replaced it
                    await self.relogin("401")
