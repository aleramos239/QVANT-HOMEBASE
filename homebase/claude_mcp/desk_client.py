"""The HTTP client for the desk's own API (:8850) -- loopback only, an EXACT allowlist of routes.

Mirrors client.py's Client (same urllib plumbing, same Origin-header trick to pass the desk's
WriteGuard) but with a stricter check: an allowed PREFIX is not enough for the desk (most of its
routes place orders, flatten or kill), so this client refuses any path that is not exactly one of
ALLOWED_GET / ALLOWED_POST. Adding a route here is a deliberate, reviewable one-line change --
never widen it to a prefix.

How a non-browser caller passes the desk's WriteGuard (homebase/desk_api.py, homebase/netguard.py):
  * Host: urllib sends `Host: 127.0.0.1:8850` itself -- on netguard's loopback allowlist;
  * Origin: we send `Origin: http://127.0.0.1:<port>` -- a loopback origin, which the guard accepts;
  * JSON writes: every POST carries `Content-Type: application/json`.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .client import ToolError

DEFAULT_URL = "http://127.0.0.1:8850"
ENV = "HOMEBASE_DESK_URL"
LOOPBACK = ("127.0.0.1", "localhost")

# The entire attack surface of this module: nothing else the desk exposes is ever reachable
# through it. No order, flatten, kill, arm/disarm, book or strategy/chart-trading route here.
ALLOWED_GET = frozenset({"/api/status", "/api/journal"})
ALLOWED_POST = frozenset({"/api/accounts/reconnect", "/api/accounts/remove"})


def base_url() -> str:
    url = os.environ.get(ENV) or DEFAULT_URL
    p = urllib.parse.urlsplit(url)
    if p.scheme != "http" or p.hostname not in LOOPBACK or p.path not in ("", "/"):
        raise ToolError(f"{ENV} must be http://127.0.0.1:<port> (got {url!r})")
    return f"http://{p.hostname}:{p.port or 80}"


class DeskClient:
    def __init__(self, url: str | None = None, timeout: float = 15.0):
        self.url = url or base_url()
        self.timeout = timeout

    def _req(self, method: str, path: str, params: dict | None = None, body=None):
        allowed = ALLOWED_GET if method == "GET" else ALLOWED_POST
        if path not in allowed:
            raise ToolError(f"refused: {path} is not an allowed desk route")
        url = self.url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = None
        headers = {"Accept": "application/json", "Origin": self.url}
        if method != "GET":
            data = json.dumps({} if body is None else body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read() or b"{}").get("detail") or ""
            except (ValueError, AttributeError):
                pass
            if isinstance(detail, list):          # FastAPI's 422 shape
                detail = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
            raise ToolError(f"{e.code}: {detail or e.reason}") from None
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ToolError(f"the desk at {self.url} is not reachable ({reason}). "
                            "Is Homebase running?") from None
        try:
            return json.loads(raw or b"null")
        except ValueError:
            raise ToolError(f"{path}: the desk answered something that is not JSON") from None

    def get(self, path: str, params: dict | None = None):
        return self._req("GET", path, params=params)

    def post(self, path: str, body=None):
        return self._req("POST", path, body=body)
