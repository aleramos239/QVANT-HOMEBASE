"""python -m homebase.labrun [--charts http://127.0.0.1:8852] [--root <store root>]

The runner of promoted Lab strategies (labrun/host.py), SHADOW only: it reads the chart service's tick stream and
writes the store. It places no order and opens no other connection; a --charts that is not this machine is refused.
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlsplit

from . import host

CHARTS = "http://127.0.0.1:8852"
LOCAL = ("127.0.0.1", "localhost")
DESK_PORT = 8850                 # the trading app: never ours to talk to


def local_url(url: str) -> str:
    """The chart service's address, or ValueError: http, 127.0.0.1 or localhost, a port that is not the desk's."""
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        raise ValueError("not a URL") from None
    if u.scheme != "http" or u.hostname not in LOCAL or "@" in u.netloc or u.path not in ("", "/") or u.query or u.fragment:
        raise ValueError("it must be http://127.0.0.1:<port> or http://localhost:<port>")
    if port == DESK_PORT:
        raise ValueError(f"port {DESK_PORT} is the desk: the runner never talks to it")
    return f"http://{u.netloc}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.labrun")
    ap.add_argument("--charts", default=CHARTS, help="the chart service on this machine")
    ap.add_argument("--root", default=None, help="the store of promoted strategies (default ~/.homebase/desklab)")
    a = ap.parse_args(argv)
    try:
        charts = local_url(a.charts)
    except ValueError as e:
        ap.error(f"--charts {a.charts}: {e}")
    host.run(charts, a.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
