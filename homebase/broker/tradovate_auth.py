"""Tradovate web-client-compatible auth — no browser, no paid API plan.

Replicates the auth flow used by trader.tradovate.com: HMAC-SHA256 request
signing + the web client's password-obfuscation routine. Constants were
extracted from the web bundle (2026-05-26); re-extract if login starts failing.

Usage:
    auth = TradovateAuth(env="demo")          # or "live"
    auth.login(username="...", password="...")
    auth.access_token                         # bearer for REST + WS authorize
    auth.ensure_valid()                       # renew if near expiry
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ----------------------------------------------------------------------------
# Constants extracted from trader.tradovate.com (2026-05-26)
# ----------------------------------------------------------------------------
HMAC_KEY = "035a1259-11e7-485a-aeae-9b6016579351"   # verified live 2026-09-16
CID = "1"
APP_ID = "tradovate_trader(web)"
APP_VERSION = "3.260911.0"   # re-extracted 2026-09-16 (was 3.260522.0)
# The five fields concatenated to form the HMAC message, in this exact order:
HMAC_FIELDS = ["chl", "deviceId", "name", "password", "appId"]

ENDPOINTS = {
    "live": "https://live.tradovateapi.com/v1",
    "demo": "https://demo.tradovateapi.com/v1",
}

WS_ENDPOINTS = {
    "live": "wss://live.tradovateapi.com/v1/websocket",
    "demo": "wss://demo.tradovateapi.com/v1/websocket",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ----------------------------------------------------------------------------
# Cryptographic helpers (the reverse-engineered bits)
# ----------------------------------------------------------------------------
def encrypt_password(name: str, password: str) -> str:
    """Replicate the web client's `St` password-obfuscation function.

        shift   = len(name) % len(password)
        rotated = password[shift:] + password[:shift]
        result  = base64(reverse(rotated))
    """
    if not password:
        return ""
    shift = len(name) % len(password)
    rotated = password[shift:] + password[:shift]
    reversed_str = rotated[::-1]
    return base64.b64encode(reversed_str.encode("utf-8")).decode("ascii")


def make_challenge() -> str:
    """Web client's `chl` field: `Date.now() - 1581e9` (ms since a 2020 epoch)."""
    return str(int(time.time() * 1000) - 1_581_000_000_000)


