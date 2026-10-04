"""Which Host / Origin may WRITE to the desk (Task 5b; controller ruling P4).

One shared allowlist: loopback (127.0.0.1, localhost, [::1]) plus the
optional `allowed_hosts` in config.json — exact hostnames or IPs, e.g. a
Tailscale MagicDNS name or a 100.x address, if the desk is ever published
that way. Nothing else: no wildcard, no suffix match. A DNS-rebinding page
(evil.example resolving to 127.0.0.1) arrives with Host: evil.example and
is refused; `localhost.evil.com` and `127.0.0.1.nip.io` are other names.

Pure functions, no I/O: the desk's guard (desk_api.WriteGuard), its
/api/chart-trading check and the chart service's proxy (Task 8) all call
these with an allowlist built by `allowlist()`. `refusal()` is the combined
check (Host on every method; Origin + JSON on writes); `require_json=False`
turns it into Host + Origin only, for a body-less write such as the chart
page's DELETE /api/layouts/…; `host_allowed()` alone is the Host-only check.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Iterable, Optional

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# a hostname or IPv4 (letters, digits, '-' and '.', no empty label) or a
# bracketed IPv6 literal; then an optional :port. Matched on the lowercased
# header as a whole: whitespace, userinfo, paths and trailing dots never pass.
_NAME = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
_HOST = re.compile(rf"(?:\[(?P<v6>[0-9a-f:.]+)\]|(?P<name>{_NAME}))(?::(?P<port>[0-9]{{1,5}}))?")
_NAME_RE = re.compile(_NAME)
_ORIGIN = re.compile(r"(?P<scheme>https?)://(?P<host>[^/?#@\s]+)")


def allowlist(extra: Optional[Iterable] = None) -> frozenset:
    """LOOPBACK plus every usable entry of `extra` (config's allowed_hosts),
    lowercased and stripped. An entry that could never equal a Host's
    hostname part (not a string, empty, a port, a wildcard, a space…) is
    dropped rather than guessed at."""
    out = set(LOOPBACK)
    if not isinstance(extra, (list, tuple, set, frozenset)):
        return frozenset(out)                 # a malformed config value opens nothing
    for e in extra:
        n = clean_entry(e)
        if n:
            out.add(n)
    return frozenset(out)


def _v6(text: str) -> Optional[str]:
    """An IPv6 literal in its one canonical spelling, or None."""
    try:
        return ipaddress.IPv6Address(text).compressed
    except ValueError:
        return None


def clean_entry(e) -> Optional[str]:
    """One allowed_hosts entry as the allowlist holds it (a hostname or IPv4
    lowercased, an IPv6 address unbracketed and canonical), or None."""
    if not isinstance(e, str):
        return None
    n = e.strip().lower()
    if ":" in n:
        return _v6(n)
    return n if _NAME_RE.fullmatch(n) else None


def host_name(host: Optional[str]) -> Optional[str]:
    """The hostname part of a Host header value (IPv6 without brackets), or
    None when the value is not exactly `name[:port]` / `[v6][:port]`."""
    if not host:
        return None
    m = _HOST.fullmatch(host.lower())
    if m is None or (m.group("port") is not None and int(m.group("port")) > 65535):
        return None
    return _v6(m.group("v6")) if m.group("v6") is not None else m.group("name")


def host_allowed(host_header: Optional[str], allowed: frozenset) -> bool:
    """Exact, case-insensitive match of the Host's hostname part (an optional
    port is ignored). A missing Host is refused."""
    name = host_name(host_header)
    return name is not None and name in allowed


def origin_allowed(origin: Optional[str], allowed: frozenset) -> bool:
    """An Origin header is `http(s)://host[:port]` and nothing more; its
    hostname must be on the allowlist. `null`, file:, a path, userinfo or an
    empty value are refused."""
    if not origin:
        return False
    # The port is ignored: any page served from an allowed host (e.g. the
    # chart service on :8852) may write. That is safe ONLY while the response
    # carries no CORS header -- no page elsewhere can then read it, even if
    # its write goes through. A route that DOES need to answer another
    # origin (desk-settings plan: charts/paperbook.py's DESK_ORIGINS, shared
    # by /api/settings, /api/status and /api/paper/accounts*) must add its
    # OWN exact-origin check (paperbook.desk_origin_refusal) in front of this
    # one and only emit the CORS header for that exact match -- never widen
    # this allowlist-by-host check itself to stand in for it.
    m = _ORIGIN.fullmatch(origin.lower())
    return m is not None and host_allowed(m.group("host"), allowed)


def is_json(content_type: Optional[str]) -> bool:
    """Content-Type is application/json, parameters allowed (`; charset=…`).
    A cross-site page can send text/plain, form or multipart bodies without
    a CORS preflight — never application/json."""
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() == "application/json"


def refusal(method: str, headers, allowed: frozenset, *,
            require_json: bool = True) -> Optional[tuple[int, str]]:
    """(status, error) when a request must be refused, else None.
    `headers` are raw ASGI (name, value) byte pairs. In this order:
      * EVERY method: exactly one Host, on the allowlist       -> 403
        (a DNS-rebound page must not even READ, e.g. the book or the journal);
      * GET/HEAD/OPTIONS stop here;
      * an Origin, when sent: exactly one, on the allowlist     -> 403
      * require_json: exactly one Content-Type, application/json -> 415
    A guarded header sent twice is ambiguous and refused."""
    seen: dict[bytes, list[str]] = {b"host": [], b"origin": [], b"content-type": []}
    for k, v in headers:
        k = k.lower()
        if k in seen:
            seen[k].append(v.decode("latin-1"))
    host, origin, ctype = seen[b"host"], seen[b"origin"], seen[b"content-type"]
    if len(host) != 1 or not host_allowed(host[0], allowed):
        return 403, "host not allowed"
    if method.upper() in SAFE_METHODS:
        return None
    if origin and (len(origin) != 1 or not origin_allowed(origin[0], allowed)):
        return 403, "origin not allowed"
    if require_json and (len(ctype) != 1 or not is_json(ctype[0])):
        return 415, "send JSON (Content-Type: application/json)"
    return None
