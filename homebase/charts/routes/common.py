"""Pure helpers the route modules share: the Origin rule, the JSON files, the browser-write check."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from ...core import atomic
from ...core.jsonio import read_dict as read_json  # noqa: F401 -- the route modules and server.py import it from here

LOCAL_HOSTS = ("localhost", "127.0.0.1")


def origin_ok(origin: str | None, host: str | None) -> bool:
    """May a page from `origin` open /ws on `host`? Browsers apply no CORS
    to websocket handshakes, so without this any site open in the desk
    machine's browser could drive the chart process. Allowed: this
    service's own host, localhost, and no Origin at all (not a browser)."""
    if origin is None:
        return True
    try:
        o, h = urlsplit(origin).hostname, urlsplit("//" + (host or "")).hostname
    except ValueError:                  # e.g. a malformed IPv6 literal
        return False
    return o is not None and (o in LOCAL_HOSTS or o == h)


def write_json(path: Path, data: dict | list) -> None:
    """Via a temp file + atomic rename: a crash or a full disk mid-write
    must never tear the file (torn, it reads back as {} and the next
    save would wipe everything in it)."""
    atomic.write_text(path, json.dumps(data, indent=2), tmp=path.with_name(path.name + ".tmp"))

def read_json_list(path: Path) -> list:
    try:
        v = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return v if isinstance(v, list) else []


def browser_write_ok(request: Request) -> None:
    """Browsers send a cross-site PUT/DELETE after a preflight that this
    app never answers, but a simple no-CORS request could still reach
    us; refuse any write from a page that is not this service's own
    (same rule as the /ws handshake).

    Desk-settings plan: /api/settings' PUT and /api/paper/accounts*'s
    writes now ALSO answer the desk page's exact origin with a CORS
    header, so "no CORS request could still reach us" is no longer true
    for those two routes specifically -- they add their own exact-origin
    check (desk_origin_refusal) and only emit the header for that exact
    match, in front of this same-origin check, rather than loosening it."""
    if not origin_ok(request.headers.get("origin"), request.headers.get("host")):
        raise HTTPException(403, "writes from another site are refused")
