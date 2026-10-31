"""AlphaTrader (Alpha Futures) session: logs in the way futures.alphatrader.com does (email + password), keeps its tokens in
memory, renews them with the refresh token (free), and fetches the T4 credentials the trading socket logs in with.

The store holds just the email and password (key `atr:<email lower>`). The password, the tokens, the signed credential token
and the T4 password are never logged, never in `repr`, never in an exception's text.

Built offline from the site's code: every guessed value below is a named constant marked `# unconfirmed`, so the first real
login's corrections touch this block only.

Locking: `session.lock` is the one lock for Alpha login, refresh, credential fetch and T4 login. It is re-entrant for the
task that holds it: `login`, `access` (when it renews) and `request` (on a 401) take it themselves and simply carry on when
their caller already holds it, so a caller may hold `session.lock` around multi-step work without a deadlock.
`t4_creds` takes it through `request`; `t4_login_slot` and `aclose` do not need it.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
from dataclasses import dataclass

import httpx

from ..store import secrets_store
from .login_budget import LoginBudget, LoginDeferred
from .tradovate_auth import USER_AGENT

log = logging.getLogger(__name__)

BASE = "https://apiv2.alphatrader.com"
WS_URL = "wss://wss-sim.t4login.com/v1"
HEADERS = {"Origin": "https://futures.alphatrader.com", "Referer": "https://futures.alphatrader.com",
           "User-Agent": USER_AGENT, "Accept": "application/json"}
RENEW_LEFT_S = 600              # a token with less than this left is renewed before use (room for a retry)
TOKEN_TTL_S = 3600              # unconfirmed: when the access token is not a JWT (or has no exp)
LOGIN_PATH = "/api/v1/auth/login/"                  # unconfirmed
REFRESH_PATH = "/api/v1/auth/token/refresh/"        # unconfirmed
ME_PATH = "/api/v1/auth/me/"                        # unconfirmed
CRED_PATH = "/api/v1/t4/credentials/token/"         # unconfirmed
LOGIN_FIELDS = ("email", "password")                # unconfirmed: the login body's field names
CODE_FIELD = "code"                                 # unconfirmed: a one-time code goes in the login body
CODE_MARKERS = ("mfa", "verify", "verification", "two_factor", "two-factor", "2fa")   # unconfirmed: a code step's words
DATA_FIELD = "data"                                 # unconfirmed: the answer's envelope
TOKENS_FIELD = "tokens"                             # unconfirmed: inside it, or the envelope itself
ACCESS_FIELD = "access_token"                       # unconfirmed (the id token is the Bearer when this is absent)
REFRESH_FIELD = "refresh_token"                     # unconfirmed
ID_FIELD = "id_token"                               # unconfirmed
ERROR_FIELDS = ("message", "detail", "error")       # unconfirmed: where Alpha's own words sit in a failed answer
CRED_TOKEN_FIELD = "signed_credential_token"        # in `data` of the CRED_PATH answer
T4_FIELDS = ("t4_firm", "t4_username", "t4_password", "t4_app_name", "t4_app_license")   # the credential JWT's payload


class NeedsCode(RuntimeError):
    """AlphaTrader wants a one-time code for this login."""


class AtrLoginFailed(RuntimeError):
    """Wrong email / password, or an answer that cannot be read. The message is Alpha's own words, never the password."""


@dataclass(repr=False)
class T4Creds:
    firm: str
    username: str
    password: str
    app_name: str
    app_license: str

    def __repr__(self) -> str:
        return f"T4Creds(firm={self.firm!r}, app_name={self.app_name!r})"


class _TaskLock(asyncio.Lock):
    """An asyncio.Lock that knows which task holds it, so that task can pass through it again."""
    owner = None

    async def acquire(self):
        await super().acquire()
        self.owner = asyncio.current_task()
        return True

    def release(self):
        self.owner = None
        super().release()


def _payload(token: str) -> dict:
    """A JWT's payload (the signature is not checked). ValueError when it is not one."""
    try:
        seg = token.split(".")[1]
        out = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
    except (IndexError, ValueError, AttributeError):
        raise ValueError("not a JWT") from None
    if not isinstance(out, dict):
        raise ValueError("not a JWT")
    return out


def _expiry(token: str) -> float:
    try:
        return float(_payload(token)["exp"])
    except (ValueError, KeyError, TypeError):
        return time.time() + TOKEN_TTL_S


def _tokens(answer) -> dict:
    """The token fields of a login / refresh answer: `data.tokens`, `data`, or the answer itself."""
    d = answer.get(DATA_FIELD) if isinstance(answer, dict) else None
    d = d if isinstance(d, dict) else answer
    t = d.get(TOKENS_FIELD) if isinstance(d, dict) else None
    return t if isinstance(t, dict) else d if isinstance(d, dict) else {}


def _json(resp: httpx.Response):
    try:
        return resp.json()
    except ValueError:
        return None