def compute_sec(payload: dict) -> str:
    """HMAC-SHA256 over HMAC_FIELDS, using the RAW (un-obfuscated) password."""
    message = "".join(str(payload.get(f, "") or "") for f in HMAC_FIELDS)
    h = hmac.new(HMAC_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
    return h.hexdigest()


# ----------------------------------------------------------------------------
# Device ID — stable per-account UUID, persisted to disk
# ----------------------------------------------------------------------------
def get_or_create_device_id(persist_path: Path) -> str:
    if persist_path.exists():
        try:
            data = json.loads(persist_path.read_text())
            if "device_id" in data:
                return data["device_id"]
        except Exception:
            pass
    device_id = str(uuid.uuid4())
    persist_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if persist_path.exists():
        try:
            existing = json.loads(persist_path.read_text())
        except Exception:
            existing = {}
    existing["device_id"] = device_id
    persist_path.write_text(json.dumps(existing, indent=2))
    try:
        persist_path.chmod(0o600)   # owner-only: device identity, not world-readable
    except OSError:
        pass
    return device_id


# ----------------------------------------------------------------------------
# HTTP helper
# ----------------------------------------------------------------------------
def http_post_json(url: str, body: dict, headers: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Origin": "https://trader.tradovate.com",
        "Referer": "https://trader.tradovate.com/",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8")
        except Exception:
            body_text = ""
        raise RuntimeError(f"HTTP {e.code} from {url}: {body_text}") from e


def http_get_json(url: str, headers: Optional[dict] = None):
    """GET JSON (used for read-only REST calls like /account/list)."""
    hdrs = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8")
        except Exception:
            body_text = ""
        raise RuntimeError(f"HTTP {e.code} from {url}: {body_text}") from e


# ----------------------------------------------------------------------------
# Auth state + flows
# ----------------------------------------------------------------------------
@dataclass
class TradovateTokens:
    access_token: str
    md_access_token: str = ""
    expiration_time: str = ""  # ISO8601 from server
    user_id: int = 0
    user_status: str = ""
    has_live: bool = False
    has_funded: bool = False
    has_sim_plus: bool = False
    has_market_data: bool = False
    name: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def expires_at_unix(self) -> float:
        if not self.expiration_time:
            return 0
        try:
            from datetime import datetime, timezone
            ts = self.expiration_time.rstrip("Z")
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0


class TradovateAuth:
    def __init__(
        self,
        env: str = "demo",
        token_persist_path: Optional[Path] = None,
        device_persist_path: Optional[Path] = None,
    ):
        if env not in ENDPOINTS:
            raise ValueError(f"env must be 'live' or 'demo', got {env!r}")
        self.env = env
        self.base_url = ENDPOINTS[env]
        self.ws_url = WS_ENDPOINTS[env]
        here = Path(__file__).resolve().parent
        self.token_persist_path = token_persist_path or (here / "tokens.json")
        self.device_persist_path = device_persist_path or (here / "device.json")
        self.device_id = get_or_create_device_id(self.device_persist_path)
        self.tokens: Optional[TradovateTokens] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        # refresh()'s login fallback asks this first (login_budget.LoginGuard: allow(err)
        # -> bool, done(err)); None = unbudgeted, as before
        self.login_guard = None

    @property
    def access_token(self) -> Optional[str]:
        return self.tokens.access_token if self.tokens else None

    def build_login_payload(self, username: str, password: str) -> dict:
        payload = {
            "name": username,
            "password": password,        # raw — used for HMAC, replaced before send
            "appId": APP_ID,
            "appVersion": APP_VERSION,
            "deviceId": self.device_id,
            "cid": CID,
            "chl": make_challenge(),
        }
        payload["sec"] = compute_sec(payload)
        payload["password"] = encrypt_password(username, password)
        payload["enc"] = True
        # fields the 2026-09 web client also sends (all optional per its own
        # validators, but match it byte-for-byte; sec covers only HMAC_FIELDS)
        payload["userAgent"] = USER_AGENT
        payload["locale"] = "en"
        payload["organization"] = ""
        payload["hibpCheck"] = False
        return payload

    def login(self, username: str, password: str) -> TradovateTokens:
        self._username = username
        self._password = password
        payload = self.build_login_payload(username, password)
        url = f"{self.base_url}/auth/accesstokenrequest"
        resp = http_post_json(url, payload)
        if not resp.get("accessToken"):
            # keep the WHOLE response visible: errorText alone hides the
            # p-ticket / p-captcha / p-time anti-bot flags
            raise RuntimeError(f"Login failed: {json.dumps(resp)[:400]}")
        self.tokens = TradovateTokens(
            access_token=resp["accessToken"],
            md_access_token=resp.get("mdAccessToken", ""),
            expiration_time=resp.get("expirationTime", ""),
            user_id=resp.get("userId", 0),
            user_status=resp.get("userStatus", ""),
            has_live=resp.get("hasLive", False),
            has_funded=resp.get("hasFunded", False),
            has_sim_plus=resp.get("hasSimPlus", False),
            has_market_data=resp.get("hasMarketData", False),
            name=resp.get("name", username),
            raw=resp,
        )
        self._persist_tokens()
        return self.tokens

    def list_accounts(self) -> list:
        """Every trading account under this login (REST /account/list).

        One Tradovate login commonly fronts many accounts (a prop firm hands you
        20 under one username); this enumerates them so the app can let the user
        pick which to copy. Returns the raw account entities (id, name, nickname,
        active, ...). Requires a prior login().
        """
        if not self.tokens or not self.tokens.access_token:
            raise RuntimeError("not logged in — call login() first")
        url = f"{self.base_url}/account/list"
        resp = http_get_json(
            url, headers={"Authorization": f"Bearer {self.tokens.access_token}"})
        return resp if isinstance(resp, list) else []

    def renew(self) -> TradovateTokens:
        if not self.tokens or not self.tokens.access_token:
            raise RuntimeError("Cannot renew — no access token. Call login() first.")
        url = f"{self.base_url}/auth/renewaccesstoken"
        resp = http_post_json(
            url, {}, headers={"Authorization": f"Bearer {self.tokens.access_token}"}
        )
        if not resp.get("accessToken"):
            err = resp.get("errorText") or json.dumps(resp)[:500]
            raise RuntimeError(f"Renew failed: {err}")
        self.tokens.access_token = resp["accessToken"]
        self.tokens.md_access_token = resp.get("mdAccessToken", self.tokens.md_access_token)
        self.tokens.expiration_time = resp.get("expirationTime", self.tokens.expiration_time)
        self.tokens.raw = resp
        self._persist_tokens()
        return self.tokens

    def refresh(self) -> TradovateTokens:
        """Renew now; if the renewal fails, log in again with the credentials
        this session logged in with (none remembered -> the renewal's error)."""
        try:
            return self.renew()
        except Exception as e:
            if self._username and self._password:
                guard = self.login_guard
                if guard is not None and not guard.allow(e):
                    raise        # the user's login budget says no: the renewal's error
                try:
                    tokens = self.login(self._username, self._password)
                except Exception as le:
                    if guard is not None:
                        guard.done(le)
                    raise
                if guard is not None:
                    guard.done(None)
                return tokens
            raise

    def ensure_valid(self, refresh_buffer_sec: float = 600,
                     now: Optional[float] = None) -> TradovateTokens:
        """Refresh when less than `refresh_buffer_sec` of the token's life is
        left at `now` (unix seconds; default the current time)."""
        if not self.tokens:
            raise RuntimeError("Not logged in. Call login() first.")
        now = time.time() if now is None else now
        if self.tokens.expires_at_unix - now < refresh_buffer_sec:
            return self.refresh()
        return self.tokens

    def _persist_tokens(self):
        if self.tokens is None:
            return
        data = {
            "env": self.env,
            "access_token": self.tokens.access_token,
            "md_access_token": self.tokens.md_access_token,
            "expiration_time": self.tokens.expiration_time,
            "user_id": self.tokens.user_id,
            "name": self.tokens.name,
            "user_status": self.tokens.user_status,
            "has_live": self.tokens.has_live,
            "has_funded": self.tokens.has_funded,
        }
        self.token_persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_persist_path.write_text(json.dumps(data, indent=2))
        try:
            self.token_persist_path.chmod(0o600)   # owner-only: holds live tokens
        except OSError:
            pass

    def load_tokens(self) -> Optional[TradovateTokens]:
        if not self.token_persist_path.exists():
            return None
        try:
            data = json.loads(self.token_persist_path.read_text())
        except Exception:
            return None
        if data.get("env") != self.env:
            return None
        self.tokens = TradovateTokens(
            access_token=data.get("access_token", ""),
            md_access_token=data.get("md_access_token", ""),
            expiration_time=data.get("expiration_time", ""),
            user_id=data.get("user_id", 0),
            name=data.get("name", ""),
            user_status=data.get("user_status", ""),
            has_live=data.get("has_live", False),
            has_funded=data.get("has_funded", False),
        )
        return self.tokens


def _selftest():
    out = encrypt_password("alice", "secret123")
    expected = base64.b64encode("erces321t".encode()).decode()
    assert out == expected, f"encrypt_password failed: {out} != {expected}"
    payload = {"chl": "1000", "deviceId": "abc", "name": "alice",
               "password": "secret123", "appId": "tradovate_trader(web)"}
    sec = compute_sec(payload)
    expected_msg = "1000abcalicesecret123tradovate_trader(web)"
    expected_sec = hmac.new(HMAC_KEY.encode(), expected_msg.encode(), hashlib.sha256).hexdigest()
    assert sec == expected_sec, f"compute_sec failed: {sec} != {expected_sec}"
    print("OK: crypto self-tests passed")


if __name__ == "__main__":
    _selftest()
