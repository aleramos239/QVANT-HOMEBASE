"""python -m homebase.labrun [--charts http://127.0.0.1:8852] [--root <store root>]
                          [--desk http://127.0.0.1:8850 [--desk-key <the Desk's lab.key>]]

The runner of promoted Lab strategies (labrun/host.py). Without --desk it is SHADOW only: it reads the chart service's
tick stream and writes the store; it places no order and opens no other connection. A --charts that is not this
machine is refused.

With --desk (Step B) a strategy that has accounts booked on the Desk is hosted in desk mode: its orders are sent to
the Desk's guarded intake (labrun/deskclient.py). The Desk must be this machine (127.0.0.1 or localhost, a port given)
and never the chart service's own address; anything else is refused at the start, in one line. --desk-key is the key
file the Desk writes (default: homebase/.state/lab.key of this checkout); it is only ever read, at each request, and
only when --desk is given.

One runner per store: it holds an exclusive lock on <store root>/runner.lock while it works, and a second one says so
in one line and exits 1 (two runners would write the same day files).
"""
from __future__ import annotations

import argparse
import fcntl
import sys
from pathlib import Path
from urllib.parse import urlsplit

from . import host, store

CHARTS = "http://127.0.0.1:8852"
LOCAL = ("127.0.0.1", "localhost")
DESK_PORT = 8850                 # the trading app: never ours to talk to
LOCK_FILE = "runner.lock"        # in the store root; the lock is the open file's, so it goes when the process goes
DESK_KEY = Path(__file__).resolve().parents[1] / ".state" / "lab.key"    # what the Desk writes (desk_api.LAB_KEY_FILE)


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


def desk_url(url: str, charts: str) -> str:
    """The Desk's address, or ValueError: http, 127.0.0.1 or localhost, a port, nothing else in it -- and not the
    chart service's own address (this machine has one of each name: the same port is the same address)."""
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        raise ValueError("not a URL") from None
    if (u.scheme != "http" or u.hostname not in LOCAL or port is None or "@" in u.netloc or u.path not in ("", "/")
            or u.query or u.fragment):
        raise ValueError("it must be http://127.0.0.1:<port> or http://localhost:<port>")
    if port == urlsplit(charts).port:
        raise ValueError("that is the chart service's own address")
    return f"http://{u.netloc}"


def only_runner(at=None):
    """The store's lock, held by the open file this returns (keep it; close it to let go) -- or None when another
    runner holds it."""
    d = store.root(at)
    d.mkdir(parents=True, exist_ok=True)
    fh = open(d / LOCK_FILE, "a")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    return fh


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.labrun")
    ap.add_argument("--charts", default=CHARTS, help="the chart service on this machine")
    ap.add_argument("--root", default=None, help="the store of promoted strategies (default ~/.homebase/desklab)")
    ap.add_argument("--desk", default=None, help="the Desk on this machine: strategies with accounts send it their orders")
    ap.add_argument("--desk-key", default=None, help="the Desk's key file for the runner (default homebase/.state/lab.key)")
    a = ap.parse_args(argv)
    try:
        charts = local_url(a.charts)
    except ValueError as e:
        ap.error(f"--charts {a.charts}: {e}")
    desk = None
    if a.desk is not None:
        try:
            desk = {"desk": desk_url(a.desk, charts), "desk_key": Path(a.desk_key) if a.desk_key else DESK_KEY}
        except ValueError as e:
            print(f"--desk {a.desk}: {e}. The runner did not start.", file=sys.stderr)
            return 2
    lock = only_runner(a.root)
    if lock is None:
        print(f"Another runner already holds this store ({store.root(a.root)}): this one stops.", file=sys.stderr)
        return 1
    try:
        if desk is None:
            host.run(charts, a.root)                 # shadow only, as it always was
        else:
            host.run(charts, a.root, **desk)
    finally:
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
