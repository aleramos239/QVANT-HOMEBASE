"""The HTTP client for the chart service (:8852) -- loopback only, a fixed path prefix (default
/api/tester/*; desk_tools.py's export client passes /api/export/* -- still the same chart
service, never the desk).

How a non-browser caller passes the chart service's guards (homebase/charts/server.py):
  * HostGuard + tester_api.host_ok: urllib sends `Host: 127.0.0.1:8852` itself -- on netguard's loopback
    allowlist and matching host_ok's `127.0.0.1(:port)` rule;
  * browser_write_ok (origin_ok): we send `Origin: http://127.0.0.1:<port>` -- a loopback origin, which
    origin_ok accepts (a missing Origin would pass too: "not a browser");
  * JSON writes: every POST carries `Content-Type: application/json` (POST /api/tester/show requires it).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8852"
ENV = "HOMEBASE_CHARTS_URL"
LOOPBACK = ("127.0.0.1", "localhost")
PREFIX = "/api/tester/"


class ToolError(Exception):
    """A failure to report to Claude as the tool's result (isError), message as is."""


def base_url() -> str:
    url = os.environ.get(ENV) or DEFAULT_URL
    p = urllib.parse.urlsplit(url)
    if p.scheme != "http" or p.hostname not in LOOPBACK or p.path not in ("", "/"):
        raise ToolError(f"{ENV} must be http://127.0.0.1:<port> (got {url!r})")
    return f"http://{p.hostname}:{p.port or 80}"


class Client:
    def __init__(self, url: str | None = None, timeout: float = 60.0, prefix: str | tuple = PREFIX):
        self.url = url or base_url()
        self.timeout = timeout
        self.prefix = prefix   # str or tuple of allowed path prefixes (str.startswith takes either)

    def _req(self, method: str, path: str, body=None):
        if not path.startswith(self.prefix):
            raise ToolError(f"refused: {path} is not an allowed route")
        data = None
        headers = {"Accept": "application/json", "Origin": self.url}
        if method != "GET":
            data = json.dumps({} if body is None else body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
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
            raise ToolError(f"the chart service at {self.url} is not reachable ({reason}). "
                            "Is the Homebase chart service running?") from None
        try:
            return json.loads(raw or b"null")
        except ValueError:
            raise ToolError(f"{path}: the chart service answered something that is not JSON") from None

    def get(self, path: str):
        return self._req("GET", path)

    def post(self, path: str, body=None):
        return self._req("POST", path, body)
