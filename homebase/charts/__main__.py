"""python -m homebase.charts [--replay YYYY-MM-DD [--speed 20] [--start 09:25]] [--port 8852]"""
from __future__ import annotations

import argparse
import datetime as dt

import uvicorn

from . import DEFAULT_ROOTS, PORT
from .calendar import http_get
from .server import create_app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.charts")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--roots", default=",".join(DEFAULT_ROOTS))
    ap.add_argument("--replay", metavar="YYYY-MM-DD",
                    help="play an archived session instead of the live feed (records nothing)")
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--start", default="09:25", help="replay start, ET HH:MM")
    a = ap.parse_args(argv)
    app = create_app(roots=[r for r in a.roots.split(",") if r],
                     replay=dt.date.fromisoformat(a.replay) if a.replay else None,
                     speed=a.speed, start_et=dt.time.fromisoformat(a.start),
                     # a replay never fetches ForexFactory: the cached weeks on disk are served as is
                     calendar_fetch=None if a.replay else http_get)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