class AtrSession:
    def __init__(self, key: str, *, http: httpx.AsyncClient | None = None, budget: LoginBudget | None = None):
        self.key = key
        self._http = http
        self._own_http = http is None
        self.budget = budget                  # the desk sets it after construction; None = no budget checks
        self.journal = lambda event, **kw: None   # the desk sets it later
        self.lock = _TaskLock()               # see the module docstring
        self.taken = 0                        # times Alpha ended the T4 session (a later task adds to it)
        self.lost: str | None = None          # why the session is down (deferred, needs a code, refused): the card shows it
        self.expires_at = 0.0
        self._access: str | None = None
        self._refresh: str | None = None
        self._id: str | None = None

    def __repr__(self) -> str:
        return f"AtrSession(key={self.key!r}, token={'held' if self._access else 'none'})"

    async def aclose(self) -> None:
        if self._own_http and self._http is not None:
            await self._http.aclose()

    @contextlib.asynccontextmanager
    async def _held(self):
        if self.lock.owner is asyncio.current_task():
            yield
        else:
            async with self.lock:
                yield

    async def _send(self, method: str, path: str, **kw) -> httpx.Response:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=15.0)
        kw["headers"] = {**HEADERS, **kw.get("headers", {})}
        return await self._http.request(method, BASE + path, **kw)

    def _keep(self, tokens: dict) -> bool:
        access = tokens.get(ACCESS_FIELD) or tokens.get(ID_FIELD)
        if not isinstance(access, str) or not access:
            return False
        self._access, self.expires_at = access, _expiry(access)
        self._refresh = tokens.get(REFRESH_FIELD) or self._refresh
        self._id = tokens.get(ID_FIELD) or self._id
        return True

    def _fresh(self) -> bool:
        return bool(self._access) and self.expires_at - time.time() > RENEW_LEFT_S

    # -- login -------------------------------------------------------------------------------------------------
    async def login(self, code: str | None = None) -> None:
        """One password login, booked on the budget: refused (LoginDeferred) when the cap, backoff or a 429 cool-down says so."""
        async with self._held():
            b = self.budget
            if b is not None:
                blocked = b.blocked(self.key, first=self._access is None)
                if blocked:
                    raise LoginDeferred(blocked)
                b.record_login(self.key)
            try:
                await self._login(code)
            except NeedsCode:
                if b is not None:
                    b.login_result(self.key)      # a code request is not a failed password
                raise
            except Exception as e:
                if b is not None:
                    b.login_result(self.key, e)
                raise
            if b is not None:
                b.login_result(self.key)
            self.lost = None
            log.info("alphatrader %s: logged in", self.key)

    async def _login(self, code: str | None) -> None:
        c = secrets_store.get_credentials(self.key) or {}
        if not c.get("username") or not c.get("password"):
            raise AtrLoginFailed(f"{self.key}: no email / password stored")
        body = dict(zip(LOGIN_FIELDS, (c["username"], c["password"])))
        if code:
            body[CODE_FIELD] = code
        resp = await self._send("POST", LOGIN_PATH, json=body)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()           # its message carries the status and URL only, no body
        answer = _json(resp)
        if not isinstance(answer, dict):
            raise AtrLoginFailed(f"login answer unreadable (status {resp.status_code})")
        tokens = _tokens(answer)
        if not (tokens.get(ACCESS_FIELD) or tokens.get(ID_FIELD)):
            if any(m in json.dumps(answer).lower() for m in CODE_MARKERS):
                raise NeedsCode("AlphaTrader needs a code")
            why = next((str(answer[k]) for k in ERROR_FIELDS if answer.get(k)), f"status {resp.status_code}")
            raise AtrLoginFailed(why.replace(c["password"], "***")[:200])
        self._keep(tokens)

    async def _refresh_tokens(self) -> bool:
        """Renew with the refresh token (free, no budget). False when Alpha refuses it: it is dropped, never retried."""
        if not self._refresh:
            return False
        resp = await self._send("POST", REFRESH_PATH, json={REFRESH_FIELD: self._refresh})
        if resp.status_code == 200 and self._keep(_tokens(_json(resp))):
            return True
        self._refresh = None
        return False

    async def _renew(self) -> None:
        """The lock is held: refresh, else one password login through the budget."""
        if await self._refresh_tokens():
            self.lost = None
            return
        try:
            await self.login()
        except Exception as e:
            self.lost = str(e)
            raise

    async def access(self) -> str:
        if not self._fresh():
            async with self._held():
                if not self._fresh():             # a sibling may have renewed
                    await self._renew()
        return self._access

    # -- calls -------------------------------------------------------------------------------------------------
    async def request(self, method: str, path: str, **kw) -> httpx.Response:
        """Send with the Bearer. A 401 renews ONCE and resends once; the second answer is returned as it is.
        A timeout or a 5xx is never resent here (an order must not go twice)."""
        extra = kw.pop("headers", {})
        for attempt in (0, 1):
            tok = await self.access()
            resp = await self._send(method, path, headers={**extra, "Authorization": f"Bearer {tok}"}, **kw)
            if resp.status_code != 401 or attempt:
                return resp
            async with self._held():
                if self._access == tok:           # a sibling that already renewed has replaced it
                    await self._renew()

    async def t4_creds(self) -> T4Creds:
        """The credentials the T4 socket logs in with: fetched on each call, never kept."""
        resp = await self.request("POST", CRED_PATH)
        if resp.status_code != 200:
            raise AtrLoginFailed(f"T4 credentials refused (status {resp.status_code})")
        data = (_json(resp) or {}).get(DATA_FIELD)
        try:
            claims = _payload(data[CRED_TOKEN_FIELD])
            return T4Creds(*(str(claims[f]) for f in T4_FIELDS))
        except (ValueError, KeyError, TypeError):
            raise AtrLoginFailed("T4 credentials answer unreadable") from None

    async def t4_login_slot(self) -> None:
        """Book one budget slot for a T4 socket login (LoginDeferred when the budget says wait)."""
        b = self.budget
        if b is not None:
            blocked = b.blocked(self.key)
            if blocked:
                raise LoginDeferred(blocked)
            b.record_login(self.key)
